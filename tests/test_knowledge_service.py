from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

from pymilvus import DataType

import tools.rag.service as rag_service
from common.config import settings
from common.knowledge_registry import KnowledgeRegistry, KnowledgeRegistryPaths
from tools.rag.file_parser import ParsedKnowledgeDocument
from tools.rag.service import KnowledgeMilvusStore, KnowledgeService, RagEmbeddingClient


class _FakeObjectStore:
    def __init__(self) -> None:
        self.uploaded: dict[str, object] | None = None

    def is_configured(self) -> bool:
        return True

    def upload_bytes(
        self,
        *,
        file_id: str,
        filename: str,
        content_type: str,
        data: bytes,
    ) -> tuple[str, str]:
        self.uploaded = {
            "file_id": file_id,
            "filename": filename,
            "content_type": content_type,
            "data": data,
        }
        return "weaver-knowledge", f"knowledge/{file_id}/{filename}"

    def download_bytes(self, *, bucket: str, object_key: str) -> bytes:
        return b""


class _FakeEmbeddingClient:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def is_configured(self) -> bool:
        return True

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        return [[0.1, 0.2] for _ in texts]


class _FakeMilvusStore:
    def __init__(self) -> None:
        self.dimension: int | None = None
        self.inserted_chunks: list[dict[str, object]] = []
        self.search_hits: list[dict[str, object]] = []

    def is_configured(self) -> bool:
        return True

    def ensure_collection(self, *, dimension: int) -> None:
        self.dimension = dimension

    def insert_chunks(self, chunks: list[dict[str, object]]) -> None:
        self.inserted_chunks = list(chunks)

    def search(self, *, query_vector: list[float], limit: int) -> list[dict[str, object]]:
        return list(self.search_hits)


class _FakeSchemaBuilder:
    def __init__(self, *, auto_id: bool, enable_dynamic_field: bool) -> None:
        self.auto_id = auto_id
        self.enable_dynamic_field = enable_dynamic_field
        self.fields: list[dict[str, object]] = []

    def add_field(self, *, field_name: str, datatype, **kwargs) -> None:
        self.fields.append(
            {
                "field_name": field_name,
                "datatype": datatype,
                "kwargs": kwargs,
            }
        )


class _FakeIndexParams:
    def __init__(self) -> None:
        self.indexes: list[dict[str, object]] = []

    def add_index(self, **kwargs) -> None:
        self.indexes.append(kwargs)


class _FakeMilvusClient:
    def __init__(self, *, exists: bool = True, vector_dim: int = 1024, enable_dynamic_field: bool = True) -> None:
        self.exists = exists
        self.vector_dim = vector_dim
        self.enable_dynamic_field = enable_dynamic_field
        self.created_schema: _FakeSchemaBuilder | None = None
        self.created_index_params: _FakeIndexParams | None = None
        self.insert_payload: list[dict[str, object]] | None = None
        self.search_kwargs: dict[str, object] | None = None

    def has_collection(self, *, collection_name: str) -> bool:
        return self.exists

    def describe_collection(self, collection_name: str) -> dict[str, object]:
        return {
            "collection_name": collection_name,
            "enable_dynamic_field": self.enable_dynamic_field,
            "fields": [
                {
                    "name": "chunk_id",
                    "type": DataType.VARCHAR,
                    "params": {"max_length": 128},
                    "is_primary": True,
                },
                {
                    "name": "embedding",
                    "type": DataType.FLOAT_VECTOR,
                    "params": {"dim": self.vector_dim},
                },
            ],
        }

    def create_schema(self, *, auto_id: bool, enable_dynamic_field: bool) -> _FakeSchemaBuilder:
        self.created_schema = _FakeSchemaBuilder(
            auto_id=auto_id,
            enable_dynamic_field=enable_dynamic_field,
        )
        return self.created_schema

    def prepare_index_params(self) -> _FakeIndexParams:
        self.created_index_params = _FakeIndexParams()
        return self.created_index_params

    def create_collection(self, *, collection_name: str, schema: _FakeSchemaBuilder, index_params: _FakeIndexParams) -> None:
        self.exists = True
        self.created_schema = schema
        self.created_index_params = index_params

    def insert(self, *, collection_name: str, data: list[dict[str, object]]) -> None:
        self.insert_payload = list(data)

    def search(self, *, collection_name: str, data: list[list[float]], limit: int, output_fields: list[str], anns_field: str):
        self.search_kwargs = {
            "collection_name": collection_name,
            "data": data,
            "limit": limit,
            "output_fields": output_fields,
            "anns_field": anns_field,
        }
        return [[{"id": "kf_1:1", "distance": 0.9, "entity": {"chunk_id": "kf_1:1", "text": "result"}}]]


