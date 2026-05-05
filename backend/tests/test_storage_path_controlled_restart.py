import unittest
from unittest.mock import patch

from app.api.knowledge_routes import rebuild_memory_exports


class KnowledgeRebuildApiTests(unittest.TestCase):
    @patch("app.api.knowledge_routes.md_export_service")
    def test_rebuild_exports_endpoint_returns_summary(self, mock_export_service):
        mock_export_service.rebuild_memory_exports.return_value = {
            "status": "success",
            "rebuilt_count": 4,
            "failed_count": 0,
            "deleted_memory_ids": [],
            "errors": [],
        }

        response = rebuild_memory_exports()

        self.assertEqual(response["rebuilt_count"], 4)
        self.assertEqual(response["deleted_memory_ids"], [])


if __name__ == "__main__":
    unittest.main()
