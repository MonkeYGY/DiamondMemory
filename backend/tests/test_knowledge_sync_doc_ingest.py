import os
import time
from pathlib import Path

from app.config import settings
from app.services.knowledge_service import knowledge_service
from app.services.task_queue_service import task_queue_service


def test_sync_user_docs_ingests_only_on_change(tmp_path: Path, monkeypatch):
    """
    最小可行：同步仅扫描 storage_path/用户文档 下的文档（pdf/doc/docx/xls/xlsx），
    并基于 file_sync（mtime+hash）做增量判定：未变化不重复 ingest。
    """
    # 避免污染全局（update_storage_path 会写配置/触发全局 store 绑定）。
    # 这里仅对本用例临时 patch storage_path。
    monkeypatch.setattr(settings, "storage_path", str(tmp_path), raising=False)

    user_docs = tmp_path / "用户文档"
    user_docs.mkdir(parents=True, exist_ok=True)
    f = user_docs / "a.pdf"
    f.write_bytes(b"%PDF-1.4 fake")

    # fake store：避免污染真实 sqlite
    file_sync = {}

    class _FakeStore:
        def get_file_sync_info(self, file_path: str):
            return file_sync.get(file_path)

        def update_file_sync_info(self, file_path: str, last_modified: float, file_hash: str, status: str = "synced"):
            file_sync[file_path] = {
                "file_path": file_path,
                "last_modified": last_modified,
                "file_hash": file_hash,
                "status": status,
            }

    monkeypatch.setattr(knowledge_service, "store", _FakeStore(), raising=False)

    calls = {"n": 0}

    def _fake_ingest(path: str, disturb_free: bool = False, progress_callback=None):
        assert os.path.exists(path)
        assert disturb_free is True
        calls["n"] += 1
        return {"success": True}

    # 注：sync_user_docs 会在函数内部 import ingest_service，这里直接 patch 实例方法
    from app.services.ingest.ingest_service import ingest_service as ingest_svc

    monkeypatch.setattr(ingest_svc, "ingest_file", _fake_ingest, raising=True)

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


def test_knowledge_sync_executor_calls_sync_user_docs(monkeypatch):
    """
    task_queue 执行器必须调用 knowledge_service.sync_user_docs（而不是旧的 sync_knowledge_base），
    并将其结果作为 task result 返回。
    """
    # 取出已注册执行器
    exec_fn = task_queue_service._executors.get("knowledge_sync")
    assert exec_fn is not None

    expected = {"ok": True, "scanned": 1, "ingested": 1, "skipped": 0, "failed": 0, "errors": []}

    def _fake_sync_user_docs(*, only_folder: str = "用户文档"):
        assert only_folder == "用户文档"
        return expected

    monkeypatch.setattr(knowledge_service, "sync_user_docs", _fake_sync_user_docs, raising=False)

    # 避免真实写 sqlite：stub update_task_queue_item
    updates = []

    def _fake_update_task_queue_item(task_id: str, **kwargs):
        updates.append((task_id, kwargs))
        return True

    monkeypatch.setattr(task_queue_service.store, "update_task_queue_item", _fake_update_task_queue_item, raising=True)

    result = exec_fn("task-1", {})
    assert result == expected
    assert any(k.get("progress") == 5 for _, k in updates)
    assert any(k.get("progress") == 95 for _, k in updates)
