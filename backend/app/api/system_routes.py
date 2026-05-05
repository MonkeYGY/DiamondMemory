from fastapi import APIRouter

from app.api import config_routes
from app.services.embedding_service import embedding_service

router = APIRouter(prefix="/system", tags=["system"])


def _derive_degraded_reason(startup: dict) -> str:
    if not startup.get("ollama_ready"):
        return "OLLAMA_NOT_RUNNING"
    if not startup.get("llm_installed"):
        return "MODEL_NOT_INSTALLED"
    if not startup.get("llm_loaded"):
        return "MODEL_NOT_LOADED"
    return "OK"


@router.get("/capabilities")
def get_capabilities():
    """统一能力状态接口：用于前端做降级可用性与按钮可用性判断。"""
    startup = config_routes.get_startup_status()
    emb_info = embedding_service.get_backend_info()

    model_ready = bool(startup.get("llm_loaded"))
    degraded_reason = _derive_degraded_reason(startup)

    allowed = {
        "browse": True,
        "search": True,
        "export": True,
        "manage": True,
        "llm_summarize": model_ready,
        "llm_extract_skill": model_ready,
        "graph_rebuild": True,
    }

    return {
        "backend_ready": bool(startup.get("backend_ready")),
        "ollama_ready": bool(startup.get("ollama_ready")),
        "model_ready": model_ready,
        "degraded_reason": degraded_reason,
        "llm": {
            "model": startup.get("llm_model_name", ""),
            "installed": bool(startup.get("llm_installed")),
            "loaded": bool(startup.get("llm_loaded")),
        },
        "embedding": {
            "model": startup.get("embedding_model_name", ""),
            "available": True,
            "backend": emb_info.get("backend", "tfidf"),
        },
        "allowed": allowed,
    }

