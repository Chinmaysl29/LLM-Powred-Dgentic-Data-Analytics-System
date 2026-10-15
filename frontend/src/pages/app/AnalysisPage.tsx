import { useCallback, useEffect, useRef, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { datasetService } from '../../services/datasetService';
import { analysisService } from '../../services/analysisService';
import type { Dataset } from '../../types/datasets';
import type {
  AnalysisSessionDetail,
  AnalysisSessionSummary,
  AnalysisTurn,
  ChartSpec,
  KpiMetrics,
} from '../../types/analysis';

export default function AnalysisPage() {
  const location = useLocation();
  const navigate = useNavigate();
  const initial = location.state as { question?: string; datasetId?: string; sessionId?: string } | null;
  const searchParams = new URLSearchParams(location.search);

  // Core state
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [datasetId, setDatasetId] = useState<string>(
    initial?.datasetId ?? searchParams.get('datasetId') ?? searchParams.get('dataset') ?? ''
  );
  const [question, setQuestion] = useState<string>(initial?.question ?? '');
  const [loadingDatasets, setLoadingDatasets] = useState(true);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string>('');

  // Persistent Sessions state
  const [sessions, setSessions] = useState<AnalysisSessionSummary[]>([]);
  const [loadingSessions, setLoadingSessions] = useState(false);
  const [sessionSearch, setSessionSearch] = useState<string>('');
  const [activeSessionId, setActiveSessionId] = useState<string | null>(
    initial?.sessionId ?? searchParams.get('session_id') ?? null
  );
  const [activeSession, setActiveSession] = useState<AnalysisSessionDetail | null>(null);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  const requestRef = useRef<AbortController | null>(null);
  const turnsEndRef = useRef<HTMLDivElement | null>(null);

  // 1. Load available datasets
  useEffect(() => {
    let active = true;
    datasetService
      .list()
      .then((items) => {
        if (!active) return;
        setDatasets(items);
        setDatasetId((current) =>
          items.some((d) => d.dataset_id === current) ? current : items[0]?.dataset_id ?? ''
        );
      })
      .catch((e) => {
        if (active) setError(e instanceof Error ? e.message : 'Unable to load datasets.');
      })
      .finally(() => {
        if (active) setLoadingDatasets(false);
      });
    return () => {
      active = false;
    };
  }, []);

  // 2. Load persistent session history
  const loadSessions = useCallback(async () => {
    setLoadingSessions(true);
    try {
      const list = await analysisService.listSessions(null, sessionSearch);
      setSessions(list);
    } catch {
      // Non-blocking error for session list
    } finally {
      setLoadingSessions(false);
    }
  }, [sessionSearch]);

  useEffect(() => {
    void loadSessions();
  }, [loadSessions]);

  // 3. Load active session details when activeSessionId changes
  useEffect(() => {
    if (!activeSessionId) {
      setActiveSession(null);
      return;
    }

    let active = true;
    analysisService
      .getSession(activeSessionId)
      .then((detail) => {
        if (!active) return;
        setActiveSession(detail);
        if (detail.dataset_id && (!datasetId || datasetId !== detail.dataset_id)) {
          setDatasetId(detail.dataset_id);
        }
      })
      .catch((err) => {
        if (active) {
          setError(err instanceof Error ? err.message : 'Failed to restore analysis session.');
          setActiveSession(null);
        }
      });

    return () => {
      active = false;
    };
  }, [activeSessionId]);

  // Abort on unmount
  useEffect(() => () => requestRef.current?.abort(), []);

  // Auto-scroll to bottom of conversation
  useEffect(() => {
    turnsEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [activeSession?.turns]);

  // Handle switching or creating new session
  function handleStartNewSession() {
    setActiveSessionId(null);
    setActiveSession(null);
    setQuestion('');
    setError('');
    navigate('/analysis', { replace: true });
  }

  function handleSelectSession(sid: string) {
    if (sid === activeSessionId) return;
    setActiveSessionId(sid);
    setError('');
    navigate(`/analysis?session_id=${encodeURIComponent(sid)}`, { replace: true });
  }

  async function handleDeleteSession(e: React.MouseEvent, sid: string) {
    e.stopPropagation();
    if (!window.confirm('Are you sure you want to delete this analysis session?')) return;
    try {
      await analysisService.deleteSession(sid);
      if (activeSessionId === sid) {
        handleStartNewSession();
      }
      await loadSessions();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not delete session.');
    }
  }

  // Execute or follow-up analysis
  async function handleSubmitAnalysis(e?: React.FormEvent) {
    if (e) e.preventDefault();
    const promptText = question.trim();
    if (!promptText || !datasetId || running) return;

    const controller = new AbortController();
    requestRef.current = controller;
    setRunning(true);
    setError('');

    try {
      const response = await analysisService.ask({
        message: promptText,
        datasetId,
        sessionId: activeSessionId,
        signal: controller.signal,
      });

      if (controller.signal.aborted) return;

      const sid = response.session_id || activeSessionId;
      if (sid && sid !== activeSessionId) {
        setActiveSessionId(sid);
        navigate(`/analysis?session_id=${encodeURIComponent(sid)}`, { replace: true });
      }

      setQuestion('');
      // Reload active session turns from server for persistent single source of truth
      if (sid) {
        const updated = await analysisService.getSession(sid);
        setActiveSession(updated);
      }
      await loadSessions();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Analysis could not complete.');
    } finally {
      setRunning(false);
    }
  }

  const selectedDataset = datasets.find((d) => d.dataset_id === datasetId);

  return (
    <div className="ws-page" style={{ padding: '24px 32px', maxWidth: 1600 }}>
      {/* Editorial Hero Header */}
      <header className="analysis-hero" style={{ marginBottom: 20 }}>
        <div>
          <p className="eyebrow">AI ANALYSIS & PERSISTENT CONVERSATIONAL WORKSPACE</p>
          <h1 style={{ margin: '14px 0' }}>
            Good questions.<br />
            <em>Verifiable answers.</em>
          </h1>
          <p style={{ margin: 0 }}>
            Every calculation, chart, and citation is saved into your persistent workspace history.
          </p>
        </div>
        <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
          <button
            type="button"
            className="btn btn--primary"
            onClick={handleStartNewSession}
            style={{ fontWeight: 600 }}
          >
            + New Analysis
          </button>
          <Link className="editorial-link" to="/datasets/upload">
            Add dataset ↗
          </Link>
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
          <button
            className="btn btn--ghost btn--sm"
            onClick={() => setError('')}
            style={{ color: '#f87171' }}
          >
            Dismiss
          </button>
        </div>
      )}

      {loadingDatasets ? (
        <p role="status" style={{ color: 'var(--text-muted)' }}>
          Loading analytical workspace…
        </p>
      ) : datasets.length === 0 ? (
        <section className="dataset-empty surface-panel" style={{ textAlign: 'center', padding: 48 }}>
          <h2>No datasets uploaded yet.</h2>
          <p style={{ color: 'var(--text-muted)' }}>
            Upload your Excel or CSV dataset to start asking analytical questions.
          </p>
          <Link to="/datasets/upload" className="btn btn--primary" style={{ marginTop: 16 }}>
            Upload dataset
          </Link>
        </section>
      ) : (
        /* Workspace Main Layout: Sidebar + Main Stage */
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: sidebarCollapsed ? '48px minmax(0, 1fr)' : '300px minmax(0, 1fr)',
            gap: 24,
            transition: 'grid-template-columns 0.2s ease',
          }}
        >
          {/* ================================================================ */}
          {/* LEFT: COLLAPSIBLE SESSION HISTORY PANEL                         */}
          {/* ================================================================ */}
          <aside
            className="surface-panel"
            style={{
              padding: sidebarCollapsed ? '16px 8px' : '20px',
              display: 'flex',
              flexDirection: 'column',
              gap: 16,
              height: 'fit-content',
              maxHeight: 'calc(100vh - 160px)',
              overflowY: 'auto',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              {!sidebarCollapsed && (
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span style={{ fontSize: 13, fontWeight: 700, letterSpacing: '0.05em' }}>
                    SESSIONS
                  </span>
                  <span
                    style={{
                      fontSize: 11,
                      padding: '2px 6px',
                      borderRadius: 12,
                      background: 'var(--surface-raised)',
                      color: 'var(--text-muted)',
                    }}
                  >
                    {sessions.length}
                  </span>
                </div>
              )}
              <button
                type="button"
                className="btn btn--ghost btn--sm"
                onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
                title={sidebarCollapsed ? 'Expand history' : 'Collapse history'}
                style={{ padding: '4px 8px' }}
              >
                {sidebarCollapsed ? '▶' : '◀'}
              </button>
            </div>

            {!sidebarCollapsed && (
              <>
                <button
                  type="button"
                  className="btn btn--secondary"
                  onClick={handleStartNewSession}
                  style={{ width: '100%', justifyContent: 'center' }}
                >
                  + New Analysis
                </button>

                <input
                  type="search"
                  placeholder="Search previous questions…"
                  value={sessionSearch}
                  onChange={(e) => setSessionSearch(e.target.value)}
                  style={{
                    padding: '8px 12px',
                    borderRadius: 8,
                    border: '1px solid var(--border)',
                    background: 'var(--surface-raised)',
                    color: 'var(--text-h)',
                    fontSize: 13,
                    width: '100%',
                    boxSizing: 'border-box',
                  }}
                />

                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  {loadingSessions && sessions.length === 0 ? (
                    <p style={{ fontSize: 12, color: 'var(--text-muted)' }}>Loading history…</p>
                  ) : sessions.length === 0 ? (
                    <p style={{ fontSize: 12, color: 'var(--text-muted)', textAlign: 'center', padding: '16px 0' }}>
                      No previous sessions.
                    </p>
                  ) : (
                    sessions.map((sess) => {
                      const isActive = sess.session_id === activeSessionId;
                      return (
                        <div
                          key={sess.session_id}
                          onClick={() => handleSelectSession(sess.session_id)}
                          style={{
                            padding: '12px',
                            borderRadius: 10,
                            border: isActive ? '1px solid var(--accent)' : '1px solid var(--border)',
                            background: isActive ? 'var(--accent-bg)' : 'var(--surface-raised)',
                            cursor: 'pointer',
                            display: 'flex',
                            flexDirection: 'column',
                            gap: 6,
                            transition: 'all 0.15s ease',
                          }}
                        >
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                            <span
                              style={{
                                fontSize: 13,
                                fontWeight: 600,
                                color: isActive ? 'var(--text-h)' : 'var(--text)',
                                lineHeight: 1.3,
                                wordBreak: 'break-word',
                              }}
                            >
                              {sess.title || 'Untitled Analysis'}
                            </span>
                            <button
                              type="button"
                              onClick={(e) => handleDeleteSession(e, sess.session_id)}
                              title="Delete session"
                              style={{
                                background: 'transparent',
                                border: 'none',
                                color: 'var(--text-muted)',
                                cursor: 'pointer',
                                padding: '2px 4px',
                                fontSize: 12,
                                opacity: 0.6,
                              }}
                              onMouseEnter={(e) => ((e.target as HTMLElement).style.opacity = '1')}
                              onMouseLeave={(e) => ((e.target as HTMLElement).style.opacity = '0.6')}
                            >
                              ✕
                            </button>
                          </div>

                          <div
                            style={{
                              display: 'flex',
                              alignItems: 'center',
                              justifyContent: 'space-between',
                              fontSize: 11,
                              color: 'var(--text-muted)',
                            }}
                          >
                            <span>{sess.dataset_name || 'Dataset'}</span>
                            <span>{sess.turn_count} {sess.turn_count === 1 ? 'turn' : 'turns'}</span>
                          </div>
                        </div>
                      );
                    })
                  )}
                </div>
              </>
            )}
          </aside>

          {/* ================================================================ */}
          {/* MAIN AREA: ACTIVE SESSION CONVERSATION & ANALYTICAL TURNS       */}
          {/* ================================================================ */}
          <main style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
            {/* Session Status Header */}
            <div
              className="surface-panel"
              style={{
                padding: '16px 20px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                flexWrap: 'wrap',
                gap: 16,
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <span style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-muted)' }}>
                  ACTIVE DATASET:
                </span>
                <select
                  id="analysis-dataset"
                  value={datasetId}
                  disabled={running}
                  onChange={(e) => setDatasetId(e.target.value)}
                  style={{
                    padding: '8px 12px',
                    borderRadius: 8,
                    border: '1px solid var(--border)',
                    background: 'var(--surface-raised)',
                    color: 'var(--text-h)',
                    fontSize: 13,
                    minWidth: 220,
                  }}
                >
                  {datasets.map((d) => (
                    <option key={d.dataset_id} value={d.dataset_id}>
                      {d.filename} {d.row_count ? `(${d.row_count.toLocaleString()} rows)` : ''}
                    </option>
                  ))}
                </select>
                {selectedDataset && (
                  <span
                    style={{
                      fontSize: 11,
                      padding: '4px 8px',
                      borderRadius: 6,
                      background: 'rgba(200, 253, 57, 0.1)',
                      color: 'var(--brand-lime)',
                      border: '1px solid rgba(200, 253, 57, 0.25)',
                    }}
                  >
                    Verified Schema Pinning
                  </span>
                )}
              </div>

              {activeSession && (
                <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                  <span style={{ fontSize: 13, color: 'var(--text-muted)' }}>
                    Session: <strong style={{ color: 'var(--text-h)' }}>{activeSession.title}</strong>
                  </span>
                  <Link
                    to="/reports"
                    className="btn btn--ghost btn--sm"
                    style={{ textDecoration: 'none', fontSize: 12 }}
                  >
                    View in Reports ↗
                  </Link>
                </div>
              )}
            </div>

            {/* Turn History or Empty Session Prompt */}
            {activeSession && activeSession.turns.length > 0 ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
                {activeSession.turns.map((turn, index) => (
                  <TurnCard
                    key={turn.turn_id || index}
                    turn={turn}
                    datasetName={selectedDataset?.filename || activeSession.dataset_name || 'Dataset'}
                    sessionId={activeSession.session_id}
                  />
                ))}
                <div ref={turnsEndRef} />
              </div>
            ) : (
              <div
                className="surface-panel"
                style={{
                  padding: 40,
                  textAlign: 'center',
                  background: 'var(--surface)',
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  gap: 12,
                }}
              >
                <div
                  style={{
                    width: 52,
                    height: 52,
                    borderRadius: 26,
                    background: 'rgba(200, 253, 57, 0.12)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    color: 'var(--brand-lime)',
                    fontSize: 24,
                  }}
                >
                  ⚡
                </div>
                <h2 style={{ margin: '8px 0 4px', fontSize: 20 }}>Ask the AI Data Analyst</h2>
                <p style={{ color: 'var(--text-muted)', maxWidth: 520, margin: 0, fontSize: 14 }}>
                  Submit an analytical question or request a calculation. Results, charts, tables, and KPIs
                  will be saved into this session automatically.
                </p>
                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 12, justifyContent: 'center' }}>
                  {[
                    'Summarize the numeric measures',
                    'Total revenue by company_name',
                    'Which entity has the highest observation?',
                    'Compare top 2 entities',
                  ].map((quick) => (
                    <button
                      key={quick}
                      type="button"
                      className="btn btn--ghost btn--sm"
                      onClick={() => setQuestion(quick)}
                      style={{ fontSize: 12 }}
                    >
                      {quick}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* Input Composer / Follow-up Bar */}
            <form
              onSubmit={handleSubmitAnalysis}
              className="surface-panel"
              style={{
                padding: '18px 20px',
                display: 'flex',
                flexDirection: 'column',
                gap: 12,
                position: 'sticky',
                bottom: 20,
                zIndex: 10,
                boxShadow: '0 8px 32px rgba(0,0,0,0.25)',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <label
                  htmlFor="analysis-question"
                  style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-muted)', letterSpacing: '0.04em' }}
                >
                  {activeSession && activeSession.turns.length > 0
                    ? 'ASK A FOLLOW-UP QUESTION'
                    : 'NEW ANALYTICAL QUESTION'}
                </label>
                {activeSession && (
                  <span style={{ fontSize: 11, color: 'var(--brand-lime)' }}>
                    ● Maintaining context for {activeSession.title}
                  </span>
                )}
              </div>

              <textarea
                id="analysis-question"
                rows={2}
                maxLength={2000}
                required
                value={question}
                disabled={running}
                onChange={(e) => setQuestion(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    void handleSubmitAnalysis();
                  }
                }}
                placeholder={
                  activeSession && activeSession.turns.length > 0
                    ? 'e.g. Which company has the highest profit? Compare it with the second-highest.'
                    : 'e.g. Analyze companies and their profits across the population'
                }
                style={{
                  width: '100%',
                  padding: '12px 14px',
                  borderRadius: 8,
                  border: '1px solid var(--border)',
                  background: 'var(--surface-raised)',
                  color: 'var(--text-h)',
                  fontSize: 14,
                  resize: 'none',
                  boxSizing: 'border-box',
                }}
              />

              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                  Press <kbd style={{ padding: '2px 5px', borderRadius: 4, background: 'var(--code-bg)' }}>Enter ↵</kbd> to execute
                </span>

                <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
                  {running && (
                    <button
                      type="button"
                      className="btn btn--ghost btn--sm"
                      onClick={() => requestRef.current?.abort()}
                    >
                      Cancel
                    </button>
                  )}
                  <button
                    type="submit"
                    className="btn btn--primary"
                    disabled={running || !question.trim()}
                    style={{ minWidth: 130, justifyContent: 'center' }}
                  >
                    {running ? 'Analyzing…' : activeSession ? 'Send Follow-up' : 'Run Analysis'}
                  </button>
                </div>
              </div>
            </form>
          </main>
        </div>
      )}
    </div>
  );
}

// ==============================================================================
// TURN CARD COMPONENT: Shows question + verified answer + KPIs + Chart + Table
// ==============================================================================
function TurnCard({
  turn,
  datasetName,
  sessionId,
}: {
  turn: AnalysisTurn;
  datasetName: string;
  sessionId: string;
}) {
  const navigate = useNavigate();
  const columns = Array.from(new Set((turn.data || []).flatMap((row) => Object.keys(row))));

  function handleOpenReportStudio() {
    navigate('/reports', {
      state: {
        selectedRunId: turn.run_id,
        sessionId,
        title: turn.question,
      },
    });
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      {/* 1. User Question Prompt */}
      <div
        style={{
          display: 'flex',
          alignItems: 'flex-start',
          gap: 12,
          padding: '14px 18px',
          borderRadius: 12,
          background: 'var(--surface-raised)',
          border: '1px solid var(--border)',
          alignSelf: 'flex-start',
          maxWidth: '85%',
        }}
      >
        <div
          style={{
            width: 28,
            height: 28,
            borderRadius: 14,
            background: 'var(--accent-bg)',
            color: 'var(--accent)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontSize: 12,
            fontWeight: 700,
            flexShrink: 0,
          }}
        >
          Q
        </div>
        <div>
          <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-h)' }}>
            {turn.question}
          </div>
          {turn.asked_at && (
            <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 4 }}>
              {new Date(turn.asked_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
            </div>
          )}
        </div>
      </div>

      {/* 2. AI Analyst Answer & Verified Artifacts */}
      <div
        className="surface-panel"
        style={{
          padding: '24px',
          borderLeft: '4px solid var(--brand-lime)',
          display: 'flex',
          flexDirection: 'column',
          gap: 18,
        }}
      >
        {/* Header: Status, Execution time, Source */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 10 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <span
              style={{
                fontSize: 11,
                fontWeight: 700,
                padding: '3px 8px',
                borderRadius: 4,
                background: turn.status === 'clarification_required' ? 'rgba(245, 158, 11, 0.2)' : 'rgba(16, 185, 129, 0.2)',
                color: turn.status === 'clarification_required' ? '#f59e0b' : '#10b981',
              }}
            >
              {turn.status === 'clarification_required' ? 'CLARIFICATION NEEDED' : 'CALCULATED & VERIFIED'}
            </span>
            <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
              Source: <strong>{datasetName}</strong> · Latency: {turn.execution_time.toFixed(2)}s
            </span>
          </div>

          {turn.run_id && turn.status !== 'clarification_required' && (
            <button
              type="button"
              className="btn btn--secondary btn--sm"
              onClick={handleOpenReportStudio}
              title="Generate a formal PDF report from this verified analysis"
            >
              Generate Detailed Report 📄
            </button>
          )}
        </div>

        {/* Primary Answer */}
        <div>
          <h3 style={{ margin: '0 0 8px', fontSize: 18, color: 'var(--text-h)', lineHeight: 1.4 }}>
            {turn.answer}
          </h3>
          {turn.explanation && (
            <p style={{ margin: 0, color: 'var(--text)', fontSize: 14, lineHeight: 1.6 }}>
              {turn.explanation}
            </p>
          )}
        </div>

        {/* Population KPIs */}
        {turn.kpis && Object.keys(turn.kpis).length > 0 && (
          <KpiGrid kpis={turn.kpis} />
        )}

        {/* Chart Visualization */}
        {turn.chart && turn.chart.points && turn.chart.points.length > 0 && (
          <BarChartRenderer chart={turn.chart} />
        )}

        {/* Data Table */}
        {turn.data && turn.data.length > 0 && (
          <div style={{ overflowX: 'auto' }}>
            <table
              className="dataset-table"
              style={{
                width: '100%',
                fontSize: 13,
                borderCollapse: 'collapse',
                textAlign: 'left',
              }}
            >
              <thead>
                <tr style={{ borderBottom: '1px solid var(--border)' }}>
                  {columns.map((c) => (
                    <th key={c} style={{ padding: '8px 12px', color: 'var(--text-muted)', fontWeight: 600 }}>
                      {c}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {turn.data.slice(0, 20).map((row, rIdx) => (
                  <tr key={rIdx} style={{ borderBottom: '1px solid var(--border)' }}>
                    {columns.map((c) => (
                      <td key={c} style={{ padding: '8px 12px' }}>
                        {row[c] == null ? '—' : String(row[c])}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
            {turn.data.length > 20 && (
              <div style={{ fontSize: 11, color: 'var(--text-muted)', padding: '6px 12px' }}>
                Showing 20 of {turn.data.length} observations
              </div>
            )}
          </div>
        )}

        {/* Verified RAG Citations */}
        {turn.citations && turn.citations.length > 0 && (
          <div style={{ borderTop: '1px solid var(--border)', paddingTop: 14 }}>
            <span style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-muted)', display: 'block', marginBottom: 8 }}>
              RETRIEVED DOCUMENT EVIDENCE ({turn.citations.length} CITATIONS)
            </span>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 10 }}>
              {turn.citations.map((cite, cIdx) => (
                <div
                  key={cIdx}
                  style={{
                    padding: '10px 14px',
                    borderRadius: 8,
                    background: 'var(--surface-raised)',
                    border: '1px solid var(--border)',
                    fontSize: 12,
                  }}
                >
                  <strong style={{ color: 'var(--brand-lime)', display: 'block', marginBottom: 4 }}>
                    {cite.title || cite.doc_id || `Source #${cIdx + 1}`}
                  </strong>
                  <p style={{ margin: 0, color: 'var(--text)', fontStyle: 'italic', opacity: 0.9 }}>
                    "{cite.snippet ? cite.snippet.slice(0, 160) + '…' : 'Document passage reference'}"
                  </p>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Actionable Recommendations */}
        {turn.actionable && turn.actionable.length > 0 && (
          <div style={{ borderTop: '1px solid var(--border)', paddingTop: 12 }}>
            <span style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-muted)' }}>
              SUGGESTED NEXT ACTIONS:
            </span>
            <ul style={{ margin: '6px 0 0', paddingLeft: 20, fontSize: 13, color: 'var(--text)' }}>
              {turn.actionable.map((item, iIdx) => (
                <li key={iIdx} style={{ margin: '3px 0' }}>{item}</li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
}

// ==============================================================================
// KPI GRID COMPONENT
// ==============================================================================
function KpiGrid({ kpis }: { kpis: KpiMetrics }) {
  const fields = ['total', 'mean', 'median', 'min', 'max', 'count'];
  const present = fields.filter((f) => kpis[f] !== undefined);
  if (present.length === 0) return null;

  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: `repeat(auto-fit, minmax(110px, 1fr))`,
        gap: 12,
      }}
    >
      {present.map((key) => {
        const val = kpis[key];
        const displayVal =
          typeof val === 'number'
            ? val % 1 !== 0
              ? val.toLocaleString(undefined, { maximumFractionDigits: 2 })
              : val.toLocaleString()
            : String(val);

        return (
          <div
            key={key}
            style={{
              padding: '12px 14px',
              borderRadius: 10,
              background: 'var(--surface-raised)',
              border: '1px solid var(--border)',
            }}
          >
            <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase' }}>
              {key}
            </div>
            <div style={{ fontSize: 20, fontWeight: 700, color: 'var(--text-h)', marginTop: 4 }}>
              {displayVal}
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ==============================================================================
// BAR CHART RENDERER COMPONENT: Clean, robust, verified visualization preview
// ==============================================================================
function BarChartRenderer({ chart }: { chart: ChartSpec }) {
  const maxVal = Math.max(...chart.points.map((p) => p.value), 1);

  return (
    <div
      style={{
        padding: '16px 20px',
        borderRadius: 12,
        background: 'var(--surface-raised)',
        border: '1px solid var(--border)',
        display: 'flex',
        flexDirection: 'column',
        gap: 14,
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-h)' }}>
          {chart.chart_label || `${chart.y_field} by ${chart.x_field}`}
        </span>
        <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>
          Verified Aggregate Series
        </span>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        {chart.points.map((pt, idx) => {
          const pct = Math.max(0, Math.min(100, (pt.value / maxVal) * 100));
          return (
            <div key={idx} style={{ display: 'grid', gridTemplateColumns: '160px minmax(0, 1fr) 90px', gap: 12, alignItems: 'center' }}>
              <span
                style={{
                  fontSize: 12,
                  fontWeight: 500,
                  color: 'var(--text)',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                }}
                title={pt.label}
              >
                {pt.label}
              </span>
              <div
                style={{
                  height: 18,
                  borderRadius: 4,
                  background: 'var(--code-bg)',
                  overflow: 'hidden',
                  position: 'relative',
                }}
              >
                <div
                  style={{
                    height: '100%',
                    width: `${pct}%`,
                    background: 'var(--brand-lime)',
                    borderRadius: 4,
                    transition: 'width 0.4s ease',
                  }}
                />
              </div>
              <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-h)', textAlign: 'right' }}>
                {pt.value.toLocaleString(undefined, { maximumFractionDigits: 2 })}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
