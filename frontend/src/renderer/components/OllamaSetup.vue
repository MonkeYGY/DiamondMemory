<template>
  <div class="ollama-setup-overlay" v-if="visible">
    <div class="ollama-setup-card">
      <button class="close-btn" @click="closeSetup" title="关闭">✕</button>
      <div class="setup-header">
        <div class="setup-icon" :class="iconClass">{{ iconText }}</div>
        <h2 class="setup-title">{{ titleText }}</h2>
        <p class="setup-desc">{{ descText }}</p>
      </div>

      <div class="setup-body" v-if="status === 'downloading'">
        <div class="progress-bar-wrapper">
          <div class="progress-bar">
            <div class="progress-fill" :class="{ 'progress-indeterminate': progress < 0 }" :style="progress >= 0 ? { width: progress + '%' } : {}"></div>
          </div>
          <span class="progress-text">{{ progress >= 0 ? progress + '%' : '...' }}</span>
        </div>
        <div class="progress-details">
          <span>{{ formatSize(downloaded) }}{{ total > 0 ? ' / ' + formatSize(total) : '' }}</span>
          <span>{{ speed }}</span>
        </div>
      </div>

      <div class="setup-body" v-else-if="status === 'failed'">
        <div class="error-message">{{ errorMessage }}</div>
      </div>

      <div class="setup-body" v-else-if="status === 'completed'">
        <div class="success-message">Ollama 下载完成，正在启动服务...</div>
      </div>

      <div class="setup-body" v-else-if="status === 'idle'">
        <div class="info-list">
          <div class="info-item">
            <span class="info-label">平台</span>
            <span class="info-value">{{ platformInfo }}</span>
          </div>
          <div class="info-item">
            <span class="info-label">引擎大小</span>
            <span class="info-value">约 100 MB</span>
          </div>
        </div>
      </div>

      <div class="setup-tips">
        <div class="tip-item">Ollama 是本地 AI 推理引擎，下载后无需再次安装</div>
        <div class="tip-item">AI 模型文件需在应用内单独下载</div>
      </div>

      <div class="setup-actions">
        <button
          v-if="status === 'idle' || status === 'failed'"
          class="btn-primary"
          @click="startDownload"
          :disabled="isStarting"
        >
          {{ isStarting ? '启动中...' : status === 'failed' ? '重新下载' : '开始下载' }}
        </button>

        <button
          v-if="status === 'downloading'"
          class="btn-secondary"
          @click="cancelDownload"
        >
          取消下载
        </button>

        <button
          v-if="status === 'failed'"
          class="btn-secondary"
          @click="skipSetup"
        >
          跳过，稍后安装
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { apiRequest } from '../api/backend'

defineProps<{
  visible: boolean
}>()

const emit = defineEmits<{
  (e: 'complete'): void
  (e: 'skip'): void
  (e: 'close'): void
}>()

const status = ref<'idle' | 'downloading' | 'completed' | 'failed' | 'cancelled'>('idle')
const progress = ref(0)
const downloaded = ref(0)
const total = ref(0)
const speed = ref('0 B/s')
const errorMessage = ref('')
const isStarting = ref(false)
const platformInfo = ref(`${navigator.platform}`)
let pollTimer: ReturnType<typeof setInterval> | null = null

const iconClass = computed(() => {
  switch (status.value) {
    case 'downloading': return 'icon-downloading'
    case 'completed': return 'icon-success'
    case 'failed': return 'icon-error'
    default: return 'icon-info'
  }
})

const iconText = computed(() => {
  switch (status.value) {
    case 'downloading': return '⬇'
    case 'completed': return '✓'
    case 'failed': return '✕'
    default: return '⚙'
  }
})

const titleText = computed(() => {
  switch (status.value) {
    case 'idle': return '安装 AI 引擎'
    case 'downloading': return '正在下载 Ollama'
    case 'completed': return '安装完成'
    case 'failed': return '安装失败'
    case 'cancelled': return '已取消'
    default: return '安装 AI 引擎'
  }
})

const descText = computed(() => {
  switch (status.value) {
    case 'idle': return '首次使用需要下载 Ollama 推理引擎'
    case 'downloading': return '正在下载适合当前系统的版本'
    case 'completed': return 'Ollama 引擎已就绪'
    case 'failed': return '下载失败，请检查网络连接后重试'
    case 'cancelled': return '下载已取消'
    default: return ''
  }
})

onMounted(async () => {
  await checkInstallStatus()
})

onUnmounted(() => {
  stopPolling()
})

async function checkInstallStatus() {
  try {
    const data = await apiRequest<{ installed: boolean; platform: string; architecture: string }>('/api/ollama/install-status')
    platformInfo.value = `${data.platform} ${data.architecture}`
    if (data.installed) {
      status.value = 'completed'
      emit('complete')
    }
  } catch {
    // ignore
  }
}

async function startDownload() {
  isStarting.value = true
  try {
    await apiRequest<{ status: string }>('/api/ollama/download', {
      method: 'POST'
    })
    status.value = 'downloading'
    startPolling()
  } catch (err: any) {
    errorMessage.value = err.message || '启动下载失败'
    status.value = 'failed'
  } finally {
    isStarting.value = false
  }
}

async function cancelDownload() {
  try {
    await apiRequest<{ status: string }>('/api/ollama/cancel-download', {
      method: 'POST'
    })
    status.value = 'cancelled'
    stopPolling()
  } catch {
    // ignore
  }
}

