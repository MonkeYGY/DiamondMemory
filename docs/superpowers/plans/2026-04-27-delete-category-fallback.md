# 删除 L3/L5 分类自动迁移到默认分类 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让分类管理中删除 `L3/L5` 分类时，相关 `L4/L6` 自动迁移到默认分类，并阻止默认分类被误删。

**Architecture:** 将分类删除逻辑从 `config_routes.py` 直接调用 `store.delete_category()`，收口到 `memory_service` 的服务层编排方法中。服务层负责默认分类自动创建、默认分类删除保护、关联记忆迁移、向量元数据同步和 Markdown 重导出；前端只更新删除确认文案与错误提示展示。

**Tech Stack:** Python、FastAPI、SQLiteStore、Vue 3、TypeScript

---

### Task 1: 后端收口分类删除编排

**Files:**
- Modify: `backend/app/services/memory_service.py`
- Modify: `backend/app/api/config_routes.py`
- Test: 手动调用 `DELETE /api/config/categories/{category_id}`

- [ ] **Step 1: 写出失败场景**

```text
当前从“管理分类体系”删除分类时，只会删除 categories 表记录，不会把相关 L4/L6 迁移到默认分类，也不会阻止删除默认分类本身。
```

- [ ] **Step 2: 确认失败**

Run: 通过前端或接口删除一个有子内容的 L3/L5 分类
Expected: 分类被删，但对应 L4/L6 没有自动迁移到 `未归档/未分类`

- [ ] **Step 3: 在服务层写最小删除编排**

```python
def _get_default_category_name(self, layer: int) -> Optional[str]:
    if layer == 3:
        return "未归档"
    if layer == 5:
        return "未分类"
    return None

def _ensure_default_category_exists(self, layer: int) -> Dict[str, Any]:
    default_name = self._get_default_category_name(layer)
    for category in self.store.get_categories_by_layer(layer):
        if category.get("name") == default_name:
            return category
    return self.store.create_category(
        category_id=str(uuid.uuid4()),
        name=default_name,
        layer=layer,
        level=1,
        parent_id=None
    )

def delete_managed_category(self, category_id: str) -> Dict[str, Any]:
    category = self.store.get_category_by_id(category_id)
    if not category:
        return {"error": "NOT_FOUND", "message": "分类不存在"}
    if (category["layer"], category["name"]) in [(3, "未归档"), (5, "未分类")]:
        return {"error": "PROTECTED_CATEGORY", "message": "默认分类不可删除"}
    self._ensure_default_category_exists(category["layer"])
    # 迁移关联记忆
    # 删除分类记录
    return {"message": "分类删除成功"}
```

- [ ] **Step 4: 改接口为调用服务层**

```python
@router.delete("/categories/{category_id}")
def delete_category(category_id: str):
    result = memory_service.delete_managed_category(category_id)
    if result.get("error") == "NOT_FOUND":
        raise HTTPException(status_code=404, detail=result["message"])
    if result.get("error"):
        raise HTTPException(status_code=400, detail=result["message"])
    return result
```

- [ ] **Step 5: 验证接口返回**

Run: 删除普通分类与默认分类各一次
Expected: 普通分类返回成功；默认分类返回 400 且提示“默认分类不可删除”

- [ ] **Step 6: 提交**

```bash
git add backend/app/services/memory_service.py backend/app/api/config_routes.py
git commit -m "feat: route category deletion through memory service"
```

### Task 2: 实现迁移、元数据同步与重导出

**Files:**
- Modify: `backend/app/services/memory_service.py`
- Test: 手动删除带内容的分类并检查数据库与导出目录

- [ ] **Step 1: 写出失败场景**

```text
即使分类删除改为服务层处理，如果没有批量迁移逻辑，L4/L6 仍然留在旧分类名下，知识库导出目录和向量元数据也不会同步更新。
```

- [ ] **Step 2: 确认失败**

Run: 删除有内容的 L3/L5 分类
Expected: 相关 L4/L6 的 `category` 不会自动改成 `未归档/未分类`

- [ ] **Step 3: 复用并扩展现有迁移逻辑**

```python
def _move_child_memories_to_fallback(self, category_name: str, child_layer: int, fallback_category: str, reason: str) -> None:
    child_memories = self.store.get_by_layer(child_layer)
    for child in child_memories:
        if child.get("category") != category_name:
            continue
        self.store.update(child["id"], category=fallback_category, reason=reason)
        child_old_meta = self.vector_store.get_metadata(child["id"]) or {}
        child_old_meta["category"] = fallback_category
        current_embedding = self.vector_store.get_embedding(child["id"])
        if current_embedding:
            self.vector_store.save_embedding(child["id"], current_embedding, child_old_meta)
        updated_child = self.store.get_by_id(child["id"])
        if updated_child:
            md_export_service.export_memory_to_md(updated_child)
```

```python
if category["layer"] == 3:
    self._move_child_memories_to_fallback(category["name"], 4, "未归档", "L3分类被删除，移入未归档")
elif category["layer"] == 5:
    self._move_child_memories_to_fallback(category["name"], 6, "未分类", "L5分类被删除，移入未分类")
```

- [ ] **Step 4: 在删除前确保默认分类存在**

```python
default_category = self._ensure_default_category_exists(category["layer"])
if not default_category:
    return {"error": "DEFAULT_CATEGORY_CREATE_FAILED", "message": "默认分类创建失败"}
```

- [ ] **Step 5: 验证迁移闭环**

Run: 删除一个普通 `L3`，再删除一个普通 `L5`
Expected: 对应 `L4 -> 未归档`、`L6 -> 未分类`，知识库导出目录中的文件移动到默认目录

- [ ] **Step 6: 提交**

```bash
git add backend/app/services/memory_service.py
git commit -m "feat: move child memories to default categories on delete"
```

### Task 3: 更新前端删除提示文案

**Files:**
- Modify: `frontend/src/renderer/views/MemoryView.vue`
- Test: 手动点击分类删除确认框

- [ ] **Step 1: 写出失败场景**

```text
当前删除确认文案仍提示“会使这些记忆变为无分类”，与新的后端行为不一致。
```

- [ ] **Step 2: 确认失败**

Run: 打开“管理分类体系”，点击删除任意分类
Expected: 确认文案仍是旧描述

- [ ] **Step 3: 写最小前端文案逻辑**

```ts
async function deleteCategory(cat: any) {
  const fallbackLabel = cat.layer === 3 ? '未归档' : cat.layer === 5 ? '未分类' : '默认分类'
  if (!confirm(`确定要删除分类 "${cat.name}" 吗？该分类下的内容不会被删除，但会自动移动到「${fallbackLabel}」下。`)) return
  // existing delete request
}
```

- [ ] **Step 4: 验证交互**

Run: 分别尝试删除 L3 与 L5 分类
Expected: 文案分别提示迁移到 `未归档` 或 `未分类`；删除默认分类时显示后端错误提示

- [ ] **Step 5: 提交**

```bash
git add frontend/src/renderer/views/MemoryView.vue
git commit -m "feat: update category delete fallback messaging"
```

