<template>
  <transition name="update-fade">
    <div v-if="showUpdateDialog" class="update-overlay">
      <div class="update-dialog">
        <div class="update-header">
          <div class="update-icon">🔄</div>
          <div class="update-title">
            <h3>{{ dialogTitle }}</h3>
            <span class="update-version">{{ dialogSubtitle }}</span>
          </div>
          <button v-if="allowClose" class="close-btn" @click="closeDialog">×</button>
        </div>

        <div class="update-body">
          <div v-if="updateState === 'checking'" class="update-status">
            <div class="loading-spinner"></div>
            <p>正在检查更新...</p>
          </div>

          <div v-else-if="updateState === 'available'" class="update-status">
            <p class="update-desc">发现新版本，是否立即下载？</p>
            <div v-if="updateInfo.releaseNotes" class="release-notes">
              <h4>更新内容：</h4>
              <div class="notes-content" v-html="formatReleaseNotes(updateInfo.releaseNotes)"></div>
            </div>
          </div>

          <div v-else-if="updateState === 'downloading'" class="update-status">
            <p>正在下载更新...</p>
            <div class="progress-container">
              <div class="progress-bar">
                <div class="progress-fill" :style="{ width: downloadProgress.percent + '%' }"></div>
              </div>
              <div class="progress-info">
                <span class="progress-percent">{{ downloadProgress.percent }}%</span>
                <span class="progress-speed">{{ downloadProgress.speed }}</span>
                <span class="progress-size">{{ downloadProgress.transferred }} / {{ downloadProgress.total }}</span>
              </div>
            </div>
          </div>

          <div v-else-if="updateState === 'downloaded'" class="update-status">
            <p>更新已下载完成，需要重启应用以安装更新。</p>
            <div v-if="updateInfo.releaseNotes" class="release-notes">
              <h4>版本 {{ updateInfo.version }} 更新内容：</h4>
              <div class="notes-content" v-html="formatReleaseNotes(updateInfo.releaseNotes)"></div>
            </div>
          </div>

          <div v-else-if="updateState === 'error'" class="update-status error">
            <p>⚠️ {{ updateInfo.releaseNotes || '检查更新失败' }}</p>
          </div>

          <div v-else-if="updateState === 'latest'" class="update-status">
            <p>✅ {{ updateInfo.message || '当前已是最新版本' }}</p>
          </div>
        </div>

        <div class="update-footer">
          <button v-if="showCancelBtn" class="btn-secondary" @click="closeDialog">{{ updateState === 'checking' ? '取消检查' : '暂不更新' }}</button>
          <button v-if="showDownloadBtn" class="btn-primary" @click="downloadUpdate" :disabled="isDownloading">
            {{ isDownloading ? '下载中...' : '立即下载' }}
          </button>
          <button v-if="showInstallBtn" class="btn-primary" @click="installUpdate">
            重启并安装
          </button>
        </div>
      </div>
    </div>
  </transition>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import DOMPurify from 'dompurify'

type UpdateState = 'idle' | 'checking' | 'available' | 'downloading' | 'downloaded' | 'error' | 'latest'

const showUpdateDialog = ref(false)
const updateState = ref<UpdateState>('idle')
const updateInfo = ref<any>({})
const downloadProgress = ref({ percent: 0, speed: '0 MB/s', transferred: '0 MB', total: '0 MB' })
const isDownloading = ref(false)
const checkType = ref<'auto' | 'manual'>('auto')

const allowClose = computed(() => {
  return true
})

const showCancelBtn = computed(() => {
  return updateState.value === 'available' || updateState.value === 'checking'
})

const showDownloadBtn = computed(() => {
  return updateState.value === 'available' && !isDownloading.value
})

const showInstallBtn = computed(() => {
  return updateState.value === 'downloaded'
})

const dialogTitle = computed(() => {
  switch (updateState.value) {
    case 'checking': return '检查更新'
    case 'available': return '发现新版本'
    case 'downloading': return '下载更新'
    case 'downloaded': return '更新就绪'
    case 'error': return '更新失败'
    case 'latest': return '检查更新'
    default: return '版本更新'
  }
})

const dialogSubtitle = computed(() => {
  if (updateState.value === 'available' && updateInfo.value.version) {
    return `版本 ${updateInfo.value.version}`
  }
  if (updateState.value === 'downloaded' && updateInfo.value.version) {
    return `版本 ${updateInfo.value.version}`
  }
  return ''
})

function formatReleaseNotes(notes: unknown): string {
  if (typeof notes === 'string') {
    return DOMPurify.sanitize(notes.replace(/\n/g, '<br>'))
  }
  if (Array.isArray(notes)) {
    const html = (notes as any[]).map((n: any) => `<p>${typeof n === 'string' ? n : JSON.stringify(n)}</p>`).join('')
    return DOMPurify.sanitize(html)
  }
  return DOMPurify.sanitize(String(notes || ''))
}

let checkTimeoutId: ReturnType<typeof setTimeout> | null = null
const CHECK_TIMEOUT_MS = 15000

function checkForUpdates(manual: boolean = false) {
  checkType.value = manual ? 'manual' : 'auto'
  updateState.value = 'checking'
  showUpdateDialog.value = true

  if (checkTimeoutId) clearTimeout(checkTimeoutId)
  checkTimeoutId = setTimeout(() => {
    if (updateState.value === 'checking') {
      updateState.value = 'error'
      updateInfo.value = { releaseNotes: '检查更新超时，请检查网络连接后重试' }
    }
  }, CHECK_TIMEOUT_MS)

  window.electronAPI.checkForUpdates().catch((err: any) => {
    if (checkTimeoutId) { clearTimeout(checkTimeoutId); checkTimeoutId = null }
    updateState.value = 'error'
    updateInfo.value = { releaseNotes: err.message || '检查更新失败' }
  })
}

