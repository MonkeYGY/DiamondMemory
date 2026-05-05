import unittest
from unittest.mock import Mock, patch

from app.services.memory_service import MemoryService


class MemoryServiceCategoryConsolidationTests(unittest.TestCase):
    def build_service(self):
        service = MemoryService.__new__(MemoryService)
        service.store = Mock()
        service.vector_store = Mock()
        return service

    def test_normalize_similar_categories_respects_max_groups_and_returns_cleanup_stats(self):
        service = self.build_service()
        service.store.get_memories_by_category.side_effect = lambda category, layer: [
            {"id": f"{category}-child", "content": "正文", "category": category, "layer": layer}
        ]
        service.store.get_by_id.side_effect = lambda memory_id: {
            "id": memory_id,
            "content": "正文",
            "category": "主分类",
            "layer": 4,
        }
        service.cleanup_empty_categories = Mock(return_value={"memories_deleted": 2, "directories_deleted": 1})

        with patch(
            "app.services.memory_service.category_normalization_service.build_merge_plan",
            return_value=[
                {
                    "target_category": "主分类A",
                    "target_category_id": "l3-a",
                    "redundant_category_ids": ["l3-a-dup"],
                    "redundant_category_names": ["近义分类A"],
                    "child_layer": 4,
                },
                {
                    "target_category": "主分类B",
                    "target_category_id": "l3-b",
                    "redundant_category_ids": ["l3-b-dup"],
                    "redundant_category_names": ["近义分类B"],
                    "child_layer": 4,
                },
            ],
        ), patch("app.services.memory_service.md_export_service.export_memory_to_md"), patch.object(
            service, "delete_memory", return_value=True
        ) as delete_mock:
            result = service.normalize_similar_categories(3, max_groups=1)

        self.assertEqual(result["layer"], 3)
        self.assertEqual(result["detected_groups"], 1)
        self.assertEqual(result["merged_groups"], 1)
        self.assertEqual(result["moved_children"], 1)
        self.assertEqual(result["categories_deleted"], 2)
        self.assertEqual(result["directories_deleted"], 1)
        delete_mock.assert_called_once_with("l3-a-dup")
        service.cleanup_empty_categories.assert_called_once()


if __name__ == "__main__":
    unittest.main()
