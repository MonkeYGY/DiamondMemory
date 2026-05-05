<template>
  <div class="model-view">
    <div class="header">
      <div class="title">
        <h1>模型管理</h1>
        <p>配置本地 Ollama 模型和外部商用 API，为系统提供推理算力</p>
      </div>

      <div class="global-switch">
        <span class="label">启用大模型处理</span>
        <label class="switch">
          <input type="checkbox" v-model="config.llm_enabled" @change="saveConfig">
          <span class="slider round"></span>
        </label>
      </div>
    </div>

    <div class="content-body" :class="{ 'disabled': !config.llm_enabled }">
      <div v-if="!config.llm_enabled" class="disabled-notice">
        <span class="notice-icon">⚠️</span>
        <span>大模型处理已禁用，记忆系统将以基础模式运行（仅向量检索，无智能推理）。请开启开关以使用完整功能。</span>
      </div>

      <div class="provider-selector">
        <button
          class="provider-btn"
          :class="{ active: config.provider === 'local' }"
          @click="switchProvider('local')"
        >
          <span>🏠 本地模型 (Ollama)</span>
        </button>
        <button
          class="provider-btn"
          :class="{ active: config.provider === 'external' }"
          @click="switchProvider('external')"
        >
          <span>☁️ 外部模型 (API)</span>
        </button>
      </div>

      <div v-if="config.provider === 'local'" class="settings-card">
        <h3>Ollama 服务状态</h3>
        <div class="status-box" :class="{ 'online': ollamaStatus.running }">
          <div class="status-indicator"></div>
          <span>{{ ollamaStatus.running ? '服务运行中' : '服务未启动' }}</span>
        </div>

        <div v-if="ollamaStatus.running" class="model-list">
          <h3>已安装模型</h3>
          <div v-if="ollamaStatus.models.length === 0" class="empty-state">
            <div class="empty-icon">📦</div>
            <p>暂无已安装的模型</p>
            <p class="hint">请在下方下载推荐模型，或手动输入模型名称下载</p>
          </div>
          <div
            v-for="model in ollamaStatus.model_details"
            :key="model.name"
            class="model-item"
            :class="{ active: config.local.model === model.name || config.local.model === model.name.replace(':latest', '') }"
          >
            <div class="model-info">
              <span class="icon">📦</span>
              <div class="model-meta">
                <span class="name">{{ model.name }}</span>
                <span v-if="model.size" class="size">{{ formatSize(model.size) }}</span>
              </div>
              <span
                v-if="config.local.model === model.name || config.local.model === model.name.replace(':latest', '')"
                class="badge"
              >当前使用</span>
              <span v-if="model.name.includes('bge-m3')" class="badge badge-embedding">嵌入模型</span>
            </div>
            <button
              v-if="config.local.model !== model.name && config.local.model !== model.name.replace(':latest', '') && !model.name.includes('bge-m3')"
              class="btn-switch"
              @click="switchLocalModel(model.name)"
              :disabled="switchingModel === model.name"
            >
              {{ switchingModel === model.name ? '切换中...' : '切换至此模型' }}
            </button>
          </div>

          <h3 class="mt-4">下载模型</h3>

          <div class="recommend-section">
            <p class="section-hint">推荐模型（点击即可下载，下载完成后重启软件自动常驻内存）</p>
            <div class="recommend-grid">
              <div
                v-for="rec in recommendedModels"
                :key="rec.name"
                class="recommend-card"
                :class="{ installed: isModelInstalled(rec.name), pulling: getPullStatus(rec.name)?.status === 'pulling' }"
              >
                <div class="rec-header">
                  <span class="rec-icon">{{ rec.icon }}</span>
                  <span class="rec-name">{{ rec.name }}</span>
                </div>
                <p class="rec-desc">{{ rec.description }}</p>
                <p class="rec-size">{{ rec.sizeHint }}</p>
                <div v-if="isModelInstalled(rec.name)" class="rec-status installed">
                  ✅ 已安装
                </div>
                <div v-else-if="getPullStatus(rec.name)?.status === 'pulling'" class="rec-status pulling">
                  <div class="progress-bar">
                    <div class="progress-fill" :style="{ width: getPullStatus(rec.name).progress + '%' }"></div>
                  </div>
                  <span class="progress-text">{{ getPullStatus(rec.name).progress }}% - {{ formatPullDetail(getPullStatus(rec.name)) }}</span>
                  <button class="btn-cancel" @click="cancelPull(rec.name)">取消</button>
                </div>
                <div v-else-if="getPullStatus(rec.name)?.status === 'failed'" class="rec-status failed">
                  ❌ 下载失败
                  <button class="btn-retry" @click="pullModel(rec.name)">重试</button>
                </div>
                <div v-else-if="getPullStatus(rec.name)?.status === 'completed'" class="rec-status completed">
                  ✅ 下载完成，请重启软件
                </div>
                <button
                  v-else
                  class="btn-download"
                  @click="pullModel(rec.name)"
                  :disabled="getPullStatus(rec.name)?.status === 'pulling'"
                >
                  下载
                </button>
              </div>
            </div>
          </div>

          <div class="download-box">
            <input
              type="text"
              v-model="newModelName"
              placeholder="输入其他模型名称，例如: qwen2.5:7b, llama3.2"
              class="input-field"
              @keyup.enter="pullCustomModel"
            />
            <button
              class="btn-primary"
              @click="pullCustomModel"
              :disabled="!newModelName || getPullStatus(newModelName)?.status === 'pulling'"
            >
              {{ getPullStatus(newModelName)?.status === 'pulling' ? '下载中...' : '下载' }}
            </button>
          </div>

          <div v-if="customPullProgress" class="custom-progress">
            <div class="progress-bar">
              <div class="progress-fill" :style="{ width: customPullProgress.progress + '%' }"></div>
            </div>
            <span class="progress-text">{{ customPullProgress.progress }}% - {{ customPullProgress.status_detail || '下载中' }}</span>
            <button v-if="customPullProgress.status === 'pulling'" class="btn-cancel" @click="cancelPull(newModelName)">取消</button>
          </div>
        </div>

        <div v-else class="ollama-offline">
          <div class="empty-icon">🔌</div>
          <p>Ollama 服务未启动</p>
          <p class="hint">请重启软件以自动启动内嵌的 Ollama 服务，或确认系统已安装 Ollama</p>
        </div>
      </div>

      <div v-if="config.provider === 'external'" class="settings-card">
        <h3>外部 API 配置</h3>
        <p class="hint mb-4">支持兼容 OpenAI 格式的第三方大模型服务接口（如通义千问、智谱GLM、DeepSeek等）。配置保存后，下次启动将自动连接。</p>

        <div class="form-group">
          <label>API Base URL</label>
          <input type="text" v-model="config.external.endpoint" class="input-field" placeholder="https://api.openai.com/v1" />
        </div>

        <div class="form-group">
          <label>API Key</label>
          <input type="password" v-model="config.external.api_key" class="input-field" placeholder="sk-..." />
        </div>

        <div class="form-group">
          <label>模型名称</label>
          <input type="text" v-model="config.external.model" class="input-field" placeholder="例如: qwen-plus" />
        </div>

        <div class="actions">
          <button class="btn-primary" @click="saveExternalConfig" :disabled="isSaving">
            {{ isSaving ? '保存中...' : '保存配置' }}
          </button>
          <button class="btn-secondary" @click="testExternalConnection" :disabled="isTesting">
            {{ isTesting ? '测试中...' : '测试连接' }}
          </button>
        </div>

        <div v-if="testResult" class="test-result" :class="testResult.success ? 'success' : 'error'">
          {{ testResult.message }}
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed } from 'vue'
import { apiRequest } from '../api/backend'
import { useToast } from '../composables/useToast'

