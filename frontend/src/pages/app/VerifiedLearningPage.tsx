import { useCallback, useEffect, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { ShieldCheck, RefreshCw, Download } from 'lucide-react';
import { ApiError } from '../../api/client';
import { datasetService } from '../../services/datasetService';
import type { Dataset } from '../../types/datasets';
import { learningService as api } from '../../services/learningService';
import AdaptiveWorkbench from '../../components/AdaptiveWorkbench';
import type {
  Bundle,
  CaseInput,
  Controls,
  Definition,
  Evaluation,
  EvaluationCase,
  FeedbackCategory,
  Lesson,
  Metric,
  Monitor,
  RunStatus,
  RunSummary,
  TaskSpec,
  Workspace,
} from '../../services/learningService';
import '../../styles/verified-learning.css';

const stages = [
  'Interpretation',
  'Authorized inputs',
  'Preparation',
  'Data quality',
  'Calculation & validation',
  'Chart & report',
  'Evidence summary',
];
const terminal = new Set(['succeeded', 'waiting_for_input', 'partial', 'failed', 'cancelled']);
type Lists = {
  runs: RunSummary[];
  lessons: Lesson[];
  bundles: Bundle[];
  cases: EvaluationCase[];
  evaluations: Evaluation[];
};
type ListName = keyof Lists;

export default function VerifiedLearningPage() {
  const [params, setParams] = useSearchParams();
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [workspace, setWorkspace] = useState(params.get('workspace') || '');
  const [tab, setTab] = useState(params.get('view') || 'analysis');
  const [controls, setControls] = useState<Controls | null>(null);
  const [definitions, setDefinitions] = useState<Definition[]>([]);
  const [lists, setLists] = useState<Lists>({
    runs: [],
    lessons: [],
    bundles: [],
    cases: [],
    evaluations: [],
  });
  const [offsets, setOffsets] = useState<Record<ListName, number | null>>({
    runs: null,
    lessons: null,
    bundles: null,
    cases: null,
    evaluations: null,
  });
  const [runId, setRunId] = useState(params.get('run') || '');
  const [run, setRun] = useState<RunStatus | null>(null);
  const [selectedLesson, setSelectedLesson] = useState<Lesson | null>(null);
  const [monitor, setMonitor] = useState<Monitor | null>(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [datasetId, setDatasetId] = useState('');
  const [version, setVersion] = useState(1);
  const [objective, setObjective] = useState('');
  const [column, setColumn] = useState('');
  const [aggregation, setAggregation] = useState<Metric['aggregation']>('sum');
  const [missing, setMissing] = useState<Metric['missing']>('reject');
  const [dimension, setDimension] = useState('');
  const [units, setUnits] = useState('source units');
  const [currency, setCurrency] = useState('');
  const [definitionRef, setDefinitionRef] = useState('');
  const [dateColumn, setDateColumn] = useState('');
  const [dateFormat, setDateFormat] = useState('%Y-%m-%d');
  const [dateStart, setDateStart] = useState('');
  const [dateEnd, setDateEnd] = useState('');
  const [timezone, setTimezone] = useState('Asia/Kolkata');
  const [rightDataset, setRightDataset] = useState('');
  const [rightVersion, setRightVersion] = useState(1);
  const [leftKey, setLeftKey] = useState('order_id');
  const [rightKey, setRightKey] = useState('order_id');
  const [orderAmount, setOrderAmount] = useState('amount');
  const [refundAmount, setRefundAmount] = useState('refund');
  const [relationshipPurpose, setRelationshipPurpose] = useState<
    'order_net_revenue' | 'refund_event_count'
  >('order_net_revenue');
  const [confirmedTask, setConfirmedTask] = useState<TaskSpec | null>(null);
  const [filterColumn, setFilterColumn] = useState('');
  const [excludedValues, setExcludedValues] = useState('');
  const [feedbackCategory, setFeedbackCategory] = useState<FeedbackCategory>('calculation');
  const [feedbackText, setFeedbackText] = useState('');
  const [correctionColumn, setCorrectionColumn] = useState('');
  const [reason, setReason] = useState('');
  const [bundleId, setBundleId] = useState('');
  const [caseIds, setCaseIds] = useState<string[]>([]);
  const [minCases, setMinCases] = useState(30);
  const [scenario, setScenario] = useState('');
  const [caseSplit, setCaseSplit] = useState<CaseInput['split']>('final');
  const [labelSource, setLabelSource] = useState<CaseInput['label_source']>('synthetic');
  const [labelReference, setLabelReference] = useState('');
  const [expectedStatus, setExpectedStatus] = useState<CaseInput['expected_status']>('verified');
  const [expectedRows, setExpectedRows] = useState([{ group: '', value: '' }]);
  const [definitionKey, setDefinitionKey] = useState('');
  const [definitionVersion, setDefinitionVersion] = useState(1);
  const [definitionOwner, setDefinitionOwner] = useState('');
  const [definitionSource, setDefinitionSource] = useState('');
  const [definitionExample, setDefinitionExample] = useState('');
  const workspaceRef = useRef(workspace);
  const canReview = !!controls?.can_review;
  const hydratedRun = useRef('');
  const applyTask = useCallback((value: TaskSpec) => {
    setDatasetId(value.datasets[0].dataset_id);
    setVersion(value.datasets[0].version);
    setObjective(value.objective);
    setColumn(value.metrics[0].column);
    setAggregation(value.metrics[0].aggregation);
    setMissing(value.metrics[0].missing);
    setDimension(value.dimensions[0] || '');
    setUnits(value.units);
    setCurrency(value.currency || '');
    setDefinitionRef(value.metrics[0].definition_ref || '');
    setTimezone(value.timezone);
    setDateColumn(value.date_range?.column || '');
    setDateFormat(value.date_range?.format || '%Y-%m-%d');
    setDateStart(
      value.date_range ? new Date(value.date_range.start).toISOString().slice(0, 16) : '',
    );
    setDateEnd(value.date_range ? new Date(value.date_range.end).toISOString().slice(0, 16) : '');
    setRightDataset(value.datasets[1]?.dataset_id || '');
    setRightVersion(value.datasets[1]?.version || 1);
    const relation = value.relationships?.[0];
    if (relation) {
      setLeftKey(relation.left_key);
      setRightKey(relation.right_key);
      setOrderAmount(relation.order_amount);
      setRefundAmount(relation.refund_amount);
      setRelationshipPurpose(relation.purpose);
    }
    setConfirmedTask(value);
  }, []);

  function showError(e: unknown) {
    const prefix =
      e instanceof ApiError
        ? e.status === 0
          ? 'Disconnected. '
          : [401, 403, 404].includes(e.status)
            ? 'Access unavailable. '
            : ''
        : '';
    setError(prefix + (e instanceof Error ? e.message : 'The request failed.'));
  }
  const refresh = useCallback(async (w: string) => {
    const [cfg, defs, history, memory] = await Promise.all([
      api.controls(w),
      api.definitions(w),
      api.runs(w),
      api.lessons(w),
    ]);
    if (workspaceRef.current !== w) return;
    setControls(cfg);
    setDefinitions(defs);
    setLists((v) => ({ ...v, runs: history.items, lessons: memory.items }));
    setOffsets((v) => ({ ...v, runs: history.next_offset, lessons: memory.next_offset }));
    if (cfg.can_review) {
      const [bs, cs, es, ms] = await Promise.all([
        api.bundles(w),
        api.cases(w),
        api.evaluations(w),
        api.monitor(w),
      ]);
      if (workspaceRef.current !== w) return;
      setLists((v) => ({ ...v, bundles: bs.items, cases: cs.items, evaluations: es.items }));
      setMonitor(ms);
      setOffsets((v) => ({
        ...v,
        bundles: bs.next_offset,
        cases: cs.next_offset,
        evaluations: es.next_offset,
      }));
    }
  }, []);
  useEffect(() => {
    let live = true;
    Promise.all([api.workspaces(), datasetService.list()])
      .then(([ws, ds]) => {
        if (!live) return;
        setWorkspaces(ws);
        setDatasets(ds);
        setWorkspace((current) => {
          const selected = current || ws[0]?.id || '';
          workspaceRef.current = selected;
          return selected;
        });
      })
      .catch((e) => {
        if (live) showError(e);
      })
      .finally(() => {
        if (live) setLoading(false);
      });
    return () => {
      live = false;
    };
  }, []);
  useEffect(() => {
    if (!workspace) return;
    let live = true;
    refresh(workspace)
      .catch((e) => {
        if (live) showError(e);
      })
      .finally(() => {
        if (live) setLoading(false);
      });
    return () => {
      live = false;
    };
  }, [workspace, refresh]);
  useEffect(() => {
    if (!runId) return;
    const abort = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const result = await api.run(runId, abort.signal);
        if (abort.signal.aborted) return;
        setRun(result);
        if (result.task && hydratedRun.current !== runId) {
          hydratedRun.current = runId;
          applyTask(result.task);
        }
        setLists((current) => ({
          ...current,
          runs: current.runs.map((item) =>
            item.id === result.run_id
              ? { ...item, state: result.state, task: result.task, error_code: result.error_code }
              : item,
          ),
        }));
        if (!terminal.has(result.state))
          timer = setTimeout(() => {
            void poll();
          }, 1500);
      } catch (e) {
        if (!abort.signal.aborted) showError(e);
      }
    }
    void poll();
    return () => {
      abort.abort();
      clearTimeout(timer);
    };
  }, [runId, applyTask]);
  useEffect(() => {
    if (!workspace || !lists.evaluations.some((e) => ['queued', 'running'].includes(e.state)))
      return;
    const w = workspace;
    const timer = setTimeout(() => {
      api
        .evaluations(w)
        .then((p) => {
          if (workspaceRef.current === w) setLists((v) => ({ ...v, evaluations: p.items }));
        })
        .catch(showError);
    }, 2000);
    return () => clearTimeout(timer);
  }, [workspace, lists.evaluations]);

  async function action(work: () => Promise<void>) {
    setBusy(true);
    setError('');
    setNotice('');
    try {
      await work();
    } catch (e) {
      showError(e);
    } finally {
      setBusy(false);
    }
  }
  async function more(name: ListName) {
    const offset = offsets[name];
    if (offset === null) return;
    const p = await api[name](workspace, offset);
    setLists((v) => ({ ...v, [name]: [...v[name], ...p.items] }));
    setOffsets((v) => ({ ...v, [name]: p.next_offset }));
  }
  function chooseWorkspace(value: string) {
    if (value === workspace) return;
    workspaceRef.current = value;
    setLoading(true);
    setWorkspace(value);
    setParams({ workspace: value });
    setRunId('');
    setRun(null);
    setControls(null);
    setLists({ runs: [], lessons: [], bundles: [], cases: [], evaluations: [] });
    setSelectedLesson(null);
    setCaseIds([]);
    setDefinitionRef('');
    setDatasetId('');
    setRightDataset('');
    setConfirmedTask(null);
    setError('');
    setNotice('');
  }
  function chooseRun(id: string) {
    setRun(null);
    setRunId(id);
    setParams({ workspace, run: id });
    const saved = lists.runs.find((item) => item.id === id)?.task;
    if (saved) applyTask(saved);
  }
  function selectDefinition(ref: string) {
    setDefinitionRef(ref);
    const d = definitions.find((x) => x.reference === ref);
    if (d) {
      setColumn(d.content.metric.column);
      setAggregation(d.content.metric.aggregation);
      setMissing(d.content.metric.missing);
      setUnits(d.content.units);
      setCurrency(d.content.currency || '');
    }
  }
  function task(): TaskSpec {
    if (confirmedTask) return confirmedTask;
    if (!workspace || !datasetId || !objective.trim() || !column.trim() || !units.trim())
      throw new Error('Select a workspace, dataset, objective, metric and units in Analysis.');
    const def = definitions.find((d) => d.reference === definitionRef);
    return {
      workspace_id: workspace,
      objective: objective.trim(),
      task_type: 'descriptive',
      datasets: [
        { dataset_id: datasetId, version },
        ...(rightDataset ? [{ dataset_id: rightDataset, version: rightVersion }] : []),
      ],
      metrics: [
        { column: column.trim(), aggregation, missing, definition_ref: definitionRef || null },
      ],
      dimensions: dimension.trim() ? [dimension.trim()] : [],
      grain: rightDataset
        ? relationshipPurpose === 'refund_event_count'
          ? 'one refund event'
          : 'one order'
        : 'one source record; no implicit deduplication',
      filters:
        def?.content.filters ||
        (filterColumn && excludedValues
          ? [
              {
                column: filterColumn,
                operator: 'not_in',
                value: excludedValues.split(',').map((v) => v.trim()),
              },
            ]
          : []),
      date_range: dateColumn
        ? {
            column: dateColumn,
            format: dateFormat,
            start: new Date(`${dateStart}Z`).toISOString(),
            end: new Date(`${dateEnd}Z`).toISOString(),
          }
        : null,
      timezone,
      units: units.trim(),
      currency: currency.trim() || null,
      output: 'report',
      definition_refs: definitionRef ? [definitionRef] : [],
      assumptions: [
        'Descriptive aggregate; no causal interpretation.',
        'No missing-value imputation or record deduplication.',
      ],
      ambiguity: [],
      success_criteria: [
        'Independent aggregate reconciliation',
        'Charts and claims reference computed cells',
        'Immutable source version preserved',
      ],
      relationships: rightDataset
        ? [
            {
              left_dataset_id: datasetId,
              right_dataset_id: rightDataset,
              left_key: leftKey,
              right_key: rightKey,
              order_amount: orderAmount,
              refund_amount: refundAmount,
              purpose: relationshipPurpose,
              cardinality: 'one_to_many',
              missing_refund_policy: 'no_event_means_no_refund',
            },
          ]
        : [],
    };
  }
  async function download() {
    if (!run) return;
    const url = URL.createObjectURL(await api.report(run.run_id));
    const link = document.createElement('a');
    link.href = url;
    link.download = `verified-analysis-${run.run_id}.json`;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  const checks = run?.outcome?.validations || run?.attempts.flatMap((a) => a.validations) || [];
  const selectedBundle = lists.bundles.find((b) => b.id === bundleId);
  const activeDefinition = definitions.find((d) => d.reference === definitionRef);
  const running = !!run && !terminal.has(run.state);
  const moreButton = (name: ListName) =>
    offsets[name] !== null && (
      <button disabled={busy} onClick={() => void action(() => more(name))}>
        More {name}
      </button>
    );

  return (
    <div className="page-container vl-page">
      <header className="page-header editorial-heading">
        <div>
          <p className="eyebrow">INTELLIGENCE / VERIFIED LEARNING</p>
          <h1 className="page-title">
            <ShieldCheck size={30} aria-hidden="true" /> Evidence before memory.
          </h1>
          <p className="page-subtitle">
            Inspect checks, review scoped corrections, and measure their effect before rollout.
          </p>
        </div>
        <button
          disabled={!workspace || busy || loading}
          onClick={() => void action(() => refresh(workspace))}
        >
          <RefreshCw size={16} /> Refresh
        </button>
      </header>
      <div className="vl-toolbar">
        <label>
          Workspace
          <select
            aria-label="Workspace"
            value={workspace}
            onChange={(e) => chooseWorkspace(e.target.value)}
            disabled={busy}
          >
            <option value="">Select an authorized workspace</option>
            {workspaces.map((w) => (
              <option key={w.id} value={w.id}>
                {w.workspace_name}
              </option>
            ))}
          </select>
        </label>
        <span className="vl-status">
          Mode: {controls?.mode || 'disabled'} · Version:{' '}
          {controls?.active_bundle_id || controls?.engine_version || 'validated-baseline-v1'}
        </span>
        <span className="vl-muted">Numeric confidence unavailable</span>
      </div>
      {error && (
        <div role="alert" className="vl-error">
          <span>{error}</span>
          <button
            onClick={() => void action(() => refresh(workspace))}
            disabled={busy || !workspace}
          >
            Retry connection
          </button>
        </div>
      )}
      {notice && (
        <p role="status" className="vl-notice">
          {notice}
        </p>
      )}
      {loading && <p role="status">Loading authorized evidence…</p>}
      {!loading && !workspaces.length && (
        <div className="vl-panel">
          <h2>No authorized workspace</h2>
          <p>
            An active tenant and workspace membership are required. Contact your workspace owner.
          </p>
        </div>
      )}
      {workspace && (
        <>
          <nav className="vl-tabs" aria-label="Verified learning views">
            {['analysis', 'lessons', 'evaluation', 'adaptive', 'controls'].map((name) => (
              <button
                key={name}
                aria-pressed={tab === name}
                onClick={() => {
                  setTab(name);
                  setParams({ ...Object.fromEntries(params), view: name });
                }}
              >
                {name[0].toUpperCase() + name.slice(1)}
              </button>
            ))}
          </nav>
          {tab === 'analysis' && (
            <div className="vl-grid">
              <section className="vl-panel">
                <h2>Start a verified analysis</h2>
                <p>
                  Choose the meaning before calculation. Amounts, dates and source records are
                  preserved.
                </p>
                <form
                  onChangeCapture={() => setConfirmedTask(null)}
                  onSubmit={(e) => {
                    e.preventDefault();
                    void action(async () => {
                      const r = await api.start(task());
                      chooseRun(r.id);
                      await refresh(workspace);
                    });
                  }}
                >
                  <label>
                    Dataset
                    <select
                      aria-label="Dataset"
                      required
                      value={datasetId}
                      onChange={(e) => setDatasetId(e.target.value)}
                    >
                      <option value="">Select an owned, workspace-bound dataset</option>
                      {datasets.map((d) => (
                        <option key={d.dataset_id} value={d.dataset_id}>
                          {d.name}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    Dataset version
                    <input
                      type="number"
                      min="1"
                      required
                      value={version}
                      onChange={(e) => setVersion(Number(e.target.value))}
                    />
                  </label>
                  <label>
                    Objective
                    <input
                      required
                      maxLength={2000}
                      value={objective}
                      onChange={(e) => setObjective(e.target.value)}
                      placeholder="Total signed amount by region"
                    />
                  </label>
                  <label>
                    Business definition
                    <select
                      aria-label="Business definition"
                      value={definitionRef}
                      onChange={(e) => selectDefinition(e.target.value)}
                    >
                      <option value="">Explicit source measure</option>
                      {definitions
                        .filter((d) => d.active)
                        .map((d) => (
                          <option key={d.id} value={d.reference}>
                            {d.reference}
                          </option>
                        ))}
                    </select>
                  </label>
                  {activeDefinition && (
                    <p className="vl-muted">
                      Owner: {activeDefinition.content.owner}. Source:{' '}
                      {activeDefinition.content.source}. Filters:{' '}
                      {JSON.stringify(activeDefinition.content.filters)}
                    </p>
                  )}
                  <div className="vl-fields">
                    <label>
                      Metric column
                      <input
                        required
                        value={column}
                        onChange={(e) => setColumn(e.target.value)}
                        placeholder="amount"
                      />
                    </label>
                    <label>
                      Aggregation
                      <select
                        aria-label="Aggregation"
                        value={aggregation}
                        onChange={(e) => setAggregation(e.target.value as Metric['aggregation'])}
                      >
                        {['sum', 'mean', 'min', 'max', 'count'].map((v) => (
                          <option key={v}>{v}</option>
                        ))}
                      </select>
                    </label>
                    <label>
                      Group by (optional)
                      <input
                        value={dimension}
                        onChange={(e) => setDimension(e.target.value)}
                        placeholder="region"
                      />
                    </label>
                    <label>
                      Missing metric values
                      <select
                        aria-label="Missing metric values"
                        value={missing}
                        onChange={(e) => setMissing(e.target.value as Metric['missing'])}
                      >
                        <option value="reject">Ask for clarification</option>
                        <option value="exclude">Explicitly exclude missing values</option>
                      </select>
                    </label>
                    <label>
                      Units
                      <input required value={units} onChange={(e) => setUnits(e.target.value)} />
                    </label>
                    <label>
                      Currency (optional)
                      <input value={currency} onChange={(e) => setCurrency(e.target.value)} />
                    </label>
                  </div>
                  <details>
                    <summary>Order/refund relationship (optional)</summary>
                    <p className="vl-muted">
                      Select a separately authorized refund input. Net revenue reconciles refunds at
                      order grain before joining; event counts preserve refund rows. Amounts and
                      currency are never guessed.
                    </p>
                    <div className="vl-fields">
                      <label>
                        Refund dataset
                        <select
                          aria-label="Refund dataset"
                          value={rightDataset}
                          onChange={(e) => setRightDataset(e.target.value)}
                        >
                          <option value="">Single-input analysis</option>
                          {datasets
                            .filter((d) => d.dataset_id !== datasetId)
                            .map((d) => (
                              <option key={d.dataset_id} value={d.dataset_id}>
                                {d.name || d.filename}
                              </option>
                            ))}
                        </select>
                      </label>
                      <label>
                        Refund dataset version
                        <input
                          type="number"
                          min={1}
                          value={rightVersion}
                          onChange={(e) => setRightVersion(Number(e.target.value))}
                        />
                      </label>
                      <label>
                        Relationship purpose
                        <select
                          aria-label="Relationship purpose"
                          value={relationshipPurpose}
                          onChange={(e) => {
                            const purpose = e.target.value as typeof relationshipPurpose;
                            setRelationshipPurpose(purpose);
                            setDimension('');
                            setDefinitionRef('');
                            if (purpose === 'refund_event_count') {
                              setColumn('__records__');
                              setAggregation('count');
                              setUnits('events');
                              setCurrency('');
                              setObjective('Count refund events');
                            } else {
                              setColumn('net_amount');
                              setAggregation('sum');
                              setObjective('Net revenue');
                              setUnits('source currency (confirm)');
                              setCurrency('');
                            }
                          }}
                        >
                          <option value="order_net_revenue">Net revenue at order grain</option>
                          <option value="refund_event_count">Count individual refund events</option>
                        </select>
                      </label>
                      <label>
                        Order key
                        <input value={leftKey} onChange={(e) => setLeftKey(e.target.value)} />
                      </label>
                      <label>
                        Refund order key
                        <input value={rightKey} onChange={(e) => setRightKey(e.target.value)} />
                      </label>
                      <label>
                        Order amount column
                        <input
                          value={orderAmount}
                          onChange={(e) => setOrderAmount(e.target.value)}
                        />
                      </label>
                      <label>
                        Refund amount column
                        <input
                          value={refundAmount}
                          onChange={(e) => setRefundAmount(e.target.value)}
                        />
                      </label>
                    </div>
                    {rightDataset && (
                      <p className="vl-muted">
                        Declared policy: no refund event means no refund. Existing events require
                        complete nonnegative refund amounts. Net revenue requires an authorized
                        definition for the derived metric, such as net_amount.
                      </p>
                    )}
                  </details>
                  <details>
                    <summary>Filters and date range</summary>
                    <div className="vl-fields">
                      <label>
                        Exclude by column
                        <input
                          value={filterColumn}
                          onChange={(e) => setFilterColumn(e.target.value)}
                          placeholder="status"
                        />
                      </label>
                      <label>
                        Excluded values, comma separated
                        <input
                          value={excludedValues}
                          onChange={(e) => setExcludedValues(e.target.value)}
                          placeholder="cancelled"
                        />
                      </label>
                      <label>
                        Date column
                        <input value={dateColumn} onChange={(e) => setDateColumn(e.target.value)} />
                      </label>
                      <label>
                        Source date format
                        <input value={dateFormat} onChange={(e) => setDateFormat(e.target.value)} />
                      </label>
                      <label>
                        UTC start (inclusive)
                        <input
                          type="datetime-local"
                          required={!!dateColumn}
                          value={dateStart}
                          onChange={(e) => setDateStart(e.target.value)}
                        />
                      </label>
                      <label>
                        UTC end (exclusive)
                        <input
                          type="datetime-local"
                          required={!!dateColumn}
                          value={dateEnd}
                          onChange={(e) => setDateEnd(e.target.value)}
                        />
                      </label>
                      <label>
                        Source timezone
                        <input value={timezone} onChange={(e) => setTimezone(e.target.value)} />
                      </label>
                    </div>
                  </details>
                  <button className="btn--primary" disabled={busy || loading || running}>
                    Run with verification
                  </button>
                </form>
                <h3>Recent runs</h3>
                {!lists.runs.length && <p>No verified runs yet.</p>}
                <ul className="vl-list">
                  {lists.runs.map((r) => (
                    <li key={r.id}>
                      <button className="vl-link" onClick={() => chooseRun(r.id)}>
                        {r.task?.objective || r.id}
                      </button>
                      <span>{r.state}</span>
                    </li>
                  ))}
                </ul>
                {moreButton('runs')}
              </section>
              <section className="vl-panel" aria-busy={running} aria-label="Analysis evidence">
                {!run && (
                  <>
                    <h2>No run selected</h2>
                    <p>
                      Start an analysis or reopen a recent run. Progress and checks remain available
                      after refresh.
                    </p>
                  </>
                )}
                {run && (
                  <>
                    <div className="vl-row">
                      <h2>
                        {run.state === 'succeeded'
                          ? 'Verified within checked scope'
                          : run.state.replaceAll('_', ' ')}
                      </h2>
                      {running && (
                        <button
                          disabled={busy}
                          onClick={() =>
                            void action(async () => {
                              await api.cancel(run.run_id);
                              setRun(await api.run(run.run_id));
                            })
                          }
                        >
                          Cancel run
                        </button>
                      )}
                      {run.state === 'succeeded' && (
                        <button disabled={busy} onClick={() => void action(download)}>
                          <Download size={15} /> Download verified report
                        </button>
                      )}
                    </div>
                    <p className="vl-muted">
                      {run.task?.objective} · Mode {run.mode} · Repairs {run.repairs}/
                      {run.budget.max_repairs}
                    </p>
                    <ol className="vl-progress">
                      {stages.map((name, i) => {
                        const a = run.attempts
                          .filter((x) => x.stage_id.endsWith(`:${i + 1}`))
                          .at(-1);
                        return (
                          <li key={name}>
                            <span>{name}</span>
                            <strong>{a?.status.replaceAll('_', ' ') || 'queued'}</strong>
                          </li>
                        );
                      })}
                    </ol>
                    {run.error_code && (
                      <p role="status" className="vl-notice">
                        {run.error_code}. Resolve the task meaning or inputs, then create a new run.
                        Prior evidence remains intact.
                      </p>
                    )}
                    <h3>Interpretation and assumptions</h3>
                    <ul>
                      {run.task?.assumptions.map((a) => (
                        <li key={a}>{a}</li>
                      ))}
                      {run.task?.ambiguity.map((a) => (
                        <li key={a}>{a}</li>
                      ))}
                    </ul>
                    {run.outcome?.profile && (
                      <>
                        <h3>Data quality findings</h3>
                        <p>
                          {run.outcome.profile.row_count} source records.{' '}
                          {run.outcome.profile.duplicate_looking_rows} duplicate-looking records
                          retained.
                        </p>
                        <div className="vl-scroll">
                          <table>
                            <thead>
                              <tr>
                                <th>Column</th>
                                <th>Type</th>
                                <th>Missing</th>
                                <th>Unique</th>
                              </tr>
                            </thead>
                            <tbody>
                              {Object.entries(run.outcome.profile.columns).map(([name, p]) => (
                                <tr key={name}>
                                  <td>{name}</td>
                                  <td>{p.dtype}</td>
                                  <td>{p.missing}</td>
                                  <td>{p.unique}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </>
                    )}
                    <h3>Execution checks</h3>
                    {!checks.length && <p>No completed checks yet.</p>}
                    <ul className="vl-checks">
                      {checks.map((c, i) => (
                        <li key={`${c.validator}-${i}`}>
                          <strong>{c.outcome}</strong>
                          <div>
                            {c.invariant}
                            {c.limitations.map((l) => (
                              <p className="vl-muted" key={l}>
                                {l}
                              </p>
                            ))}
                          </div>
                        </li>
                      ))}
                    </ul>
                    {run.outcome?.answer && (
                      <>
                        <h3>Answer evidence</h3>
                        <div className="vl-scroll">
                          <table>
                            <thead>
                              <tr>
                                {Object.keys(run.outcome.answer.rows[0] || {}).map((k) => (
                                  <th key={k}>{k}</th>
                                ))}
                              </tr>
                            </thead>
                            <tbody>
                              {run.outcome.answer.rows.map((row, i) => (
                                <tr key={i}>
                                  {Object.values(row).map((v, j) => (
                                    <td key={j}>{v ?? 'Missing'}</td>
                                  ))}
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                        <div className="vl-chart" aria-label="Computed result chart">
                          {run.outcome.answer.chart.slice(0, 30).map((p, i) => (
                            <div key={i}>
                              <span>{p.label}</span>
                              <meter
                                min={Math.min(
                                  0,
                                  ...run.outcome!.answer!.chart.map((x) => Number(x.value) || 0),
                                )}
                                max={Math.max(
                                  1,
                                  ...run.outcome!.answer!.chart.map((x) => Number(x.value) || 0),
                                )}
                                value={Number(p.value) || 0}
                                aria-label={`${p.label}: ${p.value}`}
                              />
                              <strong>{p.value ?? 'Missing'}</strong>
                            </div>
                          ))}
                        </div>
                        <ul>
                          {run.outcome.answer.claims.slice(0, 30).map((c) => (
                            <li key={c.evidence_ref}>
                              {c.text} <code>{c.evidence_ref}</code>
                            </li>
                          ))}
                        </ul>
                        <p className="vl-hash">Result version: {run.outcome.result_hash}</p>
                      </>
                    )}
                    {run.outcome?.limitations.map((l) => (
                      <p className="vl-muted" key={l}>
                        {l}
                      </p>
                    ))}
                    <p>Numeric confidence unavailable.</p>
                    <details>
                      <summary>Give structured feedback</summary>
                      <form
                        onSubmit={(e) => {
                          e.preventDefault();
                          void action(async () => {
                            await api.feedback(
                              run.run_id,
                              feedbackCategory,
                              feedbackText,
                              correctionColumn,
                            );
                            setNotice('Feedback saved. It is not a verified numeric label.');
                            setFeedbackText('');
                          });
                        }}
                      >
                        <label>
                          Issue type
                          <select
                            aria-label="Issue type"
                            value={feedbackCategory}
                            onChange={(e) =>
                              setFeedbackCategory(e.target.value as FeedbackCategory)
                            }
                          >
                            <option value="interpretation">Wrong interpretation</option>
                            <option value="calculation">Calculation</option>
                            <option value="business_definition">Business definition</option>
                            <option value="presentation_preference">Presentation preference</option>
                            <option value="other">Other</option>
                          </select>
                        </label>
                        <label>
                          Correction or supporting explanation
                          <textarea
                            maxLength={2000}
                            value={feedbackText}
                            onChange={(e) => setFeedbackText(e.target.value)}
                          />
                        </label>
                        <label>
                          Canonical decimal correction column (optional)
                          <input
                            value={correctionColumn}
                            onChange={(e) => setCorrectionColumn(e.target.value)}
                          />
                        </label>
                        <p className="vl-muted">
                          Do not include secrets or raw customer records. Feedback cannot override
                          permissions or validators.
                        </p>
                        <button disabled={busy || controls?.mode === 'disabled'}>
                          Save feedback
                        </button>
                        {controls?.mode === 'disabled' && (
                          <p>Collection is disabled by workspace policy.</p>
                        )}
                      </form>
                    </details>
                  </>
                )}
              </section>
            </div>
          )}

          {tab === 'lessons' && (
            <section className="vl-panel">
              <h2>Scoped lesson review</h2>
              <p>
                Verification establishes correction checks. Application also requires compatible
                scope and an evaluated release.
              </p>
              {!lists.lessons.length && (
                <p>
                  No candidates recorded. Collection must be enabled and a supported correction
                  observed.
                </p>
              )}
              <div className="vl-lesson-grid">
                <ul className="vl-list">
                  {lists.lessons.map((l) => (
                    <li key={l.id}>
                      <button
                        className="vl-link"
                        onClick={() =>
                          void action(async () => {
                            setSelectedLesson(await api.lesson(workspace, l.id));
                          })
                        }
                      >
                        {l.content.correction.column}: {l.content.correction.type}
                      </button>
                      <span>{l.state}</span>
                    </li>
                  ))}
                </ul>
                {selectedLesson && (
                  <article>
                    <h3>
                      {selectedLesson.state} · Revision {selectedLesson.revision}
                    </h3>
                    <h4>Before → correction</h4>
                    <p>
                      Canonical decimal text → lossless decimal representation in{' '}
                      <strong>{selectedLesson.content.correction.column}</strong>.
                    </p>
                    <h4>Triggering conditions</h4>
                    <ul>
                      {selectedLesson.content.conditions.map((c) => (
                        <li key={c}>{c}</li>
                      ))}
                    </ul>
                    <h4>Exceptions</h4>
                    <ul>
                      {selectedLesson.content.exceptions.map((c) => (
                        <li key={c}>{c}</li>
                      ))}
                    </ul>
                    <p>
                      Definitions:{' '}
                      {selectedLesson.content.scope.definition_refs.join(', ') ||
                        'Explicit source measure'}
                      . Expires {new Date(selectedLesson.expires_at).toLocaleString()}.
                    </p>
                    <p className="vl-hash">Schema: {selectedLesson.content.scope.schema_hash}</p>
                    <h4>Sources</h4>
                    <ul>
                      {selectedLesson.content.provenance.map((p) => (
                        <li key={p}>{p}</li>
                      ))}
                    </ul>
                    <h4>Independent evidence</h4>
                    {!selectedLesson.verification_records?.length && (
                      <p>Not independently verified.</p>
                    )}
                    {selectedLesson.verification_records?.map((v) => (
                      <p key={v.id}>
                        {v.passed ? 'Passed' : 'Failed'}: {v.evidence.positive_cases} positive cases
                        and {v.evidence.counterexamples} counterexamples. {v.evidence.scope}
                      </p>
                    ))}
                    <label>
                      Review reason
                      <input
                        value={reason}
                        onChange={(e) => setReason(e.target.value)}
                        maxLength={500}
                      />
                    </label>
                    <div className="vl-actions">
                      {[
                        ['verify', 'candidate'],
                        ['activate', 'verified'],
                        ['reject', 'candidate,verified'],
                        ['revoke', 'candidate,verified,active'],
                      ].map(([name, states]) => (
                        <button
                          key={name}
                          disabled={
                            busy ||
                            !canReview ||
                            !reason.trim() ||
                            !states.split(',').includes(selectedLesson.state)
                          }
                          onClick={() =>
                            void action(async () => {
                              await api.review(workspace, selectedLesson, name, reason);
                              setSelectedLesson(await api.lesson(workspace, selectedLesson.id));
                              await refresh(workspace);
                              setNotice(
                                name === 'verify'
                                  ? 'Verified lesson saved.'
                                  : `Lesson ${name} action saved.`,
                              );
                            })
                          }
                        >
                          {name[0].toUpperCase() + name.slice(1)}
                        </button>
                      ))}
                    </div>
                    {!canReview && <p>Only administrators and owners can review lessons.</p>}
                    <h4>Revision history</h4>
                    <ul>
                      {selectedLesson.revisions?.map((r) => (
                        <li key={r.number}>
                          {r.number}: {r.state} — {r.reason}
                        </li>
                      ))}
                    </ul>
                  </article>
                )}
              </div>
              {moreButton('lessons')}
            </section>
          )}

          {tab === 'evaluation' && (
            <section className="vl-panel">
              <h2>Baseline versus frozen candidate</h2>
              {!canReview ? (
                <p>Evaluation labels and release evidence require administrator or owner access.</p>
              ) : (
                <>
                  <p>
                    Both arms use the same code, validators and repairs. Gold labels stay outside
                    runtime context. Synthetic pilots cannot establish production gains.
                  </p>
                  <details>
                    <summary>Register an independently labeled case</summary>
                    <p>
                      Uses the task configured in Analysis. Select a held-out dataset and
                      independently enter its expected result.
                    </p>
                    <form
                      onSubmit={(e) => {
                        e.preventDefault();
                        void action(async () => {
                          const configured = task();
                          const rows =
                            expectedStatus === 'verified'
                              ? expectedRows.map((r) => ({
                                  ...(configured.dimensions[0]
                                    ? { [configured.dimensions[0]]: r.group }
                                    : {}),
                                  value:
                                    r.value.trim() === ''
                                      ? null
                                      : Number.isInteger(Number(r.value))
                                        ? Number(r.value)
                                        : r.value,
                                }))
                              : [];
                          await api.addCase(workspace, {
                            task: configured,
                            scenario_group: scenario,
                            split: caseSplit,
                            dataset_version: configured.datasets[0],
                            label_source: labelSource,
                            reference: labelReference,
                            expected_status: expectedStatus,
                            expected_rows: rows,
                          });
                          await refresh(workspace);
                          setNotice('Immutable evaluation case registered.');
                        });
                      }}
                    >
                      <div className="vl-fields">
                        <label>
                          Scenario group
                          <input
                            required
                            value={scenario}
                            onChange={(e) => setScenario(e.target.value)}
                          />
                        </label>
                        <label>
                          Split
                          <select
                            value={caseSplit}
                            onChange={(e) => setCaseSplit(e.target.value as CaseInput['split'])}
                          >
                            <option value="development">Development</option>
                            <option value="calibration">Calibration collection</option>
                            <option value="final">Held-out final</option>
                          </select>
                        </label>
                        <label>
                          Label source
                          <select
                            value={labelSource}
                            onChange={(e) =>
                              setLabelSource(e.target.value as CaseInput['label_source'])
                            }
                          >
                            <option value="synthetic">Synthetic fixture</option>
                            <option value="domain_reviewed">Independently domain reviewed</option>
                          </select>
                        </label>
                        <label>
                          Trusted reference
                          <input
                            required
                            value={labelReference}
                            onChange={(e) => setLabelReference(e.target.value)}
                          />
                        </label>
                        <label>
                          Expected answer status
                          <select
                            value={expectedStatus}
                            onChange={(e) =>
                              setExpectedStatus(e.target.value as CaseInput['expected_status'])
                            }
                          >
                            <option value="verified">Verified result</option>
                            <option value="insufficient_evidence">Should abstain</option>
                          </select>
                        </label>
                      </div>
                      {expectedStatus === 'verified' &&
                        expectedRows.map((r, i) => (
                          <div className="vl-fields" key={i}>
                            <label>
                              Expected group (if grouped)
                              <input
                                value={r.group}
                                onChange={(e) =>
                                  setExpectedRows((v) =>
                                    v.map((x, j) =>
                                      j === i ? { ...x, group: e.target.value } : x,
                                    ),
                                  )
                                }
                              />
                            </label>
                            <label>
                              Expected numeric value
                              <input
                                required
                                value={r.value}
                                onChange={(e) =>
                                  setExpectedRows((v) =>
                                    v.map((x, j) =>
                                      j === i ? { ...x, value: e.target.value } : x,
                                    ),
                                  )
                                }
                              />
                            </label>
                          </div>
                        ))}
                      <div className="vl-actions">
                        <button
                          type="button"
                          onClick={() => setExpectedRows((v) => [...v, { group: '', value: '' }])}
                        >
                          Add expected group
                        </button>
                        <button disabled={busy}>Register case</button>
                      </div>
                    </form>
                  </details>
                  <div className="vl-fields">
                    <label>
                      Candidate bundle
                      <select value={bundleId} onChange={(e) => setBundleId(e.target.value)}>
                        <option value="">Select frozen candidate</option>
                        {lists.bundles.map((b) => (
                          <option key={b.id} value={b.id}>
                            {b.id} · {b.content.lessons.length} lessons
                          </option>
                        ))}
                      </select>
                    </label>
                    <label>
                      Required trusted scenarios
                      <input
                        type="number"
                        min={2}
                        max={10000}
                        value={minCases}
                        onChange={(e) => setMinCases(Number(e.target.value))}
                      />
                    </label>
                  </div>
                  <button
                    disabled={busy}
                    onClick={() =>
                      void action(async () => {
                        const b = await api.freeze(workspace);
                        await refresh(workspace);
                        setBundleId(b.id);
                        setNotice('Candidate frozen. Subsequent lessons are excluded.');
                      })
                    }
                  >
                    Freeze active lesson bundle
                  </button>
                  {moreButton('bundles')}
                  <fieldset>
                    <legend>Held-out final cases</legend>
                    {!lists.cases.filter((c) => c.split === 'final').length && (
                      <p>No final cases registered.</p>
                    )}
                    {lists.cases
                      .filter((c) => c.split === 'final')
                      .map((c) => (
                        <label className="vl-check-label" key={c.id}>
                          <input
                            type="checkbox"
                            checked={caseIds.includes(c.id)}
                            onChange={(e) =>
                              setCaseIds((v) =>
                                e.target.checked ? [...v, c.id] : v.filter((x) => x !== c.id),
                              )
                            }
                          />
                          {c.scenario_group} · {c.label_source}
                        </label>
                      ))}
                  </fieldset>
                  {moreButton('cases')}
                  <p className="vl-muted">
                    Declared gates: zero correctness regression, no harmful application, p95 latency
                    ≤ 1.5× baseline, zero provider cost increase, independent trusted scenarios, and
                    measured benefit. Hard correctness, authorization and leakage gates always
                    apply.
                  </p>
                  <button
                    className="btn--primary"
                    disabled={busy || !selectedBundle || caseIds.length < 2}
                    onClick={() =>
                      void action(async () => {
                        await api.evaluate(
                          workspace,
                          selectedBundle!,
                          lists.cases.filter((c) => caseIds.includes(c.id)),
                          minCases,
                        );
                        await refresh(workspace);
                        setNotice('Paired evaluation queued.');
                      })
                    }
                  >
                    Run paired evaluation
                  </button>
                  {!lists.evaluations.length && <p>No evaluations recorded.</p>}
                  {lists.evaluations.map((e) => (
                    <article className="vl-evaluation" key={e.id}>
                      <h3>
                        Evaluation {e.id.slice(0, 8)} · {e.state}
                      </h3>
                      {e.error_code && <p role="alert">{e.error_code}</p>}
                      {e.result?.metrics && (
                        <>
                          <p>
                            {e.result.sample_size} paired cases in{' '}
                            {e.result.independent_scenario_groups} scenario groups. Correctness
                            delta: {e.result.correctness_delta}. Release{' '}
                            {e.result.release_eligible ? 'eligible' : 'blocked'}.
                          </p>
                          <div className="vl-scroll">
                            <table>
                              <thead>
                                <tr>
                                  <th>Measure</th>
                                  <th>Baseline</th>
                                  <th>Candidate</th>
                                </tr>
                              </thead>
                              <tbody>
                                {(
                                  [
                                    'correct',
                                    'total',
                                    'completed',
                                    'abstained',
                                    'unknown',
                                    'repeated_error_rate',
                                    'p50_latency_ms',
                                    'p95_latency_ms',
                                    'cost_usd',
                                  ] as const
                                ).map((key) => (
                                  <tr key={key}>
                                    <th>{key.replaceAll('_', ' ')}</th>
                                    <td>{e.result!.metrics.baseline[key]}</td>
                                    <td>{e.result!.metrics.candidate[key]}</td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                          <p>
                            {e.result.applications} applications; {e.result.useful_applications}{' '}
                            useful; {e.result.harmful_applications} harmful. Paired scenario
                            bootstrap interval:{' '}
                            {e.result.paired_bootstrap_95_interval?.join(' to ') || 'Unavailable'}.
                          </p>
                          <ul>
                            {Object.entries(e.result.gates).map(([name, passed]) => (
                              <li key={name}>
                                {passed ? 'Pass' : 'Blocked'}: {name.replaceAll('_', ' ')}
                              </li>
                            ))}
                          </ul>
                          {e.result.limitations.map((l) => (
                            <p className="vl-muted" key={l}>
                              {l}
                            </p>
                          ))}
                          <button
                            disabled={busy || !e.result.release_eligible}
                            onClick={() =>
                              void action(async () => {
                                await api.release(workspace, e.id, controls!.generation);
                                await refresh(workspace);
                                setNotice(
                                  'Evaluated candidate released to a stable 10% allocation.',
                                );
                              })
                            }
                          >
                            Release to 10% of runs
                          </button>
                        </>
                      )}
                    </article>
                  ))}
                  {moreButton('evaluations')}
                </>
              )}
            </section>
          )}

          {tab === 'adaptive' && (
            <AdaptiveWorkbench
              key={workspace}
              workspace={workspace}
              runId={runId}
              draftTask={task}
              onUseTask={applyTask}
            />
          )}
          {tab === 'controls' && (
            <section className="vl-panel">
              <h2>Collection and application policy</h2>
              <p>
                Disabled: no optional feedback or lesson collection. Collection: draft candidates
                off the response path. Shadow: retrieve compatible references without applying them.
                Limited application: only after release gates pass.
              </p>
              <p>
                Active version: {controls?.active_bundle_id || 'validated-baseline-v1'}. Generation{' '}
                {controls?.generation ?? 0}. Allocation {controls?.rollout_percent ?? 0}%.
              </p>
              {!canReview && <p>Only administrators and owners can change these controls.</p>}
              <div className="vl-actions">
                {(['disabled', 'collection', 'shadow'] as const).map((mode) => (
                  <button
                    key={mode}
                    disabled={busy || !canReview || !controls || controls.mode === mode}
                    onClick={() =>
                      void action(async () => {
                        await api.setMode(workspace, mode, controls!.generation);
                        await refresh(workspace);
                      })
                    }
                  >
                    {mode}
                  </button>
                ))}
                <button
                  disabled={busy || !canReview || !controls}
                  onClick={() =>
                    void action(async () => {
                      await api.rollback(workspace, controls!.generation);
                      await refresh(workspace);
                      setNotice(
                        'Application stopped. Baseline active; previous bundle retained in shadow for review.',
                      );
                    })
                  }
                >
                  Rollback to validated baseline
                </button>
              </div>
              {canReview && (
                <>
                  <details>
                    <summary>Confirm a versioned business definition</summary>
                    <p>
                      Uses the metric, units, currency and explicit exclusions configured in
                      Analysis. Confirm an authorized domain owner and trusted source.
                    </p>
                    <form
                      onSubmit={(e) => {
                        e.preventDefault();
                        void action(async () => {
                          const t = task();
                          await api.createDefinition(workspace, {
                            key: definitionKey,
                            version: definitionVersion,
                            owner: definitionOwner,
                            source: definitionSource,
                            metric: { ...t.metrics[0], definition_ref: null },
                            filters: t.filters,
                            units: t.units,
                            currency: t.currency,
                            examples: [{ description: definitionExample }],
                          });
                          await refresh(workspace);
                          setNotice('Authorized business definition version saved.');
                        });
                      }}
                    >
                      <div className="vl-fields">
                        <label>
                          Definition key
                          <input
                            required
                            pattern="[a-z][a-z0-9_]*"
                            value={definitionKey}
                            onChange={(e) => setDefinitionKey(e.target.value)}
                            placeholder="net_revenue"
                          />
                        </label>
                        <label>
                          Version
                          <input
                            type="number"
                            min={1}
                            required
                            value={definitionVersion}
                            onChange={(e) => setDefinitionVersion(Number(e.target.value))}
                          />
                        </label>
                        <label>
                          Domain owner
                          <input
                            required
                            value={definitionOwner}
                            onChange={(e) => setDefinitionOwner(e.target.value)}
                          />
                        </label>
                        <label>
                          Trusted source
                          <input
                            required
                            value={definitionSource}
                            onChange={(e) => setDefinitionSource(e.target.value)}
                          />
                        </label>
                      </div>
                      <label>
                        Expected example and result
                        <textarea
                          required
                          value={definitionExample}
                          onChange={(e) => setDefinitionExample(e.target.value)}
                          placeholder="Paid 100, cancelled 1000, refund -20 → net revenue 80 USD"
                        />
                      </label>
                      <button disabled={busy}>Confirm definition</button>
                    </form>
                  </details>
                  <h3>Definition versions</h3>
                  <ul className="vl-list">
                    {definitions.map((d) => (
                      <li key={d.id}>
                        <span>
                          {d.reference} · {d.active ? 'active' : 'invalidated'}
                        </span>
                        <button
                          disabled={busy || !d.active}
                          onClick={() =>
                            void action(async () => {
                              await api.invalidateDefinition(workspace, d.id);
                              await refresh(workspace);
                              setNotice('Definition invalidated; dependent lessons revoked.');
                            })
                          }
                        >
                          Invalidate
                        </button>
                      </li>
                    ))}
                  </ul>
                  <h3>Recovery and monitoring</h3>
                  {!monitor?.failed_jobs.length && <p>No failed learning jobs recorded.</p>}
                  <ul>
                    {monitor?.failed_jobs.map((j) => (
                      <li key={j.id}>
                        {j.kind}: {j.error_code} · {j.id}
                      </li>
                    ))}
                  </ul>
                  <h3>Recent policy events</h3>
                  <ul>
                    {monitor?.items.map((m) => (
                      <li key={m.id}>
                        {m.action.replaceAll('_', ' ')} · {new Date(m.at).toLocaleString()}
                      </li>
                    ))}
                  </ul>
                </>
              )}
              <p className="vl-muted">
                Main LLM and embedding weights stay frozen. Selector training is reported separately
                in Adaptive. Calibration and production accuracy gains are not claimed.
              </p>
            </section>
          )}
        </>
      )}
    </div>
  );
}
