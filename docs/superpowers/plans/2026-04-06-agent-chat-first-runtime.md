# Agent Chat-First Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将顶层 `agent` 分支从默认工具代理改造为默认普通对话、按需升级到最小授权工具代理的 chat-first 运行模型。

**Architecture:** 保持根图仍由 `router` 选择 `agent|deep_research`，但将 `agent` 分支拆成 `chat_respond -> tool_agent? -> finalize`。真实会话只保存在 `messages`，profile/memory/browser hint 改为运行时注入，工具集按 `required_capabilities` 最小装配。

**Tech Stack:** Python 3.11, FastAPI, LangGraph 1.x, LangChain 1.x, Pydantic v2, pytest

---

**Post-Implementation Note**

- 本计划记录了最初的实施路径。
- 最终落地代码已经进一步收紧：`agent_node` 兼容层已删除，不再作为公开 runtime 入口存在。
- 根图最终也已进一步简化：`finalize` 与 `deep_research` 直接连到 `END`，不再经过单独 review 节点。
- 当前真实公开面以 `chat_respond_node`、`tool_agent_node`、`finalize_answer_node` 为准。

**Scope Notes**

- 本计划只实现 chat-first `agent` 分支，不改 Deep Research 内层 runtime 结构。
- 保留现有 checkpointer、session persistence、tool provider 基建。
- 按仓库约束，本计划不包含 `git commit` 步骤。
- 最终公开面不再保留 `agent_node` 兼容入口，只暴露 chat-first 原生节点。

**File Map**

- Create: `agent/runtime/nodes/chat.py`
  作用：实现 `chat_respond_node`，负责普通对话优先与工具升级判定。
- Create: `agent/runtime/nodes/finalize.py`
  作用：统一应用输出 contract、回写 assistant 消息、投影兼容字段。
- Create: `agent/runtime/nodes/prompting.py`
  作用：构建运行时 system prompt、本轮 memory context、browser hint 注入逻辑。
- Create: `tests/test_chat_first_agent_nodes.py`
  作用：覆盖 chat-first 分支、工具升级分支与兼容 `agent_node` 包装器。
- Create: `tests/test_agent_prompt_runtime_context.py`
  作用：覆盖动态 prompt、memory context、不污染 `messages` 的构造规则。
- Modify: `agent/application/state.py`
  作用：停止向 `messages` 注入 profile/memory `SystemMessage`，改为保存结构化 memory context。
- Modify: `agent/core/state.py`
  作用：扩展 `AgentState` 字段并维持结构化 slices 投影。
- Modify: `agent/domain/state.py`
  作用：扩展 `ResearchState` / `ConversationState` 投影，包含 memory context 与 chat-first 中间字段。
- Modify: `agent/runtime/nodes/answer.py`
  作用：收缩为 `tool_agent_node`，不再承担默认聊天主路径。
- Modify: `agent/runtime/nodes/__init__.py`
  作用：导出 `chat_respond_node`、`tool_agent_node`、`finalize_answer_node` 等原生节点。
- Modify: `agent/runtime/__init__.py`
  作用：收敛公开 runtime entrypoints，只保留 chat-first 原生节点。
- Modify: `agent/runtime/graph.py`
  作用：将根图从旧单入口 `agent` 路径改为 `router -> chat_respond -> tool_agent?/finalize -> END`，并让 `deep_research` 直接终止。
- Modify: `agent/runtime/nodes/deep_research.py`
  作用：移除简单 factual deep 查询回退到 `agent_node` 的逻辑，保持 deep 模式语义封闭。
- Modify: `agent/runtime/nodes/_shared.py`
  作用：收缩 fast path 与共用 helper，去掉对持久 `SystemMessage` 语义的依赖。
- Modify: `agent/infrastructure/tools/assembly.py`
  作用：新增 `build_tools_for_capabilities()`，按能力最小授权返回工具列表。
- Modify: `agent/infrastructure/tools/__init__.py`
  作用：导出 capability-based tool assembly 入口。
- Modify: `main.py`
  作用：更新根图节点流式状态投影、主回答 token 放行规则与 node name 映射。
- Modify: `tests/test_agent_state_slices.py`
  作用：锁定新状态契约和不污染 `messages` 的初始化行为。
