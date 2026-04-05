# Remove Outer Clarify/Legacy Research Flow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 删除根图外层 `clarify` 与整条旧 `planner/research/evaluator/reviser` 链路，收缩顶层公共状态与兼容层，只保留 `router -> agent|deep_research -> human_review` 和 Deep Research 内层正式编排。

**Architecture:** 先用根图契约测试锁定新的可达节点和路由结果，再分三层裁剪：根图/节点导出、公共状态/执行契约、`main.py` 流式与恢复输出。Deep Research 内层 `clarify/scope/review/report` 保持不变，旧 checkpoint 与旧 session 数据兼容全部放弃。

**Tech Stack:** Python 3.11、FastAPI、LangGraph、Pydantic、pytest、uv、ripgrep

---

## File Structure

**Create**

- `tests/test_root_graph_contract.py`

**Modify**

- `agent/runtime/graph.py`
- `agent/runtime/nodes/routing.py`
- `agent/runtime/nodes/answer.py`
- `agent/runtime/nodes/review.py`
- `agent/runtime/nodes/__init__.py`
- `agent/runtime/__init__.py`
- `agent/core/smart_router.py`
- `agent/core/state.py`
- `agent/domain/execution.py`
- `agent/domain/state.py`
- `agent/application/state.py`
- `main.py`
- `tests/test_agent_runtime_public_contracts.py`
- `tests/test_agent_state_slices.py`
- `tests/test_resume_session_deepsearch.py`
- `tests/test_thread_authz_interrupt_and_resume.py`

**Delete**

- `agent/runtime/nodes/planning.py`
- `tests/test_hitl_checkpoint_review_nodes.py`
- `tests/test_evaluator_emits_quality_update.py`
- `tests/test_evaluator_persists_quality_summary.py`
- `tests/test_export_json_quality_from_evaluator.py`
- `tests/test_report_citation_gate.py`
- `tests/test_claim_verifier_gate.py`
- `tests/quick_test.py`

**Responsibility Map**

- `agent/runtime/graph.py`：收缩根图，只保留真实生产路径。
- `agent/runtime/nodes/routing.py`：移除外层 `clarify`，让低置信度直接回退到 `agent`。
- `agent/runtime/nodes/answer.py` / `review.py`：去掉旧写作和评估节点，只保留 `agent_node` 与 `human_review_node`。
- `agent/core/smart_router.py` / `agent/domain/execution.py`：收缩公共路由与执行模式，不再存在外层 `clarify`。
- `agent/core/state.py` / `agent/domain/state.py` / `agent/application/state.py`：删掉旧 research/planner 流字段。
- `main.py`：删掉旧节点的 thinking/status 映射、恢复摘要和旧 revision loop 配置。
- `tests/*`：删除旧链路专属测试，补上新的根图契约测试。

**Repository Constraint**

- 根据仓库 `AGENTS.md`，本计划不包含任何 `git commit` 步骤。

### Task 1: 锁定新的根图与路由契约

**Files:**

- Create: `tests/test_root_graph_contract.py`
- Modify: `agent/runtime/graph.py`
- Modify: `agent/runtime/nodes/routing.py`

- [x] **Step 1: 先写失败测试，锁定根图只保留 4 个生产节点，且低置信度不再走外层 clarify**

```python
import agent.runtime.nodes.routing as routing
from agent.runtime.graph import create_research_graph


def test_create_research_graph_only_keeps_active_root_nodes():
    graph = create_research_graph()
    node_names = set(graph.get_graph().nodes.keys())

    assert {"router", "agent", "deep_research", "human_review"} <= node_names

    removed = {
        "clarify",
        "planner",
        "refine_plan",
        "hitl_plan_review",
        "perform_parallel_search",
        "writer",
        "hitl_draft_review",
        "evaluator",
        "reviser",
        "compressor",
        "hitl_sources_review",
    }
    assert removed.isdisjoint(node_names)


def test_route_node_low_confidence_falls_back_to_agent(monkeypatch):
    monkeypatch.setattr(
        "agent.core.smart_router.smart_route",
        lambda **_kwargs: {
            "route": "deep",
            "routing_reasoning": "uncertain",
            "routing_confidence": 0.18,
        },
    )

    result = routing.route_node(
        {"input": "help me with this", "images": []},
        {"configurable": {"routing_confidence_threshold": 0.6}},
    )

    assert result["route"] == "agent"
    assert result["routing_confidence"] == 0.18
    assert "needs_clarification" not in result
    assert "clarification_question" not in result
```

