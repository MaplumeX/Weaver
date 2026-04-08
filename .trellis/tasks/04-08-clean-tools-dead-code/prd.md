# Clean Tools Dead Code

## Goal
清理 `tools/` 目录中确认无调用路径的死代码，并收紧冗余的包级导出面，降低维护成本和误用风险。

## Requirements
- 删除确认无仓库内引用的整文件死代码。
- 移除保留模块中确认无调用的辅助符号和冗余导出。
- 将低置信度但仍需保留的包级 `__init__.py` 从通配导出改为显式 facade。
- 清除已下线的 RAG 工具、文档接口和相关配置残留。
- 保持现有工具注册、运行时行为和公开工具名不变。

## Acceptance Criteria
- [ ] `tools/browser/content_extractor.py`、`tools/browser/cdp_screencast.py`、`tools/core/collection.py` 从仓库中删除。
- [ ] `tools/crawl/crawler.py` 中未使用的全局单例辅助逻辑被移除。
- [ ] `tools/__init__.py` 不再导出仓库内无使用的 `crawl_url` / `crawl_urls`。
- [ ] `tools/automation/__init__.py`、`tools/browser/__init__.py`、`tools/code/__init__.py`、`tools/crawl/__init__.py`、`tools/io/__init__.py`、`tools/planning/__init__.py` 改为显式导出。
- [ ] `tools/rag/`、`/api/documents/*`、相关配置与测试从仓库中移除。
- [ ] 相关目标测试通过。

## Technical Notes
- 本次清理基于全仓库静态引用检索，只处理高置信度死代码和低风险的 facade 收紧。
- 不调整 `agent/infrastructure/tools/capabilities.py` 中已注册的工具能力和公开工具名。
- 对于已有显式 facade 的 `tools/rag`、`tools/research`、`tools/search` 及其子包，不做行为性删减。
