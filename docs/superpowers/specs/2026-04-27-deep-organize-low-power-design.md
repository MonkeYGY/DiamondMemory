# 深度整理低功耗改造设计

## 背景

当前“深度整理”会在一次后台任务中连续执行全量低质量清理、L4/L6 全局去重、L1-L6 提炼、重分类和目录清理。由于这些阶段都包含大量向量检索、本地模型推理和文件导出，任务启动后容易长时间占满 CPU，影响用户日常使用电脑。

## 目标

- 保留“深度整理”的能力边界，不删除现有整理环节
- 将默认深度整理改为低功耗慢速执行，允许更长耗时换取更温和的资源占用
- 通过配置控制每个阶段的处理上限和阶段暂停时长，避免再次出现一口气全量猛跑
- 前端文案明确告知用户：现在是低功耗慢速整理，而不是高负载整理

## 方案

### 后端执行策略

- 在 `backend/app/services/memory_service.py` 中保留现有 `organize_entire_knowledge_base()` 入口
- 为深度整理增加默认低功耗路径
- 低功耗路径按固定阶段顺序执行：
  - 低质量清理
  - L4 去重
  - L6 去重
  - L1 -> L2
  - L2 -> L4
  - L4 -> L6
  - 空分类/空目录清理
- 每个阶段执行完成后主动暂停一小段时间，再进入下一阶段

### 限流方式

- 为全库扫描型操作增加“本轮处理上限”
  - `remove_low_quality_memories(limit=...)`
  - `deduplicate_existing_l4(limit=...)`
  - `deduplicate_existing_l6(limit=...)`
  - `reclassify_default_l4(limit=...)`
  - `cleanup_empty_categories(memory_limit=..., directory_limit=...)`
- 为分批提炼型操作增加“本轮最多处理多少批”
  - `_batch_process_l1_to_l2_smart(max_batches=...)`
  - `_batch_process_l2_to_l4_smart(max_batches=...)`
  - `_batch_process_l4_to_l6_smart(max_batches=...)`

### 配置项

- 在 `backend/app/config/settings.py` 中新增低功耗整理配置，使用保守默认值
- 配置项覆盖：
  - 是否启用默认低功耗深度整理
  - 阶段间暂停毫秒数
  - 清理、去重、重分类的单轮处理上限
  - L1/L2/L4 提炼的单轮批次数上限
  - 空分类记忆和空目录的单轮清理上限

### 前端提示

- 在 `frontend/src/renderer/views/MemoryView.vue` 中更新深度整理确认弹窗文案
- 将“高负载”表述改为“低功耗慢速”
- 向用户明确说明：单次深度整理可能只推进一部分全库任务，需要多次执行逐步完成

## 结果结构

- 深度整理接口仍返回成功结果
- 返回值中补充各阶段实际处理量，便于后续 UI 或日志展示
- 单次任务未覆盖完整知识库时，不视为失败，只表示本轮推进完成

## 边界处理

- 快速整理 `quick_organize()` 不改行为，继续作为高频增量整理入口
- 这次不引入 CPU/空闲检测，不额外增加系统级依赖
- 若未来需要“高性能全量整理”模式，可在当前低功耗实现之上追加开关，而不是回退默认行为

## 影响范围

- 修改 `backend/app/config/settings.py`
- 修改 `backend/app/services/memory_service.py`
- 修改 `frontend/src/renderer/views/MemoryView.vue`
- 新增 `backend/tests/test_deep_organize_low_power.py`

## 验证

- 后端单测验证低功耗深度整理会按阶段传入限额参数并执行阶段暂停
- 手动触发深度整理，确认任务能够启动且返回正常
- 查看前端确认弹窗，确认文案已改为低功耗慢速整理
- 手动重复执行多次深度整理，确认知识库会逐步推进，而不是一次性高负载全量处理
