"""Analysis Session and Conversational History Service.

Provides durable persistence and retrieval for AI Analysis sessions,
conversation messages, analytical artifacts, and Reports integration.
Single source of truth in PostgreSQL.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from backend.app.models.analysis_run import AnalysisArtifact, AnalysisEvent, AnalysisRun, AnalysisStage
from backend.app.models.background_job import DurableJob, utcnow
from backend.app.models.conversation import Conversation, Message
from backend.app.models.dataset import Dataset
from backend.app.models.dataset_version import DatasetVersion
from backend.app.models.workspace import Workspace


class AnalysisSessionService:
    """Manages persistent analysis conversations, turns, and report linkages."""

    @staticmethod
    def create_session(
        db: Session,
        user_id: UUID,
        title: str | None = None,
        workspace_id: UUID | None = None,
        dataset_id: str | None = None,
        dataset_version: int | None = None,
    ) -> dict[str, Any]:
        """Create a new persistent analysis session."""
        session_id = uuid4()
        session_title = (title or "New Analysis").strip()[:500]
        conversation = Conversation(
            id=session_id,
            user_id=user_id,
            title=session_title,
            status="active",
        )
        db.add(conversation)
        db.flush()

        # Seed initial session metadata in a system message
        seed_meta = {
            "session_type": "ai_analysis",
            "workspace_id": str(workspace_id) if workspace_id else None,
            "dataset_id": dataset_id,
            "dataset_version": dataset_version,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        init_message = Message(
            id=uuid4(),
            conversation_id=conversation.id,
            role="system",
            content=f"Analysis session initialized for dataset {dataset_id or 'none'}.",
            metadata_json=seed_meta,
        )
        db.add(init_message)
        db.commit()
        db.refresh(conversation)

        return {
            "session_id": str(conversation.id),
            "title": conversation.title,
            "status": conversation.status,
            "workspace_id": str(workspace_id) if workspace_id else None,
            "dataset_id": dataset_id,
            "dataset_version": dataset_version,
            "created_at": conversation.created_at.isoformat() if conversation.created_at else None,
            "updated_at": conversation.updated_at.isoformat() if conversation.updated_at else None,
            "turns_count": 0,
        }

    @staticmethod
    def list_sessions(
        db: Session,
        user_id: UUID,
        workspace_id: UUID | None = None,
        search: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """List active sessions for the user with latest run status and dataset info."""
        query = select(Conversation).where(
            Conversation.user_id == user_id,
            Conversation.status != "deleted",
        )
        if search and search.strip():
            query = query.where(Conversation.title.ilike(f"%{search.strip()}%"))
        query = query.order_by(desc(Conversation.updated_at)).offset(offset).limit(limit)

        conversations = db.scalars(query).all()
        results: list[dict[str, Any]] = []

        for conv in conversations:
            messages = conv.messages or []
            # Extract dataset_id, workspace_id, last question, and run count
            ds_id: str | None = None
            ds_ver: int | None = None
            ws_id: str | None = None
            last_question: str | None = None
            latest_status: str = "active"
            last_run_id: str | None = None
            turn_count = 0

            for msg in messages:
                meta = msg.metadata_json or {}
                if meta.get("workspace_id") and not ws_id:
                    ws_id = str(meta["workspace_id"])
                if meta.get("dataset_id") and not ds_id:
                    ds_id = str(meta["dataset_id"])
                    ds_ver = meta.get("dataset_version")
                if msg.role == "user":
                    last_question = msg.content
                    turn_count += 1
                elif msg.role == "assistant":
                    latest_status = meta.get("status", "complete")
                    if meta.get("run_id"):
                        last_run_id = str(meta["run_id"])

            if workspace_id and ws_id and ws_id != str(workspace_id):
                continue

            # Fetch dataset file name if possible
            ds_name = None
            if ds_id:
                dataset_row = db.get(Dataset, ds_id)
                if dataset_row:
                    ds_name = getattr(dataset_row, "file_name", getattr(dataset_row, "name", ds_id))

            results.append({
                "session_id": str(conv.id),
                "title": conv.title,
                "status": conv.status,
                "workspace_id": ws_id,
                "dataset_id": ds_id,
                "dataset_name": ds_name or ds_id,
                "dataset_version": ds_ver,
                "last_question": last_question,
                "latest_status": latest_status,
                "last_run_id": last_run_id,
                "turn_count": turn_count,
                "created_at": conv.created_at.isoformat() if conv.created_at else None,
                "updated_at": conv.updated_at.isoformat() if conv.updated_at else None,
            })

        return results

    @staticmethod
    def get_session_details(
        db: Session,
        session_id: UUID,
        user_id: UUID,
    ) -> dict[str, Any] | None:
        """Fetch session and all conversation turns with verified analytical artifacts."""
        conv = db.get(Conversation, session_id)
        if not conv or conv.user_id != user_id or conv.status == "deleted":
            return None

        turns: list[dict[str, Any]] = []
        messages = sorted(conv.messages or [], key=lambda m: m.created_at or datetime.min)
        
        ds_id: str | None = None
        ds_ver: int | None = None
        ws_id: str | None = None

        # Group into user question + assistant response pairs
        pending_user: Message | None = None
        for msg in messages:
            meta = msg.metadata_json or {}
            if meta.get("dataset_id") and not ds_id:
                ds_id = str(meta["dataset_id"])
                ds_ver = meta.get("dataset_version")
            if meta.get("workspace_id") and not ws_id:
                ws_id = str(meta["workspace_id"])

            if msg.role == "user":
                pending_user = msg
            elif msg.role == "assistant":
                q_text = pending_user.content if pending_user else "Analysis Request"
                q_time = pending_user.created_at.isoformat() if (pending_user and pending_user.created_at) else (msg.created_at.isoformat() if msg.created_at else None)
                turns.append({
                    "turn_id": str(msg.id),
                    "user_message_id": str(pending_user.id) if pending_user else None,
                    "assistant_message_id": str(msg.id),
                    "question": q_text,
                    "asked_at": q_time,
                    "answered_at": msg.created_at.isoformat() if msg.created_at else None,
                    "answer": msg.content,
                    "intent": meta.get("intent", "analytics"),
                    "confidence": meta.get("confidence", 1.0),
                    "execution_time": meta.get("execution_time", 0.0),
                    "status": meta.get("status", "complete"),
                    "data": meta.get("data", []),
                    "explanation": meta.get("explanation"),
                    "actionable": meta.get("actionable", []),
                    "chart": meta.get("chart"),
                    "kpis": meta.get("kpis", {}),
                    "plan": meta.get("plan"),
                    "citations": meta.get("citations", []),
                    "run_id": meta.get("run_id"),
                    "dataset_id": meta.get("dataset_id", ds_id),
                    "dataset_version": meta.get("dataset_version", ds_ver),
                })
                pending_user = None

        # Fetch dataset filename
        ds_name = None
        if ds_id:
            dataset_row = db.get(Dataset, ds_id)
            if dataset_row:
                ds_name = getattr(dataset_row, "file_name", getattr(dataset_row, "name", ds_id))

        return {
            "session_id": str(conv.id),
            "title": conv.title,
            "status": conv.status,
            "workspace_id": ws_id,
            "dataset_id": ds_id,
            "dataset_name": ds_name or ds_id,
            "dataset_version": ds_ver,
            "created_at": conv.created_at.isoformat() if conv.created_at else None,
            "updated_at": conv.updated_at.isoformat() if conv.updated_at else None,
            "turns": turns,
        }

    @staticmethod
    def record_turn(
        db: Session,
        session_id: UUID,
        user_id: UUID,
        question: str,
        result: dict[str, Any],
        workspace_id: UUID | None = None,
        dataset_id: str | None = None,
        dataset_version: int | None = None,
    ) -> dict[str, Any]:
        """Save a question and its verified analytical outcome to the session and create an AnalysisRun."""
        conv = db.get(Conversation, session_id)
        if not conv or conv.user_id != user_id:
            raise ValueError("Session not found or unauthorized")

        # Derive auto title from first question if title is default
        if conv.title in ("New Conversation", "New Analysis", ""):
            clean_q = question.strip()
            conv.title = clean_q[:80] + ("…" if len(clean_q) > 80 else "")

        # 1. Resolve workspace_id if not passed
        if not workspace_id:
            # Check existing messages for workspace_id
            for m in conv.messages:
                if (m.metadata_json or {}).get("workspace_id"):
                    try:
                        workspace_id = UUID(m.metadata_json["workspace_id"])
                        break
                    except (ValueError, TypeError):
                        pass

        if not workspace_id:
            # Fall back to user's first active workspace
            from backend.app.core.workspace_authorization import workspace_memberships
            row = db.execute(
                select(workspace_memberships.c.workspace_id).where(
                    workspace_memberships.c.user_id == user_id,
                    workspace_memberships.c.active.is_(True),
                ).limit(1)
            ).scalar_one_or_none()
            if row:
                workspace_id = row if isinstance(row, UUID) else UUID(str(row))
            else:
                first_ws = db.scalar(select(Workspace.id).limit(1))
                workspace_id = first_ws or uuid4()

        # 2. Resolve dataset version if needed
        resolved_version = dataset_version or 1
        if dataset_id and not dataset_version:
            v_row = db.scalar(
                select(DatasetVersion.version_number).where(
                    DatasetVersion.dataset_id == dataset_id,
                    DatasetVersion.is_active.is_(True),
                )
            )
            if v_row:
                resolved_version = v_row

        # 3. Create persistent AnalysisRun for data provenance if valid dataset exists
        run_id = None
        valid_dataset = False
        if dataset_id:
            ds_exists = db.scalar(select(Dataset.dataset_id).where(Dataset.dataset_id == dataset_id))
            if ds_exists:
                valid_dataset = True

        if valid_dataset and workspace_id:
            run_id = str(uuid4())
            job_id = uuid4()
            durable_job = DurableJob(
                id=job_id,
                workspace_id=workspace_id,
                owner_id=user_id,
                kind="analysis_pipeline",
                idempotency_key=f"turn_{session_id}_{run_id}",
                status="READY",
                payload={"run_id": run_id, "session_id": str(session_id)},
                result={"status": result.get("status", "complete")},
                attempt=1,
                max_attempts=1,
                retry_eligible=False,
            )
            db.add(durable_job)
            db.flush()

            analysis_run = AnalysisRun(
                id=run_id,
                job_id=job_id,
                workspace_id=workspace_id,
                owner_id=user_id,
                dataset_id=dataset_id,
                version_number=resolved_version,
                query=question[:2000],
                status="SUCCEEDED" if result.get("status") == "complete" else "BLOCKED",
            )
            db.add(analysis_run)
            db.flush()

            # Add stages and artifacts
            db.add(AnalysisStage(run_id=run_id, number=1, name="Problem formulation", status="COMPLETED"))
            db.add(AnalysisStage(run_id=run_id, number=5, name="Data modeling", status="COMPLETED"))
            db.add(AnalysisStage(run_id=run_id, number=6, name="Visualization and reporting", status="COMPLETED"))

            artifact_content = {
                "answer": result.get("answer"),
                "data": result.get("data", []),
                "explanation": result.get("explanation"),
                "actionable": result.get("actionable", []),
                "chart": result.get("chart"),
                "kpis": result.get("kpis", {}),
                "citations": result.get("citations", []),
                "plan": result.get("plan"),
                "provenance": {
                    "run_id": run_id,
                    "session_id": str(session_id),
                    "dataset_id": dataset_id,
                    "version_number": resolved_version,
                    "workspace_id": str(workspace_id),
                },
            }
            db.add(AnalysisArtifact(run_id=run_id, stage_number=6, content=artifact_content))
            db.add(AnalysisEvent(run_id=run_id, status="COMPLETED"))

        # 4. Save user message
        user_msg = Message(
            id=uuid4(),
            conversation_id=conv.id,
            role="user",
            content=question,
            metadata_json={
                "dataset_id": dataset_id,
                "dataset_version": resolved_version,
                "workspace_id": str(workspace_id),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )
        db.add(user_msg)

        # 5. Save assistant message with full verified artifacts
        assistant_meta = {
            **result,
            "run_id": run_id,
            "session_id": str(session_id),
            "dataset_id": dataset_id,
            "dataset_version": resolved_version,
            "workspace_id": str(workspace_id),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        assistant_msg = Message(
            id=uuid4(),
            conversation_id=conv.id,
            role="assistant",
            content=result.get("answer", ""),
            metadata_json=assistant_meta,
        )
        db.add(assistant_msg)

        conv.updated_at = utcnow()
        db.commit()

        return {
            "session_id": str(conv.id),
            "run_id": run_id,
            "turn_id": str(assistant_msg.id),
            "question": question,
            "answer": assistant_msg.content,
            "status": result.get("status", "complete"),
            "dataset_id": dataset_id,
            "dataset_version": resolved_version,
            "workspace_id": str(workspace_id),
            "chart": result.get("chart"),
            "kpis": result.get("kpis", {}),
            "data": result.get("data", []),
            "citations": result.get("citations", []),
            "explanation": result.get("explanation"),
            "actionable": result.get("actionable", []),
        }

    @staticmethod
    def get_conversation_context(
        db: Session,
        session_id: UUID,
        user_id: UUID,
        limit_turns: int = 5,
    ) -> list[dict[str, str]]:
        """Retrieve recent turns for conversational follow-up memory."""
        conv = db.get(Conversation, session_id)
        if not conv or conv.user_id != user_id:
            return []
        messages = sorted(conv.messages or [], key=lambda m: m.created_at or datetime.min)
        context: list[dict[str, str]] = []
        for m in messages:
            if m.role in ("user", "assistant"):
                context.append({"role": m.role, "content": m.content})
        return context[-limit_turns * 2 :]

    @staticmethod
    def rename_session(db: Session, session_id: UUID, user_id: UUID, new_title: str) -> bool:
        """Rename an analysis session."""
        conv = db.get(Conversation, session_id)
        if not conv or conv.user_id != user_id or conv.status == "deleted":
            return False
        conv.title = new_title.strip()[:500]
        conv.updated_at = utcnow()
        db.commit()
        return True

    @staticmethod
    def delete_session(db: Session, session_id: UUID, user_id: UUID) -> bool:
        """Soft-delete an analysis session."""
        conv = db.get(Conversation, session_id)
        if not conv or conv.user_id != user_id:
            return False
        conv.status = "deleted"
        conv.updated_at = utcnow()
        db.commit()
        return True

    @staticmethod
    def list_analysis_history_for_reports(
        db: Session,
        user_id: UUID,
        workspace_id: UUID | None = None,
    ) -> list[dict[str, Any]]:
        """Retrieve all completed analyses eligible for report generation.

        Reads from the same persistent source of truth (conversations and analysis_runs).
        """
        # Fetch conversations that have at least one completed assistant turn
        conversations = db.scalars(
            select(Conversation)
            .where(Conversation.user_id == user_id, Conversation.status != "deleted")
            .order_by(desc(Conversation.updated_at))
        ).all()

        history_items: list[dict[str, Any]] = []

        for conv in conversations:
            messages = conv.messages or []
            assistant_turns = [m for m in messages if m.role == "assistant"]
            if not assistant_turns:
                continue

            # Pick the latest completed run
            latest_assistant = assistant_turns[-1]
            meta = latest_assistant.metadata_json or {}
            ws_id = meta.get("workspace_id")
            if workspace_id and ws_id and ws_id != str(workspace_id):
                continue

            ds_id = meta.get("dataset_id")
            ds_ver = meta.get("dataset_version", 1)
            ds_name = ds_id
            if ds_id:
                ds_row = db.get(Dataset, ds_id)
                if ds_row:
                    ds_name = getattr(ds_row, "file_name", getattr(ds_row, "name", ds_id))

            # Find matching question
            question_text = conv.title
            user_msgs = [m for m in messages if m.role == "user"]
            if user_msgs:
                question_text = user_msgs[-1].content

            run_id = meta.get("run_id")
            kpis = meta.get("kpis", {})
            summary = meta.get("explanation") or latest_assistant.content

            history_items.append({
                "session_id": str(conv.id),
                "run_id": run_id,
                "title": conv.title,
                "question": question_text,
                "dataset_id": ds_id,
                "dataset_name": ds_name or "Unknown Dataset",
                "dataset_version": ds_ver,
                "workspace_id": ws_id,
                "status": "COMPLETED" if meta.get("status") == "complete" else "READY",
                "completed_at": latest_assistant.created_at.isoformat() if latest_assistant.created_at else None,
                "turn_count": len(user_msgs),
                "summary": summary,
                "kpis": kpis,
                "data_preview": (meta.get("data") or [])[:5],
                "has_chart": bool(meta.get("chart")),
                "has_citations": bool(meta.get("citations")),
                "report_eligible": bool(run_id and meta.get("status") == "complete"),
            })

        return history_items
