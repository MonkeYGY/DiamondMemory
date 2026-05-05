# MCP 接入与一键自检说明（DiamondMemory）

> 目标：新用户从 0 到可用 ≤ 5 分钟：**复制配置 → 粘贴到客户端 → 点自检 → 通过**  
> Schema 版本：`mcp_schema_version`（服务端会在 `/api/mcp/schema`、`/api/mcp/tools` 以及工具返回里带上该字段）

---

## 1. 5 分钟接入（最短版）

### Step 1：拿到“复制即用”的 MCP 配置

打开浏览器访问（本机）：

- `GET http://127.0.0.1:<后端端口>/api/mcp/config-info`

你会得到：
- `python_path`
- `mcp_server_path`
- `mcp_schema_version`

把它们填到你的 MCP 客户端配置里即可。

### Step 2：粘贴到 MCP 客户端（示例：Claude Desktop）

在 `claude_desktop_config.json` 中加入（示例）：

```json
{
  "mcpServers": {
    "diamond-memory": {
      "command": "<python_path>",
      "args": ["<mcp_server_path>"],
      "env": {
        "DIAMOND_MCP_SOURCE": "claude-desktop"
      }
    }
  }
}
```

> 说明：`DIAMOND_MCP_SOURCE` 用于权限控制与审计日志（建议必填）。

### Step 3：点“一键自检”

连接成功后，调用工具：

- `get_startup_status()`

若返回 `overall_status = pass / degraded`，说明可用；若为 `fail`，按 `checks[].suggestion` 逐项修复。

---

## 2. 一键自检（核心）

### 2.1 自检工具

MCP 工具（推荐）：
- `get_startup_status()`

HTTP 接口（便于在浏览器里直接看）：
- `GET /api/mcp/self-check`

### 2.2 自检覆盖范围

| 检查项 | 说明 | 失败时常见原因 | 修复建议示例 |
|---|---|---|---|
| backend | 后端在线/端口/health | 后端未启动、端口被占用 | 启动后端 / 更换端口 / 查看日志 |
| database | SQLite 可写 | 数据目录无权限 | 重新选择数据目录到可写路径 |
| vector_store | 向量库可用（允许 fallback） | Qdrant/FAISS 不可用 | 安装依赖或在设置中切换引擎 |
| knowledge_base_path | 知识库路径可读 | 路径不存在/权限不足 | 重新选择工作区路径/授予权限 |
| ollama | Ollama/模型状态（允许降级） | 11434 未启动、模型未下载 | 启动 Ollama / 下载模型；也可先降级使用 |

> 重要：**Ollama 不可用时不会直接 fail**，会返回 `degraded`（仍可提供部分能力），并给出下载/启动建议。

---

## 3. 固定工具集合（Schema 稳定）

对外固定工具集合如下（不要依赖内部临时工具名）：

1. `search_memories(query, limit, filters)`
2. `create_memory(content, category, tags, source, layer, metadata)`
3. `get_startup_status()`
4. `search_knowledge(query)`
5. `get_stats()`

---

## 4. 高级版（权限与安全）

### 4.1 权限隔离（按 source）

服务端会对每次 MCP 调用做来源识别：
- 推荐通过环境变量：`DIAMOND_MCP_SOURCE`
- 或在 `search_memories` 的 `filters.source` 里显式传入
- `create_memory` 必须提供 `source`

当出现：
- `SOURCE_BLOCKED`：来源被管理员禁用（读写全禁）
- `SOURCE_READ_BLOCKED`：来源未授权读取（只禁读）

请在钻石记忆系统设置中开启对应来源的集成/读取权限开关后再试。

### 4.2 调用审计（默认开启）

每次 MCP 调用会写入审计日志（SQLite）：
- 来源（source）
- 工具名
- 参数摘要（脱敏：不记录 content/query 全文）
- 结果数量

---

## 5. 常见客户端接入提示

> 下方只给出关键差异；核心都是“command + args + env”。

### Cursor / Trae

将 MCP Server 配置为：
- `command = <python_path>`
- `args = [<mcp_server_path>]`
- `env.DIAMOND_MCP_SOURCE = "cursor"` 或 `"trae"`

接入后先调用 `get_startup_status()`，按建议修复至 `pass/degraded`。

