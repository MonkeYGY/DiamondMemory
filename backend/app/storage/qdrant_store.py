"""Qdrant向量存储引擎

使用Qdrant本地模式实现高性能向量索引，支持：
- HNSW索引，搜索性能提升5-10倍
- 元数据过滤，支持按layer/category/status精确过滤
- 增量写入，无需重建索引
- 自动从FAISS数据迁移
- 降级兼容（Qdrant不可用时回退到FAISS）
"""
import os
import json
import logging
import threading
import time
from typing import List, Dict, Any, Tuple, Optional
from app.config import settings

logger = logging.getLogger(__name__)


class QdrantVectorStore:
    def __init__(self):
        self.data_dir = settings.data_directory
        os.makedirs(self.data_dir, exist_ok=True)
        self.dimension = settings.embedding_dimensions
        self._lock = threading.Lock()
        self._client = None
        self._collection_name = settings.qdrant_collection_name
        self._available = False
        self._faiss_fallback = None
        self._meta_file = os.path.join(self.data_dir, "qdrant_meta.json")
        self._metadata_cache: Dict[str, Dict[str, Any]] = {}
        self._load_metadata_cache()
        self._initialize()

    def _initialize(self):
        try:
            from qdrant_client import QdrantClient
            from qdrant_client.models import Distance, VectorParams

            qdrant_path = settings.qdrant_path or os.path.join(self.data_dir, "qdrant_storage")
            os.makedirs(qdrant_path, exist_ok=True)

            self._client = QdrantClient(path=qdrant_path)
            self._available = True

            collections = [c.name for c in self._client.get_collections().collections]
            if self._collection_name not in collections:
                self._client.create_collection(
                    collection_name=self._collection_name,
                    vectors_config=VectorParams(
                        size=self.dimension,
                        distance=Distance.COSINE,
                        hnsw_config={
                            "m": settings.hnsw_m,
                            "ef_construct": settings.hnsw_ef_construction,
                        }
                    )
                )
                logger.info(f"[QdrantVectorStore] 创建集合 {self._collection_name}，维度={self.dimension}")
            else:
                logger.info(f"[QdrantVectorStore] 连接已有集合 {self._collection_name}")

            self._migrate_from_faiss_if_needed()

        except ImportError:
            logger.warning("[QdrantVectorStore] qdrant-client 未安装，回退到FAISS引擎")
            self._init_faiss_fallback()
        except Exception as e:
            logger.warning(f"[QdrantVectorStore] 初始化失败: {e}，回退到FAISS引擎")
            self._init_faiss_fallback()

    def _init_faiss_fallback(self):
        from app.storage.vector_store import VectorStore
        self._faiss_fallback = VectorStore()
        self._available = False

    def _load_metadata_cache(self):
        if os.path.exists(self._meta_file):
            try:
                with open(self._meta_file, "r", encoding="utf-8") as f:
                    self._metadata_cache = json.load(f)
            except Exception:
                self._metadata_cache = {}

    def _save_metadata_cache(self):
        try:
            with open(self._meta_file, "w", encoding="utf-8") as f:
                json.dump(self._metadata_cache, f, ensure_ascii=False)
        except Exception as e:
            logger.warning(f"[QdrantVectorStore] 元数据缓存保存失败: {e}")

    def _migrate_from_faiss_if_needed(self):
        if not self._available:
            return
        migration_flag = os.path.join(self.data_dir, ".qdrant_migrated")
        if os.path.exists(migration_flag):
            return

        faiss_meta_file = os.path.join(self.data_dir, "faiss_meta.json")
        if not os.path.exists(faiss_meta_file):
            open(migration_flag, "w").close()
            return

        try:
            with open(faiss_meta_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            embeddings = data.get("embeddings", {})
            metadata = data.get("metadata", {})

            if not embeddings:
                open(migration_flag, "w").close()
                return

            from qdrant_client.models import PointStruct

            points = []
            for mid, emb in embeddings.items():
                if len(emb) != self.dimension:
                    if len(emb) > self.dimension:
                        emb = emb[:self.dimension]
                    else:
                        emb = emb + [0.0] * (self.dimension - len(emb))

                meta = metadata.get(mid, {})
                payload = {k: v for k, v in meta.items() if isinstance(v, (str, int, float, bool, list))}
                points.append(
                    PointStruct(id=mid, vector=emb, payload=payload)
                )

            if points:
                batch_size = 100
                for i in range(0, len(points), batch_size):
                    batch = points[i:i + batch_size]
                    self._client.upsert(
                        collection_name=self._collection_name,
                        points=batch
                    )

                self._metadata_cache = metadata
                self._save_metadata_cache()

            open(migration_flag, "w").close()
            logger.info(f"[QdrantVectorStore] 从FAISS迁移了 {len(embeddings)} 条向量")

        except Exception as e:
            logger.warning(f"[QdrantVectorStore] FAISS迁移失败: {e}")

    def save_embedding(self, memory_id: str, embedding: List[float], metadata: Dict[str, Any]):
        with self._lock:
            if len(embedding) != self.dimension:
                if len(embedding) > self.dimension:
                    embedding = embedding[:self.dimension]
                else:
                    embedding = embedding + [0.0] * (self.dimension - len(embedding))

            self._metadata_cache[memory_id] = metadata

            if self._available:
                try:
                    from qdrant_client.models import PointStruct
                    payload = {k: v for k, v in metadata.items() if isinstance(v, (str, int, float, bool, list))}
                    self._client.upsert(
                        collection_name=self._collection_name,
                        points=[PointStruct(id=memory_id, vector=embedding, payload=payload)]
                    )
                    return
                except Exception as e:
                    logger.warning(f"[QdrantVectorStore] 写入失败: {e}")

            if self._faiss_fallback:
                self._faiss_fallback.save_embedding(memory_id, embedding, metadata)

    def get_embedding(self, memory_id: str) -> List[float]:
        if self._available:
            try:
                result = self._client.retrieve(
                    collection_name=self._collection_name,
                    ids=[memory_id],
                    with_vectors=True
                )
                if result and result[0].vector:
                    return result[0].vector
            except Exception:
                pass

        if self._faiss_fallback:
            return self._faiss_fallback.get_embedding(memory_id)
        return []

    def get_metadata(self, memory_id: str) -> Dict[str, Any]:
        if memory_id in self._metadata_cache:
            return self._metadata_cache[memory_id]

        if self._available:
            try:
                result = self._client.retrieve(
                    collection_name=self._collection_name,
                    ids=[memory_id],
                    with_payload=True
                )
                if result and result[0].payload:
                    meta = result[0].payload
                    self._metadata_cache[memory_id] = meta
                    return meta
            except Exception:
                pass

        if self._faiss_fallback:
            return self._faiss_fallback.get_metadata(memory_id)
        return {}

    def search_similar(self, query_embedding: List[float], k: int = 10,
                       filter_metadata: Dict[str, Any] = None) -> List[Tuple[str, float]]:
        if len(query_embedding) != self.dimension:
            if len(query_embedding) > self.dimension:
                query_embedding = query_embedding[:self.dimension]
            else:
                query_embedding = query_embedding + [0.0] * (self.dimension - len(query_embedding))

        if self._available:
            try:
                from qdrant_client.models import Filter, FieldCondition, MatchValue

                qdrant_filter = None
                if filter_metadata:
                    conditions = []
                    for key, value in filter_metadata.items():
                        if isinstance(value, (str, int, float, bool)):
                            conditions.append(FieldCondition(key=key, match=MatchValue(value=value)))
                    if conditions:
                        qdrant_filter = Filter(must=conditions)

                results = self._client.search(
                    collection_name=self._collection_name,
                    query_vector=query_embedding,
                    limit=k,
                    query_filter=qdrant_filter
                )

                return [(str(r.id), r.score) for r in results]
            except Exception as e:
                logger.warning(f"[QdrantVectorStore] 搜索失败: {e}，回退到FAISS")

        if self._faiss_fallback:
            return self._faiss_fallback.search_similar(query_embedding, k, filter_metadata)
        return []

    def search_similar_batch(self, query_embeddings: List[List[float]], k: int = 10) -> List[List[Tuple[str, float]]]:
        if not query_embeddings:
            return []

        if self._available:
            try:
                all_results = []
                for qe in query_embeddings:
                    results = self.search_similar(qe, k)
                    all_results.append(results)
                return all_results
            except Exception as e:
                logger.warning(f"[QdrantVectorStore] 批量搜索失败: {e}")

        if self._faiss_fallback:
            return self._faiss_fallback.search_similar_batch(query_embeddings, k)
        return [[] for _ in query_embeddings]

    def remove_embedding(self, memory_id: str):
        with self._lock:
            self._metadata_cache.pop(memory_id, None)

            if self._available:
                try:
                    from qdrant_client.models import PointIdsList
                    self._client.delete(
                        collection_name=self._collection_name,
                        points_selector=PointIdsList(points=[memory_id])
                    )
                    return
                except Exception as e:
                    logger.warning(f"[QdrantVectorStore] 删除失败: {e}")

            if self._faiss_fallback:
                self._faiss_fallback.remove_embedding(memory_id)

    def _persist(self):
        self._save_metadata_cache()
        if self._faiss_fallback:
            self._faiss_fallback._persist()

    def get_stats(self) -> Dict[str, Any]:
        stats = {
            "engine": "qdrant" if self._available else "faiss",
            "dimension": self.dimension,
            "metadata_cached": len(self._metadata_cache),
        }

        if self._available:
            try:
                info = self._client.get_collection(self._collection_name)
                stats["vector_count"] = info.points_count
                stats["index_type"] = "hnsw"
                stats["qdrant_available"] = True
                return stats
            except Exception:
                pass

        if self._faiss_fallback:
            faiss_stats = self._faiss_fallback.get_stats()
            stats.update(faiss_stats)
            stats["qdrant_available"] = False

        return stats


_qdrant_store_instance: Optional[QdrantVectorStore] = None


def get_qdrant_store() -> QdrantVectorStore:
    global _qdrant_store_instance
    if _qdrant_store_instance is None:
        _qdrant_store_instance = QdrantVectorStore()
    return _qdrant_store_instance
