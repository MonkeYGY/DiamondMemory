# Exit Cleanup: Ollama Autostart Guard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ensure DiamondMemory quits cleanly without leaving behind extra Ollama/runner processes by preventing the Python backend from spawning detached `ollama serve` when it is managed by the Electron app.

**Architecture:** Electron is the single owner of the Ollama lifecycle. When Electron spawns the backend, it injects `DM_MANAGED_BY_ELECTRON=1` and `DM_DISABLE_OLLAMA_AUTOSTART=1`. The backend respects these flags: it still probes Ollama, but it never calls `subprocess.Popen(["ollama","serve"])` and never spawns detached Ollama from `/api/ollama/start` while managed.

**Tech Stack:** Electron, TypeScript, Python, FastAPI, unittest

---

## File Map

- Modify: `frontend/src/main/backend-manager.ts`
  - Add environment flags when Electron spawns the backend process.
- Modify: `backend/app/services/inference/inference_service.py`
  - Guard `ensure_ollama_running()` so it does not spawn Ollama when managed by Electron.
- Modify: `backend/app/services/ollama_download_service.py`
  - Guard `start_ollama()` so it does not spawn detached Ollama when managed by Electron (but still returns success when Ollama is already running).
- Create: `backend/tests/test_ollama_autostart_guard.py`
  - Ensure the guards prevent `subprocess.Popen` in managed mode.

---

### Task 1: Add Backend Autostart Guard Tests

**Files:**
- Create: `backend/tests/test_ollama_autostart_guard.py`

- [ ] **Step 1: Write the failing test for InferenceService not spawning Ollama**

```python
import os
import unittest
from unittest.mock import patch

from app.services.inference.inference_service import InferenceService


class OllamaAutostartGuardTests(unittest.TestCase):
    @patch("app.services.inference.inference_service.subprocess.Popen")
    @patch("app.services.inference.inference_service.requests.get")
    def test_inference_service_does_not_spawn_ollama_when_managed(self, mock_get, mock_popen):
        os.environ["DM_DISABLE_OLLAMA_AUTOSTART"] = "1"
        try:
            mock_get.side_effect = Exception("connection failed")
            service = InferenceService()
            ok = service.ensure_ollama_running()
            self.assertFalse(ok)
            mock_popen.assert_not_called()
        finally:
            os.environ.pop("DM_DISABLE_OLLAMA_AUTOSTART", None)
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd /Users/gengyun/Desktop/DiamondMemory/backend && ../backend/venv/bin/python3 -m unittest backend.tests.test_ollama_autostart_guard.OllamaAutostartGuardTests.test_inference_service_does_not_spawn_ollama_when_managed
```

Expected: FAIL because `ensure_ollama_running()` still attempts `subprocess.Popen(["ollama","serve"])`.

- [ ] **Step 3: Write the failing test for OllamaDownloadService not spawning detached Ollama**

```python
from unittest.mock import MagicMock
from app.services.ollama_download_service import OllamaDownloadService


    @patch("app.services.ollama_download_service.subprocess.Popen")
    def test_ollama_download_service_does_not_spawn_when_managed(self, mock_popen):
        os.environ["DM_DISABLE_OLLAMA_AUTOSTART"] = "1"
        try:
            service = OllamaDownloadService(install_dir="/tmp/dm-test-ollama")
            service.is_installed = MagicMock(return_value=True)
            service.is_ollama_running = MagicMock(return_value=False)
            ok = service.start_ollama(11434)
            self.assertFalse(ok)
            mock_popen.assert_not_called()
        finally:
            os.environ.pop("DM_DISABLE_OLLAMA_AUTOSTART", None)
```

- [ ] **Step 4: Run test to verify it fails**

Run:

```bash
cd /Users/gengyun/Desktop/DiamondMemory/backend && ../backend/venv/bin/python3 -m unittest backend.tests.test_ollama_autostart_guard.OllamaAutostartGuardTests.test_ollama_download_service_does_not_spawn_when_managed
```

Expected: FAIL because `start_ollama()` still calls `subprocess.Popen(... serve ...)`.

---

### Task 2: Inject Electron Managed Flags When Spawning Backend

**Files:**
- Modify: `frontend/src/main/backend-manager.ts`

- [ ] **Step 1: Add managed flags to the backend process environment**

```ts
const env: Record<string, string> = {
  ...process.env as Record<string, string>,
  PYTHONIOENCODING: 'utf-8',
  PYTHONDONTWRITEBYTECODE: '1',
  PYTHONUNBUFFERED: '1',
  DM_MANAGED_BY_ELECTRON: '1',
  DM_DISABLE_OLLAMA_AUTOSTART: '1',
}
```

- [ ] **Step 2: Run frontend build verification**

Run:

```bash
cd /Users/gengyun/Desktop/DiamondMemory/frontend && npm run electron:build-main
```

Expected: PASS

---

### Task 3: Implement Guards In Python Backend

**Files:**
- Modify: `backend/app/services/inference/inference_service.py`
- Modify: `backend/app/services/ollama_download_service.py`

- [ ] **Step 1: Guard InferenceService.ensure_ollama_running()**

```python
    def ensure_ollama_running(self):
        try:
            response = requests.get(self.ollama_tags_url, timeout=2)
            return response.status_code == 200
        except Exception:
            disable_autostart = str(os.environ.get("DM_DISABLE_OLLAMA_AUTOSTART", "")).lower() in ("1", "true", "yes")
            if disable_autostart:
                return False
            ...
```

- [ ] **Step 2: Guard OllamaDownloadService.start_ollama()**

```python
    def start_ollama(self, port: int = 11434) -> bool:
        if not self.is_installed():
            ...

        if self.is_ollama_running(f"http://127.0.0.1:{port}"):
            return True

        disable_autostart = str(os.environ.get("DM_DISABLE_OLLAMA_AUTOSTART", "")).lower() in ("1", "true", "yes")
        if disable_autostart:
            logger.info("[OllamaDownload] 托管模式已开启，禁止从后端直接启动 Ollama")
            return False
        ...
```

---

### Task 4: Run Backend Tests

**Files:**
- Test: `backend/tests/test_ollama_autostart_guard.py`

- [ ] **Step 1: Run the new guard tests**

Run:

```bash
cd /Users/gengyun/Desktop/DiamondMemory/backend && ../backend/venv/bin/python3 -m unittest backend.tests.test_ollama_autostart_guard -v
```

Expected: PASS

---

## Self-Review

- **Spec coverage:** Prevents the backend from starting detached Ollama in the managed Electron lifecycle, eliminating the main source of “quit leaves ollama/runner running”.
- **Placeholder scan:** No `TODO` / `TBD` placeholders.
- **Type consistency:** Uses `DM_MANAGED_BY_ELECTRON=1` and `DM_DISABLE_OLLAMA_AUTOSTART=1` consistently across Electron and backend.

