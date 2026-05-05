<template>
  <div class="view-container">
    <div class="view-header">
      <div class="header-text">
        <h2>仪表盘</h2>
        <p class="subtitle">智能记忆系统，让AI拥有持久化记忆</p>
      </div>
    </div>

    <div class="section-title">数据概览</div>
    <div class="stats-grid">
      <div class="stat-card">
        <div class="stat-header">
          <div class="stat-icon purple">🧠</div>
          <span class="stat-badge purple">{{ memoryStore.stats.totalMemories > 0 ? '实时' : '离线' }}</span>
        </div>
        <div class="stat-value">{{ memoryStore.stats.totalMemories || 0 }}</div>
        <div class="stat-label">总记忆数</div>
      </div>
      <div class="stat-card">
        <div class="stat-header">
          <div class="stat-icon blue">➕</div>
          <span class="stat-badge blue">{{ todayGrowthText }}</span>
        </div>
        <div class="stat-value">{{ memoryStore.stats.todayCount || 0 }}</div>
        <div class="stat-label">今日新增</div>
      </div>
      <div class="stat-card">
        <div class="stat-header">
          <div class="stat-icon orange">📁</div>
          <span class="stat-badge orange">{{ memoryStore.stats.categoryCount > 0 ? '活跃' : '暂无' }}</span>
        </div>
        <div class="stat-value">{{ memoryStore.stats.categoryCount || 0 }}</div>
        <div class="stat-label">记忆分类</div>
      </div>
      <div class="stat-card">
        <div class="stat-header">
          <div class="stat-icon green">✅</div>
          <span class="stat-badge green">{{ memoryStore.stats.systemStatus === '正常' ? '运行中' : '异常' }}</span>
        </div>
        <div class="stat-value">{{ memoryStore.stats.systemStatus || '正常' }}</div>
        <div class="stat-label">系统状态</div>
      </div>
    </div>

    <div class="section-title">核心功能</div>
    <div class="features-grid">
      <div class="feature-card" @click="switchTab('memory')">
        <div class="feature-header">
          <div class="feature-icon purple">📄</div>
          <span class="feature-badge">热门</span>
        </div>
        <h3>记忆管理</h3>
        <p>创建、查询、管理智能记忆</p>
      </div>
      <div class="feature-card" @click="switchTab('knowledge')">
        <div class="feature-header">
          <div class="feature-icon blue">🔍</div>
          <span class="feature-badge blue">AI驱动</span>
        </div>
        <h3>智能检索</h3>
        <p>基于语义的记忆检索</p>
      </div>
      <div class="feature-card" @click="switchTab('chat')">
        <div class="feature-header">
          <div class="feature-icon orange">🧪</div>
          <span class="feature-badge orange">Beta</span>
        </div>
        <h3>知识推理</h3>
        <p>基于记忆的智能推理</p>
      </div>
      <div class="feature-card" @click="switchTab('chat')">
        <div class="feature-header">
          <div class="feature-icon green">🔗</div>
          <span class="feature-badge green">新功能</span>
        </div>
        <h3>采集中心</h3>
        <p>上传文档、网页采集</p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, computed, inject } from 'vue'
import { useMemoryStore } from '../stores/memory'
import { useInterval } from '../composables/useTimer'
import { APP_CONFIG } from '../config/constants'

const memoryStore = useMemoryStore()

const switchTab = inject<(tab: string) => void>('switchTab', () => {})

const todayGrowthText = computed(() => {
  const count = memoryStore.stats.todayCount || 0
  if (count > 0) return `+${count}`
  return '今日'
})

const { start: startAutoRefresh } = useInterval(async () => {
  try { await memoryStore.fetchStats() } catch {}
}, APP_CONFIG.BACKEND_STATUS_INTERVAL)

onMounted(async () => {
  try { await memoryStore.fetchStats() } catch {}
  startAutoRefresh()
})


</script>

<style scoped>
.view-container {
  padding: 24px;
  height: 100%;
  overflow-y: auto;
  overflow-x: hidden;
}

.view-header {
  margin-bottom: 28px;
}

.header-text h2 {
  font-size: 24px;
  font-weight: 700;
  color: var(--color-text);
  margin: 0 0 4px 0;
}

.subtitle {
  font-size: 13px;
  color: var(--color-text-secondary);
  margin: 0;
}

.section-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text);
  margin-bottom: 14px;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin-bottom: 28px;
}

.stat-card {
  padding: 16px;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 12px;
  box-shadow: var(--shadow);
  min-height: 120px;
  display: flex;
  flex-direction: column;
}

.stat-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.stat-icon {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
}

.stat-icon.purple { background: var(--color-indigo-bg); }
.stat-icon.blue { background: var(--color-cyan-bg); }
.stat-icon.orange { background: var(--color-warning-bg-soft); }
.stat-icon.green { background: var(--color-success-bg-soft); }

.stat-badge {
  font-size: 10px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 10px;
}

.stat-badge.purple { color: var(--color-indigo); background: var(--color-indigo-bg-subtle); border: 1px solid var(--color-indigo-border); }
.stat-badge.blue { color: var(--color-cyan); background: var(--color-cyan-bg-subtle); border: 1px solid var(--color-cyan-border); }
.stat-badge.orange { color: var(--color-warning); background: var(--color-warning-bg-subtle); border: 1px solid var(--color-warning-border); }
.stat-badge.green { color: var(--color-success); background: var(--color-success-bg-subtle); border: 1px solid var(--color-success-border); }

.stat-value {
  font-size: 24px;
  font-weight: 700;
  color: var(--color-text);
}

.stat-label {
  font-size: 12px;
  color: var(--color-text-secondary);
  margin-top: 2px;
}

.features-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin-bottom: 20px;
}

.feature-card {
  padding: 16px;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 12px;
  box-shadow: var(--shadow);
  cursor: pointer;
  transition: all 0.2s ease;
  min-height: 120px;
  display: flex;
  flex-direction: column;
}

.feature-card:hover {
  box-shadow: var(--shadow-hover);
  transform: translateY(-2px);
}

.feature-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.feature-icon {
  width: 32px;
  height: 32px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
}

.feature-icon.purple { background: var(--color-indigo-bg-subtle); }
.feature-icon.blue { background: var(--color-cyan-bg-subtle); }
.feature-icon.orange { background: var(--color-warning-bg-subtle); }
.feature-icon.green { background: var(--color-success-bg-subtle); }

.feature-badge {
  font-size: 9px;
  font-weight: 600;
  padding: 2px 6px;
  border-radius: 6px;
  background: var(--color-indigo-bg);
  border: 1px solid var(--color-indigo-border-strong);
}

.feature-badge.blue { background: var(--color-cyan-bg); color: var(--color-cyan); border-color: var(--color-cyan-border-strong); }
.feature-badge.orange { background: var(--color-warning-bg-soft); color: var(--color-warning); border-color: var(--color-warning-border-strong); }
.feature-badge.green { background: var(--color-success-bg-soft); color: var(--color-success); border-color: var(--color-success-border-strong); }

.feature-card h3 {
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text);
  margin: 0 0 4px 0;
}

.feature-card p {
  font-size: 12px;
  color: var(--color-text-secondary);
  margin: 0;
  line-height: 1.4;
}

@media (max-width: 900px) {
  .stats-grid, .features-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 600px) {
  .stats-grid, .features-grid {
    grid-template-columns: 1fr;
  }
}
</style>
