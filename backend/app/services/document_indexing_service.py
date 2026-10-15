"""Durable document indexing on the existing job manager and RAG pipeline."""
import hashlib
from pathlib import Path
from uuid import UUID
from sqlalchemy import select
from fastapi import HTTPException
from backend.app.core.authorization import owned_dataset
from backend.app.core.workspace_authorization import authorize_workspace, authorize_bound_dataset, dataset_workspace_bindings
from backend.app.models.background_job import DurableJob
from backend.app.models.dataset_version import DatasetVersion
from backend.app.core.config import get_settings
from backend.jobs.persistence import PersistentJobStore
from backend.app.schemas.rag_pipeline import RAGIngestRequest, RAGQueryRequest


class DocumentSourceError(ValueError):
    def __init__(self, code):
        self.error_code = code
        super().__init__(code)


class DocumentIndexingService:
    def __init__(self, session_factory):
        self.sessions = session_factory
        self.jobs = PersistentJobStore(session_factory)

    @staticmethod
    def resource(db, dataset_id, owner_id, version=None, require_workspace=True):
        dataset = owned_dataset(db, dataset_id, str(owner_id))
        query = select(DatasetVersion).where(DatasetVersion.dataset_id == dataset_id)
        query = query.where(DatasetVersion.version_number == version) if version else query.where(DatasetVersion.is_active.is_(True))
        selected = db.scalar(query)
        if selected is None:
            raise HTTPException(404, 'Dataset version not found')
        workspace = db.scalar(select(dataset_workspace_bindings.c.workspace_id).where(dataset_workspace_bindings.c.dataset_id == dataset_id))
        if workspace:
            access = authorize_workspace(db, owner_id, workspace)
            authorize_bound_dataset(db, access, dataset_id)
        elif require_workspace:
            raise HTTPException(409, 'Select an authorized workspace before indexing')
        return dataset, selected, workspace

    def enqueue(self, dataset_id, owner_id, version=None):
        with self.sessions() as db:
            dataset, selected, workspace = self.resource(db, dataset_id, owner_id, version)
            authorize_workspace(db, owner_id, workspace, 'write')
            if dataset.file_type.lower() not in {'pdf', 'txt', 'text', 'md', 'markdown'}:
                return None
            storage = StorageService(get_settings())
            path = storage.retrieve_file(selected.storage_path)
            checksum = hashlib.sha256(path.read_bytes()).hexdigest()
            payload = {'dataset_id': dataset_id, 'document_id': dataset_id,
                       'dataset_version': selected.version_number, 'source_checksum': checksum,
                       'embedding_model': 'sentence-transformers/all-MiniLM-L6-v2'}
            key = hashlib.sha256(f'{dataset_id}:{selected.version_number}:{checksum}'.encode()).hexdigest()
        return self.jobs.create(workspace_id=workspace, owner_id=owner_id, kind='rag', key=key, payload=payload)

    def state(self, dataset_id, owner_id, version=None):
        with self.sessions() as db:
            dataset, selected, workspace = self.resource(db, dataset_id, owner_id, version, require_workspace=False)
            job = db.scalar(select(DurableJob).where(DurableJob.owner_id == UUID(str(owner_id)),
                DurableJob.workspace_id == workspace, DurableJob.kind == 'rag',
                DurableJob.payload['dataset_id'].as_string() == dataset_id,
                DurableJob.payload['dataset_version'].as_integer() == selected.version_number)
                .order_by(DurableJob.created_at.desc())) if workspace else None
            return {'status': job.status if job else ('UPLOADED' if dataset.file_type.lower() in {'pdf', 'txt', 'text', 'md', 'markdown'} else 'NOT_APPLICABLE'),
                    'job_id': str(job.id) if job else None, 'dataset_version': selected.version_number,
                    'workspace_id': str(workspace) if workspace else None,
                    'attempt': job.attempt if job else 0,
                    'retry_eligible': bool(job and job.status == 'FAILED' and job.retry_eligible and job.attempt < job.max_attempts),
                    'error_code': job.error_code if job else None,
                    'indexed_chunk_count': (job.result or {}).get('indexed_chunk_count', 0) if job else 0}

    @staticmethod
    def pipeline(owner_id, workspace_id):
        from backend.rag.rag_pipeline import RAGPipeline
        from backend.rag.vectorstores.chromadb_store import ChromaDBStore
        settings = get_settings()
        owner, workspace = UUID(str(owner_id)), UUID(str(workspace_id))
        scope = hashlib.sha256(f'{owner}:{workspace}'.encode()).hexdigest()[:32]
        store = ChromaDBStore(collection_name=f'rag_scope_{scope}', host=settings.chroma_host, port=settings.chroma_port,
                              embedding_model='sentence-transformers/all-MiniLM-L6-v2', expected_dimension=384)
        sparse = Path(settings.upload_dir) / 'embeddings' / owner.hex / workspace.hex / 'sparse.sqlite'
        return RAGPipeline(vector_store=store, sparse_index_path=sparse), store

    def execute(self, job, progress):
        payload = job['payload']
        with self.sessions() as db:
            dataset, version, workspace = self.resource(db, payload['dataset_id'], job['owner_id'], payload['dataset_version'])
            authorize_workspace(db, job['owner_id'], workspace, 'write')
            if workspace != job['workspace_id']:
                raise PermissionError('Job workspace no longer matches source')
            storage = StorageService(get_settings())
            source = storage.retrieve_file(version.storage_path)
            raw = source.read_bytes()
            filename = dataset.file_name
        if hashlib.sha256(raw).hexdigest() != payload['source_checksum']:
            raise DocumentSourceError('SOURCE_CHECKSUM_CHANGED')
        progress('EXTRACTING')
        content = self.extract_text(raw)
        pipeline, store = self.pipeline(job['owner_id'], workspace)
        response = pipeline.ingest(RAGIngestRequest(document_id=payload['dataset_id'], content=content,
            metadata={'dataset_id': payload['dataset_id'], 'document_version': payload['dataset_version'],
                      'workspace_id': str(workspace), 'source_checksum': payload['source_checksum'],
                      'file_name': filename, 'embedding_model': payload['embedding_model']}), progress=progress)
        filters = {'document_id': payload['dataset_id'], 'document_version': payload['dataset_version'],
                   'workspace_id': str(workspace)}
        dense = store._collection.get(where={'$and': [{key: {'$eq': value}} for key, value in filters.items()]}, include=['metadatas'])
        if len(dense['ids']) != response.chunks_indexed or response.chunks_indexed <= 0:
            raise RuntimeError('Index verification failed')
        return {'indexed_chunk_count': response.chunks_indexed, 'collection_id': str(store._collection.id),
                'embedding_model': payload['embedding_model'], 'dataset_version': payload['dataset_version'],
                'source_checksum': payload['source_checksum']}

    @staticmethod
    def extract_text(raw):
        if raw.startswith(b"%PDF"):
            from io import BytesIO
            from pypdf import PdfReader
            from pypdf.errors import PdfReadError
            try:
                reader = PdfReader(BytesIO(raw))
                if reader.is_encrypted:
                    raise DocumentSourceError('PDF_ENCRYPTED')
                content = '\n\n'.join(page.extract_text() or '' for page in reader.pages)
            except PdfReadError as exc:
                raise DocumentSourceError('PDF_INVALID') from exc
            if not content.strip():
                raise DocumentSourceError('PDF_NO_EXTRACTABLE_TEXT')
            return content
        else:
            try:
                content = raw.decode("utf-8")
            except UnicodeDecodeError:
                content = raw.decode("latin-1", errors="replace")
            if not content.strip():
                raise DocumentSourceError('DOCUMENT_NO_EXTRACTABLE_TEXT')
            return content

    def query(self, dataset_id, owner_id, version, query):
        state = self.state(dataset_id, owner_id, version)
        if state['status'] != 'READY':
            raise HTTPException(409, 'Document is not search ready')
        pipeline, _ = self.pipeline(owner_id, state['workspace_id'])
        result = pipeline.query(RAGQueryRequest(query=query, use_hybrid=True,
            filters={'document_id': dataset_id, 'document_version': state['dataset_version'], 'workspace_id': state['workspace_id']}))
        response = result.model_dump()
        for source in response['sources']:
            source['citation_url'] = f'/api/v1/datasets/{dataset_id}/source?version={state["dataset_version"]}'
        response['dataset_version'] = state['dataset_version']
        response['workspace_id'] = state['workspace_id']
        response['answer_mode'] = 'retrieved_evidence'  # No pretend LLM synthesis.
        return response
