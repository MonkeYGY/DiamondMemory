# L4/L6 父级标签显示 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为记忆管理页中的 `L4` 和 `L6` 记忆补充并展示所属 `L3/L5` 父级标签。

**Architecture:** 后端在 `memory_service.list_memories()` 返回结果中统一补充 `parent_label` 字段，避免前端自行推导父级归属。前端 `MemoryView.vue` 复用该标准字段，在列表标签区和详情元信息区统一展示，非 `L4/L6` 保持不变。

**Tech Stack:** Python、FastAPI、SQLiteStore、Vue 3、TypeScript

---

### Task 1: 后端补充父级标签字段

**Files:**
- Modify: `backend/app/services/memory_service.py`
- Test: 手动调用 `/api/memories` 检查返回 JSON

- [ ] **Step 1: 写出失败场景**

```text
当前 `/api/memories` 返回的 `L4/L6` 记忆只有自身的 `category` 和 `tags`，没有明确的 `parent_label` 字段，前端无法直接显示“L3: xxx”或“L5: xxx”。
```

- [ ] **Step 2: 确认失败**

Run: 手动请求 `GET /api/memories`
Expected: `L4/L6` 记录中不存在 `parent_label`

- [ ] **Step 3: 写最小实现**

```python
def _build_parent_label_map(self, parent_layer: int) -> Dict[str, Dict[str, Any]]:
    parent_map = {}
    for memory in self.store.get_by_layer(parent_layer):
        category = (memory.get("category") or "").strip()
        if not category or category in parent_map:
            continue
        parent_map[category] = {
            "layer": parent_layer,
            "name": category,
            "memory_id": memory.get("id")
        }
    return parent_map

def _attach_parent_labels(self, memories: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    l3_map = self._build_parent_label_map(3)
    l5_map = self._build_parent_label_map(5)

    enriched = []
    for memory in memories:
        item = dict(memory)
        category = (item.get("category") or "").strip()
        layer = item.get("layer")
        if layer == 4 and category in l3_map:
            item["parent_label"] = l3_map[category]
        elif layer == 6 and category in l5_map:
            item["parent_label"] = l5_map[category]
        else:
            item["parent_label"] = None
        enriched.append(item)
    return enriched

def list_memories(self, limit: int = 100) -> List[Dict[str, Any]]:
    memories = self.store.list_all(limit=limit)
    return self._attach_parent_labels(memories)
```

- [ ] **Step 4: 验证返回结果**

Run: 再次请求 `GET /api/memories`
Expected: `L4` 记录包含 `{"layer": 3, "name": "..."}` 形式的 `parent_label`，`L6` 记录包含 `{"layer": 5, "name": "..."}`，其他层级为 `null`

- [ ] **Step 5: 提交**

```bash
git add backend/app/services/memory_service.py
git commit -m "feat: add parent labels to memory list response"
```

### Task 2: 前端列表展示父级标签

**Files:**
- Modify: `frontend/src/renderer/views/MemoryView.vue`
- Test: 手动验证记忆列表

- [ ] **Step 1: 写出失败场景**

```text
后端即使补充了 `parent_label`，列表卡片仍只展示普通标签和分类标签，用户看不到 `L3/L5` 父级归属。
```

- [ ] **Step 2: 确认失败**

Run: 刷新记忆管理页
Expected: `L4/L6` 卡片底部没有 `L3: xxx` 或 `L5: xxx`

- [ ] **Step 3: 写最小展示逻辑**

```ts
function getParentLabel(memory: any): { layer: number; name: string } | null {
  const label = memory?.parent_label
  if (!label || !label.name || !label.layer) return null
  return { layer: Number(label.layer), name: String(label.name) }
}

function getParentLabelText(memory: any): string {
  const label = getParentLabel(memory)
  if (!label) return ''
  return `L${label.layer}: ${label.name}`
}
```

```vue
<span v-if="getParentLabel(memory)" class="tag parent-tag">
  {{ getParentLabelText(memory) }}
</span>
```

- [ ] **Step 4: 验证列表**

Run: 查看 `L4` 与 `L6` 列表
Expected: `L4` 显示 `L3: xxx`，`L6` 显示 `L5: xxx`，其他层级不显示该标签

- [ ] **Step 5: 提交**

```bash
git add frontend/src/renderer/views/MemoryView.vue
git commit -m "feat: show parent label in memory cards"
```

### Task 3: 前端详情页展示父级标签并做样式收口

**Files:**
- Modify: `frontend/src/renderer/views/MemoryView.vue`
- Test: 手动验证详情弹窗与样式

- [ ] **Step 1: 写出失败场景**

```text
详情弹窗元信息中仍然没有父级归属，列表和详情展示不一致；即使补充文本，也缺少独立样式区分父级标签和普通分类。
```

- [ ] **Step 2: 确认失败**

Run: 点开任意 `L4` 或 `L6` 详情
Expected: 元信息区没有 `L3: xxx` 或 `L5: xxx`

- [ ] **Step 3: 写最小实现**

```ts
const detailParentLabel = computed(() => {
  if (!selectedMemory.value) return ''
  return getParentLabelText(selectedMemory.value)
})
```

```vue
<span v-if="detailParentLabel" class="meta-item">🧭 {{ detailParentLabel }}</span>
```

```css
.parent-tag {
  background: var(--color-primary-bg, rgba(59, 130, 246, 0.08));
  color: var(--color-primary);
}
```

- [ ] **Step 4: 验证详情与样式**

Run: 分别打开 `L4`、`L6`、`L3` 详情
Expected: `L4/L6` 元信息区显示父级标签，列表中的父级标签样式与普通标签区分明显，`L3` 不显示父级标签

- [ ] **Step 5: 提交**

```bash
git add frontend/src/renderer/views/MemoryView.vue
git commit -m "feat: show parent label in memory detail"
```

