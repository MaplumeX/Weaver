# brainstorm: tool system standardization

## Goal

将当前工具系统标准化，减少自研装配与官方范式之间的偏差，使 Weaver 的工具定义、工具上下文、工具执行编排、MCP 接入和工具暴露方式更接近 LangChain / LangGraph 官方推荐做法，同时控制改造风险，避免一次性重写整套运行时。

## What I already know

* 当前项目已经建立在 LangChain / LangGraph 1.x 上，依赖见 `requirements.txt`。
* Agent 执行层已经使用 `create_agent()` 和官方 middleware。
* 根图和 Deep Research 图已经使用 `StateGraph`、`Send`、`interrupt()`、自定义 checkpointer。
* 当前工具系统不是纯官方 canonical 形态，主要偏差在：
* agent 模式先用关键词规则预选工具，再进入内层 tool agent。
* 工具上下文主要通过 `RunnableConfig["configurable"]` 和手动注入 `thread_id` 传递。
* MCP 主链路使用自定义 `MCPClients`，不是官方 `MultiServerMCPClient` 主路径。
* 仓库中同时混用了 `langchain.tools` 与 `langchain_core.tools` 风格。

## Assumptions (temporary)

* 用户说的“标准化”是指对齐 LangChain / LangGraph 官方推荐范式，而不是只做命名清理。
* 本次改造优先关注后端运行时，不涉及前端 UI 重做。
* 可以接受分阶段改造，而不是一次完成所有工具子系统迁移。

## Open Questions

* 无

## Requirements (evolving)

* 以 LangChain / LangGraph 官方 canonical 风格为目标标准化当前工具系统。
* 保留现有业务能力与主要图编排能力，不做无必要的功能删减。
* 采用分阶段迁移，而不是一次性重写全部运行时。
* 第一阶段采用激进范围：普通 agent 与 Deep Research 一并切到新的 graph-native 工具执行模型。
* 第一阶段允许破坏性调整，不要求兼容现有 API、tool 名、事件字段或 resume 形态。
* 新主执行模型采用“LangGraph 外壳 + Agent 内核”：
* 外层负责状态迁移、并发、checkpoint、interrupt、阶段控制。
* 内层允许在节点内使用 `create_agent()` 执行多轮 tool calling。
* 优先减少以下偏差：
* 规则式选工具路径
* 自定义工具上下文注入方式
* 自定义 MCP 主接入路径
* 混合工具定义风格
* 新系统中的工具暴露采用混合模式：
* 对外按 capability / role 配置
* 对内展开为 concrete tool ids / tool objects
* model tool calling 仍面向 concrete tools
* 产出一套可执行的分阶段标准化方案，后续进入实现。

## Acceptance Criteria (evolving)

* [ ] 明确 canonical graph-native 目标形态
* [ ] 明确工具系统中需要优先标准化的模块
* [ ] 明确第一阶段改造范围和不做项
* [ ] 明确迁移期间必须保持兼容的运行时契约
* [ ] 明确第一阶段激进改造下的回归边界
* [ ] 明确允许被重订的对外契约
* [ ] 明确新系统中的工具暴露与权限控制模型
* [ ] 明确需要迁移的核心模块、文件和顺序

## Definition of Done (team quality bar)

* Tests added/updated (unit/integration where appropriate)
* Lint / typecheck / CI green
* Docs/notes updated if behavior changes
* Rollout/rollback considered if risky

## Out of Scope (explicit)

* 一次性重写全部 agent runtime
* 无明确收益的全仓库风格整理
* 与工具系统标准化无关的业务功能调整
* 在第一阶段直接改写 Deep Research 全部内部角色逻辑

## Technical Notes

* 已检查关键文件：
* `agent/infrastructure/agents/factory.py`
* `agent/infrastructure/tools/assembly.py`
* `agent/infrastructure/tools/capabilities.py`
* `agent/infrastructure/tools/providers.py`
* `agent/infrastructure/tools/catalog.py`
* `agent/runtime/graph.py`
* `agent/runtime/nodes/chat.py`
* `agent/runtime/nodes/answer.py`
* `agent/runtime/deep/orchestration/graph.py`
* `tools/mcp.py`
* `tools/core/mcp.py`
* `tools/core/mcp_clients.py`
* `tools/core/wrappers.py`
* 官方基线已对照：
* LangChain Agents
* LangChain Tools
* LangChain Human-in-the-Loop
* LangChain MCP
* LangGraph Graph API

## Research Notes

### What similar official patterns do

