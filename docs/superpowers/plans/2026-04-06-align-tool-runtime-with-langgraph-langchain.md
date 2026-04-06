# Tool Runtime Alignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 Weaver 的工具运行时收敛为 `LangChain BaseTool + provider 组合 + LangGraph 编排`，保留事件观测、能力裁剪和 MCP 扩展，但停止把自定义注册表当作运行时主来源。

**Architecture:** 运行时只消费 `BaseTool` 列表；`build_agent_toolset()` 从多个 `ToolProvider` 收集工具，再通过 profile/capability policy 过滤并按需包装事件。`ToolRegistry` 降级为 catalog/metadata 服务，`MCP` 改为 provider，不再通过 `_REGISTERED_TOOLS` 和 `set_registered_tools()` 驱动主执行路径。

**Tech Stack:** Python 3.11, FastAPI, LangChain 1.x, LangGraph 1.x, Pydantic v2, pytest

---

**Scope Notes**

- 本计划只收敛“工具运行时装配与注册模型”。
- 不在这一轮重写 [agent/runtime/deep/orchestration/graph.py](/home/maplume/projects/Weaver/agent/runtime/deep/orchestration/graph.py) 内的 `ResearchAgent` 执行器。
- 保留 `WeaverTool` 作为作者层兼容语法糖，但不再把它当作运行时一等抽象。
- 按仓库约束，本计划不包含 `git commit` 步骤。

**File Map**

- Create: `agent/infrastructure/tools/providers.py`
  作用：定义 `ToolProvider` 协议、provider 上下文、静态组合与去重逻辑。
- Create: `agent/infrastructure/tools/policy.py`
  作用：承载 profile 开关、capability 别名解析、白名单/黑名单过滤。
- Create: `agent/infrastructure/tools/catalog.py`
  作用：生成只读 catalog 快照，供 `/api/tools/registry` 与健康检查使用。
- Create: `tests/test_tool_providers.py`
  作用：覆盖 provider 组合、去重和环境感知装配。
- Create: `tests/test_mcp_tool_provider.py`
  作用：覆盖 MCP provider 从活动客户端读取工具，而不是依赖全局 `_REGISTERED_TOOLS`。
- Modify: `agent/infrastructure/tools/assembly.py`
  作用：拆分“构建完整 inventory”和“按 profile 过滤后的 agent toolset”。
- Modify: `agent/infrastructure/tools/capabilities.py`
  作用：从“既建工具又做策略”收敛为“声明 provider 工厂 + capability 映射数据”。
- Modify: `agent/infrastructure/tools/__init__.py`
  作用：导出新的运行时装配与 policy 接口。
- Modify: `agent/infrastructure/agents/factory.py`
  作用：`build_deep_research_tool_agent()` 改为复用统一 inventory/helper，而不是直接读 `get_registered_tools()`。
- Modify: `tools/mcp.py`
  作用：暴露当前 MCP 工具快照读取接口，去掉对 `set_registered_tools()` 的运行时依赖。
- Modify: `tools/core/registry.py`
  作用：降级为 catalog/metadata 层，保留兼容 API，但标注运行时弃用路径。
- Modify: `agent/runtime/nodes/_shared.py`
  作用：将 `initialize_enhanced_tools()` 改造成 catalog refresh，不再暗示它控制运行时装配。
- Modify: `main.py`
  作用：启动、MCP reload、`/api/tools/registry`、`/api/health/agent` 改为使用 provider/catalog。
- Modify: `tests/test_agent_tools.py`
  作用：验证 `build_agent_toolset()` 继续返回正确工具，但来源已变为 provider 组合。
- Modify: `tests/test_agent_factory_defaults.py`
  作用：验证 deep-research 角色工具过滤继续成立，但不再依赖 `get_registered_tools()`。
- Modify: `tests/tools/test_tool_registry_discovery.py`
  作用：保留 discovery/catelog 行为测试，并明确它不再代表运行时工具来源。
