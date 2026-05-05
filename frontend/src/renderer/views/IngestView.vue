<template>
  <div class="view-container">
    <div class="view-header">
      <h2>采集中心</h2>
    </div>

    <div class="ingest-grid">
      <div class="ingest-card" @click="showFileUpload = true" :class="{ active: showFileUpload }">
        <div class="card-icon">📄</div>
        <h3>上传文件</h3>
        <p>PDF、Word、Excel等文档</p>
        <div class="supported-formats">
          <span class="format">.pdf</span>
          <span class="format">.docx</span>
          <span class="format">.xlsx</span>
        </div>
      </div>

      <div class="ingest-card" @click="showUrlInput = true" :class="{ active: showUrlInput }">
        <div class="card-icon">🌐</div>
        <h3>网页采集</h3>
        <p>输入URL采集网页内容</p>
        <div class="supported-formats">
          <span class="format">URL</span>
          <span class="format">HTML</span>
        </div>
      </div>

      <div class="ingest-card" @click="showTextInput = true" :class="{ active: showTextInput }">
        <div class="card-icon">✍️</div>
        <h3>手动输入</h3>
        <p>直接输入文本内容</p>
        <div class="supported-formats">
          <span class="format">文本</span>
          <span class="format">Markdown</span>
        </div>
      </div>
    </div>

    <transition name="progress-fade">
      <div v-if="uploading" class="upload-progress">
        <div class="progress-bar">
          <div class="progress-fill" :style="{ width: progress + '%' }"></div>
        </div>
        <p>处理中... {{ Math.round(progress) }}%</p>
      </div>
    </transition>

    <transition name="modal-fade">
      <div v-if="showFileUpload" class="modal-overlay" @click.self="showFileUpload = false">
        <div class="modal">
          <h3>上传文件</h3>
          <div
            class="drop-zone"
            :class="{ 'drag-over': isDragging, 'has-files': selectedFiles.length > 0 }"
            @dragover.prevent="onDragOver"
            @dragleave.prevent="onDragLeave"
            @drop.prevent="handleDrop"
            @click="triggerFileInput"
          >
            <input ref="fileInput" type="file" @change="handleFileSelect" class="file-input" accept=".pdf,.docx,.xlsx,.doc,.xls,.txt,.md,.csv" multiple />
            <div class="drop-icon">{{ isDragging ? '📥' : '📁' }}</div>
            <p class="drop-main-text">{{ isDragging ? '松开鼠标上传文件' : '点击或拖拽文件到此处' }}</p>
            <p v-if="isDragging && dragFileCount > 0" class="drag-count">{{ dragFileCount }} 个文件待上传</p>
            <span class="file-hint">支持 PDF、Word、Excel、TXT、Markdown 格式</span>
          </div>
          <transition-group name="file-list" tag="div" class="file-list" v-if="selectedFiles.length > 0">
            <div v-for="(file, index) in selectedFiles" :key="file.name + file.size" class="file-item">
              <span class="file-type-icon">{{ getFileIcon(file.name) }}</span>
              <span class="file-name">{{ file.name }}</span>
              <div class="file-item-right">
                <span class="file-size">{{ formatFileSize(file.size) }}</span>
                <button class="file-remove" @click.stop="selectedFiles.splice(index, 1)">✕</button>
              </div>
            </div>
          </transition-group>
          <div class="disturb-free-row">
            <label class="disturb-free-label">
              <input type="checkbox" v-model="disturbFree" />
              <span>免打扰模式（上传文件不触发 AI 结构化提炼）</span>
            </label>
          </div>
          <div class="modal-actions">
            <button @click="showFileUpload = false; selectedFiles = []" class="btn-secondary">取消</button>
            <button @click="uploadFiles" :disabled="uploading || selectedFiles.length === 0" class="btn-primary">
              上传 ({{ selectedFiles.length }})
            </button>
          </div>
        </div>
      </div>
    </transition>

    <transition name="modal-fade">
      <div v-if="showUrlInput" class="modal-overlay" @click.self="showUrlInput = false">
        <div class="modal">
          <h3>网页采集</h3>
          <input v-model="inputUrl" type="url" placeholder="输入网页URL..." class="url-input" @keyup.enter="crawlUrl" />
          <div class="modal-actions">
            <button @click="showUrlInput = false" class="btn-secondary">取消</button>
            <button @click="crawlUrl" :disabled="uploading || !inputUrl" class="btn-primary">采集</button>
          </div>
        </div>
      </div>
    </transition>

    <transition name="modal-fade">
      <div v-if="showTextInput" class="modal-overlay" @click.self="showTextInput = false">
        <div class="modal large">
          <h3>手动输入</h3>
          <textarea v-model="textInput" placeholder="输入文本内容..." class="text-input" rows="8"></textarea>
          <div class="disturb-free-row">
            <label class="disturb-free-label">
              <input type="checkbox" v-model="disturbFree" />
              <span>免打扰模式（保留原文排版，不做整理）</span>
            </label>
          </div>
          <div class="modal-actions">
            <button @click="showTextInput = false" class="btn-secondary">取消</button>
            <button @click="submitText" :disabled="uploading || !textInput.trim()" class="btn-primary">提交</button>
          </div>
        </div>
      </div>
    </transition>
  </div>
