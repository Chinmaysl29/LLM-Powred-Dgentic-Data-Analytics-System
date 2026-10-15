"""Dataset-backed dashboard computation and durable, scoped configuration storage."""
from __future__ import annotations
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4
import numpy as np
import pandas as pd

DASHBOARD_STORAGE_ROOT = Path("storage/dashboards")

class DashboardBuilderService:
    def __init__(self, storage_dir: Path | str | None = None):
        self.storage_dir = Path(storage_dir or DASHBOARD_STORAGE_ROOT)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._dashboards = {}
        for file in self.storage_dir.glob("dash-*.json"):
            try:
                value = json.loads(file.read_text(encoding="utf-8"))
                if value.get("id"): self._dashboards[value["id"]] = value
            except (ValueError, OSError):
                continue

    def _persist_dashboard(self, dashboard_id):
        target = self.storage_dir / f"{dashboard_id}.json"
        temporary = target.with_suffix(f".{uuid4().hex}.tmp")
        try:
            with temporary.open("w", encoding="utf-8") as handle:
                json.dump(self._dashboards[dashboard_id], handle, ensure_ascii=False, allow_nan=False)
                handle.flush(); os.fsync(handle.fileno())
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)

    @staticmethod
    def compute(df, metric, dimension=None, filters=None):
        if metric not in df.columns or not pd.api.types.is_numeric_dtype(df[metric]):
            raise ValueError("Choose an existing numeric metric")
        if dimension and dimension not in df.columns:
            raise ValueError("Choose an existing dimension")
        filtered = df.copy()
        for field, value in (filters or {}).items():
            if field not in filtered.columns: raise ValueError("Unknown filter column")
            filtered = filtered.loc[filtered[field].astype(str) == str(value)]
        values = pd.to_numeric(filtered[metric], errors="coerce").replace([np.inf, -np.inf], np.nan)
        valid = values.dropna()
        kpis = [
            {"id": "count", "label": "Matching records", "value": len(filtered)},
            {"id": "sum", "label": f"Sum of {metric}", "value": float(valid.sum()) if len(valid) else None},
            {"id": "mean", "label": f"Mean of {metric}", "value": float(valid.mean()) if len(valid) else None},
            {"id": "missing", "label": f"Missing or nonfinite {metric}", "value": int(values.isna().sum())},
        ]
        points = []
        if dimension:
            data = pd.DataFrame({"label": filtered[dimension].astype("string").fillna("(missing)"), "value": values})
            for label, group in data.groupby("label", sort=True):
                measure = group["value"].dropna()
                points.append({"label": str(label), "value": float(measure.sum()) if len(measure) else None, "count": len(group)})
        return {"kpis": kpis, "charts": [{"id": "grouped", "type": "bar", "title": f"Sum of {metric} by {dimension}", "points": points}] if dimension else [],
                "population_size": len(df), "filtered_rows": len(filtered), "sampling_method": "none", "filters": filters or {},
                "metric": metric, "dimension": dimension, "aggregation": "sum", "units": "source units",
                "warnings": ["Null and nonfinite metric values are excluded; no values are imputed."]}

    def create_dashboard_from_prompt(self, prompt, df, workspace_id="default-ws", title=None,
                                     metric=None, dimension=None, filters=None, provenance=None):
        if metric is None:
            numeric = df.select_dtypes(include=[np.number]).columns.tolist()
            if not numeric:
                raise ValueError("Dataset has no numeric columns for dashboard metrics")
            metric = numeric[0]
        now = datetime.now(timezone.utc).isoformat()
        dashboard = {"id": f"dash-{uuid4().hex}", "title": title or "Dataset dashboard", "prompt": prompt,
                     "workspace_id": str(workspace_id), "created_at": now, "updated_at": now,
                     "layout": "grid", "provenance": provenance or {}, **self.compute(df, metric, dimension, filters)}
        self._dashboards[dashboard["id"]] = dashboard
        self._persist_dashboard(dashboard["id"])
        return dashboard

    def get_dashboard(self, dashboard_id):
        if dashboard_id not in self._dashboards: raise KeyError("Dashboard not found")
        return self._dashboards[dashboard_id]

    def list_dashboards(self, workspace_id=None):
        return [d for d in self._dashboards.values() if not workspace_id or d.get("workspace_id") == str(workspace_id)]

    def update_dashboard(self, dashboard_id, df, *, layout, metric, dimension=None, filters=None, title=None):
        if layout not in {"grid", "list"}: raise ValueError("Unsupported layout")
        current = self.get_dashboard(dashboard_id)
        current.update(self.compute(df, metric, dimension, filters))
        current.update(layout=layout, updated_at=datetime.now(timezone.utc).isoformat())
        if title: current["title"] = title
        self._persist_dashboard(dashboard_id)
        return current

    def delete_dashboard(self, dashboard_id):
        self.get_dashboard(dashboard_id)
        (self.storage_dir / f"{dashboard_id}.json").unlink()
        del self._dashboards[dashboard_id]

_dashboard_builder_service = DashboardBuilderService()
def get_dashboard_builder_service(): return _dashboard_builder_service
