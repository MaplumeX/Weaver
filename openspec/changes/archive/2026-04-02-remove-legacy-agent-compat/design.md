## Context

Weaver 当前已经把公开聊天模式收敛到 `agent` / `deep`，但代码库仍同时维护以下历史层：

- 公开 facade 仍导出旧 Deep Research 入口，如 `run_deepsearch`
- 后端 session / metrics / resume 仍对历史 route 与历史 `search_mode` 字段做迁移或回填
- 前端 history / snapshot 仍对 `web`、`direct`、`ultra` 等历史 route 做归一化
- Deep Research 主路径内部仍保留 `deepsearch_*` 命名、`research_tree` 命名、`coordinator` 角色、outer hierarchical 分支和 legacy runtime 文件
- `SessionManager` 与公开 artifacts 仍对旧顶层 state 与旧 artifact key 做 fallback 拼装

这导致当前系统表面上已经 hard-cut，但内部依然存在多套命名、状态和 patch 点。继续保留这些层会让模块边界、恢复契约、测试命名和后续 API 演化长期处于“半迁移”状态。

本变更选择一次性 hard cut，而不是继续保留双写或长期 shim。

## Goals / Non-Goals

**Goals:**

- 删除旧模式、旧 Deep Research runtime、旧导出和旧命名的运行时兼容层
- 让 `agent` facade、Deep Research runtime、session artifacts、事件与 checkpoint 只保留一套 canonical 语义
- 删除 outer hierarchical / coordinator 兼容路径，使 Deep Research 控制面只剩 `supervisor`
- 让恢复和导出逻辑只依赖当前权威 runtime snapshot，而不是旧 state fallback
- 统一前后端与测试基线，避免继续围绕历史别名保留 patch 点

**Non-Goals:**

- 不为旧会话、旧 checkpoint、旧前端本地缓存保留长期兼容
- 不引入新的 runtime 模式或新的 Deep Research 功能
- 不尝试通过双写或灰度桥接实现无缝迁移
- 不重构与本次 hard cut 无关的 tool、provider 或 UI 视觉逻辑

## Decisions

### 1. 采用硬切兼容策略，不保留旧 route / 旧导出 / 旧 checkpoint 的运行时迁移

保留兼容层的主要代价不在单个 if 分支，而在于整个系统必须长期维护旧 facade、旧状态回填、旧前端归一化和旧测试 patch 点。当前公开模式已经 hard-cut 到 `agent` / `deep`，继续保留运行时兼容只会把这次清理无限延期。

因此本次设计明确选择：

- 删除后端 `_LEGACY_*` route 迁移与旧 route 重写
- 删除前端 `web` / `direct` / `ultra` 等历史 route 归一化
- 删除公开 facade 上的旧 Deep Research 导出
- 删除旧 checkpoint 名和旧 artifact key 的恢复兼容

备选方案：

- 保留双读双写一段时间：兼容性最好，但会继续污染 facade、resume 和测试基线
- 仅删导出、不删状态兼容：实现成本较低，但不能满足“完整清除旧实现、旧导出、旧命名”

选择硬切，是因为本变更的目标就是彻底消除历史层，而不是再引入一轮过渡层。

### 2. 统一 canonical 命名，从 `deepsearch_*` 迁移到 `deep_research_*`

当前系统虽然公开名称是 “Deep Research”，但内部仍大量使用 `deepsearch_*` 前缀和 `research_tree` 旧术语。这会让当前权威实现继续带着 legacy 语义。

本次设计将命名统一为：

- 入口 / 函数 / 模块：`deep_research_*`
- 公开 artifacts：`deep_research_artifacts`
- topology 快照：`research_topology`
- checkpoint：`deep_research_clarify`、`deep_research_scope_review`、`deep_research_merge`
- 事件：`deep_research_topology_update` 等 canonical Deep Research 事件名
- 配置：`deep_research_*` 前缀

备选方案：

- 保留 `deepsearch_*`，只删 legacy runtime：实现最省，但旧命名仍留在主路径
- 把内部命名压缩成 `deep_*`：更短，但和现有 “Deep Research” 术语的语义映射不如 `deep_research_*` 直接