def test_ingest_file_uploads_original_bytes_to_object_storage_and_indexes_chunks(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "knowledge_milvus_collection", "knowledge_chunks", raising=False)

    registry = KnowledgeRegistry(
        KnowledgeRegistryPaths(root=tmp_path, file=Path(tmp_path) / "knowledge_files.json")
    )
    object_store = _FakeObjectStore()
    embedding_client = _FakeEmbeddingClient()
    milvus_store = _FakeMilvusStore()

    monkeypatch.setattr(
        rag_service,
        "parse_uploaded_file",
        lambda data, filename, content_type="": ParsedKnowledgeDocument(
            text="Alpha paragraph.\n\nBeta paragraph.",
            parser_name="txt",
            metadata={"source": "unit-test"},
        ),
    )
    monkeypatch.setattr(
        rag_service,
        "split_into_passages",
        lambda text, max_chars: [
            {"text": "Alpha paragraph with enough content.", "start_char": 0, "end_char": 36, "heading": "Alpha"},
            {"text": "Beta paragraph with enough content.", "start_char": 37, "end_char": 72, "heading": "Beta"},
        ],
    )

    service = KnowledgeService(
        registry=registry,
        object_store=object_store,
        embedding_client=embedding_client,
        milvus_store=milvus_store,
    )
    payload = b"original knowledge payload"

    record = service.ingest_file(
        filename="../../private/guide.txt",
        content_type="text/plain",
        data=payload,
    )

    assert object_store.uploaded is not None
    assert object_store.uploaded["data"] == payload
    assert object_store.uploaded["filename"] == "guide.txt"
    assert record.filename == "guide.txt"
    assert record.bucket == "weaver-knowledge"
    assert record.object_key == f"knowledge/{record.id}/guide.txt"
    assert record.status == "indexed"
    assert record.chunk_count == 2
    assert record.metadata == {"source": "unit-test"}
    assert embedding_client.calls == [["Alpha paragraph with enough content.", "Beta paragraph with enough content."]]
    assert milvus_store.dimension == 2
    assert [chunk["filename"] for chunk in milvus_store.inserted_chunks] == ["guide.txt", "guide.txt"]
    assert [chunk["chunk_id"] for chunk in milvus_store.inserted_chunks] == [f"{record.id}:1", f"{record.id}:2"]
    assert [chunk["bucket"] for chunk in milvus_store.inserted_chunks] == ["weaver-knowledge", "weaver-knowledge"]
    assert registry.get_record(record.id) == record


