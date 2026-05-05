<template>
  <div class="file-tree">
    <div v-if="!basePath" class="empty-hint">未设置存储路径</div>
    <div v-else-if="loading" class="loading-hint">加载中...</div>
    <div v-else-if="displayEntries.length === 0" class="empty-hint">
      <div>{{ searchKeyword ? '未找到匹配文件' : '文件夹为空' }}</div>
      <div v-if="!searchKeyword && depth === 0" class="empty-actions">
        <button class="btn-empty" @click="forceRebuildExports" :disabled="loading">强制重建导出</button>
        <button class="btn-empty" @click="forceSyncKnowledgeBase" :disabled="loading">强制同步</button>
      </div>
    </div>
    <div v-else class="tree-list">
      <div v-for="entry in displayEntries" :key="entry.path" class="tree-node">
        <div
          class="tree-item"
          :class="{ active: selectedPath === entry.path }"
          @click="handleClick(entry)"
        >
          <span v-if="entry.isDirectory && !searchKeyword" class="expand-arrow" :class="{ expanded: expandedPaths.has(entry.path) }">▶</span>
          <span v-else class="expand-arrow placeholder"></span>
          <span class="item-name">{{ entry.name }}</span>
        </div>
        <transition name="slide-down">
          <div v-if="entry.isDirectory && !searchKeyword && expandedPaths.has(entry.path)" class="tree-children">
            <FileTree
              :base-path="entry.path"
              :depth="depth + 1"
              :search-keyword="searchKeyword"
              @select-file="$emit('select-file', $event)"
            />
          </div>
        </transition>
      </div>
      <div
        v-if="!searchKeyword && hasMore && !loading"
        class="load-more"
        @click="loadMore"
      >
        加载更多…
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { KNOWLEDGE_TREE_REFRESH_EVENT } from '../utils/knowledge-tree-events'
import { apiRequest } from '../api/backend'

interface FileEntry {
  name: string
  path: string
  isDirectory: boolean
  extension?: string
  size?: number
  modifiedAt?: string
  isHidden?: boolean
}

const props = withDefaults(defineProps<{
  basePath: string
  depth?: number
  searchKeyword?: string
}>(), {
  depth: 0,
  searchKeyword: ''
})

const emit = defineEmits<{
  'select-file': [file: { name: string; path: string; extension?: string }]
}>()

const entries = ref<FileEntry[]>([])
const loading = ref(false)
const isFirstLoad = ref(true)
const hasMore = ref(false)
const nextOffset = ref<number | null>(null)
const pageSize = 300
const SYSTEM_FOLDERS = ['backups', 'qdrant_storage', 'temp', '__pycache__', '.git', '.vscode', 'node_modules']
const SYSTEM_FILES = ['storage_config.json', 'memory.db', 'memory.db-shm', 'memory.db-wal', 'embeddings.pkl', 'embedding_index.pkl']
const expandedPaths = ref<Set<string>>(new Set())
const selectedPath = ref('')
const searchResults = ref<FileEntry[]>([])
const isSearching = ref(false)

const displayEntries = computed(() => {
  const keyword = props.searchKeyword?.trim().toLowerCase()
  if (!keyword) return entries.value
  if (props.depth === 0) return searchResults.value
  return entries.value.filter(e => !e.isDirectory && e.name.toLowerCase().includes(keyword))
})

async function recursiveSearch(dirPath: string, keyword: string): Promise<FileEntry[]> {
  const results: FileEntry[][] = []
  try {
    if (window.electronAPI?.readDirectory) {
      const allEntries = (await window.electronAPI.readDirectory(dirPath)) as FileEntry[]
      const filtered = allEntries.filter((entry: FileEntry) => {
        if (entry.isHidden) return false
        if (entry.isDirectory && SYSTEM_FOLDERS.includes(entry.name)) return false
        if (!entry.isDirectory && SYSTEM_FILES.includes(entry.name)) return false
        return true
      })
      for (const entry of filtered) {
        if (!entry.isDirectory && entry.name.toLowerCase().includes(keyword)) {
          results.push([entry])
        }
        if (entry.isDirectory) {
          const subResults = await recursiveSearch(entry.path, keyword)
          if (subResults.length > 0) results.push(subResults)
        }
      }
    }
  } catch { /* ignore */ }
  return results.flat()
}

let refreshTimer: ReturnType<typeof setInterval> | null = null
const handleKnowledgeTreeRefresh = () => { void loadDirectory() }

onMounted(() => {
  loadDirectory()
  window.addEventListener(KNOWLEDGE_TREE_REFRESH_EVENT, handleKnowledgeTreeRefresh)
  if (props.depth === 0) {
    refreshTimer = setInterval(loadDirectory, 5000)
  }
})

onUnmounted(() => {
  window.removeEventListener(KNOWLEDGE_TREE_REFRESH_EVENT, handleKnowledgeTreeRefresh)
  if (refreshTimer) { clearInterval(refreshTimer); refreshTimer = null }
})

watch(() => props.basePath, () => {
  isFirstLoad.value = true
  loadDirectory()
})

watch(() => props.searchKeyword, async (keyword) => {
  if (!keyword?.trim() || props.depth !== 0) {
    searchResults.value = []
    return
  }
  if (!props.basePath) return
  isSearching.value = true
  try {
    const results = await recursiveSearch(props.basePath, keyword.trim().toLowerCase())
    searchResults.value = results
  } finally {
    isSearching.value = false
  }
})

