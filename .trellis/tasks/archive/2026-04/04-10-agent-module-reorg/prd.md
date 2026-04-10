# brainstorm: reorganize agent module architecture

## Goal

重新组织 `agent/` 模块的目录边界、职责分层和公开接口，降低运行时编排、提示词、工具装配、研究领域逻辑之间的耦合度，使后续在 `agent` 子系统内扩展新 runtime、角色、prompt 或工具策略时更容易定位代码与控制影响范围。

## What I already know

* 用户希望重新组织 `agent` 模块，并允许深入到代码层级。
* 当前仓库后端规范要求保持既有包边界，不要硬套通用 controller/service/repository 分层。
* `agent/` 当前包含 `application`、`contracts`、`core`、`domain`、`infrastructure`、`prompts`、`research`、`runtime` 等一级目录。
* `agent/runtime/deep` 已经形成独立子系统，其中 [agent/runtime/deep/orchestration/graph.py](/home/maplume/projects/Weaver/agent/runtime/deep/orchestration/graph.py) 超过 3000 行，是当前最大的复杂度热点。
* [agent/application/state.py](/home/maplume/projects/Weaver/agent/application/state.py) 直接依赖 `agent.runtime.deep.config`，说明应用层与具体 runtime 存在直接耦合。
* [agent/prompts/prompt_manager.py](/home/maplume/projects/Weaver/agent/prompts/prompt_manager.py) 依赖 `agent.infrastructure.prompts`，而 [agent/infrastructure/prompts/registry.py](/home/maplume/projects/Weaver/agent/infrastructure/prompts/registry.py) 又反向依赖 `agent.prompts.*`，存在明显的双向依赖信号。
* `main.py` 既使用 `agent` 顶层 facade，也直接使用 `agent.application`、`agent.contracts`、`agent.infrastructure.tools`，说明公开 API 面没有完全收口。

## Assumptions (temporary)

* 本任务大概率不是纯目录移动，而是需要同时调整模块职责边界与导入方向。
* 优先目标应该是降低维护成本和认知负担，而不是追求抽象层数增加。
* Deep Research runtime 很可能需要作为独立“能力子域”处理，而不是继续塞在通用 runtime 目录里。
* 用户已选择 `Approach C`，即顶层按能力域重组。

## Open Questions

* 迁移策略采用哪种：保留旧路径兼容层，还是全仓一次切到新能力域路径？

## Requirements (evolving)

* 梳理 `agent/` 当前模块地图、入口点和主要依赖方向。
* 识别当前目录结构中最值得先动的边界问题与“上帝模块”。
* 给出 2-3 个可执行的重组方案，并说明迁移成本、收益和风险。
* 若用户确认方向，再进入实际代码重组。
* 顶层目录命名应优先表达业务能力，而不是通用技术分层名。

## Acceptance Criteria (evolving)

* [ ] 能明确说明 `agent/` 当前主导架构风格与边界问题。
* [ ] 能指出至少一条核心执行链路及其跨目录依赖。
* [ ] 能给出可落地的重组方案，而不是泛化建议。
* [ ] 方案能映射到具体文件与迁移步骤。

## Definition of Done (team quality bar)

* Tests added/updated (unit/integration where appropriate)
* Lint / typecheck / CI green
* Docs/notes updated if behavior changes
* Rollout/rollback considered if risky

## Out of Scope (explicit)

* 当前不直接改动 `common/`、`tools/`、`triggers/` 的整体架构，除非 `agent` 边界调整必须触达。
* 当前不讨论前端展示层重构。
* 当前不做“为了未来可能有用”的泛化框架设计。

## Technical Notes

* Relevant specs:
  * [directory-structure.md](/home/maplume/projects/Weaver/.trellis/spec/backend/directory-structure.md): 约束 `agent/` 应承载 runtime orchestration、contracts、prompts 和 reusable agent APIs。
  * [tool-runtime-contracts.md](/home/maplume/projects/Weaver/.trellis/spec/backend/tool-runtime-contracts.md): 若重组触及 tool runtime、profile、streaming 或 deep runtime artifact，需要保持契约稳定。
  * [cross-layer-thinking-guide.md](/home/maplume/projects/Weaver/.trellis/spec/guides/cross-layer-thinking-guide.md): 本任务涉及多层边界，需要先识别数据流和契约边界。
* Initial findings:
  * `agent/` 总计约 15.9k 行 Python。
  * 复杂度主要集中在 deep runtime、prompt 模板、agent factory、多模型与事件系统。
  * `agent/api.py` 和 `agent/__init__.py` 已有 facade 设计，但入口还未完全统一。
* Module map:
  * `agent.application`: 组装执行请求与初始状态，但目前仍依赖具体 runtime 配置。
  * `agent.domain`: 执行模式、profile 配置、状态切片等领域契约。
  * `agent.core`: 对话消息、状态聚合、事件流、多模型等运行时公共能力。
  * `agent.runtime`: root graph、chat/tool/deep 节点，以及 `deep` 子系统。
  * `agent.infrastructure`: tool/provider 装配、agent factory、prompt registry、browser context。
  * `agent.prompts`: prompt 内容、模板与 prompt manager facade。
  * `agent.research`: 领域路由、证据 passage、URL 归一化等研究辅助逻辑。
  * `agent.contracts`: 对外稳定契约与 facade。
