import { useState } from 'react';
import { Brain, Download, Search } from 'lucide-react';
import { apiClient } from '../../api/client';
import { downloadWorkbenchJson } from '../../services/workbenchService';

interface SessionMemory {
  workspace_id: string; session_id: string; created_at: string;
  conversation: { id: string; timestamp: string; user_message: string; ai_response: string; intent: string; context: Record<string, unknown> }[];
  analytics: unknown[]; forecasts: unknown[]; dashboard: Record<string, unknown>; datasets: Record<string, unknown>;
}
export default function AIMemoryExplorerPage() {
  const [workspace, setWorkspace] = useState('');
  const [session, setSession] = useState('');
  const [memory, setMemory] = useState<SessionMemory | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [search, setSearch] = useState('');
  async function load() {
    setBusy(true); setError(''); setMemory(null);
    try {
      const data = await apiClient.get<SessionMemory>(`/api/v1/os/memory/${encodeURIComponent(workspace.trim())}/${encodeURIComponent(session.trim())}`);
      if (!Array.isArray(data.conversation)) throw new Error('The memory service returned an invalid session.');
      setMemory(data);
    } catch (e) { setError(e instanceof Error ? e.message : 'Unable to retrieve session memory.'); }
    finally { setBusy(false); }
  }
  const entries = memory?.conversation.filter(turn => `${turn.user_message} ${turn.ai_response} ${turn.intent}`.toLowerCase().includes(search.toLowerCase())) ?? [];
  return <div className="page-container">
    <header className="page-header editorial-heading"><div><p className="eyebrow">INTELLIGENCE / AI MEMORY</p><h1 className="page-title">Context worth keeping.</h1><p className="page-subtitle">Inspect recorded conversation context for a specific workspace and session.</p></div>
      <button className="btn btn--ghost" disabled={!memory || busy} onClick={() => downloadWorkbenchJson(memory, 'session-memory.json')}><Download size={15} /> Export session</button>
    </header>
    <div className="memory-workspace">
    <form className="mem-panel workspace-inspector" onSubmit={e => { e.preventDefault(); void load(); }}>
      <p className="eyebrow">SESSION LOOKUP</p><h2>Return to a conversation</h2>
      <label className="fw-param">Workspace ID<input className="fw-select" required value={workspace} onChange={e => { setWorkspace(e.target.value); setMemory(null); }} disabled={busy} autoComplete="off" /></label>
      <label className="fw-param">Session ID<input className="fw-select" required value={session} onChange={e => { setSession(e.target.value); setMemory(null); }} disabled={busy} autoComplete="off" /></label>
      <button className="btn btn--primary" disabled={busy || !workspace.trim() || !session.trim()}>{busy ? 'Loading session…' : 'Load session'}</button>
      <p className="page-subtitle">Use the IDs from your analysis session. Session discovery and memory deletion are not available in the connected API.</p>
    </form>
    <section className="memory-results" aria-label="Recorded session memory" aria-busy={busy}>
    {error && <p role="alert" className="source-note">{error} Check the IDs and connection, then load the session again.</p>}
    {busy && <p role="status">Retrieving stored context…</p>}
    {!memory && !busy && !error && <div className="mem-empty"><Brain size={32} /><h2>No session selected</h2><p>Load a session to see what has actually been recorded.</p></div>}
    {memory && <>
      <div className="mem-stats">{[['Conversation turns', memory.conversation.length], ['Analyses', memory.analytics?.length ?? 0], ['Forecasts', memory.forecasts?.length ?? 0], ['Dataset memories', Object.keys(memory.datasets ?? {}).length]].map(([label, value]) => <div className="mem-stat-card" key={label}><div className="mem-stat-value">{value}</div><div className="mem-stat-label">{label}</div></div>)}</div>
      <p className="page-subtitle">Workspace: {memory.workspace_id} · Session: {memory.session_id}</p>
      <label className="mem-search-wrapper"><Search size={15} /><span className="sr-only">Search session memory</span><input className="mem-search" placeholder="Search recorded messages" value={search} onChange={e => setSearch(e.target.value)} /></label>
      {!entries.length && <div className="mem-empty"><p>{memory.conversation.length ? 'No recorded messages match your search.' : 'No conversation memory has been recorded for these IDs.'}</p></div>}
      <div className="mem-timeline">{entries.map(turn => <details className="mem-entry" key={turn.id}><summary className="mem-entry-header"><span>{turn.user_message}</span><time dateTime={turn.timestamp}>{new Date(turn.timestamp).toLocaleString()}</time></summary><div className="mem-entry-body"><p style={{ whiteSpace: 'pre-wrap' }}>{turn.ai_response}</p><p className="page-subtitle">Recorded intent: {turn.intent}</p></div></details>)}</div>
    </>}
    </section></div>
  </div>;
}
