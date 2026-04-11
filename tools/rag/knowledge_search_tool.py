from __future__ import annotations

import logging
from typing import Any

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from tools.rag.service import KnowledgeSearchScope, get_knowledge_service

logger = logging.getLogger(__name__)


class KnowledgeSearchInput(BaseModel):
    query: str = Field(min_length=1, description="Query to search in the user's knowledge files")
    max_results: int = Field(default=4, ge=1, le=10, description="Maximum results to return")


class KnowledgeSearchTool(BaseTool):
    name: str = "knowledge_search"
    description: str = (
        "Search the current user's uploaded knowledge files and return relevant excerpts. "
        "Use this for private documents, uploaded files, and internal knowledge."
    )
    args_schema: type[BaseModel] = KnowledgeSearchInput

    thread_id: str = "default"
    user_id: str = "default_user"
    agent_id: str = ""
    knowledge_service: Any = Field(default_factory=get_knowledge_service, exclude=True)

    def _run(self, query: str, max_results: int = 4) -> dict[str, Any]:
        service = self.knowledge_service or get_knowledge_service()
        available = bool(getattr(service, "is_search_ready", lambda: True)())
        try:
            results = service.search(
                query=query,
                limit=max_results,
                scope=KnowledgeSearchScope(
                    user_id=str(self.user_id or "").strip() or "default_user",
                    agent_id=str(self.agent_id or "").strip(),
                ),
            )
        except Exception as exc:
            logger.error(
                "[knowledge_search] query failed | user_id=%s | agent_id=%s | error=%s",
                self.user_id,
                self.agent_id,
                exc,
                exc_info=True,
            )
            return {
                "query": query,
                "available": available,
                "results": [],
                "result_count": 0,
                "error": str(exc),
            }

        return {
            "query": query,
            "available": available,
            "results": results,
            "result_count": len(results),
        }


def build_knowledge_tools(thread_id: str, *, user_id: str, agent_id: str = "") -> list[BaseTool]:
    return [
        KnowledgeSearchTool(
            thread_id=thread_id,
            user_id=str(user_id or "").strip() or "default_user",
            agent_id=str(agent_id or "").strip(),
        )
    ]


__all__ = [
    "KnowledgeSearchInput",
    "KnowledgeSearchTool",
    "build_knowledge_tools",
]
