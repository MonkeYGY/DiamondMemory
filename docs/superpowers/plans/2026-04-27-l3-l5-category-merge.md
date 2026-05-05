# L3/L5 Category Merge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 `L3/L5` 增加“只合并明显近义分类”的实时归并与历史收敛能力，减少分类树碎片化。

**Architecture:** 新增一个轻量分类标准化服务，负责比较键生成、明显近义匹配和主分类决策。`memory_service` 在 `L2 -> L4` 与 `L4 -> L6` 生成分类时调用该服务做实时归并；同时通过新增 API 提供历史 `L3/L5` 手动收敛入口，并复用现有 Markdown 导出与空目录清理逻辑保持数据库和知识库一致。

**Tech Stack:** Python、FastAPI、现有 `MemoryService`、`md_export_service`、`unittest`

---

### Task 1: 建立分类标准化服务与规则测试

**Files:**
- Create: `backend/app/services/category_normalization_service.py`
- Create: `backend/tests/test_category_normalization_service.py`
- Test: `backend/tests/test_category_normalization_service.py`

- [ ] **Step 1: 写失败测试**

```python
import unittest

from app.services.category_normalization_service import CategoryNormalizationService


class CategoryNormalizationServiceTests(unittest.TestCase):
    def setUp(self):
        self.service = CategoryNormalizationService()

    def test_prefers_existing_category_for_obvious_synonym(self):
        existing = ["知识库同步", "OpenClaw配置"]
        result = self.service.normalize_category_name("知识库同步机制", layer=3, existing_categories=existing)
        self.assertEqual(result["resolved_name"], "知识库同步")
        self.assertTrue(result["matched_existing"])

    def test_keeps_distinct_category_when_topic_differs(self):
        existing = ["知识库同步", "知识库写入"]
        result = self.service.normalize_category_name("知识库部署", layer=3, existing_categories=existing)
        self.assertEqual(result["resolved_name"], "知识库部署")
        self.assertFalse(result["matched_existing"])
```

- [ ] **Step 2: 跑测试确认失败**

Run: `PYTHONPATH=backend backend/venv/bin/python -m unittest backend.tests.test_category_normalization_service -v`
Expected: FAIL，原因是 `category_normalization_service.py` 尚不存在

- [ ] **Step 3: 写最小实现**

```python
class CategoryNormalizationService:
    _WEAK_SUFFIXES = ("相关", "说明", "整理", "总结")
    _NORMALIZED_SUFFIXES = {"机制": "流程", "方案": "流程", "规范": "流程"}

    def normalize_category_name(self, candidate: str, layer: int, existing_categories: list[str]) -> dict:
        cleaned = self._clean_name(candidate)
        candidate_key = self._build_compare_key(cleaned)
        for existing in existing_categories:
            if self._build_compare_key(existing) == candidate_key:
                return {"resolved_name": existing, "matched_existing": True}
        return {"resolved_name": cleaned, "matched_existing": False}
```

- [ ] **Step 4: 再跑测试确认通过**

Run: `PYTHONPATH=backend backend/venv/bin/python -m unittest backend.tests.test_category_normalization_service -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/app/services/category_normalization_service.py backend/tests/test_category_normalization_service.py
git commit -m "feat: add category normalization service"
```

### Task 2: 接入实时归并到 L2->L4 与 L4->L6

**Files:**
- Modify: `backend/app/services/memory_service.py`
- Modify: `backend/app/services/category_normalization_service.py`
- Create: `backend/tests/test_memory_service_category_merge.py`
- Test: `backend/tests/test_memory_service_category_merge.py`

- [ ] **Step 1: 写失败测试**

```python
import unittest
from unittest.mock import patch

from app.services.memory_service import MemoryService


class MemoryServiceCategoryMergeTests(unittest.TestCase):
    def test_resolve_l3_category_prefers_existing_stable_name(self):
        service = MemoryService.__new__(MemoryService)
        service.store = type("Store", (), {
            "get_by_layer": lambda self, layer: [{"category": "知识库同步"}] if layer == 3 else []
        })()

        with patch("app.services.memory_service.category_normalization_service.normalize_category_name") as normalize:
            normalize.return_value = {"resolved_name": "知识库同步", "matched_existing": True}
            result = service._resolve_structured_category_name("知识库同步机制", layer=3)
            self.assertEqual(result, "知识库同步")
```

