"""Reviewed, frozen, scenario-disjoint selection evaluation; no provider requests."""
from backend.app.learning.memory_contract import digest
from backend.app.learning.selection_models import ChartPolicy, ProviderBandit, PROVIDERS, chart_options, outcome, load_model


def manifest(value):
    if (not isinstance(value, dict) or set(value) != {'format', 'kind', 'models', 'cases'}
            or type(value['format']) is not int or value['format'] != 1 or value['kind'] not in ('chart', 'provider')
            or not isinstance(value['cases'], list) or not 40 <= len(value['cases']) <= 500):
        raise ValueError('Invalid reviewed selection manifest')
    if value['kind'] == 'chart':
        if value['models'] != {}:
            raise ValueError('Chart manifest has no external models')
    else:
        ProviderBandit({'models': value['models'], 'arms': {p: {'count': 0, 'correct': 0, 'reward': 0} for p in value['models']}})
    groups = {'train': set(), 'golden': set()}; counts = {'train': 0, 'golden': 0}; ids = set()
    for row in value['cases']:
        fields = {'id', 'group', 'split', 'context', 'expected'} if value['kind'] == 'chart' else {'id', 'group', 'split', 'outcomes'}
        if (not isinstance(row, dict) or set(row) != fields or row['split'] not in counts
                or any(not isinstance(row[k], str) or not 1 <= len(row[k]) <= 100 for k in ('id', 'group'))
                or row['id'] in ids):
            raise ValueError('Invalid or duplicated reviewed case')
        ids.add(row['id']); groups[row['split']].add(row['group']); counts[row['split']] += 1
        if value['kind'] == 'chart':
            if row['expected'] not in chart_options(row['context']):
                raise ValueError('Unsafe chart label')
        else:
            if not isinstance(row['outcomes'], dict) or set(row['outcomes']) != set(value['models']):
                raise ValueError('Require paired outcomes for every pinned provider')
            for measured in row['outcomes'].values():
                outcome(measured)
    if counts['train'] < 10 or counts['golden'] < 30 or groups['train'] & groups['golden']:
        raise ValueError('Insufficient or leaking reviewed splits')
    return value


def train(value):
    value = manifest(value)
    if value['kind'] == 'chart':
        model = ChartPolicy()
        for _ in range(20):
            for row in value['cases']:
                if row['split'] == 'train':
                    model.update(row['context'], row['expected'])
    else:
        model = ProviderBandit({'models': value['models'], 'arms': {p: {'count': 0, 'correct': 0, 'reward': 0} for p in value['models']}})
        for row in value['cases']:
            if row['split'] == 'train':
                for p, measured in row['outcomes'].items():
                    model.update(p, measured)
    return model.snapshot()


def evaluate(value, payload, current=None):
    value = manifest(value); kind = value['kind']
    model = load_model(kind, payload); live = load_model(kind, current) if current is not None else None
    candidate_score = baseline_score = live_score = 0.0; all_correct = True; count = 0
    if kind == 'provider' and (model.models != value['models'] or (live and live.models != model.models)):
        raise ValueError('Provider/model benchmark changed')
    for row in value['cases']:
        if row['split'] != 'golden':
            continue
        count += 1
        if kind == 'chart':
            predicted = model.predict(row['context'])
            candidate_score += predicted == row['expected']
            baseline_score += row['expected'] == 'bar'
            live_score += (live.predict(row['context']) if live else 'bar') == row['expected']
            all_correct = all_correct and predicted == row['expected']
        else:
            baseline = next(p for p in PROVIDERS if p in value['models'])
            probabilities = model.probabilities()
            all_correct = all_correct and bool(probabilities) and all(row['outcomes'][p]['correct'] for p in probabilities)
            candidate_score += sum(probability * outcome(row['outcomes'][p]) for p, probability in probabilities.items())
            baseline_score += outcome(row['outcomes'][baseline])
            current_probabilities = live.probabilities() if live else {baseline: 1.0}
            live_score += sum(probability * outcome(row['outcomes'][p]) for p, probability in current_probabilities.items())
    return {'manifest_digest': digest(value), 'kind': kind, 'cases': count,
        'candidate_score': candidate_score, 'baseline_score': baseline_score, 'live_score': live_score,
        'all_correct': bool(all_correct), 'passed': bool(all_correct and candidate_score > max(baseline_score, live_score) + 1e-9)}
