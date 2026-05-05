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


class TaskQueueServiceTests(unittest.TestCase):
    def test_requires_model_blocks_when_model_not_ready(self):
        from unittest.mock import patch
        from app.services.task_queue_service import task_queue_service

        with patch("app.services.task_queue_service._is_model_ready", return_value=False):
            task_id = task_queue_service.enqueue("extract_skills", requires_model=True)
            item = task_queue_service.store.get_task_queue_item(task_id)
            self.assertEqual(item["status"], "blocked")
            self.assertEqual(item["blocked_reason"], "MODEL_NOT_READY")


class TaskQueueApiTests(unittest.TestCase):
    def test_enqueue_and_list_tasks(self):
        from unittest.mock import patch
        from app.api import task_routes

        with patch("app.services.task_queue_service._is_model_ready", return_value=False):
            resp = task_routes.enqueue_task(task_routes.EnqueueTaskRequest(
                type="deep_organize",
                power_mode="normal",
                params={"force": False},
            ))
            task_id = resp["id"]
            self.assertIn(resp["status"], ("queued", "blocked"))

            listed = task_routes.list_tasks(status="queued,running,blocked", limit=50)
            ids = [t["id"] for t in listed.get("items", [])]
            self.assertIn(task_id, ids)


if __name__ == "__main__":
    unittest.main()