const toast = useToast()

const config = ref({
  model: '',
  provider: 'local',
  llm_enabled: true,
  local: { model: '', endpoint: '' },
  external: { endpoint: '', api_key: '', model: '' }
})

const ollamaStatus = ref({
  running: false,
  models: [] as string[],
  model_details: [] as Array<{ name: string; size: number; modified_at: string; details: any }>,
  has_model: false,
  has_embedding_model: false
})

const pullProgress = ref<Record<string, any>>({})
const newModelName = ref('')
const switchingModel = ref('')
const isSaving = ref(false)
const isTesting = ref(false)
const testResult = ref<{ success: boolean; message: string } | null>(null)

let progressTimer: ReturnType<typeof setInterval> | null = null

const recommendedModels = [
  {
    name: 'qwen3.5:4b',
    icon: '🧠',
    description: '推荐 LLM 模型，4B 参数量，适合日常对话和智能推理',
    sizeHint: '约 2.5 GB'
  },
  {
    name: 'bge-m3',
    icon: '🔢',
    description: '语义嵌入模型，用于高质量向量检索',
    sizeHint: '约 1.2 GB'
  }
]

const customPullProgress = computed(() => {
  if (!newModelName.value) return null
  return pullProgress.value[newModelName.value] || null
})

onMounted(async () => {
  await loadConfig()
  await checkOllamaStatus()
  startProgressPolling()
})

