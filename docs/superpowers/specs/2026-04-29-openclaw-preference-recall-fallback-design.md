<!--
钻石记忆系统 - 设计文档（Spec）
主题：OpenClaw 偏好召回修复（L1 兜底 + 中文关键词兜底）
日期：2026-04-29
关联：版本优化0.9.1 - Backlog ID=16（P0）
-->

# OpenClaw 偏好召回修复（L1 兜底 + 中文关键词兜底）设计

## 背景与问题

### 问题现象
- 明明 L4 已有 `preference` 内容，但 OpenClaw 仍反馈“没有偏好”
- 在“未整理（只有 L1/L2）”阶段更明显
- 当嵌入模型不可用/返回空时，中文查询命中率显著下降

### 根因定位（现状）
- `/memory/query` → `memory_service.query_memory()` → `retrieval_service.query()`
- 当前 `retrieval_service.query()` **未使用 `categories` 参数做任何过滤**，导致：
  - OpenClaw 以 `categories=preference` 查询时，结果仍可能混入其它分类/类型
  - 偏好相关结果被“非偏好内容”稀释，甚至 TopK 内看不到偏好
- 当前检索流程对“embedding 不可用”缺少明确降级策略（仍然会走语义链路/精排链路的部分逻辑）

## 目标与验收标准

### 目标
1. 即使未触发整理，也能从 L1 全量记录中保底召回用户偏好关键细节
2. 中文查询时即使嵌入模型不可用，也能通过关键词检索稳定命中
3. 默认召回仍保持“干净”：L1 进入上下文前必须经过质量过滤/去重/时间排序

### 验收标准（对应 Backlog ID=16）
- ✅ 未触发整理也能召回近期 L1 关键细节（例如最近 30 条）
- ✅ 无嵌入模型时仍能用中文关键词命中（FTS/LIKE 兜底）
- ✅ 对外接口兼容：OpenClaw 继续调用 `/memory/query`（不引入新必选接口）

## 设计原则
- **最小破坏**：不改调用方协议，仅增强服务端检索策略
- **分层兜底**：偏好召回优先结构化层（L4/L6），再降级到 L2，再到 L1
- **强制质量过滤**：L1 兜底必须走现有 `post_retrieval_dedup`（或其增强版）
- **明确降级路径**：embedding 不可用时不走语义检索与精排（避免空跑/不稳定）

## 方案对比与结论

### 方案 A：后端为主（推荐）
- 后端修复 `categories` 过滤
- 为 `preference` 查询增加“分层兜底 + 中文关键词兜底”
- OpenClaw 侧仅做“固定中文查询词增强”（可选但推荐）

**优点**：对所有调用方一致生效；更稳定；可测试、可观测。  
**缺点**：改动范围略大，但边界清晰。

### 方案 B：仅改 OpenClaw 指令
让 OpenClaw 自己多次调用并兜底。  
**缺点**：依赖智能体执行质量；`categories` 不生效的根因仍在。

### 方案 C：只修 `categories` 过滤
**缺点**：无法满足“未整理阶段 L1 兜底”和“embedding 不可用中文命中”的目标。

**结论：采用方案 A。**

## 详细设计

### 1）检索入口与参数约定
仍使用现有接口：
- `GET /memory/query?query=...&categories=preference&limit=...`

参数说明：
- `categories`：当包含 `preference` 时，触发偏好专用召回策略

### 2）`categories` 过滤修复（通用）
在 `retrieval_service.query()` 内，对三路召回结果统一执行：
- 若传入 `categories`：
  - 仅保留 `memory.category ∈ categories` 的候选
  - 保持 `include_history` 的语义不变（默认仍过滤无效版本）

覆盖范围：
- semantic_results / keyword_results / entity_results

### 3）偏好专用“分层兜底”（仅 categories 包含 preference）

#### 3.1 召回流程（推荐默认开启）
按阶段执行，满足就提前返回（或合并后截断）：
1. **阶段1：L4/L6 优先**
   - 目标：快速命中“已整理偏好”
   - 查询范围：`category=preference AND layer in {4,6}`