- Modify: `tests/test_agent_mode_selection.py`
  作用：从 fast-path 主导测试调整为 chat-first / capability escalation 测试。
- Modify: `tests/test_agent_tools.py`
  作用：验证 capability-based tool assembly 只暴露最小工具集。
- Modify: `tests/test_root_graph_contract.py`
  作用：锁定新的根图节点结构与条件边。
- Modify: `tests/test_deepsearch_mode_selection.py`
  作用：锁定 Deep Research 简单问题也继续留在 deep runner，不再回退到 `agent_node`。
- Modify: `tests/test_chat_sse_process_progress.py`
  作用：锁定新节点名下的流式状态映射与 thinking intro 行为。
- Modify: `tests/test_agent_runtime_public_contracts.py`
  作用：断言原生节点 entrypoints 可导入，且 `agent_node` 已被移除。

### Task 1: 收紧状态契约并停止污染 `messages`

**Files:**
- Modify: `agent/application/state.py`
- Modify: `agent/core/state.py`
- Modify: `agent/domain/state.py`
- Test: `tests/test_agent_state_slices.py`

- [ ] **Step 1: 先写失败测试，锁定 agent 模式初始化不再注入 `SystemMessage`**

```python
# tests/test_agent_state_slices.py
from agent.application import build_execution_request, build_initial_agent_state


def test_build_initial_agent_state_keeps_agent_messages_clean_and_stores_memory_context():
    request = build_execution_request(
        input_text="帮我解释一下 FastAPI 的依赖注入",
        thread_id="thread-chat-1",
        user_id="user-1",
        mode_info={"mode": "agent"},
        agent_profile={
            "id": "default",
            "system_prompt": "You are a calm assistant.",
            "enabled_tools": {"web_search": True},
        },
    )

    state = build_initial_agent_state(
        request,
        stored_memories=["用户喜欢简洁回答"],
        relevant_memories=["上次问过 FastAPI 路由组织"],
    )

    assert state["messages"] == []
    assert state["memory_context"] == {
        "stored": ["用户喜欢简洁回答"],
        "relevant": ["上次问过 FastAPI 路由组织"],
    }
    assert state["research_state"]["memory_context"] == state["memory_context"]
    assert state["conversation_state"]["messages"] == []
```

- [ ] **Step 2: 运行测试，确认当前实现仍把 prompt/memory 塞进 `messages`**

Run: `pytest tests/test_agent_state_slices.py::test_build_initial_agent_state_keeps_agent_messages_clean_and_stores_memory_context -v`

Expected:
- FAIL，表现为 `state["messages"]` 非空，且缺少 `memory_context`

- [ ] **Step 3: 最小实现 chat-first 所需状态字段与初始化逻辑**

```python
# agent/domain/state.py
class ResearchState(TypedDict, total=False):
    scraped_content: list[dict[str, Any]]
    code_results: list[dict[str, Any]]
    summary_notes: list[str]
    sources: list[dict[str, str]]
    research_topology: dict[str, Any]
    current_branch_id: str | None
    domain: str
    domain_config: dict[str, Any]
    sub_agent_contexts: dict[str, dict[str, Any]]
    memory_context: dict[str, list[str]]
    assistant_draft: str
    needs_tools: bool
    tool_reason: str
    required_capabilities: list[str]
    tool_observations: list[dict[str, Any]]


def build_research_state(state: Mapping[str, Any] | None) -> ResearchState:
    data = state or {}
    return {
        "scraped_content": list(data.get("scraped_content") or []),
        "code_results": list(data.get("code_results") or []),
        "summary_notes": list(data.get("summary_notes") or []),
        "sources": list(data.get("sources") or []),
        "research_topology": dict(data.get("research_topology") or {}),
        "current_branch_id": data.get("current_branch_id"),
        "domain": str(data.get("domain") or "").strip(),
        "domain_config": dict(data.get("domain_config") or {}),
        "sub_agent_contexts": dict(data.get("sub_agent_contexts") or {}),
        "memory_context": dict(data.get("memory_context") or {"stored": [], "relevant": []}),
        "assistant_draft": str(data.get("assistant_draft") or ""),
        "needs_tools": bool(data.get("needs_tools")),
        "tool_reason": str(data.get("tool_reason") or ""),
        "required_capabilities": list(data.get("required_capabilities") or []),
        "tool_observations": list(data.get("tool_observations") or []),
    }
```

