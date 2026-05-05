<template>
  <div v-if="error" class="error-boundary">
    <div class="error-content">
      <div class="error-icon">⚠️</div>
      <h3>页面渲染异常</h3>
      <p class="error-message">{{ error.message }}</p>
      <button @click="resetError" class="btn-retry">重试</button>
    </div>
  </div>
  <slot v-else />
</template>

<script setup lang="ts">
import { ref, onErrorCaptured } from 'vue'

const error = ref<Error | null>(null)

onErrorCaptured((err) => {
  error.value = err
  console.error('[ErrorBoundary]', err)
  return false
})

function resetError() {
  error.value = null
}
</script>

<style scoped>
.error-boundary {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  padding: 40px;
}
.error-content {
  text-align: center;
  max-width: 400px;
}
.error-icon {
  font-size: 48px;
  margin-bottom: 16px;
}
h3 {
  font-size: 18px;
  color: var(--color-text);
  margin: 0 0 12px;
}
.error-message {
  font-size: 13px;
  color: var(--color-text-secondary);
  background: var(--color-bg);
  padding: 12px;
  border-radius: 8px;
  margin: 0 0 20px;
  word-break: break-all;
  line-height: 1.5;
}
.btn-retry {
  padding: 8px 24px;
  border: none;
  border-radius: 8px;
  background: var(--color-primary);
  color: var(--color-text-on-primary);
  font-size: 13px;
  cursor: pointer;
  font-weight: 500;
}
.btn-retry:hover {
  background: var(--color-primary-hover);
}
</style>
