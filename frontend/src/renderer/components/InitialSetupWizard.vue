<template>
  <div class="wizard-overlay" v-if="visible">
    <div class="wizard-card">
      <button class="close-btn" @click="dismiss" title="关闭">✕</button>
      <div class="wizard-header">
        <div class="wizard-title">首次使用设置</div>
        <div class="wizard-subtitle">完成一次存储路径、备份路径与模型下载设置</div>
        <div class="wizard-steps">
          <div class="wizard-step" :class="{ active: step === 0, done: step > 0 }">1 存储</div>
          <div class="wizard-step" :class="{ active: step === 1, done: step > 1 }">2 备份</div>
          <div class="wizard-step" :class="{ active: step === 2 }">3 模型</div>
        </div>
      </div>

      <div class="wizard-body">
        <div v-if="step === 0" class="step-panel">
          <div class="panel-title">设置存储路径</div>
          <div class="panel-desc">存储路径用于保存知识库、记忆、向量索引等数据。</div>
          <div class="path-row">
            <div class="path-label">当前路径</div>
            <div class="path-value">{{ selectedStoragePath || '默认路径（系统用户目录）' }}</div>
          </div>
          <div class="panel-actions">
            <button class="btn-secondary" @click="selectStoragePath">选择存储路径</button>
          </div>
          <div class="panel-hint" v-if="storagePathChanged">已记录新路径，建议完成设置后重启应用以确保全部服务使用新工作区。</div>
        </div>

        <div v-else-if="step === 1" class="step-panel">
          <div class="panel-title">设置备份路径</div>
          <div class="panel-desc">备份路径用于保存“立即备份/自动备份”的输出文件。</div>
          <div class="path-row">
            <div class="path-label">备份路径</div>
            <div class="path-value">{{ backupPath || '未设置（建议设置）' }}</div>
          </div>
          <div class="panel-actions">
            <button class="btn-secondary" @click="selectBackupPath">选择备份路径</button>
          </div>
        </div>

        <div v-else class="step-panel">
          <div class="panel-title">下载模型</div>
          <div class="panel-desc">安装包不包含大模型文件，首次使用需下载。</div>

          <div v-if="!backendRunning" class="status-box">
            <div class="status-title">核心服务未就绪</div>
            <div class="status-desc">请等待系统启动完成后再进行模型下载。</div>
          </div>

          <template v-else>
            <div class="status-box" v-if="!startupStatus.ollama_ready">
              <div class="status-title">安装 AI 引擎（Ollama）</div>
              <div class="status-desc">本地推理需要先安装 Ollama，引擎安装完成后再下载模型。</div>

              <div class="progress-block" v-if="ollamaDownloadStatus.status === 'downloading'">
                <div class="progress-bar">
                  <div class="progress-fill" :class="{ indeterminate: ollamaDownloadStatus.progress < 0 }" :style="ollamaDownloadStatus.progress >= 0 ? { width: ollamaDownloadStatus.progress + '%' } : {}"></div>
                </div>
                <div class="progress-meta">
                  <span>{{ ollamaDownloadStatus.progress >= 0 ? ollamaDownloadStatus.progress + '%' : '...' }}</span>
                  <span>{{ formatSize(ollamaDownloadStatus.downloaded) }}{{ ollamaDownloadStatus.total > 0 ? ' / ' + formatSize(ollamaDownloadStatus.total) : '' }}</span>
                  <span>{{ ollamaDownloadStatus.speed }}</span>
                </div>
                <div class="panel-actions">
                  <button class="btn-secondary" @click="cancelOllamaDownload">取消下载</button>
                </div>
              </div>

              <div class="status-error" v-else-if="ollamaDownloadStatus.status === 'failed'">{{ ollamaDownloadStatus.error || '下载失败' }}</div>
              <div class="status-ok" v-else-if="ollamaDownloadStatus.status === 'completed'">下载完成，正在启动服务...</div>

              <div class="panel-actions" v-else>
                <button class="btn-primary" @click="startOllamaDownload" :disabled="ollamaStarting">{{ ollamaStarting ? '启动中...' : (ollamaDownloadStatus.status === 'failed' ? '重新下载' : '开始下载') }}</button>
                <button class="btn-secondary" @click="openSettings">去设置</button>
              </div>
            </div>

            <div v-else class="models-box">
              <div class="model-row" v-if="needEmbedding">
                <div class="model-info">
                  <div class="model-name">bge-m3</div>
                  <div class="model-desc">语义嵌入模型（用于向量检索）</div>
                </div>
                <div class="model-actions">
                  <span v-if="startupStatus.embedding_installed" class="tag ok">✅ 已安装</span>
                  <template v-else-if="getPullStatus('bge-m3')?.status === 'pulling'">
                    <div class="progress-inline">
                      <div class="progress-bar small"><div class="progress-fill" :style="{ width: getPullStatus('bge-m3')?.progress + '%' }"></div></div>
                      <span class="progress-text">{{ getPullStatus('bge-m3')?.progress }}%</span>
                    </div>
                    <button class="btn-mini" @click="cancelPull('bge-m3')">取消</button>
                  </template>
                  <template v-else-if="getPullStatus('bge-m3')?.status === 'failed'">
                    <span class="tag fail">❌ 失败</span>
                    <button class="btn-mini" @click="pullModel('bge-m3')">重试</button>
                  </template>
                  <button v-else class="btn-mini primary" @click="pullModel('bge-m3')">下载</button>
                </div>
              </div>

              <div class="model-row" v-if="needLlm">
                <div class="model-info">
                  <div class="model-name">{{ llmName }}</div>
                  <div class="model-desc">主模型（用于对话与推理）</div>
                </div>
                <div class="model-actions">
                  <span v-if="startupStatus.llm_installed" class="tag ok">✅ 已安装</span>
                  <template v-else-if="getPullStatus(llmName)?.status === 'pulling'">
                    <div class="progress-inline">
                      <div class="progress-bar small"><div class="progress-fill" :style="{ width: getPullStatus(llmName)?.progress + '%' }"></div></div>
                      <span class="progress-text">{{ getPullStatus(llmName)?.progress }}%</span>
                    </div>
                    <button class="btn-mini" @click="cancelPull(llmName)">取消</button>
                  </template>
                  <template v-else-if="getPullStatus(llmName)?.status === 'failed'">
                    <span class="tag fail">❌ 失败</span>
                    <button class="btn-mini" @click="pullModel(llmName)">重试</button>
                  </template>
                  <button v-else class="btn-mini primary" @click="pullModel(llmName)">下载</button>
                </div>
              </div>

              <div class="status-ok" v-if="!needEmbedding && !needLlm">已检测到核心模型均已安装。</div>
              <div class="panel-actions">
                <button class="btn-secondary" @click="openSettings">去设置</button>
              </div>
            </div>
          </template>
        </div>
      </div>

      <div class="wizard-actions">
        <button class="btn-secondary" v-if="step > 0" @click="prevStep">上一步</button>
        <button class="btn-secondary" @click="dismiss">跳过</button>
        <button class="btn-primary" @click="nextStep">{{ step < 2 ? '下一步' : '完成' }}</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { apiRequest } from '../api/backend'