onUnmounted(() => {
  stopProgressPolling()
})

function startProgressPolling() {
  progressTimer = setInterval(async () => {
    await fetchPullProgress()
  }, 2000)
}

function stopProgressPolling() {
  if (progressTimer) {
    clearInterval(progressTimer)
    progressTimer = null
  }
}

async function loadConfig() {
  try {
    config.value = await apiRequest('/api/config/llm-model')
  } catch (error: any) {
    toast.error('加载模型配置失败: ' + error.message)
  }
}

async function checkOllamaStatus() {
  try {
    ollamaStatus.value = await apiRequest('/api/config/ollama-status')
  } catch (error) {
    ollamaStatus.value = {
      running: false,
      models: [],
      model_details: [],
      has_model: false,
      has_embedding_model: false
    }
  }
}

async function fetchPullProgress() {
  try {
    const data = await apiRequest<{ pulls: Record<string, any> }>('/api/config/pull-progress')
    pullProgress.value = data.pulls || {}

    const hasActivePull = Object.values(pullProgress.value).some((p: any) => p.status === 'pulling')
    if (!hasActivePull) {
      const hadCompleted = Object.values(pullProgress.value).some((p: any) => p.status === 'completed')
      if (hadCompleted) {
        await checkOllamaStatus()
      }
    }
  } catch {
    // ignore
  }
}

function getPullStatus(modelName: string) {
  return pullProgress.value[modelName] || null
}

function isModelInstalled(modelName: string): boolean {
  return ollamaStatus.value.models.some(m =>
    m === modelName || m === modelName + ':latest' || m.replace(':latest', '') === modelName
  )
}

function formatSize(bytes: number): string {
  if (bytes === 0) return ''
  const units = ['B', 'KB', 'MB', 'GB']
  let i = 0
  let size = bytes
  while (size >= 1024 && i < units.length - 1) {
    size /= 1024
    i++
  }
  return size.toFixed(1) + ' ' + units[i]
}

function formatPullDetail(progress: any): string {
  if (!progress) return ''
  const total = progress.total || 0
  const completed = progress.completed || 0
  if (total > 0) {
    return `${formatSize(completed)} / ${formatSize(total)}`
  }
  return progress.status_detail || '下载中'
}

