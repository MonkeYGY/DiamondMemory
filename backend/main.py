import sys
import os

# 确保所有请求（包括 HuggingFace 模型下载和校验）使用国内镜像加速
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

import argparse
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import inference, memory_routes, openclaw_routes, hermes_routes, qclaw_routes, storage_routes, config_routes, knowledge_routes, health, chat_routes, ingest, mcp_routes, ollama_routes, skill_routes, system_routes, task_routes
from app.config import settings
from app.config.settings import update_data_directory, update_storage_path
from app.services.memory_service import memory_service
from app.services.knowledge_service import knowledge_service

logger = logging.getLogger(__name__)


def _is_packaged_runtime() -> bool:
    """判断是否为打包后的运行时（Nuitka / PyInstaller 等）"""
    return bool(getattr(sys, "frozen", False) or getattr(sys, "nuitka", False))


def update_startup_runtime(**kwargs):
    config_routes.startup_runtime.update(kwargs)


def parse_arguments():
    parser = argparse.ArgumentParser(description="DiamondMemory Backend")
    parser.add_argument("--data-dir", type=str, help="Data storage directory path")
    parser.add_argument("--storage-path", type=str, help="Workspace storage path")
    parser.add_argument("--port", type=int, help="Server port", default=settings.server_port)
    args, unknown = parser.parse_known_args()
    return args