</template>

<script setup lang="ts">
import { ref, onUnmounted, watch } from 'vue'
import { apiRequest, uploadFileToBackend, crawlUrlToBackend } from '../api/backend'
import { useToast } from '../composables/useToast'
import { APP_CONFIG } from '../config/constants'

const toast = useToast()
const uploading = ref(false)
const progress = ref(0)
const showFileUpload = ref(false)
const showUrlInput = ref(false)
const showTextInput = ref(false)
const selectedFiles = ref<File[]>([])
const inputUrl = ref('')
const textInput = ref('')
const fileInput = ref<HTMLInputElement>()
const isDragging = ref(false)
const dragFileCount = ref(0)
const disturbFree = ref(localStorage.getItem('dm-disturb-free') === 'true')

let progressIntervalId: number | null = null

watch(disturbFree, (v) => {
  localStorage.setItem('dm-disturb-free', String(v))
})

onUnmounted(() => {
  if (progressIntervalId !== null) clearInterval(progressIntervalId)
})

function startFakeProgress() {
  progress.value = 0
  if (progressIntervalId) clearInterval(progressIntervalId)
  progressIntervalId = window.setInterval(() => {
    if (progress.value < APP_CONFIG.FAKE_PROGRESS_MAX) {
      progress.value += Math.random() * 5
    }
  }, APP_CONFIG.FAKE_PROGRESS_INTERVAL)
}

function stopFakeProgress(success: boolean) {
  if (progressIntervalId !== null) {
    clearInterval(progressIntervalId)
    progressIntervalId = null
  }
  progress.value = success ? 100 : 0
  setTimeout(() => {
    uploading.value = false
    progress.value = 0
  }, 1000)
}

function onDragOver(e: DragEvent) {
  isDragging.value = true
  if (e.dataTransfer) {
    dragFileCount.value = e.dataTransfer.items.length
  }
}

function onDragLeave() {
  isDragging.value = false
  dragFileCount.value = 0
}

function triggerFileInput() {
  fileInput.value?.click()
}

function handleFileSelect(event: Event) {
  const target = event.target as HTMLInputElement
  if (target.files) {
    selectedFiles.value = [...selectedFiles.value, ...Array.from(target.files)]
  }
  target.value = ''
}

function handleDrop(event: DragEvent) {
  isDragging.value = false
  dragFileCount.value = 0
  if (event.dataTransfer) {
    selectedFiles.value = [...selectedFiles.value, ...Array.from(event.dataTransfer.files)]
  }
}

