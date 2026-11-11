"""Bounded lexical vectors and non-executable correction contracts."""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any

import numpy as np
from backend.app.learning.perceptron import LABELS

DIMENSION = 1024
EMBEDDING_VERSION = "perceptron-failure-lexical-v1-1024"
MIN_SIMILARITY = 0.90
SAFE_STEPS = frozenset({"validation", "eda", "statistics"})


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def correction(value: Any) -> dict:
    if (not isinstance(value, dict) or set(value) != {"format", "intent", "add_steps"}
            or type(value["format"]) is not int or value["format"] != 1
            or value["intent"] not in LABELS or value["intent"] == "unknown"):
        raise ValueError("Invalid correction contract")
    steps = value["add_steps"]
    if (not isinstance(steps, list) or not 1 <= len(steps) <= 3
            or any(not isinstance(step, str) or step not in SAFE_STEPS for step in steps)
            or len(set(steps)) != len(steps)):
        raise ValueError("Correction may only add approved analytical checks")
    return {"format": 1, "intent": value["intent"], "add_steps": list(steps)}


def embedding(question: str) -> list[float]:
    if not isinstance(question, str) or not 1 <= len(question) <= 2000:
        raise ValueError("Unsupported question")
    tokens = re.findall(r"[^\W_]+", question.casefold(), flags=re.UNICODE)[:256]
    if not tokens:
        raise ValueError("Question has no lexical features")
    vector = np.zeros(DIMENSION, dtype=np.float64)
    for size in (1, 2):
        for start in range(len(tokens) - size + 1):
            token = f"{size}:" + " ".join(tokens[start:start + size])
            index = int.from_bytes(hashlib.sha256(token.encode()).digest()[:8], "big") % DIMENSION
            vector[index] = 1
    return (vector / np.linalg.norm(vector)).tolist()


def checked_vector(value: Any) -> np.ndarray:
    if (not isinstance(value, list) or len(value) != DIMENSION
            or any(type(item) not in (int, float) for item in value)):
        raise ValueError("Invalid stored vector")
    vector = np.asarray(value, dtype=np.float64)
    if not np.isfinite(vector).all() or np.any(vector < 0) or abs(np.linalg.norm(vector) - 1) > 1e-6:
        raise ValueError("Invalid stored vector values")
    return vector


def payload_digest(row: dict) -> str:
    return digest({key: row[key] for key in (
        "dataset_schema_hash", "question_hash", "features", "predicted", "truth", "signal_type", "error_type", "corrected_plan")})


def merge_steps(steps: list[str], hints: list[dict], intent: str) -> list[str]:
    result = list(steps)
    for hint in hints[:3]:
        plan = correction(hint)
        if plan["intent"] != intent:
            continue
        for step in plan["add_steps"]:
            if step not in result:
                result.append(step)
    return result
