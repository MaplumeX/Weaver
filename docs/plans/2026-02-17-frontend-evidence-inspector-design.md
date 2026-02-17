# Frontend Evidence Inspector (Passages Grouping) — Design

**Date:** 2026-02-17  
**Owner:** Codex + Luke  

## Goal
把后端 evidence-first 的 artifacts（`/api/sessions/{thread_id}/evidence`）在前端提供一个“可读、可扫描、可定位”的 Inspector 视图：

- Passages 按 `heading_path` 分组折叠（并保留“未分组”兜底）。
- 使用 `snippet_hash` 作为稳定 key，并在 **同一 URL 内** 做去重展示。
- 提供轻量的“刷新/复制 quote/打开来源”操作，便于引用与核查。

## Non-goals
- 不做复杂的全文定位（高亮/滚动到原网页具体位置）。
- 不改变聊天消息渲染逻辑（sources/citations 仍按现有 MessageSource 走）。
- 不把 evidence 持久化到本地历史（当前历史不保存 thread_id）。

## UX Placement
- 在 Chat 右侧面板（现有 Artifacts 面板）新增一个 Evidence tab，统一为 **Inspector**：
  - Tab 1: Artifacts（原有功能不变）
  - Tab 2: Evidence（新）
- Mobile 使用现有 overlay 入口（同一个按钮），overlay 内同样提供 tab。

## Data Flow
- 触发条件：有 `threadId` 时可加载 evidence。
- 读取：`GET /api/sessions/{threadId}/evidence`
- 结构：
  - `fetched_pages[]`（用于页面级 meta）
  - `passages[]`（用于展示与引用）
- 组装策略：
  - page group key = `url`
  - heading group key = `heading_path.join(" / ")`（缺失则 `heading`，再缺失则 `Ungrouped`）
  - passage key = `${url}::${snippet_hash || start_end}`
  - passage preview = `quote`（缺失则用 `text` 规范化截断）

## Success Criteria
- Evidence tab 在 deepsearch session 可用，且展示结构清晰。
- 不破坏现有 Artifacts UI。
- `pnpm -C web lint` 与 `pnpm -C web build` 通过。

