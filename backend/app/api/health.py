"""健康检查端点（增强版）

展示系统状态和所有优化项的运行状态
"""
from fastapi import APIRouter

router = APIRouter()


@router.get("")
@router.get("/")
async def health_check():
    from app.config import settings

    features = {
        "vector_engine": settings.vector_store_engine,
        "graph_rag_enabled": settings.graph_rag_enabled,
        "decay_model": settings.decay_model,
        "memory_type_enabled": settings.memory_type_enabled,
        "memory_type_auto_classify": settings.memory_type_auto_classify,
        "contradiction_detection_enabled": settings.contradiction_detection_enabled,
        "retrieval_cache_enabled": settings.retrieval_cache_enabled,
        "memory_compression_enabled": settings.memory_compression_enabled,
        "adaptive_organize_enabled": settings.adaptive_organize_enabled,
        "entity_extraction_enhanced": settings.entity_extraction_enhanced,
    }

    services_status = {}
    try:
        from app.storage import get_active_vector_store
        store = get_active_vector_store()
        stats = store.get_stats()
        services_status["vector_store"] = {
            "engine": stats.get("engine", "unknown"),
            "available": True,
            "vector_count": stats.get("vector_count", 0),
        }
    except Exception as e:
        services_status["vector_store"] = {"available": False, "error": str(e)}

    try:
        from app.services.retrieval_cache_service import retrieval_cache_service
        cache_stats = retrieval_cache_service.get_stats()
        services_status["retrieval_cache"] = {
            "available": True,
            "query_cache_size": cache_stats.get("query_cache", {}).get("size", 0),
            "hit_rate": cache_stats.get("query_cache", {}).get("hit_rate", 0),
        }
    except Exception:
        services_status["retrieval_cache"] = {"available": False}

    try:
        from app.services.adaptive_organize_service import adaptive_organize_service
        adaptive_stats = adaptive_organize_service.get_stats()
        services_status["adaptive_organize"] = {
            "available": True,
            "cpu_percent": adaptive_stats.get("cpu_percent", 0),
            "memory_percent": adaptive_stats.get("memory_percent", 0),
        }
    except Exception:
        services_status["adaptive_organize"] = {"available": False}

    try:
        from app.services.memory_graph import memory_graph_service
        graph_stats = memory_graph_service.get_graph_stats()
        services_status["memory_graph"] = {
            "available": True,
            "nodes": graph_stats.get("nodes", 0),
            "edges": graph_stats.get("edges", 0),
        }
    except Exception:
        services_status["memory_graph"] = {"available": False}

    return {
        "status": "ok",
        "service": "diamond_memory_backend",
        "version": "0.9.0",
        "features": features,
        "services": services_status,
    }
