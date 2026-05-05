# OpenClaw 偏好召回兜底 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复 OpenClaw 查询 `categories=preference` 时的召回失败问题：支持 categories 过滤、偏好分层兜底（L4/L6→L2→最近N条L1）、embedding 不可用时中文关键词兜底。

**Architecture:** 在 `backend/app/services/retrieval_service.py` 中增强 `RetrievalService.query()`：补齐 categories 过滤；当 categories 包含 preference 时，走偏好专用三阶段召回并把最近 L1 加入候选池；当 embedding 不可用时跳过语义检索与精排、强制走 FTS/LIKE 并做中文偏好词扩展。通过新增 Settings 开关与 SQLiteStore 辅助方法实现可控兜底。

**Tech Stack:** Python / FastAPI / pytest / SQLite FTS /（可选）Qdrant/FAISS 向量检索

---

## 需要修改的文件（锁定范围）

**Modify:**
- `backend/app/services/retrieval_service.py`：categories 过滤、偏好分层兜底、embedding 降级与缓存策略
- `backend/app/config/settings.py`：新增可配置项
- `backend/app/storage/sqlite_store.py`：新增 `get_recent_by_layer()` 便于 L1 最近N条兜底

**Create (tests):**
- `backend/tests/test_openclaw_preference_recall_fallback.py`

---

## Task 1: SQLiteStore 增加“按层取最近N条”能力

**Files:**
- Modify: `backend/app/storage/sqlite_store.py`
- Test: `backend/tests/test_openclaw_preference_recall_fallback.py`

- [ ] **Step 1: 写失败测试（先不依赖 retrieval_service）**

在 `backend/tests/test_openclaw_preference_recall_fallback.py` 中先写一个最小测试：插入两条 L1 记忆，断言 `get_recent_by_layer(1, 1)` 返回最新一条。

（本 Task 完成后，这个测试应通过；在实现前应失败：方法不存在）

- [ ] **Step 2: 运行测试确认失败**

Run:
```bash
pytest -q backend/tests/test_openclaw_preference_recall_fallback.py -k recent -q
```
Expected: FAIL（AttributeError / ImportError：`get_recent_by_layer` 不存在）

- [ ] **Step 3: 实现 `get_recent_by_layer(layer, limit, include_inactive=False)`**

在 `SQLiteStore` 增加方法，SQL 形态参考现有 `get_by_layer` / `list_all`：

```python
def get_recent_by_layer(self, layer: int, limit: int = 30, include_inactive: bool = False) -> List[Dict[str, Any]]:
    conn = self._get_conn()
    cursor = conn.cursor()
    where_clause = "" if include_inactive else "AND status = 'active' AND (invalid_at IS NULL OR invalid_at = '')"
    cursor.execute(f"""
        SELECT id, content, category, layer, level, tags, source, confidence,
               expires_at, is_pinned, metadata, status, processed_status,
               parent_id, file_path, valid_at, invalid_at, superseded_by,
               created_at, updated_at, access_count, short_name, memory_type
        FROM memories
        WHERE layer = ? {where_clause}
        ORDER BY created_at DESC
        LIMIT ?
    """, (layer, int(limit)))
    rows = cursor.fetchall()
    return [self._row_to_dict(row) for row in rows]
```

- [ ] **Step 4: 重跑测试确认通过**

Run:
```bash
pytest -q backend/tests/test_openclaw_preference_recall_fallback.py -k recent -q
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/storage/sqlite_store.py backend/tests/test_openclaw_preference_recall_fallback.py
git commit -m "feat(retrieval): add sqlite recent-by-layer helper"
```

---

## Task 2: Settings 增加 OpenClaw 偏好兜底相关配置

**Files:**
- Modify: `backend/app/config/settings.py`
- Test: `backend/tests/test_openclaw_preference_recall_fallback.py`

- [ ] **Step 1: 写失败测试（配置存在性 + 默认值）**

在测试里 reload settings 后断言这些字段存在且默认值符合预期：
- `openclaw_preference_enable_l1_fallback == True`
- `openclaw_preference_l1_recent_n == 30`
- `openclaw_preference_disable_cache == True`
- `openclaw_preference_keyword_expands` 含 “喜欢/偏好/不喜欢/习惯/格式/风格”

- [ ] **Step 2: 运行测试确认失败**

Run:
```bash
pytest -q backend/tests/test_openclaw_preference_recall_fallback.py -k settings -q
```
Expected: FAIL（Settings 无字段）

- [ ] **Step 3: 在 Settings(BaseSettings) 中新增字段**

