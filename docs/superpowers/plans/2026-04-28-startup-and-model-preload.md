# Startup And Model Preload Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the app window appear immediately in both dev mode and packaged mode while backend, Ollama, and model warmup continue asynchronously with accurate red/yellow/green status indicators.

**Architecture:** Move startup from a blocking linear chain to a staged async pipeline. The Electron main process owns startup orchestration, the Python backend exposes a single aggregated warmup-status API, and the Vue renderer renders both model badges from that aggregated status instead of probing multiple endpoints independently.

**Tech Stack:** Electron, Vue 3, TypeScript, Python, FastAPI, node:test, unittest, shell script

---

## File Map

- Modify: `DM开发辅助/open_dev_mode.sh`
- Modify: `frontend/src/main/backend-manager.ts`
- Modify: `frontend/src/renderer/App.vue`
- Modify: `frontend/src/renderer/components/TopNav.vue`
- Modify: `backend/main.py`
- Modify: `backend/app/api/config_routes.py`
- Test: `frontend/src/main/__tests__/backend-manager.test.ts`
- Test: `backend/tests/test_startup_status_api.py`

### Task 1: Add backend warmup state API

**Files:**
- Modify: `backend/main.py`
- Modify: `backend/app/api/config_routes.py`
- Test: `backend/tests/test_startup_status_api.py`

- [ ] **Step 1: Write the failing backend tests**

```python
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from main import app


class StartupStatusApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_ollama_status_reports_installed_and_loaded_separately(self):
        tags_payload = {
            "models": [
                {"name": "qwen3.5:4b"},
                {"name": "bge-m3"},
            ]
        }
        ps_payload = {
            "models": [
                {"name": "qwen3.5:4b"},
            ]
        }

        with patch("app.api.config_routes.requests.get") as mock_get:
            mock_get.side_effect = [
                type("Resp", (), {"status_code": 200, "json": lambda self: tags_payload})(),
                type("Resp", (), {"status_code": 200, "json": lambda self: ps_payload})(),
            ]

            response = self.client.get("/api/config/startup-status")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["ollama_ready"])
        self.assertTrue(data["llm_installed"])
        self.assertTrue(data["llm_loaded"])
        self.assertTrue(data["embedding_installed"])
        self.assertFalse(data["embedding_loaded"])
        self.assertEqual(data["warmup_phase"], "warming_up")

    def test_ollama_status_reports_degraded_when_tags_probe_fails(self):
        with patch("app.api.config_routes.requests.get", side_effect=Exception("boom")):
            response = self.client.get("/api/config/startup-status")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data["ollama_ready"])
        self.assertEqual(data["warmup_phase"], "degraded")
```

- [ ] **Step 2: Run backend tests to verify they fail**

Run: `cd /Users/gengyun/Desktop/DiamondMemory/backend && python3 -m unittest tests.test_startup_status_api -v`

Expected: FAIL with `404` on `/api/config/startup-status` or missing keys such as `llm_loaded`

- [ ] **Step 3: Add shared warmup state in `backend/main.py`**

```python
startup_runtime = {
    "backend_ready": False,
    "ollama_ready": False,
    "warmup_phase": "idle",
    "llm_model_name": settings.local_llm_model,
    "embedding_model_name": settings.embedding_provider,
    "llm_loaded": False,
    "embedding_loaded": False,
    "last_error": "",
}


def update_startup_runtime(**kwargs):
    startup_runtime.update(kwargs)
```

And inside `lifespan()`:

```python
    update_startup_runtime(
        backend_ready=False,
        ollama_ready=False,
        warmup_phase="starting_services",
        llm_model_name=settings.local_llm_model,
        embedding_model_name=settings.embedding_provider,
        llm_loaded=False,
        embedding_loaded=False,
        last_error="",
    )
```

Before `yield`:

```python
    update_startup_runtime(backend_ready=True)
```

Inside `_preload_llm()` success path:

```python
                update_startup_runtime(llm_loaded=True)
```

Inside `_preload_embedding()` success path:

```python
                update_startup_runtime(embedding_loaded=True)
```

When Ollama becomes reachable:

```python
                    update_startup_runtime(ollama_ready=True, warmup_phase="warming_up")
```

When both warmups finish:

```python
        final_phase = "ready" if startup_runtime["llm_loaded"] and startup_runtime["embedding_loaded"] else "warming_up"
        update_startup_runtime(warmup_phase=final_phase)
```

On timeout or exception:

```python
            update_startup_runtime(warmup_phase="degraded", last_error=str(e))
```

- [ ] **Step 4: Implement aggregated status endpoint in `config_routes.py`**