function getFileIcon(filename: string): string {
  const ext = filename.split('.').pop()?.toLowerCase()
  const icons: Record<string, string> = {
    pdf: '📕', docx: '📘', doc: '📘',
    xlsx: '📗', xls: '📗', csv: '📊',
    txt: '📝', md: '📝'
  }
  return icons[ext || ''] || '📄'
}

async function uploadFiles() {
  uploading.value = true
  startFakeProgress()
  showFileUpload.value = false

  try {
    for (const file of selectedFiles.value) {
      await uploadFileToBackend(file)
    }

    toast.success('文件上传处理完成！')
    selectedFiles.value = []
    stopFakeProgress(true)
  } catch (error: any) {
    console.error('上传失败:', error)
    toast.error('上传处理失败: ' + error.message)
    stopFakeProgress(false)
  }
}

async function crawlUrl() {
  uploading.value = true
  startFakeProgress()
  showUrlInput.value = false

  try {
    await crawlUrlToBackend(inputUrl.value)

    toast.success('网页采集完成！')
    inputUrl.value = ''
    stopFakeProgress(true)
  } catch (error: any) {
    console.error('采集失败:', error)
    toast.error('采集处理失败: ' + error.message)
    stopFakeProgress(false)
  }
}

async function submitText() {
  uploading.value = true
  startFakeProgress()
  showTextInput.value = false

  try {
    await apiRequest('/api/memory/create', {
      method: 'POST',
      body: JSON.stringify({ content: textInput.value, category: '手动记录', disturb_free: disturbFree.value })
    })
    toast.success('文本记录提交成功！')
    textInput.value = ''
    stopFakeProgress(true)
  } catch (error: any) {
    console.error('提交失败:', error)
    toast.error('提交文本失败: ' + error.message)
    stopFakeProgress(false)
  }
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
}
</script>

<style scoped>
.view-container { padding: 24px; max-width: 1100px; overflow-y: auto; height: 100%; }

.view-header h2 { font-size: 24px; font-weight: 700; color: var(--color-text); margin: 0 0 24px 0; }

.ingest-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 20px; }

.ingest-card {
  background: var(--color-surface);
  border: 2px dashed var(--color-border);
  border-radius: 12px;
  padding: 32px 24px;
  text-align: center;
  cursor: pointer;
  transition: all 0.2s;
}

.ingest-card:hover, .ingest-card.active {
  border-color: var(--color-primary);
  background: rgba(99, 102, 241, 0.03);
  transform: translateY(-2px);
}

.card-icon { font-size: 48px; margin-bottom: 16px; }
.ingest-card h3 { font-size: 18px; margin: 0 0 8px; color: var(--color-text); }
.ingest-card p { color: var(--color-text-secondary); font-size: 14px; margin: 0 0 12px; }
.supported-formats { display: flex; justify-content: center; gap: 8px; flex-wrap: wrap; }
.format { background: var(--color-bg); color: var(--color-text-secondary); padding: 2px 8px; border-radius: 4px; font-size: 12px; }

.progress-fade-enter-active, .progress-fade-leave-active { transition: all 0.3s ease; }
.progress-fade-enter-from, .progress-fade-leave-to { opacity: 0; transform: translateY(-10px); }

.upload-progress { margin-top: 24px; padding: 20px; background: var(--color-surface); border-radius: 8px; text-align: center; border: 1px solid var(--color-border); }
.progress-bar { height: 8px; background: var(--color-bg); border-radius: 4px; overflow: hidden; margin-bottom: 12px; }
.progress-fill { height: 100%; background: var(--color-primary); border-radius: 4px; transition: width 0.3s; }

.modal-fade-enter-active, .modal-fade-leave-active { transition: opacity 0.2s ease; }
.modal-fade-enter-from, .modal-fade-leave-to { opacity: 0; }

