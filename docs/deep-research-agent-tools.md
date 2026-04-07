# Deep Research Agent 工具分析

## 结论

当前仓库里，Deep Research 的“agent 有什么工具”要分成两层看：

1. **运行时真实执行层**
   `MultiAgentDeepResearchRuntime` 直接实例化的是 `DeepResearchClarifyAgent`、`DeepResearchScopeAgent`、`ResearchSupervisor`、`ResearchAgent`、`ResearchReporter` 等角色类，而**没有**在 runtime 中直接调用 `build_deep_research_tool_agent()`。
2. **基础设施白名单层**
   `agent/infrastructure/agents/factory.py` 的确为 Deep Research 角色定义了工具白名单，但这更像“可供角色型 tool-agent 使用的预留能力”，**不等于当前 multi-agent runtime 中每个角色都真的在走这些 LangChain tools**。
3. **`fabric` 的真实含义**
   `fabric` 不在本地 `tools/` 静态实现里；它来自 `tools/mcp.py` 暴露的 **live MCP tools**。只有外部 MCP server 注入了同名工具，它才会真正进入 inventory。

## 运行时实际角色与能力

| 角色 | 分类 | 当前是否直接使用 LangChain Tool | 实际能力来源 | 作用 | 代码依据 |
| --- | --- | --- | --- | --- | --- |
| `clarify` | 控制面 | 否 | `DeepResearchClarifyAgent` + LLM prompt | 归一化用户输入，判断是否需要继续追问，产出 `clarification_state` | `agent/runtime/deep/roles/clarify.py`、`agent/runtime/deep/orchestration/graph.py:2038-2098` |
| `scope` | 控制面 | 否 | `DeepResearchScopeAgent` + LLM prompt | 基于 topic、clarify transcript 和 feedback 生成/修订 scope draft | `agent/runtime/deep/roles/scope.py`、`agent/runtime/deep/orchestration/graph.py:2106-2145` |
| `supervisor` | 控制面 | 否 | `ResearchSupervisor`，内部复用 `ResearchPlanner` | 生成 outline、把 section 变成 task、决定继续 dispatch 还是进入 report/stop | `agent/runtime/deep/roles/supervisor.py`、`agent/runtime/deep/roles/planner.py`、`agent/runtime/deep/orchestration/graph.py:2236-2297`、`2779-2820` |
| `researcher` | 执行面 | **不是 tool-agent**，但会调用内部检索/抓取能力 | `_search_with_tracking()` -> `support._search_query()` -> `multi_search` / `tavily_search` 回退；`ContentFetcher`；passage 抽取与证据综合 | 执行搜索、抓正文、抽 passage、合成 section draft 和 evidence bundle | `agent/runtime/deep/roles/researcher.py:113-218`、`agent/runtime/deep/orchestration/graph.py:544-573`、`2350-2418`、`tools/research/content_fetcher.py` |
| `revisor` | 执行面内部阶段 | 否 | graph 内部逻辑 | 对已有 section draft 做“保留已落地 claim + 补限制说明”的修订，不额外发起搜索 | `agent/runtime/deep/orchestration/graph.py:2435-2526` |
| `reviewer` | 执行面内部阶段 | 否 | graph 内部规则审查 | 审核章节是否满足 objective、grounding、sources、freshness，决定 accept / revise / request_research | `agent/runtime/deep/orchestration/graph.py:2642-2774` |
| `reporter` | 执行面 | 否 | `ResearchReporter` | 汇总已认证 section，生成最终报告、归一化引用、生成 executive summary | `agent/runtime/deep/roles/reporter.py:421-506`、`agent/runtime/deep/orchestration/graph.py:2839-2914` |
| `verifier` | 执行面 | 否 | `ClaimVerifier` | 对最终报告做 deterministic claim gate，判定 `verified` / `unsupported` / `contradicted` | `agent/contracts/claim_verifier.py:135-196`、`agent/runtime/deep/orchestration/graph.py:2916-2961` |

## 基础设施层角色工具白名单

下面这张表描述的是 `agent/infrastructure/agents/factory.py` 中定义的 **role -> tool allowlist**，不是当前 runtime 的实际 tool 调用情况。

| 角色 | 白名单工具 | 预期用途 | 备注 |
| --- | --- | --- | --- |
| `clarify` | `fabric` | 预留给控制面做外部 MCP 辅助能力 | 当前 runtime 未接入 tool-agent |
| `scope` | `fabric` | 预留给 scope 阶段使用外部 MCP 辅助能力 | 当前 runtime 未接入 tool-agent |
| `supervisor` | `fabric` | 预留给 supervisor 的控制面能力 | 默认只有 `fabric`；若 `deep_research_supervisor_allow_world_tools=true`，还能扩展到搜索/浏览/抓取工具 |
| `researcher` | `fabric`、`browser_search`、`tavily_search`、`fallback_search`、`sandbox_web_search`、`sandbox_search_and_click`、`sandbox_extract_search_results`、`browser_navigate`、`browser_click`、`crawl_url`、`crawl_urls`、`sb_browser_navigate`、`sb_browser_click`、`sb_browser_type`、`sb_browser_press`、`sb_browser_scroll`、`sb_browser_extract_text`、`sb_browser_screenshot` | 为检索型 researcher 预留搜索、阅读、提取、浏览、截图能力 | 当前 multi-agent runtime 的 researcher 实际走的是内部搜索/抓取流水线，不是 `build_deep_research_tool_agent()` |
| `verifier` | 与 `researcher` 相同 | 预留给 verifier 进行补充检索、核验、阅读证据 | 当前 final claim gate 实际走 `ClaimVerifier`，不是 tool-agent |
| `reporter` | `fabric`、`execute_python_code` | 预留给 reporter 做外部 MCP 调用和 Python 计算/可视化 | `deep_research_reporter_enable_python_tools=false` 时会移除 `execute_python_code`；当前 runtime reporter 也未接入该 tool-agent |
| `reviewer` | 无专门白名单 | 无 | `factory.py` 没有 reviewer 的角色工具配置 |
| `revisor` | 无专门白名单 | 无 | `factory.py` 没有 revisor 的角色工具配置 |

