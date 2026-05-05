from app.api import knowledge_routes


def test_knowledge_sync_endpoint_enqueues_task(monkeypatch):
    """
    /api/knowledge/sync 最小验收：接口应入队一个 knowledge_sync 任务并返回 task_id/status，
    而不是在接口里同步执行完整扫描。
    """
    calls = {"enqueued": 0}

    def _fake_enqueue(task_type: str, requires_model: bool = False, power_mode: str = "normal", params=None):
        assert task_type == "knowledge_sync"
        assert requires_model is False
        calls["enqueued"] += 1
        return "task-123"

    class _FakeStore:
        def get_task_queue_item(self, task_id: str):
            assert task_id == "task-123"
            return {"id": task_id, "status": "queued"}

    class _FakeTaskQueueService:
        store = _FakeStore()

        def enqueue(self, task_type: str, requires_model: bool = False, power_mode: str = "normal", params=None):
            return _fake_enqueue(task_type, requires_model=requires_model, power_mode=power_mode, params=params)

    # 当前实现还未引入 task_queue_service（本测试先作为 RED，后续实现会补齐）
    # 这里用 raising=False 允许先打桩一个属性，确保用例表达目标行为。
    monkeypatch.setattr(
        knowledge_routes,
        "task_queue_service",
        _FakeTaskQueueService(),
        raising=False,
    )

    resp = knowledge_routes.sync_knowledge_base()
    assert resp["id"] == "task-123"
    assert resp["status"] == "queued"
    assert calls["enqueued"] == 1
