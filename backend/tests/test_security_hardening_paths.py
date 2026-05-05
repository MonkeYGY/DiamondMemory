import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

from app.api import knowledge_routes
from app.api import ingest as ingest_routes
from app.api import storage_routes
from app.services.knowledge_service import KnowledgeService


class SecurityHardeningTests(unittest.TestCase):
    def test_knowledge_read_file_rejects_path_traversal_with_backslashes(self):
        with self.assertRaises(HTTPException):
            knowledge_routes.read_file(path="..\\..\\secret.md")

    def test_knowledge_get_tree_rejects_root_path_outside_storage(self):
        with tempfile.TemporaryDirectory() as base_dir:
            base = Path(base_dir)
            outside = base / "outside"
            outside.mkdir(parents=True, exist_ok=True)

            with patch("app.api.knowledge_routes.settings") as mocked_settings:
                mocked_settings.storage_path = str(base)
                with self.assertRaises(HTTPException):
                    knowledge_routes.get_file_tree(root_path=str(outside))

    def test_knowledge_service_read_file_denies_escape(self):
        with tempfile.TemporaryDirectory() as base_dir:
            kb = Path(base_dir) / "kb"
            kb.mkdir(parents=True, exist_ok=True)

            with patch("app.services.knowledge_service.settings") as mocked_settings:
                mocked_settings.storage_path = str(kb)
                service = KnowledgeService()
                # 试图逃逸到 kb 之外
                self.assertIsNone(service.read_file("../x.md"))
                self.assertIsNone(service.read_file("..\\x.md"))

    def test_ingest_url_rejects_localhost(self):
        async def _run():
            with self.assertRaises(HTTPException):
                await ingest_routes.ingest_url(url="http://127.0.0.1:1234/test")

        asyncio.run(_run())

    def test_storage_config_rejects_root_dir(self):
        req = storage_routes.StorageConfigRequest(data_directory="/")
        with self.assertRaises(HTTPException):
            storage_routes.configure_storage(req)


if __name__ == "__main__":
    unittest.main()