> 额外说明：仓库内搜索 `build_deep_research_tool_agent(`，命中只有 `agent/infrastructure/agents/factory.py` 自身和测试文件，说明当前 multi-agent Deep Research runtime 并未直接消费这套角色工具代理。

## 工具作用速查表

| 工具名 | 作用 | 主要实现 |
| --- | --- | --- |
| `fabric` | 动态 MCP 工具名。本仓库没有静态实现；具体能力取决于外接 MCP server 注入了什么同名工具 | `tools/mcp.py` |
| `browser_search` | 在轻量浏览器会话中发起搜索，返回搜索页 URL、标题、链接和文本摘要 | `tools/browser/browser_tools.py` |
| `browser_navigate` | 打开指定 URL，提取页面标题、链接和文本摘要 | `tools/browser/browser_tools.py` |
| `browser_click` | 按当前页面的 1-based 链接索引点击并跳转 | `tools/browser/browser_tools.py` |
| `tavily_search` | 使用 Tavily API 做深搜，返回结果摘要、snippet、raw_excerpt、score | `tools/search/search.py` |
| `fallback_search` | 按配置顺序尝试多个 API 搜索引擎，取第一个成功结果 | `tools/search/fallback_search.py` |
| `sandbox_web_search` | 在 sandbox browser 中做搜索并截图；优先 API 搜索，浏览器流程兜底 | `tools/sandbox/sandbox_web_search_tool.py` |
| `sandbox_search_and_click` | 搜索后直接点击某个结果，并返回搜索页/目标页截图 | `tools/sandbox/sandbox_web_search_tool.py` |
| `sandbox_extract_search_results` | 从当前 sandbox 搜索结果页提取结构化结果 | `tools/sandbox/sandbox_web_search_tool.py` |
| `crawl_url` | 通过 HTTP 抓取单个网页，并返回提取后的纯文本 | `tools/crawl/crawl_tools.py` |
| `crawl_urls` | 批量抓取多个网页，并分别返回提取后的纯文本 | `tools/crawl/crawl_tools.py` |
| `sb_browser_navigate` | 在 sandbox Chromium 中打开 URL，并返回截图与页面信息 | `tools/sandbox/sandbox_browser_tools.py` |
| `sb_browser_click` | 在 sandbox 浏览器里按 selector 或可见文本点击元素 | `tools/sandbox/sandbox_browser_tools.py` |
| `sb_browser_type` | 在 sandbox 浏览器输入文本，可选回车提交 | `tools/sandbox/sandbox_browser_tools.py` |
| `sb_browser_press` | 向 sandbox 浏览器发送键盘快捷键 | `tools/sandbox/sandbox_browser_tools.py` |
| `sb_browser_scroll` | 在 sandbox 浏览器滚动页面 | `tools/sandbox/sandbox_browser_tools.py` |
| `sb_browser_extract_text` | 抽取当前 sandbox 页面可见文本 | `tools/sandbox/sandbox_browser_tools.py` |
| `sb_browser_screenshot` | 对当前 sandbox 页面截图 | `tools/sandbox/sandbox_browser_tools.py` |
| `execute_python_code` | 在 E2B sandbox 中执行 Python，返回 `stdout`、`stderr`、错误和可能的图片输出 | `tools/code/code_executor.py` |

## 关键区别

| 问题 | 结论 |
| --- | --- |
| 当前 Deep Research runtime 里的 agent 是否普遍通过 LangChain tools 工作？ | 否。当前只有 `researcher` 明显使用内部检索/抓取能力；其余多为 LLM 阶段或 graph 内部逻辑。 |
| `factory.py` 里的工具白名单是否等于当前 runtime 的真实执行工具？ | 否。它描述的是“可构造的角色型 tool-agent 能力”，不是当前 multi-agent graph 的实际接线。 |
| `fabric` 是否是仓库自带工具？ | 否。它依赖 MCP 动态注入；若当前会话没有 live MCP tool 叫 `fabric`，它就不会真正出现在 inventory 里。 |
| `planner` 是否是单独的 agent？ | 不是。`ResearchPlanner` 是 `ResearchSupervisor` 的内部 helper，不在 `AgentRole` 里。 |
