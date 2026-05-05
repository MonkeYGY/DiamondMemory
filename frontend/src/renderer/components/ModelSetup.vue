<template>
  <div class="model-setup-overlay" v-if="visible">
    <div class="model-setup-card">
      <button class="close-btn" @click="closeSetup" title="关闭">✕</button>
      <div class="setup-header">
        <div class="setup-icon">📦</div>
        <h2 class="setup-title">下载核心模型</h2>
        <p class="setup-desc">安装包不包含大模型文件，首次使用需下载（可跳过，系统将以降级模式运行）。</p>
      </div>

      <div class="setup-body">
        <div class="model-row" v-if="needEmbedding">
          <div class="model-info">
            <span class="model-name">bge-m3</span>
            <span class="model-tag">嵌入模型</span>
          </div>
          <div class="model-actions">
            <span v-if="startupStatus.embedding_installed" class="status installed">✅ 已安装</span>
            <template v-else-if="getPullStatus('bge-m3')?.status === 'pulling'">
              <div class="progress">
                <div class="progress-bar"><div class="progress-fill" :style="{ width: getPullStatus('bge-m3')?.progress + '%' }"></div></div>
                <span class="progress-text">{{ getPullStatus('bge-m3')?.progress }}%</span>
              </div>
              <button class="btn-cancel" @click="cancelPull('bge-m3')">取消</button>
            </template>
            <template v-else-if="getPullStatus('bge-m3')?.status === 'failed'">
              <span class="status failed">❌ 失败</span>
              <button class="btn-retry" @click="pullModel('bge-m3')">重试</button>
            </template>
            <button v-else class="btn-download" @click="pullModel('bge-m3')">下载</button>
          </div>
        </div>

        <div class="model-row" v-if="needLlm">
          <div class="model-info">
            <span class="model-name">{{ llmName }}</span>
            <span class="model-tag">主模型</span>
          </div>
          <div class="model-actions">
            <span v-if="startupStatus.llm_installed" class="status installed">✅ 已安装</span>
            <template v-else-if="getPullStatus(llmName)?.status === 'pulling'">
              <div class="progress">
                <div class="progress-bar"><div class="progress-fill" :style="{ width: getPullStatus(llmName)?.progress + '%' }"></div></div>
                <span class="progress-text">{{ getPullStatus(llmName)?.progress }}%</span>
              </div>
              <button class="btn-cancel" @click="cancelPull(llmName)">取消</button>
            </template>
            <template v-else-if="getPullStatus(llmName)?.status === 'failed'">
              <span class="status failed">❌ 失败</span>
              <button class="btn-retry" @click="pullModel(llmName)">重试</button>
            </template>
            <button v-else class="btn-download" @click="pullModel(llmName)">下载</button>
          </div>
        </div>
      </div>

      <div class="setup-actions">
        <button class="btn-secondary" @click="openSettings">去设置</button>
        <button class="btn-secondary" @click="skipSetup">本次跳过</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { apiRequest } from '../api/backend'

const props = defineProps<{
  visible: boolean
  startupStatus: {
    ollama_ready: boolean
    llm_model_name: string
    llm_installed: boolean
    embedding_installed: boolean
  }
}>()

const emit = defineEmits<{
  (e: 'skip'): void
  (e: 'close'): void
  (e: 'open-settings'): void
}>()

const pullProgress = ref<Record<string, any>>({})
let pollTimer: ReturnType<typeof setInterval> | null = null

const llmName = computed(() => props.startupStatus.llm_model_name || '主模型')
const needEmbedding = computed(() => props.startupStatus.ollama_ready && !props.startupStatus.embedding_installed)
const needLlm = computed(() => props.startupStatus.ollama_ready && !props.startupStatus.llm_installed)

function getPullStatus(modelName: string) {
  return pullProgress.value[modelName] || null
}

function startPolling() {
  stopPolling()
  pollTimer = setInterval(async () => {
    try {
      const data = await apiRequest<{ pulls: Record<string, any> }>('/api/config/pull-progress')
      pullProgress.value = data.pulls || {}
    } catch {}
  }, 1000)
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

onMounted(() => {
  startPolling()
})

onUnmounted(() => {
  stopPolling()
})

async function pullModel(modelName: string) {
  const name = (modelName || '').trim()
  if (!name) return
  try {
    await apiRequest('/api/config/pull-model', {
      method: 'POST',
      body: JSON.stringify({ model_name: name })
    })
  } catch {}
}

async function cancelPull(modelName: string) {
  const name = (modelName || '').trim()
  if (!name) return
  try {
    await apiRequest('/api/config/cancel-pull', {
      method: 'POST',
      body: JSON.stringify({ model_name: name })
    })
  } catch {}
}

function openSettings() {
  emit('open-settings')
}

function skipSetup() {
  emit('skip')
}

function closeSetup() {
  emit('close')
}
</script>

<style scoped>
.model-setup-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 9999;
}

.model-setup-card {
  width: 520px;
  max-width: calc(100vw - 40px);
  background: var(--color-surface);
  border-radius: 12px;
  padding: 20px;
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

.setup-header {
  text-align: center;
  margin-bottom: 14px;
}

.setup-icon {
  font-size: 30px;
  margin-bottom: 6px;
}

.setup-title {
  font-size: 18px;
  margin: 0 0 4px;
}

.setup-desc {
  font-size: 13px;
  color: var(--color-text-secondary);
  margin: 0;
  line-height: 1.5;
}

.setup-body {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin: 14px 0 16px;
}

.model-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  border: 1px solid var(--color-border);
  border-radius: 10px;
  padding: 12px;
  background: var(--color-bg);
}

.model-info {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.model-name {
  font-weight: 600;
  font-size: 14px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 280px;
}

.model-tag {
  font-size: 12px;
  color: var(--color-text-secondary);
}

.model-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.status {
  font-size: 12px;
  font-weight: 500;
}
.status.installed {
  color: var(--color-success);
}
.status.failed {
  color: var(--color-error);
}

.progress {
  display: flex;
  align-items: center;
  gap: 8px;
}

.progress-bar {
  width: 120px;
  height: 6px;
  background: #e2e8f0;
  border-radius: 3px;
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background: var(--color-primary);
  transition: width 0.3s ease;
}

.progress-text {
  font-size: 12px;
  color: var(--color-text-secondary);
  width: 42px;
  text-align: right;
}

.setup-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}

.btn-download {
  padding: 6px 14px;
  border: none;
  border-radius: 6px;
  background: var(--color-primary);
  color: var(--color-text-on-primary);
  font-size: 12px;
  cursor: pointer;
  font-weight: 500;
}

.btn-secondary {
  padding: 6px 14px;
  border: 1px solid var(--color-border);
  border-radius: 6px;
  background: var(--color-surface);
  color: var(--color-text);
  font-size: 12px;
  cursor: pointer;
  font-weight: 500;
}

.btn-retry {
  padding: 2px 10px;
  border: 1px solid var(--color-error);
  border-radius: 4px;
  background: transparent;
  color: var(--color-error);
  font-size: 12px;
  cursor: pointer;
}

.btn-cancel {
  padding: 2px 10px;
  border: 1px solid var(--color-primary);
  border-radius: 4px;
  background: transparent;
  color: var(--color-primary);
  font-size: 12px;
  cursor: pointer;
}
</style>
