from __future__ import annotations

import io
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from agent.foundation.passages import split_into_passages
from common.config import settings
from common.knowledge_registry import KnowledgeFileRecord, KnowledgeRegistry
from tools.rag.file_parser import parse_uploaded_file

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class KnowledgeMilvusSchema:
    primary_field: str
    vector_field: str
    vector_dim: int | None
    enable_dynamic_field: bool
    field_names: tuple[str, ...]


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _safe_filename(filename: str) -> str:
    value = Path(str(filename or "").strip()).name
    return value or f"knowledge-{uuid.uuid4().hex[:8]}.bin"


class KnowledgeObjectStore:
    def __init__(self) -> None:
        self._client: Any | None = None

    def is_configured(self) -> bool:
        return bool(
            settings.minio_endpoint.strip()
            and settings.minio_access_key.strip()
            and settings.minio_secret_key.strip()
            and settings.minio_bucket.strip()
        )

    def _client_or_raise(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            from minio import Minio
        except ImportError as exc:  # pragma: no cover - depends on env state
            raise RuntimeError("minio dependency is required for knowledge file storage") from exc
        self._client = Minio(
            settings.minio_endpoint.strip(),
            access_key=settings.minio_access_key.strip(),
            secret_key=settings.minio_secret_key.strip(),
            secure=bool(settings.minio_secure),
        )
        return self._client

    def ensure_bucket(self) -> None:
        client = self._client_or_raise()
        bucket = settings.minio_bucket.strip()
        if client.bucket_exists(bucket):
            return
        client.make_bucket(bucket)

    def upload_bytes(
        self,
        *,
        file_id: str,
        filename: str,
        content_type: str,
        data: bytes,
    ) -> tuple[str, str]:
        self.ensure_bucket()
        bucket = settings.minio_bucket.strip()
        object_key = f"knowledge/{file_id}/{filename}"
        payload = io.BytesIO(data)
        self._client_or_raise().put_object(
            bucket,
            object_key,
            payload,
            length=len(data),
            content_type=content_type or "application/octet-stream",
        )
        return bucket, object_key

    def download_bytes(self, *, bucket: str, object_key: str) -> bytes:
        response = self._client_or_raise().get_object(bucket, object_key)
        try:
            return bytes(response.read())
        finally:
            response.close()
            response.release_conn()


class RagEmbeddingClient:
    def __init__(self) -> None:
        self._client: Any | None = None

    def is_configured(self) -> bool:
        return bool(
            settings.rag_embedding_model.strip()
            and settings.rag_embedding_api_key.strip()
        )

    def _client_or_raise(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover - depends on env state
            raise RuntimeError("openai dependency is required for knowledge embeddings") from exc
        if not self.is_configured():
            raise RuntimeError("RAG embedding provider is not configured")
        params: dict[str, Any] = {
            "api_key": settings.rag_embedding_api_key.strip(),
            "timeout": settings.rag_embedding_timeout or None,
        }
        if settings.rag_embedding_base_url.strip():
            params["base_url"] = settings.rag_embedding_base_url.strip()
        self._client = OpenAI(**params)
        return self._client

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        cleaned = [str(item or "").strip() for item in texts if str(item or "").strip()]
        if not cleaned:
            return []
        batch_size = max(1, int(settings.rag_embedding_batch_size or 64))
        embeddings: list[list[float]] = []
        client = self._client_or_raise()
        model = settings.rag_embedding_model.strip()
        for start in range(0, len(cleaned), batch_size):
            batch = cleaned[start : start + batch_size]
            response = client.embeddings.create(
                model=model,
                input=batch,
            )
            batch_embeddings = [list(item.embedding) for item in response.data]
            if len(batch_embeddings) != len(batch):
                raise RuntimeError("Embedding response count does not match request batch size")
            embeddings.extend(batch_embeddings)
        return embeddings


class KnowledgeMilvusStore:
    def __init__(self) -> None:
        self._client: Any | None = None
        self._collection_ready = False
        self._schema: KnowledgeMilvusSchema | None = None

    def is_configured(self) -> bool:
        return bool(settings.milvus_uri.strip() and settings.knowledge_milvus_collection.strip())

    def _client_or_raise(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            from pymilvus import MilvusClient
        except ImportError as exc:  # pragma: no cover - depends on env state
            raise RuntimeError("pymilvus dependency is required for knowledge retrieval") from exc
        if not self.is_configured():
            raise RuntimeError("Milvus is not configured")
        params: dict[str, Any] = {"uri": settings.milvus_uri.strip()}
        if settings.milvus_token.strip():
            params["token"] = settings.milvus_token.strip()
        if settings.milvus_db_name.strip():
            params["db_name"] = settings.milvus_db_name.strip()
        self._client = MilvusClient(**params)
        return self._client

    def _is_vector_field_type(self, value: Any) -> bool:
        try:
            from pymilvus import DataType
        except ImportError as exc:  # pragma: no cover - depends on env state
            raise RuntimeError("pymilvus dependency is required for knowledge retrieval") from exc

        vector_types = {
            DataType.FLOAT_VECTOR,
            DataType.FLOAT16_VECTOR,
            DataType.BFLOAT16_VECTOR,
            DataType.INT8_VECTOR,
            DataType.BINARY_VECTOR,
            DataType.SPARSE_FLOAT_VECTOR,
        }
        if value in vector_types:
            return True
        return str(getattr(value, "name", "") or "").upper() in {
            "FLOAT_VECTOR",
            "FLOAT16_VECTOR",
            "BFLOAT16_VECTOR",
            "INT8_VECTOR",
            "BINARY_VECTOR",
            "SPARSE_FLOAT_VECTOR",
        }

    def _describe_schema(self) -> KnowledgeMilvusSchema:
        info = self._client_or_raise().describe_collection(
            settings.knowledge_milvus_collection.strip(),
        )
        fields = [item for item in info.get("fields") or [] if isinstance(item, dict)]
        if not fields:
            raise RuntimeError("Milvus collection schema has no fields")

        primary_field = ""
        vector_field = ""
        vector_dim: int | None = None
        field_names: list[str] = []
        for field in fields:
            name = str(field.get("name") or "").strip()
            if not name:
                continue
            field_names.append(name)
            if not primary_field and bool(field.get("is_primary")):
                primary_field = name
            if not vector_field and self._is_vector_field_type(field.get("type")):
                vector_field = name
                params = field.get("params") if isinstance(field.get("params"), dict) else {}
                raw_dim = params.get("dim")
                if raw_dim is not None and str(raw_dim).strip():
                    vector_dim = int(raw_dim)

        if not primary_field:
            raise RuntimeError("Milvus collection schema is missing a primary field")
        if not vector_field:
            raise RuntimeError("Milvus collection schema is missing a vector field")
        return KnowledgeMilvusSchema(
            primary_field=primary_field,
            vector_field=vector_field,
            vector_dim=vector_dim,
            enable_dynamic_field=bool(info.get("enable_dynamic_field")),
            field_names=tuple(field_names),
        )

    def _schema_or_raise(self) -> KnowledgeMilvusSchema:
        if self._schema is None:
            collection_name = settings.knowledge_milvus_collection.strip()
            if self._client_or_raise().has_collection(collection_name=collection_name):
                self._schema = self._describe_schema()
                self._collection_ready = True
        if self._schema is None:
            raise RuntimeError("Milvus collection schema has not been initialized")
        return self._schema

    def _validate_existing_schema_dimension(self, *, schema: KnowledgeMilvusSchema, dimension: int) -> None:
        if schema.vector_dim is None:
            return
        if int(schema.vector_dim) != int(dimension):
            raise RuntimeError(
                "Milvus collection vector dimension mismatch: "
                f"collection expects {schema.vector_dim}, embedding produced {dimension}"
            )

    def ensure_collection(self, *, dimension: int) -> None:
        if self._collection_ready:
            self._validate_existing_schema_dimension(schema=self._schema_or_raise(), dimension=dimension)
            return
        client = self._client_or_raise()
        collection_name = settings.knowledge_milvus_collection.strip()
        if client.has_collection(collection_name=collection_name):
            self._schema = self._describe_schema()
            self._validate_existing_schema_dimension(schema=self._schema, dimension=dimension)
            self._collection_ready = True
            return
        try:
            from pymilvus import DataType
        except ImportError as exc:  # pragma: no cover - depends on env state
            raise RuntimeError("pymilvus dependency is required for knowledge retrieval") from exc

        schema = client.create_schema(auto_id=False, enable_dynamic_field=True)
        schema.add_field(field_name="chunk_id", datatype=DataType.VARCHAR, is_primary=True, max_length=255)
        schema.add_field(field_name="embedding", datatype=DataType.FLOAT_VECTOR, dim=dimension)

        index_params = client.prepare_index_params()
        index_params.add_index(field_name="embedding", index_type="AUTOINDEX", metric_type="COSINE")
        client.create_collection(
            collection_name=collection_name,
            schema=schema,
            index_params=index_params,
        )
        self._schema = KnowledgeMilvusSchema(
            primary_field="chunk_id",
            vector_field="embedding",
            vector_dim=int(dimension),
            enable_dynamic_field=True,
            field_names=("chunk_id", "embedding"),
        )
        self._collection_ready = True

    def insert_chunks(self, chunks: list[dict[str, Any]]) -> None:
        if not chunks:
            return
        schema = self._schema_or_raise()
        payloads: list[dict[str, Any]] = []
        known_fields = set(schema.field_names)
        for chunk in chunks:
            primary_value = str(
                chunk.get(schema.primary_field)
                or chunk.get("chunk_id")
                or chunk.get("id")
                or ""
            ).strip()
            if not primary_value:
                raise RuntimeError("Knowledge chunk is missing a Milvus primary key value")
            vector = chunk.get(schema.vector_field)
            if vector is None:
                vector = chunk.get("embedding")
            if vector is None:
                vector = chunk.get("vector")
            if vector is None:
                raise RuntimeError("Knowledge chunk is missing embedding vector data")

            payload: dict[str, Any] = {
                schema.primary_field: primary_value,
                schema.vector_field: vector,
            }
            for key, value in chunk.items():
                if key in {"id", "vector", "embedding"}:
                    continue
                if key == schema.primary_field or key == schema.vector_field:
                    continue
                if schema.enable_dynamic_field or key in known_fields:
                    payload[key] = value
            payloads.append(payload)
        self._client_or_raise().insert(
            collection_name=settings.knowledge_milvus_collection.strip(),
            data=payloads,
        )

    def search(self, *, query_vector: list[float], limit: int) -> list[dict[str, Any]]:
        if not query_vector:
            return []
        schema = self._schema_or_raise()
        desired_output_fields = [
            schema.primary_field,
            "chunk_id",
            "file_id",
            "filename",
            "text",
            "download_url",
            "bucket",
            "object_key",
            "uploaded_at",
            "content_type",
            "start_char",
            "end_char",
            "heading",
            "parser_name",
        ]
        if schema.enable_dynamic_field:
            output_fields = list(dict.fromkeys(desired_output_fields))
        else:
            output_fields = [name for name in dict.fromkeys(desired_output_fields) if name in schema.field_names]
        raw = self._client_or_raise().search(
            collection_name=settings.knowledge_milvus_collection.strip(),
            data=[query_vector],
            limit=max(1, limit),
            output_fields=output_fields,
            anns_field=schema.vector_field,
        )
        if isinstance(raw, list) and raw and isinstance(raw[0], list):
            return [item for item in raw[0] if isinstance(item, dict)]
        return [item for item in raw or [] if isinstance(item, dict)]


class KnowledgeService:
    def __init__(
        self,
        *,
        registry: KnowledgeRegistry | None = None,
        object_store: KnowledgeObjectStore | None = None,
        embedding_client: RagEmbeddingClient | None = None,
        milvus_store: KnowledgeMilvusStore | None = None,
    ) -> None:
        self.registry = registry or KnowledgeRegistry()
        self.object_store = object_store or KnowledgeObjectStore()
        self.embedding_client = embedding_client or RagEmbeddingClient()
        self.milvus_store = milvus_store or KnowledgeMilvusStore()

    def list_files(self) -> list[KnowledgeFileRecord]:
        return self.registry.list_records()

    def get_file(self, file_id: str) -> KnowledgeFileRecord | None:
        return self.registry.get_record(file_id)

    def _assert_upload_ready(self) -> None:
        if not self.object_store.is_configured():
            raise RuntimeError("MinIO storage is not configured")
        if not self.embedding_client.is_configured():
            raise RuntimeError("RAG embedding provider is not configured")
        if not self.milvus_store.is_configured():
            raise RuntimeError("Milvus is not configured")

    def _build_initial_record(
        self,
        *,
        file_id: str,
        filename: str,
        content_type: str,
        extension: str,
        size_bytes: int,
    ) -> KnowledgeFileRecord:
        return KnowledgeFileRecord(
            id=file_id,
            filename=filename,
            content_type=content_type,
            extension=extension,
            size_bytes=size_bytes,
            download_path=f"/api/knowledge/files/{file_id}/download",
            collection_name=settings.knowledge_milvus_collection.strip(),
            status="uploading",
        )

    def ingest_file(self, *, filename: str, content_type: str, data: bytes) -> KnowledgeFileRecord:
        self._assert_upload_ready()
        safe_filename = _safe_filename(filename)
        extension = safe_filename.rsplit(".", 1)[-1].lower() if "." in safe_filename else ""
        allowed = set(settings.knowledge_allowed_extensions_list)
        if extension not in allowed:
            raise ValueError(f"Unsupported knowledge file type: {extension or 'unknown'}")
        if len(data) > int(settings.knowledge_max_upload_bytes or 0):
            raise ValueError("Knowledge file exceeds upload size limit")

        file_id = f"kf_{uuid.uuid4().hex[:12]}"
        record = self._build_initial_record(
            file_id=file_id,
            filename=safe_filename,
            content_type=content_type,
            extension=extension,
            size_bytes=len(data),
        )
        self.registry.upsert_record(record)

        try:
            bucket, object_key = self.object_store.upload_bytes(
                file_id=file_id,
                filename=safe_filename,
                content_type=content_type,
                data=data,
            )
            record = self.registry.upsert_record(
                record.model_copy(
                    update={
                        "bucket": bucket,
                        "object_key": object_key,
                        "status": "uploaded",
                    }
                )
            )

            parsed = parse_uploaded_file(data, filename=safe_filename, content_type=content_type)
            full_text = str(parsed.text or "").strip()
            if not full_text:
                raise ValueError("Knowledge file has no extractable text")

            base_chunks = split_into_passages(full_text, max_chars=int(settings.knowledge_chunk_max_chars or 1200))
            chunks_payload: list[dict[str, Any]] = []
            chunk_texts: list[str] = []
            for index, item in enumerate(base_chunks, 1):
                text = str(item.get("text") or "").strip()
                if len(text) < 20:
                    continue
                chunk_id = f"{file_id}:{index}"
                chunk_texts.append(text)
                chunks_payload.append(
                    {
                        "id": chunk_id,
                        "chunk_id": chunk_id,
                        "file_id": file_id,
                        "filename": safe_filename,
                        "text": text,
                        "download_url": record.download_path,
                        "bucket": bucket,
                        "object_key": object_key,
                        "uploaded_at": record.created_at,
                        "content_type": content_type,
                        "start_char": int(item.get("start_char") or 0),
                        "end_char": int(item.get("end_char") or 0),
                        "heading": str(item.get("heading") or ""),
                        "parser_name": parsed.parser_name,
                    }
                )

            if not chunks_payload:
                chunks_payload = [
                    {
                        "id": f"{file_id}:1",
                        "chunk_id": f"{file_id}:1",
                        "file_id": file_id,
                        "filename": safe_filename,
                        "text": full_text,
                        "download_url": record.download_path,
                        "bucket": bucket,
                        "object_key": object_key,
                        "uploaded_at": record.created_at,
                        "content_type": content_type,
                        "start_char": 0,
                        "end_char": len(full_text),
                        "heading": "",
                        "parser_name": parsed.parser_name,
                    }
                ]
                chunk_texts = [full_text]

            embeddings = self.embedding_client.embed_texts(chunk_texts)
            if len(embeddings) != len(chunks_payload):
                raise RuntimeError("Embedding response count does not match chunk count")
            dimension = int(settings.rag_embedding_dimensions or 0) or len(embeddings[0])
            self.milvus_store.ensure_collection(dimension=dimension)

            indexed_chunks: list[dict[str, Any]] = []
            for chunk, embedding in zip(chunks_payload, embeddings, strict=False):
                indexed_chunks.append({**chunk, "vector": embedding})
            self.milvus_store.insert_chunks(indexed_chunks)

            return self.registry.upsert_record(
                record.model_copy(
                    update={
                        "bucket": bucket,
                        "object_key": object_key,
                        "status": "indexed",
                        "parser_name": parsed.parser_name,
                        "chunk_count": len(indexed_chunks),
                        "indexed_at": _now_iso(),
                        "metadata": dict(parsed.metadata or {}),
                    }
                )
            )
        except Exception as exc:
            logger.error("[knowledge_service] ingest failed | file=%s | error=%s", safe_filename, exc, exc_info=True)
            return self.registry.upsert_record(
                record.model_copy(
                    update={
                        "status": "failed",
                        "error": str(exc),
                    }
                )
            )

    def download_file(self, file_id: str) -> tuple[KnowledgeFileRecord, bytes]:
        record = self.get_file(file_id)
        if record is None:
            raise ValueError("Knowledge file not found")
        if not record.bucket or not record.object_key:
            raise RuntimeError("Knowledge file storage location is missing")
        payload = self.object_store.download_bytes(bucket=record.bucket, object_key=record.object_key)
        return record, payload

    def search(self, *, query: str, limit: int | None = None) -> list[dict[str, Any]]:
        query_text = str(query or "").strip()
        if not query_text:
            return []
        indexed = [item for item in self.registry.list_records() if item.status == "indexed"]
        if not indexed:
            return []
        if not self.embedding_client.is_configured() or not self.milvus_store.is_configured():
            return []
        query_embeddings = self.embedding_client.embed_texts([query_text])
        if not query_embeddings:
            return []
        raw_hits = self.milvus_store.search(
            query_vector=query_embeddings[0],
            limit=int(limit or settings.knowledge_search_top_k or 4),
        )

        normalized: list[dict[str, Any]] = []
        for item in raw_hits:
            entity = item.get("entity") or {}
            hit_id = str(
                item.get("id")
                or entity.get("chunk_id")
                or entity.get("id")
                or ""
            ).strip()
            file_id = str(entity.get("file_id") or "").strip()
            base_url = str(entity.get("download_url") or f"/api/knowledge/files/{file_id}/download").strip()
            text = str(entity.get("text") or "").strip()
            url = f"{base_url}#chunk={hit_id}" if hit_id else base_url
            normalized.append(
                {
                    "title": str(entity.get("filename") or file_id or "Knowledge File").strip(),
                    "url": url,
                    "raw_url": base_url,
                    "summary": text[:240],
                    "raw_excerpt": text,
                    "content": text,
                    "score": float(item.get("distance", 0.0) or 0.0),
                    "provider": "milvus_rag",
                    "published_date": None,
                    "knowledge_file_id": file_id,
                    "chunk_id": hit_id,
                    "bucket": str(entity.get("bucket") or "").strip(),
                    "object_key": str(entity.get("object_key") or "").strip(),
                    "content_type": str(entity.get("content_type") or "").strip(),
                    "retrieved_at": str(entity.get("uploaded_at") or "").strip() or None,
                    "start_char": entity.get("start_char"),
                    "end_char": entity.get("end_char"),
                    "heading": str(entity.get("heading") or "").strip(),
                    "parser_name": str(entity.get("parser_name") or "").strip(),
                    "source_type": "knowledge_file",
                }
            )
        return normalized


@lru_cache(maxsize=1)
def get_knowledge_service() -> KnowledgeService:
    return KnowledgeService()


__all__ = ["KnowledgeService", "get_knowledge_service"]
