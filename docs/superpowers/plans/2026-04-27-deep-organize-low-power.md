# Deep Organize Low Power Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将默认“深度整理”改为低功耗慢速执行，通过阶段限额和阶段暂停降低 CPU 峰值。

**Architecture:** 保留现有 `organize_entire_knowledge_base()` 入口，但在其内部新增默认低功耗执行路径。低功耗路径按阶段串行推进，每个阶段只处理有限对象或批次，并在阶段之间主动暂停；快速整理保持原状。前端仅更新确认弹窗文案，不增加新的交互开关。

**Tech Stack:** Python、FastAPI、现有 `MemoryService`、Vue 3、TypeScript、pytest

---

### Task 1: 为低功耗深度整理补测试

**Files:**
- Create: `backend/tests/test_deep_organize_low_power.py`
- Modify: `backend/app/services/memory_service.py`
- Test: `backend/tests/test_deep_organize_low_power.py`

- [ ] **Step 1: 写失败测试**

```python
def test_deep_organize_low_power_runs_stages_with_limits(monkeypatch):
    ...
    assert calls == [
        ("remove_low_quality_memories", 3),
        ("sleep", 0.25),
        ("deduplicate_existing_l4", 4),
    ]
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m pytest backend/tests/test_deep_organize_low_power.py -q`
Expected: FAIL，原因是当前深度整理不会向各阶段传入低功耗限额，也不会在阶段间暂停

- [ ] **Step 3: 写最小实现让测试通过**

```python
if settings.deep_organize_low_power_enabled:
    return self._organize_entire_knowledge_base_low_power()
```

- [ ] **Step 4: 再跑测试确认通过**

Run: `python3 -m pytest backend/tests/test_deep_organize_low_power.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/tests/test_deep_organize_low_power.py backend/app/services/memory_service.py
git commit -m "test: cover low power deep organize flow"
```

### Task 2: 改造后端低功耗整理调度

**Files:**
- Modify: `backend/app/config/settings.py`
- Modify: `backend/app/services/memory_service.py`
- Test: `backend/tests/test_deep_organize_low_power.py`

- [ ] **Step 1: 写失败场景**

```text
当前深度整理会在一次任务中把所有阶段尽可能跑完，无法通过配置控制单轮推进量和阶段暂停。
```

- [ ] **Step 2: 确认失败**

Run: 阅读 `organize_entire_knowledge_base()` 和各阶段方法
Expected: 现有代码缺少低功耗专用配置、阶段暂停和单轮限额参数

- [ ] **Step 3: 写最小实现**

```python
deep_organize_low_power_enabled: bool = True
deep_organize_stage_pause_ms: int = 1200
deep_organize_dedup_limit: int = 8
deep_organize_reclassify_limit: int = 6
deep_organize_cleanup_memory_limit: int = 12
deep_organize_cleanup_directory_limit: int = 6
deep_organize_l1_batches_per_run: int = 1
deep_organize_l2_batches_per_run: int = 1
deep_organize_l4_batches_per_run: int = 1
```

- [ ] **Step 4: 验证行为**

Run: `python3 -m pytest backend/tests/test_deep_organize_low_power.py -q`
Expected: PASS，且结果中包含各阶段处理量

- [ ] **Step 5: 提交**

```bash
git add backend/app/config/settings.py backend/app/services/memory_service.py backend/tests/test_deep_organize_low_power.py
git commit -m "feat: add low power deep organize mode"
```

### Task 3: 更新前端提示文案

**Files:**
- Modify: `frontend/src/renderer/views/MemoryView.vue`
- Test: 手动验证深度整理确认弹窗

- [ ] **Step 1: 写失败场景**

```text
深度整理确认弹窗仍提示“高负载”，与新实现的低功耗慢速行为不一致。
```

- [ ] **Step 2: 确认失败**

Run: 打开记忆管理页，触发“深度整理”确认弹窗
Expected: 仍显示“预计耗时 (高负载)”和全量猛跑描述

- [ ] **Step 3: 写最小文案改动**

```vue
<h4>⏱️ 预计耗时 (低功耗慢速)</h4>
<p>系统会分阶段慢速推进整理任务，CPU 更温和，但整体耗时更长。单次整理可能只推进一部分全库任务，建议按需多次执行。</p>
```

- [ ] **Step 4: 验证文案**

Run: 刷新页面后重新打开确认弹窗
Expected: 文案与实际行为一致，仍能正常点击开始整理

- [ ] **Step 5: 提交**

```bash
git add frontend/src/renderer/views/MemoryView.vue
git commit -m "copy: update deep organize low power messaging"
```

### Task 4: 回归验证与收尾

**Files:**
- Modify: `版本优化记录/版本优化0.8.md`
- Test: `backend/tests/test_deep_organize_low_power.py`

- [ ] **Step 1: 跑后端测试**

```bash
python3 -m pytest backend/tests/test_deep_organize_low_power.py -q
```

- [ ] **Step 2: 跑诊断**

Run: 使用 IDE diagnostics 检查 `backend/app/config/settings.py`、`backend/app/services/memory_service.py`、`frontend/src/renderer/views/MemoryView.vue`
Expected: 无新报错

- [ ] **Step 3: 更新版本优化记录**

```md
### 2026-04-27 深度整理低功耗化
- **任务类型**: 优化
- **任务简述**: 将默认深度整理改为分阶段慢跑，限制单轮处理量并加入阶段暂停，降低 CPU 峰值。
```

- [ ] **Step 4: 手动验证**

Run: 手动触发一次深度整理
Expected: 任务可启动；弹窗提示为低功耗慢速；整理结果正常返回

- [ ] **Step 5: 提交**

```bash
git add 版本优化记录/版本优化0.8.md
git commit -m "docs: record low power deep organize update"
```
