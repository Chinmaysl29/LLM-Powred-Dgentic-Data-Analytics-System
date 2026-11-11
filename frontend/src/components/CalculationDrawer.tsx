import { useEffect, useRef, useState } from 'react';
import { companyService as api, type ReviewState } from '../services/companyService';

interface Calculation {
  historical_notice: string | null;
  current_definition_status: string | null;
  definition_id?: string;
  definition_version?: number;
  definition_context?: Record<string, unknown>;
  snapshot_id?: string;
  source_version?: string;
  coverage?: string;
  input_rows?: number;
  collected_at?: string;
  started_at?: string;
  validation_status?: string;
  plan?: unknown;
  quality_checks?: unknown[];
  technical?: unknown;
  require_artifact_review?: boolean;
  review?: ReviewState;
}

export default function CalculationDrawer({
  workspace,
  identity,
  onClose,
}: {
  workspace: string;
  identity: string;
  onClose: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [data, setData] = useState<Calculation | null>(null);
  const [error, setError] = useState('');
  const [reason, setReason] = useState('');
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    const el = dialog.current;
    el?.showModal();
    return () => el?.close();
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    api
      .get<Calculation>(workspace, 'evidence/' + identity, controller.signal)
      .then((value) => {
        if (!controller.signal.aborted) setData(value);
      })
      .catch((e) => {
        if (!controller.signal.aborted)
          setError(e instanceof Error ? e.message : 'Evidence unavailable');
      });
    return () => controller.abort();
  }, [workspace, identity, revision]);
  async function review(action: string) {
    try {
      await api.post(workspace, 'artifacts/' + identity + '/review', {
        expected_revision: data?.review?.revision || 0,
        action,
        reason,
      });
      setRevision((v) => v + 1);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Review failed');
    }
  }
  return (
    <dialog
      ref={dialog}
      onCancel={onClose}
      aria-labelledby="calculation-title"
      style={{ maxWidth: 'min(800px, 94vw)', maxHeight: '85vh', overflow: 'auto', padding: 24 }}
    >
      <h2 id="calculation-title">Show how this was calculated</h2>
      <button onClick={onClose}>Close calculation</button>
      {error && <p role="alert">{error}</p>}
      {!data && !error && <p role="status">Loading stored calculation evidence…</p>}
      {data && (
        <>
          {data.historical_notice && <p>{data.historical_notice}</p>}
          {data.current_definition_status && data.current_definition_status !== 'approved' && (
            <p role="alert">
              Current definition is {data.current_definition_status}. This historical result retains
              its original definition.
            </p>
          )}
          <dl>
            {Object.entries({
              'Definition ID': data.definition_id,
              'Definition version': data.definition_version,
              Snapshot: data.snapshot_id,
              'Source version': data.source_version,
              Coverage: data.coverage,
              'Input rows': data.input_rows,
              'Collected at': data.collected_at,
              'Run started at': data.started_at,
              Validation: data.validation_status,
              ...data.definition_context,
            }).map(([key, value]) => (
              <div key={key}>
                <dt>{key}</dt>
                <dd style={{ overflowWrap: 'anywhere' }}>
                  {value === undefined || value === null
                    ? 'Unknown'
                    : typeof value === 'object'
                      ? JSON.stringify(value)
                      : String(value)}
                </dd>
              </div>
            ))}
          </dl>
          <details>
            <summary>Filters, grain and quality checks</summary>
            <pre style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>
              {JSON.stringify({ plan: data.plan, checks: data.quality_checks }, null, 2)}
            </pre>
          </details>
          <button
            onClick={() => {
              api
                .get<Calculation>(workspace, `evidence/${identity}?technical=true`)
                .then(setData)
                .catch((e) =>
                  setError(e instanceof Error ? e.message : 'Technical evidence is restricted'),
                );
            }}
          >
            View restricted technical evidence
          </button>
          {data.technical !== undefined && (
            <pre style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>
              {JSON.stringify(data.technical, null, 2)}
            </pre>
          )}
          {data.require_artifact_review && (
            <section>
              <h3>Artifact review</h3>
              <p>{data.review?.status || 'draft'}</p>
              <label>
                Review reason
                <input value={reason} onChange={(e) => setReason(e.target.value)} maxLength={500} />
              </label>
              <button
                disabled={!reason.trim() || data.review?.status !== 'draft'}
                onClick={() => void review('review')}
              >
                Submit artifact for review
              </button>
              <button
                disabled={!reason.trim() || data.review?.status !== 'review'}
                onClick={() => void review('approve')}
              >
                Approve artifact
              </button>
            </section>
          )}
        </>
      )}
    </dialog>
  );
}
