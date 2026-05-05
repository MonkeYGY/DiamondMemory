<template>
  <div class="toast-container">
    <transition-group name="toast-list">
      <div 
        v-for="toast in toasts" 
        :key="toast.id" 
        class="toast-item" 
        :class="`toast-${toast.type}`"
      >
        <span class="toast-icon">{{ getIcon(toast.type) }}</span>
        <span class="toast-message">{{ toast.message }}</span>
        <button class="toast-close" @click="removeToast(toast.id)">&times;</button>
      </div>
    </transition-group>
  </div>
</template>

<script setup lang="ts">
import { useToast, ToastType } from '../composables/useToast'

const { toasts, removeToast } = useToast()

const getIcon = (type: ToastType) => {
  switch(type) {
    case 'success': return '✅'
    case 'error': return '❌'
    case 'warning': return '⚠️'
    case 'info': return 'ℹ️'
    default: return '💬'
  }
}
</script>

<style scoped>
.toast-container {
  position: fixed;
  top: 20px;
  right: 20px;
  z-index: 9999;
  display: flex;
  flex-direction: column;
  gap: 10px;
  pointer-events: none;
}

.toast-item {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 250px;
  max-width: 400px;
  padding: 12px 16px;
  border-radius: 8px;
  background: var(--color-surface);
  box-shadow: var(--shadow);
  pointer-events: auto;
  font-size: 14px;
  color: var(--color-text);
  border-left: 4px solid transparent;
}

.toast-success { border-left-color: var(--color-success); }
.toast-error { border-left-color: var(--color-error); }
.toast-warning { border-left-color: var(--color-warning); }
.toast-info { border-left-color: var(--color-primary); }

.toast-message {
  flex: 1;
}

.toast-close {
  background: none;
  border: none;
  font-size: 18px;
  cursor: pointer;
  color: var(--color-text-tertiary);
}
.toast-close:hover {
  color: var(--color-text);
}

/* Vue Transition */
.toast-list-enter-active,
.toast-list-leave-active {
  transition: all 0.3s ease;
}
.toast-list-enter-from {
  opacity: 0;
  transform: translateX(30px);
}
.toast-list-leave-to {
  opacity: 0;
  transform: translateX(30px);
}
</style>
