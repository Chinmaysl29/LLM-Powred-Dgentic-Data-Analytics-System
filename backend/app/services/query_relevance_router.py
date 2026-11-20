"""
Query Relevance Router — dataset-aware intent gate that runs before all analytics.

Classifies every incoming question as one of:
  OUT_OF_SCOPE             → "Irrelevant topic."
  NO_ACTIVE_DATA_SOURCE    → ask user to upload/select a dataset
  DATA_QUERY               → route to analytics engine
  DATA_ANALYSIS            → route to analytics engine
  DATA_VISUALIZATION       → route to analytics engine
  DATA_FORECASTING         → route to analytics engine
  DATA_METADATA            → route to analytics engine
  RELEVANT_BUT_UNANSWERABLE→ explain what's missing
  AMBIGUOUS_QUERY          → ask clarification
"""
from __future__ import annotations

import logging
import re
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# --- Deterministic out-of-scope pattern library ----------------------------
# These patterns match questions that are CLEARLY about general knowledge,
# people, places, events, or other topics with no data analytics relevance.
# IMPORTANT: Do NOT hardcode specific names. Use semantic categories.
_OUT_OF_SCOPE_PATTERNS = [
    # Questions about people / politicians / celebrities
    r"\btell\s+me\s+about\s+(?!my\s+data|this\s+data|the\s+data|dataset)(\w+)\b",
    r"\bwho\s+is\s+(the\s+)?(president|prime\s+minister|ceo|founder|cto|cfo|king|queen|mayor|governor|chancellor)\b",
    r"\bwhat\s+did\s+\w+\s+say\b",
    r"\bbiography\s+of\b",
    # Geography / politics with no dataset qualifier
    r"\bpolitical\s+(history|situation|system|party|parties)\b",
    r"\bcapital\s+(city\s+)?of\b",
    r"\bpopulation\s+of\s+(mars|venus|jupiter|moon|earth|the\s+sun)\b",
    r"\bwhat\s+country\s+is\b",
    # Creative / entertainment content
    r"\bwrite\s+(a\s+)?(poem|song|story|joke|essay|letter|email)\b",
    r"\btell\s+me\s+a\s+joke\b",
    r"\brecite\s+a\b",
    r"\bwhat\s+(happened|won|lost)\s+(in\s+)?(yesterday|last\s+night|the\s+match|the\s+game|the\s+election)\b",
    r"\b(cricket|football|soccer|basketball|baseball)\s+(match|game|score|result)\b",
    r"\blatest\s+(news|headlines|updates)\b",
    # Philosophy / metaphysics
    r"\bmeaning\s+of\s+life\b",
    r"\bwhat\s+is\s+god\b",
    r"\bexplain\s+(quantum\s+physics|relativity|string\s+theory|dark\s+matter)\b",
    # Recipes / personal advice
    r"\brecipe\s+for\b",
    r"\bhow\s+to\s+cook\b",
    r"\brelationship\s+advice\b",
]

# Dataset analytics trigger patterns — if any match, the question is data-related
_DATA_ANALYTICS_PATTERNS = [
    r"\b(total|sum|average|avg|mean|count|how\s+many|number\s+of|how\s+much)\b",
    r"\b(top|bottom|highest|lowest|best|worst|maximum|minimum|rank)\b",
    r"\b(trend|growth|decline|compare|comparison|versus|vs)\b",
    r"\b(distribution|histogram|correlation|outlier|anomaly)\b",
    r"\b(revenue|sales|profit|margin|cost|price|quantity|amount)\b",
    r"\b(chart|plot|graph|visualize|dashboard)\b",
    r"\b(predict|forecast|projection)\b",
    r"\b(dataset|data|rows|columns|records|schema|upload|file)\b",
    r"\b(show|display|list|find|filter|group|aggregate)\b.*\b(data|records|rows|companies|customers|products)\b",
    r"\b(find|identify|detect|check|validate)\b.*\b(missing|null|duplicate|outlier|error|invalid)\b",
    r"\bwhich\s+(company|customer|product|region|category|entity)\b",
    r"\bin\s+(my|the|this)\s+(data|dataset|table|file|spreadsheet)\b",
]

# Follow-up continuation patterns — these suggest the question continues a data conversation
_FOLLOWUP_PATTERNS = [
    r"^what\s+about\s",
    r"^(and|also|now)\s+(what|show|tell|give)\b",
    r"^(how\s+about|what\s+if)\b",
    r"^(break\s+it|break\s+that)\s+down\b",
    r"^same\s+(but|for)\b",
    r"^\bfilter\s+(by|for|to)\b",
]

# Minimum analytics vocabulary required when no other signals are present
_ANALYTICS_KEYWORDS = {
    "total", "sum", "average", "avg", "mean", "count", "top", "bottom",
    "highest", "lowest", "best", "worst", "rank", "ranking", "maximum", "minimum",
    "trend", "growth", "compare", "distribution", "correlation", "outlier",
    "forecast", "predict", "chart", "plot", "graph", "dashboard", "revenue",
    "sales", "profit", "margin", "data", "dataset", "records", "rows", "columns",
    "schema", "upload", "filter", "group", "aggregate", "show", "list", "find",
    "missing", "null", "duplicate", "outlier", "values", "quality", "validate",
}


class RelevanceDecision(BaseModel):
    """Structured routing decision from the QueryRelevanceRouter."""

    intent_category: str  # OUT_OF_SCOPE | DATA_QUERY | DATA_METADATA | etc.
    dataset_relevant: bool | None
    answerable: bool
    confidence: float = Field(ge=0.0, le=1.0)
    reason_code: str
    rejection_message: str | None = None  # Only set for non-data intents
    requires_execution: bool = True


