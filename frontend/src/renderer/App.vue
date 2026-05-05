<template>
  <div class="app-container">
    <div class="app-body">
      <TopNav
        :startup-status="startupStatus"
        :backend-running="backendStatus.isRunning"
        :show-middle-panel="showMiddlePanel"
        :middle-panel-collapsed="middlePanelCollapsed"
      />

      <div class="app-main">
        <Sidebar
          :selected-tab="selectedTab"
          @update:selected-tab="selectedTab = $event"
          ref="sidebarRef"
        />

        <div v-show="showMiddlePanel" class="middle-panel" :class="{ collapsed: middlePanelCollapsed, 'no-transition': isResizing }" :style="middlePanelStyle">
          <div class="middle-panel-header">
            <h3>知识库</h3>
            <div class="kb-search-wrapper">
              <svg class="kb-search-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
              <input
                v-model="knowledgeSearchKeyword"
                class="kb-search-input"
                type="text"
                placeholder="搜索文件..."
                @input="onKnowledgeSearch"
              />
              <button v-if="knowledgeSearchKeyword" class="kb-search-clear" @click="clearKnowledgeSearch" title="清除搜索">×</button>
            </div>
            <button class="panel-toggle-btn" @click="toggleMiddlePanel" :title="middlePanelCollapsed ? '展开' : '折叠'">
              {{ middlePanelCollapsed ? '▶' : '◀' }}
            </button>
          </div>
          <div v-show="!middlePanelCollapsed" class="middle-panel-content">
            <FileTree :base-path="storagePath" :search-keyword="knowledgeSearchKeyword" @select-file="handleSelectFile" />
          </div>
          <div
            v-show="!middlePanelCollapsed"
            class="middle-resize-handle"
            :class="{ resizing: isResizing }"
            @mousedown="startResize"
          ></div>
        </div>

        <main class="main-content">
          <ErrorBoundary>
            <keep-alive :include="['ChatView']">
              <component :is="currentView" :key="selectedTab" :selected-file="selectedFile" />
            </keep-alive>
          </ErrorBoundary>
        </main>
      </div>

      <button
        v-show="showMiddlePanel && middlePanelCollapsed"
        class="middle-expand-btn"
        @click="toggleMiddlePanel"
        title="展开知识库"
      >▶</button>

      <!-- 后端断开时允许用户进入“设置”页（例如切换存储路径/查看状态），避免全局遮罩导致无法操作 -->
      <div v-if="!isInitializing && !backendStatus.isRunning && !isBackendRestarting && !isStoragePathChanging && selectedTab !== 'settings'" class="global-overlay">
        <div class="overlay-card" v-if="backendStatus.state === 'starting' || backendStatus.state === 'idle'">
          <div class="overlay-icon rotating">⏳</div>
          <h2 class="starting-title">系统启动中</h2>
          <p>DiamondMemory 核心服务正在启动，请稍候...</p>
          <p class="hint">正在拉起本地大模型与数据库引擎</p>
        </div>
        <div class="overlay-card" v-else>
          <div class="overlay-icon">🔌</div>
          <h2>服务已断开</h2>
          <p>DiamondMemory 核心后端服务已停止运行，系统无法继续工作。</p>
          <p class="hint">请检查端口是否被占用，或尝试重启服务。</p>
          <div class="overlay-actions mt-4">
            <button class="btn-secondary" @click="openSettings">去设置</button>
            <button class="btn-primary" @click="restartService" :disabled="isRestarting">
              {{ isRestarting ? '重启中...' : '尝试重启核心服务' }}
            </button>
          </div>
        </div>
      </div>
    </div>

    <ToastContainer />
    <ShortcutsHelp :visible="showShortcutsHelp" @close="showShortcutsHelp = false" />
    <UpdateNotification ref="updateNotificationRef" />
    <InitialSetupWizard
      :visible="showInitialSetupWizard"
      :backend-running="backendStatus.isRunning"
      :storage-path="storagePath"
      :startup-status="startupStatus"
      @dismiss="onInitialSetupDismiss"
      @complete="onInitialSetupComplete"
      @open-settings="openSettings"
    />
    <OllamaSetup :visible="showOllamaSetup" @complete="onOllamaSetupComplete" @skip="onOllamaSetupSkip" @close="onOllamaSetupClose" />
    <ModelSetup :visible="showModelSetup" :startup-status="startupStatus" @skip="onModelSetupSkip" @close="onModelSetupClose" @open-settings="onModelSetupOpenSettings" />
    <TaskPanel />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, provide, watch } from 'vue'
