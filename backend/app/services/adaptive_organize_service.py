"""自适应低功耗整理服务

基于系统负载动态调度整理任务，支持：
1. CPU/内存负载检测
2. 动态暂停时间调整
3. 批次大小自适应
4. 整理任务优先级调度
"""
import time
import logging
from typing import Dict, Any, Optional
from app.config import settings

logger = logging.getLogger(__name__)


class AdaptiveOrganizeService:
    def __init__(self):
        self._psutil_available = False
        self._last_check_time: float = 0
        self._cached_cpu: float = 0.0
        self._cached_memory: float = 0.0
        self._check_interval = getattr(settings, "adaptive_check_interval_seconds", 60)
        self._init_psutil()

    def _init_psutil(self):
        try:
            import psutil
            self._psutil_available = True
            logger.info("[AdaptiveOrganize] psutil 可用，启用系统负载感知")
        except ImportError:
            logger.warning("[AdaptiveOrganize] psutil 不可用，使用静态配置")

    def get_system_load(self) -> Dict[str, float]:
        if not self._psutil_available:
            return {"cpu_percent": 50.0, "memory_percent": 50.0}

        now = time.time()
        if now - self._last_check_time < self._check_interval:
            return {"cpu_percent": self._cached_cpu, "memory_percent": self._cached_memory}

        try:
            import psutil
            self._cached_cpu = psutil.cpu_percent(interval=0.5)
            self._cached_memory = psutil.virtual_memory().percent
            self._last_check_time = now
            return {"cpu_percent": self._cached_cpu, "memory_percent": self._cached_memory}
        except Exception:
            return {"cpu_percent": 50.0, "memory_percent": 50.0}

    def get_adaptive_pause_ms(self) -> int:
        if not getattr(settings, "adaptive_organize_enabled", True):
            return getattr(settings, "deep_organize_stage_pause_ms", 1200)

        load = self.get_system_load()
        cpu = load["cpu_percent"] / 100.0
        memory = load["memory_percent"] / 100.0

        cpu_threshold = getattr(settings, "adaptive_cpu_threshold", 0.8)
        memory_threshold = getattr(settings, "adaptive_memory_threshold", 0.85)
        min_pause = getattr(settings, "adaptive_min_pause_ms", 500)
        max_pause = getattr(settings, "adaptive_max_pause_ms", 3000)

        load_factor = max(cpu / cpu_threshold, memory / memory_threshold)

        if load_factor <= 0.5:
            return min_pause
        elif load_factor <= 1.0:
            ratio = (load_factor - 0.5) / 0.5
            return int(min_pause + ratio * (max_pause - min_pause))
        else:
            return max_pause

    def get_adaptive_batch_size(self, base_batch: int = 1) -> int:
        if not getattr(settings, "adaptive_organize_enabled", True):
            return base_batch

        load = self.get_system_load()
        cpu = load["cpu_percent"] / 100.0

        if cpu <= 0.3:
            return base_batch * 3
        elif cpu <= 0.5:
            return base_batch * 2
        elif cpu <= 0.7:
            return base_batch
        else:
            return max(1, base_batch // 2)

    def should_pause_heavy_task(self) -> bool:
        if not getattr(settings, "adaptive_organize_enabled", True):
            return False

        load = self.get_system_load()
        cpu_threshold = getattr(settings, "adaptive_cpu_threshold", 0.8)
        memory_threshold = getattr(settings, "adaptive_memory_threshold", 0.85)

        return (load["cpu_percent"] / 100.0 > cpu_threshold or
                load["memory_percent"] / 100.0 > memory_threshold)

    def adaptive_sleep(self):
        pause_ms = self.get_adaptive_pause_ms()
        if pause_ms > 0:
            time.sleep(pause_ms / 1000.0)

    def get_stats(self) -> Dict[str, Any]:
        load = self.get_system_load()
        return {
            "cpu_percent": load["cpu_percent"],
            "memory_percent": load["memory_percent"],
            "adaptive_pause_ms": self.get_adaptive_pause_ms(),
            "adaptive_batch_size": self.get_adaptive_batch_size(),
            "should_pause_heavy": self.should_pause_heavy_task(),
            "psutil_available": self._psutil_available,
        }


adaptive_organize_service = AdaptiveOrganizeService()