- [x] **Step 2: 运行测试，确认当前实现仍暴露旧节点和 clarify 回退**

Run: `uv run pytest tests/test_root_graph_contract.py -v`

Expected: FAIL  
Expected failure shape:
- `create_research_graph()` 仍包含 `clarify`、`planner`、`writer` 等旧节点
- `route_node()` 低置信度时仍把 `route` 改成 `clarify`

- [x] **Step 3: 收缩根图与外层路由实现**

```python
# agent/runtime/graph.py
import logging

import psycopg
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import END, StateGraph
from psycopg.rows import dict_row

from agent.core.state import AgentState
from agent.runtime.nodes import (
    agent_node,
    deep_research_node,
    human_review_node,
    route_node,
)

logger = logging.getLogger(__name__)


def create_research_graph(checkpointer=None, interrupt_before=None, store=None):
    from common.config import settings

    workflow = StateGraph(AgentState)
    workflow.add_node("router", route_node)
    workflow.add_node("agent", agent_node)
    workflow.add_node("deep_research", deep_research_node)
    workflow.add_node("human_review", human_review_node)
    workflow.set_entry_point("router")

    def route_decision(state: AgentState) -> str:
        route = state.get("route", "agent")
        if route == "deep":
            return "deep_research"
        return "agent"

    workflow.add_conditional_edges("router", route_decision, ["agent", "deep_research"])
    workflow.add_edge("agent", "human_review")
    workflow.add_edge("deep_research", "human_review")
    workflow.add_edge("human_review", END)

    hitl_checkpoints = getattr(settings, "hitl_checkpoints", "") or ""
    if hitl_checkpoints.strip():
        logger.info(f"HITL checkpoints enabled: {hitl_checkpoints}")

    return workflow.compile(
        checkpointer=checkpointer,
        store=store,
        interrupt_before=interrupt_before,
    )
```

```python
# agent/runtime/nodes/routing.py
def route_node(
    state: Dict[str, Any],
    config: RunnableConfig,
    *,
    _deps: Any = None,
) -> Dict[str, Any]:
    from agent.core.smart_router import smart_route

    deps = _resolve_deps(_deps)
    configurable = deps._configurable(config)
    mode_info = configurable.get("search_mode", {}) or {}
    override_mode = mode_info.get("mode")
    confidence_threshold = float(configurable.get("routing_confidence_threshold", 0.6))

    result = smart_route(
        query=state.get("input", ""),
        images=state.get("images"),
        config=config,
        override_mode=override_mode if override_mode else None,
    )

    route = result.get("route", "agent")
    confidence = result.get("routing_confidence", 1.0)
    if not override_mode and confidence < confidence_threshold:
        logger.info(
            f"Low confidence ({confidence:.2f} < {confidence_threshold}), routing to agent"
        )
        route = "agent"
        result["route"] = "agent"

    if route not in {"agent", "deep"}:
        route = "agent"
        result["route"] = "agent"

    if getattr(settings, "domain_routing_enabled", False) and route == "deep":
        try:
            from agent.research.domain_router import DomainClassifier

            domain_llm = deps._chat_model(deps._model_for_task("routing", config), temperature=0.3)
            classifier = DomainClassifier(domain_llm, config)

            classification = classifier.classify(state.get("input", ""))
            result["domain"] = classification.domain.value
            result["domain_config"] = classification.to_dict()

            logger.info(
                f"[route_node] Domain classified: {classification.domain.value} "
                f"(confidence: {classification.confidence:.2f})"
            )
        except Exception as e:
            logger.warning(f"[route_node] Domain classification failed: {e}")
            result["domain"] = "general"
            result["domain_config"] = {}

    return deps.project_state_updates(state, result)
```

- [x] **Step 4: 重新运行根图契约测试**

Run: `uv run pytest tests/test_root_graph_contract.py -v`