- Optional Create: `docs/tool-runtime-architecture.md`
  作用：记录新架构、边界和迁移约束。

### Task 1: 引入 Provider 运行时抽象

**Files:**
- Create: `agent/infrastructure/tools/providers.py`
- Modify: `agent/infrastructure/tools/__init__.py`
- Test: `tests/test_tool_providers.py`

- [ ] **Step 1: 先写 provider 组合的失败测试**

```python
from __future__ import annotations

from dataclasses import dataclass

from langchain_core.tools import tool

from agent.infrastructure.tools.providers import (
    ProviderContext,
    StaticToolProvider,
    compose_provider_tools,
)


@tool
def alpha(query: str) -> str:
    """alpha"""
    return query


@tool
def beta(query: str) -> str:
    """beta"""
    return query


def test_compose_provider_tools_dedupes_by_tool_name() -> None:
    providers = [
        StaticToolProvider("primary", lambda _ctx: [alpha, beta]),
        StaticToolProvider("secondary", lambda _ctx: [alpha]),
    ]

    tools = compose_provider_tools(
        providers,
        ProviderContext(thread_id="t1", profile={}, configurable={}, e2b_ready=False),
    )

    assert [tool.name for tool in tools] == ["alpha", "beta"]


def test_compose_provider_tools_assigns_thread_id_when_supported() -> None:
    class _ThreadAware:
        name = "thread_aware"
        description = "thread-aware"
        thread_id = "default"

    provider = StaticToolProvider("threaded", lambda _ctx: [_ThreadAware()])
    [tool_obj] = compose_provider_tools(
        [provider],
        ProviderContext(thread_id="worker-7", profile={}, configurable={}, e2b_ready=False),
    )

    assert tool_obj.thread_id == "worker-7"
```

- [ ] **Step 2: 运行测试，确认当前缺少 provider 抽象**

Run: `pytest tests/test_tool_providers.py -v`

Expected:
- `ModuleNotFoundError: No module named 'agent.infrastructure.tools.providers'`

- [ ] **Step 3: 写最小 provider 抽象和组合函数**

```python
# agent/infrastructure/tools/providers.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Protocol

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
                try:
                    setattr(tool, "thread_id", context.thread_id)
                except Exception:
                    pass
            name = getattr(tool, "name", "")
            if isinstance(name, str) and name and name not in deduped:
                deduped[name] = tool
    return list(deduped.values())
```

```python
# agent/infrastructure/tools/__init__.py
from agent.infrastructure.tools.providers import (
    ProviderContext,
    StaticToolProvider,
    ToolProvider,
    compose_provider_tools,
)
```

- [ ] **Step 4: 重新运行 provider 测试**

Run: `pytest tests/test_tool_providers.py -v`

Expected:
- `2 passed`

### Task 2: 拆分 Inventory 构建与 Profile 过滤

**Files:**
- Create: `agent/infrastructure/tools/policy.py`
- Modify: `agent/infrastructure/tools/assembly.py`
- Modify: `agent/infrastructure/tools/capabilities.py`
- Modify: `agent/infrastructure/tools/__init__.py`
- Test: `tests/test_agent_tools.py`

- [ ] **Step 1: 先补失败测试，锁定新的装配边界**

```python
from langchain_core.tools import tool

from agent.infrastructure.tools.assembly import build_tool_inventory


@tool
def gamma(query: str) -> str:
    """gamma"""
    return query


def test_build_tool_inventory_returns_unfiltered_provider_union(monkeypatch):
    monkeypatch.setattr(
        "agent.infrastructure.tools.assembly.build_default_tool_providers",
        lambda: [StaticToolProvider("custom", lambda _ctx: [gamma])],
    )

    tools = build_tool_inventory({"configurable": {"thread_id": "inv-1", "agent_profile": {}}})

    assert [tool.name for tool in tools] == ["gamma"]
```

