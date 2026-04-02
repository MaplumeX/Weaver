## Context

`agent/` 包已经完成了第一轮模块显式化，但当前结构仍停留在“迁移过渡态”：

- `agent.api` 仍直接从 `agent.workflows` 暴露部分能力，导致 facade 与内部实现边界没有真正切开。
- `agent.runtime.nodes.*` 和 `agent.runtime.deep.multi_agent.*` 仍通过 `agent.workflows.*` 借用 builder、domain/source helper、quality helper 和可视化 helper。
- `agent.compat.nodes` 与 `runtime` 中的 `sys.modules.get("agent.compat.nodes")` 回退判断仍在承担测试 patch 点与导入兼容职责。
- `agent.core.graph`、`agent.workflows.search_cache`、`agent.workflows.message_utils` 这类非 `compat/` 目录下的 shim 仍然存在。
- `agent/workflows` 目录同时混杂 builder、interaction helper、research helper、legacy adapter 和历史公开出口，已经不再对应单一责任。
- Deep Research runtime 的角色边界已经形成，但运行时代码仍没有围绕 agent 角色、编排层和 shared helper 彻底重组。

这次变更不是“继续显式化 compat”，而是一次完整 hard cut：调用方要一起迁，compat 语义必须消失，最终目录结构需要直接反映真实 ownership。

## Goals / Non-Goals

**Goals:**

- 删除 `agent.compat` 目录及所有兼容回退逻辑，不保留新的替代 compat 层。
- 移除 `agent.core.graph`、`agent.workflows.search_cache`、`agent.workflows.message_utils` 等隐藏 shim，使兼容语义不再分散在 owned modules 中。
- 将 `agent/` 顶层组织为稳定 facade、shared contracts、shared primitives、runtime、builders、interaction、research helpers、prompts、parsers 等清晰边界。
- 将 Deep Research runtime 围绕 agent 角色与 orchestration 子域重组，使 `clarify`、`scope`、`supervisor`、`researcher`、`reporter` 及其 supporting services/artifacts/state 归位。
- 保持 `agent` facade 和显式 public contracts 稳定，同时完成 examples、tests、内部调用方对新 owned 模块的迁移。
- 拆分 oversized deep runtime 文件，并把 `deep_runtime` 嵌套状态提升为唯一权威结构。

**Non-Goals:**

- 不改变 Deep Research、direct、web、agent 模式的产品行为语义。
- 不在本次变更中引入新的模型供应商、搜索策略或外部依赖。
- 不为未迁移调用方保留向后兼容 shim。
- 不重写 prompts、parsers 或 examples 的功能逻辑；只在目录归属或导入路径必须调整时修改。

## Decisions

### 1. 顶层目录按 ownership 划分，而不是保留 `workflows`/`compat` 过渡结构

目标顶层边界：

- `agent/__init__.py`、`agent/api.py`: facade
- `agent/contracts/*`: 稳定共享契约
- `agent/core/*`: mode-agnostic shared primitives
- `agent/runtime/*`: graph assembly、nodes、Deep Research runtime
- `agent/builders/*`: tool-agent builder、agent factory、provider-safe middleware
- `agent/interaction/*`: response handler、continuation 等交互型 helper
- `agent/research/*`: domain/source/query/quality/browser-visualization 等研究辅助能力
- `agent/prompts/*`、`agent/parsers/*`: 内容与解析能力

`agent/workflows` 与 `agent/compat` 不再作为长期目录存在。

选择原因：

- 当前 `workflows` 已经失去单一职责，继续保留只会把“历史路径”误导成“真实所有权”。
- 删除 `compat` 后，目录结构本身必须能回答“谁拥有这段代码”。

备选方案：

- 保留 `workflows`，只删除 `compat`。放弃原因：这会把大量旧 helper 继续留在模糊目录中，实际只是换名保留迁移态。

### 2. Deep Research 子域围绕 agent 角色与 orchestration 组织

Deep Research 目标结构采用“顶层按边界，子域按 agent”：

- `agent/runtime/deep/agents/*`: `clarify`、`scope`、`supervisor`、`researcher`、`reporter`
- `agent/runtime/deep/orchestration/*`: runtime loop、dispatcher、graph assembly、entrypoints
- `agent/runtime/deep/services/*`: gap analysis、verification、artifact assembly 等 service
- `agent/runtime/deep/artifacts/*`: public artifact adapter 与 runtime artifact helper
- `agent/runtime/deep/state/*` 或等价状态模块：mode-scoped runtime state

选择原因：

- Deep Research 已经具备清晰角色边界，是唯一真正适合按 agent 组织的子域。
- 将角色与 orchestration 分开，能避免 `graph.py` 再次膨胀为“全知大文件”。

备选方案：

- 继续使用 `roles/` + 单一 `multi_agent/graph.py` 主导一切。放弃原因：角色、状态、dispatcher、tool-agent session 和 artifact adapter 的 ownership 仍然混在一起。