@asynccontextmanager
async def lifespan(app_instance):
    # 立即记录启动信息，让 uvicorn 尽快响应健康检查
    logger.info("后端服务启动中...")
    update_startup_runtime(
        backend_ready=False,
        ollama_ready=False,
        warmup_phase="starting_services",
        llm_model_name=settings.local_llm_model,
        embedding_model_name=settings.embedding_provider,
        llm_loaded=False,
        embedding_loaded=False,
        last_error="",
    )
    
    try:
        args = parse_arguments()
        if args.data_dir:
            logger.info(f"使用自定义数据目录: {args.data_dir}")
            update_data_directory(args.data_dir)
        else:
            logger.info(f"使用默认数据目录: {settings.data_directory}")

        if args.storage_path:
            logger.info(f"使用自定义工作区路径: {args.storage_path}")
            update_storage_path(args.storage_path)
    except Exception as e:
        logger.warning(f"参数解析警告 (开发模式可忽略): {e}")
        logger.info(f"使用默认数据目录: {settings.data_directory}")

    # 将模型预加载放在后台线程，不阻塞 yield
    import threading
    import requests
    import time

    ollama_url = settings.local_llm_endpoint.rstrip("/")

    def _preload_models():
        ollama_ready = False
        # 开发模式下，前端编译较慢导致 Ollama 启动延迟，增加等待次数至 60 次 (约 120 秒)
        for i in range(60):
            try:
                resp = requests.get(f"{ollama_url}/api/tags", timeout=2)
                if resp.status_code == 200:
                    ollama_ready = True
                    update_startup_runtime(ollama_ready=True, warmup_phase="warming_up")
                    logger.info(f"[Preload] Ollama 服务已就绪")
                    break
            except Exception:
                logger.info(f"[Preload] 等待 Ollama 启动... ({i + 1}/60)")
                time.sleep(2)

        if not ollama_ready:
            update_startup_runtime(warmup_phase="degraded", last_error="Ollama 服务未响应")
            logger.warning("[Preload] Ollama 服务未响应，跳过模型预加载")
            return

        try:
            resp = requests.get(f"{ollama_url}/api/tags", timeout=5)
            if resp.status_code == 200:
                installed_models = [m.get("name", "") for m in resp.json().get("models", [])]
            else:
                installed_models = []
        except Exception:
            installed_models = []

        provider = "ollama"
        keep_alive = -1
        try:
            from app.storage.sqlite_store import SQLiteStore
            _store = SQLiteStore()
            provider = _store.get_config("llm_provider") or settings.llm_provider
            _keep_alive = _store.get_config("keep_alive")
            if _keep_alive is None or _keep_alive == "":
                _store.set_config("keep_alive", "-1", "模型常驻内存策略")
                keep_alive = -1
            elif str(_keep_alive).lower() in ("0", "false"):
                _store.set_config("keep_alive", "5m", "模型常驻内存策略")
                keep_alive = "5m"
            else:
                try:
                    keep_alive = int(_keep_alive)
                except (ValueError, TypeError):
                    keep_alive = _keep_alive
            
            saved_llm_model = _store.get_config("local_llm_model")
            if saved_llm_model:
                settings.local_llm_model = saved_llm_model
                logger.info("[Preload] 从数据库加载用户选择的LLM模型: %s", saved_llm_model)
        except Exception as e:
            logger.warning("[Preload] 读取配置失败，使用默认值: %s", e)

        if provider == "external":
            update_startup_runtime(warmup_phase="ready")
            logger.info("[Preload] 当前使用外部大模型，跳过本地模型预加载")
            return

        llm_model = settings.local_llm_model
        emb_model = settings.embedding_provider
        llm_installed = any(llm_model in m or m.startswith(llm_model.split(":")[0]) for m in installed_models)
        emb_installed = any(emb_model in m for m in installed_models)

        if not llm_installed and not emb_installed:
            update_startup_runtime(warmup_phase="no_models", last_error="未检测到已安装的大模型，请前往设置页面下载模型")
            logger.warning("[Preload] 未检测到任何已安装的大模型 (LLM=%s, Embedding=%s)", llm_model, emb_model)
            return

        import concurrent.futures

        def _preload_llm():
            if not llm_installed:
                logger.info(f"[Preload] LLM 模型 {llm_model} 未安装，跳过预加载")
                return
            try:
                logger.info(f"[Preload] 正在常驻加载主 LLM 模型: {llm_model} ...")
                requests.post(f"{ollama_url}/api/generate", json={
                    "model": llm_model,
                    "prompt": " ",
                    "stream": False,
                    "keep_alive": keep_alive,
                    "options": { "num_predict": 1, "num_ctx": 2048 }
                }, timeout=120)
                update_startup_runtime(llm_loaded=True)
                logger.info(f"[Preload] LLM 模型 {llm_model} 已成功加载到内存")
            except Exception as e:
                update_startup_runtime(last_error=f"LLM模型加载失败: {e}")
                logger.warning(f"[Preload] 加载 LLM 模型失败: {e}")

        def _preload_embedding():
            if not emb_installed:
                logger.info(f"[Preload] Embedding 模型 {emb_model} 未安装，跳过预加载")
                return
            try:
                logger.info(f"[Preload] 正在常驻加载 Embedding 模型: {emb_model} ...")
                requests.post(f"{ollama_url}/api/embeddings", json={
                    "model": emb_model,
                    "prompt": "warmup",
                    "keep_alive": keep_alive
                }, timeout=120)
                update_startup_runtime(embedding_loaded=True)
                logger.info(f"[Preload] Embedding 模型 {emb_model} 已成功加载到内存")
            except Exception as e:
                update_startup_runtime(last_error=f"Embedding模型加载失败: {e}")
                logger.warning(f"[Preload] 加载 Embedding 模型失败: {e}")

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(_preload_llm), executor.submit(_preload_embedding)]
            concurrent.futures.wait(futures)
        _llm_loaded = config_routes.startup_runtime.get("llm_loaded", False)
        _emb_loaded = config_routes.startup_runtime.get("embedding_loaded", False)
        if _llm_loaded and _emb_loaded:
            final_phase = "ready"
        elif llm_installed or emb_installed:
            final_phase = "warming_up"
        else:
            final_phase = "no_models"
        update_startup_runtime(warmup_phase=final_phase)

    threading.Thread(target=_preload_models, daemon=True).start()

    update_startup_runtime(backend_ready=True)
    logger.info("后端服务启动完成")

    try:
        from app.services.backup_service import auto_backup_service
        auto_backup_service.start()
        logger.info("自动备份服务已启动")
    except Exception as e:
        logger.warning(f"自动备份服务启动失败: {e}")

    yield

    update_startup_runtime(backend_ready=False)
    logger.info("后端服务关闭")


app = FastAPI(title="DiamondMemory API", version="1.0.0", lifespan=lifespan)

from fastapi import Request
from fastapi.responses import JSONResponse

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"未捕获的异常: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "服务器内部错误"}
    )

from starlette.middleware.base import BaseHTTPMiddleware


class LocalOnlyMiddleware(BaseHTTPMiddleware):
    """仅允许本机环回访问（用于生产环境，降低放宽 CORS 带来的风险）"""

    def __init__(self, app, enabled: bool = False):
        super().__init__(app)
        self.enabled = enabled

    async def dispatch(self, request: Request, call_next):
        if not self.enabled:
            return await call_next(request)
        client_host = request.client.host if request.client else ""
        if client_host not in ("127.0.0.1", "::1"):
            return JSONResponse(status_code=403, content={"detail": "forbidden"})
        return await call_next(request)