async function saveConfig() {
  try {
    await apiRequest('/api/config/set', {
      method: 'POST',
      body: JSON.stringify({ key: 'llm_enabled', value: config.value.llm_enabled.toString() })
    })
    toast.success(config.value.llm_enabled ? '大模型处理已启用' : '大模型处理已禁用')
  } catch (error: any) {
    toast.error('保存配置失败: ' + error.message)
  }
}

async function switchProvider(provider: 'local' | 'external') {
  config.value.provider = provider
  try {
    await apiRequest('/api/config/set', {
      method: 'POST',
      body: JSON.stringify({ key: 'llm_provider', value: provider })
    })
    toast.success(`已切换至${provider === 'local' ? '本地' : '外部'}模型`)
  } catch (error: any) {
    toast.error('切换模型提供商失败: ' + error.message)
  }
}

async function switchLocalModel(modelName: string) {
  switchingModel.value = modelName
  try {
    await apiRequest('/api/config/switch-model', {
      method: 'POST',
      body: JSON.stringify({ model_name: modelName })
    })
    toast.success(`已下发切换模型指令，后台加载中...`)
    setTimeout(async () => {
      await loadConfig()
      switchingModel.value = ''
    }, 3000)
  } catch (error: any) {
    toast.error('切换模型失败: ' + error.message)
    switchingModel.value = ''
  }
}

async function pullModel(modelName: string) {
  try {
    const res: any = await apiRequest('/api/config/pull-model', {
      method: 'POST',
      body: JSON.stringify({ model_name: modelName })
    })
    if (res.status === 'already_pulling') {
      toast.info(`模型 ${modelName} 正在下载中`)
    } else {
      toast.info(`开始下载模型: ${modelName}`)
    }
  } catch (error: any) {
    toast.error('下载请求失败: ' + error.message)
  }
}

async function pullCustomModel() {
  if (!newModelName.value || getPullStatus(newModelName.value)?.status === 'pulling') return
  const name = newModelName.value.trim()
  await pullModel(name)
}

async function cancelPull(modelName: string) {
  const name = (modelName || '').trim()
  if (!name) return
  try {
    await apiRequest('/api/config/cancel-pull', {
      method: 'POST',
      body: JSON.stringify({ model_name: name })
    })
    toast.info(`已取消下载: ${name}`)
  } catch (error: any) {
    toast.error('取消下载失败: ' + error.message)
  }
}

async function saveExternalConfig() {
  isSaving.value = true
  try {
    await apiRequest('/api/config/set', { method: 'POST', body: JSON.stringify({ key: 'llm_provider', value: 'external' }) })
    await apiRequest('/api/config/set', { method: 'POST', body: JSON.stringify({ key: 'external_llm_endpoint', value: config.value.external.endpoint }) })
    await apiRequest('/api/config/set', { method: 'POST', body: JSON.stringify({ key: 'external_llm_api_key', value: config.value.external.api_key }) })
    await apiRequest('/api/config/set', { method: 'POST', body: JSON.stringify({ key: 'external_llm_model', value: config.value.external.model }) })
    config.value.provider = 'external'
    toast.success('外部 API 配置已保存，下次启动将自动连接')
  } catch (error: any) {
    toast.error('保存失败: ' + error.message)
  } finally {
    isSaving.value = false
  }
}

async function testExternalConnection() {
  isTesting.value = true
  testResult.value = null
  try {
    const res = await apiRequest<{ success: boolean; message?: string; error?: string }>('/api/config/test-external')
    if (res.success) {
      testResult.value = { success: true, message: '✅ ' + (res.message || '连接成功') }
      toast.success('连接测试成功')
    } else {
      testResult.value = { success: false, message: '❌ ' + (res.error || '连接失败') }
    }
  } catch (error: any) {
    testResult.value = { success: false, message: '❌ 请求异常: ' + error.message }
  } finally {
    isTesting.value = false
  }
}
</script>

<style scoped>
.model-view {
  padding: 24px 32px;
  height: 100%;
  overflow-y: auto;
}

.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--color-border);
}

