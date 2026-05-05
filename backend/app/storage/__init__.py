"""存储模块"""
from .sqlite_store import SQLiteStore
from .vector_store import VectorStore, get_vector_store
from .qdrant_store import QdrantVectorStore, get_qdrant_store


def get_active_vector_store():
    engine = getattr(__import__('app.config', fromlist=['settings']).settings, 'vector_store_engine', 'faiss')
    if engine == "qdrant":
        try:
            # 统一返回 QdrantVectorStore，由其内部决定是否使用 qdrant 或 faiss fallback，
            # 这样外部调用方（如 /health）可以准确拿到当前真实引擎状态。
            return get_qdrant_store()
        except Exception:
            # 极端情况下（例如初始化抛出非预期异常）再回退到本地 VectorStore
            return get_vector_store()
    return get_vector_store()


__all__ = ["SQLiteStore", "VectorStore", "get_vector_store", "QdrantVectorStore", "get_qdrant_store", "get_active_vector_store"]
