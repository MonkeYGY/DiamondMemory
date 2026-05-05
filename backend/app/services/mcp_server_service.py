"""MCP (Model Context Protocol) Server 集成服务

会话任务卡（ID=10，P0）目标：MCP 接入体验产品化
- Schema 稳定：固定工具集合 + mcp_schema_version
- 权限隔离：按 source / 管理开关控制读写
- 审计：每次调用记录来源、工具名、参数摘要、结果数量（不记录敏感全文）
- 一键自检：可定位问题，并给出修复建议；Ollama 允许降级
"""
import json
import logging
import os
from typing import Any, Dict, List, Optional
from app.config import settings

logger = logging.getLogger(__name__)

MCP_SCHEMA_VERSION = "1.0.0"


class MCPServerService:
    def _error(self, code: str, message: str, details: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"code": code, "message": message}
        if details:
            payload["details"] = details
        return {"error": payload}

    def get_tools_schema(self) -> List[Dict[str, Any]]:
        # 固定工具集合：对外作为兼容契约（不要随意增删改字段）
        return [
            {
                "name": "search_memories",
                "description": "搜索记忆库，支持 filters 过滤。",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "搜索关键词或自然语言问题"},
                        "limit": {"type": "integer", "default": 10, "description": "返回数量（默认10，最大100）"},
                        "filters": {
                            "type": "object",
                            "description": "过滤条件（可选）。建议通过 filters.source 指定来源用于权限控制/审计。",
                            "properties": {
                                "categories": {"type": "array", "items": {"type": "string"}},
                                "tags": {"type": "array", "items": {"type": "string"}},
                                "layer": {"type": "integer", "description": "只返回指定层级（可选）"},
                                "source": {"type": "string", "description": "来源标识（用于权限控制/审计）"},
                            },
                        },
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "create_memory",
                "description": "创建一条新记忆（写入）。",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "content": {"type": "string", "description": "记忆内容"},
                        "category": {"type": "string", "description": "分类（可选）"},
                        "tags": {"type": "array", "items": {"type": "string"}, "description": "标签（可选）"},
                        "source": {"type": "string", "description": "来源标识（用于权限控制/审计）"},
                        "layer": {"type": "integer", "default": 1, "description": "写入层级（默认1）"},
                        "metadata": {"type": "object", "description": "扩展元数据（可选）"},
                    },
                    "required": ["content", "source"],
                },
            },
            {
                "name": "get_startup_status",
                "description": "一键自检：后端/端口/数据库/向量库/知识库路径/Ollama（允许降级）+ 修复建议。",
                "inputSchema": {"type": "object", "properties": {}},
            },
            {
                "name": "search_knowledge",
                "description": "搜索知识库笔记。",
                "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
            },
            {
                "name": "get_stats",
                "description": "获取统计信息（记忆/向量库/缓存）。",
                "inputSchema": {"type": "object", "properties": {}},
            },
        ]

    def handle_tool_call(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        handler = {
            "search_memories": self._handle_search,
            "create_memory": self._handle_create,
            "get_startup_status": self._handle_startup_status,
            "search_knowledge": self._handle_search_knowledge,
            "get_stats": self._handle_stats,
        }

        handler_fn = handler.get(tool_name)
        if not handler_fn:
            return self._error("UNKNOWN_TOOL", f"未知工具: {tool_name}")

        # 统一在入口做审计（best-effort）
        source = self._extract_source(tool_name, arguments)
        status = "ok"
        err_text = ""
        result: Any = None
        try:
            result = handler_fn(arguments)
            return result
        except Exception as e:
            status = "error"
            err_text = str(e)
            logger.error(f"MCP工具调用失败 [{tool_name}]: {e}")
            return self._error("INTERNAL_ERROR", str(e))
        finally:
            try:
                from app.storage.sqlite_store import SQLiteStore

                SQLiteStore().add_mcp_audit_log(
                    source=source,
                    tool_name=tool_name,
                    args_summary=self._summarize_arguments(arguments),
                    result_count=self._count_results(result),
                    status=status,
                    error=err_text,
                )
            except Exception:
                pass

    def _handle_search(self, args: Dict[str, Any]) -> Dict[str, Any]:
        from app.services.memory_service import memory_service
        from app.services.source_access_control import source_access_control

        query = args.get("query", "")
        limit = min(int(args.get("limit", 10) or 10), 100)

        # 新 schema：filters
        filters = args.get("filters") or {}
        categories = filters.get("categories") or args.get("categories")
        layer = filters.get("layer")

        # MCP 访问控制：支持 filters.source（兼容部分客户端协议）
        source = filters.get("source") or args.get("source")
        if source_access_control.is_mcp_read_blocked(source):
            return self._error(
                "SOURCE_READ_BLOCKED" if not source_access_control.is_source_blocked(source) else "SOURCE_BLOCKED",
                f"来源 '{source}' 当前未被授权读取。",
            )

        result = memory_service.query_memory(query, categories, limit)

        memories = result.get("memories", [])
        simplified = []
        for m in memories:
            if layer is not None and m.get("layer") != layer:
                continue
            simplified.append({
                "id": m.get("id", "")[:8],
                "content": m.get("content", "")[:200],
                "category": m.get("category"),
                "layer": m.get("layer"),
                "score": round(m.get("final_score", m.get("relevance_score", 0)), 3),
                "memory_type": m.get("memory_type", "episodic"),
                "created_at": m.get("created_at"),
            })

        return {
            "mcp_schema_version": MCP_SCHEMA_VERSION,
            "results": simplified,
            "total_found": len(simplified),
            "search_time_ms": result.get("search_time_ms", 0),
            "cache_hit": result.get("cache_hit", False),
        }

    def _handle_create(self, args: Dict[str, Any]) -> Dict[str, Any]:
        from app.services.memory_service import memory_service
        from app.services.source_access_control import source_access_control

        content = args.get("content", "")
        if not content:
            return self._error("INVALID_ARGUMENT", "content 不能为空")

        source = (args.get("source") or "").strip() or os.getenv("DIAMOND_MCP_SOURCE", "") or "unknown"
        if source_access_control.is_mcp_write_blocked(source):
            return self._error(
                "SOURCE_BLOCKED",
                f"来源 '{source}' 当前未被授权写入。",
            )

        result = memory_service.create_memory(
            content=content,
            category=args.get("category"),
            layer=args.get("layer", 1),
            tags=args.get("tags", []),
            source=source,
            metadata=args.get("metadata"),
        )

        if "error" in result:
            return {
                "mcp_schema_version": MCP_SCHEMA_VERSION,
                "status": "duplicate",
                "message": result.get("message", ""),
                "id": result.get("similar_memory_id", "")[:8],
            }

        return {
            "mcp_schema_version": MCP_SCHEMA_VERSION,
            "status": "created",
            "id": result.get("id", "")[:8],
            "layer": result.get("layer"),
            "category": result.get("category"),
            "memory_type": result.get("memory_type", "episodic"),
        }

    def _handle_startup_status(self, args: Dict[str, Any]) -> Dict[str, Any]:
        from app.services.mcp_self_check_service import run_self_check

        return {"mcp_schema_version": MCP_SCHEMA_VERSION, **run_self_check()}

    def _handle_search_knowledge(self, args: Dict[str, Any]) -> Dict[str, Any]:
        from app.services.knowledge_service import knowledge_service
        from app.services.source_access_control import source_access_control

        query = (args.get("query") or "").strip()
        if not query:
            return self._error("INVALID_ARGUMENT", "query 不能为空")

        # 读权限同样纳入控制：允许通过 args.source 传入来源
        source = args.get("source") or os.getenv("DIAMOND_MCP_SOURCE", "") or "unknown"
        if source_access_control.is_mcp_read_blocked(source):
            return self._error("SOURCE_READ_BLOCKED", f"来源 '{source}' 当前未被授权读取。")

        results = knowledge_service.search_notes(query) or []
        simplified = [
            {"path": r.get("path", ""), "title": r.get("title", ""), "snippet": (r.get("snippet") or r.get("content") or "")[:200]}
            for r in results
        ]
        return {"mcp_schema_version": MCP_SCHEMA_VERSION, "results": simplified, "total": len(simplified)}

    def _handle_graph(self, args: Dict[str, Any]) -> Dict[str, Any]:
        from app.services.memory_graph import memory_graph_service

        memory_id = args.get("memory_id")
        max_nodes = args.get("max_nodes", 50)

        if memory_id:
            related = memory_graph_service.get_related_memories(memory_id, max_depth=2)
            return {
                "center_id": memory_id[:8],
                "related_count": len(related),
                "related_memories": [
                    {"id": m.get("id", "")[:8], "content": m.get("content", "")[:100], "depth": m.get("graph_depth", 0)}
                    for m in related[:20]
                ],
            }

        viz_data = memory_graph_service.get_visualization_data(max_nodes=max_nodes)
        stats = memory_graph_service.get_graph_stats()

        return {
            "nodes_count": len(viz_data.get("nodes", [])),
            "edges_count": len(viz_data.get("edges", [])),
            "stats": stats,
        }

    def _handle_stats(self, args: Dict[str, Any]) -> Dict[str, Any]:
        from app.services.memory_service import memory_service
        from app.services.retrieval_cache_service import retrieval_cache_service
        from app.storage import get_active_vector_store

        all_memories = memory_service.list_memories(10000)
        categories = set()
        layer_counts = {}
        for m in all_memories:
            cat = m.get("category")
            if cat:
                categories.add(cat)
            layer = m.get("layer", 0)
            layer_counts[f"l{layer}_count"] = layer_counts.get(f"l{layer}_count", 0) + 1

        cache_stats = retrieval_cache_service.get_stats()
        try:
            vs = get_active_vector_store()
            vector_stats = vs.get_stats() if vs and callable(getattr(vs, "get_stats", None)) else {}
        except Exception:
            vector_stats = {}

        return {
            "mcp_schema_version": MCP_SCHEMA_VERSION,
            "memory_stats": {
                "total": len(all_memories),
                "categories": len(categories),
                **layer_counts,
            },
            "cache_stats": cache_stats,
            "vector_stats": vector_stats,
            "features": {
                "vector_engine": settings.vector_store_engine,
                "graph_rag_enabled": settings.graph_rag_enabled,
                "decay_model": settings.decay_model,
            },
        }

    def _handle_decay_stats(self, args: Dict[str, Any]) -> Dict[str, Any]:
        from app.services.memory_service import memory_service
        from app.services.memory_decay_service import memory_decay_service

        all_memories = memory_service.list_memories(10000)
        stats = memory_decay_service.get_decay_stats(all_memories)

        return stats

    # ------------------
    # audit helpers
    # ------------------
    def _extract_source(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        source = (arguments.get("source") or "").strip()
        if not source and isinstance(arguments.get("filters"), dict):
            source = (arguments["filters"].get("source") or "").strip()
        if not source:
            source = (os.getenv("DIAMOND_MCP_SOURCE", "") or "").strip()
        return source or "unknown"

    def _summarize_arguments(self, arguments: Dict[str, Any]) -> str:
        def _truncate(s: str, limit: int = 80) -> str:
            s = (s or "").replace("\n", " ").strip()
            return (s[:limit] + "…") if len(s) > limit else s

        try:
            args_copy = json.loads(json.dumps(arguments or {}, ensure_ascii=False))
        except Exception:
            args_copy = dict(arguments or {})

        if "content" in args_copy:
            args_copy["content"] = _truncate(str(args_copy.get("content") or ""))
        if "query" in args_copy:
            args_copy["query"] = _truncate(str(args_copy.get("query") or ""))
        if isinstance(args_copy.get("metadata"), dict):
            args_copy["metadata"] = {"keys": list(args_copy["metadata"].keys())[:20]}
        return json.dumps(args_copy, ensure_ascii=False)

    def _count_results(self, result: Any) -> int:
        if not result:
            return 0
        if isinstance(result, dict):
            if isinstance(result.get("results"), list):
                return len(result["results"])
            if isinstance(result.get("total"), int):
                return int(result["total"])
            if isinstance(result.get("total_found"), int):
                return int(result["total_found"])
            return 1
        if isinstance(result, list):
            return len(result)
        return 1


mcp_server_service = MCPServerService()
