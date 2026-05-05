export interface BackendStatus {
  isRunning: boolean
  state: 'idle' | 'starting' | 'running' | 'error'
  port: number
  lastError: string
}

export interface AppInfo {
  platform: string
  version: string
  isPackaged: boolean
}

let cachedPort = 15920
const isDev = import.meta.env.DEV

function headersToObject(headers?: HeadersInit): Record<string, string> {
  if (!headers) return {}
  if (headers instanceof Headers) {
    const obj: Record<string, string> = {}
    headers.forEach((v, k) => (obj[k] = v))
    return obj
  }
  if (Array.isArray(headers)) {
    return Object.fromEntries(headers.map(([k, v]) => [k, String(v)]))
  }
  return Object.fromEntries(Object.entries(headers).map(([k, v]) => [k, String(v)]))
}

async function resolvePort(): Promise<number> {
  if (window.electronAPI?.getBackendStatus) {
    try {
      const status = await window.electronAPI.getBackendStatus()
      if (status.isRunning && status.port) {
        cachedPort = status.port
        return status.port
      }
    } catch {
      // ignore
    }
  }
  return cachedPort
}

export async function getBackendStatus(): Promise<BackendStatus> {
  try {
    if (window.electronAPI?.getBackendStatus) {
      const status = await window.electronAPI.getBackendStatus()
      if (status.isRunning && status.port) {
        cachedPort = status.port
      }
      return status
    }
  } catch {
    // Fall through to direct HTTP health check
  }

  try {
    const url = isDev ? '/health' : `http://127.0.0.1:${cachedPort}/health`
    const response = await fetch(url)
    if (response.ok) {
      return { isRunning: true, state: 'running', port: cachedPort, lastError: '' }
    }
  } catch {
    // ignore
  }

  return { isRunning: false, state: 'error', port: cachedPort, lastError: '无法获取后端状态' }
}

export async function restartBackend(): Promise<boolean> {
  if (window.electronAPI?.restartBackend) {
    return await window.electronAPI.restartBackend()
  }
  return false
}

export async function stopBackend(): Promise<boolean> {
  if (window.electronAPI?.stopBackend) {
    return await window.electronAPI.stopBackend()
  }
  return false
}

export async function getAppInfo(): Promise<AppInfo> {
  if (window.electronAPI?.getAppInfo) {
    return await window.electronAPI.getAppInfo()
  }
  return { platform: 'unknown', version: '', isPackaged: true }
}

export async function updateBackendPort(port: number) {
  cachedPort = port
}

export async function getResolvedApiBase(): Promise<string> {
  if (isDev) return ''
  const resolvedPort = await resolvePort()
  return `http://127.0.0.1:${resolvedPort}`
}

export function getApiBase(): string {
  if (isDev) return ''
  return `http://127.0.0.1:${cachedPort}`
}

export async function apiRequest<T>(
  endpoint: string,
  options?: RequestInit
): Promise<T> {
  // Electron 环境：优先走 IPC（绕开 CORS + 避免开发模式下 Vite proxy 固定端口导致“多后端/多数据源”）
  if (window.electronAPI?.httpRequest) {
    const method = (options?.method || 'GET').toString()
    const headers = headersToObject(options?.headers)
    const body = options?.body

    const resp = await window.electronAPI.httpRequest({
      method,
      path: endpoint,
      headers: {
        'Content-Type': 'application/json',
        ...headers
      },
      bodyType: body != null ? 'text' : undefined,
      body: body ?? undefined
    })

    if (!resp?.ok) {
      throw new Error(resp?.error || `API请求失败: ${resp?.status ?? 'unknown'}`)
    }

    return resp.data as T
  }

  // 开发环境（纯浏览器/Vite）：Vite proxy（相对路径）
  if (isDev) {
    const response = await fetch(endpoint, {
      headers: {
        'Content-Type': 'application/json',
        ...headersToObject(options?.headers)
      },
      ...options
    })

    if (!response.ok) {
      throw new Error(`API请求失败: ${response.status} ${response.statusText}`)
    }
    return response.json()
  }

  // 兜底：旧直连逻辑（理论上生产环境一定有 electronAPI）
  const apiBase = `http://127.0.0.1:${await resolvePort()}`
  const response = await fetch(`${apiBase}${endpoint}`, {
    headers: {
      'Content-Type': 'application/json',
      ...headersToObject(options?.headers)
    },
    ...options
  })

  if (!response.ok) {
    throw new Error(`API请求失败: ${response.status} ${response.statusText}`)
  }

  return response.json()
}