def test_search_prefers_entity_chunk_id_when_hit_id_is_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "knowledge_milvus_collection", "knowledge_chunks", raising=False)
    monkeypatch.setattr(settings, "knowledge_search_top_k", 4, raising=False)

    registry = KnowledgeRegistry(
        KnowledgeRegistryPaths(root=tmp_path, file=Path(tmp_path) / "knowledge_files.json")
    )
    registry.upsert_record(
        rag_service.KnowledgeFileRecord(
            id="kf_1",
            filename="guide.txt",
            status="indexed",
            download_path="/api/knowledge/files/kf_1/download",
        )
    )

    class _SearchEmbeddingClient:
        def is_configured(self) -> bool:
            return True

        def embed_texts(self, texts: list[str]) -> list[list[float]]:
            return [[0.1, 0.2]]

    milvus_store = _FakeMilvusStore()
    milvus_store.search_hits = [
        {
            "distance": 0.91,
            "entity": {
                "chunk_id": "kf_1:7",
                "file_id": "kf_1",
                "filename": "guide.txt",
                "text": "Knowledge chunk content.",
                "download_url": "/api/knowledge/files/kf_1/download",
                "bucket": "weaver-knowledge",
                "object_key": "knowledge/kf_1/guide.txt",
                "uploaded_at": "2026-04-10T00:00:00Z",
                "content_type": "text/plain",
                "start_char": 10,
                "end_char": 30,
                "heading": "Chapter 1",
                "parser_name": "txt",
            },
        }
    ]

    service = KnowledgeService(
        registry=registry,
        object_store=_FakeObjectStore(),
        embedding_client=_SearchEmbeddingClient(),
        milvus_store=milvus_store,
    )

    results = service.search(query="knowledge", limit=2)

    assert results[0]["chunk_id"] == "kf_1:7"
    assert results[0]["url"] == "/api/knowledge/files/kf_1/download#chunk=kf_1:7"


def test_milvus_store_adapts_to_existing_chunk_id_embedding_schema(monkeypatch):
    monkeypatch.setattr(settings, "knowledge_milvus_collection", "knowledge_chunks", raising=False)

    client = _FakeMilvusClient(exists=True, vector_dim=1024, enable_dynamic_field=True)
    store = KnowledgeMilvusStore()
    store._client = client

    store.ensure_collection(dimension=1024)
    store.insert_chunks(
        [
            {
                "id": "kf_1:1",
                "chunk_id": "kf_1:1",
                "file_id": "kf_1",
                "filename": "guide.txt",
                "text": "hello",
                "vector": [0.1, 0.2],
            }
        ]
    )
    store.search(query_vector=[0.3, 0.4], limit=2)

    assert client.insert_payload == [
        {
            "chunk_id": "kf_1:1",
            "embedding": [0.1, 0.2],
            "file_id": "kf_1",
            "filename": "guide.txt",
            "text": "hello",
        }
    ]
    assert client.search_kwargs is not None
    assert client.search_kwargs["anns_field"] == "embedding"
    assert "chunk_id" in client.search_kwargs["output_fields"]


def test_milvus_store_raises_on_existing_dimension_mismatch(monkeypatch):
    monkeypatch.setattr(settings, "knowledge_milvus_collection", "knowledge_chunks", raising=False)

    store = KnowledgeMilvusStore()
    store._client = _FakeMilvusClient(exists=True, vector_dim=1024, enable_dynamic_field=True)

    try:
        store.ensure_collection(dimension=1536)
    except RuntimeError as exc:
        assert "dimension mismatch" in str(exc)
    else:
        raise AssertionError("expected dimension mismatch error")


def test_milvus_store_creates_collection_with_chunk_id_and_embedding_fields(monkeypatch):
    monkeypatch.setattr(settings, "knowledge_milvus_collection", "knowledge_chunks", raising=False)

    client = _FakeMilvusClient(exists=False)
    store = KnowledgeMilvusStore()
    store._client = client

    store.ensure_collection(dimension=1024)

    assert client.created_schema is not None
    assert [field["field_name"] for field in client.created_schema.fields] == ["chunk_id", "embedding"]
    assert client.created_schema.fields[0]["kwargs"]["is_primary"] is True
    assert client.created_schema.fields[1]["kwargs"]["dim"] == 1024
    assert client.created_index_params is not None
    assert client.created_index_params.indexes == [
        {"field_name": "embedding", "index_type": "AUTOINDEX", "metric_type": "COSINE"}
    ]


