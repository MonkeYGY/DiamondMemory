"""Qclaw智能体API路由"""
from fastapi import APIRouter, HTTPException
from typing import Optional
from app.services.qclaw_service import qclaw_service

router = APIRouter(prefix="/qclaw", tags=["qclaw"])


@router.get("/check-installation")
def check_installation():
    result = qclaw_service.check_installation()
    result["diamond_memory_integrated"] = qclaw_service.is_diamond_memory_integrated()
    agents = result.get("agents", [])
    agents_status = []
    for a in agents:
        agents_status.append({
            "id": a.get("id", ""),
            "name": a.get("name", ""),
            "integrated": qclaw_service.is_agent_integrated(a.get("id", ""))
        })
    result["agents_status"] = agents_status
    return result


@router.post("/configure-diamond-memory")
def configure_diamond_memory(agent_id: Optional[str] = None):
    result = qclaw_service.configure_diamond_memory(agent_id)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result)
    return result


@router.post("/unconfigure-diamond-memory")
def unconfigure_diamond_memory(agent_id: Optional[str] = None):
    result = qclaw_service.unconfigure_diamond_memory(agent_id)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result)
    return result


@router.get("/integration-status")
def get_integration_status():
    return {"integrated": qclaw_service.is_diamond_memory_integrated()}


@router.get("/health")
def health_check():
    status = qclaw_service.health_check()
    return {
        "status": "up" if status else "down",
        "service": "qclaw"
    }
