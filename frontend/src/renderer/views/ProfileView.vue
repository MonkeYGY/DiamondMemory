<template>
  <div class="view-container">
    <div class="profile-container">
      <div class="profile-header">
        <div class="avatar-large">
          <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
            <path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"/>
            <circle cx="12" cy="7" r="4"/>
          </svg>
        </div>
        <div class="user-info">
          <h2>{{ userName }}</h2>
          <p class="user-role">钻石记忆系统用户</p>
        </div>
      </div>

      <div class="profile-sections">
        <section class="profile-section">
          <h3>账户信息</h3>
          <div class="info-list">
            <div class="info-row">
              <span class="info-label">用户名</span>
              <span class="info-value">{{ userName }}</span>
            </div>
            <div class="info-row">
              <span class="info-label">注册时间</span>
              <span class="info-value">{{ registerDate }}</span>
            </div>
            <div class="info-row">
              <span class="info-label">系统版本</span>
              <span class="info-value">{{ appVersion }}</span>
            </div>
          </div>
        </section>

        <section class="profile-section">
          <h3>使用统计</h3>
          <div class="stats-grid">
            <div class="stat-card">
              <div class="stat-number">{{ memoryCount }}</div>
              <div class="stat-label">记忆总数</div>
            </div>
            <div class="stat-card">
              <div class="stat-number">{{ knowledgeCount }}</div>
              <div class="stat-label">知识文档</div>
            </div>
            <div class="stat-card">
              <div class="stat-number">{{ chatCount }}</div>
              <div class="stat-label">会话次数</div>
            </div>
          </div>
        </section>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { getAppInfo, apiRequest } from '../api/backend'

const userName = ref('默认用户')
const registerDate = ref('')
const appVersion = ref('')
const memoryCount = ref(0)
const knowledgeCount = ref(0)
const chatCount = ref(0)

onMounted(async () => {
  try {
    const info = await getAppInfo()
    appVersion.value = info.version || ''
  } catch {}
  try {
    const stats: any = await apiRequest('/memory/memories/stats')
    memoryCount.value = stats.totalMemories || 0
  } catch {}
})
</script>

<style scoped>
.view-container { padding: 24px; height: 100%; overflow-y: auto; overflow-x: hidden; }

.profile-container { max-width: 600px; margin: 0 auto; }

.profile-header {
  display: flex;
  align-items: center;
  gap: 20px;
  padding-bottom: 24px;
  border-bottom: 1px solid var(--color-border);
  margin-bottom: 24px;
}

.avatar-large {
  width: 80px;
  height: 80px;
  border-radius: 50%;
  background: var(--color-primary-bg);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--color-primary);
  flex-shrink: 0;
}

.user-info h2 {
  margin: 0;
  font-size: 24px;
  font-weight: 600;
  color: var(--color-text);
}

.user-role {
  margin: 4px 0 0;
  font-size: 14px;
  color: var(--color-text-secondary);
}

.profile-sections {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.profile-section {
  background: var(--color-surface);
  border-radius: 12px;
  padding: 20px;
  box-shadow: var(--shadow);
  border: 1px solid var(--color-border);
}

.profile-section h3 {
  margin: 0 0 16px;
  font-size: 15px;
  font-weight: 600;
  color: var(--color-text);
  padding-bottom: 10px;
  border-bottom: 1px solid var(--color-border);
}

.info-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.info-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 0;
}

.info-label {
  color: var(--color-text-secondary);
  font-size: 13px;
}

.info-value {
  color: var(--color-text);
  font-size: 13px;
  font-weight: 500;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
}

.stat-card {
  background: var(--color-bg);
  border-radius: 8px;
  padding: 16px;
  text-align: center;
}

.stat-number {
  font-size: 24px;
  font-weight: 700;
  color: var(--color-primary);
  margin-bottom: 4px;
}

.stat-label {
  font-size: 12px;
  color: var(--color-text-secondary);
}
</style>