```python
# agent/core/state.py
class AgentState(TypedDict):
    input: str
    images: List[Dict[str, Any]]
    final_report: str
    draft_report: str
    assistant_draft: str
    needs_tools: bool
    tool_reason: str
    required_capabilities: List[str]
    tool_observations: Annotated[List[Dict[str, Any]], operator.add]
    memory_context: Dict[str, List[str]]
```

```python
# agent/application/state.py
initial_state: dict[str, Any] = {
    "input": request.input_text,
    "images": list(request.images),
    "final_report": "",
    "draft_report": "",
    "assistant_draft": "",
    "needs_tools": False,
    "tool_reason": "",
    "required_capabilities": [],
    "tool_observations": [],
    "memory_context": {
        "stored": [str(item).strip() for item in (stored_memories or []) if str(item).strip()],
        "relevant": [str(item).strip() for item in (relevant_memories or []) if str(item).strip()],
    },
    "messages": [],
}

if route == "deep":
    initial_state["messages"] = [SystemMessage(content=get_deep_agent_prompt())]
```

- [ ] **Step 4: 重新运行状态契约测试**

Run: `pytest tests/test_agent_state_slices.py -v`

Expected:
- `3 passed`

### Task 2: 引入运行时 prompt/context builder

**Files:**
- Create: `agent/runtime/nodes/prompting.py`
- Test: `tests/test_agent_prompt_runtime_context.py`

- [ ] **Step 1: 先写失败测试，锁定动态 prompt 与 memory context 的拼装行为**

```python
# tests/test_agent_prompt_runtime_context.py
from langchain_core.messages import AIMessage, HumanMessage

from agent.runtime.nodes.prompting import build_chat_runtime_messages


def test_build_chat_runtime_messages_uses_real_history_and_turn_context():
    state = {
        "input": "继续讲一下依赖覆盖怎么测",
        "images": [],
        "messages": [
            HumanMessage(content="先解释一下 FastAPI 依赖注入"),
            AIMessage(content="它允许你把共享依赖声明为参数。"),
        ],
        "memory_context": {
            "stored": ["用户喜欢简洁回答"],
            "relevant": ["之前在问 FastAPI 测试"],
        },
    }
    config = {
        "configurable": {
            "agent_profile": {
                "system_prompt": "You are a concise assistant.",
            }
        }
    }

    messages = build_chat_runtime_messages(state, config)

    assert messages[0].type == "system"
    assert "You are a concise assistant." in messages[0].content
    assert "用户喜欢简洁回答" in messages[0].content
    assert "之前在问 FastAPI 测试" in messages[0].content
    assert messages[1].content == "先解释一下 FastAPI 依赖注入"
    assert messages[2].content == "它允许你把共享依赖声明为参数。"
    assert messages[-1].content == "继续讲一下依赖覆盖怎么测"
```

- [ ] **Step 2: 运行测试，确认缺少 runtime prompt builder**

Run: `pytest tests/test_agent_prompt_runtime_context.py -v`

Expected:
- `ModuleNotFoundError: No module named 'agent.runtime.nodes.prompting'`

- [ ] **Step 3: 新建 prompt/context helper，统一 runtime 注入规则**

```python
# agent/runtime/nodes/prompting.py
from __future__ import annotations

from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from agent.infrastructure.browser_context import build_browser_context_hint


def _profile_prompt(config: dict[str, Any]) -> str:
    profile = (config.get("configurable") or {}).get("agent_profile") or {}
    return str(profile.get("system_prompt") or "").strip()


def _memory_block(state: dict[str, Any]) -> str:
    memory = dict(state.get("memory_context") or {})
    stored = [str(item).strip() for item in memory.get("stored") or [] if str(item).strip()]
    relevant = [str(item).strip() for item in memory.get("relevant") or [] if str(item).strip()]
    parts: list[str] = []
    if stored:
        parts.append("Stored memories:\n" + "\n".join(f"- {item}" for item in stored))
    if relevant:
        parts.append("Relevant past knowledge:\n" + "\n".join(f"- {item}" for item in relevant))
    return "\n\n".join(parts).strip()


def build_chat_runtime_messages(
    state: dict[str, Any],
    config: dict[str, Any],
    *,
    include_browser_hint: bool = False,
) -> list[Any]:
    system_parts = [part for part in [_profile_prompt(config), _memory_block(state)] if part]
    if include_browser_hint:
        thread_id = str(((config.get("configurable") or {}).get("thread_id") or "default"))
        browser_hint = build_browser_context_hint(thread_id)
        if browser_hint:
            system_parts.append(browser_hint)

    messages: list[Any] = []
    if system_parts:
        messages.append(SystemMessage(content="\n\n".join(system_parts)))
    messages.extend(list(state.get("messages") or []))
    messages.append(HumanMessage(content=state.get("input", "")))
    return messages
```