// ---- Local-first：任务队列 / 能力状态 ----

export async function fetchCapabilities(): Promise<any> {
  return apiRequest('/api/system/capabilities')
}

export async function enqueueTask(payload: { type: string; power_mode?: string; params?: any }): Promise<{ id: string; status: string }> {
  return apiRequest('/api/tasks/enqueue', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export async function fetchTasks(status: string = 'running,queued,blocked', limit: number = 50): Promise<{ items: any[] }> {
  const qs = new URLSearchParams({ status, limit: String(limit) }).toString()
  return apiRequest(`/api/tasks?${qs}`)
}

export async function pauseTask(id: string) {
  return apiRequest(`/api/tasks/${id}/pause`, { method: 'POST' })
}

export async function resumeTask(id: string) {
  return apiRequest(`/api/tasks/${id}/resume`, { method: 'POST' })
}

export async function cancelTask(id: string) {
  return apiRequest(`/api/tasks/${id}/cancel`, { method: 'POST' })
}

export async function rebuildKnowledgeMemoryExports(): Promise<{
  status: string
  message: string
  rebuilt_count: number
  failed_count: number
  deleted_memory_ids: string[]
  errors: string[]
}> {
  return apiRequest('/api/knowledge/rebuild-memory-exports', {
    method: 'POST'
  })
}

export async function syncKnowledgeBase(): Promise<{ id: string; status: string }> {
  return apiRequest('/api/knowledge/sync', { method: 'POST' })
}

export interface ChatStreamCallbacks {
  onChunk: (content: string) => void
  onThinkingChunk?: (thinking: string) => void
  onDone: () => void
  onError: (error: string) => void
}

export async function chatStreamRequest(
  messages: Array<{ role: string; content: string }>,
  callbacks: ChatStreamCallbacks,
  useMemory: boolean = true,
  options?: { useWebSearch?: boolean; maxTokens?: number }
): Promise<AbortController> {
  const controller = new AbortController()
  const apiBase = isDev ? '' : `http://127.0.0.1:${await resolvePort()}`

  try {
    // Electron 环境：优先走 IPC 流式通道（绕开 CORS + 避免开发模式下 Vite proxy 固定端口）
    if (window.electronAPI?.httpStreamStart && window.electronAPI?.onHttpStreamChunk) {
      let streamId = ''
      let buffer = ''

      const cleanupFns: Array<() => void> = []
      const cleanup = () => {
        while (cleanupFns.length) {
          try {
            cleanupFns.pop()?.()
          } catch {
            // ignore
          }
        }
      }

      cleanupFns.push(
        window.electronAPI.onHttpStreamChunk((p: any) => {
          if (!p || p.streamId !== streamId) return
          buffer += p.chunk || ''
          const lines = buffer.split('\n')
          buffer = lines.pop() || ''
          for (const line of lines) {
            const trimmed = (line || '').trim()
            if (!trimmed) continue
            try {
              const data = JSON.parse(trimmed)
              const msg = data?.message || {}
              const thinking = msg?.thinking || ''
              const content = msg?.content || ''
              if (thinking) callbacks.onThinkingChunk?.(thinking)
              if (content && (!thinking || content !== thinking)) callbacks.onChunk(content)
              if (data?.done) {
                cleanup()
                callbacks.onDone()
              }
            } catch {
              // ignore
            }
          }
        })
      )

      if (window.electronAPI?.onHttpStreamDone) {
        cleanupFns.push(
          window.electronAPI.onHttpStreamDone((p: any) => {
            if (!p || p.streamId !== streamId) return
            cleanup()
            callbacks.onDone()
          })
        )
      }

      if (window.electronAPI?.onHttpStreamError) {
        cleanupFns.push(
          window.electronAPI.onHttpStreamError((p: any) => {
            if (!p || p.streamId !== streamId) return
            cleanup()
            callbacks.onError(p.error || '流式请求异常')
          })
        )
      }

      controller.signal.addEventListener('abort', async () => {
        try {
          if (streamId && window.electronAPI?.httpStreamAbort) {
            await window.electronAPI.httpStreamAbort(streamId)
          }
        } finally {
          cleanup()
          callbacks.onDone()
        }
      })

      const startResp = await window.electronAPI.httpStreamStart({
        method: 'POST',
        path: '/api/chat/stream',
        headers: { 'Content-Type': 'application/json' },
        bodyType: 'json',
        body: {
          messages,
          use_memory: useMemory,
          use_web_search: !!options?.useWebSearch,
          max_tokens: typeof options?.maxTokens === 'number' ? options?.maxTokens : undefined
        }
      })

      if (!startResp?.ok) {
        cleanup()
        callbacks.onError(startResp?.error || '无法启动流式请求')
        return controller
      }

      streamId = startResp.streamId
      return controller
    }

    // fallback：旧直连逻辑（开发环境 / IPC 不可用）
    const response = await fetch(`${apiBase}/api/chat/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        messages,
        use_memory: useMemory,
        use_web_search: !!options?.useWebSearch,
        max_tokens: typeof options?.maxTokens === 'number' ? options?.maxTokens : undefined
      }),
      signal: controller.signal
    })

    if (!response.ok) {
      const errorText = await response.text().catch(() => '')
      callbacks.onError(`请求失败: ${response.status} ${response.statusText} ${errorText}`)
      return controller
    }

    const reader = response.body?.getReader()
    if (!reader) {
      callbacks.onError('无法获取响应流')
      return controller
    }

    const decoder = new TextDecoder()
    let buffer = ''

    const processStream = async () => {
      try {
        while (true) {
          const { done, value } = await reader.read()
          if (done) break

          buffer += decoder.decode(value, { stream: true })
          const lines = buffer.split('\n')
          buffer = lines.pop() || ''

          for (const line of lines) {
            const trimmed = line.trim()
            if (!trimmed) continue

            try {
              const data = JSON.parse(trimmed)
              const msg = data?.message || {}
              const thinking = msg?.thinking || ''
              const content = msg?.content || ''
              if (thinking) callbacks.onThinkingChunk?.(thinking)
              if (content && (!thinking || content !== thinking)) callbacks.onChunk(content)
              if (data?.done) {
                callbacks.onDone()
                return
              }
            } catch {
              // skip unparseable lines
            }
          }
        }
        callbacks.onDone()
      } catch (err: any) {
        if (err.name === 'AbortError') {
          callbacks.onDone()
        } else {
          callbacks.onError(err.message || '流式请求异常')
        }
      }
    }

    processStream()
  } catch (err: any) {
    if (err.name === 'AbortError') {
      callbacks.onDone()
    } else {
      callbacks.onError(err.message || '请求异常')
    }
  }

  return controller
}

export async function chatSummaryRequest(payload: {
  dropped_messages: Array<{ role: string; content: string }>
  max_tokens?: number
}): Promise<{ summary_text: string }> {
  return apiRequest('/api/chat/summary', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  })
}

export async function uploadFileToBackend(file: File): Promise<void> {
  const disturbFree = typeof (globalThis as any).localStorage?.getItem === 'function'
    ? localStorage.getItem('dm-disturb-free') === 'true'
    : false

  const extractErrorMessage = (rawText: string, parsed: any): string => {
    if (parsed && typeof parsed === 'object') {
      // FastAPI 常见错误格式：{"detail":"..."} 或 {"detail":{...}}
      const detail = (parsed as any).detail
      if (typeof detail === 'string' && detail.trim()) return detail
      if (detail && typeof detail === 'object') {
        try {
          return JSON.stringify(detail)
        } catch {
          // ignore
        }
      }
      // 业务层错误格式：{"success":false,"error":"..."}
      const err = (parsed as any).error
      if (typeof err === 'string' && err.trim()) return err
      const msg = (parsed as any).message
      if (typeof msg === 'string' && msg.trim()) return msg
    }
    const t = (rawText || '').trim()
    return t || '上传失败'
  }

  // Electron 环境：优先走 IPC（避免开发模式下 Vite proxy 固定端口导致命中错误后端）
  if (window.electronAPI?.httpUploadFile) {
    const buffer = await file.arrayBuffer()
    const resp = await window.electronAPI.httpUploadFile({
      filename: file.name,
      mime: file.type,
      buffer,
      disturbFree
    })
    const text = resp?.data || ''
    let parsed: any = null
    try {
      parsed = text ? JSON.parse(text) : null
    } catch {
      parsed = null
    }
    if (!resp?.ok) throw new Error(resp?.error || extractErrorMessage(text, parsed))
    if (parsed && typeof parsed === 'object' && parsed.success === false) {
      throw new Error(extractErrorMessage(text, parsed))
    }
    return
  }

  // 开发环境（纯浏览器/Vite）：走相对路径（依赖 Vite proxy）
  if (isDev) {
    const apiBase = await getResolvedApiBase()
    const fd = new FormData()
    fd.append('file', file)
    fd.append('disturb_free', disturbFree ? 'true' : 'false')
    const resp = await fetch(`${apiBase}/api/ingest/file`, { method: 'POST', body: fd })
    const text = await resp.text().catch(() => '')
    let parsed: any = null
    try {
      parsed = text ? JSON.parse(text) : null
    } catch {
      parsed = null
    }
    if (!resp.ok) throw new Error(extractErrorMessage(text, parsed))
    if (parsed && typeof parsed === 'object' && parsed.success === false) {
      throw new Error(extractErrorMessage(text, parsed))
    }
    return
  }

  throw new Error('上传失败：缺少 IPC 通道')
}

export async function crawlUrlToBackend(url: string): Promise<void> {
  const extractErrorMessage = (rawText: string, parsed: any): string => {
    if (parsed && typeof parsed === 'object') {
      const detail = (parsed as any).detail
      if (typeof detail === 'string' && detail.trim()) return detail
      const err = (parsed as any).error
      if (typeof err === 'string' && err.trim()) return err
      const msg = (parsed as any).message
      if (typeof msg === 'string' && msg.trim()) return msg
    }
    const t = (rawText || '').trim()
    return t || '采集失败'
  }

  // Electron 环境：优先走 IPC（避免开发模式下 Vite proxy 固定端口导致命中错误后端）
  if (window.electronAPI?.httpCrawlUrl) {
    const resp = await window.electronAPI.httpCrawlUrl(url)
    const text = resp?.data || ''
    let parsed: any = null
    try {
      parsed = text ? JSON.parse(text) : null
    } catch {
      parsed = null
    }
    if (!resp?.ok) throw new Error(resp?.error || extractErrorMessage(text, parsed))
    if (parsed && typeof parsed === 'object' && parsed.success === false) {
      throw new Error(extractErrorMessage(text, parsed))
    }
    return
  }

  // 开发环境（纯浏览器/Vite）：走相对路径（依赖 Vite proxy）
  if (isDev) {
    const apiBase = await getResolvedApiBase()
    const fd = new FormData()
    fd.append('url', url)
    const resp = await fetch(`${apiBase}/api/ingest/url`, { method: 'POST', body: fd })
    const text = await resp.text().catch(() => '')
    let parsed: any = null
    try {
      parsed = text ? JSON.parse(text) : null
    } catch {
      parsed = null
    }
    if (!resp.ok) throw new Error(extractErrorMessage(text, parsed))
    if (parsed && typeof parsed === 'object' && parsed.success === false) {
      throw new Error(extractErrorMessage(text, parsed))
    }
    return
  }

  throw new Error('采集失败：缺少 IPC 通道')
}
