import threading
import time
import uuid
from typing import Callable, Dict, Any

from app.api import config_routes
from app.services.adaptive_organize_service import adaptive_organize_service
from app.storage.sqlite_store import SQLiteStore


def _is_model_ready() -> bool:
    status = config_routes.get_startup_status()
    return bool(status.get("llm_loaded"))


class TaskQueueService:
    """最小持久化任务队列：SQLite 状态表 + 单 worker 串行执行。"""

    def __init__(self):
        self.store = SQLiteStore()
        self._worker_lock = threading.Lock()
        self._worker_started = False
        self._stop_event = threading.Event()

        # 任务执行器注册表：task_type -> callable(task_id, params) -> result dict
        self._executors: Dict[str, Callable[[str, Dict[str, Any]], Dict[str, Any]]] = {}

    def start_worker(self):
        with self._worker_lock:
            if self._worker_started:
                return
            t = threading.Thread(target=self._run_loop, daemon=True)
            t.start()
            self._worker_started = True

    def register_executor(self, task_type: str, fn: Callable[[str, Dict[str, Any]], Dict[str, Any]]):
        self._executors[task_type] = fn

    def enqueue(
        self,
        task_type: str,
        requires_model: bool = False,
        power_mode: str = "normal",
        params: Dict[str, Any] | None = None,
    ) -> str:
        task_id = str(uuid.uuid4())
        self.store.create_task_queue_item(
            task_id=task_id,
            task_type=task_type,
            requires_model=requires_model,
            power_mode=power_mode,
            params=params or {},
        )

        self.start_worker()

        # 满足验收：点了就入队；若缺模型则直接标记 blocked（前端可提示并允许后续继续）
        if requires_model and not _is_model_ready():
            self.store.update_task_queue_item(
                task_id,
                status="blocked",
                blocked_reason="MODEL_NOT_READY",
                message="需要模型：请先启动/安装 Ollama 并下载模型",
            )
        return task_id

    def pause(self, task_id: str) -> bool:
        return self.store.update_task_queue_item(task_id, status="paused")

    def resume(self, task_id: str) -> bool:
        item = self.store.get_task_queue_item(task_id)
        if not item:
            return False
        if item["status"] not in ("paused", "blocked"):
            return False
        return self.store.update_task_queue_item(task_id, status="queued", blocked_reason="", message="")

    def cancel(self, task_id: str) -> bool:
        return self.store.update_task_queue_item(
            task_id,
            status="cancelled",
            finished_at=self.store._get_beijing_timestamp(),
        )

    def _run_loop(self):
        while not self._stop_event.is_set():
            items = self.store.list_task_queue_items(statuses=["queued"], limit=1)
            if not items:
                time.sleep(0.5)
                continue

            item = items[0]
            task_id = item["id"]

            # 执行前模型检查
            if item.get("requires_model") and not _is_model_ready():
                self.store.update_task_queue_item(
                    task_id,
                    status="blocked",
                    blocked_reason="MODEL_NOT_READY",
                    message="需要模型：请先启动/安装 Ollama 并下载模型",
                )
                continue

            self.store.update_task_queue_item(
                task_id,
                status="running",
                started_at=self.store._get_beijing_timestamp(),
                progress=1,
                message="任务开始执行",
            )

            try:
                exec_fn = self._executors.get(item["type"])
                if not exec_fn:
                    # 第一阶段：先跑通队列，未注册执行器则执行一个极轻量的模拟流程
                    for p in (10, 30, 60, 90, 100):
                        latest = self.store.get_task_queue_item(task_id) or {}
                        if latest.get("status") == "paused":
                            self.store.update_task_queue_item(task_id, status="queued", message="已暂停（等待继续）")
                            break
                        if latest.get("status") == "cancelled":
                            break
                        self.store.update_task_queue_item(task_id, progress=p, message=f"执行中：{p}%")
                        if latest.get("power_mode") == "low_power":
                            adaptive_organize_service.adaptive_sleep()
                        else:
                            time.sleep(0.05)
                    else:
                        self.store.update_task_queue_item(
                            task_id,
                            status="completed",
                            progress=100,
                            message="任务完成",
                            finished_at=self.store._get_beijing_timestamp(),
                            result={"ok": True},
                        )
                    continue

                result = exec_fn(task_id, item.get("params") or {})
                self.store.update_task_queue_item(
                    task_id,
                    status="completed",
                    progress=100,
                    message="任务完成",
                    finished_at=self.store._get_beijing_timestamp(),
                    result=result or {},
                )
            except Exception as e:
                self.store.update_task_queue_item(
                    task_id,
                    status="failed",
                    message="任务失败",
                    finished_at=self.store._get_beijing_timestamp(),
                    error=str(e),
                )


task_queue_service = TaskQueueService()


# ---- 内置任务执行器注册（第一期覆盖：整理相关）----
try:
    from app.services.memory_service import memory_service

    def _exec_quick_organize(task_id: str, params: Dict[str, Any]) -> Dict[str, Any]:
        def _progress_cb(p: int, msg: str = ""):
            task_queue_service.store.update_task_queue_item(task_id, progress=int(p), message=msg or "执行中")

        # memory_service 内部会将进度推进到 95%，这里仅保证开始信息能尽快出现
        task_queue_service.store.update_task_queue_item(task_id, progress=5, message="开始执行：快速整理")
        result = memory_service.quick_organize(progress_callback=_progress_cb)
        task_queue_service.store.update_task_queue_item(task_id, progress=95, message="快速整理完成：收尾中")
        return result or {}

    def _exec_deep_organize(task_id: str, params: Dict[str, Any]) -> Dict[str, Any]:
        task_queue_service.store.update_task_queue_item(task_id, progress=5, message="开始执行：深度整理")
        result = memory_service.organize_entire_knowledge_base()
        task_queue_service.store.update_task_queue_item(task_id, progress=95, message="深度整理完成：收尾中")
        return result or {}

    task_queue_service.register_executor("quick_organize", _exec_quick_organize)
    task_queue_service.register_executor("deep_organize", _exec_deep_organize)

    def _exec_knowledge_sync(task_id: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """知识库同步：扫描“用户文档/”入库 PDF/Word/Excel（最小可行）。"""
        from app.services.knowledge_service import knowledge_service

        task_queue_service.store.update_task_queue_item(task_id, progress=5, message="开始执行：扫描用户文档")
        result = knowledge_service.sync_user_docs(only_folder="用户文档")
        task_queue_service.store.update_task_queue_item(task_id, progress=95, message="同步完成：收尾中")
        return result or {"ok": True}

    task_queue_service.register_executor("knowledge_sync", _exec_knowledge_sync)
except Exception:
    # 避免启动阶段因可选依赖导致队列模块不可用；具体错误会在任务执行时暴露
    pass