Expected: PASS  
Expected passing shape:
- 根图只暴露 `router/agent/deep_research/human_review`
- 低置信度时 `route_node()` 返回 `agent`

### Task 2: 删除旧节点模块并收缩 runtime 导出

**Files:**

- Delete: `agent/runtime/nodes/planning.py`
- Modify: `agent/runtime/nodes/answer.py`
- Modify: `agent/runtime/nodes/review.py`
- Modify: `agent/runtime/nodes/__init__.py`
- Modify: `agent/runtime/__init__.py`
- Modify: `tests/test_agent_runtime_public_contracts.py`

- [x] **Step 1: 先写失败测试，锁定 runtime 包不再导出旧外层节点**

```python
import pytest

import agent.runtime as runtime_pkg
import agent.runtime.nodes as runtime_nodes


def test_removed_outer_runtime_nodes_are_not_exported():
    removed = {
        "clarify_node",
        "compressor_node",
        "evaluator_node",
        "hitl_draft_review_node",
        "hitl_plan_review_node",
        "hitl_sources_review_node",
        "initiate_research",
        "perform_parallel_search",
        "planner_node",
        "refine_plan_node",
        "revise_report_node",
        "writer_node",
    }

    for name in removed:
        assert name not in runtime_nodes.__all__
        assert name not in runtime_pkg.__all__
        with pytest.raises(AttributeError):
            getattr(runtime_pkg, name)


def test_runtime_node_entrypoints_are_importable():
    assert callable(runtime_nodes.route_node)
    assert callable(runtime_nodes.agent_node)
    assert callable(runtime_nodes.deep_research_node)
    assert callable(runtime_nodes.human_review_node)
```

- [x] **Step 2: 运行测试，确认当前 runtime 仍暴露旧导出**

Run: `uv run pytest tests/test_agent_runtime_public_contracts.py -v`

Expected: FAIL  
Expected failure shape:
- `runtime_nodes.__all__` 和 `runtime_pkg.__all__` 仍包含 `clarify_node`、`writer_node`、`planner_node` 等符号

- [x] **Step 3: 删除旧节点模块并收缩导出表**

```diff
*** Delete File: agent/runtime/nodes/planning.py
```

```python
# agent/runtime/nodes/__init__.py
from agent.runtime.nodes.answer import agent_node
from agent.runtime.nodes.common import (
    check_cancellation,
    handle_cancellation,
    initialize_enhanced_tools,
)
from agent.runtime.nodes.deep_research import deep_research_node
from agent.runtime.nodes.review import human_review_node
from agent.runtime.nodes.routing import route_node

__all__ = [
    "agent_node",
    "check_cancellation",
    "deep_research_node",
    "handle_cancellation",
    "human_review_node",
    "initialize_enhanced_tools",
    "route_node",
]
```

```python
# agent/runtime/__init__.py
__all__ = [
    "agent_node",
    "check_cancellation",
    "create_research_graph",
    "deep_research_node",
    "handle_cancellation",
    "human_review_node",
    "initialize_enhanced_tools",
    "route_node",
    "run_deep_research",
]

_SYMBOL_TO_MODULE: Dict[str, str] = {
    "agent_node": "agent.runtime.nodes",
    "check_cancellation": "agent.runtime.nodes",
    "create_research_graph": "agent.runtime.graph",
    "deep_research_node": "agent.runtime.nodes",
    "handle_cancellation": "agent.runtime.nodes",
    "human_review_node": "agent.runtime.nodes",
    "initialize_enhanced_tools": "agent.runtime.nodes",
    "route_node": "agent.runtime.nodes",
    "run_deep_research": "agent.runtime.deep",
}
```

