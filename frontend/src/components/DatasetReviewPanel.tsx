import { useEffect, useState } from 'react';
import {
  companyService as api,
  type DictionaryEntry,
  type ReviewState,
} from '../services/companyService';

interface Grant {
  id: string;
  reviewer_id: string;
  name: string;
  active: boolean;
  expires_at: string;
  revision: number;
}
interface SharedReview {
  id: string;
  kind: string;
  dataset_id: string;
  payload: Record<string, unknown>;
  review: ReviewState;
}
interface Inbox {
  items: SharedReview[];
  definitions: DictionaryEntry[];
  next_offset: number | null;
}
const failure = (e: unknown) => (e instanceof Error ? e.message : 'Review request failed.');
const object = (value: unknown): Record<string, unknown> =>
  value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
const display = (value: unknown) =>
  value == null ? 'Unknown' : typeof value === 'object' ? JSON.stringify(value) : String(value);

function ReviewSummary({ item }: { item: SharedReview }) {
  const payload = item.payload;
  const context = object(payload.definition_context);
  const spec = object(payload.spec);
  const query = object(spec.query);
  const plan = object(query.plan);
  const fields =
    item.kind === 'workflow'
      ? {
          Name: spec.name,
          Purpose: spec.purpose,
          'Approved metric': plan.metric,
          'Definition ID': query.definition_id,
          'Source snapshot': query.snapshot_id,
          'Business date': query.business_date,
          'Source selection': spec.source_selection,
          'Separate output approval': spec.require_artifact_review,
        }
      : {
          Formula: context.formula,
          Units: context.units,
          Grain: context.grain,
          'Definition version': payload.definition_version,
          'Source version': payload.source_version,
          Coverage: payload.coverage,
          Validation: payload.validation_status,
          'Input rows': payload.input_rows,
          'Completed at': payload.completed_at,
        };
  return (
    <dl>
      {Object.entries(fields).map(([label, value]) => (
        <div key={label}>
          <dt>{label}</dt>
          <dd>{display(value)}</dd>
        </div>
      ))}
    </dl>
  );
}

function AggregateRows({ rows }: { rows: unknown[] }) {
  const [offset, setOffset] = useState(0);
  return (
    <div>
      <p>
        Stored aggregate rows {rows.length ? offset + 1 : 0}–{Math.min(offset + 20, rows.length)} of{' '}
        {rows.length}.
      </p>
      <pre>{JSON.stringify(rows.slice(offset, offset + 20), null, 2)}</pre>
      <button disabled={offset === 0} onClick={() => setOffset((v) => Math.max(0, v - 20))}>
        Previous aggregate rows
      </button>
      <button disabled={offset + 20 >= rows.length} onClick={() => setOffset((v) => v + 20)}>
        Next aggregate rows
      </button>
    </div>
  );
}