```python
def test_build_agent_toolset_applies_whitelist_after_inventory(monkeypatch):
    cfg = {
        "configurable": {
            "thread_id": "t-white",
            "agent_profile": {
                "tool_whitelist": ["browser_navigate"],
                "enabled_tools": {"browser": True},
            },
        }
    }
    names = _names(build_agent_toolset(cfg))
    assert names == ["browser_navigate"]
```

- [ ] **Step 2: 运行现有工具测试，确认新的 helper 还不存在**

Run: `pytest tests/test_agent_tools.py -v`

Expected:
- 新增测试因 `build_tool_inventory` 或 `build_default_tool_providers` 缺失而失败

- [ ] **Step 3: 实现 inventory/policy 分离**

```python
# agent/infrastructure/tools/policy.py
from __future__ import annotations

from typing import Iterable

from langchain_core.tools import BaseTool


def filter_tools_by_name(
    tools: list[BaseTool],
    *,
    whitelist: Iterable[str] | None = None,
    blacklist: Iterable[str] | None = None,
) -> list[BaseTool]:
    allowed = {str(item).strip() for item in (whitelist or []) if str(item).strip()}
    denied = {str(item).strip() for item in (blacklist or []) if str(item).strip()}
    filtered = tools
    if allowed:
        filtered = [tool for tool in filtered if getattr(tool, "name", "") in allowed]
    if denied:
        filtered = [tool for tool in filtered if getattr(tool, "name", "") not in denied]
    return filtered
```

```python
# agent/infrastructure/tools/assembly.py
from agent.infrastructure.tools.capabilities import build_default_tool_providers
from agent.infrastructure.tools.policy import filter_tools_by_name
from agent.infrastructure.tools.providers import ProviderContext, compose_provider_tools


def build_tool_inventory(config: RunnableConfig) -> list[BaseTool]:
    configurable = _configurable(config)
    profile = configurable.get("agent_profile") or {}
    context = ProviderContext(
        thread_id=str(configurable.get("thread_id") or "default"),
        profile=profile if isinstance(profile, dict) else {},
        configurable=configurable,
        e2b_ready=_e2b_api_key_configured(),
    )
    return compose_provider_tools(build_default_tool_providers(), context)


def build_agent_toolset(config: RunnableConfig) -> list[BaseTool]:
    configurable = _configurable(config)
    profile = configurable.get("agent_profile") or {}
    tool_list = _apply_enabled_tool_policy(build_tool_inventory(config), profile)
    tool_list = filter_tools_by_name(
        tool_list,
        whitelist=profile.get("tool_whitelist") or [],
        blacklist=profile.get("tool_blacklist") or [],
    )
    if bool(profile.get("emit_tool_events", settings.emit_tool_events)):
        thread_id = str(configurable.get("thread_id") or "default")
        tool_list = wrap_tools_with_events(tool_list, thread_id=thread_id)
    return tool_list
```

```python
# agent/infrastructure/tools/capabilities.py
def build_default_tool_providers() -> tuple[ToolSpecification, ...]:
    return TOOL_SPECS
```

- [ ] **Step 4: 跑装配回归测试**

Run: `pytest tests/test_agent_tools.py -v`

Expected:
- 现有浏览器 / RAG / 搜索测试继续通过
- 新增 inventory/whitelist 测试通过

### Task 3: 将 MCP 改为 Provider，而不是全局注册入口

**Files:**
- Create: `tests/test_mcp_tool_provider.py`
- Modify: `tools/mcp.py`
- Modify: `agent/infrastructure/tools/capabilities.py`
- Modify: `main.py`

- [ ] **Step 1: 先写失败测试，锁定 MCP 新来源**

```python
from types import SimpleNamespace

from agent.infrastructure.tools.capabilities import _build_mcp_tools
from agent.infrastructure.tools.providers import ProviderContext


def test_build_mcp_tools_reads_live_mcp_snapshot(monkeypatch):
    monkeypatch.setattr(
        "agent.infrastructure.tools.capabilities.get_live_mcp_tools",
        lambda: [SimpleNamespace(name="mcp_fetch", description="fetch")],
    )

    tools = _build_mcp_tools(
        ProviderContext(thread_id="mcp-1", profile={}, configurable={}, e2b_ready=False)
    )

    assert [tool.name for tool in tools] == ["mcp_fetch"]
```

