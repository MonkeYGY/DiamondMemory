import { onUnmounted } from 'vue'

export function useInterval(callback: () => void, delay: number): { start: () => void; stop: () => void } {
  let intervalId: number | null = null

  function start() {
    stop()
    intervalId = window.setInterval(callback, delay)
  }

  function stop() {
    if (intervalId !== null) {
      clearInterval(intervalId)
      intervalId = null
    }
  }

  onUnmounted(stop)

  return { start, stop }
}

export function useTimeout(callback: () => void, delay: number): { start: () => void; stop: () => void } {
  let timeoutId: number | null = null

  function start() {
    stop()
    timeoutId = window.setTimeout(() => {
      timeoutId = null
      callback()
    }, delay)
  }

  function stop() {
    if (timeoutId !== null) {
      clearTimeout(timeoutId)
      timeoutId = null
    }
  }

  onUnmounted(stop)

  return { start, stop }
}
