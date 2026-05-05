"""L6 技能产品化 API（最小可行）"""

from fastapi import APIRouter, Body, Query, HTTPException
from typing import Optional, Dict, Any

from app.services.skill_service import SkillService
from app.storage import SQLiteStore


router = APIRouter(prefix="/skill", tags=["skill"])

skill_service = SkillService()
store = SQLiteStore()


@router.get("/list")
def list_skills(limit: int = Query(200, ge=1, le=5000)):
    """列出技能（按 skill_id 聚合的最新版本）"""
    return skill_service.list_latest_skills(limit=limit)


@router.get("/versions/{skill_memory_id}")
def get_skill_versions(skill_memory_id: str):
    """按任意版本 memory_id 查询该技能的版本链（root -> latest）"""
    return skill_service.get_skill_versions_by_memory(skill_memory_id)


@router.post("/invoke")
def invoke_skill(skill_memory_id: str = Body(..., embed=True)):
    """记录一次技能调用（累计调用次数/最近调用时间）"""
    try:
        return skill_service.record_invocation(skill_memory_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/feedback")
def feedback_skill(
    skill_memory_id: str = Body(..., embed=True),
    rating: int = Body(..., ge=1, le=5),
    comment: str = Body("", embed=True),
    success: Optional[bool] = Body(None, embed=True),
):
    """提交评分/反馈（可触发自动升级）"""
    try:
        return skill_service.submit_feedback(skill_memory_id, rating=rating, comment=comment, success=success)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/upgrade")
def manual_upgrade_skill(
    skill_memory_id: str = Body(..., embed=True),
    note: str = Body("", embed=True),
):
    """手动触发一次技能升级（生成 v+1，并保留旧版本历史）"""
    try:
        return skill_service.manual_upgrade(skill_memory_id, note=note)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/upgrade-tasks")
def list_upgrade_tasks(
    skill_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
) -> Dict[str, Any]:
    """查看升级任务队列（pending/completed）"""
    tasks = store.list_skill_upgrade_tasks(skill_id=skill_id, status=status, limit=limit)
    return {"tasks": tasks, "total": len(tasks)}