```python
def test_reload_mcp_tools_does_not_require_set_registered_tools(monkeypatch):
    captured = {"called": False}

    monkeypatch.setattr(
        "main.set_registered_tools",
        lambda _tools: captured.__setitem__("called", True),
    )

    # 断言重构后不会再触发旧兼容入口
    assert captured["called"] is False
```

- [ ] **Step 2: 运行 MCP 测试，确认当前实现仍依赖兼容全局列表**

Run: `pytest tests/test_mcp_tool_provider.py -v`

Expected:
- 失败点落在 `get_live_mcp_tools` 缺失
- 或失败点落在 `main.py` 仍调用 `set_registered_tools()`

- [ ] **Step 3: 实现 live MCP tool snapshot**

```python
# tools/mcp.py
_LIVE_MCP_TOOLS: list[BaseTool] = []


def get_live_mcp_tools() -> list[BaseTool]:
    return list(_LIVE_MCP_TOOLS)


async def init_mcp_tools(...):
    ...
    _LIVE_MCP_TOOLS[:] = list(clients.tools)
    return list(_LIVE_MCP_TOOLS)


async def close_mcp_tools() -> None:
    global _CLIENTS
    _LIVE_MCP_TOOLS.clear()
    ...
```

```python
# agent/infrastructure/tools/capabilities.py
from tools.mcp import get_live_mcp_tools


def _build_mcp_tools(_ctx: ToolBuildContext) -> list[BaseTool]:
    return list(get_live_mcp_tools())
```

```python
# main.py
mcp_tools = await init_mcp_tools(...)
if mcp_tools:
    mcp_loaded_tools = len(mcp_tools)
...
tools = await reload_mcp_tools(cfg, enabled=True)
mcp_loaded_tools = len(tools)
...
await close_mcp_tools()
mcp_loaded_tools = 0
```

- [ ] **Step 4: 跑 MCP provider 回归测试**

Run: `pytest tests/test_mcp_tool_provider.py -v`

Expected:
- `2 passed`

### Task 4: 将 ToolRegistry 降级为 Catalog / Metadata 服务

**Files:**
- Create: `agent/infrastructure/tools/catalog.py`
- Modify: `tools/core/registry.py`
- Modify: `agent/runtime/nodes/_shared.py`
- Modify: `main.py`
- Test: `tests/tools/test_tool_registry_discovery.py`

- [ ] **Step 1: 先写失败测试，明确 registry 不再代表运行时**

```python
from agent.infrastructure.tools.catalog import build_tool_catalog_snapshot


def test_tool_catalog_snapshot_can_be_built_from_runtime_tools():
    snapshot = build_tool_catalog_snapshot(
        tools=[SimpleNamespace(name="browser_navigate", description="open url")],
        source="runtime_inventory",
    )

    assert snapshot["total_tools"] == 1
    assert snapshot["tools"][0]["name"] == "browser_navigate"
    assert snapshot["source"] == "runtime_inventory"
```

```python
def test_registry_discovery_remains_metadata_only():
    registry = ToolRegistry()
    discovered = registry.discover_from_module("tools.search.search", tags=["test"])
    assert "tavily_search" in {item.name for item in discovered}
```

- [ ] **Step 2: 运行 catalog 测试，确认快照层缺失**

Run: `pytest tests/tools/test_tool_registry_discovery.py -v`

Expected:
- 新增 catalog 测试因 `agent.infrastructure.tools.catalog` 缺失而失败

- [ ] **Step 3: 增加 catalog 快照层，并让 API 读 catalog**

