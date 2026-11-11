"""Validated adaptation contracts. Routing scores are not answer confidence."""
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import Field, model_validator
from backend.app.schemas.learning import Contract, TaskSpec, CaseRequest

FailureCategory = Literal['ambiguous_definition','stale_schema','invalid_query','join_fan_out',
    'aggregation_mismatch','missing_data','unit_mismatch','provider_failure','permission_denial',
    'numeric_representation','budget_exhausted','integrity_failure','unknown']
SkillState = Literal['candidate','testing','verified','active','rejected','superseded','revoked']


class ProblemContext(Contract):
    version: Literal['problem-context-v1'] = 'problem-context-v1'
    task: TaskSpec
    schema_versions: dict[str, str]
    entities: list[str]
    grain: str
    quality_findings: dict[str, Any]
    constraints: list[str]
    acceptance_checks: list[str]
    interpretation_source: Literal['explicit_contract','rules','frozen_llm']
    provider: str | None
    limitations: list[str]


class Diagnosis(Contract):
    observed_failure: str
    category: FailureCategory
    evidence: list[dict[str, Any]]
    proposed_causes: list[str]
    distinguishing_checks: list[str]
    established: bool


class SkillManifest(Contract):
    skill_id: str = Field(pattern=r'^[a-z][a-z0-9_.-]{0,79}$')
    version: int = Field(ge=1)
    implementation: Literal['decimal_exact','decimal_vector_checked','refunds_per_order',
        'unique_refund_join','refund_event_count','join_cardinality_check','date_format_check','chart_result_check','approved_recipe']
    implementation_hash: str = Field(pattern=r'^[a-f0-9]{64}$')
    inputs: Literal['ProblemContext+authorized-dataframes@1']
    outputs: Literal['SkillResult+ValidationResult@1']
    preconditions: list[str] = Field(min_length=1)
    permitted_tools: list[str] = Field(min_length=1, max_length=8)
    resource_limits: dict[str, int]
    stages: list[int] = Field(min_length=1)
    workspace_id: UUID
    definition_refs: list[str]
    task_types: list[Literal['descriptive']]
    tests: list[str] = Field(min_length=1)
    lifecycle: SkillState
    recipe: list[str] = Field(default_factory=list, max_length=6)
    source: Literal['repository_reviewed','composed_candidate']


class DecisionRecord(Contract):
    context_version: str
    feature_version: str
    context_hash: str
    eligible_candidates: list[dict[str, Any]]
    selected_skill: str | None
    selected_version: int | None
    selector: str
    model_id: str | None
    scores: dict[str, float]
    shadow_scores: dict[str, float]
    fallback_reason: str | None
    decided_at: datetime
    remaining_repairs: int = Field(ge=0)
    selection_probability: float | None
    exploration: Literal[False] = False


class OutcomeRecord(Contract):
    decision_id: str
    action_id: str
    action_version: int
    result: Literal['success','failure','unknown']
    label_status: Literal['positive','negative','unknown','disputed']
    label_policy: Literal['independent-action-postconditions-v1']
    evidence: list[dict[str, Any]]
    failure_category: FailureCategory | None
    usage: dict[str, Any]
    parent_run_id: str | None
    source_kind: Literal['live','synthetic','domain_reviewed','verified_run']


class ModelBundle(Contract):
    format: Literal['repair-scorer-json-v1']
    kind: Literal['linear','mlp']
    weights: list[list[list[float]]]
    biases: list[list[float]]
    preprocessing: dict[str, list[float]]
    feature_schema: list[str]
    feature_version: str
    embedding_version: Literal['unused-frozen-embeddings']
    training_manifest: dict[str, Any]
    label_policy: Literal['independent-action-postconditions-v1']
    compatibility: dict[str, Any]
    calibration_status: Literal['unavailable']
    evaluation: dict[str, Any]


class AdaptiveCaseRequest(Contract):
    task: TaskSpec
    scenario_group: str = Field(min_length=1, max_length=100)
    split: Literal['train','development','calibration','final']
    source_kind: Literal['synthetic','domain_reviewed','verified_run']
    source_run_id: str | None = Field(default=None,max_length=36)
    reference: str = Field(min_length=1, max_length=250)
    expected_status: Literal['verified','insufficient_evidence']
    expected_rows: list[dict[str, Any]] = Field(max_length=1000)

    @model_validator(mode='after')
    def validate_gold(self):
        CaseRequest(task=self.task, scenario_group=self.scenario_group, split='final',
            dataset_version=self.task.datasets[0], label_source='synthetic' if self.source_kind=='verified_run' else self.source_kind, reference=self.reference,
            expected_status=self.expected_status, expected_rows=self.expected_rows)
        if self.source_kind=='verified_run' and (not self.source_run_id or self.split not in {'train','development'}):
            raise ValueError('Previously observed verified runs can be enrolled only in train/development, with a source run reference.')
        if self.source_kind!='verified_run' and self.source_run_id:
            raise ValueError('Source run references require verified_run provenance.')
        return self


class ReplayRequest(Contract):
    case_ids: list[str] = Field(min_length=1, max_length=200)
    idempotency_key: str = Field(min_length=1, max_length=128)


class SelectorGates(Contract):
    min_trusted_final_groups: int = Field(default=30, ge=2, le=10000)
    max_final_regressions: Literal[0] = 0
    max_first_attempt_regressions: Literal[0] = 0
    max_harmful_repairs: Literal[0] = 0
    max_p95_ratio: float = Field(default=1.5, ge=1, le=5)
    require_policy_benefit: Literal[True] = True


class TrainingRequest(Contract):
    train_case_ids: list[str] = Field(min_length=2, max_length=300)
    development_case_ids: list[str] = Field(min_length=2, max_length=100)
    final_case_ids: list[str] = Field(min_length=2, max_length=100)
    min_examples: int = Field(default=40, ge=8, le=100000)
    min_groups: int = Field(default=6, ge=2, le=1000)
    min_per_class: int = Field(default=8, ge=2, le=10000)
    seed: int = Field(default=17, ge=0, le=100000)
    max_epochs: int = Field(default=120, ge=5, le=300)
    deadline_seconds: int = Field(default=120, ge=10, le=600)
    gates: SelectorGates = Field(default_factory=SelectorGates)
    idempotency_key: str = Field(min_length=1, max_length=128)

    @model_validator(mode='after')
    def disjoint(self):
        lists=[self.train_case_ids,self.development_case_ids,self.final_case_ids]
        if any(len(set(values)) != len(values) for values in lists) or any(set(lists[i]) & set(lists[j]) for i in range(3) for j in range(i)):
            raise ValueError('Training/development/final cases must be distinct; no duplicate cases.')
        return self


class LifecycleRequest(Contract):
    expected_state: SkillState
    action: Literal['test','activate','reject','revoke','supersede']
    reason: str = Field(min_length=1, max_length=500)


class SelectorControlRequest(Contract):
    mode: Literal['disabled','collection','shadow','active']
    expected_generation: int = Field(ge=0)
    model_id: str | None = None


class OutcomeReviewRequest(Contract):
    expected_revision: int = Field(ge=1)
    label_status: Literal['unknown','disputed']
    reason: str = Field(min_length=1, max_length=500)


class InterpretationRequest(Contract):
    task: TaskSpec
    use_provider: bool = False


SKILL_TRANSITIONS={'candidate':{'testing','rejected','revoked'},'testing':{'verified','rejected','revoked'},
    'verified':{'active','rejected','revoked','superseded'},'active':{'revoked','superseded'},
    'rejected':set(),'superseded':set(),'revoked':set()}