class QueryRelevanceRouter:
    """
    Deterministic first-pass gate that runs before expensive analytics operations.

    Uses pattern matching + semantic signals + conversation context to decide:
    - Is this question about the user's data? → allow through
    - Is this a general knowledge / off-topic question? → reject with "Irrelevant topic."
    - Does it need a dataset that isn't selected? → ask user to select one
    - Is it ambiguous? → ask for clarification
    """

    def route(
        self,
        message: str,
        dataset_id: str | None,
        schema_columns: list[str] | None = None,
        conversation_context: list[dict[str, str]] | None = None,
    ) -> RelevanceDecision:
        """
        Classify the message and return a routing decision.

        Args:
            message: The user's natural language question.
            dataset_id: Active dataset ID (None if no dataset selected).
            schema_columns: Column names from the active dataset, if available.
            conversation_context: Recent conversation turns for follow-up detection.

        Returns:
            RelevanceDecision with intent_category and optional rejection_message.
        """
        q = message.strip()
        q_lower = q.lower()

        # 1. Check for explicit out-of-scope patterns FIRST (high precision)
        for pattern in _OUT_OF_SCOPE_PATTERNS:
            # Exception: "tell me about X in my dataset" is data-relevant
            if re.search(pattern, q_lower, re.IGNORECASE):
                # Check if the same message ALSO has a data qualifier
                has_data_qualifier = bool(re.search(
                    r"\b(in\s+(my|the|this)\s+(data|dataset|table)|from\s+(my|the)\s+(data|dataset))\b",
                    q_lower
                ))
                if not has_data_qualifier:
                    return RelevanceDecision(
                        intent_category="OUT_OF_SCOPE",
                        dataset_relevant=False,
                        answerable=False,
                        confidence=0.97,
                        reason_code="GENERAL_KNOWLEDGE_REQUEST",
                        rejection_message="Irrelevant topic.",
                        requires_execution=False,
                    )

        # 2. Check if this looks like a data-analytics question
        is_analytics = self._is_analytics_question(q_lower, schema_columns)

        # 3. Check if this is a follow-up in an ongoing data conversation
        is_followup = self._is_followup(q_lower, conversation_context)

        # 4. If no dataset and question seems analytics-related → ask for dataset
        if not dataset_id and is_analytics and not is_followup:
            return RelevanceDecision(
                intent_category="NO_ACTIVE_DATA_SOURCE",
                dataset_relevant=True,
                answerable=False,
                confidence=0.90,
                reason_code="NO_DATASET_SELECTED",
                rejection_message="Please upload or select a dataset before asking data-related questions.",
                requires_execution=False,
            )

        # 5. If it has analytics signals → let it through
        if is_analytics or is_followup:
            return RelevanceDecision(
                intent_category="DATA_QUERY",
                dataset_relevant=True,
                answerable=True,
                confidence=0.88,
                reason_code="ANALYTICS_SIGNALS_DETECTED",
                requires_execution=True,
            )

        # 6. Very short or vague with no analytics vocabulary → ambiguous
        words = q.split()
        if len(words) <= 3 and not is_analytics:
            return RelevanceDecision(
                intent_category="AMBIGUOUS_QUERY",
                dataset_relevant=None,
                answerable=False,
                confidence=0.60,
                reason_code="INSUFFICIENT_CONTEXT",
                rejection_message="Could you clarify what you'd like to know about your data?",
                requires_execution=False,
            )

        # 7. No analytics signals, no out-of-scope pattern match → out of scope
        # This catches generic statements that matched no specific pattern
        # but also have no data analytics vocabulary.
        analytics_word_count = sum(1 for w in q_lower.split() if w in _ANALYTICS_KEYWORDS)
        if analytics_word_count == 0:
            return RelevanceDecision(
                intent_category="OUT_OF_SCOPE",
                dataset_relevant=False,
                answerable=False,
                confidence=0.82,
                reason_code="NO_ANALYTICS_VOCABULARY",
                rejection_message="Irrelevant topic.",
                requires_execution=False,
            )

        # 8. Default: allow through with moderate confidence
        return RelevanceDecision(
            intent_category="DATA_QUERY",
            dataset_relevant=True,
            answerable=True,
            confidence=0.70,
            reason_code="DEFAULT_ALLOW",
            requires_execution=True,
        )

    def _is_analytics_question(
        self, q_lower: str, schema_columns: list[str] | None
    ) -> bool:
        """Return True if the question contains analytics signals."""
        # Check known analytics patterns
        for pattern in _DATA_ANALYTICS_PATTERNS:
            if re.search(pattern, q_lower, re.IGNORECASE):
                return True
        # Check if any schema column name appears in the question
        if schema_columns:
            for col in schema_columns:
                col_words = re.split(r"[_ -]+", col.lower())
                if any(len(w) > 2 and w in q_lower for w in col_words):
                    return True
        return False

    def _is_followup(
        self, q_lower: str, context: list[dict[str, str]] | None
    ) -> bool:
        """Return True if the question looks like a follow-up to a data conversation."""
        if not context:
            return False
        # Check follow-up linguistic patterns
        for pattern in _FOLLOWUP_PATTERNS:
            if re.search(pattern, q_lower, re.IGNORECASE):
                return True
        return False


# Singleton instance
_router = QueryRelevanceRouter()


def get_query_relevance_router() -> QueryRelevanceRouter:
    return _router