import DashboardView from './views/DashboardView.vue'
import MemoryView from './views/MemoryView.vue'
import KnowledgeView from './views/KnowledgeView.vue'
import ChatView from './views/ChatView.vue'
import KnowledgeGraphView from './views/KnowledgeGraphView.vue'
import SettingsView from './views/SettingsView.vue'
import ProfileView from './views/ProfileView.vue'
import FeedbackView from './views/FeedbackView.vue'
import FileTree from './components/FileTree.vue'
import Sidebar from './components/Sidebar.vue'
import TopNav from './components/TopNav.vue'
import ToastContainer from './components/ToastContainer.vue'
import ErrorBoundary from './components/ErrorBoundary.vue'
import ShortcutsHelp from './components/ShortcutsHelp.vue'
import UpdateNotification from './components/UpdateNotification.vue'
import InitialSetupWizard from './components/InitialSetupWizard.vue'
import OllamaSetup from './components/OllamaSetup.vue'
import ModelSetup from './components/ModelSetup.vue'
import TaskPanel from './components/TaskPanel.vue'
import { getBackendStatus, updateBackendPort, restartBackend, apiRequest, rebuildKnowledgeMemoryExports } from './api/backend'
import { useInterval } from './composables/useTimer'
import { APP_CONFIG } from './config/constants'
import { syncKnowledgeTree } from './utils/knowledge-tree-events'
import { requestGraphRefresh } from './utils/graph-events'
import { shouldClearSelectedFile } from './utils/path-utils'
import { useTasksStore } from './stores/tasks'

const tabComponents: Record<string, any> = {
  dashboard: DashboardView,
  chat: ChatView,
  memory: MemoryView,
  knowledge: KnowledgeView,
  graph: KnowledgeGraphView,
  settings: SettingsView,
  profile: ProfileView,
  feedback: FeedbackView,
}

const selectedTab = ref('dashboard')
const backendStatus = ref<{ isRunning: boolean; state?: string; port: number }>({ isRunning: false, state: 'idle', port: APP_CONFIG.BACKEND_DEFAULT_PORT })
const startupStatus = ref({
  backend_ready: false,
  ollama_ready: false,
  llm_model_name: '',
  embedding_model_name: 'bge-m3',
  llm_installed: false,
  llm_loaded: false,
  embedding_installed: false,
  embedding_loaded: false,
  warmup_phase: 'idle',
  last_error: ''
})
const isInitializing = ref(true)
const isRestarting = ref(false)
const showShortcutsHelp = ref(false)
const middlePanelCollapsed = ref(localStorage.getItem('dm-middle-panel-collapsed') === 'true')
const middlePanelWidth = ref(parseInt(localStorage.getItem('dm-middle-panel-width') || '260', 10))
const isResizing = ref(false)
const storagePath = ref('')
const selectedFile = ref<{ name: string; path: string; extension?: string } | null>(null)
const knowledgeSearchKeyword = ref('')
const isBackendRestarting = ref(false)
const isStoragePathChanging = ref(localStorage.getItem('dm-storage-path-changing') === 'true')
const showOllamaSetup = ref(false)
const showModelSetup = ref(false)
const showInitialSetupWizard = ref(false)
const appRunId = ref('')
const hasKnowledgeExportsRebuilt = ref(false)
const isRebuildingKnowledgeExports = ref(false)
const updateNotificationRef = ref<any>(null)
const tasksStore = useTasksStore()

const showMiddlePanel = computed(() => selectedTab.value === 'knowledge')

const middlePanelStyle = computed(() => {
  if (middlePanelCollapsed.value) return {}
  return {
    width: `${middlePanelWidth.value}px`,
    minWidth: `${middlePanelWidth.value}px`,
  }
})