import { useToast } from '../composables/useToast'

const props = defineProps<{
  visible: boolean
  backendRunning: boolean
  storagePath: string
  startupStatus: {
    ollama_ready: boolean
    llm_model_name: string
    llm_installed: boolean
    embedding_installed: boolean
  }
}>()

const emit = defineEmits<{
  (e: 'dismiss'): void
  (e: 'complete', payload: { needsRestart: boolean }): void
  (e: 'open-settings'): void
}>()

const toast = useToast()
const step = ref(0)
const selectedStoragePath = ref(props.storagePath || '')
const storagePathChanged = ref(false)
const backupPath = ref(localStorage.getItem('dm-backup-path') || '')

const llmName = computed(() => props.startupStatus.llm_model_name || '主模型')
const needEmbedding = computed(() => props.startupStatus.ollama_ready && !props.startupStatus.embedding_installed)
const needLlm = computed(() => props.startupStatus.ollama_ready && !props.startupStatus.llm_installed)

const pullProgress = ref<Record<string, any>>({})
const ollamaDownloadStatus = ref<{ status: string; progress: number; downloaded: number; total: number; speed: string; error: string }>({ status: 'idle', progress: 0, downloaded: 0, total: 0, speed: '', error: '' })
const ollamaStarting = ref(false)
let pollTimer: ReturnType<typeof setInterval> | null = null

watch(() => props.storagePath, (v) => {
  if (!storagePathChanged.value) selectedStoragePath.value = v || ''
})

watch(() => props.visible, (v) => {
  if (v) startPolling()
  else stopPolling()
})

onMounted(() => {
  if (props.visible) startPolling()
})

onUnmounted(() => {
  stopPolling()
})

function dismiss() {
  stopPolling()
  emit('dismiss')
}

function openSettings() {
  emit('open-settings')
}

function prevStep() {
  step.value = Math.max(0, step.value - 1)
}

function nextStep() {
  if (step.value < 2) {
    step.value += 1
    return
  }
  stopPolling()
  emit('complete', { needsRestart: storagePathChanged.value })
}

