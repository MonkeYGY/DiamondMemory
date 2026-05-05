<template>
  <div class="chat-view">
    <div class="chat-header">
      <div class="header-text">
        <h1>AI 对话</h1>
        <p>基于记忆库的智能问答，让AI拥有持久记忆</p>
      </div>
      <div class="header-actions">
        <button class="btn-header" @click="showIngestPanel = !showIngestPanel" :class="{ active: showIngestPanel }" title="采集中心">
          📥 采集
        </button>
        <button class="btn-header btn-clear" @click="clearChat" :disabled="messages.length === 0" title="清空对话">清空对话</button>
      </div>
    </div>

    <div class="chat-body">
      <div v-if="llmUnavailable" class="model-unavailable-banner" @click="handleGoToSettings">
        <span class="banner-icon">⚠️</span>
        <span class="banner-text">{{ llmUnavailableText }}</span>
        <span class="banner-action">前往设置下载 →</span>
      </div>

      <div class="chat-messages" ref="messagesContainer">
        <div v-if="messages.length === 0 && !showIngestPanel && !llmUnavailable" class="empty-state">
          <div class="empty-icon">💬</div>
          <h3>开始对话</h3>
          <p>向AI助手提问，它会基于你的记忆库进行智能回答</p>
          <div class="quick-prompts">
            <button v-for="prompt in quickPrompts" :key="prompt.text" class="quick-btn" @click="sendQuickPrompt(prompt.text)">
              <span class="quick-icon">{{ prompt.icon }}</span>
              <span>{{ prompt.text }}</span>
            </button>
          </div>
        </div>

        <div v-else-if="messages.length === 0 && !showIngestPanel && llmUnavailable" class="empty-state">
          <div class="empty-icon">🤖</div>
          <h3>大模型暂不可用</h3>
          <p>{{ llmUnavailableText }}，请先下载所需模型后再使用 AI 对话功能。</p>
        </div>

        <div v-for="(msg, index) in messages" :key="index" class="message-row" :class="msg.role">
          <div class="avatar">
            <span v-if="msg.role === 'user'">👤</span>
            <span v-else>💎</span>
          </div>
          <div class="message-content">
            <div class="message-bubble" :class="msg.role">
              <div v-if="msg.role === 'assistant'">
                <details
                  v-if="msg.thinking"
                  class="thinking-details"
                  :open="!msg.thinkingCollapsed"
                  @toggle="(e) => handleThinkingToggle(msg, e)"
                >
                  <summary class="thinking-summary">思考过程</summary>
                  <div class="thinking-body">{{ msg.thinking }}</div>
                </details>
                <div class="markdown-body" v-html="renderMarkdown(msg.content)"></div>
              </div>
              <div v-else class="user-text">{{ msg.content }}</div>
            </div>
            <div v-if="msg.role === 'assistant' && msg.error" class="error-hint">⚠️ {{ msg.error }}</div>
          </div>
        </div>

        <div v-if="isLoading && !streamingThinking && !streamingContent" class="message-row assistant">
          <div class="avatar"><span>💎</span></div>
          <div class="message-content">
            <div class="message-bubble assistant thinking">
              <div class="thinking-dots"><span></span><span></span><span></span></div>
              <span class="thinking-text">思考中...</span>
            </div>
          </div>
        </div>

        <div v-if="isLoading && (streamingThinking || streamingContent)" class="message-row assistant">
          <div class="avatar"><span>💎</span></div>
          <div class="message-content">
            <div class="message-bubble assistant">
              <details v-if="streamingThinking" class="thinking-details" open>
                <summary class="thinking-summary">思考中...</summary>
                <div class="thinking-body">{{ streamingThinking }}</div>
              </details>
              <div v-if="streamingContent" class="markdown-body" v-html="renderMarkdown(streamingContent)"></div>
            </div>
          </div>
        </div>
      </div>

      <transition name="slide-panel">
        <div v-if="showIngestPanel" class="ingest-panel">
          <div class="ingest-header">
            <h3>采集中心</h3>
            <button class="close-btn" @click="showIngestPanel = false">✕</button>
          </div>
          <div class="ingest-tabs">
            <button :class="{ active: ingestTab === 'file' }" @click="ingestTab = 'file'">📄 上传文件</button>
            <button :class="{ active: ingestTab === 'url' }" @click="ingestTab = 'url'">🌐 网页采集</button>
            <button :class="{ active: ingestTab === 'text' }" @click="ingestTab = 'text'">✍️ 手动输入</button>
          </div>
          <div v-if="ingestTab === 'file'" class="ingest-content">
            <div class="drop-zone" :class="{ 'drag-over': isDragging }" @dragover.prevent="isDragging = true" @dragleave.prevent="isDragging = false" @drop.prevent="handleDrop" @click="triggerFileInput">
              <input ref="fileInput" type="file" @change="handleFileSelect" class="file-input" accept=".pdf,.docx,.xlsx,.doc,.xls,.txt,.md,.csv" multiple />
              <div class="drop-icon">{{ isDragging ? '📥' : '📁' }}</div>
              <p>{{ isDragging ? '松开鼠标上传' : '点击或拖拽文件到此处' }}</p>
              <span class="file-hint">支持 PDF、Word、Excel、TXT、Markdown</span>
            </div>
            <div v-if="selectedFiles.length > 0" class="file-list">
              <div v-for="(file, i) in selectedFiles" :key="file.name + file.size" class="file-item">
                <span>{{ file.name }}</span>
                <span class="file-size">{{ formatFileSize(file.size) }}</span>
                <button class="file-remove" @click="selectedFiles.splice(i, 1)">✕</button>
              </div>
            </div>
            <div class="dnd-row">
              <label class="dnd-label">
                <input type="checkbox" v-model="disturbFree" />
                <span>免打扰（上传文件不触发 AI 结构化提炼）</span>
              </label>
            </div>
            <button class="btn-primary" @click="uploadFiles" :disabled="uploading || selectedFiles.length === 0">
              {{ uploading ? '上传中...' : `上传 (${selectedFiles.length})` }}
            </button>
          </div>
          <div v-if="ingestTab === 'url'" class="ingest-content">
            <input v-model="inputUrl" type="url" placeholder="输入网页URL..." class="url-input" @keyup.enter="crawlUrl" />
            <button class="btn-primary" @click="crawlUrl" :disabled="uploading || !inputUrl">{{ uploading ? '采集中...' : '采集' }}</button>
          </div>
          <div v-if="ingestTab === 'text'" class="ingest-content">
            <textarea v-model="textInput" placeholder="输入文本内容..." class="text-input" rows="6"></textarea>
            <div class="dnd-row">
              <label class="dnd-label">
                <input type="checkbox" v-model="disturbFree" />
                <span>免打扰（保留原文排版，不做整理）</span>
              </label>
            </div>
            <button class="btn-primary" @click="submitText" :disabled="uploading || !textInput.trim()">{{ uploading ? '提交中...' : '提交到记忆库' }}</button>
          </div>
          <div v-if="uploadProgress > 0 && uploadProgress < 100" class="upload-progress">
            <div class="progress-bar"><div class="progress-fill" :style="{ width: uploadProgress + '%' }"></div></div>
          </div>
        </div>
      </transition>
    </div>

    <div class="chat-input-area">
      <div class="prompt-box" :class="{ 'is-loading': isLoading }" @dragover.prevent="onDragOver" @dragleave.prevent="onDragLeave" @drop.prevent="onDrop">
        <div v-if="attachedImages.length > 0" class="attachment-preview">
          <div v-for="(img, i) in attachedImages" :key="i" class="attachment-thumb" @click="previewImage = img.url">
            <img :src="img.url" :alt="img.name" />
            <button class="thumb-remove" @click.stop="removeAttachment(i)">✕</button>
          </div>
        </div>

        <div class="textarea-wrapper">
          <textarea
            ref="inputRef"
            v-model="inputText"
            @keydown.enter.exact="handleSend"
            @input="autoResize"
            :placeholder="currentPlaceholder"
            rows="1"
            class="prompt-textarea"
            :disabled="isLoading"
          ></textarea>
        </div>

        <div class="prompt-toolbar">
          <div class="toolbar-left">
            <button class="toolbar-btn" @click="triggerImageUpload" :disabled="isLoading" title="上传图片">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m21.44 11.05-9.19 9.19a6 6 0 0 1-8.49-8.49l8.57-8.57A4 4 0 1 1 18 8.84l-8.59 8.57a2 2 0 0 1-2.83-2.83l8.49-8.48"/></svg>
              <input ref="imageInputRef" type="file" class="hidden-input" accept="image/*" @change="handleImageSelect" />
            </button>

            <div class="toolbar-divider"></div>

            <button
              class="mode-btn"
              :class="{ active: useMemory }"
              @click="toggleMemory"
              :disabled="isLoading"
              title="记忆增强：对话时检索记忆库"
            >
              <svg class="mode-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2a8 8 0 0 0-8 8c0 3.4 2.1 6.3 5 7.5V20h6v-2.5c2.9-1.2 5-4.1 5-7.5a8 8 0 0 0-8-8Z"/><path d="M9 22h6"/><path d="M10 2v2"/><path d="M14 2v2"/></svg>
              <span class="mode-label" v-if="useMemory">记忆增强</span>
            </button>
          </div>

          <div class="toolbar-right">
            <button
              class="send-btn"
              :class="sendBtnClass"
              @click="handleSendAction"
              :disabled="!isLoading && !hasContent"
              :title="sendBtnTitle"
            >
              <svg v-if="isLoading" class="stop-icon" width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="6" width="12" height="12" rx="2"/></svg>
              <svg v-else-if="hasContent" width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M12 3a1 1 0 0 0-1 1v7H4a1 1 0 1 0 0 2h7v7a1 1 0 1 0 2 0v-7h7a1 1 0 1 0 0-2h-7V4a1 1 0 0 0-1-1z"/></svg>
              <svg v-else width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/><line x1="12" x2="12" y1="19" y2="22"/></svg>
            </button>
          </div>
        </div>
      </div>
    </div>

    <transition name="modal-fade">
      <div v-if="previewImage" class="image-modal-overlay" @click="previewImage = null">
        <div class="image-modal-content" @click.stop>
          <button class="modal-close" @click="previewImage = null">✕</button>
          <img :src="previewImage" alt="预览" />
        </div>
      </div>
    </transition>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, nextTick, onMounted, onUnmounted, onActivated, watch, inject, type Ref } from 'vue'
