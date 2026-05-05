"""用户配置和分类管理API路由"""
import logging
import os
import re
import threading
import time
import uuid

import json

from fastapi import APIRouter, Body, HTTPException, Query

from app.config import settings
from app.config.settings import update_data_directory, update_storage_path
from app.services.md_export_service import md_export_service
from app.services.memory_service import memory_service
from app.storage.sqlite_store import SQLiteStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/config", tags=["config"])
store = SQLiteStore()
# 启动时同步一次关键开关到 runtime settings（避免重启后丢失 / 让其他路由可直接读取 settings）
try:
    _allow_history = store.get_config("allow_history_query")
    if _allow_history is not None:
        settings.allow_history_query = str(_allow_history).lower() == "true"
except Exception:
    pass
startup_runtime = {
    "backend_ready": False,
    "ollama_ready": False,
    "warmup_phase": "idle",
    "llm_model_name": settings.local_llm_model,
    "embedding_model_name": settings.embedding_provider,
    "llm_loaded": False,
    "embedding_loaded": False,
    "last_error": "",
}

def update_startup_runtime(**kwargs):
    startup_runtime.update(kwargs)

def _get_keep_alive_for_ollama():
    keep_alive = store.get_config("keep_alive")
    if keep_alive is None or keep_alive == "":
        return -1
    try:
        return int(keep_alive)
    except (ValueError, TypeError):
        return keep_alive

DEFAULT_SYSTEM_TAGS = ["开发辅助", "日常对话", "知识经验", "系统配置", "错误排查", "功能需求", "工作流"]

@router.get("/tags")
def get_tags():
    system_tags_str = store.get_config("system_tags")
    user_tags_str = store.get_config("user_tags")
    
    system_tags = json.loads(system_tags_str) if system_tags_str else DEFAULT_SYSTEM_TAGS
    user_tags = json.loads(user_tags_str) if user_tags_str else []
    
    return {
        "system_tags": system_tags,
        "user_tags": user_tags,
        "all_tags": system_tags + user_tags
    }

@router.post("/tags/user")
def add_user_tag(tag: str = Body(..., embed=True)):
    user_tags_str = store.get_config("user_tags")
    user_tags = json.loads(user_tags_str) if user_tags_str else []
    
    tag = tag.strip()
    if tag and tag not in user_tags and tag not in DEFAULT_SYSTEM_TAGS:
        user_tags.append(tag)
        store.set_config("user_tags", json.dumps(user_tags))
        
    return {"status": "success", "user_tags": user_tags}

@router.delete("/tags/user/{tag}")
def delete_user_tag(tag: str):
    user_tags_str = store.get_config("user_tags")
    user_tags = json.loads(user_tags_str) if user_tags_str else []
    
    if tag in user_tags:
        user_tags.remove(tag)
        store.set_config("user_tags", json.dumps(user_tags))
        
    return {"status": "success", "user_tags": user_tags}

import threading

_pull_progress = {}
_pull_progress_lock = threading.Lock()
_pull_threads = {}
_pull_cancel_flags = {}
_MAX_CONCURRENT_PULLS = 3


def _get_ollama_url():
    return settings.local_llm_endpoint.rstrip("/")

def _validate_abs_dir_path(input_path: str) -> str:
    """用于 data_directory / storage_path 等目录型配置的基础校验。"""
    if not isinstance(input_path, str):
        raise HTTPException(status_code=400, detail="路径无效")
    p = input_path.strip()
    if not p or "\0" in p:
        raise HTTPException(status_code=400, detail="路径无效")
    if not os.path.isabs(p):
        raise HTTPException(status_code=400, detail="路径必须为绝对路径")

    resolved = os.path.abspath(p)
    # 禁止根目录：容易导致全盘扫描/误删/权限异常
    import sys as _sys
    root = os.path.abspath(os.path.splitdrive(resolved)[0] + os.sep) if _sys.platform == "win32" else os.path.abspath(os.sep)
    if os.path.abspath(resolved) == root:
        raise HTTPException(status_code=400, detail="禁止将路径设置为磁盘根目录")
    return resolved

