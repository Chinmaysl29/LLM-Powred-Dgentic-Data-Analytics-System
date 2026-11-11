"""Public, validated supervisor contracts. No hidden reasoning is collected."""
from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Contract(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)


class DatasetRef(Contract):
    dataset_id: str = Field(min_length=1, max_length=36)
    version: int = Field(ge=1)


class Metric(Contract):
    column: str = Field(min_length=1, max_length=128)
    aggregation: Literal['sum', 'mean', 'min', 'max', 'count']
    missing: Literal['reject', 'exclude']
    definition_ref: str | None


class Filter(Contract):
    column: str = Field(min_length=1, max_length=128)
    operator: Literal['eq', 'ne', 'in', 'not_in']
    value: str | int | float | list[str | int | float]


class DateRange(Contract):
    column: str = Field(min_length=1, max_length=128)
    format: str = Field(min_length=1, max_length=40)
    start: datetime
    end: datetime

    @model_validator(mode='after')
    def ordered(self):
        if self.start.tzinfo is None or self.end.tzinfo is None or self.start >= self.end:
            raise ValueError('Date bounds must be timezone-aware and start before end (exclusive).')
        return self


class Relationship(Contract):
    left_dataset_id: str = Field(min_length=1, max_length=36)
    right_dataset_id: str = Field(min_length=1, max_length=36)
    left_key: str = Field(min_length=1, max_length=128)
    right_key: str = Field(min_length=1, max_length=128)
    order_amount: str = Field(min_length=1, max_length=128)
    refund_amount: str = Field(min_length=1, max_length=128)
    purpose: Literal['order_net_revenue', 'refund_event_count']
    cardinality: Literal['one_to_many']
    missing_refund_policy: Literal['no_event_means_no_refund']


class TaskSpec(Contract):
    workspace_id: UUID
    objective: str = Field(min_length=1, max_length=2000)
    task_type: Literal['descriptive', 'predictive', 'sql']
    datasets: Annotated[list[DatasetRef], Field(min_length=1, max_length=2)]
    metrics: Annotated[list[Metric], Field(min_length=1, max_length=1)]
    dimensions: list[str] = Field(max_length=3)
    grain: str = Field(min_length=1, max_length=200)
    filters: list[Filter] = Field(max_length=10)
    date_range: DateRange | None
    timezone: str
    units: str = Field(min_length=1, max_length=80)
    currency: str | None
    output: Literal['table', 'chart', 'report']
    definition_refs: list[str] = Field(max_length=10)
    assumptions: list[str] = Field(max_length=20)
    ambiguity: list[str] = Field(max_length=20)
    success_criteria: Annotated[list[str], Field(min_length=1, max_length=20)]
    relationships: list[Relationship] = Field(default_factory=list, max_length=1)

    @field_validator('timezone')
    @classmethod
    def valid_zone(cls, value):
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError:
            raise ValueError('Unknown IANA timezone') from None
        return value

    @model_validator(mode='after')
    def definition_selection(self):
        if self.metrics[0].definition_ref and self.metrics[0].definition_ref not in self.definition_refs:
            raise ValueError('Selected metric definition must appear in definition_refs.')
        if len({r.dataset_id for r in self.datasets}) != len(self.datasets):
            raise ValueError('Dataset references must be distinct.')
        if (len(self.datasets) == 2) != bool(self.relationships):
            raise ValueError('Two inputs require one explicit approved relationship.')
        if self.relationships and {self.relationships[0].left_dataset_id, self.relationships[0].right_dataset_id} != {r.dataset_id for r in self.datasets}:
            raise ValueError('Relationship datasets must match the pinned inputs.')
        return self


class Operation(Contract):
    type: Literal['exact_decimal_parse']
    column: str = Field(min_length=1, max_length=128)


class TransformationPlan(Contract):
    operations: list[Operation]
    input_versions: list[DatasetRef]
    preconditions: list[str]
    expected_effects: list[str]
    validation_rules: list[str]
    lineage: list[str]
    training_only_fit: bool


class ValidationResult(Contract):
    validator: str
    version: str
    invariant: str
    severity: Literal['error', 'warning', 'info']
    outcome: Literal['pass', 'fail', 'unknown']
    evidence_refs: list[str]
    limitations: list[str]


class Usage(Contract):
    provider: str
    calls: int = Field(ge=0)
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    cost_usd: float | None = Field(ge=0)


class StageResult(Contract):
    run_id: str
    stage_id: str
    attempt_id: str
    status: Literal['running', 'succeeded', 'waiting_for_input', 'failed', 'cancelled']
    input_artifacts: list[str]
    output_artifacts: list[str]
    validations: list[ValidationResult]
    versions: dict[str, str]
    started_at: datetime
    finished_at: datetime | None
    usage: Usage
    error_category: str | None


class Scope(Contract):
    workspace_id: UUID
    schema_hash: str = Field(pattern=r'^[a-f0-9]{64}$')
    definition_refs: list[str]
    task_type: Literal['descriptive']
    dataset_id: str | None


class LessonCandidate(Contract):
    type: Literal['technical', 'preference', 'domain_definition', 'dataset_fact']
    conditions: list[str] = Field(min_length=1, max_length=10)
    correction: Operation
    exceptions: list[str] = Field(min_length=1, max_length=10)
    scope: Scope
    provenance: list[str] = Field(min_length=1, max_length=20)
    verification_evidence: list[str]
    state: Literal['candidate', 'verified', 'active', 'rejected', 'superseded', 'expired', 'revoked']
    expires_at: datetime
    invalidation_rules: list[str] = Field(min_length=1, max_length=10)