function startPolling() {
  stopPolling()
  pollTimer = setInterval(async () => {
    try {
      const data = await apiRequest<{
        status: string
        progress: number
        downloaded: number
        total: number
        speed: string
        error: string | null
      }>('/api/ollama/download-progress')

      progress.value = data.progress || 0
      downloaded.value = data.downloaded || 0
      total.value = data.total || 0
      speed.value = data.speed || ''

      if (data.status === 'completed') {
        status.value = 'completed'
        stopPolling()
        emit('complete')
      } else if (data.status === 'failed') {
        status.value = 'failed'
        errorMessage.value = data.error || '下载失败'
        stopPolling()
      } else if (data.status === 'cancelled') {
        status.value = 'cancelled'
        stopPolling()
      }
    } catch {
      // ignore polling errors
    }
  }, 1000)
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

function skipSetup() {
  stopPolling()
  emit('skip')
}

function closeSetup() {
  stopPolling()
  emit('close')
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`
  return `${(bytes / 1024 / 1024 / 1024).toFixed(2)} GB`
}
</script>

<style scoped>
.ollama-setup-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: var(--color-overlay-light);
  backdrop-filter: blur(4px);
  z-index: 2000;
  display: flex;
  align-items: center;
  justify-content: center;
}

.ollama-setup-card {
  background: var(--color-surface);
  border-radius: 16px;
  padding: 36px 40px;
  max-width: 460px;
  width: 90%;
  box-shadow: 0 10px 40px rgba(0, 0, 0, 0.15);
  border: 1px solid var(--color-border);
  position: relative;
}

.close-btn {
  position: absolute;
  top: 12px;
  right: 12px;
  width: 32px;
  height: 32px;
  border: none;
  background: transparent;
  color: var(--color-text-tertiary);
  font-size: 18px;
  cursor: pointer;
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.15s;
  line-height: 1;
}

.close-btn:hover {
  background: var(--color-hover-bg);
  color: var(--color-text);
}

.setup-header {
  text-align: center;
  margin-bottom: 28px;
}

.setup-icon {
  font-size: 44px;
  margin-bottom: 12px;
  line-height: 1;
}

.icon-downloading {
  animation: pulse 1.5s ease-in-out infinite;
}

.icon-success {
  color: var(--color-success);
}

.icon-error {
  color: var(--color-error);
}

.icon-info {
  color: var(--color-primary);
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

.setup-title {
  font-size: 20px;
  font-weight: 600;
  color: var(--color-text);
  margin: 0 0 8px;
}

.setup-desc {
  font-size: 14px;
  color: var(--color-text-secondary);
  margin: 0;
}

.setup-body {
  margin-bottom: 24px;
}

.progress-bar-wrapper {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
}

.progress-bar {
  flex: 1;
  height: 8px;
  background: var(--color-surface-secondary);
  border-radius: 4px;
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background: var(--color-primary);
  border-radius: 4px;
  transition: width 0.3s ease;
}

.progress-indeterminate {
  width: 30% !important;
  animation: indeterminate 1.5s ease-in-out infinite;
}

@keyframes indeterminate {
  0% { transform: translateX(-100%); }
  100% { transform: translateX(400%); }
}

.progress-text {
  font-size: 13px;
  font-weight: 600;
  color: var(--color-primary);
  min-width: 36px;
  text-align: right;
}

.progress-details {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
  color: var(--color-text-tertiary);
}

.error-message {
  padding: 12px 16px;
  background: var(--color-error-bg);
  color: var(--color-error-text);
  border-radius: 8px;
  font-size: 13px;
  line-height: 1.5;
}

.success-message {
  padding: 12px 16px;
  background: var(--color-success-bg);
  color: var(--color-success-text);
  border-radius: 8px;
  font-size: 13px;
  text-align: center;
}

.info-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.info-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px;
  background: var(--color-surface-secondary);
  border-radius: 6px;
}

.info-label {
  font-size: 13px;
  color: var(--color-text-secondary);
}

.info-value {
  font-size: 13px;
  font-weight: 500;
  color: var(--color-text);
}

.setup-tips {
  margin-bottom: 24px;
  padding: 12px 16px;
  background: var(--color-surface-secondary);
  border-radius: 8px;
}

.tip-item {
  font-size: 12px;
  color: var(--color-text-tertiary);
  line-height: 1.6;
  padding-left: 12px;
  position: relative;
}

.tip-item::before {
  content: '•';
  position: absolute;
  left: 0;
  color: var(--color-text-tertiary);
}

.setup-actions {
  display: flex;
  gap: 12px;
  justify-content: center;
}

.btn-primary {
  padding: 10px 24px;
  background: var(--color-primary);
  color: var(--color-text-on-primary);
  border: none;
  border-radius: 8px;
  cursor: pointer;
  font-size: 14px;
  font-weight: 500;
  transition: background 0.15s;
}

.btn-primary:hover {
  background: var(--color-primary-hover);
}

.btn-primary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-secondary {
  padding: 10px 24px;
  background: transparent;
  color: var(--color-text-secondary);
  border: 1px solid var(--color-border);
  border-radius: 8px;
  cursor: pointer;
  font-size: 14px;
  font-weight: 500;
  transition: all 0.15s;
}

.btn-secondary:hover {
  background: var(--color-hover-bg);
  border-color: var(--color-border-hover);
}
</style>
