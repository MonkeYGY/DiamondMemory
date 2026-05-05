# L3/L5 分类归并与 L4/L6 文档式阅读 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让快速整理后的 `L3/L5` 自动收敛明显近义分类，并把 `L4/L6` 详情页升级为可读的文档式阅读界面。

**Architecture:** 后端新增一个纯规则的分类标准化服务，只负责“候选分类名 -> 标准分类名”与“历史近义分类合并计划”的判定；真正的记忆迁移、导出重写和删除冗余目录型记忆仍由 `memory_service` 执行，避免循环依赖。前端在 `MemoryView.vue` 保留现有弹窗结构，但把正文渲染切换为轻量 Markdown 渲染，并新增“收敛分类”入口来修复已有历史重复分类。

**Tech Stack:** Python、FastAPI、SQLiteStore、Vue 3、TypeScript、`marked`、`dompurify`、pytest

---

> **Execution note:** 仓库当前已有大量无关改动。每次提交都只 `git add` 本任务列出的文件，禁止整仓提交。

### File Map

**Backend**
- Create: `backend/app/services/category_normalization_service.py`
  - 负责分类名清洗、比较键生成、明显近义匹配、历史分类合并计划生成
- Modify: `backend/app/services/memory_service.py`
  - 在 `L2 -> L4`、`L4 -> L6` 路径接入实时分类标准化
  - 执行历史 `L3/L5` 分类收敛
- Modify: `backend/app/api/memory_routes.py`
  - 暴露“收敛近义分类”的后端入口
- Create: `backend/tests/test_category_normalization_service.py`
  - 覆盖纯规则匹配与合并计划生成
- Create: `backend/tests/test_category_normalization_flow.py`
  - 覆盖 `memory_service` 执行迁移、重导出与删除冗余分类记忆

**Frontend**
- Modify: `frontend/package.json`
  - 增加 `marked` 与 `dompurify`
- Modify: `frontend/package-lock.json`
  - 锁定新增依赖
- Create: `frontend/src/renderer/utils/memory-detail-markdown.ts`
  - 负责详情正文归一化与安全 HTML 渲染
- Modify: `frontend/src/renderer/views/MemoryView.vue`
  - 新增“收敛分类”按钮与状态
  - 接入文档式正文渲染与样式

**Docs**
- Modify: `版本优化记录/版本优化0.8.md`
  - 记录本次实现

### Task 1: 为分类标准化规则补后端测试

**Files:**
- Create: `backend/tests/test_category_normalization_service.py`
- Create: `backend/app/services/category_normalization_service.py`
- Test: `backend/tests/test_category_normalization_service.py`

- [ ] **Step 1: 写失败测试**

```python
import unittest
from unittest.mock import Mock

from app.services.category_normalization_service import CategoryNormalizationService


class CategoryNormalizationServiceTests(unittest.TestCase):
    def build_service(self):
        service = CategoryNormalizationService.__new__(CategoryNormalizationService)
        service.store = Mock()
        return service

    def test_resolve_category_name_reuses_obvious_existing_l3_category(self):
        service = self.build_service()
        service.store.get_by_layer.return_value = [
            {"id": "l3-1", "category": "记忆同步机制"},
            {"id": "l3-2", "category": "Python服务启动"},
        ]

        resolved = service.resolve_category_name("记忆同步自动化", 3)

        self.assertEqual(resolved, "记忆同步机制")

    def test_build_merge_plan_groups_l5_categories_by_same_core_phrase(self):
        service = self.build_service()
        service.store.get_by_layer.side_effect = [
            [
                {"id": "l5-1", "category": "服务部署流程", "content": "服务部署流程"},
                {"id": "l5-2", "category": "服务部署自动化", "content": "服务部署自动化"},
            ],
            [{"id": "l6-1", "category": "服务部署流程", "content": "旧技能"}],
            [],
        ]

        plan = service.build_merge_plan(5)

        self.assertEqual(len(plan), 1)
        self.assertEqual(plan[0]["target_category"], "服务部署流程")
        self.assertEqual(plan[0]["redundant_category_ids"], ["l5-2"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `PYTHONPATH=backend python3 -m pytest backend/tests/test_category_normalization_service.py -q`
Expected: FAIL，原因是 `category_normalization_service.py` 还不存在，`resolve_category_name()` 与 `build_merge_plan()` 尚未实现

- [ ] **Step 3: 写最小规则实现**

```python
import re
from typing import Any, Dict, List

