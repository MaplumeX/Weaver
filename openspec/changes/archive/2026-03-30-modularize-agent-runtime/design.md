## Context

当前 `agent/` 包已经形成 facade、graph、prompt、workflow、parser 等表层分层，但复杂度并没有随目录切分而真正分散。实际运行路径仍高度依赖几个中心文件：

- `agent/workflows/nodes.py` 同时承担 graph node 入口、路由、deepsearch 入口、agent/writer/evaluator/review 节点逻辑
- `agent/workflows/deepsearch_optimized.py` 同时承担 legacy deep runtime 细节与 engine 选择
- `agent/workflows/deepsearch_multi_agent.py` 同时承担 artifact schema、task queue、runtime loop、worker dispatch、event emit
- `agent/core/state.py` 持续吸纳所有模式的共享与私有运行时字段

同时，代码里已经出现边界失真信号：

- `agent/core/__init__.py` 和 `agent/workflows/__init__.py` 都通过 lazy import 避免循环依赖
- `agent/core/context.py` 与 `agent/core/context_manager.py` 同时定义 `ContextManager`
- `agent/core/search_cache.py` 与 `agent/workflows/search_cache.py` 同时定义 `SearchCache`
- `main.py`、`common/session_manager.py`、`tools/*` 仍直接依赖 `agent.workflows.*` 或 `agent.core.*` 内部细节

这次变更是一次包内架构重组，不改变现有对外 API 语义，也不把 `agent/` 拆成多个顶层工程。目标是在保持交付节奏的前提下，把模块边界从“约定”收敛成“结构 + 依赖方向 + 稳定入口”的组合约束。

## Goals / Non-Goals

**Goals:**

- 在 `agent/` 单包内明确模块边界，降低 orchestration、deep runtime、共享契约之间的交叉耦合
- 把超大文件拆成职责明确的子模块，同时保持现有 graph 入口和运行语义稳定
- 为 deep research legacy runtime 与 multi-agent runtime 建立清晰的组合点和共享契约
- 统一重复命名与重复基础设施概念，减少维护歧义
- 收敛外部调用方对 `agent` 内部实现文件的直接依赖，保留稳定 facade

**Non-Goals:**

- 不把 `agent/` 立即拆成独立仓库、微服务或插件市场式架构
- 不改变 `direct / web / agent / deep` 的对外模式语义
- 不在本变更中引入新的模型供应商、搜索源或前端功能
- 不要求一次性重写全部 Deep Research 实现；允许按 runtime 和节点边界逐步迁移

## Decisions

### 1. 保持 `agent/` 作为单一顶层包，优先做包内模块化重组

`agent/` 继续作为统一对外能力包存在，`agent/__init__.py` 与 `agent/api.py` 保持 facade 角色。重组主要发生在包内子目录与依赖规则上，而不是拆出新的顶层工程。

这样做的原因：

- 当前复杂度集中在内部模块，而不是发布/部署边界
- 先做包内边界收敛，能以更低成本验证职责划分是否正确
- 避免在问题尚未收敛前引入新的包管理、发布和版本兼容成本

备选方案：

- 方案 A：把 runtime、events、prompts、tools contract 直接拆成多个顶层包
  - 未选原因：现在的主要问题是内部职责混杂，不是发布单元过大
- 方案 B：保持现状，仅按文件长度做机械拆分
  - 未选原因：如果不先定义边界和依赖方向，拆完仍会重新耦合

### 2. 把 orchestration、runtime、shared contracts 分成三个明确层次

本次重组采用以下职责切分：

- facade / composition：`agent/__init__.py`、`agent/api.py`、`agent/core/graph.py`
- runtime orchestration：graph nodes、deep runtime selector、legacy runtime、multi-agent runtime
- shared contracts：事件类型、worker context、artifact/task schema、source registry、必要的 cache 接口

其中 shared contracts 必须是被 runtime 与外围依赖共同消费的稳定点，不能继续挂靠在某个具体 workflow 实现文件下。

这样做的原因：

- 共享契约从实现文件中抽离后，`tools/*` 与 `common/*` 不再需要反向依赖 workflow internals
- orchestration 层只负责编排，不直接拥有所有数据结构

备选方案：

- 继续让 `tools/*` 直接依赖 `agent.workflows.source_registry`、`agent.core.events` 等内部位置
  - 未选原因：这会把内部目录结构固化成对外契约，阻碍后续重组

### 3. deep runtime 选择器与具体 runtime 实现分离

`deepsearch_node` 继续作为 graph 入口，但 runtime 选择逻辑必须独立于 legacy runtime 细节。legacy tree/linear runtime 与 multi-agent runtime 分别位于独立模块，选择器只负责解析配置并委托执行。

