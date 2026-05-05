import json
import logging
import re
from fastapi import APIRouter, Body
from fastapi.responses import StreamingResponse
from app.services.retrieval_service import retrieval_service
from app.services.inference.inference_service import InferenceService
from app.services.web_search_service import web_search_service
from app.config.settings import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])

inference_service = InferenceService()

SYSTEM_PROMPT = """你是钻石记忆系统的AI助手。你拥有持久化的记忆能力，能够记住用户的所有对话和知识。

你的核心能力：
1. 基于用户的记忆库进行智能问答和推理
2. 帮助用户整理、归纳和管理记忆
3. 基于记忆内容提供建议和洞察
4. 在联网搜索模式下，结合网络信息回答实时性问题

回答要求：
- 综合记忆库内容和你的通用知识进行回答
- 如果记忆中有相关信息，优先引用并结合你的知识给出完整回答
- 如果记忆中没有相关信息，直接基于你的通用知识回答即可
- 回答要简洁、有条理，使用中文
- 对于记忆库中的内容，不要编造或臆测
- 结合上下文给出自然流畅的回答"""

CONTEXT_TEMPLATE = """

===检索到的相关记忆（最多展示少量高相关条目；仅供参考）===
{context}
===记忆检索结束===

要求：
- 不要逐条复述以上清单
- 不要输出思考过程，只输出最终回答
- 若用户只是问候/寒暄，请自然回应即可，不要展开回顾历史"""

WEB_SEARCH_TEMPLATE = """

===联网搜索结果===
{context}
===搜索结果结束===

请基于以上搜索结果、记忆内容和你的知识，回答用户的问题。如果搜索结果中包含有用信息，请引用来源。"""

WEB_SEARCH_ONLY_TEMPLATE = """

===联网搜索结果===
{context}
===搜索结果结束===

请基于以上搜索结果和你的知识，回答用户的问题。如果搜索结果中包含有用信息，请引用来源。"""

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


SUMMARY_SYSTEM_PROMPT = """你是钻石记忆系统的对话摘要器。
目标：把“被裁剪掉的旧对话”压缩为一段可供继续对话的摘要。

要求：
- 只保留：事实、明确偏好、已做决定、进行中的任务、必要上下文
- 删除：寒暄、重复内容、无关细节
- 不要输出思考过程
- 输出中文，200-500 字为宜"""


def _build_summary_input(dropped_messages: list[dict]) -> str:
    parts: list[str] = []
    for m in dropped_messages or []:
        role = (m.get("role") or "").strip()
        content = (m.get("content") or "").strip()
        if not content:
            continue
        parts.append(f"{role}: {content}")
    return "\n".join(parts)


@router.post("/stream")
async def chat_stream(
    messages: list[dict] = Body(..., description="聊天消息列表"),
    use_memory: bool = Body(True, description="是否使用记忆检索增强"),
    use_web_search: bool = Body(False, description="是否使用联网搜索"),
    max_tokens: int = Body(2048, description="最大生成token数")
):
    try:
        enhanced_messages = list(messages)
        system_content = SYSTEM_PROMPT

        user_content = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                user_content = msg.get("content", "")
                break

        if use_memory and messages and user_content:
            try:
                intent = detect_intent(user_content)
                limit = int(getattr(settings, "chat_memory_limit_normal", 6) or 6)
                if intent == "greeting":
                    limit = int(getattr(settings, "chat_memory_limit_greeting", 3) or 3)
                elif intent == "preference":
                    limit = min(8, max(6, limit))

                if intent == "greeting" and hasattr(retrieval_service, "query_recent_similar_l1"):
                    retrieval_result = retrieval_service.query_recent_similar_l1(
                        user_content,
                        recent_n=int(getattr(settings, "chat_greeting_recent_n", 30) or 30),
                        limit=limit,
                        min_score=float(getattr(settings, "chat_greeting_min_score", 0.55) or 0.55),
                    )
                else:
                    retrieval_result = retrieval_service.query(user_content, limit=limit)
                memories = retrieval_result.get("memories", [])
                if memories:
                    context_parts = []
                    for i, mem in enumerate(memories, 1):
                        layer = mem.get("layer", 0)
                        content = mem.get("content", "")
                        score = mem.get("relevance_score", 0)
                        context_parts.append(f"[{i}] (L{layer}, 相关度:{score:.2f}) {content}")
                    context_text = "\n\n".join(context_parts)
                    system_content += CONTEXT_TEMPLATE.format(context=context_text)
            except Exception as e:
                logger.warning(f"记忆检索失败: {e}")

        if use_web_search and messages and user_content and settings.web_search_enabled:
            try:
                search_result = web_search_service.search(user_content)
                search_context = search_result.get("context", "")
                if search_context:
                    if use_memory:
                        system_content += WEB_SEARCH_TEMPLATE.format(context=search_context)
                    else:
                        system_content += WEB_SEARCH_ONLY_TEMPLATE.format(context=search_context)
            except Exception as e:
                logger.warning(f"联网搜索失败: {e}")

        has_system = False
        for i, msg in enumerate(enhanced_messages):
            if msg.get("role") == "system":
                enhanced_messages[i] = {"role": "system", "content": system_content}
                has_system = True
                break
        if not has_system:
            enhanced_messages.insert(0, {"role": "system", "content": system_content})

        generator = inference_service.chat_stream(enhanced_messages, max_tokens=max_tokens)
        return StreamingResponse(generator, media_type="application/x-ndjson")
    except Exception as e:
        logger.error(f"聊天流式接口异常: {e}")
        error_chunk = {"message": {"content": f"聊天服务异常: {str(e)}"}, "done": True}
        async def error_gen():
            yield json.dumps(error_chunk).encode("utf-8") + b"\n"
        return StreamingResponse(error_gen(), media_type="application/x-ndjson")