const currentView = computed(() => {
  return tabComponents[selectedTab.value] || DashboardView
})

function switchTab(tabId: string) {
  selectedTab.value = tabId
}

function toggleMiddlePanel() {
  middlePanelCollapsed.value = !middlePanelCollapsed.value
  localStorage.setItem('dm-middle-panel-collapsed', String(middlePanelCollapsed.value))
}

provide('switchTab', switchTab)
provide('setBackendRestarting', (val: boolean) => { isBackendRestarting.value = val })
provide('setStoragePathChanging', (val: boolean) => { isStoragePathChanging.value = val; localStorage.setItem('dm-storage-path-changing', String(val)) })
provide('checkForUpdates', () => {
  updateNotificationRef.value?.checkForUpdates(true)
})
provide('refreshKnowledgeBaseState', async (force = true, newPath?: string) => {
  if (newPath) {
    storagePath.value = newPath
    if (window.electronAPI?.setStoragePath) await window.electronAPI.setStoragePath(newPath)
    if (window.electronAPI?.initStorageDir) await window.electronAPI.initStorageDir(newPath)
    // 切换工作区后，旧选中文件可能已不在新路径允许范围内（否则会触发"访问被拒绝"）
    if (shouldClearSelectedFile(selectedFile.value?.path, newPath)) {
      selectedFile.value = null
    }
    // 统一时序：Electron -> 后端 storage_path -> 重建导出
    if (backendStatus.value.isRunning) {
      try {
        await apiRequest('/api/config/storage-path', {
          method: 'POST',
          body: JSON.stringify({ path: newPath }),
        })
      } catch {
        // ignore（后端可能正在启动/重连）
      }
    }
  } else {
    await loadStoragePath()
  }
  hasKnowledgeExportsRebuilt.value = false
  await ensureKnowledgeTreeReady(force)
  requestGraphRefresh()
})
provide('startupStatus', startupStatus)
provide('openSettings', openSettings)

const MIN_WIDTH = 160
const MAX_WIDTH = 600

function startResize(e: MouseEvent) {
  e.preventDefault()
  isResizing.value = true
  const startX = e.clientX
  const startWidth = middlePanelWidth.value

  function onMouseMove(moveEvent: MouseEvent) {
    const diff = moveEvent.clientX - startX
    const newWidth = Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, startWidth + diff))
    middlePanelWidth.value = newWidth
  }

  function onMouseUp() {
    isResizing.value = false
    localStorage.setItem('dm-middle-panel-width', String(middlePanelWidth.value))
    document.removeEventListener('mousemove', onMouseMove)
    document.removeEventListener('mouseup', onMouseUp)
  }

  document.addEventListener('mousemove', onMouseMove)
  document.addEventListener('mouseup', onMouseUp)
}

const { start: startStatusPoll, stop: stopStatusPoll } = useInterval(checkStatus, APP_CONFIG.BACKEND_STATUS_INTERVAL)

onMounted(async () => {
  localStorage.removeItem('dm-ollama-setup-dismissed')
  localStorage.removeItem('dm-model-setup-dismissed')
  localStorage.removeItem('dm-model-setup-skipped')
  sessionStorage.removeItem('dm-model-setup-dismissed')
  try { if (window.electronAPI?.getAppRunId) appRunId.value = await window.electronAPI.getAppRunId() } catch {}
  try {
    const firstRun = await window.electronAPI?.isFirstRun?.()
    if (firstRun && !localStorage.getItem('dm-initial-setup-dismissed')) {
      showInitialSetupWizard.value = true
    }
  } catch {}
  await Promise.all([checkStatus(), loadStoragePath()])
  isInitializing.value = false
  startStatusPoll()
  tasksStore.startPolling()
  window.addEventListener('keydown', handleGlobalKeydown)
})

onUnmounted(() => {
  stopStatusPoll()
  tasksStore.stopPolling()
  window.removeEventListener('keydown', handleGlobalKeydown)
})

watch(selectedTab, async (tab) => {
  if (tab === 'knowledge') {
    await ensureKnowledgeTreeReady()
  }
})

