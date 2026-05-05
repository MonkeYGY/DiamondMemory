# Remove Settings External API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 仅在 `SettingsView` 中移除外部 API 连接设置，保留本地模型相关能力不变。

**Architecture:** 只修改 `frontend/src/renderer/views/SettingsView.vue`。删除模板中的“外部API”入口与表单，并清理脚本里只服务于该表单的状态和方法，保持后端接口与其他页面完全不变。

**Tech Stack:** Vue 3、TypeScript、Vite、Electron

---

### Task 1: 清理设置页模板

**Files:**
- Modify: `frontend/src/renderer/views/SettingsView.vue`

- [ ] **Step 1: 记录将被删除的模板片段**

```vue
<div class="provider-tabs">
  <button class="provider-tab" :class="{ active: modelConfig.provider === 'local' }" @click="modelConfig.provider = 'local'">🏠 本地模型</button>
  <button class="provider-tab" :class="{ active: modelConfig.provider === 'external' }" @click="modelConfig.provider = 'external'">☁️ 外部API</button>
</div>

<div v-if="modelConfig.provider === 'external'" class="external-model-section">
  <p class="hint mb-4">支持兼容 OpenAI 格式的第三方大模型服务接口</p>
  <div class="form-group"><label>API Base URL</label><input type="text" v-model="modelConfig.external.endpoint" class="input-field" placeholder="https://api.openai.com/v1" /></div>
  <div class="form-group"><label>API Key</label><input type="password" v-model="modelConfig.external.api_key" class="input-field" placeholder="sk-..." /></div>
  <div class="form-group"><label>模型名称</label><input type="text" v-model="modelConfig.external.model" class="input-field" placeholder="例如: qwen-plus" /></div>
  <div class="actions">
    <button class="btn-primary" @click="saveExternalConfig" :disabled="isSaving">{{ isSaving ? '保存中...' : '保存配置' }}</button>
    <button class="btn-secondary" @click="testExternalConnection" :disabled="isTesting">{{ isTesting ? '测试中...' : '测试连接' }}</button>
  </div>
  <div v-if="testResult" class="test-result" :class="testResult.success ? 'success' : 'error'">{{ testResult.message }}</div>
</div>
```

- [ ] **Step 2: 将“模型来源”改为只读说明，不再提供外部 API 切换**

```vue
<div class="model-provider-row">
  <span class="setting-label">模型来源</span>
  <span class="setting-value">本地模型（仅设置页）</span>
</div>
```

- [ ] **Step 3: 保持本地模型区域始终可见**

```vue
<div class="local-model-section">
  <div v-if="ollamaStatus.running">
    <!-- 原有本地模型列表、下载、模型库内容保持不变 -->
  </div>
  <div v-else class="ollama-offline">
    <div class="empty-icon">🔌</div>
    <p>Ollama 服务未启动</p>
    <p class="hint">请重启软件以自动启动内嵌的 Ollama 服务</p>
  </div>
</div>
```

- [ ] **Step 4: 自查模板不再引用外部 API 变量**

Run: `rg -n "external|saveExternalConfig|testExternalConnection|isSaving|isTesting|testResult" /Users/gengyun/Desktop/DiamondMemory/frontend/src/renderer/views/SettingsView.vue`
Expected: 仅剩与本次保留逻辑无关的必要文本，且不再有外部 API 表单引用

- [ ] **Step 5: Commit**

```bash
git add frontend/src/renderer/views/SettingsView.vue
git commit -m "refactor: remove external api settings from settings view"
```

### Task 2: 清理脚本状态与方法

**Files:**
- Modify: `frontend/src/renderer/views/SettingsView.vue`

- [ ] **Step 1: 删除仅服务于外部 API 的状态定义**

```ts
const isSaving = ref(false)
const isTesting = ref(false)
const testResult = ref<{ success: boolean; message: string } | null>(null)
```

- [ ] **Step 2: 简化 `modelConfig` 类型，仅保留本地模型结构**

```ts
const modelConfig = ref({
  model: '',
  llm_enabled: true,
  local: { model: '', endpoint: '' }
})
```

- [ ] **Step 3: 删除外部 API 保存与测试方法**

```ts
async function saveExternalConfig() {
  isSaving.value = true
  try {
    await apiRequest('/api/config/set', { method: 'POST', body: JSON.stringify({ key: 'llm_provider', value: 'external' }) })
    await apiRequest('/api/config/set', { method: 'POST', body: JSON.stringify({ key: 'external_llm_endpoint', value: modelConfig.value.external.endpoint }) })
    await apiRequest('/api/config/set', { method: 'POST', body: JSON.stringify({ key: 'external_llm_api_key', value: modelConfig.value.external.api_key }) })
    await apiRequest('/api/config/set', { method: 'POST', body: JSON.stringify({ key: 'external_llm_model', value: modelConfig.value.external.model }) })
    modelConfig.value.provider = 'external'; toast.success('外部 API 配置已保存')
  } catch (error: any) { toast.error('保存失败: ' + error.message) } finally { isSaving.value = false }
}

async function testExternalConnection() {
  isTesting.value = true; testResult.value = null
  try { const r = await apiRequest<{ success: boolean; message?: string; error?: string }>('/api/config/test-external'); testResult.value = r.success ? { success: true, message: '✅ ' + (r.message || '连接成功') } : { success: false, message: '❌ ' + (r.error || '连接失败') } }
  catch (error: any) { testResult.value = { success: false, message: '❌ 请求异常: ' + error.message } } finally { isTesting.value = false }
}
```

- [ ] **Step 4: 保证已有本地模型读取逻辑继续兼容后端返回结构**

```ts
async function loadModelConfig() {
  try {
    const config = await apiRequest<{
      model?: string
      llm_enabled?: boolean
      local?: { model?: string; endpoint?: string }
    }>('/api/config/llm-model')

    modelConfig.value = {
      model: config.model || '',
      llm_enabled: config.llm_enabled ?? true,
      local: {
        model: config.local?.model || '',
        endpoint: config.local?.endpoint || ''
      }
    }
    selectedModel.value = modelConfig.value.local.model || ''
  } catch {}
}
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/renderer/views/SettingsView.vue
git commit -m "refactor: remove unused external api state from settings view"
```

### Task 3: 验证与记录

**Files:**
- Modify: `版本优化记录/版本优化X.Y.md` 或当前版本文档

- [ ] **Step 1: 运行前端诊断确认无新增错误**

Run: `cd /Users/gengyun/Desktop/DiamondMemory/frontend && npm exec vue-tsc --noEmit`
Expected: 无新增 TypeScript/Vue 报错

- [ ] **Step 2: 获取 IDE 诊断确认 `SettingsView.vue` 正常**

Run: `GetDiagnostics` for `frontend/src/renderer/views/SettingsView.vue`
Expected: 无新增诊断，或仅存在与本次改动无关的旧问题

- [ ] **Step 3: 更新版本优化记录**

```md
### 优化
- 任务类型：优化
- 任务简述：移除设置页中的外部 API 连接设置，仅保留本地模型入口
- 修改文件：frontend/src/renderer/views/SettingsView.vue
- 完成状态：已完成
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/renderer/views/SettingsView.vue "版本优化记录/版本优化X.Y.md"
git commit -m "docs: record settings external api removal"
```
