# Weaver 项目学习指南

这份指南面向第一次系统阅读 Weaver 的开发者。目标不是一次性看完所有文件，而是用最短路径建立正确的心智模型，然后再进入定向深入。

## 1. 学习目标

完成这份指南后，你应该能回答下面这些问题：

- Weaver 是一个什么类型的项目，解决什么问题
- 仓库里哪些目录是主业务，哪些是基础设施或扩展能力
- 一条聊天请求如何从前端进入后端，再进入 LangGraph 工作流，最后流回 UI
- 工具系统、流式协议、OpenAPI 合约、SDK 之间是什么关系
- 如果要改一个功能，应该先读哪里、改哪里、测哪里

## 2. 适合的学习顺序

建议按下面顺序推进，不要一开始就直接钻进 `main.py`。

1. 先跑起来，确认产品行为。
2. 再看文档，理解功能面和运行方式。
3. 再看架构，建立目录级和模块级地图。
4. 然后只追一条主链路：聊天流式请求。
5. 最后再拆开研究工具系统、协议、SDK、触发器和浏览器实时流。

## 3. 学习前准备

### 3.1 前置知识

- Python 3.11、FastAPI、Pydantic
- TypeScript、React、Next.js
- 基本的 SSE、WebSocket、OpenAPI 概念
- 对 LangChain/LangGraph 有粗略认识会更快，但不是硬要求

### 3.2 本地环境

先按仓库文档把项目跑起来：

```bash
make setup
pnpm -C web install --frozen-lockfile
.venv/bin/python main.py
pnpm -C web dev
```

更完整的本地运行说明看：

- `docs/getting-started.md`
- `docs/development.md`

如果你在团队流程里使用 beads，可先尝试：

```bash
bd onboard
```

如果当前环境没有安装 `bd`，可以跳过，不影响代码学习。

## 4. 第一阶段：先理解产品，不先看实现

目标：知道 Weaver 对外提供哪些能力。

### 4.1 推荐阅读

按顺序阅读：

1. `README.md`
2. `docs/README.md`
3. `docs/usage.md`
4. `docs/getting-started.md`

### 4.2 你要重点记住什么

- Weaver 不是单纯聊天 UI，而是 AI Agent 平台
- 它的核心价值在于：
  - 智能路由
  - Deep Research
  - 工具调用
  - 浏览器自动化
  - 多协议流式交互
  - OpenAPI 驱动的前后端/SDK 契约对齐

### 4.3 建议动手操作

至少在 Web 界面里跑一遍下面四种模式：

1. 直接模式
2. 搜索模式
3. 工具模式
4. 深度模式

如果只是读代码、不看实际行为，后面看到状态流、工具事件和证据面板时会很抽象。

## 5. 第二阶段：建立仓库地图

目标：知道“代码大概都放在哪”。

### 5.1 先读这份分析

- `docs/project-architecture-analysis.md`

### 5.2 再记住这个目录划分

| 目录/文件 | 作用 | 学习优先级 |
| --- | --- | --- |
| `main.py` | FastAPI 入口与运行时装配中心 | 很高 |
| `agent/core/` | 图定义、状态、路由、事件系统 | 很高 |
| `agent/workflows/` | 各工作流节点与深度研究逻辑 | 很高 |
| `tools/` | 搜索、浏览器、沙箱、自动化等能力实现 | 高 |
| `common/` | 配置、SSE、日志、指标、会话等横切基础设施 | 高 |
| `web/` | Next.js 前端、流式消费、聊天界面 | 高 |
| `sdk/` | Python/TypeScript SDK | 中 |
| `triggers/` | 定时、Webhook、事件触发器 | 中 |
| `tests/` | 行为回归与契约保护 | 很高 |
| `support_agent.py` | 独立轻量客服图 | 低到中 |

### 5.3 学习时要避免的误区

- 不要把 `main.py` 当成全部业务实现，它更多是平台入口和装配点
- 不要只看目录名猜职责，要结合真实调用链
- 不要一开始试图把 `tools/` 全读完，先理解“工具如何被装配进 Agent”

## 6. 第三阶段：追一条主链路

目标：把最核心的聊天流式链路看透。

### 6.1 推荐阅读顺序

按这个顺序读：

1. `web/app/page.tsx`
2. `web/components/chat/Chat.tsx`
3. `web/hooks/useChatStream.ts`
4. `web/lib/chatStreamProtocol.ts`
5. `main.py` 中：
   - `/api/chat`
   - `/api/chat/sse`
   - `stream_agent_events()`
6. `agent/core/graph.py`
7. `agent/workflows/nodes.py`

### 6.2 这条链路要搞懂的关键问题