async function selectStoragePath() {
  const p = await window.electronAPI?.selectDirectory?.({ title: '选择存储路径' })
  if (!p) return
  try {
    if (window.electronAPI?.setStoragePath) await window.electronAPI.setStoragePath(p)
    if (window.electronAPI?.initStorageDir) await window.electronAPI.initStorageDir(p)
    selectedStoragePath.value = p
    storagePathChanged.value = true
    toast.success('存储路径已保存')
  } catch (e: any) {
    toast.error('保存存储路径失败: ' + (e?.message || '未知错误'))
  }
}

async function selectBackupPath() {
  const p = await window.electronAPI?.selectDirectory?.({ title: '选择备份路径' })
  if (!p) return
  localStorage.setItem('dm-backup-path', p)
  backupPath.value = p
  toast.success('备份路径已保存')
}

function getPullStatus(modelName: string) {
  return pullProgress.value[modelName] || null
}

async function pullModel(modelName: string) {
  const name = (modelName || '').trim()
  if (!name) return
  try {
    await apiRequest('/api/config/pull-model', { method: 'POST', body: JSON.stringify({ model_name: name }) })
  } catch {}
}

async function cancelPull(modelName: string) {
  const name = (modelName || '').trim()
  if (!name) return
  try {
    await apiRequest('/api/config/cancel-pull', { method: 'POST', body: JSON.stringify({ model_name: name }) })
  } catch {}
}

async function startOllamaDownload() {
  if (ollamaStarting.value) return
  ollamaStarting.value = true
  try {
    await apiRequest('/api/ollama/download', { method: 'POST' })
    ollamaDownloadStatus.value = { status: 'downloading', progress: 0, downloaded: 0, total: 0, speed: '', error: '' }
  } catch (e: any) {
    ollamaDownloadStatus.value = { status: 'failed', progress: 0, downloaded: 0, total: 0, speed: '', error: e?.message || '启动下载失败' }
  } finally {
    ollamaStarting.value = false
  }
}

async function cancelOllamaDownload() {
  try {
    await apiRequest('/api/ollama/cancel-download', { method: 'POST' })
    ollamaDownloadStatus.value.status = 'cancelled'
  } catch {}
}

function startPolling() {
  stopPolling()
  pollTimer = setInterval(async () => {
    if (!props.visible) return
    if (!props.backendRunning) return
    if (step.value === 2) {
      try {
        const data = await apiRequest<{ pulls: Record<string, any> }>('/api/config/pull-progress')
        pullProgress.value = data.pulls || {}
      } catch {}

      try {
        const d = await apiRequest<{ status: string; progress: number; downloaded: number; total: number; speed: string; error: string | null }>('/api/ollama/download-progress')
        if (d.status === 'downloading') {
          ollamaDownloadStatus.value = { status: 'downloading', progress: d.progress ?? 0, downloaded: d.downloaded ?? 0, total: d.total ?? 0, speed: d.speed || '', error: '' }
        } else if (d.status === 'completed') {
          ollamaDownloadStatus.value = { status: 'completed', progress: 100, downloaded: d.downloaded ?? 0, total: d.total ?? 0, speed: d.speed || '', error: '' }
        } else if (d.status === 'failed') {
          ollamaDownloadStatus.value = { status: 'failed', progress: d.progress ?? 0, downloaded: d.downloaded ?? 0, total: d.total ?? 0, speed: d.speed || '', error: d.error || '下载失败' }
        }
      } catch {}
    }
  }, 1000)
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

function formatSize(bytes: number): string {
  const b = Math.max(0, Number(bytes || 0))
  if (b < 1024) return `${b} B`
  const kb = b / 1024
  if (kb < 1024) return `${kb.toFixed(1)} KB`
  const mb = kb / 1024
  if (mb < 1024) return `${mb.toFixed(1)} MB`
  const gb = mb / 1024
  return `${gb.toFixed(1)} GB`
}
</script>

<style scoped>
.wizard-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 10000;
}

.wizard-card {
  width: 640px;
  max-width: calc(100vw - 40px);
  background: var(--color-surface);
  border-radius: 12px;
  padding: 18px;
  box-shadow: var(--shadow);
  position: relative;
}

.close-btn {
  position: absolute;
  right: 12px;
  top: 12px;
  width: 28px;
  height: 28px;
  border: none;
  border-radius: 6px;
  background: transparent;
  cursor: pointer;
  color: var(--color-text-secondary);
}

.wizard-header {
  text-align: center;
  margin-bottom: 14px;
}

.wizard-title {
  font-size: 18px;
  font-weight: 700;
}

.wizard-subtitle {
  font-size: 13px;
  color: var(--color-text-secondary);
  margin-top: 4px;
}

