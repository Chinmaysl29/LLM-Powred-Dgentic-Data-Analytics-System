"""Code-only descriptive executor and independent validators.

No SQL, eval, generated Python, provider calls, fitted preprocessing or prompt
instructions are accepted. Unsupported semantics return insufficient evidence.
"""
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import importlib.metadata
import json
import math
from pathlib import Path
import re
import time
from typing import Callable

import pandas as pd

from backend.app.schemas.learning import (Budget, DatasetRef, Metric, Operation, TaskSpec,
                                          TransformationPlan, ValidationResult)
from backend.app.services.natural_language_analytics import NaturalLanguageAnalyticsService

ENGINE_VERSION = 'deterministic-supervisor-v1'
DECIMAL_PATTERN = re.compile(r'^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$')


def load_preserved_frame(path, file_type):
    if path.stat().st_size > 50_000_000:
        raise ValueError('DATASET_BYTE_LIMIT_EXCEEDED')
    if file_type in {'csv', 'tsv'}:
        frame = pd.read_csv(path, sep='\t' if file_type == 'tsv' else ',', dtype=object,
                            keep_default_na=False, na_values=[''], nrows=500_001)
    elif file_type in {'xlsx', 'xls'}:
        frame = pd.read_excel(path, dtype=object, keep_default_na=False, na_values=[''], nrows=500_001)
    elif file_type == 'parquet':
        frame = pd.read_parquet(path)
    elif file_type == 'json':
        payload = json.loads(path.read_text(encoding='utf-8'), parse_float=Decimal)
        if isinstance(payload, dict):
            payload = payload.get('records', payload.get('data'))
        if not isinstance(payload, list) or not all(isinstance(r, dict) for r in payload):
            raise ValueError('EXPLICIT_TABULAR_RECORDS_REQUIRED')
        frame = pd.DataFrame(payload, dtype=object)
    else:
        raise ValueError('SUPERVISOR_TABULAR_FORMAT_UNSUPPORTED')
    if len(frame) > 500_000 or len(frame.columns) > 200 or not frame.columns.is_unique:
        raise ValueError('SUPERVISOR_DATASET_SHAPE_UNSUPPORTED')
    return frame


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False, default=str).encode()).hexdigest()


_service_dir = Path(__file__).resolve().parent
# Captured once at process import. Restart processes when changing code; bundles
# cannot release against different policy code or computation dependencies.
RUNTIME_IDENTITY = {
    'policy_hash': digest({str(p.relative_to(_service_dir.parent)): sha256(p.read_bytes()).hexdigest() for p in
        [_service_dir/name for name in ('learning_engine.py','learning_supervisor.py','learning_evaluation.py','analysis_run_service.py',
            'adaptive_skills.py','adaptive_selector.py','adaptive_routing.py','adaptive_service.py','adaptive_jobs.py')]
        + [_service_dir.parent/'schemas'/name for name in ('learning.py','adaptive.py')]}),
    'dependencies': {name: importlib.metadata.version(name) for name in ('pandas','pydantic','SQLAlchemy')},
}


def schema_hash(frame):
    return digest([(str(c), str(frame[c].dtype)) for c in frame])


def frame_hash(frame):
    return sha256(pd.util.hash_pandas_object(frame, index=True).values.tobytes()).hexdigest()


def scrub(text):
    """Feedback is never a source of instructions or raw records for lessons."""
    text = re.sub(r'(?i)(bearer\s+\S+|(?:sk|gsk)[-_][A-Za-z0-9_-]+|(?:password|token|secret|api.?key)\s*[:=]\s*\S+)', '[redacted]', text)
    text = re.sub(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}', '[redacted email]', text)
    return text[:2000]


def check(name, passed, invariant, severity='error', limitations=None):
    return ValidationResult(validator=name, version='1', invariant=invariant, severity=severity,
                            outcome='unknown' if passed is None else ('pass' if passed else 'fail'),
                            evidence_refs=[f'check:{name}'], limitations=limitations or []).model_dump(mode='json')


