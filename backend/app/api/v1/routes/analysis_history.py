"""Persistent AI Analysis History, Sessions, and Reports Integration API."""

from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.security import get_current_user
from backend.app.core.workspace_authorization import authorize_bound_dataset, authorize_workspace
from backend.app.database.postgres import get_db_session
from backend.app.models.analysis_run import AnalysisArtifact, AnalysisRun
from backend.app.models.dataset import Dataset
from backend.app.models.dataset_version import DatasetVersion
from backend.app.services.analysis_session_service import AnalysisSessionService
from backend.app.services.report_studio_service import REPORT_STUDIO_STORAGE_ROOT, ReportStudioService, ReportType

router = APIRouter(tags=["Analysis History & Reports"])


# ==============================================================================
# SCHEMAS
# ==============================================================================

class CreateSessionRequest(BaseModel):
    title: str | None = Field(None, max_length=500)
    workspace_id: UUID | None = None
    dataset_id: str | None = None
    dataset_version: int | None = Field(None, ge=1)


class UpdateSessionRequest(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=500)
    status: str | None = Field(None, max_length=50)


class GenerateReportFromAnalysisRequest(BaseModel):
    run_id: str = Field(..., description="Completed AnalysisRun UUID")
    session_id: str | None = Field(None, description="Source analysis session UUID")
    title: str | None = Field(None, max_length=500)
    report_type: str = Field("Executive Report", description="Executive Report, Board Report, etc.")
    format_type: str = Field("pdf", description="pdf, docx, xlsx, pptx")
    sections: list[str] = Field(default_factory=list)


# ==============================================================================
# ANALYSIS SESSIONS ENDPOINTS
# ==============================================================================

@router.post("/analysis/sessions", status_code=201)
def create_session(
    payload: CreateSessionRequest,
    db: Session = Depends(get_db_session),
    user: Any = Depends(get_current_user),
) -> dict[str, Any]:
    """Create a new persistent AI analysis session."""
    if payload.workspace_id:
        authorize_workspace(db, user.id, payload.workspace_id, "write")
    if payload.dataset_id and payload.workspace_id:
        access = authorize_workspace(db, user.id, payload.workspace_id)
        authorize_bound_dataset(db, access, payload.dataset_id)

    return AnalysisSessionService.create_session(
        db=db,
        user_id=user.id,
        title=payload.title,
        workspace_id=payload.workspace_id,
        dataset_id=payload.dataset_id,
        dataset_version=payload.dataset_version,
    )


