"""Natural-language analytics chat API with persistent conversational sessions."""

from __future__ import annotations

from time import perf_counter
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, sessionmaker

from backend.app.core.security import get_current_user
from backend.app.database.postgres import get_db_session
from backend.app.services.analysis_session_service import AnalysisSessionService
from backend.app.services.data_retrieval_service import DataRetrievalService
from backend.app.services.document_indexing_service import DocumentIndexingService
from backend.app.services.intent_classification_service import (
    IntentClassificationService,
    get_intent_classification_service,
)
from backend.app.services.natural_language_analytics import NaturalLanguageAnalyticsService
from backend.app.services.orchestrator_service import OrchestratorService
from backend.app.services.storage_service import StorageService, get_storage_service
from backend.monitoring.prometheus_metrics import platform_metrics

router = APIRouter(prefix="/chat", tags=["Natural Language Analytics"])


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    dataset_id: str | None = None
    dataset_version: int | None = Field(None, ge=1)
    workspace_id: str | None = None
    session_id: str | None = None


class ChatResponse(BaseModel):
    session_id: str | None = None
    run_id: str | None = None
    answer: str
    intent: str
    confidence: float = Field(ge=0, le=1)
    execution_time: float
    data: list[dict[str, Any]] = Field(default_factory=list)
    explanation: str | None = None
    actionable: list[str] = Field(default_factory=list)
    status: str = "complete"
    plan: dict[str, Any] | None = None
    chart: dict[str, Any] | None = None
    kpis: dict[str, Any] | None = None
    citations: list[dict[str, Any]] = Field(default_factory=list)


@router.post("", response_model=ChatResponse)
async def chat(
    payload: ChatRequest,
    request: Request,
    intent_service: IntentClassificationService = Depends(get_intent_classification_service),
    db: Session | None = Depends(get_db_session),
    storage: StorageService = Depends(get_storage_service),
    current_user: Any = Depends(get_current_user),
) -> ChatResponse:
    started = perf_counter()

    # 1. Resolve or initialize persistent session
    session_uuid: UUID | None = None
    workspace_uuid: UUID | None = None
    if payload.workspace_id:
        try:
            workspace_uuid = UUID(payload.workspace_id)
        except (ValueError, TypeError):
            pass

    if db is not None:
        if payload.session_id:
            try:
                session_uuid = UUID(payload.session_id)
            except (ValueError, TypeError):
                session_uuid = None

        if not session_uuid:
            sess_info = AnalysisSessionService.create_session(
                db=db,
                user_id=current_user.id,
                title=payload.message[:80],
                workspace_id=workspace_uuid,
                dataset_id=payload.dataset_id,
                dataset_version=payload.dataset_version,
            )
            session_uuid = UUID(sess_info["session_id"])

    # 2. Retrieve conversation context for follow-up questions
    context: list[dict[str, str]] = []
    if db is not None and session_uuid:
        context = AnalysisSessionService.get_conversation_context(
            db, session_uuid, current_user.id, limit_turns=5
        )

    # 3. Execute analytical query or RAG
    data_retrieval = DataRetrievalService(db, storage, owner_id=str(current_user.id)) if db is not None else None
    analytics = NaturalLanguageAnalyticsService(data_retrieval)
    citations: list[dict[str, Any]] = []

    # Check if dataset is an indexed document (PDF, TXT, MD)
    is_doc = False
    if db is not None and payload.dataset_id and data_retrieval:
        try:
            _, version, _, file_type, _ = data_retrieval.discover(payload.dataset_id, payload.dataset_version)
            if file_type in ("pdf", "txt", "md"):
                is_doc = True
                doc_svc = DocumentIndexingService(sessionmaker(bind=db.get_bind(), expire_on_commit=False))
                rag_out = doc_svc.query(payload.dataset_id, current_user.id, version.version_number, payload.message)
                citations = rag_out.get("sources", [])
                result = {
                    "answer": rag_out.get("summary") or "Retrieved relevant evidence from document.",
                    "data": [],
                    "explanation": f"Retrieved {len(citations)} source citations from document index.",
                    "actionable": [],
                    "status": "complete",
                    "citations": citations,
                }
                intent = "rag_search"
                confidence = 0.95
        except Exception:
            is_doc = False

    if not is_doc:
        if analytics.is_analytics_query(payload.message) and payload.dataset_id:
            result = await analytics.analyze(
                payload.message,
                dataset_id=payload.dataset_id,
                dataset_version=payload.dataset_version,
                context=context,
            )
            intent = "analytics"
            confidence = 0.0 if result.get("status") == "clarification_required" else 1.0
        elif analytics.is_analytics_query(payload.message):
            result = await analytics.analyze(payload.message, context=context)
            intent, confidence = "analytics", 0.0
        else:
            classification = await intent_service.classify(payload.message, dataset_id=payload.dataset_id)
            orchestrator = OrchestratorService(intent_classifier=intent_service, db=db, owner_id=str(current_user.id))
            outcome = await orchestrator.execute(payload.message, dataset_id=payload.dataset_id)
            result = {
                "answer": outcome.summary,
                "data": [],
                "explanation": "Processed through the configured analytics workflow.",
                "actionable": [],
            }
            intent, confidence = outcome.intent, classification.confidence

    if citations and "citations" not in result:
        result["citations"] = citations

    exec_time = round(perf_counter() - started, 4)
    result["execution_time"] = exec_time
    result["intent"] = intent
    result["confidence"] = confidence

    # 4. Persist turn and create durable AnalysisRun
    run_id: str | None = None
    if db is not None and session_uuid:
        turn_record = AnalysisSessionService.record_turn(
            db=db,
            session_id=session_uuid,
            user_id=current_user.id,
            question=payload.message,
            result=result,
            workspace_id=workspace_uuid,
            dataset_id=payload.dataset_id,
            dataset_version=payload.dataset_version,
        )
        run_id = turn_record.get("run_id")

    platform_metrics.record_agent_execution("natural_language_analytics", result.get("status", "complete"))

    return ChatResponse(
        session_id=str(session_uuid) if session_uuid else None,
        run_id=run_id,
        answer=result.get("answer", ""),
        intent=intent,
        confidence=confidence,
        execution_time=exec_time,
        data=result.get("data", []),
        explanation=result.get("explanation"),
        actionable=result.get("actionable", []),
        status=result.get("status", "complete"),
        plan=result.get("plan"),
        chart=result.get("chart"),
        kpis=result.get("kpis"),
        citations=result.get("citations", []),
    )
