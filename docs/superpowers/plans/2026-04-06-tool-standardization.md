# Tool 系统完整标准化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 Weaver 的 tool 系统一次性收敛为标准 LangChain/LangGraph 风格，只保留 concrete `BaseTool/@tool/StructuredTool` 作为正式工具抽象，删除 `WeaverTool`、`ToolResult`、`tool_schema`、旧 `ToolRegistry`、`capability` 和 `toolset` 公共契约，并同步完成 API、profile、state、测试和前端类型的 breaking 更新。

**Architecture:** 运行时以 `list[BaseTool]` 为唯一真相源。profile 直接声明允许的 concrete tool names；聊天和 deep research 路径都直接选择 concrete tools，而不是先映射 capability/toolset；tool catalog 直接从运行时 inventory 派生。所有旧 registry/discovery 入口都删除，不保留兼容分支。

**Tech Stack:** Python 3.11, FastAPI, LangChain 1.x, LangGraph 1.x, Pydantic v2, pytest, openapi-typescript, TypeScript

---

**Scope Notes**

- 本计划是一次性 breaking 标准化，不保留兼容字段、兼容 alias、兼容 API 路径。
- 本计划不包含 `git commit` 步骤，遵循仓库约束。
- 本计划假定具体 tool 的 `name` 尽量稳定，避免无意义重命名事件流和断言。
- 本计划优先改“工具协议和对外契约”，不重写每个工具的业务实现。

**File Map**

- Delete: `tools/core/base.py`
  作用：删除 `WeaverTool`、`ToolResult`、`tool_schema` 这套自定义工具协议。
- Delete: `tools/core/langchain_adapter.py`
  作用：删除 `WeaverTool -> LangChain tool` 兼容桥。
- Delete: `tools/core/registry.py`
  作用：删除旧静态 registry/discovery/compat 入口。
- Delete: `agent/infrastructure/tools/capabilities.py`
  作用：删除 capability/toolset 主路径和 `TOOL_SPECS`。
- Delete: `tests/test_tool_base.py`
  作用：删除围绕 `WeaverTool/ToolResult` 的测试。
- Delete: `tests/tools/test_tool_registry_discovery.py`
  作用：删除围绕旧 registry discovery 的测试。
- Modify: `common/agents_store.py`
  作用：将 `AgentProfile` 从 `enabled_tools` 重构为 concrete tool allow/block 配置。
- Modify: `agent/domain/execution.py`
  作用：删除 `ToolCapability`、重构 `AgentProfileConfig`。
- Modify: `agent/core/state.py`
  作用：删除 `required_capabilities`、`enabled_tools`，新增 concrete tool 选择字段。
- Modify: `agent/domain/state.py`
  作用：同步状态切片结构，移除 capability/toolset 痕迹。
- Modify: `agent/application/state.py`
  作用：初始化新的 profile/state 契约。
- Modify: `agent/infrastructure/tools/assembly.py`
  作用：将运行时装配收敛为 inventory + concrete tool filter。
- Modify: `agent/infrastructure/tools/policy.py`
  作用：从 profile 过滤切换到 concrete tool allow/block 规则。
- Modify: `agent/infrastructure/tools/providers.py`
  作用：保留 provider 组合，但不再暴露 toolset/capability 语义。
- Modify: `agent/infrastructure/tools/catalog.py`
  作用：明确 catalog 语义，必要时补充来源字段。
- Modify: `agent/infrastructure/tools/__init__.py`
  作用：清理旧 capability/toolset 导出。
- Modify: `agent/infrastructure/agents/factory.py`
  作用：deep research 角色直接按 concrete tool names 过滤，不再使用 capability。
- Modify: `agent/runtime/nodes/chat.py`
  作用：改为直接选择 `selected_tools`，不再产出 `required_capabilities`。
- Modify: `agent/runtime/nodes/answer.py`
  作用：直接消费 `selected_tools` 构建 tool agent。
- Modify: `agent/runtime/nodes/_shared.py`
  作用：删除旧 registry 初始化和 `get_registered_tools()` 依赖。
- Modify: `agent/runtime/nodes/__init__.py`
  作用：移除 `initialize_enhanced_tools` 等旧公开符号。
- Modify: `agent/runtime/__init__.py`
  作用：同步 runtime 公开导出面。
- Modify: `agent/api.py`
  作用：移除 `initialize_enhanced_tools` 公共 API 暴露。