```python
# agent/runtime/nodes/answer.py
from datetime import datetime

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

import agent.infrastructure.agents.factory as _agent_factory
import agent.runtime.nodes._shared as _shared
from agent.infrastructure.agents.stuck_middleware import detect_stuck, inject_stuck_hint
from agent.infrastructure.browser_context import build_browser_context_hint
from agent.infrastructure.tools import build_agent_toolset
from agent.prompts import get_prompt_manager

ENHANCED_TOOLS_AVAILABLE = _shared.ENHANCED_TOOLS_AVAILABLE
_answer_simple_agent_query = _shared._answer_simple_agent_query
_build_user_content = _shared._build_user_content
_configurable = _shared._configurable
_model_for_task = _shared._model_for_task
_should_use_fast_agent_path = _shared._should_use_fast_agent_path
project_state_updates = _shared.project_state_updates
check_cancellation = _shared.check_cancellation
handle_cancellation = _shared.handle_cancellation
logger = _shared.logger
settings = _shared.settings
build_tool_agent = _agent_factory.build_tool_agent

# 文件最终只保留 agent_node；writer_node 及其写作路径全部删除。

__all__ = ["agent_node"]
```

```python
# agent/runtime/nodes/review.py
# 文件最终只保留 human_review_node 及其必需辅助函数：
# - _resolve_deps
# - _hitl_checkpoints_enabled
# - human_review_node
#
# 删除以下旧符号及其辅助函数：
# - hitl_plan_review_node
# - hitl_draft_review_node
# - hitl_sources_review_node
# - evaluator_node
# - revise_report_node
# - should_continue_research
# - _parse_research_plan_content
# - _format_sources_snapshot_for_instruction
#
# 删除后，文件内不得再引用：
# - plan/draft/sources checkpoint interrupt 路径
# - evaluator/reviser 的 ChatPromptTemplate 路径
# - compressed_knowledge review 路径

__all__ = [
    "human_review_node",
]
```

- [x] **Step 4: 重新运行 runtime 公共契约测试**

Run: `uv run pytest tests/test_agent_runtime_public_contracts.py -v`

Expected: PASS  
Expected passing shape:
- `agent.runtime` 与 `agent.runtime.nodes` 不再导出旧外层节点
- `route_node`、`agent_node`、`deep_research_node`、`human_review_node` 仍可导入

### Task 3: 收缩公共路由/状态契约与恢复摘要

**Files:**

- Modify: `agent/core/smart_router.py`
- Modify: `agent/domain/execution.py`
- Modify: `agent/core/state.py`
- Modify: `agent/domain/state.py`
- Modify: `agent/application/state.py`
- Modify: `main.py`
- Modify: `tests/test_agent_state_slices.py`
- Modify: `tests/test_resume_session_deepsearch.py`
- Modify: `tests/test_thread_authz_interrupt_and_resume.py`

- [x] **Step 1: 先写失败测试，锁定顶层状态中不再出现旧字段**

```python
from agent.application import build_execution_request, build_initial_agent_state
from agent.core.state import project_state_updates


def test_build_initial_agent_state_projects_structured_slices():
    request = build_execution_request(
        input_text="AI chips roadmap",
        thread_id="thread-1",
        user_id="user-1",
        mode_info={"mode": "deep"},
        agent_profile={
            "id": "researcher",
            "system_prompt": "You are a custom analyst.",
            "enabled_tools": {"web_search": True},
        },
        options={"tool_call_limit": 9},
    )

    state = build_initial_agent_state(request)

    assert state["route"] == "deep"
    assert state["execution_state"]["mode"] == "deep_research"
    assert state["execution_state"]["tool_call_limit"] == 9
    assert "research_plan" not in state
    assert "current_step" not in state
    assert "suggested_queries" not in state
    assert "needs_clarification" not in state
    assert "clarification_question" not in state
    assert "max_revisions" not in state
    assert "research_plan" not in state["research_state"]
    assert "clarification_question" not in state["conversation_state"]


def test_project_state_updates_keeps_structured_state_in_sync():
    request = build_execution_request(
        input_text="Latest AI chip prices",
        thread_id="thread-2",
        user_id="user-2",
        mode_info={"mode": "agent"},
        agent_profile={"id": "default", "enabled_tools": {"web_search": True}},
    )
    state = build_initial_agent_state(request)

    projected = project_state_updates(
        state,
        {
            "route": "agent",
            "routing_confidence": 0.42,
        },
    )

    assert projected["execution_state"]["route"] == "agent"
    assert projected["execution_state"]["mode"] == "tool_assisted"
    assert projected["execution_state"]["routing_confidence"] == 0.42
    assert "clarification_question" not in projected["conversation_state"]
    assert "research_plan" not in projected["research_state"]
```