在 `backend/app/config/settings.py` 的 Settings 类里加入（按项目风格放在“检索配置/记忆配置”附近即可）：

```python
# OpenClaw 偏好召回兜底（P0）
openclaw_preference_enable_l1_fallback: bool = True
openclaw_preference_l1_recent_n: int = 30
openclaw_preference_disable_cache: bool = True
openclaw_preference_keyword_expands: List[str] = ["喜欢","偏好","爱","最爱","不喜欢","讨厌","习惯","风格","格式"]
```

- [ ] **Step 4: 重跑测试确认通过**

Run:
```bash
pytest -q backend/tests/test_openclaw_preference_recall_fallback.py -k settings -q
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/config/settings.py backend/tests/test_openclaw_preference_recall_fallback.py
git commit -m "feat(settings): add openclaw preference recall fallback toggles"
```

---

## Task 3: retrieval_service 支持 categories 过滤 + 偏好分层兜底 + embedding 降级

**Files:**
- Modify: `backend/app/services/retrieval_service.py`
- Modify: `backend/app/storage/sqlite_store.py`（如 Task1 未做或需调整）
- Test: `backend/tests/test_openclaw_preference_recall_fallback.py`

- [ ] **Step 1: 写失败测试（核心行为）**

在 `backend/tests/test_openclaw_preference_recall_fallback.py` 增加 3 组测试：

1) **categories 过滤生效（不走 L1 兜底）**
```python
result = retrieval_service.query("偏好", categories=["preference"], limit=10)
assert all(m.get("category") == "preference" for m in result["memories"] if m.get("layer") in (2,4,6))
```
（允许 L1 兜底条目不是 preference 分类；但 L2/L4/L6 必须严格 preference）

2) **embedding 不可用时中文关键词仍命中**
- monkeypatch `embedding_service.embed_text` 返回 `[]`
- 创建一条 `category="preference"` 的 L4 内容包含 “我喜欢用 VSCode”
- query “我喜欢什么” + categories preference，断言结果非空且包含该条

3) **L1 最近N条兜底能进候选池**
- 构造：不写入任何 preference 分类的 L2/L4/L6
- 写入 L1 对话（category="conversation"）包含 “我喜欢用 VSCode”
- query “我喜欢什么” + categories preference
- 断言返回 memories 中存在 layer=1 且包含 “我喜欢”

- [ ] **Step 2: 运行测试确认失败**

Run:
```bash
pytest -q backend/tests/test_openclaw_preference_recall_fallback.py -q
```
Expected: FAIL（categories 不过滤 / 无 L1 兜底 / embedding 降级不生效）

- [ ] **Step 3: 在 retrieval_service.py 增加 3 个小型工具函数（便于保持 query() 可读性）**

建议添加到 `RetrievalService` 类内部（私有方法）：

```python
def _normalize_categories(self, categories: Optional[List[str]]) -> List[str]:
    return [c.strip() for c in (categories or []) if isinstance(c, str) and c.strip()]

def _filter_by_categories(self, items: List[Dict[str, Any]], categories: List[str]) -> List[Dict[str, Any]]:
    if not categories:
        return items
    allow = set(categories)
    return [m for m in items if (m.get("category") in allow)]

def _expand_preference_keywords(self, query_text: str) -> str:
    expands = getattr(settings, "openclaw_preference_keyword_expands", None) or []
    # 简单拼接即可：FTS/LIKE 自行处理匹配
    extra = " ".join([w for w in expands if w and w not in query_text])
    return f"{query_text} {extra}".strip()
```

- [ ] **Step 4: 重构出一个“可复用的混合召回函数”（支持 layer/category 过滤 + degraded）**

新增私有方法（仍放在 `RetrievalService` 内）：

