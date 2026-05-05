import unittest
from unittest.mock import patch, MagicMock


class MemoryDedupMergeSupersedeTests(unittest.TestCase):
    def _build_service(self):
        from app.services.memory_service import MemoryService

        service = MemoryService.__new__(MemoryService)
        service.beijing_tz = None
        service.store = MagicMock()
        service.vector_store = MagicMock()
        return service

    def test_merge_on_high_similarity_updates_existing_and_logs_audit(self):
        service = self._build_service()

        existing = {
            "id": "old-1",
            "content": "旧内容",
            "category": "分类",
            "layer": 4,
            "status": "active",
            "processed_status": "processed",
        }

        service.store.get_by_id.return_value = existing
        service.store.update.return_value = {**existing, "content": "旧内容\n\n新增"}

        # 冲突命中：高相似 -> merge
        service._check_conflicts = MagicMock(return_value=[{**existing, "conflict_score": 0.95}])

        with patch("app.services.memory_service.embedding_service") as embedding_mock, patch(
            "app.services.memory_service.settings"
        ) as settings_mock:
            settings_mock.max_content_length = 999999
            settings_mock.max_tags = 99
            settings_mock.dedup_threshold = 0.9
            settings_mock.conflict_threshold = 0.75
            settings_mock.memory_type_default = "episodic"

            embedding_mock.embed_text.return_value = [0.1, 0.2]
            embedding_mock.persist.return_value = None

            result = service.create_memory(
                content="新增",
                category="分类",
                tags=[],
                source="test",
                confidence=1.0,
                ttl=None,
                is_pinned=False,
                metadata={},
                layer=4,
                level=1,
            )

        self.assertEqual(result.get("action"), "merged")
        self.assertEqual(result.get("id"), "old-1")
        service.store.create.assert_not_called()
        service.store.invalidate_memory.assert_not_called()
        self.assertTrue(service.store.add_audit_log.called)

    def test_supersede_on_lower_similarity_creates_new_invalidates_old_and_links_versions(self):
        service = self._build_service()

        existing = {
            "id": "old-1",
            "content": "旧事实：A=1",
            "category": "分类",
            "layer": 4,
            "status": "active",
            "processed_status": "processed",
        }

        service.store.get_by_id.return_value = existing
        service._check_conflicts = MagicMock(return_value=[{**existing, "conflict_score": 0.8}])

        # new record returned by store.create
        service.store.create.return_value = {
            "id": "new-1",
            "content": "更正：A=2",
            "category": "分类",
            "layer": 4,
            "status": "active",
            "parent_id": "old-1",
        }

        with patch("app.services.memory_service.embedding_service") as embedding_mock, patch(
            "app.services.memory_service.settings"
        ) as settings_mock, patch("app.services.memory_service.uuid.uuid4") as uuid_mock:
            settings_mock.max_content_length = 999999
            settings_mock.max_tags = 99
            settings_mock.dedup_threshold = 0.9
            settings_mock.conflict_threshold = 0.75
            settings_mock.memory_type_default = "episodic"

            uuid_mock.return_value = "new-1"
            embedding_mock.embed_text.return_value = [0.1, 0.2]
            embedding_mock.persist.return_value = None

            result = service.create_memory(
                content="更正：A=2",
                category="分类",
                tags=[],
                source="test",
                confidence=1.0,
                ttl=None,
                is_pinned=False,
                metadata={},
                layer=4,
                level=1,
            )

        self.assertEqual(result.get("action"), "superseded")
        self.assertEqual(result.get("id"), "new-1")
        service.store.invalidate_memory.assert_called_once()

        # 确保新版本记录带 parent_id
        create_kwargs = service.store.create.call_args.kwargs
        self.assertEqual(create_kwargs.get("parent_id"), "old-1")


if __name__ == "__main__":
    unittest.main()