watch(storagePath, async () => {
  hasKnowledgeExportsRebuilt.value = false
  // 切换工作区后立即清空“越界”的旧文件选择，避免 IPC 访问被拒绝
  if (shouldClearSelectedFile(selectedFile.value?.path, storagePath.value)) {
    selectedFile.value = null
  }
  requestGraphRefresh()
  if (selectedTab.value === 'knowledge' && backendStatus.value.isRunning) {
    await ensureKnowledgeTreeReady(true)
  }
})

async function loadStoragePath() {
  try {
    if (backendStatus.value.isRunning) {
      try {
        const data = await apiRequest<{ path: string; storage_path: string }>('/api/config/storage-path')
        const sp = data.path || data.storage_path
        if (sp) {
          storagePath.value = sp
          if (window.electronAPI?.setStoragePath) {
            await window.electronAPI.setStoragePath(sp)
          }
          if (window.electronAPI?.initStorageDir) {
            await window.electronAPI.initStorageDir(sp)
          }
          return
        }
      } catch {}
    }
    if (window.electronAPI?.getStoragePath) {
      const savedPath = await window.electronAPI.getStoragePath()
      if (savedPath) {
        storagePath.value = savedPath
        if (window.electronAPI?.initStorageDir) await window.electronAPI.initStorageDir(savedPath)
      }
    }
  } catch {}
}

function handleSelectFile(file: { name: string; path: string; extension?: string }) {
  selectedFile.value = file
}

function onKnowledgeSearch() {}

function clearKnowledgeSearch() {
  knowledgeSearchKeyword.value = ''
}

async function ensureKnowledgeTreeReady(force = false) {
  if (!backendStatus.value.isRunning || !storagePath.value) return
  if (isRebuildingKnowledgeExports.value) return
  if (hasKnowledgeExportsRebuilt.value && !force) return

  isRebuildingKnowledgeExports.value = true
  try {
    await syncKnowledgeTree(rebuildKnowledgeMemoryExports)
    hasKnowledgeExportsRebuilt.value = true
  } catch (error) {
    console.error('知识库导出重建失败', error)
  } finally {
    isRebuildingKnowledgeExports.value = false
  }
}

function handleGlobalKeydown(e: KeyboardEvent) {
  const mod = e.metaKey || e.ctrlKey
  if (mod && e.key === APP_CONFIG.SHORTCUTS.SEARCH.key) {
    e.preventDefault(); selectedTab.value = 'knowledge'
  } else if (mod && e.key === APP_CONFIG.SHORTCUTS.NEW_MEMORY.key) {
    e.preventDefault(); selectedTab.value = 'memory'
  } else if (mod && e.key === 'j') {
    e.preventDefault(); selectedTab.value = 'chat'
  } else if (mod && e.key === APP_CONFIG.SHORTCUTS.SETTINGS.key) {
    e.preventDefault(); selectedTab.value = 'settings'
  } else if (mod && e.key === APP_CONFIG.SHORTCUTS.HELP.key) {
    e.preventDefault(); showShortcutsHelp.value = !showShortcutsHelp.value
  } else if (e.key === 'Escape') {
    showShortcutsHelp.value = false
  }
}

