"""Curated question contracts for the four user-approved saved spreadsheets.

Labels follow the meaning of each question, never classifier output. Expected
numbers are computed only by the independent reference oracle during freezing.
"""

SOURCES = {
    "cashflow": {"sheet": "Cash Flow", "header_row": 1,
        "columns": ["id", "company_id", "year", "operating_activity", "investing_activity", "financing_activity", "net_cash_flow"],
        "metrics": ["net_cash_flow", "operating_activity", "financing_activity"]},
    "profitandloss": {"sheet": "Profit & Loss", "header_row": 1,
        "columns": ["id", "company_id", "year", "sales", "expenses", "operating_profit", "opm_percentage", "other_income", "interest", "depreciation", "profit_before_tax", "tax_percentage", "net_profit", "eps", "dividend_payout"],
        "metrics": ["sales", "net_profit", "operating_profit"]},
    "balancesheet": {"sheet": "Balance Sheet", "header_row": 1,
        "columns": ["id", "company_id", "year", "equity_capital", "reserves", "borrowings", "other_liabilities", "total_liabilities", "fixed_assets", "cwip", "investments", "other_asset", "total_assets"],
        "metrics": ["total_assets", "borrowings", "equity_capital"]},
    "prosandcons": {"sheet": "Pros & Cons", "header_row": 1,
        "columns": ["id", "company_id", "pros", "cons"], "metrics": []},
}

# These test the canonical intent API, which is distinct from the chat analytics bypass.
INTENT_QUESTIONS = [
    ("dataset_overview", "prosandcons", "Describe the dataset schema", "Summarize the pros and cons dataset"),
    ("eda_analysis", "profitandloss", "Perform exploratory data analysis on sales", "Explore the data on net_profit"),
    ("trend_analysis", "cashflow", "Show net_cash_flow trends over time", "Analyze historical operating_activity trends"),
    ("comparison_analysis", "balancesheet", "Compare borrowings with reserves", "Comparison between fixed_assets and investments"),
    ("distribution_analysis", "profitandloss", "Show the distribution of sales", "Histogram of operating_profit"),
    ("correlation_analysis", "balancesheet", "Correlation between total_assets and borrowings", "Is there a correlation between reserves and fixed_assets?"),
    ("ranking_analysis", "cashflow", "Top 5 company_id by net_cash_flow", "Bottom 5 company_id by operating_activity"),
    ("forecasting", "profitandloss", "Forecast sales next quarter", "Predict net_profit for next year"),
    ("anomaly_detection", "cashflow", "Find outliers in financing_activity", "Detect anomalies in net_cash_flow"),
    ("dashboard_generation", "balancesheet", "Create dashboard with total_assets and borrowings", "Build a dashboard for equity_capital"),
    ("report_generation", "profitandloss", "Generate report on sales and expenses", "Create a report about net_profit"),
    ("recommendation_generation", "cashflow", "Give me recommendations about net_cash_flow", "Suggest strategies to improve operating_activity"),
    ("what_if_analysis", "profitandloss", "What if we increase expenses by 10 percent?", "Simulate the impact of lower sales"),
    ("sql_query", "balancesheet", "Write a SQL query for total_assets by company_id", "SELECT company_id, borrowings FROM balancesheet"),
    ("rag_query", "prosandcons", "Search documentation explaining the pros and cons fields", "Look up in docs the company_id definition"),
    ("data_quality", "cashflow", "Find duplicate records by id", "Check data quality for missing financing_activity values"),
    ("unknown", "prosandcons", "Hello", "Tell me a bedtime story about a dragon"),
]


def question_contracts() -> list[dict]:
    cases = []
    for source, spec in SOURCES.items():
        for metric in spec["metrics"]:
            for operation, phrase in (("sum", "total"), ("average", "average"), ("min", "minimum"), ("max", "maximum")):
                cases.append(dict(id=f"{source}-{metric}-{operation}", kind="analytics", source=source,
                    question=f"show {phrase} {metric}", expected_status="complete", operation=operation,
                    metric=metric, dimension=None))
        cases.append(dict(id=f"{source}-count", kind="analytics", source=source,
            question="count records", expected_status="complete", operation="count", metric=None, dimension=None))
        cases.append(dict(id=f"{source}-clarification", kind="analytics", source=source,
            question="show total", expected_status="clarification_required", operation="sum", metric=None, dimension=None))
        if spec["metrics"]:
            metric = spec["metrics"][0]
            for operation, phrase in (("sum", "total"), ("top", "top 5")):
                cases.append(dict(id=f"{source}-group-{operation}", kind="analytics", source=source,
                    question=f"show {phrase} {metric} by company_id", expected_status="complete",
                    operation=operation, metric=metric, dimension="company_id"))
    for label, source, *questions in INTENT_QUESTIONS:
        for index, question in enumerate(questions, 1):
            cases.append(dict(id=f"intent-{label}-{index}", kind="intent", source=source,
                              question=question, expected_intent=label))
    return cases