- [ ] **Step 2: 跑测试确认失败**

Run: `PYTHONPATH=backend backend/venv/bin/python -m unittest backend.tests.test_memory_service_category_merge -v`
Expected: FAIL，原因是 `MemoryService` 还没有 `_resolve_structured_category_name()`

- [ ] **Step 3: 写最小实现**

```python
from app.services.category_normalization_service import category_normalization_service

def _resolve_structured_category_name(self, candidate: str, layer: int) -> str:
    existing_categories = []
    for memory in self.store.get_by_layer(layer):
        category = (memory.get("category") or "").strip()
        if category and category not in existing_categories:
            existing_categories.append(category)
    result = category_normalization_service.normalize_category_name(candidate, layer=layer, existing_categories=existing_categories)
    return result["resolved_name"]
```

- [ ] **Step 4: 接入现有生成路径并验证**

Run: `PYTHONPATH=backend backend/venv/bin/python -m unittest backend.tests.test_memory_service_category_merge -v`
Expected: PASS，且 `_generate_category()` / `_generate_skill_category()` 产出的候选分类在落库前会先经过 `_resolve_structured_category_name()`

- [ ] **Step 5: 提交**

```bash
git add backend/app/services/memory_service.py backend/app/services/category_normalization_service.py backend/tests/test_memory_service_category_merge.py
git commit -m "feat: normalize l3 l5 categories in realtime"
```

### Task 3: 实现历史 L3/L5 收敛服务逻辑

**Files:**
- Modify: `backend/app/services/memory_service.py`
- Modify: `backend/app/services/category_normalization_service.py`
- Create: `backend/tests/test_memory_service_category_consolidation.py`
- Test: `backend/tests/test_memory_service_category_consolidation.py`

- [ ] **Step 1: 写失败测试**

```python
import unittest

from app.services.memory_service import MemoryService


class MemoryServiceCategoryConsolidationTests(unittest.TestCase):
    def test_merge_layer_categories_moves_children_to_primary_category(self):
        service = MemoryService.__new__(MemoryService)
        moved = []
        deleted = []
        service.store = type("Store", (), {
            "get_by_layer": lambda self, layer: (
                [{"id": "l3a", "category": "知识库同步"}, {"id": "l3b", "category": "知识库同步机制"}] if layer == 3 else
                [{"id": "l4a", "category": "知识库同步机制"}] if layer == 4 else []
            ),
            "update": lambda self, memory_id, **kwargs: moved.append((memory_id, kwargs["category"])),
            "get_by_id": lambda self, memory_id: {"id": memory_id, "category": "知识库同步机制", "layer": 4, "content": "demo"},
        })()
        service.delete_memory = lambda memory_id: deleted.append(memory_id)
        service.cleanup_empty_categories = lambda **kwargs: {"memories_deleted": 1, "directories_deleted": 1}

        result = service.merge_similar_categories(layer=3, max_groups=10)
        self.assertEqual(result["children_moved"], 1)
        self.assertIn(("l4a", "知识库同步"), moved)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `PYTHONPATH=backend backend/venv/bin/python -m unittest backend.tests.test_memory_service_category_consolidation -v`
Expected: FAIL，原因是 `merge_similar_categories()` 尚不存在

- [ ] **Step 3: 写最小实现**

```python
def merge_similar_categories(self, layer: int, max_groups: int = 10) -> Dict[str, Any]:
    grouped = category_normalization_service.group_similar_categories(...)
    for group in grouped[:max_groups]:
        primary = group["primary"]
        duplicates = group["duplicates"]
        child_layer = 4 if layer == 3 else 6
        for duplicate_name in duplicates:
            self._move_child_memories_to_fallback(duplicate_name, child_layer, primary, "分类归并迁移")
    cleanup = self.cleanup_empty_categories()
    return {"groups_merged": len(grouped), "cleanup": cleanup}
