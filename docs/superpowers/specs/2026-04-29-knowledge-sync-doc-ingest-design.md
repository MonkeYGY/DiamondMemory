<!--
钻石记忆系统 - 设计文档
主题：ID=19（P1）拖文件进存储路径自动入库 / 一键同步（最小可行）
日期：2026-04-29
-->

# ID=19（P1）拖文件自动入库 / 一键同步（设计）

## 1. 背景与问题

用户习惯把文档（PDF/Word/Excel）直接拖入“存储路径”（知识库根目录下的用户区域），但系统不会自动录入数据库（SQLite + 向量库），导致：
- 不能检索/引用
- 知识库相关视图（内容/图谱等）无法体现“已入库”的状态

现状梳理（已存在能力）：
- 前端文件树：基于 Electron 读取文件系统，且会定时刷新（5s）
- 文档上传：前端上传 -> 后端 `/api/storage/file` -> `IngestService.ingest_file()`
- 知识库同步：后端已有 `/api/knowledge/sync`，但当前同步逻辑主要处理 `.md` 文件
- 任务队列：后端已有 `/api/tasks/enqueue` 与持久化 `task_queue`（单 worker 串行执行）

## 2. 目标（Goals）

最小可行（本次交付）：
1. 增加“🔄 同步知识库（扫描并入库）”按钮（Settings 或 Knowledge 页）
2. 点击按钮后：扫描并将新增/变更的 PDF/Word/Excel 摄取入库（进入 DB + 向量库），并可检索
3. 同步过程不阻塞 UI：走任务队列异步执行，前端展示任务进度
4. 同步完成后强制刷新：
   - FileTree 刷新（立即反映文件系统变化）
   - `rebuild-memory-exports`（如需要，优先保证一致性）

增强项（后续，不在本次必交）：
- 自动检测（文件系统 watcher / 启动时增量同步 / 定时同步）

## 3. 非目标（Non-goals）

- 不做全盘文件类型摄取（仅覆盖：pdf/doc/docx/xls/xlsx）
- 不改变现有“上传文件”的 ingest 链路
- 不在本次引入跨平台文件系统监听（watchdog/inotify/fsevents）

## 4. 用户体验与交互

入口：
- Settings 页或 Knowledge 页新增按钮：`🔄 同步知识库（扫描并入库）`

点击后的体验：
- 立即提示“已加入任务队列”
- 在任务面板显示任务：`知识库同步`（含进度、运行中/完成/失败）
- 完成后提示 “同步完成：新增/更新 X 个文件”
- 自动触发知识库树刷新（无需用户手动刷新）

## 5. 技术方案概览（推荐：方案 B）

总体策略：
- 仍然使用后端入口 `POST /api/knowledge/sync`
- 但该接口不再同步执行，而是 **入队一个 task_queue 任务**（类型 `knowledge_sync`）
- worker 线程执行具体扫描/摄取逻辑，并持续更新任务进度

关键收益：
- 不阻塞 UI
- 复用现有任务队列与任务面板能力

## 6. 后端设计

### 6.1 API 设计

#### `POST /api/knowledge/sync`
行为（改造后）：
- 创建任务队列项：`type=knowledge_sync`
- 立即返回：
```json
{ "id": "<task_id>", "status": "queued" }
```

> 备注：保留原接口路径不变，满足“最小可行：直接调用 /api/knowledge/sync”的要求。

#### 任务查询（复用现有）
- `GET /api/tasks/{task_id}`：轮询任务状态/进度

### 6.2 任务执行器：`knowledge_sync`

注册位置：
- `backend/app/services/task_queue_service.py` 中注册 executor（类似 quick_organize/deep_organize）

executor 伪流程：
1. progress=5：准备扫描
2. progress=10~60：遍历目标目录并识别增量文件
3. progress=60~95：逐个调用 ingest（带节流与异常捕获），记录成功/失败
4. progress=95：可选执行 rebuild-memory-exports（若设计决定放在后端做）
5. progress=100：完成，返回统计信息

