# Local-first 降级可用性 + 持久化任务队列 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在未安装 Ollama/未下载模型时，应用仍可检索/浏览/导出/管理；耗时整理/提炼/图谱重建进入持久化任务队列，支持进度与暂停/继续、低功耗节流。

**Architecture:** 后端提供统一能力状态 API（capabilities），并引入 SQLite 持久化任务表 + 单 worker 串行执行；前端通过任务面板展示与控制任务，同时对“需要模型”的任务进入 blocked 状态并给予引导。

**Tech Stack:** FastAPI + SQLite（SQLiteStore）+ Vue3/Pinia + Electron

---

## 0. 文件结构与改动范围（先锁定边界）

### 后端（Python/FastAPI）

**Create**
- `backend/app/api/system_routes.py`：`GET /api/system/capabilities`
- `backend/app/api/task_routes.py`：任务队列 API（enqueue/list/detail/pause/resume/cancel）
- `backend/app/services/task_queue_service.py`：任务队列 service + 单 worker
- `backend/app/models/task_models.py`：Pydantic 请求/响应模型（如工程已有 models 目录）
- `backend/tests/test_capabilities_api.py`：能力状态 API 单测
- `backend/tests/test_task_queue_api.py`：任务队列 API 单测（最小状态机）

**Modify**
- `backend/main.py`：注册新 router
- `backend/app/storage/sqlite_store.py`：新增 task_queue 表（_init_database + _migrate_database）及 CRUD 方法

### 前端（Vue3/Electron renderer）

**Create**
- `frontend/src/renderer/stores/tasks.ts`：任务队列 store（轮询、enqueue、pause/resume/cancel）
- `frontend/src/renderer/components/TaskPanel.vue`：任务面板（最小 UI）

**Modify**
- `frontend/src/renderer/App.vue`：挂载 TaskPanel、启动轮询
- `frontend/src/renderer/views/MemoryView.vue`：深度整理/快速整理 → enqueue（并保留兼容逻辑开关）
- `frontend/src/renderer/api/backend.ts`：新增 tasks/capabilities API 封装

---

## Task 1: 后端 SQLite 增加 task_queue 表与 CRUD

**Files:**
- Modify: `backend/app/storage/sqlite_store.py`
- Test: `backend/tests/test_task_queue_api.py`（后续任务会用到）

- [ ] **Step 1: 写一个最小的表存在性测试（失败优先）**

新增测试文件 `backend/tests/test_task_queue_api.py`（先只测表能创建并可插入一条任务）：

```python
import unittest
import uuid

from app.storage.sqlite_store import SQLiteStore


class TaskQueueDbTests(unittest.TestCase):
    def test_task_queue_table_exists_and_can_insert(self):
        store = SQLiteStore()
        task_id = str(uuid.uuid4())

        ok = getattr(store, "create_task_queue_item", None)
        self.assertTrue(callable(ok), "SQLiteStore.create_task_queue_item should exist")

        created = store.create_task_queue_item(
            task_id=task_id,
            task_type="deep_organize",
            requires_model=True,
            power_mode="low_power",
            params={"force": False},
        )
        self.assertTrue(created)

        item = store.get_task_queue_item(task_id)
        self.assertEqual(item["id"], task_id)
        self.assertEqual(item["type"], "deep_organize")
        self.assertEqual(item["status"], "queued")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行测试，确认失败**

Run:
```bash
python -m unittest backend.tests.test_task_queue_api.TaskQueueDbTests -v
```
Expected: FAIL（缺少 `create_task_queue_item/get_task_queue_item` 或表字段不存在）

- [ ] **Step 3: 在 SQLiteStore._init_database 增加 task_queue 表**

在 `SQLiteStore._init_database()` 的建表区块追加：

```python
cursor.execute(
    """
    CREATE TABLE IF NOT EXISTS task_queue (
        id TEXT PRIMARY KEY,
        type TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'queued',
        progress INTEGER NOT NULL DEFAULT 0,
        message TEXT DEFAULT '',
        requires_model INTEGER NOT NULL DEFAULT 0,
        blocked_reason TEXT DEFAULT '',
        power_mode TEXT NOT NULL DEFAULT 'normal',
        params_json TEXT NOT NULL DEFAULT '{}',
        result_json TEXT NOT NULL DEFAULT '{}',
        error TEXT DEFAULT '',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        started_at TEXT,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
        finished_at TEXT
    )
    """
)
cursor.execute("CREATE INDEX IF NOT EXISTS idx_task_queue_status_created ON task_queue(status, created_at)")
cursor.execute("CREATE INDEX IF NOT EXISTS idx_task_queue_type_created ON task_queue(type, created_at)")
```

并在 `_migrate_database()` 中补充一次 `CREATE TABLE IF NOT EXISTS task_queue ...`（避免老库缺表）。

- [ ] **Step 4: 在 SQLiteStore 增加 CRUD 方法（最小够用）**

在 `SQLiteStore` 中新增方法（参考 skill_upgrade_tasks 的写法）：

```python
import time


