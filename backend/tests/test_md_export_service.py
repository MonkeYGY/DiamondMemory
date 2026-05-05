import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, Mock, patch

from app.services.md_export_service import MarkdownExportService
from app.services.memory_service import MemoryService
import app.services.memory_service as memory_service_module


class MarkdownExportServiceFolderTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        self.service = MarkdownExportService()
        self.service.store = MagicMock()
        self.service.get_knowledge_base_path = lambda: self.temp_dir.name

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_export_l3_creates_summary_folder_without_markdown_file(self):
        memory = {"id": "l3-1", "layer": 3, "category": "Python服务启动", "content": "Python服务启动"}

        result = self.service.export_memory_to_md(memory)

        expected_dir = Path(self.temp_dir.name) / "总结经验" / "Python服务启动"
        self.assertEqual(Path(result), expected_dir)
        self.assertTrue(expected_dir.is_dir())
        self.assertEqual(list(expected_dir.glob("*.md")), [])
        self.service.store.update_memory_file_path.assert_called_once_with("l3-1", None)

    def test_export_l4_writes_markdown_and_refreshes_file_sync_info(self):
        memory = {
            "id": "l4-1",
            "layer": 4,
            "category": "Python服务启动",
            "content": "主题: Python服务启动\n\n正文内容",
            "created_at": "2026-04-27 00:00:00",
            "processed_status": "summarized",
            "tags": ["Python"],
            "level": 2,
        }

        result = self.service.export_memory_to_md(memory)

        exported_file = Path(result)
        self.assertTrue(exported_file.is_file())
        self.assertEqual(exported_file.parent, Path(self.temp_dir.name) / "总结经验" / "Python服务启动")
        self.service.store.update_memory_file_path.assert_called_once()
        self.service.store.update_file_sync_info.assert_called_once()

    def test_rebuild_exports_rewrites_existing_l3_to_l6_structure(self):
        self.service.store.list_all.return_value = [
            {"id": "l3-1", "layer": 3, "category": "Python服务启动", "content": "Python服务启动"},
            {
                "id": "l4-1",
                "layer": 4,
                "category": "Python服务启动",
                "content": "主题: Python服务启动\n\n正文",
                "created_at": "2026-04-27 00:00:00",
                "processed_status": "summarized",
                "tags": [],
                "level": 2,
            },
            {"id": "l5-1", "layer": 5, "category": "服务部署", "content": "服务部署"},
            {
                "id": "l6-1",
                "layer": 6,
                "category": "服务部署",
                "content": "技能名称: 服务部署\n\n步骤",
                "created_at": "2026-04-27 00:00:00",
                "processed_status": "skilled",
                "tags": [],
                "level": 3,
            },
        ]

        summary = self.service.rebuild_memory_exports()

        self.assertEqual(summary["rebuilt_count"], 4)
        self.assertTrue((Path(self.temp_dir.name) / "总结经验" / "Python服务启动").is_dir())
        self.assertTrue((Path(self.temp_dir.name) / "技能" / "服务部署").is_dir())

    def test_rebuild_exports_removes_stale_system_markdown(self):
        stale_dir = Path(self.temp_dir.name) / "总结经验" / "旧分类"
        stale_dir.mkdir(parents=True)
        stale_file = stale_dir / "旧记录.md"
        stale_file.write_text("---\nmemory_id: stale-id\n---\n\n旧内容\n", encoding="utf-8")

        self.service.store.list_all.return_value = []
        self.service.store.get_by_id.return_value = None

        summary = self.service.rebuild_memory_exports()

        self.assertFalse(stale_file.exists())
        self.assertIn("stale-id", summary["deleted_memory_ids"])


