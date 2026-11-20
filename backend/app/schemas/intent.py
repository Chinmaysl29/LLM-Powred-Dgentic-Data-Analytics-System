"""Pydantic schemas and enums for Phase 3.1 Intent Classification."""

from enum import Enum
from typing import Any
from pydantic import BaseModel, ConfigDict, Field


class IntentType(str, Enum):
    """Supported intent categories for the AI Data Analyst OS."""

    DATASET_OVERVIEW = "dataset_overview"
    EDA_ANALYSIS = "eda_analysis"
    TREND_ANALYSIS = "trend_analysis"
    COMPARISON_ANALYSIS = "comparison_analysis"
    DISTRIBUTION_ANALYSIS = "distribution_analysis"
    CORRELATION_ANALYSIS = "correlation_analysis"
    RANKING_ANALYSIS = "ranking_analysis"
    FORECASTING = "forecasting"
    ANOMALY_DETECTION = "anomaly_detection"
    DASHBOARD_GENERATION = "dashboard_generation"
    REPORT_GENERATION = "report_generation"
    RECOMMENDATION_GENERATION = "recommendation_generation"
    WHAT_IF_ANALYSIS = "what_if_analysis"
    SQL_QUERY = "sql_query"
    RAG_QUERY = "rag_query"
    DATA_QUALITY = "data_quality"
    UNKNOWN = "unknown"
    OUT_OF_SCOPE = "out_of_scope"
    RELEVANT_BUT_UNANSWERABLE = "relevant_but_unanswerable"
    NO_ACTIVE_DATA_SOURCE = "no_active_data_source"
    AMBIGUOUS_QUERY = "ambiguous_query"


class IntentDefinition(BaseModel):
    """Metadata and routing rules for an intent within the extensible registry."""

    model_config = ConfigDict(from_attributes=True)

    name: str = Field(description="Unique identifier for the intent")
    description: str = Field(description="Detailed description of what this intent represents")
    required_agents: list[str] = Field(default_factory=list, description="List of agent names required to execute this intent")
    keywords: list[str] = Field(default_factory=list, description="Keywords associated with this intent")
    patterns: list[str] = Field(default_factory=list, description="Regex patterns that match this intent")
    examples: list[str] = Field(default_factory=list, description="Sample user queries for few-shot prompt construction")


class IntentClassificationRequest(BaseModel):
    """Incoming request payload for intent classification."""

    query: str = Field(..., min_length=1, max_length=2000, description="Natural language user prompt")
    context: dict[str, Any] | None = Field(default=None, description="Optional conversational or dataset context")
    dataset_id: str | None = Field(default=None, description="Optional active dataset UUID")


class IntentClassificationResponse(BaseModel):
    """Structured response conforming to Phase 3.1 specification."""

    model_config = ConfigDict(from_attributes=True)

    intent: str = Field(..., description="Classified intent category name")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score between 0.0 and 1.0")
    reasoning: str = Field(..., description="Explanation of why this intent was selected")
    required_agents: list[str] = Field(default_factory=list, description="Specialized agents required to fulfill this intent")


class QueryRelevanceResult(BaseModel):
    """Structured result from the QueryRelevanceRouter."""

    model_config = ConfigDict(from_attributes=True)

    intent: IntentType
    dataset_relevant: bool
    answerable: bool
    confidence: float = Field(ge=0.0, le=1.0)
    reason_code: str
    target_dataset_id: str | None = None
    requested_fields: list[str] = Field(default_factory=list)
    requires_execution: bool = True
