from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient

import main
from common.knowledge_registry import KnowledgeFileRecord
from tools.rag.service import DuplicateKnowledgeFileError


class FakeKnowledgeService:
    def __init__(self) -> None:
        self.ingest_calls: list[dict[str, object]] = []
        self.reindex_calls: list[str] = []
        self.delete_calls: list[str] = []
        self.raise_duplicate = False

    def list_files(self):
        return [
            {
                "id": "kf_1",
                "filename": "guide.md",
                "content_type": "text/markdown",
                "extension": "md",
                "size_bytes": 128,
                "bucket": "weaver-knowledge",
                "object_key": "knowledge/kf_1/guide.md",
                "download_path": "/api/knowledge/files/kf_1/download",
                "collection_name": "knowledge_chunks",
                "status": "indexed",
                "parser_name": "markdown",
                "chunk_count": 2,
                "indexed_at": "2026-04-10T00:00:00Z",
                "error": "",
                "metadata": {},
                "created_at": "2026-04-10T00:00:00Z",
                "updated_at": "2026-04-10T00:00:00Z",
            }
        ]

    def ingest_file(self, *, filename: str, content_type: str, data: bytes):
        if self.raise_duplicate:
            raise DuplicateKnowledgeFileError(
                KnowledgeFileRecord(
                    id="kf_existing",
                    filename="guide.txt",
                    content_hash="abc123",
                    status="indexed",
                )
            )
        self.ingest_calls.append(
            {
                "filename": filename,
                "content_type": content_type,
                "size": len(data),
            }
        )
        return {
            "id": "kf_uploaded",
            "filename": filename,
            "content_type": content_type,
            "extension": "txt",
            "size_bytes": len(data),
            "bucket": "weaver-knowledge",
            "object_key": f"knowledge/kf_uploaded/{filename}",
            "download_path": "/api/knowledge/files/kf_uploaded/download",
            "collection_name": "knowledge_chunks",
            "status": "indexed",
            "parser_name": "txt",
            "chunk_count": 1,
            "indexed_at": "2026-04-10T01:00:00Z",
            "error": "",
            "metadata": {},
            "created_at": "2026-04-10T01:00:00Z",
            "updated_at": "2026-04-10T01:00:00Z",
        }

    def download_file(self, file_id: str):
        return (
            SimpleNamespace(filename=f"{file_id}.txt", content_type="text/plain"),
            b"knowledge payload",
        )

    def reindex_file(self, file_id: str):
        self.reindex_calls.append(file_id)
        return {
            "id": file_id,
            "filename": "guide.txt",
            "content_type": "text/plain",
            "extension": "txt",
            "size_bytes": 14,
            "bucket": "weaver-knowledge",
            "object_key": f"knowledge/{file_id}/guide.txt",
            "download_path": f"/api/knowledge/files/{file_id}/download",
            "collection_name": "knowledge_chunks",
            "status": "indexed",
            "parser_name": "txt",
            "chunk_count": 1,
            "indexed_at": "2026-04-11T01:00:00Z",
            "error": "",
            "metadata": {"version": 2},
            "created_at": "2026-04-10T01:00:00Z",
            "updated_at": "2026-04-11T01:00:00Z",
        }

    def delete_file(self, file_id: str):
        self.delete_calls.append(file_id)
        return SimpleNamespace(id=file_id, filename="guide.txt")


@pytest.mark.asyncio
async def test_list_knowledge_files(monkeypatch):
    service = FakeKnowledgeService()
    monkeypatch.setattr(main, "get_knowledge_service", lambda: service)

    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/api/knowledge/files")

    assert response.status_code == 200
    payload = response.json()
    assert payload["files"][0]["filename"] == "guide.md"
    assert payload["files"][0]["status"] == "indexed"


@pytest.mark.asyncio
async def test_upload_knowledge_files(monkeypatch):
    service = FakeKnowledgeService()
    monkeypatch.setattr(main, "get_knowledge_service", lambda: service)

    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.post(
            "/api/knowledge/files",
            files=[("files", ("guide.txt", b"hello knowledge", "text/plain"))],
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["files"][0]["filename"] == "guide.txt"
    assert service.ingest_calls == [
        {
            "filename": "guide.txt",
            "content_type": "text/plain",
            "size": len(b"hello knowledge"),
        }
    ]


@pytest.mark.asyncio
async def test_upload_knowledge_files_returns_409_for_duplicate(monkeypatch):
    service = FakeKnowledgeService()
    service.raise_duplicate = True
    monkeypatch.setattr(main, "get_knowledge_service", lambda: service)

    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.post(
            "/api/knowledge/files",
            files=[("files", ("guide.txt", b"hello knowledge", "text/plain"))],
        )

    assert response.status_code == 409
    assert "Knowledge file already exists" in str(response.json())


@pytest.mark.asyncio
async def test_reindex_knowledge_file(monkeypatch):
    service = FakeKnowledgeService()
    monkeypatch.setattr(main, "get_knowledge_service", lambda: service)

    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.post("/api/knowledge/files/kf_1/reindex")

    assert response.status_code == 200
    payload = response.json()
    assert payload["file"]["id"] == "kf_1"
    assert payload["file"]["status"] == "indexed"
    assert service.reindex_calls == ["kf_1"]


@pytest.mark.asyncio
async def test_delete_knowledge_file(monkeypatch):
    service = FakeKnowledgeService()
    monkeypatch.setattr(main, "get_knowledge_service", lambda: service)

    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.delete("/api/knowledge/files/kf_1")

    assert response.status_code == 200
    payload = response.json()
    assert payload == {
        "file_id": "kf_1",
        "filename": "guide.txt",
        "deleted": True,
    }
    assert service.delete_calls == ["kf_1"]


@pytest.mark.asyncio
async def test_download_knowledge_file(monkeypatch):
    service = FakeKnowledgeService()
    monkeypatch.setattr(main, "get_knowledge_service", lambda: service)

    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/api/knowledge/files/kf_1/download")

    assert response.status_code == 200
    assert response.content == b"knowledge payload"
    assert 'attachment; filename="kf_1.txt"' in response.headers["content-disposition"]