async function loadDirectory() {
  if (!props.basePath) return
  if (isFirstLoad.value) loading.value = true
  try {
    if (window.electronAPI?.readDirectoryPaged) {
      const res = (await window.electronAPI.readDirectoryPaged(props.basePath, { offset: 0, limit: pageSize })) as {
        entries: FileEntry[]
        hasMore: boolean
        nextOffset: number | null
      }
      
      const filteredEntries = res.entries
      hasMore.value = res.hasMore
      nextOffset.value = res.nextOffset

      // 仅在根目录（depth === 0）进行特定文件夹的自定义排序
      if (props.depth === 0) {
        const SORT_ORDER = ['用户文档', '总结经验', '经验总结', '技能']
        filteredEntries.sort((a: FileEntry, b: FileEntry) => {
          const indexA = SORT_ORDER.indexOf(a.name)
          const indexB = SORT_ORDER.indexOf(b.name)
          
          // 如果都在自定义排序列表中，按列表顺序排序
          if (indexA !== -1 && indexB !== -1) return indexA - indexB
          // 如果只有一个在自定义列表中，在列表中的排前面
          if (indexA !== -1) return -1
          if (indexB !== -1) return 1
          
          // 如果都不在自定义列表中，文件夹排在文件前面
          if (a.isDirectory && !b.isDirectory) return -1
          if (!a.isDirectory && b.isDirectory) return 1
          
          // 最后按名称拼音字母顺序排序
          return a.name.localeCompare(b.name, 'zh-CN')
        })
      } else {
        // 子目录默认排序：文件夹在前，文件在后，同类型按名称排序
        filteredEntries.sort((a: FileEntry, b: FileEntry) => {
          if (a.isDirectory && !b.isDirectory) return -1
          if (!a.isDirectory && b.isDirectory) return 1
          return a.name.localeCompare(b.name, 'zh-CN')
        })
      }
      
      entries.value = filteredEntries
    } else if (window.electronAPI?.readDirectory) {
      // 兼容旧版本：无分页接口时回退全量读取
      const allEntries = (await window.electronAPI.readDirectory(props.basePath)) as FileEntry[]
      const filteredEntries = allEntries.filter((entry: FileEntry) => {
        if (entry.isHidden) return false
        if (entry.isDirectory && SYSTEM_FOLDERS.includes(entry.name)) return false
        if (!entry.isDirectory && SYSTEM_FILES.includes(entry.name)) return false
        return true
      })
      entries.value = filteredEntries
      hasMore.value = false
      nextOffset.value = null
    } else { entries.value = [] }
  } catch { entries.value = [] }
  finally {
    loading.value = false
    isFirstLoad.value = false
  }
}

async function loadMore() {
  if (!props.basePath) return
  if (!hasMore.value || nextOffset.value === null) return
  try {
    if (!window.electronAPI?.readDirectoryPaged) return
    const res = (await window.electronAPI.readDirectoryPaged(props.basePath, { offset: nextOffset.value, limit: pageSize })) as {
      entries: FileEntry[]
      hasMore: boolean
      nextOffset: number | null
    }
    entries.value = [...entries.value, ...res.entries]
    hasMore.value = res.hasMore
    nextOffset.value = res.nextOffset
  } catch {
    // ignore
  }
}

function handleClick(entry: FileEntry) {
  if (entry.isDirectory) {
    if (expandedPaths.value.has(entry.path)) {
      expandedPaths.value.delete(entry.path)
      expandedPaths.value = new Set(expandedPaths.value)
    } else {
      expandedPaths.value = new Set([...expandedPaths.value, entry.path])
    }
  } else {
    selectedPath.value = entry.path
    emit('select-file', { name: entry.name, path: entry.path, extension: entry.extension })
  }
}

async function forceRebuildExports() {
  if (!props.basePath) return
  try {
    await apiRequest('/api/knowledge/rebuild-memory-exports', { method: 'POST' })
  } catch {
    // ignore
  } finally {
    void loadDirectory()
  }
}

async function forceSyncKnowledgeBase() {
  if (!props.basePath) return
  try {
    await apiRequest('/api/knowledge/sync', { method: 'POST' })
  } catch {
    // ignore
  } finally {
    void loadDirectory()
  }
}
</script>

<style scoped>
.file-tree { font-size: 13px; }
.empty-hint, .loading-hint { padding: 8px 8px 8px 26px; color: var(--color-text-secondary); font-size: 12px; text-align: left; }
.empty-actions { display: flex; gap: 8px; margin-top: 10px; }
.btn-empty {
  padding: 4px 10px;
  border: 1px solid var(--color-border);
  border-radius: 6px;
  background: var(--color-surface);
  color: var(--color-text-secondary);
  font-size: 12px;
  cursor: pointer;
}
.btn-empty:hover { border-color: var(--color-primary); color: var(--color-primary); }
.tree-list { display: flex; flex-direction: column; }
.tree-node { display: flex; flex-direction: column; }
.tree-item {
  display: flex; align-items: center; gap: 4px;
  padding: 5px 8px; cursor: pointer; border-radius: 4px;
  transition: background 0.1s; white-space: nowrap; overflow: hidden;
}
.tree-item:hover { background: rgba(0, 0, 0, 0.04); }
.tree-item.active { background: var(--color-primary-bg); color: var(--color-primary); }
.expand-arrow {
  font-size: 9px; color: var(--color-text-secondary); width: 14px;
  text-align: center; flex-shrink: 0; transition: transform 0.2s;
}
.expand-arrow.expanded { transform: rotate(90deg); }
.expand-arrow.placeholder { visibility: hidden; }
.item-name { font-size: 13px; overflow: hidden; text-overflow: ellipsis; }
.tree-children { padding-left: 8px; }
.slide-down-enter-active, .slide-down-leave-active { transition: all 0.2s ease; overflow: hidden; }
.slide-down-enter-from, .slide-down-leave-to { opacity: 0; max-height: 0; }
.slide-down-enter-to, .slide-down-leave-from { opacity: 1; max-height: 500px; }
</style>
