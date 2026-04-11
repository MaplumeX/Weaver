from __future__ import annotations

from tools.rag import KnowledgeSearchScope
from tools.rag.knowledge_search_tool import KnowledgeSearchTool, build_knowledge_tools


class _FakeKnowledgeService:
    def __init__(self, *, ready: bool = True) -> None:
        self.ready = ready
        self.calls: list[dict[str, object]] = []

    def is_search_ready(self) -> bool:
        return self.ready

    def search(self, *, query: str, limit: int | None = None, scope: KnowledgeSearchScope | None = None):
        self.calls.append(
            {
                "query": query,
                "limit": limit,
                "scope": scope,
            }
        )
        return [
            {
                "title": "guide.txt",
                "url": "/api/knowledge/files/kf_1/download#chunk=kf_1:1",
                "raw_url": "/api/knowledge/files/kf_1/download",
                "summary": "Visible knowledge",
                "content": "Visible knowledge",
                "provider": "milvus_rag",
                "knowledge_file_id": "kf_1",
                "chunk_id": "kf_1:1",
                "source_type": "knowledge_file",
            }
        ]


def test_knowledge_search_tool_passes_runtime_scope_to_service() -> None:
    service = _FakeKnowledgeService()
    tool = KnowledgeSearchTool(
        thread_id="thread-1",
        user_id="user-1",
        agent_id="agent-1",
        knowledge_service=service,
    )

    payload = tool.invoke({"query": "deployment guide", "max_results": 2})

    assert payload["available"] is True
    assert payload["result_count"] == 1
    assert service.calls[0]["query"] == "deployment guide"
    assert service.calls[0]["limit"] == 2
    assert service.calls[0]["scope"] == KnowledgeSearchScope(user_id="user-1", agent_id="agent-1")


def test_build_knowledge_tools_binds_owner_to_tool_instance() -> None:
    tools = build_knowledge_tools("thread-2", user_id="user-2", agent_id="agent-2")

    assert len(tools) == 1
    tool = tools[0]
    assert getattr(tool, "name", "") == "knowledge_search"
    assert getattr(tool, "user_id", "") == "user-2"
    assert getattr(tool, "agent_id", "") == "agent-2"