def create_task_queue_item(
    self,
    task_id: str,
    task_type: str,
    requires_model: bool = False,
    power_mode: str = "normal",
    params: dict | None = None,
) -> bool:
    conn = self._get_conn()
    cursor = conn.cursor()
    now = self._get_beijing_timestamp()
    cursor.execute(
        """
        INSERT OR REPLACE INTO task_queue (
            id, type, status, progress, message,
            requires_model, blocked_reason, power_mode,
            params_json, result_json, error,
            created_at, updated_at
        ) VALUES (?, ?, 'queued', 0, '', ?, '', ?, ?, '{}', '', ?, ?)
        """,
        (
            task_id,
            task_type,
            1 if requires_model else 0,
            power_mode,
            json.dumps(params or {}, ensure_ascii=False),
            now,
            now,
        ),
    )
    conn.commit()
    return cursor.rowcount > 0


def get_task_queue_item(self, task_id: str) -> dict | None:
    conn = self._get_conn()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id, type, status, progress, message, requires_model, blocked_reason,
               power_mode, params_json, result_json, error,
               created_at, started_at, updated_at, finished_at
        FROM task_queue
        WHERE id = ?
        """,
        (task_id,),
    )
    row = cursor.fetchone()
    if not row:
        return None
    keys = [
        "id","type","status","progress","message","requires_model","blocked_reason",
        "power_mode","params","result","error",
        "created_at","started_at","updated_at","finished_at",
    ]
    item = dict(zip(keys, row))
    item["requires_model"] = bool(item.get("requires_model"))
    for k in ("params", "result"):
        try:
            item[k] = json.loads(item.get(k) or "{}")
        except Exception:
            item[k] = {}
    return item


def list_task_queue_items(self, statuses: list[str] | None = None, limit: int = 50) -> list[dict]:
    conn = self._get_conn()
    cursor = conn.cursor()
    where_sql = ""
    params: list = []
    if statuses:
        placeholders = ",".join(["?"] * len(statuses))
        where_sql = f"WHERE status IN ({placeholders})"
        params.extend(statuses)
    cursor.execute(
        f"""
        SELECT id, type, status, progress, message, requires_model, blocked_reason,
               power_mode, params_json, result_json, error,
               created_at, started_at, updated_at, finished_at
        FROM task_queue
        {where_sql}
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (*params, int(limit)),
    )
    rows = cursor.fetchall() or []
    return [self.get_task_queue_item(r[0]) for r in rows if r and r[0]]


def update_task_queue_item(
    self,
    task_id: str,
    status: str | None = None,
    progress: int | None = None,
    message: str | None = None,
    blocked_reason: str | None = None,
    result: dict | None = None,
    error: str | None = None,
    started_at: str | None = None,
    finished_at: str | None = None,
) -> bool:
    conn = self._get_conn()
    cursor = conn.cursor()
    updates = []
    params = []
    if status is not None:
        updates.append("status = ?")
        params.append(status)
    if progress is not None:
        updates.append("progress = ?")
        params.append(int(progress))
    if message is not None:
        updates.append("message = ?")
        params.append(message)
    if blocked_reason is not None:
        updates.append("blocked_reason = ?")
        params.append(blocked_reason)
    if result is not None:
        updates.append("result_json = ?")
        params.append(json.dumps(result, ensure_ascii=False))
    if error is not None:
        updates.append("error = ?")
        params.append(error)
    if started_at is not None:
        updates.append("started_at = ?")
        params.append(started_at)
    if finished_at is not None:
        updates.append("finished_at = ?")
        params.append(finished_at)
    updates.append("updated_at = ?")
    params.append(self._get_beijing_timestamp())
    params.append(task_id)
    cursor.execute(f"UPDATE task_queue SET {', '.join(updates)} WHERE id = ?", tuple(params))
    conn.commit()
    return cursor.rowcount > 0
