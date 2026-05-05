# 2026-05-01 会话上下文预算、相似记忆限额与自动摘要设计

## 背景与问题

当前会话链路中，“上下文（本次发送给模型的 messages）”与“记忆（长期存储，检索后注入 system prompt）”同时存在。

现状关键点：
- 前端会把 `messages` 裁剪为窗口（条数与 token 预算），见 [ChatView.vue](file:///Users/gengyun/Desktop/DiamondMemory/frontend/src/renderer/views/ChatView.vue#L631-L645)。
- 后端在 `use_memory=true` 时固定检索 `limit=8` 并将结果拼入 system prompt，见 [chat_routes.py](file:///Users/gengyun/Desktop/DiamondMemory/backend/app/api/chat_routes.py#L74-L87)。
- 前端在“只收到 thinking 未收到最终回答”时，会把“问题 + thinking 原文”再次发送，见 [ChatView.vue](file:///Users/gengyun/Desktop/DiamondMemory/frontend/src/renderer/views/ChatView.vue#L571-L599)，可能造成 token 翻倍并触发上下文溢出。

用户诉求：
1) 问候也可检索，但不要每次把历史都“反复思考一遍”，限制为“最近 2-3 次相似问题”。
2) 提供“重新开始一个对话（无历史上下文）”，并支持“记忆检索可选开关”。
3) 当上下文超长时自动提炼重点并压缩打包：把被裁剪的旧对话压成摘要插入 messages；并将摘要写入 L1 供后续检索使用。
4) 点击清除对话后，能真正清掉历史对话并作为新对话开始（至少不再发送旧 messages）。

## 目标（Goals）

- G1：在不牺牲问候体验的前提下，将问候类记忆注入限制到“相似且最近的 2-3 条”，显著降低无关记忆与 token 消耗。
- G2：清除对话后开启“新会话（无历史上下文）”，并提供“记忆检索/联网检索”会话级开关。
- G3：当上下文裁剪发生时，自动生成“对话摘要”并作为系统摘要插入到发送消息中，同时写入 L1 记忆，便于后续检索复用。
- G4：避免 thinking 回灌导致 token 翻倍；在缺少最终输出时仅做轻量“补全最终答案”重试。

## 非目标（Non-Goals）

- NG1：不改变底层向量库/索引结构，不引入新数据库。
- NG2：不做跨设备同步与多端会话合并。
- NG3：不强制替换现有 RAG 逻辑，仅做限额、路由与摘要增强。

## 术语

- 上下文（Context）：本次请求发送给大模型的 `messages` 列表（user/assistant/system）。
- 记忆（Memory）：存储在记忆库中的长期内容（L1-L6），通过检索后注入 system prompt 或用于回答参考。
- 会话摘要（Session Summary）：由本地裁剪产生的“被丢弃对话内容”压缩成的一段摘要，用于本会话继续对话；同时写入 L1 以便未来检索。

## 总体方案（方案 B）

1) 意图路由 + 相似记忆限额（问候/偏好/普通问题分档）
2) 清除对话 = 新会话（无历史上下文）+ 会话级“记忆/联网”开关
3) 上下文裁剪触发自动摘要：摘要插入 messages + 写入 L1
4) thinking 回灌止损：二次请求不携带 thinking 原文

## 1) 意图路由与“相似问题最近 2-3”

### 1.1 路由策略

在后端 `chat_routes` 中对最后一条 user 输入做轻量意图判断：
- greeting：你好/在吗/hello/hi/早安/晚安/哈喽/嗨/早/晚上好 等
- preference：包含“我喜欢/偏好/不喜欢/口味/习惯/风格/格式/吃/喝”等（可复用检索服务里已有偏好关键词扩展）
- normal：其余默认

输出：`intent in {"greeting","preference","normal"}`。

### 1.2 检索策略（“两者结合”）

按照用户确认的口径：先意图路由，再在对应集合内做语义筛选 top2-3，并偏向近期内容。

