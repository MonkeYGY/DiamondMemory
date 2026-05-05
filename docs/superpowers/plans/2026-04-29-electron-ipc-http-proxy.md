# Electron IPC HTTP Proxy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 生产环境下渲染进程不再直连本机后端 HTTP，所有请求统一走 IPC→主进程→HTTP，彻底绕开 CORS（含普通接口/聊天流式/文件上传/URL采集）。

**Architecture:** preload 暴露 `electronAPI.httpRequest/httpStreamStart/httpUploadFile/httpCrawlUrl`；主进程注册对应 IPC handler，由主进程对 `http://127.0.0.1:<backendPort>` 发起请求并回传结果/流式分片；渲染侧在 `src/renderer/api/backend.ts` 收敛所有请求入口并在生产环境切换到 IPC 通道。

**Tech Stack:** Electron 29（主进程 Node fetch/FormData/Blob）、Vue3、TypeScript、FastAPI 后端（不改协议）。

---

## 文件结构与职责（锁定）

**Create**
- `frontend/src/main/http-ipc-proxy.ts`：主进程 HTTP 代理核心实现 + IPC 注册（普通/流式/上传/采集）

**Modify**
- `frontend/src/main/index.ts`：在 app ready 后注册代理 IPC handlers（并注入 mainWindow）
- `frontend/src/preload/index.ts`：expose 新 API + 事件订阅/退订方法
- `frontend/src/renderer/api/backend.ts`：生产环境切换到 IPC；新增上传/采集封装；改造流式聊天
- `frontend/src/renderer/views/ChatView.vue`：上传/采集改走封装
- `frontend/src/renderer/views/IngestView.vue`：上传/采集改走封装
- `frontend/src/renderer/views/MemoryView.vue`：删除接口改走 `apiRequest`
- `frontend/src/renderer/stores/knowledge.ts`：list/search 改走 `apiRequest`

---

### Task 1: 主进程实现 HTTP→IPC 代理核心（普通请求 + 安全策略）

**Files:**
- Create: `frontend/src/main/http-ipc-proxy.ts`
- Modify: `frontend/src/main/index.ts`

- [ ] **Step 1: 新建主进程代理文件（先不接入流式/上传）**

创建 `frontend/src/main/http-ipc-proxy.ts`：

```ts
import { ipcMain, WebContents } from 'electron'
import { backendManager } from './backend-manager.js'

type BodyType = 'json' | 'text' | 'binary'

export interface HttpRequestPayload {
  method: string
  path: string
  headers?: Record<string, string>
  bodyType?: BodyType
  body?: any
  timeoutMs?: number
}

export interface HttpResponsePayload {
  ok: boolean
  status: number
  headers: Record<string, string>
  dataType: BodyType
  data: any
  error?: string
}

function toHeadersObject(headers: Headers): Record<string, string> {
  const obj: Record<string, string> = {}
  headers.forEach((v, k) => { obj[k.toLowerCase()] = v })
  return obj
}

function isAllowedPath(path: string): boolean {
  // 仅允许访问后端路由，避免滥用
  return /^\\/(api|health)(\\/|$)/.test(path)
}

function sanitizeHeaders(input?: Record<string, string>): Record<string, string> {
  const out: Record<string, string> = {}
  if (!input) return out
  for (const [k, v] of Object.entries(input)) {
    const key = k.toLowerCase()
    if (['host', 'origin', 'referer', 'connection', 'content-length'].includes(key)) continue
    out[key] = String(v)
  }
  return out
}

function resolveBackendBase(): string {
  const port = backendManager.getPort()
  return `http://127.0.0.1:${port}`
}

