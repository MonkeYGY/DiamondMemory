"""记忆类型自动分类服务

根据认知科学理论，将记忆分为三种类型：
1. Episodic (情景记忆) - 具体事件、对话、经历
2. Semantic (语义记忆) - 事实、概念、知识
3. Procedural (程序记忆) - 技能、步骤、工作流

分类策略：
- 基于规则：根据内容和层级快速判断
- 基于LLM：对模糊内容使用大模型推理
"""
import re
import logging
from typing import Dict, Any, Optional
from app.config import settings

logger = logging.getLogger(__name__)


class MemoryTypeClassifier:
    PROCEDURAL_PATTERNS = [
        r'(步骤|流程|方法|操作|如何|怎么|教程|指南|手册|配置|部署|安装|搭建)',
        r'(先.*然后|首先.*其次|第一步|第二步|1\.\s|2\.\s)',
        r'(命令|脚本|代码|终端|命令行|CLI|API)',
        r'(最佳实践|注意事项|常见问题|FAQ)',
    ]

    SEMANTIC_PATTERNS = [
        r'(定义|概念|原理|理论|是什么|什么是|解释|说明)',
        r'(特点|特征|属性|类型|分类|区别|对比)',
        r'(历史|背景|起源|发展|演变)',
    ]

    EPISODIC_PATTERNS = [
        r'(今天|昨天|刚才|刚刚|上次|之前|最近|刚才)',
        r'(我|我们|他|她|他们)(说|做|去|来|见|聊|开|参加)',
        r'(会议|讨论|对话|聊天|见面|电话)',
    ]

    def classify(self, content: str, layer: int = 1, category: str = None,
                 metadata: Dict[str, Any] = None) -> str:
        if not getattr(settings, "memory_type_enabled", True):
            return getattr(settings, "memory_type_default", "episodic")

        if not getattr(settings, "memory_type_auto_classify", True):
            return getattr(settings, "memory_type_default", "episodic")

        type_from_layer = self._classify_by_layer(layer)
        if type_from_layer:
            return type_from_layer

        type_from_rules = self._classify_by_rules(content)
        if type_from_rules:
            return type_from_rules

        type_from_category = self._classify_by_category(category)
        if type_from_category:
            return type_from_category

        return self._classify_by_llm(content)

    def _classify_by_layer(self, layer: int) -> Optional[str]:
        if layer in [5, 6]:
            return "procedural"
        if layer == 4:
            return None
        if layer in [1, 2]:
            return None
        return None

    def _classify_by_rules(self, content: str) -> Optional[str]:
        content_lower = content.lower()

        procedural_score = sum(1 for p in self.PROCEDURAL_PATTERNS if re.search(p, content))
        if procedural_score >= 2:
            return "procedural"

        semantic_score = sum(1 for p in self.SEMANTIC_PATTERNS if re.search(p, content))
        if semantic_score >= 2:
            return "semantic"

        episodic_score = sum(1 for p in self.EPISODIC_PATTERNS if re.search(p, content))
        if episodic_score >= 2:
            return "episodic"

        if procedural_score > 0 and procedural_score > semantic_score and procedural_score > episodic_score:
            return "procedural"
        if semantic_score > 0 and semantic_score > episodic_score:
            return "semantic"
        if episodic_score > 0:
            return "episodic"

        return None

    def _classify_by_category(self, category: str) -> Optional[str]:
        if not category:
            return None

        procedural_keywords = ["部署", "配置", "安装", "开发", "测试", "运维", "流程", "自动化", "脚本"]
        semantic_keywords = ["概念", "原理", "理论", "知识", "百科", "词典", "定义"]

        for kw in procedural_keywords:
            if kw in category:
                return "procedural"

        for kw in semantic_keywords:
            if kw in category:
                return "semantic"

        return None

    def _classify_by_llm(self, content: str) -> str:
        try:
            from app.services.inference.inference_service import inference_service

            prompt = f"""请判断以下记忆内容属于哪种记忆类型，只输出类型名称：

- episodic: 情景记忆（具体事件、对话、个人经历）
- semantic: 语义记忆（事实、概念、知识、信息）
- procedural: 程序记忆（技能、步骤、工作流、操作方法）

内容：
{content[:500]}

只输出一个类型名称（episodic/semantic/procedural）："""

            result = inference_service.generate_text(
                prompt,
                model_path=settings.local_llm_model,
                max_tokens=10
            )

            if result.get("success"):
                text = result.get("generated_text", "").strip().lower()
                if "procedural" in text:
                    return "procedural"
                if "semantic" in text:
                    return "semantic"
                if "episodic" in text:
                    return "episodic"
        except Exception as e:
            logger.warning(f"LLM记忆类型分类失败: {e}")

        return "episodic"


memory_type_classifier = MemoryTypeClassifier()
