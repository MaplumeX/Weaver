# Optimize search tool

## Goal

重写并优化仓库中的搜索工具体系，降低当前搜索链路的重复实现和行为分叉，提升稳定性、可观测性与可扩展性，并明确 Deep Research 与普通 agent 模式对搜索能力的复用边界。

## What I already know

* 当前搜索实现分散在 `tools/search/multi_search.py`、`tools/search/search.py`、`tools/search/fallback_search.py`。
* Deep Research 当前主链路通过 `agent/runtime/deep/support/runtime_support.py` 的 `_search_query()` 调 `multi_search()`，失败时回退到 `tavily_search`。
* 普通 agent / sandbox / browser 相关路径仍会直接使用 `fallback_search`、`tavily_search`、`browser_search` 等不同入口。
* `multi_search` 已经内置 provider 编排、缓存、健康状态、去重和 ranking。
* `fallback_search` 仍保留一套独立的多引擎顺序回退逻辑，和 `multi_search` 存在职责重叠。
* `main.py` 暴露了 `/api/search/providers` 等 provider 观测接口，说明搜索 provider 状态已经被视为公共运行时能力。

## Assumptions (temporary)

* 本任务优先处理后端搜索运行时，不涉及前端展示重做。
* 目标不是简单调参，而是梳理并收敛搜索工具的职责与调用入口。
* 需要尽量复用现有 provider、缓存、指标和测试资产，避免推倒重来。
* 已确认采用 A2：统一到新的单一搜索入口，并清理不再需要的旧入口和死代码。

## Open Questions

* 是否接受对公开工具名和配置语义做 breaking change，例如移除 `fallback_search` / `tavily_search` 这类旧工具入口，并同步调整 `data/agents.json`、tool catalog 与相关测试？
* 统一后的唯一公开 API 搜索工具名应该是什么？

## Requirements (evolving)

* 明确搜索能力的单一主入口，减少平行实现。
* 保留或增强现有 provider fallback、缓存、可靠性与可观测性能力。
* 降低 Deep Research、agent、sandbox 等路径的接入分叉。
* 保持外部接口和现有测试基线可迁移。
* 以 `multi_search` 作为统一搜索内核，避免继续维护独立的多引擎回退实现。
* 清理不再使用的搜索入口、冗余配置分支和失效测试资产。

## Acceptance Criteria (evolving)

* [ ] 搜索工具职责边界清晰，不再存在难以解释的重复入口。
* [ ] 至少一条主要搜索链路完成收敛或重写，并有回归测试覆盖。
* [ ] Deep Research 与普通 agent 的搜索接入关系能用代码结构直接说明。
* [ ] provider fallback / ranking / cache 行为有明确归属。

## Definition of Done (team quality bar)

* Tests added/updated (unit/integration where appropriate)
* Lint / typecheck / CI green
* Docs/notes updated if behavior changes
* Rollout/rollback considered if risky

## Out of Scope (explicit)

* 前端搜索 UI 改版
* 新增外部搜索供应商
* 无明确收益的全面架构翻新

## Technical Notes

* 任务目录：`.trellis/tasks/04-08-optimize-search-tool/`
* 已定位核心文件：
* `tools/search/multi_search.py`
* `tools/search/search.py`
* `tools/search/fallback_search.py`
* `agent/runtime/deep/support/runtime_support.py`
* `main.py` 中搜索 provider 观测接口
* 主要调用方：
* `tools/__init__.py` 目前对外导出的是 `fallback_search` 和 `tavily_search`
* `agent/runtime/nodes/_shared.py` 的 fast-agent 路径仍直接在 `fallback_search` 和 `tavily_search` 之间分支
* Deep Research 在 `agent/runtime/deep/support/runtime_support.py` 中直接调用 `multi_search`，失败后回退到 `tavily_search`
* 当前测试面：
* `tests/test_deepsearch_multi_search.py` 约束 Deep Research 优先 `multi_search`，失败时回退 `tavily_search`
* `tests/test_fallback_search.py` 约束 `fallback_search` 的 alias / 顺序回退 / 错误继续执行语义
* `tests/test_multi_search_profiles.py` 约束 `multi_search` 的 provider profile 行为
* 初步判断：
* `multi_search` 已经是最接近“统一内核”的实现，具备 provider 编排、cache、health、ranking
* `fallback_search` 更像历史兼容入口，职责和 `multi_search` 高度重叠
* 若选 A，最合理的方向是保留旧工具名作为薄兼容层，但把底层执行统一到 `multi_search`

## Research Notes

### 当前仓库里的搜索入口

* `multi_search`：多 provider 编排内核，包含 provider profile、缓存、可靠性状态、去重和排序
* `fallback_search`：另一套按引擎顺序回退的 API 搜索入口
* `tavily_search`：单 provider 工具，同时也被 `fallback_search` 和 `multi_search` 间接复用

### A 方案下的可执行收敛路径

**方案 A1：兼容优先收敛**（Recommended）

* 保留 `fallback_search` / `tavily_search` 这些公开工具名
* 底层统一转到一个新的 `multi_search` 适配入口
* 先不删旧接口，只把旧逻辑改成薄包装
* 优点：
* 风险最低，改动面清晰
* 现有 agent / deep research / sandbox / tests 容易渐进迁移
* 缺点：
* 会保留少量历史命名包袱

**方案 A2：收缩入口优先**

* 直接把旧入口下沉为内部实现甚至废弃
* 上层调用方统一改到新的单一搜索服务
* 优点：
* 结构更干净
* 后续维护成本更低
* 缺点：
* 一次性改动面更大
* 对工具目录、agent profile、测试和兼容层影响更大

### 当前已确认方向

* 采用 **A2：收缩入口优先**
* 用户额外要求：**清除不用的代码**
* 用户已确认：**允许 breaking change**

### 公开搜索入口命名候选

**候选 1：`web_search`**（Recommended）

* 优点：
* 贴合用户语义，而不是暴露 `multi_search` 这类实现细节
* 仓库现有 tool provider key 已经叫 `web_search`
* 后续底层即使继续换 provider / ranking / cache 实现，也不需要再改公开契约
* 缺点：
* 需要同步清理历史文档里对 `web_search` 作为“能力”或“旧术语”的混用

**候选 2：`multi_search`**

* 优点：
* 和当前统一内核同名，开发期理解成本低
* 缺点：
* 把内部实现细节暴露成公共工具契约
* 未来如果底层不再是当前 `MultiSearchOrchestrator`，名字会误导

**候选 3：`search_web`**

* 优点：
* 动宾结构直观
* 缺点：
* 与现有 `browser_search` / `sandbox_web_search` 命名体系不够一致
* 仓库内部没有既有语义锚点，迁移收益低
* 已知风险：
* `multi_search` 与 `fallback_search` 均承担“多引擎回退”语义，可能造成 DRY 破坏和行为漂移。
* Deep Research、sandbox、普通 agent 可能各自依赖不同返回格式或事件语义，重写前需要先盘清调用方。
