import hashlib
import unittest
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from app.services.ingest.doc_blocks import (
    build_blocks_from_pages,
    compute_offsets,
    compute_text_hash,
)


class DocBlocksUnitTests(unittest.TestCase):
    def test_compute_text_hash_is_stable(self):
        h1 = compute_text_hash("hello")
        h2 = compute_text_hash("hello")
        self.assertEqual(h1, h2)
        self.assertEqual(h1, hashlib.sha256("hello".encode("utf-8")).hexdigest())

    def test_compute_offsets_produces_monotonic_ranges(self):
        full_text = "A\n\nB\n\nC"
        blocks = [{"text": "A"}, {"text": "B"}, {"text": "C"}]
        out = compute_offsets(full_text, blocks)
        self.assertEqual(out[0]["start_offset"], 0)
        self.assertTrue(out[0]["end_offset"] > out[0]["start_offset"])
        self.assertTrue(out[1]["start_offset"] > out[0]["end_offset"])

    def test_build_blocks_from_pages_keeps_page_numbers(self):
        pages = ["P1 line1\n\nP1 line2", "P2 line1"]
        blocks = build_blocks_from_pages(pages)
        self.assertTrue(any(b.get("page") == 1 for b in blocks))
        self.assertTrue(any(b.get("page") == 2 for b in blocks))


class _DummyStore:
    def __init__(self):
        self.created = []

    def create(self, **kwargs):
        # sqlite_store.create 返回 get_by_id 的 dict，这里最小模拟即可
        self.created.append(kwargs)
        return {
            "id": kwargs.get("memory_id"),
            "content": kwargs.get("content"),
            "category": kwargs.get("category"),
            "layer": kwargs.get("layer"),
            "metadata": kwargs.get("metadata") or {},
            "memory_type": kwargs.get("memory_type"),
        }


class _DummyVectorStore:
    def __init__(self):
        self.saved = []

    def save_embedding(self, memory_id, embedding, metadata):
        self.saved.append((memory_id, embedding, metadata))


class IngestAPipelineTests(unittest.TestCase):
    def test_ingest_file_disturb_free_only_writes_a(self):
        from app.services.ingest.ingest_service import IngestService

        dummy_store = _DummyStore()
        dummy_vector = _DummyVectorStore()

        with TemporaryDirectory() as td:
            # 准备一个“上传文件”
            src = f"{td}/a.pdf"
            with open(src, "wb") as f:
                f.write(b"fake")

            with patch("app.services.ingest.ingest_service.settings.storage_path", td), patch(
                "app.storage.SQLiteStore", return_value=dummy_store
            ), patch(
                "app.storage.vector_store.get_vector_store", return_value=dummy_vector
            ), patch(
                "app.services.embedding_service.embedding_service.embed_text", return_value=[0.1, 0.2]
            ), patch(
                "app.services.embedding_service.embedding_service.persist"
            ):
                svc = IngestService()
                svc._parsers_loaded = True
                svc.pdf_parser = Mock()
                svc.pdf_parser.parse.return_value = {
                    "text": "A\n\nB\n",
                    "metadata": {"num_pages": 1},
                    "blocks": [
                        {"text": "A", "page": 1, "chunk_index": 0},
                        {"text": "B", "page": 1, "chunk_index": 1},
                    ],
                }

                result = svc.ingest_file(src, disturb_free=True)
                self.assertTrue(result["success"])
                self.assertIn("doc_id", result)

        created_types = [c.get("memory_type") for c in dummy_store.created]
        self.assertIn("doc", created_types)
        self.assertIn("doc_chunk", created_types)
        self.assertNotIn("doc_structured", created_types)