选择 `deep_research_*`，因为它与当前产品术语一致，且能清楚地区分历史 `deepsearch` 时代和当前 canonical runtime。

### 3. 删除 `coordinator` / hierarchical 兼容路径，所有循环决策统一收敛到 `supervisor`

当前 outer graph 仍保留 `use_hierarchical_agents` 和 `coordinator_node`，而 `ResearchSupervisor` 也继续包装 `ResearchCoordinator`。这让控制面存在两套语义：

- 当前规范语义：`supervisor`
- 历史兼容语义：`coordinator` / hierarchical path

本次设计要求：

- 删除 outer graph 中的 hierarchical branch
- 删除 `use_hierarchical_agents` 配置和相关状态字段
- 将现有 deterministic decision 逻辑直接内聚进 `ResearchSupervisor`
- 不再公开 `coordinator` 角色、节点、动作字段或测试 patch 点

备选方案：

- 保留 coordinator 作为 supervisor 内部 helper：实现改动较小，但旧概念仍然存活
- 保留 outer hierarchical graph 但默认关闭：仍会继续占用边界、测试和状态契约

选择完全删除，是为了让编排语义和角色模型只保留一套权威定义。

### 4. 恢复与公开 artifacts 只依赖权威 runtime snapshot，不再从旧顶层 state 回填

当前 `SessionManager` 会从 `deepsearch_artifacts`、`research_plan`、`research_tree`、`quality_summary` 等旧顶层字段反推公开 artifacts，并在 resume 时再把这些字段写回顶层 state。这样会让新 runtime 长期受制于旧 state shape。

本次设计要求：

- 公开 artifacts 只从当前 Deep Research runtime store 派生
- 恢复路径只读取 canonical public artifacts 与 runtime snapshot
- 不再将旧 artifacts key、旧 tree key、旧 query key 回填到顶层 state
- 旧 checkpoint / session 若不满足新契约，视为不受支持

备选方案：

- 保留 fallback 拼装逻辑：兼容旧 checkpoint，但会永久保留旧 state shape
- 做一次迁移脚本并继续保留 fallback：比纯 hard cut 更复杂，也不符合本次目标

选择只认权威 snapshot，可以让 runtime state contract 变得清晰且可验证。

## Risks / Trade-offs

- [旧会话、旧 checkpoint 无法恢复] → 在发布说明中明确标注 hard cut，前端本地缓存与旧 Deep Research 会话视为不受支持
- [Python 外部导入方因删除旧导出而报错] → 在 proposal/spec/tasks 中明确列出 facade breaking change，并同步更新 repo 内 tests/examples/docs
- [命名迁移范围大，容易漏改测试与事件消费端] → 以 capability 为单位同步更新 backend、frontend、tests、docs，并用搜索校验不再残留旧名
- [拓扑事件与 artifact key 更名会影响前端过程展示] → 将前端事件解析、interrupt review、session restore 一并纳入同一 change，而不是拆到后续
- [删除 coordinator 后，supervisor 决策逻辑可能暂时膨胀] → 在实现中优先内聚 deterministic rules，必要时再以 supervisor-owned helper 拆分，但不重新引入公开 coordinator 概念

## Migration Plan

1. 先删除 facade、route、前端 snapshot 中的旧模式兼容和旧导出。
2. 再删除 Deep Research legacy runtime、outer hierarchical path 与 coordinator 兼容层。
3. 同一批次完成 `deepsearch_*` → `deep_research_*` 的命名迁移，包括 checkpoint、events、artifacts、config、tests 和 docs。
4. 更新 resume / session / event / artifact 相关测试，使其仅验证 canonical 契约。
5. 发布时将旧 session / checkpoint / local cache 视为不受支持状态，不提供运行时回填。

回滚策略：

- 若必须回滚，只能整体回滚这次变更；不计划在代码中保留双向兼容桥

## Open Questions

- 是否需要在前端为“检测到旧本地缓存”提供一次显式清理提示，而不是静默回到空白 canonical 会话
- 是否将 topology 统一命名为 `research_topology`，还是保留更窄的 `branch_topology` 语义
