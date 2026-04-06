# Tool 系统完整标准化设计

## 1. 背景

当前仓库的 tool 系统同时存在两套抽象和两套语义：

- 运行时主路径已经偏向 LangChain/LangGraph 风格，核心是 `BaseTool`、provider 组装、运行时 inventory。
- 作者侧和部分管理侧仍保留 `WeaverTool`、`tool_schema`、`ToolResult`、旧 `ToolRegistry` 等兼容层。
- 外部契约又混入了 `capability`、provider key、具体 tool name 三类不同粒度的名字。

具体表现为：

- `required_capabilities` 会出现 `web_search`、`browser`、`files`、`python` 这类半能力半实现的值。
- `AgentProfile.enabled_tools` 实际控制的是 provider/toolset，而不是具体 tool。
- `/api/tools/registry` 名义上是 registry，实际返回的是运行时 inventory 快照。
- 部分 prompt、测试、前端事件逻辑直接依赖旧命名。

这导致三个根本问题：

1. **标准不唯一**：系统同时维护“自定义工具协议”和“LangChain 标准工具协议”。
2. **命名层级混乱**：能力、实现族、具体工具在不同位置被混用。
3. **真相源不唯一**：旧 registry 和运行时 inventory 并存，语义重叠。

本次设计要求进行 **一次性、内外一致的 breaking 标准化**，目标是把系统收敛到标准 LangChain/LangGraph 风格：**只保留 `tool` 为正式一等公民**。

## 2. 目标

### 2.1 目标

- 删除所有非标准工具协议，只保留 LangChain `tool` 体系。
- 将系统唯一正式抽象收敛为：
  - `@tool`
  - `BaseTool`
  - `StructuredTool`
- 删除正式的 `capability` 与 `toolset` 契约，不再将其作为 API、state、profile、路由的公共语言。
- 将运行时 `list[BaseTool]` 作为唯一真相源。
- 将对外“registry”语义改为“catalog / inventory”语义。
- 将 agent profile 从“启用某类工具”改为“直接声明允许哪些具体工具”。
- 保持具体 tool `name` 尽量稳定，避免无意义重命名。
- 使普通 agent 路径与 deep research 路径都基于同一套 concrete tools 工作。

### 2.2 非目标

- 不重写每个具体 tool 的业务实现逻辑。
- 不要求所有 tool 返回值统一成单一业务数据结构；只要求其符合 LangChain tool contract。
- 不在本次设计中重做前端整体设置页或可视化交互。
- 不引入新的自定义工具框架来替代 `WeaverTool`。
- 不保留旧兼容字段、旧 alias、旧 registry 刷新入口。

## 3. 设计原则

- **与官方一致**：尽量贴近标准 LangChain/LangGraph 用法，不再额外发明工具协议。
- **单一真相源**：系统内部和 API 对外都以运行时 concrete tools 为准。
- **单一命名层级**：公共契约里只说 tool，不再说 capability/toolset。
- **最小惊讶**：尽量保留现有具体 tool 名称，降低事件流、日志、前端展示和调试成本。
- **一次收口**：既然本次接受 breaking，就不保留过渡桥接层和 deprecated 分支。

## 4. 当前问题

### 4.1 双协议并存

当前仓库同时存在：

- LangChain `BaseTool` / `@tool`
- `WeaverTool` / `tool_schema` / `ToolResult`
- 旧 `ToolRegistry`

这使 tool 的定义方式、装配方式、catalog 来源和测试模型都不统一。

### 4.2 capability 与 toolset 被抬成正式契约

`required_capabilities`、`enabled_tools`、`TOOL_SPECS` 当前在系统中承担了超过“内部筛选辅助”的职责，导致：

- router、chat node、profile、API 使用不同命名粒度。
- `web_search` 这类历史术语进入公共接口。
- 运行时逻辑需要维护 alias 映射，例如 `web_search -> search`、`python -> execute`。

### 4.3 registry 语义失真

`/api/tools/registry` 和 `ToolRegistryResponse` 看起来像“静态注册表”，但实际来自运行时 inventory 快照。

这会误导开发者，也会让 catalog、tool discovery、profile 配置之间的职责边界不清晰。

## 5. 目标架构

### 5.1 唯一正式抽象：Tool

标准化后，系统正式承认的工具只有一种：**LangChain tool**。

允许形式仅限：

- `@tool`
- `BaseTool`
- `StructuredTool`

不再存在第二套“自定义工具定义协议”。

### 5.2 唯一真相源：Runtime Inventory