.title h1 {
  font-size: 24px;
  margin-bottom: 4px;
  color: var(--color-text);
}

.title p {
  color: var(--color-text-secondary);
  font-size: 14px;
}

.global-switch {
  display: flex;
  align-items: center;
  gap: 12px;
  background: var(--color-surface);
  padding: 10px 16px;
  border-radius: 8px;
  box-shadow: var(--shadow);
  border: 1px solid var(--color-border);
}

.label {
  font-weight: 500;
  font-size: 14px;
}

.switch {
  position: relative;
  display: inline-block;
  width: 44px;
  height: 24px;
}
.switch input { opacity: 0; width: 0; height: 0; }
.slider {
  position: absolute;
  cursor: pointer;
  top: 0; left: 0; right: 0; bottom: 0;
  background-color: #ccc;
  transition: .4s;
}
.slider:before {
  position: absolute;
  content: "";
  height: 18px; width: 18px;
  left: 3px; bottom: 3px;
  background-color: white;
  transition: .4s;
}
input:checked + .slider { background-color: var(--color-success); }
input:checked + .slider:before { transform: translateX(20px); }
.slider.round { border-radius: 24px; }
.slider.round:before { border-radius: 50%; }

.content-body {
  transition: opacity 0.3s;
}
.content-body.disabled {
  opacity: 0.5;
  pointer-events: none;
}

.disabled-notice {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 14px 18px;
  background: #fffbeb;
  border: 1px solid #fde68a;
  border-radius: 8px;
  margin-bottom: 20px;
  font-size: 13px;
  color: #92400e;
  line-height: 1.5;
}
.disabled-notice .notice-icon { font-size: 18px; flex-shrink: 0; }

.provider-selector {
  display: flex;
  gap: 12px;
  margin-bottom: 24px;
}

.provider-btn {
  flex: 1;
  padding: 16px;
  border: 2px solid var(--color-border);
  background: var(--color-surface);
  border-radius: 12px;
  cursor: pointer;
  font-size: 16px;
  font-weight: 600;
  color: var(--color-text-secondary);
  transition: all 0.2s;
}
.provider-btn:hover {
  border-color: #cbd5e1;
}
.provider-btn.active {
  border-color: var(--color-primary);
  background: var(--color-primary-bg);
  color: var(--color-primary);
}

.settings-card {
  background: var(--color-surface);
  border-radius: 12px;
  padding: 24px;
  box-shadow: var(--shadow);
  border: 1px solid var(--color-border);
}

.settings-card h3 {
  font-size: 18px;
  margin-bottom: 16px;
  color: var(--color-text);
}

.status-box {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 16px;
  background: #f1f5f9;
  border-radius: 8px;
  margin-bottom: 24px;
  font-weight: 500;
}
.status-indicator {
  width: 10px; height: 10px;
  border-radius: 50%;
  background: var(--color-error);
}
.status-box.online .status-indicator {
  background: var(--color-success);
}
.status-box.online {
  background: #ecfdf5;
  color: #065f46;
}

.model-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.model-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  border: 1px solid var(--color-border);
  border-radius: 8px;
  background: #fafafa;
}
.model-item.active {
  border-color: var(--color-primary);
  background: #f0fdf4;
}
.model-info {
  display: flex;
  align-items: center;
  gap: 12px;
}
.model-meta {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.model-info .name {
  font-weight: 600;
  font-size: 15px;
}
.model-info .size {
  font-size: 12px;
  color: var(--color-text-secondary);
}
.badge {
  background: var(--color-success);
  color: white;
  padding: 2px 8px;
  border-radius: 12px;
  font-size: 12px;
}
.badge-embedding {
  background: #6366f1;
}

.empty-state {
  text-align: center;
  padding: 24px;
  color: var(--color-text-secondary);
}
.empty-icon {
  font-size: 40px;
  margin-bottom: 8px;
}

.ollama-offline {
  text-align: center;
  padding: 32px;
  color: var(--color-text-secondary);
}

.recommend-section {
  margin-top: 12px;
}
.section-hint {
  font-size: 13px;
  color: var(--color-text-secondary);
  margin-bottom: 12px;
}

.recommend-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
  margin-bottom: 16px;
}

