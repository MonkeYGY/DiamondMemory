"""检索缓存服务

基于LRU策略的检索结果缓存，支持：
1. 热门查询结果缓存
2. TTL过期自动清理
3. 嵌入向量缓存
4. 缓存命中率统计
"""
import hashlib
import time
import threading
import logging
from typing import Dict, Any, Optional, List, Tuple
from collections import OrderedDict
from app.config import settings

logger = logging.getLogger(__name__)


class LRUCache:
    def __init__(self, max_size: int = 500, ttl_seconds: int = 300):
        self._cache: OrderedDict = OrderedDict()
        self._max_size = max_size
        self._ttl = ttl_seconds
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            if key in self._cache:
                entry = self._cache[key]
                if time.time() - entry["timestamp"] < self._ttl:
                    self._cache.move_to_end(key)
                    self._hits += 1
                    return entry["value"]
                else:
                    del self._cache[key]
            self._misses += 1
            return None

    def put(self, key: str, value: Any):
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
            self._cache[key] = {"value": value, "timestamp": time.time()}
            while len(self._cache) > self._max_size:
                self._cache.popitem(last=False)

    def invalidate(self, key: str):
        with self._lock:
            self._cache.pop(key, None)

    def clear(self):
        with self._lock:
            self._cache.clear()
            self._hits = 0
            self._misses = 0

    def stats(self) -> Dict[str, Any]:
        total = self._hits + self._misses
        return {
            "size": len(self._cache),
            "max_size": self._max_size,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": round(self._hits / total, 3) if total > 0 else 0,
        }


class RetrievalCacheService:
    def __init__(self):
        self._query_cache = LRUCache(
            max_size=getattr(settings, "retrieval_cache_max_size", 500),
            ttl_seconds=getattr(settings, "retrieval_cache_ttl_seconds", 300)
        )
        self._embedding_cache = LRUCache(
            max_size=getattr(settings, "embedding_cache_max_size", 2000),
            ttl_seconds=3600
        )

    @staticmethod
    def _hash_key(text: str) -> str:
        return hashlib.md5(text.encode("utf-8")).hexdigest()

    def get_query_result(self, query_text: str, categories: List[str] = None,
                          limit: int = 10) -> Optional[Dict[str, Any]]:
        if not getattr(settings, "retrieval_cache_enabled", True):
            return None
        key = self._hash_key(f"{query_text}|{categories}|{limit}")
        return self._query_cache.get(key)

    def put_query_result(self, query_text: str, categories: List[str] = None,
                          limit: int = 10, result: Dict[str, Any] = None):
        if not getattr(settings, "retrieval_cache_enabled", True):
            return
        key = self._hash_key(f"{query_text}|{categories}|{limit}")
        self._query_cache.put(key, result)

    def get_embedding(self, text: str) -> Optional[List[float]]:
        key = self._hash_key(text[:500])
        return self._embedding_cache.get(key)

    def put_embedding(self, text: str, embedding: List[float]):
        key = self._hash_key(text[:500])
        self._embedding_cache.put(key, embedding)

    def invalidate_memory(self, memory_id: str):
        self._query_cache.clear()

    def clear_all(self):
        self._query_cache.clear()
        self._embedding_cache.clear()

    def get_stats(self) -> Dict[str, Any]:
        return {
            "query_cache": self._query_cache.stats(),
            "embedding_cache": self._embedding_cache.stats(),
        }


retrieval_cache_service = RetrievalCacheService()
