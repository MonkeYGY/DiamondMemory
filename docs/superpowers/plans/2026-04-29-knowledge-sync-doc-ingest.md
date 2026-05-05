# ID=19（P1）一键同步入库（PDF/Word/Excel）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用户将 PDF/Word/Excel 拖入存储路径的 `用户文档/` 后，点击“同步知识库”即可异步入库（DB + 向量库），并在同步完成后刷新知识库树；同步过程不阻塞 UI（走任务队列）。

**Architecture:** 在后端把 `POST /api/knowledge/sync` 改为“入队 knowledge_sync 任务并立即返回 task_id”；任务执行器扫描 `用户文档/` 目录，基于 `file_sync` 做增量判定，对新增/变更文档调用 `IngestService.ingest_file()` 摄取入库；前端在 Settings 页增加按钮触发该接口，并利用现有任务面板展示进度；任务完成后调用 `syncKnowledgeTree(rebuildKnowledgeMemoryExports)` 强制刷新。

**Tech Stack:** Electron + Vue3 + TypeScript；FastAPI；SQLite（含 file_sync/task_queue）；现有 IngestService 文档入库双管道；现有 TaskQueueService 单 worker。

---

## 0) 变更文件清单（先锁定边界）

**后端**
- Modify: `backend/app/api/knowledge_routes.py`（/sync 改为入队并返回 task_id）
- Modify: `backend/app/services/task_queue_service.py`（注册执行器 knowledge_sync）
- Modify: `backend/app/services/knowledge_service.py`（抽出“同步入库文档”的可复用逻辑，或新增 helper）
- Modify (optional): `backend/app/services/ingest/ingest_service.py`（如需把 source_path/source_hash 写入 metadata 便于按文件去重/追踪）
- Test: `backend/tests/test_knowledge_sync_doc_ingest.py`（新增）

**前端**
- Modify: `frontend/src/renderer/views/SettingsView.vue`（增加“同步知识库”按钮；入队/提示/完成后刷新）
- Modify: `frontend/src/renderer/api/backend.ts`（新增 `syncKnowledgeBase()` API 封装）
- (Optional) Modify: `frontend/src/renderer/stores/tasks.ts`（如需在 enqueue 后强制打开面板/或更及时刷新）

---

## Task 1: 后端——为“知识库同步”增加任务化入口

**Files:**
- Modify: `backend/app/api/knowledge_routes.py`
- Modify: `backend/app/services/task_queue_service.py`

- [ ] **Step 1: 在 task_queue 注册执行器骨架（先不做真实逻辑）**

在 `backend/app/services/task_queue_service.py` 的“内置任务执行器注册”区域中，新增：
```py
def _exec_knowledge_sync(task_id: str, params: Dict[str, Any]) -> Dict[str, Any]:
    task_queue_service.store.update_task_queue_item(task_id, progress=5, message="开始执行：知识库同步")
    # 先返回一个占位结果（下一 Task 会补全）
    task_queue_service.store.update_task_queue_item(task_id, progress=95, message="知识库同步完成：收尾中")
    return {"ok": True, "scanned": 0, "ingested": 0, "skipped": 0, "failed": 0, "errors": []}

task_queue_service.register_executor("knowledge_sync", _exec_knowledge_sync)
```

- [ ] **Step 2: 改造 `POST /api/knowledge/sync`：入队并返回 task_id**

在 `backend/app/api/knowledge_routes.py`，将当前同步执行：
```py
result = knowledge_service.sync_knowledge_base()
return result
```
改为：
```py
from app.services.task_queue_service import task_queue_service

@router.post("/sync")
def sync_knowledge_base():
    task_id = task_queue_service.enqueue(
        "knowledge_sync",
        requires_model=False,
        power_mode="normal",
        params={},
    )
    item = task_queue_service.store.get_task_queue_item(task_id) or {}
    return {"id": task_id, "status": item.get("status", "queued")}
```

- [ ] **Step 3: 本地运行后端单测冒烟（先确保能 import + 启动）**

Run:
```bash
pytest -q backend/tests/test_startup_status_api.py -q
```
Expected: PASS（至少确保本次改动不破坏启动链路）

- [ ] **Step 4: Commit**

```bash
git add backend/app/api/knowledge_routes.py backend/app/services/task_queue_service.py
git commit -m "feat(knowledge): enqueue knowledge sync task"
```

---

## Task 2: 后端——实现 knowledge_sync 执行器：扫描“用户文档/”并摄取 PDF/Word/Excel

**Files:**
- Modify: `backend/app/services/task_queue_service.py`
- Modify: `backend/app/services/knowledge_service.py`

- [ ] **Step 1: 在 KnowledgeService 中新增“仅同步用户文档”的 helper（不碰旧 md 同步）**