2. **阶段2：L2 补召回**
   - 目标：覆盖“已沉淀但未总结”的偏好
   - 查询范围：`category=preference AND layer=2`
3. **阶段3：L1 最近 N 条兜底**
   - 目标：覆盖“完全未整理”的偏好细节
   - 查询范围：`layer=1` 最近 N 条（默认 N=30）
   - 注：不强制 category=preference（因为 L1 多为 conversation/task），靠质量过滤与关键词/语义去重控制噪声

#### 3.2 L1 兜底的质量过滤要求（强制）
L1 候选合并进结果前必须经过：
- `post_retrieval_dedup`（现有能力）：
  - 质量过滤（过短/无意义）
  - L1/L2 内部去重
  - 与 L4/L6 的包含关系去重（避免碎片重复）
  - 输出顺序优化（核心知识→分类骨架→近期细节）

### 4）中文关键词兜底（embedding 不可用时）

触发条件：
- `embedding_service.embed_text(query_text)` 抛异常，或返回空/None/维度不合法

策略：
- 跳过 `_semantic_search` 与 `reranker_service.rerank`
- 强制走 `SQLiteStore.search_by_keyword`（FTS；失败则 LIKE）
- 对 query 做简单中文扩展词拼接（“或”关系语义由 FTS/LIKE 自然承担）：
  - `喜欢/偏好/爱/最爱/不喜欢/讨厌/习惯/风格/格式`

### 5）缓存策略（避免“空结果缓存”）
现状：query cache key 含 `query_text|categories|limit`，可能缓存空结果 300s。  
建议：
- 对 `categories` 包含 `preference` 的查询：默认不写入缓存，或使用更短 TTL（例如 30s）
- 目的：避免“刚写入/刚整理后仍持续返回空结果”影响 OpenClaw 体验

### 6）OpenClaw 侧（可选增强）
在 OpenClaw 的启动/对话前检索指令中，将偏好召回固定 query 强化为中文：
- `query=用户偏好 喜欢 不喜欢 习惯 风格 格式`
- `categories=preference`

目的：更贴合中文语料与 FTS 命中模式，embedding 不可用时更稳。

### 7）偏好写入策略（可选，体验增强）
当用户在“记忆管理”手动新增记忆，若分类为 `preference`：
- UI 默认层级建议设置为 **L2**
- 目的：提升“未整理阶段”的可召回性（无需等待 L4）

## 配置项（后端 Settings）
新增可配置项（默认开启/推荐值）：
- `openclaw_preference_enable_l1_fallback: bool = True`
- `openclaw_preference_l1_recent_n: int = 30`
- `openclaw_preference_keyword_expands: List[str] = ["喜欢","偏好","爱","最爱","不喜欢","讨厌","习惯","风格","格式"]`
- `openclaw_preference_disable_cache: bool = True`（或缩短 TTL 的等价实现）

## 可观测性（日志/调试）
建议在检索结果中增加调试字段（不影响 UI，仅 API 返回）：
- `degraded_mode`: 是否进入 embedding 不可用降级
- `preference_fallback_stage`: 命中的阶段（L4/L6 / L2 / L1_recent）
- `candidates_by_stage`: 每阶段候选数量（便于排障）

## 测试策略

### 单元测试（后端）
新增测试覆盖：
1. `categories=preference` 时返回结果全部满足 category 过滤（不混入其它 category）
2. 当 embedding 返回空时：
   - 不走语义检索/精排
   - keyword 结果可返回
3. preference 分层兜底：
   - L4/L6 为空但 L1 有相关对话时，能从 L1_recent 命中并通过质量过滤

### 回归测试（手工）
- OpenClaw 侧执行“你喜欢什么/用户偏好是什么”：
  - 已整理场景：优先命中 L4/L6
  - 未整理场景：仍能从最近 L1 命中
  - 关闭/缺失 embedding：中文关键词仍命中

