import sys
import os
import json
import logging
from typing import Any, Dict, Optional

# 确保 backend 目录在 sys.path 中，以便能导入 app 模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mcp.server.fastmcp import FastMCP

from app.services.mcp_server_service import MCP_SCHEMA_VERSION
from app.services.source_access_control import source_access_control

# 初始化 FastMCP 服务器（stdio）
mcp = FastMCP("DiamondMemory", description="钻石记忆系统 MCP Server（stdio）")

# 抑制一些日志输出，以免污染 stdio
logging.getLogger("app").setLevel(logging.WARNING)


def _audit(source: str, tool_name: str, arguments: Dict[str, Any], result: Any, status: str = "ok", error: str = ""):
    """best-effort MCP 审计（不记录敏感全文）。"""
    try:
        from app.storage.sqlite_store import SQLiteStore

        args_copy = json.loads(json.dumps(arguments or {}, ensure_ascii=False))
        if "content" in args_copy:
            s = str(args_copy.get("content") or "").replace("\n", " ").strip()
            args_copy["content"] = (s[:80] + "…") if len(s) > 80 else s
        if "query" in args_copy:
            s = str(args_copy.get("query") or "").replace("\n", " ").strip()
            args_copy["query"] = (s[:80] + "…") if len(s) > 80 else s
        if isinstance(args_copy.get("metadata"), dict):
            args_copy["metadata"] = {"keys": list(args_copy["metadata"].keys())[:20]}
        args_summary = json.dumps(args_copy, ensure_ascii=False)

        result_count = 0
        if isinstance(result, dict) and isinstance(result.get("results"), list):
            result_count = len(result["results"])
        elif isinstance(result, list):
            result_count = len(result)
        elif result:
            result_count = 1

        SQLiteStore().add_mcp_audit_log(
            source=source or "unknown",
            tool_name=tool_name,
            args_summary=args_summary,
            result_count=result_count,
            status=status,
            error=error,
        )
    except Exception:
        pass


def _get_source(explicit: Optional[str] = None) -> str:
    return (explicit or "").strip() or (os.getenv("DIAMOND_MCP_SOURCE", "") or "").strip() or "unknown"


@mcp.tool()
def search_memories(query: str, limit: int = 10, filters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """search_memories(query, limit, filters)"""
    from app.services.memory_service import memory_service

    filters = filters or {}
    source = _get_source(filters.get("source"))
    if source_access_control.is_mcp_read_blocked(source):
        return {"error": {"code": "SOURCE_READ_BLOCKED", "message": f"来源 '{source}' 当前未被授权读取。"}}

    try:
        categories = filters.get("categories")
        layer = filters.get("layer")
        limit = min(int(limit or 10), 100)
        result = memory_service.query_memory(query, categories, limit)
        memories = result.get("memories", [])
        simplified = []
        for m in memories:
            if layer is not None and m.get("layer") != layer:
                continue
            simplified.append(
                {
                    "id": m.get("id", "")[:8],
                    "content": m.get("content", "")[:200],
                    "category": m.get("category"),
                    "layer": m.get("layer"),
                    "score": round(m.get("final_score", m.get("relevance_score", 0)), 3),
                }
            )
        payload = {"mcp_schema_version": MCP_SCHEMA_VERSION, "results": simplified, "total_found": len(simplified)}
        _audit(source, "search_memories", {"query": query, "limit": limit, "filters": filters}, payload)
        return payload
    except Exception as e:
        _audit(source, "search_memories", {"query": query, "limit": limit, "filters": filters}, None, status="error", error=str(e))
        return {"error": {"code": "TOOL_ERROR", "message": str(e)}}


@mcp.tool()
def create_memory(
    content: str,
    category: Optional[str] = None,
    tags: Optional[list] = None,
    source: str = "unknown",
    layer: int = 1,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """create_memory(content, category, tags, source, layer, metadata)"""
    from app.services.memory_service import memory_service

    src = _get_source(source)
    if source_access_control.is_mcp_write_blocked(src):
        return {"error": {"code": "SOURCE_BLOCKED", "message": f"来源 '{src}' 当前未被授权写入。"}}

    try:
        result = memory_service.create_memory(
            content=content,
            category=category,
            tags=tags or [],
            source=src,
            layer=layer,
            metadata=metadata,
        )
        if "error" in result:
            payload = {
                "mcp_schema_version": MCP_SCHEMA_VERSION,
                "status": "duplicate",
                "message": result.get("message", ""),
                "id": result.get("similar_memory_id", "")[:8],
            }
        else:
            payload = {
                "mcp_schema_version": MCP_SCHEMA_VERSION,
                "status": "created",
                "id": result.get("id", "")[:8],
                "layer": result.get("layer"),
                "category": result.get("category"),
            }
        _audit(src, "create_memory", {"content": content, "category": category, "tags": tags, "source": src, "layer": layer, "metadata": metadata}, payload)
        return payload
    except Exception as e:
        _audit(src, "create_memory", {"content": content, "category": category, "tags": tags, "source": src, "layer": layer, "metadata": metadata}, None, status="error", error=str(e))
        return {"error": {"code": "TOOL_ERROR", "message": str(e)}}


@mcp.tool()
def get_startup_status() -> Dict[str, Any]:
    """get_startup_status()：一键自检（允许 Ollama 降级）。"""
    from app.services.mcp_self_check_service import run_self_check

    payload = {"mcp_schema_version": MCP_SCHEMA_VERSION, **run_self_check()}
    _audit(_get_source(None), "get_startup_status", {}, payload)
    return payload


@mcp.tool()
def search_knowledge(query: str) -> Dict[str, Any]:
    """search_knowledge(query)"""
    from app.services.knowledge_service import knowledge_service

    source = _get_source(None)
    if source_access_control.is_mcp_read_blocked(source):
        return {"error": {"code": "SOURCE_READ_BLOCKED", "message": f"来源 '{source}' 当前未被授权读取。"}}

    results = knowledge_service.search_notes((query or "").strip()) or []
    simplified = [
        {"path": r.get("path", ""), "title": r.get("title", ""), "snippet": (r.get("snippet") or r.get("content") or "")[:200]}
        for r in results
    ]
    payload = {"mcp_schema_version": MCP_SCHEMA_VERSION, "results": simplified, "total": len(simplified)}
    _audit(source, "search_knowledge", {"query": query}, payload)
    return payload


@mcp.tool()
def get_stats() -> Dict[str, Any]:
    """get_stats()"""
    from app.services.mcp_server_service import mcp_server_service as http_mcp_service

    payload = http_mcp_service.handle_tool_call("get_stats", {})
    if isinstance(payload, dict) and "mcp_schema_version" not in payload:
        payload["mcp_schema_version"] = MCP_SCHEMA_VERSION
    _audit(_get_source(None), "get_stats", {}, payload)
    return payload


if __name__ == "__main__":
    mcp.run(transport="stdio")