#### greeting（核心）
- 仅注入 `top_k=3`（可配置，默认 3）。
- “近期约束”：从 L1 最近 N 条（默认 30，可配置）中筛选相似度最高的 2-3 条作为候选池；如果语义检索不可用，则使用关键词+时间衰减排序。
- “相似阈值”：低于阈值的结果不注入（默认 0.55，可配置），避免问候触发无关偏好。

实现形态（建议）：
- 在 `RetrievalService` 增加一个专用入口：`query_recent_similar(query_text, layer=1, recent_n=30, limit=3, min_score=0.55)`。
- 内部流程：
  1. 从 store 取 layer=1 最近 recent_n 条（已有类似能力：偏好兜底使用 `get_recent_by_layer`）。
  2. 若 embedding 可用：对 query 与候选做向量相似度排序；否则用关键词重叠 + 时间衰减。
  3. 返回 top limit，并附上分数与理由。

#### preference
- 保持现有偏好分层兜底（L4/L6→L2→L1_recent）逻辑不变，检索上限可保持 6-8。

#### normal
- 默认 `top_k=6`（可配置），保留时间衰减与去重过滤。

### 1.3 记忆注入模板优化

现有模板会把每条记忆完整列出。为了减少“逐条复述/思考”的诱导，在注入模板中新增约束语句：
- 仅将记忆当作参考素材，不要逐条复述清单
- 输出只给最终答案，不输出思考过程
- 问候类只需自然回应，不要展开长篇回顾

## 2) 新会话与“清除对话”行为

### 2.1 语义定义

用户选择：清上下文 + 可选记忆（推荐）。

行为：
- 清除对话后，不再发送任何历史 messages（上下文为“空”），等同新会话。
- 记忆检索与联网检索由 UI 会话级开关控制（默认开启记忆、默认关闭联网或保持现有默认）。

### 2.2 前端改动点

- `clearChat()` 除现有清空 messages/localStorage 外，还需重置会话态：
  - promptTrim 警告状态（如 `didWarnPromptTrim`）
  - 会话摘要缓存（新增）
  - 会话 id（新增，用于摘要入库 metadata）
- UI 提供：
  - “记忆增强”开关（现有 `useMemory` 已存在并传入 `chatStreamRequest`）
  - “联网搜索”开关（如已存在则复用；否则新增并传到后端）
- 清除对话按钮触发后：
  - 本地历史立刻删除
  - 重新生成 sessionId

## 3) 超长上下文自动摘要 + 写入 L1

### 3.1 触发时机

当 `buildPromptWindow()` 发生裁剪（trimmed=true）且存在 droppedMessages 时触发：
- droppedMessages = all - picked（旧消息集合）
- 仅当 droppedMessages 的估算 token 超过阈值时才摘要（避免小裁剪频繁摘要）；阈值建议默认 300 tokens（可配置）。

### 3.2 摘要生成方式

新增后端接口（建议）：
- `POST /api/chat/summary`
  - 入参：
    - `dropped_messages: [{role, content}]`
    - `kept_messages: [{role, content}]`（可选，用于摘要对齐上下文）
    - `mode: "auto_trim"`（预留）
    - `max_tokens`（默认较小，如 400-800）
  - 出参：
    - `summary_text: string`
    - `summary_tokens_est: number`（可选）

摘要提示词要求：
- 输出中文
- 只保留事实、任务、偏好、决定、上下文必要信息
- 不要包含逐轮对话记录，不要包含思考过程
- 控制长度（目标 200-500 字，可随 dropped 内容规模弹性）

### 3.3 摘要插入 messages（会话继续用）

前端在发送最终聊天请求前，将摘要插入为一条 `role=system`（默认）：
- content 格式：
  - 固定前缀：`【对话摘要（自动生成）】`
  - 摘要正文
  - 固定约束：`后续回答请优先参考该摘要；不要复述摘要；只输出最终答案。`

并将该 system 摘要视为“会话摘要缓存”，后续请求如果仍在本会话中、且还发生裁剪，可：
- 合并摘要（增量摘要），或
- 仅保留最新摘要（默认策略：保留最新，避免摘要叠摘要膨胀）