class LessonVersion(LessonCandidate):
    lesson_id: str
    revision: int = Field(ge=1)
    content_hash: str


class Budget(Contract):
    max_repairs: int = Field(default=2, ge=0, le=2)
    deadline_seconds: int = Field(default=120, ge=1, le=600)
    provider: Literal['none'] = 'none'
    max_calls: Literal[0] = 0
    max_tokens: Literal[0] = 0
    max_cost_usd: Literal[0] = 0


class FeedbackRequest(Contract):
    idempotency_key: str = Field(min_length=1, max_length=128)
    category: Literal['interpretation', 'calculation', 'business_definition', 'presentation_preference', 'other']
    sentiment: Literal['positive', 'negative', 'neutral']
    comment: str = Field(default='', max_length=2000)
    correction: Operation | None = None
    evidence_artifact: str | None = None


class ReviewRequest(Contract):
    expected_state: str
    action: Literal['verify', 'activate', 'reject', 'revoke', 'expire']
    reason: str = Field(min_length=1, max_length=500)


class DefinitionRequest(Contract):
    key: str = Field(pattern=r'^[a-z][a-z0-9_]{0,63}$')
    version: int = Field(ge=1)
    source: str = Field(min_length=1, max_length=200)
    owner: str = Field(min_length=1, max_length=120)
    metric: Metric
    filters: list[Filter]
    units: str = Field(min_length=1, max_length=80)
    currency: str | None
    examples: Annotated[list[dict[str, Any]], Field(min_length=1, max_length=10)]


class Gates(Contract):
    min_cases: int = Field(default=30, ge=2, le=10000)
    max_correctness_regression: float = Field(default=0, ge=0, le=0.1)
    max_p95_ratio: float = Field(default=1.5, ge=1, le=5)
    max_cost_delta_usd: float = Field(default=0, ge=0, le=100)
    require_measured_benefit: bool = True


class EvaluationManifest(Contract):
    case_ids: Annotated[list[str], Field(min_length=2, max_length=200)]
    split_version: str = Field(min_length=1, max_length=128)
    dataset_versions: Annotated[list[DatasetRef], Field(min_length=1, max_length=200)]
    baseline_bundle: Literal['validated-baseline-v1']
    candidate_bundle: str
    memory_cutoff: datetime
    model_configuration: Literal['deterministic-supervisor-v1']
    graders: Literal['exact-decimal-reference-v1']
    metrics: Literal['paired-correctness-cost-latency-v1']
    budget: Budget
    gates: Gates


class EvaluationRequest(Contract):
    idempotency_key: str = Field(min_length=1, max_length=128)
    manifest: EvaluationManifest


class CaseRequest(Contract):
    task: TaskSpec
    scenario_group: str = Field(min_length=1, max_length=100)
    split: Literal['development', 'calibration', 'final']
    dataset_version: DatasetRef
    label_source: Literal['synthetic', 'domain_reviewed']
    reference: str = Field(min_length=1, max_length=200)
    expected_status: Literal['verified', 'insufficient_evidence']
    expected_rows: list[dict[str, Any]] = Field(max_length=1000)

    @model_validator(mode='after')
    def valid_gold(self):
        from decimal import Decimal, InvalidOperation
        if self.expected_status == 'insufficient_evidence' and self.expected_rows:
            raise ValueError('An abstention label cannot include result rows.')
        keys = set(self.task.dimensions) | {'value'}
        groups = set()
        for row in self.expected_rows:
            if set(row) != keys:
                raise ValueError('Expected row fields must match grouping dimensions and value.')
            if any(row[k] is not None and not isinstance(row[k], str) for k in self.task.dimensions):
                raise ValueError('Expected group labels must be strings or null, matching result serialization.')
            group = tuple(row[k] for k in self.task.dimensions)
            if group in groups:
                raise ValueError('Expected groups must be unique.')
            groups.add(group)
            value = row['value']
            try:
                if value is not None and (isinstance(value, bool) or not Decimal(str(value)).is_finite()):
                    raise ValueError('Expected numeric values must be finite.')
            except InvalidOperation:
                raise ValueError('Expected result is not numeric.') from None
        return self


RUN_TRANSITIONS = {
    'queued': {'running', 'cancelled'},
    'running': {'waiting_for_input', 'succeeded', 'partial', 'failed', 'cancelled'},
    'waiting_for_input': {'queued', 'cancelled'},
    'partial': set(), 'succeeded': set(), 'failed': {'queued'}, 'cancelled': set(),
}
LESSON_TRANSITIONS = {
    'candidate': {'verified', 'rejected', 'revoked', 'expired'},
    'verified': {'active', 'rejected', 'revoked', 'expired', 'superseded'},
    'active': {'revoked', 'expired', 'superseded'},
    'rejected': set(), 'superseded': set(), 'expired': set(), 'revoked': set(),
}


def transition(current: str, target: str, machine=RUN_TRANSITIONS):
    if target not in machine.get(current, set()):
        raise ValueError(f'Illegal transition: {current} -> {target}')
    return target