在 `backend/app/services/knowledge_service.py` 中新增方法（建议放在 `sync_knowledge_base()` 附近）：
```py
def sync_user_docs(self, *, only_folder: str = "用户文档") -> Dict[str, Any]:
    import hashlib
    from app.services.ingest.ingest_service import ingest_service

    base_path = self.get_knowledge_base_path()
    target_root = os.path.join(base_path, only_folder)
    os.makedirs(target_root, exist_ok=True)

    exts = {".pdf", ".doc", ".docx", ".xls", ".xlsx"}
    skipped = ingested = failed = scanned = 0
    errors: List[str] = []

    for root, dirs, files in os.walk(target_root):
        dirs[:] = [d for d in dirs if not d.startswith(".") and d not in self.HIDDEN_ITEMS]

        # 防止 ingest 自摄取：跳过 raw/processed
        rel_root = os.path.relpath(root, base_path).replace("\\", "/")
        if rel_root.startswith("raw/") or rel_root.startswith("processed/"):
            continue

        for name in files:
            scanned += 1
            if name.startswith("."):
                skipped += 1
                continue
            ext = os.path.splitext(name)[1].lower()
            if ext not in exts:
                skipped += 1
                continue

            full_path = os.path.join(root, name)
            relative_path = os.path.relpath(full_path, base_path)
            try:
                st = os.stat(full_path)
                mtime = st.st_mtime
                sync_info = self.store.get_file_sync_info(relative_path)
                if sync_info and abs(sync_info["last_modified"] - mtime) < 1.0:
                    skipped += 1
                    continue

                # 计算 hash（先 md5，满足最小可行；未来可切 sha256）
                with open(full_path, "rb") as f:
                    file_hash = hashlib.md5(f.read()).hexdigest()
                if sync_info and sync_info.get("file_hash") == file_hash:
                    self.store.update_file_sync_info(relative_path, mtime, file_hash)
                    skipped += 1
                    continue

                # 摄取入库
                ingest_service.ingest_file(full_path, disturb_free=True)
                self.store.update_file_sync_info(relative_path, mtime, file_hash)
                ingested += 1
            except Exception as e:
                failed += 1
                errors.append(f"{relative_path}: {e}")

    return {"ok": True, "scanned": scanned, "ingested": ingested, "skipped": skipped, "failed": failed, "errors": errors}
```

说明：
- disturb_free=True：避免结构化提炼（更快、更稳），符合“一键同步最小可用”
- 仅扫描 `用户文档/`：避免扫到系统目录，也避免 ingest 写入 `raw/` 导致自摄取

- [ ] **Step 2: 将 task 执行器改为调用 sync_user_docs，并写入 progress/message**

在 `backend/app/services/task_queue_service.py` 中将 `_exec_knowledge_sync` 改为：
```py
from app.services.knowledge_service import knowledge_service

def _exec_knowledge_sync(task_id: str, params: Dict[str, Any]) -> Dict[str, Any]:
    task_queue_service.store.update_task_queue_item(task_id, progress=5, message="开始执行：扫描用户文档")
    result = knowledge_service.sync_user_docs(only_folder="用户文档")
    task_queue_service.store.update_task_queue_item(task_id, progress=95, message="同步完成：收尾中")
    return result or {"ok": True}
```

- [ ] **Step 3: 增加后端单测（mock ingest_service）**

Create: `backend/tests/test_knowledge_sync_doc_ingest.py`

测试要点：
- 构造临时 storage_path 目录结构：`用户文档/a.pdf`
- monkeypatch `settings.storage_path` 指向临时目录（或调用 update_storage_path）
- monkeypatch `ingest_service.ingest_file` 为计数器函数（避免真实解析依赖）
- 首次 sync：应 ingest 1 次
- 二次 sync（不变）：应 ingest 0 次
- 修改 mtime+内容：应 ingest 1 次

示例测试代码（可直接用）：
```py
import os
import time
from pathlib import Path
from unittest.mock import patch

from app.config import settings
from app.config.settings import update_storage_path
from app.services.knowledge_service import knowledge_service


def test_sync_user_docs_ingests_only_on_change(tmp_path: Path, monkeypatch):
    update_storage_path(str(tmp_path))

    user_docs = tmp_path / "用户文档"
    user_docs.mkdir(parents=True, exist_ok=True)
    f = user_docs / "a.pdf"
    f.write_bytes(b"%PDF-1.4 fake")

    calls = {"n": 0}

    def _fake_ingest(path: str, disturb_free: bool = False, progress_callback=None):
        assert os.path.exists(path)
        calls["n"] += 1
        return {"success": True}

    from app.services.ingest import ingest_service as ingest_module
    monkeypatch.setattr(ingest_module.ingest_service, "ingest_file", _fake_ingest)

    r1 = knowledge_service.sync_user_docs()
    assert r1["ingested"] == 1
    assert calls["n"] == 1

    r2 = knowledge_service.sync_user_docs()
    assert r2["ingested"] == 0
    assert calls["n"] == 1

    time.sleep(1.1)
    f.write_bytes(b"%PDF-1.4 fake changed")
    r3 = knowledge_service.sync_user_docs()
    assert r3["ingested"] == 1
    assert calls["n"] == 2
```

- [ ] **Step 4: Run test**

Run:
```bash
pytest -q backend/tests/test_knowledge_sync_doc_ingest.py -q
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/knowledge_service.py backend/app/services/task_queue_service.py backend/tests/test_knowledge_sync_doc_ingest.py
git commit -m "feat(knowledge): sync user docs to ingest pdf/office files"
```

