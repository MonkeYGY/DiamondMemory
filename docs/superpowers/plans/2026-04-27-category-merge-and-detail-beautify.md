# Category Merge Refinement & Detail Beautify Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refine category normalization rules with prefixes and synonym mappings, and upgrade the memory detail view to a modern document reader style.

**Architecture:** 
1. Backend: Enhance `CategoryNormalizationService` to strip prefixes and map common synonyms (e.g., Config -> 配置) during key generation.
2. Frontend: Adjust CSS in `MemoryView.vue` to render metadata as modern badges and style markdown elements (pre, code, blockquote) for better readability.

**Tech Stack:** Python, Vue 3, marked, CSS

---

### Task 1: Refine Backend Normalization Rules

**Files:**
- Modify: `backend/app/services/category_normalization_service.py`
- Modify: `backend/tests/test_category_normalization_service.py`

- [ ] **Step 1: Write the failing tests for new rules**

```python
    def test_compare_key_removes_prefixes_and_maps_synonyms(self):
        service = CategoryNormalizationService()
        self.assertEqual(service._compare_key("关于Git配置"), "GIT配置")
        self.assertEqual(service._compare_key("Deploy流程"), "部署")
        self.assertEqual(service._compare_key("如何修复Bug"), "修复")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=backend ./backend/venv/bin/python -m unittest backend.tests.test_category_normalization_service -v`
Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

Update `CategoryNormalizationService`:
- Add `SOFT_PREFIXES = ("关于", "如何", "怎样", "浅析", "深入")`
- Add `SYNONYM_MAPPINGS = {"CONFIG": "配置", "DEPLOY": "部署", "发布": "部署", "BUG": "修复", "FIX": "修复", "ERROR": "报错", "ERR": "报错"}`
- Update `_compare_key` to:
  1. Upper case
  2. Strip prefixes
  3. Strip suffixes
  4. Replace matched strings using `SYNONYM_MAPPINGS` (e.g. if key exactly matches or contains, depending on safe boundary, simplest is exact match after stripping for root words, but for safety, we can do substring replacement or exact match. Exact match of the remaining root is safer). Let's do exact match or `if cleaned == k: cleaned = v`.

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=backend ./backend/venv/bin/python -m unittest backend.tests.test_category_normalization_service -v`
Expected: PASS

### Task 2: Enhance Markdown Renderer Configuration

**Files:**
- Modify: `frontend/src/renderer/utils/memory-detail-markdown.ts`

- [ ] **Step 1: Update marked configuration**

Ensure `marked` is configured with `gfm: true` and `breaks: true` to support standard markdown features like tables and code blocks properly. (It likely already is, but verify and explicitly set it if needed, and ensure `dompurify` allows `<pre>`, `<code>`, `<table>`, `<th>`, `<td>`, `<tr>`).

### Task 3: Beautify Detail View CSS

**Files:**
- Modify: `frontend/src/renderer/views/MemoryView.vue`

- [ ] **Step 1: Update CSS for Metadata Badges**

Target `.detail-metadata` and `.meta-item`. Give them a more modern, pill-like appearance.
```css
.detail-metadata {
  gap: 8px;
  background: transparent;
  padding: 0 0 16px 0;
  border-bottom: 1px solid var(--color-border);
  margin-bottom: 16px;
  border-radius: 0;
}
.detail-metadata .meta-item {
  font-size: 12px;
  background: var(--color-bg);
  border: 1px solid var(--color-border);
  padding: 4px 12px;
  border-radius: 999px;
}
```

- [ ] **Step 2: Update CSS for Markdown Body**

Target `.memory-detail-content`.
```css
.memory-detail-content {
  font-size: 15px;
  line-height: 1.75;
  padding: 10px 0;
  background: transparent;
  border: none;
}
.memory-detail-content :deep(pre) {
  background: var(--color-surface);
  padding: 16px;
  border-radius: 8px;
  overflow-x: auto;
  border: 1px solid var(--color-border);
  margin: 1.2em 0;
}
.memory-detail-content :deep(pre code) {
  background: transparent;
  padding: 0;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 13px;
}
.memory-detail-content :deep(blockquote) {
  background: var(--color-primary-bg, rgba(59, 130, 246, 0.05));
  border-left: 4px solid var(--color-primary);
  margin: 1.5em 0;
  padding: 12px 16px;
  border-radius: 0 8px 8px 0;
  color: var(--color-text);
}
.memory-detail-content :deep(table) {
  width: 100%;
  border-collapse: collapse;
  margin: 1.5em 0;
}
.memory-detail-content :deep(th), .memory-detail-content :deep(td) {
  border: 1px solid var(--color-border);
  padding: 8px 12px;
  text-align: left;
}
.memory-detail-content :deep(th) {
  background: var(--color-surface);
}
```

- [ ] **Step 3: Build Frontend**

Run: `npm --prefix frontend run build`
Expected: Success

### Task 4: Record and Diagnostics

- [ ] **Step 1: Run global diagnostics**

- [ ] **Step 2: Update project log**
Append the completion status to `版本优化记录/版本优化0.8.md`.