.recommend-card {
  padding: 16px;
  border: 1px solid var(--color-border);
  border-radius: 10px;
  background: #fafafa;
  transition: border-color 0.2s;
}
.recommend-card.installed {
  border-color: var(--color-success);
  background: #f0fdf4;
}
.recommend-card.pulling {
  border-color: var(--color-primary);
  background: #eff6ff;
}

.rec-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}
.rec-icon {
  font-size: 20px;
}
.rec-name {
  font-weight: 600;
  font-size: 15px;
}
.rec-desc {
  font-size: 13px;
  color: var(--color-text-secondary);
  margin: 4px 0;
  line-height: 1.4;
}
.rec-size {
  font-size: 12px;
  color: #6b7280;
  margin-bottom: 8px;
}

.rec-status {
  margin-top: 8px;
  font-size: 13px;
  font-weight: 500;
}
.rec-status.installed {
  color: var(--color-success);
}
.rec-status.pulling {
  color: var(--color-primary);
}
.rec-status.failed {
  color: var(--color-error);
  display: flex;
  align-items: center;
  gap: 8px;
}
.rec-status.completed {
  color: var(--color-success);
}

.progress-bar {
  width: 100%;
  height: 6px;
  background: #e2e8f0;
  border-radius: 3px;
  overflow: hidden;
  margin: 6px 0;
}
.progress-fill {
  height: 100%;
  background: var(--color-primary);
  border-radius: 3px;
  transition: width 0.3s ease;
}
.progress-text {
  font-size: 12px;
  color: var(--color-text-secondary);
}

.btn-download {
  padding: 6px 16px;
  border: none;
  border-radius: 6px;
  background: var(--color-primary);
  color: white;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: opacity 0.2s;
}
.btn-download:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
.btn-download:hover:not(:disabled) {
  opacity: 0.9;
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
  margin-top: 6px;
}

.custom-progress {
  margin-top: 12px;
}

.download-box {
  display: flex;
  gap: 12px;
}
.input-field {
  flex: 1;
  padding: 10px 14px;
  border: 1px solid var(--color-border);
  border-radius: 6px;
  font-size: 14px;
  outline: none;
}
.input-field:focus {
  border-color: var(--color-primary);
}

.btn-primary, .btn-secondary, .btn-switch {
  padding: 10px 20px;
  border: none;
  border-radius: 6px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: opacity 0.2s;
}
.btn-primary { background: var(--color-primary); color: white; }
.btn-primary:disabled { opacity: 0.6; cursor: not-allowed; }
.btn-secondary { background: #e2e8f0; color: #333; }
.btn-switch { background: #e2e8f0; color: #333; padding: 6px 14px; font-size: 13px; }
.btn-switch:hover { background: #cbd5e1; }

.form-group {
  margin-bottom: 16px;
}
.form-group label {
  display: block;
  margin-bottom: 6px;
  font-weight: 500;
  color: var(--color-text-secondary);
}

.actions {
  display: flex;
  gap: 12px;
  margin-top: 24px;
}

.test-result {
  margin-top: 16px;
  padding: 12px;
  border-radius: 6px;
  font-weight: 500;
}
.test-result.success { background: #ecfdf5; color: #065f46; }
.test-result.error { background: #fef2f2; color: #991b1b; }

.hint {
  font-size: 13px;
  color: var(--color-text-secondary);
  margin-top: 6px;
}
.mt-4 { margin-top: 24px; }
.mb-4 { margin-bottom: 16px; }

@media (max-width: 768px) {
  .recommend-grid {
    grid-template-columns: 1fr;
  }
}
</style>
