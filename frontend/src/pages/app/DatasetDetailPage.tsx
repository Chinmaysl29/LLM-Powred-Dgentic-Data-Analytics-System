import { useState, useEffect } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import {
  ArrowLeft,
  Table,
  FileCode,
  Activity,
  ShieldCheck,
  GitBranch,
  Network,
  Sparkles,
  BarChart3,
  HardDrive,
  Search,
  CheckCircle2,
  AlertTriangle,
  RotateCcw,
  GitCompare,
  Bot,
} from 'lucide-react';
import { apiClient } from '../../api/client';
import { datasetService } from '../../services/datasetService';
import PdfDocumentPanel from '../../components/datasets/PdfDocumentPanel';
import {
  formatFileSize,
  formatDate,
  formatDateTime,
  getExtension,
} from '../../datasetUtils';
import type {
  Dataset,
  DatasetPreview,
  ColumnMetadata,
  DatasetProfileData,
  DatasetQualityData,
  DatasetVersionItem,
  DatasetLineageNode,
} from '../../types/datasets';

type DetailTab = 'overview' | 'metadata' | 'profile' | 'quality' | 'versions' | 'lineage';

export default function DatasetDetailPage() {
  const { datasetId } = useParams<{ datasetId: string }>();
  const navigate = useNavigate();

  const [activeTab, setActiveTab] = useState<DetailTab>('overview');
  const [dataset, setDataset] = useState<Dataset | null>(null);
  const [preview, setPreview] = useState<DatasetPreview | null>(null);
  const [metadata, setMetadata] = useState<ColumnMetadata[]>([]);
  const [profile, setProfile] = useState<DatasetProfileData | null>(null);
  const [quality, setQuality] = useState<DatasetQualityData | null>(null);
  const [versions, setVersions] = useState<DatasetVersionItem[]>([]);
  const [lineage, setLineage] = useState<DatasetLineageNode[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState('');
  const [retry, setRetry] = useState(0);
  const [comparison, setComparison] = useState<{ rows_added: number; rows_removed: number; columns_added: string[]; columns_removed: string[] } | null>(null);
  const [comparisonError, setComparisonError] = useState('');
  const [comparisonLoading, setComparisonLoading] = useState(false);
  const [rollbackLoading, setRollbackLoading] = useState(false);

  // Preview table controls
  const [previewSearch, setPreviewSearch] = useState('');
  const [previewPage, setPreviewPage] = useState(0);
  const pageSize = 15;

  // Version rollback notification
  const [rollbackStatus, setRollbackStatus] = useState<string | null>(null);
  const [comparingVersions, setComparingVersions] = useState<boolean>(false);

  useEffect(() => {
    async function loadDatasetDetails() {
      if (!datasetId) { setError('Dataset identifier is missing.'); setIsLoading(false); return; }
      setIsLoading(true);
      setError('');
      try {
        const ds = await datasetService.getById(datasetId);
        setDataset(ds);

        // PDFs are documents, not canonical tables. Their indexing lifecycle
        // remains accessible even while extraction is queued or has failed.
        if (ds.file_type?.toLowerCase() === 'pdf' || ds.filename.toLowerCase().endsWith('.pdf')) {
          setPreview(null); setMetadata([]); setProfile(null); setQuality(null);
          const [verData, linData] = await Promise.all([
            datasetService.getVersions(datasetId), datasetService.getLineage(ds),
          ]);
          setVersions(verData); setLineage(linData);
          return;
        }

        // Preview records from backend
        const previewData = await datasetService.getPreview(datasetId);
        setPreview(previewData);

        // Fetch remaining tab data in parallel
        const [metaData, profData, qualData, verData, linData] = await Promise.all([
          datasetService.getMetadata(datasetId),
          datasetService.getProfile(datasetId),
          datasetService.getQuality(datasetId),
          datasetService.getVersions(datasetId),
          datasetService.getLineage(ds),
        ]);

        setMetadata(metaData);
        setProfile(profData);
        setQuality(qualData);
        setVersions(verData);
        setLineage(linData);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Unable to load dataset details.');
      } finally {
        setIsLoading(false);
      }
    }
    loadDatasetDetails();
  }, [datasetId, retry]);

  if (error) return <div className="ws-page" role="alert"><h1 className="ws-page-heading">Dataset unavailable</h1><p>{error}</p><button className="reports-btn-secondary" onClick={() => setRetry(n => n + 1)}>Try again</button><Link to="/datasets">Back to datasets</Link></div>;

  if (isLoading || !dataset) {
    return (
      <div className="flex flex-col items-center justify-center p-16 space-y-4">
        <div className="w-8 h-8 border-2 border-sky-500 border-t-transparent rounded-full animate-spin" />
        <p className="text-xs text-zinc-400 font-mono">Loading Enterprise Dataset Details...</p>
      </div>
    );
  }

  const isPdf = dataset.file_type?.toLowerCase() === 'pdf' || dataset.filename.toLowerCase().endsWith('.pdf');

  // Filtered Preview Rows
  const filteredRows = (preview?.rows || []).filter((row) => {
    if (!previewSearch.trim()) return true;
    const query = previewSearch.toLowerCase();
    return Object.values(row).some((val) => String(val ?? '').toLowerCase().includes(query));
  });

  const paginatedRows = filteredRows.slice(previewPage * pageSize, (previewPage + 1) * pageSize);
  const totalPages = Math.ceil(filteredRows.length / pageSize);

  async function handleRollback(versionNumber: number) {
    if (!dataset || !window.confirm('Activate version ' + versionNumber + '? This changes the dataset used by future analyses.')) return;
    setRollbackLoading(true);
    const res = await datasetService.rollbackVersion(dataset.dataset_id, versionNumber);
    setRollbackStatus(res.message);
    setRollbackLoading(false);
    if (res.success) setRetry(n => n + 1);
  }

  async function compareVersions(versionNumber?: number) {
    if (!dataset || versions.length < 2) return;
    const active = versions.find(v => v.isActive) ?? versions[0];
    const other = versions.find(v => v.version_number === versionNumber && v.version_number !== active.version_number) ?? versions.find(v => v.version_number !== active.version_number)!;
    setComparingVersions(true); setComparison(null); setComparisonError(''); setComparisonLoading(true);
    try {
      setComparison(await apiClient.get('/api/v1/datasets/' + encodeURIComponent(dataset.dataset_id) + '/versions/compare', { params: { v1: String(active.version_number), v2: String(other.version_number) } }));
    } catch (err) { setComparisonError(err instanceof Error ? err.message : 'Unable to compare versions.'); }
    finally { setComparisonLoading(false); }
  }

  return (
    <div className="space-y-6 max-w-7xl mx-auto pb-16">
      {/* Top Breadcrumb & Actions */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-zinc-800/80 pb-5">
        <div className="flex items-center gap-3">
          <Link
            to="/datasets"
            className="p-2 text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 rounded-xl transition-colors"
            title="Back to Datasets"
          >
            <ArrowLeft className="w-5 h-5" />
          </Link>
          <div>
            <div className="flex items-center gap-2.5">
              <h1 className="text-2xl font-bold tracking-tight text-zinc-100 font-mono">
                {dataset.name || dataset.filename}
              </h1>
              <span className="px-2.5 py-0.5 text-xs font-semibold rounded-md border border-sky-500/30 bg-sky-500/10 text-sky-400">
                {dataset.file_type || getExtension(dataset.filename)}
              </span>
              <span className="px-2.5 py-0.5 text-xs font-semibold rounded-full border border-emerald-500/30 bg-emerald-500/10 text-emerald-400">
                {dataset.status}
              </span>
            </div>
            <p className="text-xs text-zinc-400 mt-1 max-w-2xl">{dataset.description}</p>
          </div>
        </div>

        {/* AI Launch Actions */}
        <div className="flex items-center gap-2">
          <button
            onClick={() => navigate(`/analysis?dataset=${dataset.dataset_id}`)}
            className="flex items-center gap-2 px-4 py-2 text-xs font-semibold text-white bg-sky-600 hover:bg-sky-500 rounded-xl transition-all shadow-lg shadow-sky-600/20"
          >
            <Sparkles className="w-4 h-4" />
            <span>AI Analysis</span>
          </button>
          <button
            onClick={() => navigate(`/visualizations?dataset=${dataset.dataset_id}`)}
            className="flex items-center gap-2 px-3.5 py-2 text-xs font-medium text-zinc-300 bg-zinc-900 hover:bg-zinc-800 border border-zinc-800 rounded-xl transition-all"
          >
            <BarChart3 className="w-4 h-4 text-emerald-400" />
            <span>Visualizations</span>
          </button>
        </div>
      </div>

      {/* =================================================================== */}
      {/* 6 USER SPECIFIED TABS                                               */}
      {/* =================================================================== */}
      <div className="flex items-center gap-1.5 p-1 bg-zinc-900 border border-zinc-800 rounded-2xl overflow-x-auto">
        {[
          { id: 'overview', label: 'Overview', icon: Table },
          { id: 'metadata', label: 'Metadata', icon: FileCode },
          { id: 'profile', label: 'Profile', icon: Activity },
          { id: 'quality', label: 'Quality', icon: ShieldCheck },
          { id: 'versions', label: 'Versions', icon: GitBranch },
          { id: 'lineage', label: 'Lineage', icon: Network },
        ].filter(tab => !isPdf || ['overview', 'versions', 'lineage'].includes(tab.id)).map((tab) => {
          const Icon = tab.icon;
          const isActive = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id as DetailTab)}
              className={`flex items-center gap-2 px-4 py-2 text-xs font-medium rounded-xl whitespace-nowrap transition-all ${
                isActive
                  ? 'bg-sky-500/15 text-sky-400 border border-sky-500/30 shadow-sm'
                  : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/50'
              }`}
            >
              <Icon className="w-4 h-4" />
              <span>{tab.label}</span>
            </button>
          );
        })}
      </div>

      {/* =================================================================== */}
      {/* TAB 1: OVERVIEW                                                     */}
      {/* =================================================================== */}
      {activeTab === 'overview' && isPdf && <PdfDocumentPanel
        key={`${dataset.dataset_id}:${dataset.version ?? 1}`} datasetId={dataset.dataset_id}
        initialVersion={dataset.version ?? versions.find(v => v.isActive)?.version_number ?? 1}
        versions={versions} filename={dataset.filename} />}
      {activeTab === 'overview' && !isPdf && (
        <div className="space-y-6">
          {/* Top Key Metrics Card */}
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
            <div className="p-4 bg-zinc-900/70 border border-zinc-800/80 rounded-2xl">
              <span className="text-[11px] text-zinc-500 block mb-1">Total Rows</span>
              <span className="text-xl font-bold font-mono text-zinc-100">
                {dataset.pages ? `${dataset.pages} Pages` : (dataset.row_count ?? 0).toLocaleString()}
              </span>
            </div>
            <div className="p-4 bg-zinc-900/70 border border-zinc-800/80 rounded-2xl">
              <span className="text-[11px] text-zinc-500 block mb-1">Columns</span>
              <span className="text-xl font-bold font-mono text-zinc-100">
                {dataset.pages ? '—' : dataset.column_count ?? 'Unavailable'}
              </span>
            </div>
            <div className="p-4 bg-zinc-900/70 border border-zinc-800/80 rounded-2xl">
              <span className="text-[11px] text-zinc-500 block mb-1">File Size</span>
              <span className="text-xl font-bold font-mono text-zinc-100">{formatFileSize(dataset.size_bytes)}</span>
            </div>
            <div className="p-4 bg-zinc-900/70 border border-zinc-800/80 rounded-2xl">
              <span className="text-[11px] text-zinc-500 block mb-1">Quality Score</span>
              <span className="text-xl font-bold font-mono text-emerald-400">{dataset.quality_score == null ? 'Unavailable' : dataset.quality_score + '%'}</span>
            </div>
            <div className="p-4 bg-zinc-900/70 border border-zinc-800/80 rounded-2xl">
              <span className="text-[11px] text-zinc-500 block mb-1">Created Date</span>
              <span className="text-xs font-medium text-zinc-200 mt-1 block">{formatDate(dataset.uploaded_at)}</span>
            </div>
            <div className="p-4 bg-zinc-900/70 border border-zinc-800/80 rounded-2xl">
              <span className="text-[11px] text-zinc-500 block mb-1">Last Updated</span>
              <span className="text-xs font-medium text-zinc-200 mt-1 block">
                {formatDate(dataset.updated_at || dataset.uploaded_at)}
              </span>
            </div>
          </div>

          {/* Dataset Storage Architecture Callout */}
          <div className="p-5 bg-zinc-900/80 border border-zinc-800 rounded-2xl shadow-lg space-y-3">
            <div className="flex items-center gap-2">
              <HardDrive className="w-5 h-5 text-sky-400" />
              <h3 className="text-sm font-semibold text-zinc-100">Enterprise Storage Architecture</h3>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3 pt-1">
              <div className="p-3 bg-zinc-950/80 rounded-xl border border-zinc-800">
                <span className="text-zinc-500 text-[11px] block">Raw Storage</span>
                <span className="font-mono text-xs text-emerald-400 truncate block mt-0.5">
                  {dataset.raw_path || 'Not recorded'}
                </span>
                <span className="text-[10px] text-zinc-500 mt-1 block">Registered upload path</span>
              </div>
              <div className="p-3 bg-zinc-950/80 rounded-xl border border-zinc-800">
                <span className="text-zinc-500 text-[11px] block">Processed Storage</span>
                <span className="font-mono text-xs text-sky-400 truncate block mt-0.5">
                  {dataset.processed_path || 'Not recorded'}
                </span>
                <span className="text-[10px] text-zinc-500 mt-1 block">Canonical storage path</span>
              </div>
              <div className="p-3 bg-zinc-950/80 rounded-xl border border-zinc-800">
                <span className="text-zinc-500 text-[11px] block">Registry Artifacts</span>
                <span className="font-mono text-xs text-purple-400 truncate block mt-0.5">
                  {dataset.dataset_id}
                </span>
                <span className="text-[10px] text-zinc-500 mt-1 block">metadata, profile, quality, lineage</span>
              </div>
            </div>
          </div>

          {/* AI Integration Hub */}
          <div className="p-5 bg-zinc-900 border border-sky-500/20 rounded-2xl space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2.5">
                <Bot className="w-5 h-5 text-sky-400" />
                <h3 className="text-sm font-semibold text-zinc-100">Explore this dataset</h3>
              </div>
              <span className="text-xs text-emerald-400 font-medium">Choose an analytical workflow</span>
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2.5 pt-1">
              {[
                { name: 'EDA Agent', desc: 'Auto Exploratory Analysis', route: '/eda' },
                { name: 'SQL Agent', desc: 'Text-to-SQL Querying', route: '/analysis' },
                { name: 'Visualization Agent', desc: 'Intelligent Chart Engine', route: '/visualizations' },
                { name: 'Forecast Agent', desc: 'Prophet / XGBoost Models', route: '/analysis' },
                { name: 'Insight Agent', desc: 'Causal Drivers & Risks', route: '/insights' },
                { name: 'Recommendation Agent', desc: 'Decision Intelligence', route: '/insights' },
              ].map((agent) => (
                <button
                  key={agent.name}
                  onClick={() => navigate(`${agent.route}?dataset=${dataset.dataset_id}`)}
                  className="p-3 bg-zinc-950/70 hover:bg-zinc-800 border border-zinc-800/80 hover:border-sky-500/40 rounded-xl text-left transition-all group"
                >
                  <div className="flex items-center justify-between mb-1">
                    <span className="w-2 h-2 rounded-full bg-sky-400" />
                    <Sparkles className="w-3 h-3 text-zinc-500 group-hover:text-sky-400" />
                  </div>
                  <h4 className="text-xs font-semibold text-zinc-200 group-hover:text-sky-300 transition-colors">
                    {agent.name}
                  </h4>
                  <p className="text-[10px] text-zinc-500 mt-0.5 line-clamp-1">{agent.desc}</p>
                </button>
              ))}
            </div>
          </div>

          {/* First 100 Records Interactive Preview Table */}
          <div className="bg-zinc-900/70 border border-zinc-800/80 rounded-2xl shadow-xl overflow-hidden space-y-3 p-5">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
              <div>
                <h3 className="text-sm font-semibold text-zinc-100 flex items-center gap-2">
                  <Table className="w-4 h-4 text-sky-400" />
                  <span>Preview: First 50 Records</span>
                </h3>
                <p className="text-xs text-zinc-400">
                  Showing {filteredRows.length} matching preview rows of {preview?.rows.length ?? 0} loaded; dataset total: {preview?.totalRows == null ? 'unknown' : preview.totalRows.toLocaleString()}. Source: {dataset.filename}
                </p>
              </div>

              <div className="relative min-w-[220px]">
                <Search className="w-3.5 h-3.5 absolute left-3 top-2.5 text-zinc-500" />
                <input
                  type="text"
                  aria-label="Filter preview rows"
                  placeholder="Filter preview rows..."
                  value={previewSearch}
                  onChange={(e) => {
                    setPreviewSearch(e.target.value);
                    setPreviewPage(0);
                  }}
                  className="w-full pl-8 pr-3 py-1.5 text-xs bg-zinc-950 border border-zinc-800 rounded-xl text-zinc-100 placeholder:text-zinc-600 outline-none"
                />
              </div>
            </div>

            {preview && preview.columns.length > 0 ? (
              <div className="border border-zinc-800 rounded-xl overflow-x-auto">
                <table className="w-full text-left text-xs border-collapse font-mono">
                  <thead className="bg-zinc-950/80 border-b border-zinc-800 text-zinc-400">
                    <tr>
                      <th className="px-3 py-2.5 w-12 text-zinc-600 font-normal">#</th>
                      {preview.columns.map((col) => (
                        <th key={col} className="px-4 py-2.5 font-medium whitespace-nowrap text-zinc-300">
                          {col}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-zinc-800/60">
                    {paginatedRows.map((row, idx) => (
                      <tr key={idx} className="hover:bg-zinc-800/30">
                        <td className="px-3 py-2 text-zinc-600 text-[11px]">{previewPage * pageSize + idx + 1}</td>
                        {preview.columns.map((col) => (
                          <td key={col} className="px-4 py-2 text-zinc-300 whitespace-nowrap">
                            {row[col] !== null && row[col] !== undefined ? String(row[col]) : <span className="text-zinc-600">—</span>}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="p-8 text-center text-zinc-500 text-xs">
                No preview tabular data available for this file type.
              </div>
            )}

            {/* Pagination Controls */}
            {totalPages > 1 && (
              <div className="flex items-center justify-between pt-2 text-xs text-zinc-400">
                <span>
                  Page {previewPage + 1} of {totalPages}
                </span>
                <div className="flex gap-2">
                  <button
                    onClick={() => setPreviewPage((p) => Math.max(0, p - 1))}
                    disabled={previewPage === 0}
                    className="px-3 py-1 rounded-lg bg-zinc-800 disabled:opacity-40"
                  >
                    Previous
                  </button>
                  <button
                    onClick={() => setPreviewPage((p) => Math.min(totalPages - 1, p + 1))}
                    disabled={previewPage === totalPages - 1}
                    className="px-3 py-1 rounded-lg bg-zinc-800 disabled:opacity-40"
                  >
                    Next
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* =================================================================== */}
      {/* TAB 2: METADATA                                                     */}
      {/* =================================================================== */}
      {activeTab === 'metadata' && (
        <div className="bg-zinc-900/70 border border-zinc-800/80 rounded-2xl shadow-xl overflow-hidden p-5 space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-sm font-semibold text-zinc-100 flex items-center gap-2">
                <FileCode className="w-4 h-4 text-sky-400" />
                <span>Column Schema & Inferred Data Types</span>
              </h3>
              <p className="text-xs text-zinc-400">Detailed columnar profiling, null counts, and cardinality.</p>
            </div>
            <span className="text-xs font-mono text-zinc-400">{metadata.length} Columns Indexed</span>
          </div>

          <div className="border border-zinc-800 rounded-xl overflow-x-auto">
            <table className="w-full text-left text-xs border-collapse">
              <thead className="bg-zinc-950/80 border-b border-zinc-800 text-zinc-400 font-medium">
                <tr>
                  <th className="px-4 py-3">Column Name</th>
                  <th className="px-4 py-3">Datatype</th>
                  <th className="px-4 py-3">Unique Values</th>
                  <th className="px-4 py-3">Null %</th>
                  <th className="px-4 py-3">Sample Values</th>
                  <th className="px-4 py-3">Constraints</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-800/60 font-mono">
                {metadata.map((col) => (
                  <tr key={col.name} className="hover:bg-zinc-800/30">
                    <td className="px-4 py-3 font-semibold text-zinc-200">{col.name}</td>
                    <td className="px-4 py-3 text-sky-400">{col.datatype}</td>
                    <td className="px-4 py-3 text-zinc-300">{col.uniqueValues.toLocaleString()}</td>
                    <td className="px-4 py-3">
                      <span className={`px-2 py-0.5 rounded text-[11px] font-bold ${col.nullPercentage > 0 ? 'bg-amber-500/10 text-amber-400' : 'text-emerald-400'}`}>
                        {col.nullPercentage.toFixed(2)}% ({col.nullCount})
                      </span>
                    </td>
                    <td className="px-4 py-3 text-zinc-400 text-[11px]">
                      {col.sampleValues.length ? col.sampleValues.join(', ') : 'Not provided'}
                    </td>
                    <td className="px-4 py-3">
                      {col.isPrimaryKey && (
                        <span className="px-2 py-0.5 rounded text-[10px] bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 font-bold">
                          PRIMARY KEY
                        </span>
                      )}
                      {col.isTarget && (
                        <span className="px-2 py-0.5 rounded text-[10px] bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 font-bold">
                          TARGET
                        </span>
                      )}
                      {!col.isPrimaryKey && !col.isTarget && <span className="text-zinc-600">—</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* =================================================================== */}
      {/* TAB 3: PROFILE                                                      */}
      {/* =================================================================== */}
      {activeTab === 'profile' && !profile && <p role="status">Profile is unavailable. Retry loading the dataset to check again.</p>}
      {activeTab === 'quality' && !quality && <p role="status">Quality assessment is unavailable.</p>}
      {activeTab === 'profile' && profile && (
        <div className="space-y-6">
          {/* Summary Statistics Table */}
          <div className="bg-zinc-900/70 border border-zinc-800/80 rounded-2xl shadow-xl p-5 space-y-4">
            <h3 className="text-sm font-semibold text-zinc-100 flex items-center gap-2">
              <Activity className="w-4 h-4 text-sky-400" />
              <span>Summary Statistics (Mean, Median, Std Dev, Quantiles)</span>
            </h3>

            <div className="border border-zinc-800 rounded-xl overflow-x-auto">
              <table className="w-full text-left text-xs border-collapse font-mono">
                <thead className="bg-zinc-950/80 border-b border-zinc-800 text-zinc-400">
                  <tr>
                    <th className="px-4 py-2.5">Numeric Metric</th>
                    <th className="px-4 py-2.5">Mean</th>
                    <th className="px-4 py-2.5">Median</th>
                    <th className="px-4 py-2.5">Std Dev</th>
                    <th className="px-4 py-2.5">Min</th>
                    <th className="px-4 py-2.5">25%</th>
                    <th className="px-4 py-2.5">75%</th>
                    <th className="px-4 py-2.5">Max</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-800/60">
                  {Object.entries(profile.summary).map(([key, stat]) => (
                    <tr key={key} className="hover:bg-zinc-800/30">
                      <td className="px-4 py-3 font-semibold text-zinc-200">{key}</td>
                      <td className="px-4 py-3 text-sky-400">{stat.mean?.toLocaleString()}</td>
                      <td className="px-4 py-3 text-emerald-400">{stat.median?.toLocaleString()}</td>
                      <td className="px-4 py-3 text-zinc-300">±{stat.stdDev?.toLocaleString()}</td>
                      <td className="px-4 py-3 text-zinc-400">{stat.min?.toLocaleString()}</td>
                      <td className="px-4 py-3 text-zinc-400">{stat.q25?.toLocaleString()}</td>
                      <td className="px-4 py-3 text-zinc-400">{stat.q75?.toLocaleString()}</td>
                      <td className="px-4 py-3 text-zinc-400">{stat.max?.toLocaleString()}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <p className="text-sm text-zinc-400">Distribution and correlation plots are not supplied by the profile API. Summary statistics above are computed by the backend.</p>
        </div>
      )}

      {/* =================================================================== */}
      {/* TAB 4: QUALITY                                                      */}
      {/* =================================================================== */}
      {activeTab === 'quality' && quality && (
        <div className="space-y-6">
          {/* Quality Score Header & KPI Banner */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <div className="p-5 bg-zinc-900/70 border border-zinc-800/80 rounded-2xl flex flex-col items-center justify-center text-center">
              <span className="text-xs font-medium text-zinc-400 mb-2">Overall Quality Score</span>
              <div className="relative w-24 h-24 flex items-center justify-center">
                <svg className="w-full h-full transform -rotate-90" viewBox="0 0 36 36">
                  <path
                    className="text-zinc-800"
                    strokeWidth="3.5"
                    stroke="currentColor"
                    fill="none"
                    d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                  />
                  <path
                    className="text-emerald-500"
                    strokeDasharray={`${quality.qualityScore}, 100`}
                    strokeWidth="3.5"
                    strokeLinecap="round"
                    stroke="currentColor"
                    fill="none"
                    d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                  />
                </svg>
                <span className="absolute text-2xl font-bold font-mono text-zinc-100">
                  {quality.qualityScore}%
                </span>
              </div>
              <span className="text-[11px] text-emerald-400 font-medium mt-2">Backend quality assessment</span>
            </div>


          </div>

          {/* Data Hygiene Rules Checklist */}
          <div className="p-5 bg-zinc-900/70 border border-zinc-800/80 rounded-2xl shadow-xl space-y-4">
            <h3 className="text-sm font-semibold text-zinc-100">Quality Assessment & Rule Evaluation</h3>
            <div className="space-y-2.5">
              {quality.rules.map((rule) => (
                <div
                  key={rule.rule}
                  className="flex items-center justify-between p-3.5 bg-zinc-950/70 border border-zinc-800/80 rounded-xl"
                >
                  <div className="flex items-center gap-3">
                    {rule.status === 'passed' ? (
                      <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
                    ) : (
                      <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0" />
                    )}
                    <div>
                      <h4 className="text-xs font-semibold text-zinc-200">{rule.rule}</h4>
                      <p className="text-[11px] text-zinc-400 mt-0.5">{rule.description}</p>
                    </div>
                  </div>
                  <span className="font-mono text-xs font-bold text-zinc-300">{rule.score}%</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* =================================================================== */}
      {/* TAB 5: VERSIONS                                                     */}
      {/* =================================================================== */}
      {activeTab === 'versions' && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-sm font-semibold text-zinc-100">Dataset Versioning & Snapshots</h3>
              <p className="text-xs text-zinc-400">Track mutations, schema modifications, and audit rollback history.</p>
            </div>
            <button
              onClick={() => comparingVersions ? setComparingVersions(false) : void compareVersions()}
              disabled={versions.length < 2 || comparisonLoading}
              className="flex items-center gap-1.5 px-3.5 py-1.5 text-xs font-medium text-sky-400 bg-sky-500/10 hover:bg-sky-500/20 border border-sky-500/20 rounded-xl transition-all"
            >
              <GitCompare className="w-3.5 h-3.5" />
              <span>{comparingVersions ? 'Hide Compare' : 'Compare Versions'}</span>
            </button>
          </div>

          {rollbackStatus && (
            <div className="p-3 bg-emerald-500/10 border border-emerald-500/30 rounded-xl text-xs text-emerald-300 flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4" />
              <span>{rollbackStatus}</span>
            </div>
          )}

          {comparingVersions && <div className="p-4 bg-zinc-950 border border-zinc-800 rounded-xl" aria-live="polite">
            {comparisonLoading ? <p>Comparing versions…</p> : comparisonError ? <p role="alert">{comparisonError}</p> : comparison && <><p>Changes from the active version to the selected version:</p><p>Rows added: {comparison.rows_added}; rows removed: {comparison.rows_removed}</p><p>Columns added: {comparison.columns_added.join(', ') || 'None'}</p><p>Columns removed: {comparison.columns_removed.join(', ') || 'None'}</p></>}
          </div>}

          {/* Version Cards */}
          <div className="space-y-3">
            {versions.map((ver) => (
              <div
                key={ver.version_number}
                className={`p-5 rounded-2xl border transition-all ${
                  ver.isActive
                    ? 'bg-zinc-900/90 border-sky-500/40 shadow-lg shadow-sky-950/20'
                    : 'bg-zinc-900/50 border-zinc-800/80 hover:border-zinc-700'
                }`}
              >
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                  <div>
                    <div className="flex items-center gap-2.5">
                      <h4 className="text-sm font-semibold text-zinc-100 font-mono">{ver.label}</h4>
                      {ver.isActive && (
                        <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-sky-500/10 text-sky-400 border border-sky-500/30">
                          ACTIVE
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-zinc-400 mt-1">{ver.changelog}</p>
                    <div className="flex items-center gap-3 text-[11px] text-zinc-500 mt-2 font-mono">
                      <span>{ver.rows.toLocaleString()} rows</span>
                      <span>•</span>
                      <span>{ver.columns} columns</span>
                      <span>•</span>
                      <span>{formatDateTime(ver.created_at)}</span>
                    </div>
                  </div>

                  <div className="flex items-center gap-2">
                    {!ver.isActive && (
                      <button
                        disabled={rollbackLoading}
                        onClick={() => void handleRollback(ver.version_number)}
                        className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-amber-400 bg-amber-500/10 hover:bg-amber-500/20 border border-amber-500/20 rounded-xl transition-all"
                      >
                        <RotateCcw className="w-3.5 h-3.5" />
                        <span>Rollback to v{ver.version_number}</span>
                      </button>
                    )}
                    <button
                      disabled={versions.length < 2 || comparisonLoading}
                      onClick={() => void compareVersions(ver.version_number)}
                      className="px-3 py-1.5 text-xs font-medium text-zinc-300 bg-zinc-800 hover:bg-zinc-700 rounded-xl transition-all"
                    >
                      Inspect
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* =================================================================== */}
      {/* TAB 6: LINEAGE                                                      */}
      {/* =================================================================== */}
      {activeTab === 'lineage' && (
        <div className="bg-zinc-900/70 border border-zinc-800/80 rounded-2xl shadow-xl p-6 space-y-6">
          <div>
            <h3 className="text-sm font-semibold text-zinc-100 flex items-center gap-2">
              <Network className="w-4 h-4 text-sky-400" />
              <span>Registered dataset storage</span>
            </h3>
            <p className="text-xs text-zinc-400 mt-0.5">
              Source and canonical paths supplied by the dataset registry. This is not an execution lineage trace.
            </p>
          </div>

          {/* Visual DAG Flow */}
          <div className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-5 gap-3 relative">
              {lineage
                .filter((n) => n.type !== 'ai_agent')
                .map((node) => (
                  <div key={node.id} className="p-4 bg-zinc-950 border border-zinc-800 rounded-xl text-center space-y-2">
                    <span className="px-2 py-0.5 text-[10px] font-mono text-sky-400 rounded bg-sky-500/10 uppercase">
                      {node.type.replace('_', ' ')}
                    </span>
                    <h4 className="text-xs font-bold text-zinc-200">{node.title}</h4>
                    <p className="text-[10px] text-zinc-500 font-mono truncate">{node.description}</p>
                  </div>
                ))}
            </div>


          </div>
        </div>
      )}
    </div>
  );
}
