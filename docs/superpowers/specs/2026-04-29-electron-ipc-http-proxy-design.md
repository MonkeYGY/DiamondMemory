# Electron 生产环境 HTTP→IPC 代理（彻底绕开 CORS）- 设计文档

日期：2026-04-29  
版本：V0.9.1（任务卡 #1 / ID=1 / P0）  
范围：Electron（Vue3 渲染进程 + preload + 主进程）→ 本机后端 FastAPI（127.0.0.1）  

---

## 1. 背景与问题

打包后 Electron 使用 `file://` 加载页面，渲染进程对本机后端发起 `fetch("http://127.0.0.1:<port>/...")` 时，浏览器侧会出现 `Origin: null`，导致 CORS/预检策略在部分环境下不稳定（尤其是涉及流式/上传等场景）。

目标：**生产环境彻底不让渲染进程直连后端 HTTP**，从根因绕开 CORS。

---

## 2. 目标 / 非目标

### 2.1 目标
1. 生产环境（`app.isPackaged === true`）下：渲染进程所有后端访问统一走 **IPC→主进程→HTTP**。
2. 覆盖所有请求类型：
   - 普通 JSON 请求（GET/POST/PUT/DELETE…）
   - SSE/流式（现有 `/api/chat/stream` 的逐行 JSON 流）
   - 文件上传（`/api/storage/file`）
   - URL 采集（`/api/storage/url`）
3. 安全兜底：主进程仅允许访问 `http://127.0.0.1:<backendPort>`，并做路径白名单。
4. 尽量最小侵入：渲染层接口封装保持 `apiRequest()` / `chatStreamRequest()` 的调用方式不变或接近不变。

### 2.2 非目标
1. 不引入额外本地 HTTP 代理服务（避免多一个端口/进程/攻击面）。
2. 不改后端 API 协议与路由（保持兼容）。

---

## 3. 推荐方案概览（B1：统一 IPC HTTP 代理）

### 3.1 核心思路
- 渲染进程只发送“请求描述”，不直接 `fetch` 后端。
- 主进程执行对后端的真实 HTTP 请求，并把结果返回给渲染进程。
- 流式请求通过事件推送分片（chunk），并支持 abort。

### 3.2 组件与文件
- 主进程：`frontend/src/main/index.ts`（新增 IPC handler + 流式推送）
- preload：`frontend/src/preload/index.ts`（expose 新 API 给 window）
- 渲染封装：`frontend/src/renderer/api/backend.ts`（统一切换为 IPC）
- 渲染调用点收敛（移除散点直连）：
  - `frontend/src/renderer/views/ChatView.vue`
  - `frontend/src/renderer/views/IngestView.vue`
  - `frontend/src/renderer/views/MemoryView.vue`
  - `frontend/src/renderer/stores/knowledge.ts`

---

## 4. IPC 接口设计

### 4.1 普通请求：`electronAPI.httpRequest(req)`

请求结构：
- `method: string`
- `path: string`（必须以 `/` 开头，禁止传完整 URL）
- `headers?: Record<string, string>`
- `bodyType?: 'json' | 'text' | 'binary'`
- `body?: any`（json/text/base64）
- `timeoutMs?: number`

响应结构：
- `ok: boolean`
- `status: number`
- `headers: Record<string, string>`
- `dataType: 'json' | 'text' | 'binary'`
- `data: any`
- `error?: string`

主进程安全策略：
- 仅允许 `host in {127.0.0.1}`（固定）且端口来自 `backendManager.getPort()`
- 路径白名单：`^/(api|health)(/|$)`
- 过滤/覆盖危险头：`Host`、`Origin`、`Referer`、`Connection`、`Content-Length`

### 4.2 流式请求（聊天）：`electronAPI.httpStreamStart(req)` + 事件

IPC：
- `http:stream:start`（invoke）→ 返回 `streamId`
- `http:stream:abort`（invoke 或 send）→ 中止
- 事件推送：
  - `http:stream:chunk`（携带 `{streamId, chunk}`）
  - `http:stream:done`
  - `http:stream:error`

chunk 内容定义：
- 直接透传后端返回的“逐行 JSON”文本（渲染侧复用现有解析逻辑）。

### 4.3 文件上传：`electronAPI.httpUploadFile(payload)`

请求结构：
- `filename: string`
- `mime: string`
- `buffer: ArrayBuffer`（通过 structured clone 传输）

主进程：
- 组装 `FormData`（`file` 字段），请求 `/api/storage/file`

### 4.4 URL 采集：`electronAPI.httpCrawlUrl(url)`

请求结构：
- `url: string`

主进程：
- 组装 `FormData`（`url` 字段），请求 `/api/storage/url`

---

## 5. 渲染端改造策略（最小侵入）

### 5.1 后端访问统一入口
目标：所有“对后端的 fetch”收敛到 `frontend/src/renderer/api/backend.ts`。

规则：
- 生产环境优先使用 `window.electronAPI.httpRequest/httpStream/...`
- 开发环境保持现状（Vite proxy / 直连）以便调试

### 5.2 需要替换的散点直连
当前存在直接 `fetch(`${apiBase}/...`)` 的调用点（非 `apiRequest`）：
- ChatView：上传文件 / 采集 URL
- IngestView：上传文件 / 采集 URL
- MemoryView：delete 直连
- knowledge store：list/search 直连

统一改为调用 `apiRequest` 或新的上传/采集封装方法。

---

## 6. 错误处理与可观测性
1. 主进程对每个请求打日志（debug 级别，避免泄漏内容）：
   - method/path/status/durationMs/是否流式
2. 渲染端保留现有 toast/error 展示逻辑。
3. 流式异常：在 `http:stream:error` 中回传 message（截断到合理长度）。

---

## 7. 验收与自测

### 7.1 验收标准
打包运行后：
- 设置页 / 记忆页 / 聊天页 / 入库页等所有接口正常
- 控制台无 CORS 报错（渲染进程不再直连 HTTP）

### 7.2 冒烟步骤（人工）
1. 打包后打开 App
2. 执行一次：创建记忆 / 查询记忆 / 读取知识库树 / 聊天

---

## 8. 回滚策略
保留渲染端原有 `http://127.0.0.1:<port>` 直连逻辑（通过 `app.isPackaged` 分支控制）。
如 IPC 代理出现兼容性问题，可快速切回直连方案。