```python
@router.get("/startup-status")
def get_startup_status():
    import requests
    from main import startup_runtime

    llm_name = settings.local_llm_model
    emb_name = settings.embedding_provider

    try:
        tags_resp = requests.get(f"{_get_ollama_url()}/api/tags", timeout=5)
        ps_resp = requests.get(f"{_get_ollama_url()}/api/ps", timeout=5)

        installed_models = []
        loaded_models = []

        if tags_resp.status_code == 200:
            installed_models = [m.get("name", "") for m in tags_resp.json().get("models", [])]
        if ps_resp.status_code == 200:
            loaded_models = [m.get("name", "") for m in ps_resp.json().get("models", [])]

        llm_installed = any(name == llm_name or name.startswith(llm_name.split(":")[0]) for name in installed_models)
        llm_loaded = any(name == llm_name or name.startswith(llm_name.split(":")[0]) for name in loaded_models) or startup_runtime["llm_loaded"]
        embedding_installed = any("bge-m3" in name for name in installed_models)
        embedding_loaded = any("bge-m3" in name for name in loaded_models) or startup_runtime["embedding_loaded"]

        warmup_phase = "ready" if llm_loaded and embedding_loaded else "warming_up"

        return {
            "backend_ready": startup_runtime["backend_ready"],
            "ollama_ready": bool(installed_models or loaded_models),
            "llm_model_name": llm_name,
            "embedding_model_name": emb_name,
            "llm_installed": llm_installed,
            "llm_loaded": llm_loaded,
            "embedding_installed": embedding_installed,
            "embedding_loaded": embedding_loaded,
            "warmup_phase": warmup_phase,
            "last_error": startup_runtime["last_error"],
        }
    except Exception as exc:
        return {
            "backend_ready": startup_runtime["backend_ready"],
            "ollama_ready": False,
            "llm_model_name": llm_name,
            "embedding_model_name": emb_name,
            "llm_installed": False,
            "llm_loaded": startup_runtime["llm_loaded"],
            "embedding_installed": False,
            "embedding_loaded": startup_runtime["embedding_loaded"],
            "warmup_phase": "degraded",
            "last_error": str(exc),
        }
```

Also fix existing `/preload-models` embedding call:

```python
            requests.post(f"{_get_ollama_url()}/api/embeddings", json={"model": emb_model, "prompt": "warmup", "keep_alive": -1}, timeout=120)
```

- [ ] **Step 5: Run backend tests to verify they pass**

Run: `cd /Users/gengyun/Desktop/DiamondMemory/backend && python3 -m unittest tests.test_startup_status_api -v`

Expected: PASS for both `StartupStatusApiTests`

- [ ] **Step 6: Commit**

```bash
git add backend/main.py backend/app/api/config_routes.py backend/tests/test_startup_status_api.py
git commit -m "feat: add startup warmup status api"
```

### Task 2: Make Electron startup non-blocking

**Files:**
- Modify: `frontend/src/main/backend-manager.ts`
- Test: `frontend/src/main/__tests__/backend-manager.test.ts`

- [ ] **Step 1: Write the failing Electron startup tests**

```ts
import test from 'node:test'
import assert from 'node:assert/strict'

import { BackendManager } from '../backend-manager.js'

test('startBackend launches backend without waiting for Ollama warmup', async () => {
  const manager = new BackendManager()
  const steps: string[] = []

  ;(manager as any).startOllama = async () => {
    steps.push('ollama:start')
    await new Promise(resolve => setTimeout(resolve, 50))
    steps.push('ollama:done')
    return true
  }
  ;(manager as any).resolveBackendPort = async () => 18000
  ;(manager as any).waitForBackend = async () => true
  ;(manager as any).getBackendSourcePath = () => '/tmp/main.py'

  const originalSpawn = (manager as any).spawnProcessForTest
  ;(manager as any).spawnProcessForTest = () => {
    steps.push('backend:spawn')
    return { stdout: { on() {} }, stderr: { on() {} }, on() {} }
  }

  await manager.startBackend('/tmp/data')

  assert.deepEqual(steps.slice(0, 2), ['ollama:start', 'backend:spawn'])
  ;(manager as any).spawnProcessForTest = originalSpawn
})
```

- [ ] **Step 2: Run frontend tests to verify they fail**

Run: `cd /Users/gengyun/Desktop/DiamondMemory/frontend && node --test src/main/__tests__/backend-manager.test.ts`

Expected: FAIL because `BackendManager` is not exported for direct testing or because backend spawn still happens after Ollama wait completes

- [ ] **Step 3: Refactor `backend-manager.ts` into staged startup**

Add test seam:

```ts
export class BackendManager {
  protected spawnProcessForTest(command: string, args: string[], options: Parameters<typeof spawn>[2]) {
    return spawn(command, args, options)
  }
```