### 3. builder / interaction / research helper 从 runtime 中显式抽离

以下能力不再寄居 `agent.workflows.*`：

- `agent_factory`、`agent_tools`、provider-safe middleware → `agent/builders/*`
- `response_handler`、`continuation` → `agent/interaction/*`
- `domain_router`、`source_url_utils`、`quality_assessor`、browser visualization/helper → `agent/research/*`

runtime 可以依赖这些显式 owned 模块，但不得再通过历史 `workflows` 包访问它们。

选择原因：

- 这些模块不是 runtime loop 本体，也不是 facade/contracts；单独成层后，依赖方向更可读。
- 这能同时清掉 `agent.runtime.* -> agent.workflows.*` 的反向依赖。

备选方案：

- 把这些模块全部塞进 `runtime`。放弃原因：会让 runtime 再次成为无边界大集合，并把交互/研究辅助工具错误地归入执行引擎。

### 4. Public surface 只保留 facade、contracts 和显式 runtime entrypoints

受支持入口收敛为：

- `agent`
- `agent.api`
- `agent.contracts.*`
- 显式 runtime public entrypoints，例如 `agent.runtime.*`、`agent.runtime.deep.*`

实现要求：

- `agent.api` 不再从 `agent.workflows` 转发能力。
- examples、tests、内部调用方必须迁移到新 owned 模块或 facade/public contract。
- 不为旧 patch 点保留兼容别名；测试改为 patch 新 owning module。

选择原因：

- hard cut 的目标是消除“支持面”和“历史文件路径”之间的歧义。
- 继续保留兼容 alias 会让这次 change 失去意义。

备选方案：

- 先迁实现、后迁测试，临时保留别名。放弃原因：这仍然会把 compat 语义继续注入新结构。

### 5. `deep_runtime` 成为唯一权威状态，删除顶层 deep compatibility mirrors

目标状态约束：

- Deep-only 运行时数据只写入 `state["deep_runtime"]`
- 删除 `deepsearch_engine`、`deepsearch_task_queue`、`deepsearch_artifact_store`、`deepsearch_runtime_state`、`deepsearch_agent_runs` 等顶层镜像字段
- 非 deep 模式继续与 deep runtime 私有状态解耦

选择原因：

- 这些镜像字段本质上是状态级 compat layer；在 hard cut 目标下不应继续存在。
- state 面收缩后，测试和 serialization 约束都会更简单。

备选方案：

- 保留镜像字段，只约束新代码不用。放弃原因：这仍会让旧路径在后续重构中反复被继续引用。

## Risks / Trade-offs

- [导入链一次性大范围变动] → 先建立目标目录与 owned 模块，再批量替换调用方，最后删除旧目录，避免中间状态反复横跳。
- [测试 patch 点全部失效] → 在实现前先建立旧 patch 点到新 owning module 的映射清单，并同步修改测试。
- [Deep runtime 拆分引入行为漂移] → 保持 public entrypoint、事件契约和 artifacts 形状不变，用现有 deep runtime 测试覆盖回归。
- [删除 flattened deep fields 影响 session/serialization] → 先搜索所有 `deepsearch_*` 读写点，再统一迁到 `deep_runtime` 嵌套块。
- [目录重命名与职责迁移同时发生，review 成本高] → 任务拆分按 “移动 owned helpers” → “迁调用方” → “删旧路径” 顺序执行。

## Migration Plan

1. 建立目标目录与 owning modules
   - 创建 `builders`、`interaction`、`research`、Deep Research agent/orchestration 子域。
   - 迁移 `agent.workflows.*` 中仍有真实 ownership 的模块到新位置。

2. 迁移 runtime 与 facade 依赖
   - 更新 `agent.runtime.*`、`agent.api`、`agent.__init__` 的导入。
   - 让 runtime 不再出现对 `agent.workflows.*`、`agent.compat.*` 或 `sys.modules` compat 回退的依赖。

3. 迁移状态与测试
   - 删除 `AgentState` 顶层 `deepsearch_*` mirrors，统一改读写 `deep_runtime`。
   - 更新 tests、examples、内部 patch 点与文档。

4. 删除 legacy 路径
   - 删除 `agent.compat/*`
   - 删除 `agent/workflows/*` 中仅承载 compat 或历史聚合职责的文件
   - 删除 `agent/core/graph.py` 等隐藏 shim

回滚策略：

- 回滚以 git 级别整体回退本次 change 为准，不在代码中预留新的 compat 路径。
- 对外公共 facade 保持稳定，以减少回滚时的外围爆炸半径。

## Open Questions

- Deep Research 子域最终使用 `agents/` 还是保留 `roles/` 作为目录名；两者都能表达所有权，但实现阶段需要统一命名并一次性迁完，避免双目录并存。
- `browser_visualizer` 一类带明显调试/展示属性的研究辅助能力是否全部进入 `agent.research.*`，还是保留更窄的 `agent.research.visualization.*` 子域；实现阶段可根据文件体量决定。