async function checkStatus() {
  try {
    const status = await getBackendStatus()
    backendStatus.value = status
    if (status.port) updateBackendPort(status.port)
  } catch {
    backendStatus.value = { isRunning: false, state: 'error', port: APP_CONFIG.BACKEND_DEFAULT_PORT }
  }
  try {
    if (backendStatus.value.isRunning) {
      startupStatus.value = await apiRequest('/api/config/startup-status')
    } else {
      startupStatus.value = {
        backend_ready: false,
        ollama_ready: false,
        llm_model_name: startupStatus.value.llm_model_name,
        embedding_model_name: 'bge-m3',
        llm_installed: false,
        llm_loaded: false,
        embedding_installed: false,
        embedding_loaded: false,
        warmup_phase: 'idle',
        last_error: ''
      }
    }
  } catch {
    startupStatus.value.warmup_phase = 'degraded'
    startupStatus.value.last_error = '无法获取启动状态'
  }

  if (showInitialSetupWizard.value) {
    showOllamaSetup.value = false
    showModelSetup.value = false
    return
  }

  try {
    if (backendStatus.value.isRunning && !startupStatus.value.ollama_ready) {
      const ollamaStatus = await apiRequest<{ installed: boolean; system_ollama: string | null }>('/api/ollama/install-status')
      if (ollamaStatus.installed) {
        showOllamaSetup.value = false
      } else if (!localStorage.getItem('dm-ollama-setup-skipped') && !localStorage.getItem('dm-ollama-setup-dismissed')) {
        showOllamaSetup.value = true
      }
    }
  } catch {}

  try {
    if (backendStatus.value.isRunning && !showOllamaSetup.value && startupStatus.value.ollama_ready) {
      const missing = !startupStatus.value.embedding_installed || !startupStatus.value.llm_installed
      const noModels = startupStatus.value.warmup_phase === 'no_models'
      const modelDismissed = isModelSetupSuppressedForRun()
      if (!missing && !noModels) {
        showModelSetup.value = false
      } else if ((missing || noModels) && !modelDismissed) {
        showModelSetup.value = true
      }
    }
  } catch {}
}

async function restartService() {
  isRestarting.value = true
  try { await restartBackend(); await checkStatus() } catch (error) { console.error('重启失败', error) }
  finally { isRestarting.value = false }
}

function openSettings() {
  selectedTab.value = 'settings'
}

function onOllamaSetupComplete() {
  showOllamaSetup.value = false
  checkStatus()
}

function onOllamaSetupSkip() {
  showOllamaSetup.value = false
  localStorage.setItem('dm-ollama-setup-skipped', 'true')
  selectedTab.value = 'settings'
}

function onOllamaSetupClose() {
  showOllamaSetup.value = false
  localStorage.setItem('dm-ollama-setup-dismissed', 'true')
  selectedTab.value = 'settings'
}

function onModelSetupSkip() {
  showModelSetup.value = false
  suppressModelSetupForRun()
  selectedTab.value = 'settings'
}

function onModelSetupClose() {
  showModelSetup.value = false
  suppressModelSetupForRun()
  selectedTab.value = 'settings'
}

function onModelSetupOpenSettings() {
  showModelSetup.value = false
  selectedTab.value = 'settings'
}

function isModelSetupSuppressedForRun(): boolean {
  const runId = appRunId.value
  if (!runId) return !!sessionStorage.getItem('dm-model-setup-dismissed')
  return localStorage.getItem('dm-model-setup-suppressed-run-id') === runId
}

function suppressModelSetupForRun() {
  const runId = appRunId.value
  if (runId) {
    localStorage.setItem('dm-model-setup-suppressed-run-id', runId)
  } else {
    sessionStorage.setItem('dm-model-setup-dismissed', 'true')
  }
}

function onInitialSetupDismiss() {
  showInitialSetupWizard.value = false
  localStorage.setItem('dm-initial-setup-dismissed', 'true')
  checkStatus()
}

async function onInitialSetupComplete(payload: { needsRestart: boolean }) {
  showInitialSetupWizard.value = false
  localStorage.setItem('dm-initial-setup-dismissed', 'true')
  if (payload.needsRestart && window.electronAPI?.relaunchApp) {
    const confirmed = window.confirm('存储路径已修改。为确保新工作区完全生效，建议立即重启应用。是否现在重启？')
    if (confirmed) {
      await window.electronAPI.relaunchApp()
      return
    }
  }
  checkStatus()
}
</script>

<style>
* { margin: 0; padding: 0; box-sizing: border-box; }

