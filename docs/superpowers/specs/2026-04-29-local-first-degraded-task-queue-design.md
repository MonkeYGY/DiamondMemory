# Local-first 降级可用性 & 耗时任务队列化（最小持久化队列）设计

> 会话任务卡：ID=12（P2）  
> 日期：2026-04-29  
> 目标关键词：**无模型也能用** / **降级可用性** / **耗时任务队列化** / **低功耗节流**

## 背景

当前应用在未安装 Ollama 或未下载模型时，虽然部分能力理论上可运行（例如 SQLite/FTS、历史记忆浏览、知识库文件树、MD 导出、备份/恢复），但用户体验上容易出现：

- 页面/按钮呈现“不可用”或错误提示过多，用户误以为“软件整体不可用”
- “深度整理/提炼/图谱重建”等耗时操作虽然已用线程异步执行，但缺乏统一的队列与任务管理能力（暂停/继续/进度/重试/持久化）

代码现状（已验证）：

- 后端已有聚合状态接口：`GET /api/config/startup-status`（包含 `backend_ready/ollama_ready/llm_installed/llm_loaded/...`）
- Embedding 已具备降级：`EmbeddingService` 在 Ollama 不可用时降级为本地 TF‑IDF
- 整理任务目前为“线程 + 内存态状态”：`POST /api/memory/organize` + `GET /api/memory/organize/status`（quick 同理）

## 目标（验收标准）

1. **未安装 Ollama / 未下载模型时**：
   - 不会出现“核心页面全红导致不可用”的主观体验
   - 仍可正常 **检索 / 浏览 / 导出 / 管理**
2. 触发 **整理/提炼/图谱重建**：
   - 不阻塞 UI
   - 若需要模型则进入队列并提示“需要模型”，且不会导致页面不可用
3. **低功耗模式**：
   - 任务节流明显（阶段 pause / 批次限制 / 自适应 sleep 生效）
4. 队列能力具备 **持久化**：
   - App 重启后仍可看到任务记录，并可继续执行未完成任务（至少 running/paused 可恢复）

## 非目标

- 本期不做多 worker 并行、分布式队列、跨设备任务同步
- 不对“整理/提炼”的算法质量做大改；主要做编排、降级、体验与可观测性

## 方案概览（推荐方案）

采用 **最小持久化队列（SQLite 状态表） + 单 Worker 串行执行**：

- 后端新增统一的 **Capabilities 能力状态 API**
- 后端新增 **Task Queue Service**（SQLite 持久化任务表 + 单 worker）
- 前端新增 **任务面板**（进度、暂停/继续、低功耗标识、阻塞原因）
- 旧的“整理线程接口”保留对外兼容，但内部逐步映射到队列（降低一次性改动风险）

## 能力分级与降级策略

### 1) 无模型也可用（强保证）

- SQLite/FTS 检索、历史记忆浏览
- 知识库文件树
- MD 导出/浏览（含重建导出索引）
- 备份/恢复
- 分类管理（不依赖 LLM 的部分）

### 2) 需要 LLM（受限/可排队）

- L2→L4 总结归纳
- L4→L6 技能提炼
- 需要 LLM 的“重排/抽取/提炼”类技能

### 3) 图谱重建（默认可用，但需注意依赖）

- 图谱构建主要依赖 SQLite 数据与 NetworkX；理论上可在无模型情况下运行
- 若图谱重建流程内部依赖实体抽取/embedding，则需拆分为两段：
  - **可离线段**：纯 SQL 关系构建/缓存更新
  - **需模型段（可选）**：实体抽取增强、向量相关增强

> 本期建议先将图谱重建作为队列任务纳入统一编排，具体“是否 requires_model”按当前实现依赖判定。

## 统一能力状态 API 设计

### Endpoint

`GET /api/system/capabilities`

### Response（示例）

```json
{
  "backend_ready": true,
  "ollama_ready": false,
  "model_ready": false,
  "degraded_reason": "OLLAMA_NOT_RUNNING",
  "llm": { "model": "qwen3.5:4b", "installed": false, "loaded": false },
  "embedding": { "model": "bge-m3", "available": true, "backend": "tfidf" },
  "allowed": {
    "browse": true,
    "search": true,
    "export": true,
    "manage": true,
    "llm_summarize": false,
    "llm_extract_skill": false,
    "graph_rebuild": true
  }
}
```

### 字段定义

- `model_ready`：表示 LLM 类能力（总结/提炼/重排）是否可执行
- `degraded_reason`：稳定枚举（用于 UI 文案与引导）
  - `OK`
  - `OLLAMA_NOT_INSTALLED`
  - `OLLAMA_NOT_RUNNING`
  - `MODEL_NOT_INSTALLED`
  - `MODEL_NOT_LOADED`
  - `UNKNOWN`
- `embedding.backend`：`bge-m3 | tfidf`（用于解释“检索可用但效果降级”）
- `allowed.*`：前端按钮可用性统一来源，避免 scattered if/else

### 与现有接口关系

- `GET /api/config/startup-status`：继续作为“启动与模型热加载状态”来源（TopNav 继续使用）
- `GET /api/system/capabilities`：作为“是否允许某能力、是否需要提示/降级”的统一策略入口