- [ ] **Step 4: 运行新的 runtime prompt 测试**

Run: `pytest tests/test_agent_prompt_runtime_context.py -v`

Expected:
- `1 passed`

### Task 3: 拆分 chat-first 节点并保留兼容 `agent_node`

**Files:**
- Create: `agent/runtime/nodes/chat.py`
- Create: `agent/runtime/nodes/finalize.py`
- Modify: `agent/runtime/nodes/answer.py`
- Modify: `agent/runtime/nodes/__init__.py`
- Modify: `agent/runtime/__init__.py`
- Create: `tests/test_chat_first_agent_nodes.py`
- Modify: `tests/test_agent_mode_selection.py`

- [ ] **Step 1: 先写失败测试，锁定无工具路径与工具升级路径**

```python
# tests/test_chat_first_agent_nodes.py
from langchain_core.messages import AIMessage

import agent.runtime.nodes.answer as answer_nodes
import agent.runtime.nodes.chat as chat_nodes
import agent.runtime.nodes.finalize as finalize_nodes


def test_chat_respond_node_returns_plain_answer_without_tools(monkeypatch):
    class _FakeLLM:
        def invoke(self, _messages, config=None):
            return {
                "assistant_draft": "当然可以，我先用一个简单例子说明。",
                "needs_tools": False,
                "tool_reason": "",
                "required_capabilities": [],
            }

    monkeypatch.setattr(chat_nodes, "_chat_model", lambda *_args, **_kwargs: _FakeLLM())
    monkeypatch.setattr(chat_nodes, "_model_for_task", lambda *_args, **_kwargs: "gpt-4o-mini")

    result = chat_nodes.chat_respond_node(
        {"input": "解释一下 FastAPI 依赖注入", "messages": [], "memory_context": {"stored": [], "relevant": []}},
        {"configurable": {}},
    )

    assert result["assistant_draft"].startswith("当然可以")
    assert result["needs_tools"] is False
    assert result["required_capabilities"] == []


def test_agent_node_wrapper_runs_tool_agent_and_finalize_when_tools_needed(monkeypatch):
    monkeypatch.setattr(
        answer_nodes,
        "chat_respond_node",
        lambda state, config: {
            "assistant_draft": "",
            "needs_tools": True,
            "tool_reason": "need live web data",
            "required_capabilities": ["web_search"],
        },
    )
    monkeypatch.setattr(
        answer_nodes,
        "tool_agent_node",
        lambda state, config: {
            "assistant_draft": "根据最新搜索结果，今天的价格是 99 美元。",
            "tool_observations": [{"tool": "fallback_search"}],
            "messages": [AIMessage(content="根据最新搜索结果，今天的价格是 99 美元。")],
        },
    )
    monkeypatch.setattr(
        finalize_nodes,
        "finalize_answer_node",
        lambda state, config: {
            "final_report": state["assistant_draft"],
            "draft_report": state["assistant_draft"],
            "messages": state["messages"],
            "is_complete": False,
        },
    )

    result = answer_nodes.agent_node(
        {"input": "今天的价格是多少？", "messages": [], "memory_context": {"stored": [], "relevant": []}},
        {"configurable": {}},
    )

    assert result["final_report"] == "根据最新搜索结果，今天的价格是 99 美元。"
```

- [ ] **Step 2: 运行测试，确认新节点与兼容包装器尚不存在**

Run: `pytest tests/test_chat_first_agent_nodes.py -v`

Expected:
- FAIL，缺少 `agent.runtime.nodes.chat`
- FAIL，并提示 `AttributeError: module 'agent.runtime.nodes.answer' has no attribute 'tool_agent_node'`