- Modify: `agent/__init__.py`
  作用：同步顶层 `agent` 包公共符号。
- Modify: `main.py`
  作用：重构 profile schema、catalog API、默认 agent、health 字段、删除 registry refresh。
- Modify: `data/agents.json`
  作用：迁移默认 profile 到 concrete tool 列表。
- Modify: `agent/prompts/system_prompts.py`
  作用：清理 `web_search` 等旧公共术语，改为 tool/catalog 语言。
- Modify: `web/lib/api-types.ts`
  作用：重新生成并接入新的 agents/catalog OpenAPI 类型。
- Modify: `web/hooks/useBrowserEvents.ts`
  作用：如有必要，仅保留 concrete tool name 判断，不依赖旧 registry/toolset 语义。
- Modify: `tests/test_agents_api.py`
  作用：更新 profile API 的请求/响应字段。
- Modify: `tests/test_agent_tools.py`
  作用：改为 concrete tool profile/filter 测试，删除 capability/toolset 断言。
- Modify: `tests/test_agent_mode_selection.py`
  作用：改为 `selected_tools` 断言。
- Modify: `tests/test_agent_factory_defaults.py`
  作用：deep research 角色过滤改为 concrete tool 断言。
- Modify: `tests/test_agent_public_api.py`
  作用：删除 `initialize_enhanced_tools` 公共符号断言。
- Modify: `tests/test_agent_runtime_public_contracts.py`
  作用：收口 runtime 公开面。
- Modify: `tests/test_mcp_tool_provider.py`
  作用：删除围绕 `set_registered_tools()` 的历史约束，改测 inventory 语义。
- Modify: `tests/test_tool_catalog_api.py`
  作用：切换到 `/api/tools/catalog` 和新的 health 字段。
- Modify: `tests/test_agent_state_slices.py`
  作用：更新 state slice 中的 profile/tool 字段。
- Modify: `tests/test_prompt_comparison.py`
  作用：删除 `enabled_tools` 旧语义断言，改为 concrete tools。

### Task 1: 先锁定新的公共契约

**Files:**
- Modify: `common/agents_store.py`
- Modify: `agent/domain/execution.py`
- Modify: `agent/core/state.py`
- Modify: `agent/domain/state.py`
- Modify: `agent/application/state.py`
- Test: `tests/test_agents_api.py`
- Test: `tests/test_agent_state_slices.py`

- [ ] **Step 1: 先写失败测试，锁定 profile 和 state 的新字段**

```python
# tests/test_agents_api.py
create_payload = {
    "name": "My Agent",
    "description": "demo",
    "system_prompt": "You are a test agent.",
    "tools": ["browser_search", "browser_navigate", "crawl_url"],
    "blocked_tools": ["browser_click"],
}

resp3 = await ac.post("/api/agents", json=create_payload)
assert resp3.status_code == 200
created = resp3.json()
assert created["tools"] == ["browser_search", "browser_navigate", "crawl_url"]
assert created["blocked_tools"] == ["browser_click"]
assert "enabled_tools" not in created
```

```python
# tests/test_agent_state_slices.py
def test_build_initial_agent_state_uses_concrete_tools_contract():
    request = build_execution_request(
        input_text="帮我打开 OpenAI 首页并总结要点",
        thread_id="tool-state-1",
        user_id="user-1",
        mode_info={"mode": "agent"},
        agent_profile={
            "id": "default",
            "tools": ["browser_search", "browser_navigate", "crawl_url"],
            "blocked_tools": ["browser_click"],
        },
    )

    state = build_initial_agent_state(request)

    assert state["selected_tools"] == []
    assert state["available_tools"] == ["browser_search", "browser_navigate", "crawl_url"]
    assert state["blocked_tools"] == ["browser_click"]
    assert "required_capabilities" not in state
    assert "enabled_tools" not in state
```

- [ ] **Step 2: 运行测试，确认当前实现仍暴露旧字段**

Run: `pytest tests/test_agents_api.py tests/test_agent_state_slices.py -v`

Expected:
- FAIL，表现为 `enabled_tools` 仍在 schema/响应中
- FAIL，表现为 state 缺少 `available_tools` / `selected_tools`

- [ ] **Step 3: 最小重构 profile 与 state 模型**

```python
# common/agents_store.py
class AgentProfile(BaseModel):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str = ""
    system_prompt: str = ""
    model: str = ""
    tools: list[str] = Field(default_factory=list)
    blocked_tools: list[str] = Field(default_factory=list)
    mcp_servers: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=_utc_now_iso)
    updated_at: str = Field(default_factory=_utc_now_iso)
```

