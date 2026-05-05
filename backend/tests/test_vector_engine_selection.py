import asyncio
import unittest
from unittest.mock import patch


class VectorEngineSelectionTests(unittest.TestCase):
    def test_get_active_vector_store_returns_qdrant_store_even_when_unavailable(self):
        """
        settings 选择 qdrant 时：统一返回 QdrantVectorStore（其内部自行决定是否 fallback）。
        这样 /health 等接口才能准确反映真实 engine（qdrant 或 faiss fallback）。
        """
        import app.storage as storage
        from app.config import settings

        class FakeQdrantStore:
            def __init__(self):
                self._available = False  # 模拟 qdrant-client 不可用/初始化失败后的状态

            def get_stats(self):
                return {"engine": "faiss"}

        fake_store = FakeQdrantStore()

        with patch.object(settings, "vector_store_engine", "qdrant", create=True):
            with patch.object(storage, "get_qdrant_store", return_value=fake_store):
                active = storage.get_active_vector_store()

        self.assertIs(active, fake_store)
        self.assertEqual(active.get_stats()["engine"], "faiss")

    def test_memory_service_initializes_vector_store_via_get_active_vector_store(self):
        import app.storage as storage

        sentinel_store = object()

        with patch.object(storage, "get_active_vector_store", return_value=sentinel_store):
            # 重新导入以确保 MemoryService 使用的注入点来自 app.storage
            from app.services.memory_service import MemoryService

            service = MemoryService()

        self.assertIs(service.vector_store, sentinel_store)

    def test_health_endpoint_reports_current_vector_engine(self):
        import app.storage as storage

        class FakeStore:
            def get_stats(self):
                return {"engine": "qdrant", "vector_count": 123}

        with patch.object(storage, "get_active_vector_store", return_value=FakeStore()):
            from app.api.health import health_check

            payload = asyncio.run(health_check())

        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["services"]["vector_store"]["engine"], "qdrant")
        self.assertEqual(payload["services"]["vector_store"]["vector_count"], 123)


if __name__ == "__main__":
    unittest.main()