- [ ] **Step 3: 实现 chat-first 三节点与兼容包装器**

```python
# agent/runtime/nodes/chat.py
from __future__ import annotations

from typing import Any, Dict

from langchain_core.runnables import RunnableConfig

from agent.runtime.nodes._shared import _chat_model, _configurable, _model_for_task, project_state_updates
from agent.runtime.nodes.prompting import build_chat_runtime_messages


def chat_respond_node(state: Dict[str, Any], config: RunnableConfig) -> Dict[str, Any]:
    user_input = str(state.get("input", "") or "").strip()
    lower = user_input.lower()
    forced_capabilities: list[str] = []
    if any(token in lower for token in ("latest", "today", "current", "price", "news")):
        forced_capabilities.append("web_search")
    if any(token in lower for token in ("open ", "website", "browse", "click", "login")):
        forced_capabilities.append("browser")
    if any(token in lower for token in ("file", "read ", "write ", "save ", "download")):
        forced_capabilities.append("files")
    if any(token in lower for token in ("python", "script", "calculate", "chart", "plot")):
        forced_capabilities.append("python")

    if forced_capabilities:
        return project_state_updates(
            state,
            {
                "assistant_draft": "",
                "needs_tools": True,
                "tool_reason": "forced by deterministic capability rules",
                "required_capabilities": sorted(set(forced_capabilities)),
            },
        )

    llm = _chat_model(_model_for_task("writing", config), temperature=0.2)
    messages = build_chat_runtime_messages(state, config)
    response = llm.invoke(messages, config=config)
    content = response.content if hasattr(response, "content") else str(response)

    return project_state_updates(
        state,
        {
            "assistant_draft": content,
            "needs_tools": False,
            "tool_reason": "",
            "required_capabilities": [],
        },
    )
```

```python
# agent/runtime/nodes/finalize.py
from __future__ import annotations

from typing import Any, Dict

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig

from agent.runtime.nodes._shared import _apply_output_contract, project_state_updates


def finalize_answer_node(state: Dict[str, Any], config: RunnableConfig) -> Dict[str, Any]:
    report = _apply_output_contract(state.get("input", ""), state.get("assistant_draft", ""))
    return project_state_updates(
        state,
        {
            "final_report": report,
            "draft_report": report,
            "messages": [AIMessage(content=report)],
            "is_complete": False,
        },
    )
```

```python
# agent/runtime/nodes/answer.py
from agent.infrastructure.tools import build_tools_for_capabilities
from agent.runtime.nodes.chat import chat_respond_node
from agent.runtime.nodes.finalize import finalize_answer_node


def tool_agent_node(state: Dict[str, Any], config: RunnableConfig, *, _deps: Any = None) -> Dict[str, Any]:
    deps = _resolve_deps(_deps)
    tools = build_tools_for_capabilities(state.get("required_capabilities") or [], config)
    agent = deps.build_tool_agent(model=deps._model_for_task("research", config), tools=tools, temperature=0.7)
    messages = build_chat_runtime_messages(
        state,
        config,
        include_browser_hint="browser" in set(state.get("required_capabilities") or []),
    )
    response = agent.invoke({"messages": messages}, config=config)
    last = response["messages"][-1]
    text = getattr(last, "content", str(last))
    return deps.project_state_updates(
        state,
        {
            "assistant_draft": text,
            "tool_observations": [{"tool": getattr(tool, "name", "")} for tool in tools],
            "messages": [AIMessage(content=text)],
        },
    )


def agent_node(state: Dict[str, Any], config: RunnableConfig, *, _deps: Any = None) -> Dict[str, Any]:
    merged = dict(state)
    merged.update(chat_respond_node(merged, config))
    if merged.get("needs_tools"):
        merged.update(tool_agent_node(merged, config, _deps=_deps))
    return finalize_answer_node(merged, config)
```

- [ ] **Step 4: 运行 chat-first 节点测试与原 agent 模式测试**

Run: `pytest tests/test_chat_first_agent_nodes.py tests/test_agent_mode_selection.py -v`

Expected:
- 新增 chat-first 测试通过
- 旧的 fast-path 导向测试需要被替换或更新为新的 chat-first 行为断言

### Task 4: 引入 capability-based tool assembly