```python
# agent/domain/execution.py
@dataclass(frozen=True)
class AgentProfileConfig:
    id: str = ""
    system_prompt: str = ""
    tools: list[str] = field(default_factory=list)
    blocked_tools: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    prompt_pack: str = ""
    prompt_variant: str = "full"
```

```python
# agent/core/state.py
class AgentState(TypedDict):
    ...
    available_tools: List[str]
    blocked_tools: List[str]
    selected_tools: List[str]
    ...
```

```python
# agent/application/state.py
initial_state: dict[str, Any] = {
    ...
    "available_tools": list(request.agent_profile.tools),
    "blocked_tools": list(request.agent_profile.blocked_tools),
    "selected_tools": [],
    ...
}
```

- [ ] **Step 4: 重新运行契约测试**

Run: `pytest tests/test_agents_api.py tests/test_agent_state_slices.py -v`

Expected:
- PASS，且输出中不再出现 `enabled_tools` / `required_capabilities`

### Task 2: 将运行时装配收敛为 concrete tool inventory

**Files:**
- Modify: `agent/infrastructure/tools/assembly.py`
- Modify: `agent/infrastructure/tools/policy.py`
- Modify: `agent/infrastructure/tools/providers.py`
- Modify: `agent/infrastructure/tools/__init__.py`
- Test: `tests/test_agent_tools.py`

- [ ] **Step 1: 先写失败测试，锁定 profile 直接按 tool name 过滤**

```python
# tests/test_agent_tools.py
def test_build_agent_toolset_filters_inventory_by_concrete_profile_tools():
    cfg = {
        "configurable": {
            "thread_id": "tools-1",
            "agent_profile": {
                "tools": ["browser_navigate", "crawl_url"],
                "blocked_tools": ["browser_click"],
            },
        }
    }

    names = _names(build_agent_toolset(cfg))

    assert names == ["browser_navigate", "crawl_url"]
```

```python
def test_build_agent_toolset_applies_blocked_tools_after_allowlist():
    cfg = {
        "configurable": {
            "thread_id": "tools-2",
            "agent_profile": {
                "tools": ["browser_navigate", "browser_click"],
                "blocked_tools": ["browser_click"],
            },
        }
    }

    names = _names(build_agent_toolset(cfg))

    assert names == ["browser_navigate"]
```

- [ ] **Step 2: 运行测试，确认当前装配仍依赖 `enabled_tools/capabilities`**

Run: `pytest tests/test_agent_tools.py -v`

Expected:
- FAIL，表现为 `build_agent_toolset()` 不认识 `tools/blocked_tools`
- FAIL，旧 capability 测试仍主导装配逻辑

- [ ] **Step 3: 最小重构装配接口**

```python
# agent/infrastructure/tools/policy.py
from __future__ import annotations

from collections.abc import Iterable
from langchain_core.tools import BaseTool


def filter_tools_by_name(
    tools: list[BaseTool],
    *,
    allowed: Iterable[str] | None = None,
    blocked: Iterable[str] | None = None,
) -> list[BaseTool]:
    allowed_set = {str(item).strip() for item in (allowed or []) if str(item).strip()}
    blocked_set = {str(item).strip() for item in (blocked or []) if str(item).strip()}

    selected = tools
    if allowed_set:
        selected = [tool for tool in selected if getattr(tool, "name", "") in allowed_set]
    if blocked_set:
        selected = [tool for tool in selected if getattr(tool, "name", "") not in blocked_set]
    return selected
```

```python
# agent/infrastructure/tools/assembly.py
def build_tool_inventory(config: RunnableConfig) -> list[BaseTool]:
    return compose_provider_tools(build_default_tool_providers(), _provider_context(config))


def build_agent_toolset(config: RunnableConfig) -> list[BaseTool]:
    configurable = _configurable(config)
    profile = configurable.get("agent_profile") or {}
    if not isinstance(profile, dict):
        profile = {}

    inventory = build_tool_inventory(config)
    tools = filter_tools_by_name(
        inventory,
        allowed=profile.get("tools") or [],
        blocked=profile.get("blocked_tools") or [],
    )
    ...
    return tools
```

```python
# agent/infrastructure/tools/__init__.py
from agent.infrastructure.tools.assembly import (
    build_agent_toolset,
    build_tool_inventory,
    build_tools_for_names,
)
```