.modal-overlay { position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0, 0, 0, 0.5); display: flex; align-items: center; justify-content: center; z-index: 100; }
.modal { background: var(--color-surface); border-radius: 12px; padding: 24px; width: 450px; max-width: 90vw; }
.modal.large { width: 600px; }
.modal h3 { margin: 0 0 16px; font-size: 18px; }

.drop-zone {
  border: 2px dashed var(--color-border);
  border-radius: 8px;
  padding: 32px;
  text-align: center;
  cursor: pointer;
  transition: all 0.25s ease;
  position: relative;
}
.drop-zone:hover { border-color: var(--color-primary); background: rgba(99, 102, 241, 0.02); }
.drop-zone.drag-over {
  border-color: var(--color-primary);
  background: rgba(99, 102, 241, 0.06);
  border-style: solid;
  transform: scale(1.01);
  box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.15);
}
.drop-zone.has-files { border-style: solid; border-color: var(--color-success); background: rgba(16, 185, 129, 0.03); }

.drop-icon { font-size: 36px; margin-bottom: 8px; transition: transform 0.2s; }
.drop-zone.drag-over .drop-icon { transform: scale(1.2); }
.drop-main-text { color: var(--color-text); font-size: 14px; margin: 0 0 4px; }
.drag-count { color: var(--color-primary); font-size: 13px; font-weight: 500; margin: 4px 0; }
.file-input { display: none; }
.file-hint { font-size: 12px; color: var(--color-text-secondary); }

.file-list { margin-top: 12px; max-height: 180px; overflow-y: auto; }
.file-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border-bottom: 1px solid var(--color-bg);
  transition: background 0.15s;
}
.file-item:hover { background: var(--color-bg); }
.file-type-icon { font-size: 16px; flex-shrink: 0; }
.file-item-right { display: flex; align-items: center; gap: 8px; margin-left: auto; flex-shrink: 0; }
.file-name { font-size: 13px; color: var(--color-text); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.file-size { font-size: 12px; color: var(--color-text-secondary); white-space: nowrap; }
.file-remove { background: none; border: none; cursor: pointer; font-size: 14px; color: var(--color-text-secondary); padding: 0 4px; }
.file-remove:hover { color: var(--color-error, #ef4444); }

.file-list-enter-active, .file-list-leave-active { transition: all 0.2s ease; }
.file-list-enter-from { opacity: 0; transform: translateX(-10px); }
.file-list-leave-to { opacity: 0; transform: translateX(10px); }

.url-input, .text-input { width: 100%; padding: 12px; border: 1px solid var(--color-border); border-radius: 8px; font-size: 14px; outline: none; font-family: inherit; }
.url-input:focus, .text-input:focus { border-color: var(--color-primary); }
.text-input { resize: vertical; }

.disturb-free-row { margin-top: 12px; padding: 10px 12px; background: var(--color-bg); border: 1px solid var(--color-border); border-radius: 8px; }
.disturb-free-label { display: flex; align-items: center; gap: 10px; font-size: 13px; color: var(--color-text); cursor: pointer; user-select: none; }
.disturb-free-label input { width: 16px; height: 16px; }
.disturb-free-label span { color: var(--color-text-secondary); }

.modal-actions { display: flex; justify-content: flex-end; gap: 10px; margin-top: 16px; }
.btn-primary { padding: 8px 16px; border: none; border-radius: 8px; background: var(--color-primary); color: white; font-size: 13px; cursor: pointer; font-weight: 500; }
.btn-primary:hover:not(:disabled) { background: var(--color-primary-hover, #2563eb); }
.btn-primary:disabled { opacity: 0.6; cursor: not-allowed; }
.btn-secondary { padding: 8px 16px; border: 1px solid var(--color-border); border-radius: 8px; background: var(--color-surface); color: var(--color-text); font-size: 13px; cursor: pointer; font-weight: 500; }
.btn-secondary:hover { background: var(--color-bg); }

@media (max-width: 768px) { .ingest-grid { grid-template-columns: 1fr; } }
</style>