Replace the blocking call in `startBackend()`:

```ts
      void this.ensureOllamaServiceAndWarmModels()

      this.backendPort = await this.resolveBackendPort()
```

Add staged helper:

```ts
  private warmupPromise: Promise<void> | null = null

  private async ensureOllamaServiceAndWarmModels(): Promise<void> {
    if (this.warmupPromise) return this.warmupPromise

    this.warmupPromise = (async () => {
      const ollamaReady = await this.startOllama()
      if (!ollamaReady) return
      await this.waitForOllama()
      await this.warmupModels()
    })()

    try {
      await this.warmupPromise
    } finally {
      this.warmupPromise = null
    }
  }
```

Add model warmup:

```ts
  private async warmupModels(): Promise<void> {
    try {
      await fetch(`http://127.0.0.1:${this.backendPort}/api/config/preload-models`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      })
    } catch (error) {
      console.warn('[BackendManager] 后台模型预热触发失败:', error)
    }
  }
```

Use the seam for process spawn:

```ts
      this.backendProcess = this.spawnProcessForTest(command, args, {
        cwd,
        stdio: ['pipe', 'pipe', 'pipe'],
        detached: false,
        env
      })
```

- [ ] **Step 4: Run frontend tests to verify they pass**

Run: `cd /Users/gengyun/Desktop/DiamondMemory/frontend && node --test src/main/__tests__/backend-manager.test.ts`

Expected: PASS and the recorded order shows backend spawn before `ollama:done`

- [ ] **Step 5: Commit**

```bash
git add frontend/src/main/backend-manager.ts frontend/src/main/__tests__/backend-manager.test.ts
git commit -m "feat: make backend startup non-blocking"
```

### Task 3: Switch renderer to aggregated startup status

**Files:**
- Modify: `frontend/src/renderer/App.vue`
- Modify: `frontend/src/renderer/components/TopNav.vue`

- [ ] **Step 1: Add the renderer state shape**

In `App.vue`, replace the old booleans:

```ts
const startupStatus = ref({
  backend_ready: false,
  ollama_ready: false,
  llm_model_name: '',
  embedding_model_name: 'bge-m3',
  llm_installed: false,
  llm_loaded: false,
  embedding_installed: false,
  embedding_loaded: false,
  warmup_phase: 'idle',
  last_error: '',
})
```

- [ ] **Step 2: Replace direct `/api/tags` probing with `/api/config/startup-status`**

In `checkStatus()`:

```ts
  try {
    if (backendStatus.value.isRunning) {
      startupStatus.value = await apiRequest('/api/config/startup-status')
      llmModelName.value = startupStatus.value.llm_model_name || llmModelName.value
    } else {
      startupStatus.value = {
        backend_ready: false,
        ollama_ready: false,
        llm_model_name: llmModelName.value || '',
        embedding_model_name: 'bge-m3',
        llm_installed: false,
        llm_loaded: false,
        embedding_installed: false,
        embedding_loaded: false,
        warmup_phase: 'idle',
        last_error: '',
      }
    }
  } catch {
    startupStatus.value.warmup_phase = 'degraded'
  }
```

Update `TopNav` props:

```vue
<TopNav
  :startup-status="startupStatus"
  :backend-running="backendStatus.isRunning"
