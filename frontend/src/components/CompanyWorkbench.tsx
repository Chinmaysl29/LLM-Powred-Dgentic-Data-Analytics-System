import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  companyService as api,
  type DictionaryEntry,
  type Workflow,
  type Policy,
  type Comparison,
  type Incident,
} from '../services/companyService';
import { requestKey, type PlaneRecord } from '../services/dataplaneService';
import CalculationDrawer from './CalculationDrawer';
import DatasetReviewPanel from './DatasetReviewPanel';

const message = (e: unknown) =>
  e instanceof Error ? e.message : 'Request failed. Reload and retry.';
const save = (blob: Blob, name: string) => {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = name;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
};

export default function CompanyWorkbench({
  workspace,
  records,
  refresh,
}: {
  workspace: string;
  records: PlaneRecord[];
  refresh: () => void;
}) {
  const [entries, setEntries] = useState<DictionaryEntry[]>([]);
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [policy, setPolicy] = useState<Policy | null>(null);
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [search, setSearch] = useState('');
  const [offset, setOffset] = useState(0);
  const [next, setNext] = useState<number | null>(null);
  const [version, setVersion] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [dictionaryError, setDictionaryError] = useState('');
  const [panelError, setPanelError] = useState('');
  const [notice, setNotice] = useState('');
  const [snapshotId, setSnapshotId] = useState('');
  const [definitionId, setDefinitionId] = useState('');
  const [dimension, setDimension] = useState('');
  const [businessDate, setBusinessDate] = useState('');
  const [reason, setReason] = useState('');
  const [selfApproval, setSelfApproval] = useState(false);
  const [evidenceId, setEvidenceId] = useState('');
  const [previous, setPrevious] = useState('');
  const [current, setCurrent] = useState('');
  const [comparison, setComparison] = useState<Comparison | null>(null);
  const [details, setDetails] = useState<unknown>(null);
  const [activeVersion, setActiveVersion] = useState('');
  const [workflowName, setWorkflowName] = useState('');
  const [purpose, setPurpose] = useState('');
  const [scheduleTimezone, setScheduleTimezone] = useState('UTC');
  const [scheduleTime, setScheduleTime] = useState('09:00');
  const recordKey = records.map((r) => r.id).join(',');
  const visibleError = error || dictionaryError || panelError;

  useEffect(() => {
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      api
        .get<{ items: DictionaryEntry[]; next_offset: number | null }>(
          workspace,
          `dictionary?search=${encodeURIComponent(search)}&offset=${offset}`,
          controller.signal,
        )
        .then((dictionary) => {
          if (controller.signal.aborted) return;
          setEntries(dictionary.items);
          setNext(dictionary.next_offset);
          setDictionaryError('');
        })
        .catch((e) => {
          if (!controller.signal.aborted) {
            setEntries([]);
            setNext(null);
            setDictionaryError(message(e));
          }
        });
    }, 250);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [workspace, search, offset, version, recordKey]);

  useEffect(() => {
    const controller = new AbortController();
    Promise.all([
      api.get<{ items: Workflow[] }>(workspace, 'workflows', controller.signal),
      api.get<Policy>(workspace, 'policy', controller.signal),
      api.get<{ items: Incident[] }>(workspace, 'incidents', controller.signal),
    ])
      .then(([workflow, configuration, findings]) => {
        if (controller.signal.aborted) return;
        setWorkflows(workflow.items);
        setPolicy(configuration);
        setIncidents(findings.items);
        setPanelError('');
      })
      .catch((e) => {
        if (!controller.signal.aborted) {
          setWorkflows([]);
          setIncidents([]);
          setPolicy(null);
          setPanelError(message(e));
        }
      });
    return () => controller.abort();
  }, [workspace, version, recordKey]);

  async function act(task: () => Promise<unknown>, success: string) {
    setBusy(true);
    setError('');
    setNotice('');
    try {
      await task();
      setNotice(success);
      setVersion((v) => v + 1);
      refresh();
    } catch (e) {
      setError(message(e));
    } finally {
      setBusy(false);
    }
  }
  const snapshots = records.filter((r) => r.kind === 'snapshot');
  const evidence = records.filter((r) => r.kind === 'evidence');
  const snapshot = snapshots.find((r) => r.id === snapshotId);
  const selected = entries.find((e) => e.id === definitionId);
  const columns = Object.keys(snapshot?.payload.schema || {});
  const query = () => ({
    definition_id: definitionId,
    snapshot_id: snapshotId,
    business_date: businessDate,
    plan: { metric: selected?.key, dimensions: dimension ? [dimension] : [] },
    idempotency_key: requestKey(),
  });
  const ready = !!snapshot && !!selected && !!businessDate && selected.status === 'approved';
  const review = (id: string, revision: number, action: string, dictionary = false) =>
    act(
      () =>
        api.post(workspace, `${dictionary ? 'dictionary' : 'artifacts'}/${id}/review`, {
          expected_revision: revision,
          action,
          reason,
        }),
      'Review saved.',
    );

  return (
    <section aria-label="Company review">
      <h2>Company definitions and reporting</h2>
      <p>
        Approved definitions pin the calculation, source, and checks. Existing direct metrics are
        exploratory.
      </p>
      <button disabled={busy} onClick={() => setVersion((v) => v + 1)}>
        Refresh company review
      </button>
      {visibleError && (
        <p role="alert" className="dh-error">
          {visibleError} <button onClick={() => setVersion((v) => v + 1)}>Reload</button>
        </p>
      )}
      {notice && <p role="status">{notice}</p>}
      <details>
        <summary>Approval policy</summary>
        <p>
          Current self-approval policy:{' '}
          {policy?.allow_self_approval === null
            ? 'Not configured'
            : policy?.allow_self_approval
              ? 'Allowed'
              : 'Separate reviewer required'}
          . Only workspace managers can change this.
        </p>
        <label>
          <input
            type="checkbox"
            checked={selfApproval}
            onChange={(e) => setSelfApproval(e.target.checked)}
          />
          Allow authors to approve their own work
        </label>
        <button
          disabled={busy || !reason.trim() || !policy}
          onClick={() =>
            void act(
              () =>
                api.put(workspace, 'policy', {
                  allow_self_approval: selfApproval,
                  expected_revision: policy?.revision,
                  reason,
                }),
              'Company policy saved.',
            )
          }
        >
          Save explicit policy
        </button>
      </details>
      <label>
        Review or change reason
        <input
          value={reason}
          maxLength={500}
          onChange={(e) => setReason(e.target.value)}
          placeholder="Required for approvals, revocation and version changes"
        />
      </label>
      <label>
        Source snapshot
        <select
          aria-label="Source snapshot"
          value={snapshotId}
          onChange={(e) => {
            setSnapshotId(e.target.value);
            setActiveVersion('');
          }}
        >
          <option value="">Select an immutable snapshot</option>
          {snapshots.map((s) => (
            <option key={s.id} value={s.id}>
              {s.id.slice(0, 8)} · {s.payload.row_count} rows
            </option>
          ))}
        </select>
      </label>
      <DatasetReviewPanel
        key={`${workspace}:${snapshot?.dataset_id || ''}`}
        workspace={workspace}
        datasetId={snapshot?.dataset_id}
        canManage={!!policy && ['analyst', 'admin', 'owner'].includes(policy.role || '')}
      />
      <details>
        <summary>Create an immutable dictionary draft</summary>
        <p>
          Supply your reviewed company meaning. No definition is inferred from these fields. To edit
          an existing definition, use its key with a new version.
        </p>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            const form = new FormData(e.currentTarget);
            const value = (key: string) => String(form.get(key) || '');
            void act(async () => {
              if (!snapshot) throw new Error('Select a source snapshot.');
              const examples = JSON.parse(value('examples')) as unknown;
              await api.post(workspace, 'dictionary', {
                definition: {
                  key: value('key'),
                  version: Number(value('version')),
                  owner: value('owner'),
                  source: snapshot.id,
                  metric: {
                    column: value('column'),
                    aggregation: value('aggregation'),
                    missing: value('missing'),
                    definition_ref: null,
                  },
                  filters: [],
                  units: value('units'),
                  currency: value('currency') || null,
                  examples,
                },
                dataset_id: snapshot.dataset_id,
                description: value('description'),
                domain: value('domain'),
                aliases: value('aliases')
                  .split(',')
                  .map((v) => v.trim())
                  .filter(Boolean),
                grain: value('grain'),
                timezone: value('timezone'),
                date_basis: value('date_basis'),
                exclusions: [],
                effective_from: value('effective_from'),
                effective_to: value('effective_to') || null,
                health_rules: form.get('required')
                  ? [{ column: value('column'), check: 'not_null', severity: 'critical' }]
                  : [],
              });
            }, 'Draft saved. Submit it for review before approval.');
          }}
        >
          <label>
            Stable key
            <input name="key" required pattern="[a-z][a-z0-9_]{0,63}" />
          </label>
          <label>
            Version
            <input name="version" type="number" min="1" required defaultValue="1" />
          </label>
          <label>
            Owner
            <input name="owner" required maxLength={120} />
          </label>
          <label>
            Domain
            <input name="domain" required maxLength={100} />
          </label>
          <label>
            Description
            <textarea name="description" required maxLength={500} />
          </label>
          <label>
            Aliases, separated by commas
            <input name="aliases" />
          </label>
          <label>
            Field
            <select name="column" aria-label="Field" required>
              <option value="">Select a field</option>
              {columns.map((c) => (
                <option key={c}>{c}</option>
              ))}
            </select>
          </label>
          <label>
            Calculation
            <select name="aggregation" aria-label="Calculation">
              <option value="sum">Sum</option>
              <option value="mean">Average</option>
              <option value="count">Count nonmissing values</option>
              <option value="min">Minimum</option>
              <option value="max">Maximum</option>
            </select>
          </label>
          <label>
            Missing values
            <select name="missing" aria-label="Missing values">
              <option value="reject">Block calculation</option>
              <option value="exclude">Exclude and disclose</option>
            </select>
          </label>
          <label>
            <input name="required" type="checkbox" />
            Require a full-snapshot nonmissing check
          </label>
          <label>
            Unit
            <input name="units" required maxLength={80} />
          </label>
          <label>
            Currency, if applicable
            <input name="currency" maxLength={40} />
          </label>
          <label>
            Grain
            <input
              name="grain"
              required
              maxLength={200}
              placeholder="What one source row represents"
            />
          </label>
          <label>
            Time zone
            <input name="timezone" required defaultValue="UTC" />
          </label>
          <label>
            Date basis
            <input
              name="date_basis"
              required
              maxLength={200}
              placeholder="Describe which dates and records this definition covers"
            />
          </label>
          <label>
            Effective from
            <input name="effective_from" type="date" required />
          </label>
          <label>
            Effective until (exclusive)
            <input name="effective_to" type="date" />
          </label>
          <label>
            Reviewed calculation examples (JSON array)
            <textarea
              name="examples"
              required
              placeholder='[{"values": [10, 20], "expected": 30}]'
            />
          </label>
          <button disabled={busy || !snapshot}>Save draft</button>
        </form>
      </details>
      <label>
        Search dictionary
        <input
          value={search}
          onChange={(e) => {
            setSearch(e.target.value);
            setOffset(0);
          }}
        />
      </label>
      {!entries.length && (
        <p>No matching definitions. Create a draft using an uploaded snapshot.</p>
      )}
      <div className="dh-table-wrap">
        <table>
          <thead>
            <tr>
              <th>Definition</th>
              <th>Meaning</th>
              <th>Review</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {entries.map((entry) => (
              <tr key={entry.id}>
                <td>
                  {entry.key} v{entry.version}
                </td>
                <td>{entry.spec?.description || 'Historical definition without company review'}</td>
                <td>{entry.status}</td>
                <td>
                  <button
                    onClick={() =>
                      void act(
                        async () => setDetails(await api.get(workspace, 'dictionary/' + entry.id)),
                        'Definition details loaded.',
                      )
                    }
                  >
                    Details and history
                  </button>
                  {entry.status === 'draft' && (
                    <button
                      disabled={busy || !reason.trim()}
                      onClick={() => void review(entry.id, entry.revision, 'review', true)}
                    >
                      Submit for review
                    </button>
                  )}
                  {entry.status === 'review' && (
                    <button
                      disabled={busy || !reason.trim()}
                      onClick={() => void review(entry.id, entry.revision, 'approve', true)}
                    >
                      Approve definition
                    </button>
                  )}
                  {entry.status === 'approved' && (
                    <>
                      <button
                        disabled={busy || !reason.trim()}
                        onClick={() => void review(entry.id, entry.revision, 'revoke', true)}
                      >
                        Revoke
                      </button>
                      <button
                        disabled={busy || !reason.trim()}
                        onClick={() => void review(entry.id, entry.revision, 'supersede', true)}
                      >
                        Supersede
                      </button>
                    </>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {details !== null && (
        <details open>
          <summary>Definition record and review history</summary>
          <pre style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>
            {JSON.stringify(details, null, 2)}
          </pre>
          <button onClick={() => setDetails(null)}>Close details</button>
        </details>
      )}
      <button disabled={!offset} onClick={() => setOffset(Math.max(0, offset - 50))}>
        Previous definitions
      </button>
      <button disabled={next === null} onClick={() => setOffset(next || 0)}>
        Next definitions
      </button>
      <h3>Calculate with an approved definition</h3>
      <label>
        Approved definition
        <select
          aria-label="Approved definition"
          value={definitionId}
          onChange={(e) => setDefinitionId(e.target.value)}
        >
          <option value="">Choose a definition</option>
          {entries
            .filter((e) => e.status === 'approved' && e.spec?.dataset_id === snapshot?.dataset_id)
            .map((e) => (
              <option key={e.id} value={e.id}>
                {e.key} v{e.version}
              </option>
            ))}
        </select>
      </label>
      <label>
        Business date for definition eligibility
        <input type="date" value={businessDate} onChange={(e) => setBusinessDate(e.target.value)} />
      </label>
      <p>
        This date selects an effective definition. Source rows are filtered only by the recorded
        query filters.
      </p>
      <label>
        Group by
        <select
          aria-label="Company group by"
          value={dimension}
          onChange={(e) => setDimension(e.target.value)}
        >
          <option value="">All selected source rows</option>
          {columns.map((c) => (
            <option key={c}>{c}</option>
          ))}
        </select>
      </label>
      <button
        disabled={busy || !ready}
        onClick={() =>
          void act(
            () => api.post(workspace, 'query', query()),
            'Calculation queued. Its result or blocking incident appears below.',
          )
        }
      >
        Calculate approved metric
      </button>
      <details>
        <summary>Select a cleaned version or undo</summary>
        <p>
          The selected snapshot becomes active. Existing reports keep their original source
          versions.
        </p>
        <button
          disabled={busy || !snapshot}
          onClick={() =>
            void act(async () => {
              const versions = await api.get<{ id: string; active: boolean }[]>(
                workspace,
                'versions/' + snapshot?.dataset_id,
              );
              setActiveVersion(versions.find((v) => v.active)?.id || '');
            }, 'Current active version loaded. Review the target snapshot before changing it.')
          }
        >
          Load current active version
        </button>
        <p>Expected active version: {activeVersion || 'Load it before selecting a target'}</p>
        <button
          disabled={busy || !snapshot || !activeVersion || !reason.trim()}
          onClick={() =>
            void act(
              () =>
                api.post(workspace, 'versions/' + snapshot?.dataset_id + '/select', {
                  expected_active_version_id: activeVersion,
                  target_snapshot_id: snapshotId,
                  reason,
                }),
              'Active version changed. Historical snapshots remain available.',
            )
          }
        >
          Make selected snapshot active
        </button>
      </details>
      <h3>Show how this was calculated</h3>
      {!evidence.length && <p>No result evidence on this page yet.</p>}
      {evidence.map((e) => (
        <button key={e.id} onClick={() => setEvidenceId(e.id)}>
          Calculation {e.id.slice(0, 8)}
        </button>
      ))}
      {evidenceId && (
        <CalculationDrawer
          workspace={workspace}
          identity={evidenceId}
          onClose={() => setEvidenceId('')}
        />
      )}
      <h3>What changed?</h3>
      <label>
        Previous result
        <select
          aria-label="Previous result"
          value={previous}
          onChange={(e) => setPrevious(e.target.value)}
        >
          <option value="">Select result</option>
          {evidence.map((e) => (
            <option key={e.id} value={e.id}>
              {e.id.slice(0, 8)}
            </option>
          ))}
        </select>
      </label>
      <label>
        Current result
        <select
          aria-label="Current result"
          value={current}
          onChange={(e) => setCurrent(e.target.value)}
        >
          <option value="">Select result</option>
          {evidence.map((e) => (
            <option key={e.id} value={e.id}>
              {e.id.slice(0, 8)}
            </option>
          ))}
        </select>
      </label>
      <button
        disabled={busy || !previous || !current}
        onClick={() =>
          void act(
            async () =>
              setComparison(
                await api.post<Comparison>(workspace, 'compare', {
                  previous_id: previous,
                  current_id: current,
                }),
              ),
            'Comparison saved.',
          )
        }
      >
        Compare stored results
      </button>
      {comparison && (
        <div>
          <p>
            {comparison.comparable
              ? 'Comparable calculation definitions.'
              : 'Incompatible: ' + comparison.mismatches.join(', ')}
          </p>
          <div className="dh-table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Group</th>
                  <th>Previous</th>
                  <th>Current</th>
                  <th>Absolute delta ({comparison.absolute_change_unit})</th>
                  <th>Percent delta</th>
                  <th>Entity</th>
                </tr>
              </thead>
              <tbody>
                {comparison.rows.map((r, i) => (
                  <tr key={i}>
                    <td>{JSON.stringify(r.dimensions)}</td>
                    <td>{String(r.previous ?? 'Missing')}</td>
                    <td>{String(r.current ?? 'Missing')}</td>
                    <td>{r.absolute_change ?? 'Unavailable'}</td>
                    <td>
                      {r.percentage_change === null ? 'Undefined' : r.percentage_change + '%'}
                    </td>
                    <td>{r.entity}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p>
            {comparison.percentage_denominator}. {comparison.contribution_note}.{' '}
            {comparison.causality}
          </p>
          <button
            onClick={() =>
              void act(
                async () =>
                  save(
                    await api.download(workspace, comparison.id),
                    `comparison-${comparison.id}.json`,
                  ),
                'Comparison downloaded.',
              )
            }
          >
            Download comparison
          </button>
        </div>
      )}
      <h3>Approved workflows</h3>
      <label>
        Workflow name
        <input
          value={workflowName}
          onChange={(e) => setWorkflowName(e.target.value)}
          maxLength={100}
        />
      </label>
      <label>
        Purpose
        <input value={purpose} onChange={(e) => setPurpose(e.target.value)} maxLength={500} />
      </label>
      <button
        disabled={busy || !ready || !workflowName.trim() || !purpose.trim()}
        onClick={() =>
          void act(
            () =>
              api.post(workspace, 'workflows', {
                name: workflowName,
                purpose,
                query: query(),
                require_artifact_review: true,
              }),
            'Workflow draft saved. Review, approve and activate it before running.',
          )
        }
      >
        Save selected calculation as workflow draft
      </button>
      <label>
        Schedule time zone
        <input value={scheduleTimezone} onChange={(e) => setScheduleTimezone(e.target.value)} />
      </label>
      <label>
        Schedule local time
        <input type="time" value={scheduleTime} onChange={(e) => setScheduleTime(e.target.value)} />
      </label>
      <p>
        Schedules start disabled and require a successful manual run. Missed slots use the latest
        only; overlaps are skipped. During daylight-saving changes, the first occurrence runs and
        nonexistent times are skipped.
      </p>
      {!workflows.length && <p>No workflows in this workspace.</p>}
      {workflows.map((w) => (
        <article key={w.id}>
          <h4>
            {w.spec.name} v{w.version}
          </h4>
          <p>
            {w.spec.purpose} · {w.review.status} · Schedule{' '}
            {w.schedule.enabled ? 'enabled' : 'disabled'}
          </p>
          <details>
            <summary>Calculation manifest</summary>
            <p>Review this version's pinned inputs, calculation and limits before approving it.</p>
            <pre style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>
              {JSON.stringify(
                {
                  definition_id: w.spec.query.definition_id,
                  snapshot_id: w.spec.query.snapshot_id,
                  business_date: w.spec.query.business_date,
                  metric: w.spec.query.plan.metric,
                  dimensions: w.spec.query.plan.dimensions || [],
                  filters:
                    w.spec.query.plan.filters?.map((filter) => ({
                      ...filter,
                      value: '[redacted]',
                    })) || [],
                  time_window: w.spec.query.time_window || null,
                  relative_window: w.spec.relative_window || null,
                  source_selection: w.spec.source_selection || 'pinned',
                  resource_limits: w.spec.resources,
                  separate_artifact_review: w.spec.require_artifact_review,
                },
                null,
                2,
              )}
            </pre>
          </details>
          {(
            {
              draft: ['review'],
              review: ['approve'],
              approved: ['activate', 'revoke'],
              active: ['pause', 'revoke'],
              paused: ['activate', 'retire'],
            }[w.review.status] || []
          ).map((action) => (
            <button
              key={action}
              disabled={busy || !reason.trim()}
              onClick={() => void review(w.id, w.review.revision, action)}
            >
              {action}
            </button>
          ))}
          <button
            disabled={busy || w.review.status !== 'active'}
            onClick={() =>
              void act(
                () =>
                  api.post(workspace, `workflows/${w.id}/run`, { idempotency_key: requestKey() }),
                'Manual workflow queued. Its artifact requires separate review before download.',
              )
            }
          >
            Run manually
          </button>
          <button
            disabled={busy || !ready || !workflowName.trim() || !purpose.trim()}
            onClick={() =>
              void act(
                () =>
                  api.post(workspace, 'workflows', {
                    name: workflowName,
                    purpose,
                    query: query(),
                    require_artifact_review: true,
                    previous_version_id: w.id,
                  }),
                'New immutable workflow version created. It requires a new review.',
              )
            }
          >
            Create revised draft from selected calculation
          </button>
          <details>
            <summary>Recent runs and scheduled slots</summary>
            {!w.recent_runs?.length && <p>No runs yet.</p>}
            <ul>
              {w.recent_runs?.map((run) => (
                <li key={run.id}>
                  {run.id.slice(0, 8)}: {run.status}, attempt {run.attempt}
                  {run.error_code ? `, ${run.error_code}` : ''}. {run.schedule_slot || 'Manual run'}
                  . {run.schedule_policy}
                </li>
              ))}
            </ul>
          </details>
          <button
            disabled={busy}
            onClick={() =>
              void act(
                () =>
                  api.put(workspace, `workflows/${w.id}/schedule`, {
                    expected_revision: w.schedule.revision,
                    enabled: !w.schedule.enabled,
                    timezone: scheduleTimezone,
                    hour: Number(scheduleTime.split(':')[0]),
                    minute: Number(scheduleTime.split(':')[1]),
                  }),
                w.schedule.enabled
                  ? 'Schedule disabled.'
                  : 'Schedule enabled by your explicit action.',
              )
            }
          >
            {w.schedule.enabled ? 'Disable schedule' : 'Enable schedule'}
          </button>
        </article>
      ))}
      <h3>Data incidents and affected outputs</h3>
      {!incidents.length && (
        <p>
          No blocking incidents recorded. This does not establish that unconfigured checks passed.
        </p>
      )}
      {incidents.map((incident) => (
        <article key={incident.id}>
          <h4>
            Incident {incident.id.slice(0, 8)} · {incident.review.status}
          </h4>
          <p>
            Snapshot {incident.snapshot_id} · Coverage: {incident.coverage}. {incident.impact_limit}
          </p>
          <ul>
            {incident.checks.map((check, index) => (
              <li key={index}>
                {check.field}: {check.status}; observed {String(check.observed)}, expected{' '}
                {String(check.expected)}; {check.impact}
              </li>
            ))}
          </ul>
          <details>
            <summary>Affected outputs and lineage paths</summary>
            <ul>
              {incident.affected_outputs.map((output) => (
                <li key={output.id}>
                  {output.kind} {output.id.slice(0, 8)}: {output.impact}. {output.reason}.{' '}
                  {output.path.join(' → ')}
                </li>
              ))}
            </ul>
          </details>
          <button
            disabled={busy || !reason.trim() || incident.review.status !== 'draft'}
            onClick={() => void review(incident.id, incident.review.revision, 'acknowledge')}
          >
            Acknowledge incident
          </button>
          <button
            disabled={busy || !reason.trim() || incident.review.status !== 'acknowledged'}
            onClick={() => void review(incident.id, incident.review.revision, 'resolve')}
          >
            Resolve with passing recheck
          </button>
          <p>
            Acknowledgement does not change the original failed check. Recovery requires new passing
            evidence.
          </p>
        </article>
      ))}
      <h3>Reviewed correction memory</h3>
      <p>
        Submit corrections against their originating analysis. Independent checks and manager review
        precede reuse.
      </p>
      <Link to={`/verified-learning?workspace=${encodeURIComponent(workspace)}`}>
        Open existing correction review and reuse history
      </Link>
    </section>
  );
}
