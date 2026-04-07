# brainstorm: upgrade deep research researcher

## Goal

升级 Deep Research 流程中的 `researcher`，把当前以固定流水线为主的 research branch 执行器提升为更接近真正 agent 的能力单元，使其能够在受控边界内使用更多研究工具，并在不牺牲可控性和证据质量的前提下提升研究深度、覆盖面和复杂网页场景处理能力。

## What I already know

* 用户希望增强 deep research 流程里的 `researcher`，提升研究能力，提供更多工具，并形成“真正 agent”。
* 当前 runtime 入口在 `agent/runtime/deep/orchestration/graph.py`，其中 `self.researcher` 直接实例化 `ResearchAgent`。
* 当前 `ResearchAgent` 在 `agent/runtime/deep/roles/researcher.py` 中是固定流程：`search -> rank -> fetch -> passage -> synthesize`。
* 当前 researcher 的搜索入口是 graph 内部的 `_search_with_tracking()`，底层走 `support._search_query()`；正文抓取走 `tools/research/content_fetcher.py`。
* 仓库存在 `build_deep_research_tool_agent()` 和按角色划分的工具白名单，定义在 `agent/infrastructure/agents/factory.py`。
* `researcher` 的工具白名单已经包含搜索、抓取、sandbox browser、页面提取等较丰富能力，但 current runtime 未接入这套 tool-agent。
* `ResearchTask.allowed_tools` 会在 planner / graph 中写入任务，但当前 researcher 执行阶段并未真正消费该字段。
* 配置项 `deep_research_use_tool_agents` 已存在于 `common/config.py`，但当前 runtime 中没有实际接线。
* 现有测试默认通过 monkeypatch 把 `deep_research_use_tool_agents` 关闭，说明“tool-agent 化”目前仍被视为未启用/未完成能力。
* `fabric` 不是本地静态工具；它来自 `tools/mcp.py` 暴露的 live MCP tools，是否可用取决于运行时是否接入了对应 MCP server。

## Assumptions (temporary)

* 这次改造优先聚焦 `researcher`，不把整个 Deep Research runtime 的所有角色都 agent 化。
* 需要保持现有 evidence-first 契约，不能因为更灵活的工具调用而弱化 passage / claim grounding。
* 大概率需要保留脚本化 researcher 作为 fallback，以降低回归风险。
* 工具扩展应受角色白名单和任务级约束限制，不能放开成任意工具调用。

## Open Questions

* 本次 MVP 的改造边界要落在哪一层：仅 researcher tool-agent 化，还是连任务级工具策略、fallback、review 链路一起补齐？

## Requirements (evolving)

* 明确 current `researcher` 与 `tool-agent` 预留设施之间的接缝。
* 设计一个可控的 researcher agent 化方案，避免无限调用和证据失真。
* 让 researcher 能使用比当前固定流水线更丰富的研究工具。
* 保持或增强现有 evidence bundle / section draft / claim grounding 产物契约。

## Acceptance Criteria (evolving)

* [ ] 形成明确的 researcher 升级方案和实现范围。
* [ ] 新方案能够解释现有 `allowed_tools`、角色白名单、`deep_research_use_tool_agents` 如何落地。
* [ ] 保留明确的证据产出边界，而不是只生成自由文本。
* [ ] 有清晰的回退策略，避免 tool-agent 失败时整个 runtime 退化不可控。

## Definition of Done (team quality bar)

* Tests added/updated (unit/integration where appropriate)
* Lint / typecheck / CI green
* Docs/notes updated if behavior changes
* Rollout/rollback considered if risky

## Out of Scope (explicit)

* 暂不默认把 `clarify`、`scope`、`supervisor`、`reporter` 全部重写成 tool-agent
* 暂不讨论与当前目标无关的前端或 API 交互改造

## Technical Notes

* Runtime orchestration: `agent/runtime/deep/orchestration/graph.py`
* Current researcher: `agent/runtime/deep/roles/researcher.py`
* Role tool allowlists + factory: `agent/infrastructure/agents/factory.py`
* Tool assembly: `agent/infrastructure/tools/assembly.py`, `agent/infrastructure/tools/capabilities.py`
* MCP live tools: `tools/mcp.py`
* Existing tests:
  * `tests/test_deepsearch_researcher.py`
  * `tests/test_deepsearch_multi_agent_runtime.py`
  * `tests/test_agent_factory_defaults.py`

## Research Notes

### What similar structure already exists in this repo

* Runtime has already reserved a role-based tool-agent factory and role tool allowlists.
* Config already includes `deep_research_use_tool_agents`, `deep_research_supervisor_allow_world_tools`, and `deep_research_reporter_enable_python_tools`.
* Current runtime still executes researcher as a deterministic, script-first role instead of a LangChain tool agent.

### Constraints from this repo

* Deep Research output is structured around `evidence_bundle`, `section_draft`, `section_review`, and `final_report`.
* Tests and runtime assumptions currently expect a predictable branch execution contract.
* Sandbox and MCP tools are environment-dependent, so any agentification needs graceful degradation.

### Feasible approaches here

**Approach A: Bounded researcher tool-agent + scripted fallback** (initially recommended)

* How it works:
  Replace or wrap the current `ResearchAgent` execution path with a bounded tool agent that is restricted by the researcher role allowlist and task-level allowed tools, then normalize tool outputs back into the existing evidence bundle contract. If the agent path fails or yields weak evidence, fall back to the current scripted pipeline.
* Pros:
  Uses existing reserved infrastructure; change scope is focused; lower regression risk; preserves current artifacts.
* Cons:
  Requires careful adapter design between tool traces and current `documents/passages/claims` schema.

**Approach B: Hybrid researcher with explicit phase planner**

* How it works:
  Keep the current scripted pipeline as the default skeleton, but allow the LLM to choose tools inside specific sub-phases such as search expansion, page navigation, or evidence extraction.
* Pros:
  More controlled than a full agent; easier to preserve current output shape.
* Cons:
  Flexibility is weaker; may still feel “half-agent” rather than a true autonomous researcher.

**Approach C: Execution-plane agentification**

* How it works:
  Introduce a unified execution-agent abstraction for `researcher`, `verifier`, and possibly `reporter`, with role-based tool policies and shared middleware.
* Pros:
  Cleaner long-term architecture; consistent execution model across roles.
* Cons:
  Scope expands quickly; much higher regression and design cost for an MVP.
