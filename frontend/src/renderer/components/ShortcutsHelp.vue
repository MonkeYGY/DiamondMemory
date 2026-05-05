<template>
  <transition name="modal-fade">
    <div v-if="visible" class="shortcuts-overlay" @click.self="$emit('close')">
      <div class="shortcuts-modal">
        <div class="modal-header">
          <h3>键盘快捷键</h3>
          <button class="close-btn" @click="$emit('close')">✕</button>
        </div>
        <div class="shortcuts-list">
          <div v-for="shortcut in shortcuts" :key="shortcut.key" class="shortcut-item">
            <span class="shortcut-label">{{ shortcut.label }}</span>
            <span class="shortcut-keys">
              <kbd>{{ modKey }}</kbd>
              <span class="plus">+</span>
              <kbd>{{ shortcut.key }}</kbd>
            </span>
          </div>
          <div class="shortcut-item">
            <span class="shortcut-label">关闭弹窗</span>
            <span class="shortcut-keys"><kbd>Esc</kbd></span>
          </div>
        </div>
      </div>
    </div>
  </transition>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { APP_CONFIG } from '../config/constants'

defineProps<{ visible: boolean }>()
defineEmits<{ close: [] }>()

const modKey = computed(() => navigator.platform.includes('Mac') ? '⌘' : 'Ctrl')

const shortcuts = [
  { key: APP_CONFIG.SHORTCUTS.SEARCH.key, label: APP_CONFIG.SHORTCUTS.SEARCH.label },
  { key: APP_CONFIG.SHORTCUTS.NEW_MEMORY.key, label: APP_CONFIG.SHORTCUTS.NEW_MEMORY.label },
  { key: APP_CONFIG.SHORTCUTS.SETTINGS.key, label: APP_CONFIG.SHORTCUTS.SETTINGS.label },
  { key: APP_CONFIG.SHORTCUTS.HELP.key, label: APP_CONFIG.SHORTCUTS.HELP.label }
]
</script>

<style scoped>
.shortcuts-overlay {
  position: fixed;
  top: 0; left: 0; right: 0; bottom: 0;
  background: var(--color-overlay);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 200;
}
.shortcuts-modal {
  background: var(--color-surface);
  border-radius: 12px;
  padding: 24px;
  width: 380px;
  max-width: 90vw;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.2);
}
.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}
.modal-header h3 {
  margin: 0;
  font-size: 18px;
  color: var(--color-text);
}
.close-btn {
  background: none;
  border: none;
  font-size: 16px;
  cursor: pointer;
  color: var(--color-text-secondary);
  padding: 4px;
}
.close-btn:hover { color: var(--color-text); }

.shortcuts-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.shortcut-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 0;
  border-bottom: 1px solid var(--color-bg);
}
.shortcut-item:last-child { border-bottom: none; }
.shortcut-label {
  font-size: 14px;
  color: var(--color-text);
}
.shortcut-keys {
  display: flex;
  align-items: center;
  gap: 4px;
}
kbd {
  display: inline-block;
  padding: 3px 8px;
  font-size: 12px;
  font-family: inherit;
  background: var(--color-bg);
  border: 1px solid var(--color-border);
  border-radius: 4px;
  box-shadow: 0 1px 0 var(--color-border);
  color: var(--color-text);
  min-width: 24px;
  text-align: center;
  user-select: text;
  -webkit-user-select: text;
  cursor: text;
}
.plus {
  font-size: 12px;
  color: var(--color-text-secondary);
}

.modal-fade-enter-active, .modal-fade-leave-active {
  transition: opacity 0.2s ease;
}
.modal-fade-enter-from, .modal-fade-leave-to {
  opacity: 0;
}
</style>
