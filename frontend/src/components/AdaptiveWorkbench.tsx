import { useCallback, useEffect, useState } from 'react';
import { ApiError } from '../api/client';
import { learningService } from '../services/learningService';
import type { TaskSpec } from '../services/learningService';
import { adaptiveService as api } from '../services/adaptiveService';
import type {
  AdaptiveCase,
  AdaptiveContext,
  AdaptiveJob,
  CaseInput,
  Decision,
  Interpretation,
  SelectorControls,
  SelectorModel,
  Skill,
} from '../services/adaptiveService';

interface Props {
  workspace: string;
  runId: string;
  draftTask: () => TaskSpec;
  onUseTask: (task: TaskSpec) => void;
}
type Tab = 'understanding' | 'skills' | 'decisions' | 'training' | 'controls';
const empty = {
  skills: [] as Skill[],
  decisions: [] as Decision[],
  cases: [] as AdaptiveCase[],
  jobs: [] as AdaptiveJob[],
  models: [] as SelectorModel[],
};
type ListName = keyof typeof empty;

export default function AdaptiveWorkbench({ workspace, runId, draftTask, onUseTask }: Props) {
  const [tab, setTab] = useState<Tab>('understanding');
  const [control, setControl] = useState<SelectorControls | null>(null);
  const [lists, setLists] = useState(empty);
  const [offsets, setOffsets] = useState<Record<ListName, number | null>>({
    skills: null,
    decisions: null,
    cases: null,
    jobs: null,
    models: null,
  });
  const [selectedSkill, setSelectedSkill] = useState<Skill | null>(null);
  const [selectedModel, setSelectedModel] = useState('');
  const [selectedCases, setSelectedCases] = useState<string[]>([]);
  const [runContext, setRunContext] = useState<AdaptiveContext | null>(null);
  const [proposal, setProposal] = useState<Interpretation | null>(null);
  const [useProvider, setUseProvider] = useState(false);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [reason, setReason] = useState('');
  const [scenario, setScenario] = useState('');
  const [split, setSplit] = useState<AdaptiveCase['split']>('train');
  const [source, setSource] = useState<AdaptiveCase['source_kind']>('synthetic');
  const [reference, setReference] = useState('');
  const [expectedStatus, setExpectedStatus] = useState<CaseInput['expected_status']>('verified');
  const [gold, setGold] = useState([{ group: '', value: '' }]);
  const [minimumExamples, setMinimumExamples] = useState(40);
  const [minimumGroups, setMinimumGroups] = useState(6);
  const [minimumClass, setMinimumClass] = useState(8);
  const [epochs, setEpochs] = useState(120);
  const canReview = !!control?.can_review;

  function failure(e: unknown) {
    const prefix =
      e instanceof ApiError
        ? e.status === 0
          ? 'Disconnected. '
          : [401, 403, 404].includes(e.status)
            ? 'Access unavailable. '
            : ''
        : '';
    setError(prefix + (e instanceof Error ? e.message : 'Adaptive request failed.'));
  }
  const refresh = useCallback(async () => {
    const [cfg, skills, decisions] = await Promise.all([
      api.controls(workspace),
      api.skills(workspace),
      api.decisions(workspace),
    ]);
    setControl(cfg);
    setLists((v) => ({ ...v, skills: skills.items, decisions: decisions.items }));
    setOffsets((v) => ({ ...v, skills: skills.next_offset, decisions: decisions.next_offset }));
    if (cfg.can_review) {
      const [cases, jobs, models] = await Promise.all([
        api.cases(workspace),
        api.jobs(workspace),
        api.models(workspace),
      ]);
      setLists((v) => ({ ...v, cases: cases.items, jobs: jobs.items, models: models.items }));
      setOffsets((v) => ({
        ...v,
        cases: cases.next_offset,
        jobs: jobs.next_offset,
        models: models.next_offset,
      }));
    }
  }, [workspace]);
  useEffect(() => {
    let live = true;
    Promise.resolve()
      .then(refresh)
      .catch((e) => {
        if (live) failure(e);
      })
      .finally(() => {
        if (live) setLoading(false);
      });
    return () => {
      live = false;
    };
  }, [refresh]);
  useEffect(() => {
    if (!runId) return;
    let live = true;
    api
      .context(runId)
      .then((data) => {
        if (live) setRunContext(data);
      })
      .catch((e) => {
        if (live) failure(e);
      });
    return () => {
      live = false;
    };
  }, [runId]);
  useEffect(() => {
    if (!lists.jobs.some((job) => ['queued', 'running'].includes(job.state))) return;
    const timer = setTimeout(() => {
      refresh().catch(failure);
    }, 2000);
    return () => clearTimeout(timer);
  }, [lists.jobs, refresh]);

  async function act(work: () => Promise<void>) {
    setBusy(true);
    setError('');
    setNotice('');
    try {
      await work();
    } catch (e) {
      failure(e);
    } finally {
      setBusy(false);
    }
  }
  async function more(name: ListName) {
    const offset = offsets[name];
    if (offset === null) return;
    const page = await api[name](workspace, offset);
    setLists((v) => ({ ...v, [name]: [...v[name], ...page.items] }));
    setOffsets((v) => ({ ...v, [name]: page.next_offset }));
  }
  const moreButton = (name: ListName) =>
    offsets[name] !== null && (
      <button disabled={busy} onClick={() => void act(() => more(name))}>
        More {name}
      </button>
    );
  async function register() {
    let task: TaskSpec;
    let rows: CaseInput['expected_rows'];
    if (source === 'verified_run') {
      if (!runId) throw new Error('Select a completed run in Analysis first.');
      const run = await learningService.run(runId);
      if (run.state !== 'succeeded' || !run.task || !run.outcome?.answer)
        throw new Error('A fully verified source run is required.');
      task = run.task;
      rows = run.outcome.answer.rows;
    } else {
      task = draftTask();
      if (task.dimensions.length > 1)
        throw new Error('Register multi-dimension gold rows through the typed case API.');
      rows =
        expectedStatus === 'verified'
          ? gold.map((row) => {
              if (row.value.trim() && !Number.isFinite(Number(row.value)))
                throw new Error('Expected values must be finite numbers.');
              return {
                ...(task.dimensions[0] ? { [task.dimensions[0]]: row.group } : {}),
                value: !row.value.trim()
                  ? null
                  : Number.isSafeInteger(Number(row.value))
                    ? Number(row.value)
                    : row.value,
              };
            })
          : [];
    }
    await api.registerCase(workspace, {
      task,
      scenario_group: scenario,
      split,
      source_kind: source,
      source_run_id: source === 'verified_run' ? runId : null,
      reference: reference || `verified run ${runId}`,
      expected_status: source === 'verified_run' ? 'verified' : expectedStatus,
      expected_rows: rows,
    });
    await refresh();
    setNotice(
      'Versioned source case registered. Previously observed runs cannot become final cases.',
    );
  }
  async function train() {
    const cases = lists.cases.filter((c) => selectedCases.includes(c.id));
    await api.train(workspace, {
      train_case_ids: cases.filter((c) => c.split === 'train').map((c) => c.id),
      development_case_ids: cases.filter((c) => c.split === 'development').map((c) => c.id),
      final_case_ids: cases.filter((c) => c.split === 'final').map((c) => c.id),
      min_examples: minimumExamples,
      min_groups: minimumGroups,
      min_per_class: minimumClass,
      max_epochs: epochs,
      idempotency_key: api.key(),
    });
    await refresh();
    setNotice(
      'Training queued. Evidence thresholds are checked before fitting; both candidate scorers face the same frozen final cases.',
    );
  }
  async function download(id: string) {
    const url = URL.createObjectURL(await api.download(workspace, id));
    const link = document.createElement('a');
    link.href = url;
    link.download = `repair-selector-${id}.json`;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  const chosen = lists.models.find((m) => m.id === selectedModel);
  const diagnosis = proposal?.diagnosis || runContext?.context?.diagnosis;
  const problem = proposal?.problem_context || runContext?.context?.problem;

  return (
    <section className="vl-panel" aria-label="Adaptive skills workbench" aria-busy={loading}>
      <div className="vl-row">
        <div>
          <h2>Tested skills. Measured selection.</h2>
          <p className="vl-muted">
            Main LLM and embedding weights stay frozen. Selector training changes numerical weights
            only.
          </p>
        </div>
        <button disabled={busy || loading} onClick={() => void act(refresh)}>
          Refresh adaptive evidence
        </button>
      </div>
      <div className="vl-toolbar">
        <span>
          Selector mode: <strong>{control?.mode || 'disabled'}</strong>
        </span>
        <span>
          Executing: <strong>{control?.effective_selector || 'rules-memory-v1'}</strong>
        </span>
        <span>Numeric confidence unavailable</span>
      </div>
      {loading && <p role="status">Loading scoped skills and decisions…</p>}
      {error && (
        <p role="alert" className="vl-error">
          {error}
        </p>
      )}
      {notice && (
        <p role="status" className="vl-notice">
          {notice}
        </p>
      )}
      <nav className="vl-tabs" aria-label="Adaptive workbench views">
        {(['understanding', 'skills', 'decisions', 'training', 'controls'] as Tab[]).map((name) => (
          <button key={name} aria-pressed={tab === name} onClick={() => setTab(name)}>
            {name[0].toUpperCase() + name.slice(1)}
          </button>
        ))}
      </nav>
      {tab === 'understanding' && (
        <>
          <h3>Resolve the task before execution</h3>
          <p className="vl-muted">
            Uses the task configured in Analysis, authorized schema profiles and business
            definitions. Provider proposals require your confirmation and cannot execute tools.
          </p>
          <label className="vl-check-label">
            <input
              type="checkbox"
              checked={useProvider}
              onChange={(e) => setUseProvider(e.target.checked)}
            />
            Ask the configured frozen LLM for a bounded interpretation
          </label>
          <button
            disabled={busy || !control?.can_write}
            onClick={() =>
              void act(async () => {
                setProposal(await api.interpret(workspace, draftTask(), useProvider));
              })
            }
          >
            Inspect task context
          </button>
          {!problem && (
            <p>No context selected. Configure a task in Analysis or reopen a recorded run.</p>
          )}
          {problem && (
            <>
              <h3>{problem.task.objective}</h3>
              <p>
                Source: {problem.interpretation_source}. Grain: {problem.grain}. Units:{' '}
                {problem.task.units}. Timezone: {problem.task.timezone}.
              </p>
              <p>
                Definitions: {problem.task.definition_refs.join(', ') || 'Explicit source measure'}.
              </p>
              <h4>Acceptance checks</h4>
              <ul>
                {problem.acceptance_checks.map((c) => (
                  <li key={c}>{c}</li>
                ))}
              </ul>
              {!!problem.task.ambiguity.length && (
                <>
                  <h4>Clarification required</h4>
                  <ul>
                    {problem.task.ambiguity.map((a) => (
                      <li key={a}>{a}</li>
                    ))}
                  </ul>
                </>
              )}
              {problem.limitations.map((item) => (
                <p className="vl-muted" key={item}>
                  {item}
                </p>
              ))}
              {proposal && (
                <>
                  <p>
                    Interpretation status: {proposal.interpretation_status.replaceAll('_', ' ')}.
                    Logical provider calls: {proposal.usage.logical_calls}.
                  </p>
                  <button
                    disabled={busy || !!problem.task.ambiguity.length}
                    onClick={() => {
                      onUseTask(problem.task);
                      setNotice(
                        'Task proposal applied to the visible Analysis form. Start execution explicitly after reviewing it.',
                      );
                    }}
                  >
                    Use this reviewed task proposal
                  </button>
                </>
              )}
            </>
          )}
          {diagnosis && (
            <article>
              <h3>Evidence-based diagnosis</h3>
              <p>
                <strong>{diagnosis.category.replaceAll('_', ' ')}</strong>:{' '}
                {diagnosis.observed_failure}
              </p>
              <p>
                {diagnosis.established
                  ? 'Observation supported by displayed checks.'
                  : 'Unestablished hypothesis; more checks required.'}
              </p>
              <details>
                <summary>Observed evidence</summary>
                <pre className="vl-hash">{JSON.stringify(diagnosis.evidence, null, 2)}</pre>
              </details>
              <h4>Proposed causes</h4>
              {!diagnosis.proposed_causes.length && (
                <p>No cause asserted beyond the observation.</p>
              )}
              <ul>
                {diagnosis.proposed_causes.map((c) => (
                  <li key={c}>{c}</li>
                ))}
              </ul>
              <h4>Distinguishing checks</h4>
              <ul>
                {diagnosis.distinguishing_checks.map((c) => (
                  <li key={c}>{c}</li>
                ))}
              </ul>
            </article>
          )}
        </>
      )}
      {tab === 'skills' && (
        <>
          <div className="vl-row">
            <h3>Executable skill inventory</h3>
            <button
              disabled={busy || !canReview}
              onClick={() =>
                void act(async () => {
                  await api.bootstrap(workspace);
                  await refresh();
                  setNotice('Trusted functions registered after their independent tests passed.');
                })
              }
            >
              Initialize tested skill catalog
            </button>
            <button
              disabled={busy || !canReview}
              onClick={() =>
                void act(async () => {
                  await api.scan(workspace);
                  await refresh();
                  setNotice(
                    'Capability-gap scan completed. Proposals remain candidates until separately tested and activated.',
                  );
                })
              }
            >
              Scan recurring capability gaps
            </button>
          </div>
          {!lists.skills.length && (
            <p>
              No workspace skill registry initialized. Repository-reviewed rules remain the
              baseline.
            </p>
          )}
          <div className="vl-lesson-grid">
            <ul className="vl-list">
              {lists.skills.map((skill) => (
                <li key={skill.id}>
                  <button
                    className="vl-link"
                    onClick={() =>
                      void act(async () => setSelectedSkill(await api.skill(workspace, skill.id)))
                    }
                  >
                    {skill.skill_id} v{skill.version}
                  </button>
                  <span>{skill.state}</span>
                </li>
              ))}
            </ul>
            {selectedSkill && (
              <article>
                <h3>
                  {selectedSkill.skill_id} v{selectedSkill.version} · {selectedSkill.state}
                </h3>
                <p>
                  Source: {selectedSkill.manifest.source.replaceAll('_', ' ')}. Input/output
                  contracts: {selectedSkill.manifest.inputs} → {selectedSkill.manifest.outputs}.
                </p>
                <h4>Preconditions</h4>
                <ul>
                  {selectedSkill.manifest.preconditions.map((p) => (
                    <li key={p}>{p}</li>
                  ))}
                </ul>
                <h4>Permitted tools</h4>
                <p>{selectedSkill.manifest.permitted_tools.join(' → ')}</p>
                <p className="vl-hash">
                  Implementation: {selectedSkill.manifest.implementation_hash}
                </p>
                <p>
                  {selectedSkill.test_result
                    ? `${selectedSkill.test_result.passed ? 'Passed' : 'Failed'} ${selectedSkill.test_result.checks} isolated checks.`
                    : 'Independent tests pending.'}
                </p>
                {selectedSkill.test_result?.limitations.map((l) => (
                  <p className="vl-muted" key={l}>
                    {l}
                  </p>
                ))}
                <label>
                  Skill review reason
                  <input
                    value={reason}
                    onChange={(e) => setReason(e.target.value)}
                    maxLength={500}
                  />
                </label>
                <div className="vl-actions">
                  {(['test', 'activate', 'reject', 'revoke', 'supersede'] as const).map(
                    (action) => {
                      const states = {
                        test: ['candidate'],
                        activate: ['verified'],
                        reject: ['candidate', 'verified'],
                        revoke: ['candidate', 'testing', 'verified', 'active'],
                        supersede: ['verified', 'active'],
                      }[action];
                      return (
                        <button
                          key={action}
                          disabled={
                            busy ||
                            !canReview ||
                            !reason.trim() ||
                            !states.includes(selectedSkill.state)
                          }
                          onClick={() =>
                            void act(async () => {
                              await api.reviewSkill(workspace, selectedSkill, action, reason);
                              setSelectedSkill(await api.skill(workspace, selectedSkill.id));
                              await refresh();
                              setNotice(`Skill ${action} action recorded.`);
                            })
                          }
                        >
                          {action[0].toUpperCase() + action.slice(1)}
                        </button>
                      );
                    },
                  )}
                </div>
                {!canReview && <p>Workspace administrators and owners review executable skills.</p>}
                <h4>Lifecycle evidence</h4>
                <ul>
                  {selectedSkill.revisions?.map((r, i) => (
                    <li key={i}>
                      {r.state} · {new Date(r.at).toLocaleString()}
                    </li>
                  ))}
                </ul>
              </article>
            )}
          </div>
          {moreButton('skills')}
        </>
      )}
      {tab === 'decisions' && (
        <>
          <h3>Action-level decisions and labels</h3>
          <p className="vl-muted">
            Only executed, independently checked actions receive positive/negative labels. Untried
            candidates and missing outcomes remain unknown. Scores route repairs; they are not
            answer-confidence percentages.
          </p>
          {!lists.decisions.length && (
            <p>
              No collected decisions. Enable collection, then execute a task that needs a supported
              repair.
            </p>
          )}
          {lists.decisions.map((item) => (
            <details key={item.id}>
              <summary>
                {item.decision.selected_skill} v{item.decision.selected_version} ·{' '}
                {item.decision.selector} · {item.outcome?.label_status || 'unknown'}
              </summary>
              <p>
                Failure: {item.decision.diagnosis.category.replaceAll('_', ' ')}. Remaining repair
                budget: {item.decision.remaining_repairs}. Source:{' '}
                {item.outcome?.record.source_kind || 'outcome pending'}.
              </p>
              <p>
                Model: {item.decision.model_id || 'rules/memory'}. Fallback:{' '}
                {item.decision.fallback_reason || 'none'}.
              </p>
              <div className="vl-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Eligible skill</th>
                      <th>Routing score</th>
                      <th>Shadow score</th>
                      <th>Observed outcome</th>
                    </tr>
                  </thead>
                  <tbody>
                    {item.decision.eligible_candidates.map((c) => (
                      <tr key={c.skill_id}>
                        <td>
                          {c.skill_id} v{c.version}
                        </td>
                        <td>{item.decision.scores[c.skill_id]}</td>
                        <td>{item.decision.shadow_scores[c.skill_id] ?? 'Unavailable'}</td>
                        <td>
                          {c.skill_id === item.decision.selected_skill
                            ? item.outcome?.label_status || 'Unknown'
                            : 'Untried / unknown'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <ul>
                {item.outcome?.record.evidence.map((e, i) => (
                  <li key={i}>
                    {e.outcome}: {e.invariant}
                  </li>
                ))}
              </ul>
              <p className="vl-muted">
                Features: {item.decision.feature_version}. Context: {item.decision.context_version}.
                Target: local action postconditions, not complete-answer correctness.
              </p>
              {canReview && item.outcome && (
                <>
                  <label>
                    Outcome review reason
                    <input
                      value={reason}
                      onChange={(e) => setReason(e.target.value)}
                      maxLength={500}
                    />
                  </label>
                  <div className="vl-actions">
                    {(['disputed', 'unknown'] as const).map((label) => (
                      <button
                        key={label}
                        disabled={busy || !reason.trim()}
                        onClick={() =>
                          void act(async () => {
                            await api.reviewOutcome(
                              workspace,
                              item.outcome!.id,
                              item.outcome!.revision,
                              label,
                              reason,
                            );
                            await refresh();
                            setNotice(
                              'Label revision saved; dependent selector bundles invalidated. Positive/negative relabeling requires fresh independent verification.',
                            );
                          })
                        }
                      >
                        Mark {label}
                      </button>
                    ))}
                  </div>
                </>
              )}
            </details>
          ))}
          {moreButton('decisions')}
        </>
      )}
      {tab === 'training' && (
        <>
          <h3>Prepare data, replay alternatives, then train</h3>
          {!canReview ? (
            <p>
              Training data, job controls and candidate weights require administrator or owner
              access.
            </p>
          ) : (
            <>
              <details>
                <summary>Register a source case</summary>
                <p className="vl-muted">
                  Uses the configured Analysis task. A verified-run enrollment reuses its actual
                  collected action outcomes. Untouched final inputs must not already have been
                  analyzed.
                </p>
                <form
                  onSubmit={(e) => {
                    e.preventDefault();
                    void act(register);
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
                      Case split
                      <select
                        aria-label="Case split"
                        value={split}
                        onChange={(e) => setSplit(e.target.value as AdaptiveCase['split'])}
                      >
                        {['train', 'development', 'calibration', 'final'].map((s) => (
                          <option key={s}>{s}</option>
                        ))}
                      </select>
                    </label>
                    <label>
                      Label provenance
                      <select
                        aria-label="Label provenance"
                        value={source}
                        onChange={(e) => setSource(e.target.value as AdaptiveCase['source_kind'])}
                      >
                        <option value="synthetic">Synthetic fixture</option>
                        <option value="domain_reviewed">Independent domain review</option>
                        <option value="verified_run">
                          Selected verified run (train/development only)
                        </option>
                      </select>
                    </label>
                    <label>
                      Independent reference
                      <input
                        required={source !== 'verified_run'}
                        value={reference}
                        onChange={(e) => setReference(e.target.value)}
                      />
                    </label>
                  </div>
                  {source !== 'verified_run' && (
                    <>
                      <label>
                        Expected rubric status
                        <select
                          aria-label="Expected rubric status"
                          value={expectedStatus}
                          onChange={(e) =>
                            setExpectedStatus(e.target.value as CaseInput['expected_status'])
                          }
                        >
                          <option value="verified">Verified numeric result</option>
                          <option value="insufficient_evidence">Should clarify/abstain</option>
                        </select>
                      </label>
                      {expectedStatus === 'verified' &&
                        gold.map((row, i) => (
                          <div className="vl-fields" key={i}>
                            <label>
                              Expected group label
                              <input
                                value={row.group}
                                onChange={(e) =>
                                  setGold((values) =>
                                    values.map((v, n) =>
                                      n === i ? { ...v, group: e.target.value } : v,
                                    ),
                                  )
                                }
                              />
                            </label>
                            <label>
                              Expected result value
                              <input
                                value={row.value}
                                onChange={(e) =>
                                  setGold((values) =>
                                    values.map((v, n) =>
                                      n === i ? { ...v, value: e.target.value } : v,
                                    ),
                                  )
                                }
                              />
                            </label>
                          </div>
                        ))}
                      <button
                        type="button"
                        onClick={() => setGold((v) => [...v, { group: '', value: '' }])}
                      >
                        Add expected result group
                      </button>
                    </>
                  )}
                  <button disabled={busy}>Register source case</button>
                </form>
              </details>
              <fieldset>
                <legend>Compatible case partitions</legend>
                {!lists.cases.length && <p>No source cases registered.</p>}
                {lists.cases.map((c) => (
                  <label key={c.id} className="vl-check-label">
                    <input
                      type="checkbox"
                      disabled={!c.available}
                      checked={selectedCases.includes(c.id)}
                      onChange={(e) =>
                        setSelectedCases((v) =>
                          e.target.checked ? [...v, c.id] : v.filter((id) => id !== c.id),
                        )
                      }
                    />
                    {c.scenario_group} · {c.split} · {c.source_kind}
                    {!c.available && ' · invalidated'}
                  </label>
                ))}
              </fieldset>
              {moreButton('cases')}
              <button
                disabled={
                  busy ||
                  !selectedCases.some((id) =>
                    lists.cases.some(
                      (c) => c.id === id && ['train', 'development'].includes(c.split),
                    ),
                  )
                }
                onClick={() =>
                  void act(async () => {
                    await api.replay(
                      workspace,
                      lists.cases
                        .filter(
                          (c) =>
                            selectedCases.includes(c.id) &&
                            ['train', 'development'].includes(c.split),
                        )
                        .map((c) => c.id),
                    );
                    await refresh();
                    setNotice(
                      'Permissible train/development alternatives queued for isolated execution. Final inputs remain hidden from tuning.',
                    );
                  })
                }
              >
                Replay selected development alternatives
              </button>
              <div className="vl-fields">
                <label>
                  Minimum verified action examples
                  <input
                    type="number"
                    min={8}
                    value={minimumExamples}
                    onChange={(e) => setMinimumExamples(Number(e.target.value))}
                  />
                </label>
                <label>
                  Minimum independent train groups
                  <input
                    type="number"
                    min={2}
                    value={minimumGroups}
                    onChange={(e) => setMinimumGroups(Number(e.target.value))}
                  />
                </label>
                <label>
                  Minimum examples per class
                  <input
                    type="number"
                    min={2}
                    value={minimumClass}
                    onChange={(e) => setMinimumClass(Number(e.target.value))}
                  />
                </label>
                <label>
                  Maximum MLP epochs
                  <input
                    type="number"
                    min={5}
                    max={300}
                    value={epochs}
                    onChange={(e) => setEpochs(Number(e.target.value))}
                  />
                </label>
              </div>
              <p className="vl-muted">
                Both scorers share task/action features. Scaling fits training data only;
                tuning/stopping uses the declared development set. Final policy comparison is
                separate. Gates are frozen before results: no correctness/first-attempt regression
                or harmful output, p95 ≤ 1.5× baseline, 30 trusted final scenarios and measured
                policy benefit.
              </p>
              <button
                className="btn--primary"
                disabled={
                  busy ||
                  !(['train', 'development', 'final'] as const).every(
                    (s) =>
                      lists.cases.filter((c) => selectedCases.includes(c.id) && c.split === s)
                        .length >= 2,
                  )
                }
                onClick={() => void act(train)}
              >
                Train linear and MLP candidates
              </button>
              <h3>Durable adaptation jobs</h3>
              {!lists.jobs.length && <p>No replay or training jobs submitted.</p>}
              {lists.jobs.map((job) => (
                <details key={job.id} open={job.kind === 'train'}>
                  <summary>
                    {job.kind} · {job.state} · attempt {job.attempt}/{job.max_attempts}
                  </summary>
                  {job.error_code && <p role="alert">{job.error_code}</p>}
                  {job.result?.reason && <p>{job.result.reason}</p>}
                  {job.result?.trained === true && (
                    <p>
                      Selector numerical weights trained. Main LLM/embedding weights unchanged.
                      Active selector: {job.result.active_model}.
                    </p>
                  )}
                  {job.result?.trained === false && (
                    <p>No weights trained: evidence conditions not met.</p>
                  )}
                  {job.result?.measurements && (
                    <p>
                      CPU training: {job.result.measurements.training_seconds.toFixed(3)} seconds;
                      observed RSS{' '}
                      {(job.result.measurements.rss_peak_observed_bytes / 1048576).toFixed(1)} MiB;{' '}
                      {job.result.measurements.cpu_threads} numerical thread.
                    </p>
                  )}
                  {job.result?.comparison && (
                    <>
                      <p>
                        {job.result.comparison.sample_size} final cases,{' '}
                        {job.result.comparison.scenario_groups} scenario groups,{' '}
                        {job.result.comparison.trusted_final_groups} trusted final groups.
                      </p>
                      <div className="vl-scroll">
                        <table>
                          <thead>
                            <tr>
                              <th>Measure</th>
                              <th>Rules/memory</th>
                              <th>Linear</th>
                              <th>MLP</th>
                            </tr>
                          </thead>
                          <tbody>
                            {(
                              [
                                'first_attempt_correct',
                                'final_correct',
                                'verified_repair_success',
                                'attempted_repairs',
                                'failed_repair_attempts',
                                'repeated_errors',
                                'harmful_repairs',
                                'abstained',
                                'unknown',
                                'p50_latency_ms',
                                'p95_latency_ms',
                                'provider_cost_usd',
                              ] as const
                            ).map((metric) => (
                              <tr key={metric}>
                                <th>{metric.replaceAll('_', ' ')}</th>
                                {(['baseline', 'linear', 'mlp'] as const).map((kind) => (
                                  <td key={kind}>
                                    {job.result!.comparison!.metrics[kind][metric]}
                                  </td>
                                ))}
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                      {job.result.comparison.limits.map((l) => (
                        <p key={l} className="vl-muted">
                          {l}
                        </p>
                      ))}
                    </>
                  )}
                  <button
                    disabled={
                      busy ||
                      job.job_status !== 'FAILED' ||
                      !job.retry_eligible ||
                      job.attempt >= job.max_attempts
                    }
                    onClick={() =>
                      void act(async () => {
                        await api.retry(workspace, job.id);
                        await refresh();
                      })
                    }
                  >
                    Retry eligible transient job
                  </button>
                </details>
              ))}
              {moreButton('jobs')}
              <h3>Immutable selector bundles</h3>
              {!lists.models.length && (
                <p>No fitted candidate bundles. Rules/memory remains the active selector.</p>
              )}
              {lists.models.map((model) => (
                <details key={model.id}>
                  <summary>
                    {model.kind} · {model.state} ·{' '}
                    {model.evaluation.release_eligible ? 'release eligible' : 'release blocked'}
                  </summary>
                  <p>
                    {model.evaluation.parameter_count} numerical parameters. Train action log loss{' '}
                    {model.evaluation.train_action_log_loss}; development action log loss{' '}
                    {model.evaluation.development_action_log_loss}.
                  </p>
                  <p>
                    Inference p50/p95: {model.evaluation.inference_p50_ms} /{' '}
                    {model.evaluation.inference_p95_ms} ms. Calibration {model.calibration_status}.
                  </p>
                  <p>
                    Final correctness delta: {model.evaluation.paired_correctness_delta}; paired
                    scenario interval:{' '}
                    {model.evaluation.paired_scenario_bootstrap_95_interval?.join(' to ') ||
                      'Unavailable'}
                    .
                  </p>
                  <ul>
                    {Object.entries(model.evaluation.gates).map(([gate, pass]) => (
                      <li key={gate}>
                        {pass ? 'Pass' : 'Blocked'}: {gate.replaceAll('_', ' ')}
                      </li>
                    ))}
                  </ul>
                  {model.invalid_reason && <p>{model.invalid_reason}</p>}
                  <button
                    disabled={busy || !!model.invalid_reason}
                    onClick={() => void act(() => download(model.id))}
                  >
                    Download {model.kind} model bundle
                  </button>
                </details>
              ))}
              {moreButton('models')}
            </>
          )}
        </>
      )}
      {tab === 'controls' && (
        <>
          <h3>Collection, shadow and evaluated execution</h3>
          <p>
            Collection records action evidence while executing rules/memory. Shadow adds learned
            scores without executing alternative side effects. Active selection requires an
            independently evaluated release; unknown/new skills and incompatible models fall back to
            rules.
          </p>
          <p>
            Active model: {control?.active_model_id || 'rules-memory-v1'}. Generation:{' '}
            {control?.generation ?? 0}. Previous model: {control?.previous_model_id || 'none'}.
          </p>
          {!canReview && (
            <p>Only workspace administrators and owners can change adaptation policy.</p>
          )}
          <label>
            Candidate selector
            <select
              aria-label="Candidate selector"
              value={selectedModel}
              onChange={(e) => setSelectedModel(e.target.value)}
            >
              <option value="">Select evaluated candidate</option>
              {lists.models
                .filter((m) => !m.invalid_reason)
                .map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.kind} · {m.id}
                  </option>
                ))}
            </select>
          </label>
          <div className="vl-actions">
            {(['disabled', 'collection'] as const).map((mode) => (
              <button
                key={mode}
                disabled={busy || !canReview || control?.mode === mode}
                onClick={() =>
                  void act(async () => {
                    await api.configure(workspace, mode, control!.generation);
                    await refresh();
                  })
                }
              >
                {mode === 'disabled' ? 'Disable adaptive collection' : 'Collect action outcomes'}
              </button>
            ))}
            <button
              disabled={busy || !canReview || !selectedModel}
              onClick={() =>
                void act(async () => {
                  await api.configure(workspace, 'shadow', control!.generation, selectedModel);
                  await refresh();
                  setNotice(
                    'Shadow ranking enabled. Rules/memory still executes the selected action.',
                  );
                })
              }
            >
              Use shadow scores
            </button>
            <button
              disabled={busy || !canReview || !chosen?.evaluation.release_eligible}
              onClick={() =>
                void act(async () => {
                  await api.configure(workspace, 'active', control!.generation, selectedModel);
                  await refresh();
                  setNotice('Evaluated repair selector active for future runs.');
                })
              }
            >
              Activate evaluated selector
            </button>
            <button
              disabled={busy || !canReview || !control}
              onClick={() =>
                void act(async () => {
                  await api.rollback(workspace, control!.generation);
                  await refresh();
                  setNotice('Selector rolled back to rules/memory. No live weights were mutated.');
                })
              }
            >
              Rollback selector to rules
            </button>
          </div>
          <p className="vl-muted">
            Skill composition, saved experience, trained candidate weights and an evaluated active
            model are distinct states. No production improvement is inferred from a synthetic pilot.
          </p>
        </>
      )}
    </section>
  );
}