class ValidatorRegistry:
    def __init__(self):
        self.validators: dict[str, Callable] = {}

    def register(self, name, validator):
        if name in self.validators:
            raise ValueError('Validator version already registered')
        self.validators[name] = validator

    def validate(self, context):
        return [validator(context) for validator in self.validators.values()]


def validate_join(left, right, keys, cardinality='many_to_one'):
    """Preflight only; this release does not execute joins."""
    valid = all(k in left and k in right for k in keys)
    if valid:
        valid = not right.duplicated(keys).any() if cardinality == 'many_to_one' else False
    return check('join_cardinality', bool(valid), 'Right keys unique before a many-to-one join; no double counting.')


def validate_training_split(train_ids, validation_ids, train_end, validation_start, fitted_ids, feature_available=True):
    valid = not set(train_ids).intersection(validation_ids) and set(fitted_ids) <= set(train_ids)
    valid = valid and train_end < validation_start and feature_available
    return check('prediction_leakage', bool(valid), 'Time boundary, entity separation, training-only fitting and feature availability.')


def profile(frame):
    # No customer cell values or outlier rows go into lessons/profile evidence.
    return {
        'row_count': len(frame), 'schema_hash': schema_hash(frame), 'source_hash': frame_hash(frame),
        'columns': {str(c): {'dtype': str(frame[c].dtype), 'missing': int(frame[c].isna().sum()),
                            'unique': int(frame[c].nunique(dropna=False))} for c in frame},
        'duplicate_looking_rows': int(frame.duplicated().sum()),
        'policy': 'No rows dropped, imputed, deduplicated or clipped. Extreme values are observations.',
        'limitations': ['Uniqueness is not a business record-key definition.', 'Outliers are not established errors.'],
    }


def infer_task(workspace, dataset, version, query, frame):
    numeric = frame.select_dtypes(include='number').columns.tolist()
    dates = [str(c) for c in frame if pd.api.types.is_datetime64_any_dtype(frame[c]) or re.search(r'(^|[_ -])(date|month|time|year)([_ -]|$)', str(c), re.I)]
    parsed = NaturalLanguageAnalyticsService().parse(query, list(frame.columns), numeric, dates)
    # Explicit object-number columns can be interpreted but require lossless conversion.
    if parsed.metric is None:
        candidates = [str(c) for c in frame if NaturalLanguageAnalyticsService._mentions(query.lower(), str(c))
                      and all(DECIMAL_PATTERN.fullmatch(str(v)) for v in frame[c].dropna())
                      and len(frame[c].dropna()) > 0]
        if len(candidates) == 1:
            parsed = NaturalLanguageAnalyticsService().parse(query, list(frame.columns), numeric + candidates, dates)
    ambiguity = list(parsed.validation_errors)
    if parsed.operation not in {'sum', 'average', 'min', 'max', 'count'}:
        ambiguity.append('Use an explicit supported aggregate task contract; ranking, preview and trend semantics need a separate contract.')
    column = parsed.metric or ('__records__' if parsed.operation == 'count' else '__unresolved__')
    return TaskSpec(workspace_id=workspace, objective=query, task_type='descriptive',
                    datasets=[DatasetRef(dataset_id=dataset, version=version)],
                    metrics=[Metric(column=column, aggregation=parsed.aggregation or 'sum', missing='reject', definition_ref=None)],
                    dimensions=parsed.dimensions, grain='one source record; business key not asserted', filters=[], date_range=None,
                    timezone='UTC', units='source units (not independently confirmed)', currency=None, output='table',
                    definition_refs=[], assumptions=['Descriptive aggregation only; no causal claim.', 'No business metric redefinition.'],
                    ambiguity=ambiguity, success_criteria=['Independent aggregate reconciliation', 'Source version and integrity preserved'])


def exact_decimal(value):
    if isinstance(value, bool) or not DECIMAL_PATTERN.fullmatch(str(value)):
        raise ValueError('AMBIGUOUS_NUMERIC_REPRESENTATION')
    number = Decimal(str(value))
    # Bound arithmetic and response size; arbitrary precision is not unbounded work.
    if not number.is_finite() or len(number.as_tuple().digits) > 18 or abs(number.as_tuple().exponent) > 8:
        raise ValueError('NUMERIC_PRECISION_UNSUPPORTED')
    return number