from app.storage import SQLiteStore


class CategoryNormalizationService:
    SOFT_SUFFIXES = ("相关", "整理", "总结", "说明", "方案", "规范")
    CORE_SUFFIXES = ("自动化", "机制", "流程", "方法")
    CATEGORY_LAYER_TO_MEMORY_LAYER = {3: 3, 5: 5}
    CATEGORY_LAYER_TO_CHILD_LAYER = {3: 4, 5: 6}

    def __init__(self):
        self.store = SQLiteStore()

    def _display_name(self, raw_name: str) -> str:
        cleaned = re.sub(r"[\s_\\-/（）()]+", "", (raw_name or "").strip())
        return cleaned or "未分类"

    def _compare_key(self, raw_name: str) -> str:
        cleaned = self._display_name(raw_name)
        for suffix in self.SOFT_SUFFIXES:
            if cleaned.endswith(suffix) and len(cleaned) > len(suffix) + 1:
                cleaned = cleaned[:-len(suffix)]
        for suffix in self.CORE_SUFFIXES:
            if cleaned.endswith(suffix) and len(cleaned) > len(suffix) + 1:
                return cleaned[:-len(suffix)]
        return cleaned

    def resolve_category_name(self, candidate_name: str, category_layer: int) -> str:
        candidate_display = self._display_name(candidate_name)
        candidate_key = self._compare_key(candidate_display)
        existing_memories = self.store.get_by_layer(self.CATEGORY_LAYER_TO_MEMORY_LAYER[category_layer])

        for memory in existing_memories:
            existing_name = (memory.get("category") or "").strip()
            if existing_name and self._compare_key(existing_name) == candidate_key:
                return existing_name

        return candidate_display

    def build_merge_plan(self, category_layer: int) -> List[Dict[str, Any]]:
        category_memories = self.store.get_by_layer(self.CATEGORY_LAYER_TO_MEMORY_LAYER[category_layer])
        child_layer = self.CATEGORY_LAYER_TO_CHILD_LAYER[category_layer]
        grouped: Dict[str, List[Dict[str, Any]]] = {}

        for memory in category_memories:
            category_name = (memory.get("category") or "").strip()
            if not category_name:
                continue
            grouped.setdefault(self._compare_key(category_name), []).append(memory)

        merge_plan = []
        for _, group in grouped.items():
            if len(group) < 2:
                continue
            ranked = sorted(
                group,
                key=lambda item: (
                    -len(self.store.get_memories_by_category(item["category"], child_layer)),
                    len(item["category"]),
                    item["category"],
                ),
            )
            target = ranked[0]
            redundant = [item for item in ranked[1:]]
            merge_plan.append({
                "target_category": target["category"],
                "target_category_id": target["id"],
                "redundant_category_ids": [item["id"] for item in redundant],
                "redundant_category_names": [item["category"] for item in redundant],
                "child_layer": child_layer,
            })

        return merge_plan
```

- [ ] **Step 4: 再跑测试确认通过**

Run: `PYTHONPATH=backend python3 -m pytest backend/tests/test_category_normalization_service.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/app/services/category_normalization_service.py backend/tests/test_category_normalization_service.py
git commit -m "test: cover category normalization rules"
```

### Task 2: 接入实时分类标准化

**Files:**
- Modify: `backend/app/services/memory_service.py`
- Modify: `backend/app/services/category_normalization_service.py`
- Test: `backend/tests/test_category_normalization_service.py`

- [ ] **Step 1: 写失败场景**

```text
当前 L2->L4 和 L4->L6 在生成分类名后直接写入，导致“记忆同步机制 / 记忆同步自动化”这类明显近义分类继续并列增长。
```

- [ ] **Step 2: 确认失败**

Run: 阅读 `backend/app/services/memory_service.py` 中 `_process_single_l2_to_l4()`、`_batch_process_l2_to_l4()`、`_process_single_l4_to_l6()`、`_batch_process_l4_to_l6()`
Expected: 所有路径都直接使用 `_generate_category()` 或 `_generate_skill_category()` 的原始返回值，没有标准化归并步骤

- [ ] **Step 3: 写最小接入实现**

```python
from app.services.category_normalization_service import category_normalization_service


