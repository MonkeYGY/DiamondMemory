import json
import unittest
from unittest.mock import MagicMock, patch


class SkillProductizationTests(unittest.TestCase):
    def _build_service(self, now_str: str = "2026-04-29 12:00:00"):
        from app.services.skill_service import SkillService

        store = MagicMock()
        service = SkillService(store=store)
        service._now_str = MagicMock(return_value=now_str)  # 固定时间，便于断言
        return service, store

    def test_record_invocation_updates_metrics(self):
        service, store = self._build_service()

        store.get_by_id.return_value = {
            "id": "m1",
            "layer": 6,
            "status": "active",
            "content": "技能名称：示例技能\n\n触发条件：\n- 用户说“做X”",
            "category": "测试",
            "metadata": {"skill_id": "s1", "version": 1},
        }

        service.record_invocation("m1")

        # store.update(metadata=...) 被调用，且 metrics.invoke_count 递增
        update_kwargs = store.update.call_args.kwargs
        self.assertEqual(update_kwargs["memory_id"], "m1")
        meta = json.loads(update_kwargs["metadata"])
        self.assertEqual(meta["skill_id"], "s1")
        self.assertEqual(meta["version"], 1)
        self.assertEqual(meta["metrics"]["invoke_count"], 1)
        self.assertEqual(meta["metrics"]["last_invoked_at"], "2026-04-29 12:00:00")

    def test_negative_feedback_triggers_auto_upgrade_creates_new_version_and_keeps_history(self):
        service, store = self._build_service()

        # 旧版本（已达到调用阈值）
        store.get_by_id.return_value = {
            "id": "m1",
            "layer": 6,
            "status": "active",
            "content": "技能名称：示例技能\n\n目标任务：完成X\n\n触发条件：\n- 条件A\n\n包含步骤/子技能：\n1. 第一步\n\n涉及工具：\n- 工具A",
            "category": "测试",
            "tags": [],
            "source": "test",
            "confidence": 1.0,
            "metadata": {
                "skill_id": "s1",
                "version": 1,
                "source_memory_ids": ["l4-1"],
                "metrics": {"invoke_count": 3, "negative_feedback_count": 0},
            },
        }

        # 不存在未完成任务，允许触发
        store.get_pending_skill_upgrade_task.return_value = None

        # 新版本写入后返回
        store.create.return_value = {"id": "m2"}

        service.submit_feedback("m1", rating=1, comment="不好用")

        # 1) 创建升级任务
        store.create_skill_upgrade_task.assert_called_once()

        # 2) 自动生成 v+1（创建新 L6 版本）
        create_kwargs = store.create.call_args.kwargs
        self.assertEqual(create_kwargs["layer"], 6)
        meta = create_kwargs["metadata"]
        self.assertEqual(meta["skill_id"], "s1")
        self.assertEqual(meta["version"], 2)
        self.assertEqual(meta["source_memory_ids"], ["l4-1"])
        self.assertEqual(create_kwargs["parent_id"], "m1")

        # 3) 旧版本被标记为 superseded（可通过版本链查询历史）
        store.invalidate_memory.assert_called_once_with("m1", "m2")


if __name__ == "__main__":
    unittest.main()

