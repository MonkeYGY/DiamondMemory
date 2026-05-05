import { ref, computed, watch } from 'vue'

export type ThemeMode = 'light' | 'dark'

const STORAGE_KEY = 'dm-theme-mode'

const currentTheme = ref<ThemeMode>(
  (localStorage.getItem(STORAGE_KEY) as ThemeMode) || 'light'
)

function applyTheme(theme: ThemeMode) {
  document.documentElement.setAttribute('data-theme', theme)
}

export function useTheme() {
  applyTheme(currentTheme.value)

  watch(currentTheme, (newTheme) => {
    applyTheme(newTheme)
    localStorage.setItem(STORAGE_KEY, newTheme)
  })

  function toggleTheme() {
    currentTheme.value = currentTheme.value === 'light' ? 'dark' : 'light'
  }

  function setTheme(theme: ThemeMode) {
    currentTheme.value = theme
  }

  return {
    currentTheme,
    toggleTheme,
    setTheme,
    isDark: computed(() => currentTheme.value === 'dark')
  }
}