这样做的原因：

- 将“选择哪个 runtime”和“runtime 如何执行”分开，符合单一职责
- 可以在不污染 legacy 实现的前提下继续演进 multi-agent runtime

备选方案：

- 继续把 `run_deepsearch_auto()` 作为“选择器 + legacy 实现 + multi-agent 分发”的混合入口
  - 未选原因：这会继续放大 `deepsearch_optimized.py` 的职责范围

### 4. multi-agent runtime 内部按 schema、store、dispatcher、loop、events 再次拆分

`deepsearch_multi_agent.py` 不再作为单文件容器，至少应拆成：

- schema / artifact definitions
- task queue / artifact store
- worker context helpers
- coordinator loop / dispatcher
- event emit helpers
- public runtime entrypoint

这样做的原因：

- 这些部件变化频率和测试粒度不同
- schema、store 与 event helper 不应跟 coordinator loop 强绑定在一个文件里

备选方案：

- 只保留一个 `MultiAgentDeepSearchRuntime` 类，把内部继续私有方法化
  - 未选原因：类内私有方法不能替代模块边界，测试与复用仍然困难

### 5. 重命名重复概念，并为共享状态建立嵌套边界

`ContextManager`、`SearchCache` 这类重复命名必须收敛：

- token/window 相关管理器改为上下文窗口语义名称
- worker/sub-agent 上下文相关管理器改为 worker context 语义名称
- 搜索缓存保留单一权威实现；如果存在轻量封装，应明确标记为 adapter，而不是第二个同名核心类型

同时，`AgentState` 中 deep runtime 私有字段应收敛到嵌套运行时块，而不是继续平铺增加顶层字段。

这样做的原因：

- 语义明确比单纯文件拆分更重要
- 大型 TypedDict 平铺字段会让所有节点天然耦合到所有模式

备选方案：

- 维持现有名字不变，只在注释中解释差异
  - 未选原因：注释无法替代命名本身的约束效果

### 6. 外围调用方默认走 facade 或共享契约，而不是 workflow internals

`main.py`、`common/*`、`tools/*` 访问 agent 能力时遵循两条规则：

- 对“能力调用”走 `agent` facade 或公开构建入口
- 对“共享数据/事件契约”走专门公开的 shared contracts 模块

外围模块不得继续直接依赖 `agent.workflows.nodes`、`agent.workflows.deepsearch_*` 这类实现位置，除非该模块被显式声明为公开契约。

这样做的原因：

- 外围直接 import 内部实现，会把内部目录结构变成兼容性负担
- 有利于后续在包内迁移文件而不影响 API 层和工具层

备选方案：

- 继续允许外围按需导入内部模块，只要“目前能跑”
  - 未选原因：这正是当前边界持续失真的来源

## Risks / Trade-offs

- [迁移期间会出现临时适配层] → 通过 facade 和兼容 re-export 控制迁移窗口，避免一次性断裂
- [模块变多后查找成本上升] → 通过明确命名、目录职责和公开入口降低认知负担
- [重组可能打破隐式 import 链] → 通过先建立共享契约和 facade，再迁移外围调用方降低风险
- [`AgentState` 收敛过快可能影响现有节点] → 先引入嵌套运行时块并保留过渡读取逻辑，再逐步删除旧字段
- [legacy 与 multi-agent runtime 的共享代码抽离不当] → 仅抽离真正共享的契约和 helper，避免为了复用而制造抽象污染

## Migration Plan

1. 先建立新的目录边界与公开入口，增加必要的兼容 re-export，保证现有调用方仍可运行
2. 拆分 `nodes.py`，优先抽出 deepsearch、planning/review、answer/agent 等节点族
3. 拆分 legacy deep runtime，把 runtime 选择逻辑从 legacy 实现中抽离
4. 拆分 multi-agent runtime，把 schema、store、dispatcher、loop、events 分离
5. 统一 `ContextManager`、`SearchCache` 等重复概念，并迁移调用方到单一权威实现
6. 收敛 `AgentState` 的 runtime 私有字段，迁移外围模块从内部实现导入到 facade/shared contracts
7. 删除过渡兼容层，补齐模块边界与依赖方向的回归测试

## Open Questions

- shared contracts 最终放在 `agent/core/*` 还是单独的 `agent/contracts/*`，哪种对现有 import 迁移成本更低？
- `source_registry` 是否应升级为跨 runtime 共享契约，还是只作为 deep research 共享基础设施？
- `AgentState` 的嵌套运行时块是使用单一 `deep_runtime` dict，还是按 `legacy` / `multi_agent` 继续分隔更合适？