**Files:**
- Modify: `agent/infrastructure/tools/assembly.py`
- Modify: `agent/infrastructure/tools/__init__.py`
- Modify: `tests/test_agent_tools.py`

- [ ] **Step 1: 先写失败测试，锁定按能力最小授权的工具集合**

```python
# tests/test_agent_tools.py
from agent.infrastructure.tools import build_tools_for_capabilities


def test_build_tools_for_capabilities_limits_tools_to_search_family():
    cfg = {
        "configurable": {
            "thread_id": "cap-1",
            "agent_profile": {"enabled_tools": {"web_search": True, "browser": True}},
        }
    }

    names = _names(build_tools_for_capabilities(["web_search"], cfg))

    assert "fallback_search" in names
    assert "browser_navigate" not in names


def test_build_tools_for_capabilities_returns_empty_list_for_empty_request():
    cfg = {"configurable": {"thread_id": "cap-2", "agent_profile": {"enabled_tools": {}}}}

    assert build_tools_for_capabilities([], cfg) == []
```

- [ ] **Step 2: 运行工具测试，确认还没有 capability 装配入口**

Run: `pytest tests/test_agent_tools.py::test_build_tools_for_capabilities_limits_tools_to_search_family -v`

Expected:
- `ImportError: cannot import name 'build_tools_for_capabilities' from 'agent.infrastructure.tools'`

- [ ] **Step 3: 在装配层新增 capability-based toolset**

```python
# agent/infrastructure/tools/assembly.py
from agent.infrastructure.tools.capabilities import resolve_tool_names_for_capabilities


def build_tools_for_capabilities(
    required_capabilities: list[str],
    config: RunnableConfig,
) -> list[BaseTool]:
    requested = [str(item).strip() for item in (required_capabilities or []) if str(item).strip()]
    if not requested:
        return []

    wanted = resolve_tool_names_for_capabilities(requested)
    tools = build_tools_for_names(wanted, config)
    configurable = _configurable(config)
    profile = configurable.get("agent_profile") or {}
    return filter_tools_by_name(
        tools,
        whitelist=profile.get("tool_whitelist") or [],
        blacklist=profile.get("tool_blacklist") or [],
    )
```

```python
# agent/infrastructure/tools/__init__.py
from agent.infrastructure.tools.assembly import (
    build_agent_toolset,
    build_tool_inventory,
    build_tools_for_capabilities,
    build_tools_for_names,
)
```

- [ ] **Step 4: 重新运行工具装配测试**

Run: `pytest tests/test_agent_tools.py -v`

Expected:
- 现有 `build_agent_toolset()` 测试继续通过
- 新增 capability 装配测试通过

### Task 5: 修改根图、移除 Deep Research 回退委派与 SSE 节点投影

**Files:**
- Modify: `agent/runtime/graph.py`
- Modify: `agent/runtime/nodes/deep_research.py`
- Modify: `main.py`
- Modify: `tests/test_root_graph_contract.py`
- Modify: `tests/test_deepsearch_mode_selection.py`
- Modify: `tests/test_chat_sse_process_progress.py`
- Modify: `tests/test_agent_runtime_public_contracts.py`

- [ ] **Step 1: 先写失败测试，锁定新的根图节点名与导出契约**

```python
# tests/test_root_graph_contract.py
def test_create_research_graph_uses_chat_first_agent_path():
    graph = create_research_graph()
    node_names = set(graph.get_graph().nodes.keys())

    assert {"router", "chat_respond", "tool_agent", "finalize", "deep_research"} <= node_names
    assert "agent" not in node_names
```

```python
# tests/test_deepsearch_mode_selection.py
def test_deep_research_node_keeps_simple_factual_query_in_deep_runner(monkeypatch):
    called = {"auto": False}

    def fail_agent(state, config):
        raise AssertionError("deepsearch should not delegate simple factual queries to agent mode")

    def fake_auto(state, config):
        called["auto"] = True
        assert state.get("route") != "agent"
        return {"final_report": "Paris", "messages": []}

    monkeypatch.setattr(nodes, "agent_node", fail_agent, raising=False)
    monkeypatch.setattr(nodes, "run_deep_research", fake_auto, raising=False)

    result = nodes.deep_research_node(
        {"input": "Use deep research to answer: what is the capital of France?"},
        {"configurable": {}},
    )

    assert called["auto"] is True
    assert result["final_report"] == "Paris"
```