返回结构（用于任务结果展示）：
```json
{
  "ok": true,
  "scanned": 123,
  "ingested": 7,
  "skipped": 116,
  "failed": 0,
  "errors": []
}
```

### 6.3 扫描范围与过滤规则

扫描根目录（默认）：
- 仅扫描：`<settings.storage_path>/用户文档/`

理由：
- 避免扫到系统生成目录（如 raw/processed/qdrant_storage/backups/temp），降低误摄取与性能风险

过滤：
- 跳过隐藏目录/系统目录：复用 `KnowledgeService.HIDDEN_ITEMS`，并额外显式跳过：
  - `raw/`、`processed/`（IngestService 会把源文件 copy 到 raw，避免自摄取导致死循环）
- 仅处理扩展名：`.pdf .doc .docx .xls .xlsx`

### 6.4 增量判定与去重

复用 `file_sync` 表（SQLite）作为“同步账本”，字段：
- `file_path`（相对路径，如 `用户文档/xxx.pdf`）
- `last_modified`
- `file_hash`（建议：sha256；若性能压力可先 md5）

判定逻辑：
- 若无记录：新增 -> ingest
- 若 mtime 未变：跳过
- 若 mtime 变了但 hash 未变：仅更新 file_sync（跳过 ingest）
- 若 hash 变了：更新 -> ingest

> 说明：IngestService 内部会生成 doc_id 并拷贝文件到 raw 目录；本设计不要求 doc_id 与 file_path 绑定，但要求“可检索”，因此摄取进入 memory/vector 即可。

### 6.5 与“全量整理”的关系（重要）

当前 `KnowledgeService.sync_knowledge_base()` 末尾会触发 `organize_entire_knowledge_base()`，该操作可能耗时且依赖模型。

本次设计建议：
- **默认不触发全量整理**（避免同步任务耗时过长、以及在无模型/降级时卡住）
- 若确需整理，由用户单独执行“深度整理”（已存在 task 类型 `deep_organize`）

实现策略（可选其一，推荐 A）：
- A. 给 `sync_knowledge_base()` 增加参数 `run_organize: bool = False`
- B. 任务执行器内仅在用户显式勾选时才 enqueue `deep_organize`

## 7. 前端设计

### 7.1 新增按钮与调用链

位置：
- SettingsView 或 KnowledgeView（任选其一，后续可两处都放）

点击行为：
1. 调用 `POST /api/knowledge/sync`（通过 `apiRequest`）
2. 取得 `task_id` 后：
   - 将任务添加到任务面板展示（现有 tasks store）
   - 开始轮询 `GET /api/tasks/{task_id}` 直到 completed/failed
3. 完成后触发刷新：
   - `syncKnowledgeTree(rebuildKnowledgeMemoryExports)`（项目已有封装：先 rebuild 再发事件刷新 FileTree）

### 7.2 失败与提示
- 如果任务失败：toast 提示失败原因（取 `error` / `message`）
- 如果任务 blocked（MODEL_NOT_READY）：本任务不依赖模型（requires_model=false），原则上不应 blocked

## 8. 测试方案

后端单测（pytest）建议覆盖：
1. 给临时 storage_path 下创建 `用户文档/a.pdf`（可用最小假文件或 mock ingest_file）
2. 调用 executor：确认创建 file_sync 记录、并触发 ingest
3. 二次执行：mtime/hash 未变时应跳过 ingest
4. 修改文件：应再次 ingest
5. 确认扫描不会摄取 raw/processed（可在这些目录放同类文件验证被跳过）

前端验证点（冒烟）：
1. 手动把 pdf 拖入 `用户文档/`
2. 点击“同步知识库” -> 任务面板出现任务并推进
3. 同步完成后，可在检索中命中（或 DB 中看到新增 doc/doc_chunk 记录）

## 9. 兼容性与回滚

兼容性：
- 接口路径不变：仍为 `POST /api/knowledge/sync`
- 任务队列为增量能力，不影响旧逻辑

回滚：
- 若任务队列异常，可临时切回同步执行（保留旧实现分支），但不建议长期使用