---

## Task 3: 前端——Settings 增加“一键同步”按钮并接入任务面板

**Files:**
- Modify: `frontend/src/renderer/api/backend.ts`
- Modify: `frontend/src/renderer/views/SettingsView.vue`

- [ ] **Step 1: 在前端 API 封装新增 `syncKnowledgeBase()`**

在 `frontend/src/renderer/api/backend.ts` 添加：
```ts
export async function syncKnowledgeBase(): Promise<{ id: string; status: string }> {
  return apiRequest('/api/knowledge/sync', { method: 'POST' })
}
```

- [ ] **Step 2: SettingsView 增加按钮与点击逻辑（toast + 刷新）**

在 `frontend/src/renderer/views/SettingsView.vue` 的“数据管理”区域（存储路径按钮附近）增加按钮：
- 文案：`🔄 同步知识库（扫描并入库）`
- 点击行为：
  1) 调用 `syncKnowledgeBase()`
  2) `tasks.refresh()` + `tasks.startPolling()`（确保面板能看到）
  3) toast：已加入队列
  4) 启动一个轻量轮询 `fetch('/api/tasks/{id}')`（用 `apiRequest`）直到 completed/failed
  5) completed 时调用：
     - `syncKnowledgeTree(rebuildKnowledgeMemoryExports)`

示例实现（可直接套用到 `<script setup>`）：
```ts
import { useTasksStore } from '../stores/tasks'
import { syncKnowledgeBase, apiRequest, rebuildKnowledgeMemoryExports } from '../api/backend'
import { syncKnowledgeTree } from '../utils/knowledge-tree-events'

const tasks = useTasksStore()
const syncingKnowledge = ref(false)

async function handleSyncKnowledgeBase() {
  if (syncingKnowledge.value) return
  syncingKnowledge.value = true
  try {
    const { id } = await syncKnowledgeBase()
    toast.success('已加入任务队列：知识库同步')
    await tasks.refresh()
    tasks.startPolling()

    // 轮询直到任务结束（最多 10 分钟）
    const deadline = Date.now() + 10 * 60 * 1000
    while (Date.now() < deadline) {
      const t: any = await apiRequest(`/api/tasks/${id}`)
      if (t.status === 'completed') break
      if (t.status === 'failed' || t.status === 'cancelled') throw new Error(t.error || t.message || '同步失败')
      await new Promise(r => setTimeout(r, 800))
    }

    await syncKnowledgeTree(rebuildKnowledgeMemoryExports)
    toast.success('知识库同步完成')
  } catch (e: any) {
    toast.error('知识库同步失败：' + (e?.message || 'unknown'))
  } finally {
    syncingKnowledge.value = false
  }
}
```

- [ ] **Step 3: 前端 TypeScript 构建检查**

Run:
```bash
npm -C frontend run build
```
Expected: build 成功

- [ ] **Step 4: Commit**

```bash
git add frontend/src/renderer/api/backend.ts frontend/src/renderer/views/SettingsView.vue
git commit -m "feat(ui): add knowledge sync button (enqueue backend task)"
```

---

## Task 4: 端到端冒烟与回归

**Files:**
- (no code changes required)

- [ ] **Step 1: 后端全量单测（至少覆盖新增用例）**

Run:
```bash
pytest -q
```
Expected: PASS（允许已有 skip）

- [ ] **Step 2: 手工冒烟步骤（验收脚本）**
1. 在存储路径下创建/拖入：`用户文档/test.pdf`
2. 打开 Settings → 点击 `🔄 同步知识库（扫描并入库）`
3. 观察任务面板出现 `knowledge_sync` 且进度推进
4. 完成后在检索中验证能命中（或在 DB 里看到新增 doc/doc_chunk）

- [ ] **Step 3: 更新版本优化记录（ID=19）**

修改：`版本优化记录/版本优化0.9.1.md`
- Backlog 表：ID=19 状态从 `🚧 进行中` → `✅ 已完成`
- 在“任务记录”顶部追加本次实现记录（时间倒序），包含：
  - 任务类型：修复/优化/测试
  - 任务简述：一键同步按钮 + 后端任务化同步 + 文档入库支持 + 单测
  - 修改文件列表（本计划涉及的文件）
  - 完成状态：✅ 已完成（注明 pytest / npm build）

- [ ] **Step 4: Commit**

```bash
git add "版本优化记录/版本优化0.9.1.md"
git commit -m "chore: close ID-19 in release notes"
```

---

## 自检（针对 spec 覆盖）

- 覆盖 “按钮触发 /api/knowledge/sync” ✅（Task 3）
- 覆盖 “不阻塞 UI，走任务队列” ✅（Task 1 + Task 2）
- 覆盖 “同步范围 PDF/Word/Excel” ✅（Task 2）
- 覆盖 “完成后强制刷新 FileTree + rebuild-memory-exports” ✅（Task 3，调用 syncKnowledgeTree）
- 覆盖 “增量去重” ✅（Task 2，复用 file_sync）

