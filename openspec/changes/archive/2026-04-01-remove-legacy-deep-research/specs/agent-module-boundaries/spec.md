## ADDED Requirements

### Requirement: Deep Research compatibility layers are removed from workflow internals
系统 MUST 不再在 `agent.workflows.*` 中保留 Deep Research runtime 的兼容实现、镜像入口或共享 helper 宿主；相关职责 MUST 收敛到 runtime、shared contracts 和公开 facade 的明确边界内。

#### Scenario: Reused deep research helper still exists in a legacy workflow module
- **WHEN** 某个仍被当前功能使用的 Deep Research helper 仍定义在 `agent.workflows.deepsearch_*` 中
- **THEN** 系统 MUST 将该 helper 迁移到显式 shared/runtime 模块
- **THEN** 删除 legacy workflow 模块后，剩余调用方 MUST 不再依赖旧路径

#### Scenario: Assigning ownership after cleanup
- **WHEN** 系统重新梳理 Deep Research 相关目录职责
- **THEN** `agent.runtime.deep.*` MUST 持有 runtime orchestration 与内部状态实现
- **THEN** `agent.workflows.*` MUST NOT 继续承载隐藏的 Deep Research 入口或长期兼容层
