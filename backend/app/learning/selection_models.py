"""NumPy presentation/provider policies. No business calculations or API calls."""
import math
import numpy as np

KINDS = ('chart', 'provider')
PROVIDERS = ('groq', 'gemini', 'openai')
CHARTS = ('bar', 'line')
EPSILON = 0.05


def chart_features(context):
    if (not isinstance(context, dict) or set(context) != {'temporal', 'points', 'dimensions', 'ranking', 'explicit'}
            or any(type(context[key]) is not bool for key in ('temporal', 'ranking', 'explicit'))
            or type(context['points']) is not int or not 1 <= context['points'] <= 50
            or type(context['dimensions']) is not int or not 1 <= context['dimensions'] <= 4):
        raise ValueError('Invalid chart context')
    return np.array([1, context['temporal'], context['points'] / 50,
        context['dimensions'] / 4, context['ranking'], context['explicit']], dtype=float)


def chart_options(context):
    chart_features(context)
    return CHARTS if (context['temporal'] and context['points'] >= 2 and context['dimensions'] == 1
        and not context['ranking'] and not context['explicit']) else ('bar',)


class ChartPolicy:
    def __init__(self, payload=None):
        rows = [[0.0] * 6 for _ in CHARTS] if payload is None else payload
        if (not isinstance(rows, list) or len(rows) != 2 or any(not isinstance(r, list) or len(r) != 6 for r in rows)
                or any(type(v) not in (int, float) for r in rows for v in r)):
            raise ValueError('Invalid chart weights')
        self.weights = np.asarray(rows, dtype=float).copy()
        if not np.isfinite(self.weights).all() or np.any(np.abs(self.weights) > 1000):
            raise ValueError('Invalid chart weight values')
        self.total = np.zeros((2, 6)); self.steps = 0

    def predict(self, context):
        options = chart_options(context)
        if len(options) == 1:
            return options[0]
        scores = (self.total / self.steps if self.steps else self.weights) @ chart_features(context)
        return CHARTS[int(np.argmax(scores))] if abs(scores[0] - scores[1]) > 0.5 else 'bar'

    def update(self, context, truth):
        if truth not in chart_options(context):
            raise ValueError('Unsafe reviewed chart')
        vector = chart_features(context)
        predicted = int(np.argmax(self.weights @ vector))
        target = CHARTS.index(truth)
        self.weights *= 0.999
        if target != predicted:
            self.weights[target] += vector
            self.weights[predicted] -= vector
        self.total += self.weights; self.steps += 1

    def snapshot(self):
        return (self.total / self.steps if self.steps else self.weights).tolist()


def outcome(value):
    if not isinstance(value, dict) or set(value) != {'correct', 'latency_ms', 'cost_usd'} or type(value['correct']) is not bool:
        raise ValueError('A reviewed correctness label and measured latency/cost are required')
    for key, maximum in (('latency_ms', 120000), ('cost_usd', 10)):
        if type(value[key]) not in (int, float) or not math.isfinite(value[key]) or not 0 <= value[key] <= maximum:
            raise ValueError('Invalid measured outcome')
    return float(value['correct']) - .1 * min(value['latency_ms'] / 30000, 1) - .1 * min(value['cost_usd'] / .01, 1)


class ProviderBandit:
    """Reviewed empirical arm means; exploration only among fully correct warm arms."""
    def __init__(self, payload):
        if not isinstance(payload, dict) or set(payload) != {'models', 'arms'}:
            raise ValueError('Invalid bandit snapshot')
        models, arms = payload['models'], payload['arms']
        if (not isinstance(models, dict) or not 2 <= len(models) <= 3 or not set(models) <= set(PROVIDERS)
                or any(not isinstance(v, str) or not 1 <= len(v) <= 120 for v in models.values())
                or not isinstance(arms, dict) or set(arms) != set(models)):
            raise ValueError('Invalid pinned providers')
        for arm in arms.values():
            if (not isinstance(arm, dict) or set(arm) != {'count', 'correct', 'reward'}
                    or type(arm['count']) is not int or not 0 <= arm['count'] <= 500
                    or type(arm['correct']) is not int or not 0 <= arm['correct'] <= arm['count']
                    or type(arm['reward']) not in (float, int) or not math.isfinite(arm['reward'])
                    or not -.2 * arm['count'] - 1e-6 <= arm['reward'] <= arm['count'] + 1e-6):
                raise ValueError('Invalid reviewed arm evidence')
        self.models = dict(models)
        self.arms = {key: dict(value) for key, value in arms.items()}

    def update(self, provider, measured):
        reward = outcome(measured)
        arm = self.arms[provider]
        arm['count'] += 1; arm['correct'] += int(measured['correct']); arm['reward'] += reward

    def probabilities(self):
        safe = [p for p in PROVIDERS if p in self.arms and self.arms[p]['count'] >= 5
            and self.arms[p]['correct'] == self.arms[p]['count']]
        if not safe:
            return {}
        best = max(safe, key=lambda p: self.arms[p]['reward'] / self.arms[p]['count'])
        return {p: EPSILON / len(safe) + (1 - EPSILON if p == best else 0) for p in safe}

    def choose(self, rng=None):
        probabilities = self.probabilities()
        if not probabilities:
            return None
        rng = np.random.default_rng() if rng is None else rng
        return str(rng.choice(list(probabilities), p=list(probabilities.values())))

    def snapshot(self):
        return {'models': dict(self.models), 'arms': {k: dict(v) for k, v in self.arms.items()}}


def load_model(kind, payload):
    if kind == 'chart':
        return ChartPolicy(payload)
    if kind == 'provider':
        return ProviderBandit(payload)
    raise ValueError('Unknown selection learner')