candidate_category = self._generate_category(summary)
normalized_category = category_normalization_service.resolve_category_name(
    candidate_category,
    3,
)

candidate_skill_category = self._generate_skill_category(skill)
normalized_skill_category = category_normalization_service.resolve_category_name(
    candidate_skill_category,
    5,
)
```

- [ ] **Step 4: 补齐所有落点**

```python
self.store.update(related_l4_id, merged_summary, category=normalized_category, reason="合并了新的相关记忆(L2->L4)")
self.store.create(
    memory_id=summary_memory_id,
    content=summary,
    category=normalized_category,
    layer=4,
    ...
)
self.store.create(
    memory_id=category_memory_id,
    content=normalized_category,
    category=normalized_category,
    layer=3,
    ...
)
```

- [ ] **Step 5: 跑规则测试回归**

Run: `PYTHONPATH=backend python3 -m pytest backend/tests/test_category_normalization_service.py -q`
Expected: PASS，且人工阅读代码时能看到 `L3` 使用 `category_layer=3`、`L5` 使用 `category_layer=5`

- [ ] **Step 6: 提交**

```bash
git add backend/app/services/memory_service.py backend/app/services/category_normalization_service.py
git commit -m "feat: normalize generated L3 and L5 categories"
```

### Task 3: 为历史重复分类增加收敛执行流

**Files:**
- Create: `backend/tests/test_category_normalization_flow.py`
- Modify: `backend/app/services/memory_service.py`
- Modify: `backend/app/api/memory_routes.py`
- Test: `backend/tests/test_category_normalization_flow.py`

- [ ] **Step 1: 写失败测试**

```python
import unittest
from unittest.mock import Mock, patch

from app.services.memory_service import MemoryService


class CategoryNormalizationFlowTests(unittest.TestCase):
    def test_normalize_categories_moves_children_and_deletes_redundant_l3(self):
        service = MemoryService.__new__(MemoryService)
        service.store = Mock()
        service.vector_store = Mock()

        service.store.get_memories_by_category.return_value = [
            {"id": "l4-2", "content": "正文", "category": "记忆同步自动化", "layer": 4}
        ]
        service.store.get_by_id.side_effect = lambda memory_id: {
            "l4-2": {"id": "l4-2", "content": "正文", "category": "记忆同步机制", "layer": 4}
        }.get(memory_id)

        with patch("app.services.memory_service.category_normalization_service.build_merge_plan", return_value=[
            {
                "target_category": "记忆同步机制",
                "target_category_id": "l3-1",
                "redundant_category_ids": ["l3-2"],
                "redundant_category_names": ["记忆同步自动化"],
                "child_layer": 4,
            }
        ]), patch("app.services.memory_service.md_export_service.export_memory_to_md") as export_mock, patch.object(service, "delete_memory", return_value=True) as delete_mock:
            result = service.normalize_similar_categories(3)

        self.assertEqual(result["merged_groups"], 1)
        service.store.update.assert_any_call("l4-2", "正文", category="记忆同步机制", reason="L3分类收敛合并")
        export_mock.assert_called_once()
        delete_mock.assert_called_once_with("l3-2")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `PYTHONPATH=backend python3 -m pytest backend/tests/test_category_normalization_flow.py -q`
Expected: FAIL，原因是 `normalize_similar_categories()` 和路由入口尚不存在

- [ ] **Step 3: 写最小后端执行流**

```python
def normalize_similar_categories(self, category_layer: int) -> Dict[str, Any]:
    merge_plan = category_normalization_service.build_merge_plan(category_layer)
    merged_groups = 0
    moved_children = 0

    for group in merge_plan:
        for redundant_name, redundant_id in zip(group["redundant_category_names"], group["redundant_category_ids"]):
            children = self.store.get_memories_by_category(redundant_name, group["child_layer"])
            for child in children:
                self.store.update(
                    child["id"],
                    child["content"],
                    category=group["target_category"],
                    reason=f"L{category_layer}分类收敛合并",
                )
                updated_child = self.store.get_by_id(child["id"])
                if updated_child:
                    md_export_service.export_memory_to_md(updated_child)
                moved_children += 1
            self.delete_memory(redundant_id)
        merged_groups += 1

    return {"merged_groups": merged_groups, "moved_children": moved_children}
```

- [ ] **Step 4: 暴露 API**

