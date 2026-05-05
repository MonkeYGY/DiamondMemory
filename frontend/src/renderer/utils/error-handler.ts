import type { App } from 'vue'
import { useToast } from '../composables/useToast'

export function setupGlobalErrorHandler(app: App) {
  app.config.errorHandler = (err, _instance, info) => {
    console.error('[Vue Error]', info, err)
    try {
      const toast = useToast()
      toast.error(`界面异常: ${err instanceof Error ? err.message : String(err)}`)
    } catch {
      // toast may not be available during bootstrap
    }
  }

  window.addEventListener('error', (event) => {
    console.error('[Window Error]', event.message, event.filename, event.lineno)
    if (event.error && event.error.name !== 'NetworkError') {
      try {
        const toast = useToast()
        toast.error(`运行时错误: ${event.message}`)
      } catch {
        // silent
      }
    }
  })

  window.addEventListener('unhandledrejection', (event) => {
    console.error('[Unhandled Promise]', event.reason)
    const msg = event.reason instanceof Error ? event.reason.message : String(event.reason)
    const lower = msg.toLowerCase()
    // 常见“网络/后端未启动”类异常：启动阶段可能短暂出现（尤其是轮询任务列表/状态），不应弹 toast 干扰用户
    if (
      !lower.includes('failed to fetch') &&
      !lower.includes('fetch failed') &&
      !lower.includes('networkerror') &&
      !lower.includes('econnrefused') &&
      !lower.includes('err_connection_refused')
    ) {
      try {
        const toast = useToast()
        toast.error(`异步异常: ${msg}`)
      } catch {
        // silent
      }
    }
  })
}