* Cross-module signals:
  * `application -> runtime`: [agent/application/state.py](/home/maplume/projects/Weaver/agent/application/state.py) 直接读取 `SUPPORTED_DEEP_RESEARCH_RUNTIME`。
  * `prompts <-> infrastructure`: [agent/prompts/prompt_manager.py](/home/maplume/projects/Weaver/agent/prompts/prompt_manager.py) 与 [agent/infrastructure/prompts/registry.py](/home/maplume/projects/Weaver/agent/infrastructure/prompts/registry.py) 形成双向依赖。
  * `main.py` 同时消费 `agent` facade 与多个内部子包，说明公共入口没有完全成为唯一入口。
  * `common/`、`tools/` 对 `agent.contracts`、`agent.core`、`agent.runtime.deep.artifacts` 也有直接依赖，迁移时需要保兼容层。

## Research Notes

### Current dominant style

* 显式事实：`agent/` 已经在目录名上尝试表达 `application / domain / infrastructure / runtime`。
* 推断：当前更接近“模块化单体里的混合分层”，不是严格的整洁架构，因为部分应用层和 prompt 层仍直接依赖具体实现。

### Core execution paths

* Chat/Tool path:
  * `main.py` 构造 request/state
  * `agent.runtime.graph.create_research_graph()`
  * `agent.runtime.nodes.routing/chat/answer/finalize`
  * `agent.infrastructure.tools` / `agent.infrastructure.agents`
* Deep Research path:
  * `main.py`
  * `agent.runtime.graph`
  * `agent.runtime.nodes.deep_research`
  * `agent.runtime.deep.entrypoints`
  * `agent.runtime.deep.orchestration.graph`
  * `agent.runtime.deep.roles.*` / `agent.runtime.deep.support.*`

### Highest-value problems

* `deep` 子系统过重，编排、artifact 组装、质量判定、状态推进仍高度集中在单文件。
* prompt 相关职责分散在 `prompts` 与 `infrastructure/prompts` 两边，依赖方向不干净。
* `application` 层持有一部分 runtime 细节，导致“准备输入”和“选择执行引擎”没有彻底分离。
* 外部调用面对 `agent` 内部结构感知过多，未来搬目录会产生高迁移成本。

### Feasible approaches here

**Approach A: 边界收口优先**（推荐，低风险）

* How it works:
  * 保留现有一级目录。
  * 先收口依赖方向和公开入口：让 `application` 不再依赖具体 runtime，让 `prompts` 不再依赖 `infrastructure`，让 `main.py` 更多走 facade。
  * 在 `runtime/deep` 内部再做二级拆分，不先大规模搬顶层目录。
* Pros:
  * 风险最低，便于分阶段提交。
  * 先解决最伤维护性的边界问题，不破坏大量 import。
  * 适合先建立稳定 facade，再逐步迁移。
* Cons:
  * 顶层目录观感变化有限。
  * 大文件拆分要分后续阶段继续推进。

**Approach B: 以 Deep Research 为核心重切 runtime 子域**

* How it works:
  * 将 `runtime/deep` 明确视为独立子系统，围绕 `entrypoints / orchestration / roles / artifacts / support / state` 继续拆细。
  * 同步把与 deep 强耦合的 prompt、schema、research helper 重新归类或下沉。
* Pros:
  * 直接命中当前最大复杂度来源。
  * 对后续 deep runtime 扩展最友好。
* Cons:
  * 需要更广泛的 import 调整和回归验证。
  * 如果不先收口 facade，外部引用会让迁移成本偏高。

**Approach C: 顶层按能力域重组**

* How it works:
  * 弱化 `application/domain/infrastructure` 这类通用层名，改为按能力域重组，例如 `agent/chat`、`agent/deep_research`、`agent/tooling`、`agent/prompts`、`agent/contracts`。
* Pros:
  * 对阅读者最直观，文件归属更贴近业务能力。
  * 适合后续继续扩多个 agent runtime。
* Cons:
  * 迁移面最大，几乎所有导入路径都会受影响。
  * 需要先证明现有域边界足够稳定，否则容易“换名字不降复杂度”。

### Capability-domain target draft for Approach C

* `agent/chat/`
  * 当前 `runtime/nodes/{routing,chat,answer,finalize,prompting}` 中与 chat/tool-assisted 路径直接相关的内容。
  * 负责普通对话、工具升级路径、chat runtime prompt 组装。
* `agent/deep_research/`
  * 当前 `runtime/deep/*` 以及与 deep 运行链高度耦合的研究编排逻辑。
  * 作为独立能力子系统维护。
* `agent/tooling/`
  * 当前 `infrastructure/tools/*`、`infrastructure/agents/*`、`infrastructure/browser_context.py`。
  * 统一承载工具注册、运行时上下文、tool agent factory。
* `agent/prompting/`
  * 当前 `prompts/*` 与 `infrastructure/prompts/*`。
  * 目标是把 prompt 内容、registry、manager 收到同一能力域，去掉双向依赖。
* `agent/execution/`
  * 当前 `application/*` 与 `domain/execution.py` 中偏“执行入口/请求建模/初始状态构造”的部分。
  * 负责 request、mode、初始 state 装配。
* `agent/foundation/`
  * 当前 `core/*` 与 `domain/state.py` 中更偏运行时公共基座的部分，例如事件、状态类型、多模型、消息处理、缓存。
  * 作为跨能力域共享基座，不承载具体业务编排。
* `agent/contracts/`
  * 保留为稳定导出层，供 `main.py`、`tools/`、`common/`、测试与未来外部调用使用。

### Initial migration principle for Approach C

* 根 `agent/__init__.py` 和 `agent/api.py` 应继续作为稳定 facade。
* 对外高频导入路径需要优先通过兼容导出层过渡，否则 `main.py`、`common/`、`tools/`、测试面会同时爆炸。
* 应先迁移“内部真实实现”，再决定是否批量清理历史导入路径。
