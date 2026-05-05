import unittest
from unittest.mock import Mock, patch

from app.services.memory_service import MemoryService


class CategoryNormalizationFlowTests(unittest.TestCase):
    def test_normalize_categories_moves_children_and_deletes_redundant_l3(self):
        service = MemoryService.__new__(MemoryService)
        service.store = Mock()
        service.vector_store = Mock()
        service.cleanup_empty_categories = Mock(return_value={"memories_deleted": 0, "directories_deleted": 0})

        service.store.get_memories_by_category.return_value = [
            {"id": "l4-2", "content": "正文", "category": "记忆同步自动化", "layer": 4}
        ]
        service.store.get_by_id.side_effect = lambda memory_id: {
            "l4-2": {"id": "l4-2", "content": "正文", "category": "记忆同步机制", "layer": 4}
        }.get(memory_id)

        with patch(
            "app.services.memory_service.category_normalization_service.build_merge_plan",
            return_value=[
                {
                    "target_category": "记忆同步机制",
                    "target_category_id": "l3-1",
                    "redundant_category_ids": ["l3-2"],
                    "redundant_category_names": ["记忆同步自动化"],
                    "child_layer": 4,
                }
            ],
        ), patch(
            "app.services.memory_service.md_export_service.export_memory_to_md"
        ) as export_mock, patch.object(service, "delete_memory", return_value=True) as delete_mock:
            result = service.normalize_similar_categories(3)

        self.assertEqual(result["merged_groups"], 1)
        self.assertEqual(result["directories_deleted"], 0)
        service.store.update.assert_any_call(
            "l4-2",
            "正文",
            category="记忆同步机制",
            reason="L3分类收敛合并",
        )
        export_mock.assert_called_once()
        delete_mock.assert_called_once_with("l3-2")


if __name__ == "__main__":
    unittest.main()
