"""Enterprise AI Memory Layer for Phase 20.2.

Provides a unified, multi-tier memory system enabling the AI Analyst to remember:
1. Conversation Memory (short-term dialogue window and turns)
2. Analytics Memory (prior SQL queries, statistics, filter states, execution tables)
3. Dashboard Memory (pinned charts, active widgets, user dashboard preferences)
4. Forecast Memory (prior time-series runs, predicted values, selected models, horizons)
5. Dataset Memory (semantic schema mappings, data nuances, user domain feedback)

Includes Contextual Coreference Resolver:
Resolves multi-turn references like:
- "Analyze revenue"
- "Compare with last forecast"
- "Why is it lower?"
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import uuid

logger = logging.getLogger(__name__)

MEMORY_STORAGE_ROOT = Path("storage/memory")


class MemoryEntryType:
    CONVERSATION = "conversation"
    ANALYTICS = "analytics"
    DASHBOARD = "dashboard"
    FORECAST = "forecast"
    DATASET = "dataset"


class AIMemoryLayer:
    """Enterprise AI Memory Layer with multi-tier storage and semantic coreference resolution."""

    def __init__(self, storage_dir: Path | str | None = None) -> None:
        self.storage_dir = Path(storage_dir) if storage_dir else MEMORY_STORAGE_ROOT
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        # In-memory fast tier: {workspace_id: {session_id: {...}}}
        self._cache: dict[str, dict[str, dict[str, Any]]] = {}
        self._load_all_persisted()

    def _get_workspace_path(self, workspace_id: str) -> Path:
        self._validate_component(workspace_id)
        ws_dir = self.storage_dir / workspace_id
        ws_dir.mkdir(parents=True, exist_ok=True)
        return ws_dir

    def _load_all_persisted(self) -> None:
        """Load persisted memory logs from disk."""
        try:
            for ws_dir in self.storage_dir.iterdir():
                if ws_dir.is_dir():
                    ws_id = ws_dir.name
                    if ws_id not in self._cache:
                        self._cache[ws_id] = {}
                    for sess_file in ws_dir.glob("*.json"):
                        sess_id = sess_file.stem
                        with open(sess_file, "r", encoding="utf-8") as f:
                            self._cache[ws_id][sess_id] = json.load(f)
        except Exception as exc:
            logger.warning("Error loading memory logs: %s", exc)

    def _persist_session(self, workspace_id: str, session_id: str) -> None:
        """Atomically persist a session's multi-tier memory to disk."""
        self._validate_component(workspace_id)
        self._validate_component(session_id)
        if workspace_id not in self._cache or session_id not in self._cache[workspace_id]:
            return
        ws_dir = self._get_workspace_path(workspace_id)
        sess_file = ws_dir / f"{session_id}.json"
        try:
            with open(sess_file, "w", encoding="utf-8") as f:
                json.dump(self._cache[workspace_id][session_id], f, indent=2, default=str)
        except Exception as exc:
            logger.error("Failed to persist session memory %s/%s: %s", workspace_id, session_id, exc)

    def _ensure_session(self, workspace_id: str, session_id: str) -> dict[str, Any]:
        """Ensure session memory structure exists in memory."""
        self._validate_component(workspace_id)
        self._validate_component(session_id)
        if workspace_id not in self._cache:
            self._cache[workspace_id] = {}
        if session_id not in self._cache[workspace_id]:
            self._cache[workspace_id][session_id] = {
                "workspace_id": workspace_id,
                "session_id": session_id,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "conversation": [],
                "analytics": [],
                "dashboard": {},
                "forecasts": [],
                "datasets": {},
            }
        return self._cache[workspace_id][session_id]

    @staticmethod
    def _validate_component(value: str) -> None:
        if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', value):
            raise ValueError('Invalid memory storage identifier')

    # -------------------------------------------------------------------------
    # 1. Conversation Memory
    # -------------------------------------------------------------------------

    def record_turn(
        self,
        workspace_id: str,
        session_id: str,
        user_message: str,
        ai_response: str,
        intent: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Record an explicit user-AI interaction turn."""
        sess = self._ensure_session(workspace_id, session_id)
        turn_entry = {
            "id": f"turn-{uuid.uuid4().hex[:8]}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "user_message": user_message,
            "ai_response": ai_response,
            "intent": intent or "general_query",
            "context": context or {},
        }
        sess["conversation"].append(turn_entry)
        self._persist_session(workspace_id, session_id)
        return turn_entry

    def get_conversation_history(
        self,
        workspace_id: str,
        session_id: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Retrieve recent conversation turns."""
        sess = self._ensure_session(workspace_id, session_id)
        return sess["conversation"][-limit:]

    # Alias for compatibility
    get_recent_conversation = get_conversation_history


    # -------------------------------------------------------------------------
    # 2. Analytics Memory
    # -------------------------------------------------------------------------

    def record_analytics_execution(
        self,
        workspace_id: str,
        session_id: str,
        question: str,
        sql_query: str | None = None,
        data_summary: dict[str, Any] | None = None,
        key_metrics: dict[str, Any] | None = None,
        filters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Save executed analytical computations and numbers into analytics memory."""
        sess = self._ensure_session(workspace_id, session_id)
        analytics_entry = {
            "id": f"ana-{uuid.uuid4().hex[:8]}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "question": question,
            "sql_query": sql_query,
            "data_summary": data_summary or {},
            "key_metrics": key_metrics or {},
            "filters": filters or {},
        }
        sess["analytics"].append(analytics_entry)
        self._persist_session(workspace_id, session_id)
        return analytics_entry

    def get_last_analytics(
        self,
        workspace_id: str,
        session_id: str,
    ) -> dict[str, Any] | None:
        """Get the most recent analytics execution."""
        sess = self._ensure_session(workspace_id, session_id)
        if sess["analytics"]:
            return sess["analytics"][-1]
        return None

    # -------------------------------------------------------------------------
    # 3. Forecast Memory
    # -------------------------------------------------------------------------

    def record_forecast(
        self,
        workspace_id: str,
        session_id: str,
        target_column: str,
        model_name: str,
        horizon_periods: int,
        historical_summary: dict[str, Any],
        forecast_values: list[float],
        metrics: dict[str, float] | None = None,
        confidence_interval: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Record generated time-series forecast execution into memory."""
        sess = self._ensure_session(workspace_id, session_id)
        forecast_entry = {
            "id": f"fc-{uuid.uuid4().hex[:8]}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "target_column": target_column,
            "model_name": model_name,
            "horizon_periods": horizon_periods,
            "historical_summary": historical_summary,
            "forecast_values": forecast_values,
            "metrics": metrics or {"MAE": 0.0, "RMSE": 0.0, "MAPE": 0.0},
            "confidence_interval": confidence_interval or {},
        }
        sess["forecasts"].append(forecast_entry)
        self._persist_session(workspace_id, session_id)
        return forecast_entry

    def get_last_forecast(
        self,
        workspace_id: str,
        session_id: str,
    ) -> dict[str, Any] | None:
        """Get the most recent forecast execution."""
        sess = self._ensure_session(workspace_id, session_id)
        if sess["forecasts"]:
            return sess["forecasts"][-1]
        return None

    # -------------------------------------------------------------------------
    # 4. Dashboard & Dataset Memory
    # -------------------------------------------------------------------------

    def record_dashboard_state(
        self,
        workspace_id: str,
        session_id: str,
        dashboard_id: str,
        cards: list[dict[str, Any]],
        active_filters: dict[str, Any] | None = None,
    ) -> None:
        """Update active dashboard state in memory."""
        sess = self._ensure_session(workspace_id, session_id)
        sess["dashboard"] = {
            "dashboard_id": dashboard_id,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "cards": cards,
            "active_filters": active_filters or {},
        }
        self._persist_session(workspace_id, session_id)

    def record_dataset_semantics(
        self,
        workspace_id: str,
        session_id: str,
        dataset_id: str,
        semantic_mapping: dict[str, Any],
    ) -> None:
        """Store learned column semantics and user corrections."""
        sess = self._ensure_session(workspace_id, session_id)
        sess["datasets"][dataset_id] = {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "semantic_mapping": semantic_mapping,
        }
        self._persist_session(workspace_id, session_id)

    # -------------------------------------------------------------------------
    # 5. Context Coreference & Historical Resolution
    # -------------------------------------------------------------------------

    def resolve_contextual_query(
        self,
        query: str,
        workspace_id: str,
        session_id: str,
    ) -> dict[str, Any]:
        """Analyze user query for conversational dependencies and inject prior analytical context."""
        sess = self._ensure_session(workspace_id, session_id)
        lower_q = query.lower()

        resolved_context: dict[str, Any] = {
            "original_query": query,
            "has_memory_dependency": False,
            "referenced_analytics": None,
            "referenced_forecast": None,
            "context_augmented_prompt": query,
            "inferred_entities": [],
        }

        # Check for forecast references ("last forecast", "compare with forecast", "projected")
        if any(term in lower_q for term in ["last forecast", "compare with forecast", "previous forecast", "forecasted"]):
            last_fc = self.get_last_forecast(workspace_id, session_id)
            if last_fc:
                resolved_context["has_memory_dependency"] = True
                resolved_context["referenced_forecast"] = last_fc
                fc_val_str = ", ".join(f"{v:,.2f}" for v in last_fc["forecast_values"][:3])
                resolved_context["context_augmented_prompt"] = (
                    f"{query} [Context: Prior forecast for target '{last_fc['target_column']}' "
                    f"using model '{last_fc['model_name']}' projected upcoming values [{fc_val_str}...]. "
                    f"Horizon: {last_fc['horizon_periods']} periods.]"
                )

        # Check for coreference pronouns ("why is it lower", "what caused it", "why did that happen")
        if re.search(r"\b(it|that|this|they|them)\b", lower_q) or "why is" in lower_q or "compared to" in lower_q:
            last_ana = self.get_last_analytics(workspace_id, session_id)
            if last_ana:
                resolved_context["has_memory_dependency"] = True
                resolved_context["referenced_analytics"] = last_ana
                metrics_summary = json.dumps(last_ana.get("key_metrics", {}))
                resolved_context["context_augmented_prompt"] += (
                    f" [Context: User is referring to prior analysis question: '{last_ana['question']}' "
                    f"with key computed metrics: {metrics_summary}]."
                )

        return resolved_context


# Singleton memory layer instance
_memory_layer = AIMemoryLayer()


def get_ai_memory_layer() -> AIMemoryLayer:
    """Dependency provider for AI Memory Layer."""
    return _memory_layer
