"""MCP 一键自检服务

输出要求：
- 返回 pass/fail/degraded + 每项检查的可操作修复建议
- Ollama 缺失时允许降级（degraded），不要直接 fail
"""

from __future__ import annotations

import os
import socket
from typing import Any, Dict, List, Literal, Optional

import requests

from app.config import settings

CheckStatus = Literal["pass", "fail", "degraded"]


def _check_port_open(host: str, port: int, timeout: float = 0.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:
        return False


def _mk_check(
    name: str,
    status: CheckStatus,
    message: str,
    suggestion: str = "",
    details: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return {
        "name": name,
        "status": status,
        "message": message,
        "suggestion": suggestion,
        "details": details or {},
    }


def run_self_check() -> Dict[str, Any]:
    checks: List[Dict[str, Any]] = []

    # 1) 后端在线 / 端口
    port = int(getattr(settings, "server_port", 8000))
    backend_url = f"http://127.0.0.1:{port}"

    if not _check_port_open("127.0.0.1", port):
        checks.append(
            _mk_check(
                "backend",
                "fail",
                f"后端端口未监听: {port}",
                suggestion="请先启动钻石记忆系统后端（或检查端口是否被占用/被防火墙拦截）。",
                details={"port": port},
            )
        )
    else:
        try:
            resp = requests.get(f"{backend_url}/health", timeout=2)
            if resp.status_code == 200:
                checks.append(_mk_check("backend", "pass", "后端在线", details={"url": backend_url}))
            else:
                checks.append(
                    _mk_check(
                        "backend",
                        "fail",
                        f"后端在线但健康检查失败: HTTP {resp.status_code}",
                        suggestion="请查看后端日志，确认依赖服务是否启动。",
                        details={"url": f"{backend_url}/health"},
                    )
                )
        except Exception as e:
            checks.append(
                _mk_check(
                    "backend",
                    "fail",
                    f"后端在线但无法访问 /health: {e}",
                    suggestion="请检查后端是否已完整启动，或确认本机网络代理/防火墙设置。",
                    details={"url": f"{backend_url}/health"},
                )
            )

    # 2) 数据库可写
    try:
        from app.storage.sqlite_store import SQLiteStore

        store = SQLiteStore()
        store.set_config("self_check_last_run", "1", "MCP 自检探针（自动写入，可安全忽略）")
        checks.append(_mk_check("database", "pass", "数据库可写", details={"db_path": store.db_path}))
    except Exception as e:
        checks.append(
            _mk_check(
                "database",
                "fail",
                f"数据库不可写: {e}",
                suggestion="请检查数据目录权限，或在设置中切换数据目录到可写路径。",
            )
        )

    # 3) 向量库可用（允许 fallback）
    try:
        from app.storage import get_active_vector_store

        vs = get_active_vector_store()
        stats = vs.get_stats() if vs and callable(getattr(vs, "get_stats", None)) else {}
        checks.append(
            _mk_check(
                "vector_store",
                "pass",
                "向量库可用",
                details={"engine": stats.get("engine", "unknown"), "vector_count": stats.get("vector_count", 0)},
            )
        )
    except Exception as e:
        checks.append(
            _mk_check(
                "vector_store",
                "fail",
                f"向量库不可用: {e}",
                suggestion="请检查 Qdrant/FAISS 依赖安装情况，或在设置中切换向量引擎。",
            )
        )

    # 4) 知识库路径可读
    kb_path = ""
    try:
        from app.storage.sqlite_store import SQLiteStore

        kb_path = (SQLiteStore().get_config("knowledge_base_path") or "").strip() or getattr(settings, "storage_path", "")
    except Exception:
        kb_path = getattr(settings, "storage_path", "")
    kb_path = (kb_path or "").strip()

    if not kb_path:
        checks.append(_mk_check("knowledge_base_path", "fail", "知识库路径未配置", suggestion="请在设置中指定知识库/工作区路径。"))
    elif not os.path.exists(kb_path):
        checks.append(
            _mk_check(
                "knowledge_base_path",
                "fail",
                f"知识库路径不存在: {kb_path}",
                suggestion="请确认路径是否正确，或在设置中重新选择工作区路径。",
                details={"path": kb_path},
            )
        )
    elif not os.access(kb_path, os.R_OK):
        checks.append(
            _mk_check(
                "knowledge_base_path",
                "fail",
                f"知识库路径不可读: {kb_path}",
                suggestion="请检查目录权限（macOS 需在系统设置中授予文件访问权限）。",
                details={"path": kb_path},
            )
        )
    else:
        checks.append(_mk_check("knowledge_base_path", "pass", "知识库路径可读", details={"path": kb_path}))

    # 5) Ollama 状态（允许降级）
    ollama_url = (getattr(settings, "local_llm_endpoint", "http://127.0.0.1:11434") or "").rstrip("/")
    llm_model = getattr(settings, "local_llm_model", "")
    emb_model = getattr(settings, "embedding_provider", "bge-m3")
    try:
        resp = requests.get(f"{ollama_url}/api/tags", timeout=2)
        if resp.status_code != 200:
            raise RuntimeError(f"HTTP {resp.status_code}")
        models = [m.get("name", "") for m in (resp.json() or {}).get("models", [])]
        has_llm = any(llm_model and (m == llm_model or m.startswith(llm_model.split(":")[0])) for m in models)
        has_emb = any(emb_model and emb_model in m for m in models)

        if not models:
            checks.append(
                _mk_check(
                    "ollama",
                    "degraded",
                    "Ollama 已启动但未发现任何模型",
                    suggestion="可在设置-模型管理中下载模型；也可以先用“外部模型”模式继续使用。",
                    details={"ollama_url": ollama_url},
                )
            )
        elif not has_llm or not has_emb:
            checks.append(
                _mk_check(
                    "ollama",
                    "degraded",
                    "Ollama 已启动但所需模型未安装完整（允许降级）",
                    suggestion=f"请下载/拉取模型：LLM={llm_model}，Embedding={emb_model}",
                    details={"installed_models": models, "llm_model": llm_model, "embedding_model": emb_model},
                )
            )
        else:
            checks.append(
                _mk_check(
                    "ollama",
                    "pass",
                    "Ollama 已就绪",
                    details={"ollama_url": ollama_url, "llm_model": llm_model, "embedding_model": emb_model},
                )
            )
    except Exception as e:
        checks.append(
            _mk_check(
                "ollama",
                "degraded",
                f"Ollama 不可用（允许降级）: {e}",
                suggestion="若需要本地模型能力，请启动 Ollama（默认端口 11434）并下载模型；否则可继续使用降级能力。",
                details={"ollama_url": ollama_url, "expected_port": 11434},
            )
        )

    hard_fail = any(c["status"] == "fail" and c["name"] != "ollama" for c in checks)
    degraded_only = (not hard_fail) and any(c["status"] == "degraded" for c in checks)
    overall_status: CheckStatus = "fail" if hard_fail else ("degraded" if degraded_only else "pass")

    return {"overall_status": overall_status, "checks": checks}
