import { describe, expect, it } from 'vitest'

import { startBackendWithBackgroundWarmup } from '../backend-startup.js'

describe('startBackendWithBackgroundWarmup', () => {
  it('不会等待 warmup 完成才 spawn backend', async () => {
    const steps: string[] = []
    let ollamaFinished = false

    const result = await startBackendWithBackgroundWarmup({
      startWarmup: async () => {
        steps.push('warmup:start')
        await new Promise(resolve => setTimeout(resolve, 200))
        steps.push('warmup:done')
        ollamaFinished = true
      },
      resolvePort: async () => {
        steps.push('port')
        return 18000
      },
      spawnBackend: async (port: number) => {
        steps.push(`spawn:${port}`)
      },
      waitForBackend: async () => {
        steps.push('wait')
        return true
      }
    })

    expect(result.ready).toBe(true)
    expect(result.port).toBe(18000)
    expect(steps.slice(0, 3)).toEqual(['warmup:start', 'port', 'spawn:18000'])
    expect(ollamaFinished).toBe(false)
    await result.warmupPromise
    expect(steps).toEqual(['warmup:start', 'port', 'spawn:18000', 'wait', 'warmup:done'])
  })

  it('复用已有 warmup promise', async () => {
    const steps: string[] = []

    const existingWarmup = (async () => {
      steps.push('reuse:start')
      await new Promise(resolve => setTimeout(resolve, 200))
      steps.push('reuse:done')
    })()

    const result = await startBackendWithBackgroundWarmup({
      existingWarmupPromise: existingWarmup,
      startWarmup: async () => {
        steps.push('should-not-run')
      },
      resolvePort: async () => 19000,
      spawnBackend: async () => {
        steps.push('spawn')
      },
      waitForBackend: async () => true
    })

    await result.warmupPromise
    expect(steps).toEqual(['reuse:start', 'spawn', 'reuse:done'])
  })
})
