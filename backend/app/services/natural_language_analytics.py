"""Validated deterministic analytics; uncertainty is a result, never a guessed sum."""
from __future__ import annotations

import asyncio
import re
from dataclasses import asdict, dataclass, field
from typing import Any

import pandas as pd
from backend.app.services.data_retrieval_service import DataRetrievalService


@dataclass(frozen=True)
class AnalyticsRequest:
    operation: str
    metric: str | None = None
    dimension: str | None = None
    limit: int = 10
    dimensions: list[str] = field(default_factory=list)
    date_field: str | None = None
    date_granularity: str | None = None
    aggregation: str | None = None
    clarification_required: bool = False
    validation_errors: list[str] = field(default_factory=list)
    metric_options: list[str] = field(default_factory=list)
    dataset_id: str | None = None
    dataset_version: int | None = None
    filters: list[dict[str, Any]] = field(default_factory=list)
    sort: str | None = None


class NaturalLanguageAnalyticsService:
    def __init__(self, data_retrieval: DataRetrievalService | None = None) -> None:
        self._data_retrieval = data_retrieval

    @staticmethod
    def is_analytics_query(message: str) -> bool:
        # Forecasts/correlation/distribution must reach their existing agents.
        if re.search(r'\b(predict|forecast|correlation|correlate|distribution|histogram)\b', message, re.I):
            return False
        return bool(re.search(r'\b(total|sum|average|avg|mean|count|top|bottom|highest|lowest|trend|monthly|revenue|sales|profit|compare|which|chart|show)\b|\b(show|preview|describe|explain|summarize)\b.*\b(data|dataset|records|rows|columns)\b', message, re.I))

    @staticmethod
    def _mentions(message: str, column: str) -> bool:
        words = re.split(r'[ _-]+', column.lower())
        expression = r'[ _-]+'.join(re.escape(w) for w in words)
        return bool(re.search(r'(?<!\w)' + expression + r's?(?!\w)', message))

    def parse(
        self,
        message: str,
        columns: list[str],
        numeric_columns: list[str] | None = None,
        date_columns: list[str] | None = None,
        context: list[dict[str, str]] | None = None,
    ) -> AnalyticsRequest:
        q = message.lower().strip().rstrip('.?!')
        numeric = numeric_columns if numeric_columns is not None else columns
        dates = date_columns or []
        errors: list[str] = []

        if re.fullmatch(r'(?:please )?(?:show|preview)(?: me)?(?: the)? (?:data|dataset|records|rows)', q):
            return AnalyticsRequest('preview')
        if re.fullmatch(r'(?:please )?(?:describe|explain|summarize)(?: the)? (?:data|dataset)', q):
            return AnalyticsRequest('description')
        for pattern, intent in [(r'predict|forecast', 'forecast'), (r'correlat', 'correlation'), (r'distribution|histogram', 'distribution')]:
            if re.search(pattern, q):
                return AnalyticsRequest(intent, clarification_required=True, validation_errors=[f'Use the {intent} workflow; no aggregation was executed.'], metric_options=numeric)
        if re.search(r'\b(where|filter|only|excluding|except|last|next|this|between|for)\b|[<>]=?', q):
            errors.append('This request includes constraints that this deterministic workflow cannot safely resolve. Specify filters in the visualization workflow.')
        if re.search(r'average order value|\baov\b', q):
            errors.append('Average order value needs a verified order-grain definition and revenue mapping; no unrelated average was computed.')

        mentioned = [c for c in columns if self._mentions(q, c)]
        metrics = [c for c in mentioned if c in numeric and c not in dates and not re.search(r'(^|[_ -])(id|code|zip|phone|account)([_ -]|$)', c, re.I)]
        
        # Follow-up context extraction: if metric not mentioned, check context
        if not metrics and context:
            for past in reversed(context):
                past_content = past.get('content', '').lower()
                for num_col in numeric:
                    if self._mentions(past_content, num_col) and num_col not in dates:
                        metrics = [num_col]
                        break
                if metrics:
                    break

        metric = metrics[0] if len(metrics) == 1 else None
        dimensions = [c for c in mentioned if c not in metrics and c not in dates]

        # Follow-up context extraction: if dimension not mentioned, check context
        if not dimensions and context:
            for past in reversed(context):
                past_content = past.get('content', '').lower()
                for c in columns:
                    if c not in numeric and c not in dates and (self._mentions(past_content, c) or any(w in c.lower() for w in ('company', 'category', 'dept', 'region', 'segment', 'product', 'brand'))):
                        dimensions = [c]
                        break
                if dimensions:
                    break

        # Entity/category resolution for questions like "Which company has highest..."
        if not dimensions:
            for dim_candidate in columns:
                if dim_candidate not in numeric and dim_candidate not in dates:
                    cand_words = set(re.split(r'[^a-zA-Z0-9]+', dim_candidate.lower()))
                    if cand_words.intersection({'company', 'name', 'title', 'category', 'region', 'segment', 'product', 'brand', 'type', 'dept', 'department'}):
                        if any(re.search(r'\b' + re.escape(w) + r'\b', q) for w in ('company', 'which', 'who', 'highest', 'top', 'compare', 'second', 'rank')):
                            dimensions = [dim_candidate]
                            break

        if not dimensions:
            non_numeric = [c for c in columns if c not in numeric and c not in dates]
            if len(non_numeric) == 1 and any(re.search(r'\b' + re.escape(w) + r'\b', q) for w in ('company', 'which', 'who', 'highest', 'top', 'compare', 'second')):
                dimensions = [non_numeric[0]]

        limit = 10
        match = re.search(r'\b(?:top|bottom)\s+(\d+)\b', q)
        if match:
            limit = int(match.group(1))

        # Check for specific question types
        if re.search(r'\b(compare|second[- ]highest|second[- ]top)\b', q):
            operation, aggregation = 'top', 'sum'
            limit = 2
            if not dimensions:
                errors.append('Name the category to compare.')
        elif re.search(r'\b(which|who)\b.*\b(highest|top|maximum|best)\b|\bhighest\b.*\b(which|who|company|entity)\b', q):
            operation, aggregation = 'top', 'sum'
            limit = 1
            if not dimensions:
                errors.append('Name the category to rank.')
        elif re.search(r'\b(count|how many|number of)\b', q):
            operation, aggregation = 'count', 'count'
            if not re.search(r'\b(records|rows)\b', q):
                errors.append('Specify count records by a dimension; distinct entity counts require a verified identifier.')
        elif re.search(r'\b(average|avg|mean)\b', q):
            operation, aggregation = 'average', 'mean'
        elif re.search(r'\b(top|bottom)\b', q):
            operation = 'bottom' if re.search(r'\bbottom\b', q) else 'top'
            aggregation = 'sum'
            if not dimensions:
                errors.append('Name the category to rank.')
        elif re.search(r'\b(minimum|min|lowest)\b', q):
            operation, aggregation = 'min', 'min'
        elif re.search(r'\b(maximum|max|highest)\b', q):
            if dimensions:
                operation, aggregation = 'top', 'sum'
                limit = 1
            else:
                operation, aggregation = 'max', 'max'
        elif re.search(r'\b(trend|monthly|over time)\b', q):
            operation, aggregation = 'trend', 'sum'
        elif re.search(r'\b(total|sum)\b', q):
            operation, aggregation = 'sum', 'sum'
        elif re.search(r'\b(chart|visualize|plot|graph)\b', q):
            operation = 'top' if dimensions else 'preview'
            aggregation = 'sum'
            if re.search(r'\b(compare|comparison|second)\b', q):
                limit = 2
        elif metric and re.fullmatch(r'(?:total[ _-])?(revenue|sales|profit)(?:[ _-]amount)?', metric, re.I) and dimensions:
            operation, aggregation = 'sum', 'sum'
        else:
            operation, aggregation = 'ambiguous', None
            errors.append('Specify an operation such as total, average, or count records and name the metric.')

        if operation != 'count' and not metric:
            if re.search(r'\bprofit\b', q) and 'profit' not in columns:
                perf_metrics = [c for c in numeric if re.search(r'(roe|roce|margin|revenue|income|value)', c, re.I)]
                if perf_metrics:
                    errors.append(f"The dataset does not contain a 'profit' column. Available performance metrics are: {', '.join(perf_metrics)}.")
                else:
                    errors.append(f"The dataset does not contain a 'profit' column. Available numeric fields: {', '.join(numeric)}.")
            else:
                errors.append('Name exactly one numeric measure from the available fields; no default metric is selected.')

        if re.search(r'\bby\b', q) and not dimensions and operation not in {'top', 'bottom', 'trend'}:
            errors.append('The requested grouping dimension could not be resolved.')

        date_field = None
        if operation == 'trend':
            chosen = [c for c in dates if c in mentioned] or dates
            if len(chosen) != 1:
                errors.append('Name one unambiguous date column for the monthly trend.')
            else:
                date_field = chosen[0]

        if not 1 <= limit <= 100:
            errors.append('Ranking limit must be between 1 and 100.')

        return AnalyticsRequest(
            operation,
            metric,
            dimensions[0] if dimensions else None,
            limit,
            dimensions,
            date_field,
            'month' if operation == 'trend' else None,
            aggregation,
            bool(errors),
            errors,
            numeric,
            sort='ascending' if operation == 'bottom' else 'descending',
        )

    async def analyze(
        self,
        message: str,
        dataset_id: str | None = None,
        dataframe: pd.DataFrame | None = None,
        dataset_version: int | None = None,
        context: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        if dataframe is None:
            if not dataset_id or self._data_retrieval is None:
                return self._clarify(AnalyticsRequest('ambiguous', clarification_required=True, validation_errors=['Select a dataset before requesting an analysis.']))
            _, version, _, _, _ = await asyncio.to_thread(self._data_retrieval.discover, dataset_id, dataset_version)
            dataset_version = version.version_number
            # Pin the resolved version and disable automatic sampling for exact aggregates.
            dataframe, sampled = await asyncio.to_thread(self._data_retrieval.load_dataframe, dataset_id, version_number=dataset_version, sample_size=0)
            if sampled:
                return self._clarify(AnalyticsRequest('ambiguous', clarification_required=True, validation_errors=['Exact analytics cannot run on an undeclared sample.']))
        return await asyncio.to_thread(self._execute, message, dataframe, dataset_id, dataset_version, context)

    @staticmethod
    def _clarify(plan: AnalyticsRequest) -> dict[str, Any]:
        return {
            'status': 'clarification_required',
            'answer': ' '.join(plan.validation_errors),
            'data': [],
            'explanation': 'No analytical calculation was executed.',
            'actionable': [],
            'plan': asdict(plan),
            'kpis': {},
            'chart': None,
        }

    def _execute(
        self,
        message: str,
        dataframe: pd.DataFrame,
        dataset_id: str | None = None,
        dataset_version: int | None = None,
        context: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        numeric = dataframe.select_dtypes(include='number').columns.tolist()
        dates = [c for c in dataframe if pd.api.types.is_datetime64_any_dtype(dataframe[c]) or re.search(r'(^|[_ -])(date|month|time|year)([_ -]|$)', c, re.I)]
        plan = self.parse(message, list(dataframe.columns), numeric, dates, context)
        plan = AnalyticsRequest(**{**asdict(plan), 'dataset_id': dataset_id, 'dataset_version': dataset_version})
        if plan.clarification_required:
            return self._clarify(plan)

        kpis: dict[str, Any] = {}
        chart: dict[str, Any] | None = None
        actionable: list[str] = []

        if plan.operation == 'preview':
            rows = self._records(dataframe.head(100))
            answer = f'Showing {len(rows)} of {len(dataframe)} records.'
            explanation = 'Bounded snapshot of dataset observations.'
        elif plan.operation == 'description':
            rows = [{'column': str(c), 'type': str(dataframe[c].dtype), 'non_null_count': int(dataframe[c].count())} for c in dataframe]
            answer = f'The dataset contains {len(dataframe)} rows and {len(dataframe.columns)} columns.'
            explanation = 'Dataset structural profile and completeness summary.'
        else:
            work = dataframe.copy()
            groups = list(plan.dimensions)
            if plan.operation == 'trend':
                dates_parsed = pd.to_datetime(work[plan.date_field], errors='coerce')
                if dates_parsed.isna().any():
                    return self._clarify(AnalyticsRequest(**{**asdict(plan), 'clarification_required': True, 'validation_errors': ['The date field contains missing or invalid dates. Resolve them before trend analysis.']}))
                work[plan.date_field] = dates_parsed.dt.to_period('M').astype(str)
                groups = [plan.date_field, *groups]

            label = 'records' if plan.operation == 'count' else plan.metric
            if plan.operation == 'count':
                values = work.groupby(groups, dropna=False).size() if groups else len(work)
            else:
                if not work[plan.metric].dropna().map(lambda v: float('-inf') < v < float('inf')).all():
                    return self._clarify(AnalyticsRequest(**{**asdict(plan), 'clarification_required': True, 'validation_errors': ['The metric contains non-finite values.']}))
                values = work.groupby(groups, dropna=False)[plan.metric] if groups else work[plan.metric]
                values = values.sum(min_count=1) if plan.aggregation == 'sum' else getattr(values, plan.aggregation)()

            if groups:
                if plan.operation in {'top', 'bottom'}:
                    values = values.sort_values(ascending=plan.operation == 'bottom').head(plan.limit)
                elif plan.operation == 'trend':
                    values = values.sort_index()
                else:
                    values = values.sort_values(ascending=False)
                rows = self._records(values.rename(label).reset_index())
            else:
                rows = [{label: None if pd.isna(values) else self._number(values)}]

            agg_name = plan.aggregation.title() if plan.aggregation else "Calculated"
            answer = f"{agg_name} {label}" + (f" by {', '.join(groups)}" if groups else '') + ': ' + '; '.join(', '.join(f'{k} = {v}' for k, v in row.items()) for row in rows[:10]) + '.'
            explanation = f'Executed validated {plan.operation} against the selected dataset version. Null grouping keys are retained.'

            # Compute population KPIs for the analyzed metric
            if plan.metric and plan.metric in dataframe.columns and pd.api.types.is_numeric_dtype(dataframe[plan.metric]):
                metric_series = dataframe[plan.metric].dropna()
                if not metric_series.empty:
                    kpis = {
                        "total": self._number(metric_series.sum()),
                        "mean": round(float(metric_series.mean()), 2),
                        "median": round(float(metric_series.median()), 2),
                        "min": self._number(metric_series.min()),
                        "max": self._number(metric_series.max()),
                        "count": int(metric_series.count()),
                    }

            # Generate structured chart points
            if groups and rows and len(rows) <= 50:
                dim_col = groups[0]
                chart_points = []
                for r in rows:
                    if dim_col in r and label in r and r[label] is not None:
                        try:
                            chart_points.append({"label": str(r[dim_col]), "value": float(r[label])})
                        except (ValueError, TypeError):
                            pass
                if chart_points:
                    chart = {
                        "chart_type": "bar",
                        "x_field": dim_col,
                        "y_field": label,
                        "points": chart_points,
                        "chart_label": f"{agg_name} of {label}",
                    }

            # Generate actionable recommendations
            if plan.metric:
                actionable.append(f"Explore distributions or relationships for '{plan.metric}' in Visualization Studio.")
            if groups:
                actionable.append(f"Generate an Executive Report covering category-level performance across {', '.join(groups)}.")

        return {
            'status': 'complete',
            'answer': answer,
            'data': rows,
            'explanation': explanation,
            'actionable': actionable,
            'plan': asdict(plan),
            'kpis': kpis,
            'chart': chart,
        }

    @staticmethod
    def _records(df: pd.DataFrame) -> list[dict[str, Any]]:
        # JSON round-trip also safely represents timestamps and missing values.
        import json
        return json.loads(df.to_json(orient='records', date_format='iso'))

    @staticmethod
    def _number(value: Any) -> int | float:
        value = float(value)
        return int(value) if value.is_integer() else value


def get_natural_language_analytics_service() -> NaturalLanguageAnalyticsService:
    return NaturalLanguageAnalyticsService()
