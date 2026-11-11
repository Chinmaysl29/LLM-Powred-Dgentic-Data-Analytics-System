"""Schema-only candidate constraints and reviewed, disjoint evaluation cases."""
from dataclasses import replace
import re
import pandas as pd

from backend.app.learning.column_ranker import ColumnRanker, question_hash
from backend.app.learning.memory_contract import digest

MISSING = 'Name exactly one numeric measure from the available fields; no default metric is selected.'
OPERATIONS = {'sum', 'average', 'min', 'max', 'top', 'bottom', 'trend'}


def schema_fields(schema: dict):
    if not isinstance(schema, dict) or set(schema) != {'columns', 'dtypes'}:
        raise ValueError('Invalid resolver schema')
    columns, dtypes = schema['columns'], schema['dtypes']
    if (not isinstance(columns, list) or not 1 <= len(columns) <= 200
            or any(not isinstance(c, str) or not 1 <= len(c) <= 256 for c in columns)
            or len(set(columns)) != len(columns) or set(dtypes) != set(columns)
            or any(not isinstance(t, str) or len(t) > 100 for t in dtypes.values())):
        raise ValueError('Invalid resolver schema fields')
    numeric = [c for c in columns if pd.api.types.is_numeric_dtype(dtypes[c]) and not pd.api.types.is_bool_dtype(dtypes[c])]
    dates = [c for c in columns if pd.api.types.is_datetime64_any_dtype(dtypes[c]) or re.search(r'(^|[_ -])(date|month|time|year)([_ -]|$)', c, re.I)]
    candidates = [c for c in numeric if c not in dates and not re.search(r'(^|[_ -])(id|code|zip|phone|account)([_ -]|$)', c, re.I)]
    return columns, numeric, dates, candidates


def eligible(question, schema, plan, context=None) -> bool:
    from backend.app.services.natural_language_analytics import NaturalLanguageAnalyticsService
    _, numeric, _, candidates = schema_fields(schema)
    return bool(candidates and not context and plan.operation in OPERATIONS and plan.metric is None
        and plan.clarification_required and plan.validation_errors == [MISSING]
        and not any(NaturalLanguageAnalyticsService._mentions(question.lower(), c) for c in numeric))


def apply_choice(plan, choice, candidates):
    if choice is None:
        return plan
    if choice not in candidates or plan.metric is not None or plan.validation_errors != [MISSING]:
        raise ValueError('Unsafe resolver choice')
    return replace(plan, metric=choice, clarification_required=False, validation_errors=[])


def manifest(value: dict) -> dict:
    if not isinstance(value, dict) or set(value) != {'format', 'schema', 'cases'} or type(value['format']) is not int or value['format'] != 1:
        raise ValueError('Invalid reviewed manifest')
    _, _, _, candidates = schema_fields(value['schema'])
    cases = value['cases']
    if not isinstance(cases, list) or not 40 <= len(cases) <= 500:
        raise ValueError('Require at least 10 training and 30 held-out cases')
    questions, groups = set(), {'train': set(), 'golden': set()}
    counts = {'train': 0, 'golden': 0}
    for row in cases:
        if (not isinstance(row, dict) or set(row) != {'question', 'expected', 'split', 'group'}
                or row['split'] not in counts or not isinstance(row['question'], str)
                or not 1 <= len(row['question']) <= 2000 or not isinstance(row['group'], str)
                or not 1 <= len(row['group']) <= 100 or row['expected'] not in [None, *candidates]):
            raise ValueError('Invalid reviewed example')
        hashed = question_hash(row['question'])
        if hashed in questions:
            raise ValueError('Duplicate/leaked question')
        questions.add(hashed)
        groups[row['split']].add(row['group'])
        counts[row['split']] += 1
    if counts['train'] < 10 or counts['golden'] < 30 or groups['train'] & groups['golden']:
        raise ValueError('Insufficient or overlapping splits')
    if sum(row['expected'] is None for row in cases if row['split'] == 'golden') < 5:
        raise ValueError('Held-out evaluation requires five abstention cases')
    return value


def train(value: dict) -> ColumnRanker:
    value = manifest(value)
    _, _, _, candidates = schema_fields(value['schema'])
    model = ColumnRanker()
    for _ in range(20):
        for row in value['cases']:
            if row['split'] == 'train':
                model.update(row['question'], candidates, value['schema']['dtypes'], row['expected'])
    return ColumnRanker(model.snapshot(), sorted(model.vocabulary))


def evaluate(value: dict, model: ColumnRanker, current: ColumnRanker | None = None) -> dict:
    from backend.app.services.natural_language_analytics import NaturalLanguageAnalyticsService
    value = manifest(value)
    schema = value['schema']
    columns, numeric, dates, candidates = schema_fields(schema)
    parser = NaturalLanguageAnalyticsService()
    results = []
    for row in value['cases']:
        if row['split'] != 'golden':
            continue
        plan = parser.parse(row['question'], columns, numeric, dates)
        baseline = None if plan.clarification_required else plan.metric
        candidate, live = baseline, baseline
        if eligible(row['question'], schema, plan):
            candidate = model.predict(row['question'], candidates, schema['dtypes'])[0]
            if current:
                live = current.predict(row['question'], candidates, schema['dtypes'])[0]
        results.append({'question_hash': question_hash(row['question']), 'correct': candidate == row['expected'],
            'baseline_correct': baseline == row['expected'], 'live_correct': live == row['expected']})
    correct = sum(r['correct'] for r in results)
    baseline = sum(r['baseline_correct'] for r in results)
    live = sum(r['live_correct'] for r in results)
    return {'manifest_digest': digest(value), 'cases': len(results), 'correct': correct,
        'baseline_correct': baseline, 'live_correct': live,
        'passed': correct == len(results) and correct > max(baseline, live), 'results': results}
