<template>
  <!-- 关闭状态下的“启动器”：有活跃任务时出现，允许用户手动打开 -->
  <div v-if="showLauncher" class="task-launcher-wrap" :title="'查看任务（' + tasks.items.length + '）'">
    <button class="task-launcher" @click="openPanel">任务 {{ tasks.items.length }}</button>
    <button class="task-launcher-close" @click="dismissLauncher" title="隐藏任务提示">×</button>
  </div>

  <!-- 主面板：有任务自动弹出；没任务自动隐藏 -->
  <div v-else-if="showPanel" class="task-panel" :class="{ minimized: collapsed }">
    <div class="task-panel-header">
      <span>任务 <span class="count">{{ tasks.items.length }}</span></span>
      <div class="header-actions">
        <button class="icon-btn" @click="tasks.refresh" :disabled="tasks.loading" title="刷新">↻</button>
        <button class="icon-btn" @click="toggleCollapse" :title="collapsed ? '展开' : '最小化'">
          {{ collapsed ? '▢' : '—' }}
        </button>
        <button class="icon-btn" @click="closePanel" title="关闭">×</button>
      </div>
    </div>

    <div v-if="tasks.items.length === 0" class="empty">暂无任务</div>

    <div v-if="collapsed && tasks.items.length > 0" class="mini-summary">
      <div v-for="t in tasks.items.slice(0, 2)" :key="t.id" class="mini-row">
        <span class="mini-type">{{ t.type }}</span>
        <span class="mini-progress">{{ t.progress || 0 }}%</span>
      </div>
      <div v-if="tasks.items.length > 2" class="mini-more">+{{ tasks.items.length - 2 }}…</div>
    </div>

    <div v-show="!collapsed">
      <div v-for="t in tasks.items" :key="t.id" class="task-item">
        <div class="row">
          <div class="type">{{ t.type }}</div>
          <div class="status" :class="t.status">{{ t.status }}</div>
        </div>
        <div class="msg">{{ t.message }}</div>
        <div class="progress">
          <div class="bar" :style="{ width: (t.progress || 0) + '%' }"></div>
        </div>
        <div class="actions">
          <button class="btn" v-if="t.status === 'running'" @click="tasks.pause(t.id)">暂停</button>
          <button class="btn" v-if="t.status === 'paused' || t.status === 'blocked'" @click="tasks.resume(t.id)">继续</button>
          <button class="btn danger" @click="tasks.cancel(t.id)">取消</button>
        </div>
        <div v-if="t.status === 'blocked'" class="blocked">原因：{{ t.blocked_reason }}</div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useTasksStore } from '../stores/tasks'

const tasks = useTasksStore()

// 状态持久化（验收要求）
// - dm-task-panel-hidden：是否隐藏面板（用户点 × 关闭）
// - dm-task-panel-collapsed：是否最小化（用户点 — 最小化）
const hidden = ref(localStorage.getItem('dm-task-panel-hidden') === 'true')
const collapsed = ref(localStorage.getItem('dm-task-panel-collapsed') === 'true')

const hasTasks = computed(() => tasks.items.length > 0)
const launcherDismissed = ref(localStorage.getItem('dm-task-launcher-dismissed') === 'true')
const showPanel = computed(() => hasTasks.value && !hidden.value)
const showLauncher = computed(() => hasTasks.value && hidden.value && !launcherDismissed.value)

// 默认行为：无任务时自动隐藏（不改变用户“隐藏”选择）
watch(
  () => tasks.items.length,
  (len) => {
    if (len === 0) {
      // 任务清空后，自动恢复 launcher（避免用户下次完全找不到入口）
      launcherDismissed.value = false
      localStorage.setItem('dm-task-launcher-dismissed', 'false')
      return
    }
    // 有任务且未隐藏：确保可见（showPanel 由计算属性控制，此处用于首次加载补齐本地存储状态）
  },
  { immediate: true }
)

