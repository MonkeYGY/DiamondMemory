# L4 High Similarity Merge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让同一 `L3/category` 下高度近似的历史 `L4` 自动归并到一起，减少重复总结碎片。

**Architecture:** 在现有 `deduplicate_existing_l4()` 基础上收紧归并边界：只允许同分类 `L4` 参与候选，并提高归并阈值。继续复用 `_merge_summary()`、向量索引更新和 Markdown 重新导出逻辑，避免引入第二套归并链。

**Tech Stack:** Python、FastAPI 后端服务、现有 SQLiteStore、向量检索、Markdown 导出服务、unittest

---

### Task 1: 为同分类 L4 归并写失败测试

**Files:**
- Modify: `backend/tests/test_md_export_service.py`
- Test: `backend/tests/test_md_export_service.py`

- [ ] **Step 1: Write the failing test**

```python
def test_deduplicate_existing_l4_merges_only_same_category_duplicates(self):
    ...
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && ../backend/venv/bin/python -m unittest backend.tests.test_md_export_service`
Expected: FAIL because current `deduplicate_existing_l4()` still treats cross-category L4 as merge candidates

- [ ] **Step 3: Write minimal implementation**

```python
if sim_mem and sim_mem.get("layer") == 4 and sim_mem.get("category") == current_mem.get("category"):
    duplicates.append(sim_mem)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && ../backend/venv/bin/python -m unittest backend.tests.test_md_export_service`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/tests/test_md_export_service.py backend/app/services/memory_service.py
git commit -m "fix: merge only same-category L4 duplicates"
```

### Task 2: 收紧 L4 归并阈值并保持导出一致性

**Files:**
- Modify: `backend/app/services/memory_service.py`
- Modify: `backend/tests/test_deep_organize_low_power.py`
- Test: `backend/tests/test_md_export_service.py`

- [ ] **Step 1: Write the failing test**

```python
def test_deduplicate_existing_l4_ignores_low_similarity_candidates(self):
    ...
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && ../backend/venv/bin/python -m unittest backend.tests.test_md_export_service`
Expected: FAIL because current threshold still accepts loosely related L4

- [ ] **Step 3: Write minimal implementation**

```python
L4_DEDUP_THRESHOLD = 0.72
if score >= L4_DEDUP_THRESHOLD:
    ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && ../backend/venv/bin/python -m unittest backend.tests.test_md_export_service backend.tests.test_deep_organize_low_power`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/memory_service.py backend/tests/test_md_export_service.py backend/tests/test_deep_organize_low_power.py
git commit -m "fix: tighten L4 high similarity merge criteria"
```

### Task 3: 更新文档与版本记录

**Files:**
- Create: `docs/superpowers/specs/2026-04-27-l4-high-similarity-merge-design.md`
- Create: `docs/superpowers/plans/2026-04-27-l4-high-similarity-merge.md`
- Modify: `版本优化记录/版本优化0.8.md`
- Test: 手动检查版本记录条目

- [ ] **Step 1: Write the docs**

```markdown
## 目标
- 只在同一 L3/category 内自动归并高度近似 L4
```

- [ ] **Step 2: Verify docs are present**

Run: `ls docs/superpowers/specs docs/superpowers/plans`
Expected: 能看到新增的 L4 高相似归并文档

- [ ] **Step 3: Update version record**

```markdown
### 2026-04-27 L4 高相似归并
- **任务类型**: 修复
```

- [ ] **Step 4: Verify record**

Run: `sed -n '1,40p' 版本优化记录/版本优化0.8.md`
Expected: 新条目位于顶部

- [ ] **Step 5: Commit**

```bash
git add docs/superpowers/specs/2026-04-27-l4-high-similarity-merge-design.md docs/superpowers/plans/2026-04-27-l4-high-similarity-merge.md 版本优化记录/版本优化0.8.md
git commit -m "docs: record L4 high similarity merge change"
```
