"""嵌入服务模块

通过 Ollama API 调用 bge-m3 模型生成真正的语义嵌入向量。
当 Ollama 不可用时，自动降级为 TF-IDF 本地编码。
"""
import os
import pickle
import logging
import requests
from typing import List, Optional, Dict
from app.config import settings

logger = logging.getLogger(__name__)


class EmbeddingService:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True

        self._backend = "bge-m3"
        self._dimension = settings.embedding_dimensions
        self._ollama_url = settings.local_llm_endpoint.rstrip("/")
        self._embedding_model = settings.embedding_provider
        self._cache: Dict[str, List[float]] = {}
        self._corpus: Dict[str, set] = {}
        self._idf_cache: Dict[str, float] = {}
        self._ollama_available = False
        self._last_check_time: float = 0
        self._check_cooldown: float = 30.0
        self._index_file = os.path.join(settings.data_directory, "embedding_index.pkl")

        self._check_ollama_embedding()
        self._load_index()

    def _check_ollama_embedding(self) -> bool:
        try:
            resp = requests.get(f"{self._ollama_url}/api/tags", timeout=3)
            if resp.status_code == 200:
                models = [m.get("name", "") for m in resp.json().get("models", [])]
                model_found = any(self._embedding_model in m for m in models)
                if model_found:
                    self._ollama_available = True
                    self._backend = "bge-m3"
                    logger.info(f"[Embedding] Ollama 嵌入模型 {self._embedding_model} 可用，使用语义嵌入")
                else:
                    logger.warning(f"[Embedding] Ollama 中未找到 {self._embedding_model}，将尝试自动拉取")
                    self._ollama_available = True
                    self._backend = "bge-m3"
            else:
                self._ollama_available = False
        except Exception:
            self._ollama_available = False

        if not self._ollama_available:
            self._backend = "tfidf"
            self._dimension = 384
            logger.warning("[Embedding] Ollama 不可用，降级为 TF-IDF 编码")
            
        return self._ollama_available

    def _get_keep_alive(self):
        try:
            from app.storage.sqlite_store import SQLiteStore
            store = SQLiteStore()
            keep_alive = store.get_config("keep_alive")
        except Exception:
            keep_alive = None

        if keep_alive is None or keep_alive == "":
            return -1
        if str(keep_alive).lower() == "false":
            return 0
        if str(keep_alive).strip() == "0":
            return 0
        try:
            return int(keep_alive)
        except (ValueError, TypeError):
            return keep_alive

    def _embed_via_ollama(self, text: str) -> Optional[List[float]]:
        if not text or not text.strip():
            return None
        keep_alive = self._get_keep_alive()
        try:
            resp = requests.post(
                f"{self._ollama_url}/api/embed",
                json={"model": self._embedding_model, "input": text, "keep_alive": keep_alive},
                timeout=30,
            )
            if resp.status_code == 200:
                data = resp.json()
                embeddings = data.get("embeddings", [])
                if embeddings and len(embeddings) > 0:
                    return embeddings[0]
            logger.warning(f"[Embedding] Ollama embed 返回异常 (status={resp.status_code})，尝试 /api/embeddings 兼容端点")
            resp2 = requests.post(
                f"{self._ollama_url}/api/embeddings",
                json={"model": self._embedding_model, "prompt": text, "keep_alive": keep_alive},
                timeout=30,
            )
            if resp2.status_code == 200:
                return resp2.json().get("embedding")
        except requests.exceptions.Timeout:
            logger.warning("[Embedding] Ollama 嵌入请求超时")
        except Exception as e:
            logger.warning(f"[Embedding] Ollama 嵌入请求失败: {e}")
        return None

    def _tokenize(self, text: str) -> List[str]:
        import re
        text = text.lower()
        return re.findall(r'[\u4e00-\u9fff]+|[a-z]+|\d+', text)

    def _compute_idf(self, token: str) -> float:
        import math
        if token in self._idf_cache:
            return self._idf_cache[token]
        n_corpus = max(len(self._corpus), 1)
        n_with_token = sum(1 for tokens in self._corpus.values() if token in tokens)
        idf = math.log((1 + n_corpus) / (1 + n_with_token)) + 1
        self._idf_cache[token] = idf
        return idf

    def _embed_tfidf(self, text: str, memory_id: str = None) -> List[float]:
        tokens = self._tokenize(text)
        if memory_id:
            self._corpus[memory_id] = set(tokens)
        vector = []
        for token in tokens:
            tf = tokens.count(token) / max(len(tokens), 1)
            idf = self._compute_idf(token)
            vector.append(tf * idf)
        if not vector:
            return [0.0] * 384
        if len(vector) >= 384:
            return vector[:384]
        extended = list(vector)
        while len(extended) < 384:
            hash_val = hash(f"{len(extended)}_{extended[-1] if extended else 0}")
            extended.append((hash_val % 1000) / 1000.0)
        return extended

    def embed_text(self, text: str, memory_id: str = None) -> List[float]:
        if not self._ollama_available:
            import time
            now = time.time()
            if now - self._last_check_time >= self._check_cooldown:
                self._last_check_time = now
                self._check_ollama_embedding()

        if not text or not text.strip():
            dim = self._dimension if self._backend == "bge-m3" else 384
            return [0.0] * dim

        cache_key = text.strip()[:500]
        if cache_key in self._cache:
            return self._cache[cache_key]

        if self._backend == "bge-m3" and self._ollama_available:
            result = self._embed_via_ollama(text)
            if result:
                self._dimension = len(result)
                if memory_id:
                    self._corpus[memory_id] = set(self._tokenize(text))
                self._cache[cache_key] = result
                return result
            logger.warning("[Embedding] 语义嵌入失败，降级为 TF-IDF")
            tfidf_vec = self._embed_tfidf(text, memory_id)
            self._cache[cache_key] = tfidf_vec
            return tfidf_vec

        tfidf_vec = self._embed_tfidf(text, memory_id)
        self._cache[cache_key] = tfidf_vec
        return tfidf_vec

    def embed_batch(self, texts: List[str], memory_ids: List[str] = None) -> List[List[float]]:
        if not texts:
            return []
        results = []
        for i, text in enumerate(texts):
            mid = memory_ids[i] if memory_ids and i < len(memory_ids) else None
            results.append(self.embed_text(text, mid))
        return results

    def get_backend_info(self) -> dict:
        return {
            "backend": self._backend,
            "dimension": self._dimension,
            "corpus_size": len(self._corpus),
            "ollama_available": self._ollama_available,
            "embedding_model": self._embedding_model,
        }

    def update_corpus(self, memory_id: str, text: str):
        tokens = self._tokenize(text)
        self._corpus[memory_id] = set(tokens)
        cache_key = text.strip()[:500]
        self._cache.pop(cache_key, None)

    def remove_from_corpus(self, memory_id: str):
        self._corpus.pop(memory_id, None)

    def _load_index(self):
        if os.path.exists(self._index_file):
            try:
                with open(self._index_file, "rb") as f:
                    data = pickle.load(f)
                    self._idf_cache = data.get("idf", {})
                    self._corpus = data.get("corpus", {})
            except Exception:
                self._idf_cache = {}
                self._corpus = {}

    def _save_index(self):
        os.makedirs(os.path.dirname(self._index_file) or ".", exist_ok=True)
        with open(self._index_file, "wb") as f:
            pickle.dump({"idf": self._idf_cache, "corpus": self._corpus}, f)

    def persist(self):
        self._save_index()


embedding_service = EmbeddingService()
