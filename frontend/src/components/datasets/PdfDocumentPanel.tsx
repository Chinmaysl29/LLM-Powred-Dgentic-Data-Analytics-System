import { useEffect, useRef, useState } from 'react';
import { apiClient } from '../../api/client';
import type { DatasetVersionItem } from '../../types/datasets';

export type IndexStatus = 'UPLOADED' | 'QUEUED' | 'RUNNING' | 'EXTRACTING' | 'CHUNKING' | 'EMBEDDING' | 'INDEXING' | 'READY' | 'FAILED' | 'CANCELLED';
export interface DocumentIndexState {
  status: IndexStatus; job_id?: string; attempt: number; retry_eligible: boolean;
  error_code?: string; indexed_chunk_count?: number; dataset_version: number; workspace_id?: string | null;
}
interface Workspace { id: string; workspace_name: string; tenant_id?: string }
interface Citation {
  source_id: string; chunk_id: string; document_id: string; filename?: string;
  preview: string; page_number?: number; citation_url?: string;
}
interface DocumentAnswer { answer: string; sources: Citation[]; retrieval_strategy: string }
function isIndexingActive(status: IndexStatus) {
  return ['QUEUED', 'RUNNING', 'EXTRACTING', 'CHUNKING', 'EMBEDDING', 'INDEXING'].includes(status);
}
function isDocumentReady(state: DocumentIndexState | null, version: number) {
  return state?.status === 'READY' && state.dataset_version === version;
}
function documentSourcePath(datasetId: string, version: number) {
  return `/api/v1/datasets/${encodeURIComponent(datasetId)}/source?version=${version}`;
}