```python
# tests/test_agent_runtime_public_contracts.py
from agent.runtime.nodes import chat_respond_node, finalize_answer_node, route_node, tool_agent_node


def test_runtime_chat_first_entrypoints_are_importable():
    assert callable(route_node)
    assert callable(chat_respond_node)
    assert callable(tool_agent_node)
    assert callable(finalize_answer_node)
```

```python
# tests/test_chat_sse_process_progress.py
def test_chat_respond_node_has_no_first_person_thinking_intro():
    assert main._thinking_intro_for_node("chat_respond", use_zh=True) == ""
```

- [ ] **Step 2: 运行根图 / runtime / SSE 测试，确认当前图结构仍是旧节点且 deep 仍会错误回退**

Run: `pytest tests/test_root_graph_contract.py tests/test_deepsearch_mode_selection.py tests/test_agent_runtime_public_contracts.py tests/test_chat_sse_process_progress.py -v`

Expected:
- FAIL，根图中仍有 `agent`
- FAIL，`test_deep_research_node_keeps_simple_factual_query_in_deep_runner` 仍会触发 `agent_node`
- FAIL，缺少 `chat_respond_node` / `tool_agent_node` / `finalize_answer_node` 导出

- [ ] **Step 3: 修改根图边、移除 Deep Research 回退委派并更新流式状态映射**

```python
# agent/runtime/graph.py
from agent.runtime.nodes import (
    chat_respond_node,
    deep_research_node,
    finalize_answer_node,
    route_node,
    tool_agent_node,
)


workflow.add_node("router", route_node)
workflow.add_node("chat_respond", chat_respond_node)
workflow.add_node("tool_agent", tool_agent_node)
workflow.add_node("finalize", finalize_answer_node)
workflow.add_node("deep_research", deep_research_node)

workflow.set_entry_point("router")
workflow.add_conditional_edges("router", route_decision, ["chat_respond", "deep_research"])


def after_chat(state: AgentState) -> str:
    return "tool_agent" if state.get("needs_tools") else "finalize"


workflow.add_conditional_edges("chat_respond", after_chat, ["tool_agent", "finalize"])
workflow.add_edge("tool_agent", "finalize")
workflow.add_edge("finalize", END)
workflow.add_edge("deep_research", END)
```

```python
# agent/runtime/nodes/deep_research.py
token_id = state.get("cancel_token_id")
if token_id:
    _check_cancellation(token_id)

result = deps.run_deep_research(state, config)
```

```python
# main.py
def _should_emit_main_text_for_node(node_name: str) -> bool:
    name = (node_name or "").strip().lower()
    if not name:
        return False
    return name in {"chat_respond", "tool_agent"}


def _thinking_intro_for_node(node_name: str, *, use_zh: bool) -> str:
    name = (node_name or "").strip().lower()
    if not name:
        return ""
    if "clarify" in name:
        return "我会先确认研究问题是否还缺关键上下文。" if use_zh else "I'll check whether the research request is missing any critical context."
    if "supervisor" in name:
        return "我会先结合已批准 scope 决定要派发哪些研究分支。" if use_zh else "I'll use the approved scope to decide which research branches to dispatch."
    if "deepsearch" in name:
        return "我会进行迭代式深度检索（生成查询 → 搜索 → 阅读 → 汇总），直到覆盖充分。" if use_zh else "I'll run an iterative deep-search loop (query → search → read → summarize) until coverage is solid."
    if name in {"chat_respond", "tool_agent", "finalize"}:
        return ""
    return ""


# stream loop status mapping
elif node_name == "tool_agent":
    yield await format_stream_event(
        "status",
        {
            "text": "Using tools for live context",
            "step": "agent_tools",
        },
    )
```

- [ ] **Step 4: 运行根图、deep runner 与 SSE 回归测试**

Run: `pytest tests/test_root_graph_contract.py tests/test_deepsearch_mode_selection.py tests/test_chat_sse_process_progress.py tests/test_agent_runtime_public_contracts.py -v`

Expected:
- 根图节点结构通过
- Deep Research 简单问题保持在 deep runner 内通过
- `chat_respond` / `tool_agent` 的 SSE 映射通过

