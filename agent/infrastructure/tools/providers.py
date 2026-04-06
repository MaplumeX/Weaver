from __future__ import annotations

from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from typing import Any, Protocol

from langchain_core.tools import BaseTool


@dataclass(frozen=True)
class ProviderContext:
    thread_id: str
    profile: dict[str, Any]
    configurable: dict[str, Any]
    e2b_ready: bool


class ToolProvider(Protocol):
    key: str

    def build_tools(self, context: ProviderContext) -> list[BaseTool]:
        ...


@dataclass(frozen=True)
class StaticToolProvider:
    key: str
    factory: Callable[[ProviderContext], list[BaseTool]]

    def build_tools(self, context: ProviderContext) -> list[BaseTool]:
        return list(self.factory(context))


def compose_provider_tools(
    providers: list[ToolProvider],
    context: ProviderContext,
) -> list[BaseTool]:
    deduped: dict[str, BaseTool] = {}
    for provider in providers:
        for tool in provider.build_tools(context):
            if hasattr(tool, "thread_id"):
                with suppress(Exception):
                    tool.thread_id = context.thread_id
            name = getattr(tool, "name", "")
            if isinstance(name, str) and name and name not in deduped:
                deduped[name] = tool
    return list(deduped.values())