所有运行时和对外展示都来自同一个来源：

- 当前上下文下可用的 `list[BaseTool]`

由此派生：

- tool catalog API
- agent profile 可选工具清单
- deep research 角色允许的工具子集
- 事件、审计和测试中的工具名断言

### 5.3 capability/toolset 降级为实现细节或删除

标准化后：

- `ToolCapability` 删除
- `required_capabilities` 删除
- `ToolSpecification` / `TOOL_SPECS` 删除
- provider key 不再成为正式领域模型或外部字段

如果运行时仍需做工具分组或筛选，只允许使用以下方式：

- 普通 Python 常量
- `tags`
- 运行时函数过滤

这些都只是内部实现细节，不能再出现在外部契约中。

## 6. 模块边界

### 6.1 Tool 定义层

位置：

- `tools/`

职责：

- 定义 concrete tools
- 每个 tool 暴露标准 LangChain contract

约束：

- 不再依赖 `WeaverTool`
- 不再返回 `ToolResult` 作为主协议
- 不再通过自定义 schema decorator 定义输入

### 6.2 Tool 装配层

位置：

- `agent/infrastructure/tools/assembly.py`
- `agent/infrastructure/tools/providers.py`
- `agent/infrastructure/tools/policy.py`

职责：

- 根据运行时上下文构造 concrete tool 列表
- 按 profile 的 allow/block 配置做最终过滤
- 对需要 thread 绑定、事件包装的 tool 做运行时装饰

约束：

- 装配函数直接返回 `list[BaseTool]`
- 不再接受 capability 输入
- 不再接受 toolset key 作为公共参数

### 6.3 Tool 目录层

位置：

- `agent/infrastructure/tools/catalog.py`
- `main.py`

职责：

- 从运行时 concrete tools 派生 catalog
- 提供 catalog API

约束：

- 名称统一为 `catalog`
- 不再使用 `registry` 术语描述运行时 inventory

### 6.4 Profile 与状态层

位置：

- `common/agents_store.py`
- `agent/domain/execution.py`
- `agent/application/state.py`
- `agent/domain/state.py`
- `agent/core/state.py`

职责：

- 保存 agent profile
- 保存本轮允许的具体工具列表

约束：

- profile 不再存 `enabled_tools`
- state 不再存 `required_capabilities`

## 7. 外部契约重定义

### 7.1 AgentProfile

当前：

- `enabled_tools: Dict[str, bool]`
- `mcp_servers`

目标：

- `tools: list[str]`
- `blocked_tools: list[str]`
- `mcp_servers`

说明：

- `tools` 表示该 profile 默认允许暴露给 agent 的 concrete tool names。
- `blocked_tools` 用于在共享基线工具上做减法。
- 不再保留 `enabled_tools`、`tool_whitelist`、`tool_blacklist`。

推荐语义：

- `tools` 是 profile 的主契约。
- `blocked_tools` 只作为少量覆盖使用。
- 如果 `tools` 非空，则视为显式 allowlist。

### 7.2 Chat / Agent Runtime State

删除字段：

- `required_capabilities`

新增或收口字段：

- `selected_tools`
- `needs_tools`
- `tool_reason`

语义：

- `chat_respond` 只决定“是否需要工具”和“需要哪些 concrete tools”。
- `tool_agent` 直接接收工具列表，而不是 capability。

### 7.3 API

重命名：

- `/api/tools/registry` -> `/api/tools/catalog`
- `ToolRegistryResponse` -> `ToolCatalogResponse`
- `ToolRegistryStats` -> `ToolCatalogStats`
- `ToolRegistryTool` -> `ToolCatalogItem`

删除：

- `/api/tools/registry/refresh`

说明：

- 既然系统不再以旧 registry 为真相源，dev-only 的“重新 discovery registry”入口应一起删除。
- 如果未来确实需要重新加载动态工具，应设计为显式的 inventory/catalog reload，而不是 registry refresh。

## 8. 命名规则

### 8.1 保留的命名

保留：

- concrete tool `name`

例如：

- `browser_navigate`
- `browser_search`
- `crawl_url`
- `execute_python_code`
- `sandbox_execute_command`
- `create_tasks`

原因：

- 这些名称已经深入事件流、前端展示、日志、测试断言和工具调用记录。
- 它们是具体工具名，本身没有层级混乱问题。

### 8.2 删除的公共命名

以下名称不应再出现在主路径公共契约中：