.wizard-steps {
  display: flex;
  gap: 8px;
  justify-content: center;
  margin-top: 12px;
}

.wizard-step {
  padding: 6px 10px;
  border-radius: 999px;
  background: var(--color-surface-secondary);
  color: var(--color-text-secondary);
  font-size: 12px;
}

.wizard-step.active {
  background: var(--color-primary-bg);
  color: var(--color-primary);
  border: 1px solid var(--color-indigo-border);
}

.wizard-step.done {
  background: var(--color-success-bg-subtle);
  color: var(--color-success-text);
  border: 1px solid var(--color-success-border-strong);
}

.wizard-body {
  min-height: 300px;
}

.step-panel {
  background: var(--color-surface-secondary);
  border: 1px solid var(--color-border);
  border-radius: 10px;
  padding: 14px;
}

.panel-title {
  font-size: 14px;
  font-weight: 700;
}

.panel-desc {
  margin-top: 6px;
  color: var(--color-text-secondary);
  font-size: 13px;
  line-height: 1.5;
}

.path-row {
  margin-top: 14px;
  padding: 10px;
  background: var(--color-surface);
  border-radius: 8px;
  border: 1px solid var(--color-border);
}

.path-label {
  color: var(--color-text-tertiary);
  font-size: 12px;
}

.path-value {
  margin-top: 6px;
  font-size: 13px;
  word-break: break-all;
}

.panel-actions {
  margin-top: 12px;
  display: flex;
  gap: 10px;
}

.panel-hint {
  margin-top: 10px;
  color: var(--color-text-secondary);
  font-size: 12px;
}

.wizard-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 14px;
}

.btn-primary,
.btn-secondary {
  border: none;
  border-radius: 8px;
  padding: 10px 14px;
  cursor: pointer;
}

.btn-primary {
  background: var(--color-primary);
  color: var(--color-text-on-primary);
}

.btn-secondary {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  color: var(--color-text);
}

.status-box {
  margin-top: 12px;
  padding: 12px;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 10px;
}

.status-title {
  font-weight: 700;
  font-size: 13px;
}

.status-desc {
  margin-top: 6px;
  color: var(--color-text-secondary);
  font-size: 13px;
  line-height: 1.5;
}

.status-error {
  margin-top: 10px;
  color: var(--color-error);
  font-size: 13px;
}

.status-ok {
  margin-top: 10px;
  color: var(--color-success-text);
  font-size: 13px;
}

.progress-block {
  margin-top: 12px;
}

.progress-bar {
  width: 100%;
  height: 10px;
  background: var(--color-surface-secondary);
  border-radius: 999px;
  overflow: hidden;
  border: 1px solid var(--color-border);
}

.progress-bar.small {
  height: 8px;
  width: 120px;
}

.progress-fill {
  height: 100%;
  background: var(--color-primary);
  transition: width 0.2s ease;
}

.progress-fill.indeterminate {
  width: 35%;
  animation: indeterminate 1.2s ease-in-out infinite;
}

@keyframes indeterminate {
  0% { transform: translateX(-120%); }
  100% { transform: translateX(320%); }
}

.progress-meta {
  margin-top: 8px;
  display: flex;
  gap: 10px;
  color: var(--color-text-secondary);
  font-size: 12px;
  flex-wrap: wrap;
}

.models-box {
  margin-top: 12px;
}

.model-row {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding: 12px;
  background: var(--color-surface);
  border-radius: 10px;
  border: 1px solid var(--color-border);
  margin-top: 10px;
}

.model-info {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.model-name {
  font-weight: 700;
  font-size: 13px;
}

.model-desc {
  color: var(--color-text-secondary);
  font-size: 12px;
}

.model-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.tag {
  padding: 4px 8px;
  border-radius: 999px;
  font-size: 12px;
  border: 1px solid var(--color-border);
  background: var(--color-surface-secondary);
}

.tag.ok {
  background: var(--color-success-bg-subtle);
  border-color: var(--color-success-border-strong);
  color: var(--color-success-text);
}

.tag.fail {
  background: var(--color-error-bg);
  border-color: var(--color-error);
  color: var(--color-error-text);
}

.btn-mini {
  border: 1px solid var(--color-border);
  background: var(--color-surface);
  border-radius: 8px;
  padding: 6px 10px;
  cursor: pointer;
  font-size: 12px;
}

.btn-mini.primary {
  border: none;
  background: var(--color-primary);
  color: var(--color-text-on-primary);
}

.progress-inline {
  display: flex;
  align-items: center;
  gap: 6px;
}

.progress-text {
  font-size: 12px;
  color: var(--color-text-secondary);
}
</style>