```python
@router.post("/organize/normalize-categories")
def normalize_categories():
    return {
        "status": "success",
        "l3": memory_service.normalize_similar_categories(3),
        "l5": memory_service.normalize_similar_categories(5),
    }
```

- [ ] **Step 5: 跑测试确认通过**

Run: `PYTHONPATH=backend python3 -m pytest backend/tests/test_category_normalization_flow.py -q`
Expected: PASS

- [ ] **Step 6: 回归规则测试**

Run: `PYTHONPATH=backend python3 -m pytest backend/tests/test_category_normalization_service.py backend/tests/test_category_normalization_flow.py -q`
Expected: PASS

- [ ] **Step 7: 提交**

```bash
git add backend/app/services/memory_service.py backend/app/api/memory_routes.py backend/tests/test_category_normalization_flow.py
git commit -m "feat: add historical category normalization flow"
```

### Task 4: 在记忆页增加“收敛分类”入口

**Files:**
- Modify: `frontend/src/renderer/views/MemoryView.vue`
- Test: 手动验证按钮与收敛后的刷新行为

- [ ] **Step 1: 写失败场景**

```text
即使后端已经支持历史重复分类收敛，用户在界面上仍没有直接触发入口，只能手动调接口。
```

- [ ] **Step 2: 确认失败**

Run: 打开记忆管理页头部操作区
Expected: 当前只有“新建记忆 / 快速整理 / 深度整理 / 刷新”，没有“收敛分类”按钮

- [ ] **Step 3: 写最小状态与请求实现**

```ts
const isNormalizingCategories = ref(false)

async function normalizeCategories() {
  if (isNormalizingCategories.value) return
  isNormalizingCategories.value = true
  try {
    const result = await apiRequest<any>('/api/memory/organize/normalize-categories', {
      method: 'POST'
    })
    toast.success(`分类收敛完成：L3 ${result.l3.merged_groups} 组，L5 ${result.l5.merged_groups} 组`)
    await fetchMemories()
    requestKnowledgeTreeRefresh()
  } catch (error: any) {
    toast.error('分类收敛失败: ' + error.message)
  } finally {
    isNormalizingCategories.value = false
  }
}
```

- [ ] **Step 4: 写最小按钮接入**

```vue
<button @click="normalizeCategories" :disabled="isNormalizingCategories" class="btn-secondary">
  {{ isNormalizingCategories ? '收敛中...' : '🧹 收敛分类' }}
</button>
```

- [ ] **Step 5: 手动验证**

Run: 打开记忆管理页并点击“🧹 收敛分类”
Expected: 按钮进入 loading 态；成功后弹出统计提示；记忆列表与知识库树刷新

- [ ] **Step 6: 提交**

```bash
git add frontend/src/renderer/views/MemoryView.vue
git commit -m "feat: add manual category normalization action"
```

### Task 5: 为详情页接入 Markdown 渲染与文档式样式

**Files:**
- Modify: `frontend/package.json`
- Modify: `frontend/package-lock.json`
- Create: `frontend/src/renderer/utils/memory-detail-markdown.ts`
- Modify: `frontend/src/renderer/views/MemoryView.vue`
- Test: `npm --prefix frontend run build`

- [ ] **Step 1: 安装依赖并写出失败场景**

```bash
npm --prefix frontend install marked dompurify
```

```text
当前详情页只做浅层正则替换和换行转 <br>，不能正确渲染 Markdown 标题、列表、引用和分段，因此长文阅读仍然像原始文本块。
```

- [ ] **Step 2: 确认失败**

Run: 打开任意含有“主题 / 核心要点 / 详细记录”结构的 `L4` 或 `L6`
Expected: 详情正文更像一整块文本，没有真正的标题层级和列表视觉结构

- [ ] **Step 3: 创建正文渲染工具**

```ts
import DOMPurify from 'dompurify'
import { marked } from 'marked'

marked.setOptions({
  gfm: true,
  breaks: true,
})

export function normalizeMemoryDetailMarkdown(raw: string): string {
  return (raw || '')
    .replace(/^---$/gm, '')
    .replace(/\*\*(?:时间|会话|来源|标签|置信度)\*\*:\s*.+$/gm, '')
    .trim()
}

export function renderMemoryDetailMarkdown(raw: string): string {
  const normalized = normalizeMemoryDetailMarkdown(raw)
  const html = marked.parse(normalized) as string
  return DOMPurify.sanitize(html)
}
```