- [ ] **Step 4: 删除 capability 相关测试并只跑新的 inventory/profile 测试**

Run: `pytest tests/test_agent_tools.py -v`

Expected:
- PASS，且测试文件中不再 import `ToolCapability`

### Task 3: 删除 capability/toolset 主路径

**Files:**
- Delete: `agent/infrastructure/tools/capabilities.py`
- Modify: `agent/infrastructure/tools/__init__.py`
- Modify: `agent/infrastructure/agents/factory.py`
- Modify: `agent/runtime/nodes/chat.py`
- Modify: `agent/runtime/nodes/answer.py`
- Test: `tests/test_agent_mode_selection.py`
- Test: `tests/test_agent_factory_defaults.py`

- [ ] **Step 1: 先写失败测试，锁定运行时直接选择 concrete tools**

```python
# tests/test_agent_mode_selection.py
def test_chat_respond_node_selects_concrete_tools_for_current_info_queries():
    result = chat_nodes.chat_respond_node(
        {
            "input": "Use current web search to verify today's price of Bitcoin.",
            "messages": [],
            "memory_context": {"stored": [], "relevant": []},
            "available_tools": ["browser_search", "crawl_url", "execute_python_code"],
            "blocked_tools": [],
        },
        {"configurable": {}},
    )

    assert result["needs_tools"] is True
    assert result["selected_tools"] == ["browser_search", "crawl_url"]
    assert "required_capabilities" not in result
```

```python
def test_tool_agent_node_uses_selected_tools(monkeypatch):
    class FakeAgent:
        def invoke(self, payload, config=None):
            return {"messages": [AIMessage(content="Structured comparison")]}

    captured = {}

    monkeypatch.setattr(
        answer_nodes,
        "build_tools_for_names",
        lambda names, _config=None: [captured.setdefault("names", sorted(names))] and [],
    )
    monkeypatch.setattr(answer_nodes, "build_tool_agent", lambda **_kwargs: FakeAgent())

    result = answer_nodes.tool_agent_node(
        {
            "input": "Compare EV battery supply chain risks across the US and EU in 2025.",
            "messages": [],
            "memory_context": {"stored": [], "relevant": []},
            "selected_tools": ["browser_search", "crawl_url"],
        },
        {"configurable": {}},
    )

    assert captured["names"] == ["browser_search", "crawl_url"]
    assert result["assistant_draft"] == "Structured comparison"
```

- [ ] **Step 2: 运行测试，确认 chat/answer 仍依赖 `required_capabilities`**

Run: `pytest tests/test_agent_mode_selection.py tests/test_agent_factory_defaults.py -v`

Expected:
- FAIL，表现为 chat node 仍写入 `required_capabilities`
- FAIL，表现为 `build_deep_research_tool_agent()` 仍使用 capability 解析

- [ ] **Step 3: 用 concrete tool names 重写选择与 deep research 过滤**

```python
# agent/runtime/nodes/chat.py
def _select_tools_for_input(user_input: str, available_tools: list[str]) -> list[str]:
    text = str(user_input or "").strip().lower()
    wanted: list[str] = []

    if any(token in text for token in ("latest", "today", "current", "price", "news")):
        wanted.extend(["browser_search", "crawl_url"])
    if any(token in text for token in ("open ", "website", "browse", "click", "login")):
        wanted.extend(["browser_navigate", "browser_click"])
    if any(token in text for token in ("python", "script", "calculate", "chart", "plot")):
        wanted.append("execute_python_code")

    allowed = {name for name in available_tools if name}
    return sorted({name for name in wanted if name in allowed})
```

```python
# agent/runtime/nodes/answer.py
tools = deps.build_tools_for_names(set(state.get("selected_tools") or []), config)
```

```python
# agent/infrastructure/agents/factory.py
_DEEP_RESEARCH_ROLE_TOOL_ALLOWLISTS = {
    "clarify": {"fabric"},
    "scope": {"fabric"},
    "supervisor": {"fabric"},
    "researcher": {"fabric", "browser_search", "crawl_url", "sb_browser_extract_text"},
    "verifier": {"fabric", "browser_search", "crawl_url"},
    "reporter": {"fabric", "execute_python_code"},
}
```

- [ ] **Step 4: 删除 capability/toolset 导出并验证新路径**