def _validate_ollama_model_name(model_name: str) -> str:
    """基础校验：避免空值/空白/参数注入（如以 '-' 开头）。"""
    if not isinstance(model_name, str):
        raise HTTPException(status_code=400, detail="model_name 必须为字符串")
    name = model_name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="model_name 不能为空")
    if name.startswith("-"):
        raise HTTPException(status_code=400, detail="model_name 非法")
    if re.search(r"\s", name):
        raise HTTPException(status_code=400, detail="model_name 不能包含空白字符")
    # 允许 ollama 常见命名：namespace/model:tag 或 model:tag
    if not re.match(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,200}$", name):
        raise HTTPException(status_code=400, detail="model_name 包含非法字符")
    return name


@router.get("/llm-model")
def get_llm_model():
    llm_enabled = store.get_config("llm_enabled")
    llm_enabled = llm_enabled.lower() == "true" if llm_enabled else getattr(settings, "llm_enabled", True)
    provider = store.get_config("llm_provider") or settings.llm_provider
    ext_endpoint = store.get_config("external_llm_endpoint") or settings.external_llm_endpoint
    ext_api_key = store.get_config("external_llm_api_key") or settings.external_llm_api_key
    ext_model = store.get_config("external_llm_model") or settings.external_llm_model

    return {
        "model": ext_model if provider == "external" else settings.local_llm_model,
        "provider": provider,
        "llm_enabled": llm_enabled,
        "local": {"model": settings.local_llm_model, "endpoint": settings.local_llm_endpoint},
        "external": {"endpoint": ext_endpoint, "api_key": bool(ext_api_key), "model": ext_model},
    }


@router.get("/test-external")
def test_external():
    from app.services.inference.inference_service import inference_service

    res = inference_service.generate_text("你好，请只回复'连接成功'四个字。", max_tokens=10)
    if res.get("success"):
        return {"success": True, "message": "连接成功！"}
    return {"success": False, "error": res.get("error", "未知错误")}