### 3.4 写入 L1 供检索复用

前端在成功获得 `summary_text` 后，调用：
- `POST /api/memory/create`
  - `content=summary_text`
  - `category="对话摘要"`
  - `layer=1`
  - `metadata`：
    - `source="chat_auto_summary"`
    - `session_id`
    - `created_at`
    - `dropped_count`
  - `disturb_free=true`（避免自动整理链路引入额外噪声）

目的：
- 未来检索可复用摘要，提高长会话连续性与召回质量。

风险与缓解：
- 记忆污染：摘要可能带入误解或不重要信息
  - 缓解：摘要提示词强调“只保留可验证事实/明确偏好/明确决定”，并在 metadata 标记来源；后续可加“低权重/时间衰减更强”策略（本期不做）。

## 4) thinking 回灌止损

现状：当只收到 thinking 时，前端会把 thinking 原文拼回 prompt 让模型输出最终答案，容易造成 token 翻倍。

改造：
- 二次请求改为仅发送简短指令，不携带 thinking 原文：
  - `你刚才没有输出最终答案。请直接输出最终答案，不要输出思考过程。`
- 仍保留 thinking 存储与折叠展示（如果产品需要），但不再回灌到模型输入。

## 配置项（建议新增/复用）

后端 settings（建议）：
- `chat_memory_limit_greeting` 默认 3
- `chat_memory_limit_normal` 默认 6
- `chat_greeting_recent_n` 默认 30
- `chat_greeting_min_score` 默认 0.55
- `chat_auto_summary_enabled` 默认 true
- `chat_auto_summary_trigger_token` 默认 300
- `chat_auto_summary_max_tokens` 默认 600
- `chat_summary_insert_role` 固定 system（本期固定，后续可配置）

前端（建议）：
- `promptWindowMaxMessages` 现有 24（可保持）
- `promptWindowTokenBudget` 现有 2200（可保持，后续再调优）

## 接口与数据流

### 发送消息（含自动摘要）
1. 用户输入 → messages 追加 user
2. `buildPromptWindow(all)` 取 kept + dropped
3. 若发生裁剪且满足阈值：
   - 请求 `/api/chat/summary` 得到 summary_text
   - 将 summary 插入为 system 消息（本次发送用）
   - 请求 `/api/memory/create` 写入 L1（供未来检索）
4. 请求 `/api/chat/stream`，携带：
   - messages（含摘要 system + kept）
   - use_memory（会话级开关）
   - use_web_search（会话级开关）

### 后端增强
- `/api/chat/stream` 内部：
  - 提取最后 user_content
  - 计算 intent
  - 根据 intent 决定检索策略与 limit
  - 注入模板（避免列表复述与思考过程）

## 验收标准（Acceptance Criteria）

- AC1：问候“你好/在吗/hi”等请求中，记忆注入最多 3 条，且优先来自近期相似 L1；无相似则不注入。
- AC2：点击清除对话后，下一次发送请求不包含任何旧 messages；且 UI 仍可选择是否启用记忆/联网。
- AC3：当上下文发生裁剪且 dropped 超阈值时，系统会自动生成摘要并插入到本次请求 messages 中；并写入 L1，后续可检索到该摘要。
- AC4：在“仅返回 thinking”场景下，不再把 thinking 原文回灌；二次请求 token 不出现数量级膨胀。

## 测试计划（最小集）

- 手工用例：
  - 连续多轮对话直到触发裁剪，确认出现“自动摘要”并继续可对话
  - 清除对话后发送消息，确认后端接收到的 messages 不含历史
  - 问候触发检索：确认注入条数<=3，并观察注入内容更贴近最近相似对话
  - 构造“thinking-only”模型响应（或用支持 thinking 的模型），确认不发生 thinking 回灌

## 回滚策略

- 新增功能均以配置开关控制（auto_summary、greeting_limit 等）。
- 出现异常可关闭 `chat_auto_summary_enabled` 或将 greeting limit 调回旧值，恢复原行为。

