## Context

`agent/` 包当前同时存在 `core`、`runtime`、`workflows`、`contracts` 四层，但它们的职责边界没有真正收敛。`agent.core.graph` 仍负责 graph 装配并直接依赖 `agent.runtime.nodes`，`agent.contracts.*` 仍通过 re-export 指向 `agent.workflows.*` 实现，`agent.workflows.nodes` 与 `agent.runtime.nodes.*` 之间互相兼容回调，而 `agent.runtime.deep.multi_agent.graph` 继续直接依赖 `agent.workflows.agents.*` 与多个 workflow service。结果是：

- 公开入口重复，调用方难以判断哪些 import 是受支持的。
- lazy import 与兼容桥承担了边界修复职责，结构失真被隐藏而不是消除。
- Deep Research multi-agent runtime 已经是实际主路径，但代码所有权仍分散在 legacy workflow 目录中。
- `AgentState` 和 runtime loop 持续膨胀，增加后续拆分成本。

本次设计面向“结构收口”，而不是重写研究行为本身。目标是为后续实现提供清晰的模块归属和分阶段迁移路径。

## Goals / Non-Goals

**Goals:**

- 明确 `agent` facade、`agent.contracts`、`agent.core`、`agent.runtime` 的职责边界。
- 让 Deep Research runtime 对其角色、服务、状态和入口形成自洽所有权。
- 保持受支持的公开入口稳定，同时收缩 `agent.workflows.*` 作为隐式 API 的使用面。
- 为兼容迁移提供显式、可删除的桥接位置，而不是继续把桥接代码放在 owned modules 中。
- 为后续代码实现提供分阶段任务顺序，降低一次性大重构风险。

**Non-Goals:**

- 不改变 Deep Research、direct answer、web、agent 模式的产品级行为语义。
- 不在本次设计中引入新的模型供应商、搜索策略或外部依赖。
- 不要求一次性删除所有 legacy 文件；允许短期兼容层存在，但必须显式化。
- 不重做 prompts、parsers 或 examples 的内容，除非其导入路径因结构重组必须调整。

## Decisions

### 1. 公开 API 收敛到 facade 与 contracts

支持的外部入口收敛为：

- `agent`
- `agent.api`
- `agent.contracts.*`
- 必要时新增的显式 runtime public entrypoint

`agent.workflows.*` 不再继续扮演受支持的公开 API。若迁移期间仍需要兼容导入，必须提供显式 compat 层，而不是继续扩展 `agent.workflows.*` 的 re-export。

选择原因：

- 能让“受支持入口”和“内部实现目录”清晰分离。
- 可以在内部重组时保持外围调用方稳定。

备选方案：

- 保留 `agent.workflows.*` 兼容出口并长期维护。放弃原因：这会继续掩盖模块边界问题，并把 workflow internals 锁死为事实标准 API。

### 2. `core` 回到 shared primitives，`runtime` 拥有装配与执行

目标所有权如下：

- `agent.core.*`: mode-agnostic shared primitives，例如 state fragment、events、context、llm factory、routing primitive。
- `agent.runtime.*`: graph assembly、nodes、deep runtime loop、runtime-owned roles/services。
- `agent.contracts.*`: 共享契约和稳定 wrapper。
- `agent.compat.*`: 临时兼容桥，仅服务迁移。

其中 graph 装配不再视为 `core` 责任；如果某个模块需要直接装配 runtime nodes，它就属于 `runtime` 边界。

选择原因：

- graph assembly 天然依赖 execution node，放在 `core` 会迫使 `core -> runtime` 反向依赖。
- shared primitives 与 orchestration 拆开后，更容易识别和切断循环导入。

备选方案：

- 维持 `core.graph` 现状，只通过 lazy import 降低循环导入。放弃原因：只是在技术上延后问题，没有修正错误的所有权。

### 3. Deep Research runtime 自有化角色与服务

当前 `multi_agent` runtime 仍直接依赖 `agent.workflows.agents.*`、`claim_verifier`、`knowledge_gap`、`result_aggregator` 等实现。设计上将这些模块按所有权迁移到 runtime-owned 位置：

- runtime roles：clarify、scope、researcher、reporter、supervisor 等
- runtime services：verification、gap analysis、artifact assembly、source registry 等
- runtime schema/store/dispatcher/events/public entrypoints：继续保留在 `agent.runtime.deep.*`

