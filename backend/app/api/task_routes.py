from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.services.task_queue_service import task_queue_service

router = APIRouter(prefix="/tasks", tags=["tasks"])


class EnqueueTaskRequest(BaseModel):
    type: str
    power_mode: str = "normal"
    params: dict = {}


@router.post("/enqueue")
def enqueue_task(payload: EnqueueTaskRequest):
    """任务入队：第一期采用最小策略，部分任务默认 requires_model=True。"""
    requires_model = payload.type in ("deep_organize", "extract_skills")
    task_id = task_queue_service.enqueue(
        payload.type,
        requires_model=requires_model,
        power_mode=payload.power_mode,
        params=payload.params,
    )
    item = task_queue_service.store.get_task_queue_item(task_id) or {}
    return {"id": task_id, "status": item.get("status", "queued")}


@router.get("")
def list_tasks(
    status: str = Query("", description="逗号分隔状态，如 queued,running,blocked"),
    limit: int = 50,
):
    statuses = [s.strip() for s in (status or "").split(",") if s.strip()]
    items = task_queue_service.store.list_task_queue_items(statuses=statuses or None, limit=min(int(limit), 200))
    return {"items": items}


@router.get("/{task_id}")
def get_task(task_id: str):
    item = task_queue_service.store.get_task_queue_item(task_id)
    if not item:
        raise HTTPException(status_code=404, detail="任务不存在")
    return item


@router.post("/{task_id}/pause")
def pause_task(task_id: str):
    if not task_queue_service.pause(task_id):
        raise HTTPException(status_code=400, detail="无法暂停")
    return {"ok": True}


@router.post("/{task_id}/resume")
def resume_task(task_id: str):
    if not task_queue_service.resume(task_id):
        raise HTTPException(status_code=400, detail="无法继续")
    return {"ok": True}


@router.post("/{task_id}/cancel")
def cancel_task(task_id: str):
    if not task_queue_service.cancel(task_id):
        raise HTTPException(status_code=400, detail="无法取消")
    return {"ok": True}