export function registerHttpProxyIpcHandlers(options: { getWebContents: () => WebContents | null }) {
  ipcMain.handle('http:request', async (_evt, payload: HttpRequestPayload): Promise<HttpResponsePayload> => {
    try {
      if (!payload?.path || typeof payload.path !== 'string' || !payload.path.startsWith('/')) {
        return { ok: false, status: 400, headers: {}, dataType: 'text', data: '', error: 'invalid path' }
      }
      if (!isAllowedPath(payload.path)) {
        return { ok: false, status: 403, headers: {}, dataType: 'text', data: '', error: 'path forbidden' }
      }

      const method = (payload.method || 'GET').toUpperCase()
      const url = `${resolveBackendBase()}${payload.path}`
      const headers = sanitizeHeaders(payload.headers)

      const controller = new AbortController()
      const timeoutMs = Math.max(1000, Math.min(payload.timeoutMs ?? 30000, 120000))
      const t = setTimeout(() => controller.abort(), timeoutMs)

      let body: any = undefined
      if (payload.bodyType === 'json') {
        headers['content-type'] = headers['content-type'] || 'application/json'
        body = JSON.stringify(payload.body ?? {})
      } else if (payload.bodyType === 'text') {
        headers['content-type'] = headers['content-type'] || 'text/plain; charset=utf-8'
        body = String(payload.body ?? '')
      } else if (payload.bodyType === 'binary') {
        // 约定：binary body 为 ArrayBuffer（renderer structured clone）
        body = payload.body ? Buffer.from(payload.body) : undefined
      }

      const resp = await fetch(url, { method, headers, body, signal: controller.signal })
      clearTimeout(t)

      const respHeaders = toHeadersObject(resp.headers)
      const contentType = resp.headers.get('content-type') || ''

      // 默认：json，否则 text
      if (contentType.includes('application/json')) {
        const data = await resp.json().catch(() => null)
        return { ok: resp.ok, status: resp.status, headers: respHeaders, dataType: 'json', data }
      } else {
        const data = await resp.text().catch(() => '')
        return { ok: resp.ok, status: resp.status, headers: respHeaders, dataType: 'text', data }
      }
    } catch (e: any) {
      return { ok: false, status: 500, headers: {}, dataType: 'text', data: '', error: e?.message || 'proxy error' }
    }
  })
}
```

- [ ] **Step 2: 在主进程入口注册 handler（生产环境/开发环境都可注册）**

在 `frontend/src/main/index.ts` 顶部引入并在 `app.whenReady()` 后注册：

```ts
import { registerHttpProxyIpcHandlers } from './http-ipc-proxy.js'
```

在 `app.whenReady().then(() => { ... })` 内部（创建窗口之后、启动后端之前/之后均可）加入：

```ts
registerHttpProxyIpcHandlers({
  getWebContents: () => mainWindow?.webContents || null
})
```

- [ ] **Step 3: TypeScript 构建检查**

Run:
```bash
npm -C frontend run electron:build-main
```

Expected: 命令成功，无 TS 报错。

- [ ] **Step 4: Commit**

```bash
git add frontend/src/main/index.ts frontend/src/main/http-ipc-proxy.ts
git commit -m "feat(electron): add main-process http proxy ipc handler"
```

---

### Task 2: preload 暴露 httpRequest API（渲染侧可用）

**Files:**
- Modify: `frontend/src/preload/index.ts`

- [ ] **Step 1: 扩展 electronAPI 暴露方法**

在 `contextBridge.exposeInMainWorld('electronAPI', { ... })` 中增加：

```ts
  httpRequest: (payload: any) => ipcRenderer.invoke('http:request', payload),
