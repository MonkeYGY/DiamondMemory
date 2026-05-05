import unittest
from unittest.mock import Mock

from app.services.category_normalization_service import CategoryNormalizationService


class CategoryNormalizationServiceTests(unittest.TestCase):
    def build_service(self):
        service = CategoryNormalizationService.__new__(CategoryNormalizationService)
        service.store = Mock()
        return service

    def test_compare_key_removes_prefixes_and_maps_synonyms(self):
        service = CategoryNormalizationService()
        self.assertEqual(service._compare_key("关于Git配置"), "GIT配置")
        self.assertEqual(service._compare_key("Deploy流程"), "部署")
        self.assertEqual(service._compare_key("如何修复Bug"), "修复")

    def test_resolve_category_name_reuses_obvious_existing_l3_category(self):
        service = self.build_service()
        service.store.get_by_layer.return_value = [
            {"id": "l3-1", "category": "记忆同步机制"},
            {"id": "l3-2", "category": "Python服务启动"},
        ]

        resolved = service.resolve_category_name("记忆同步自动化", 3)

        self.assertEqual(resolved, "记忆同步机制")

    def test_build_merge_plan_groups_l5_categories_by_same_core_phrase(self):
        service = self.build_service()
        service.store.get_by_layer.return_value = [
            {"id": "l5-1", "category": "服务部署流程", "content": "服务部署流程"},
            {"id": "l5-2", "category": "服务部署自动化", "content": "服务部署自动化"},
        ]
        service.store.get_memories_by_category.side_effect = lambda category, layer: [
            {"id": "l6-1", "category": category, "layer": layer}
        ] if category == "服务部署流程" else []

        plan = service.build_merge_plan(5)

        self.assertEqual(len(plan), 1)
        self.assertEqual(plan[0]["target_category"], "服务部署流程")
        self.assertEqual(plan[0]["redundant_category_ids"], ["l5-2"])


if __name__ == "__main__":
    unittest.main()