```

- [ ] **Step 4: 再跑测试确认通过**

Run: `PYTHONPATH=backend backend/venv/bin/python -m unittest backend.tests.test_memory_service_category_consolidation -v`
Expected: PASS，且收敛结果会统计近义组、迁移条数和目录清理结果

- [ ] **Step 5: 提交**

```bash
git add backend/app/services/memory_service.py backend/app/services/category_normalization_service.py backend/tests/test_memory_service_category_consolidation.py
git commit -m "feat: add historical l3 l5 category consolidation"
```

### Task 4: 暴露手动历史收敛 API

**Files:**
- Modify: `backend/app/api/memory_routes.py`
- Modify: `backend/app/services/memory_service.py`
- Create: `backend/tests/test_memory_routes_category_merge.py`
- Test: `backend/tests/test_memory_routes_category_merge.py`

- [ ] **Step 1: 写失败测试**

```python
import unittest
from fastapi.testclient import TestClient

from app.api.memory_routes import router
from fastapi import FastAPI


class MemoryRoutesCategoryMergeTests(unittest.TestCase):
    def test_merge_categories_endpoint_calls_service(self):
        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)
        response = client.post("/memory/organize/categories/merge", json={"layer": 3, "max_groups": 5})
        self.assertEqual(response.status_code, 200)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `PYTHONPATH=backend backend/venv/bin/python -m unittest backend.tests.test_memory_routes_category_merge -v`
Expected: FAIL，原因是接口不存在

- [ ] **Step 3: 写最小实现**

```python
@router.post("/organize/categories/merge")
def merge_categories(layer: str = Body("all"), max_groups: int = Body(10)):
    if layer == "all":
        l3 = memory_service.merge_similar_categories(layer=3, max_groups=max_groups)
        l5 = memory_service.merge_similar_categories(layer=5, max_groups=max_groups)
        return {"status": "success", "l3": l3, "l5": l5}
    return {"status": "success", "result": memory_service.merge_similar_categories(layer=int(layer), max_groups=max_groups)}
```

- [ ] **Step 4: 再跑测试确认通过**

Run: `PYTHONPATH=backend backend/venv/bin/python -m unittest backend.tests.test_memory_routes_category_merge -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/app/api/memory_routes.py backend/app/services/memory_service.py backend/tests/test_memory_routes_category_merge.py
git commit -m "feat: expose category merge api"
```

### Task 5: 回归验证与文档收尾

**Files:**
- Modify: `版本优化记录/版本优化0.8.md`
- Test: `backend/tests/test_category_normalization_service.py`
- Test: `backend/tests/test_memory_service_category_merge.py`
- Test: `backend/tests/test_memory_service_category_consolidation.py`
- Test: `backend/tests/test_memory_routes_category_merge.py`

- [ ] **Step 1: 运行全部新增测试**

```bash
PYTHONPATH=backend backend/venv/bin/python -m unittest \
  backend.tests.test_category_normalization_service \
  backend.tests.test_memory_service_category_merge \
  backend.tests.test_memory_service_category_consolidation \
  backend.tests.test_memory_routes_category_merge -v
```

- [ ] **Step 2: 检查诊断**

Run: 使用 IDE diagnostics 检查 `backend/app/services/category_normalization_service.py`、`backend/app/services/memory_service.py`、`backend/app/api/memory_routes.py`
Expected: 无新报错

- [ ] **Step 3: 更新版本优化记录**

```md
### 2026-04-27 L3L5 分类归并实现
- **任务类型**: 优化
- **任务简述**: 为 L3/L5 增加明显近义分类实时归并与历史收敛入口，降低分类树碎片化。
```

- [ ] **Step 4: 手动验证**

Run: 手动触发一次整理，再调用分类收敛接口
Expected: 新产生的近义分类会优先复用稳定类名；历史收敛会迁移子项并清理空目录

- [ ] **Step 5: 提交**

```bash
git add 版本优化记录/版本优化0.8.md
git commit -m "docs: record l3 l5 category merge work"
```