@router.post("/pull-model")
async def pull_model(model_name: str = Body(..., embed=True)):
    model_name = _validate_ollama_model_name(model_name)
    with _pull_progress_lock:
        pulling_count = sum(1 for p in _pull_progress.values() if p.get("status") == "pulling")
        if pulling_count >= _MAX_CONCURRENT_PULLS:
            return {"message": "同时下载任务过多，请稍后重试", "model": model_name, "status": "rejected"}
        if model_name in _pull_progress and _pull_progress[model_name].get("status") == "pulling":
            return {"message": f"模型 {model_name} 正在下载中", "model": model_name, "status": "already_pulling"}
        cancel_flag = threading.Event()
        _pull_cancel_flags[model_name] = cancel_flag
        _pull_progress[model_name] = {
            "status": "pulling",
            "progress": 0,
            "total": 0,
            "completed": 0,
            "error": None,
            "started_at": time.time(),
        }

    def _pull():
        try:
            logger.info("[ModelPull] 开始拉取模型: %s", model_name)
            import requests

            pull_url = f"{_get_ollama_url()}/api/pull"
            resp = requests.post(
                pull_url,
                json={"name": model_name, "stream": True},
                stream=True,
                timeout=600,
            )
            if resp.status_code != 200:
                with _pull_progress_lock:
                    _pull_progress[model_name] = {
                        **_pull_progress.get(model_name, {}),
                        "status": "failed",
                        "status_detail": "下载失败",
                        "error": f"HTTP {resp.status_code}",
                        "finished_at": time.time(),
                    }
                return

            last_total = 0
            last_completed = 0
            last_progress = 0

            for raw_line in resp.iter_lines(decode_unicode=True):
                if cancel_flag.is_set():
                    with _pull_progress_lock:
                        _pull_progress[model_name] = {
                            **_pull_progress.get(model_name, {}),
                            "status": "cancelled",
                            "status_detail": "已取消",
                            "finished_at": time.time(),
                        }
                    return

                line = (raw_line or "").strip()
                if not line:
                    continue

                try:
                    data = json.loads(line)
                except Exception:
                    with _pull_progress_lock:
                        _pull_progress[model_name] = {
                            **_pull_progress.get(model_name, {}),
                            "status": "pulling",
                            "status_detail": line[:200],
                            "error": None,
                        }
                    continue

                status_detail = str(data.get("status") or "")
                if data.get("error"):
                    with _pull_progress_lock:
                        _pull_progress[model_name] = {
                            **_pull_progress.get(model_name, {}),
                            "status": "failed",
                            "status_detail": "下载失败",
                            "error": str(data.get("error")),
                            "finished_at": time.time(),
                        }
                    return

                total = int(data.get("total") or last_total or 0)
                completed = int(data.get("completed") or last_completed or 0)
                progress = last_progress
                if total > 0:
                    progress = int(completed / total * 100)

                last_total = total
                last_completed = completed
                last_progress = progress

                if cancel_flag.is_set():
                    with _pull_progress_lock:
                        _pull_progress[model_name] = {
                            **_pull_progress.get(model_name, {}),
                            "status": "cancelled",
                            "status_detail": "已取消",
                            "finished_at": time.time(),
                        }
                    return

                with _pull_progress_lock:
                    _pull_progress[model_name] = {
                        **_pull_progress.get(model_name, {}),
                        "status": "pulling",
                        "progress": progress,
                        "total": total,
                        "completed": completed,
                        "status_detail": status_detail,
                        "error": None,
                    }

                if status_detail.lower() == "success":
                    with _pull_progress_lock:
                        _pull_progress[model_name] = {
                            **_pull_progress.get(model_name, {}),
                            "status": "completed",
                            "progress": 100,
                            "total": last_total,
                            "completed": last_total if last_total > 0 else last_completed,
                            "status_detail": "下载完成",
                            "error": None,
                            "finished_at": time.time(),
                        }
                    logger.info("[ModelPull] 模型 %s 拉取成功", model_name)
                    return

            if cancel_flag.is_set():
                with _pull_progress_lock:
                    _pull_progress[model_name] = {
                        **_pull_progress.get(model_name, {}),
                        "status": "cancelled",
                        "status_detail": "已取消",
                        "finished_at": time.time(),
                    }
                return

            with _pull_progress_lock:
                _pull_progress[model_name] = {
                    **_pull_progress.get(model_name, {}),
                    "status": "failed",
                    "status_detail": "下载结束",
                    "error": "未收到 success 状态",
                    "finished_at": time.time(),
                }
        except Exception as e:
            with _pull_progress_lock:
                _pull_progress[model_name] = {
                    "status": "failed",
                    "progress": _pull_progress[model_name].get("progress", 0),
                    "total": _pull_progress[model_name].get("total", 0),
                    "completed": _pull_progress[model_name].get("completed", 0),
                    "status_detail": "下载异常",
                    "error": str(e),
                    "started_at": _pull_progress[model_name].get("started_at", time.time()),
                    "finished_at": time.time(),
                }
            logger.error("[ModelPull] 模型拉取异常: %s", e)
        finally:
            with _pull_progress_lock:
                _pull_threads.pop(model_name, None)
                _pull_cancel_flags.pop(model_name, None)

    thread = threading.Thread(target=_pull, daemon=True)
    _pull_threads[model_name] = thread
    thread.start()
    return {"message": f"开始拉取模型 {model_name}", "model": model_name, "status": "started"}


@router.get("/pull-progress/{model_name}")
def get_pull_progress(model_name: str):
    with _pull_progress_lock:
        return _pull_progress.get(model_name, {"status": "not_started", "progress": 0, "total": 0, "completed": 0, "error": None})


@router.get("/pull-progress")
def get_all_pull_progress():
    with _pull_progress_lock:
        return {"pulls": dict(_pull_progress)}