export default function PdfDocumentPanel({ datasetId, initialVersion, versions, filename }: {
  datasetId: string; initialVersion: number; versions: DatasetVersionItem[]; filename: string;
}) {
  const [version, setVersion] = useState(initialVersion);
  const [state, setState] = useState<DocumentIndexState | null>(null);
  const [error, setError] = useState('');
  const [revision, setRevision] = useState(0);
  const [busy, setBusy] = useState(false);
  const [question, setQuestion] = useState('');
  const [answer, setAnswer] = useState<DocumentAnswer | null>(null);
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [workspaceId, setWorkspaceId] = useState('');
  const actionController = useRef<AbortController | null>(null);
  const base = `/api/v1/datasets/${encodeURIComponent(datasetId)}`;
  const ready = isDocumentReady(state, version);
  const needsWorkspace = Boolean(state && !state.workspace_id);

  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    async function poll() {
      try {
        const result = await apiClient.get<DocumentIndexState>(`${base}/indexing`, {
          params: { version: String(version) }, signal: controller.signal,
        });
        if (controller.signal.aborted) return;
        setState(result); setError('');
        if (isIndexingActive(result.status)) timer = setTimeout(() => void poll(), 2000);
      } catch {
        if (!controller.signal.aborted) setError('Unable to check document indexing. Refresh the status to retry.');
      }
    }
    void poll();
    return () => { controller.abort(); clearTimeout(timer); };
  }, [base, version, revision]);

  useEffect(() => () => { actionController.current?.abort(); }, []);

  useEffect(() => {
    if (!needsWorkspace) return;
    const controller = new AbortController();
    apiClient.get<Workspace[]>('/api/v1/workspaces/mine', { signal: controller.signal })
      .then(items => { if (!controller.signal.aborted) setWorkspaces(items); })
      .catch(() => { if (!controller.signal.aborted) setError('Unable to load your workspaces. Refresh the status to retry.'); });
    return () => controller.abort();
  }, [needsWorkspace, revision]);

  async function perform(action: 'retry' | 'cancel' | 'bind' | 'ask' | 'source') {
    if (action === 'ask' && (!ready || !question.trim())) return;
    const controller = new AbortController();
    actionController.current?.abort(); actionController.current = controller;
    setBusy(true); setError('');
    try {
      if (action === 'ask') {
        setAnswer(null);
        const result = await apiClient.post<DocumentAnswer>(`${base}/ask`, { version, query: question.trim() }, { signal: controller.signal, timeout: 120_000 });
        if (!controller.signal.aborted) setAnswer(result);
      } else if (action === 'source') {
        const blob = await apiClient.getBlob(documentSourcePath(datasetId, version), { signal: controller.signal });
        if (controller.signal.aborted) return;
        const url = URL.createObjectURL(blob);
        const anchor = document.createElement('a'); anchor.href = url; anchor.download = filename;
        anchor.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
      } else {
        if (action === 'bind') await apiClient.post(`${base}/workspace`, { workspace_id: workspaceId }, { signal: controller.signal });
        else await apiClient.post(`${base}/indexing/${action}`, { version }, { signal: controller.signal });
        if (!controller.signal.aborted) { setAnswer(null); setRevision(n => n + 1); }
      }
    } catch {
      if (!controller.signal.aborted) setError(action === 'ask' ? 'Unable to answer from this document. Check its indexing status and retry.' : 'The document action could not be completed. Refresh its status and retry.');
    } finally { if (!controller.signal.aborted) setBusy(false); }
  }

  const versionNumbers = [...new Set([initialVersion, ...versions.map(v => v.version_number)])].sort((a, b) => b - a);
  return <section className="surface-panel space-y-4" aria-label="Document indexing and questions">
    <h2 className="ws-section-card-title">Document knowledge</h2>
    <label className="control-field">Document version<select aria-label="Document version" value={version} disabled={busy} onChange={e => {
      if (Number(e.target.value) === version) return;
      actionController.current?.abort(); setVersion(Number(e.target.value)); setState(null); setAnswer(null); setError('');
    }}>{versionNumbers.map(n => <option key={n} value={n}>Version {n}</option>)}</select></label>
    <p role="status">{state ? `Indexing status: ${state.status} · Attempt ${state.attempt}` : 'Checking indexing status…'}</p>
    {ready && <p>{state?.indexed_chunk_count ?? 0} indexed passages. Questions use this document version only.</p>}
    {state?.status === 'FAILED' && <p>Indexing failed{state.error_code ? ` (${state.error_code})` : ''}. The original source is preserved.</p>}
    {error && <p role="alert">{error}</p>}
    <div className="studio-actions">
      <button className="reports-btn-secondary" disabled={busy} onClick={() => setRevision(n => n + 1)}>Refresh indexing status</button>
      {state?.retry_eligible && <button className="reports-btn-secondary" disabled={busy} onClick={() => void perform('retry')}>Retry indexing</button>}
      {state && isIndexingActive(state.status) && <button className="reports-btn-secondary" disabled={busy} onClick={() => void perform('cancel')}>Cancel indexing</button>}
      <button className="reports-btn-secondary" disabled={busy} onClick={() => void perform('source')}>Download original PDF</button>
    </div>
    {state && !state.workspace_id && <form onSubmit={e => { e.preventDefault(); if (workspaceId) void perform('bind'); }}>
      <label className="control-field">Workspace for this document<select aria-label="Workspace for this document" value={workspaceId} disabled={busy} onChange={e => setWorkspaceId(e.target.value)}><option value="">Choose an authorized workspace</option>{workspaces.map(w => <option key={w.id} value={w.id}>{w.workspace_name}</option>)}</select></label>
      <button className="reports-create-btn" disabled={busy || !workspaceId}>Assign workspace and index</button>
      <p>Choose where this document belongs before indexing. No workspace is assigned automatically.</p>
    </form>}
    <form onSubmit={e => { e.preventDefault(); void perform('ask'); }}>
      <label className="control-field">Ask this PDF<textarea value={question} onChange={e => setQuestion(e.target.value)} disabled={!ready || busy} maxLength={4000} placeholder="Ask a question supported by this document" /></label>
      <button className="reports-create-btn" disabled={!ready || busy || !question.trim()}>{busy ? 'Working…' : 'Ask document'}</button>
      {!ready && <p>Questions become available when this version is READY.</p>}
    </form>
    {answer && <article aria-label="Document answer"><h3>Document answer</h3><p style={{ whiteSpace: 'pre-wrap' }}>{answer.answer}</p>
      {answer.sources.length > 0 && <><h4>Sources</h4><ul>{answer.sources.map(source => <li key={source.chunk_id}>
        <p>{source.source_id} · {source.filename || filename}{source.page_number ? ` · Page ${source.page_number}` : ''} · Version {version}</p><blockquote>{source.preview}</blockquote>
        <button className="reports-btn-secondary" disabled={busy} onClick={() => void perform('source')}>Download cited source</button>
      </li>)}</ul></>}
    </article>}
  </section>;
}

