import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { apiRequest } from '../api/backend'

export interface MemoryStats {
  totalMemories: number
  todayCount: number
  categoryCount: number
  systemStatus: string
  l0Count: number
  l1Count: number
  l2Count: number
  l3Count: number
  lastConsolidation: string
}

export const useMemoryStore = defineStore('memory', () => {
  const memories = ref<any[]>([])
  const loading = ref(false)
  const selectedMemory = ref<any>(null)

  const stats = ref<MemoryStats>({
    totalMemories: 0,
    todayCount: 0,
    categoryCount: 0,
    systemStatus: '正常',
    l0Count: 0,
    l1Count: 0,
    l2Count: 0,
    l3Count: 0,
    lastConsolidation: ''
  })

  const isOrganizing = ref(false)
  const organizeResult = ref<any>(null)
  const organizeError = ref<string | null>(null)
  let organizeTimer: number | null = null

  const memoryCount = computed(() => memories.value.length)

  async function fetchMemories() {
    loading.value = true
    try {
      const data = await apiRequest<any[]>('/api/memories')
      memories.value = Array.isArray(data) ? data : []
      stats.value.totalMemories = memories.value.length
    } catch (error) {
      console.error('获取记忆列表失败:', error)
    } finally {
      loading.value = false
    }
  }

  async function fetchStats() {
    try {
      const data = await apiRequest<any>('/api/memories/stats')
      stats.value = {
        totalMemories: data.totalMemories || stats.value.totalMemories,
        todayCount: data.todayCount || 0,
        categoryCount: data.categoryCount || 0,
        systemStatus: data.systemStatus || '正常',
        l0Count: data.l0Count || 0,
        l1Count: data.l1Count || 0,
        l2Count: data.l2Count || 0,
        l3Count: data.l3Count || 0,
        lastConsolidation: data.lastConsolidation || ''
      }
    } catch {
      stats.value.systemStatus = '后端未连接'
    }
  }

  function _startOrganizePolling() {
    if (organizeTimer) return
    organizeTimer = window.setInterval(async () => {
      const status = await checkOrganizeStatus()
      if (status.finished || !isOrganizing.value) {
        if (organizeTimer) {
          window.clearInterval(organizeTimer)
          organizeTimer = null
        }
      }
    }, 3000)
  }

  async function startOrganize(): Promise<{ status: string; message?: string }> {
    if (isOrganizing.value) {
      return { status: 'already_running', message: '整理任务正在执行中' }
    }
    isOrganizing.value = true
    organizeResult.value = null
    organizeError.value = null
    try {
      const result = await apiRequest<{ status: string; message?: string }>('/api/memory/organize', { method: 'POST' })
      _startOrganizePolling()
      return result
    } catch (error: any) {
      isOrganizing.value = false
      organizeError.value = error.message
      return { status: 'error', message: error.message }
    }
  }

  async function checkOrganizeStatus() {
    try {
      const data = await apiRequest<{
        running: boolean
        started_at: number | null
        result: any
        error: string | null
      }>('/api/memory/organize/status')
      const wasRunning = isOrganizing.value
      isOrganizing.value = data.running
      
      // 如果后端正在运行，但前端还没开始轮询，启动轮询
      if (data.running && !organizeTimer) {
        _startOrganizePolling()
      }

      if (data.result) {
        organizeResult.value = data.result
      }
      if (data.error) {
        organizeError.value = data.error
      }
      if (wasRunning && !data.running) {
        return { finished: true, result: data.result, error: data.error }
      }
      return { finished: false }
    } catch {
      return { finished: false }
    }
  }

  const isQuickOrganizing = ref(false)
  const quickOrganizeResult = ref<any>(null)
  const quickOrganizeError = ref<string | null>(null)
  let quickOrganizeTimer: number | null = null

  function _startQuickOrganizePolling() {
    if (quickOrganizeTimer) return
    quickOrganizeTimer = window.setInterval(async () => {
      const status = await checkQuickOrganizeStatus()
      if (status.finished || !isQuickOrganizing.value) {
        if (quickOrganizeTimer) {
          window.clearInterval(quickOrganizeTimer)
          quickOrganizeTimer = null
        }
      }
    }, 3000)
  }

  async function startQuickOrganize() {
    if (isQuickOrganizing.value) {
      return { status: 'already_running', message: '快速整理任务正在执行中' }
    }
    isQuickOrganizing.value = true
    quickOrganizeResult.value = null
    quickOrganizeError.value = null
    try {
      const result = await apiRequest<{ status: string; message?: string }>('/api/memory/organize/quick', { method: 'POST' })
      _startQuickOrganizePolling()
      return result
    } catch (error: any) {
      isQuickOrganizing.value = false
      quickOrganizeError.value = error.message
      return { status: 'error', message: error.message }
    }
  }

  async function checkQuickOrganizeStatus() {
    try {
      const data = await apiRequest<{
        running: boolean
        started_at: number | null
        result: any
        error: string | null
      }>('/api/memory/organize/quick/status')
      const wasRunning = isQuickOrganizing.value
      isQuickOrganizing.value = data.running

      // 如果后端正在运行，但前端还没开始轮询，启动轮询
      if (data.running && !quickOrganizeTimer) {
        _startQuickOrganizePolling()
      }

      if (data.result) {
        quickOrganizeResult.value = data.result
      }
      if (data.error) {
        quickOrganizeError.value = data.error
      }
      if (wasRunning && !data.running) {
        return { finished: true, result: data.result, error: data.error }
      }
      return { finished: false }
    } catch {
      return { finished: false }
    }
  }

  return {
    memories,
    loading,
    selectedMemory,
    stats,
    memoryCount,
    isOrganizing,
    organizeResult,
    organizeError,
    isQuickOrganizing,
    quickOrganizeResult,
    quickOrganizeError,
    fetchMemories,
    fetchStats,
    startOrganize,
    checkOrganizeStatus,
    startQuickOrganize,
    checkQuickOrganizeStatus
  }
})