* LangChain 官方 agent 模式强调由模型原生 tool calling 驱动工具选择，并通过 middleware 控制工具暴露、重试、限流、HITL。
* LangGraph 官方图模式强调用 `StateGraph` 管理状态迁移，用 `interrupt()` 处理人工介入，用 `Send` 处理并发分支。
* 官方推荐的工具上下文更偏向显式 runtime/context 注入，而不是依赖隐式全局状态或手动给 tool 实例塞字段。
* 官方 MCP 接入更偏向 `MultiServerMCPClient` 这类标准适配层，而不是项目私有 proxy client。
* 工具权限与暴露一般采用混合模式：
* 对外按 capability 或 role 配置。
* 对内展开为 concrete tool IDs / tool objects。
* 执行时仍然由具体工具 schema 驱动 model tool calling。

### Constraints from our repo/project

* 当前根图和 Deep Research 图已经深度依赖现有 state shape 和中间事件系统，不能一次性推倒。
* 当前前端依赖 `tool_start/tool_progress/tool_result/tool_error/tool_screenshot` 这套事件契约。
* 当前 agent profile 机制依赖工具名白名单。
* 当前大量工具已经存在，真正需要改的是“装配方式、上下文方式、执行方式”，不是重写每个工具能力。

### Feasible approaches here

**Approach A: 轻量标准化**

* How it works:
统一工具定义风格、收敛 MCP 入口、保留现有路由和工具执行方式。
* Pros:
风险最低，能快速提升一致性。
* Cons:
核心架构仍旧不是官方 canonical。

**Approach B: 官方范式优先的渐进式标准化** (Recommended)

* How it works:
保留现有 graph 和业务能力，分阶段替换工具上下文、MCP 接入、工具选择策略。
* Pros:
收益和风险平衡最好。
* Cons:
过渡期会出现新旧模式并存。

**Approach C: 完全重构为 canonical graph-native**

* How it works:
以 LangGraph/LangChain 官方推荐形态为目标重建工具执行主路径，尽量移除当前自研装配与规则式选工具路径。
* Pros:
长期一致性最好，技术债最少。
* Cons:
改造面最大，回归风险最高，需要阶段化迁移和充分回归测试。

## Decision (ADR-lite)

**Context**:
当前工具系统已经使用 LangChain / LangGraph 核心能力，但工具选择、工具上下文和 MCP 接入仍存在较多项目私有 glue code，长期会增加维护成本并阻碍后续演进。

**Decision**:
选择 **Approach C: 完全重构为 canonical graph-native** 作为目标架构，但采用分阶段迁移落地。

**Consequences**:
* 长期工具系统一致性更高
* 迁移期间可以重订现有对外契约，但需要明确新的 canonical 目标契约
* 第一阶段会同时冲击根图、Deep Research、前端事件契约和 agent profile 体系，必须先定义新的统一模型

## Target Architecture Draft

### Layer 1: Capability / Role Layer

* 对外不再直接暴露零散工具名，统一为 capability 与 role：
* capability 示例：`search`、`browser`、`files`、`shell`、`python`、`mcp`、`planning`
* role 示例：`default_agent`、`researcher`、`reporter`、`supervisor`

### Layer 2: Tool Registry Layer

* 所有具体工具统一进入单一 registry。
* 每个工具具备：
* stable tool id
* LangChain-compatible name
* args schema
* description
* tags / capability labels
* optional policy metadata

### Layer 3: Exposure / Policy Layer

* role 与 capability 在运行前解析为具体工具集合。
* 权限控制、allowlist、blocklist、HITL、危险工具策略都在这一层完成。

### Layer 4: Runtime / Context Layer

* 线程、用户、store、checkpoint、事件写入器、权限上下文统一经 runtime/context 注入。
* 运行时不再依赖手动给 tool 实例设置 `thread_id` 或读取项目私有全局状态。

### Layer 5: Execution Layer

* 外层 LangGraph 负责状态迁移、阶段编排、并发分支、interrupt、checkpoint。
* 内层 `create_agent()` 负责在给定 concrete tools 集合上执行多轮 tool calling。
* 普通 agent 与 Deep Research 共用同一工具 registry、policy 与 runtime context 模型。

### MCP Target Shape

* MCP 统一走官方 adapter 风格主链路。
* MCP 工具视为 registry 中的一类 tool source，而不是单独旁路系统。

### Event Target Shape

* 工具事件从“工具各自私有发事件”收敛为统一 runtime 事件通道。
* 事件模型区分：
* tool lifecycle
* artifact / screenshot
* task / graph progress
* decision / interrupt

## Current Preference Snapshot

