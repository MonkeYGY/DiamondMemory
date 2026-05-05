<template>
  <div class="knowledge-view">
    <div v-if="!selectedFile" class="empty-state">
      <div class="empty-icon">📚</div>
      <h3>知识库</h3>
      <p>从左侧文件浏览器选择文件查看内容</p>
      <p class="hint">文件浏览器展示您存储路径下的所有文件和文件夹</p>
    </div>

    <div v-else class="file-preview">
      <div class="preview-header">
        <div class="file-info">
          <span class="file-icon">{{ getFileIcon(selectedFile.extension) }}</span>
          <span class="file-name">{{ selectedFile.name }}</span>
        </div>
        <button class="btn-copy" @click="copyContent" title="复制文件内容">📋 复制</button>
      </div>
      <div class="preview-content">
        <div v-if="loadingContent" class="loading">加载中...</div>
        <div v-else-if="renderedHtml" class="markdown-body" v-html="renderedHtml"></div>
        <div v-else class="no-content">无法读取文件内容</div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import { useToast } from '../composables/useToast'
import { renderKnowledgeMarkdown } from '../utils/memory-detail-markdown'

const toast = useToast()

const props = defineProps<{
  selectedFile?: { name: string; path: string; extension?: string } | null
}>()

const fileContent = ref('')
const loadingContent = ref(false)

const renderedHtml = computed(() => {
  if (!fileContent.value) return ''
  const ext = props.selectedFile?.extension?.toLowerCase() || ''
  if (['.md', '.markdown', '.txt', ''].includes(ext) || !ext) {
    return renderKnowledgeMarkdown(fileContent.value)
  }
  return ''
})

watch(() => props.selectedFile, async (newFile) => {
  if (newFile) {
    await loadFileContent(newFile.path)
  } else {
    fileContent.value = ''
  }
}, { immediate: true })

async function loadFileContent(filePath: string) {
  loadingContent.value = true
  fileContent.value = ''
  try {
    if (window.electronAPI?.readFileContent) {
      fileContent.value = await window.electronAPI.readFileContent(filePath)
    } else {
      fileContent.value = '[文件预览需要Electron环境支持]'
    }
  } catch (error: any) {
    fileContent.value = `[读取失败] ${error.message}`
  } finally {
    loadingContent.value = false
  }
}

function getFileIcon(extension?: string): string {
  const ext = extension || ''
  const iconMap: Record<string, string> = {
    '.md': '📝', '.txt': '📄', '.json': '📋', '.yaml': '📋', '.yml': '📋',
    '.csv': '📊', '.pdf': '📕', '.doc': '📘', '.docx': '📘',
    '.xls': '📗', '.xlsx': '📗', '.py': '🐍', '.js': '⚡', '.ts': '🔷',
    '.html': '🌐', '.css': '🎨', '.xml': '📰', '.sql': '🗃️',
  }
  return iconMap[ext] || '📄'
}

async function copyContent() {
  if (!fileContent.value) return
  try {
    await navigator.clipboard.writeText(fileContent.value)
    toast.success('文件内容已复制到剪贴板')
  } catch {
    toast.error('复制失败')
  }
}
</script>

<style scoped>
.knowledge-view {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
  padding-top: 32px;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  flex: 1;
  text-align: center;
  color: var(--color-text-secondary);
  padding: 40px 20px;
}

.empty-icon { font-size: 56px; margin-bottom: 16px; }
.empty-state h3 { font-size: 18px; color: var(--color-text); margin: 0 0 8px 0; }
.empty-state p { font-size: 14px; margin: 0 0 8px 0; }
.hint { font-size: 12px; color: var(--color-text-secondary); }

.file-preview {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}

.preview-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 20px;
  border-bottom: 1px solid var(--color-border);
  background: var(--color-surface);
  flex-shrink: 0;
}

.file-info {
  display: flex;
  align-items: center;
  gap: 8px;
}

.file-icon { font-size: 18px; }
.file-name { font-size: 14px; font-weight: 600; color: var(--color-text); }

.btn-copy {
  padding: 4px 12px;
  border: 1px solid var(--color-border);
  border-radius: 6px;
  background: var(--color-surface);
  color: var(--color-text-secondary);
  font-size: 12px;
  cursor: pointer;
  transition: all 0.15s;
}

.btn-copy:hover {
  border-color: var(--color-primary);
  color: var(--color-primary);
}

.preview-content {
  flex: 1;
  overflow: auto;
  padding: 16px 20px;
}

.loading {
  text-align: center;
  color: var(--color-text-secondary);
  padding: 40px;
}

.markdown-body {
  font-size: 14px;
  line-height: 1.7;
  color: var(--color-text);
  word-break: break-word;
}

.markdown-body :deep(h1) {
  font-size: 22px;
  font-weight: 700;
  margin: 0 0 16px 0;
  padding-bottom: 8px;
  border-bottom: 2px solid var(--color-border);
  color: var(--color-text);
}

.markdown-body :deep(h2) {
  font-size: 18px;
  font-weight: 600;
  margin: 20px 0 12px 0;
  color: var(--color-text);
}

.markdown-body :deep(h3) {
  font-size: 16px;
  font-weight: 600;
  margin: 16px 0 8px 0;
  color: var(--color-text);
}

.markdown-body :deep(p) {
  margin: 0 0 10px 0;
}

.markdown-body :deep(ul), .markdown-body :deep(ol) {
  margin: 0 0 10px 0;
  padding-left: 20px;
}

.markdown-body :deep(li) {
  margin: 4px 0;
}

.markdown-body :deep(code) {
  background: var(--color-surface);
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 13px;
  font-family: 'SF Mono', 'Fira Code', 'Menlo', monospace;
}

.markdown-body :deep(pre) {
  background: var(--color-surface);
  padding: 12px 16px;
  border-radius: 8px;
  overflow-x: auto;
  margin: 0 0 12px 0;
}

.markdown-body :deep(pre code) {
  background: transparent;
  padding: 0;
}

.markdown-body :deep(blockquote) {
  border-left: 3px solid var(--color-primary);
  margin: 0 0 12px 0;
  padding: 4px 12px;
  color: var(--color-text-secondary);
}

.markdown-body :deep(hr) {
  border: none;
  border-top: 1px solid var(--color-border);
  margin: 16px 0;
}

.markdown-body :deep(strong) {
  font-weight: 600;
}

.markdown-body :deep(table) {
  border-collapse: collapse;
  width: 100%;
  margin: 0 0 12px 0;
}

.markdown-body :deep(th), .markdown-body :deep(td) {
  border: 1px solid var(--color-border);
  padding: 8px 12px;
  text-align: left;
}

.markdown-body :deep(th) {
  background: var(--color-surface);
  font-weight: 600;
}

.no-content {
  text-align: center;
  color: var(--color-text-secondary);
  padding: 40px;
}
</style>
