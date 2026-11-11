"""Averaged NumPy perceptron over variable column candidates, including abstention.

Only schema and question features enter this module; never dataset values.
"""
from __future__ import annotations

import hashlib
import re
import numpy as np

SIZE = 512
FEATURE_VERSION = 'column-ranker-v2-512-vocabulary'
MIN_MARGIN = 0.5
GRAMMAR = frozenset('please show me the a an of by per and total sum average avg mean minimum min maximum max top bottom highest lowest monthly trend over time'.split())


def tokens(value: str) -> list[str]:
    return re.findall(r'[^\W_]+', value.casefold())[:64]


def question_hash(question: str) -> str:
    return hashlib.sha256(' '.join(tokens(question)).encode()).hexdigest()


def features(question: str, column: str | None, dtype: str = '') -> np.ndarray:
    if not isinstance(question, str) or not 1 <= len(question) <= 2000:
        raise ValueError('Invalid resolver question')
    if len(re.findall(r'[^\W_]+', question)) > 64:
        raise ValueError('Resolver questions must not be partially interpreted')
    if column is not None and (not isinstance(column, str) or not 1 <= len(column) <= 256):
        raise ValueError('Invalid resolver column')
    q = tokens(question)
    c = tokens(column) if column is not None else []
    vector = np.zeros(SIZE)
    vector[0 if column is None else 1] = 1
    vector[2] = len(set(q) & set(c)) / max(1, len(set(c)))
    vector[3] = float(bool(c) and (' ' + ' '.join(c) + ' ') in (' ' + ' '.join(q) + ' '))
    candidate = 'column:' + column if column is not None else 'abstain'
    terms = q + [' '.join(q[i:i+2]) for i in range(len(q)-1)]
    for term in terms:
        for value in (candidate + ':' + term, 'dtype:' + dtype + ':' + term):
            slot = 8 + int.from_bytes(hashlib.sha256(value.encode()).digest()[:8], 'big') % (SIZE - 8)
            vector[slot] = 1
    return vector


class ColumnRanker:
    def __init__(self, weights=None, vocabulary=None):
        if weights is None:
            weights = [0.0] * SIZE
            weights[0], weights[2], weights[3] = 1.0, 1.0, 2.0
        if (not isinstance(weights, list) or len(weights) != SIZE
                or any(type(v) not in (int, float) for v in weights)):
            raise ValueError('Invalid resolver weights')
        self.weights = np.array(weights, dtype=np.float64)
        if not np.isfinite(self.weights).all() or np.any(np.abs(self.weights) > 1000):
            raise ValueError('Invalid resolver weight range')
        self.total = np.zeros(SIZE)
        self.steps = 0
        vocabulary = [] if vocabulary is None else vocabulary
        if (not isinstance(vocabulary, list) or len(vocabulary) > 512
                or any(not isinstance(v, str) or not re.fullmatch('[0-9a-f]{64}', v) for v in vocabulary)
                or len(set(vocabulary)) != len(vocabulary)):
            raise ValueError('Invalid resolver vocabulary')
        self.vocabulary = set(vocabulary)

    def matrix(self, question: str, candidates: list[str], dtypes: dict):
        if (not isinstance(candidates, list) or not 1 <= len(candidates) <= 200
                or len(set(candidates)) != len(candidates)):
            raise ValueError('Invalid candidates')
        choices = [None, *sorted(candidates)]
        return choices, np.stack([features(question, c, str(dtypes.get(c, ''))) for c in choices])

    def predict(self, question: str, candidates: list[str], dtypes: dict) -> tuple[str | None, float]:
        choices, matrix = self.matrix(question, candidates, dtypes)
        # A large score on familiar aggregation words is not evidence for a new
        # business term. Novel content words must first receive reviewed labels.
        schema_words = {word for name in dtypes for word in tokens(name)}
        content = set(tokens(question)) - GRAMMAR - schema_words
        if any(hashlib.sha256(word.encode()).hexdigest() not in self.vocabulary for word in content):
            return None, 0.0
        weights = self.total / self.steps if self.steps else self.weights
        scores = matrix @ weights
        winner = int(np.argmax(scores))
        margin = float(scores[winner] - np.max(np.delete(scores, winner)))
        return (choices[winner] if margin > MIN_MARGIN else None), margin

    def update(self, question: str, candidates: list[str], dtypes: dict, truth: str | None):
        choices, matrix = self.matrix(question, candidates, dtypes)
        if truth not in choices:
            raise ValueError('Reviewed choice is not a candidate')
        self.vocabulary.update(hashlib.sha256(word.encode()).hexdigest() for word in set(tokens(question)) - GRAMMAR)
        if len(self.vocabulary) > 512:
            raise ValueError('Reviewed vocabulary exceeds bound')
        winner = int(np.argmax(matrix @ self.weights))
        self.weights *= 0.999
        target = choices.index(truth)
        if winner != target:
            self.weights += matrix[target] - matrix[winner]
        if not np.isfinite(self.weights).all() or np.any(np.abs(self.weights) > 1000):
            raise ValueError('Resolver weight bound exceeded')
        self.total += self.weights
        self.steps += 1

    def snapshot(self) -> list[float]:
        return (self.total / self.steps if self.steps else self.weights).tolist()