@router.post("/message")
async def chat_message(
    messages: list[dict] = Body(..., description="聊天消息列表"),
    use_memory: bool = Body(True, description="是否使用记忆检索增强"),
    use_web_search: bool = Body(False, description="是否使用联网搜索"),
    max_tokens: int = Body(2048, description="最大生成token数")
):
    try:
        enhanced_messages = list(messages)
        system_content = SYSTEM_PROMPT

        user_content = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                user_content = msg.get("content", "")
                break

        if use_memory and messages and user_content:
            try:
                intent = detect_intent(user_content)
                limit = int(getattr(settings, "chat_memory_limit_normal", 6) or 6)
                if intent == "greeting":
                    limit = int(getattr(settings, "chat_memory_limit_greeting", 3) or 3)
                elif intent == "preference":
                    limit = min(8, max(6, limit))

                if intent == "greeting" and hasattr(retrieval_service, "query_recent_similar_l1"):
                    retrieval_result = retrieval_service.query_recent_similar_l1(
                        user_content,
                        recent_n=int(getattr(settings, "chat_greeting_recent_n", 30) or 30),
                        limit=limit,
                        min_score=float(getattr(settings, "chat_greeting_min_score", 0.55) or 0.55),
                    )
                else:
                    retrieval_result = retrieval_service.query(user_content, limit=limit)
                memories = retrieval_result.get("memories", [])
                if memories:
                    context_parts = []
                    for i, mem in enumerate(memories, 1):
                        layer = mem.get("layer", 0)
                        content = mem.get("content", "")
                        score = mem.get("relevance_score", 0)
                        context_parts.append(f"[{i}] (L{layer}, 相关度:{score:.2f}) {content}")
                    context_text = "\n\n".join(context_parts)
                    system_content += CONTEXT_TEMPLATE.format(context=context_text)
            except Exception as e:
                logger.warning(f"记忆检索失败: {e}")

        if use_web_search and messages and user_content and settings.web_search_enabled:
            try:
                search_result = web_search_service.search(user_content)
                search_context = search_result.get("context", "")
                if search_context:
                    if use_memory:
                        system_content += WEB_SEARCH_TEMPLATE.format(context=search_context)
                    else:
                        system_content += WEB_SEARCH_ONLY_TEMPLATE.format(context=search_context)
            except Exception as e:
                logger.warning(f"联网搜索失败: {e}")

        has_system = False
        for i, msg in enumerate(enhanced_messages):
            if msg.get("role") == "system":
                enhanced_messages[i] = {"role": "system", "content": system_content}
                has_system = True
                break
        if not has_system:
            enhanced_messages.insert(0, {"role": "system", "content": system_content})

        result = inference_service.chat_completion(enhanced_messages, max_tokens=max_tokens)
        return result
    except Exception as e:
        logger.error(f"聊天接口异常: {e}")
        return {"success": False, "error": str(e)}


@router.post("/summary")
def chat_summary(
    dropped_messages: list[dict] = Body(..., description="被裁剪掉的旧对话消息"),
    max_tokens: int = Body(None, description="最大生成token数")
):
    try:
        summary_input = _build_summary_input(dropped_messages)
        if not summary_input.strip():
            return {"summary_text": ""}

        if max_tokens is None:
            max_tokens = int(getattr(settings, "chat_auto_summary_max_tokens", 600) or 600)

        messages = [
            {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
            {"role": "user", "content": summary_input},
        ]
        result = inference_service.chat_completion(messages, max_tokens=max_tokens)
        if isinstance(result, dict):
            if result.get("success"):
                summary_text = (result.get("generated_text") or "").strip()
                return {"summary_text": summary_text}
            return {"summary_text": ""}
        return {"summary_text": ""}
    except Exception as e:
        logger.error(f"对话摘要接口异常: {e}")
        return {"success": False, "error": str(e)}