```python
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
) -> List[Dict[str, Any]]:
    # entities
    query_entities = []
    try:
        query_entities = entity_extractor.extract(query_text)
    except Exception:
        pass

    # embedding
    query_embedding = []
    if not degraded_mode:
        try:
            query_embedding = embedding_service.embed_text(query_text) or []
        except Exception:
            query_embedding = []

    if not query_embedding:
        degraded_mode = True

    semantic_results = []
    if not degraded_mode:
        semantic_results = self._semantic_search(query_embedding, limit * 2, include_history=include_history)

    keyword_query = self._expand_preference_keywords(query_text) if force_keyword_expand else query_text
    try:
        keyword_results = self.store.search_by_keyword(keyword_query, limit=limit * 2, include_inactive=include_history)
    except Exception:
        keyword_results = []

    try:
        entity_results = self._entity_search(query_entities, limit * 2, include_history=include_history)
    except Exception:
        entity_results = []

    # categories filter（通用修复点）
    if categories:
        semantic_results = self._filter_by_categories(semantic_results, categories)
        keyword_results = self._filter_by_categories(keyword_results, categories)
        entity_results = self._filter_by_categories(entity_results, categories)

    # layer filter（用于 preference 分阶段）
    if layer_allow:
        semantic_results = [m for m in semantic_results if m.get("layer") in layer_allow]
        keyword_results = [m for m in keyword_results if m.get("layer") in layer_allow]
        entity_results = [m for m in entity_results if m.get("layer") in layer_allow]

    merged = self._merge_results(semantic_results, keyword_results, entity_results)

    # degraded 时跳过精排（避免空跑/不稳定）
    if (not degraded_mode) and getattr(settings, "enable_bge_reranker", True):
        merged = reranker_service.rerank(query_text, merged)

    merged = self._apply_time_decay(merged)
    merged.sort(key=lambda x: x.get("final_score", 0), reverse=True)
    return merged[: max(limit * 2, limit)]
```

- [ ] **Step 5: 在 `query()` 中实现 preference 分层兜底主流程**

修改 `query()`：
1. 解析 `categories_norm = self._normalize_categories(categories)`
2. 判定：
   - `is_preference_query = ("preference" in categories_norm)`
   - `disable_cache = is_preference_query and settings.openclaw_preference_disable_cache`
3. 缓存逻辑：
   - `disable_cache` 为真时：跳过 get/put cache
4. degraded_mode 判定：
   - 以 `embed_text` 是否返回有效向量为准（空/异常即 degraded）
5. 分阶段：
   - stage1 = `_hybrid_candidates(... categories=["preference"], layer_allow={4,6}, force_keyword_expand=degraded_mode)`
   - stage2 = `_hybrid_candidates(... categories=["preference"], layer_allow={2}, force_keyword_expand=degraded_mode)`
   - stage3_l1 = `self.store.get_recent_by_layer(1, limit=settings.openclaw_preference_l1_recent_n, include_inactive=include_history)`
     - 对 stage3_l1 中每条补充字段：`retrieval_reason="L1_recent_fallback"`、`final_score=0.0`
6. 合并候选池：
   - `candidates = stage1 + stage2 + stage3_l1`
   - 按 id 去重（保留第一次出现的）
7. 格式化 + 后置去重：
   - `formatted = self._format_results(candidates)`
   - `filtered = self._post_retrieval_dedup(formatted)`
   - `filtered = filtered[:limit]`
8. 返回字段建议增加：
   - `degraded_mode`
   - `preference_fallback_stage`（如果 stage1 有结果则 "L4/L6"，否则若 stage2 有则 "L2"，否则 "L1_recent"）

- [ ] **Step 6: 重跑测试确认通过**

Run:
```bash
pytest -q backend/tests/test_openclaw_preference_recall_fallback.py -q
```
Expected: PASS

（并跑一个小回归集，避免影响其它检索逻辑）
```bash
pytest -q backend/tests/test_retrieval_history_filter.py backend/tests/test_vector_engine_selection.py -q
```

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/retrieval_service.py backend/tests/test_openclaw_preference_recall_fallback.py
git commit -m "fix(retrieval): preference recall fallback with categories filter and keyword degrade"
```

---

## Task 4（可选，体验增强）: “新建记忆” preference 默认 L2

> 非验收硬性项；如果想把体验一起做掉再开。

**Files:**
- Modify: `frontend/src/renderer/views/MemoryView.vue`

- [ ] **Step 1: 写最小交互逻辑**
当用户在“新建记忆”对话框选择分类为 `preference`（或中文“偏好”映射）时：
- 若当前层级为 L1，则自动切换到 L2（用户仍可手动改回）

- [ ] **Step 2: 前端构建验证**
Run:
```bash
npm -C frontend run build
```
Expected: PASS

- [ ] **Step 3: Commit**
```bash
git add frontend/src/renderer/views/MemoryView.vue
git commit -m "feat(ui): default preference memories to L2 on manual create"
```

---

## 完成后检查清单（与验收对齐）
- [ ] `categories=preference` 查询能稳定命中偏好（不再被其它分类稀释）
- [ ] 未整理阶段：仍能从最近 L1 找到“我喜欢/不喜欢/习惯/格式”等关键细节
- [ ] embedding 不可用时：仍能通过中文关键词命中
- [ ] `pytest -q` 至少关键回归集通过