```

- [ ] **Step 5: 运行测试，确认通过**

Run:
```bash
python -m unittest backend.tests.test_task_queue_api.TaskQueueDbTests -v
```
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/storage/sqlite_store.py backend/tests/test_task_queue_api.py
git commit -m "feat(backend): add task_queue table and sqlite store helpers"
```

---

## Task 2: 后端 Capabilities 能力状态 API（降级可用性统一入口）

**Files:**
- Create: `backend/app/api/system_routes.py`
- Modify: `backend/main.py`
- Test: `backend/tests/test_capabilities_api.py`

- [ ] **Step 1: 写 failing test（capabilities 基本字段）**

`backend/tests/test_capabilities_api.py`：

```python
import unittest
from fastapi.testclient import TestClient

from main import app


class CapabilitiesApiTests(unittest.TestCase):
    def test_capabilities_returns_allowed_flags(self):
        client = TestClient(app)
        resp = client.get("/api/system/capabilities")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("backend_ready", data)
        self.assertIn("model_ready", data)
        self.assertIn("allowed", data)
        self.assertTrue(data["allowed"]["browse"])
        self.assertTrue(data["allowed"]["search"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行测试确认失败**

Run:
```bash
python -m unittest backend.tests.test_capabilities_api.CapabilitiesApiTests -v
```
Expected: FAIL（404 / router 未注册）

- [ ] **Step 3: 实现 system_routes（capabilities）**

`backend/app/api/system_routes.py`（最小实现：基于现有 `config_routes.get_startup_status()` + `embedding_service.get_backend_info()`）：

```python
from fastapi import APIRouter

from app.api import config_routes
from app.services.embedding_service import embedding_service

router = APIRouter(prefix="/system", tags=["system"])


def _derive_degraded_reason(startup: dict, emb: dict) -> str:
    if not startup.get("ollama_ready"):
        return "OLLAMA_NOT_RUNNING"
    if not startup.get("llm_installed"):
        return "MODEL_NOT_INSTALLED"
    if not startup.get("llm_loaded"):
        return "MODEL_NOT_LOADED"
    return "OK"


@router.get("/capabilities")
def get_capabilities():
    startup = config_routes.get_startup_status()
    emb_info = embedding_service.get_backend_info()

    # LLM readiness：以 llm_loaded 为主；embedding 可允许 tfidf
    model_ready = bool(startup.get("llm_loaded"))
    degraded_reason = _derive_degraded_reason(startup, emb_info)

    allowed = {
        "browse": True,
        "search": True,
        "export": True,
        "manage": True,
        "llm_summarize": model_ready,
        "llm_extract_skill": model_ready,
        "graph_rebuild": True,
    }

    return {
        "backend_ready": bool(startup.get("backend_ready")),
        "ollama_ready": bool(startup.get("ollama_ready")),
        "model_ready": model_ready,
        "degraded_reason": degraded_reason,
        "llm": {
            "model": startup.get("llm_model_name", ""),
            "installed": bool(startup.get("llm_installed")),
            "loaded": bool(startup.get("llm_loaded")),
        },
        "embedding": {
            "model": startup.get("embedding_model_name", ""),
            "available": True,
            "backend": emb_info.get("backend", "tfidf"),
        },
        "allowed": allowed,
    }
```

- [ ] **Step 4: 在 backend/main.py 注册 router**

在 `backend/main.py` 的 import 里加入：

```python
from app.api import system_routes
```

并在 include_router 区域加入：

```python
app.include_router(system_routes.router, prefix="/api", tags=["system"])
```

- [ ] **Step 5: 运行测试确认通过**

Run:
```bash
python -m unittest backend.tests.test_capabilities_api.CapabilitiesApiTests -v
```
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/system_routes.py backend/main.py backend/tests/test_capabilities_api.py
git commit -m "feat(backend): add /api/system/capabilities for degraded mode"
```