:root {
  --sidebar-width: 75px;
  --middle-panel-width: 260px;
  --top-nav-height: 48px;
  --color-primary: #3b82f6;
  --color-primary-hover: #2563eb;
  --color-primary-bg: rgba(59, 130, 246, 0.1);
  --color-success: #10b981;
  --color-success-hover: #059669;
  --color-success-bg: #ecfdf5;
  --color-success-text: #065f46;
  --color-warning: #f59e0b;
  --color-warning-hover: #d97706;
  --color-warning-bg: #fffbeb;
  --color-warning-text: #92400e;
  --color-error: #ef4444;
  --color-error-hover: #dc2626;
  --color-error-bg: #fef2f2;
  --color-error-text: #991b1b;
  --color-bg: #f8fafc;
  --color-surface: #ffffff;
  --color-surface-secondary: #f1f5f9;
  --color-sidebar: #ffffff;
  --color-text: #1e293b;
  --color-text-secondary: #64748b;
  --color-text-tertiary: #9ca3af;
  --color-border: #e2e8f0;
  --color-border-hover: #cbd5e1;
  --color-overlay: rgba(0, 0, 0, 0.5);
  --color-overlay-light: rgba(255, 255, 255, 0.85);
  --color-scrollbar: #c1c9d4;
  --color-scrollbar-hover: #a0aab5;
  --color-code-bg: #1e293b;
  --color-code-text: #e2e8f0;
  --color-inline-code-bg: rgba(0, 0, 0, 0.06);
  --color-hover-bg: rgba(0, 0, 0, 0.04);
  --color-text-on-primary: #ffffff;
  --color-overlay-hover: rgba(0, 0, 0, 0.8);
  --color-indigo-bg: rgba(99, 102, 241, 0.12);
  --color-indigo-bg-subtle: rgba(99, 102, 241, 0.1);
  --color-indigo-border: rgba(99, 102, 241, 0.2);
  --color-indigo-border-strong: rgba(99, 102, 241, 0.25);
  --color-cyan-bg: rgba(14, 165, 233, 0.12);
  --color-cyan-bg-subtle: rgba(14, 165, 233, 0.1);
  --color-cyan-border: rgba(14, 165, 233, 0.2);
  --color-cyan-border-strong: rgba(14, 165, 233, 0.25);
  --color-warning-bg-soft: rgba(245, 158, 11, 0.12);
  --color-warning-bg-subtle: rgba(245, 158, 11, 0.1);
  --color-warning-border: rgba(245, 158, 11, 0.2);
  --color-warning-border-strong: rgba(245, 158, 11, 0.25);
  --color-success-bg-soft: rgba(16, 185, 129, 0.12);
  --color-success-bg-subtle: rgba(16, 185, 129, 0.1);
  --color-success-border: rgba(16, 185, 129, 0.2);
  --color-success-border-strong: rgba(16, 185, 129, 0.25);
  --shadow-hover: 0 4px 12px rgba(0, 0, 0, 0.08);
  --color-level-1: #6366f1;
  --color-level-2: #3b82f6;
  --color-level-3: #10b981;
  --color-level-4: #f59e0b;
  --color-level-5: #8b5cf6;
  --color-level-6: #ec4899;
  --color-indigo: #6366f1;
  --color-violet: #8b5cf6;
  --color-pink: #ec4899;
  --color-cyan: #0891b2;
  --radius: 8px;
  --shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
}