export default function DatasetReviewPanel({
  workspace,
  datasetId,
  canManage,
}: {
  workspace: string;
  datasetId?: string | null;
  canManage: boolean;
}) {
  const [grantRows, setGrants] = useState<Grant[]>([]);
  const [candidateRows, setCandidates] = useState<{ id: string; name: string }[]>([]);
  const [managementScope, setManagementScope] = useState('');
  const [grantState, setGrantState] = useState<{
    reviewer: string;
    revision: number;
    expires_at: string | null;
    active: boolean;
  } | null>(null);
  const [search, setSearch] = useState('');
  const [candidateOffset, setCandidateOffset] = useState(0);
  const [candidateNext, setCandidateNext] = useState<number | null>(null);
  const [grantOffset, setGrantOffset] = useState(0);
  const [grantNext, setGrantNext] = useState<number | null>(null);
  const [reviewer, setReviewer] = useState('');
  const [expiry, setExpiry] = useState('');
  const [reason, setReason] = useState('');
  const [inbox, setInbox] = useState<Inbox | null>(null);
  const [offset, setOffset] = useState(0);
  const [version, setVersion] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [loading, setLoading] = useState(true);

  const scope = JSON.stringify([
    workspace,
    datasetId,
    canManage,
    search,
    grantOffset,
    candidateOffset,
    version,
  ]);
  const grants = managementScope === scope ? grantRows : [];
  const candidates = managementScope === scope ? candidateRows : [];
  const selectedGrant = grantState?.reviewer === reviewer ? grantState : null;

  useEffect(() => {
    const controller = new AbortController();
    if (reviewer && datasetId && canManage) {
      api
        .get<{ revision: number; expires_at: string | null; active: boolean }>(
          workspace,
          `review-grants/revision?dataset_id=${encodeURIComponent(datasetId)}&reviewer_id=${encodeURIComponent(reviewer)}`,
          controller.signal,
        )
        .then((data) => {
          if (!controller.signal.aborted) setGrantState({ ...data, reviewer });
        })
        .catch((e) => {
          if (!controller.signal.aborted) setError(failure(e));
        });
    }
    return () => controller.abort();
  }, [workspace, datasetId, canManage, reviewer, version]);

  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    async function load() {
      try {
        const data = await api.get<Inbox>(workspace, `reviews?offset=${offset}`, controller.signal);
        if (controller.signal.aborted) return;
        setInbox(data);
      } catch (e) {
        if (controller.signal.aborted) return;
        setInbox(null);
        setError(failure(e));
      } finally {
        if (!controller.signal.aborted) {
          setLoading(false);
          timer = setTimeout(() => void load(), 5000);
        }
      }
    }
    void load();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [workspace, offset, version]);

  useEffect(() => {
    const controller = new AbortController();
    if (datasetId && canManage) {
      const source = encodeURIComponent(datasetId);
      Promise.all([
        api.get<{ items: Grant[]; next_offset: number | null }>(
          workspace,
          `review-grants?dataset_id=${source}&offset=${grantOffset}`,
          controller.signal,
        ),
        api.get<{ items: { id: string; name: string }[]; next_offset: number | null }>(
          workspace,
          `reviewer-candidates?dataset_id=${source}&search=${encodeURIComponent(search)}&offset=${candidateOffset}`,
          controller.signal,
        ),
      ])
        .then(([assigned, people]) => {
          if (controller.signal.aborted) return;
          setGrants(assigned.items);
          setGrantNext(assigned.next_offset);
          setCandidates(people.items);
          setCandidateNext(people.next_offset);
          setManagementScope(scope);
        })
        .catch((e) => {
          if (!controller.signal.aborted) setError(failure(e));
        });
    }
    return () => controller.abort();
  }, [workspace, datasetId, canManage, search, grantOffset, candidateOffset, version, scope]);

  async function act(task: () => Promise<unknown>, success: string) {
    setBusy(true);
    setError('');
    setNotice('');
    try {
      await task();
      setNotice(success);
      setVersion((v) => v + 1);
    } catch (e) {
      setError(failure(e));
    } finally {
      setBusy(false);
    }
  }
  const approve = (id: string, revision: number, dictionary = false) =>
    act(
      () =>
        api.post(workspace, `${dictionary ? 'dictionary' : 'artifacts'}/${id}/review`, {
          expected_revision: revision,
          action: 'approve',
          reason,
        }),
      'Independent approval recorded.',
    );

  return (
    <section aria-label="Dataset reviewer access" className="dh-section">
      <h3>Dataset reviewers</h3>
      <p>
        Owners assign a named workspace member to a specific dataset until an explicit expiry.
        Reviewers can inspect submitted calculation metadata and aggregate results and record
        approvals.
      </p>
      {error && (
        <p role="alert" className="dh-error">
          {error} <button onClick={() => setVersion((v) => v + 1)}>Reload reviewers</button>
        </p>
      )}
      {notice && <p role="status">{notice}</p>}
      <label>
        Reviewer decision reason
        <input
          aria-label="Reviewer decision reason"
          maxLength={500}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
        />
      </label>
      {datasetId && canManage ? (
        <details>
          <summary>Manage reviewers for selected dataset</summary>
          <p>
            Dataset <code>{datasetId}</code>. Granting access exposes submitted aggregate results
            and source schema. Raw records, downloads and execution remain owner controlled.
            Revocation stops new access; prior approvals stay in the audit history.
          </p>
          <label>
            Find workspace member
            <input
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                setCandidateOffset(0);
                setReviewer('');
              }}
            />
          </label>
          <label>
            Dataset reviewer
            <select
              aria-label="Dataset reviewer"
              value={reviewer}
              onChange={(e) => setReviewer(e.target.value)}
            >
              <option value="">Choose a workspace member</option>
              {candidates.map((person) => (
                <option value={person.id} key={person.id}>
                  {person.name} · {person.id.slice(0, 8)}
                </option>
              ))}
            </select>
          </label>
          <button
            disabled={candidateOffset === 0}
            onClick={() => {
              setCandidateOffset((v) => Math.max(0, v - 50));
              setReviewer('');
            }}
          >
            Previous members
          </button>
          <button
            disabled={candidateNext === null}
            onClick={() => {
              setCandidateOffset(candidateNext!);
              setReviewer('');
            }}
          >
            Next members
          </button>
          <label>
            Review access expires (local time)
            <input
              aria-label="Review access expiry"
              type="datetime-local"
              value={expiry}
              onChange={(e) => setExpiry(e.target.value)}
            />
          </label>
          {selectedGrant && (
            <p>
              Current grant revision {selectedGrant.revision}:{' '}
              {selectedGrant.active ? 'active' : 'inactive'}
              {selectedGrant.expires_at
                ? `, expires ${new Date(selectedGrant.expires_at).toLocaleString()}`
                : ', no prior grant'}
              .
            </p>
          )}
          <button
            disabled={
              busy ||
              !reason.trim() ||
              !reviewer ||
              !expiry ||
              !selectedGrant ||
              managementScope !== scope
            }
            onClick={() =>
              void act(async () => {
                return api.put(
                  workspace,
                  `review-grants/${encodeURIComponent(datasetId)}/${reviewer}`,
                  {
                    expected_revision: selectedGrant!.revision,
                    expires_at: new Date(expiry).toISOString(),
                    reason,
                  },
                );
              }, 'Dataset review grant saved.')
            }
          >
            Grant dataset review access
          </button>
          <ul>
            {grants.map((item) => (
              <li key={item.id}>
                {item.name} ·{' '}
                {item.active && new Date(item.expires_at) > new Date()
                  ? 'Active'
                  : 'Inactive or expired'}{' '}
                · expires {new Date(item.expires_at).toLocaleString()}
                <button
                  disabled={busy || !reason.trim() || !item.active}
                  onClick={() =>
                    void act(
                      () =>
                        api.post(workspace, `review-grants/${item.id}/revoke`, {
                          expected_revision: item.revision,
                          reason,
                        }),
                      'Review grant revoked.',
                    )
                  }
                >
                  Revoke {item.name}
                </button>
              </li>
            ))}
          </ul>
          {!grants.length && <p>No reviewer grants on this page.</p>}
          <button
            disabled={grantOffset === 0}
            onClick={() => setGrantOffset((v) => Math.max(0, v - 50))}
          >
            Previous grants
          </button>
          <button disabled={grantNext === null} onClick={() => setGrantOffset(grantNext!)}>
            Next grants
          </button>
        </details>
      ) : (
        <p>Select an owned source snapshot above to manage dataset reviewers.</p>
      )}
      <h4>Assigned review inbox</h4>
      <p>
        Only explicitly assigned, unexpired dataset grants appear here. Filter literals are
        redacted. Open each submitted manifest before recording a decision.
      </p>
      {loading && <p role="status">Loading assigned reviews…</p>}
      {inbox && !inbox.items.length && !inbox.definitions.length && (
        <p>No submitted work awaiting your review on this page.</p>
      )}
      {inbox?.definitions.map((entry) => (
        <article key={entry.id}>
          <h4>
            {entry.key} v{entry.version} · dictionary review
          </h4>
          <p>{entry.spec?.description}</p>
          <p>
            Formula: {entry.content.metric.aggregation}({entry.content.metric.column}) · Units:{' '}
            {entry.content.units} · Grain: {entry.spec?.grain || 'Unknown'}.
          </p>
          <details>
            <summary>Review submitted definition {entry.key}</summary>
            <pre>{JSON.stringify(entry.spec, null, 2)}</pre>
          </details>
          <button
            disabled={busy || !reason.trim()}
            onClick={() => void approve(entry.id, entry.revision, true)}
          >
            Approve definition {entry.key}
          </button>
        </article>
      ))}
      {inbox?.items.map((item) => {
        const { rows, ...metadata } = item.payload;
        return (
          <article key={item.id}>
            <h4>
              {item.kind === 'workflow' ? 'Workflow' : 'Calculated output'} · {item.id.slice(0, 8)}
            </h4>
            <p>
              Dataset <code>{item.dataset_id}</code> · submitted revision {item.review.revision}
            </p>
            <ReviewSummary item={item} />
            <details>
              <summary>Review submitted calculation {item.id.slice(0, 8)}</summary>
              {Array.isArray(rows) && <AggregateRows rows={rows} />}
              <details>
                <summary>Technical calculation metadata</summary>
                <pre>{JSON.stringify(metadata, null, 2)}</pre>
              </details>
            </details>
            <button
              disabled={busy || !reason.trim()}
              onClick={() => void approve(item.id, item.review.revision)}
            >
              Approve {item.kind} {item.id.slice(0, 8)}
            </button>
          </article>
        );
      })}
      <button disabled={busy || offset === 0} onClick={() => setOffset((v) => Math.max(0, v - 50))}>
        Previous assigned reviews
      </button>
      <button
        disabled={busy || inbox?.next_offset == null}
        onClick={() => setOffset(inbox!.next_offset!)}
      >
        Next assigned reviews
      </button>
    </section>
  );
}