@router.get("/analysis/sessions")
def list_sessions(
    workspace_id: UUID | None = Query(None),
    search: str | None = Query(None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db_session),
    user: Any = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """List analysis sessions for current user in chronological order."""
    if workspace_id:
        authorize_workspace(db, user.id, workspace_id, "read")
    return AnalysisSessionService.list_sessions(
        db=db,
        user_id=user.id,
        workspace_id=workspace_id,
        search=search,
        limit=limit,
        offset=offset,
    )


@router.get("/analysis/sessions/{session_id}")
def get_session(
    session_id: UUID,
    db: Session = Depends(get_db_session),
    user: Any = Depends(get_current_user),
) -> dict[str, Any]:
    """Fetch session details, all chronological turns, verified artifacts, and citations."""
    session = AnalysisSessionService.get_session_details(db, session_id, user.id)
    if not session:
        raise HTTPException(404, "Analysis session not found or unauthorized")
    return session


@router.patch("/analysis/sessions/{session_id}")
def update_session(
    session_id: UUID,
    payload: UpdateSessionRequest,
    db: Session = Depends(get_db_session),
    user: Any = Depends(get_current_user),
) -> dict[str, Any]:
    """Rename or update the status of an analysis session."""
    if payload.title:
        renamed = AnalysisSessionService.rename_session(db, session_id, user.id, payload.title)
        if not renamed:
            raise HTTPException(404, "Analysis session not found or unauthorized")
    if payload.status == "deleted":
        deleted = AnalysisSessionService.delete_session(db, session_id, user.id)
        if not deleted:
            raise HTTPException(404, "Analysis session not found or unauthorized")
    return {"status": "updated", "session_id": str(session_id)}


@router.delete("/analysis/sessions/{session_id}")
def delete_session(
    session_id: UUID,
    db: Session = Depends(get_db_session),
    user: Any = Depends(get_current_user),
) -> dict[str, Any]:
    """Soft-delete an analysis session."""
    deleted = AnalysisSessionService.delete_session(db, session_id, user.id)
    if not deleted:
        raise HTTPException(404, "Analysis session not found or unauthorized")
    return {"status": "deleted", "session_id": str(session_id)}


# ==============================================================================
# ANALYSIS RUNS & ARTIFACTS ENDPOINTS
# ==============================================================================

@router.get("/analysis/runs/{run_id}")
def get_analysis_run(
    run_id: str,
    db: Session = Depends(get_db_session),
    user: Any = Depends(get_current_user),
) -> dict[str, Any]:
    """Get durable AnalysisRun record."""
    run = db.get(AnalysisRun, run_id)
    if not run or str(run.owner_id) != str(user.id):
        raise HTTPException(404, "Analysis run not found or unauthorized")
    access = authorize_workspace(db, user.id, run.workspace_id, "read")
    authorize_bound_dataset(db, access, run.dataset_id)

    return {
        "run_id": run.id,
        "workspace_id": str(run.workspace_id),
        "owner_id": str(run.owner_id),
        "dataset_id": run.dataset_id,
        "version_number": run.version_number,
        "query": run.query,
        "status": run.status,
        "created_at": run.created_at.isoformat() if run.created_at else None,
    }


@router.get("/analysis/runs/{run_id}/artifacts")
def get_analysis_run_artifacts(
    run_id: str,
    db: Session = Depends(get_db_session),
    user: Any = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """Get all saved analytical artifacts for a run."""
    run = db.get(AnalysisRun, run_id)
    if not run or str(run.owner_id) != str(user.id):
        raise HTTPException(404, "Analysis run not found or unauthorized")
    access = authorize_workspace(db, user.id, run.workspace_id, "read")
    authorize_bound_dataset(db, access, run.dataset_id)

    artifacts = db.scalars(
        select(AnalysisArtifact).where(AnalysisArtifact.run_id == run_id).order_by(AnalysisArtifact.stage_number)
    ).all()
    return [
        {
            "id": a.id,
            "run_id": a.run_id,
            "stage_number": a.stage_number,
            "content": a.content,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in artifacts
    ]


# ==============================================================================
# REPORTS INTEGRATION ENDPOINTS
# ==============================================================================

@router.get("/reports/analysis-history")
def get_reports_analysis_history(
    workspace_id: UUID | None = Query(None),
    db: Session = Depends(get_db_session),
    user: Any = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """Retrieve all completed analyses eligible for report generation.

    Reads from the exact same persistent PostgreSQL source of truth as AI Analysis.
    """
    if workspace_id:
        authorize_workspace(db, user.id, workspace_id, "read")
    return AnalysisSessionService.list_analysis_history_for_reports(db, user.id, workspace_id)


@router.post("/reports/from-analysis", status_code=201)
def generate_report_from_analysis(
    payload: GenerateReportFromAnalysisRequest,
    request: Request,
    db: Session = Depends(get_db_session),
    user: Any = Depends(get_current_user),
) -> dict[str, Any]:
    """Generate a verified, evidence-backed detailed report from a completed AnalysisRun."""
    # 1. Authorize run and access
    run = db.get(AnalysisRun, payload.run_id)
    if not run or str(run.owner_id) != str(user.id):
        raise HTTPException(404, "Analysis run not found or unauthorized")
    access = authorize_workspace(db, user.id, run.workspace_id, "write")
    authorize_bound_dataset(db, access, run.dataset_id)

    # 2. Retrieve verified artifacts
    artifact_rows = db.scalars(
        select(AnalysisArtifact).where(AnalysisArtifact.run_id == payload.run_id).order_by(AnalysisArtifact.stage_number)
    ).all()
    if not artifact_rows:
        raise HTTPException(422, "No verified analytical artifacts found for this run")

    # Combine artifact content from stages 5 and 6
    merged_content: dict[str, Any] = {}
    for a in artifact_rows:
        if isinstance(a.content, dict):
            merged_content.update(a.content)

    answer = merged_content.get("answer") or run.query
    summary = merged_content.get("explanation") or answer
    kpis = merged_content.get("kpis") or {}
    chart = merged_content.get("chart")
    action_items = merged_content.get("actionable") or []
    citations = merged_content.get("citations") or []
    data_rows = merged_content.get("data") or []

    # 3. Resolve dataset metadata
    dataset_name = run.dataset_id
    ds_row = db.get(Dataset, run.dataset_id)
    if ds_row:
        dataset_name = getattr(ds_row, "file_name", getattr(ds_row, "name", run.dataset_id))

    report_title = payload.title or f"{dataset_name} — {run.query[:60]}"

    # 4. Build report data dictionary matching ReportGenerator specification
    report_data: dict[str, Any] = {
        "summary": summary,
        "kpis": kpis,
        "insights": [
            f"Analytical Objective: {run.query}",
            f"Dataset Source: {dataset_name} (Version {run.version_number})",
            f"Verified Core Finding: {answer}",
        ],
        "action_items": action_items or ["Review findings and monitor metric distributions in Visualization Studio."],
    }

    if chart and chart.get("points"):
        report_data["chart"] = chart["points"]
        report_data["chart_label"] = chart.get("chart_label", "Observed Units")

    if citations:
        report_data["insights"].append(f"Grounded with {len(citations)} source document citation(s).")

    # 5. Execute report generator through ReportStudioService
    svc = ReportStudioService(storage_dir=REPORT_STUDIO_STORAGE_ROOT)
    provenance = {
        "analysis_run_id": run.id,
        "session_id": payload.session_id,
        "dataset_id": run.dataset_id,
        "dataset_version": run.version_number,
        "workspace_id": str(run.workspace_id),
    }

    try:
        report_record = svc.generate_report(
            title=report_title,
            report_type=payload.report_type or ReportType.EXECUTIVE,
            workspace_id=str(run.workspace_id),
            format_type=payload.format_type or "pdf",
            provenance=provenance,
            report_data=report_data,
        )
    except Exception as exc:
        raise HTTPException(500, f"Report generation failed: {exc}") from exc

    report_record["download_url"] = f"/api/v1/reports/{report_record['id']}/download"
    report_record["dataset_name"] = dataset_name
    report_record["query"] = run.query

    return report_record


@router.get("/reports/{report_id}")
def get_report_record(
    report_id: str,
    user: Any = Depends(get_current_user),
) -> dict[str, Any]:
    """Get stored report manifest by ID."""
    svc = ReportStudioService(storage_dir=REPORT_STUDIO_STORAGE_ROOT)
    report = svc.get_report(report_id)
    if not report:
        raise HTTPException(404, "Report not found")
    report["download_url"] = f"/api/v1/reports/{report_id}/download"
    return report


@router.get("/reports/{report_id}/download")
def download_report_file(
    report_id: str,
    user: Any = Depends(get_current_user),
) -> FileResponse:
    """Download the actual generated binary report document (PDF, DOCX, XLSX, PPTX)."""
    svc = ReportStudioService(storage_dir=REPORT_STUDIO_STORAGE_ROOT)
    report = svc.get_report(report_id)
    if not report:
        raise HTTPException(404, "Report not found")

    fmt = report.get("format", "pdf").lower()
    filename = report.get("filename") or f"{report_id}.{fmt}"
    file_path = REPORT_STUDIO_STORAGE_ROOT / filename

    if not file_path.exists():
        # Check fallback data/reports
        fallback = Path("data/reports") / filename
        if fallback.exists():
            file_path = fallback
        else:
            raise HTTPException(404, f"Report artifact file '{filename}' was not found on storage")

    content_type, _ = mimetypes.guess_type(str(file_path))
    if not content_type:
        content_type = "application/pdf" if fmt == "pdf" else "application/octet-stream"

    return FileResponse(
        path=str(file_path),
        media_type=content_type,
        filename=filename,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