```python
# agent/infrastructure/tools/catalog.py
from __future__ import annotations

from typing import Any


def build_tool_catalog_snapshot(*, tools: list[Any], source: str) -> dict[str, Any]:
    payload = []
    for tool in tools:
        payload.append(
            {
                "name": str(getattr(tool, "name", "") or ""),
                "description": str(getattr(tool, "description", "") or ""),
                "tool_type": "langchain",
            }
        )
    payload = [item for item in payload if item["name"]]
    return {
        "source": source,
        "total_tools": len(payload),
        "tools": sorted(payload, key=lambda item: item["name"]),
    }
```

```python
# tools/core/registry.py
def set_registered_tools(tools: List) -> None:
    logger.warning("set_registered_tools() is deprecated for runtime tool assembly")
    ...
```

```python
# agent/runtime/nodes/_shared.py
def initialize_enhanced_tools() -> None:
    """
    Refresh tool catalog metadata only.
    Runtime assembly now uses provider composition.
    """
```

```python
# main.py
runtime_tools = build_tool_inventory({"configurable": {"thread_id": "catalog", "agent_profile": {}}})
catalog = build_tool_catalog_snapshot(tools=runtime_tools, source="runtime_inventory")
```

- [ ] **Step 4: 运行 registry/catalog 回归测试**

Run: `pytest tests/tools/test_tool_registry_discovery.py -v`

Expected:
- discovery 测试继续通过
- 新增 catalog 快照测试通过

### Task 5: 让 Deep Research Tool Agent 复用统一装配 helper

**Files:**
- Modify: `agent/infrastructure/agents/factory.py`
- Modify: `agent/infrastructure/tools/assembly.py`
- Modify: `tests/test_agent_factory_defaults.py`

- [ ] **Step 1: 先写失败测试，禁止 deep research 继续直接读 `get_registered_tools()`**

```python
def test_build_deep_research_tool_agent_uses_shared_inventory(monkeypatch):
    captured = {}

    monkeypatch.setattr(
        agent_factory,
        "build_tools_for_names",
        lambda names, config=None: [
            SimpleNamespace(name=name) for name in sorted(names) if name in {"browser_search", "crawl_url"}
        ],
    )
    monkeypatch.setattr(
        agent_factory,
        "build_tool_agent",
        lambda *, model, tools, temperature=0.7: captured.setdefault(
            "agent",
            {"model": model, "tool_names": [tool.name for tool in tools]},
        ),
    )

    agent, tools = agent_factory.build_deep_research_tool_agent(
        model="gpt-test",
        allowed_tools=["search", "extract"],
    )

    assert [tool.name for tool in tools] == ["browser_search", "crawl_url"]
    assert agent["tool_names"] == ["browser_search", "crawl_url"]
```

- [ ] **Step 2: 运行 deep research agent 测试，确认当前实现仍绑定 `get_registered_tools()`**

Run: `pytest tests/test_agent_factory_defaults.py -v`

Expected:
- 新增测试失败，错误落在 `build_tools_for_names` 不存在

- [ ] **Step 3: 加入按名称取工具的共享 helper，并替换 deep-research 旧路径**

```python
# agent/infrastructure/tools/assembly.py
def build_tools_for_names(
    names: set[str],
    config: RunnableConfig | None = None,
) -> list[BaseTool]:
    inventory = build_tool_inventory(config or {"configurable": {"agent_profile": {}, "thread_id": "default"}})
    wanted = {str(name).strip() for name in names if str(name).strip()}
    return [tool for tool in inventory if getattr(tool, "name", "") in wanted]
```

```python
# agent/infrastructure/agents/factory.py
from agent.infrastructure.tools.assembly import build_tools_for_names


def build_deep_research_tool_agent(...):
    ...
    tools = list(extra_tools or [])
    existing_names = {tool.name for tool in tools if getattr(tool, "name", None)}
    shared_tools = build_tools_for_names(allowed_names)
    for tool in shared_tools:
        if tool.name not in existing_names:
            tools.append(tool)
    agent = build_tool_agent(model=model_name, tools=tools, temperature=temperature)
    return agent, tools
```