class MemoryServiceExportHookTests(unittest.TestCase):
    @patch("app.services.md_export_service.md_export_service")
    @patch.object(memory_service_module.embedding_service, "persist")
    @patch.object(memory_service_module.embedding_service, "embed_text", return_value=[0.1, 0.2])
    @patch.object(memory_service_module.embedding_service, "update_corpus")
    def test_update_memory_reexports_l4_record(
        self,
        _mock_update_corpus,
        _mock_embed_text,
        _mock_persist,
        mock_export_service,
    ):
        service = MemoryService.__new__(MemoryService)
        service.store = Mock()
        service.vector_store = Mock()
        service.store.get_by_id.side_effect = [
            {
                "id": "l4-1",
                "layer": 4,
                "category": "Python服务启动",
                "source": "system",
                "content": "旧内容",
            },
            {
                "id": "l4-1",
                "layer": 4,
                "category": "Python服务启动",
                "source": "system",
                "content": "新内容",
            },
        ]
        service.store.update.return_value = {
            "id": "l4-1",
            "layer": 4,
            "category": "Python服务启动",
            "content": "新内容",
        }

        service.update_memory("l4-1", "新内容", "测试")

        mock_export_service.export_memory_to_md.assert_called_once()

    @patch("app.services.md_export_service.md_export_service")
    @patch.object(memory_service_module.embedding_service, "remove_from_corpus")
    @patch.object(memory_service_module.embedding_service, "persist")
    def test_delete_memory_removes_exported_file(
        self,
        _mock_persist,
        _mock_remove_from_corpus,
        mock_export_service,
    ):
        service = MemoryService.__new__(MemoryService)
        service.store = Mock()
        service.vector_store = Mock()
        service.store.get_by_id.return_value = {
            "id": "l6-1",
            "layer": 6,
            "category": "服务部署",
            "file_path": "技能/服务部署/服务部署.md",
            "is_pinned": False,
        }
        service.store.delete.return_value = True

        service.delete_memory("l6-1")

        mock_export_service.delete_memory_file.assert_called_once()


class MemoryServiceL4DedupTests(unittest.TestCase):
    @patch("app.services.md_export_service.md_export_service")
    @patch.object(memory_service_module.embedding_service, "persist")
    @patch.object(memory_service_module.embedding_service, "embed_text", return_value=[0.9, 0.1])
    def test_deduplicate_existing_l4_merges_only_same_category_duplicates(
        self,
        _mock_embed_text,
        _mock_persist,
        mock_export_service,
    ):
        service = MemoryService.__new__(MemoryService)
        service.store = Mock()
        service.vector_store = Mock()
        service._merge_summary = Mock(side_effect=lambda old, new: f"{old}\n\n{new}")
        service.delete_memory = Mock()

        current = {"id": "l4-main", "layer": 4, "category": "后端启动", "content": "主总结"}
        same_category_dup = {"id": "l4-dup-1", "layer": 4, "category": "后端启动", "content": "同类重复"}
        other_category_dup = {"id": "l4-dup-2", "layer": 4, "category": "接口创建", "content": "异类相似"}
        updated = {"id": "l4-main", "layer": 4, "category": "后端启动", "content": "合并后"}

        service.store.get_by_layer.return_value = [current]
        service.vector_store.get_embedding.return_value = [0.5, 0.5]
        service.vector_store.search_similar.return_value = [
            ("l4-main", 1.0),
            ("l4-dup-1", 0.91),
            ("l4-dup-2", 0.93),
        ]
        service.store.get_by_id.side_effect = lambda memory_id: {
            "l4-dup-1": same_category_dup,
            "l4-dup-2": other_category_dup,
            "l4-main": updated,
        }.get(memory_id)
        service.store.update.return_value = updated
        service.vector_store.get_metadata.return_value = {"category": "后端启动"}

        result = service.deduplicate_existing_l4()

        self.assertEqual(result["merged"], 1)
        service.delete_memory.assert_called_once_with("l4-dup-1")
        service.store.update.assert_called_once()
        mock_export_service.export_memory_to_md.assert_called_once_with(updated)

    @patch("app.services.md_export_service.md_export_service")
    @patch.object(memory_service_module.embedding_service, "persist")
    @patch.object(memory_service_module.embedding_service, "embed_text", return_value=[0.2, 0.8])
    def test_deduplicate_existing_l4_ignores_low_similarity_candidates(
        self,
        _mock_embed_text,
        _mock_persist,
        mock_export_service,
    ):
        service = MemoryService.__new__(MemoryService)
        service.store = Mock()
        service.vector_store = Mock()
        service._merge_summary = Mock(side_effect=lambda old, new: f"{old}\n\n{new}")
        service.delete_memory = Mock()

        current = {"id": "l4-main", "layer": 4, "category": "后端启动", "content": "主总结"}
        low_similarity_dup = {"id": "l4-dup-1", "layer": 4, "category": "后端启动", "content": "轻度相关"}

        service.store.get_by_layer.return_value = [current]
        service.vector_store.get_embedding.return_value = [0.4, 0.6]
        service.vector_store.search_similar.return_value = [
            ("l4-main", 1.0),
            ("l4-dup-1", 0.60),
        ]
        service.store.get_by_id.side_effect = lambda memory_id: {
            "l4-dup-1": low_similarity_dup,
            "l4-main": current,
        }.get(memory_id)

        result = service.deduplicate_existing_l4()

        self.assertEqual(result["merged"], 0)
        service.delete_memory.assert_not_called()
        service.store.update.assert_not_called()
        mock_export_service.export_memory_to_md.assert_not_called()


if __name__ == "__main__":
    unittest.main()
