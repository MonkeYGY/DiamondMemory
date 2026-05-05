# Memory Detail Children Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在记忆管理页中，为 `L3` 和 `L5` 详情弹窗补充同分类下的 `L4` 或 `L6` 名称列表，并支持点击切换详情。

**Architecture:** 复用 `MemoryView.vue` 已加载的 `memories` 列表，在前端通过 `layer + category` 计算当前目录型记忆的直属下层条目。详情弹窗增加一个仅在 `L3/L5` 生效的区块，列表项点击后复用现有 `selectedMemory` 状态切换详情，不新增接口与状态管理层。

**Tech Stack:** Vue 3、TypeScript、现有 `MemoryView.vue` 组合式 API 逻辑

---

### Task 1: 扩展详情弹窗的派生数据

**Files:**
- Modify: `frontend/src/renderer/views/MemoryView.vue`
- Test: 手动验证详情弹窗交互

- [ ] **Step 1: 写出失败场景**

```text
当前打开 L3 或 L5 详情时，弹窗中只能看到当前记录正文，看不到该分类下的 L4 或 L6 名称列表，也无法从目录型详情继续点进具体内容。
```

- [ ] **Step 2: 确认失败**

Run: 手动打开记忆管理页，点开任意 `L3` 或 `L5`
Expected: 详情弹窗中没有“该分类下的 L4 内容”或“该分类下的 L6 内容”区块

- [ ] **Step 3: 实现最小派生逻辑**

```ts
const detailChildItems = computed(() => {
  if (!selectedMemory.value) return []
  const layer = getLayer(selectedMemory.value)
  const category = selectedMemory.value.category
  const targetLayer = layer === 3 ? 4 : layer === 5 ? 6 : 0
  if (!targetLayer || !category) return []

  return memories.value.filter(memory => (
    memory.id !== selectedMemory.value.id &&
    getLayer(memory) === targetLayer &&
    memory.category === category
  ))
})
```

- [ ] **Step 4: 验证派生逻辑可驱动 UI**

Run: 保存后在页面中重新打开 `L3` 或 `L5` 详情
Expected: 控制台无报错，后续模板可直接消费 `detailChildItems`

- [ ] **Step 5: 提交**

```bash
git add frontend/src/renderer/views/MemoryView.vue
git commit -m "feat: add child memory list to detail modal"
```

### Task 2: 渲染子项列表并支持切换

**Files:**
- Modify: `frontend/src/renderer/views/MemoryView.vue`
- Test: 手动验证详情弹窗交互

- [ ] **Step 1: 写出失败场景**

```text
即使详情弹窗已有子项数据，模板仍未渲染列表，也没有点击切换到对应 L4/L6 详情的入口。
```

- [ ] **Step 2: 确认失败**

Run: 查看 `MemoryView.vue` 详情弹窗模板
Expected: 没有子项列表区块和点击切换函数

- [ ] **Step 3: 写最小模板与交互实现**

```vue
<div v-if="detailChildSectionTitle" class="detail-related-section">
  <div class="detail-related-header">
    <span>{{ detailChildSectionTitle }}</span>
    <span>{{ detailChildItems.length }} 条</span>
  </div>
  <div v-if="detailChildItems.length > 0" class="detail-related-list">
    <button
      v-for="item in detailChildItems"
      :key="item.id"
      class="detail-related-item"
      @click="openDetail(item)"
    >
      <span>{{ getTitle(item) }}</span>
      <span>{{ getLevelLabel(item) }}</span>
    </button>
  </div>
  <div v-else class="detail-related-empty">暂无对应内容</div>
</div>
```

- [ ] **Step 4: 验证交互**

Run: 点开 `L3` 或 `L5` 详情，再点击列表项
Expected: 弹窗不关闭，标题、元信息和正文切换为对应 `L4` 或 `L6` 的详情

- [ ] **Step 5: 提交**

```bash
git add frontend/src/renderer/views/MemoryView.vue
git commit -m "feat: support detail child item navigation"
```

### Task 3: 样式与空状态收口

**Files:**
- Modify: `frontend/src/renderer/views/MemoryView.vue`
- Test: 手动验证详情弹窗视觉效果

- [ ] **Step 1: 写出失败场景**

```text
新增列表若没有样式，会与正文和底部操作区域混在一起，空状态也不明确。
```

- [ ] **Step 2: 确认失败**

Run: 在未添加样式时预览弹窗
Expected: 子项区块层次不清晰，可点击区域不明显

- [ ] **Step 3: 写最小样式**

```css
.detail-related-section {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid var(--color-border);
}

.detail-related-item {
  width: 100%;
  display: flex;
  justify-content: space-between;
}
```

- [ ] **Step 4: 验证样式**

Run: 分别查看有子项和无子项的 `L3/L5` 详情
Expected: 区块层次清晰，按钮可点击，空状态文案清楚，其他层级详情无变化

- [ ] **Step 5: 提交**

```bash
git add frontend/src/renderer/views/MemoryView.vue
git commit -m "style: polish child list in detail modal"
```