```

- [ ] **Step 2: preload 构建检查**

Run:
```bash
npm -C frontend run electron:build-preload
```

Expected: 成功。

- [ ] **Step 3: Commit**

```bash
git add frontend/src/preload/index.ts
git commit -m "feat(preload): expose httpRequest ipc api"
```

---

### Task 3: 渲染端 apiRequest 生产环境切换为 IPC（替换直连 HTTP）

**Files:**
- Modify: `frontend/src/renderer/api/backend.ts`

- [ ] **Step 1: 在 apiRequest 内优先走 IPC**

将 `apiRequest` 改造为：

```ts
export async function apiRequest<T>(endpoint: string, options?: RequestInit): Promise<T> {
  // dev：保持 Vite proxy（相对路径）
  if (isDev) {
    const response = await fetch(endpoint, {
      headers: { 'Content-Type': 'application/json', ...options?.headers },
      ...options
    })
    if (!response.ok) throw new Error(`API请求失败: ${response.status} ${response.statusText}`)
    return response.json()
  }

  // prod：优先 IPC 代理
  if (window.electronAPI?.httpRequest) {
    const method = (options?.method || 'GET').toString()
    const headers = (options?.headers || {}) as any

    let bodyType: 'json' | 'text' | 'binary' | undefined
    let body: any = undefined
    if (options?.body != null) {
      // 约定：现有调用基本都是 JSON.stringify(...)
      bodyType = 'text'
      body = options.body
      const ct = (headers['Content-Type'] || headers['content-type'] || '') as string
      if (ct.includes('application/json')) {
        bodyType = 'text' // 这里直接透传字符串，主进程按 text 发出
      }
    }

    const resp = await window.electronAPI.httpRequest({
      method,
      path: endpoint,
      headers,
      bodyType,
      body
    })

    if (!resp?.ok) throw new Error(resp?.error || `API请求失败: ${resp?.status}`)
    return resp.data as T
  }

  // 兜底：旧逻辑直连（理论上生产环境一定有 electronAPI）
  const apiBase = `http://127.0.0.1:${await resolvePort()}`
  const response = await fetch(`${apiBase}${endpoint}`, {
    headers: { 'Content-Type': 'application/json', ...options?.headers },
    ...options
  })
  if (!response.ok) throw new Error(`API请求失败: ${response.status} ${response.statusText}`)
  return response.json()
}
```

（实现时可小幅调整，但核心是：prod → `electronAPI.httpRequest`）

- [ ] **Step 2: Typecheck**

Run:
```bash
npm -C frontend run build
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/renderer/api/backend.ts
git commit -m "refactor(renderer): route apiRequest through ipc in production"
```

---

### Task 4: 主进程实现“聊天流式” IPC（start/chunk/done/error/abort）

**Files:**
- Modify: `frontend/src/main/http-ipc-proxy.ts`
- Modify: `frontend/src/preload/index.ts`
- Modify: `frontend/src/renderer/api/backend.ts`

- [ ] **Step 1: 主进程增加 stream handlers**

在 `http-ipc-proxy.ts` 中增加：
- `ipcMain.handle('http:stream:start', ...)` → 返回 `streamId`
- `ipcMain.handle('http:stream:abort', ...)` → abort
- 用 `options.getWebContents()?.send('http:stream:chunk', { streamId, chunk })` 推送

关键实现片段（示例）：

```ts
const streamControllers = new Map<string, AbortController>()

ipcMain.handle('http:stream:start', async (_evt, payload: HttpRequestPayload) => {
  const streamId = `${Date.now()}-${Math.random().toString(16).slice(2)}`
  const wc = options.getWebContents()
  if (!wc) return { ok: false, streamId: '', error: 'no webContents' }

  const controller = new AbortController()
  streamControllers.set(streamId, controller)

  ;(async () => {
    try {
      const url = `${resolveBackendBase()}${payload.path}`
      const resp = await fetch(url, {
        method: (payload.method || 'POST').toUpperCase(),
        headers: sanitizeHeaders(payload.headers),
        body: typeof payload.body === 'string' ? payload.body : JSON.stringify(payload.body ?? {}),
        signal: controller.signal
      })
      if (!resp.ok || !resp.body) {
        wc.send('http:stream:error', { streamId, error: `upstream ${resp.status}` })
        return
      }

      const reader = resp.body.getReader()
      const decoder = new TextDecoder()
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        const chunk = decoder.decode(value, { stream: true })
        wc.send('http:stream:chunk', { streamId, chunk })
      }
      wc.send('http:stream:done', { streamId })
    } catch (e: any) {
      wc.send('http:stream:error', { streamId, error: e?.message || 'stream error' })
    } finally {
      streamControllers.delete(streamId)
    }
  })()

  return { ok: true, streamId }
})

ipcMain.handle('http:stream:abort', async (_evt, streamId: string) => {
  streamControllers.get(streamId)?.abort()
  streamControllers.delete(streamId)
  return true
})
```

- [ ] **Step 2: preload 暴露 stream API + 事件订阅**

在 preload 添加：

```ts
  httpStreamStart: (payload: any) => ipcRenderer.invoke('http:stream:start', payload),
  httpStreamAbort: (streamId: string) => ipcRenderer.invoke('http:stream:abort', streamId),
  onHttpStreamChunk: (callback: (p: any) => void) => {
    const h = (_e: any, p: any) => callback(p)
    ipcRenderer.on('http:stream:chunk', h)
    return () => ipcRenderer.removeListener('http:stream:chunk', h)
  },
  onHttpStreamDone: (callback: (p: any) => void) => {
    const h = (_e: any, p: any) => callback(p)
    ipcRenderer.on('http:stream:done', h)
    return () => ipcRenderer.removeListener('http:stream:done', h)
  },
  onHttpStreamError: (callback: (p: any) => void) => {
    const h = (_e: any, p: any) => callback(p)
    ipcRenderer.on('http:stream:error', h)
    return () => ipcRenderer.removeListener('http:stream:error', h)
  },
