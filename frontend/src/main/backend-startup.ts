export interface StartBackendWithBackgroundWarmupOptions {
  existingWarmupPromise?: Promise<void> | null
  startWarmup: () => Promise<void>
  resolvePort: () => Promise<number>
  spawnBackend: (port: number) => Promise<void> | void
  waitForBackend: () => Promise<boolean>
}

export interface StartBackendWithBackgroundWarmupResult {
  port: number
  ready: boolean
  warmupPromise: Promise<void>
}

export async function startBackendWithBackgroundWarmup(
  options: StartBackendWithBackgroundWarmupOptions
): Promise<StartBackendWithBackgroundWarmupResult> {
  const warmupPromise = options.existingWarmupPromise ?? options.startWarmup()
  const port = await options.resolvePort()
  await options.spawnBackend(port)
  const ready = await options.waitForBackend()

  return {
    port,
    ready,
    warmupPromise
  }
}