Run: `pytest tests/test_agent_mode_selection.py tests/test_agent_factory_defaults.py -v`

Expected:
- PASS
- 仓库主路径不再 import `ToolCapability`

### Task 4: 删除旧工具协议与 registry

**Files:**
- Delete: `tools/core/base.py`
- Delete: `tools/core/langchain_adapter.py`
- Delete: `tools/core/registry.py`
- Delete: `tests/test_tool_base.py`
- Delete: `tests/tools/test_tool_registry_discovery.py`
- Modify: `tools/__init__.py`
- Modify: `agent/runtime/nodes/_shared.py`
- Modify: `agent/runtime/nodes/__init__.py`
- Modify: `agent/runtime/__init__.py`
- Modify: `agent/api.py`
- Modify: `agent/__init__.py`
- Test: `tests/test_agent_public_api.py`
- Test: `tests/test_agent_runtime_public_contracts.py`

- [ ] **Step 1: 先写失败测试，锁定公开面不再暴露旧 registry 初始化**

```python
# tests/test_agent_public_api.py
def test_agent_package_exports_public_symbols() -> None:
    agent = importlib.import_module("agent")

    expected = [
        "AgentState",
        "ToolEvent",
        "build_execution_request",
        "build_initial_agent_state",
        "create_checkpointer",
        "create_research_graph",
        "event_stream_generator",
        "get_default_agent_prompt",
        "get_emitter",
        "remove_emitter",
    ]

    missing = [name for name in expected if not hasattr(agent, name)]
    assert missing == []
    assert not hasattr(agent, "initialize_enhanced_tools")
```

```python
# tests/test_agent_runtime_public_contracts.py
def test_runtime_active_entrypoints_remain_importable():
    assert callable(runtime_nodes.route_node)
    assert callable(runtime_nodes.chat_respond_node)
    assert callable(runtime_nodes.deep_research_node)
    assert callable(runtime_nodes.finalize_answer_node)
    assert callable(runtime_nodes.human_review_node)
    assert callable(runtime_nodes.tool_agent_node)
    assert not hasattr(runtime_nodes, "initialize_enhanced_tools")
```

- [ ] **Step 2: 运行测试，确认旧公开面仍存在**

Run: `pytest tests/test_agent_public_api.py tests/test_agent_runtime_public_contracts.py -v`

Expected:
- FAIL，表现为 `initialize_enhanced_tools` 仍在公共导出里

- [ ] **Step 3: 删除旧公开面并清理所有 registry 依赖**

```python
# agent/api.py
from agent.application import build_execution_request, build_initial_agent_state
from agent.core import AgentState, ToolEvent, event_stream_generator, get_emitter, remove_emitter
from agent.prompts import get_default_agent_prompt
from agent.runtime.graph import create_checkpointer, create_research_graph

__all__ = sorted(
    [
        "AgentState",
        "ToolEvent",
        "build_execution_request",
        "build_initial_agent_state",
        "create_checkpointer",
        "create_research_graph",
        "event_stream_generator",
        "get_default_agent_prompt",
        "get_emitter",
        "remove_emitter",
    ]
)
```

```python
# agent/runtime/nodes/_shared.py
def _get_writer_tools() -> list[Any]:
    return [execute_python_code]
```

```python
# tools/__init__.py
from tools.code.code_executor import execute_python_code
from tools.crawl.crawler import crawl_url, crawl_urls
from tools.search.fallback_search import fallback_search
from tools.search.search import tavily_search
```

- [ ] **Step 4: 删除文件并验证公开面**

Run: `pytest tests/test_agent_public_api.py tests/test_agent_runtime_public_contracts.py -v`

Expected:
- PASS
- `rg -n "WeaverTool|tool_schema|ToolResult|get_registered_tools|set_registered_tools|initialize_enhanced_tools" agent tools tests` 只剩历史文档或 0 结果

### Task 5: 将 registry API 改成 catalog API

**Files:**
- Modify: `main.py`
- Modify: `agent/infrastructure/tools/catalog.py`
- Modify: `tests/test_tool_catalog_api.py`
- Modify: `web/lib/api-types.ts`

- [ ] **Step 1: 先写失败测试，锁定新的 catalog 路径与 health 字段**

```python
# tests/test_tool_catalog_api.py
@pytest.mark.asyncio
async def test_tools_catalog_endpoint_uses_runtime_inventory(monkeypatch):
    monkeypatch.setattr(
        main,
        "build_tool_inventory",
        lambda _config: [SimpleNamespace(name="browser_navigate", description="open url")],
    )

    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/api/tools/catalog")

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["stats"]["total_tools"] == 1
    assert payload["tools"][0]["name"] == "browser_navigate"
```