class IngestBPipelineTests(unittest.TestCase):
    def test_ingest_file_generates_structured_when_not_disturb_free(self):
        from app.services.ingest.ingest_service import IngestService

        dummy_store = _DummyStore()
        dummy_vector = _DummyVectorStore()

        with TemporaryDirectory() as td:
            src = f"{td}/a.pdf"
            with open(src, "wb") as f:
                f.write(b"fake")

            with patch("app.services.ingest.ingest_service.settings.storage_path", td), patch(
                "app.storage.SQLiteStore", return_value=dummy_store
            ), patch(
                "app.storage.vector_store.get_vector_store", return_value=dummy_vector
            ), patch(
                "app.services.embedding_service.embedding_service.embed_text", return_value=[0.1, 0.2]
            ), patch(
                "app.services.embedding_service.embedding_service.persist"
            ), patch(
                "app.services.inference.inference_service.inference_service.generate",
                return_value='{"keypoints":["k1"],"citations":[{"chunk_index":0}]}',
            ):
                svc = IngestService()
                svc._parsers_loaded = True
                svc.pdf_parser = Mock()
                svc.pdf_parser.parse.return_value = {
                    "text": "A\n\nB\n",
                    "metadata": {"num_pages": 1},
                    "blocks": [
                        {"text": "A", "page": 1, "chunk_index": 0},
                        {"text": "B", "page": 1, "chunk_index": 1},
                    ],
                }

                result = svc.ingest_file(src, disturb_free=False)
                self.assertTrue(result["success"])

        created_types = [c.get("memory_type") for c in dummy_store.created]
        self.assertIn("doc_structured", created_types)


class RetrievalCitationTests(unittest.TestCase):
    def test_format_results_includes_citations_for_doc_chunk(self):
        from app.services.retrieval_service import RetrievalService

        svc = RetrievalService()
        results = [
            {
                "id": "c1",
                "content": "原文段落",
                "category": "user_doc",
                "layer": 1,
                "level": 1,
                "final_score": 0.9,
                "source": "file",
                "created_at": "2026-01-01",
                "tags": [],
                "access_count": 0,
                "is_pinned": False,
                "metadata": {
                    "memory_type": "doc_chunk",
                    "doc_id": "d1",
                    "page": 2,
                    "start_offset": 10,
                    "end_offset": 20,
                    "source_path": "raw/x.pdf",
                },
            }
        ]
        out = svc._format_results(results)
        self.assertIn("citations", out[0])
        self.assertTrue(out[0]["citations"])


class IngestApiParamTests(unittest.TestCase):
    def test_ingest_file_passes_disturb_free(self):
        import asyncio
        try:
            import multipart  # type: ignore
        except Exception:
            self.skipTest("未安装 python-multipart，跳过 FastAPI Form 参数测试")

        import app.api.ingest as ingest_api

        with patch("app.api.ingest.ingest_service") as mock_ingest:
            mock_ingest.ingest_file.return_value = {"success": True}

            class FakeUpload:
                filename = "a.pdf"

                async def read(self):
                    return b"pdf"

            res = asyncio.get_event_loop().run_until_complete(
                ingest_api.ingest_file(file=FakeUpload(), disturb_free=True)
            )
            self.assertTrue(res["success"])
            mock_ingest.ingest_file.assert_called()


class VectorMetaMemoryTypeTests(unittest.TestCase):
    @patch("app.services.memory_service.embedding_service.embed_text", return_value=[0.1, 0.2])
    @patch("app.services.memory_service.embedding_service.persist")
    @patch("app.services.entity_extractor.entity_extractor.extract", return_value=[])
    def test_create_memory_writes_memory_type_to_vector_metadata(self, _entities, _persist, _embed):
        from app.services.memory_service import MemoryService

        service = MemoryService.__new__(MemoryService)
        service.store = Mock()
        service.vector_store = Mock()
        from datetime import timezone, timedelta

        service.beijing_tz = timezone(timedelta(hours=8))

        service.store.create.return_value = {"id": "m1", "layer": 2, "category": "user_doc", "content": "x"}

        service.create_memory(
            content="x",
            category="user_doc",
            layer=1,
            source="file",
            metadata={"memory_type": "doc_chunk"},
        )

        saved_meta = service.vector_store.save_embedding.call_args[0][2]
        self.assertEqual(saved_meta.get("memory_type"), "doc_chunk")


if __name__ == "__main__":
    unittest.main()