## 任务队列（SQLite 持久化）设计

### 任务类型（第一期覆盖）

- `quick_organize`（快速整理）
- `deep_organize`（深度整理）
- `extract_skills`（技能提炼：L4→L6 或等价流程）
- `graph_rebuild`（图谱重建）

### 数据表：task_queue

建议字段（最小集合 + 可扩展）：

- `id`：uuid
- `type`：任务类型（字符串枚举）
- `status`：
  - `queued` / `running` / `paused`
  - `completed` / `failed` / `cancelled`
  - `blocked`（例如“缺模型”）
- `progress`：0~100（整数）
- `message`：阶段说明（展示在前端）
- `requires_model`：boolean
- `blocked_reason`：例如 `MODEL_NOT_READY`
- `power_mode`：`normal | low_power`
- `params_json`：任务参数（JSON 字符串）
- `result_json`：任务结果（JSON 字符串）
- `error`：失败原因（字符串）
- `created_at / started_at / updated_at / finished_at`

### 状态机

```
queued -> running -> completed
              \-> failed

queued -> blocked  (requires_model && !model_ready)
blocked -> queued  (模型就绪后允许继续)

running -> paused -> queued
running -> cancelled
```

### Worker 行为（单 worker 串行）

1. 每次取最早 `queued` 任务执行
2. 执行前检查：
   - 若 `requires_model=true` 且 `capabilities.model_ready=false` → `blocked`
3. 执行中：
   - 在 **批次边界/阶段边界** 检查 `paused/cancelled`
   - 更新 `progress/message/updated_at`
4. 低功耗：
   - `power_mode=low_power` 时启用：
     - 现有 `deep_organize_low_power_enabled` 相关的 stage pause / 批次限制
     - `adaptive_organize_service.adaptive_sleep()`（系统负载感知节流）

## 后端 API 设计（队列）

### 1) 入队

`POST /api/tasks/enqueue`

Request：
```json
{
  "type": "deep_organize",
  "power_mode": "low_power",
  "params": { "force": false }
}
```

Response（最小）：
```json
{ "id": "...", "status": "queued" }
```

> 若缺模型并且本次任务 `requires_model=true`，也可以直接返回 `status=blocked`（由后端策略决定，推荐后端直接落库为 blocked，前端无需猜测）。

### 2) 列表/详情

- `GET /api/tasks?status=running,queued,blocked&limit=50`
- `GET /api/tasks/{id}`

### 3) 控制

- `POST /api/tasks/{id}/pause`
- `POST /api/tasks/{id}/resume`
- `POST /api/tasks/{id}/cancel`

## 与现有整理接口的兼容策略

为降低一次性改动，第一期建议：

- 保留以下接口对外行为不变（前端可逐步切换）：
  - `POST /api/memory/organize`
  - `GET /api/memory/organize/status`
  - `POST /api/memory/organize/quick`
  - `GET /api/memory/organize/quick/status`
- 但内部实现逐步改为：
  - `POST /api/memory/organize` → enqueue(`deep_organize`)
  - `/status` → 映射到“当前任务”或“最近一次 deep_organize 任务”的状态

## 前端交互设计

### 按钮可用性与提示

- 前端在触发“整理/提炼”等任务前：
  1. 拉取 `GET /api/system/capabilities`
  2. 若 `allowed.llm_summarize=false` 且任务需要模型：
     - 仍允许“点击触发”，但直接入队为 `blocked` 并提示原因（符合“点了会进入队列并提示需要模型”）
  3. “检索/浏览/导出/管理”不因模型不可用而禁用

### 任务面板（最小实现）

- 展示 running/queued/blocked 列表
- running 展示进度条 + message + 暂停/取消
- blocked 展示 blocked_reason + 一键跳转 ModelView/OllamaSetup 引导
- 支持切换默认 power_mode（影响后续入队任务）

## 测试与自测

### 自测路径（与验收一致）

1. 不安装/关闭 Ollama → 启动 App → 浏览/检索/知识库/导出正常
2. 点击“深度整理/技能提炼”：
   - 任务入队
   - 显示 blocked + “需要模型”提示（不阻塞 UI）
3. 开启低功耗 → 触发 deep_organize：
   - 任务执行节流明显（pause_ms / adaptive_sleep 生效）

### 自动化测试建议（最小集合）

- capabilities 接口在以下情形返回正确 allowed 与 degraded_reason：
  - Ollama 不可达
  - Ollama 可达但模型未安装
  - 模型已安装未 loaded
  - 模型 loaded
- task_queue 状态机测试：
  - enqueue -> queued -> running -> completed
  - requires_model + !model_ready -> blocked
  - paused/resume/cancel

## 风险与回滚策略

### 风险

- 队列引入状态机与持久化带来复杂度
- 旧接口兼容层若映射不当，可能出现前端状态不一致

### 回滚

第一期保持单 worker + 单表最小实现，且保留旧整理线程逻辑可切回：

- 通过配置开关（配置层读取）控制：
  - `task_queue_enabled=true/false`
- 若关闭队列，则恢复旧的“线程 + 内存态 status”行为