- [ ] **Step 4: 替换详情页计算属性**

```ts
import { renderMemoryDetailMarkdown } from '../utils/memory-detail-markdown'

const renderedContent = computed(() => {
  if (!selectedMemory.value) return ''
  const raw = selectedMemory.value.content || selectedMemory.value.raw_content || ''
  return renderMemoryDetailMarkdown(raw)
})
```

- [ ] **Step 5: 写文档式样式**

```css
.memory-detail-content {
  max-height: 420px;
  overflow-y: auto;
  padding: 20px 24px;
  background: var(--color-bg);
  border-radius: 10px;
  font-size: 14px;
  line-height: 1.9;
}

.memory-detail-content :deep(h1),
.memory-detail-content :deep(h2),
.memory-detail-content :deep(h3) {
  color: var(--color-text);
  margin: 1.1em 0 0.55em;
}

.memory-detail-content :deep(ul),
.memory-detail-content :deep(ol) {
  padding-left: 1.4em;
}

.memory-detail-content :deep(blockquote) {
  border-left: 3px solid var(--color-primary);
  margin: 1em 0;
  padding-left: 12px;
  color: var(--color-text-secondary);
}
```

- [ ] **Step 6: 跑前端构建确认通过**

Run: `npm --prefix frontend run build`
Expected: PASS

- [ ] **Step 7: 手动验证阅读体验**

Run: 打开一个 `L4` 和一个 `L6` 详情
Expected: 标题、列表、段落、引用正常显示；正文更像文档阅读器；现有 `L3/L5` 关联内容区块仍正常显示

- [ ] **Step 8: 提交**

```bash
git add frontend/package.json frontend/package-lock.json frontend/src/renderer/utils/memory-detail-markdown.ts frontend/src/renderer/views/MemoryView.vue
git commit -m "feat: render memory detail as readable markdown"
```

### Task 6: 回归验证、诊断与记录

**Files:**
- Modify: `版本优化记录/版本优化0.8.md`
- Test: `backend/tests/test_category_normalization_service.py`
- Test: `backend/tests/test_category_normalization_flow.py`

- [ ] **Step 1: 跑后端测试**

```bash
PYTHONPATH=backend python3 -m pytest backend/tests/test_category_normalization_service.py backend/tests/test_category_normalization_flow.py -q
```

Expected: PASS

- [ ] **Step 2: 跑前端构建**

```bash
npm --prefix frontend run build
```

Expected: PASS

- [ ] **Step 3: 跑诊断**

Run: 使用 IDE diagnostics 检查 `backend/app/services/category_normalization_service.py`、`backend/app/services/memory_service.py`、`backend/app/api/memory_routes.py`、`frontend/src/renderer/utils/memory-detail-markdown.ts`、`frontend/src/renderer/views/MemoryView.vue`
Expected: 无新报错

- [ ] **Step 4: 更新版本优化记录**

```md
### 2026-04-27 L3L5 分类归并与 L4L6 文档阅读
- **任务类型**: 优化
- **任务简述**: 为新生成分类增加明显近义自动归并，并提供历史重复分类收敛入口；将 L4/L6 详情页升级为 Markdown 文档式阅读界面。
- **修改文件**:
  - `backend/app/services/category_normalization_service.py`
  - `backend/app/services/memory_service.py`
  - `backend/app/api/memory_routes.py`
  - `backend/tests/test_category_normalization_service.py`
  - `backend/tests/test_category_normalization_flow.py`
  - `frontend/package.json`
  - `frontend/package-lock.json`
  - `frontend/src/renderer/utils/memory-detail-markdown.ts`
  - `frontend/src/renderer/views/MemoryView.vue`
  - `版本优化记录/版本优化0.8.md`
- **完成状态**: 已完成
```

- [ ] **Step 5: 做最终手动联调**

Run: 依次执行“快速整理 -> 收敛分类 -> 打开 L4/L6 详情 -> 切换到知识库查看目录”
Expected: 新分类优先收敛到稳定命名；历史近义分类可手动合并；详情页阅读明显改善；知识库目录与分类迁移保持一致

- [ ] **Step 6: 提交**

```bash
git add 版本优化记录/版本优化0.8.md
git commit -m "docs: record category normalization and detail reader update"
```
