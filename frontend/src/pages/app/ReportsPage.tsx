import { useCallback, useEffect, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import {
  downloadReportFile,
  downloadStoredReport,
  generateReportFromAnalysis,
  getReportsAnalysisHistory,
  getStoredReports,
  type GeneratedReportResponse,
  type StoredReport,
} from '../../services/reportsService';
import type { AnalysisHistoryReportItem } from '../../types/analysis';

export default function ReportsPage() {
  const location = useLocation();
  const initial = location.state as {
    selectedRunId?: string;
    sessionId?: string;
    title?: string;
  } | null;

  // Active Tab: 'history' (Analysis History from same DB) or 'generated' (Saved Report Documents)
  const [activeTab, setActiveTab] = useState<'history' | 'generated'>('history');

  // Analysis History from persistent database
  const [analysisHistory, setAnalysisHistory] = useState<AnalysisHistoryReportItem[]>([]);
  const [loadingHistory, setLoadingHistory] = useState(true);
  const [historySearch, setHistorySearch] = useState('');

  // Stored / Generated Reports list
  const [storedReports, setStoredReports] = useState<StoredReport[]>([]);
  const [loadingStored, setLoadingStored] = useState(true);
  const [reportSearch, setReportSearch] = useState('');

  // General error and status
  const [error, setError] = useState('');

  // Report Generation Modal state
  const [modalOpen, setModalOpen] = useState(false);
  const [selectedAnalysis, setSelectedAnalysis] = useState<AnalysisHistoryReportItem | null>(null);
  const [reportTitle, setReportTitle] = useState('');
  const [reportType, setReportType] = useState('Executive Report');
  const [formatType, setFormatType] = useState<'pdf' | 'docx' | 'xlsx' | 'pptx'>('pdf');
  const [generating, setGenerating] = useState(false);
  const [latestGenerated, setLatestGenerated] = useState<GeneratedReportResponse | null>(null);

  // 1. Load Analysis History (Single source of truth)
  const loadHistory = useCallback(async () => {
    setLoadingHistory(true);
    setError('');
    try {
      const items = await getReportsAnalysisHistory();
      setAnalysisHistory(items);

      // If pre-selected from Analysis Page, auto-open modal
      if (initial?.selectedRunId) {
        const match = items.find((h) => h.run_id === initial.selectedRunId);
        if (match) {
          setSelectedAnalysis(match);
          setReportTitle(initial.title || match.title);
          setModalOpen(true);
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to load analysis history.');
    } finally {
      setLoadingHistory(false);
    }
  }, [initial]);

  // 2. Load Generated Reports
  const loadStored = useCallback(async () => {
    setLoadingStored(true);
    try {
      const items = await getStoredReports();
      setStoredReports(items);
    } catch {
      // Non-blocking
    } finally {
      setLoadingStored(false);
    }
  }, []);

  useEffect(() => {
    void loadHistory();
    void loadStored();
  }, [loadHistory, loadStored]);

  // Open generation dialog for a specific analysis run
  function handleInitiateReport(item: AnalysisHistoryReportItem) {
    setSelectedAnalysis(item);
    setReportTitle(`Executive Analysis — ${item.title}`);
    setLatestGenerated(null);
    setModalOpen(true);
  }

  // Submit report generation
  async function handleGenerateReport(e: React.FormEvent) {
    e.preventDefault();
    if (!selectedAnalysis?.run_id || generating) return;

    setGenerating(true);
    setError('');
    try {
      const result = await generateReportFromAnalysis({
        run_id: selectedAnalysis.run_id,
        session_id: selectedAnalysis.session_id,
        title: reportTitle.trim() || selectedAnalysis.title,
        report_type: reportType,
        format_type: formatType,
      });

      setLatestGenerated(result);
      // Refresh stored reports list
      await loadStored();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Report generation failed.');
    } finally {
      setGenerating(false);
    }
  }

  // Handle direct file download
  async function handleDownload(reportId: string, filename?: string) {
    try {
      await downloadReportFile(reportId, filename);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Download failed.');
    }
  }

  // Filtered views
  const filteredHistory = analysisHistory.filter((item) =>
    item.title.toLowerCase().includes(historySearch.toLowerCase()) ||
    item.dataset_name.toLowerCase().includes(historySearch.toLowerCase()) ||
    item.question.toLowerCase().includes(historySearch.toLowerCase())
  );

  const filteredStored = storedReports.filter((r) =>
    r.title.toLowerCase().includes(reportSearch.toLowerCase())
  );

  return (
    <div className="ws-page reports-workspace" style={{ padding: '24px 32px', maxWidth: 1600 }}>
      {/* Page Header */}
      <header className="reports-header editorial-heading" style={{ marginBottom: 24 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 16 }}>
          <div>
            <p className="eyebrow">REPORTS STUDIO / ONE SOURCE OF TRUTH</p>
            <h1 className="ws-page-heading" style={{ margin: '8px 0' }}>
              Evidence-Backed Reports
            </h1>
            <p className="ws-page-sub" style={{ margin: 0, maxWidth: 700 }}>
              Generate formal PDF, DOCX, and XLSX reports directly from verified AI Analysis runs.
              Zero duplicate computation—your calculations and charts are preserved verbatim.
            </p>
          </div>

          <div style={{ display: 'flex', gap: 10 }}>
            <button
              type="button"
              className="btn btn--secondary"
              onClick={() => {
                void loadHistory();
                void loadStored();
              }}
              style={{ minHeight: 40 }}
            >
              Refresh
            </button>
            <Link to="/analysis" className="btn btn--primary" style={{ minHeight: 40, fontWeight: 600 }}>
              + Open AI Analysis
            </Link>
          </div>
        </div>

        {/* Tab Navigation */}
        <div style={{ display: 'flex', gap: 12, borderBottom: '1px solid var(--border)', marginTop: 24 }}>
          <button
            type="button"
            onClick={() => setActiveTab('history')}
            style={{
              padding: '10px 18px',
              fontSize: 14,
              fontWeight: 600,
              background: 'transparent',
              border: 'none',
              borderBottom: activeTab === 'history' ? '3px solid var(--brand-lime)' : '3px solid transparent',
              color: activeTab === 'history' ? 'var(--text-h)' : 'var(--text-muted)',
              cursor: 'pointer',
            }}
          >
            Analysis History ({analysisHistory.length})
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('generated')}
            style={{
              padding: '10px 18px',
              fontSize: 14,
              fontWeight: 600,
              background: 'transparent',
              border: 'none',
              borderBottom: activeTab === 'generated' ? '3px solid var(--brand-lime)' : '3px solid transparent',
              color: activeTab === 'generated' ? 'var(--text-h)' : 'var(--text-muted)',
              cursor: 'pointer',
            }}
          >
            Generated Reports ({storedReports.length})
          </button>
        </div>
      </header>

      {error && (
        <div
          role="alert"
          style={{
            padding: '14px 18px',
            borderRadius: 10,
            background: 'rgba(239, 68, 68, 0.12)',
            border: '1px solid rgba(239, 68, 68, 0.3)',
            color: '#f87171',
            marginBottom: 20,
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
          }}
        >
          <span>{error}</span>
          <button className="btn btn--ghost btn--sm" onClick={() => setError('')} style={{ color: '#f87171' }}>
            Dismiss
          </button>
        </div>
      )}

      {/* ==================================================================== */}
      {/* TAB 1: ANALYSIS HISTORY (SELECT COMPLETED RUN TO GENERATE REPORT)     */}
      {/* ==================================================================== */}
      {activeTab === 'history' && (
        <section>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 18, flexWrap: 'wrap', gap: 12 }}>
            <input
              type="search"
              placeholder="Filter by question, dataset, or title…"
              value={historySearch}
              onChange={(e) => setHistorySearch(e.target.value)}
              style={{
                padding: '10px 14px',
                borderRadius: 8,
                border: '1px solid var(--border)',
                background: 'var(--surface-raised)',
                color: 'var(--text-h)',
                fontSize: 13,
                width: 340,
                maxWidth: '100%',
              }}
            />
            <span style={{ fontSize: 13, color: 'var(--text-muted)' }}>
              Showing {filteredHistory.length} completed analytical runs
            </span>
          </div>

          {loadingHistory ? (
            <p style={{ color: 'var(--text-muted)', padding: '32px 0' }}>Loading analysis history from database…</p>
          ) : filteredHistory.length === 0 ? (
            <div className="surface-panel" style={{ textAlign: 'center', padding: '48px 24px' }}>
              <h2 style={{ fontSize: 18, margin: '0 0 8px' }}>No completed analyses found</h2>
              <p style={{ color: 'var(--text-muted)', margin: '0 0 16px', maxWidth: 480, marginInline: 'auto' }}>
                Run an analytical question in AI Analysis first. Completed results, KPIs, and charts will appear here automatically.
              </p>
              <Link to="/analysis" className="btn btn--primary">
                Open AI Analysis
              </Link>
            </div>
          ) : (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(360px, 1fr))', gap: 20 }}>
              {filteredHistory.map((item) => (
                <article
                  key={item.run_id || item.session_id}
                  className="surface-panel"
                  style={{
                    padding: '22px',
                    display: 'flex',
                    flexDirection: 'column',
                    justifyContent: 'space-between',
                    gap: 16,
                    borderLeft: '4px solid var(--brand-lime)',
                  }}
                >
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                      <span
                        style={{
                          fontSize: 11,
                          fontWeight: 700,
                          padding: '2px 7px',
                          borderRadius: 4,
                          background: 'rgba(16, 185, 129, 0.15)',
                          color: '#10b981',
                        }}
                      >
                        {item.status}
                      </span>
                      {item.completed_at && (
                        <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                          {new Date(item.completed_at).toLocaleDateString()}
                        </span>
                      )}
                    </div>

                    <h2 style={{ fontSize: 17, fontWeight: 600, color: 'var(--text-h)', margin: 0, lineHeight: 1.35 }}>
                      {item.title}
                    </h2>

                    <p style={{ fontSize: 13, color: 'var(--text)', margin: 0, lineHeight: 1.5 }}>
                      {item.summary || item.question}
                    </p>

                    <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 4 }}>
                      <span style={{ fontSize: 11, padding: '3px 8px', borderRadius: 4, background: 'var(--surface-raised)', color: 'var(--text-muted)' }}>
                        📊 {item.dataset_name}
                      </span>
                      {item.has_chart && (
                        <span style={{ fontSize: 11, padding: '3px 8px', borderRadius: 4, background: 'rgba(200, 253, 57, 0.15)', color: 'var(--brand-lime)' }}>
                          📈 Chart Verified
                        </span>
                      )}
                      {item.has_citations && (
                        <span style={{ fontSize: 11, padding: '3px 8px', borderRadius: 4, background: 'rgba(59, 130, 246, 0.15)', color: '#60a5fa' }}>
                          📄 RAG Evidence
                        </span>
                      )}
                    </div>
                  </div>

                  <div style={{ display: 'flex', gap: 10, borderTop: '1px solid var(--border)', paddingTop: 14 }}>
                    <Link
                      to={`/analysis?session_id=${encodeURIComponent(item.session_id)}`}
                      className="btn btn--ghost btn--sm"
                      style={{ flex: 1, justifyContent: 'center' }}
                    >
                      Reopen Analysis
                    </Link>
                    <button
                      type="button"
                      className="btn btn--primary btn--sm"
                      onClick={() => handleInitiateReport(item)}
                      style={{ flex: 1, justifyContent: 'center', fontWeight: 600 }}
                    >
                      Generate Report 📄
                    </button>
                  </div>
                </article>
              ))}
            </div>
          )}
        </section>
      )}

      {/* ==================================================================== */}
      {/* TAB 2: GENERATED REPORTS ARCHIVE & INSTANT DOWNLOADS                  */}
      {/* ==================================================================== */}
      {activeTab === 'generated' && (
        <section>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 18, flexWrap: 'wrap', gap: 12 }}>
            <input
              type="search"
              placeholder="Search saved reports by title…"
              value={reportSearch}
              onChange={(e) => setReportSearch(e.target.value)}
              style={{
                padding: '10px 14px',
                borderRadius: 8,
                border: '1px solid var(--border)',
                background: 'var(--surface-raised)',
                color: 'var(--text-h)',
                fontSize: 13,
                width: 340,
                maxWidth: '100%',
              }}
            />
            <span style={{ fontSize: 13, color: 'var(--text-muted)' }}>
              {filteredStored.length} saved documents
            </span>
          </div>

          {loadingStored ? (
            <p style={{ color: 'var(--text-muted)', padding: '32px 0' }}>Loading saved reports…</p>
          ) : filteredStored.length === 0 ? (
            <div className="surface-panel" style={{ textAlign: 'center', padding: '48px 24px' }}>
              <h2 style={{ fontSize: 18, margin: '0 0 8px' }}>No reports generated yet</h2>
              <p style={{ color: 'var(--text-muted)', margin: '0 0 16px' }}>
                Select a completed run from the Analysis History tab to create your first report.
              </p>
              <button
                type="button"
                className="btn btn--primary"
                onClick={() => setActiveTab('history')}
              >
                Go to Analysis History
              </button>
            </div>
          ) : (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(360px, 1fr))', gap: 20 }}>
              {filteredStored.map((r) => (
                <article
                  key={r.id}
                  className="surface-panel"
                  style={{
                    padding: '22px',
                    display: 'flex',
                    flexDirection: 'column',
                    justifyContent: 'space-between',
                    gap: 16,
                  }}
                >
                  <div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                      <span
                        style={{
                          fontSize: 11,
                          fontWeight: 700,
                          padding: '2px 7px',
                          borderRadius: 4,
                          background: 'rgba(200, 253, 57, 0.15)',
                          color: 'var(--brand-lime)',
                          textTransform: 'uppercase',
                        }}
                      >
                        {r.format || 'PDF'}
                      </span>
                      <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                        {new Date(r.created_at).toLocaleDateString()}
                      </span>
                    </div>

                    <h2 style={{ fontSize: 17, fontWeight: 600, color: 'var(--text-h)', margin: '0 0 6px' }}>
                      {r.title}
                    </h2>

                    <p style={{ fontSize: 13, color: 'var(--text-muted)', margin: 0 }}>
                      Type: {r.report_type}
                    </p>
                  </div>

                  <div style={{ display: 'flex', gap: 10, borderTop: '1px solid var(--border)', paddingTop: 14 }}>
                    <button
                      type="button"
                      className="btn btn--primary btn--sm"
                      onClick={() => handleDownload(r.id, `${r.title.replace(/[^a-zA-Z0-9_-]/g, '_')}.pdf`)}
                      style={{ flex: 1, justifyContent: 'center', fontWeight: 600 }}
                    >
                      Download Document ⬇
                    </button>
                    <button
                      type="button"
                      className="btn btn--ghost btn--sm"
                      onClick={() => downloadStoredReport(r)}
                      title="Download JSON manifest"
                    >
                      JSON
                    </button>
                  </div>
                </article>
              ))}
            </div>
          )}
        </section>
      )}

      {/* ==================================================================== */}
      {/* REPORT GENERATION MODAL                                              */}
      {/* ==================================================================== */}
      {modalOpen && selectedAnalysis && (
        <div
          role="dialog"
          aria-modal="true"
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(0, 0, 0, 0.75)',
            backdropFilter: 'blur(4px)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000,
            padding: 20,
          }}
        >
          <div
            className="surface-panel"
            style={{
              width: '100%',
              maxWidth: 620,
              padding: '28px',
              borderRadius: 16,
              background: 'var(--surface)',
              boxShadow: '0 20px 50px rgba(0,0,0,0.5)',
              display: 'flex',
              flexDirection: 'column',
              gap: 20,
              maxHeight: '90vh',
              overflowY: 'auto',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div>
                <span className="eyebrow" style={{ color: 'var(--brand-lime)', margin: 0 }}>
                  GENERATE FORMAL REPORT
                </span>
                <h2 style={{ margin: '4px 0 0', fontSize: 20, color: 'var(--text-h)' }}>
                  {latestGenerated ? 'Report Generated Successfully!' : 'Configure Analysis Report'}
                </h2>
              </div>
              <button
                type="button"
                className="btn btn--ghost btn--sm"
                onClick={() => setModalOpen(false)}
                style={{ padding: '4px 8px' }}
              >
                ✕
              </button>
            </div>

            {latestGenerated ? (
              /* Success State */
              <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
                <div
                  style={{
                    padding: '16px',
                    borderRadius: 10,
                    background: 'rgba(16, 185, 129, 0.12)',
                    border: '1px solid rgba(16, 185, 129, 0.3)',
                    color: '#34d399',
                    fontSize: 14,
                  }}
                >
                  ✓ Detailed document compiled with verified calculation metrics and chart series.
                </div>

                <div style={{ fontSize: 13, color: 'var(--text)' }}>
                  <div><strong>Document:</strong> {latestGenerated.title}</div>
                  <div><strong>Format:</strong> {latestGenerated.format.toUpperCase()}</div>
                  <div><strong>Source Dataset:</strong> {latestGenerated.dataset_name || selectedAnalysis.dataset_name}</div>
                </div>

                <div style={{ display: 'flex', gap: 12, marginTop: 12 }}>
                  <button
                    type="button"
                    className="btn btn--primary"
                    onClick={() => handleDownload(latestGenerated.id, latestGenerated.filename)}
                    style={{ flex: 1, justifyContent: 'center', fontWeight: 600 }}
                  >
                    Download {latestGenerated.format.toUpperCase()} ⬇
                  </button>
                  <button
                    type="button"
                    className="btn btn--ghost"
                    onClick={() => setModalOpen(false)}
                  >
                    Done
                  </button>
                </div>
              </div>
            ) : (
              /* Configuration Form */
              <form onSubmit={handleGenerateReport} style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
                <div>
                  <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: 'var(--text-muted)', marginBottom: 6 }}>
                    Report Title
                  </label>
                  <input
                    type="text"
                    required
                    value={reportTitle}
                    onChange={(e) => setReportTitle(e.target.value)}
                    placeholder="Report title"
                    style={{
                      width: '100%',
                      padding: '10px 12px',
                      borderRadius: 8,
                      border: '1px solid var(--border)',
                      background: 'var(--surface-raised)',
                      color: 'var(--text-h)',
                      fontSize: 14,
                      boxSizing: 'border-box',
                    }}
                  />
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
                  <div>
                    <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: 'var(--text-muted)', marginBottom: 6 }}>
                      Report Type
                    </label>
                    <select
                      value={reportType}
                      onChange={(e) => setReportType(e.target.value)}
                      style={{
                        width: '100%',
                        padding: '10px 12px',
                        borderRadius: 8,
                        border: '1px solid var(--border)',
                        background: 'var(--surface-raised)',
                        color: 'var(--text-h)',
                        fontSize: 13,
                      }}
                    >
                      <option value="Executive Report">Executive Report</option>
                      <option value="Detailed Analysis">Detailed Analysis</option>
                      <option value="Board Presentation">Board Presentation</option>
                      <option value="Operational Audit">Operational Audit</option>
                    </select>
                  </div>

                  <div>
                    <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: 'var(--text-muted)', marginBottom: 6 }}>
                      Export Format
                    </label>
                    <select
                      value={formatType}
                      onChange={(e) => setFormatType(e.target.value as 'pdf' | 'docx' | 'xlsx' | 'pptx')}
                      style={{
                        width: '100%',
                        padding: '10px 12px',
                        borderRadius: 8,
                        border: '1px solid var(--border)',
                        background: 'var(--surface-raised)',
                        color: 'var(--text-h)',
                        fontSize: 13,
                      }}
                    >
                      <option value="pdf">PDF (Print-Ready Document)</option>
                      <option value="docx">DOCX (Editable Word)</option>
                      <option value="xlsx">XLSX (Calculation Workbook)</option>
                      <option value="pptx">PPTX (Presentation Deck)</option>
                    </select>
                  </div>
                </div>

                <div
                  style={{
                    padding: '14px',
                    borderRadius: 8,
                    background: 'var(--surface-raised)',
                    border: '1px solid var(--border)',
                    fontSize: 12,
                    color: 'var(--text-muted)',
                    lineHeight: 1.5,
                  }}
                >
                  <strong style={{ color: 'var(--text-h)', display: 'block', marginBottom: 4 }}>
                    Verified Provenance Binding:
                  </strong>
                  Analysis Run: <code>{selectedAnalysis.run_id}</code><br />
                  Dataset: {selectedAnalysis.dataset_name} (Version {selectedAnalysis.dataset_version || 1})<br />
                  Calculations and chart series will be derived strictly from the saved analytical artifacts.
                </div>

                <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 12, marginTop: 8 }}>
                  <button
                    type="button"
                    className="btn btn--ghost"
                    onClick={() => setModalOpen(false)}
                    disabled={generating}
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    className="btn btn--primary"
                    disabled={generating || !reportTitle.trim()}
                    style={{ minWidth: 150, justifyContent: 'center', fontWeight: 600 }}
                  >
                    {generating ? 'Generating…' : 'Generate & Save'}
                  </button>
                </div>
              </form>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
