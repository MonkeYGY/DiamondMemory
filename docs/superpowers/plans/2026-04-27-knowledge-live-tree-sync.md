# Knowledge Live Tree Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让知识库中实时显示记忆里的 `L3-L6`，其中 `L3/L5` 只显示为文件夹，`L4/L6` 以 `.md` 文件显示，并在变更后立刻刷新文件树。

**Architecture:** 后端收口 `md_export_service` 的导出语义，使 `L3/L5` 只维护目录、`L4/L6` 维护 Markdown 文件，并补一个全量重建入口修复历史数据。前端通过统一刷新事件让 `FileTree` 在记忆变更和进入知识库时立即重新读取真实文件系统。

**Tech Stack:** FastAPI、Python、Vue 3、TypeScript、Electron 文件系统桥接

---

### Task 1: 修正后端导出语义

**Files:**
- Modify: `backend/app/services/md_export_service.py`
- Modify: `backend/app/services/memory_service.py`
- Test: 手动验证知识库目录结构

- [ ] **Step 1: 写出失败场景**

```text
当前 L3/L5 会被导出成与分类同级的 .md 文件，而不是仅作为目录；L4/L6 路径变化时旧文件也可能残留。
```

- [ ] **Step 2: 确认失败**

Run: 打开知识库文件树，查看 `总结经验/` 和 `技能/`
Expected: 能看到 L3/L5 生成的旧 md，且部分旧路径可能残留

- [ ] **Step 3: 写最小后端实现**

```python
if layer in (3, 5):
    os.makedirs(folder_path, exist_ok=True)
    self.store.update_memory_file_path(memory['id'], None)
    return folder_path

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)
self.store.update_memory_file_path(memory['id'], relative_path)
self.store.update_file_sync_info(relative_path, mtime, file_hash)
```

- [ ] **Step 4: 验证导出行为**

Run: 新建一个 L3、一个 L5、一个 L4、一个 L6
Expected: L3/L5 仅显示目录，L4/L6 仅显示 md，旧文件不再继续产生

- [ ] **Step 5: 提交**

```bash
git add backend/app/services/md_export_service.py backend/app/services/memory_service.py
git commit -m "feat: align knowledge export with L3-L6 mapping"
```

### Task 2: 增加历史数据重建入口

**Files:**
- Modify: `backend/app/services/md_export_service.py`
- Modify: `backend/app/api/knowledge_routes.py`
- Modify: `frontend/src/renderer/api/backend.ts`
- Test: 手动触发重建接口

- [ ] **Step 1: 写出失败场景**

```text
仅修正新导出规则还不够，历史已有的 L3-L6 目录结构不会自动变成最新语义。
```

- [ ] **Step 2: 确认失败**

Run: 修正规则后直接查看旧知识库目录
Expected: 历史旧 md 和旧目录结构仍保留

- [ ] **Step 3: 写最小重建入口**

```python
@router.post("/rebuild-memory-exports")
def rebuild_memory_exports():
    return md_export_service.rebuild_memory_exports()
```

- [ ] **Step 4: 验证重建**

Run: 调用 `/api/knowledge/rebuild-memory-exports`
Expected: 历史 L3/L5 旧 md 被清理，目录结构按新规则补齐

- [ ] **Step 5: 提交**

```bash
git add backend/app/services/md_export_service.py backend/app/api/knowledge_routes.py frontend/src/renderer/api/backend.ts
git commit -m "feat: add rebuild endpoint for knowledge exports"
```

### Task 3: 让文件树立即刷新

**Files:**
- Create: `frontend/src/renderer/utils/knowledge-tree-events.ts`
- Modify: `frontend/src/renderer/components/FileTree.vue`
- Modify: `frontend/src/renderer/views/MemoryView.vue`
- Modify: `frontend/src/renderer/App.vue`
- Test: 手动验证文件树即时更新

- [ ] **Step 1: 写出失败场景**

```text
即使后端已正确写文件，知识库文件树仍主要依赖 5 秒轮询，用户不能在操作后立即看到最新结构。
```

- [ ] **Step 2: 确认失败**

Run: 新建或删除一条 L4/L6，然后立即切到知识库
Expected: 左侧文件树不一定立刻变化

- [ ] **Step 3: 写最小事件与监听实现**

```ts
export const KNOWLEDGE_TREE_REFRESH_EVENT = 'dm:knowledge-tree-refresh'

export function requestKnowledgeTreeRefresh() {
  window.dispatchEvent(new CustomEvent(KNOWLEDGE_TREE_REFRESH_EVENT))
}
```

- [ ] **Step 4: 接入触发点**

Run: 在 `MemoryView.vue` 成功创建、删除、整理完成、分类修改后调用刷新事件；在 `App.vue` 进入知识库页后调用重建接口并触发刷新
Expected: 知识库左侧文件树立刻更新，不等 5 秒轮询

- [ ] **Step 5: 提交**

```bash
git add frontend/src/renderer/utils/knowledge-tree-events.ts frontend/src/renderer/components/FileTree.vue frontend/src/renderer/views/MemoryView.vue frontend/src/renderer/App.vue
git commit -m "feat: refresh knowledge tree immediately after memory changes"
```
