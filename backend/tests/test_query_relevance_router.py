"""Tests for the QueryRelevanceRouter — covers all intent categories."""
import pytest
from backend.app.services.query_relevance_router import QueryRelevanceRouter


@pytest.fixture
def router():
    return QueryRelevanceRouter()


# ── Group A: Irrelevant questions ──────────────────────────────────────────
@pytest.mark.parametrize("question", [
    "tell me about Modi",
    "tell me about USA",
    "Who is the current Prime Minister?",
    "Write a poem",
    "Tell me a joke",
    "What happened in yesterday's cricket match?",
    "What is the population of Mars?",
    "Who won the last election?",
    "Tell me about the history of Rome",
    "What is the meaning of life?",
    "Who is Elon Musk?",
    "Tell me about France",
])
def test_out_of_scope_questions(router, question):
    decision = router.route(message=question, dataset_id="ds-123")
    assert decision.intent_category == "OUT_OF_SCOPE", (
        f"Expected OUT_OF_SCOPE for '{question}', got {decision.intent_category} "
        f"(reason: {decision.reason_code})"
    )
    assert decision.rejection_message == "Irrelevant topic."
    assert decision.requires_execution is False
    assert decision.dataset_relevant is False


# ── Group B: Valid dataset questions ──────────────────────────────────────
@pytest.mark.parametrize("question", [
    "How many records are uploaded?",
    "What columns exist in this dataset?",
    "Which company has the highest revenue?",
    "Calculate average sales",
    "Find missing values",
    "Show the top 10 records by profit",
    "Total revenue by company",
    "What is the average profit margin?",
    "Show companies located in the USA",
    "How many companies are in my dataset?",
    "Which company has the highest revenue?",
    "Compare top 2 companies by sales",
    "Show revenue trend over time",
    "What is the distribution of profit?",
])
def test_valid_dataset_questions(router, question):
    decision = router.route(message=question, dataset_id="ds-123")
    assert decision.intent_category != "OUT_OF_SCOPE", (
        f"Should NOT be OUT_OF_SCOPE for '{question}', got {decision.intent_category}"
    )
    assert decision.requires_execution is True


# ── Group C: No dataset selected ───────────────────────────────────────────
def test_no_dataset_selected(router):
    decision = router.route(message="Show total revenue by company", dataset_id=None)
    assert decision.intent_category == "NO_ACTIVE_DATA_SOURCE"
    assert decision.requires_execution is False


# ── Group D: Schema-aware routing ──────────────────────────────────────────
def test_schema_aware_routing(router):
    """Column names in schema should help identify data questions."""
    schema = ["company_name", "annual_revenue", "country", "profit_margin"]
    decision = router.route(
        message="Show companies by country",
        dataset_id="ds-123",
        schema_columns=schema,
    )
    assert decision.intent_category != "OUT_OF_SCOPE"
    assert decision.requires_execution is True


# ── Group E: Follow-up context ──────────────────────────────────────────────
def test_followup_in_data_conversation(router):
    """'What about USA?' after a data question is data-relevant."""
    context = [
        {"role": "user", "content": "Show total sales by country"},
        {"role": "assistant", "content": "USA: 500000, UK: 300000, Germany: 200000"},
    ]
    decision = router.route(
        message="What about USA?",
        dataset_id="ds-123",
        conversation_context=context,
    )
    assert decision.intent_category != "OUT_OF_SCOPE", (
        "Follow-up 'What about USA?' in a data context should NOT be OUT_OF_SCOPE"
    )


def test_usa_standalone_is_out_of_scope(router):
    """'Tell me about USA' with no data context is out of scope."""
    decision = router.route(
        message="Tell me about USA",
        dataset_id="ds-123",
        conversation_context=None,
    )
    assert decision.intent_category == "OUT_OF_SCOPE"
    assert decision.rejection_message == "Irrelevant topic."


# ── Group F: data qualifier makes USA relevant ─────────────────────────────
def test_usa_with_data_qualifier_is_data_query(router):
    """'Show companies in the USA in my dataset' is a valid data question."""
    decision = router.route(
        message="Show companies located in the USA in my dataset",
        dataset_id="ds-123",
    )
    assert decision.intent_category != "OUT_OF_SCOPE"


# ── Group G: Rejection message precision ───────────────────────────────────
def test_rejection_message_exact_text(router):
    """Out-of-scope rejection must be exactly 'Irrelevant topic.' with no extra text."""
    decision = router.route(message="Tell me about Modi", dataset_id="ds-123")
    assert decision.rejection_message == "Irrelevant topic."
