"""记忆衰变服务模块

实现基于认知科学的记忆衰变模型：
1. 艾宾浩斯遗忘曲线 (Ebbinghaus Forgetting Curve)
2. 复习加成机制 (Review Bonus)
3. 重要性权重 (Importance Factor)
4. 层级权重 (Layer Factor)

替代原有的简单指数衰减，更贴近人类记忆规律。
"""
import math
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional
from app.config import settings

logger = logging.getLogger(__name__)


class MemoryDecayService:
    def __init__(self):
        self.beijing_tz = timezone(timedelta(hours=8))

    def calculate_retention(self, days_diff: float, access_count: int = 0,
                            confidence: float = 1.0, layer: int = 3,
                            is_pinned: bool = False, level: int = 1) -> float:
        model = getattr(settings, "decay_model", "ebbinghaus")

        if model == "ebbinghaus":
            return self._ebbinghaus_retention(days_diff, access_count, confidence, layer, is_pinned, level)
        return self._simple_decay(days_diff)

    def _ebbinghaus_retention(self, days_diff: float, access_count: int,
                               confidence: float, layer: int,
                               is_pinned: bool, level: int) -> float:
        if is_pinned:
            return 1.0

        if days_diff < 0:
            days_diff = 0

        base_retention = getattr(settings, "ebbinghaus_base_retention", 0.68)
        decay_exponent = getattr(settings, "ebbinghaus_decay_exponent", -0.25)
        review_bonus_rate = getattr(settings, "ebbinghaus_review_bonus", 0.15)
        max_reviews = getattr(settings, "ebbinghaus_max_review_count", 10)
        importance_base = getattr(settings, "ebbinghaus_importance_factor", 0.5)

        days_safe = max(days_diff, 0.01)
        base_ret = base_retention * (days_safe ** decay_exponent)
        base_ret = min(base_ret, 1.0)

        review_factor = 1.0 + review_bonus_rate * min(access_count, max_reviews)

        importance = importance_base + (1.0 - importance_base) * confidence

        layer_factor = self._get_layer_factor(layer)

        level_factor = 1.0 + (level - 1) * 0.1

        retention = base_ret * review_factor * importance * layer_factor * level_factor

        return min(retention, 1.0)

    def _get_layer_factor(self, layer: int) -> float:
        layer_factors = {
            1: 0.6,
            2: 0.8,
            3: 0.3,
            4: 1.2,
            5: 0.3,
            6: 1.5,
        }
        return layer_factors.get(layer, 1.0)

    def _simple_decay(self, days_diff: float) -> float:
        decay_rate = getattr(settings, "decay_rate", 0.1)
        return 1.0 / (1.0 + decay_rate * days_diff)

    def compute_final_score(self, base_score: float, memory: Dict[str, Any]) -> float:
        created_at = memory.get("created_at")
        if not created_at:
            return base_score

        try:
            if isinstance(created_at, str):
                created_dt = datetime.fromisoformat(created_at)
            else:
                created_dt = created_at

            now = datetime.now(self.beijing_tz).replace(tzinfo=None)
            days_diff = max((now - created_dt).days, 0)
        except Exception:
            days_diff = 0

        access_count = memory.get("access_count", 0)
        confidence = memory.get("confidence", 1.0)
        layer = memory.get("layer", 3)
        is_pinned = memory.get("is_pinned", False)
        level = memory.get("level", 1)

        retention = self.calculate_retention(
            days_diff=days_diff,
            access_count=access_count,
            confidence=confidence,
            layer=layer,
            is_pinned=is_pinned,
            level=level
        )

        return base_score * retention

    def should_consolidate(self, memory: Dict[str, Any]) -> bool:
        created_at = memory.get("created_at")
        if not created_at:
            return False

        try:
            if isinstance(created_at, str):
                created_dt = datetime.fromisoformat(created_at)
            else:
                created_dt = created_at

            now = datetime.now(self.beijing_tz).replace(tzinfo=None)
            days_diff = max((now - created_dt).days, 0)
        except Exception:
            return False

        access_count = memory.get("access_count", 0)
        confidence = memory.get("confidence", 1.0)
        layer = memory.get("layer", 1)

        retention = self.calculate_retention(
            days_diff=days_diff,
            access_count=access_count,
            confidence=confidence,
            layer=layer,
            is_pinned=False,
            level=1
        )

        return retention < 0.3 and access_count == 0

    def get_decay_stats(self, memories: list) -> Dict[str, Any]:
        if not memories:
            return {"total": 0, "high_retention": 0, "medium_retention": 0, "low_retention": 0, "forgotten": 0}

        stats = {"total": len(memories), "high_retention": 0, "medium_retention": 0, "low_retention": 0, "forgotten": 0}

        for mem in memories:
            created_at = mem.get("created_at")
            if not created_at:
                continue

            try:
                if isinstance(created_at, str):
                    created_dt = datetime.fromisoformat(created_at)
                else:
                    created_dt = created_at
                now = datetime.now(self.beijing_tz).replace(tzinfo=None)
                days_diff = max((now - created_dt).days, 0)
            except Exception:
                continue

            retention = self.calculate_retention(
                days_diff=days_diff,
                access_count=mem.get("access_count", 0),
                confidence=mem.get("confidence", 1.0),
                layer=mem.get("layer", 3),
                is_pinned=mem.get("is_pinned", False),
                level=mem.get("level", 1)
            )

            if retention >= 0.7:
                stats["high_retention"] += 1
            elif retention >= 0.4:
                stats["medium_retention"] += 1
            elif retention >= 0.15:
                stats["low_retention"] += 1
            else:
                stats["forgotten"] += 1

        return stats


memory_decay_service = MemoryDecayService()