- 前端何时创建消息、何时发请求、何时更新状态
- 后端为何同时保留 `/api/chat` 和 `/api/chat/sse`
- `thread_id` 是如何生成、传播和用于取消/事件流的
- LangGraph 如何根据路由进入 `direct / agent / web / deep / clarify`
- 工作流事件如何被编码成前端可消费的流

### 6.3 学习输出

你应该能自己画出这条链路：

```text
Chat UI -> useChatStream -> /api/chat -> stream_agent_events
-> research_graph -> nodes/tool events -> legacy/SSE stream -> UI
```

如果这条链路没有完全打通，不建议继续深挖局部细节。

## 7. 第四阶段：理解 Agent 编排层

目标：知道 Weaver 的“智能性”主要写在哪。

### 7.1 核心阅读文件

- `agent/core/graph.py`
- `agent/core/smart_router.py`
- `agent/core/events.py`
- `agent/workflows/nodes.py`
- `agent/workflows/agent_factory.py`
- `agent/workflows/agent_tools.py`

### 7.2 重点问题

- `smart_router` 负责什么，`graph` 负责什么，`nodes` 又负责什么
- 深度研究路径为什么会经过 `planner -> search -> writer -> evaluator`
- `agent` 模式与 `deep` 模式的核心区别是什么
- 为什么事件系统单独抽出来，而不是直接写在前端协议里
- Agent Profile 如何影响工具集合

### 7.3 读法建议

- 先看 `graph.py` 的节点和边，建立骨架
- 再挑 `nodes.py` 里的 `route_node`、`planner_node`、`perform_parallel_search`、`writer_node`、`agent_node` 重点读
- 最后看 `agent_factory.py` 和 `agent_tools.py`，理解运行时怎么拼 Agent

## 8. 第五阶段：理解工具系统

目标：搞清楚 Weaver 的能力扩展面。

### 8.1 推荐阅读

1. `docs/TOOL_REFERENCE.md`
2. `tools/__init__.py`
3. `tools/core/registry.py`
4. `agent/workflows/agent_tools.py`
5. 代表性工具实现：
   - `tools/search/multi_search.py`
   - `tools/research/content_fetcher.py`
   - `tools/browser/browser_session.py`

### 8.2 学习重点

- 工具不是“自动全开”，而是按 Agent Profile 和运行环境动态装配
- `tools/core/registry.py` 是统一注册中心
- 搜索、抓取、浏览器、沙箱、MCP、任务管理是几条不同能力线
- 你要先学“工具怎么进入工作流”，再学“单个工具怎么实现”

### 8.3 最佳实践式读法

优先挑一个能力面深入，例如：

- 只看搜索链：`multi_search -> content_fetcher -> sources/evidence`
- 或只看浏览器链：`browser tools -> browser stream -> BrowserViewer`
- 或只看沙箱链：`agent_tools.py` 中的 E2B 相关装配

不要同时展开三个方向。

## 9. 第六阶段：理解前端展示层

目标：知道前端到底承担什么，不承担什么。

### 9.1 推荐阅读

- `web/components/chat/Chat.tsx`
- `web/components/chat/MessageItem.tsx`
- `web/components/chat/ArtifactsPanel.tsx`
- `web/components/chat/BrowserViewer.tsx`
- `web/hooks/useChatStream.ts`
- `web/hooks/useBrowserStream.ts`
- `web/lib/api.ts`

### 9.2 重点问题

- 前端为什么要维护消息、工具事件、artifact、browser viewer 几套状态
- 浏览器实时流为什么单独走 WebSocket
- 前端为什么还保留 legacy 协议解析器
- 哪些内容属于纯 UI，哪些内容是协议耦合

### 9.3 学习结论

读完这部分后，你应明确：

- 前端不是业务编排层
- 前端主要是流式协议消费者和运行态可视化层
- 如果出现“流式显示不对”，首先查的是协议与 hook，而不是节点逻辑

## 10. 第七阶段：理解协议、契约和 SDK

目标：知道后端变更如何影响前端和 SDK。

### 10.1 推荐阅读

- `docs/api.md`
- `docs/chat-streaming.md`
- `docs/openapi-contract.md`
- `sdk/python/weaver_sdk/client.py`
- `sdk/typescript/src/client.ts`
- `sdk/typescript/src/sse.ts`

### 10.2 你要搞懂什么

- `/api/chat` 与 `/api/chat/sse` 的职责差异
- SSE 和 legacy 行协议的差异
- OpenAPI 为什么是后端、前端、SDK 的单一契约源
- TypeScript SDK 为什么依赖生成类型

### 10.3 关键开发动作

