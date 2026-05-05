import { describe, expect, it } from 'vitest'

import { performControlledBackendRestart, waitForBackendToStop } from '../backend-restart-helpers.js'

describe('backend-restart-helpers', () => {
  it('performControlledBackendRestart：先 stop 再 start', async () => {
    const steps: string[] = []

    const result = await performControlledBackendRestart({
      waitMs: 0,
      stopBackend: async () => {
        steps.push('stop:start')
        await new Promise(resolve => setTimeout(resolve, 10))
        steps.push('stop:done')
      },
      startBackend: async () => {
        steps.push('start:called')
        return true
      }
    })

    expect(result).toBe(true)
    expect(steps).toEqual(['stop:start', 'stop:done', 'start:called'])
  })

  it('waitForBackendToStop：持续轮询直到 backend 停止', async () => {
    const checks: boolean[] = [true, true, false]

    const stopped = await waitForBackendToStop(
      async () => checks.shift() ?? false,
      { pollMs: 0, maxAttempts: 5 }
    )

    expect(stopped).toBe(true)
    expect(checks.length).toBe(0)
  })
})