---

## Task 3: 后端 Task Queue Service（单 worker + blocked/paused 状态机）

**Files:**
- Create: `backend/app/services/task_queue_service.py`
- Test: `backend/tests/test_task_queue_api.py`（补充 service 级别测试）

- [ ] **Step 1: 在测试里增加“requires_model -> blocked”用例（先失败）**

在 `backend/tests/test_task_queue_api.py` 追加：

```python
from unittest.mock import patch


class TaskQueueServiceTests(unittest.TestCase):
    def test_requires_model_blocks_when_model_not_ready(self):
        from app.services.task_queue_service import task_queue_service

        # 强制 model_ready = False
        with patch("app.services.task_queue_service._is_model_ready", return_value=False):
            task_id = task_queue_service.enqueue("extract_skills", requires_model=True)
            item = task_queue_service.store.get_task_queue_item(task_id)
            self.assertEqual(item["status"], "blocked")
            self.assertEqual(item["blocked_reason"], "MODEL_NOT_READY")
```

- [ ] **Step 2: 实现 task_queue_service（最小可跑）**

`backend/app/services/task_queue_service.py`：

```python
import threading
import time
import uuid
from typing import Any, Callable

from app.storage.sqlite_store import SQLiteStore
from app.services.adaptive_organize_service import adaptive_organize_service
from app.api import config_routes


def _is_model_ready() -> bool:
    s = config_routes.get_startup_status()
    return bool(s.get("llm_loaded"))


class TaskQueueService:
    def __init__(self):
        self.store = SQLiteStore()
        self._worker_lock = threading.Lock()
        self._worker_started = False
        self._stop_event = threading.Event()

        # 任务执行器注册表（第一期只做占位执行：实际逻辑在后续 task 填充）
        self._executors: dict[str, Callable[[str, dict], dict]] = {}

    def start_worker(self):
        with self._worker_lock:
            if self._worker_started:
                return
            t = threading.Thread(target=self._run_loop, daemon=True)
            t.start()
            self._worker_started = True

    def enqueue(self, task_type: str, requires_model: bool = False, power_mode: str = "normal", params: dict | None = None) -> str:
        task_id = str(uuid.uuid4())
        self.store.create_task_queue_item(
            task_id=task_id,
            task_type=task_type,
            requires_model=requires_model,
            power_mode=power_mode,
            params=params or {},
        )
        # 入队后立即尝试 worker
        self.start_worker()

        # 若明确需要模型但当前不可用，直接标记 blocked（符合验收：点了也入队，但提示需要模型）
        if requires_model and not _is_model_ready():
            self.store.update_task_queue_item(task_id, status="blocked", blocked_reason="MODEL_NOT_READY", message="需要模型：请先启动/安装 Ollama 并下载模型")
        return task_id

    def pause(self, task_id: str) -> bool:
        return self.store.update_task_queue_item(task_id, status="paused")

    def resume(self, task_id: str) -> bool:
        # blocked/paused -> queued
        item = self.store.get_task_queue_item(task_id)
        if not item:
            return False
        if item["status"] not in ("paused", "blocked"):
            return False
        return self.store.update_task_queue_item(task_id, status="queued", blocked_reason="", message="")

    def cancel(self, task_id: str) -> bool:
        return self.store.update_task_queue_item(task_id, status="cancelled", finished_at=self.store._get_beijing_timestamp())

    def register_executor(self, task_type: str, fn: Callable[[str, dict], dict]):
        self._executors[task_type] = fn

    def _run_loop(self):
        while not self._stop_event.is_set():
            # 取一个 queued 任务
            items = self.store.list_task_queue_items(statuses=["queued"], limit=1)
            if not items:
                time.sleep(0.5)
                continue

            item = items[0]
            task_id = item["id"]

            # 执行前：requires_model 检查
            if item.get("requires_model") and not _is_model_ready():
                self.store.update_task_queue_item(task_id, status="blocked", blocked_reason="MODEL_NOT_READY", message="需要模型：请先启动/安装 Ollama 并下载模型")
                continue

            now = self.store._get_beijing_timestamp()
            self.store.update_task_queue_item(task_id, status="running", started_at=now, progress=1, message="任务开始执行")

            try:
                exec_fn = self._executors.get(item["type"])
                if not exec_fn:
                    # 第一阶段：先跑通队列，不实现具体业务也能验证状态机
                    for p in (10, 30, 60, 90, 100):
                        # paused/cancelled 轮询
                        latest = self.store.get_task_queue_item(task_id) or {}
                        if latest.get("status") == "paused":
                            self.store.update_task_queue_item(task_id, status="queued", message="已暂停（等待继续）")
                            break
                        if latest.get("status") == "cancelled":
                            break
                        self.store.update_task_queue_item(task_id, progress=p, message=f"模拟执行中：{p}%")
                        # 低功耗节流
                        if latest.get("power_mode") == "low_power":
                            adaptive_organize_service.adaptive_sleep()
                        else:
                            time.sleep(0.05)
                    else:
                        self.store.update_task_queue_item(task_id, status="completed", progress=100, message="任务完成", finished_at=self.store._get_beijing_timestamp(), result={"ok": True})
                    continue

                result = exec_fn(task_id, item.get("params") or {})
                self.store.update_task_queue_item(task_id, status="completed", progress=100, message="任务完成", finished_at=self.store._get_beijing_timestamp(), result=result or {})
            except Exception as e:
                self.store.update_task_queue_item(task_id, status="failed", message="任务失败", finished_at=self.store._get_beijing_timestamp(), error=str(e))


task_queue_service = TaskQueueService()
```