def test_rag_embedding_client_requires_dedicated_provider_settings(monkeypatch):
    monkeypatch.setattr(settings, "rag_embedding_model", "text-embedding-3-small", raising=False)
    monkeypatch.setattr(settings, "rag_embedding_api_key", "", raising=False)
    monkeypatch.setattr(settings, "openai_api_key", "llm-key", raising=False)
    monkeypatch.setattr(settings, "openai_base_url", "https://llm.example.com/v1", raising=False)

    client = RagEmbeddingClient()

    assert client.is_configured() is False


def test_rag_embedding_client_uses_only_dedicated_provider_config(monkeypatch):
    monkeypatch.setattr(settings, "rag_embedding_model", "embed-model", raising=False)
    monkeypatch.setattr(settings, "rag_embedding_api_key", "rag-key", raising=False)
    monkeypatch.setattr(settings, "rag_embedding_base_url", "https://embed.example.com/v1", raising=False)
    monkeypatch.setattr(settings, "rag_embedding_timeout", 33, raising=False)
    monkeypatch.setattr(settings, "rag_embedding_batch_size", 64, raising=False)
    monkeypatch.setattr(settings, "openai_api_key", "llm-key", raising=False)
    monkeypatch.setattr(settings, "openai_base_url", "https://llm.example.com/v1", raising=False)

    captured: dict[str, object] = {}

    class _FakeOpenAI:
        def __init__(self, **kwargs):
            captured["client_kwargs"] = kwargs
            self.embeddings = SimpleNamespace(create=self._create)

        def _create(self, *, model: str, input: list[str]):
            captured["model"] = model
            captured["input"] = list(input)
            return SimpleNamespace(data=[SimpleNamespace(embedding=[0.1, 0.2, 0.3]) for _ in input])

    fake_module = ModuleType("openai")
    fake_module.OpenAI = _FakeOpenAI
    monkeypatch.setitem(sys.modules, "openai", fake_module)

    client = RagEmbeddingClient()
    embeddings = client.embed_texts([" private knowledge query "])

    assert embeddings == [[0.1, 0.2, 0.3]]
    assert captured["client_kwargs"] == {
        "api_key": "rag-key",
        "timeout": 33,
        "base_url": "https://embed.example.com/v1",
    }
    assert captured["model"] == "embed-model"
    assert captured["input"] == ["private knowledge query"]


def test_rag_embedding_client_splits_large_batches(monkeypatch):
    monkeypatch.setattr(settings, "rag_embedding_model", "embed-model", raising=False)
    monkeypatch.setattr(settings, "rag_embedding_api_key", "rag-key", raising=False)
    monkeypatch.setattr(settings, "rag_embedding_base_url", "https://embed.example.com/v1", raising=False)
    monkeypatch.setattr(settings, "rag_embedding_timeout", 33, raising=False)
    monkeypatch.setattr(settings, "rag_embedding_batch_size", 64, raising=False)

    batch_sizes: list[int] = []

    class _FakeOpenAI:
        def __init__(self, **kwargs):
            self.embeddings = SimpleNamespace(create=self._create)

        def _create(self, *, model: str, input: list[str]):
            assert model == "embed-model"
            batch_sizes.append(len(input))
            return SimpleNamespace(
                data=[SimpleNamespace(embedding=[float(index)]) for index, _ in enumerate(input, 1)]
            )

    fake_module = ModuleType("openai")
    fake_module.OpenAI = _FakeOpenAI
    monkeypatch.setitem(sys.modules, "openai", fake_module)

    client = RagEmbeddingClient()
    texts = [f"chunk-{index}" for index in range(65)]

    embeddings = client.embed_texts(texts)

    assert batch_sizes == [64, 1]
    assert len(embeddings) == 65
    assert embeddings[0] == [1.0]
    assert embeddings[63] == [64.0]
    assert embeddings[64] == [1.0]