async function downloadUpdate() {
  isDownloading.value = true
  updateState.value = 'downloading'
  
  try {
    await window.electronAPI.downloadUpdate()
  } catch (err: any) {
    updateState.value = 'error'
    updateInfo.value = { releaseNotes: err.message || '下载更新失败' }
    isDownloading.value = false
  }
}

function installUpdate() {
  window.electronAPI.installUpdate()
}

function closeDialog() {
  clearCheckTimeout()
  showUpdateDialog.value = false
  updateState.value = 'idle'
  updateInfo.value = {}
  isDownloading.value = false
}

function clearCheckTimeout() {
  if (checkTimeoutId) { clearTimeout(checkTimeoutId); checkTimeoutId = null }
}

const cleanupFns: (() => void)[] = []

function setupUpdateListeners() {
  cleanupFns.push(window.electronAPI.onUpdateAvailable((info: any) => {
    clearCheckTimeout()
    updateInfo.value = info
    updateState.value = 'available'
    isDownloading.value = false
  }))

  cleanupFns.push(window.electronAPI.onUpdateNotAvailable((info: any) => {
    clearCheckTimeout()
    updateInfo.value = info
    updateState.value = 'latest'
    isDownloading.value = false
  }))

  cleanupFns.push(window.electronAPI.onUpdateError((info: any) => {
    clearCheckTimeout()
    updateInfo.value = info
    updateState.value = 'error'
    isDownloading.value = false
  }))

  cleanupFns.push(window.electronAPI.onUpdateDownloadProgress((info: any) => {
    downloadProgress.value = info
  }))

  cleanupFns.push(window.electronAPI.onUpdateDownloaded((info: any) => {
    updateInfo.value = info
    updateState.value = 'downloaded'
    isDownloading.value = false
  }))
}

onMounted(() => {
  setupUpdateListeners()
})

onUnmounted(() => {
  cleanupFns.forEach(fn => fn())
  cleanupFns.length = 0
})

defineExpose({ checkForUpdates })
</script>

<style scoped>
.update-fade-enter-active,
.update-fade-leave-active {
  transition: opacity 0.3s ease;
}

.update-fade-enter-from,
.update-fade-leave-to {
  opacity: 0;
}

.update-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  backdrop-filter: blur(4px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 10000;
}

.update-dialog {
  background: var(--color-surface, #fff);
  border-radius: 16px;
  box-shadow: 0 10px 40px rgba(0, 0, 0, 0.2);
  width: 480px;
  max-width: 90vw;
  overflow: hidden;
}

.update-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 20px 24px;
  border-bottom: 1px solid var(--color-border, #eee);
  position: relative;
}

.update-icon {
  font-size: 28px;
}

.update-title {
  flex: 1;
}

.update-title h3 {
  margin: 0;
  font-size: 16px;
  color: var(--color-text, #333);
}

.update-version {
  font-size: 12px;
  color: var(--color-text-secondary, #999);
}

.close-btn {
  background: none;
  border: none;
  font-size: 24px;
  color: var(--color-text-secondary, #999);
  cursor: pointer;
  padding: 0 4px;
  line-height: 1;
}

.close-btn:hover {
  color: var(--color-text, #333);
}

.update-body {
  padding: 24px;
  min-height: 120px;
}

.update-status {
  text-align: center;
}

.update-status.error {
  color: #e53e3e;
}

.loading-spinner {
  width: 40px;
  height: 40px;
  border: 3px solid var(--color-border, #eee);
  border-top-color: var(--color-primary, #409eff);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
  margin: 0 auto 16px;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.update-desc {
  font-size: 14px;
  color: var(--color-text, #333);
  margin-bottom: 16px;
}

.release-notes {
  text-align: left;
  margin-top: 16px;
  padding: 12px;
  background: var(--color-bg, #f5f5f5);
  border-radius: 8px;
  max-height: 200px;
  overflow-y: auto;
}

.release-notes h4 {
  margin: 0 0 8px;
  font-size: 13px;
  color: var(--color-text-secondary, #666);
}

.notes-content {
  font-size: 13px;
  color: var(--color-text, #333);
  line-height: 1.6;
}

.progress-container {
  margin-top: 16px;
}

.progress-bar {
  height: 8px;
  background: var(--color-bg, #f5f5f5);
  border-radius: 4px;
  overflow: hidden;
  margin-bottom: 8px;
}

.progress-fill {
  height: 100%;
  background: linear-gradient(90deg, var(--color-primary, #409eff), var(--color-primary-hover, #66b1ff));
  transition: width 0.3s ease;
}

.progress-info {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
  color: var(--color-text-secondary, #999);
}

.progress-percent {
  font-weight: 600;
  color: var(--color-primary, #409eff);
}

.update-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  padding: 16px 24px;
  border-top: 1px solid var(--color-border, #eee);
}

.btn-primary,
.btn-secondary {
  padding: 8px 20px;
  border-radius: 8px;
  font-size: 14px;
  cursor: pointer;
  border: none;
  transition: all 0.2s;
}

.btn-primary {
  background: var(--color-primary, #409eff);
  color: #fff;
}

.btn-primary:hover:not(:disabled) {
  background: var(--color-primary-hover, #66b1ff);
}

.btn-primary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-secondary {
  background: var(--color-bg, #f5f5f5);
  color: var(--color-text, #333);
  border: 1px solid var(--color-border, #eee);
}

.btn-secondary:hover {
  background: var(--color-hover-bg, #eee);
}
</style>