- [ ] **Step 3: 运行测试确认通过**

Run:
```bash
python -m unittest backend.tests.test_task_queue_api -v
```
Expected: PASS（DB + service blocked 测试通过）

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/task_queue_service.py backend/tests/test_task_queue_api.py
git commit -m "feat(backend): add persistent task queue service with single worker"
```

---

## Task 4: 后端 Task Queue API（enqueue/list/detail/pause/resume/cancel）

**Files:**
- Create: `backend/app/api/task_routes.py`
- Modify: `backend/main.py`
- Test: `backend/tests/test_task_queue_api.py`（补 API 测试）

- [ ] **Step 1: 写 API failing test（enqueue + list）**

在 `backend/tests/test_task_queue_api.py` 追加：

```python
from fastapi.testclient import TestClient
from main import app


class TaskQueueApiTests(unittest.TestCase):
    def test_enqueue_and_list_tasks(self):
        client = TestClient(app)
        resp = client.post("/api/tasks/enqueue", json={"type": "deep_organize", "power_mode": "normal", "params": {"force": False}})
        self.assertEqual(resp.status_code, 200)
        task_id = resp.json()["id"]

        resp2 = client.get("/api/tasks", params={"status": "queued,running,blocked"})
        self.assertEqual(resp2.status_code, 200)
        ids = [t["id"] for t in resp2.json().get("items", [])]
        self.assertIn(task_id, ids)
```

- [ ] **Step 2: 实现 task_routes**

`backend/app/api/task_routes.py`：

```python
from fastapi import APIRouter, Body, HTTPException, Query
from pydantic import BaseModel

from app.services.task_queue_service import task_queue_service

router = APIRouter(prefix="/tasks", tags=["tasks"])


class EnqueueTaskRequest(BaseModel):
    type: str
    power_mode: str = "normal"
    params: dict = {}


@router.post("/enqueue")
def enqueue_task(payload: EnqueueTaskRequest):
    # 简单规则：这三类任务默认 requires_model=True（后续可细化）
    requires_model = payload.type in ("deep_organize", "extract_skills")
    task_id = task_queue_service.enqueue(payload.type, requires_model=requires_model, power_mode=payload.power_mode, params=payload.params)
    item = task_queue_service.store.get_task_queue_item(task_id)
    return {"id": task_id, "status": item.get("status", "queued")}


@router.get("")
def list_tasks(status: str = Query("", description="逗号分隔状态，如 queued,running,blocked"), limit: int = 50):
    statuses = [s.strip() for s in status.split(",") if s.strip()]
    items = task_queue_service.store.list_task_queue_items(statuses=statuses or None, limit=min(int(limit), 200))
    return {"items": items}


@router.get("/{task_id}")
def get_task(task_id: str):
    item = task_queue_service.store.get_task_queue_item(task_id)
    if not item:
        raise HTTPException(status_code=404, detail="任务不存在")
    return item


