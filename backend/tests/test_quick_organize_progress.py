from __future__ import annotations


def test_quick_organize_reports_progress(monkeypatch):
    """
    回归：快速整理的进度应随着阶段/批次推进而更新，而不是只在开始/结束时跳变。

    该用例不跑真实整理逻辑（避免依赖模型/向量库），通过 monkeypatch 注入“可控的阶段批次”，
    验证 quick_organize 会：
    1) 接受 progress_callback 参数
    2) 在执行过程中多次调用 callback（包含中间进度）
    3) 进度整体单调不减，且能到达 95% 附近的“收尾”阶段
    """
    from app.services.memory_service import memory_service

    progress_calls: list[int] = []

    def progress_callback(p: int, _msg: str = ""):
        progress_calls.append(int(p))

    # ---- 注入可控的“阶段批次推进” ----
    def fake_l1_to_l2(*, max_batches=None, progress_hook=None):
        assert callable(progress_hook)
        for i in range(5):
            progress_hook(i + 1, 5)
        return {"processed": 10, "total": 10, "batches": 5}

    def fake_l2_to_l4(*, max_batches=None, progress_hook=None):
        assert callable(progress_hook)
        for i in range(4):
            progress_hook(i + 1, 4)
        return {"processed": 8, "total": 8, "batches": 4}

    def fake_l4_to_l3(*, progress_hook=None):
        assert callable(progress_hook)
        for i in range(3):
            progress_hook(i + 1, 3)
        return {"created": 1, "updated": 2}

    def fake_l4_to_l6(*, max_batches=None, progress_hook=None):
        assert callable(progress_hook)
        for i in range(6):
            progress_hook(i + 1, 6)
        return {"processed": 6, "total": 6, "batches": 6}

    def fake_l6_to_l5(*, progress_hook=None):
        assert callable(progress_hook)
        for i in range(2):
            progress_hook(i + 1, 2)
        return {"created": 1, "updated": 1}

    monkeypatch.setattr(memory_service, "_batch_process_l1_to_l2_smart", fake_l1_to_l2, raising=True)
    monkeypatch.setattr(memory_service, "_batch_process_l2_to_l4_smart", fake_l2_to_l4, raising=True)
    monkeypatch.setattr(memory_service, "process_l4_to_l3", fake_l4_to_l3, raising=True)
    monkeypatch.setattr(memory_service, "_batch_process_l4_to_l6_smart", fake_l4_to_l6, raising=True)
    monkeypatch.setattr(memory_service, "process_l6_to_l5", fake_l6_to_l5, raising=True)

    memory_service.quick_organize(progress_callback=progress_callback)

    assert len(progress_calls) >= 5, "应产生多次进度更新"
    assert progress_calls == sorted(progress_calls), "进度应单调不减"
    assert any(10 < p < 90 for p in progress_calls), "应包含中间进度（非仅开始/结束）"
    assert max(progress_calls) >= 95, "应进入收尾阶段（>=95%）"

