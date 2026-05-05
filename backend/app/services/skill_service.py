"""
L6 技能层产品化服务（最小可行）

目标：
- 将技能从“纯文本记忆”升级为可运营资产：可追溯（来源/版本）、可评估（统计/反馈）、可迭代（自动/手动升级）。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional, Tuple

from app.config import settings
from app.storage import SQLiteStore


def _beijing_now_str() -> str:
    beijing_tz = timezone(timedelta(hours=8))
    return datetime.now(beijing_tz).strftime("%Y-%m-%d %H:%M:%S")


@dataclass(frozen=True)
class SkillUpgradeTrigger:
    min_invokes: int = 3
    min_negative_feedbacks: int = 1
    negative_rating_threshold: int = 2  # <= 2 视为负反馈


class SkillService:
    """
    注意：本服务不直接依赖 LLM。升级内容目前采用“复制 + 反馈注入”的最小策略，
    后续可替换为真正的“基于反馈重写技能”的 LLM 版本。
    """

    def __init__(self, store: Optional[SQLiteStore] = None):
        self.store = store or SQLiteStore()
        self._trigger = SkillUpgradeTrigger(
            min_invokes=getattr(settings, "skill_auto_upgrade_min_invokes", 3),
            min_negative_feedbacks=getattr(settings, "skill_auto_upgrade_min_negative_feedbacks", 1),
            negative_rating_threshold=getattr(settings, "skill_negative_rating_threshold", 2),
        )

    # --- 内部工具 ---
    def _now_str(self) -> str:
        return _beijing_now_str()

    def _ensure_skill_metadata(self, memory: Dict[str, Any]) -> Dict[str, Any]:
        """
        为 L6 记忆补齐技能元数据（可选字段 + 默认值策略，兼容旧数据）。
        返回可写回 DB 的 metadata dict。
        """
        meta = dict(memory.get("metadata") or {})

        # 1) 核心身份/版本
        if not meta.get("skill_id"):
            meta["skill_id"] = str(uuid.uuid4())
        try:
            meta["version"] = int(meta.get("version") or 1)
        except Exception:
            meta["version"] = 1

        # 2) 可追溯来源（默认从 summary_memory_id 兜底）
        if not isinstance(meta.get("source_memory_ids"), list) or not meta.get("source_memory_ids"):
            summary_id = meta.get("summary_memory_id")
            meta["source_memory_ids"] = [summary_id] if summary_id else []

        # 3) 适用条件 / 工具 / 步骤 / 期望产出（默认空，后续可由生成流程填充）
        meta.setdefault("preconditions", [])
        meta.setdefault("tools", [])
        meta.setdefault("steps", [])
        meta.setdefault("expected_output", "")

        # 4) 评估指标（最小集合）
        metrics = dict(meta.get("metrics") or {})
        metrics.setdefault("invoke_count", 0)
        metrics.setdefault("last_invoked_at", None)
        metrics.setdefault("rating_count", 0)
        metrics.setdefault("rating_sum", 0)
        metrics.setdefault("rating_avg", None)
        metrics.setdefault("negative_feedback_count", 0)
        metrics.setdefault("success_count", 0)
        metrics.setdefault("failure_count", 0)
        metrics.setdefault("last_feedback", None)
        meta["metrics"] = metrics

        return meta

    def _build_upgraded_content(self, old_content: str, rating: int, comment: str) -> str:
        # MVP：不引入 LLM，只将反馈注入到末尾，保证版本可查与可迭代
        suffix = (
            "\n\n---\n"
            "升级记录：\n"
            f"- 触发原因：用户负反馈（评分={rating}）\n"
            f"- 反馈内容：{comment or '（无）'}\n"
            "- 处理方式：已生成新版本（内容暂为自动复制 + 反馈注入，后续可由 LLM 重写）\n"
        )
        return (old_content or "").rstrip() + suffix

    def _should_trigger_upgrade(self, meta: Dict[str, Any], rating: Optional[int]) -> bool:
        metrics = meta.get("metrics") or {}
        invoke_ok = int(metrics.get("invoke_count") or 0) >= self._trigger.min_invokes
        negative_ok = int(metrics.get("negative_feedback_count") or 0) >= self._trigger.min_negative_feedbacks
        rating_ok = rating is not None and rating <= self._trigger.negative_rating_threshold
        return invoke_ok and negative_ok and rating_ok

    # --- 对外能力 ---
    def record_invocation(self, skill_memory_id: str) -> Dict[str, Any]:
        mem = self.store.get_by_id(skill_memory_id)
        if not mem or mem.get("layer") != 6:
            raise ValueError("技能不存在或不是 L6 记忆")

        meta = self._ensure_skill_metadata(mem)
        metrics = meta["metrics"]
        metrics["invoke_count"] = int(metrics.get("invoke_count") or 0) + 1
        metrics["last_invoked_at"] = self._now_str()

        self.store.update(memory_id=skill_memory_id, metadata=_json_dumps(meta))
        return {"success": True, "skill_id": meta["skill_id"], "version": meta["version"], "metrics": metrics}

    def submit_feedback(
        self,
        skill_memory_id: str,
        rating: int,
        comment: str = "",
        success: Optional[bool] = None,
    ) -> Dict[str, Any]:
        mem = self.store.get_by_id(skill_memory_id)
        if not mem or mem.get("layer") != 6:
            raise ValueError("技能不存在或不是 L6 记忆")

        meta = self._ensure_skill_metadata(mem)
        metrics = meta["metrics"]

        # 1) 统计：评分/反馈
        rating = int(rating)
        metrics["rating_count"] = int(metrics.get("rating_count") or 0) + 1
        metrics["rating_sum"] = int(metrics.get("rating_sum") or 0) + rating
        metrics["rating_avg"] = round(metrics["rating_sum"] / metrics["rating_count"], 3)
        if rating <= self._trigger.negative_rating_threshold:
            metrics["negative_feedback_count"] = int(metrics.get("negative_feedback_count") or 0) + 1
        if success is True:
            metrics["success_count"] = int(metrics.get("success_count") or 0) + 1
        elif success is False:
            metrics["failure_count"] = int(metrics.get("failure_count") or 0) + 1

        metrics["last_feedback"] = {
            "rating": rating,
            "comment": comment,
            "success": success,
            "at": self._now_str(),
        }

        self.store.update(memory_id=skill_memory_id, metadata=_json_dumps(meta))

        # 2) 触发自动升级（最小可行：创建任务 + 生成新版本）
        upgraded = None
        if self._should_trigger_upgrade(meta, rating):
            upgraded = self._trigger_auto_upgrade(
                mem=mem,
                meta=meta,
                rating=rating,
                comment=comment,
            )

        return {
            "success": True,
            "skill_id": meta["skill_id"],
            "version": meta["version"],
            "metrics": metrics,
            "auto_upgrade": upgraded,
        }

    def manual_upgrade(self, skill_memory_id: str, note: str = "") -> Dict[str, Any]:
        """手动触发一次“技能升级”，生成 v+1 并保留历史版本链路。"""
        mem = self.store.get_by_id(skill_memory_id)
        if not mem or mem.get("layer") != 6:
            raise ValueError("技能不存在或不是 L6 记忆")

        meta = self._ensure_skill_metadata(mem)
        upgraded = self._trigger_manual_upgrade(mem=mem, meta=meta, note=note)
        return {"success": True, "skill_id": meta["skill_id"], "from_version": meta["version"], "manual_upgrade": upgraded}

    def list_latest_skills(self, limit: int = 200) -> Dict[str, Any]:
        """按 skill_id 聚合，返回每个技能的最新版本（MVP：内存中聚合）。"""
        all_l6 = self.store.get_by_layer(6, include_inactive=True) or []
        latest_by_skill: Dict[str, Tuple[int, Dict[str, Any]]] = {}
        for mem in all_l6:
            meta = self._ensure_skill_metadata(mem)
            sid = meta.get("skill_id")
            ver = int(meta.get("version") or 1)
            cur = latest_by_skill.get(sid)
            if not cur or ver > cur[0]:
                latest_by_skill[sid] = (ver, {**mem, "metadata": meta})
        items = [v[1] for v in sorted(latest_by_skill.values(), key=lambda x: x[0], reverse=True)]
        return {"skills": items[:limit], "total": len(items)}

    def get_skill_versions_by_memory(self, skill_memory_id: str) -> Dict[str, Any]:
        chain = self.store.get_version_chain(skill_memory_id) or []
        versions = []
        for mem in chain:
            if mem.get("layer") != 6:
                continue
            meta = self._ensure_skill_metadata(mem)
            versions.append({**mem, "metadata": meta})
        # 兜底：可能 chain 为空但 skill_memory_id 存在
        if not versions:
            mem = self.store.get_by_id(skill_memory_id)
            if mem and mem.get("layer") == 6:
                versions = [{**mem, "metadata": self._ensure_skill_metadata(mem)}]
        latest = versions[-1] if versions else None
        return {"versions": versions, "latest": latest, "total": len(versions)}

    def _trigger_auto_upgrade(self, mem: Dict[str, Any], meta: Dict[str, Any], rating: int, comment: str) -> Optional[Dict[str, Any]]:
        skill_id = meta["skill_id"]
        from_version = int(meta.get("version") or 1)
        to_version = from_version + 1

        pending = None
        get_pending = getattr(self.store, "get_pending_skill_upgrade_task", None)
        if callable(get_pending):
            pending = get_pending(skill_id=skill_id, from_version=from_version)
        if pending:
            return {"triggered": False, "reason": "pending_task_exists", "task_id": pending.get("id")}

        task_id = str(uuid.uuid4())
        create_task = getattr(self.store, "create_skill_upgrade_task", None)
        if callable(create_task):
            create_task(
                task_id=task_id,
                skill_id=skill_id,
                from_memory_id=mem.get("id"),
                from_version=from_version,
                to_version=to_version,
                reason="auto_threshold",
                details={"rating": rating, "comment": comment},
            )

        # 生成新版本（MVP：复制 + 反馈注入）
        new_meta = dict(meta)
        new_meta["version"] = to_version
        # 新版本的指标从 0 开始（历史可由旧版本保存）
        new_meta["metrics"] = {
            "invoke_count": 0,
            "last_invoked_at": None,
            "rating_count": 0,
            "rating_sum": 0,
            "rating_avg": None,
            "negative_feedback_count": 0,
            "success_count": 0,
            "failure_count": 0,
            "last_feedback": None,
        }

        new_content = self._build_upgraded_content(mem.get("content", ""), rating, comment)

        created = self.store.create(
            memory_id=str(uuid.uuid4()),
            content=new_content,
            category=mem.get("category"),
            layer=6,
            level=mem.get("level", 3),
            tags=mem.get("tags") or [],
            source=mem.get("source"),
            confidence=mem.get("confidence", 1.0),
            metadata=new_meta,
            status="active",
            processed_status="processed",
            parent_id=mem.get("id"),
            short_name=mem.get("short_name"),
        )
        new_id = (created or {}).get("id") or None

        if new_id:
            self.store.invalidate_memory(mem.get("id"), new_id)

        complete_task = getattr(self.store, "complete_skill_upgrade_task", None)
        if callable(complete_task):
            complete_task(task_id=task_id, new_memory_id=new_id)

        return {"triggered": True, "task_id": task_id, "new_memory_id": new_id, "to_version": to_version}

    def _trigger_manual_upgrade(self, mem: Dict[str, Any], meta: Dict[str, Any], note: str) -> Dict[str, Any]:
        skill_id = meta["skill_id"]
        from_version = int(meta.get("version") or 1)
        to_version = from_version + 1

        # 手动升级不阻塞于 pending task（但仍记录任务，便于运营追踪）
        task_id = str(uuid.uuid4())
        create_task = getattr(self.store, "create_skill_upgrade_task", None)
        if callable(create_task):
            create_task(
                task_id=task_id,
                skill_id=skill_id,
                from_memory_id=mem.get("id"),
                from_version=from_version,
                to_version=to_version,
                reason="manual",
                details={"note": note},
            )

        new_meta = dict(meta)
        new_meta["version"] = to_version
        new_meta["metrics"] = {
            "invoke_count": 0,
            "last_invoked_at": None,
            "rating_count": 0,
            "rating_sum": 0,
            "rating_avg": None,
            "negative_feedback_count": 0,
            "success_count": 0,
            "failure_count": 0,
            "last_feedback": None,
        }

        new_content = self._build_upgraded_content(mem.get("content", ""), rating=5, comment=note or "手动升级")
        created = self.store.create(
            memory_id=str(uuid.uuid4()),
            content=new_content,
            category=mem.get("category"),
            layer=6,
            level=mem.get("level", 3),
            tags=mem.get("tags") or [],
            source=mem.get("source"),
            confidence=mem.get("confidence", 1.0),
            metadata=new_meta,
            status="active",
            processed_status="processed",
            parent_id=mem.get("id"),
            short_name=mem.get("short_name"),
        )
        new_id = (created or {}).get("id") or None
        if new_id:
            self.store.invalidate_memory(mem.get("id"), new_id)

        complete_task = getattr(self.store, "complete_skill_upgrade_task", None)
        if callable(complete_task):
            complete_task(task_id=task_id, new_memory_id=new_id)

        return {"triggered": True, "task_id": task_id, "new_memory_id": new_id, "to_version": to_version}


def _json_dumps(data: Dict[str, Any]) -> str:
    import json

    return json.dumps(data or {}, ensure_ascii=False)