@router.post("/{task_id}/pause")
def pause_task(task_id: str):
    if not task_queue_service.pause(task_id):
        raise HTTPException(status_code=400, detail="无法暂停")
    return {"ok": True}


@router.post("/{task_id}/resume")
def resume_task(task_id: str):
    if not task_queue_service.resume(task_id):
        raise HTTPException(status_code=400, detail="无法继续")
    return {"ok": True}


@router.post("/{task_id}/cancel")
def cancel_task(task_id: str):
    if not task_queue_service.cancel(task_id):
        raise HTTPException(status_code=400, detail="无法取消")
    return {"ok": True}
```

- [ ] **Step 3: 注册 router**

在 `backend/main.py` import 中加入：

```python
from app.api import task_routes
```

并 include：

```python
app.include_router(task_routes.router, prefix="/api", tags=["tasks"])
```

- [ ] **Step 4: 运行测试**

Run:
```bash
python -m unittest backend.tests.test_task_queue_api.TaskQueueApiTests -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/task_routes.py backend/main.py backend/tests/test_task_queue_api.py
git commit -m "feat(backend): add task queue APIs"
```

---

## Task 5: 将“深度整理/快速整理”接入队列（后端执行器）

**Files:**
- Modify: `backend/app/services/task_queue_service.py`
- Modify: `backend/app/services/memory_service.py`（如需拆分为可汇报进度的分段执行，可在计划内做最小拆分）
- Modify(兼容层): `backend/app/api/memory_routes.py`

- [ ] **Step 1: 为 deep_organize/quick_organize 注册 executor**

在 `task_queue_service.TaskQueueService.__init__` 后注册：

```python
from app.services.memory_service import memory_service


def _exec_quick(task_id: str, params: dict) -> dict:
    # 这里 quick_organize 本身已是增量逻辑
    return memory_service.quick_organize()


def _exec_deep(task_id: str, params: dict) -> dict:
    # 低功耗开关走现有 settings 开关（后续可由 params 覆盖）
    return memory_service.organize_entire_knowledge_base()


task_queue_service.register_executor("quick_organize", _exec_quick)
task_queue_service.register_executor("deep_organize", _exec_deep)
```

- [ ] **Step 2: 在执行器前后更新进度（最小可观测）**

在 executor 内用 `store.update_task_queue_item(progress/message)` 打点：

```python
task_queue_service.store.update_task_queue_item(task_id, progress=5, message="开始执行：深度整理")
...
task_queue_service.store.update_task_queue_item(task_id, progress=80, message="整理完成：收尾中")
```

- [ ] **Step 3: memory_routes 兼容层改为 enqueue**

将 `POST /api/memory/organize` 改为：
- enqueue `deep_organize`
- 返回 `{status:"started"}` 保持现有前端兼容

将 `GET /api/memory/organize/status` 改为：
- 返回最近一次 `deep_organize` 任务的运行态（running/started_at/result/error）

> 注意：第一期可只映射“最近一条 deep_organize”，不追求完美。

- [ ] **Step 4: 手工验证**

启动后端后：
```bash
curl -s http://127.0.0.1:15920/api/tasks?status=queued,running,blocked | head
curl -s -X POST http://127.0.0.1:15920/api/memory/organize
```
Expected: deep_organize 进入队列并执行/或 blocked

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/task_queue_service.py backend/app/api/memory_routes.py
git commit -m "feat(backend): run organize tasks via task queue (compat kept)"
```

---

## Task 6: 前端任务 Store + TaskPanel（最小 UI）

**Files:**
- Create: `frontend/src/renderer/stores/tasks.ts`
- Create: `frontend/src/renderer/components/TaskPanel.vue`
- Modify: `frontend/src/renderer/App.vue`
- Modify: `frontend/src/renderer/api/backend.ts`

- [ ] **Step 1: 在 api/backend.ts 增加封装**

