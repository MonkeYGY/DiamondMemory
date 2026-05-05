"""检索服务模块
钻石记忆系统层级说明：
- L1: 原始数据层（AI软件全量记录，不去重）
- L2: 沉淀层（L1去重得到，增量合并）
- L4: 总结记忆层（系统调用大模型整理L2内容合并总结得到）
- L3: 分类层（L4层进行归类得到，目录层）
- L6: 技能层（L4层进行技能提炼得到）
- L5: 技能分类层（L6层进行归类得到，目录层）

L3-L6层级关系：
- L3目录 -> L4内容（分类->总结）
- L5目录 -> L6内容（技能分类->技能）
"""
import time
import hashlib
import logging
from typing import List, Dict, Any, Optional, Tuple
from app.storage import SQLiteStore
from app.storage import get_active_vector_store
from app.services.embedding_service import embedding_service
from app.services.entity_extractor import entity_extractor
from app.services.reranker_service import reranker_service
from app.config import settings

logger = logging.getLogger(__name__)


class RetrievalService:
    """检索服务类"""
    
    def __init__(self):
        self.store = SQLiteStore()
        self.vector_store = get_active_vector_store()

    def _cosine(self, a: List[float], b: List[float]) -> float:
        if not a or not b:
            return 0.0
        n = min(len(a), len(b))
        dot = 0.0
        na = 0.0
        nb = 0.0
        for i in range(n):
            av = float(a[i] or 0.0)
            bv = float(b[i] or 0.0)
            dot += av * bv
            na += av * av
            nb += bv * bv
        if na <= 0.0 or nb <= 0.0:
            return 0.0
        return dot / ((na ** 0.5) * (nb ** 0.5))

    def query_recent_similar_l1(
        self,
        query_text: str,
        recent_n: int = 30,
        limit: int = 3,
        min_score: float = 0.55,
    ) -> Dict[str, Any]:
        start_time = time.time()
        recent_n = int(recent_n or 30)
        limit = int(limit or 3)
        min_score = float(min_score or 0.0)

        recent = self.store.get_recent_by_layer(1, limit=recent_n, include_inactive=False) or []

        degraded_mode = False
        try:
            query_embedding = embedding_service.embed_text(query_text) or []
        except Exception:
            query_embedding = []
        if not query_embedding:
            degraded_mode = True

        scored: List[Dict[str, Any]] = []
        for mem in recent:
            mid = mem.get("id")
            content = (mem.get("content") or "").strip()
            if not mid or not content:
                continue

            score = 0.0
            if not degraded_mode:
                emb = self.vector_store.get_embedding(mid) if self.vector_store else []
                if emb:
                    score = self._cosine(query_embedding, emb)
            else:
                q = (query_text or "").strip()
                score = 1.0 if (q and (q in content or content in q)) else 0.0

            mem2 = dict(mem)
            mem2["final_score"] = float(score)
            mem2["retrieval_reason"] = "L1_recent_similar"
            scored.append(mem2)

        scored.sort(key=lambda x: x.get("final_score", 0.0), reverse=True)
        filtered = [m for m in scored if float(m.get("final_score") or 0.0) >= min_score]

        formatted = self._format_results(filtered[:limit])
        result_memories = self._post_retrieval_dedup(formatted)[:limit]

        elapsed_ms = round((time.time() - start_time) * 1000, 2)
        return {
            "memories": result_memories,
            "total_tokens": 0,
            "search_time_ms": elapsed_ms,
            "total_candidates": len(scored),
            "entities_found": 0,
            "weight_strategy": "recent_similar_l1",
            "cache_hit": False,
            "degraded_mode": degraded_mode,
            "preference_fallback_stage": None,
        }

    def _normalize_categories(self, categories: Optional[List[str]]) -> List[str]:
        return [c.strip() for c in (categories or []) if isinstance(c, str) and c.strip()]

    def _filter_by_categories(self, items: List[Dict[str, Any]], categories: List[str]) -> List[Dict[str, Any]]:
        """严格按 categories 过滤（用于修复 OpenClaw categories=preference 失效的根因）。"""
        if not categories:
            return items
        allow = set(categories)
        return [m for m in (items or []) if (m.get("category") in allow)]

    def _expand_preference_keywords(self, query_text: str) -> str:
        """为“偏好召回”构造 FTS 友好的 OR 查询串。

        说明：
        - SQLite FTS 对空格默认是 AND，会导致扩展后反而更难命中；
        - 因此这里显式拼 OR，提高“embedding 不可用”时的命中率。
        """
        expands = list(getattr(settings, "openclaw_preference_keyword_expands", None) or [])
        # 兜底关键词：即使用户未配置，也要保证“我喜欢什么”这类 query 能命中偏好内容
        # （与 query() 中的默认偏好关键词保持一致）
        if not expands:
            expands = ["喜欢", "偏好", "不喜欢", "讨厌", "习惯", "风格", "格式", "口味", "喝", "吃"]
        # 不做 “w in query_text” 的子串排除：中文分词/FTS token 可能与字符串包含关系不一致，
        # 过度排除会导致兜底检索反而无法命中（例如 query='我喜欢什么' 含 '喜欢' 子串，但 FTS 并不一定能命中）。
        tokens = [query_text] + [w for w in expands if w]

        parts: List[str] = []
        for t in tokens:
            t = (t or "").strip()
            if not t:
                continue
            # 若包含空格等，使用引号包裹；SQLiteStore.search_by_keyword 会做双引号转义
            if any(ch.isspace() for ch in t):
                parts.append(f"\"{t}\"")
            else:
                parts.append(t)

        return " OR ".join(parts) if parts else query_text

    def _hybrid_candidates(
        self,
        query_text: str,
        *,
        limit: int,
        include_history: bool,
        categories: List[str],
        layer_allow: Optional[set] = None,
        degraded_mode: bool,
        force_keyword_expand: bool,
    ) -> Tuple[List[Dict[str, Any]], bool, List[Dict[str, Any]]]:
        """返回候选池（未 format），并告知是否进入 degraded_mode。

        Returns:
            candidates: List[Dict] (包含 final_score 等字段)
            degraded_mode: bool（若 embedding 不可用则为 True）
            query_entities: List[Dict]（用于上层 GraphRAG/统计）
        """
        # 1) 实体提取（即使 degraded 也可用）
        try:
            query_entities = entity_extractor.extract(query_text)
        except Exception as e:
            logger.warning("实体提取失败: %s", e)
            query_entities = []

        # 2) 嵌入生成（不可用则进入 degraded）
        query_embedding: List[float] = []
        if not degraded_mode:
            try:
                query_embedding = embedding_service.embed_text(query_text) or []
            except Exception as e:
                logger.warning("嵌入生成失败: %s", e)
                query_embedding = []
        if not query_embedding:
            degraded_mode = True
        # degraded 模式下强制启用关键词扩展（即使调用方未显式开启）
        force_keyword_expand = bool(force_keyword_expand) or bool(degraded_mode)

        # 3) 语义检索（degraded 时跳过）
        semantic_results: List[Dict[str, Any]] = []
        if not degraded_mode:
            try:
                semantic_results = self._semantic_search(query_embedding, limit * 2, include_history=include_history)
            except Exception as e:
                logger.warning("向量检索失败: %s", e)
                semantic_results = []

        # 4) 关键词检索（degraded 时强制兜底；采用“多次查询 + 去重”而不是 OR 表达式）
        # 原因：SQLite FTS5 在中文分词场景下对“词级 token”不稳定，且 OR 查询容易引入解析差异；
        # 多次单词查询可以稳定走 LIKE 兜底，保证命中率。
        keyword_results: List[Dict[str, Any]] = []
        keyword_queries: List[str] = [query_text]
        if force_keyword_expand:
            keyword_queries.extend(list(getattr(settings, "openclaw_preference_keyword_expands", None) or []))

        seen_kw = set()
        for q in keyword_queries:
            q = (q or "").strip()
            if not q:
                continue
            try:
                part = self.store.search_by_keyword(q, limit=limit * 2, include_inactive=include_history) or []
            except Exception as e:
                logger.warning("关键词检索失败: %s", e)
                part = []
            for it in part:
                mid = it.get("id")
                if not mid or mid in seen_kw:
                    continue
                seen_kw.add(mid)
                keyword_results.append(it)

        # 5) 实体检索（不依赖 embedding）
        try:
            entity_results = self._entity_search(query_entities, limit * 2, include_history=include_history)
        except Exception as e:
            logger.warning("实体检索失败: %s", e)
            entity_results = []

        # 6) categories 过滤（修复点：原本 categories 参数完全未生效）
        if categories:
            semantic_results = self._filter_by_categories(semantic_results, categories)
            keyword_results = self._filter_by_categories(keyword_results, categories)
            entity_results = self._filter_by_categories(entity_results, categories)

        # 7) layer 过滤（用于 preference 分阶段）
        if layer_allow:
            semantic_results = [m for m in semantic_results if m.get("layer") in layer_allow]
            keyword_results = [m for m in keyword_results if m.get("layer") in layer_allow]
            entity_results = [m for m in entity_results if m.get("layer") in layer_allow]

        merged = self._merge_results(semantic_results, keyword_results, entity_results)

        # 8) GraphRAG 图谱增强（允许 degraded；仅依赖实体）
        if getattr(settings, "graph_rag_enabled", True):
            try:
                from app.services.memory_graph import memory_graph_service
                graph_boosts = memory_graph_service.get_graph_boost_scores(query_entities)
                if graph_boosts:
                    graph_weight = getattr(settings, "graph_rag_weight", 0.3)
                    for item in merged:
                        mem_id = item.get("id")
                        if mem_id in graph_boosts:
                            item["graph_score"] = graph_boosts[mem_id]
                            item["final_score"] = item.get("rrf_score", 0) + graph_weight * graph_boosts[mem_id]
                        else:
                            item["graph_score"] = 0.0
            except Exception as e:
                logger.warning("GraphRAG增强失败: %s", e)

        # 9) degraded 时跳过精排（避免空跑/不稳定）
        if (not degraded_mode) and getattr(settings, "enable_bge_reranker", True):
            merged = reranker_service.rerank(query_text, merged)

        merged = self._apply_time_decay(merged)
        merged.sort(key=lambda x: x.get("final_score", 0), reverse=True)
        return merged[: max(limit * 2, limit)], degraded_mode, query_entities
    
    def query(
        self,
        query_text: str,
        categories: List[str] = None,
        limit: int = 10,
        include_history: bool = False,
    ) -> Dict[str, Any]:
        """混合检索记忆（带缓存）

        关键增强（P0 - OpenClaw 偏好召回）：
        - 修复 categories 参数未生效的问题（严格过滤）
        - categories 包含 preference 时启用分层兜底（L4/L6 → L2 → 最近 N 条 L1）
        - embedding 不可用时跳过语义检索与精排，强制走中文关键词兜底
        """
        start_time = time.time()

        if limit is None:
            limit = settings.retrieval_top_k

        categories_norm = self._normalize_categories(categories)
        # 偏好召回判定：
        # 1) 显式 categories=preference（最可靠）
        # 2) 未显式传 categories 时：根据中文偏好关键词启用兜底（避免“我喜欢什么/咖啡/喝茶”查不到）
        is_preference_query = "preference" in categories_norm if categories_norm else False
        if not is_preference_query:
            keywords = list(getattr(settings, "openclaw_preference_keyword_expands", None) or [])
            # 提供默认关键词（即使配置为空也能工作）
            if not keywords:
                keywords = ["喜欢", "偏好", "不喜欢", "讨厌", "习惯", "风格", "格式", "口味", "喝", "吃"]
            if any(k and k in query_text for k in keywords):
                is_preference_query = True
        disable_cache = bool(is_preference_query) and bool(getattr(settings, "openclaw_preference_disable_cache", False))

        # 历史查询不进缓存（避免污染默认召回）；preference 默认也不进缓存（避免“空结果缓存”影响体验）
        cached = None
        if (not include_history) and (not disable_cache):
            try:
                from app.services.retrieval_cache_service import retrieval_cache_service
                cached = retrieval_cache_service.get_query_result(query_text, categories_norm, limit)
            except Exception:
                cached = None
            if cached:
                cached["cache_hit"] = True
                return cached

        degraded_mode = False
        query_entities: List[Dict[str, Any]] = []

        if is_preference_query and bool(getattr(settings, "openclaw_preference_enable_l1_fallback", True)):
            # preference 分层兜底：L4/L6 → L2 → 最近 N 条 L1
            stage1, degraded_mode, query_entities = self._hybrid_candidates(
                query_text,
                limit=limit,
                include_history=include_history,
                categories=["preference"],
                layer_allow={4, 6},
                degraded_mode=degraded_mode,
                force_keyword_expand=degraded_mode,
            )
            stage2, degraded_mode, query_entities = self._hybrid_candidates(
                query_text,
                limit=limit,
                include_history=include_history,
                categories=["preference"],
                layer_allow={2},
                degraded_mode=degraded_mode,
                force_keyword_expand=degraded_mode,
            )

            l1_recent_n = int(getattr(settings, "openclaw_preference_l1_recent_n", 30) or 30)
            try:
                stage3_l1 = self.store.get_recent_by_layer(1, limit=l1_recent_n, include_inactive=include_history)
            except Exception:
                stage3_l1 = []
            for item in stage3_l1:
                item["retrieval_reason"] = "L1兜底：最近对话补充"
                item["final_score"] = float(item.get("final_score") or 0.0)

            # 合并候选池并按 id 去重（保留 stage1/2 更高质量结果优先）
            seen = set()
            candidates: List[Dict[str, Any]] = []
            for it in (stage1 + stage2 + stage3_l1):
                mid = it.get("id")
                if not mid or mid in seen:
                    continue
                seen.add(mid)
                candidates.append(it)

            preference_fallback_stage = "L1_recent"
            if stage1:
                preference_fallback_stage = "L4/L6"
            elif stage2:
                preference_fallback_stage = "L2"

            formatted_memories = self._format_results(candidates)
            result_memories = self._post_retrieval_dedup(formatted_memories)[:limit]
            total_candidates = len(candidates)

        else:
            # 通用检索：修复 categories 过滤（不含 preference 分层兜底）
            candidates, degraded_mode, query_entities = self._hybrid_candidates(
                query_text,
                limit=limit,
                include_history=include_history,
                categories=categories_norm,
                layer_allow=None,
                degraded_mode=False,
                force_keyword_expand=bool(degraded_mode and is_preference_query),
            )

            # 格式化结果
            formatted_memories = self._format_results(candidates[:limit])
            # 检索后去重过滤（针对 L1/L2 原始碎片）
            result_memories = self._post_retrieval_dedup(formatted_memories)
            total_candidates = len(candidates)
            preference_fallback_stage = None

        self._increment_access_counts(result_memories)

        elapsed_ms = round((time.time() - start_time) * 1000, 2)
        
        result = {
            "memories": result_memories,
            "total_tokens": 0,
            "search_time_ms": elapsed_ms,
            "total_candidates": total_candidates,
            "entities_found": len(query_entities),
            "weight_strategy": "hybrid",
            "cache_hit": False,
            "degraded_mode": degraded_mode,
            "preference_fallback_stage": preference_fallback_stage,
        }

        if (not include_history) and (not disable_cache):
            try:
                from app.services.retrieval_cache_service import retrieval_cache_service
                retrieval_cache_service.put_query_result(query_text, categories_norm, limit, result)
            except Exception:
                pass
        
        return result

    def _is_active_memory(self, memory: Dict[str, Any]) -> bool:
        """默认召回：只允许 active 且未被废止（invalid_at 为空）。"""
        if not memory:
            return False
        if memory.get("status") != "active":
            return False
        invalid_at = memory.get("invalid_at")
        return (invalid_at is None) or (str(invalid_at).strip() == "")

    def _is_history_visible_memory(self, memory: Dict[str, Any]) -> bool:
        """历史可见：允许 active/invalid，但仍过滤 deleted。"""
        if not memory:
            return False
        return memory.get("status") != "deleted"
    
    def _increment_access_counts(self, memories: List[Dict[str, Any]]):
        try:
            for m in memories[:5]:
                mid = m.get("id")
                if mid:
                    self.store.increment_access(mid)
        except Exception:
            pass

    def _post_retrieval_dedup(self, memories: List[Dict[str, Any]], threshold: float = 0.85) -> List[Dict[str, Any]]:
        """检索后去重过滤器（Post-Retrieval Deduplication & Quality Filter）
        
        确保外部 AI 能够安全、干净地检索到 L1 层的所有细节，而不被垃圾数据淹没。
        
        输出排序针对 LLM Context Window 注意力特性优化（"Lost in the Middle"效应）：
        1. 开头（高注意力）：L4/L6 核心知识，建立回答基线
        2. 中间（辅助信息）：L3/L5 分类骨架，提供体系结构
        3. 末尾（高注意力）：L1/L2 近期细节，与用户问题形成推理闭环
        
        增强功能：
        1. 多层级去重过滤（L1/L2 之间、跨层之间）
        2. 质量过滤（过滤过短、无意义、低质量内容）
        3. 时间窗口衰减（近期内重复内容只保留最新）
        4. 内容完整性优先（保留更完整/更长的版本）
        """
        if not memories:
            return []
            
        l1_l2_candidates = []
        l4_l6_memories = []
        l3_l5_memories = []
        
        # 质量过滤阈值
        #
        # 注意：L1/L2 本质是“对话碎片/短期记忆”，会存在大量 <15 字的有效信息（尤其是用户偏好/禁忌等）。
        # 如果一刀切按 15 字过滤，会导致 OpenClaw 这类“我不喜欢什么/我喜欢什么”召回不到刚录入的短偏好。
        # 因此这里对 L1/L2 使用更宽松的阈值，并对“偏好关键词”短句额外放行。
        MIN_CONTENT_LENGTH_DEFAULT = 15  # L3+ 默认阈值
        MIN_CONTENT_LENGTH_L2 = 10
        MIN_CONTENT_LENGTH_L1 = 6
        BLACKLIST_PATTERNS = ["", "null", "undefined", "none", "...", "。。。。", "？？？", "！！！"]
        preference_markers = list(getattr(settings, "openclaw_preference_keyword_expands", None) or [])
        if not preference_markers:
            preference_markers = ["喜欢", "偏好", "不喜欢", "讨厌", "习惯", "风格", "格式", "口味", "喝", "吃"]
        
        # 分离不同层级
        for mem in memories:
            layer = mem.get("layer", 0)
            content = mem.get("content", "").strip()
            clean_content = content.split("]：\n")[-1] if "]：\n" in content else content
            
            # 质量过滤：过滤过短内容（但允许“短偏好句”通过）
            min_len = MIN_CONTENT_LENGTH_DEFAULT
            if layer == 1:
                min_len = MIN_CONTENT_LENGTH_L1
            elif layer == 2:
                min_len = MIN_CONTENT_LENGTH_L2

            is_preference_like = any((m and m in clean_content) for m in preference_markers)
            if len(clean_content) < min_len and not is_preference_like:
                continue
            
            # 质量过滤：过滤无意义内容
            if clean_content.lower() in BLACKLIST_PATTERNS:
                continue
            
            # L4/L6 高层级知识无条件保留（最高优先级，放开头）
            if layer in [4, 6]:
                l4_l6_memories.append(mem)
                continue
            
            # L3/L5 目录层全部保留（放中间，提供分类骨架）
            if layer in [3, 5]:
                l3_l5_memories.append(mem)
                continue
            
            # L1/L2 收集到候选池（放末尾，保留近期细节）
            if layer in [1, 2]:
                l1_l2_candidates.append(mem)
        
        # 对 L1/L2 候选者按时间倒序排序（优先保留最新的）
        l1_l2_candidates.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        
        # 内存中进行轻量级语义去重
        from app.services.embedding_service import embedding_service
        import numpy as np
        
        def cosine_similarity(v1, v2):
            if not v1 or not v2: 
                return 0.0
            v1_arr, v2_arr = np.array(v1), np.array(v2)
            norm_v1 = np.linalg.norm(v1_arr)
            norm_v2 = np.linalg.norm(v2_arr)
            if norm_v1 == 0 or norm_v2 == 0: 
                return 0.0
            return float(np.dot(v1_arr, v2_arr) / (norm_v1 * norm_v2))
            
        retained_l1_l2 = []
        retained_embeddings = []
        retained_content_hashes = set()
        
        # 合并高层知识用于交叉去重
        all_hq_memories = l4_l6_memories + l3_l5_memories
        
        for candidate in l1_l2_candidates:
            content = candidate.get("content", "")
            clean_content = content.split("]：\n")[-1] if "]：\n" in content else content
            
            # 内容哈希去重（精确匹配）
            content_hash = hashlib.md5(clean_content.strip()[:100].encode('utf-8')).hexdigest()
            if content_hash in retained_content_hashes:
                continue
            
            try:
                emb = embedding_service.embed_text(clean_content)
            except:
                emb = None
                
            is_duplicate = False
            if emb:
                for retained_emb in retained_embeddings:
                    if cosine_similarity(emb, retained_emb) >= threshold:
                        is_duplicate = True
                        break
            
            # 额外去重：与已保留的高层知识对比，避免 L1/L2 碎片与 L4/L6 重复
            if not is_duplicate and emb:
                for hq_mem in all_hq_memories:
                    hq_content = hq_mem.get("content", "")
                    hq_clean = hq_content.split("]：\n")[-1] if "]：\n" in hq_content else hq_content
                    if len(clean_content) < len(hq_clean) and len(hq_clean) > 0:
                        # 短内容与高层长内容重叠度高时，过滤短内容
                        if clean_content.strip() in hq_clean.strip():
                            is_duplicate = True
                            break
                        
            if not is_duplicate:
                retained_l1_l2.append(candidate)
                if emb:
                    retained_embeddings.append(emb)
                retained_content_hashes.add(content_hash)
        
        # 按 LLM 注意力最优顺序合并：核心知识 -> 分类骨架 -> 近期细节
        filtered_results = l4_l6_memories + l3_l5_memories + retained_l1_l2
        
        return filtered_results
    
    def _semantic_search(
        self, query_embedding: List[float], k: int = 20, include_history: bool = False
    ) -> List[Dict[str, Any]]:
        """语义检索"""
        if not query_embedding:
            return []
        
        # 搜索相似向量
        similar = self.vector_store.search_similar(query_embedding, k=k)
        
        # 获取完整记忆信息，包含L1-L6层，让外部AI也能获取短期对话记录
        results = []
        for memory_id, score in similar:
            memory = self.store.get_by_id(memory_id)
            if not memory or not (1 <= memory.get("layer", 0) <= 6):
                continue
            if include_history:
                if not self._is_history_visible_memory(memory):
                    continue
            else:
                if not self._is_active_memory(memory):
                    continue
            memory["semantic_score"] = score
            results.append(memory)
        
        return results
    
    def _entity_search(
        self, entities: List[Dict[str, Any]], k: int = 20, include_history: bool = False
    ) -> List[Dict[str, Any]]:
        """实体检索"""
        if not entities:
            return []
        
        all_memories = self.store.list_all(limit=1000, include_inactive=include_history)
        results = []
        
        for memory in all_memories:
            if not (1 <= memory.get("layer", 0) <= 6):
                continue
            if include_history:
                if not self._is_history_visible_memory(memory):
                    continue
            else:
                if not self._is_active_memory(memory):
                    continue
                content = memory.get("content", "").lower()
                match_count = 0
                
                for entity in entities:
                    if entity["text"].lower() in content:
                        match_count += 1
                
                if match_count > 0:
                    memory["entity_score"] = match_count / len(entities)
                    results.append(memory)
        
        results.sort(key=lambda x: x.get("entity_score", 0), reverse=True)
        
        return results[:k]
    
    def _merge_results(self, semantic_results: List[Dict[str, Any]], 
                      keyword_results: List[Dict[str, Any]], 
                      entity_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """融合检索结果 (使用 Reciprocal Rank Fusion - RRF)"""
        seen = {}
        rrf_k = 60  # RRF 平滑常数
        
        def process_ranked_results(results_list, score_key, weight=1.0):
            # 按各自的分数排序以获取排名
            sorted_results = sorted(results_list, key=lambda x: x.get(score_key, 0), reverse=True)
            for rank, item in enumerate(sorted_results):
                item_id = item["id"]
                if item_id not in seen:
                    # 初始化
                    seen[item_id] = item.copy()
                    seen[item_id]["rrf_score"] = 0.0
                    seen[item_id]["semantic_score"] = 0.0
                    seen[item_id]["keyword_score"] = 0.0
                    seen[item_id]["entity_score"] = 0.0
                
                # 记录原始分数用于调试或参考
                seen[item_id][score_key] = item.get(score_key, 0)
                
                # 计算 RRF 分数并叠加 (引入权重支持对不同召回源的偏好)
                seen[item_id]["rrf_score"] += weight * (1.0 / (rrf_k + rank + 1))

        process_ranked_results(semantic_results, "semantic_score", settings.vector_weight)
        
        for idx, item in enumerate(keyword_results):
            if "keyword_score" not in item:
                item["keyword_score"] = len(keyword_results) - idx
        process_ranked_results(keyword_results, "keyword_score", settings.bm25_weight)
        
        process_ranked_results(entity_results, "entity_score", settings.entity_weight)
        
        for item_id, item in seen.items():
            item["final_score"] = item["rrf_score"]
            reasons = []
            if item.get("semantic_score", 0) > 0:
                reasons.append(f"语义相似({round(item['semantic_score'], 3)})")
            if item.get("keyword_score", 0) > 0:
                reasons.append(f"关键词匹配({round(item['keyword_score'], 3)})")
            if item.get("entity_score", 0) > 0:
                reasons.append(f"实体关联({round(item['entity_score'], 3)})")
            item["retrieval_reason"] = " + ".join(reasons) if reasons else "综合排序"
        
        return list(seen.values())
    
    def _apply_time_decay(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """应用时间衰减（艾宾浩斯遗忘曲线模型）"""
        from app.services.memory_decay_service import memory_decay_service

        for item in results:
            try:
                item["final_score"] = memory_decay_service.compute_final_score(
                    item.get("final_score", 0), item
                )
            except Exception:
                pass

        return results
    
    def _format_results(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """格式化结果"""
        formatted = []
        
        for item in results:
            layer = item.get("layer", 3)
            original_content = item.get("content", "")
            metadata = item.get("metadata") or {}
            memory_type = item.get("memory_type") or metadata.get("memory_type")
            citations: List[Dict[str, Any]] = []
            
            # 为外部AI添加上下文前缀，区分短期记忆与长期经验
            if memory_type == "doc_chunk":
                context_prefix = "[用户文档原文片段]：\n"
                citations = [
                    {
                        "chunk_id": item.get("id"),
                        "doc_id": metadata.get("doc_id"),
                        "chunk_index": metadata.get("chunk_index"),
                        "page": metadata.get("page"),
                        "start_offset": metadata.get("start_offset"),
                        "end_offset": metadata.get("end_offset"),
                        "source_path": metadata.get("source_path"),
                        "source_mtime": metadata.get("source_mtime"),
                        "source_hash": metadata.get("source_hash"),
                    }
                ]
            elif memory_type == "doc_structured":
                context_prefix = "[用户文档结构化索引]：\n"
                citations = list(metadata.get("citations") or [])
            elif layer in [1, 2]:
                context_prefix = f"[近期短期记忆 / 未经整理的对话碎片 (L{layer})]：\n"
            elif layer in [4, 5, 6]:
                context_prefix = f"[长期核心经验 / 结构化知识 (L{layer})]：\n"
            else:
                context_prefix = f"[目录或索引 (L{layer})]：\n"
                
            formatted_content = f"{context_prefix}{original_content}"
            
            formatted.append({
                "id": item["id"],
                "content": formatted_content,
                "category": item.get("category", ""),
                "layer": layer,
                "level": item.get("level", 1),
                "relevance_score": round(item.get("final_score", 0), 3),
                "source": item.get("source"),
                "created_at": item.get("created_at", ""),
                "tags": item.get("tags", []),
                "access_count": item.get("access_count", 0),
                "is_pinned": item.get("is_pinned", False),
                "metadata": metadata,
                "citations": citations,
            })
        
        return formatted
    
    def search_by_tags(self, tags: List[str], limit: int = 10) -> Dict[str, Any]:
        """按标签搜索"""
        all_memories = self.store.list_all(limit=1000)
        results = []
        
        for memory in all_memories:
            # 允许检索所有层级的记忆
            if memory.get("layer", 0) >= 1 and memory.get("layer", 0) <= 6:
                mem_tags = memory.get("tags", [])
                if any(tag in mem_tags for tag in tags):
                    layer = memory.get("layer", 3)
                    original_content = memory.get("content", "")
                    
                    if layer in [1, 2]:
                        context_prefix = f"[近期短期记忆 / 未经整理的对话碎片 (L{layer})]：\n"
                    elif layer in [4, 5, 6]:
                        context_prefix = f"[长期核心经验 / 结构化知识 (L{layer})]：\n"
                    else:
                        context_prefix = f"[目录或索引 (L{layer})]：\n"
                        
                    formatted_content = f"{context_prefix}{original_content}"
                    
                    results.append({
                        "id": memory["id"],
                        "content": formatted_content,
                        "category": memory.get("category", ""),
                        "layer": layer,
                        "level": memory.get("level", 1),
                        "source": memory.get("source"),
                        "created_at": memory.get("created_at", ""),
                        "tags": memory.get("tags", []),
                        "access_count": memory.get("access_count", 0),
                        "is_pinned": memory.get("is_pinned", False),
                    })
        
        return {
            "memories": results[:limit],
            "total": len(results)
        }
    
    def search_recent(self, days: int = 7, limit: int = 10, 
                      category: str = None) -> Dict[str, Any]:
        """搜索近期记忆"""
        import datetime
        from datetime import datetime as dt
        
        cutoff = (dt.now() - datetime.timedelta(days=days)).isoformat()
        
        # 简单实现，实际应该在数据库层面过滤
        all_memories = self.store.list_all(limit=1000)
        results = []
        
        for memory in all_memories:
            # 只处理L1-L6层的记忆
            if memory.get("layer", 0) >= 1 and memory.get("layer", 0) <= 6:
                created_at = memory.get("created_at")
                if created_at and created_at >= cutoff:
                    if category and memory.get("category") != category:
                        continue
                    layer = memory.get("layer", 3)
                    original_content = memory.get("content", "")
                    
                    if layer in [1, 2]:
                        context_prefix = f"[近期短期记忆 / 未经整理的对话碎片 (L{layer})]：\n"
                    elif layer in [4, 5, 6]:
                        context_prefix = f"[长期核心经验 / 结构化知识 (L{layer})]：\n"
                    else:
                        context_prefix = f"[目录或索引 (L{layer})]：\n"
                        
                    formatted_content = f"{context_prefix}{original_content}"
                    
                    results.append({
                        "id": memory["id"],
                        "content": formatted_content,
                        "category": memory.get("category", ""),
                        "layer": layer,
                        "level": memory.get("level", 1),
                        "source": memory.get("source"),
                        "created_at": memory.get("created_at", ""),
                        "tags": memory.get("tags", []),
                        "access_count": memory.get("access_count", 0),
                        "is_pinned": memory.get("is_pinned", False),
                    })
        
        return {
            "memories": results[:limit],
            "total": len(results),
            "days": days
        }


# 全局检索服务实例
retrieval_service = RetrievalService()
