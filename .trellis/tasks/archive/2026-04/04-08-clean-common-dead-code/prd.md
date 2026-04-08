# Clean Common Dead Code

## Goal
清理 `common/` 目录中已经没有实际调用路径的死代码和本地运行残留，降低维护成本，避免后续误判这些模块仍然有效。

## Requirements
- 删除确认无引用的整文件死代码。
- 删除 `common/` 下的本地运行缓存和残留目录。
- 精简仍保留模块中确认无调用的辅助符号，但不改动仍在业务路径上的实现。
- 保持现有业务行为不变。

## Acceptance Criteria
- [ ] `common/agent_runs.py` 从仓库中删除。
- [ ] `common/logger.py` 和 `common/concurrency.py` 中确认无调用的辅助符号被移除。
- [ ] `common/__init__.py` 不再导出已删除符号。
- [ ] `common/__pycache__/` 和 `common/preferences/` 被清理。
- [ ] 相关 lint 和目标测试通过。

## Technical Notes
- 本次清理基于全仓库静态引用检索，只处理高置信度无用项。
- 不处理仍有业务入口的 `metrics.py`、`session_service.py`、`session_store.py`、`tracing.py` 等模块。