```python
# tests/test_resume_session_deepsearch.py
assert "research_plan_count" not in data["resume_state"]
```

```python
# tests/test_thread_authz_interrupt_and_resume.py
fake_checkpointer = _FakeCheckpointer(
    by_thread_id={
        "thread_alice": {"user_id": "alice"},
    }
)
```

- [x] **Step 2: 运行测试，确认当前状态切片和 resume 输出仍携带旧字段**

Run: `uv run pytest tests/test_agent_state_slices.py tests/test_resume_session_deepsearch.py tests/test_thread_authz_interrupt_and_resume.py -v`

Expected: FAIL  
Expected failure shape:
- 初始 state 仍包含 `research_plan`、`clarification_question`、`max_revisions`
- resume 输出仍包含 `research_plan_count`

- [x] **Step 3: 收缩 smart router 和执行模式契约**

```python
# agent/core/smart_router.py
RouteType = Literal["agent", "deep"]


class RouteDecision(BaseModel):
    route: RouteType = Field(
        description="The execution route: 'agent' for the default tool-using path, 'deep' for comprehensive research"
    )
    reasoning: str = Field(description="Brief explanation of why this route was chosen")
    confidence: float = Field(
        default=0.8, ge=0.0, le=1.0, description="Confidence level of this routing decision (0-1)"
    )
    suggested_queries: List[str] = Field(
        default_factory=list, description="For 'deep' routes, suggested search queries"
    )
```

```python
# agent/domain/execution.py
class ExecutionMode(str, Enum):
    DIRECT_ANSWER = "direct_answer"
    TOOL_ASSISTED = "tool_assisted"
    DEEP_RESEARCH = "deep_research"


_PUBLIC_MODE_TO_EXECUTION: dict[str, ExecutionMode] = {
    "agent": ExecutionMode.TOOL_ASSISTED,
    "tool_assisted": ExecutionMode.TOOL_ASSISTED,
    "direct_answer": ExecutionMode.DIRECT_ANSWER,
    "deep": ExecutionMode.DEEP_RESEARCH,
    "deep_research": ExecutionMode.DEEP_RESEARCH,
}

_EXECUTION_TO_ROUTE: dict[ExecutionMode, str] = {
    ExecutionMode.DIRECT_ANSWER: "agent",
    ExecutionMode.TOOL_ASSISTED: "agent",
    ExecutionMode.DEEP_RESEARCH: "deep",
}
```

- [x] **Step 4: 收缩顶层状态与初始 state**

```python
# agent/application/state.py
initial_state: dict[str, Any] = {
    "input": request.input_text,
    "images": list(request.images),
    "final_report": "",
    "draft_report": "",
    "user_id": request.user_id,
    "thread_id": request.thread_id,
    "agent_id": request.agent_profile.id,
    "messages": [],
    "status": "pending",
    "is_complete": False,
    "route": route,
    "routing_reasoning": "",
    "routing_confidence": 0.0,
    "scraped_content": [],
    "code_results": [],
    "summary_notes": [],
    "sources": [],
    "tool_approved": False,
    "pending_tool_calls": [],
    "tool_call_count": 0,
    "tool_call_limit": int(request.options.get("tool_call_limit") or settings.tool_call_limit),
    "enabled_tools": dict(request.agent_profile.enabled_tools),
    "cancel_token_id": request.thread_id,
    "is_cancelled": False,
    "errors": [],
    "last_error": "",
    "research_topology": {},
    "domain": "",
    "domain_config": {},
    "sub_agent_contexts": {},
    "deep_runtime": build_deep_runtime_snapshot(
        engine=deep_runtime_engine,
    ),
    "total_input_tokens": 0,
    "total_output_tokens": 0,
}
```