@router.post("/cancel-pull")
def cancel_pull(model_name: str = Body(..., embed=True)):
    model_name = _validate_ollama_model_name(model_name)
    with _pull_progress_lock:
        flag = _pull_cancel_flags.get(model_name)
        if flag:
            flag.set()
        if model_name in _pull_progress and _pull_progress[model_name].get("status") == "pulling":
            _pull_progress[model_name] = {
                **_pull_progress[model_name],
                "status": "cancelled",
                "status_detail": "已取消",
                "finished_at": time.time(),
            }
            return {"message": f"已取消下载 {model_name}", "model": model_name, "status": "cancelled"}
        return {"message": f"模型 {model_name} 未在下载中", "model": model_name, "status": "not_pulling"}


@router.get("/ollama-status")
def get_ollama_status():
    import requests

    try:
        resp = requests.get(f"{_get_ollama_url()}/api/tags", timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            models = data.get("models", [])
            model_names = [m.get("name", "") for m in models]
            model_details = [
                {"name": m.get("name", ""), "size": m.get("size", 0), "modified_at": m.get("modified_at", ""), "details": m.get("details", {})}
                for m in models
            ]
            return {
                "running": True,
                "models": model_names,
                "model_details": model_details,
                "has_model": settings.local_llm_model in model_names,
                "has_embedding_model": any("bge-m3" in m for m in model_names),
            }
        return {"running": False, "models": [], "model_details": [], "has_model": False, "has_embedding_model": False}
    except Exception as e:
        logger.warning("[OllamaStatus] 检查失败: %s", e)
        return {"running": False, "models": [], "model_details": [], "has_model": False, "has_embedding_model": False}


@router.get("/startup-status")
def get_startup_status():
    import requests

    llm_name = settings.local_llm_model
    emb_name = settings.embedding_provider

    try:
        tags_resp = requests.get(f"{_get_ollama_url()}/api/tags", timeout=5)
        ps_resp = requests.get(f"{_get_ollama_url()}/api/ps", timeout=5)

        installed_models = []
        loaded_models = []

        tags_ok = tags_resp.status_code == 200
        ps_ok = ps_resp.status_code == 200
        ollama_ready = tags_ok or ps_ok

        if tags_ok:
            installed_models = [m.get("name", "") for m in tags_resp.json().get("models", [])]
        if ps_ok:
            loaded_models = [m.get("name", "") for m in ps_resp.json().get("models", [])]

        llm_prefix = llm_name.split(":")[0]
        llm_installed = any(name == llm_name or name.startswith(llm_prefix) for name in installed_models)
        llm_loaded = any(name == llm_name or name.startswith(llm_prefix) for name in loaded_models)
        embedding_installed = any("bge-m3" in name for name in installed_models)
        embedding_loaded = any("bge-m3" in name for name in loaded_models)

        warmup_phase = startup_runtime["warmup_phase"]
        if llm_loaded and embedding_loaded:
            warmup_phase = "ready"
        elif ollama_ready and (llm_installed or embedding_installed):
            warmup_phase = "warming_up"
        elif ollama_ready:
            warmup_phase = "no_models"

        _result = {
            "backend_ready": startup_runtime["backend_ready"],
            "ollama_ready": ollama_ready,
            "llm_model_name": llm_name,
            "embedding_model_name": emb_name,
            "llm_installed": llm_installed,
            "llm_loaded": llm_loaded,
            "embedding_installed": embedding_installed,
            "embedding_loaded": embedding_loaded,
            "warmup_phase": warmup_phase,
            "last_error": startup_runtime["last_error"],
            "installed_models": installed_models,
            "loaded_models": loaded_models,
        }
        startup_runtime["llm_loaded"] = llm_loaded
        startup_runtime["embedding_loaded"] = embedding_loaded
        return _result
    except Exception as exc:
        logger.warning("[StartupStatus] 检查失败: %s", exc)
        return {
            "backend_ready": startup_runtime["backend_ready"],
            "ollama_ready": False,
            "llm_model_name": llm_name,
            "embedding_model_name": emb_name,
            "llm_installed": False,
            "llm_loaded": False,
            "embedding_installed": False,
            "embedding_loaded": False,
            "warmup_phase": "degraded",
            "last_error": str(exc),
            "installed_models": [],
            "loaded_models": [],
        }


@router.post("/switch-model")
async def switch_model(model_name: str = Body(..., embed=True)):
    import requests

    model_name = _validate_ollama_model_name(model_name)
    previous_model_name = settings.local_llm_model

    try:
        settings.local_llm_model = model_name
        store.set_config("local_llm_model", model_name, "当前使用的LLM模型")
        store.set_config("llm_enabled", "true", "大模型处理开关")
        settings.llm_enabled = True
        startup_runtime["llm_model_name"] = model_name
    except Exception as e:
        logger.error("[ModelSwitch] 保存模型配置失败: %s", e)
        raise HTTPException(status_code=500, detail="保存模型配置失败")

    def _switch():
        try:
            logger.info("[ModelSwitch] 开始切换模型到: %s", model_name)

            update_startup_runtime(warmup_phase="warming_up", llm_loaded=False, last_error=f"正在切换到模型 {model_name}...")
            keep_alive = _get_keep_alive_for_ollama()

            try:
                resp = requests.post(
                    f"{_get_ollama_url()}/api/generate",
                    json={"model": previous_model_name, "prompt": "", "stream": False, "keep_alive": 0},
                    timeout=10,
                )
                if resp.status_code == 200:
                    logger.info("[ModelSwitch] 已卸载当前模型: %s", previous_model_name)
                else:
                    logger.warning("[ModelSwitch] 卸载模型响应异常: %d", resp.status_code)
            except Exception as e:
                logger.warning("[ModelSwitch] 卸载模型失败: %s", e)

            try:
                resp = requests.post(
                    f"{_get_ollama_url()}/api/generate",
                    json={"model": model_name, "prompt": "", "stream": False, "keep_alive": keep_alive},
                    timeout=120,
                )
                if resp.status_code == 200:
                    logger.info("[ModelSwitch] 新模型加载成功: %s", model_name)
                    update_startup_runtime(llm_loaded=True, warmup_phase="ready", last_error="")
                else:
                    logger.warning("[ModelSwitch] 新模型加载失败: %s", resp.text)
                    update_startup_runtime(warmup_phase="degraded", last_error=f"模型 {model_name} 加载失败")
            except Exception as e:
                logger.warning("[ModelSwitch] 加载模型失败: %s", e)
                update_startup_runtime(warmup_phase="degraded", last_error=f"模型 {model_name} 加载异常: {str(e)}")
        except Exception as e:
            logger.error("[ModelSwitch] 切换模型异常: %s", e)
            update_startup_runtime(warmup_phase="degraded", last_error=f"切换模型异常: {str(e)}")

    thread = threading.Thread(target=_switch, daemon=True)
    thread.start()
    return {"message": f"正在切换模型到 {model_name}", "model": model_name}


@router.post("/preload-models")
def preload_models():
    import requests
    import threading

    def _preload():
        llm_model = settings.local_llm_model
        emb_model = settings.embedding_provider
        keep_alive = _get_keep_alive_for_ollama()

        try:
            logger.info("[Preload] 正在常驻加载 LLM 模型: %s", llm_model)
            requests.post(
                f"{_get_ollama_url()}/api/generate",
                json={"model": llm_model, "prompt": "", "stream": False, "keep_alive": keep_alive},
                timeout=120,
            )
            logger.info("[Preload] LLM 模型 %s 已常驻内存", llm_model)
        except Exception as e:
            logger.warning("[Preload] 加载 LLM 模型失败: %s", e)

        try:
            logger.info("[Preload] 正在常驻加载 Embedding 模型: %s", emb_model)
            requests.post(
                f"{_get_ollama_url()}/api/embeddings",
                json={"model": emb_model, "prompt": "warmup", "keep_alive": keep_alive},
                timeout=120,
            )
            logger.info("[Preload] Embedding 模型 %s 已常驻内存", emb_model)
        except Exception as e:
            logger.warning("[Preload] 加载 Embedding 模型失败: %s", e)

    thread = threading.Thread(target=_preload, daemon=True)
    thread.start()
    return {"message": "模型预加载已启动"}


@router.get("/external-token-usage")
def get_external_token_usage():
    usage = store.get_config("external_llm_token_usage")
    return {"total_tokens": int(usage) if usage else 0}


@router.post("/unload-models")
def unload_models():
    import requests
    ollama_url = _get_ollama_url()
    try:
        resp = requests.get(f"{ollama_url}/api/ps", timeout=5)
        if resp.status_code == 200:
            loaded = resp.json().get("models", [])
            for m in loaded:
                model_name = m.get("name", "")
                if model_name:
                    try:
                        requests.post(f"{ollama_url}/api/generate", json={
                            "model": model_name,
                            "prompt": "",
                            "stream": False,
                            "keep_alive": 0
                        }, timeout=10)
                        logger.info(f"[Unload] 已卸载模型: {model_name}")
                    except Exception as e:
                        logger.warning(f"[Unload] 卸载模型 {model_name} 失败: {e}")
            return {"message": f"已卸载 {len(loaded)} 个模型", "unloaded": len(loaded)}
        return {"message": "无法获取已加载模型列表", "unloaded": 0}
    except Exception as e:
        logger.warning(f"[Unload] 卸载模型异常: {e}")
        return {"message": f"卸载模型异常: {str(e)}", "unloaded": 0}


@router.post("/restart-backend-for-models")
def restart_backend_for_models():
    import threading
    import time

    def _do_restart():
        logger.info("[RestartForModels] 3秒后重启后端服务以加载大模型...")
        time.sleep(3)
        import os, signal
        os.kill(os.getpid(), signal.SIGTERM)

    threading.Thread(target=_do_restart, daemon=True).start()
    return {"message": "后端将在3秒后自动重启，大模型将自动加载到内存"}


@router.get("/get")
def get_config(key: str):
    value = store.get_config(key)
    # 允许读取“有默认值但尚未落库”的配置
    if value is None:
        if key == "allow_history_query":
            return {"key": key, "value": "true" if getattr(settings, "allow_history_query", False) else "false"}
        raise HTTPException(status_code=404, detail=f"配置项 '{key}' 不存在")
    return {"key": key, "value": value}


@router.post("/set")
def set_config(key: str = Body(...), value: str = Body(...), description: str = Body(None)):
    ALLOWED_KEYS = {
        "llm_provider", "llm_enabled", "local_llm_model", "external_llm_endpoint",
        "external_llm_api_key", "external_llm_model", "embedding_provider",
        "embedding_dimensions", "ollama_host", "keep_alive",
        "knowledge_base_path", "auto_organize", "auto_organize_interval",
        "user_tags", "system_tags",
        "allow_history_query",
    }
    if key not in ALLOWED_KEYS:
        raise HTTPException(status_code=400, detail=f"不允许修改配置项 '{key}'")

    if key == "llm_provider" and value == "external":
        pass

    if key == "llm_provider":
        settings.llm_provider = value
    elif key == "llm_enabled":
        settings.llm_enabled = value.lower() == "true"
    elif key == "local_llm_model":
        settings.local_llm_model = value
    elif key == "external_llm_endpoint":
        settings.external_llm_endpoint = value
    elif key == "external_llm_api_key":
        settings.external_llm_api_key = value
    elif key == "external_llm_model":
        settings.external_llm_model = value
    elif key == "embedding_provider":
        settings.embedding_provider = value
    elif key == "embedding_dimensions":
        try:
            settings.embedding_dimensions = int(value)
        except (ValueError, TypeError):
            pass
    elif key == "ollama_host":
        new_host = value
        if new_host.startswith("http://") or new_host.startswith("https://"):
            settings.local_llm_endpoint = new_host
        else:
            settings.local_llm_endpoint = f"http://{new_host}"
        try:
            from app.services.embedding_service import embedding_service
            embedding_service._ollama_url = settings.local_llm_endpoint.rstrip("/")
            embedding_service._ollama_available = False
            embedding_service._last_check_time = 0
        except Exception:
            pass
        try:
            from app.services.inference.inference_service import inference_service
            inference_service.ollama_api_url = settings.local_llm_endpoint.rstrip("/")
        except Exception:
            pass
    elif key == "allow_history_query":
        settings.allow_history_query = str(value).lower() == "true"

    success = store.set_config(key, value, description)
    if success:
        return {"message": "配置更新成功", "key": key, "value": value}
    raise HTTPException(status_code=500, detail="配置更新失败")


@router.get("/list")
def list_configs():
    return {"configs": store.get_all_configs()}


@router.post("/knowledge-base-path")
def set_knowledge_base_path(path: str = Body(..., embed=True)):
    success = md_export_service.set_knowledge_base_path(path)
    if success:
        return {"message": "知识库路径设置成功", "path": path}
    raise HTTPException(status_code=500, detail="路径设置失败")


@router.get("/knowledge-base-path")
def get_knowledge_base_path():
    return {"path": md_export_service.get_knowledge_base_path()}


@router.get("/data-directory")
def get_data_directory():
    return {"path": settings.data_directory, "storage_path": settings.storage_path}


@router.post("/data-directory")
def set_data_directory(path: str = Body(..., embed=True)):
    try:
        resolved = _validate_abs_dir_path(path)
        update_data_directory(resolved)
        return {"message": "系统数据目录更新成功", "path": resolved}
    except Exception as e:
        logger.error("[DataDirectory] 更新失败: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/storage-path")
def get_storage_path():
    return {"path": settings.storage_path, "system_data_path": settings.data_directory}


@router.post("/storage-path")
def set_storage_path(path: str = Body(..., embed=True)):
    try:
        resolved = _validate_abs_dir_path(path)
        update_storage_path(resolved)
        return {"message": "存储路径更新成功", "path": resolved}
    except Exception as e:
        logger.error("[StoragePath] 更新失败: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/auto-backup")
def get_auto_backup_config():
    enabled_str = store.get_config("auto_backup_enabled")
    interval_str = store.get_config("auto_backup_interval_hours")
    max_copies_str = store.get_config("auto_backup_max_copies")
    return {
        "enabled": enabled_str == "true" if enabled_str else settings.auto_backup_enabled,
        "interval_hours": int(interval_str) if interval_str else settings.auto_backup_interval_hours,
        "max_copies": int(max_copies_str) if max_copies_str else settings.auto_backup_max_copies,
    }


@router.post("/auto-backup")
def set_auto_backup_config(
    enabled: bool = Body(None),
    interval_hours: int = Body(None),
    max_copies: int = Body(None),
):
    if enabled is not None:
        store.set_config("auto_backup_enabled", str(enabled).lower(), "自动备份开关")
        settings.auto_backup_enabled = enabled
    if interval_hours is not None:
        store.set_config("auto_backup_interval_hours", str(interval_hours), "自动备份间隔(小时)")
        settings.auto_backup_interval_hours = interval_hours
    if max_copies is not None:
        store.set_config("auto_backup_max_copies", str(max_copies), "自动备份最大份数")
        settings.auto_backup_max_copies = max_copies
    return {"message": "自动备份配置更新成功"}


@router.post("/backup-now")
def backup_now():
    try:
        import shutil
        backup_dir = settings.backup_path
        os.makedirs(backup_dir, exist_ok=True)
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        db_path = settings.database_path
        if not os.path.exists(db_path):
            raise HTTPException(status_code=500, detail="数据库文件不存在")
        backup_file = os.path.join(backup_dir, f"memory_{timestamp}.db")
        shutil.copy2(db_path, backup_file)
        max_copies = settings.auto_backup_max_copies
        backups = sorted(
            [f for f in os.listdir(backup_dir) if f.startswith("memory_") and f.endswith(".db")],
            reverse=True
        )
        for old_backup in backups[max_copies:]:
            try:
                os.remove(os.path.join(backup_dir, old_backup))
            except OSError:
                pass
        return {"message": "备份成功", "path": backup_file}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("[BackupNow] 备份失败: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/categories")
def get_categories(layer: int = Query(..., ge=3, le=5)):
    tree = md_export_service.export_category_tree(layer)
    return {"categories": tree, "total": len(tree)}


@router.post("/categories")
def create_category(name: str = Body(...), layer: int = Body(...), level: int = Body(1), parent_id: str = Body(None)):
    category_id = str(uuid.uuid4())
    result = store.create_category(category_id, name, layer, level, parent_id)
    if result:
        return {"message": "分类创建成功", **result}
    raise HTTPException(status_code=500, detail="分类创建失败")


@router.put("/categories/{category_id}")
def update_category(category_id: str, name: str = Body(None), parent_id: str = Body(None)):
    success = store.update_category(category_id, name=name, parent_id=parent_id)
    if success:
        return {"message": "分类更新成功"}
    raise HTTPException(status_code=404, detail="分类不存在或无修改")


@router.delete("/categories/{category_id}")
def delete_category(category_id: str):
    result = memory_service.delete_managed_category(category_id)
    if result.get("error") == "NOT_FOUND":
        raise HTTPException(status_code=404, detail=result.get("message", "分类不存在"))
    if result.get("error"):
        raise HTTPException(status_code=400, detail=result.get("message", "分类删除失败"))
    return result


@router.put("/categories/{category_id}/level")
def update_category_level(category_id: str, level: int = Body(..., embed=True)):
    success = store.update_category_level(category_id, level)
    if success:
        return {"message": "分类等级更新成功"}
    raise HTTPException(status_code=404, detail="分类不存在")


@router.get("/categories/{category_id}/memories")
def get_category_memories(category_id: str, layer: int = Query(..., ge=3, le=6)):
    category = store.get_category_by_id(category_id)
    if not category:
        raise HTTPException(status_code=404, detail="分类不存在")
    memories = store.get_memories_by_category(category["name"], layer)
    return {"memories": memories, "total": len(memories)}


@router.get("/memory-stats")
def get_memory_stats():
    stats = memory_service.get_statistics()
    return stats


@router.post("/reset-stats")
def reset_stats():
    stats = memory_service.reset_statistics()
    return {"message": "统计数据已重置", "stats": stats}


@router.post("/refresh-ai-integrations")
def refresh_ai_integrations(old_port: int = Body(None), new_port: int = Body(None)):
    import threading
    from app.services.openclaw_service import openclaw_service
    from app.services.qclaw_service import qclaw_service
    from app.services.hermes_service import hermes_service

    logger.info(f"[RefreshAI] 端口变更通知: {old_port} -> {new_port}，刷新AI软件集成配置")

    def _refresh():
        services = [
            ("openclaw", openclaw_service),
            ("qclaw", qclaw_service),
            ("hermes-agent", hermes_service),
        ]
        for name, service in services:
            try:
                if service.is_diamond_memory_integrated():
                    logger.info(f"[RefreshAI] 重新配置 {name} 的钻石记忆系统集成（端口变更）")
                    service.configure_diamond_memory()
                    logger.info(f"[RefreshAI] {name} 配置刷新完成")
            except Exception as e:
                logger.warning(f"[RefreshAI] 刷新 {name} 配置失败: {e}")

    thread = threading.Thread(target=_refresh, daemon=True)
    thread.start()
    return {"message": "AI软件集成配置刷新已启动", "old_port": old_port, "new_port": new_port}
