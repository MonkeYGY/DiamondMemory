<template>
  <nav class="sidebar" ref="sidebarEl">
    <div class="nav-scroll">
      <div class="nav-group">
        <div
          v-for="item in mainNavItems"
          :key="item.id"
          class="nav-item"
          :class="{ active: selectedTab === item.id }"
          @click="$emit('update:selectedTab', item.id)"
        >
          <div class="nav-icon-wrapper">
            <svg v-if="item.id === 'dashboard'" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <rect width="7" height="9" x="3" y="3" rx="1"/>
              <rect width="7" height="5" x="14" y="3" rx="1"/>
              <rect width="7" height="9" x="14" y="12" rx="1"/>
              <rect width="7" height="5" x="3" y="16" rx="1"/>
            </svg>
            <svg v-else-if="item.id === 'chat'" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M7.9 20A9 9 0 1 0 4 16.1L2 22z"/>
            </svg>
            <svg v-else-if="item.id === 'memory'" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M12 5a3 3 0 1 0-5.997.125 4 4 0 0 0-2.526 5.77 4 4 0 0 0 .556 6.588A4 4 0 1 0 12 18Z"/>
              <path d="M12 5a3 3 0 1 1 5.997.125 4 4 0 0 1 2.526 5.77 4 4 0 0 1-.556 6.588A4 4 0 1 1 12 18Z"/>
              <path d="M15 13a4.5 4.5 0 0 1-3-4 4.5 4.5 0 0 1-3 4"/>
              <path d="M17.599 6.5a3 3 0 0 0 .399-1.375"/>
              <path d="M6.003 5.125A3 3 0 0 0 6.401 6.5"/>
              <path d="M3.477 10.896a4 4 0 0 1 .585-.396"/>
              <path d="M19.938 10.5a4 4 0 0 1 .585.396"/>
              <path d="M6 18a4 4 0 0 1-1.967-.516"/>
              <path d="M19.967 17.484A4 4 0 0 1 18 18"/>
            </svg>
            <svg v-else-if="item.id === 'knowledge'" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H20v20H6.5a2.5 2.5 0 0 1 0-5H20"/>
            </svg>
          </div>
          <span class="nav-label">{{ item.label }}</span>
        </div>
      </div>

      <div class="nav-group">
        <div
          class="nav-item"
          :class="{ active: selectedTab === 'knowledge' }"
          @click="$emit('update:selectedTab', 'knowledge')"
        >
          <div class="nav-icon-wrapper">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H20v20H6.5a2.5 2.5 0 0 1 0-5H20"/>
            </svg>
          </div>
          <span class="nav-label">知识库</span>
        </div>

        <div
          class="nav-item"
          :class="{ active: selectedTab === 'graph' }"
          @click="$emit('update:selectedTab', 'graph')"
        >
          <div class="nav-icon-wrapper">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <circle cx="12" cy="5" r="3"/>
              <circle cx="5" cy="19" r="3"/>
              <circle cx="19" cy="19" r="3"/>
              <line x1="12" y1="8" x2="5" y2="16"/>
              <line x1="12" y1="8" x2="19" y2="16"/>
              <line x1="5" y1="19" x2="19" y2="19"/>
            </svg>
          </div>
          <span class="nav-label">图谱</span>
        </div>
      </div>

      <div class="nav-group">
        <div
          class="nav-item"
          :class="{ active: selectedTab === 'memory' }"
          @click="$emit('update:selectedTab', 'memory')"
        >
          <div class="nav-icon-wrapper">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M12 5a3 3 0 1 1 5.997.125 4 4 0 0 1 2.526 5.77 4 4 0 0 1-.556 6.588A4 4 0 1 1 12 18Z"/>
              <path d="M12 5a3 3 0 1 0-5.997.125 4 4 0 0 0-2.526 5.77 4 4 0 0 0 .556 6.588A4 4 0 1 0 12 18Z"/>
              <path d="M15 13a4.5 4.5 0 0 1-3-4 4.5 4.5 0 0 1-3 4"/>
              <path d="M17.599 6.5a3 3 0 0 0 .399-1.375"/>
              <path d="M6.003 5.125A3 3 0 0 0 6.401 6.5"/>
              <path d="M3.477 10.896a4 4 0 0 1 .585-.396"/>
              <path d="M19.938 10.5a4 4 0 0 1 .585.396"/>
              <path d="M6 18a4 4 0 0 1-1.967-.516"/>
              <path d="M19.967 17.484A4 4 0 0 1 18 18"/>
            </svg>
          </div>
          <span class="nav-label">记忆</span>
          <span v-if="memoryStore.isOrganizing" class="organizing-indicator" title="正在整理记忆..."></span>
        </div>
      </div>

      <div class="nav-group">
        <div
          class="nav-item"
          :class="{ active: selectedTab === 'settings' }"
          @click="$emit('update:selectedTab', 'settings')"
        >
          <div class="nav-icon-wrapper">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/>
              <circle cx="12" cy="12" r="3"/>
            </svg>
          </div>
          <span class="nav-label">设置</span>
        </div>

        <div
          class="nav-item"
          :class="{ active: selectedTab === 'feedback' }"
          @click="$emit('update:selectedTab', 'feedback')"
        >
          <div class="nav-icon-wrapper">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
            </svg>
          </div>
          <span class="nav-label">反馈</span>
        </div>
      </div>
    </div>
    <div class="sidebar-footer">
      <div class="avatar-wrapper" @click="$emit('update:selectedTab', 'profile')" :class="{ active: selectedTab === 'profile' }">
        <div class="avatar-circle">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"/>
            <circle cx="12" cy="7" r="4"/>
          </svg>
        </div>
        <span class="avatar-label">我的</span>
      </div>
    </div>
  </nav>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useMemoryStore } from '../stores/memory'

