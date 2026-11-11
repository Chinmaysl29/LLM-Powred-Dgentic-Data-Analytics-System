"""Typed company operations. Stored text is never executable code."""
from datetime import date, datetime
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo
from pydantic import Field, field_validator, model_validator
from backend.app.dataplane.contracts import StrictModel, QueryPlan
from backend.app.schemas.learning import DefinitionRequest


class HealthRule(StrictModel):
    column: str = Field(min_length=1, max_length=128)
    check: Literal['not_null', 'unique', 'range']
    minimum: float | None = None
    maximum: float | None = None
    severity: Literal['warning', 'critical'] = 'critical'

    @model_validator(mode='after')
    def bounds(self):
        if self.check == 'range' and self.minimum is None and self.maximum is None:
            raise ValueError('A range requires a bound')
        if self.minimum is not None and self.maximum is not None and self.minimum > self.maximum:
            raise ValueError('Reversed range')
        return self


class DictionaryDraft(StrictModel):
    definition: DefinitionRequest
    dataset_id: str = Field(min_length=1, max_length=36)
    description: str = Field(min_length=1, max_length=500)
    domain: str = Field(min_length=1, max_length=100)
    aliases: list[str] = Field(default_factory=list, max_length=20)
    grain: str = Field(min_length=1, max_length=200)
    timezone: str = 'UTC'
    date_basis: str = Field(min_length=1, max_length=200)
    exclusions: list[str] = Field(default_factory=list, max_length=20)
    effective_from: date
    effective_to: date | None = None
    health_rules: list[HealthRule] = Field(default_factory=list, max_length=20)

    @field_validator('timezone')
    @classmethod
    def valid_zone(cls, value):
        ZoneInfo(value)
        return value

    @field_validator('aliases', 'exclusions')
    @classmethod
    def bounded_text(cls, values):
        if any(not x.strip() or len(x) > 200 for x in values):
            raise ValueError('Use nonempty text of at most 200 characters')
        return values

    @model_validator(mode='after')
    def ordered(self):
        import json
        if len(json.dumps(self.definition.examples, default=str).encode()) > 16384:
            raise ValueError('Reviewed examples exceed the 16 KiB metadata budget')
        if self.effective_to and self.effective_to <= self.effective_from:
            raise ValueError('Effective end must follow start (exclusive)')
        if any(f.operator not in {'eq', 'ne'} for f in self.definition.filters):
            raise ValueError('This engine supports approved equality and inequality exclusions only')
        return self


class Review(StrictModel):
    expected_revision: int = Field(ge=0)
    action: Literal['review', 'approve', 'revoke', 'supersede', 'activate', 'pause', 'retire', 'acknowledge', 'resolve']
    reason: str = Field(min_length=1, max_length=500)


class TimeWindow(StrictModel):
    column: str = Field(min_length=1, max_length=128)
    start: datetime
    end: datetime

    @model_validator(mode='after')
    def bounds(self):
        if self.start.tzinfo is None or self.end.tzinfo is None or self.start >= self.end:
            raise ValueError('Use explicit offset-aware start and end (exclusive)')
        return self


class CompanyQuery(StrictModel):
    definition_id: str = Field(min_length=1, max_length=36)
    snapshot_id: UUID
    business_date: date
    plan: QueryPlan
    time_window: TimeWindow | None = None
    idempotency_key: str = Field(min_length=1, max_length=128)


class WorkflowLimits(StrictModel):
    memory_mb: int = Field(512, ge=64, le=512)
    threads: int = Field(2, ge=1, le=2)
    timeout_s: int = Field(120, ge=1, le=120)
    result_rows: int = Field(5000, ge=1, le=5000)


class RelativeWindow(StrictModel):
    column: str = Field(min_length=1, max_length=128)
    completed_days: int = Field(ge=1, le=366)


class WorkflowDraft(StrictModel):
    name: str = Field(min_length=1, max_length=100)
    purpose: str = Field(min_length=1, max_length=500)
    query: CompanyQuery
    require_artifact_review: bool = True
    previous_version_id: UUID | None = None
    resources: WorkflowLimits = Field(default_factory=WorkflowLimits)
    source_selection: Literal['pinned', 'active_at_start'] = 'pinned'
    relative_window: RelativeWindow | None = None

    @model_validator(mode='after')
    def one_window(self):
        if self.relative_window and self.query.time_window:
            raise ValueError('Select an absolute or relative time window, not both')
        return self


class EvidenceContract(StrictModel):
    """Required fields validated before publication; engine details remain separate."""
    contract_version: Literal[1]
    workspace_id: UUID
    run_id: UUID
    result_id: UUID
    definition_id: str
    definition_version: int
    definition_hash: str
    source_version: str
    snapshot_id: UUID
    coverage: Literal['full']
    execution_status: Literal['succeeded', 'blocked']
    validation_status: Literal['passed', 'failed']
    completed_at: datetime
    query_hash: str
    result_hash: str
    computation_precision: str
    model: dict
    lineage: dict


class Schedule(StrictModel):
    expected_revision: int = Field(ge=0)
    enabled: bool = False
    timezone: str = 'UTC'
    hour: int = Field(9, ge=0, le=23)
    minute: int = Field(0, ge=0, le=59)
    dst_policy: Literal['first_occurrence_skip_nonexistent'] = 'first_occurrence_skip_nonexistent'
    overlap: Literal['skip'] = 'skip'
    catch_up: Literal['latest_only'] = 'latest_only'

    @field_validator('timezone')
    @classmethod
    def zone(cls, value):
        ZoneInfo(value)
        return value


class Policy(StrictModel):
    allow_self_approval: bool
    expected_revision: int = Field(ge=0)
    reason: str = Field(min_length=1, max_length=500)


class SwitchVersion(StrictModel):
    expected_active_version_id: str
    target_snapshot_id: UUID
    reason: str = Field(min_length=1, max_length=500)


class Compare(StrictModel):
    previous_id: UUID
    current_id: UUID


class RunWorkflow(StrictModel):
    idempotency_key: str = Field(min_length=1, max_length=80)


class GrantReviewer(StrictModel):
    expected_revision: int = Field(ge=0)
    expires_at: datetime
    reason: str = Field(min_length=1, max_length=500)


class RevokeReviewer(StrictModel):
    expected_revision: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=500)
