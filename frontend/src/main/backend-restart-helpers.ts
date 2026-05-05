export interface ControlledRestartOptions {
  waitMs?: number
  stopBackend: () => Promise<void>
  startBackend: () => Promise<boolean>
}

export interface WaitForBackendStopOptions {
  pollMs?: number
  maxAttempts?: number
}

function delay(ms: number): Promise<void> {
  return new Promise(resolve => setTimeout(resolve, ms))
}

export async function performControlledBackendRestart({
  waitMs = 500,
  stopBackend,
  startBackend,
}: ControlledRestartOptions): Promise<boolean> {
  await stopBackend()
  if (waitMs > 0) {
    await delay(waitMs)
  }
  return startBackend()
}

export async function waitForBackendToStop(
  isBackendRunning: () => Promise<boolean>,
  {
    pollMs = 250,
    maxAttempts = 40,
  }: WaitForBackendStopOptions = {},
): Promise<boolean> {
  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    const running = await isBackendRunning()
    if (!running) {
      return true
    }
    if (pollMs > 0) {
      await delay(pollMs)
    }
  }
  return false
}
