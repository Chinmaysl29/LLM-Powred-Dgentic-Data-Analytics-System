"""Small bounded HTTP adapter for the verified local Chroma 0.6.3 v2 API.

Explicit numeric embeddings only. No documents, automatic embedder or shared
client/session changes. Existing embedding and Chroma systems remain untouched.
"""
from uuid import UUID

import httpx
from backend.app.core.config import get_settings
from backend.app.learning.memory_contract import DIMENSION, EMBEDDING_VERSION, checked_vector

BASE = "/api/v2/tenants/default_tenant/databases/default_database/collections"
METADATA = {"hnsw:space": "cosine", "embedding_version": EMBEDDING_VERSION, "dimension": DIMENSION}


class MemoryIndex:
    def __enter__(self):
        settings = get_settings()
        self.client = httpx.Client(base_url=httpx.URL(scheme="http", host=settings.chroma_host,
            port=settings.chroma_port), timeout=httpx.Timeout(1.0, pool=0.5), trust_env=False)
        try:
            if self.request("GET", "/api/v2/version") != "0.6.3":
                raise ValueError("Unverified failure-memory protocol")
        except Exception:
            self.client.close()
            raise
        return self

    def __exit__(self, *args):
        self.client.close()

    def request(self, method: str, path: str, body=None):
        with self.client.stream(method, path, json=body) as response:
            response.raise_for_status()
            raw = bytearray()
            for chunk in response.iter_bytes():
                raw.extend(chunk)
                if len(raw) > 1_000_000:
                    raise ValueError("Oversized index response")
        import json
        return json.loads(raw) if raw else None

    def collection(self, tenant_id, *, create=False) -> str:
        name = "perceptron_failures_" + UUID(str(tenant_id)).hex
        result = self.request("POST", BASE, {"name": name, "metadata": METADATA,
            "configuration": None, "get_or_create": True}) if create else self.request("GET", f"{BASE}/{name}")
        if result.get("metadata") != METADATA:
            raise ValueError("Incompatible failure-memory collection")
        return str(UUID(result["id"]))

    def upsert(self, tenant_id, mistake_id, vector: list[float], metadata: dict) -> None:
        checked_vector(vector)
        collection = self.collection(tenant_id, create=True)
        self.request("POST", f"{BASE}/{collection}/upsert", {"ids": [str(mistake_id)],
            "embeddings": [vector], "metadatas": [metadata], "documents": None, "uris": None})

    def query(self, tenant_id, vector: list[float], filters: dict) -> list[str]:
        checked_vector(vector)
        collection = self.collection(tenant_id)
        result = self.request("POST", f"{BASE}/{collection}/query", {"query_embeddings": [vector],
            "n_results": 20, "where": {"$and": [{key: {"$eq": value}} for key, value in filters.items()]},
            "where_document": None, "include": ["distances"]})
        # IDs only. Distances, metadata and instructions from Chroma are never trusted.
        return list(dict.fromkeys(str(UUID(value)) for value in result["ids"][0][:20]))

    def remove(self, tenant_id, mistake_id) -> None:
        collection = self.collection(tenant_id)
        self.request("POST", f"{BASE}/{collection}/delete", {"ids": [str(mistake_id)]})
