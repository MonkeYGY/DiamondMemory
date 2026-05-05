import { defineStore } from 'pinia'
import { ref } from 'vue'
import { fetchTasks, enqueueTask, pauseTask, resumeTask, cancelTask } from '../api/backend'

export const useTasksStore = defineStore('tasks', () => {
  const items = ref<any[]>([])
  const loading = ref(false)
  let timer: number | null = null
  // 仅展示“活跃任务”，用于任务面板自动弹出/自动隐藏
  const ACTIVE_STATUSES = 'running,queued,blocked,paused'

  function isStartupNetworkError(err: unknown): boolean {
    const msg = err instanceof Error ? err.message : String(err)
    const lower = msg.toLowerCase()
    return (
      lower.includes('failed to fetch') ||
      lower.includes('fetch failed') ||
      lower.includes('networkerror') ||
      lower.includes('econnrefused') ||
      lower.includes('err_connection_refused')
    )
  }

  async function refresh() {
    loading.value = true
    try {
      // 任务面板需求：无任务/任务结束则自动关闭，因此这里仅拉取活跃任务
      const data = await fetchTasks(ACTIVE_STATUSES, 50)
      items.value = data.items || []
    } catch (err) {
      // 启动阶段后端尚未 ready 时会出现短暂的连接失败：这是预期现象，避免触发全局 unhandledrejection/toast
      if (!isStartupNetworkError(err)) {
        console.error('[tasks.refresh] failed', err)
      }
    } finally {
      loading.value = false
    }
  }

  function startPolling(intervalMs = 1500) {
    if (timer) return
    timer = window.setInterval(refresh, intervalMs)
    // 立即拉取一次（内部已做错误兜底）
    void refresh()
  }

  function stopPolling() {
    if (!timer) return
    window.clearInterval(timer)
    timer = null
  }

  async function enqueue(type: string, power_mode = 'normal', params: any = {}) {
    const res = await enqueueTask({ type, power_mode, params })
    await refresh()
    return res
  }

  async function pause(id: string) {
    await pauseTask(id)
    await refresh()
  }

  async function resume(id: string) {
    await resumeTask(id)
    await refresh()
  }

  async function cancel(id: string) {
    await cancelTask(id)
    await refresh()
  }

  return { items, loading, refresh, startPolling, stopPolling, enqueue, pause, resume, cancel }
})
