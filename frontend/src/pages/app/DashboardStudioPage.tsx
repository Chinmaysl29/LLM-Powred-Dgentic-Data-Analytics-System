import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Download, LayoutDashboard, RefreshCw } from 'lucide-react';
import { apiClient } from '../../api/client';
import { useAuth } from '../../context/AuthContext';
import { downloadWorkbenchJson, workbenchService } from '../../services/workbenchService';
import type { SourceDataset } from '../../services/workbenchService';

interface DashboardSnapshot {
  id: string; title: string; created_at: string; dataset_id: string; sample_rows: number; total_rows: number | null;
  kpis: { id: string; label: string; value: number }[];
}
const STORAGE_KEY = 'analyst.dashboard.snapshot.v1';
function readSnapshot(storageKey: string): DashboardSnapshot | null {
  try {
    const data = JSON.parse(localStorage.getItem(storageKey) ?? 'null');
    return data && typeof data.dataset_id === 'string' && Array.isArray(data.kpis) && data.kpis.every((k: { value: unknown }) => typeof k.value === 'number' && Number.isFinite(k.value)) ? data : null;
  } catch { return null; }
}
export default function DashboardStudioPage() {
  const { user } = useAuth();
  const storageKey = `${STORAGE_KEY}:${user?.id ?? 'anonymous'}`;
  const [snapshot, setSnapshot] = useState<DashboardSnapshot | null>(() => readSnapshot(storageKey));
  const [datasets, setDatasets] = useState<SourceDataset[]>([]);
  const [datasetId, setDatasetId] = useState('');
  const [title, setTitle] = useState('Dataset overview');
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [revision, setRevision] = useState(0);
  const [layout, setLayout] = useState<'grid' | 'list'>('grid');
  useEffect(() => {
    let active = true;
    workbenchService.datasets().then(data => { if (active) setDatasets(data); })
      .catch(e => { if (active) setError(e.message); }).finally(() => { if (active) setBusy(false); });
    return () => { active = false; };
  }, [revision]);
  async function generate() {
    if (!datasetId) return;
    setBusy(true); setError(''); setNotice('');
    try {
      const preview = await workbenchService.preview(datasetId);
      if (!preview.rows.length) throw new Error('This dataset has no preview records. Choose a dataset with data.');
      const data = await apiClient.post<{ id: string; title: string; created_at: string; kpis: { id: string; label: string; value: number }[] }>('/api/v1/os/dashboards/generate', {
        prompt: 'Summarize the supplied dataset', title: title.trim() || 'Dataset overview', data_records: preview.rows,
      });
      if (!Array.isArray(data.kpis)) throw new Error('The dashboard service returned invalid metrics.');
      // The current backend emits fixed growth values and unsupported insight text.
      // Only computed numeric aggregates are retained in this user-facing snapshot.
      const clean: DashboardSnapshot = {
        id: data.id, title: data.title, created_at: data.created_at, dataset_id: datasetId,
        sample_rows: preview.rows.length, total_rows: preview.total_rows,
        kpis: data.kpis.filter(k => k.id !== 'kpi-4' && Number.isFinite(k.value)).map(({ id, label, value }) => ({ id, label, value })),
      };
      setSnapshot(clean);
      try { localStorage.setItem(storageKey, JSON.stringify(clean)); setNotice('Snapshot saved in this browser.'); }
      catch { setNotice('Snapshot generated, but browser storage is unavailable. Export it to keep a copy.'); }
    } catch (e) { setError(e instanceof Error ? e.message : 'Dashboard generation failed.'); }
    finally { setBusy(false); }
  }
  return <div className="page-container">
    <header className="page-header editorial-heading"><div><p className="eyebrow">WORKSPACE / DASHBOARD STUDIO</p><h1 className="page-title">Make room for the big picture.</h1><p className="page-subtitle">Build a saved summary from actual dataset records.</p></div>
      <button className="btn btn--ghost" disabled={!snapshot} onClick={() => downloadWorkbenchJson(snapshot, 'dashboard.json')}><Download size={15} /> Export JSON</button>
    </header>
    <div className="dashboard-studio-workspace">
    <form className="mem-panel workspace-inspector" onSubmit={e => { e.preventDefault(); void generate(); }}>
      <p className="eyebrow">YOUR BUILDING BLOCKS</p><h2>Configure your canvas</h2>
      <label className="fw-param">Dataset<select className="fw-select" disabled={busy} value={datasetId} onChange={e => setDatasetId(e.target.value)}><option value="">Select an uploaded dataset</option>{datasets.map(d => <option key={d.dataset_id} value={d.dataset_id}>{d.dataset_name}</option>)}</select></label>
      <label className="fw-param">Dashboard title<input className="fw-select" value={title} onChange={e => setTitle(e.target.value)} disabled={busy} maxLength={120} /></label>
      <button className="btn btn--primary" disabled={busy || !datasetId}><RefreshCw size={15} /> {busy ? 'Loading…' : 'Generate snapshot'}</button>
      <p className="page-subtitle">Uses up to 100 preview rows. Aggregates describe that sample, not the full dataset. Share links and PDF dashboard export are not available.</p>
    </form>
    <div className="dashboard-canvas" aria-busy={busy}>
    <div className="canvas-toolbar"><span className="eyebrow">LIVE WORKSPACE</span><label className="control-field">Card layout<select value={layout} onChange={e => setLayout(e.target.value as 'grid' | 'list')}><option value="grid">Grid</option><option value="list">Stacked</option></select></label></div>
    {error && <div role="alert" className="source-note"><p>{error}</p><button className="btn btn--ghost" disabled={busy} onClick={() => { setError(''); setBusy(true); setRevision(v => v + 1); }}>Retry dataset connection</button></div>}
    {notice && <p role="status">{notice}</p>}
    {busy && <p role="status">Waiting for the dataset or dashboard service…</p>}
    {!busy && !datasets.length && !error && <div className="mem-empty"><h2>No datasets uploaded yet.</h2><p>Upload a dataset to create your first dashboard.</p><Link className="btn btn--primary" to="/datasets">Open datasets</Link></div>}
    {snapshot && <section><h2>{snapshot.title}</h2><p className="page-subtitle">Saved snapshot · {new Date(snapshot.created_at).toLocaleString()} · Dataset {snapshot.dataset_id} · {snapshot.sample_rows} of {snapshot.total_rows ?? 'unknown total'} rows</p><p className="page-subtitle">Stored locally in this browser. Generate a new snapshot to fetch updated data. Values use source units; no currency is inferred.</p>
      <div className={`snapshot-cards snapshot-cards--${layout}`}>{snapshot.kpis.map(k => <article className="ds-widget" key={k.id}><div className="ds-widget-body"><div className="ds-kpi-label">{k.label}</div><div className="ds-kpi-value">{k.value.toLocaleString(undefined, { maximumFractionDigits: 2 })}</div><p className="page-subtitle">Preview sample</p></div></article>)}</div>
    </section>}
    {!snapshot && !busy && datasets.length > 0 && <div className="mem-empty"><LayoutDashboard size={36} /><h2>No dashboard created yet</h2><p>Select a dataset to calculate its summary.</p></div>}
    </div></div>
  </div>;
}
