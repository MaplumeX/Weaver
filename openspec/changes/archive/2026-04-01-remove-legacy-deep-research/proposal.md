## Why

当前 Deep Research 已经有完整的 `multi_agent` graph/runtime，但仓库仍同时维护 `legacy` runtime、selector 分支、`agent.workflows.deepsearch_*` 兼容入口、旧 artifacts 形态和旧前端事件语义。双轨实现持续放大模块耦合、公共 API 泄漏和测试负担，也让后续只围绕当前 multi-agent 演进变得困难。

## What Changes

- **BREAKING** 移除 Deep Research 的 `legacy` runtime、engine 选择分支和依赖它们的旧流程代码，`deep` 模式只保留 `multi_agent` runtime。
- 将 session/export/API 面向外部暴露的 Deep Research artifacts 改为由 `multi_agent` artifact store 直接产出，迁移仍有复用价值的字段，删除 legacy 兼容拼装逻辑。
- 移除 `agent.workflows.deepsearch_*` 及相关 compat facade，把外围依赖迁移到显式公开的 facade/shared contracts。
- 统一流式事件和前端阶段语义，收敛到当前 runtime 实际使用的 `supervisor`/`researcher`/`verifier`/`reporter` 角色，删除 `planner`/`coordinator` 等旧映射。
- 清理 legacy-only 配置项，并重命名仍由 `multi_agent` 使用但带有旧 tree/legacy 命名含义的配置。

## Capabilities

### New Capabilities
- None.

### Modified Capabilities
- `deep-research-orchestration`: 将 Deep Research 编排从双引擎选择改为 `multi_agent` 唯一运行时，并禁止失败时回退到 legacy。
- `deep-research-artifacts`: 将对外 artifacts 契约收敛到 `multi_agent` artifact store 的权威结构，并保留 API/UI 仍需要的公开字段。
- `deep-research-agent-events`: 将事件语义统一到 `supervisor` 驱动的当前多 agent 角色与阶段，不再暴露旧 planner/coordinator 语义。
- `deep-runtime-modularization`: 删除 legacy runtime 拆分要求，收敛为单一 deep runtime 及其内部模块边界。
- `agent-module-boundaries`: 移除 `agent.workflows.*` 中旧 deep research 兼容分层，明确 runtime、facade 与 shared contracts 的职责归属。
- `agent-public-api-surface`: 禁止外围模块继续依赖旧 deepsearch workflow internals，要求迁移到稳定公开入口。

## Impact

- 受影响代码主要包括 `agent/runtime/deep/*`、`agent/runtime/nodes/*`、`agent/workflows/*` 的 deep research 兼容层、`common/session_manager.py`、`common/config.py`、前端 Deep Research 流式渲染和相关测试。
- 对外影响包括 Deep Research 配置项、内部导入路径、事件角色语义和 artifacts 结构的兼容性收口，依赖 legacy engine 或旧兼容模块的调用方需要迁移。