is_packaged = _is_packaged_runtime()
cors_allow_origins = settings.cors_allow_origins_prod if is_packaged else settings.cors_allow_origins_dev
cors_allow_origin_regex = settings.cors_allow_origin_regex_prod if is_packaged else None

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_allow_origins,
    allow_origin_regex=cors_allow_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 生产环境仅允许本机访问（需要放在 CORS 之后添加，确保其处于更外层）
app.add_middleware(LocalOnlyMiddleware, enabled=is_packaged)

app.include_router(health.router, prefix="/health", tags=["health"])
app.include_router(inference.router, prefix="/api/inference", tags=["inference"])
app.include_router(memory_routes.router, prefix="/api", tags=["memory"])
app.include_router(openclaw_routes.router, prefix="/api", tags=["openclaw"])
app.include_router(hermes_routes.router, prefix="/api", tags=["hermes"])
app.include_router(qclaw_routes.router, prefix="/api", tags=["qclaw"])
app.include_router(storage_routes.router, prefix="/api/storage", tags=["storage"])
app.include_router(config_routes.router, prefix="/api", tags=["config"])
app.include_router(system_routes.router, prefix="/api", tags=["system"])
app.include_router(task_routes.router, prefix="/api", tags=["tasks"])
app.include_router(knowledge_routes.router, prefix="/api", tags=["knowledge"])
app.include_router(chat_routes.router, prefix="/api", tags=["chat"])
# 采集/摄取接口：历史上曾挂在 /api/storage 下；为避免前后端/旧客户端不一致，这里同时提供 /api/ingest 与 /api/storage 两个前缀
app.include_router(ingest.router, prefix="/api/ingest", tags=["ingest"])
app.include_router(ingest.router, prefix="/api/storage", tags=["ingest-compat"])
app.include_router(mcp_routes.router, prefix="/api/mcp", tags=["mcp"])
app.include_router(ollama_routes.router, prefix="/api", tags=["ollama"])
app.include_router(skill_routes.router, prefix="/api", tags=["skill"])

from fastapi import APIRouter

compat_router = APIRouter(prefix="/api", tags=["compatibility"])

@compat_router.get("/memories")
def get_all_memories_compat(limit: int = 1000):
    memories = memory_service.list_memories(limit)
    return memories

@compat_router.get("/memories/stats")
def get_memory_stats_compat():
    from datetime import datetime
    all_memories = memory_service.list_memories(10000)
    today = datetime.now().date()
    today_count = 0
    l0_count = l1_count = l2_count = l3_count = l4_count = l5_count = l6_count = 0
    categories = set()
    for m in all_memories:
        created = m.get("created_at", "")
        if created:
            try:
                mem_date = datetime.fromisoformat(created).date()
                if mem_date == today:
                    today_count += 1
            except Exception:
                pass
        layer = m.get("layer", 0)
        if layer == 0: l0_count += 1
        elif layer == 1: l1_count += 1
        elif layer == 2: l2_count += 1
        elif layer == 3: l3_count += 1
        elif layer == 4: l4_count += 1
        elif layer == 5: l5_count += 1
        elif layer == 6: l6_count += 1
        cat = m.get("category")
        if cat:
            categories.add(cat)
    return {
        "totalMemories": len(all_memories),
        "todayCount": today_count,
        "categoryCount": len(categories),
        "systemStatus": "ok",
        "l0Count": l0_count,
        "l1Count": l1_count,
        "l2Count": l2_count,
        "l3Count": l3_count,
        "l4Count": l4_count,
        "l5Count": l5_count,
        "l6Count": l6_count
    }

@compat_router.get("/knowledge")
def get_all_knowledge_compat():
    try:
        all_files = knowledge_service.scan_file_tree(None, None)
        result = []
        file_list = all_files if isinstance(all_files, list) else all_files.get("tree", [])
        for file_info in file_list:
            try:
                content = knowledge_service.read_file(file_info.get("path", ""))
                if content:
                    result.append({
                        "id": content.get("path", ""),
                        "title": content.get("title", file_info.get("name", "无标题")),
                        "content": content.get("content", ""),
                        "tags": content.get("tags", []),
                        "category": content.get("category", ""),
                        "created_at": content.get("created_at", ""),
                        "type": content.get("type", "knowledge")
                    })
            except Exception:
                continue
        return result
    except Exception:
        return []

app.include_router(compat_router)

if __name__ == "__main__":
    import uvicorn
    args = parse_arguments()
    port = args.port if args.port else settings.server_port

    if getattr(sys, 'frozen', False) or getattr(sys, 'nuitka', False):
        uvicorn.run(app, host=settings.server_host, port=port, timeout_keep_alive=600)
    else:
        uvicorn.run("main:app", host=settings.server_host, port=port, timeout_keep_alive=600, reload=False)
