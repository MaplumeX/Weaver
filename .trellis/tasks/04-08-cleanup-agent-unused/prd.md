# 清理 agent 模块未使用代码

## Goal

对 `agent/` 模块做一次基于静态依赖和仓库内实际引用的清理，删除当前确认无消费者的遗留代码，降低维护成本和误导性 API 面。

## What I already know

* `agent/core/processor_config.py` 目前在仓库内没有实际消费者，唯一引用来自 `agent/core/__init__.py` 的 lazy export。
* `agent/parsers/` 包及其 `xml_parser.py` 目前在仓库内没有任何导入或运行时入口证据。
* `agent/core/context.py` 中的 `fork_state` / `merge_state` 仅在定义处出现，没有实际调用方。
* `agent` 目录存在 facade / lazy export 结构，删除时需要同时检查 `__all__`、`__getattr__` 映射和回归测试。

## Assumptions (temporary)

* 本次仅清理“仓库内可证明未使用”的代码，不扩展到推测性重构。
* 对外稳定契约以当前测试覆盖和显式 facade 为准；若删除影响公开导出，需要同步更新契约测试。

## Open Questions

* 当前无阻塞问题，按保守范围直接实施。

## Requirements (evolving)

* 先基于仓库静态引用验证未使用候选项，再执行删除。
* 删除时同步修正 `__all__`、lazy export 映射和相关包入口。
* 为删除后的公开面补充或更新回归测试，避免“代码删了但 facade 还暴露”的漂移。

## Acceptance Criteria (evolving)

* [ ] `agent/` 中确认无消费者的目标代码被删除，且不存在悬空导出。
* [ ] 针对 `agent` 公共入口的测试能覆盖这次删除的行为变化。
* [ ] 相关后端测试通过，没有引入导入错误或运行时回归。

## Definition of Done (team quality bar)

* Tests added/updated (unit/integration where appropriate)
* Lint / typecheck / CI green
* Docs/notes updated if behavior changes
* Rollout/rollback considered if risky

## Out of Scope (explicit)

* 不重写仍在使用的 runtime/research 流程。
* 不做大规模架构整理，只处理明确死代码与悬空 facade。

## Technical Notes

* 初步候选：`agent/core/processor_config.py`、`agent/parsers/`、`agent/core/context.py` 中未使用 helper。
* 需要检查的文件：`agent/core/__init__.py`、`tests/test_agent_runtime_public_contracts.py`。
