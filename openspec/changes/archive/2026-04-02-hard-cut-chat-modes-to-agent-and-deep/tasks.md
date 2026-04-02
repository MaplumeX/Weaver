## 1. 前端模式面收口

- [x] 1.1 将主聊天页、命令菜单、空状态入口和模式标签统一收敛到 `agent`/`deep` 两种规范模式，并将默认模式改为 `agent`
- [x] 1.2 删除前端中的 `direct`、`web`、`mcp`、`ultra` 历史模式值与别名翻译，统一会话保存、恢复和高亮逻辑使用规范模式值
- [x] 1.3 更新前端会话恢复与历史迁移逻辑，将旧会话中的 `direct`/`web`/`mcp`/空模式迁移为 `agent`，并同步清理相关 i18n 文案与测试

## 2. 后端契约与运行时删码

- [x] 2.1 收敛 `search_mode` 请求契约与 OpenAPI 到只支持 `agent`/`deep` 的显式对象输入，并对已删除模式或历史字段返回明确校验错误
- [x] 2.2 更新会话状态恢复、运行指标和模式归一化逻辑，只再产生 `agent`/`deep` 公开模式，并将历史 `direct`/`web`/`mcp` 状态迁移到 `agent`
- [x] 2.3 调整 Smart Router 与 LangGraph 主图，只保留 `agent`、`deepsearch` 和内部 `clarify` 路径，删除 `direct_answer`、`web_plan` 及其路由分支
- [x] 2.4 删除 `direct_answer_node`、`web_search_plan_node` 及其导出；将仍被 `agent`/`deep` 复用的逻辑迁移到共享或正确 owning module，并把 deep 简单请求降级改为 `agent_node`

## 3. 验证、类型与文档同步

- [x] 3.1 更新后端与前端模式相关测试，覆盖默认 `agent`、旧会话迁移、旧 API 输入拒绝、deep 简单请求降级到 `agent` 以及删除旧 patch 点后的新断言
- [x] 3.2 重新生成并提交 OpenAPI 派生类型，确保 `web/lib/api-types.ts` 与 `sdk/typescript/src/openapi-types.ts` 反映新的模式契约
- [x] 3.3 更新 README、usage、architecture 与其他模式说明文档，删除 `direct`/`web`/独立 `mcp` 模式描述并说明默认 `agent`、显式 `deep` 的新行为