- `web_search`
- `python`
- `files`
- `enabled_tools`
- `tool_whitelist`
- `tool_blacklist`
- `required_capabilities`
- `ToolCapability`
- `ToolSpecification`
- `TOOL_SPECS`
- `registry`（用于运行时工具目录语义时）

## 9. 运行时选择策略

### 9.1 普通聊天路径

`chat_respond` 不再产出 capability，而是直接产出本轮应使用的 concrete tools。

策略：

1. 基于用户输入、profile、上下文进行判断。
2. 若无需工具，则直接回答。
3. 若需要工具，则选择最小 concrete tools 子集。
4. `tool_agent` 只拿该子集执行。

这比 capability 路由更直接，也更接近官方“agent 接收具体工具列表”的模式。

### 9.2 Deep Research 路径

deep research 角色不再持有 capability allowlist。

改为：

- 每个角色维护 concrete tool name allowlist，或运行时 tag 过滤规则。

例如：

- `researcher` 可用 `browser_search`、`crawl_url`、`sb_browser_extract_text`
- `reporter` 可用 `execute_python_code`

这些都只作为内部实现细节，不再暴露为领域枚举。

## 10. 删除与收口清单

### 10.1 删除

- `tools/core/base.py` 中 `WeaverTool`、`ToolResult`、`tool_schema`
- `tools/core/langchain_adapter.py`
- `tools/core/registry.py`
- 所有依赖旧 registry discovery 的主路径代码
- 所有 capability/toolset 相关正式领域模型

### 10.2 收口

- `agent/infrastructure/tools/assembly.py` 只保留 concrete tool inventory 和过滤逻辑
- `agent/infrastructure/tools/catalog.py` 成为唯一 catalog 派生入口
- `common/agents_store.py` 直接存 concrete tools 配置
- `main.py` 的默认 agent profile 改成具体 tool 列表
- prompt、前端文案、测试中的历史命名全部清理

## 11. Breaking 影响面

### 11.1 后端

- profile schema breaking
- state schema breaking
- tool catalog API breaking
- deep research 角色过滤逻辑 breaking

### 11.2 前端

- OpenAPI 生成类型更新
- 设置页读取/写入 profile 字段更新
- 如有依赖 `/api/tools/registry` 的页面或逻辑，全部切换到 catalog
- 任何依赖 `enabled_tools` 的类型和表单一起调整

### 11.3 测试

以下测试类型都需要同步重写：

- tool registry / discovery
- agent tools assembly
- agent mode selection
- agents API
- tool catalog API
- prompt comparison 中关于 `enabled_tools` 的断言

### 11.4 文档

- 仓库说明中所有 `enabled_tools`、`registry`、`web_search/python/files` 历史术语都需要更新

## 12. 风险与取舍

### 12.1 主要风险

- 改动面广，涉及 profile、runtime、API、前端类型、测试和文档。
- 直接删除 capability/toolset 后，部分“便捷抽象”会消失，配置会变得更显式。
- 如果没有统一的 tool catalog 视图，profile 直接写具体 tool name 容易出错。

### 12.2 取舍

本设计接受以下取舍：

- 接受更显式、更直接的 concrete tool 配置。
- 不再追求“能力层”的抽象优雅，而追求与官方标准的一致性。
- 不保留过渡兼容层，换取一次性收口后的长期简单性。

## 13. 验证标准

完成标准化后，应满足以下条件：

1. 仓库主路径中不再出现 `WeaverTool`、`tool_schema`、`ToolResult` 作为正式工具协议。
2. 仓库主路径中不再出现 `ToolCapability`、`required_capabilities`、`TOOL_SPECS` 作为正式运行时协议。
3. agent 运行时工具装配只围绕 `list[BaseTool]` 展开。
4. `/api/tools/catalog` 直接从运行时 concrete tools 派生。
5. `AgentProfile` 直接配置 concrete tool names。
6. 普通聊天与 deep research 都不再依赖 capability/toolset 语言。
7. 前端、测试、文档中不再使用旧公共命名。

## 14. 实施建议

虽然本次设计是一次性 breaking，但实现时仍建议按以下顺序落地，以降低中途失稳概率：

1. 先定义新的 profile、catalog、state 契约。
2. 再改运行时装配函数，使其只接受和返回 concrete tools。
3. 再删除 capability/toolset 主路径。
4. 再删除旧 `WeaverTool` / registry 兼容层。
5. 最后统一清理前端、测试、文档与默认数据。

这是实现顺序，不代表保留兼容期；每一步都以最终契约为目标。
