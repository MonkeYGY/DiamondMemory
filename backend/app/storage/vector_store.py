"""向量存储模块

使用 FAISS 实现高性能向量索引，支持：
- L2 距离搜索（IndexFlatL2）
- 内存映射持久化（读写分离）
- 元数据独立存储（JSON）
- 自动维度适配
- 降级兼容（FAISS 不可用时回退到纯 Python）
"""
import os
import json
import logging
import threading
from typing import List, Dict, Any, Tuple, Optional
from app.config import settings

logger = logging.getLogger(__name__)


class VectorStore:
    _FAISS_AVAILABLE = False
    try:
        import faiss
        _FAISS_AVAILABLE = True
    except ImportError:
        pass

    def __init__(self):
        self.data_dir = settings.data_directory
        os.makedirs(self.data_dir, exist_ok=True)

        self.dimension = settings.embedding_dimensions
        self.index_file = os.path.join(self.data_dir, "faiss_index.bin")
        self.meta_file = os.path.join(self.data_dir, "faiss_meta.json")
        self.embeddings: Dict[str, List[float]] = {}
        self.metadata: Dict[str, Dict[str, Any]] = {}
        self._id_list: List[str] = []
        self._faiss_index = None
        self._lock = threading.Lock()

        self._load_data()
        self._build_faiss()

    def _load_data(self):
        if os.path.exists(self.meta_file):
            try:
                with open(self.meta_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.metadata = data.get("metadata", {})
                    self.embeddings = data.get("embeddings", {})
                    self._id_list = list(self.embeddings.keys())
            except Exception as e:
                logger.warning(f"[VectorStore] 元数据加载失败: {e}")

        legacy_file = os.path.join(self.data_dir, "embeddings.pkl")
        if not self.embeddings and os.path.exists(legacy_file):
            try:
                import pickle
                with open(legacy_file, "rb") as f:
                    data = pickle.load(f)
                    self.embeddings = data.get("embeddings", {})
                    self.metadata = data.get("metadata", {})
                    self._id_list = list(self.embeddings.keys())
                logger.info(f"[VectorStore] 从旧格式迁移了 {len(self.embeddings)} 条向量")
            except Exception:
                pass

    def _build_faiss(self):
        if not self._FAISS_AVAILABLE:
            logger.warning("[VectorStore] FAISS 不可用，使用纯 Python 余弦相似度搜索")
            return

        if not self.embeddings:
            return

        try:
            import numpy as np
            import faiss

            vectors = []
            id_order = []
            for mid, emb in self.embeddings.items():
                if len(emb) == self.dimension:
                    vectors.append(emb)
                    id_order.append(mid)

            if not vectors:
                return

            matrix = np.array(vectors, dtype=np.float32)
            norms = np.linalg.norm(matrix, axis=1, keepdims=True)
            norms = np.where(norms == 0, 1, norms)
            matrix = matrix / norms

            self._faiss_index = faiss.IndexFlatIP(self.dimension)
            self._faiss_index.add(matrix)
            self._id_list = id_order
            logger.info(f"[VectorStore] FAISS 索引构建完成，{len(self._id_list)} 条向量")
        except Exception as e:
            logger.warning(f"[VectorStore] FAISS 索引构建失败: {e}，回退到纯 Python")
            self._faiss_index = None

    def _rebuild_faiss(self):
        self._build_faiss()

    def save_embedding(self, memory_id: str, embedding: List[float], metadata: Dict[str, Any]):
        with self._lock:
            if len(embedding) != self.dimension:
                if len(embedding) > self.dimension:
                    embedding = embedding[:self.dimension]
                else:
                    embedding = embedding + [0.0] * (self.dimension - len(embedding))

            is_new = memory_id not in self.embeddings
            self.embeddings[memory_id] = embedding
            self.metadata[memory_id] = metadata

            if is_new:
                self._id_list.append(memory_id)
                if self._faiss_index is not None:
                    try:
                        import numpy as np
                        vec = np.array([embedding], dtype=np.float32)
                        norm = np.linalg.norm(vec)
                        if norm > 0:
                            vec = vec / norm
                        self._faiss_index.add(vec)
                    except Exception:
                        self._rebuild_faiss()
            else:
                self._rebuild_faiss()

        self._persist()

    def get_embedding(self, memory_id: str) -> List[float]:
        return self.embeddings.get(memory_id, [])

    def search_similar(self, query_embedding: List[float], k: int = 10,
                       filter_metadata: Dict[str, Any] = None) -> List[Tuple[str, float]]:
        if not self.embeddings:
            return []

        if len(query_embedding) != self.dimension:
            if len(query_embedding) > self.dimension:
                query_embedding = query_embedding[:self.dimension]
            else:
                query_embedding = query_embedding + [0.0] * (self.dimension - len(query_embedding))

        if self._faiss_index is not None and not filter_metadata:
            return self._search_faiss(query_embedding, k)

        return self._search_python(query_embedding, k, filter_metadata)

    def _search_faiss(self, query_embedding: List[float], k: int) -> List[Tuple[str, float]]:
        try:
            import numpy as np

            query = np.array([query_embedding], dtype=np.float32)
            norm = np.linalg.norm(query)
            if norm > 0:
                query = query / norm

            actual_k = min(k, len(self._id_list))
            if actual_k == 0:
                return []

            scores, indices = self._faiss_index.search(query, actual_k)

            results = []
            for i in range(len(indices[0])):
                idx = indices[0][i]
                if idx < 0 or idx >= len(self._id_list):
                    continue
                memory_id = self._id_list[idx]
                score = float(scores[0][i])
                results.append((memory_id, score))
            return results
        except Exception as e:
            logger.warning(f"[VectorStore] FAISS 搜索失败: {e}，回退到 Python")
            return self._search_python(query_embedding, k)

    def _search_python(self, query_embedding: List[float], k: int,
                       filter_metadata: Dict[str, Any] = None) -> List[Tuple[str, float]]:
        results = []
        for memory_id, embedding in self.embeddings.items():
            if filter_metadata:
                memory_meta = self.metadata.get(memory_id, {})
                match = True
                for key, value in filter_metadata.items():
                    if memory_meta.get(key) != value:
                        match = False
                        break
                if not match:
                    continue

            similarity = self._cosine_similarity(query_embedding, embedding)
            results.append((memory_id, similarity))

        results.sort(key=lambda x: x[1], reverse=True)
        return results[:k]

    def _cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        try:
            dot_product = sum(a * b for a, b in zip(vec1, vec2))
            norm1 = sum(a * a for a in vec1) ** 0.5
            norm2 = sum(b * b for b in vec2) ** 0.5
            if norm1 == 0 or norm2 == 0:
                return 0.0
            return dot_product / (norm1 * norm2)
        except Exception:
            return 0.0

    def remove_embedding(self, memory_id: str):
        with self._lock:
            self.embeddings.pop(memory_id, None)
            self.metadata.pop(memory_id, None)
            if memory_id in self._id_list:
                self._id_list.remove(memory_id)
            self._rebuild_faiss()

        self._persist()

    def _persist(self):
        try:
            meta_data = {
                "metadata": self.metadata,
                "embeddings": self.embeddings,
            }
            with open(self.meta_file, "w", encoding="utf-8") as f:
                json.dump(meta_data, f, ensure_ascii=False)

            if self._FAISS_AVAILABLE and self._faiss_index is not None:
                try:
                    import faiss
                    faiss.write_index(self._faiss_index, self.index_file)
                except Exception as e:
                    logger.warning(f"[VectorStore] FAISS 索引写入失败: {e}")
        except Exception as e:
            logger.warning(f"[VectorStore] 持久化失败: {e}")

    def get_stats(self) -> Dict[str, Any]:
        return {
            "dimension": self.dimension,
            "vector_count": len(self.embeddings),
            "index_type": "faiss" if self._faiss_index is not None else "python_dict",
            "faiss_available": self._FAISS_AVAILABLE,
        }

    def search_similar_batch(self, query_embeddings: List[List[float]], k: int = 10) -> List[List[Tuple[str, float]]]:
        """批量搜索多个向量，使用FAISS矩阵运算加速
        
        Args:
            query_embeddings: 多个查询向量列表
            k: 每个查询返回的最相似数量
            
        Returns:
            每个查询对应的相似结果列表
        """
        if not query_embeddings or not self.embeddings:
            return [[] for _ in query_embeddings]
        
        if self._faiss_index is not None:
            return self._search_faiss_batch(query_embeddings, k)
        
        return [self._search_python(qe, k) for qe in query_embeddings]
    
    def _search_faiss_batch(self, query_embeddings: List[List[float]], k: int) -> List[List[Tuple[str, float]]]:
        """使用FAISS批量搜索"""
        try:
            import numpy as np
            
            # 构建查询矩阵
            queries = []
            for qe in query_embeddings:
                if len(qe) != self.dimension:
                    if len(qe) > self.dimension:
                        qe = qe[:self.dimension]
                    else:
                        qe = qe + [0.0] * (self.dimension - len(qe))
                queries.append(qe)
            
            query_matrix = np.array(queries, dtype=np.float32)
            norms = np.linalg.norm(query_matrix, axis=1, keepdims=True)
            norms = np.where(norms == 0, 1, norms)
            query_matrix = query_matrix / norms
            
            actual_k = min(k, len(self._id_list))
            if actual_k == 0:
                return [[] for _ in query_embeddings]
            
            scores, indices = self._faiss_index.search(query_matrix, actual_k)
            
            all_results = []
            for i in range(len(query_embeddings)):
                results = []
                for j in range(len(indices[i])):
                    idx = indices[i][j]
                    if idx < 0 or idx >= len(self._id_list):
                        continue
                    memory_id = self._id_list[idx]
                    score = float(scores[i][j])
                    results.append((memory_id, score))
                all_results.append(results)
            return all_results
        except Exception as e:
            logger.warning(f"[VectorStore] FAISS批量搜索失败: {e}，回退到逐条搜索")
            return [self._search_python(qe, k) for qe in query_embeddings]
    
    def get_metadata(self, memory_id: str) -> Dict[str, Any]:
        return self.metadata.get(memory_id, {})


_vector_store_instance: Optional[VectorStore] = None


def get_vector_store() -> VectorStore:
    global _vector_store_instance
    if _vector_store_instance is None:
        _vector_store_instance = VectorStore()
    return _vector_store_instance
