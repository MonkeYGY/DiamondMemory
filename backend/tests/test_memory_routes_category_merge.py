import unittest
from unittest.mock import patch

from app.api import memory_routes


class MemoryRoutesCategoryMergeTests(unittest.TestCase):
    def test_merge_categories_endpoint_supports_single_layer(self):
        with patch(
            "app.api.memory_routes.memory_service.normalize_similar_categories",
            return_value={"merged_groups": 1, "moved_children": 2},
        ) as normalize_mock:
            payload = memory_routes.merge_categories(layer=3, max_groups=5)

        self.assertEqual(payload["status"], "success")
        self.assertEqual(payload["layer"], 3)
        normalize_mock.assert_called_once_with(3, max_groups=5)

    def test_merge_categories_endpoint_supports_all_layers(self):
        with patch(
            "app.api.memory_routes.memory_service.normalize_similar_categories",
            side_effect=[
                {"merged_groups": 1, "moved_children": 2},
                {"merged_groups": 3, "moved_children": 4},
            ],
        ) as normalize_mock:
            payload = memory_routes.merge_categories(layer="all", max_groups=2)

        self.assertEqual(payload["status"], "success")
        self.assertEqual(payload["layer"], "all")
        self.assertEqual(payload["l3"]["merged_groups"], 1)
        self.assertEqual(payload["l5"]["merged_groups"], 3)
        self.assertEqual(normalize_mock.call_count, 2)
        normalize_mock.assert_any_call(3, max_groups=2)
        normalize_mock.assert_any_call(5, max_groups=2)


if __name__ == "__main__":
    unittest.main()