共享且可被外围消费的结构保留在 `agent.contracts.*` 或专用 schema/contract 模块中，但 `contracts` 不再反向依赖 workflow internals。

选择原因：

- runtime loop 直接依赖 workflow internals，说明 runtime 尚未完成模块化。
- 角色与服务回归 runtime-owned 目录后，`agent.runtime.deep.multi_agent.graph` 可以缩小为真正的 orchestration layer。

备选方案：

- 继续把这些实现留在 `agent.workflows.*`，把 runtime 视为单纯调用方。放弃原因：这会让 Deep Research runtime 永远无法形成自洽边界。

### 4. 兼容层显式化并限制生命周期

迁移期间允许保留少量兼容桥，但它们必须满足：

- 放在显式 compat 位置或等价的专用临时模块中。
- 只做薄 re-export 或参数适配，不承载真实业务逻辑。
- 新代码不得新增对旧路径的依赖。
- 一旦调用方迁移完成，可以直接删除 compat 层，而无需再移动真正的拥有者模块。

选择原因：

- 兼容桥本身不是问题，问题是它目前隐藏在 `workflows`、`runtime.nodes` 的 owned module 里。

备选方案：

- 立即硬删除旧路径。放弃原因：改动面过大，容易让这次 change 演变成高风险全量重命名。

### 5. Deep runtime 状态继续收敛到嵌套结构

`deep_runtime` 已经是正确方向，但顶层 `AgentState` 仍保留多组 deep-only 字段。后续实现应遵循：

- 新增 deep-only 状态一律写入 `deep_runtime` 或等价的 mode-scoped state block。
- 历史顶层字段仅作为过渡兼容，不再扩大字段集合。
- 非 deep 模式不得依赖 deep runtime 私有字段才能工作。

选择原因：

- 顶层共享状态继续膨胀会让 direct/web/agent 模式与 deep runtime 耦合。

备选方案：

- 继续平铺状态并依赖注释区分用途。放弃原因：状态面会持续失控，且测试边界更难定义。

## Risks / Trade-offs

- [导入链广泛变动] → 先建立 facade/compat，再逐步迁移内部调用方，避免一次性断裂。
- [Deep runtime 重组跨越多个目录] → 先迁 runtime-owned roles/services，再处理 graph/state 收口，减少并发变量。
- [内部调用方仍依赖 `agent.workflows.*`] → 在实现开始前先用全局搜索建立调用方清单，并为每类路径提供替代入口。
- [状态迁移期间读写双轨] → 明确把顶层 deep-only 字段视为过渡层，新代码只对嵌套状态写入。
- [过度扩大重构范围] → 本次 change 只收敛与 agent 边界直接相关的目录和导入，不顺手重写业务逻辑。

## Migration Plan

1. 建立目标边界与公开入口
   - 固化 facade/contract 支持面。
   - 引入显式 compat 位置，禁止新增对 legacy workflow 路径的依赖。

2. 迁移 Deep Research runtime-owned 模块
   - 将 roles/services 从 `agent.workflows.*` 迁入 `agent.runtime.deep.*`。
   - 更新 `multi_agent` runtime 与 graph node 的内部导入。

3. 收拢 graph assembly 与 shared contracts
   - 将 runtime graph 装配从 `core` 迁到 runtime-owned 位置。
   - 清理 `agent.contracts.*` 对 workflow internals 的反向依赖。

4. 状态与兼容层收尾
   - 推进 deep runtime state 嵌套化。
   - 删除已无调用方的 compat/legacy 桥接。

回滚策略：

- 对外继续保留 `agent` facade，不把内部目录重排直接暴露给外围调用方。
- 如果某一阶段迁移未完成，可短期恢复 compat 桥而不回滚新的 owned module 布局。

## Open Questions

- `response_handler`、`continuation` 一类交互型 helper 最终是继续保留在 `workflows`，还是单独抽成新的 interaction 目录；本次 change 先不强行解决，但实现时要避免再让它们成为 runtime-owned 模块的宿主。
- `agent.compat.*` 是否需要新增顶层目录，还是以更小粒度的临时 shim 文件承载；建议实现阶段根据实际调用方数量决定，但规范上要求“显式、可删除”。
