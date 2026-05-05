from unittest.mock import MagicMock


def _build_service():
    from app.services.retrieval_service import RetrievalService

    s = RetrievalService.__new__(RetrievalService)
    s.store = MagicMock()
    s.vector_store = MagicMock()
    s._format_results = lambda xs: xs
    s._post_retrieval_dedup = lambda xs: xs
    return s


def test_query_recent_similar_l1_filters_by_score(monkeypatch):
    service = _build_service()
    service.store.get_recent_by_layer.return_value = [
        {"id": "m1", "layer": 1, "content": "你好", "status": "active"},
        {"id": "m2", "layer": 1, "content": "我们聊过上下文窗口", "status": "active"},
    ]

    service.vector_store.get_embedding.side_effect = lambda mid: [1.0, 0.0] if mid == "m2" else [0.0, 1.0]

    emb_mod = __import__("app.services.embedding_service", fromlist=["embedding_service"])
    monkeypatch.setattr(emb_mod.embedding_service, "embed_text", lambda *_args, **_kw: [1.0, 0.0])

    result = service.query_recent_similar_l1("你好", recent_n=30, limit=3, min_score=0.5)
    memories = result.get("memories") or []
    assert len(memories) == 1
    assert memories[0]["id"] == "m2"