* 目标架构：完全重构为 canonical graph-native
* 第一阶段范围：激进，普通 agent 与 Deep Research 同步迁移
* 兼容策略：允许破坏性调整，以新 canonical 契约优先
* 主执行模型：LangGraph 外壳 + Agent 内核
* 工具暴露模型：混合模式（外部 capability / role，内部 concrete tools）

## Technical Approach

### A. Canonical Contract Redesign

* 将当前 `AgentProfile.tools / blocked_tools` 从“直接存具体工具名”升级为：
* `roles`
* `capabilities`
* `blocked_capabilities`
* optional explicit concrete overrides（仅调试或迁移期使用）
* 建立统一 `ToolSpec` / `ToolRegistry` 模型，收编现有 tool metadata、schema、tags、risk 信息。

### B. Unified Runtime Context

* 引入统一 runtime context schema，集中承载：
* user/thread/session identity
* event writer / emitter
* persistence handles / stores
* capability grants / policy decision
* tool execution metadata
* 工具不再依赖手工设置 `thread_id` 或项目私有全局状态。

### C. Standardized Execution Path

* 普通 agent：
* 移除基于关键词的 `_select_tools_for_input`
* 使用统一 policy 先解析 role/capability，再把 concrete tools 交给内层 `create_agent()`
* Deep Research：
* 各角色不再维护分散的工具装配逻辑
* 统一走同一 registry / policy / runtime context

### D. MCP Standardization

* 废弃当前自定义 MCP 主路径，统一改到官方 adapter 风格主链路。
* MCP 被视为 registry 中的一种 tool source，而不是旁路系统。

### E. Event Model Redesign

* 重新定义统一事件总线契约：
* graph lifecycle
* tool lifecycle
* artifact/screenshot
* decision/interrupt
* research progress
* 事件发射从“工具各自直接控制”转为“runtime 统一封装”。

## Files / Modules To Change

### Core Model & Policy

* `common/agents_store.py`
* `agent/domain/execution.py`
* `agent/application/state.py`
* `agent/core/state.py`

### Tool Registry / Exposure / Context

* `agent/infrastructure/tools/capabilities.py`
* `agent/infrastructure/tools/providers.py`
* `agent/infrastructure/tools/assembly.py`
* `agent/infrastructure/tools/catalog.py`
* 新增统一 registry / policy / runtime context 模块

### Agent Execution

* `agent/infrastructure/agents/factory.py`
* `agent/runtime/nodes/chat.py`
* `agent/runtime/nodes/answer.py`
* `agent/runtime/nodes/_shared.py`

### Deep Research Execution

* `agent/runtime/deep/orchestration/graph.py`
* Deep Research role/tool 相关模块

### MCP

* `tools/mcp.py`
* `tools/core/mcp.py`
* `tools/core/mcp_clients.py`

### Events / Streaming / API

* `agent/core/events.py`
* `agent/contracts/events.py`
* `main.py`

### Frontend Contract Consumers

* `web/hooks/useChatStream.ts`
* `web/hooks/useBrowserEvents.ts`
* `web/types/chat.ts`
* `web/types/browser.ts`
* `web/lib/process-display.ts`
* `web/lib/session-utils.ts`
* `web/components/chat/BrowserViewer.tsx`

## New Canonical Contract (Proposed)

### Public Product-Level Config

* Agent profile stores:
* `roles`
* `capabilities`
* optional `policy`
* 正常流程不直接依赖 concrete tool names

### Runtime-Level Contract

* Execution request resolves:
* granted capabilities
* concrete tool ids
* tool objects
* runtime context

### Event-Level Contract

* Unified process event envelope with:
* `type`
* `run_id`
* `node`
* `tool_id`
* `phase`
* `status`
* `payload`
* 旧 `tool_*` 事件可不保留

## Implementation Plan (small PRs)

* PR1: 定义新 canonical contract
  * 引入 capability / role / tool registry / runtime context 核心模型
  * 重构 agent profile 数据结构
  * 定义新的事件 envelope 和 tool metadata shape
* PR2: 接管普通 agent 执行路径
  * 移除规则式选工具
  * 普通 agent 改走 registry + policy + runtime context
  * 接入新的 MCP 主路径
* PR3: 接管 Deep Research 执行路径
  * 各角色统一通过 registry / policy 解工具
  * 合并分散的工具装配逻辑
* PR4: API / streaming / frontend 契约切换
  * `main.py` 流事件与持久化结构改到新契约
  * 前端 process/timeline/browser viewer 适配新事件模型
* PR5: 删除旧路径与清理
  * 删除关键词选工具逻辑
  * 删除旧 MCP 主路径
  * 删除旧 tool event 兼容胶水
