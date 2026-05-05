import unittest
from unittest.mock import MagicMock


class RetrievalHistoryFilterTests(unittest.TestCase):
    def _build_service(self):
        from app.services.retrieval_service import RetrievalService

        service = RetrievalService.__new__(RetrievalService)
        service.store = MagicMock()
        service.vector_store = MagicMock()
        return service

    def test_semantic_search_filters_invalid_at_by_default(self):
        service = self._build_service()

        service.vector_store.search_similar.return_value = [("m1", 0.9), ("m2", 0.8)]

        def _get(mid):
            if mid == "m1":
                return {"id": "m1", "layer": 4, "status": "active", "invalid_at": "2026-01-01 00:00:00"}
            return {"id": "m2", "layer": 4, "status": "active", "invalid_at": None}

        service.store.get_by_id.side_effect = _get

        results = service._semantic_search([0.1, 0.2], k=10, include_history=False)
        self.assertEqual([m["id"] for m in results], ["m2"])

    def test_semantic_search_can_include_history_when_enabled(self):
        service = self._build_service()

        service.vector_store.search_similar.return_value = [("m1", 0.9), ("m2", 0.8)]

        def _get(mid):
            if mid == "m1":
                return {"id": "m1", "layer": 4, "status": "invalid", "invalid_at": "2026-01-01 00:00:00"}
            return {"id": "m2", "layer": 4, "status": "active", "invalid_at": None}

        service.store.get_by_id.side_effect = _get

        results = service._semantic_search([0.1, 0.2], k=10, include_history=True)
        self.assertEqual([m["id"] for m in results], ["m1", "m2"])


if __name__ == "__main__":
    unittest.main()

