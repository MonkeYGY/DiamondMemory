"""矛盾检测引擎

LLM驱动的知识矛盾推理，支持：
1. 语义相似度预筛选
2. LLM深度矛盾验证
3. 矛盾解决策略建议
"""
import logging
from typing import List, Dict, Any, Optional, Tuple
from app.config import settings

logger = logging.getLogger(__name__)


class ContradictionDetector:
    def detect_contradictions(self, new_content: str, similar_memories: List[Dict[str, Any]],
                               threshold: float = None) -> List[Dict[str, Any]]:
        if not getattr(settings, "contradiction_detection_enabled", True):
            return []

        if threshold is None:
            threshold = getattr(settings, "contradiction_similarity_threshold", 0.6)

        candidates = [m for m in similar_memories
                       if m.get("conflict_score", 0) >= threshold or m.get("semantic_score", 0) >= threshold]

        if not candidates:
            return []

        if not getattr(settings, "contradiction_llm_verify", True):
            return [{"memory": c, "contradiction_type": "potential", "confidence": 0.5} for c in candidates[:3]]

        return self._llm_verify_contradictions(new_content, candidates)

    def _llm_verify_contradictions(self, new_content: str, candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        try:
            from app.services.inference.inference_service import inference_service
            import json

            candidates_text = ""
            for i, c in enumerate(candidates[:5]):
                content = c.get("content", "")[:300]
                candidates_text += f"\n[{i+1}] ID:{c.get('id','')[:8]} 内容:{content}"

            prompt = f"""请分析以下新内容与已有记忆之间是否存在矛盾或冲突。

新内容：
{new_content[:500]}

已有记忆：
{candidates_text}

请判断每条已有记忆与新内容的关系，输出JSON格式：
{{
  "results": [
    {{
      "id": "记忆ID前8位",
      "is_contradiction": true/false,
      "contradiction_type": "factual/temporal/perspective/none",
      "explanation": "矛盾说明",
      "resolution": "update_old/keep_both/replace_old"
    }}
  ]
}}

只输出JSON，不要其他文字："""

            result = inference_service.generate_text(
                prompt,
                model_path=settings.local_llm_model,
                max_tokens=1024,
                format="json"
            )

            if not result.get("success"):
                return []

            generated_text = result.get("generated_text", "")
            parsed = self._parse_json(generated_text)
            if not parsed:
                return []

            contradictions = []
            results = parsed.get("results", [])
            for r in results:
                if r.get("is_contradiction"):
                    target_id_prefix = r.get("id", "")
                    target_memory = None
                    for c in candidates:
                        if c.get("id", "").startswith(target_id_prefix):
                            target_memory = c
                            break

                    if target_memory:
                        contradictions.append({
                            "memory": target_memory,
                            "contradiction_type": r.get("contradiction_type", "unknown"),
                            "explanation": r.get("explanation", ""),
                            "resolution": r.get("resolution", "keep_both"),
                            "confidence": 0.8
                        })

            return contradictions

        except Exception as e:
            logger.warning(f"LLM矛盾验证失败: {e}")
            return []

    def _parse_json(self, text: str) -> dict:
        import json
        import re
        if not text:
            return {}
        text = re.sub(r'^```(?:json)?\s*', '', text, flags=re.MULTILINE)
        text = re.sub(r'\s*```$', '', text, flags=re.MULTILINE)
        text = text.strip()
        start = text.find('{')
        end = text.rfind('}')
        if start != -1 and end != -1:
            text = text[start:end+1]
        text = re.sub(r',\s*([\}\]])', r'\1', text)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {}


contradiction_detector = ContradictionDetector()