import { chatStreamRequest, chatSummaryRequest, apiRequest, uploadFileToBackend, crawlUrlToBackend } from '../api/backend'
import { useToast } from '../composables/useToast'
import DOMPurify from 'dompurify'
import { buildPromptWindow, estimateTokens } from '../utils/prompt-window'

defineOptions({ name: 'ChatView' })

const toast = useToast()
const disturbFree = ref(localStorage.getItem('dm-disturb-free') === 'true')
const startupStatus = inject<Ref<{
  ollama_ready: boolean
  llm_installed: boolean
  llm_loaded: boolean
  embedding_installed: boolean
  embedding_loaded: boolean
  warmup_phase: string
  llm_model_name: string
}>>('startupStatus', ref({
  ollama_ready: false,
  llm_installed: false,
  llm_loaded: false,
  embedding_installed: false,
  embedding_loaded: false,
  warmup_phase: 'idle',
  llm_model_name: '',
}))
const openSettings = inject<() => void>('openSettings', () => {})

watch(disturbFree, (v) => {
  localStorage.setItem('dm-disturb-free', String(v))
})

interface ChatMessage {
  role: 'user' | 'assistant' | 'system'
  content: string
  error?: string
  thinking?: string
  thinkingCollapsed?: boolean
}

interface AttachedImage {
  name: string
  url: string
  file: File
}