```python
@pytest.mark.asyncio
async def test_agent_health_endpoint_uses_catalog_inventory_count(monkeypatch):
    monkeypatch.setattr(
        main,
        "build_tool_inventory",
        lambda _config: [
            SimpleNamespace(name="browser_navigate", description="open url"),
            SimpleNamespace(name="crawl_url", description="crawl"),
        ],
    )

    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/api/health/agent")

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["tool_catalog_total_tools"] == 2
```

- [ ] **Step 2: 运行测试，确认当前仍暴露 `/api/tools/registry`**

Run: `pytest tests/test_tool_catalog_api.py -v`

Expected:
- FAIL，表现为 `/api/tools/catalog` 404 或 health 字段名不匹配

- [ ] **Step 3: 最小改造 API schema 和路由**

```python
# main.py
class ToolCatalogStats(BaseModel):
    total_tools: int
    active_tools: int
    by_type: Dict[str, int]
    tags: List[str]


class ToolCatalogItem(BaseModel):
    name: str
    description: str = ""
    tool_type: str = ""
    parameters: Dict[str, Any] = Field(default_factory=dict)
    module_name: str = ""
    class_name: str = ""
    function_name: str = ""
    tags: List[str] = Field(default_factory=list)


class ToolCatalogResponse(BaseModel):
    stats: ToolCatalogStats
    tools: List[ToolCatalogItem]
```

```python
@app.get("/api/tools/catalog", response_model=ToolCatalogResponse)
async def get_tool_catalog():
    snapshot = build_tool_catalog_snapshot(
        tools=build_tool_inventory({"configurable": {"thread_id": "catalog", "agent_profile": {}}}),
        source="runtime_inventory",
    )
    ...
```

```python
class AgentHealthResponse(BaseModel):
    agents_count: int
    agent_ids: List[str]
    tool_catalog_total_tools: int
    ...
```

- [ ] **Step 4: 更新前端 OpenAPI 类型并验证 catalog API**

Run: `pytest tests/test_tool_catalog_api.py -v`

Expected:
- PASS

Run: `make openapi-types`

Expected:
- `web/lib/api-types.ts` 更新为 `/api/tools/catalog`

### Task 6: 更新默认 profile、prompt 和 deep runtime 配置

**Files:**
- Modify: `main.py`
- Modify: `data/agents.json`
- Modify: `agent/prompts/system_prompts.py`
- Modify: `tests/test_prompt_comparison.py`

- [ ] **Step 1: 先写失败测试，锁定默认 profile 使用 concrete tools**

```python
# tests/test_prompt_comparison.py
ctx = {
    "agent_profile": {
        "tools": ["browser_search", "crawl_url", "execute_python_code"],
        "blocked_tools": [],
    }
}

assert "enabled_tools" not in ctx["agent_profile"]
```

- [ ] **Step 2: 运行测试，确认默认数据和 prompt 仍依赖旧术语**

Run: `pytest tests/test_prompt_comparison.py -v`

Expected:
- FAIL，表现为 fixture/context 仍包含 `enabled_tools`

- [ ] **Step 3: 最小更新默认 profile 和提示词**

```python
# main.py
ensure_default_agent(
    default_profile=AgentProfile(
        id="default",
        name="Weaver Default Agent",
        description="Default tool-using agent profile for agent mode.",
        system_prompt=get_default_agent_prompt(),
        tools=[
            "browser_search",
            "browser_navigate",
            "crawl_url",
            "execute_python_code",
        ],
        blocked_tools=[],
        metadata={"protected": True},
    )
)
```

```json
// data/agents.json
{
  "id": "default",
  "name": "Weaver Default Agent",
  "tools": ["browser_search", "browser_navigate", "crawl_url", "execute_python_code"],
  "blocked_tools": []
}
```

```text
# agent/prompts/system_prompts.py
将 “Use web_search to get an overview” 改为 “Use search tools such as browser_search or crawl_url to get an overview”
```

- [ ] **Step 4: 重新运行 prompt/default profile 相关测试**

Run: `pytest tests/test_prompt_comparison.py tests/test_agents_api.py -v`

Expected:
- PASS

### Task 7: 更新前端与浏览器事件消费面