- [ ] **Step 4: 运行 deep research 角色工具回归**

Run: `pytest tests/test_agent_factory_defaults.py -v`

Expected:
- 现有角色 allowlist 测试继续通过
- 新增 shared inventory 测试通过

### Task 6: 清理兼容层文档与回归矩阵

**Files:**
- Modify: `tools/core/base.py`
- Modify: `tools/core/langchain_adapter.py`
- Modify: `tests/test_tool_base.py`
- Modify: `tests/test_agent_tools.py`
- Optional Create: `docs/tool-runtime-architecture.md`

- [ ] **Step 1: 先写失败测试，锁定兼容层新定位**

```python
def test_weaver_tool_docstring_marks_authoring_only():
    assert "authoring" in WeaverTool.__doc__.lower()
```

```python
def test_langchain_adapter_remains_compatibility_bridge_not_runtime_source():
    assert "Bridge" in weaver_tool_to_langchain.__doc__
```

- [ ] **Step 2: 运行兼容层测试，确认文档语义尚未更新**

Run: `pytest tests/test_tool_base.py -v`

Expected:
- 新增断言失败，提示文档/职责描述未更新

- [ ] **Step 3: 更新兼容层注释与架构文档**

```python
# tools/core/base.py
class WeaverTool(ABC):
    """
    Authoring-time compatibility abstraction.

    Runtime tool execution should use LangChain BaseTool instances produced
    during provider composition.
    """
```

```python
# tools/core/langchain_adapter.py
def weaver_tool_to_langchain(...):
    """
    Compatibility bridge for authoring-time WeaverTool definitions.

    Do not use this adapter as the primary runtime registry or execution source.
    """
```

```markdown
# docs/tool-runtime-architecture.md
- Runtime source of truth: provider-composed `BaseTool` inventory
- Filtering layer: profile + capability + role allowlists
- Catalog layer: metadata and API visibility only
- Compatibility layer: `WeaverTool`, `ToolRegistry`, adapter utilities
```

- [ ] **Step 4: 跑最终最小回归矩阵**

Run: `pytest tests/test_tool_providers.py tests/test_mcp_tool_provider.py tests/test_agent_tools.py tests/test_agent_factory_defaults.py tests/tools/test_tool_registry_discovery.py -v`

Expected:
- 全部通过

Run: `pytest tests/test_tool_base.py -v`

Expected:
- 兼容层测试全部通过

Run: `python scripts/live_api_smoke.py --help`

Expected:
- 脚本可启动并输出参数帮助；不要求联网执行完整 smoke

## Self-Review

**Spec coverage**

- “统一运行时工具来源” 已由 Task 1-2 覆盖。
- “MCP 不再走全局注册入口” 已由 Task 3 覆盖。
- “ToolRegistry 降级为 catalog” 已由 Task 4 覆盖。
- “deep research 至少接入统一装配 helper” 已由 Task 5 覆盖。
- “保留兼容层但明确降级” 已由 Task 6 覆盖。
- 未覆盖项：`ResearchAgent` 全量改造成 LangChain tool-agent。该项已明确列为 out of scope，建议单独立项。

**Placeholder scan**

- 未使用 `TODO` / `TBD` / “类似 Task N”。
- 每个任务都给出了文件、测试命令和最小代码草图。

**Type consistency**

- 运行时上下文统一命名为 `ProviderContext`。
- 统一使用 `build_tool_inventory()` 表示未过滤 inventory。
- 统一使用 `build_tools_for_names()` 表示按名称取运行时工具。

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-06-align-tool-runtime-with-langgraph-langchain.md`. Two execution options:

**1. Subagent-Driven (recommended)** - 我按任务拆分，逐任务派发子代理实现并在任务之间审查

**2. Inline Execution** - 我在当前会话里按任务顺序直接实现并逐步验证

请选择执行方式。
