<template>
  <header class="top-nav">
    <div class="top-nav-left">
      <div class="logo-area">
        <svg class="logo-icon" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M6 3h12l4 6-10 13L2 9z"/>
          <path d="M11 3L8 9l4 13 4-13-3-6"/>
          <path d="M2 9h20"/>
        </svg>
        <span class="logo-text">钻石记忆系统</span>
      </div>
    </div>

    <div class="top-nav-center">
      <div class="drag-region" @dblclick="handleMaximize"></div>
    </div>

    <div class="top-nav-right">
      <div class="model-statuses">
        <div class="model-status" :title="embeddingStatusText">
          <div class="status-dot" :class="embeddingPhase"></div>
          <span class="status-text">{{ embeddingStatusText }}</span>
        </div>
        <div class="model-status-divider"></div>
        <div class="model-status" :title="llmStatusText">
          <div class="status-dot" :class="llmPhase"></div>
          <span class="status-text">{{ llmStatusText }}</span>
        </div>
      </div>
    </div>
  </header>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  startupStatus: {
    backend_ready: boolean
    ollama_ready: boolean
    llm_model_name: string
    embedding_model_name: string
    llm_installed: boolean
    llm_loaded: boolean
    embedding_installed: boolean
    embedding_loaded: boolean
    warmup_phase: string
    last_error: string
  }
  backendRunning: boolean
  showMiddlePanel?: boolean
  middlePanelCollapsed?: boolean
}>()

defineEmits<{
  'open-login': []
}>()

function getPhase(installed: boolean, loaded: boolean) {
  if (loaded) return 'ready'
  if (!props.startupStatus.ollama_ready) return 'offline'
  if (!installed) return 'missing'
  if (props.startupStatus.warmup_phase === 'warming_up') return 'warming'
  if (props.startupStatus.warmup_phase === 'no_models') return 'missing'
  return 'offline'
}

const embeddingPhase = computed(() => getPhase(
  props.startupStatus.embedding_installed,
  props.startupStatus.embedding_loaded
))

const llmPhase = computed(() => getPhase(
  props.startupStatus.llm_installed,
  props.startupStatus.llm_loaded
))

const embeddingStatusText = computed(() => {
  if (embeddingPhase.value === 'ready') {
    return 'BGE-M3 已就绪'
  }
  if (embeddingPhase.value === 'warming') {
    return 'BGE-M3 预热中'
  }
  if (embeddingPhase.value === 'missing') {
    return 'BGE-M3 未安装'
  }
  return 'BGE-M3 未启动'
})

const llmStatusText = computed(() => {
  const name = props.startupStatus.llm_model_name || '主模型'
  if (llmPhase.value === 'ready') {
    return `${name} 已就绪`
  }
  if (llmPhase.value === 'warming') {
    return `${name} 预热中`
  }
  if (!props.backendRunning) {
    return `${name} 未启动`
  }
  if (!props.startupStatus.ollama_ready) {
    return 'Ollama 未启动'
  }
  if (llmPhase.value === 'missing') {
    return `${name} 未安装`
  }
  return `${name} 未启动`
})

function handleMaximize() {
  (window.electronAPI as any).toggleMaximize?.()
}
</script>

<style scoped>
.top-nav {
  height: 36px;
  min-height: 36px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 12px;
  background: var(--color-surface);
  border-bottom: 1px solid var(--color-border);
  -webkit-app-region: drag;
  position: relative;
  z-index: 20;
}

.top-nav-left {
  display: flex;
  align-items: center;
  gap: 8px;
  -webkit-app-region: no-drag;
  padding-left: 70px;
}

.logo-area {
  display: flex;
  align-items: center;
  gap: 8px;
}

.logo-icon {
  color: var(--color-primary);
  flex-shrink: 0;
}

.logo-text {
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text);
  white-space: nowrap;
  letter-spacing: 0.5px;
}

.top-nav-center {
  flex: 1;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
}

.drag-region {
  width: 100%;
  height: 100%;
  -webkit-app-region: drag;
}

.top-nav-right {
  display: flex;
  align-items: center;
  gap: 16px;
  -webkit-app-region: no-drag;
  margin-right: 20px;
}

.model-statuses {
  display: flex;
  align-items: center;
  gap: 10px;
}

.model-status-divider {
  width: 1px;
  height: 14px;
  background: var(--color-border);
  flex-shrink: 0;
}

.model-status {
  display: flex;
  align-items: center;
  gap: 6px;
  cursor: default;
}

.status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
  transition: background 0.2s;
}

.status-dot.offline {
  background: var(--color-error);
}

.status-dot.warming {
  background: var(--color-warning);
}

.status-dot.ready {
  background: var(--color-success);
}

.status-dot.missing {
  background: var(--color-warning);
}

.status-text {
  font-size: 13px;
  color: var(--color-text-secondary);
  white-space: nowrap;
}
</style>
