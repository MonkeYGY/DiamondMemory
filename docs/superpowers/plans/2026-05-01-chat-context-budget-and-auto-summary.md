# Chat Context Budget & Auto Summary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不牺牲问候体验的前提下，限制“相似记忆”注入到最近 2-3 条，并在上下文裁剪时自动生成摘要插入 messages、同时写入 L1，且修复 thinking 回灌导致 token 翻倍的问题。

**Architecture:** 前端负责“上下文窗口裁剪 + 自动摘要触发 + 会话态（sessionId/摘要缓存）管理”，后端负责“意图路由（greeting/preference/normal）+ 分档检索限额 + 新增摘要生成接口 + L1 最近相似检索”。新增能力均可通过配置开关回滚。

**Tech Stack:** Electron + Vue3 + TypeScript（前端/渲染进程）；Python + FastAPI（后端）；现有 RetrievalService/InferenceService；测试：vitest、pytest/unittest。

---

## File Map（将被创建/修改的文件）

**Backend**
- Modify: [settings.py](file:///Users/gengyun/Desktop/DiamondMemory/backend/app/config/settings.py)（新增 chat 相关配置项）
- Modify: [chat_routes.py](file:///Users/gengyun/Desktop/DiamondMemory/backend/app/api/chat_routes.py)（意图路由、分档检索、注入模板、summary API）
- Modify: [retrieval_service.py](file:///Users/gengyun/Desktop/DiamondMemory/backend/app/services/retrieval_service.py)（新增 L1 最近相似检索入口）
- Create: `backend/tests/test_chat_intent_and_greeting_retrieval.py`
- Create: `backend/tests/test_retrieval_recent_similar.py`

**Frontend**
- Modify: [ChatView.vue](file:///Users/gengyun/Desktop/DiamondMemory/frontend/src/renderer/views/ChatView.vue)（prompt window 返回 dropped、自动摘要插入、清除对话重置会话态、thinking 回灌止损）
- Modify: [backend.ts](file:///Users/gengyun/Desktop/DiamondMemory/frontend/src/renderer/api/backend.ts)（新增 chatSummaryRequest；chatStreamRequest 支持 use_web_search/max_tokens 可选参数）
- Create: `frontend/src/renderer/utils/prompt-window.ts`
- Create: `frontend/src/renderer/utils/prompt-window.test.ts`
- Modify: [backend.test.ts](file:///Users/gengyun/Desktop/DiamondMemory/frontend/src/renderer/api/backend.test.ts)（新增 chatSummaryRequest IPC 路由测试）

---

### Task 1: Backend Settings（分档限额与摘要配置）

**Files:**
- Modify: [settings.py](file:///Users/gengyun/Desktop/DiamondMemory/backend/app/config/settings.py)
- Test: `backend/tests/test_chat_intent_and_greeting_retrieval.py`

- [ ] **Step 1: Add new settings defaults**

在 `Settings` 中新增字段（默认值与 spec 对齐）：

```python
chat_memory_limit_greeting: int = 3
chat_memory_limit_normal: int = 6
chat_greeting_recent_n: int = 30
chat_greeting_min_score: float = 0.55

chat_auto_summary_enabled: bool = True
chat_auto_summary_trigger_token: int = 300
chat_auto_summary_max_tokens: int = 600
```

- [ ] **Step 2: Add a regression test for defaults**

创建 `backend/tests/test_chat_intent_and_greeting_retrieval.py`（先只测 settings 默认值，后续补意图与 limit）：

```python
import importlib


def test_chat_settings_defaults():
    settings_module = importlib.import_module("app.config.settings")
    settings_module = importlib.reload(settings_module)
    s = settings_module.settings

    assert int(getattr(s, "chat_memory_limit_greeting")) == 3
    assert int(getattr(s, "chat_memory_limit_normal")) == 6
    assert int(getattr(s, "chat_greeting_recent_n")) == 30
    assert float(getattr(s, "chat_greeting_min_score")) == 0.55

    assert bool(getattr(s, "chat_auto_summary_enabled")) is True
    assert int(getattr(s, "chat_auto_summary_trigger_token")) == 300
    assert int(getattr(s, "chat_auto_summary_max_tokens")) == 600
```

- [ ] **Step 3: Run backend tests**

Run:

```bash
pytest -q backend/tests/test_chat_intent_and_greeting_retrieval.py
```

Expected: PASS

- [ ] **Step 4: Compile check**

Run:

```bash
python -m compileall backend/app > /dev/null
```

Expected: exit code 0

---

### Task 2: Backend Intent Routing + Memory Injection Limits（问候 top2-3）

**Files:**
- Modify: [chat_routes.py](file:///Users/gengyun/Desktop/DiamondMemory/backend/app/api/chat_routes.py)
- Modify: `backend/tests/test_chat_intent_and_greeting_retrieval.py`

- [ ] **Step 1: Add intent detector helper**

在 `chat_routes.py` 中增加纯函数（便于单测），返回 `greeting | preference | normal`：

```python
import re


_GREETING_RE = re.compile(r"^\s*(你好|在吗|嗨|哈喽|hello|hi|早安|早上好|晚安|晚上好|早|晚上)\s*[!！。\.]*\s*$", re.I)
_PREF_MARKERS = ["喜欢", "偏好", "不喜欢", "讨厌", "习惯", "风格", "格式", "口味", "喝", "吃"]


def detect_intent(user_text: str) -> str:
    t = (user_text or "").strip()
    if not t:
        return "normal"
    if _GREETING_RE.match(t):
        return "greeting"
    if any(m in t for m in _PREF_MARKERS):
        return "preference"
    return "normal"
```

- [ ] **Step 2: Tighten memory injection template**

将 `CONTEXT_TEMPLATE` 改为更“无诱导列表复述”的模板（保留原有结构标记，但加强约束）：

```python
CONTEXT_TEMPLATE = """

===检索到的相关记忆（最多展示少量高相关条目；仅供参考）===
{context}
===记忆检索结束===

要求：
- 不要逐条复述以上清单
- 不要输出思考过程，只输出最终回答
- 若用户只是问候/寒暄，请自然回应即可，不要展开回顾历史"""
```

- [ ] **Step 3: Apply per-intent retrieval limit**

在 `chat_stream()` / `chat_message()` 中：
1) 提取 `user_content`
2) `intent = detect_intent(user_content)`
3) 分档决定 `limit`
4) greeting 时优先走“最近相似 L1 检索”（Task 3 实现），否则沿用 `retrieval_service.query()`

参考伪码（最终以现有代码结构为准）：

```python
intent = detect_intent(user_content)
limit = settings.chat_memory_limit_normal
if intent == "greeting":
    limit = settings.chat_memory_limit_greeting
elif intent == "preference":
    limit = min(8, max(6, settings.chat_memory_limit_normal))

if intent == "greeting":
    retrieval_result = retrieval_service.query_recent_similar_l1(
        user_content,
        recent_n=settings.chat_greeting_recent_n,
        limit=limit,
        min_score=settings.chat_greeting_min_score,
    )
else:
    retrieval_result = retrieval_service.query(user_content, limit=limit)
```

- [ ] **Step 4: Add tests for detect_intent**

在 `backend/tests/test_chat_intent_and_greeting_retrieval.py` 追加：

```python
from app.api import chat_routes


def test_detect_intent_greeting():
    assert chat_routes.detect_intent("你好") == "greeting"
    assert chat_routes.detect_intent(" hi ") == "greeting"


def test_detect_intent_preference():
    assert chat_routes.detect_intent("我喜欢喝茶") == "preference"


def test_detect_intent_normal():
    assert chat_routes.detect_intent("为什么会超出上下文？") == "normal"
```

- [ ] **Step 5: Run backend tests**

Run:

```bash
pytest -q backend/tests/test_chat_intent_and_greeting_retrieval.py
```

Expected: PASS

---

### Task 3: Backend RetrievalService（L1 最近相似 top-k）

**Files:**
- Modify: [retrieval_service.py](file:///Users/gengyun/Desktop/DiamondMemory/backend/app/services/retrieval_service.py)
- Create: `backend/tests/test_retrieval_recent_similar.py`

- [ ] **Step 1: Add recent-similar L1 API**

在 `RetrievalService` 增加方法（命名固定，供 chat_routes 调用）：

```python
from typing import Dict, Any, List, Optional


def _cosine(a: List[float], b: List[float]) -> float:
    if not a or not b:
        return 0.0
    n = min(len(a), len(b))
    dot = 0.0
    na = 0.0
    nb = 0.0
    for i in range(n):
        av = float(a[i] or 0.0)
        bv = float(b[i] or 0.0)
        dot += av * bv
        na += av * av
        nb += bv * bv
    if na <= 0.0 or nb <= 0.0:
        return 0.0
    return dot / ((na ** 0.5) * (nb ** 0.5))


def query_recent_similar_l1(
    self,
    query_text: str,
    recent_n: int = 30,
    limit: int = 3,
    min_score: float = 0.55,
) -> Dict[str, Any]:
    recent = self.store.get_recent_by_layer(1, limit=int(recent_n or 30), include_inactive=False)

    from app.services.embedding_service import embedding_service
    q_emb = embedding_service.embed_text(query_text) or []

    scored = []
    for mem in recent:
        mid = mem.get("id")
        content = (mem.get("content") or "").strip()
        if not mid or not content:
            continue
        emb = self.vector_store.get_embedding(mid) if getattr(self, "vector_store", None) else []
        score = _cosine(q_emb, emb) if q_emb and emb else 0.0
        mem2 = dict(mem)
        mem2["final_score"] = float(score)
        mem2["retrieval_reason"] = "L1_recent_similar"
        scored.append(mem2)

    scored.sort(key=lambda x: x.get("final_score", 0.0), reverse=True)
    filtered = [m for m in scored if float(m.get("final_score") or 0.0) >= float(min_score or 0.0)]

    formatted = self._format_results(filtered[: int(limit or 3)])
    formatted = self._post_retrieval_dedup(formatted)[: int(limit or 3)]

    return {
        "memories": formatted,
        "total_tokens": 0,
        "search_time_ms": 0,
        "total_candidates": len(scored),
        "entities_found": 0,
        "weight_strategy": "recent_similar_l1",
        "cache_hit": False,
        "degraded_mode": False,
        "preference_fallback_stage": None,
    }
```

- [ ] **Step 2: Add tests (mock embedding/vector)**

创建 `backend/tests/test_retrieval_recent_similar.py`：

```python
from unittest.mock import MagicMock


def _build_service():
    from app.services.retrieval_service import RetrievalService

    s = RetrievalService.__new__(RetrievalService)
    s.store = MagicMock()
    s.vector_store = MagicMock()
    s._format_results = lambda xs: xs
    s._post_retrieval_dedup = lambda xs: xs
    return s


def test_query_recent_similar_l1_filters_by_score(monkeypatch):
    service = _build_service()
    service.store.get_recent_by_layer.return_value = [
        {"id": "m1", "layer": 1, "content": "你好", "status": "active"},
        {"id": "m2", "layer": 1, "content": "我们聊过上下文窗口", "status": "active"},
    ]

    service.vector_store.get_embedding.side_effect = lambda mid: [1.0, 0.0] if mid == "m2" else [0.0, 1.0]

    emb_mod = __import__("app.services.embedding_service", fromlist=["embedding_service"])
    monkeypatch.setattr(emb_mod.embedding_service, "embed_text", lambda *_args, **_kw: [1.0, 0.0])

    result = service.query_recent_similar_l1("你好", recent_n=30, limit=3, min_score=0.5)
    memories = result.get("memories") or []
    assert len(memories) == 1
    assert memories[0]["id"] == "m2"
```

- [ ] **Step 3: Run backend tests**

Run:

```bash
pytest -q backend/tests/test_retrieval_recent_similar.py
```

Expected: PASS

---

### Task 4: Backend Chat Summary API（/api/chat/summary）

**Files:**
- Modify: [chat_routes.py](file:///Users/gengyun/Desktop/DiamondMemory/backend/app/api/chat_routes.py)
- Create: `backend/tests/test_chat_summary_prompt.py`

- [ ] **Step 1: Add summary endpoint**

在 `chat_routes.py` 新增：
- 路由：`POST /chat/summary`
- 入参：`dropped_messages: list[dict]`，`max_tokens: int = settings.chat_auto_summary_max_tokens`
- 输出：`{"summary_text": "..."}`

摘要请求的 messages 结构（固定，不使用记忆检索）：

```python
SUMMARY_SYSTEM_PROMPT = """你是钻石记忆系统的对话摘要器。
目标：把“被裁剪掉的旧对话”压缩为一段可供继续对话的摘要。

要求：
- 只保留：事实、明确偏好、已做决定、进行中的任务、必要上下文
- 删除：寒暄、重复内容、无关细节
- 不要输出思考过程
- 输出中文，200-500 字为宜"""

def _build_summary_input(dropped_messages: list[dict]) -> str:
    parts = []
    for m in dropped_messages:
        role = (m.get("role") or "").strip()
        content = (m.get("content") or "").strip()
        if not content:
            continue
        parts.append(f"{role}: {content}")
    return "\n".join(parts)
```

调用：

```python
summary_input = _build_summary_input(dropped_messages)
messages = [
    {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
    {"role": "user", "content": summary_input},
]
result = inference_service.chat_completion(messages, max_tokens=max_tokens)
summary_text = (result or {}).get("message", {}).get("content", "") if isinstance(result, dict) else ""
return {"summary_text": summary_text.strip()}
```

- [ ] **Step 2: Add tests for summary input builder**

创建 `backend/tests/test_chat_summary_prompt.py`：

```python
from app.api import chat_routes


def test_build_summary_input_skips_empty():
    text = chat_routes._build_summary_input([
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": ""},
    ])
    assert "user: hello" in text
    assert "assistant:" not in text
```

- [ ] **Step 3: Run backend tests**

Run:

```bash
pytest -q backend/tests/test_chat_summary_prompt.py
```

Expected: PASS

---

### Task 5: Frontend Prompt Window Extract + Unit Tests

**Files:**
- Create: `frontend/src/renderer/utils/prompt-window.ts`
- Create: `frontend/src/renderer/utils/prompt-window.test.ts`
- Modify: [ChatView.vue](file:///Users/gengyun/Desktop/DiamondMemory/frontend/src/renderer/views/ChatView.vue)

- [ ] **Step 1: Extract estimateTokens + buildPromptWindow**

创建 `prompt-window.ts`：

```ts
export function estimateTokens(text: string): number {
  return Math.ceil((text || '').length * 1.2)
}

export function buildPromptWindow(
  all: Array<{ role: string; content: string }>,
  opts: { maxMessages: number; tokenBudget: number }
): { kept: Array<{ role: string; content: string }>; dropped: Array<{ role: string; content: string }>; trimmed: boolean } {
  let budget = opts.tokenBudget
  const picked: Array<{ role: string; content: string }> = []
  for (let i = all.length - 1; i >= 0; i--) {
    const m = all[i]
    const t = estimateTokens(m.content) + 16
    if (picked.length >= opts.maxMessages) break
    if (picked.length > 0 && budget - t < 0) break
    picked.push(m)
    budget -= t
    if (budget <= 0) break
  }
  const kept = picked.reverse()
  const trimmed = kept.length < all.length
  const dropped = trimmed ? all.slice(0, all.length - kept.length) : []
  return { kept, dropped, trimmed }
}
```

- [ ] **Step 2: Add tests**

创建 `prompt-window.test.ts`：

```ts
import { describe, expect, it } from 'vitest'
import { buildPromptWindow } from './prompt-window'

describe('buildPromptWindow', () => {
  it('returns dropped messages when trimmed', () => {
    const all = [
      { role: 'user', content: 'a'.repeat(2000) },
      { role: 'assistant', content: 'b'.repeat(2000) },
      { role: 'user', content: 'hi' }
    ]
    const { kept, dropped, trimmed } = buildPromptWindow(all, { maxMessages: 24, tokenBudget: 200 })
    expect(trimmed).toBe(true)
    expect(kept.length).toBe(1)
    expect(kept[0].content).toBe('hi')
    expect(dropped.length).toBe(2)
  })
})
```

- [ ] **Step 3: Wire ChatView.vue to new helper**

在 `ChatView.vue` 删除内联 `estimateTokens/buildPromptWindow`，改为 import 并使用返回值：
- 原：`const { messages: chatMessages, trimmed } = buildPromptWindow(rawChatMessages)`
- 新：`const { kept, dropped, trimmed } = buildPromptWindow(rawChatMessages, { maxMessages: promptWindowMaxMessages, tokenBudget: promptWindowTokenBudget })`

- [ ] **Step 4: Run frontend tests**

Run:

```bash
npm -s --prefix frontend test
```

Expected: PASS

---

### Task 6: Frontend Summary Request + Auto Insert + Write L1

**Files:**
- Modify: [backend.ts](file:///Users/gengyun/Desktop/DiamondMemory/frontend/src/renderer/api/backend.ts)
- Modify: [ChatView.vue](file:///Users/gengyun/Desktop/DiamondMemory/frontend/src/renderer/views/ChatView.vue)

- [ ] **Step 1: Add renderer API function chatSummaryRequest**

在 `backend.ts` 新增：

```ts
export async function chatSummaryRequest(payload: {
  dropped_messages: Array<{ role: string; content: string }>
  max_tokens?: number
}): Promise<{ summary_text: string }> {
  return apiRequest('/api/chat/summary', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  })
}
```

- [ ] **Step 2: Add IPC routing test**

在 `frontend/src/renderer/api/backend.test.ts` 追加：

```ts
it('chatSummaryRequest 在 dev + electronAPI.httpRequest 时应走 IPC', async () => {
  const httpRequest = vi.fn(async () => ({ ok: true, status: 200, data: { summary_text: 'ok' } }))
  window.electronAPI = { httpRequest }

  const { chatSummaryRequest } = await import('./backend')
  const data = await chatSummaryRequest({ dropped_messages: [{ role: 'user', content: 'hi' }] })

  expect(data.summary_text).toBe('ok')
  expect(httpRequest).toHaveBeenCalledTimes(1)
})
```

- [ ] **Step 3: Implement auto-summary in ChatView.vue**

在 `sendMessage()` 中：
- 获取 `{ kept, dropped, trimmed }`
- 若 `trimmed && dropped`，并且 dropped 的估算 tokens 超过阈值（先在前端定义一个常量 `autoSummaryTriggerTokens = 300`，后续可做成设置项）：
  1) `const { summary_text } = await chatSummaryRequest({ dropped_messages: dropped })`
  2) 构造一条 system 消息（仅本次发送用）：

```ts
const summarySystem = {
  role: 'system',
  content: `【对话摘要（自动生成）】\n${summary_text}\n\n要求：后续回答优先参考该摘要；不要复述摘要；只输出最终答案。`
}
```

  3) 本次发送的 `chatMessages` = `[summarySystem, ...kept]`
  4) 调用 `/api/memory/create` 写入 L1（复用现有 `apiRequest`，保持 `disturb_free: true`）：

```ts
await apiRequest('/api/memory/create', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    content: summary_text,
    category: '对话摘要',
    layer: 1,
    disturb_free: true,
    metadata: { source: 'chat_auto_summary', session_id: sessionId.value, dropped_count: dropped.length }
  })
})
```

- [ ] **Step 4: Clear chat resets session**

在 `clearChat()` 中：
- 重置 `messages/streaming*`
- 清除 localStorage
- 重置 `didWarnPromptTrim=false`
- 生成新 `sessionId`（例如 `crypto.randomUUID?.()`，没有则用时间戳拼随机数）

- [ ] **Step 5: Run frontend typecheck + tests**

Run:

```bash
npm -s --prefix frontend run build
npm -s --prefix frontend test
```

Expected: PASS

---

### Task 7: Stop “thinking backfill” Token Explosion

**Files:**
- Modify: [ChatView.vue](file:///Users/gengyun/Desktop/DiamondMemory/frontend/src/renderer/views/ChatView.vue)

- [ ] **Step 1: Replace thinking-backfill prompt**

将现有二次请求逻辑从：
- 发送 `问题 + 思考过程原文 + 请给出最终答案`

改为仅发送简短指令，不携带 thinking 原文：

```ts
const lastUser = [...chatMessages].reverse().find(m => m.role === 'user')?.content || ''
const prompt = `问题：${lastUser}\n\n你刚才没有输出最终答案。请直接输出最终答案（不要输出思考过程）。`
const finalReqMessages = [{ role: 'user', content: prompt }]
```

- [ ] **Step 2: Run frontend build**

Run:

```bash
npm -s --prefix frontend run build
```

Expected: PASS

---

### Task 8: End-to-End Smoke Checks（手工）

**Files:**
- None (manual)

- [ ] **Step 1: Run backend unit tests**

Run:

```bash
pytest -q backend/tests/test_chat_intent_and_greeting_retrieval.py backend/tests/test_retrieval_recent_similar.py backend/tests/test_chat_summary_prompt.py
```

Expected: PASS

- [ ] **Step 2: Run frontend unit tests**

Run:

```bash
npm -s --prefix frontend test
```

Expected: PASS

- [ ] **Step 3: Manual in-app verification**

1. 连续对话到触发“对话过长”提示，确认自动生成摘要后仍能继续回复，且摘要写入记忆库（可在记忆查询/列表中看到 category=对话摘要 或 tags/metadata）。
2. 点击“清除对话”，再次发送消息，确认不会引用旧对话上下文（回答不应继续接上旧问题）。
3. 输入“你好”，确认不会出现大段“把历史偏好逐条复述”的回复（最多参考 2-3 条近期相似对话片段）。

---

## Spec Coverage Self-Review

- “问候也检索但限 2-3” → Task 2 + Task 3
- “清除对话=新会话 + 记忆可选” → Task 6 Step 4（会话态）+ 现有 useMemory 继续沿用
- “超长自动摘要插入 + 写入 L1” → Task 6
- “thinking 回灌止损” → Task 7

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-01-chat-context-budget-and-auto-summary.md`. Two execution options:

1. Subagent-Driven (recommended) - I dispatch a fresh subagent per task, review between tasks, fast iteration
2. Inline Execution - Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?

