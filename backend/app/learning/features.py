"""Versioned, bounded lexical/schema features. Persist indices, never raw tokens."""
from __future__ import annotations

from functools import lru_cache
import hashlib
import json
import re
from typing import Any
import numpy as np

from backend.app.learning.perceptron import AveragedPerceptron, FEATURE_SIZE, LABELS
from backend.app.services.intent_classification_service import IntentRegistry

HASH_START = 64
AGGREGATIONS = ("sum", "total", "average", "mean", "count", "min", "max", "by")


@lru_cache(maxsize=1)
def rules() -> tuple[tuple[str, tuple[str, ...], tuple[str, ...]], ...]:
    registry = IntentRegistry()
    return tuple((name, tuple(registry.get(name).keywords), tuple(registry.get(name).patterns)) for name in LABELS)


@lru_cache(maxsize=1)
def feature_version() -> str:
    contract = ["intent-features-v1", FEATURE_SIZE, HASH_START, AGGREGATIONS, rules()]
    return hashlib.sha256(json.dumps(contract, ensure_ascii=True).encode()).hexdigest()


def _slot(token: str) -> int:
    return HASH_START + int.from_bytes(hashlib.sha256(token.encode()).digest()[:8], "big") % (FEATURE_SIZE - HASH_START)


def extract(question: str, schema: dict[str, Any] | None = None) -> np.ndarray:
    if not isinstance(question, str) or len(question) > 2000:
        raise ValueError("Unsupported shadow question")
    normalized = question.lower().strip()
    tokens = re.findall(r"[^\W_]+", normalized, flags=re.UNICODE)[:256]
    vector = np.zeros(FEATURE_SIZE, dtype=np.float64)
    vector[0] = 1
    for index, (_, keywords, patterns) in enumerate(rules()):
        vector[1 + index] = min(8, sum(keyword in normalized for keyword in keywords)) / 8
        vector[1 + len(LABELS) + index] = float(any(re.search(pattern, normalized, re.I) for pattern in patterns))
    for index, word in enumerate(AGGREGATIONS):
        vector[35 + index] = float(word in tokens)
    for size in (1, 2, 3):
        for start in range(len(tokens) - size + 1):
            vector[_slot(f"ngram:{size}:" + " ".join(tokens[start:start + size]))] = 1
    schema = schema or {}
    columns, dtypes = schema.get("columns", []), schema.get("dtypes", {})
    if not isinstance(columns, list) or not isinstance(dtypes, dict):
        raise ValueError("Unsupported shadow schema")
    normalized_tokens = " " + " ".join(tokens) + " "
    for column in columns[:200]:
        if not isinstance(column, str) or len(column) > 256:
            continue
        name = " ".join(re.findall(r"[^\W_]+", column.lower()))
        dtype = str(dtypes.get(column, "")).lower()
        vector[43] = max(vector[43], float(any(part in dtype for part in ("int", "float", "decimal", "numeric"))))
        vector[44] = max(vector[44], float(any(part in dtype for part in ("date", "time"))))
        if name and f" {name} " in normalized_tokens:
            vector[45] = 1
            vector[_slot("column:" + name)] = 1
    vector[46] = float(bool(columns))
    return vector


def bootstrap_prior() -> AveragedPerceptron:
    """Fixed global seed from existing keyword/pattern features, not user feedback."""
    weights = np.zeros((len(LABELS), FEATURE_SIZE), dtype=np.float64)
    for index in range(len(LABELS)):
        weights[index, 1 + index] = 8
        weights[index, 1 + len(LABELS) + index] = 16
    weights[LABELS.index("unknown"), 0] = 0.25
    return AveragedPerceptron(weights)
