import unittest
from unittest.mock import Mock, patch

from app.services.memory_service import MemoryService
import app.services.memory_service as memory_service_module


class DeleteCategoryFallbackTests(unittest.TestCase):
    def test_delete_l3_category_moves_children_to_unarchived_default(self):
        service = MemoryService.__new__(MemoryService)
        service.store = Mock()
        service.vector_store = Mock()

        service.store.get_category_by_id.return_value = {
            "id": "cat-l3",
            "name": "旧分类",
            "layer": 3,
        }
        service.store.get_categories_by_layer.return_value = []
        service.store.create_category.return_value = {
            "id": "default-l3",
            "name": "未归档",
            "layer": 3,
        }
        service.store.delete_category.return_value = True
        service._move_child_memories_to_fallback = Mock()

        result = service.delete_managed_category("cat-l3")

        self.assertEqual(result["message"], "分类删除成功")
        service.store.create_category.assert_called_once()
        service._move_child_memories_to_fallback.assert_called_once_with(
            "旧分类",
            4,
            "未归档",
            "L3分类被删除，移入未归档",
        )
        service.store.delete_category.assert_called_once_with("cat-l3")

    def test_delete_default_category_is_rejected(self):
        service = MemoryService.__new__(MemoryService)
        service.store = Mock()
        service.vector_store = Mock()

        service.store.get_category_by_id.return_value = {
            "id": "default-l3",
            "name": "未归档",
            "layer": 3,
        }

        result = service.delete_managed_category("default-l3")

        self.assertEqual(result["error"], "PROTECTED_CATEGORY")
        self.assertEqual(result["message"], "默认分类不可删除")
        service.store.delete_category.assert_not_called()

    def test_delete_l3_memory_moves_children_using_existing_content(self):
        service = MemoryService.__new__(MemoryService)
        service.store = Mock()
        service.vector_store = Mock()

        service.store.get_by_id.side_effect = [
            {
                "id": "l3-memory",
                "layer": 3,
                "category": "旧分类",
                "is_pinned": False,
            },
            {
                "id": "default-l3-memory",
                "layer": 3,
                "category": "未归档",
                "content": "未归档",
            },
            {
                "id": "child-l4",
                "layer": 4,
                "category": "未归档",
                "content": "原有经验内容",
            },
        ]
        service.store.get_by_layer.return_value = [
            {
                "id": "child-l4",
                "layer": 4,
                "category": "旧分类",
                "content": "原有经验内容",
            }
        ]
        service.store.get_categories_by_layer.return_value = []
        service.store.create = Mock(
            return_value={
                "id": "default-l3-memory",
                "layer": 3,
                "category": "未归档",
                "content": "未归档",
            }
        )
        service.store.update = Mock(
            side_effect=lambda memory_id, content, category=None, reason="": {
                "id": memory_id,
                "content": content,
                "category": category,
                "reason": reason,
            }
        )
        service.store.delete.return_value = True
        service.vector_store.get_metadata.return_value = {}
        service.vector_store.get_embedding.return_value = None

        with patch.object(memory_service_module.embedding_service, "remove_from_corpus"), \
             patch.object(memory_service_module.embedding_service, "persist"), \
             patch.object(memory_service_module.embedding_service, "embed_text", return_value=[0.1, 0.2]), \
             patch("app.services.md_export_service.md_export_service.export_memory_to_md"), \
             patch("app.services.md_export_service.md_export_service.delete_memory_file"):
            result = service.delete_memory("l3-memory")

        self.assertTrue(result)
        service.store.update.assert_called_once_with(
            "child-l4",
            "原有经验内容",
            category="未归档",
            reason="L3分类被删除，移入未归档",
        )

    def test_delete_l3_memory_creates_default_l3_memory_when_missing(self):
        service = MemoryService.__new__(MemoryService)
        service.store = Mock()
        service.vector_store = Mock()

        service.store.get_by_id.side_effect = [
            {
                "id": "l3-memory",
                "layer": 3,
                "category": "旧分类",
                "is_pinned": False,
            },
            {
                "id": "child-l4",
                "layer": 4,
                "category": "未归档",
                "content": "原有经验内容",
            },
            {
                "id": "default-l3-memory",
                "layer": 3,
                "category": "未归档",
                "content": "未归档",
            },
        ]
        service.store.get_by_layer.side_effect = [
            [
                {
                    "id": "child-l4",
                    "layer": 4,
                    "category": "旧分类",
                    "content": "原有经验内容",
                    "source": "batch_sync",
                }
            ],
            [],
        ]
        service.store.get_categories_by_layer.return_value = []
        service.store.update = Mock(
            side_effect=lambda memory_id, content, category=None, reason="": {
                "id": memory_id,
                "content": content,
                "category": category,
                "reason": reason,
            }
        )
        service.store.create = Mock(
            return_value={
                "id": "default-l3-memory",
                "layer": 3,
                "category": "未归档",
                "content": "未归档",
            }
        )
        service.store.delete.return_value = True
        service.vector_store.get_metadata.return_value = {}
        service.vector_store.get_embedding.return_value = None

        with patch.object(memory_service_module.embedding_service, "remove_from_corpus"), \
             patch.object(memory_service_module.embedding_service, "persist"), \
             patch.object(memory_service_module.embedding_service, "embed_text", return_value=[0.1, 0.2]), \
             patch("app.services.md_export_service.md_export_service.export_memory_to_md"), \
             patch("app.services.md_export_service.md_export_service.delete_memory_file"):
            result = service.delete_memory("l3-memory")

        self.assertTrue(result)
        service.store.create.assert_called_once()
        _, kwargs = service.store.create.call_args
        self.assertEqual(kwargs["layer"], 3)
        self.assertEqual(kwargs["category"], "未归档")
        self.assertEqual(kwargs["content"], "未归档")

    def test_delete_l5_memory_creates_default_l5_memory_when_missing(self):
        service = MemoryService.__new__(MemoryService)
        service.store = Mock()
        service.vector_store = Mock()

        service.store.get_by_id.side_effect = [
            {
                "id": "l5-memory",
                "layer": 5,
                "category": "旧技能分类",
                "is_pinned": False,
            },
            {
                "id": "child-l6",
                "layer": 6,
                "category": "未分类",
                "content": "原有技能内容",
            },
            {
                "id": "default-l5-memory",
                "layer": 5,
                "category": "未分类",
                "content": "未分类",
            },
        ]
        service.store.get_by_layer.side_effect = [
            [
                {
                    "id": "child-l6",
                    "layer": 6,
                    "category": "旧技能分类",
                    "content": "原有技能内容",
                    "source": "batch_sync",
                }
            ],
            [],
        ]
        service.store.get_categories_by_layer.return_value = []
        service.store.update = Mock(
            side_effect=lambda memory_id, content, category=None, reason="": {
                "id": memory_id,
                "content": content,
                "category": category,
                "reason": reason,
            }
        )
        service.store.create = Mock(
            return_value={
                "id": "default-l5-memory",
                "layer": 5,
                "category": "未分类",
                "content": "未分类",
            }
        )
        service.store.delete.return_value = True
        service.vector_store.get_metadata.return_value = {}
        service.vector_store.get_embedding.return_value = None

        with patch.object(memory_service_module.embedding_service, "remove_from_corpus"), \
             patch.object(memory_service_module.embedding_service, "persist"), \
             patch.object(memory_service_module.embedding_service, "embed_text", return_value=[0.1, 0.2]), \
             patch("app.services.md_export_service.md_export_service.export_memory_to_md"), \
             patch("app.services.md_export_service.md_export_service.delete_memory_file"):
            result = service.delete_memory("l5-memory")

        self.assertTrue(result)
        self.assertGreaterEqual(service.store.create.call_count, 1)
        _, kwargs = service.store.create.call_args
        self.assertEqual(kwargs["layer"], 5)
        self.assertEqual(kwargs["category"], "未分类")
        self.assertEqual(kwargs["content"], "未分类")


if __name__ == "__main__":
    unittest.main()
