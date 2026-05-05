"""OpenClaw智能体API路由"""
from fastapi import APIRouter, HTTPException
from typing import List, Optional, Dict, Any
from app.services.openclaw_service import openclaw_service

router = APIRouter(prefix="/openclaw", tags=["openclaw"])


@router.get("/check-installation")
def check_installation():
    result = openclaw_service.check_installation()
    result["diamond_memory_integrated"] = openclaw_service.is_diamond_memory_integrated()
    agents = result.get("agents", [])
    agents_status = []
    for a in agents:
        agents_status.append({
            "id": a.get("id", ""),
            "name": a.get("name", ""),
            "integrated": openclaw_service.is_agent_integrated(a.get("id", ""))
        })
    result["agents_status"] = agents_status
    return result


@router.post("/configure-diamond-memory")
def configure_diamond_memory(agent_id: Optional[str] = None):
    result = openclaw_service.configure_diamond_memory(agent_id)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result)
    return result


@router.post("/unconfigure-diamond-memory")
def unconfigure_diamond_memory(agent_id: Optional[str] = None):
    result = openclaw_service.unconfigure_diamond_memory(agent_id)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result)
    return result


@router.get("/integration-status")
def get_integration_status():
    return {"integrated": openclaw_service.is_diamond_memory_integrated()}


@router.get("/agents")
def get_agents():
    result = openclaw_service.get_agents()
    if not result.get("success") and "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])
    return result


@router.get("/agents/{agent_id}")
def get_agent(agent_id: str):
    result = openclaw_service.get_agent(agent_id)
    if not result.get("success") and "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])
    return result


@router.post("/agents")
def create_agent(
    name: str,
    description: str,
    instructions: str,
    tools: Optional[List[Dict[str, Any]]] = None
):
    result = openclaw_service.create_agent(
        name=name,
        description=description,
        instructions=instructions,
        tools=tools
    )
    if not result.get("success") and "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])
    return result


@router.post("/agents/{agent_id}/run")
def run_agent(
    agent_id: str,
    message: str,
    context: Optional[Dict[str, Any]] = None
):
    result = openclaw_service.run_agent(
        agent_id=agent_id,
        message=message,
        context=context
    )
    if not result.get("success") and "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])
    return result


@router.get("/agents/{agent_id}/history")
def get_agent_history(
    agent_id: str,
    limit: int = 10
):
    result = openclaw_service.get_agent_history(agent_id, limit)
    if not result.get("success") and "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])
    return result


@router.put("/agents/{agent_id}")
def update_agent(
    agent_id: str,
    **kwargs
):
    result = openclaw_service.update_agent(agent_id, **kwargs)
    if not result.get("success") and "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])
    return result


@router.delete("/agents/{agent_id}")
def delete_agent(agent_id: str):
    result = openclaw_service.delete_agent(agent_id)
    if not result.get("success") and "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])
    return result


@router.get("/health")
def health_check():
    status = openclaw_service.health_check()
    return {
        "status": "up" if status else "down",
        "service": "openclaw"
    }