```

- [ ] **Step 3: 渲染端 chatStreamRequest 切到 IPC**

在 `chatStreamRequest` 中：
- prod 且存在 `electronAPI.httpStreamStart` 时：
  1) 调用 start 得到 `streamId`
  2) 订阅 chunk/done/error，复用现有“逐行 JSON 解析”逻辑
  3) AbortController.abort 时调用 `httpStreamAbort(streamId)`

（实现时保留现有直连逻辑作为 fallback）

- [ ] **Step 4: Build & Commit**

Run:
```bash
npm -C frontend run electron:build-all
```

Commit:
```bash
git add frontend/src/main/http-ipc-proxy.ts frontend/src/preload/index.ts frontend/src/renderer/api/backend.ts
git commit -m "feat: proxy chat stream via ipc in production"
```

---

### Task 5: 文件上传与 URL 采集走 IPC（彻底移除散点直连）

**Files:**
- Modify: `frontend/src/main/http-ipc-proxy.ts`
- Modify: `frontend/src/preload/index.ts`
- Modify: `frontend/src/renderer/api/backend.ts`
- Modify: `frontend/src/renderer/views/ChatView.vue`
- Modify: `frontend/src/renderer/views/IngestView.vue`

- [ ] **Step 1: 主进程实现 upload/crawl handlers**

主进程新增：
- `ipcMain.handle('http:upload:file', ...)`
- `ipcMain.handle('http:crawl:url', ...)`

上传示例：

```ts
ipcMain.handle('http:upload:file', async (_evt, payload: { filename: string; mime: string; buffer: ArrayBuffer }) => {
  try {
    const url = `${resolveBackendBase()}/api/storage/file`
    const fd = new FormData()
    const blob = new Blob([Buffer.from(payload.buffer)], { type: payload.mime || 'application/octet-stream' })
    fd.set('file', blob, payload.filename || 'file')
    const resp = await fetch(url, { method: 'POST', body: fd })
    const text = await resp.text().catch(() => '')
    return { ok: resp.ok, status: resp.status, data: text }
  } catch (e: any) {
    return { ok: false, status: 500, data: '', error: e?.message || 'upload error' }
  }
})
```

URL 采集示例：

```ts
ipcMain.handle('http:crawl:url', async (_evt, urlToCrawl: string) => {
  try {
    const url = `${resolveBackendBase()}/api/storage/url`
    const fd = new FormData()
    fd.set('url', urlToCrawl)
    const resp = await fetch(url, { method: 'POST', body: fd })
    const text = await resp.text().catch(() => '')
    return { ok: resp.ok, status: resp.status, data: text }
  } catch (e: any) {
    return { ok: false, status: 500, data: '', error: e?.message || 'crawl error' }
  }
})
```

- [ ] **Step 2: preload 暴露 upload/crawl**

```ts
  httpUploadFile: (payload: any) => ipcRenderer.invoke('http:upload:file', payload),
  httpCrawlUrl: (url: string) => ipcRenderer.invoke('http:crawl:url', url),
```

- [ ] **Step 3: 渲染端新增封装函数**

在 `frontend/src/renderer/api/backend.ts` 新增：

```ts
export async function uploadFileToBackend(file: File): Promise<void> {
  if (isDev) {
    const apiBase = await getResolvedApiBase()
    const fd = new FormData()
    fd.append('file', file)
    const resp = await fetch(`${apiBase}/api/storage/file`, { method: 'POST', body: fd })
    if (!resp.ok) throw new Error(await resp.text())
    return
  }

  if (window.electronAPI?.httpUploadFile) {
    const buffer = await file.arrayBuffer()
    const resp = await window.electronAPI.httpUploadFile({ filename: file.name, mime: file.type, buffer })
    if (!resp?.ok) throw new Error(resp?.error || `upload failed: ${resp?.status}`)
    return
  }

  throw new Error('上传失败：缺少 IPC 通道')
}