defineProps<{
  selectedTab: string
}>()

defineEmits<{
  'update:selectedTab': [value: string]
}>()

const memoryStore = useMemoryStore()
const sidebarEl = ref<HTMLElement | null>(null)

const mainNavItems = [
  { id: 'dashboard', label: '仪表盘' },
  { id: 'chat', label: '会话' },
]


</script>

<style scoped>
.sidebar {
  position: relative;
  flex-shrink: 0;
  z-index: 10;
  display: flex;
  flex-direction: column;
  background: var(--color-sidebar);
  border-right: 1px solid var(--color-border);
  overflow: hidden;
  width: var(--sidebar-width);
  min-width: var(--sidebar-width);
  -webkit-app-region: no-drag;
}

.nav-scroll {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
  padding: 12px 8px 8px;
}

.nav-group {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.nav-separator {
  height: 1px;
  background: var(--color-border);
  margin: 8px 4px;
}

.nav-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 4px;
  padding: 8px 8px;
  border-radius: var(--radius);
  cursor: pointer;
  transition: background 0.15s ease, color 0.15s ease;
  position: relative;
  user-select: none;
  white-space: nowrap;
  overflow: hidden;
  min-height: 60px;
}

.nav-item:hover {
  background: var(--color-hover-bg);
}

.nav-item.active {
  background: var(--color-primary-bg);
}

.nav-item.active .nav-icon-wrapper {
  color: var(--color-primary);
}

.nav-item.active .nav-label {
  color: var(--color-primary);
  font-weight: 500;
}

.nav-icon-wrapper {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  flex-shrink: 0;
  color: var(--color-text-secondary);
  transition: color 0.15s;
}

.nav-label {
  font-size: 11px;
  color: var(--color-text-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 100%;
  text-align: center;
  transition: color 0.15s;
}

.organizing-indicator {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--color-primary);
  flex-shrink: 0;
  animation: organizing-pulse 1.2s ease-in-out infinite;
}

@keyframes organizing-pulse {
  0%, 100% { opacity: 1; box-shadow: 0 0 4px var(--color-primary-bg); }
  50% { opacity: 0.4; box-shadow: 0 0 2px var(--color-primary-bg); }
}

.sidebar-footer {
  padding: 12px 8px;
  display: flex;
  justify-content: center;
  align-items: center;
}

.avatar-wrapper {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  cursor: pointer;
  padding: 8px;
  border-radius: var(--radius);
  transition: background 0.15s ease;
  user-select: none;
}

.avatar-wrapper:hover {
  background: var(--color-hover-bg);
}

.avatar-circle {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: var(--color-primary-bg);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--color-primary);
  transition: all 0.15s ease;
}

.avatar-wrapper.active .avatar-circle {
  background: var(--color-primary);
  color: var(--color-text-on-primary);
}

.avatar-label {
  font-size: 11px;
  color: var(--color-text-secondary);
  transition: color 0.15s;
}

.avatar-wrapper.active .avatar-label {
  color: var(--color-primary);
  font-weight: 500;
}
</style>