如果你改了后端接口，必须想到下面这条链：

```text
Pydantic / response_model -> OpenAPI -> TS types -> web/sdk 消费方
```

然后执行：

```bash
make openapi-types
pnpm -C web build
```

## 11. 第八阶段：理解调试、测试和质量门

目标：学会安全地改代码，而不是只会读代码。

### 11.1 推荐阅读

- `docs/development.md`
- `Makefile`
- `tests/` 下与当前学习主题最相关的测试

### 11.2 常用命令

```bash
make test
make lint
make check
pnpm -C web test
pnpm -C web lint
pnpm -C web build
```

### 11.3 调试入口

- 后端日志：`logs/weaver.log`
- 线程日志：`logs/threads/{thread_id}.log`
- OpenAPI：`/docs`
- Browser live stream 诊断：`/api/sandbox/browser/diagnose`
- 工具注册排查：`/api/tools/registry`

### 11.4 测试阅读策略

不要一次性看所有测试。按功能倒推：

1. 先找你正在学的模块对应测试
2. 看它保护了什么行为
3. 再看失败会影响什么契约

例如：

- 聊天链路：`tests/test_chat_*`
- 浏览器流：`tests/test_browser_ws_*`
- OpenAPI/SDK：`tests/test_openapi_contract.py`、`tests/test_sdk_*`
- Deep Research：`tests/test_deepsearch_*`

## 12. 推荐的 7 天学习路径

### Day 1

- 跑通本地环境
- 阅读 `README.md`、`docs/README.md`、`docs/getting-started.md`
- 在 UI 中体验四种模式

### Day 2

- 阅读 `docs/project-architecture-analysis.md`
- 画出仓库模块地图
- 记住各目录职责

### Day 3

- 追聊天主链路
- 阅读 `Chat.tsx`、`useChatStream.ts`、`main.py` 的聊天入口
- 自己写一张时序图

### Day 4

- 阅读 `agent/core/graph.py` 和 `agent/workflows/nodes.py`
- 理解路由、规划、搜索、写作、评估节点

### Day 5

- 阅读 `agent/workflows/agent_tools.py`、`tools/core/registry.py`
- 选一个能力面深入：搜索或浏览器

### Day 6

- 阅读 `docs/chat-streaming.md`、`docs/openapi-contract.md`
- 对照 SDK 理解契约传播

### Day 7

- 看相关测试
- 尝试做一个小改动并跑验证
- 写下你的模块理解与待确认问题

## 13. 最适合新人的练手任务

按难度从低到高：

1. 修改一个前端状态文案，并确认流式展示正常
2. 给已有 API 响应补一个更明确的 `response_model`
3. 给某个工具事件补充一个展示字段，并同步前端显示
4. 新增一个只读型工具并接入 Agent Profile
5. 为一个聊天或搜索行为补一条测试
6. 调整 OpenAPI 输出并重新生成 TS types
7. 跟踪一次 deep research 的完整事件流并写出调试记录

## 14. 学习时的高频误区

- 误区 1：一上来通读 `main.py`
  - 正解：先看产品行为和聊天主链路，再回到 `main.py`

- 误区 2：把 `tools/` 当作一个完全独立的基础层
  - 正解：当前实现里它与 `agent` 存在一定反向依赖，要带着实际调用链去看

- 误区 3：只看前端界面，不看流式协议
  - 正解：Weaver 很多复杂度都在协议层，而不是组件树

- 误区 4：改后端接口却忘了 OpenAPI 和 TS types
  - 正解：把契约漂移当成一类一等问题处理

- 误区 5：试图同时理解 Deep Research、浏览器流、MCP、触发器
  - 正解：一次只追一条能力线

## 15. 学完后的进阶方向

如果你已经完成本指南，下一步建议按兴趣选择一个方向深入：

- Agent 编排方向：深入 `nodes.py`、评估器、Deep Research 迭代策略
- 工具平台方向：深入 `tools/`、MCP、E2B、浏览器能力
- 前端体验方向：深入流式协议、Evidence/Artifacts、BrowserViewer
- 平台工程方向：深入 OpenAPI、测试体系、日志、部署与限流
- 自动化方向：深入 `triggers/` 与会话恢复能力

## 16. 结束标准

当你满足下面这些条件时，可以认为已经完成“项目入门”：

- 能独立跑起前后端
- 能解释聊天请求的主执行链
- 能指出新增一个工具大概需要改哪些层
- 能说明后端接口变更会如何影响前端和 SDK
- 能找到当前问题应该先去哪个目录排查

如果做不到这些，继续回到“第三阶段：追一条主链路”，不要盲目扩大学习范围。