function toggleCollapse() {
  collapsed.value = !collapsed.value
  localStorage.setItem('dm-task-panel-collapsed', String(collapsed.value))
}

function closePanel() {
  hidden.value = true
  localStorage.setItem('dm-task-panel-hidden', 'true')
}

function openPanel() {
  hidden.value = false
  localStorage.setItem('dm-task-panel-hidden', 'false')
}

function dismissLauncher() {
  launcherDismissed.value = true
  localStorage.setItem('dm-task-launcher-dismissed', 'true')
}
</script>

<style scoped>
.task-launcher-wrap {
  position: fixed;
  right: 12px;
  bottom: 12px;
  z-index: 50;
  display: flex;
  align-items: center;
  gap: 6px;
}

.task-launcher {
  padding: 8px 10px;
  border-radius: 999px;
  border: 1px solid var(--color-border);
  background: var(--color-surface);
  box-shadow: var(--shadow);
  font-size: 12px;
  color: var(--color-text);
  cursor: pointer;
}

.task-launcher-close {
  width: 26px;
  height: 26px;
  border-radius: 999px;
  border: 1px solid var(--color-border);
  background: var(--color-surface);
  box-shadow: var(--shadow);
  font-size: 14px;
  line-height: 1;
  color: var(--color-text-secondary);
  cursor: pointer;
}

.task-launcher-close:hover {
  background: var(--color-hover-bg);
  color: var(--color-text);
}

.task-launcher:hover {
  background: var(--color-hover-bg);
}

.task-panel {
  position: fixed;
  right: 12px;
  bottom: 12px;
  width: 320px;
  max-height: 50vh;
  overflow: auto;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 10px;
  padding: 10px;
  z-index: 50;
}

.task-panel.minimized {
  width: 240px;
  max-height: unset;
}

.task-panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.count {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 18px;
  height: 18px;
  padding: 0 6px;
  border-radius: 999px;
  background: var(--color-primary-bg);
  color: var(--color-primary);
  font-size: 12px;
  margin-left: 6px;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 6px;
}

.icon-btn {
  width: 26px;
  height: 26px;
  border-radius: 6px;
  border: 1px solid var(--color-border);
  background: transparent;
  cursor: pointer;
  font-size: 12px;
  line-height: 1;
  color: var(--color-text-secondary);
}

.icon-btn:hover {
  background: var(--color-hover-bg);
  color: var(--color-text);
}

.icon-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.mini-summary {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-top: 2px;
}

.mini-row {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  font-size: 12px;
  color: var(--color-text-secondary);
}

.mini-type {
  color: var(--color-text);
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 160px;
}

.mini-progress {
  color: var(--color-text-secondary);
}

.mini-more {
  font-size: 12px;
  color: var(--color-text-tertiary);
}

.task-item {
  border-top: 1px solid var(--color-border);
  padding-top: 8px;
  margin-top: 8px;
}

.row {
  display: flex;
  justify-content: space-between;
  gap: 8px;
}

.type {
  font-weight: 600;
}

.status {
  font-size: 12px;
  opacity: 0.9;
}

.msg {
  font-size: 12px;
  color: var(--color-text-secondary);
  margin: 6px 0;
}

.progress {
  height: 6px;
  background: rgba(0, 0, 0, 0.08);
  border-radius: 99px;
  overflow: hidden;
}

.bar {
  height: 100%;
  background: var(--color-primary);
}

.actions {
  display: flex;
  gap: 8px;
  margin-top: 8px;
}

.btn {
  font-size: 12px;
  padding: 4px 8px;
  border: 1px solid var(--color-border);
  border-radius: 6px;
  background: transparent;
}

.danger {
  border-color: var(--color-error);
  color: var(--color-error);
}

.blocked {
  margin-top: 6px;
  font-size: 12px;
  color: var(--color-warning);
}

.empty {
  font-size: 12px;
  color: var(--color-text-secondary);
}
</style>