**Files:**
- Modify: `web/lib/api-types.ts`
- Modify: `web/hooks/useBrowserEvents.ts`

- [ ] **Step 1: 先写一个最小静态校验目标**

```ts
// web/lib/api-types.ts
// 目标：不再出现 "/api/tools/registry"、"enabled_tools"、"ToolRegistryResponse"
```

```ts
// web/hooks/useBrowserEvents.ts
const isBrowserRelatedTool = (tool?: string | null) => {
  if (!tool) return false
  return (
    tool.startsWith('sb_browser') ||
    tool.startsWith('browser_') ||
    tool === 'browser_use' ||
    tool === 'sandbox_web_search' ||
    tool.startsWith('sandbox_search') ||
    tool.startsWith('sandbox_extract_search')
  )
}
```

- [ ] **Step 2: 运行前端类型生成与检索，确认旧 schema 仍存在**

Run: `rg -n "/api/tools/registry|enabled_tools|ToolRegistryResponse" web/lib/api-types.ts`

Expected:
- 有匹配结果

- [ ] **Step 3: 更新 OpenAPI 生成物并做必要的最小前端兼容改动**

```ts
// 预期结果
// web/lib/api-types.ts 中改为：
// - "/api/tools/catalog"
// - AgentProfile.tools
// - AgentProfile.blocked_tools
// - ToolCatalogResponse
```

- [ ] **Step 4: 验证前端类型层清理完成**

Run: `rg -n "/api/tools/registry|enabled_tools|ToolRegistryResponse" web/lib/api-types.ts`

Expected:
- 无结果

### Task 8: 全量回归与残留清理

**Files:**
- Modify: `tests/test_mcp_tool_provider.py`
- Modify: `tests/test_agent_public_api.py`
- Modify: `tests/test_agent_runtime_public_contracts.py`
- Modify: `tests/test_tool_catalog_api.py`
- Modify: `tests/test_agent_factory_defaults.py`
- Modify: 其他受影响测试

- [ ] **Step 1: 先列出必须为 0 的旧符号残留**

```bash
rg -n "WeaverTool|tool_schema|ToolResult|ToolCapability|required_capabilities|enabled_tools|tool_whitelist|tool_blacklist|/api/tools/registry|initialize_enhanced_tools|get_registered_tools|set_registered_tools" agent tools main.py tests web
```

Expected:
- 初始阶段仍有大量命中

- [ ] **Step 2: 逐项清理残留引用并同步修正测试**

```python
# tests/test_mcp_tool_provider.py
def test_build_mcp_tools_reads_live_mcp_snapshot(monkeypatch):
    monkeypatch.setattr(
        "agent.infrastructure.tools.assembly.get_live_mcp_tools",
        lambda: [SimpleNamespace(name="mcp_fetch", description="fetch")],
    )
```

```python
# tests/test_agent_factory_defaults.py
assert [tool.name for tool in tools] == ["browser_search", "crawl_url"]
```

- [ ] **Step 3: 跑后端测试分组**

Run: `pytest tests/test_agents_api.py tests/test_agent_tools.py tests/test_agent_mode_selection.py tests/test_agent_factory_defaults.py tests/test_tool_catalog_api.py tests/test_agent_public_api.py tests/test_agent_runtime_public_contracts.py tests/test_agent_state_slices.py tests/test_prompt_comparison.py tests/test_mcp_tool_provider.py -v`

Expected:
- 全部 PASS

- [ ] **Step 4: 跑面向契约的最终检索**

Run: `rg -n "WeaverTool|tool_schema|ToolResult|ToolCapability|required_capabilities|enabled_tools|tool_whitelist|tool_blacklist|/api/tools/registry|initialize_enhanced_tools|get_registered_tools|set_registered_tools" agent tools main.py tests web`

Expected:
- 0 结果

Run: `pytest -q`

Expected:
- 全部 PASS，或仅剩与本次无关的已知失败

**Plan Self-Review**

- spec coverage：
  - 已覆盖删除旧工具协议、删除 capability/toolset、profile breaking、catalog API 重命名、deep research concrete tool 过滤、前端 OpenAPI 更新、默认数据与 prompt 清理。
- placeholder scan：
  - 无 `TBD` / `TODO` / “后续再处理” 占位描述。
- type consistency：
  - 统一使用 `tools`、`blocked_tools`、`available_tools`、`selected_tools`、`ToolCatalog*` 命名。
