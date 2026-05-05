import os
import unittest
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch
from pathlib import Path

from app.services.knowledge_service import KnowledgeService


class KnowledgeServiceScanFileTreeTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        base = Path(self.temp_dir.name)

        # layer folders
        (base / "技能" / "SkillA").mkdir(parents=True)
        (base / "总结经验" / "SumA").mkdir(parents=True)

        (base / "技能" / "SkillA" / "a.md").write_text("# a\n", encoding="utf-8")
        (base / "总结经验" / "SumA" / "s.md").write_text("# s\n", encoding="utf-8")

        # a large unrelated folder that must not be touched when layer_filter is set
        (base / "big_folder").mkdir()
        (base / "big_folder" / "x.md").write_text("# x\n", encoding="utf-8")

        self.base = base

    def tearDown(self):
        self.temp_dir.cleanup()

    def _new_service(self) -> KnowledgeService:
        service = KnowledgeService()
        service.store = MagicMock()
        service.store.get_max_file_sync_last_modified.return_value = None
        return service

    def test_scan_file_tree_layer_filter_restricts_to_mapped_root(self):
        service = self._new_service()

        tree = service.scan_file_tree(str(self.base), layer_filter=5)

        # Flatten paths
        def walk(nodes):
            for n in nodes:
                yield n["path"]
                if n.get("children"):
                    yield from walk(n["children"])

        paths = list(walk(tree))

        self.assertTrue(any(p.startswith("技能/") for p in paths))
        self.assertFalse(any(p.startswith("总结经验/") for p in paths))
        self.assertFalse(any(p.startswith("big_folder") for p in paths))

    def test_scan_file_tree_uses_cache_and_avoids_deep_rescan(self):
        service = self._new_service()

        # First scan: will walk into 子目录
        with patch("os.scandir", wraps=os.scandir) as scandir_mock_1:
            tree1 = service.scan_file_tree(str(self.base), layer_filter=5)
            visited_1 = {call.args[0] for call in scandir_mock_1.call_args_list}

        self.assertIn(str(self.base / "技能" / "SkillA"), visited_1)

        # Second scan: should only do shallow checks, not descend into SkillA again
        with patch("os.scandir", wraps=os.scandir) as scandir_mock_2:
            tree2 = service.scan_file_tree(str(self.base), layer_filter=5)
            visited_2 = {call.args[0] for call in scandir_mock_2.call_args_list}

        self.assertEqual(tree1, tree2)
        self.assertNotIn(str(self.base / "技能" / "SkillA"), visited_2)

    def test_scan_file_tree_large_folder_is_paginated(self):
        service = self._new_service()

        # Create a large directory: 技能/SkillA contains many md files
        skill_dir = self.base / "技能" / "SkillA"
        for i in range(0, 1200):
            (skill_dir / f"f{i:04d}.md").write_text(f"# {i}\n", encoding="utf-8")

        tree = service.scan_file_tree(str(self.base), layer_filter=5, per_dir_limit=200)

        # Find the SkillA node
        skill_root = next(n for n in tree if n["path"] == "技能")
        skill_a = next(n for n in skill_root["children"] if n["path"].startswith("技能/SkillA"))

        self.assertTrue(skill_a.get("has_more"))
        self.assertEqual(skill_a.get("next_offset"), 200)
        self.assertEqual(len(skill_a.get("children", [])), 200)

        page2 = service.scan_tree_children(
            str(self.base),
            dir_path="技能/SkillA",
            offset=200,
            limit=200,
            layer_filter=5,
        )
        self.assertEqual(len(page2["children"]), 200)
        self.assertTrue(page2["has_more"])
        self.assertEqual(page2["next_offset"], 400)

    def test_scan_file_tree_cache_can_short_circuit_by_file_sync_mtime(self):
        service = self._new_service()
        service.store.get_max_file_sync_last_modified.return_value = 123.0

        tree1 = service.scan_file_tree(str(self.base), layer_filter=5)

        # If caching is short-circuited by file_sync mtime, it should not compute signatures again
        service._compute_shallow_signature = MagicMock(side_effect=AssertionError("signature should not be recomputed"))

        tree2 = service.scan_file_tree(str(self.base), layer_filter=5)
        self.assertEqual(tree1, tree2)
