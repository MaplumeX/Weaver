# MCP（Model Context Protocol）在 Weaver 的使用指南

Weaver 支持通过 **MCP（Model Context Protocol）** 把外部工具“挂载”到 Agent 的工具系统中（例如：文件系统、记忆、Git、数据库等），从而让模型在对话中可以安全、可扩展地调用这些能力。

---

## 1) MCP 是什么（一句话）

**MCP 是一个开放协议**：用统一的方式让“模型/Agent 客户端”连接“工具服务器（MCP Server）”，并以标准化的 schema 暴露工具、调用工具、获取结果。

在 Weaver 里：
- **Weaver 后端**充当 MCP Client（连接 MCP Server）。
- **MCP Server** 是独立进程（本地 stdio 启动，或通过 SSE 连接）。

---

## 2) Weaver 当前支持的 MCP 连接方式

Weaver 的 MCP 配置来自 `.env`（或运行时 API 更新），主要字段：

- `ENABLE_MCP=true|false`
- `MCP_SERVERS=<JSON>`

`MCP_SERVERS` 是一个 JSON 对象，key 是 server id，value 是 server 配置：

### A. `stdio`（推荐，本地起进程）

```json
{
  "filesystem": {
    "type": "stdio",
    "command": "npx",
    "args": ["-y", "@modelcontextprotocol/server-filesystem", "/ABS/PATH/TO/ALLOW"]
  }
}
```

### B. `sse`（连接远程/本地 SSE 服务）

```json
{
  "my_sse_server": {
    "type": "sse",
    "url": "http://127.0.0.1:3333/sse"
  }
}
```

---

## 3) 快速开始（建议：filesystem + memory）

### 3.1 前置条件

- 本机安装 **Node.js**（用于 `npx`）
- 不要把 `.env` 提交到 git

### 3.2 `.env` 示例

把下面这段放进项目根目录 `.env`：

```bash
ENABLE_MCP=true
MCP_SERVERS={"filesystem":{"type":"stdio","command":"npx","args":["-y","@modelcontextprotocol/server-filesystem","/ABS/PATH/TO/ALLOW"]},"memory":{"type":"stdio","command":"npx","args":["-y","@modelcontextprotocol/server-memory"]}}
```

注意：
- `server-filesystem` **必须**传入允许访问的目录（建议只给你项目目录或一个工作区目录）。
- `server-memory` 不需要额外参数。

---

## 4) 通过 Web UI 配置 MCP（可选）

Weaver 前端 Settings 已提供 MCP 配置面板：

- `GET /api/mcp/config`：读取当前 MCP 配置与加载到的工具数量
- `POST /api/mcp/config`：更新 enable/servers，然后后端会 reload MCP tools

适合在不改 `.env` 的情况下，快速试验不同 MCP server 配置。

---

## 5) 安全建议（重要）

- **filesystem**：只给最小权限目录；不要给 `/`、`~` 这类大范围根目录。
- **数据库类 server**：优先只读账号；避免把生产连接串用于开发环境 Agent。
- **不要提交密钥**：`.env`、连接串、token 都不要进 git。

---

## 6) 常见问题排查

### 6.1 `MCP_SERVERS is not valid JSON`

说明 `.env` 里的 `MCP_SERVERS` 不是合法 JSON：
- 确认是双引号 `"`，不是中文引号
- 不要有尾随逗号
- 建议先在 JSON 校验器里过一遍

### 6.2 `MCP connect failed ... command not found`

说明 `command` 不在 PATH：
- `npx` 需要 Node.js
- `uvx` 需要安装 uv（或换成你机器可用的命令）

### 6.3 tools 数量为 0

可能原因：
- `ENABLE_MCP=false`
- `MCP_SERVERS={}` 或 server 启动失败
- MCP Server 端没有暴露任何 tool

