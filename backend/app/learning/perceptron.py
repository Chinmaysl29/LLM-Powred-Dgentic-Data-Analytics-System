"""Small NumPy averaged multiclass perceptron. No business calculations or I/O."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import numpy as np

from backend.app.schemas.intent import IntentType

LABELS = tuple(intent.value for intent in IntentType)
FEATURE_SIZE = 576
MAX_WEIGHT = 1000.0


@dataclass(frozen=True)
class Prediction:
    intent: str
    candidate: str
    margin: float
    abstained: bool


class AveragedPerceptron:
    """Average post-update weights across all labelled examples, including hits.

    `update` is an offline primitive. The shadow request path never calls it.
    Exported JSON is an inference snapshot, not a resumable training checkpoint.
    """

    def __init__(self, weights: Any = None) -> None:
        shape = (len(LABELS), FEATURE_SIZE)
        matrix = np.zeros(shape, dtype=np.float64) if weights is None else np.array(weights, dtype=np.float64, copy=True)
        if matrix.shape != shape or not np.isfinite(matrix).all() or np.any(np.abs(matrix) > MAX_WEIGHT):
            raise ValueError("Invalid perceptron weights")
        self.weights = matrix
        self._totals = np.zeros(shape, dtype=np.float64)
        self.steps = 0

    @staticmethod
    def _vector(features: Any) -> np.ndarray:
        vector = np.asarray(features, dtype=np.float64)
        if vector.shape != (FEATURE_SIZE,) or not np.isfinite(vector).all() or np.any(np.abs(vector) > 1):
            raise ValueError("Invalid perceptron features")
        return vector

    def averaged_weights(self) -> np.ndarray:
        return self._totals / self.steps if self.steps else self.weights.copy()

    def predict(self, features: Any, *, min_margin: float = 0.5, allow_unknown: bool = False) -> Prediction:
        if not np.isfinite(min_margin) or min_margin < 0:
            raise ValueError("Invalid margin threshold")
        scores = self.averaged_weights() @ self._vector(features)
        if not np.isfinite(scores).all():
            raise ValueError("Invalid perceptron scores")
        winner = int(np.argmax(scores))  # Deterministic label-order tie break.
        margin = float(scores[winner] - np.max(np.delete(scores, winner)))
        # Live routing can explicitly choose the allow-listed unknown intent.
        # Preserve the Phase 2 shadow policy unless the caller opts in.
        abstained = margin <= min_margin or (LABELS[winner] == "unknown" and not allow_unknown)
        return Prediction("unknown" if abstained else LABELS[winner], LABELS[winner], margin, abstained)

    def update(self, features: Any, truth: str, *, rate: float = 1.0, decay: float = 0.001) -> bool:
        if truth not in LABELS:
            raise ValueError("Truth must be a verified supported intent")
        if not np.isfinite(rate) or not 0 < rate <= 1 or not np.isfinite(decay) or not 0 <= decay < 1:
            raise ValueError("Invalid perceptron update parameters")
        vector = self._vector(features)
        predicted = int(np.argmax(self.weights @ vector))
        target = LABELS.index(truth)
        updated = self.weights * (1 - decay)
        if predicted != target:
            updated[target] += rate * vector
            updated[predicted] -= rate * vector
        if np.any(np.abs(updated) > MAX_WEIGHT) or not np.isfinite(updated).all():
            raise ValueError("Perceptron weight bound exceeded")
        self.weights = updated
        self._totals += updated
        self.steps += 1
        return predicted != target

    def to_payload(self, feature_version: str) -> dict[str, Any]:
        return {"format": 1, "feature_version": feature_version,
                "labels": list(LABELS), "weights": self.averaged_weights().tolist()}

    @classmethod
    def from_payload(cls, payload: dict[str, Any], feature_version: str) -> AveragedPerceptron:
        if (not isinstance(payload, dict) or set(payload) != {"format", "feature_version", "labels", "weights"}
                or type(payload["format"]) is not int or payload["format"] != 1
                or payload["feature_version"] != feature_version or payload["labels"] != list(LABELS)):
            raise ValueError("Incompatible perceptron snapshot")
        # Check lengths before NumPy allocates; reject ragged/oversized snapshots.
        rows = payload["weights"]
        if not isinstance(rows, list) or len(rows) != len(LABELS) or any(
            not isinstance(row, list) or len(row) != FEATURE_SIZE for row in rows
        ):
            raise ValueError("Invalid perceptron snapshot shape")
        if any(type(value) not in (int, float) for row in rows for value in row):
            raise ValueError("Snapshot weights must be JSON numbers")
        return cls(rows)
