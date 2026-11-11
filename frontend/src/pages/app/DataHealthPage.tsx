import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  dataplaneService as api,
  requestKey,
  type PlaneDashboard,
  type PlaneRecord,
} from '../../services/dataplaneService';
import '../../styles/data-health.css';
import CompanyWorkbench from '../../components/CompanyWorkbench';

const errorMessage = (error: unknown) =>
  error instanceof Error ? error.message : 'Request failed. Please retry.';

export default function DataHealthPage() {
  const [params, setParams] = useSearchParams();
  const workspace = params.get('workspace') || '';
  const [workspaces, setWorkspaces] = useState<{ id: string; workspace_name: string }[]>([]);
  const [enabled, setEnabled] = useState<boolean | null>(null);
  const [limit, setLimit] = useState(100);
  const [state, setState] = useState<{ scope: string; data: PlaneDashboard } | null>(null);
  const [offset, setOffset] = useState(0);
  const [refresh, setRefresh] = useState(0);
  const [selected, setSelected] = useState('');
  const [metric, setMetric] = useState('');
  const [dimension, setDimension] = useState('');
  const [metricName, setMetricName] = useState('');
  const [column, setColumn] = useState('');
  const [aggregation, setAggregation] = useState('sum');
  const [description, setDescription] = useState('');
  const [cleaning, setCleaning] = useState('drop_nulls');
  const [cleanColumn, setCleanColumn] = useState('');
  const [reason, setReason] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [loadError, setLoadError] = useState('');
  const [startupRetry, setStartupRetry] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    Promise.all([api.status(controller.signal), api.workspaces(controller.signal)])
      .then(([status, list]) => {
        if (!controller.signal.aborted) {
          setEnabled(status.enabled);
          setLimit(status.upload_mb);
          setWorkspaces(list);
        }
      })
      .catch((e) => {
        if (!controller.signal.aborted) setError(errorMessage(e));
      });
    return () => controller.abort();
  }, [startupRetry]);

  useEffect(() => {
    if (!workspace || !enabled) return;
    const controller = new AbortController();
    let running = false;
    const load = async () => {
      if (running) return;
      running = true;
      try {
        const data = await api.dashboard(workspace, offset, controller.signal);
        if (!controller.signal.aborted) {
          setState({ scope: workspace, data });
          setLoadError('');
        }
      } catch (e) {
        if (!controller.signal.aborted) {
          setState(null);
          setLoadError(errorMessage(e));
        }
      } finally {
        running = false;
      }
    };
    void load();
    const timer = window.setInterval(() => void load(), 5000);
    return () => {
      controller.abort();
      window.clearInterval(timer);
    };
  }, [workspace, enabled, offset, refresh]);

  const data = state?.scope === workspace ? state.data : null;
  const records = data?.records || [];
  const snapshots = records.filter((r) => r.kind === 'snapshot');
  const snapshot = snapshots.find((r) => r.id === selected);
  const columns = Object.keys(snapshot?.payload.schema || {});
  const metrics = records.filter((r) => r.kind === 'metric' && r.parent_id === selected);
  const selectedMetric = metrics.find((r) => r.id === metric);

  async function act(action: () => Promise<unknown>, success: string) {
    setBusy(true);
    setError('');
    setMessage('');
    try {
      await action();
      setMessage(success);
      setRefresh((v) => v + 1);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }
  async function download(record: PlaneRecord) {
    const blob = await api.report(workspace, record.id);
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = 'evidence-' + record.id + '.pdf';
    link.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  return (
    <div className="page-container data-health">
      <header>
        <p className="dh-eyebrow">DATA PROCESSING</p>
        <h1>Data health</h1>
        <p>Review dataset snapshots, calculated results, and changes before applying them.</p>
      </header>
      {(error || loadError) && (
        <div role="alert" className="dh-error">
          {error || loadError}
          <button
            onClick={() => {
              setStartupRetry((v) => v + 1);
              setRefresh((v) => v + 1);
            }}
          >
            Retry
          </button>
        </div>
      )}
      {message && <p role="status">{message}</p>}
      {enabled === null && !error && <p role="status">Loading data processing status…</p>}
      {enabled === false && (
        <section>
          <h2>Data processing is disabled</h2>
          <p>
            Your existing dataset and analysis tools remain available. An administrator can enable
            the data processing service after verification.
          </p>
        </section>
      )}
      {enabled && (
        <>
          <label>
            Workspace
            <select
              aria-label="Workspace"
              value={workspace}
              onChange={(e) => {
                setParams(e.target.value ? { workspace: e.target.value } : {});
                setSelected('');
                setMetric('');
                setOffset(0);
                setMessage('');
              }}
            >
              <option value="">Select a workspace</option>
              {workspaces.map((w) => (
                <option key={w.id} value={w.id}>
                  {w.workspace_name}
                </option>
              ))}
            </select>
          </label>
          {workspaces.length === 0 && <p>No accessible workspaces.</p>}
          {workspace && (
            <>
              <CompanyWorkbench
                key={workspace}
                workspace={workspace}
                records={data?.records || []}
                refresh={() => setRefresh((v) => v + 1)}
              />
              <section>
                <h2>Upload for background processing</h2>
                <p>
                  CSV, TSV, Parquet, XLSX or JSONL, up to {limit} MiB. Original files are preserved.
                </p>
                <input
                  aria-label="Dataset file"
                  type="file"
                  accept=".csv,.tsv,.parquet,.xlsx,.jsonl,.ndjson"
                  onChange={(e) => setFile(e.target.files?.[0] || null)}
                />
                <button
                  disabled={busy || !file}
                  onClick={() =>
                    file &&
                    void act(
                      () => api.upload(workspace, file),
                      'Upload queued. Processing status appears below.',
                    )
                  }
                >
                  Upload dataset
                </button>
              </section>
              {!data && !error && <p role="status">Loading workspace records…</p>}
              <section>
                <h2>Snapshots</h2>
                {!snapshots.length && (
                  <p>No snapshots on this page. Upload a dataset or check a processing job.</p>
                )}
                <select
                  aria-label="Snapshot"
                  value={selected}
                  onChange={(e) => {
                    setSelected(e.target.value);
                    setMetric('');
                    setColumn('');
                    setDimension('');
                    setCleanColumn('');
                  }}
                >
                  <option value="">Select a snapshot</option>
                  {snapshots.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.payload.row_count?.toLocaleString()} rows ·{' '}
                      {new Date(s.created_at).toLocaleString()} · {s.id.slice(0, 8)}
                    </option>
                  ))}
                </select>
                {snapshot && (
                  <>
                    <p>
                      Snapshot <code>{snapshot.id}</code> ·{' '}
                      {snapshot.payload.row_count?.toLocaleString()} rows
                    </p>
                    <button
                      disabled={busy}
                      onClick={() =>
                        void act(
                          () => api.post(workspace, 'snapshots/' + snapshot.id + '/quality'),
                          'Daily health check queued.',
                        )
                      }
                    >
                      Run health check
                    </button>
                    {snapshot.payload.reconciliation && (
                      <p>
                        Reconciliation: {snapshot.payload.reconciliation.before} before,{' '}
                        {snapshot.payload.reconciliation.after} after,{' '}
                        {snapshot.payload.reconciliation.quarantined} quarantined.
                      </p>
                    )}
                  </>
                )}
              </section>
              {snapshot && (
                <div className="dh-grid">
                  <section>
                    <h2>Define a metric</h2>
                    <p>
                      Describe exactly what the column and aggregation mean. Definitions are saved
                      as immutable versions.
                    </p>
                    <form
                      onSubmit={(e) => {
                        e.preventDefault();
                        void act(
                          () =>
                            api.post(workspace, 'metrics', {
                              dataset_id: snapshot.dataset_id,
                              snapshot_id: snapshot.id,
                              definition: {
                                name: metricName,
                                column: column || null,
                                aggregation,
                                description,
                              },
                            }),
                          'Metric definition saved.',
                        );
                      }}
                    >
                      <label>
                        Name
                        <input
                          required
                          pattern="[a-zA-Z][a-zA-Z0-9_]*"
                          maxLength={80}
                          value={metricName}
                          onChange={(e) => setMetricName(e.target.value)}
                        />
                      </label>
                      <label>
                        Aggregation
                        <select
                          aria-label="Aggregation"
                          value={aggregation}
                          onChange={(e) => setAggregation(e.target.value)}
                        >
                          {['sum', 'avg', 'min', 'max', 'count'].map((v) => (
                            <option key={v}>{v}</option>
                          ))}
                        </select>
                      </label>
                      <label>
                        Column
                        <select
                          aria-label="Column"
                          required={aggregation !== 'count'}
                          value={column}
                          onChange={(e) => setColumn(e.target.value)}
                        >
                          <option value="">All rows (count only)</option>
                          {columns.map((c) => (
                            <option key={c}>{c}</option>
                          ))}
                        </select>
                      </label>
                      <label>
                        Definition
                        <textarea
                          required
                          maxLength={500}
                          value={description}
                          onChange={(e) => setDescription(e.target.value)}
                        />
                      </label>
                      <button disabled={busy}>Save definition</button>
                    </form>
                  </section>
                  <section>
                    <h2>Calculate a result</h2>
                    <label>
                      Metric
                      <select
                        aria-label="Metric"
                        value={metric}
                        onChange={(e) => setMetric(e.target.value)}
                      >
                        <option value="">Select a definition</option>
                        {metrics.map((m) => (
                          <option value={m.id} key={m.id}>
                            {m.payload.definition?.name}
                          </option>
                        ))}
                      </select>
                    </label>
                    {selectedMetric && <p>{selectedMetric.payload.definition?.description}</p>}
                    <label>
                      Group by
                      <select
                        aria-label="Group by"
                        value={dimension}
                        onChange={(e) => setDimension(e.target.value)}
                      >
                        <option value="">No grouping</option>
                        {columns.map((c) => (
                          <option key={c}>{c}</option>
                        ))}
                      </select>
                    </label>
                    <button
                      disabled={busy || !selectedMetric}
                      onClick={() =>
                        selectedMetric &&
                        void act(
                          () =>
                            api.post(workspace, 'query', {
                              snapshot_id: snapshot.id,
                              metric_id: selectedMetric.id,
                              idempotency_key: requestKey(),
                              plan: {
                                metric: selectedMetric.payload.definition?.name,
                                dimensions: dimension ? [dimension] : [],
                                limit: 100,
                              },
                            }),
                          'Calculation queued. Its result will appear with the evidence below.',
                        )
                      }
                    >
                      Calculate
                    </button>
                  </section>
                  <section>
                    <h2>Propose a cleaning change</h2>
                    <p>
                      A sample comparison is generated first. Applying it requires a separate
                      approval.
                    </p>
                    <label>
                      Operation
                      <select
                        aria-label="Operation"
                        value={cleaning}
                        onChange={(e) => setCleaning(e.target.value)}
                      >
                        <option value="drop_nulls">Remove rows with missing values</option>
                        <option value="deduplicate">Remove duplicate keys</option>
                        <option value="trim">Trim text whitespace</option>
                      </select>
                    </label>
                    <label>
                      Column
                      <select
                        aria-label="Column"
                        value={cleanColumn}
                        onChange={(e) => setCleanColumn(e.target.value)}
                      >
                        <option value="">Select a column</option>
                        {columns.map((c) => (
                          <option key={c}>{c}</option>
                        ))}
                      </select>
                    </label>
                    <label>
                      Reason
                      <textarea
                        maxLength={500}
                        value={reason}
                        onChange={(e) => setReason(e.target.value)}
                      />
                    </label>
                    <button
                      disabled={busy || !cleanColumn || !reason.trim()}
                      onClick={() =>
                        void act(
                          () =>
                            api.post(workspace, 'snapshots/' + snapshot.id + '/cleaning', {
                              plan: { operation: cleaning, columns: [cleanColumn], reason },
                            }),
                          'Sample comparison queued. Review it below before approving.',
                        )
                      }
                    >
                      Test proposal
                    </button>
                  </section>
                </div>
              )}
              <section>
                <h2>Processing jobs</h2>
                {data?.jobs.length === 0 && <p>No processing jobs.</p>}
                <div className="dh-scroll">
                  <table>
                    <thead>
                      <tr>
                        <th>Operation</th>
                        <th>Status</th>
                        <th>Attempt</th>
                        <th>Action</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data?.jobs.map((j) => (
                        <tr key={j.id}>
                          <td>{j.kind.replace('dp_', '')}</td>
                          <td>
                            {j.status}
                            {j.error_code ? ' · ' + j.error_code : ''}
                          </td>
                          <td>{j.attempt}</td>
                          <td>
                            {['QUEUED', 'RUNNING'].includes(j.status) && (
                              <button
                                disabled={busy}
                                onClick={() =>
                                  void act(
                                    () => api.post(workspace, 'jobs/' + j.id + '/cancel'),
                                    'Cancellation requested.',
                                  )
                                }
                              >
                                Cancel
                              </button>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
              {records
                .filter((r) => r.kind === 'proposal')
                .map((r) => (
                  <section key={r.id}>
                    <h2>Cleaning approval</h2>
                    {r.payload.preview_rows && (
                      <details>
                        <summary>Before and after preview rows</summary>
                        <p>{r.payload.preview_rows.coverage}</p>
                        <pre style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>
                          {JSON.stringify(r.payload.preview_rows, null, 2)}
                        </pre>
                      </details>
                    )}
                    <p>
                      {r.payload.plan?.operation}: {r.payload.plan?.reason}
                    </p>
                    <p>
                      Sample: {r.payload.sample?.before} rows before, {r.payload.sample?.after}{' '}
                      after, {r.payload.sample?.removed} removed. This sample is not a population
                      estimate.
                    </p>
                    <button
                      disabled={
                        busy || records.some((a) => a.kind === 'approval' && a.parent_id === r.id)
                      }
                      onClick={() =>
                        void act(
                          () => api.post(workspace, 'proposals/' + r.id + '/approve'),
                          'Approved. A new snapshot will be created; the original is preserved.',
                        )
                      }
                    >
                      Approve and create new version
                    </button>
                  </section>
                ))}
              {records
                .filter((r) => r.kind === 'quality')
                .map((r) => (
                  <section key={r.id}>
                    <h2>Health findings</h2>
                    <p>
                      {new Date(r.created_at).toLocaleString()} ·{' '}
                      {r.payload.row_count?.toLocaleString()} rows · {r.payload.duplicate_rows}{' '}
                      duplicate rows
                    </p>
                    <p>
                      Volume baseline: {r.payload.volume?.status}. {r.payload.volume?.message}
                    </p>
                    <p>
                      Snapshot age: {Math.round((r.payload.snapshot_age_seconds || 0) / 3600)}{' '}
                      hours. Business freshness needs an event-time definition.
                    </p>
                    <ul>
                      {r.payload.columns
                        ?.filter((c) => c.nulls > 0)
                        .map((c) => (
                          <li key={c.column}>
                            {c.column}: {c.nulls} missing ({(c.missing_fraction * 100).toFixed(1)}%)
                          </li>
                        ))}
                    </ul>
                    {r.payload.distribution_warnings?.map((c) => (
                      <p key={c.column}>
                        {c.column}: mean shifted by {c.mean_shift_stddevs.toFixed(1)} prior standard
                        deviations. Investigate before drawing a business conclusion.
                      </p>
                    ))}
                  </section>
                ))}
              {records
                .filter((r) => r.kind === 'evidence')
                .map((r) => (
                  <section key={r.id}>
                    <h2>Calculated result</h2>
                    <p>
                      {r.payload.engine} · {r.payload.result_rows} groups · {r.payload.elapsed_ms}{' '}
                      ms
                    </p>
                    <p className="dh-hash">
                      Evidence {r.id}
                      <br />
                      Query {r.payload.query_hash}
                    </p>
                    <div className="dh-scroll">
                      <table>
                        <thead>
                          <tr>
                            {Object.keys(r.payload.rows?.[0] || {}).map((c) => (
                              <th key={c}>{c}</th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {r.payload.rows?.slice(0, 100).map((row, i) => (
                            <tr key={i}>
                              {Object.entries(row).map(([c, v]) => (
                                <td key={c}>{v === null ? 'Missing' : String(v)}</td>
                              ))}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                    <button
                      disabled={busy}
                      onClick={() => void act(() => download(r), 'Evidence report downloaded.')}
                    >
                      Download evidence PDF
                    </button>
                  </section>
                ))}
              <nav aria-label="Record pages">
                <button disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 50))}>
                  Newer records
                </button>
                <button
                  disabled={data?.next_offset == null}
                  onClick={() => data?.next_offset != null && setOffset(data.next_offset)}
                >
                  Older records
                </button>
              </nav>
            </>
          )}
        </>
      )}
    </div>
  );
}
