"""MCP协议路由

提供MCP (Model Context Protocol) 标准接口，让其他AI工具可以调用钻石记忆系统的能力。
"""
import sys
import os
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Any, Dict, List, Optional
from app.services.mcp_server_service import mcp_server_service

router = APIRouter()


class MCPToolCallRequest(BaseModel):
    tool_name: str
    arguments: Dict[str, Any] = {}


class MCPBatchRequest(BaseModel):
    calls: List[MCPToolCallRequest]


@router.get("/tools")
def list_tools():
    # 对外契约：带上 schema 版本，便于客户端兼容处理
    from app.services.mcp_server_service import MCP_SCHEMA_VERSION

    return {"mcp_schema_version": MCP_SCHEMA_VERSION, "tools": mcp_server_service.get_tools_schema()}


@router.post("/call")
def call_tool(request: MCPToolCallRequest):
    result = mcp_server_service.handle_tool_call(request.tool_name, request.arguments)
    return {"tool_name": request.tool_name, "result": result}


@router.post("/batch")
def batch_call(request: MCPBatchRequest):
    results = []
    for call in request.calls:
        result = mcp_server_service.handle_tool_call(call.tool_name, call.arguments)
        results.append({"tool_name": call.tool_name, "result": result})
    return {"results": results}


@router.get("/schema")
def get_schema():
    from app.services.mcp_server_service import MCP_SCHEMA_VERSION

    return {
        "protocol": "mcp",
        "version": "1.0",
        "name": "diamond-memory",
        "description": "钻石记忆系统 MCP Server",
        "mcp_schema_version": MCP_SCHEMA_VERSION,
        "tools": mcp_server_service.get_tools_schema(),
    }


@router.get("/self-check")
def self_check():
    """一键自检：推荐客户端接入后第一步调用。"""
    return mcp_server_service.handle_tool_call("get_startup_status", {})


@router.get("/config-info")
def get_mcp_config_info():
    backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    mcp_server_path = os.path.join(backend_dir, "mcp_server.py")

    mcp_installed = False
    try:
        import mcp as _mcp
        mcp_installed = True
    except ImportError:
        pass

    from app.services.mcp_server_service import MCP_SCHEMA_VERSION

    return {
        "python_path": sys.executable,
        "mcp_server_path": mcp_server_path,
        "mcp_server_exists": os.path.exists(mcp_server_path),
        "mcp_package_installed": mcp_installed,
        "mcp_schema_version": MCP_SCHEMA_VERSION,
        "tools": [
            {"name": "search_memories", "description": "搜索记忆库", "params": "query, limit, filters"},
            {"name": "create_memory", "description": "写入一条记忆", "params": "content, category, tags, source, layer, metadata"},
            {"name": "get_startup_status", "description": "一键自检（含降级信息与修复建议）", "params": "无"},
            {"name": "search_knowledge", "description": "搜索知识库", "params": "query"},
            {"name": "get_stats", "description": "系统统计", "params": "无"},
        ],
    }