```python
# agent/domain/state.py
class ConversationState(TypedDict, total=False):
    input: str
    images: list[dict[str, Any]]
    user_id: str
    thread_id: str
    agent_id: str
    messages: list[Any]
    final_report: str
    draft_report: str


class ExecutionState(TypedDict, total=False):
    mode: str
    route: str
    status: str
    is_complete: bool
    started_at: str
    ended_at: str
    routing_reasoning: str
    routing_confidence: float
    tool_approved: bool
    pending_tool_calls: list[dict[str, Any]]
    tool_call_count: int
    tool_call_limit: int
    enabled_tools: dict[str, bool]
    cancel_token_id: str | None
    is_cancelled: bool
    errors: list[str]
    last_error: str


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
```

```python
# agent/core/state.py
# 删除以下顶层字段声明与只服务旧链路的 TypedDict:
# - research_plan
# - current_step
# - suggested_queries
# - needs_clarification
# - clarification_question
# - evaluation
# - verdict
# - eval_dimensions
# - missing_topics
# - revision_count
# - max_revisions
# - compressed_knowledge
# - ResearchPlan
# - SearchResult
# - QueryState
```

- [x] **Step 5: 删除 `main.py` 中旧 revision loop 配置和旧 resume 摘要字段**

```python
# main.py
configurable: Dict[str, Any] = {
    "thread_id": thread_id,
    "model": model,
    "search_mode": mode_info,
    "agent_profile": agent_profile.model_dump(mode="json") if agent_profile else None,
    "user_id": user_id or settings.memory_user_id,
    "allow_interrupts": bool(checkpointer),
    "tool_approval": settings.tool_approval or False,
    "human_review": settings.human_review or False,
}
```

```python
# main.py
request = build_execution_request(
    input_text=input_text,
    thread_id=thread_id,
    user_id=user_id,
    mode_info=mode_info,
    images=images,
    agent_profile=agent_profile,
    options={
        "tool_call_limit": settings.tool_call_limit,
    },
)
```

```python
# main.py
"resume_state": {
    "resumed_from_checkpoint": bool(restored_state.get("resumed_from_checkpoint")),
},
```

- [x] **Step 6: 重新运行状态与恢复测试**

Run: `uv run pytest tests/test_agent_state_slices.py tests/test_resume_session_deepsearch.py tests/test_thread_authz_interrupt_and_resume.py -v`

Expected: PASS  
Expected passing shape:
- 顶层初始 state 和切片不再包含旧字段
- resume 输出不再包含 `research_plan_count`

### Task 4: 清理 `main.py` 的旧节点流式映射并删除过时测试

**Files:**

- Modify: `main.py`
- Delete: `tests/test_hitl_checkpoint_review_nodes.py`
- Delete: `tests/test_evaluator_emits_quality_update.py`
- Delete: `tests/test_evaluator_persists_quality_summary.py`
- Delete: `tests/test_export_json_quality_from_evaluator.py`
- Delete: `tests/test_report_citation_gate.py`
- Delete: `tests/test_claim_verifier_gate.py`
- Delete: `tests/quick_test.py`
- Test: `tests/test_root_graph_contract.py`
- Test: `tests/test_agent_runtime_public_contracts.py`
- Test: `tests/test_deepsearch_mode_selection.py`
- Test: `tests/test_deepsearch_multi_agent_runtime.py`
- Test: `tests/test_resume_session_deepsearch.py`

- [x] **Step 1: 删除 `main.py` 中只服务旧 outer planner/search/writer/evaluator 路径的分支，同时保留 deep runtime 合法 clarify/supervisor 提示**

```python
# main.py
def _should_emit_main_text_for_node(node_name: str) -> bool:
    name = (node_name or "").strip().lower()
    if not name:
        return False

    allow_tokens = (
        "agent",
    )
    return any(token in name for token in allow_tokens)


def _should_emit_thinking_summary_for_node(node_name: str) -> bool:
    name = (node_name or "").strip().lower()
    if not name:
        return False

    allow = (
        "clarify",
        "supervisor",
    )
    return any(token in name for token in allow)


def _thinking_intro_for_node(node_name: str, *, use_zh: bool) -> str:
    name = (node_name or "").strip().lower()
    if not name:
        return ""
    if "clarify" in name:
        return "我会先确认研究问题是否还缺关键上下文。" if use_zh else "I'll check whether the research request is missing any critical context."
    if "supervisor" in name:
        return (
            "我会先结合已批准 scope 决定要派发哪些研究分支。"
            if use_zh
            else "I'll use the approved scope to decide which research branches to dispatch."
        )
    if "deepsearch" in name:
        return (
            "我会进行迭代式深度检索（生成查询 → 搜索 → 阅读 → 汇总），直到覆盖充分。"
            if use_zh
            else "I'll run an iterative deep-search loop (query → search → read → summarize) until coverage is solid."
        )
    if name == "agent":
        return "我会调用工具完成任务步骤，并记录关键过程。" if use_zh else "I'll call tools to execute steps and log key actions."
    return ""
```

