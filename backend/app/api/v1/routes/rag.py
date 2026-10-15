"""RAG Pipeline API Endpoints (Phase 5.8)."""

from fastapi import APIRouter, HTTPException, Depends, Request, Response
from backend.app.core.security import get_current_admin, get_current_user
from backend.app.database.postgres import get_db_session
from sqlalchemy.orm import Session, sessionmaker
from backend.app.services.document_indexing_service import DocumentIndexingService

from backend.app.schemas.rag_pipeline import (
    RAGIngestRequest,
    RAGIngestResponse,
    RAGQueryRequest,
    RAGResponse,
)

router = APIRouter(prefix="/rag", tags=["RAG Pipeline"])



@router.post("/ingest", response_model=RAGIngestResponse, summary="Ingest document into RAG pipeline")
def ingest_document(request: RAGIngestRequest, db: Session = Depends(get_db_session), user=Depends(get_current_user)) -> RAGIngestResponse:
    """Queue the authorized stored source; client text never overwrites provenance."""
    index = DocumentIndexingService(sessionmaker(bind=db.get_bind(), expire_on_commit=False))
    job = index.enqueue(request.document_id, user.id, (request.metadata or {}).get('document_version'))
    if job is None:
        raise HTTPException(409, 'Only a stored PDF can be queued for document indexing')
    return RAGIngestResponse(document_id=request.document_id, chunks_created=0, chunks_indexed=0, status=job['status'])


@router.post("/query", response_model=RAGResponse, summary="Query RAG pipeline")
def query_rag(request: RAGQueryRequest, db: Session = Depends(get_db_session), user=Depends(get_current_user)) -> RAGResponse:
    """Query only a server-verified READY document/version in its bound workspace."""
    filters = request.filters or {}
    dataset_id = filters.get('dataset_id') or filters.get('document_id')
    version = filters.get('document_version')
    if not dataset_id or not isinstance(version, int) or isinstance(version, bool) or version < 1:
        raise HTTPException(422, 'Select a document and positive document_version before querying')
    index = DocumentIndexingService(sessionmaker(bind=db.get_bind(), expire_on_commit=False))
    return index.query(str(dataset_id), user.id, version, request.query)


@router.get("/health", summary="RAG pipeline health check")
async def rag_health(request: Request, response: Response):
    from backend.app.api.v1.routes.health import rag_readiness
    return await rag_readiness(request, response)


# -----------------------------------------------------------------------------
# Enterprise RAG Evaluation & Benchmarking (Phase 18.6.2)
# -----------------------------------------------------------------------------

from pydantic import BaseModel, Field
from typing import Any, List, Optional
from backend.rag.rag_evaluation import RAGEvaluationFramework, RAGBenchmark


class EvaluateRAGRequest(BaseModel):
    query: str
    retrieved_chunk_ids: List[str]
    retrieved_texts: List[str]
    relevant_chunk_ids: List[str]
    answer: str
    ground_truth: str = ""
    k: int = 5


class CreateBenchmarkRequest(BaseModel):
    benchmark_id: str = Field(..., description="Unique benchmark ID")
    query: str
    relevant_chunk_ids: List[str]
    ground_truth_answer: str
    category: str = "general"
    metadata: dict[str, Any] = Field(default_factory=dict)


@router.post("/evaluate", dependencies=[Depends(get_current_admin)], summary="Evaluate RAG Retrieval & Generation Quality (Phase 18.6.2)")
def evaluate_rag(request: EvaluateRAGRequest) -> dict[str, Any]:
    """Calculate Precision@K, Recall@K, MRR, NDCG, Context Relevance, Answer Relevance, Groundedness."""
    framework = RAGEvaluationFramework()
    res = framework.evaluate(
        query=request.query,
        retrieved_chunk_ids=request.retrieved_chunk_ids,
        retrieved_texts=request.retrieved_texts,
        relevant_chunk_ids=request.relevant_chunk_ids,
        answer=request.answer,
        ground_truth=request.ground_truth,
        k=request.k,
    )
    return res.to_dict()


@router.get("/eval-history", dependencies=[Depends(get_current_admin)], summary="Get RAG Evaluation History")
def get_rag_eval_history() -> List[dict[str, Any]]:
    """Retrieve full historical evaluations log."""
    framework = RAGEvaluationFramework()
    return framework.load_history()


@router.get("/eval-dashboard", dependencies=[Depends(get_current_admin)], summary="RAG Health & Quality Dashboard (Phase 18.6.2)")
def get_rag_eval_dashboard() -> dict[str, Any]:
    """Summary of RAG quality, average metrics, groundedness, and latest evaluation."""
    framework = RAGEvaluationFramework()
    return framework.health_summary()


@router.get("/benchmarks", dependencies=[Depends(get_current_admin)], summary="List RAG Benchmark Datasets")
def list_rag_benchmarks() -> List[dict[str, Any]]:
    """List all registered RAG benchmark queries and ground truth chunks."""
    framework = RAGEvaluationFramework()
    return framework.load_benchmarks()


@router.post("/benchmarks", dependencies=[Depends(get_current_admin)], summary="Add RAG Benchmark Dataset")
def add_rag_benchmark(request: CreateBenchmarkRequest) -> dict[str, Any]:
    """Register a new ground-truth benchmark item for RAG regression testing."""
    framework = RAGEvaluationFramework()
    bench = RAGBenchmark(
        benchmark_id=request.benchmark_id,
        query=request.query,
        relevant_chunk_ids=request.relevant_chunk_ids,
        ground_truth_answer=request.ground_truth_answer,
        category=request.category,
        metadata=request.metadata,
    )
    framework.add_benchmark(bench)
    return {"status": "created", "benchmark_id": request.benchmark_id}

