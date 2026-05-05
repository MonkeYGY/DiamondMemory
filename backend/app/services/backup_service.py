"""数据库自动备份服务"""
import os
import shutil
import logging
import threading
import time
from datetime import datetime
from app.config import settings
from app.storage import SQLiteStore

logger = logging.getLogger(__name__)


class AutoBackupService:
    def __init__(self):
        self._timer = None
        self._running = False

    def start(self):
        if self._running:
            return
        self._running = True
        self._schedule_next()

    def stop(self):
        self._running = False
        if self._timer:
            self._timer.cancel()
            self._timer = None

    def _schedule_next(self):
        if not self._running:
            return
        try:
            store = SQLiteStore()
            enabled_str = store.get_config("auto_backup_enabled")
            interval_str = store.get_config("auto_backup_interval_hours")
            enabled = enabled_str == "true" if enabled_str else settings.auto_backup_enabled
            interval_hours = int(interval_str) if interval_str else settings.auto_backup_interval_hours
        except Exception:
            enabled = settings.auto_backup_enabled
            interval_hours = settings.auto_backup_interval_hours

        if not enabled:
            self._timer = threading.Timer(60, self._schedule_next)
            self._timer.daemon = True
            self._timer.start()
            return

        interval_seconds = interval_hours * 3600
        self._timer = threading.Timer(interval_seconds, self._do_backup)
        self._timer.daemon = True
        self._timer.start()

    def _do_backup(self):
        if not self._running:
            return
        try:
            backup_dir = settings.backup_path
            os.makedirs(backup_dir, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            db_path = settings.database_path
            if not os.path.exists(db_path):
                logger.warning("[AutoBackup] 数据库文件不存在，跳过备份")
            else:
                backup_file = os.path.join(backup_dir, f"memory_auto_{timestamp}.db")
                shutil.copy2(db_path, backup_file)
                logger.info(f"[AutoBackup] 自动备份完成: {backup_file}")
                try:
                    store = SQLiteStore()
                    max_copies_str = store.get_config("auto_backup_max_copies")
                    max_copies = int(max_copies_str) if max_copies_str else settings.auto_backup_max_copies
                except Exception:
                    max_copies = settings.auto_backup_max_copies
                backups = sorted(
                    [f for f in os.listdir(backup_dir) if f.startswith("memory_auto_") and f.endswith(".db")],
                    reverse=True
                )
                for old_backup in backups[max_copies:]:
                    try:
                        os.remove(os.path.join(backup_dir, old_backup))
                    except OSError:
                        pass
        except Exception as e:
            logger.error(f"[AutoBackup] 自动备份失败: {e}")
        finally:
            self._schedule_next()


auto_backup_service = AutoBackupService()
