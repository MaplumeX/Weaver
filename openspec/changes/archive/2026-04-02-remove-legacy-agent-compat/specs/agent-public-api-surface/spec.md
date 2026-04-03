## ADDED Requirements

### Requirement: Deprecated Deep Research facade exports are removed
系统 MUST 将 `agent/__init__.py` 与 `agent/api.py` 上的 Deep Research 公开入口收敛到当前 canonical surface，而 MUST NOT 继续暴露 `run_deepsearch`、`run_deepsearch_auto` 或其他 deepsearch 时代的兼容导出。

#### Scenario: External module imports a Deep Research runtime entrypoint
- **WHEN** 外围模块需要通过 `agent` facade 调用 Deep Research 运行时能力
- **THEN** 系统 MUST 只暴露 canonical Deep Research entrypoint
- **THEN** 外围模块 MUST NOT 再通过 facade 导入 `run_deepsearch`、`run_deepsearch_auto` 或其他已退役别名

#### Scenario: Internal tests or examples patch Deep Research logic
- **WHEN** tests、examples 或内部模块需要 monkeypatch Deep Research 运行时
- **THEN** 它们 MUST 指向当前 owning module 或 canonical public entrypoint
- **THEN** 系统 MUST NOT 为保留历史 patch 点继续扩展 facade re-export
