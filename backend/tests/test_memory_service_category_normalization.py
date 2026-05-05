import unittest
from unittest.mock import patch

from app.services.memory_service import MemoryService


class MemoryServiceCategoryNormalizationTests(unittest.TestCase):
    def build_service(self):
        service = MemoryService.__new__(MemoryService)
        return service

    def test_normalize_summary_category_delegates_to_l3_normalizer(self):
        service = self.build_service()

        with patch(
            "app.services.memory_service.category_normalization_service.resolve_category_name",
            return_value="记忆同步机制",
        ) as resolve_mock:
            result = service._normalize_summary_category("记忆同步自动化")

        self.assertEqual(result, "记忆同步机制")
        resolve_mock.assert_called_once_with("记忆同步自动化", 3)

    def test_normalize_skill_category_delegates_to_l5_normalizer(self):
        service = self.build_service()

        with patch(
            "app.services.memory_service.category_normalization_service.resolve_category_name",
            return_value="服务部署流程",
        ) as resolve_mock:
            result = service._normalize_skill_category("服务部署自动化")

        self.assertEqual(result, "服务部署流程")
        resolve_mock.assert_called_once_with("服务部署自动化", 5)


if __name__ == "__main__":
    unittest.main()
