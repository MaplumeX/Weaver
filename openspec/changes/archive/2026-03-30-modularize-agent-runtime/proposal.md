## Why

当前 `agent/` 包虽然已经表面分成 `core`、`prompts`、`workflows`、`parsers`，但关键复杂度仍集中在少数超大模块中，尤其是 `agent/workflows/nodes.py`、`agent/workflows/deepsearch_optimized.py` 和 `agent/workflows/deepsearch_multi_agent.py`。随着 deep research、multi-agent runtime、事件流和工具集成持续演进，现有结构已经开始依赖懒加载和跨层导入来维持运行，降低了可维护性、可测试性和后续重构速度。

这个问题现在需要处理，因为多智能体 runtime 已经引入了新的任务、artifact、事件和上下文隔离模型；如果继续沿用当前文件与依赖组织方式，复杂度会继续叠加到同一批中心模块上，导致边界进一步失真。

## What Changes

- 为 `agent/` 包建立显式模块边界，明确 facade、graph 装配、节点编排、deep runtime、prompt、parser、共享契约各自职责，并限制跨层依赖方向。
- 将当前过大的 orchestration 模块拆分为更小的职责单元，至少覆盖 graph nodes、legacy deep runtime、multi-agent deep runtime、共享 artifact/task/event contract。
- 统一重复概念与命名，消除多个 `ContextManager`、多个 `SearchCache` 这类语义冲突，避免维护者误判模块职责。
- 收敛 `AgentState` 与 deep runtime 运行时状态的边界，减少所有模式共享一个“状态袋”带来的耦合。
- 约束 `main.py`、`common/*`、`tools/*` 对 `agent` 内部实现的直接依赖，优先通过稳定 facade 或共享契约访问 agent 能力。

## Capabilities

### New Capabilities

- `agent-module-boundaries`: 定义 `agent/` 包内部各模块的职责边界、目录归属与允许的依赖方向。
- `deep-runtime-modularization`: 定义 deep research legacy runtime 与 multi-agent runtime 的拆分方式、组合点与共享契约。
- `agent-public-api-surface`: 定义 `agent` 对外稳定 API、内部实现模块与外部调用方之间的访问规则。

### Modified Capabilities

- 无

## Impact

- 主要影响目录：`agent/core/*`、`agent/prompts/*`、`agent/workflows/*`、`agent/api.py`、`agent/__init__.py`
- 重点影响文件：`agent/workflows/nodes.py`、`agent/workflows/deepsearch_optimized.py`、`agent/workflows/deepsearch_multi_agent.py`、`agent/core/state.py`、`agent/core/context.py`、`agent/core/context_manager.py`
- 影响外围依赖方：`main.py`、`common/session_manager.py`、`tools/core/wrappers.py`、`tools/research/content_fetcher.py`、`tools/search/multi_search.py`
- 不预期改变现有外部 API 请求格式或 Deep Research 的功能语义；重点是降低内部耦合、改善模块可测试性和演进成本