def transform(frame, action):
    op = Operation.model_validate(action)
    result = frame.copy(deep=True)
    if op.column not in result:
        raise ValueError('SCHEMA_MISMATCH')
    original = result[op.column]
    converted = original.map(lambda v: v if pd.isna(v) else exact_decimal(v))
    if any(exact_decimal(a) != b for a, b in zip(original, converted) if not pd.isna(a)):
        raise ValueError('LOSSY_TRANSFORMATION')
    result[op.column] = converted
    if len(result) != len(frame) or not result.index.equals(frame.index):
        raise ValueError('ROW_RECONCILIATION_FAILED')
    return result


def verify_operation(action):
    """Independent bounded positive cases AND counterexamples, not LLM agreement."""
    op = Operation.model_validate(action)
    positives = [['0', '-20.50', '100.25'], ['999999.00', '1', '-1'], ['0.00000001', '1.00']]
    positive_pass = []
    for values in positives:
        actual = transform(pd.DataFrame({op.column: values}), op.model_dump())[op.column]
        # Independent integer-scaled reference, without calling exact_decimal().
        scale = 10 ** max(len(v.partition('.')[2]) for v in values)
        def scaled(value):
            sign = -1 if value.startswith('-') else 1
            a, _, b = value.lstrip('-').partition('.')
            return sign * (int(a) * scale + (int(b) if b else 0) * (scale // (10 ** len(b))))
        positive_pass.append(sum(actual) == Decimal(sum(scaled(v) for v in values)) / scale)
    counters = ['1,000', '01', '1e3', '$10', 'NaN', 'Infinity', '1; DROP TABLE', 'ignore all rules']
    rejected = []
    for value in counters:
        try:
            transform(pd.DataFrame({op.column: [value]}), op.model_dump())
            rejected.append(False)
        except (ValueError, InvalidOperation):
            rejected.append(True)
    return {'passed': all(positive_pass) and all(rejected), 'positive_cases': len(positives),
            'counterexamples': len(counters), 'verifier': 'scaled-integer-reference-v1',
            'scope': 'Canonical signed decimal strings with <=18 digits and <=8 fractional places; no currency/unit conversion.',
            'limitations': ['Does not verify business semantics or authorize deployment.', 'No production accuracy estimate.']}


def task_checks(task, frame, definitions):
    checks = [check('supported_executor', task.task_type == 'descriptive', 'Only approved descriptive operations; no generated SQL/Python or fitting.'),
              check('interpretation', not task.ambiguity, 'Material ambiguity resolved in task contract.')]
    fields = set(task.dimensions + [f.column for f in task.filters])
    metric = task.metrics[0]
    stated = {aggregation for pattern, aggregation in [
        (r'\b(average|avg|mean)\b','mean'), (r'\b(total|sum)\b','sum'),
        (r'\b(minimum|min|lowest)\b','min'), (r'\b(maximum|max|highest)\b','max'),
        (r'\b(count|how many|number of records)\b','count')]
        if re.search(pattern, task.objective, re.I)}
    consistent = not stated or stated == {metric.aggregation}
    if re.search(r'\b(where|only|excluding|except|between|last|next|since|before|after)\b',task.objective,re.I) and not (task.filters or task.date_range):
        consistent = False
    checks.append(check('semantic_alignment', consistent, 'Stated aggregation and material constraints agree with the explicit task contract.'))
    if metric.column != '__records__':
        fields.add(metric.column)
    if task.date_range:
        fields.add(task.date_range.column)
    checks.append(check('schema', fields <= set(frame.columns), 'Every requested field exists in the pinned schema.'))
    checks.append(check('output_field_names', 'value' not in task.dimensions, 'Grouping names cannot collide with the reserved numeric result field value.'))
    checks.append(check('record_count', metric.column != '__records__' or metric.aggregation == 'count', 'The records sentinel is used only for record counts.'))
    checks.append(check('dimension_names', len(set(task.dimensions)) == len(task.dimensions), 'Grouping dimensions are unique.'))
    filter_types_ok = True
    for f in task.filters:
        if f.column in frame:
            sample = frame[f.column].dropna()
            values = f.value if isinstance(f.value, list) else [f.value]
            if len(sample) and all(isinstance(v, str) for v in sample):
                filter_types_ok = filter_types_ok and all(isinstance(v, str) for v in values)
            filter_types_ok = filter_types_ok and (isinstance(f.value, list) if f.operator in {'in','not_in'} else not isinstance(f.value, list))
    checks.append(check('filter_literal_types', bool(filter_types_ok), 'Filter values use explicit source-compatible scalar/list representations.'))
    refs = set(task.definition_refs)
    if metric.definition_ref:
        refs.add(metric.definition_ref)
    valid = refs <= set(definitions)
    for ref in refs & set(definitions):
        definition = definitions[ref]
        expected = definition['metric']
        valid = valid and all(getattr(metric, key) == expected[key] for key in ('column', 'aggregation', 'missing'))
        valid = valid and task.units == definition['units'] and task.currency == definition['currency']
        valid = valid and all(f in [v.model_dump(mode='json') for v in task.filters] for f in definition['filters'])
    # Business words need an explicit trusted definition even if a similarly named column exists.
    if re.search(r'\b(revenue|profit|churn|sales)\b', task.objective, re.I) and not metric.definition_ref:
        valid = False
    checks.append(check('business_definition', bool(valid), 'Selected effective business definitions match metric, filters, units and currency.',
                        limitations=['Definitions are authorized domain assertions; examples are not universal ground truth.']))
    return checks


def filtered_frame(task, frame):
    work = frame.copy(deep=True)
    for f in task.filters:
        values = f.value if isinstance(f.value, list) else [f.value]
        mask = work[f.column].isin(values)
        if f.operator in {'ne', 'not_in'}:
            mask = ~mask
        work = work.loc[mask]
    if task.date_range:
        d = task.date_range
        dates = pd.to_datetime(work[d.column], format=d.format, errors='raise', exact=True)
        if dates.isna().any():
            raise ValueError('DATE_MISSING')
        if dates.dt.tz is None:
            dates = dates.dt.tz_localize(task.timezone, ambiguous='raise', nonexistent='raise')
        dates = dates.dt.tz_convert('UTC')
        work = work.loc[(dates >= d.start) & (dates < d.end)]
    return work


def as_number(value):
    if value is None:
        return None
    decimal = Decimal(str(value))
    if not decimal.is_finite():
        raise ValueError('NONFINITE_RESULT')
    if decimal == decimal.to_integral() and abs(decimal) <= 2**53:
        return int(decimal)
    # Decimal strings preserve precision across JSON/TypeScript clients.
    return format(decimal, 'f')


def aggregate(task, work):
    metric = task.metrics[0]
    groups = task.dimensions
    col = metric.column
    data = work.groupby(groups, dropna=False, sort=True) if groups else [((), work)]
    rows = []
    for key, group in data:
        keys = key if isinstance(key, tuple) else (key,)
        row = {name: None if pd.isna(value) else str(value) for name, value in zip(groups, keys)}
        if metric.aggregation == 'count':
            result = len(group) if col == '__records__' else int(group[col].count())
        else:
            values = group[col].dropna().map(lambda v: Decimal(str(v)))
            if not len(values):
                result = None
            elif metric.aggregation == 'sum':
                result = values.sum()
            elif metric.aggregation == 'mean':
                result = values.sum() / len(values)
            elif metric.aggregation == 'min':
                result = values.min()
            else:
                result = values.max()
        row['value'] = as_number(result)
        rows.append(row)
    return rows


def reference_rows(task, work):
    """Independent row iterator; no pandas groupby/aggregation used by executor."""
    buckets = defaultdict(list)
    m = task.metrics[0]
    for record in work.to_dict(orient='records'):
        key = tuple(None if pd.isna(record[d]) else str(record[d]) for d in task.dimensions)
        value = 1 if m.column == '__records__' else record[m.column]
        buckets[key].append(None if pd.isna(value) else Decimal(str(value)))
    if not task.dimensions and not buckets:
        buckets[()] = []
    result = []
    for key, values in buckets.items():
        values = [v for v in values if v is not None]
        if m.aggregation == 'count':
            number = len(values)
        elif not values:
            number = None
        elif m.aggregation in {'sum', 'mean'}:
            number = sum(values, Decimal(0))
            if m.aggregation == 'mean':
                number /= len(values)
        else:
            number = (min if m.aggregation == 'min' else max)(values)
        result.append({**dict(zip(task.dimensions, key)), 'value': as_number(number)})
    return result


def same_rows(left, right):
    def comparable(row):
        result = dict(row)
        if result.get('value') is not None:
            result['value'] = str(Decimal(str(result['value'])).normalize())
        return digest(result)
    return sorted(comparable(r) for r in left) == sorted(comparable(r) for r in right)


def answer_object(task, rows, source_hash):
    claims = [{'text': f"{task.metrics[0].aggregation} = {r['value']}", 'value': r['value'],
               'evidence_ref': f'result.rows/{i}/value'} for i, r in enumerate(rows)]
    chart = [{'label': ' / '.join(str(r[d]) for d in task.dimensions) or task.metrics[0].column,
              'value': r['value'], 'evidence_ref': f'result.rows/{i}/value'} for i, r in enumerate(rows)]
    return {'rows': rows, 'claims': claims, 'chart': chart, 'source_hash': source_hash,
            'task_hash': digest(task.model_dump(mode='json')), 'version': ENGINE_VERSION}


def validate_answer(context):
    answer, task, work = context['answer'], context['task'], context['work']
    valid = same_rows(answer['rows'], reference_rows(task, work))
    return check('numeric_reconciliation', valid, 'Independent row-iteration aggregate matches every output group.')


def validate_claims(context):
    answer = context['answer']
    rows = answer['rows']
    expected = [r['value'] for r in rows]
    valid = [c['value'] for c in answer['claims']] == expected and [c['value'] for c in answer['chart']] == expected
    valid = valid and all(c['evidence_ref'] == f'result.rows/{i}/value' and c['text'] == f"{context['task'].metrics[0].aggregation} = {c['value']}" for i, c in enumerate(answer['claims']))
    valid = valid and all(c['evidence_ref'] == f'result.rows/{i}/value' and c['label'] == (' / '.join(str(rows[i][d]) for d in context['task'].dimensions) or context['task'].metrics[0].column) for i, c in enumerate(answer['chart']))
    return check('chart_narrative', valid, 'Numeric claims and chart values reference the same computed result cells.')


def validate_selection(context):
    """Independent boolean-mask reference from raw rows, including explicit date bounds."""
    task, raw, work = context['task'], context['raw'], context['work']
    expected = []
    try:
        for index, row in raw.iterrows():
            include = True
            for f in task.filters:
                values = f.value if isinstance(f.value, list) else [f.value]
                present = False if pd.isna(row[f.column]) else row[f.column] in values
                include = include and (not present if f.operator in {'ne','not_in'} else present)
            if include and task.date_range:
                bounds = task.date_range
                value = row[bounds.column]
                date = value if isinstance(value, datetime) else datetime.strptime(str(value), bounds.format)
                timestamp = pd.Timestamp(date)
                if timestamp.tzinfo is None:
                    timestamp = timestamp.tz_localize(task.timezone, ambiguous='raise', nonexistent='raise')
                include = bounds.start <= timestamp.to_pydatetime() < bounds.end
            if include:
                expected.append(index)
        passed = expected == work.index.tolist()
    except (ValueError, TypeError, KeyError):
        passed = False
    return check('date_filter_row_reconciliation', passed, 'Independent row selection matches every explicit filter and half-open date boundary.')


REGISTRY = ValidatorRegistry()
REGISTRY.register('numeric_reconciliation', validate_answer)
REGISTRY.register('chart_narrative', validate_claims)
REGISTRY.register('date_filter_row_reconciliation', validate_selection)
REGISTRY.register('raw_integrity', lambda c: check('raw_integrity', frame_hash(c['raw']) == c['raw_hash'], 'Immutable source hash unchanged.'))
REGISTRY.register('grain', lambda c: check('grain', len(c['answer']['rows']) == len(reference_rows(c['task'], c['work'])), 'Exactly one result per declared group; no implicit join or deduplication.'))


def execute(task, frame, definitions, budget=None, lessons=None, repairs_used=0, previous_actions=None,
            deadline=None, on_repair=None, replay_reservations=None, repair_router=None):
    """One bounded current-run loop. Lessons suggest only a known, revalidated action."""
    start = time.perf_counter()
    budget = budget or Budget()
    deadline = deadline or time.monotonic() + budget.deadline_seconds
    raw_hash = frame_hash(frame)
    checks = task_checks(task, frame, definitions)
    findings = profile(frame)
    actions = list(previous_actions or [])
    applied = []
    repair_evidence = []
    plan = TransformationPlan(operations=[], input_versions=task.datasets,
        preconditions=['Authenticated workspace and pinned dataset version', 'Resolved metric semantics'],
        expected_effects=['Descriptive aggregate; immutable source'], validation_rules=list(REGISTRY.validators),
        lineage=[f'dataset:{d.dataset_id}@{d.version}' for d in task.datasets], training_only_fit=False)

    def outcome(status, error=None, answer=None):
        return {'status': status, 'error_code': error, 'validations': checks, 'profile': findings,
                'task': task.model_dump(mode='json'), 'plan': plan.model_dump(mode='json'), 'answer': answer,
                'result_hash': digest(answer) if answer else None, 'repairs': repairs_used, 'actions': actions,
                'applied_lessons': applied, 'latency_ms': (time.perf_counter() - start) * 1000,
                'repair_attempts': repair_evidence,
                'runtime_identity': RUNTIME_IDENTITY,
                'usage': {'provider': 'none', 'calls': 0, 'input_tokens': 0, 'output_tokens': 0, 'cost_usd': 0},
                'numeric_confidence': None, 'confidence_reason': 'Numeric confidence unavailable: no independently labeled calibration set.',
                'limitations': ['Checks cover declared descriptive semantics and numeric reconciliation only.',
                                'Decimal arithmetic uses 28 significant digits; nonterminating means are rounded at that precision.',
                                'No causal, predictive or universal correctness claim.']}

    if any(c['outcome'] != 'pass' for c in checks if c['severity'] == 'error'):
        return outcome('insufficient_evidence', 'TASK_CONTRACT_UNRESOLVED')
    if time.monotonic() >= deadline:
        return outcome('insufficient_evidence', 'DEADLINE_EXHAUSTED')
    if len(frame) > 500_000:
        return outcome('insufficient_evidence', 'DATASET_LIMIT_EXCEEDED')
    try:
        work = filtered_frame(task, frame)
    except (ValueError, TypeError, KeyError, OverflowError):
        checks.append(check('date_filter', False, 'Explicit format, timezone and half-open date range must be valid.'))
        return outcome('insufficient_evidence', 'DATE_OR_FILTER_INVALID')
    checks.append(check('row_reconciliation', len(work) <= len(frame), 'Explicit filters only remove rows; no join or deduplication.'))
    m = task.metrics[0]
    if m.column != '__records__':
        if work[m.column].isna().any():
            checks.append(check('missing_values', m.missing == 'exclude', 'Missing metric values require explicit exclusion policy; never imputed as zero.'))
            if m.missing == 'reject':
                return outcome('insufficient_evidence', 'MISSING_METRIC_VALUES')
        if m.aggregation != 'count':
            while not all(isinstance(v, (int, float, Decimal)) and not isinstance(v, bool) for v in work[m.column].dropna()):
                compatible = [l for l in (lessons or []) if l['correction']['column'] == m.column]
                action = Operation.model_validate(compatible[0]['correction']).model_dump(mode='json') if compatible else {'type': 'exact_decimal_parse', 'column': m.column}
                choice=repair_router.choose({task.datasets[0].dataset_id:work},max(1,budget.max_repairs-repairs_used),actions) if repair_router else None
                if repair_router and choice is None:
                    return outcome('insufficient_evidence','NO_ELIGIBLE_REPAIR')
                action_key = digest([action,choice[0].implementation_hash]) if choice else digest(action)
                reservation = next((r for r in (replay_reservations or []) if r['action_hash'] == action_key and r['input_hash'] == frame_hash(work)), None)
                if action_key in actions and not reservation:
                    return outcome('insufficient_evidence', 'NO_PROGRESS')
                if repairs_used >= budget.max_repairs and not reservation:
                    return outcome('insufficient_evidence', 'REPAIR_BUDGET_EXHAUSTED')
                if time.monotonic() >= deadline:
                    return outcome('insufficient_evidence', 'DEADLINE_EXHAUSTED')
                # Persist budget consumption BEFORE the effect; worker replay cannot reset it.
                if not reservation:
                    repairs_used += 1
                    actions.append(action_key)
                repair_record = {'number': repairs_used, 'action': action, 'decision_source': 'verified_memory' if compatible else 'validated_baseline_policy',
                                 'before_hash': frame_hash(work), 'outcome': 'running', 'checks': [], 'reconstructed_reserved_attempt': bool(reservation)}
                if choice:
                    repair_record.update(skill_id=choice[0].skill_id,skill_version=choice[0].version,decision_id=choice[1]['id'],selector=choice[1]['selector'])
                repair_evidence.append(repair_record)
                if on_repair and not reservation:
                    on_repair(repairs_used, actions, action, frame_hash(work))
                before = frame_hash(work)
                try:
                    if choice:
                        tested=repair_router.perform(choice,frame=work)
                        if not tested.success:
                            repair_record['outcome']='failed';repair_record['checks']=tested.checks
                            continue
                        repaired=tested.frame
                    else:
                        repaired = transform(work, action)
                except (ValueError, InvalidOperation):
                    repair_record['outcome'] = 'failed'
                    checks.append(check('numeric_representation', False, 'Only canonical unambiguous decimal strings may be losslessly converted.'))
                    return outcome('insufficient_evidence', 'AMBIGUOUS_NUMERIC_REPRESENTATION')
                if not all(isinstance(v, Decimal) for v in repaired[m.column].dropna()):
                    return outcome('insufficient_evidence', 'NO_PROGRESS')
                if compatible:
                    applied.append(compatible[0]['lesson_id'])
                repair_record['outcome'] = 'succeeded'
                repair_record['after_hash'] = frame_hash(repaired)
                repair_record['checks'] = ['decimal_equality', 'row_count', 'index_preserved']
                plan.operations.append(Operation.model_validate(action))
                work = repaired
                checks.append(check('lossless_numeric_parse', True, 'Decimal equality, row count and index preserved by approved repair.',
                                    limitations=['No evidence that a unit or business definition changed.']))
            try:
                if not all(Decimal(str(v)).is_finite() for v in work[m.column].dropna()):
                    raise ValueError('NONFINITE_METRIC')
                if not all(len(Decimal(str(v)).as_tuple().digits) <= 18 and
                           max(0, len(Decimal(str(v)).as_tuple().digits) + Decimal(str(v)).as_tuple().exponent) <= 18 and
                           Decimal(str(v)).as_tuple().exponent >= -8 for v in work[m.column].dropna()):
                    return outcome('insufficient_evidence', 'NUMERIC_PRECISION_UNSUPPORTED')
            except (ValueError, InvalidOperation):
                return outcome('insufficient_evidence', 'NONFINITE_METRIC')
    # Bound result cardinality before materializing output.
    if task.dimensions and len(work[task.dimensions].drop_duplicates()) > 1000:
        return outcome('insufficient_evidence', 'RESULT_LIMIT_EXCEEDED')
    try:
        rows = aggregate(task, work)
        answer = answer_object(task, rows, raw_hash)
        checks.extend(REGISTRY.validate({'answer': answer, 'task': task, 'work': work, 'raw': frame, 'raw_hash': raw_hash}))
    except (ValueError, TypeError, InvalidOperation, OverflowError):
        return outcome('insufficient_evidence', 'COMPUTATION_UNSUPPORTED')
    if time.monotonic() >= deadline:
        return outcome('insufficient_evidence', 'DEADLINE_EXHAUSTED')
    if any(c['outcome'] != 'pass' for c in checks if c['severity'] == 'error'):
        return outcome('insufficient_evidence', 'MANDATORY_VALIDATION_FAILED')
    return outcome('verified', answer=answer)
