"""增强版实体提取服务

在原有正则提取基础上，增加：
1. LLM智能实体提取（降级方案）
2. 实体置信度评估
3. 实体去重与归一化
4. 提取数量限制
"""
import re
import logging
from typing import List, Dict, Any
from app.config import settings

logger = logging.getLogger(__name__)


class EnhancedEntityExtractor:
    ENTITY_PATTERNS = {
        "person": r'[\u4e00-\u9fff]{2,4}|[A-Z][a-z]+(?:\s[A-Z][a-z]+)+',
        "organization": r'[\u4e00-\u9fff]{2,10}(?:公司|集团|机构|组织|部门|委员会|大学|学院|研究所)',
        "location": r'[\u4e00-\u9fff]{2,10}(?:省|市|区|县|镇|路|街|道|国|洲)',
        "date": r'\d{4}-\d{2}-\d{2}|\d{2}/\d{2}/\d{4}|\d{8}|\d{4}年\d{1,2}月\d{1,2}日',
        "time": r'\d{2}:\d{2}(:\d{2})?',
        "number": r'\d+(?:\.\d+)?',
        "email": r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}',
        "phone": r'1[3-9]\d{9}',
        "url": r'https?://[\w\-]+(\.[\w\-]+)+([\w\-.,@?^=%&:/~\+#]*[\w\-@?^=%&/~\+#])?',
        "technology": r'(?:Python|Java|JavaScript|TypeScript|React|Vue|Docker|Kubernetes|Git|Linux|MacOS|Windows|API|SDK|CLI|HTTP|REST|GraphQL|SQL|NoSQL|Redis|MongoDB|PostgreSQL|MySQL|FastAPI|Flask|Django|Electron|Node\.js|Ollama|GPT|BERT|Transformer|LLM|RAG|MCP)',
    }

    def extract(self, text: str) -> List[Dict[str, Any]]:
        entities = []
        seen = set()

        regex_entities = self._extract_by_regex(text)
        for ent in regex_entities:
            key = f"{ent['type']}:{ent['text']}"
            if key not in seen:
                seen.add(key)
                entities.append(ent)

        max_entities = getattr(settings, "entity_extraction_max_entities", 20)
        entities = sorted(entities, key=lambda x: x.get("confidence", 0.5), reverse=True)[:max_entities]

        if len(entities) < 3 and getattr(settings, "entity_extraction_llm_fallback", True):
            llm_entities = self._extract_by_llm(text)
            for ent in llm_entities:
                key = f"{ent['type']}:{ent['text']}"
                if key not in seen:
                    seen.add(key)
                    entities.append(ent)
            entities = entities[:max_entities]

        return entities

    def _extract_by_regex(self, text: str) -> List[Dict[str, Any]]:
        entities = []
        seen = set()

        for entity_type, pattern in self.ENTITY_PATTERNS.items():
            matches = re.finditer(pattern, text)
            for match in matches:
                entity_text = match.group()
                if entity_text not in seen and len(entity_text) > 1:
                    seen.add(entity_text)
                    confidence = self._compute_confidence(entity_text, entity_type)
                    entities.append({
                        "text": entity_text,
                        "type": entity_type,
                        "confidence": confidence,
                    })

        return entities

    def _compute_confidence(self, entity_text: str, entity_type: str) -> float:
        confidence = 0.5
        if len(entity_text) > 5:
            confidence += 0.2
        elif len(entity_text) > 2:
            confidence += 0.1

        high_confidence_types = ["email", "phone", "url", "date", "time", "technology"]
        if entity_type in high_confidence_types:
            confidence += 0.2

        return min(confidence, 1.0)

    def _extract_by_llm(self, text: str) -> List[Dict[str, Any]]:
        try:
            from app.services.inference.inference_service import inference_service
            import json

            prompt = f"""从以下文本中提取关键实体，输出JSON格式。

实体类型：person(人名), organization(组织), location(地点), technology(技术), date(日期), event(事件)

文本：
{text[:500]}

输出格式：
{{"entities": [{{"text": "实体文本", "type": "类型", "confidence": 0.9}}]}}

只输出JSON："""

            result = inference_service.generate_text(
                prompt,
                model_path=settings.local_llm_model,
                max_tokens=200,
                format="json"
            )

            if not result.get("success"):
                return []

            generated = result.get("generated_text", "")
            parsed = self._parse_json(generated)
            if not parsed:
                return []

            entities = []
            for ent in parsed.get("entities", []):
                text_val = ent.get("text", "")
                type_val = ent.get("type", "other")
                conf = ent.get("confidence", 0.7)
                if text_val and len(text_val) > 1:
                    entities.append({
                        "text": text_val,
                        "type": type_val,
                        "confidence": conf,
                    })

            return entities

        except Exception as e:
            logger.warning(f"LLM实体提取失败: {e}")
            return []

    def _parse_json(self, text: str) -> dict:
        import json
        import re
        if not text:
            return {}
        text = re.sub(r'^```(?:json)?\s*', '', text, flags=re.MULTILINE)
        text = re.sub(r'\s*```$', '', text, flags=re.MULTILINE)
        start = text.find('{')
        end = text.rfind('}')
        if start != -1 and end != -1:
            text = text[start:end+1]
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {}


enhanced_entity_extractor = EnhancedEntityExtractor()
