// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest'

declare global {
  interface Window {
    electronAPI?: any
  }
}

beforeEach(() => {
  vi.restoreAllMocks()
  ;(globalThis as any).fetch = vi.fn(async () => {
    throw new Error('fetch should not be called when electronAPI is available')
  })
  window.electronAPI = undefined
})

describe('renderer backend api routing (dev mode)', () => {
  it('apiRequest 在 dev + electronAPI.httpRequest 时应走 IPC（避免 Vite proxy 固定端口）', async () => {
    const httpRequest = vi.fn(async () => ({ ok: true, status: 200, data: { ok: 1 } }))
    window.electronAPI = { httpRequest }

    const { apiRequest } = await import('./backend')
    const data = await apiRequest<{ ok: number }>('/api/system/capabilities')

    expect(data.ok).toBe(1)
    expect(httpRequest).toHaveBeenCalledTimes(1)
    expect((globalThis as any).fetch).not.toHaveBeenCalled()
  })

  it('uploadFileToBackend 在 dev + electronAPI.httpUploadFile 时应走 IPC', async () => {
    const httpUploadFile = vi.fn(async () => ({ ok: true, status: 200, data: 'ok' }))
    window.electronAPI = { httpUploadFile }

    const { uploadFileToBackend } = await import('./backend')
    // jsdom 的 File/Blob 在不同版本下可能缺少 arrayBuffer，这里用最小可用桩对象即可
    const file: any = {
      name: 'hello.txt',
      type: 'text/plain',
      arrayBuffer: async () => new TextEncoder().encode('hello').buffer
    }

    await uploadFileToBackend(file)

    expect(httpUploadFile).toHaveBeenCalledTimes(1)
    expect((globalThis as any).fetch).not.toHaveBeenCalled()
  })

  it('chatStreamRequest 在 dev + electronAPI.httpStreamStart 时应走 IPC 流式通道', async () => {
    const httpStreamStart = vi.fn(async () => ({ ok: true, streamId: 's1' }))
    window.electronAPI = {
      httpStreamStart,
      httpStreamAbort: vi.fn(async () => true),
      onHttpStreamChunk: vi.fn(() => () => {}),
      onHttpStreamDone: vi.fn(() => () => {}),
      onHttpStreamError: vi.fn(() => () => {})
    }

    const { chatStreamRequest } = await import('./backend')
    await chatStreamRequest([{ role: 'user', content: 'hi' }], {
      onChunk: () => {},
      onDone: () => {},
      onError: () => {}
    })

    expect(httpStreamStart).toHaveBeenCalledTimes(1)
    expect((globalThis as any).fetch).not.toHaveBeenCalled()
  })

  it('chatSummaryRequest 在 dev + electronAPI.httpRequest 时应走 IPC', async () => {
    const httpRequest = vi.fn(async () => ({ ok: true, status: 200, data: { summary_text: 'ok' } }))
    window.electronAPI = { httpRequest }

    const { chatSummaryRequest } = await import('./backend')
    const data = await chatSummaryRequest({ dropped_messages: [{ role: 'user', content: 'hi' }] })

    expect(data.summary_text).toBe('ok')
    expect(httpRequest).toHaveBeenCalledTimes(1)
  })
})