新增：
```ts
export async function fetchCapabilities() {
  return apiRequest<any>('/api/system/capabilities')
}

export async function enqueueTask(payload: { type: string; power_mode?: string; params?: any }) {
  return apiRequest<{ id: string; status: string }>('/api/tasks/enqueue', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export async function fetchTasks(status = 'running,queued,blocked', limit = 50) {
  return apiRequest<{ items: any[] }>('/api/tasks', { params: { status, limit } as any })
}

export async function pauseTask(id: string) {
  return apiRequest('/api/tasks/' + id + '/pause', { method: 'POST' })
}
export async function resumeTask(id: string) {
  return apiRequest('/api/tasks/' + id + '/resume', { method: 'POST' })
}
export async function cancelTask(id: string) {
  return apiRequest('/api/tasks/' + id + '/cancel', { method: 'POST' })
}
```

- [ ] **Step 2: 新建 Pinia store（轮询 + 控制）**

`frontend/src/renderer/stores/tasks.ts`：

```ts
import { defineStore } from 'pinia'
import { ref } from 'vue'
import { fetchTasks, enqueueTask, pauseTask, resumeTask, cancelTask } from '../api/backend'

export const useTasksStore = defineStore('tasks', () => {
  const items = ref<any[]>([])
  const loading = ref(false)
  let timer: number | null = null

  async function refresh() {
    loading.value = true
    try {
      const data = await fetchTasks()
      items.value = data.items || []
    } finally {
      loading.value = false
    }
  }

  function startPolling(intervalMs = 1500) {
    if (timer) return
    timer = window.setInterval(refresh, intervalMs)
  }
  function stopPolling() {
    if (!timer) return
    window.clearInterval(timer)
    timer = null
  }

  async function enqueue(type: string, power_mode = 'normal', params: any = {}) {
    const res = await enqueueTask({ type, power_mode, params })
    await refresh()
    return res
  }

  async function pause(id: string) { await pauseTask(id); await refresh() }
  async function resume(id: string) { await resumeTask(id); await refresh() }
  async function cancel(id: string) { await cancelTask(id); await refresh() }

  return { items, loading, refresh, startPolling, stopPolling, enqueue, pause, resume, cancel }
})
```

- [ ] **Step 3: TaskPanel 最小 UI**

`frontend/src/renderer/components/TaskPanel.vue`（示意：不追求美观，先可用）：

```vue
<template>
  <div class="task-panel">
    <div class="task-panel-header">
      <span>任务</span>
      <button class="btn" @click="tasks.refresh" :disabled="tasks.loading">刷新</button>
    </div>
    <div v-if="tasks.items.length === 0" class="empty">暂无任务</div>
    <div v-for="t in tasks.items" :key="t.id" class="task-item">
      <div class="row">
        <div class="type">{{ t.type }}</div>
        <div class="status" :class="t.status">{{ t.status }}</div>
      </div>
      <div class="msg">{{ t.message }}</div>
      <div class="progress">
        <div class="bar" :style="{ width: (t.progress || 0) + '%' }"></div>
      </div>
      <div class="actions">
        <button class="btn" v-if="t.status==='running'" @click="tasks.pause(t.id)">暂停</button>
        <button class="btn" v-if="t.status==='paused' || t.status==='blocked'" @click="tasks.resume(t.id)">继续</button>
        <button class="btn danger" v-if="t.status!=='completed' && t.status!=='failed'" @click="tasks.cancel(t.id)">取消</button>
      </div>
      <div v-if="t.status==='blocked'" class="blocked">原因：{{ t.blocked_reason }}</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useTasksStore } from '../stores/tasks'
const tasks = useTasksStore()
</script>

<style scoped>
.task-panel{position:fixed;right:12px;bottom:12px;width:320px;max-height:50vh;overflow:auto;background:var(--color-surface);border:1px solid var(--color-border);border-radius:10px;padding:10px;z-index:50}
.task-panel-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:8px}
.task-item{border-top:1px solid var(--color-border);padding-top:8px;margin-top:8px}
.row{display:flex;justify-content:space-between;gap:8px}
.type{font-weight:600}
.status{font-size:12px;opacity:.9}
.msg{font-size:12px;color:var(--color-text-secondary);margin:6px 0}
.progress{height:6px;background:rgba(0,0,0,.08);border-radius:99px;overflow:hidden}
.bar{height:100%;background:var(--color-primary)}
.actions{display:flex;gap:8px;margin-top:8px}
.btn{font-size:12px;padding:4px 8px;border:1px solid var(--color-border);border-radius:6px;background:transparent}
.danger{border-color:var(--color-error);color:var(--color-error)}
.blocked{margin-top:6px;font-size:12px;color:var(--color-warning)}
.empty{font-size:12px;color:var(--color-text-secondary)}
</style>
```