:root[data-theme="dark"] {
  --color-primary: #60a5fa;
  --color-primary-hover: #93bbfd;
  --color-primary-bg: rgba(96, 165, 250, 0.15);
  --color-success: #34d399;
  --color-success-hover: #6ee7b7;
  --color-success-bg: rgba(52, 211, 153, 0.12);
  --color-success-text: #6ee7b7;
  --color-warning: #fbbf24;
  --color-warning-hover: #fcd34d;
  --color-warning-bg: rgba(251, 191, 36, 0.12);
  --color-warning-text: #fcd34d;
  --color-error: #f87171;
  --color-error-hover: #fca5a5;
  --color-error-bg: rgba(248, 113, 113, 0.12);
  --color-error-text: #fca5a5;
  --color-bg: #0f1117;
  --color-surface: #1a1b23;
  --color-surface-secondary: #22232d;
  --color-sidebar: #1a1b23;
  --color-text: #e2e8f0;
  --color-text-secondary: #94a3b8;
  --color-text-tertiary: #64748b;
  --color-border: #2e3039;
  --color-border-hover: #3e4049;
  --color-overlay: rgba(0, 0, 0, 0.7);
  --color-overlay-light: rgba(0, 0, 0, 0.85);
  --color-scrollbar: #3e4049;
  --color-scrollbar-hover: #4e5059;
  --color-code-bg: #0d0e14;
  --color-code-text: #e2e8f0;
  --color-inline-code-bg: rgba(255, 255, 255, 0.08);
  --color-hover-bg: rgba(255, 255, 255, 0.05);
  --color-text-on-primary: #0f1117;
  --color-overlay-hover: rgba(0, 0, 0, 0.9);
  --color-indigo-bg: rgba(129, 140, 248, 0.15);
  --color-indigo-bg-subtle: rgba(129, 140, 248, 0.12);
  --color-indigo-border: rgba(129, 140, 248, 0.25);
  --color-indigo-border-strong: rgba(129, 140, 248, 0.3);
  --color-cyan-bg: rgba(34, 211, 238, 0.15);
  --color-cyan-bg-subtle: rgba(34, 211, 238, 0.12);
  --color-cyan-border: rgba(34, 211, 238, 0.25);
  --color-cyan-border-strong: rgba(34, 211, 238, 0.3);
  --color-warning-bg-soft: rgba(251, 191, 36, 0.15);
  --color-warning-bg-subtle: rgba(251, 191, 36, 0.12);
  --color-warning-border: rgba(251, 191, 36, 0.25);
  --color-warning-border-strong: rgba(251, 191, 36, 0.3);
  --color-success-bg-soft: rgba(52, 211, 153, 0.15);
  --color-success-bg-subtle: rgba(52, 211, 153, 0.12);
  --color-success-border: rgba(52, 211, 153, 0.25);
  --color-success-border-strong: rgba(52, 211, 153, 0.3);
  --shadow-hover: 0 4px 12px rgba(0, 0, 0, 0.3);
  --color-level-1: #818cf8;
  --color-level-2: #60a5fa;
  --color-level-3: #34d399;
  --color-level-4: #fbbf24;
  --color-level-5: #a78bfa;
  --color-level-6: #f472b6;
  --color-indigo: #818cf8;
  --color-violet: #a78bfa;
  --color-pink: #f472b6;
  --color-cyan: #22d3ee;
  --shadow: 0 1px 3px rgba(0, 0, 0, 0.3);
}

html { scroll-behavior: smooth; }

body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
  background-color: var(--color-bg);
  color: var(--color-text);
  overflow: hidden;
  -webkit-font-smoothing: antialiased;
}

#app { width: 100vw; height: 100vh; }

::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: var(--color-scrollbar); border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: var(--color-scrollbar-hover); }
::-webkit-scrollbar-corner { background: transparent; }

* { scrollbar-width: thin; scrollbar-color: var(--color-scrollbar) transparent; }

.app-container {
  display: flex;
  flex-direction: column;
  height: 100vh;
  width: 100vw;
}

.app-body {
  display: flex;
  flex-direction: column;
  flex: 1;
  overflow: hidden;
}

.app-main {
  display: flex;
  flex: 1;
  overflow: hidden;
}

.middle-panel {
  position: relative;
  background: var(--color-surface);
  border-right: 1px solid var(--color-border);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  transition: width 0.3s ease, min-width 0.3s ease;
}

.middle-panel.no-transition {
  transition: none !important;
}

.middle-panel.collapsed {
  width: 0 !important;
  min-width: 0 !important;
  border-right: none;
}

.middle-resize-handle {
  position: absolute;
  right: -4px;
  top: 0;
  bottom: 0;
  width: 8px;
  cursor: col-resize;
  z-index: 10;
}

.middle-resize-handle:hover,
.middle-resize-handle.resizing {
  background: var(--color-primary);
  opacity: 0.15;
}

.middle-panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 14px;
  border-bottom: 1px solid var(--color-border);
  min-height: 44px;
  white-space: nowrap;
  overflow: hidden;
  gap: 8px;
}

.middle-panel-header h3 {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text);
  flex-shrink: 0;
}