### Task 6: 端到端回归 chat-first 行为

**Files:**
- Modify: `tests/test_chat_session_persistence.py`
- Modify: `tests/test_output_contracts.py`
- Modify: `tests/test_agent_mode_selection.py`

- [ ] **Step 1: 先补回归测试，锁定普通聊天不升级工具、输出 contract 仍生效**

```python
# tests/test_agent_mode_selection.py
def test_agent_node_returns_plain_chat_answer_without_tool_agent(monkeypatch):
    monkeypatch.setattr(
        "agent.runtime.nodes.answer.chat_respond_node",
        lambda state, config: {
            "assistant_draft": "当然可以，先看一个最小示例。",
            "needs_tools": False,
            "tool_reason": "",
            "required_capabilities": [],
        },
    )
    monkeypatch.setattr(
        "agent.runtime.nodes.answer.finalize_answer_node",
        lambda state, config: {
            "final_report": state["assistant_draft"],
            "draft_report": state["assistant_draft"],
            "messages": [],
            "is_complete": False,
        },
    )

    result = nodes.agent_node(
        {"input": "解释一下依赖注入", "messages": [], "memory_context": {"stored": [], "relevant": []}},
        {"configurable": {}},
    )

    assert result["final_report"] == "当然可以，先看一个最小示例。"
```

```python
# tests/test_output_contracts.py
def test_finalize_answer_node_enforces_exact_reply_contract():
    result = nodes.finalize_answer_node(
        {
            "input": 'Reply with exactly "Paris".',
            "assistant_draft": "The answer is Paris.",
            "messages": [],
        },
        {"configurable": {}},
    )

    assert result["final_report"] == "Paris"
```

- [ ] **Step 2: 运行回归测试，确认最终输出断言已经完全收敛到 `finalize`**

Run: `pytest tests/test_agent_mode_selection.py tests/test_output_contracts.py tests/test_chat_session_persistence.py -v`

Expected:
- 旧测试失败点聚焦在 `finalize_answer_node` 尚未纳入断言或 session 持久化未记录干净 `messages`

- [ ] **Step 3: 修正 session / output contract 的最终收口逻辑**

```python
# agent/runtime/nodes/finalize.py
def finalize_answer_node(state: Dict[str, Any], config: RunnableConfig) -> Dict[str, Any]:
    report = _apply_output_contract(state.get("input", ""), state.get("assistant_draft", ""))
    updated_messages = [AIMessage(content=report)]
    return project_state_updates(
        state,
        {
            "assistant_draft": report,
            "final_report": report,
            "draft_report": report,
            "messages": updated_messages,
            "is_complete": False,
        },
    )
```

```python
# tests/test_chat_session_persistence.py
assert isinstance(state_payload["messages"], list)
assert all(message.get("type") != "system" for message in state_payload["messages"] if isinstance(message, dict))
```

- [ ] **Step 4: 跑完整 chat-first 相关测试集合**

Run: `pytest tests/test_agent_state_slices.py tests/test_agent_prompt_runtime_context.py tests/test_chat_first_agent_nodes.py tests/test_agent_tools.py tests/test_root_graph_contract.py tests/test_deepsearch_mode_selection.py tests/test_chat_sse_process_progress.py tests/test_output_contracts.py tests/test_agent_mode_selection.py -v`

Expected:
- 全部 PASS

**Self-Review**

- Spec coverage:
  - chat-first 根图拆分：Task 3、Task 5
  - `messages` 仅保留真实会话：Task 1、Task 2、Task 6
  - profile/memory/browser hint 改为运行时注入：Task 1、Task 2
  - capability-based 最小工具授权：Task 4
  - `agent_node` 兼容保留：Task 3
  - Deep 模式不再回退到 `agent_node`：Task 5
  - SSE / process progress 适配：Task 5
- Placeholder scan:
  - 未发现占位词或延后实现语句
  - 每个代码步骤都包含明确代码片段
  - 每个测试步骤都包含具体命令与预期
- Type consistency:
  - 中间字段统一使用 `assistant_draft` / `needs_tools` / `tool_reason` / `required_capabilities` / `tool_observations`
  - 新导出名称统一使用 `chat_respond_node` / `tool_agent_node` / `finalize_answer_node`