- [ ] **Step 4: App.vue 挂载并启动轮询**

在 `App.vue` 引入并在模板底部加入 `<TaskPanel />`，并在 `onMounted` 启动 `tasks.startPolling()`：

```ts
import TaskPanel from './components/TaskPanel.vue'
import { useTasksStore } from './stores/tasks'

const tasks = useTasksStore()
onMounted(() => {
  tasks.startPolling()
})
onUnmounted(() => {
  tasks.stopPolling()
})
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/renderer/api/backend.ts frontend/src/renderer/stores/tasks.ts frontend/src/renderer/components/TaskPanel.vue frontend/src/renderer/App.vue
git commit -m "feat(frontend): add task panel and tasks store"
```

---

## Task 7: MemoryView 改为入队（并提示“需要模型/已入队”）

**Files:**
- Modify: `frontend/src/renderer/views/MemoryView.vue`

- [ ] **Step 1: 使用 tasks store 的 enqueue 替换 startOrganize/startQuickOrganize**

在 MemoryView 内引入：

```ts
import { useTasksStore } from '../stores/tasks'
import { fetchCapabilities } from '../api/backend'
```

并在 `organizeMemories/quickOrganizeMemories` 改为：

```ts
const tasksStore = useTasksStore()

async function organizeMemories() {
  toast.info('已加入后台任务队列：深度整理')
  const caps = await fetchCapabilities().catch(() => null)
  const res = await tasksStore.enqueue('deep_organize', 'normal', {})
  if (res.status === 'blocked') {
    toast.info('需要模型：请先启动/安装 Ollama 并下载模型（任务已进入队列）')
  }
}

async function quickOrganizeMemories() {
  toast.info('已加入后台任务队列：快速整理')
  const res = await tasksStore.enqueue('quick_organize', 'normal', {})
  if (res.status === 'blocked') {
    toast.info('需要模型：请先启动/安装 Ollama 并下载模型（任务已进入队列）')
  }
}
```

> 注：`caps` 可用于未来细化 allowed，但第一期以“可点、入队、blocked 提示”优先达标。

- [ ] **Step 2: Commit**

```bash
git add frontend/src/renderer/views/MemoryView.vue
git commit -m "feat(frontend): enqueue organize tasks instead of blocking flow"
```

---

## Task 8: 构建与回归验证

**Files:**
- N/A（执行验证）

- [ ] **Step 1: 后端单测**

Run:
```bash
python -m unittest discover -s backend/tests -v
```
Expected: PASS

- [ ] **Step 2: 前端构建**

Run:
```bash
cd frontend
npm run build
npm run electron:build-main
```
Expected: PASS

- [ ] **Step 3: 场景自测（验收路径）**

1) 关闭/不安装 Ollama → 启动 App → 浏览/检索/知识库/导出正常  
2) 点击深度整理/快速整理 → 任务出现在 TaskPanel  
3) 深度整理若 blocked → 显示 blocked_reason 并给提示  
4) 打开 Ollama + 下载模型 → 点击继续 → 任务转 queued/running 并完成  

- [ ] **Step 4: 更新版本优化记录（按项目规则）**

在 `版本优化记录/版本优化0.9.md` 顶部追加本次实现的记录块（任务类型/简述/文件列表/状态）。

- [ ] **Step 5: Commit**

```bash
git add 版本优化记录/版本优化0.9.md
git commit -m "docs: update v0.9 optimization log for task queue implementation"
```

---

## Plan 自检（覆盖 spec）

- 能力状态 API：Task 2 ✅
- SQLite 持久化队列：Task 1 ✅
- 单 worker + blocked/paused：Task 3 ✅
- 队列 API：Task 4 ✅
- 整理任务入队 & 兼容层：Task 5 ✅
- 前端任务面板与不阻塞交互：Task 6/7 ✅
- 低功耗节流：Task 3（adaptive_sleep）+ Task 5（沿用现有 low power 逻辑）✅