.kb-search-wrapper {
  display: flex;
  align-items: center;
  flex: 1;
  min-width: 0;
  height: 28px;
  padding: 0 8px;
  border-radius: 6px;
  background: var(--color-surface-secondary);
  border: 1px solid var(--color-border);
  transition: border-color 0.15s, box-shadow 0.15s;
}

.kb-search-wrapper:focus-within {
  border-color: var(--color-primary);
  box-shadow: 0 0 0 2px var(--color-primary-bg);
}

.kb-search-icon {
  flex-shrink: 0;
  color: var(--color-text-tertiary);
  margin-right: 4px;
}

.kb-search-input {
  flex: 1;
  min-width: 0;
  border: none;
  outline: none;
  background: transparent;
  font-size: 12px;
  color: var(--color-text);
  line-height: 28px;
}

.kb-search-input::placeholder {
  color: var(--color-text-tertiary);
}

.kb-search-clear {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  border: none;
  background: var(--color-text-tertiary);
  color: white;
  border-radius: 50%;
  font-size: 11px;
  cursor: pointer;
  line-height: 1;
  padding: 0;
  transition: background 0.15s;
}

.kb-search-clear:hover {
  background: var(--color-text-secondary);
}

.panel-toggle-btn {
  background: none;
  border: none;
  cursor: pointer;
  font-size: 11px;
  color: var(--color-text-secondary);
  padding: 4px 6px;
  border-radius: 4px;
}
.panel-toggle-btn:hover { background: var(--color-hover-bg); }

.middle-panel-content {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
}

.middle-expand-btn {
  position: fixed;
  left: 80px;
  top: 60px;
  width: 28px;
  height: 40px;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-left: none;
  cursor: pointer;
  font-size: 12px;
  color: var(--color-primary);
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.15s;
  border-radius: 0 8px 8px 0;
  z-index: 9999;
  box-shadow: 2px 0 6px rgba(0, 0, 0, 0.06);
}
.middle-expand-btn:hover { 
  background: var(--color-primary-bg); 
  color: var(--color-primary-hover);
}

.main-content {
  flex: 1;
  overflow: hidden;
  background: var(--color-bg);
  position: relative;
}

.global-overlay {
  position: fixed; top: 0; left: 0; right: 0; bottom: 0;
  background: var(--color-overlay-light); backdrop-filter: blur(4px);
  z-index: 1000; display: flex; align-items: center; justify-content: center;
}
.overlay-card {
  background: var(--color-surface); padding: 40px; border-radius: 16px; text-align: center;
  box-shadow: 0 10px 25px rgba(0,0,0,0.1); max-width: 400px; border: 1px solid var(--color-border);
}
.overlay-icon { font-size: 48px; margin-bottom: 16px; }
.rotating { animation: spin 2s linear infinite; display: inline-block; }
@keyframes spin { 100% { transform: rotate(360deg); } }
.overlay-card h2 { font-size: 20px; color: var(--color-error); margin-bottom: 12px; }
.overlay-card h2.starting-title { color: var(--color-primary); }
.overlay-card p { color: var(--color-text); font-size: 14px; line-height: 1.5; margin-bottom: 8px; }
.overlay-card .hint { color: var(--color-text-secondary); font-size: 13px; }
.btn-primary { padding: 10px 20px; background: var(--color-primary); color: white; border: none; border-radius: 8px; cursor: pointer; font-size: 14px; font-weight: 500; transition: background 0.15s; }
.btn-primary:hover { background: var(--color-primary-hover); }
.btn-primary:disabled { opacity: 0.6; cursor: not-allowed; }
.btn-secondary {
  padding: 10px 20px;
  background: var(--color-surface);
  color: var(--color-text);
  border: 1px solid var(--color-border);
  border-radius: 8px;
  cursor: pointer;
  font-size: 14px;
  font-weight: 500;
  transition: background 0.15s, border-color 0.15s;
}
.btn-secondary:hover { background: var(--color-surface-secondary); border-color: var(--color-primary); }
.overlay-actions { display: flex; gap: 10px; justify-content: center; }
.mt-4 { margin-top: 16px; }
</style>