/>
```

Retain the install-status popup guard:

```ts
if (backendStatus.value.isRunning && !startupStatus.value.ollama_ready) {
```

- [ ] **Step 3: Render red/yellow/green badges in `TopNav.vue`**

Replace props and computed logic with:

```ts
const props = defineProps<{
  startupStatus: {
    backend_ready: boolean
    ollama_ready: boolean
    llm_model_name: string
    embedding_model_name: string
    llm_installed: boolean
    llm_loaded: boolean
    embedding_installed: boolean
    embedding_loaded: boolean
    warmup_phase: string
    last_error: string
  }
  backendRunning: boolean
}>()

function getPhase(installed: boolean, loaded: boolean) {
  if (loaded) return 'ready'
  if (installed || props.startupStatus.ollama_ready) return 'warming'
  return 'offline'
}

const embeddingPhase = computed(() => getPhase(props.startupStatus.embedding_installed, props.startupStatus.embedding_loaded))
const llmPhase = computed(() => getPhase(props.startupStatus.llm_installed, props.startupStatus.llm_loaded))

const llmStatusText = computed(() => {
  const name = props.startupStatus.llm_model_name || '主模型'
  if (llmPhase.value === 'ready') return `${name} 已就绪`
  if (llmPhase.value === 'warming') return `${name} 预热中`
  return `${name} 未启动`
})
```

Template update:

```vue
<div class="model-status" :title="embeddingPhase">
  <div class="status-dot bge" :class="embeddingPhase"></div>
  <span class="status-text">
    {{ embeddingPhase === 'ready' ? 'BGE-M3 已就绪' : embeddingPhase === 'warming' ? 'BGE-M3 预热中' : 'BGE-M3 未启动' }}
  </span>
</div>
```

Style update:

```css
.status-dot.offline { background: var(--color-error); }
.status-dot.warming { background: var(--color-warning); }
.status-dot.ready { background: var(--color-success); }
```

- [ ] **Step 4: Run type checking**

Run: `cd /Users/gengyun/Desktop/DiamondMemory/frontend && npm run build`

Expected: PASS through `vue-tsc --noEmit` and Vite build

- [ ] **Step 5: Commit**

```bash
git add frontend/src/renderer/App.vue frontend/src/renderer/components/TopNav.vue
git commit -m "feat: show staged startup status in top nav"
```

### Task 4: Make dev-mode script show the window first

**Files:**
- Modify: `DM开发辅助/open_dev_mode.sh`
- Test: `DM开发辅助/tests/test_open_dev_mode_order.py`

- [ ] **Step 1: Write the failing script-order test**

```python
import unittest
from pathlib import Path


class OpenDevModeOrderTests(unittest.TestCase):
    def test_frontend_launch_block_comes_before_backend_bootstrap_block(self):
        script = Path("DM开发辅助/open_dev_mode.sh").read_text(encoding="utf-8")

        frontend_index = script.index('npm run electron:dev')
        backend_index = script.index('backend_bootstrap.py')

        self.assertLess(frontend_index, backend_index)
```

- [ ] **Step 2: Run the script-order test to verify it fails**

Run: `cd /Users/gengyun/Desktop/DiamondMemory && python3 -m unittest DM开发辅助.tests.test_open_dev_mode_order -v`

Expected: FAIL because the backend bootstrap block currently appears before the Electron dev block

- [ ] **Step 3: Reorder `open_dev_mode.sh`**

Move the Electron block above backend bootstrap so the script structure becomes:

```bash
# 2. 启动前端 Electron 服务
if [ -d "$PROJECT_DIR/frontend" ]; then
    echo -e "${GREEN}✓ 准备启动 Electron 跨平台前端...${NC}"
    osascript -e "tell application \"Terminal\" to do script \"cd \\\"$PROJECT_DIR/frontend\\\" && npm run electron:dev\""
    echo -e "${GREEN}✓ 已调起新终端运行前端应用${NC}"
fi

# 3. 启动后端服务
echo -e "${GREEN}✓ 准备启动 FastAPI 后端服务...${NC}"
BACKEND_LAUNCH_CMD=$(python3 "$SCRIPT_DIR/backend_bootstrap.py" --backend-dir "$PROJECT_DIR/backend" --installer-python "$(command -v python3)")
```

Keep the existing port-conflict guard intact; only change ordering so the frontend terminal opens first.

- [ ] **Step 4: Run the script-order test to verify it passes**

Run: `cd /Users/gengyun/Desktop/DiamondMemory && python3 -m unittest DM开发辅助.tests.test_open_dev_mode_order -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add DM开发辅助/open_dev_mode.sh DM开发辅助/tests/test_open_dev_mode_order.py
git commit -m "feat: launch frontend first in dev mode"
```

### Task 5: End-to-end verification and cleanup

**Files:**
- Modify: `版本优化记录/版本优化0.9.md`

- [ ] **Step 1: Run backend validation**

Run: `cd /Users/gengyun/Desktop/DiamondMemory/backend && python3 -m unittest tests.test_startup_status_api -v`

Expected: PASS

- [ ] **Step 2: Run frontend validation**

Run: `cd /Users/gengyun/Desktop/DiamondMemory/frontend && node --test src/main/__tests__/backend-manager.test.ts`

Expected: PASS

Run: `cd /Users/gengyun/Desktop/DiamondMemory/frontend && npm run build`

Expected: PASS

- [ ] **Step 3: Manual smoke test**

Run dev mode and confirm:

```bash
cd /Users/gengyun/Desktop/DiamondMemory
bash DM开发辅助/open_dev_mode.sh
```

Expected:
- Electron window appears before backend bootstrap completes
- Top-right badges move from red to yellow to green
- `BGE-M3` and the active LLM can reach green independently

- [ ] **Step 4: Update version log entry with implementation files**

Append or revise the existing `版本优化0.9.md` startup-related entry so it lists the final modified code files after implementation.

- [ ] **Step 5: Commit**

```bash
git add 版本优化记录/版本优化0.9.md
git commit -m "docs: finalize startup optimization log"
```