export async function crawlUrlToBackend(url: string): Promise<void> {
  if (isDev) {
    const apiBase = await getResolvedApiBase()
    const fd = new FormData()
    fd.append('url', url)
    const resp = await fetch(`${apiBase}/api/storage/url`, { method: 'POST', body: fd })
    if (!resp.ok) throw new Error(await resp.text())
    return
  }

  if (window.electronAPI?.httpCrawlUrl) {
    const resp = await window.electronAPI.httpCrawlUrl(url)
    if (!resp?.ok) throw new Error(resp?.error || `crawl failed: ${resp?.status}`)
    return
  }

  throw new Error('采集失败：缺少 IPC 通道')
}
```

- [ ] **Step 4: ChatView/IngestView 取消散点 fetch，改调用封装**

将两处 `fetch(`${apiBase}/api/storage/file`...)` 改为 `uploadFileToBackend(file)`；
将两处 `fetch(`${apiBase}/api/storage/url`...)` 改为 `crawlUrlToBackend(inputUrl.value)`。

- [ ] **Step 5: Build & Commit**

Run:
```bash
npm -C frontend run build
```

Commit:
```bash
git add frontend/src/main/http-ipc-proxy.ts frontend/src/preload/index.ts frontend/src/renderer/api/backend.ts frontend/src/renderer/views/ChatView.vue frontend/src/renderer/views/IngestView.vue
git commit -m "feat: proxy upload and url crawl via ipc in production"
```

---

### Task 6: 替换其它直连点（Memory delete / Knowledge list/search）

**Files:**
- Modify: `frontend/src/renderer/views/MemoryView.vue`
- Modify: `frontend/src/renderer/stores/knowledge.ts`

- [ ] **Step 1: MemoryView 删除接口改走 apiRequest**

把：
```ts
const response = await fetch(`${apiBase}/api/memory/delete/${id}`, { method: 'DELETE' })
```

改为：
```ts
await apiRequest(`/api/memory/delete/${id}`, { method: 'DELETE' })
```

- [ ] **Step 2: Knowledge store 改走 apiRequest**

把 list/search 两处直连 fetch 改为：
```ts
import { apiRequest } from '../api/backend'
knowledgeItems.value = await apiRequest('/api/knowledge')
knowledgeItems.value = await apiRequest(`/api/knowledge/search?q=${encodeURIComponent(query)}`)
```

- [ ] **Step 3: Build & Commit**

```bash
npm -C frontend run build
git add frontend/src/renderer/views/MemoryView.vue frontend/src/renderer/stores/knowledge.ts
git commit -m "refactor(renderer): route remaining backend calls through apiRequest"
```

---

### Task 7: 生产环境冒烟验证（手动 + 打包）

**Files:**
- (No code required; if发现缺口则回到对应 task 修补)

- [ ] **Step 1: 本地 Electron dev 验证（开发环境不走 IPC 代理也应正常）**

Run:
```bash
npm -C frontend run electron:dev
```
Expected: 页面正常、接口正常。

- [ ] **Step 2: 生产构建（至少确保构建过）**

Run (按你的平台选一个)：
```bash
npm -C frontend run electron:build:mac
# 或 npm -C frontend run electron:build:win
```

- [ ] **Step 3: 打包产物冒烟**
打开打包后的 App，执行：
1) 创建记忆  
2) 查询记忆  
3) 读取知识库树  
4) 聊天  
Expected: 控制台无 CORS 报错；功能正常。

- [ ] **Step 4: 更新版本优化记录**

将 `版本优化记录/版本优化0.9.1.md` 中 ID=1 状态改为 `已完成`，并追加一条“修复/重构”记录（列出修改文件）。

---

## 自检清单（写计划后必过一遍）
1. spec 覆盖：普通接口/流式/上传/采集都走 IPC（prod）
2. placeholder 扫描：无 TODO/TBD
3. 类型一致：preload 暴露方法名与渲染端调用一致

