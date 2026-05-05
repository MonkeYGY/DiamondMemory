import { ipcMain, WebContents } from 'electron'
import { backendManager } from './backend-manager.js'

type BodyType = 'json' | 'text' | 'binary'

export interface HttpRequestPayload {
  method: string
  path: string
  headers?: Record<string, string>
  bodyType?: BodyType
  // renderer → main 通过 structured clone 传输：
  // - json/text：string 或 object（json 会 stringify）
  // - binary：ArrayBuffer
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
  headers.forEach((v, k) => {
    obj[k.toLowerCase()] = v
  })
  return obj
}

function isAllowedPath(path: string): boolean {
  // 仅允许访问后端路由，避免滥用为任意请求代理
  return /^\/(api|health)(\/|$)/.test(path)
}

function sanitizeHeaders(input?: Record<string, string>): Record<string, string> {
  const out: Record<string, string> = {}
  if (!input) return out
  for (const [k, v] of Object.entries(input)) {
    const key = k.toLowerCase()
    // 这些头由 fetch/底层处理或有安全风险
    if (['host', 'origin', 'referer', 'connection', 'content-length'].includes(key)) continue
    out[key] = String(v)
  }
  return out
}

function resolveBackendBase(): string {
  const port = backendManager.getPort()
  return `http://127.0.0.1:${port}`
}

function clampTimeoutMs(v: number): number {
  if (!Number.isFinite(v)) return 30000
  return Math.max(1000, Math.min(v, 120000))
}

const streamControllers = new Map<string, AbortController>()

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
      const timeoutMs = clampTimeoutMs(payload.timeoutMs ?? 30000)
      const t = setTimeout(() => controller.abort(), timeoutMs)

      let body: any = undefined
      if (payload.bodyType === 'json') {
        headers['content-type'] = headers['content-type'] || 'application/json'
        body = typeof payload.body === 'string' ? payload.body : JSON.stringify(payload.body ?? {})
      } else if (payload.bodyType === 'text') {
        body = typeof payload.body === 'string' ? payload.body : String(payload.body ?? '')
      } else if (payload.bodyType === 'binary') {
        body = payload.body ? Buffer.from(payload.body) : undefined
      } else if (payload.body != null) {
        // 默认按 text 处理（兼容旧代码传 JSON.stringify(...)）
        body = typeof payload.body === 'string' ? payload.body : JSON.stringify(payload.body)
      }

      const resp = await fetch(url, { method, headers, body, signal: controller.signal })
      clearTimeout(t)

      const respHeaders = toHeadersObject(resp.headers)
      const contentType = resp.headers.get('content-type') || ''

      if (contentType.includes('application/json')) {
        const data = await resp.json().catch(() => null)
        return { ok: resp.ok, status: resp.status, headers: respHeaders, dataType: 'json', data }
      }

      const data = await resp.text().catch(() => '')
      return { ok: resp.ok, status: resp.status, headers: respHeaders, dataType: 'text', data }
    } catch (e: any) {
      return { ok: false, status: 500, headers: {}, dataType: 'text', data: '', error: e?.message || 'proxy error' }
    }
  })

  ipcMain.handle('http:stream:start', async (_evt, payload: HttpRequestPayload) => {
    const streamId = `${Date.now()}-${Math.random().toString(16).slice(2)}`
    const wc = options.getWebContents()
    if (!wc) return { ok: false, streamId: '', error: 'no webContents' }

    if (!payload?.path || typeof payload.path !== 'string' || !payload.path.startsWith('/')) {
      return { ok: false, streamId: '', error: 'invalid path' }
    }
    if (!isAllowedPath(payload.path)) {
      return { ok: false, streamId: '', error: 'path forbidden' }
    }

    const controller = new AbortController()
    streamControllers.set(streamId, controller)

    ;(async () => {
      try {
        const url = `${resolveBackendBase()}${payload.path}`
        const headers = sanitizeHeaders(payload.headers)
        const method = (payload.method || 'POST').toUpperCase()

        let body: any = undefined
        if (payload.bodyType === 'json') {
          headers['content-type'] = headers['content-type'] || 'application/json'
          body = typeof payload.body === 'string' ? payload.body : JSON.stringify(payload.body ?? {})
        } else if (payload.body != null) {
          body = typeof payload.body === 'string' ? payload.body : JSON.stringify(payload.body)
        }

        const resp = await fetch(url, { method, headers, body, signal: controller.signal })
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

  ipcMain.handle(
    'http:upload:file',
    async (_evt, payload: { filename: string; mime: string; buffer: ArrayBuffer; disturbFree?: boolean }) => {
      try {
        const url = `${resolveBackendBase()}/api/ingest/file`

        const FormDataCtor: any = (globalThis as any).FormData
        const BlobCtor: any = (globalThis as any).Blob
        if (!FormDataCtor || !BlobCtor) {
          return { ok: false, status: 500, data: '', error: 'FormData/Blob not available in main process' }
        }

        const fd = new FormDataCtor()
        const blob = new BlobCtor([Buffer.from(payload.buffer)], {
          type: payload.mime || 'application/octet-stream'
        })
        fd.set('file', blob, payload.filename || 'file')
        // 后端参数名为 disturb_free（snake_case）
        fd.set('disturb_free', payload.disturbFree ? 'true' : 'false')

        const resp = await fetch(url, { method: 'POST', body: fd as any })
        const text = await resp.text().catch(() => '')
        return { ok: resp.ok, status: resp.status, data: text }
      } catch (e: any) {
        return { ok: false, status: 500, data: '', error: e?.message || 'upload error' }
      }
    }
  )

  ipcMain.handle('http:crawl:url', async (_evt, urlToCrawl: string) => {
    try {
      const url = `${resolveBackendBase()}/api/ingest/url`

      const FormDataCtor: any = (globalThis as any).FormData
      if (!FormDataCtor) {
        return { ok: false, status: 500, data: '', error: 'FormData not available in main process' }
      }

      const fd = new FormDataCtor()
      fd.set('url', urlToCrawl)
      const resp = await fetch(url, { method: 'POST', body: fd as any })
      const text = await resp.text().catch(() => '')
      return { ok: resp.ok, status: resp.status, data: text }
    } catch (e: any) {
      return { ok: false, status: 500, data: '', error: e?.message || 'crawl error' }
    }
  })
}
