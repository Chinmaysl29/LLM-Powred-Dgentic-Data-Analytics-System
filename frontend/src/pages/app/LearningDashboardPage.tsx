import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Activity, RefreshCw } from 'lucide-react';
import { perceptronDashboardService as api } from '../../services/perceptronDashboardService';
import type {
  DashboardWorkspace,
  Learner,
  LearningDashboard,
} from '../../services/perceptronDashboardService';
import '../../styles/learning-dashboard.css';

const names: Record<Learner, string> = {
  intent_router: 'Intent router',
  column_metric_resolver: 'Column resolver',
  chart_selector: 'Chart selector',
  provider_bandit: 'Provider selector',
};
const errors: Record<string, string> = {
  execution_error: 'Execution error',
  empty_result: 'Empty result',
  validator_rejection: 'Validation rejected',
  other: 'Other recorded failure',
};
const percent = (value: number | null) =>
  value === null ? 'Not available' : `${(value * 100).toFixed(1)}%`;
const date = (value: string) =>
  new Date(value).toLocaleString(undefined, { timeZone: 'UTC', timeZoneName: 'short' });

export function DashboardEvidence({ data }: { data: LearningDashboard }) {
  if (!data.enabled)
    return (
      <section className="ld-panel" role="status">
        <h2>Learning is disabled</h2>
        <p>
          Collection and learned selections are off. Dashboard evidence is hidden while learning is
          disabled.
        </p>
      </section>
    );
  const failures = data.top_mistakes.reduce((sum, row) => sum + row.count, 0);
  return (
    <>
      <div className="ld-stats">
        <section className="ld-panel">
          <h2>Recorded hard failures</h2>
          <strong>{failures}</strong>
          <p>Your accessible datasets in this workspace.</p>
        </section>
        <section className="ld-panel">
          <h2>Shadow observations</h2>
          <strong>{data.shadow.observations}</strong>
          <p>{data.shadow.abstentions} abstentions in this period.</p>
        </section>
        <section className="ld-panel">
          <h2>Shadow agreement</h2>
          <strong>{percent(data.shadow.agreement_rate)}</strong>
          <p>
            {data.shadow.agreements} of {data.shadow.compared} non-abstained comparisons. Agreement
            with the live router is not accuracy.
          </p>
        </section>
      </div>
      <section className="ld-panel" aria-labelledby="ld-accuracy">
        <h2 id="ld-accuracy">Reviewed accuracy over time</h2>
        <p>
          Golden-set results saved at successful promotion, ordered by evaluation time. These are
          historical benchmarks, not production accuracy. Different benchmark hashes are not
          directly comparable.
        </p>
        {!data.evaluations.length ? (
          <p>No reviewed promotion evaluations in this period.</p>
        ) : (
          <div
            className="ld-table-scroll"
            tabIndex={0}
            role="region"
            aria-label="Reviewed accuracy table"
          >
            <table>
              <thead>
                <tr>
                  <th>Evaluated (UTC)</th>
                  <th>Learner</th>
                  <th>Version</th>
                  <th>Golden accuracy</th>
                  <th>Correct / cases</th>
                  <th>Mean reward</th>
                  <th>Benchmark</th>
                </tr>
              </thead>
              <tbody>
                {data.evaluations.map((row, index) => (
                  <tr key={`${row.learner}-${row.version}-${index}`}>
                    <td>{date(row.created_at)}</td>
                    <th scope="row">{names[row.learner]}</th>
                    <td>{row.version}</td>
                    <td>
                      <meter
                        min={0}
                        max={1}
                        value={row.accuracy}
                        aria-label={`${names[row.learner]} version ${row.version} golden accuracy`}
                      />{' '}
                      {percent(row.accuracy)}
                    </td>
                    <td>
                      {row.correct} / {row.cases}
                    </td>
                    <td>
                      {row.mean_reward === null ? 'Not applicable' : row.mean_reward.toFixed(4)}
                    </td>
                    <td>
                      <code title={row.manifest_digest}>{row.manifest_digest.slice(0, 12)}</code>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <p>
          Provider accuracy requires every eligible exploratory provider to be correct. Its reward
          includes latency and cost penalties; reward is not an accuracy percentage.
        </p>
        {data.evaluations_truncated && (
          <p role="status">
            Showing the latest 100 evaluations per audit source. Narrow the period for older
            evidence.
          </p>
        )}
        {data.omitted_evaluations > 0 && (
          <p role="status">
            {data.omitted_evaluations} incomplete or invalid evaluation records were omitted.
          </p>
        )}
      </section>
      <section className="ld-panel" aria-labelledby="ld-mistakes">
        <h2 id="ld-mistakes">Top mistakes</h2>
        <p>
          Recorded hard failures by category. These counts are not verified training labels;
          questions and dataset contents are not shown.
        </p>
        {!data.top_mistakes.length ? (
          <p>No recorded hard failures in this period.</p>
        ) : (
          <ul className="ld-mistakes">
            {data.top_mistakes.map((row) => (
              <li key={row.error_type}>
                <span>{errors[row.error_type] || errors.other}</span>
                <strong>{row.count}</strong>
              </li>
            ))}
          </ul>
        )}
      </section>
      <section className="ld-panel" aria-labelledby="ld-versions">
        <h2 id="ld-versions">Weight version history</h2>
        <p>
          All dates. Intent-router versions are shared within your tenant; other versions are
          limited to your accessible datasets in this workspace. Selected means selected in storage;
          runtime approval and feature checks still apply.
        </p>
        {!data.versions.length ? (
          <p>No weight versions on this page.</p>
        ) : (
          <div
            className="ld-table-scroll"
            tabIndex={0}
            role="region"
            aria-label="Weight version table"
          >
            <table>
              <thead>
                <tr>
                  <th>Created (UTC)</th>
                  <th>Learner</th>
                  <th>Version</th>
                  <th>Stored selection</th>
                  <th>Scope</th>
                </tr>
              </thead>
              <tbody>
                {data.versions.map((row) => (
                  <tr key={`${row.learner}-${row.version}`}>
                    <td>{date(row.created_at)}</td>
                    <th scope="row">{names[row.learner]}</th>
                    <td>{row.version}</td>
                    <td>{row.selected ? 'Selected' : 'Not selected'}</td>
                    <td>{row.learner === 'intent_router' ? 'Shared tenant' : 'Your dataset'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </>
  );
}

export default function LearningDashboardPage() {
  const [params, setParams] = useSearchParams();
  const workspace = params.get('workspace') || '';
  const [workspaces, setWorkspaces] = useState<DashboardWorkspace[] | null>(null);
  const [workspaceError, setWorkspaceError] = useState(false);
  const [days, setDays] = useState(30);
  const [offset, setOffset] = useState(0);
  const [refresh, setRefresh] = useState(0);
  const [listRefresh, setListRefresh] = useState(0);
  const [result, setResult] = useState<{
    key: string;
    data?: LearningDashboard;
    error?: boolean;
  } | null>(null);
  const key = `${workspace}:${days}:${offset}:${refresh}`;
  useEffect(() => {
    const controller = new AbortController();
    api
      .workspaces(controller.signal)
      .then((items) => {
        if (!controller.signal.aborted) {
          setWorkspaces(items);
          setWorkspaceError(false);
        }
      })
      .catch(() => {
        if (!controller.signal.aborted) setWorkspaceError(true);
      });
    return () => controller.abort();
  }, [listRefresh]);
  useEffect(() => {
    if (!workspace) return;
    const controller = new AbortController();
    api
      .read(workspace, days, offset, controller.signal)
      .then((data) => {
        if (!controller.signal.aborted) setResult({ key, data });
      })
      .catch(() => {
        if (!controller.signal.aborted) setResult({ key, error: true });
      });
    return () => controller.abort();
  }, [workspace, days, offset, refresh, key]);
  const current = result?.key === key ? result : null;
  const busy = !!workspace && !current;
  return (
    <div className="page-container ld-page">
      <header className="ld-heading">
        <Activity aria-hidden="true" />
        <div>
          <h1>Learning dashboard</h1>
          <p>Read-only evidence for the NumPy learning layer.</p>
        </div>
      </header>
      <div className="ld-toolbar">
        <label>
          Workspace
          <select
            value={workspace}
            onChange={(event) => {
              setOffset(0);
              setParams(event.target.value ? { workspace: event.target.value } : {});
            }}
          >
            <option value="">Select a workspace</option>
            {workspace && workspaces && !workspaces.some((item) => item.id === workspace) && (
              <option value={workspace}>Requested workspace</option>
            )}
            {workspaces?.map((item) => (
              <option key={item.id} value={item.id}>
                {item.workspace_name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Evidence period
          <select
            value={days}
            onChange={(event) => {
              setDays(Number(event.target.value));
              setOffset(0);
            }}
          >
            <option value={7}>Last 7 days</option>
            <option value={30}>Last 30 days</option>
            <option value={90}>Last 90 days</option>
          </select>
        </label>
        <button
          type="button"
          disabled={!workspace || busy}
          onClick={() => {
            setOffset(0);
            setRefresh((value) => value + 1);
          }}
        >
          <RefreshCw size={16} aria-hidden="true" /> Refresh
        </button>
      </div>
      {workspaceError && (
        <div role="alert">
          Unable to load workspaces.{' '}
          <button type="button" onClick={() => setListRefresh((value) => value + 1)}>
            Retry workspaces
          </button>
        </div>
      )}
      {!workspace && !workspaceError && (
        <p role="status">
          {workspaces === null
            ? 'Loading workspaces…'
            : workspaces.length
              ? 'Select a workspace to view evidence.'
              : 'No accessible workspaces.'}
        </p>
      )}
      {busy && <p role="status">Loading learning evidence…</p>}
      {current?.error && (
        <div role="alert">
          Unable to load learning evidence. Access may have changed or the service may be
          unavailable.{' '}
          <button type="button" onClick={() => setRefresh((value) => value + 1)}>
            Retry evidence
          </button>
        </div>
      )}
      {current?.data && (
        <>
          <p className="ld-asof">
            As of {date(current.data.as_of)}. Period begins {date(current.data.since)}.
          </p>
          <DashboardEvidence data={current.data} />
          {current.data.enabled && (
            <nav className="ld-pagination" aria-label="Weight history pages">
              <button
                type="button"
                disabled={offset === 0}
                onClick={() => setOffset(Math.max(0, offset - 25))}
              >
                Previous versions
              </button>
              <span>Page {Math.floor(offset / 25) + 1}</span>
              <button
                type="button"
                disabled={current.data.next_offset === null}
                onClick={() => setOffset(current.data?.next_offset ?? offset)}
              >
                Next versions
              </button>
            </nav>
          )}
        </>
      )}
    </div>
  );
}