const messages = ref<ChatMessage[]>([])
const inputText = ref('')
const isLoading = ref(false)
const useMemory = ref(true)

const streamingContent = ref('')
const streamingThinking = ref('')
const messagesContainer = ref<HTMLElement | null>(null)
const inputRef = ref<HTMLTextAreaElement | null>(null)
const imageInputRef = ref<HTMLInputElement | null>(null)
let abortController: AbortController | null = null
const autoScrollEnabled = ref(true)
const autoScrollThresholdPx = 120
const promptWindowTokenBudget = 2200
const promptWindowMaxMessages = 24
const autoSummaryTriggerTokens = 300
let didWarnPromptTrim = false

function generateSessionId(): string {
  const c = (globalThis as any).crypto
  if (c?.randomUUID) return c.randomUUID()
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`
}

const sessionId = ref(generateSessionId())
const sessionSummary = ref('')

const attachedImages = ref<AttachedImage[]>([])
const previewImage = ref<string | null>(null)
const isDragOver = ref(false)

const showIngestPanel = ref(false)
const ingestTab = ref<'file' | 'url' | 'text'>('file')
const uploading = ref(false)
const uploadProgress = ref(0)
const selectedFiles = ref<File[]>([])
const inputUrl = ref('')
const textInput = ref('')
const fileInput = ref<HTMLInputElement>()
const isDragging = ref(false)

const quickPrompts = [
  { icon: '🧠', text: '帮我回顾最近的记忆' },
  { icon: '📊', text: '总结我的知识库内容' },
  { icon: '💡', text: '基于我的记忆给出建议' },
  { icon: '🔍', text: '查找关于某个主题的记忆' }
]

const llmUnavailable = computed(() => {
  if (!startupStatus.value.ollama_ready) return true
  if (!startupStatus.value.llm_installed && !startupStatus.value.llm_loaded) return true
  if (startupStatus.value.warmup_phase === 'no_models') return true
  if (startupStatus.value.warmup_phase === 'degraded') return true
  return false
})

const llmUnavailableText = computed(() => {
  if (!startupStatus.value.ollama_ready) return 'Ollama 服务未启动'
  if (startupStatus.value.warmup_phase === 'no_models') return '未检测到大模型（LLM 模型未安装）'
  if (!startupStatus.value.llm_installed) return `LLM 模型 ${startupStatus.value.llm_model_name || ''} 未安装`
  if (!startupStatus.value.llm_loaded) return 'LLM 模型尚未加载完成'
  if (startupStatus.value.warmup_phase === 'degraded') return '大模型服务异常'
  return '大模型暂不可用'
})

function handleGoToSettings() {
  openSettings()
}

function checkLlmBeforeSend(): boolean {
  if (llmUnavailable.value) {
    toast.warning(llmUnavailableText.value + '，请前往设置页面下载所需模型')
    return false
  }
  return true
}

const hasContent = computed(() => inputText.value.trim() !== '' || attachedImages.value.length > 0)

const currentPlaceholder = computed(() => {
  if (useMemory.value) return '记忆增强模式，输入消息...'
  return '输入消息，Enter 发送...'
})

const sendBtnClass = computed(() => {
  if (isLoading.value) return 'btn-stop'
  if (hasContent.value) return 'btn-active'
  return 'btn-idle'
})

const sendBtnTitle = computed(() => {
  if (isLoading.value) return '停止生成'
  if (hasContent.value) return '发送消息'
  return '语音输入'
})

onMounted(() => {
  const saved = localStorage.getItem('dm-chat-messages')
  if (saved) {
    try {
      const parsed = JSON.parse(saved)
      if (Array.isArray(parsed) && parsed.length > 0) {
        messages.value = parsed.filter((m: ChatMessage) => m.role !== 'system' && m.content)
      }
    } catch {}
  }
  const savedMemory = localStorage.getItem('dm-chat-use-memory')
  if (savedMemory !== null) useMemory.value = savedMemory === 'true'

  document.addEventListener('paste', handlePaste)
  nextTick(() => {
    if (messagesContainer.value) {
      messagesContainer.value.addEventListener('scroll', updateAutoScroll, { passive: true } as any)
      updateAutoScroll()
    }
  })
})

onActivated(async () => {
  if (isLoading.value && messagesContainer.value) {
    await scrollToBottom()
  }
})

onUnmounted(() => {
  document.removeEventListener('paste', handlePaste)
  if (messagesContainer.value) {
    messagesContainer.value.removeEventListener('scroll', updateAutoScroll as any)
  }
})

function saveMessages() {
  const toSave = messages.value.filter(m => m.role !== 'system' && m.content)
  localStorage.setItem('dm-chat-messages', JSON.stringify(toSave))
}

function saveMemoryToggle() {
  localStorage.setItem('dm-chat-use-memory', String(useMemory.value))
}

function toggleMemory() {
  useMemory.value = !useMemory.value
  saveMemoryToggle()
}

function autoResize() {
  if (inputRef.value) {
    inputRef.value.style.height = 'auto'
    inputRef.value.style.height = Math.min(inputRef.value.scrollHeight, 200) + 'px'
  }
}

function updateAutoScroll() {
  const el = messagesContainer.value
  if (!el) return
  const distance = el.scrollHeight - el.scrollTop - el.clientHeight
  autoScrollEnabled.value = distance <= autoScrollThresholdPx
}

async function scrollToBottom(force: boolean = false) {
  await nextTick()
  if (!force && !autoScrollEnabled.value) return
  if (messagesContainer.value) messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
}

function renderMarkdown(text: string): string {
  if (!text) return ''
  let html = text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  html = html.replace(/```(\w*)\n([\s\S]*?)```/g, (_m, lang, code) => `<pre class="code-block"><code class="lang-${lang}">${code.trim()}</code></pre>`)
  html = html.replace(/`([^`]+)`/g, '<code class="inline-code">$1</code>')
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
  html = html.replace(/\*(.+?)\*/g, '<em>$1</em>')
  html = html.replace(/^### (.+)$/gm, '<h4>$1</h4>')
  html = html.replace(/^## (.+)$/gm, '<h3>$1</h3>')
  html = html.replace(/^# (.+)$/gm, '<h2>$1</h2>')
  html = html.replace(/^- (.+)$/gm, '<li>$1</li>')
  html = html.replace(/^(\d+)\. (.+)$/gm, '<li>$2</li>')
  html = html.replace(/\n{2,}/g, '\n')
  html = html.replace(/\n/g, '<br>')
  html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>')
  return DOMPurify.sanitize(html)
}

function triggerImageUpload() {
  imageInputRef.value?.click()
}

function handleImageSelect(event: Event) {
  const target = event.target as HTMLInputElement
  if (target.files && target.files.length > 0) {
    processImageFile(target.files[0])
  }
  target.value = ''
}

function processImageFile(file: File) {
  if (!file.type.startsWith('image/')) {
    toast.warning('仅支持图片文件')
    return
  }
  if (file.size > 10 * 1024 * 1024) {
    toast.warning('图片大小不能超过10MB')
    return
  }
  const reader = new FileReader()
  reader.onload = (e) => {
    attachedImages.value.push({
      name: file.name,
      url: e.target?.result as string,
      file
    })
  }
  reader.readAsDataURL(file)
}

function removeAttachment(index: number) {
  attachedImages.value.splice(index, 1)
}

function onDragOver() {
  isDragOver.value = true
}

function onDragLeave() {
  isDragOver.value = false
}

function onDrop(event: DragEvent) {
  isDragOver.value = false
  if (!event.dataTransfer) return
  const files = Array.from(event.dataTransfer.files)
  const imageFile = files.find(f => f.type.startsWith('image/'))
  if (imageFile) processImageFile(imageFile)
}

function handlePaste(e: ClipboardEvent) {
  const items = e.clipboardData?.items
  if (!items) return
  for (let i = 0; i < items.length; i++) {
    if (items[i].type.indexOf('image') !== -1) {
      const file = items[i].getAsFile()
      if (file) {
        e.preventDefault()
        processImageFile(file)
        break
      }
    }
  }
}

function handleSendAction() {
  if (isLoading.value) {
    stopGeneration()
  } else if (hasContent.value) {
    if (!checkLlmBeforeSend()) return
    handleSend()
  }
}

async function handleSend(e?: Event) {
  if (e && e instanceof KeyboardEvent && e.shiftKey) return
  if (e && e instanceof KeyboardEvent) e.preventDefault()
  const text = inputText.value.trim()
  if (!hasContent.value || isLoading.value) return
  if (!checkLlmBeforeSend()) return

  inputText.value = ''
  attachedImages.value = []
  if (inputRef.value) inputRef.value.style.height = 'auto'
  messages.value.push({ role: 'user', content: text })
  await scrollToBottom(true)
  await sendMessage()
}

async function sendQuickPrompt(text: string) {
  if (!checkLlmBeforeSend()) return
  messages.value.push({ role: 'user', content: text })
  await scrollToBottom(true)
  await sendMessage()
}

let generationStopped = false

async function sendMessage() {
  isLoading.value = true
  streamingContent.value = ''
  streamingThinking.value = ''
  generationStopped = false
  await scrollToBottom(true)
  const rawChatMessages = messages.value.filter(m => m.role !== 'system' && m.content).map(m => ({ role: m.role, content: m.content }))
  const { kept, dropped, trimmed } = buildPromptWindow(rawChatMessages, { maxMessages: promptWindowMaxMessages, tokenBudget: promptWindowTokenBudget })
  const buildSummarySystem = (text: string) => ({
    role: 'system' as const,
    content: `【对话摘要（自动生成）】\n${text}\n\n要求：后续回答优先参考该摘要；不要复述摘要；只输出最终答案。`
  })
  let chatMessages: Array<{ role: string; content: string }> = kept

  if (sessionSummary.value) {
    chatMessages = [buildSummarySystem(sessionSummary.value), ...chatMessages]
  }

  if (trimmed && dropped.length) {
    const droppedTokens = dropped.reduce((acc, m) => acc + estimateTokens(m.content) + 16, 0)
    if (droppedTokens >= autoSummaryTriggerTokens) {
      try {
        const resp = await chatSummaryRequest({ dropped_messages: dropped })
        const summaryText = (resp?.summary_text || '').trim()
        if (summaryText) {
          sessionSummary.value = summaryText
          chatMessages = [buildSummarySystem(summaryText), ...kept]
          await apiRequest('/api/memory/create', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              content: summaryText,
              category: '对话摘要',
              layer: 1,
              disturb_free: true,
              metadata: { source: 'chat_auto_summary', session_id: sessionId.value, dropped_count: dropped.length }
            })
          })
        }
      } catch {}
    }
  }
  if (trimmed && !didWarnPromptTrim) {
    didWarnPromptTrim = true
    toast.info('对话过长，已自动缩短上下文以保证可回复（历史仍保留，可滚动查看）')
  }
  try {
    abortController = await chatStreamRequest(chatMessages, {
      onChunk: (content: string) => {
        if (!generationStopped) {
          streamingContent.value += content
          scrollToBottom()
        }
      },
      onThinkingChunk: (thinking: string) => {
        if (!generationStopped) {
          streamingThinking.value += thinking
          scrollToBottom()
        }
      },
      onDone: () => {
        if (generationStopped) {
          isLoading.value = false; streamingContent.value = ''; streamingThinking.value = ''; abortController = null; saveMessages()
          scrollToBottom()
          return
        }

        if (!streamingContent.value && streamingThinking.value) {
          const lastUser = [...chatMessages].reverse().find(m => m.role === 'user')?.content || ''
          const prompt = `问题：${lastUser}\n\n你刚才没有输出最终答案。请直接输出最终答案（不要输出思考过程）。`
          const finalReqMessages = [{ role: 'user', content: prompt }]
          chatStreamRequest(finalReqMessages, {
            onChunk: (content: string) => {
              if (!generationStopped) {
                streamingContent.value += content
                scrollToBottom()
              }
            },
            onDone: () => {
              const answer = streamingContent.value
              if (answer && !generationStopped) {
                messages.value.push({ role: 'assistant', content: answer, thinking: streamingThinking.value || '', thinkingCollapsed: true })
              }
              isLoading.value = false; streamingContent.value = ''; streamingThinking.value = ''; abortController = null; saveMessages()
              scrollToBottom()
            },
            onError: (error: string) => {
              if (!generationStopped) {
                messages.value.push({ role: 'assistant', content: '抱歉，生成回答时出现了问题。', error })
                toast.error('对话异常: ' + error)
              }
              isLoading.value = false; streamingContent.value = ''; streamingThinking.value = ''; abortController = null; saveMessages()
              scrollToBottom()
            }
          }, false).then((c) => { abortController = c }).catch(() => {})
          return
        }

        const answer = streamingContent.value || streamingThinking.value
        if (answer && !generationStopped) {
          messages.value.push({ role: 'assistant', content: answer, thinking: streamingThinking.value || '', thinkingCollapsed: true })
        }
        isLoading.value = false; streamingContent.value = ''; streamingThinking.value = ''; abortController = null; saveMessages()
        scrollToBottom()
      },
      onError: (error: string) => {
        if (!generationStopped) {
          messages.value.push({ role: 'assistant', content: '抱歉，生成回答时出现了问题。', error })
          toast.error('对话异常: ' + error)
        }
        isLoading.value = false; streamingContent.value = ''; streamingThinking.value = ''; abortController = null; saveMessages()
        scrollToBottom()
      }
    }, useMemory.value)
  } catch (err: any) {
    if (!generationStopped) {
      messages.value.push({ role: 'assistant', content: '抱歉，发送请求失败。', error: err.message })
      toast.error('请求失败: ' + err.message)
    }
    isLoading.value = false; streamingContent.value = ''; streamingThinking.value = ''; saveMessages()
  }
}

function stopGeneration() {
  generationStopped = true
  if (abortController) { abortController.abort(); abortController = null }
  const answer = streamingContent.value || streamingThinking.value
  if (answer) {
    messages.value.push({ role: 'assistant', content: answer, thinking: streamingThinking.value || '', thinkingCollapsed: true })
  }
  isLoading.value = false
  streamingContent.value = ''; streamingThinking.value = ''; saveMessages()
}

function handleThinkingToggle(msg: ChatMessage, e: Event) {
  const el = e.target as HTMLDetailsElement
  msg.thinkingCollapsed = !el.open
  saveMessages()
}

function clearChat() {
  messages.value = []
  streamingContent.value = ''
  streamingThinking.value = ''
  localStorage.removeItem('dm-chat-messages')
  didWarnPromptTrim = false
  sessionSummary.value = ''
  sessionId.value = generateSessionId()
  toast.success('对话已清空')
}

function triggerFileInput() { fileInput.value?.click() }

function handleFileSelect(event: Event) {
  const target = event.target as HTMLInputElement
  if (target.files) selectedFiles.value = [...selectedFiles.value, ...Array.from(target.files)]
  target.value = ''
}

function handleDrop(event: DragEvent) {
  isDragging.value = false
  if (event.dataTransfer) selectedFiles.value = [...selectedFiles.value, ...Array.from(event.dataTransfer.files)]
}

async function uploadFiles() {
  uploading.value = true; uploadProgress.value = 10
  try {
    for (const file of selectedFiles.value) {
      await uploadFileToBackend(file)
    }
    toast.success('文件上传处理完成！'); selectedFiles.value = []; uploadProgress.value = 100
    setTimeout(() => { uploading.value = false; uploadProgress.value = 0 }, 1000)
  } catch (error: any) {
    toast.error('上传失败: ' + error.message); uploading.value = false; uploadProgress.value = 0
  }
}

async function crawlUrl() {
  uploading.value = true; uploadProgress.value = 10
  try {
    await crawlUrlToBackend(inputUrl.value)
    toast.success('网页采集完成！'); inputUrl.value = ''; uploadProgress.value = 100
    setTimeout(() => { uploading.value = false; uploadProgress.value = 0 }, 1000)
  } catch (error: any) {
    toast.error('采集失败: ' + error.message); uploading.value = false; uploadProgress.value = 0
  }
}

async function submitText() {
  uploading.value = true; uploadProgress.value = 10
  try {
    await apiRequest('/api/memory/create', { method: 'POST', body: JSON.stringify({ content: textInput.value, category: '手动记录', disturb_free: disturbFree.value }) })
    toast.success('文本已提交到记忆库！'); textInput.value = ''; uploadProgress.value = 100
    setTimeout(() => { uploading.value = false; uploadProgress.value = 0 }, 1000)
  } catch (error: any) {
    toast.error('提交失败: ' + error.message); uploading.value = false; uploadProgress.value = 0
  }
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
}
</script>

<style scoped>
.chat-view { display: flex; flex-direction: column; height: 100%; overflow: hidden; }
.chat-header { display: flex; justify-content: space-between; align-items: center; padding: 12px 24px; border-bottom: 1px solid var(--color-border); background: var(--color-surface); flex-shrink: 0; }
.header-text h1 { font-size: 20px; font-weight: 700; color: var(--color-text); margin: 0 0 2px 0; }
.header-text p { font-size: 13px; color: var(--color-text-secondary); margin: 0; }
.header-actions { display: flex; align-items: center; gap: 8px; }

.btn-header { padding: 5px 12px; border: 1px solid var(--color-border); border-radius: 6px; background: var(--color-surface); color: var(--color-text-secondary); font-size: 12px; cursor: pointer; transition: all 0.15s; }
.btn-header:hover, .btn-header.active { border-color: var(--color-primary); color: var(--color-primary); background: var(--color-primary-bg); }
.btn-clear:hover:not(:disabled) { border-color: var(--color-error) !important; color: var(--color-error) !important; }
.btn-clear:disabled { opacity: 0.4; cursor: not-allowed; }

.chat-body { flex: 1; display: flex; flex-direction: column; overflow: hidden; }
.model-unavailable-banner {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 20px;
  background: #fffbeb;
  border-bottom: 1px solid #fde68a;
  cursor: pointer;
  transition: background 0.15s;
  flex-shrink: 0;
}
.model-unavailable-banner:hover { background: #fef3c7; }
.banner-icon { font-size: 16px; flex-shrink: 0; }
.banner-text { font-size: 13px; color: #92400e; flex: 1; }
.banner-action { font-size: 12px; color: var(--color-primary); font-weight: 500; white-space: nowrap; }
.chat-messages { flex: 1; overflow-y: auto; padding: 12px 24px; display: flex; flex-direction: column; gap: 8px; }
.empty-state { display: flex; flex-direction: column; align-items: center; justify-content: center; flex: 1; text-align: center; color: var(--color-text-secondary); padding: 40px 20px; }
.empty-icon { font-size: 56px; margin-bottom: 16px; }
.empty-state h3 { font-size: 18px; color: var(--color-text); margin: 0 0 8px 0; }
.empty-state p { font-size: 14px; margin: 0 0 24px 0; }
.quick-prompts { display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; max-width: 500px; width: 100%; }
.quick-btn { display: flex; align-items: center; gap: 8px; padding: 12px 16px; border: 1px solid var(--color-border); border-radius: 10px; background: var(--color-surface); color: var(--color-text); font-size: 13px; cursor: pointer; transition: all 0.15s; text-align: left; }
.quick-btn:hover { border-color: var(--color-primary); background: var(--color-primary-bg); }
.quick-icon { font-size: 16px; flex-shrink: 0; }

.message-row { display: flex; gap: 8px; max-width: 85%; }
.message-row.user { align-self: flex-end; flex-direction: row-reverse; }
.message-row.assistant { align-self: flex-start; }
.avatar { width: 28px; height: 28px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 14px; flex-shrink: 0; background: var(--color-bg); border: 1px solid var(--color-border); }
.message-content { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.message-bubble { padding: 8px 12px; border-radius: 12px; font-size: 14px; line-height: 1.45; word-break: break-word; position: relative; }
.message-bubble.user { background: var(--color-primary); color: var(--color-text-on-primary); border-bottom-right-radius: 4px; }
.message-bubble.assistant { background: var(--color-surface); color: var(--color-text); border: 1px solid var(--color-border); border-bottom-left-radius: 4px; }
.user-text { white-space: pre-wrap; }
.message-bubble.thinking { display: flex; align-items: center; gap: 8px; padding: 10px 16px; color: var(--color-text-secondary); font-size: 13px; }
.thinking-details { margin: 0 0 8px 0; padding: 8px 10px; border: 1px dashed var(--color-border); border-radius: 10px; background: var(--color-bg); }
.thinking-summary { cursor: pointer; font-size: 12px; color: var(--color-text-secondary); user-select: none; }
.thinking-body { margin-top: 6px; white-space: pre-wrap; font-size: 12px; line-height: 1.5; color: var(--color-text-secondary); }
.thinking-dots { display: flex; gap: 4px; }
.thinking-dots span { width: 6px; height: 6px; border-radius: 50%; background: var(--color-text-secondary); animation: dot-pulse 1.4s infinite ease-in-out; }
.thinking-dots span:nth-child(2) { animation-delay: 0.2s; }
.thinking-dots span:nth-child(3) { animation-delay: 0.4s; }
@keyframes dot-pulse { 0%, 80%, 100% { opacity: 0.3; transform: scale(0.8); } 40% { opacity: 1; transform: scale(1); } }
.error-hint { font-size: 12px; color: var(--color-error); padding: 2px 4px; }

.markdown-body :deep(h2) { font-size: 16px; font-weight: 700; margin: 8px 0 4px; }
.markdown-body :deep(h3) { font-size: 15px; font-weight: 600; margin: 6px 0 3px; }
.markdown-body :deep(h4) { font-size: 14px; font-weight: 600; margin: 5px 0 2px; }
.markdown-body :deep(strong) { font-weight: 600; }
.markdown-body :deep(li) { margin-left: 16px; list-style: disc; margin-bottom: 0; }
.markdown-body :deep(.code-block) { background: var(--color-code-bg); color: var(--color-code-text); padding: 12px 16px; border-radius: 8px; overflow-x: auto; margin: 8px 0; font-size: 13px; line-height: 1.5; }
.markdown-body :deep(.inline-code) { background: var(--color-inline-code-bg); padding: 1px 6px; border-radius: 4px; font-size: 13px; font-family: 'SF Mono', 'Fira Code', monospace; }
.markdown-body :deep(a) { color: var(--color-primary); text-decoration: none; }
.markdown-body :deep(a:hover) { text-decoration: underline; }

.ingest-panel { width: 340px; min-width: 340px; border-left: 1px solid var(--color-border); background: var(--color-surface); display: flex; flex-direction: column; overflow-y: auto; }
.ingest-header { display: flex; justify-content: space-between; align-items: center; padding: 12px 16px; border-bottom: 1px solid var(--color-border); }
.ingest-header h3 { margin: 0; font-size: 15px; }
.close-btn { background: none; border: none; cursor: pointer; font-size: 16px; color: var(--color-text-secondary); padding: 4px; }
.close-btn:hover { color: var(--color-text); }
.ingest-tabs { display: flex; border-bottom: 1px solid var(--color-border); }
.ingest-tabs button { flex: 1; padding: 10px 8px; border: none; background: none; cursor: pointer; font-size: 12px; color: var(--color-text-secondary); border-bottom: 2px solid transparent; transition: all 0.15s; }
.ingest-tabs button.active { color: var(--color-primary); border-bottom-color: var(--color-primary); }
.ingest-content { padding: 16px; display: flex; flex-direction: column; gap: 12px; }

.drop-zone { border: 2px dashed var(--color-border); border-radius: 8px; padding: 24px; text-align: center; cursor: pointer; transition: all 0.2s; }
.drop-zone:hover { border-color: var(--color-primary); }
.drop-zone.drag-over { border-color: var(--color-primary); background: var(--color-primary-bg); border-style: solid; }
.drop-icon { font-size: 28px; margin-bottom: 6px; }
.drop-zone p { font-size: 13px; color: var(--color-text); margin: 4px 0; }
.file-hint { font-size: 11px; color: var(--color-text-secondary); }
.file-input { display: none; }
.file-list { max-height: 120px; overflow-y: auto; }
.file-item { display: flex; align-items: center; gap: 6px; padding: 6px 0; font-size: 12px; border-bottom: 1px solid var(--color-bg); }
.file-size { color: var(--color-text-secondary); margin-left: auto; white-space: nowrap; }
.file-remove { background: none; border: none; cursor: pointer; color: var(--color-text-secondary); padding: 0 4px; }
.file-remove:hover { color: var(--color-error); }

.url-input, .text-input { width: 100%; padding: 10px; border: 1px solid var(--color-border); border-radius: 6px; font-size: 13px; outline: none; font-family: inherit; }
.url-input:focus, .text-input:focus { border-color: var(--color-primary); }
.text-input { resize: vertical; }

.dnd-row { padding: 10px; background: var(--color-bg); border: 1px solid var(--color-border); border-radius: 8px; }
.dnd-label { display: flex; align-items: center; gap: 10px; font-size: 12px; color: var(--color-text-secondary); cursor: pointer; user-select: none; }
.dnd-label input { width: 14px; height: 14px; }

.upload-progress { margin-top: 8px; }
.progress-bar { height: 4px; background: var(--color-border); border-radius: 2px; overflow: hidden; }
.progress-fill { height: 100%; background: var(--color-primary); border-radius: 2px; transition: width 0.3s; }

.slide-panel-enter-active, .slide-panel-leave-active { transition: all 0.25s ease; }
.slide-panel-enter-from, .slide-panel-leave-to { transform: translateX(100%); opacity: 0; }

.chat-input-area { padding: 12px 24px 16px; background: var(--color-surface); flex-shrink: 0; }

.prompt-box { border-radius: 20px; border: 1px solid var(--color-border); background: var(--color-bg); padding: 8px; box-shadow: var(--shadow); transition: all 0.3s ease; }
.prompt-box:focus-within { border-color: var(--color-primary); box-shadow: 0 4px 20px var(--color-primary-bg); }
.prompt-box.is-loading { border-color: var(--color-error); }

.attachment-preview { display: flex; flex-wrap: wrap; gap: 8px; padding: 4px 8px 0; }
.attachment-thumb { position: relative; width: 56px; height: 56px; border-radius: 10px; overflow: hidden; cursor: pointer; transition: transform 0.2s; border: 1px solid var(--color-border); }
.attachment-thumb:hover { transform: scale(1.05); }
.attachment-thumb img { width: 100%; height: 100%; object-fit: cover; }
.thumb-remove { position: absolute; top: 2px; right: 2px; width: 16px; height: 16px; border-radius: 50%; background: var(--color-overlay); color: var(--color-text-on-primary); border: none; cursor: pointer; font-size: 9px; display: flex; align-items: center; justify-content: center; padding: 0; line-height: 1; transition: background 0.15s; }
.thumb-remove:hover { background: var(--color-overlay-hover); }

.textarea-wrapper { padding: 4px 8px; }
.prompt-textarea { width: 100%; border: none; outline: none; font-size: 14px; line-height: 1.6; background: transparent; color: var(--color-text); resize: none; max-height: 200px; font-family: inherit; min-height: 24px; }
.prompt-textarea::placeholder { color: var(--color-text-secondary); opacity: 0.5; }
.prompt-textarea:disabled { opacity: 0.6; }
.prompt-textarea::-webkit-scrollbar { width: 4px; }
.prompt-textarea::-webkit-scrollbar-track { background: transparent; }
.prompt-textarea::-webkit-scrollbar-thumb { background-color: var(--color-border); border-radius: 2px; }

.prompt-toolbar { display: flex; align-items: center; justify-content: space-between; padding: 4px 4px 0; gap: 8px; }
.toolbar-left { display: flex; align-items: center; gap: 2px; }

.toolbar-btn { display: flex; align-items: center; justify-content: center; width: 32px; height: 32px; border-radius: 50%; border: none; background: transparent; color: var(--color-text-secondary); cursor: pointer; transition: all 0.2s; }
.toolbar-btn:hover:not(:disabled) { background: var(--color-primary-bg); color: var(--color-text); }
.toolbar-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.hidden-input { display: none; }

.toolbar-divider { width: 1.5px; height: 16px; margin: 0 4px; background: linear-gradient(to bottom, transparent, var(--color-primary), transparent); border-radius: 1px; opacity: 0.4; }

.mode-btn { display: flex; align-items: center; gap: 4px; height: 32px; padding: 0 10px; border-radius: 16px; border: 1px solid transparent; background: transparent; color: var(--color-text-secondary); cursor: pointer; font-size: 12px; font-weight: 500; transition: all 0.25s ease; white-space: nowrap; }
.mode-btn:hover:not(:disabled) { background: var(--color-primary-bg); color: var(--color-text); }
.mode-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.mode-btn.active { background: var(--color-primary-bg); border-color: var(--color-primary); color: var(--color-primary); }
.mode-icon { transition: transform 0.3s ease; flex-shrink: 0; }
.mode-btn:hover .mode-icon { transform: rotate(15deg) scale(1.1); }
.mode-btn.active .mode-icon { transform: rotate(360deg) scale(1.1); }
@keyframes label-expand { from { max-width: 0; opacity: 0; } to { max-width: 80px; opacity: 1; } }

.send-btn { display: flex; align-items: center; justify-content: center; width: 32px; height: 32px; border-radius: 50%; border: none; cursor: pointer; transition: all 0.25s ease; flex-shrink: 0; }
.send-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.send-btn.btn-idle { background: transparent; color: var(--color-text-secondary); }
.send-btn.btn-idle:hover:not(:disabled) { background: var(--color-primary-bg); color: var(--color-text); }
.send-btn.btn-active { background: var(--color-primary); color: var(--color-text-on-primary); }
.send-btn.btn-active:hover:not(:disabled) { background: var(--color-primary-hover); transform: scale(1.05); }
.send-btn.btn-stop { background: var(--color-error); color: var(--color-text-on-primary); animation: pulse-stop 1.5s infinite; }
.send-btn.btn-stop:hover:not(:disabled) { background: var(--color-error-hover); }
@keyframes pulse-stop { 0%, 100% { opacity: 1; } 50% { opacity: 0.7; } }
.stop-icon { animation: pulse-stop 1.5s infinite; }

.image-modal-overlay { position: fixed; inset: 0; z-index: 100; background: var(--color-overlay); backdrop-filter: blur(4px); display: flex; align-items: center; justify-content: center; }
.image-modal-content { position: relative; max-width: 90vw; max-height: 80vh; border-radius: 16px; overflow: hidden; background: var(--color-surface); box-shadow: 0 20px 60px rgba(0,0,0,0.3); }
.image-modal-content img { max-width: 90vw; max-height: 80vh; object-fit: contain; display: block; }
.modal-close { position: absolute; top: 12px; right: 12px; width: 32px; height: 32px; border-radius: 50%; background: var(--color-overlay); color: var(--color-text-on-primary); border: none; cursor: pointer; font-size: 14px; display: flex; align-items: center; justify-content: center; transition: background 0.15s; z-index: 1; }
.modal-close:hover { background: var(--color-overlay-hover); }

.modal-fade-enter-active { transition: all 0.2s ease; }
.modal-fade-leave-active { transition: all 0.15s ease; }
.modal-fade-enter-from, .modal-fade-leave-to { opacity: 0; }
.modal-fade-enter-from .image-modal-content { transform: scale(0.95); }
.modal-fade-leave-to .image-modal-content { transform: scale(0.95); }

.btn-primary { padding: 8px 16px; border: none; border-radius: 6px; background: var(--color-primary); color: var(--color-text-on-primary); font-size: 13px; cursor: pointer; font-weight: 500; }
.btn-primary:hover:not(:disabled) { background: var(--color-primary-hover); }
.btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }

@media (max-width: 768px) {
  .chat-header { flex-direction: column; gap: 10px; align-items: flex-start; }
  .message-row { max-width: 95%; }
  .quick-prompts { grid-template-columns: 1fr; }
  .ingest-panel { width: 100%; min-width: unset; border-left: none; border-top: 1px solid var(--color-border); }
  .prompt-box { border-radius: 16px; }
}
</style>