```python
# main.py
if "clarify" in node_name:
    logger.debug(f"  Clarify node started | Thread: {thread_id}")
    yield await format_stream_event(
        "status",
        {"text": "Checking whether more research context is needed", "step": "clarifying"},
    )
elif "supervisor" in node_name:
    logger.debug(f"  Supervisor node started | Thread: {thread_id}")
    yield await format_stream_event(
        "status",
        {"text": "Evaluating scope and dispatching research branches", "step": "supervisor"},
    )
elif "deepsearch" in node_name:
    logger.debug(f"  Deep research node started | Thread: {thread_id}")
    text = (
        "正在进行 Deep Research（多轮检索→阅读→汇总），可能需要几分钟…"
        if use_zh
        else "Running Deep Research (iterative search → read → synthesize)…"
    )
    yield await format_stream_event(
        "status",
        {"text": text, "step": "deep_research"},
    )
elif node_name == "agent":
    logger.debug(f"  Agent node started | Thread: {thread_id}")
    yield await format_stream_event(
        "status", {"text": "Running agent (tool-calling)", "step": "agent"}
    )
```

- [x] **Step 2: 删除已废弃测试文件**

```diff
*** Delete File: tests/test_hitl_checkpoint_review_nodes.py
*** Delete File: tests/test_evaluator_emits_quality_update.py
*** Delete File: tests/test_evaluator_persists_quality_summary.py
*** Delete File: tests/test_export_json_quality_from_evaluator.py
*** Delete File: tests/test_report_citation_gate.py
*** Delete File: tests/test_claim_verifier_gate.py
*** Delete File: tests/quick_test.py
```

- [x] **Step 3: 用全文搜索确认仓库不再残留外层旧节点符号**

Run: `rg -n "clarify_node|planner_node|refine_plan_node|perform_parallel_search|compressor_node|evaluator_node|revise_report_node|writer_node|hitl_plan_review_node|hitl_draft_review_node|hitl_sources_review_node|research_plan_count" agent main.py tests`

Expected: 只剩 Deep Research 内层合法符号或 0 条结果  
Expected clean shape:
- 不再命中外层旧节点实现、导出、测试、resume 摘要
- 若命中 `deep_research_clarify`，应来自 deep runtime 合法路径

- [x] **Step 4: 运行最终受影响测试子集**

Run: `uv run pytest tests/test_root_graph_contract.py tests/test_agent_runtime_public_contracts.py tests/test_agent_state_slices.py tests/test_deepsearch_mode_selection.py tests/test_deepsearch_multi_agent_runtime.py tests/test_resume_session_deepsearch.py tests/test_thread_authz_interrupt_and_resume.py -v`

Expected: PASS  
Expected passing shape:
- 根图契约通过
- runtime 公共契约通过
- deep runtime 关键行为未回归
- resume / auth 关键路径通过

- [x] **Step 5: 运行一次补充静态检查，确保删除没有留下导入错误**

Run: `uv run pytest tests/test_python_compiles.py -v`

Expected: PASS

## Self-Review Checklist

- Spec coverage:
  - 根图收缩：Task 1
  - 删除旧节点实现与导出：Task 2
  - 删除顶层公共字段与执行模式：Task 3
  - 删除 `main.py` 兼容层与旧测试：Task 4
- Placeholder scan:
  - 本计划不包含占位词、空步骤或未定义的后续动作
  - 本计划未包含 git commit 步骤，遵循仓库 `AGENTS.md`
- Type consistency:
  - 最终公共 route 只有 `agent|deep`
  - Deep Research 内层 `deep_research_clarify` 保留，不与外层 `clarify_node` 混淆
