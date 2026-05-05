# Knowledge Realtime Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让知识库中的“总结经验/技能”在影响 `L3-L6` 的操作完成后，立即与记忆内容保持一致。

**Architecture:** 将“后端重建知识库映射 + 前端刷新文件树”封装成一个统一的前端同步方法，并加上并发锁，避免重复重建。记忆页和知识库页入口都复用这同一条同步链，保证行为一致。

**Tech Stack:** Vue 3、TypeScript、现有后端重建导出接口、Electron 文件树刷新事件

---

### Task 1: 封装统一实时同步方法

**Files:**
- Modify: `frontend/src/renderer/utils/knowledge-tree-events.ts`
- Modify: `frontend/src/renderer/api/backend.ts`
- Test: 手动验证同步方法

- [ ] **Step 1: 写出失败场景**

```text
当前不同页面各自只会触发文件树刷新事件，未统一调用后端重建导出，所以知识库可能仍读取到旧文件系统状态。
```

- [ ] **Step 2: 确认失败**

Run: 查看 `MemoryView.vue` 和 `App.vue` 中的知识库刷新调用
Expected: 只看到 `requestKnowledgeTreeRefresh()`，没有统一的“先重建后刷新”方法

- [ ] **Step 3: 写最小实现**

```ts
let syncPromise: Promise<void> | null = null

export async function syncKnowledgeTree() {
  if (syncPromise) return syncPromise
  syncPromise = (async () => {
    await rebuildKnowledgeMemoryExports()
    requestKnowledgeTreeRefresh()
  })().finally(() => {
    syncPromise = null
  })
  return syncPromise
}
```

- [ ] **Step 4: 验证同步方法**

Run: 调用一次 `syncKnowledgeTree()`
Expected: 后端重建接口被调用，成功后触发文件树刷新事件

- [ ] **Step 5: 提交**

```bash
git add frontend/src/renderer/utils/knowledge-tree-events.ts frontend/src/renderer/api/backend.ts
git commit -m "feat: add unified knowledge tree sync helper"
```

### Task 2: 接入记忆页所有关键触发点

**Files:**
- Modify: `frontend/src/renderer/views/MemoryView.vue`
- Test: 手动验证新建/删除/分类/整理完成后的同步

- [ ] **Step 1: 写出失败场景**

```text
记忆页中的关键操作成功后只是刷新记忆列表或文件树，没有统一确保后端知识库映射已经重建。
```

- [ ] **Step 2: 确认失败**

Run: 检查 `createMemory`、`deleteMemory`、`saveCategory`、`deleteCategory`、整理完成回调
Expected: 仍在直接调用 `requestKnowledgeTreeRefresh()`

- [ ] **Step 3: 写最小接入实现**

```ts
await fetchMemories()
await syncKnowledgeTree()
```

- [ ] **Step 4: 验证关键触发点**

Run: 分别执行新建、删除、分类修改、快速整理、深度整理
Expected: 每次成功后知识库都立刻和最新 `L3-L6` 一致

- [ ] **Step 5: 提交**

```bash
git add frontend/src/renderer/views/MemoryView.vue
git commit -m "feat: sync knowledge tree after memory mutations"
```

### Task 3: 接入知识库页入口

**Files:**
- Modify: `frontend/src/renderer/App.vue`
- Test: 手动验证进入知识库页时的行为

- [ ] **Step 1: 写出失败场景**

```text
即使记忆页未触发同步，进入知识库页时也应保证能补齐一次最新映射，但当前入口逻辑未与统一同步方法收口。
```

- [ ] **Step 2: 确认失败**

Run: 查看 `App.vue` 的 `ensureKnowledgeTreeReady`
Expected: 直接调用重建接口和刷新事件，没有复用统一同步方法

- [ ] **Step 3: 写最小收口实现**

```ts
await syncKnowledgeTree()
hasKnowledgeExportsRebuilt.value = true
```

- [ ] **Step 4: 验证入口行为**

Run: 切换到知识库页
Expected: 首次进入时会自动补齐同步，之后复用统一逻辑

- [ ] **Step 5: 提交**

```bash
git add frontend/src/renderer/App.vue
git commit -m "refactor: reuse unified knowledge sync in app entry"
```
