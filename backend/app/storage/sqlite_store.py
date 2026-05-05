"""SQLite存储模块 - 带连接池和WAL模式"""
import os
import sqlite3
import json
import threading
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any
from app.config import settings

logger = logging.getLogger(__name__)


class SQLiteStore:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self.db_path = settings.database_path
        if not self.db_path:
            self.db_path = os.path.join(settings.data_directory, "memory.db")
        self._local = threading.local()
        self._init_database()
        self._migrate_database()

    def _get_conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, 'conn') or self._local.conn is None:
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA busy_timeout=5000")
            conn.execute("PRAGMA cache_size=-64000")
            conn.row_factory = None
            self._local.conn = conn
        return self._local.conn

    def close(self):
        if hasattr(self._local, 'conn') and self._local.conn is not None:
            try:
                self._local.conn.close()
            except Exception:
                pass
            self._local.conn = None

    def _migrate_database(self):
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute("PRAGMA table_info(memories)")
            columns = [row[1] for row in cursor.fetchall()]

            if 'processed_status' not in columns:
                cursor.execute("ALTER TABLE memories ADD COLUMN processed_status TEXT DEFAULT 'pending'")
                conn.commit()
                logger.info("数据库迁移: 添加 processed_status 字段")

            if 'parent_id' not in columns:
                cursor.execute("ALTER TABLE memories ADD COLUMN parent_id TEXT")
                conn.commit()
                logger.info("数据库迁移: 添加 parent_id 字段")

            if 'file_path' not in columns:
                cursor.execute("ALTER TABLE memories ADD COLUMN file_path TEXT")
                conn.commit()
                logger.info("数据库迁移: 添加 file_path 字段")

            if 'valid_at' not in columns:
                cursor.execute("ALTER TABLE memories ADD COLUMN valid_at TEXT")
                conn.commit()
                logger.info("数据库迁移: 添加 valid_at 字段 (时序图谱)")

            if 'invalid_at' not in columns:
                cursor.execute("ALTER TABLE memories ADD COLUMN invalid_at TEXT")
                conn.commit()
                logger.info("数据库迁移: 添加 invalid_at 字段 (时序图谱)")

            if 'superseded_by' not in columns:
                cursor.execute("ALTER TABLE memories ADD COLUMN superseded_by TEXT")
                conn.commit()
                logger.info("数据库迁移: 添加 superseded_by 字段 (时序图谱)")

            if 'memory_type' not in columns:
                cursor.execute("ALTER TABLE memories ADD COLUMN memory_type TEXT DEFAULT 'episodic'")
                conn.commit()
                logger.info("数据库迁移: 添加 memory_type 字段 (统一记忆类型)")

            if 'short_name' not in columns:
                cursor.execute("ALTER TABLE memories ADD COLUMN short_name TEXT")
                conn.commit()
                logger.info("数据库迁移: 添加 short_name 字段 (记忆短名)")

            # 常用查询索引（active 默认检索 + 版本链/审计链路）
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_memories_layer_status_created ON memories(layer, status, created_at)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_memories_status_updated ON memories(status, updated_at)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_memories_parent_id ON memories(parent_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_memories_superseded_by ON memories(superseded_by)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_memory_id_created ON memory_audit_log(memory_id, created_at)")
            conn.commit()

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS categories (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    layer INTEGER NOT NULL,
                    level INTEGER DEFAULT 1,
                    parent_id TEXT,
                    memory_count INTEGER DEFAULT 0,
                    metadata TEXT,
                    status TEXT DEFAULT 'active',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (parent_id) REFERENCES categories(id) ON DELETE SET NULL
                )
            """)
            conn.commit()

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS config (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    description TEXT,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()

            cursor.execute("""
                INSERT OR IGNORE INTO config (key, value, description) VALUES (?, ?, ?)
            """, ('knowledge_base_path', settings.storage_path, '知识库存储路径'))
            cursor.execute("""
                INSERT OR IGNORE INTO config (key, value, description) VALUES (?, ?, ?)
            """, ('llm_model', 'qwen3.5:4b', '默认大模型'))
            cursor.execute("""
                INSERT OR IGNORE INTO config (key, value, description) VALUES (?, ?, ?)
            """, ('md_export_format', 'default', 'MD导出格式模板'))

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS file_sync (
                    file_path TEXT PRIMARY KEY,
                    last_modified REAL,
                    file_hash TEXT,
                    last_sync_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    status TEXT DEFAULT 'synced'
                )
            """)
            conn.commit()

            # Local-first：耗时任务队列（最小可行，持久化单 worker）
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS task_queue (
                    id TEXT PRIMARY KEY,
                    type TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'queued',
                    progress INTEGER NOT NULL DEFAULT 0,
                    message TEXT DEFAULT '',
                    requires_model INTEGER NOT NULL DEFAULT 0,
                    blocked_reason TEXT DEFAULT '',
                    power_mode TEXT NOT NULL DEFAULT 'normal',
                    params_json TEXT NOT NULL DEFAULT '{}',
                    result_json TEXT NOT NULL DEFAULT '{}',
                    error TEXT DEFAULT '',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    started_at TEXT,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    finished_at TEXT
                )
                """
            )
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_task_queue_status_created ON task_queue(status, created_at)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_task_queue_type_created ON task_queue(type, created_at)")
            conn.commit()

            # L6 技能产品化：升级任务队列表（最小可行）
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS skill_upgrade_tasks (
                    id TEXT PRIMARY KEY,
                    skill_id TEXT NOT NULL,
                    from_memory_id TEXT NOT NULL,
                    from_version INTEGER NOT NULL,
                    to_version INTEGER NOT NULL,
                    reason TEXT,
                    details TEXT,
                    status TEXT DEFAULT 'pending',
                    new_memory_id TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_skill_upgrade_tasks_skill_status_created ON skill_upgrade_tasks(skill_id, status, created_at)"
            )
            conn.commit()
            logger.info("数据库迁移完成")
        except Exception as e:
            logger.error(f"数据库迁移失败: {e}")

    def _init_database(self):
        db_dir = os.path.dirname(self.db_path) or "."
        os.makedirs(db_dir, exist_ok=True)
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                id TEXT PRIMARY KEY,
                content TEXT NOT NULL,
                category TEXT,
                layer INTEGER DEFAULT 3,
                level INTEGER DEFAULT 1,
                tags TEXT,
                source TEXT,
                confidence REAL DEFAULT 1.0,
                expires_at TEXT,
                is_pinned BOOLEAN DEFAULT 0,
                metadata TEXT,
                status TEXT DEFAULT 'active',
                processed_status TEXT DEFAULT 'pending',
                parent_id TEXT,
                file_path TEXT,
                valid_at TEXT,
                invalid_at TEXT,
                superseded_by TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                access_count INTEGER DEFAULT 0
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS categories (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                layer INTEGER NOT NULL,
                level INTEGER DEFAULT 1,
                parent_id TEXT,
                memory_count INTEGER DEFAULT 0,
                metadata TEXT,
                status TEXT DEFAULT 'active',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (parent_id) REFERENCES categories(id) ON DELETE SET NULL
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS config (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                description TEXT,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS memory_embeddings (
                memory_id TEXT PRIMARY KEY,
                embedding TEXT NOT NULL,
                FOREIGN KEY (memory_id) REFERENCES memories(id) ON DELETE CASCADE
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS memory_entities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                memory_id TEXT,
                entity_text TEXT NOT NULL,
                entity_type TEXT,
                FOREIGN KEY (memory_id) REFERENCES memories(id) ON DELETE CASCADE
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS memory_audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                memory_id TEXT,
                action TEXT NOT NULL,
                source_ai TEXT,
                action_type TEXT,
                old_content TEXT,
                new_content TEXT,
                category TEXT,
                tags TEXT,
                session_id TEXT,
                details TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # MCP 调用审计（不记录敏感全文，只存参数摘要）
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS mcp_audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT,
                tool_name TEXT NOT NULL,
                args_summary TEXT,
                result_count INTEGER DEFAULT 0,
                status TEXT DEFAULT 'ok',
                error TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS memory_backups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                backup_time TEXT NOT NULL,
                backup_path TEXT NOT NULL,
                size INTEGER,
                status TEXT DEFAULT 'created'
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS query_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                query_text TEXT,
                results_count INTEGER,
                search_time_ms REAL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(
                content,
                category,
                tags,
                memory_id UNINDEXED
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS file_sync (
                file_path TEXT PRIMARY KEY,
                last_modified REAL,
                file_hash TEXT,
                last_sync_at TEXT DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'synced'
            )
        """)

        # L6 技能产品化：升级任务队列表（最小可行）
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS skill_upgrade_tasks (
                id TEXT PRIMARY KEY,
                skill_id TEXT NOT NULL,
                from_memory_id TEXT NOT NULL,
                from_version INTEGER NOT NULL,
                to_version INTEGER NOT NULL,
                reason TEXT,
                details TEXT,
                status TEXT DEFAULT 'pending',
                new_memory_id TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_skill_upgrade_tasks_skill_status_created ON skill_upgrade_tasks(skill_id, status, created_at)"
        )

        # Local-first：耗时任务队列（最小可行，持久化单 worker）
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS task_queue (
                id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'queued',
                progress INTEGER NOT NULL DEFAULT 0,
                message TEXT DEFAULT '',
                requires_model INTEGER NOT NULL DEFAULT 0,
                blocked_reason TEXT DEFAULT '',
                power_mode TEXT NOT NULL DEFAULT 'normal',
                params_json TEXT NOT NULL DEFAULT '{}',
                result_json TEXT NOT NULL DEFAULT '{}',
                error TEXT DEFAULT '',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                started_at TEXT,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                finished_at TEXT
            )
            """
        )
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_task_queue_status_created ON task_queue(status, created_at)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_task_queue_type_created ON task_queue(type, created_at)")

        conn.commit()

    def update_file_sync_info(self, file_path: str, last_modified: float, file_hash: str, status: str = 'synced'):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO file_sync (file_path, last_modified, file_hash, last_sync_at, status)
            VALUES (?, ?, ?, ?, ?)
        """, (file_path, last_modified, file_hash, self._get_beijing_timestamp(), status))
        conn.commit()

    def delete_file_sync_info(self, file_path: str) -> bool:
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM file_sync WHERE file_path = ?", (file_path,))
        conn.commit()
        return cursor.rowcount > 0

    def get_file_sync_info(self, file_path: str) -> Optional[Dict[str, Any]]:
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM file_sync WHERE file_path = ?", (file_path,))
        row = cursor.fetchone()
        if row:
            return {"file_path": row[0], "last_modified": row[1], "file_hash": row[2], "last_sync_at": row[3], "status": row[4]}
        return None

    def get_max_file_sync_last_modified(self, prefix: Optional[str] = None) -> Optional[float]:
        """获取 file_sync 表中指定前缀的最大 last_modified，用于增量扫描判定。

        Args:
            prefix: 相对路径前缀（如 "技能/"）。为空则统计全表。
        """
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            if not prefix:
                cursor.execute("SELECT MAX(last_modified) FROM file_sync")
                row = cursor.fetchone()
                return row[0] if row and row[0] is not None else None

            # 兼容 Windows/Unix 路径分隔符
            p1 = prefix.replace("\\", "/")
            p2 = prefix.replace("/", "\\")
            cursor.execute(
                "SELECT MAX(last_modified) FROM file_sync WHERE file_path LIKE ? OR file_path LIKE ?",
                (p1 + "%", p2 + "%"),
            )
            row = cursor.fetchone()
            return row[0] if row and row[0] is not None else None
        except Exception:
            return None

    # ---- Local-first：耗时任务队列（持久化单 worker）----

    def create_task_queue_item(
        self,
        task_id: str,
        task_type: str,
        requires_model: bool = False,
        power_mode: str = "normal",
        params: Optional[Dict[str, Any]] = None,
    ) -> bool:
        conn = self._get_conn()
        cursor = conn.cursor()
        now = self._get_beijing_timestamp()
        cursor.execute(
            """
            INSERT OR REPLACE INTO task_queue (
                id, type, status, progress, message,
                requires_model, blocked_reason, power_mode,
                params_json, result_json, error,
                created_at, updated_at
            ) VALUES (?, ?, 'queued', 0, '', ?, '', ?, ?, '{}', '', ?, ?)
            """,
            (
                task_id,
                task_type,
                1 if requires_model else 0,
                power_mode,
                json.dumps(params or {}, ensure_ascii=False),
                now,
                now,
            ),
        )
        conn.commit()
        return cursor.rowcount > 0

    def get_task_queue_item(self, task_id: str) -> Optional[Dict[str, Any]]:
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, type, status, progress, message, requires_model, blocked_reason,
                   power_mode, params_json, result_json, error,
                   created_at, started_at, updated_at, finished_at
            FROM task_queue
            WHERE id = ?
            """,
            (task_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None
        keys = [
            "id",
            "type",
            "status",
            "progress",
            "message",
            "requires_model",
            "blocked_reason",
            "power_mode",
            "params",
            "result",
            "error",
            "created_at",
            "started_at",
            "updated_at",
            "finished_at",
        ]
        item = dict(zip(keys, row))
        item["requires_model"] = bool(item.get("requires_model"))
        for k in ("params", "result"):
            try:
                item[k] = json.loads(item.get(k) or "{}")
            except Exception:
                item[k] = {}
        return item

    def list_task_queue_items(self, statuses: Optional[List[str]] = None, limit: int = 50) -> List[Dict[str, Any]]:
        conn = self._get_conn()
        cursor = conn.cursor()
        where_sql = ""
        params: List[Any] = []
        if statuses:
            placeholders = ",".join(["?"] * len(statuses))
            where_sql = f"WHERE status IN ({placeholders})"
            params.extend(statuses)
        sql = f"""
            SELECT id
            FROM task_queue
            {where_sql}
            ORDER BY created_at DESC
            LIMIT ?
            """
        try:
            cursor.execute(sql, (*params, int(limit)))
        except sqlite3.OperationalError as e:
            # 兼容测试/运行时切换 data_directory 后的极端情况：
            # SQLiteStore 单例可能指向一个尚未完成初始化的新 DB，导致 task_queue 表缺失。
            # 这里做一次自愈（重建表）并重试，避免后台 worker 线程抛出未捕获异常。
            if "no such table: task_queue" in str(e):
                try:
                    self._init_database()
                    self._migrate_database()
                    cursor = conn.cursor()
                    cursor.execute(sql, (*params, int(limit)))
                except Exception:
                    return []
            else:
                raise
        rows = cursor.fetchall() or []
        results: List[Dict[str, Any]] = []
        for row in rows:
            if not row:
                continue
            item = self.get_task_queue_item(row[0])
            if item:
                results.append(item)
        return results

    def update_task_queue_item(
        self,
        task_id: str,
        status: Optional[str] = None,
        progress: Optional[int] = None,
        message: Optional[str] = None,
        blocked_reason: Optional[str] = None,
        result: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
        started_at: Optional[str] = None,
        finished_at: Optional[str] = None,
    ) -> bool:
        conn = self._get_conn()
        cursor = conn.cursor()

        updates = []
        params: List[Any] = []
        if status is not None:
            updates.append("status = ?")
            params.append(status)
        if progress is not None:
            updates.append("progress = ?")
            params.append(int(progress))
        if message is not None:
            updates.append("message = ?")
            params.append(message)
        if blocked_reason is not None:
            updates.append("blocked_reason = ?")
            params.append(blocked_reason)
        if result is not None:
            updates.append("result_json = ?")
            params.append(json.dumps(result, ensure_ascii=False))
        if error is not None:
            updates.append("error = ?")
            params.append(error)
        if started_at is not None:
            updates.append("started_at = ?")
            params.append(started_at)
        if finished_at is not None:
            updates.append("finished_at = ?")
            params.append(finished_at)
        updates.append("updated_at = ?")
        params.append(self._get_beijing_timestamp())
        params.append(task_id)

        cursor.execute(f"UPDATE task_queue SET {', '.join(updates)} WHERE id = ?", tuple(params))
        conn.commit()
        return cursor.rowcount > 0

    # ---- L6 技能产品化：升级任务队列 ----

    def create_skill_upgrade_task(
        self,
        task_id: str,
        skill_id: str,
        from_memory_id: str,
        from_version: int,
        to_version: int,
        reason: str = "",
        details: Optional[Dict[str, Any]] = None,
    ) -> bool:
        conn = self._get_conn()
        cursor = conn.cursor()
        now = self._get_beijing_timestamp()
        cursor.execute(
            """
            INSERT OR REPLACE INTO skill_upgrade_tasks (
                id, skill_id, from_memory_id, from_version, to_version,
                reason, details, status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)
            """,
            (
                task_id,
                skill_id,
                from_memory_id,
                int(from_version),
                int(to_version),
                reason,
                json.dumps(details or {}, ensure_ascii=False),
                now,
                now,
            ),
        )
        conn.commit()
        return cursor.rowcount > 0

    def get_pending_skill_upgrade_task(self, skill_id: str, from_version: int) -> Optional[Dict[str, Any]]:
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, skill_id, from_memory_id, from_version, to_version, reason, details,
                   status, new_memory_id, created_at, updated_at
            FROM skill_upgrade_tasks
            WHERE skill_id = ? AND from_version = ? AND status = 'pending'
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (skill_id, int(from_version)),
        )
        row = cursor.fetchone()
        if not row:
            return None
        keys = [
            "id",
            "skill_id",
            "from_memory_id",
            "from_version",
            "to_version",
            "reason",
            "details",
            "status",
            "new_memory_id",
            "created_at",
            "updated_at",
        ]
        item = dict(zip(keys, row))
        if item.get("details"):
            try:
                item["details"] = json.loads(item["details"])
            except Exception:
                item["details"] = {}
        return item

    def list_skill_upgrade_tasks(
        self,
        skill_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        conn = self._get_conn()
        cursor = conn.cursor()
        where = []
        params: List[Any] = []
        if skill_id:
            where.append("skill_id = ?")
            params.append(skill_id)
        if status:
            where.append("status = ?")
            params.append(status)
        where_sql = ("WHERE " + " AND ".join(where)) if where else ""
        cursor.execute(
            f"""
            SELECT id, skill_id, from_memory_id, from_version, to_version, reason, details,
                   status, new_memory_id, created_at, updated_at
            FROM skill_upgrade_tasks
            {where_sql}
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (*params, int(limit)),
        )
        rows = cursor.fetchall() or []
        keys = [
            "id",
            "skill_id",
            "from_memory_id",
            "from_version",
            "to_version",
            "reason",
            "details",
            "status",
            "new_memory_id",
            "created_at",
            "updated_at",
        ]
        results: List[Dict[str, Any]] = []
        for row in rows:
            item = dict(zip(keys, row))
            if item.get("details"):
                try:
                    item["details"] = json.loads(item["details"])
                except Exception:
                    item["details"] = {}
            results.append(item)
        return results

    def complete_skill_upgrade_task(self, task_id: str, new_memory_id: Optional[str] = None) -> bool:
        conn = self._get_conn()
        cursor = conn.cursor()
        now = self._get_beijing_timestamp()
        cursor.execute(
            """
            UPDATE skill_upgrade_tasks
            SET status = 'completed', new_memory_id = COALESCE(?, new_memory_id), updated_at = ?
            WHERE id = ?
            """,
            (new_memory_id, now, task_id),
        )
        conn.commit()
        return cursor.rowcount > 0

    def create(self, memory_id: str, content: str, category: str = None, layer: int = 3,
               level: int = 1, tags: List[str] = None, source: str = None, confidence: float = 1.0,
               expires_at: Optional[str] = None, is_pinned: bool = False,
               metadata: Dict[str, Any] = None, status: str = 'active',
               processed_status: str = 'pending', parent_id: str = None,
               valid_at: str = None, invalid_at: str = None, superseded_by: str = None,
               memory_type: str = None, short_name: str = None) -> Dict[str, Any]:
        conn = self._get_conn()
        cursor = conn.cursor()
        tags_str = json.dumps(tags) if tags else '[]'
        metadata_str = json.dumps(metadata) if metadata else '{}'
        
        beijing_now = self._get_beijing_timestamp()
        if not valid_at:
            valid_at = beijing_now

        if memory_type is None:
            memory_type = getattr(settings, 'memory_type_default', 'episodic')

        cursor.execute("""
            INSERT INTO memories (
                id, content, category, layer, level, tags, source, confidence,
                expires_at, is_pinned, metadata, status, processed_status, parent_id,
                valid_at, invalid_at, superseded_by, memory_type, short_name,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            memory_id, content, category, layer, level, tags_str, source, confidence,
            expires_at, is_pinned, metadata_str, status, processed_status, parent_id,
            valid_at, invalid_at, superseded_by, memory_type, short_name,
            beijing_now, beijing_now
        ))

        cursor.execute("""
            INSERT INTO memory_fts (memory_id, content, category, tags)
            VALUES (?, ?, ?, ?)
        """, (memory_id, content, category, tags_str))

        conn.commit()
        return self.get_by_id(memory_id)

    def get_by_id(self, memory_id: str) -> Optional[Dict[str, Any]]:
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, content, category, layer, level, tags, source, confidence,
                   expires_at, is_pinned, metadata, status, processed_status,
                   parent_id, file_path, valid_at, invalid_at, superseded_by,
                   created_at, updated_at, access_count, short_name, memory_type
            FROM memories WHERE id = ?
        """, (memory_id,))
        row = cursor.fetchone()
        if row:
            return self._row_to_dict(row)
        return None

    def get_config(self, key: str) -> Optional[str]:
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM config WHERE key = ?", (key,))
        row = cursor.fetchone()
        return row[0] if row else None

    def set_config(self, key: str, value: str, description: str = None) -> bool:
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO config (key, value, description, updated_at)
            VALUES (?, ?, ?, ?)
        """, (key, value, description, self._get_beijing_timestamp()))
        conn.commit()
        return True

    def get_all_configs(self) -> Dict[str, Any]:
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT key, value FROM config")
        rows = cursor.fetchall()
        return {row[0]: row[1] for row in rows}

    def create_category(self, category_id: str, name: str, layer: int, level: int = 1,
                        parent_id: str = None, metadata: Dict[str, Any] = None) -> Dict[str, Any]:
        conn = self._get_conn()
        cursor = conn.cursor()
        metadata_str = json.dumps(metadata) if metadata else '{}'
        beijing_now = self._get_beijing_timestamp()
        cursor.execute("""
            INSERT INTO categories (id, name, layer, level, parent_id, metadata, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (category_id, name, layer, level, parent_id, metadata_str, beijing_now, beijing_now))
        conn.commit()
        return self.get_category_by_id(category_id)

    def get_category_by_id(self, category_id: str) -> Optional[Dict[str, Any]]:
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, name, layer, level, parent_id, memory_count, metadata,
                   status, created_at, updated_at
            FROM categories WHERE id = ?
        """, (category_id,))
        row = cursor.fetchone()
        if row:
            return self._category_row_to_dict(row)
        return None

    def get_categories_by_layer(self, layer: int) -> List[Dict[str, Any]]:
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, name, layer, level, parent_id, memory_count, metadata,
                   status, created_at, updated_at
            FROM categories WHERE layer = ? AND status = 'active' ORDER BY level DESC, created_at DESC
        """, (layer,))
        rows = cursor.fetchall()
        return [self._category_row_to_dict(row) for row in rows]

    def get_categories_by_parent(self, parent_id: str) -> List[Dict[str, Any]]:
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, name, layer, level, parent_id, memory_count, metadata,
                   status, created_at, updated_at
            FROM categories WHERE parent_id = ? AND status = 'active' ORDER BY level DESC, created_at DESC
        """, (parent_id,))
        rows = cursor.fetchall()
        return [self._category_row_to_dict(row) for row in rows]

    def update_category(self, category_id: str, name: str = None, parent_id: str = None) -> bool:
        conn = self._get_conn()
        cursor = conn.cursor()
        
        updates = []
        params = []
        if name is not None:
            updates.append("name = ?")
            params.append(name)
        if parent_id is not None:
            updates.append("parent_id = ?")
            params.append(parent_id)
            
        if not updates:
            return False
            
        updates.append("updated_at = ?")
        params.append(self._get_beijing_timestamp())
        params.append(category_id)
        
        query = f"UPDATE categories SET {', '.join(updates)} WHERE id = ?"
        cursor.execute(query, tuple(params))
        conn.commit()
        return cursor.rowcount > 0

    def delete_category(self, category_id: str) -> bool:
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM categories WHERE id = ?", (category_id,))
        conn.commit()
        return cursor.rowcount > 0

    def update_category_level(self, category_id: str, level: int) -> bool:
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("UPDATE categories SET level = ?, updated_at = ? WHERE id = ?",
                       (level, self._get_beijing_timestamp(), category_id))
        conn.commit()
        return cursor.rowcount > 0

    def increment_category_memory_count(self, category_id: str) -> bool:
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("UPDATE categories SET memory_count = memory_count + 1 WHERE id = ?",
                       (category_id,))
        conn.commit()
        return cursor.rowcount > 0

    def update_memory_file_path(self, memory_id: str, file_path: str) -> bool:
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("UPDATE memories SET file_path = ?, updated_at = ? WHERE id = ?",
                       (file_path, self._get_beijing_timestamp(), memory_id))
        conn.commit()
        return cursor.rowcount > 0

    def get_memories_by_category(self, category_id: str, layer: int) -> List[Dict[str, Any]]:
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, content, category, layer, level, tags, source, confidence,
                   expires_at, is_pinned, metadata, status, processed_status,
                   parent_id, file_path, created_at, updated_at, access_count, memory_type
            FROM memories
            WHERE category = ? AND layer = ?
              AND status = 'active'
              AND (invalid_at IS NULL OR invalid_at = '')
            ORDER BY level DESC, created_at DESC
        """, (category_id, layer))
        rows = cursor.fetchall()
        return [self._row_to_dict(row) for row in rows]

    def update(self, memory_id: str, content: str = None, category: str = None, reason: str = "",
               metadata: str = None, status: str = None, processed_status: str = None,
               short_name: str = None, parent_label: str = None) -> Optional[Dict[str, Any]]:
        conn = self._get_conn()
        cursor = conn.cursor()
        beijing_time = self._get_beijing_timestamp()

        updates = []
        params = []

        if content is not None:
            updates.append("content = ?")
            params.append(content)
        if category is not None:
            updates.append("category = ?")
            params.append(category)
        if metadata is not None:
            updates.append("metadata = ?")
            params.append(metadata)
        if status is not None:
            updates.append("status = ?")
            params.append(status)
        if processed_status is not None:
            updates.append("processed_status = ?")
            params.append(processed_status)
        if short_name is not None:
            updates.append("short_name = ?")
            params.append(short_name)
        if parent_label is not None:
            updates.append("parent_label = ?")
            params.append(parent_label)

        updates.append("updated_at = ?")
        params.append(beijing_time)
        params.append(memory_id)

        if updates:
            cursor.execute(f"UPDATE memories SET {', '.join(updates)} WHERE id = ?", params)

        if content is not None:
            if category is not None:
                cursor.execute("UPDATE memory_fts SET content = ?, category = ? WHERE memory_id = ?",
                               (content, category, memory_id))
            else:
                cursor.execute("UPDATE memory_fts SET content = ? WHERE memory_id = ?",
                               (content, memory_id))

        conn.commit()
        return self.get_by_id(memory_id)

    def delete(self, memory_id: str) -> bool:
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM memory_fts WHERE memory_id = ?", (memory_id,))
        cursor.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
        conn.commit()
        return cursor.rowcount > 0

    def list_all(self, limit: int = 1000, include_inactive: bool = False) -> List[Dict[str, Any]]:
        conn = self._get_conn()
        cursor = conn.cursor()
        where_clause = "" if include_inactive else "WHERE status = 'active' AND (invalid_at IS NULL OR invalid_at = '')"
        cursor.execute(f"""
            SELECT id, content, category, layer, level, tags, source, confidence,
                   expires_at, is_pinned, metadata, status, processed_status,
                   parent_id, file_path, valid_at, invalid_at, superseded_by,
                   created_at, updated_at, access_count, short_name, memory_type
            FROM memories {where_clause} ORDER BY created_at DESC LIMIT ?
        """, (limit,))
        rows = cursor.fetchall()
        return [self._row_to_dict(row) for row in rows]

    def search_by_keyword(self, keyword: str, limit: int = 20, include_inactive: bool = False) -> List[Dict[str, Any]]:
        conn = self._get_conn()
        cursor = conn.cursor()
        status_filter = "" if include_inactive else "AND m.status = 'active' AND (m.invalid_at IS NULL OR m.invalid_at = '')"
        try:
            safe_keyword = keyword.replace('"', '""')
            # 重要：FTS5 不支持在同一条语句中对同一张 FTS 表使用多次 `MATCH`
            # （会报 `unable to use function MATCH in the requested context`）。
            # 因此这里使用表级 MATCH，一次性覆盖 content/category/tags 三列。
            cursor.execute(f"""
                SELECT m.id, m.content, m.category, m.layer, m.level, m.tags, m.source, m.confidence,
                       m.expires_at, m.is_pinned, m.metadata, m.status, m.processed_status,
                       m.parent_id, m.file_path, m.valid_at, m.invalid_at, m.superseded_by,
                       m.created_at, m.updated_at, m.access_count, m.short_name
                FROM memories m
                JOIN memory_fts f ON m.id = f.memory_id
                WHERE memory_fts MATCH ? {status_filter}
                ORDER BY m.level DESC, m.created_at DESC LIMIT ?
            """, (safe_keyword, limit))
            rows = cursor.fetchall()
            # 中文/短词场景下 FTS 可能返回空（分词/匹配特性），此时兜底使用 LIKE，确保“咖啡/喝茶/偏好”等可被命中。
            if rows:
                return [self._row_to_dict(row) for row in rows]

            cursor.execute(
                f"""
                SELECT m.id, m.content, m.category, m.layer, m.level, m.tags, m.source, m.confidence,
                       m.expires_at, m.is_pinned, m.metadata, m.status, m.processed_status,
                       m.parent_id, m.file_path, m.valid_at, m.invalid_at, m.superseded_by,
                       m.created_at, m.updated_at, m.access_count, m.short_name
                FROM memories m
                WHERE (m.content LIKE ? OR m.category LIKE ? OR m.tags LIKE ?) {status_filter}
                ORDER BY m.level DESC, m.created_at DESC LIMIT ?
                """,
                (f"%{keyword}%", f"%{keyword}%", f"%{keyword}%", limit),
            )
            rows = cursor.fetchall()
            return [self._row_to_dict(row) for row in rows]
        except Exception:
            cursor.execute(f"""
                SELECT m.id, m.content, m.category, m.layer, m.level, m.tags, m.source, m.confidence,
                       m.expires_at, m.is_pinned, m.metadata, m.status, m.processed_status,
                       m.parent_id, m.file_path, m.valid_at, m.invalid_at, m.superseded_by,
                       m.created_at, m.updated_at, m.access_count, m.short_name
                FROM memories m
                WHERE (m.content LIKE ? OR m.category LIKE ?) {status_filter}
                ORDER BY m.level DESC, m.created_at DESC LIMIT ?
            """, (f"%{keyword}%", f"%{keyword}%", limit))
            rows = cursor.fetchall()
            return [self._row_to_dict(row) for row in rows]

    def increment_access(self, memory_id: str):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE memories SET access_count = access_count + 1
            WHERE id = ?
        """, (memory_id,))
        conn.commit()

    def get_by_layer(self, layer: int, include_inactive: bool = False) -> List[Dict[str, Any]]:
        conn = self._get_conn()
        cursor = conn.cursor()
        where_clause = "" if include_inactive else "AND status = 'active' AND (invalid_at IS NULL OR invalid_at = '')"
        cursor.execute(f"""
            SELECT id, content, category, layer, level, tags, source, confidence,
                   expires_at, is_pinned, metadata, status, processed_status,
                   parent_id, file_path, valid_at, invalid_at, superseded_by,
                   created_at, updated_at, access_count, short_name, memory_type
            FROM memories WHERE layer = ? {where_clause} ORDER BY level DESC, created_at DESC
        """, (layer,))
        rows = cursor.fetchall()
        return [self._row_to_dict(row) for row in rows]

    def get_recent_by_layer(self, layer: int, limit: int = 30, include_inactive: bool = False) -> List[Dict[str, Any]]:
        """按层获取最近 N 条记忆（用于 OpenClaw 偏好召回的 L1 兜底等场景）。"""
        conn = self._get_conn()
        cursor = conn.cursor()
        where_clause = "" if include_inactive else "AND status = 'active' AND (invalid_at IS NULL OR invalid_at = '')"
        cursor.execute(
            f"""
            SELECT id, content, category, layer, level, tags, source, confidence,
                   expires_at, is_pinned, metadata, status, processed_status,
                   parent_id, file_path, valid_at, invalid_at, superseded_by,
                   created_at, updated_at, access_count, short_name, memory_type
            FROM memories WHERE layer = ? {where_clause} ORDER BY created_at DESC LIMIT ?
            """,
            (layer, int(limit)),
        )
        rows = cursor.fetchall()
        return [self._row_to_dict(row) for row in rows]

    def update_level(self, memory_id: str, level: int) -> bool:
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE memories SET level = ? WHERE id = ?
        """, (level, memory_id))
        conn.commit()
        return cursor.rowcount > 0

    def update_pin(self, memory_id: str, is_pinned: bool, layer: int = None) -> bool:
        conn = self._get_conn()
        cursor = conn.cursor()
        if layer is not None:
            cursor.execute("""
                UPDATE memories SET is_pinned = ?, layer = ?, updated_at = ? WHERE id = ?
            """, (1 if is_pinned else 0, layer, self._get_beijing_timestamp(), memory_id))
        else:
            cursor.execute("""
                UPDATE memories SET is_pinned = ?, updated_at = ? WHERE id = ?
            """, (1 if is_pinned else 0, self._get_beijing_timestamp(), memory_id))
        conn.commit()
        return cursor.rowcount > 0

    def save_entities(self, memory_id: str, entities: list) -> bool:
        conn = self._get_conn()
        cursor = conn.cursor()
        for entity in entities:
            cursor.execute("""
                INSERT INTO memory_entities (memory_id, entity_text, entity_type)
                VALUES (?, ?, ?)
            """, (memory_id, entity["text"], entity["type"]))
        conn.commit()
        return True

    def update_processed_status(self, memory_id: str, processed_status: str) -> bool:
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE memories SET processed_status = ?, updated_at = ? WHERE id = ?
        """, (processed_status, self._get_beijing_timestamp(), memory_id))
        conn.commit()
        return cursor.rowcount > 0

    def invalidate_memory(self, memory_id: str, superseded_by: str) -> bool:
        """废止旧记忆，将其标记为无效并关联到新的替代记忆（用于时序图谱）"""
        conn = self._get_conn()
        cursor = conn.cursor()
        now = self._get_beijing_timestamp()
        cursor.execute("""
            UPDATE memories 
            SET status = 'invalid', invalid_at = ?, superseded_by = ?, updated_at = ? 
            WHERE id = ?
        """, (now, superseded_by, now, memory_id))
        conn.commit()
        return cursor.rowcount > 0

    def set_memory_status(
        self,
        memory_id: str,
        status: str,
        invalid_at: Optional[str] = None,
        superseded_by: Optional[str] = None,
        clear_invalid_fields: bool = False,
    ) -> bool:
        """管理用途：切换记忆有效状态（active/invalid/deleted）。

        - 当 status=active 且 clear_invalid_fields=True：会清空 invalid_at/superseded_by
        - 当 status=invalid 且 invalid_at 为空：自动写入当前北京时间
        """
        if not memory_id or not status:
            return False
        conn = self._get_conn()
        cursor = conn.cursor()
        now = self._get_beijing_timestamp()

        if status == "invalid" and not invalid_at:
            invalid_at = now

        if clear_invalid_fields and status == "active":
            invalid_at = None
            superseded_by = None

        cursor.execute(
            """
            UPDATE memories
            SET status = ?,
                invalid_at = ?,
                superseded_by = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (status, invalid_at, superseded_by, now, memory_id),
        )
        conn.commit()
        return cursor.rowcount > 0

    def get_by_layer_and_status(self, layer: int, processed_status: str, include_inactive: bool = False) -> List[Dict[str, Any]]:
        conn = self._get_conn()
        cursor = conn.cursor()
        where_clause = "" if include_inactive else "AND status = 'active' AND (invalid_at IS NULL OR invalid_at = '')"
        cursor.execute(f"""
            SELECT id, content, category, layer, level, tags, source, confidence,
                   expires_at, is_pinned, metadata, status, processed_status,
                   parent_id, file_path, valid_at, invalid_at, superseded_by,
                   created_at, updated_at, access_count, short_name, memory_type
            FROM memories WHERE layer = ? AND processed_status = ? {where_clause} ORDER BY level DESC, created_at DESC
        """, (layer, processed_status))
        rows = cursor.fetchall()
        return [self._row_to_dict(row) for row in rows]

    def add_audit_log(
        self,
        memory_id: str,
        action: str,
        old_content: Optional[str] = None,
        new_content: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        action_type: Optional[str] = None,
        source_ai: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> bool:
        """写入记忆审计日志（merge/supersede 等）。"""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO memory_audit_log (
                memory_id, action, source_ai, action_type,
                old_content, new_content, session_id, details
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                memory_id,
                action,
                source_ai,
                action_type,
                old_content,
                new_content,
                session_id,
                json.dumps(details or {}, ensure_ascii=False),
            ),
        )
        conn.commit()
        return cursor.rowcount > 0

    def add_mcp_audit_log(
        self,
        source: str,
        tool_name: str,
        args_summary: str,
        result_count: int = 0,
        status: str = "ok",
        error: str = "",
    ) -> bool:
        """写入 MCP 调用审计日志。

        重要：args_summary 必须为脱敏后的摘要（不要写入完整 content/query 等敏感文本）。
        """
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO mcp_audit_log (
                source, tool_name, args_summary, result_count, status, error, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                source,
                tool_name,
                args_summary,
                int(result_count or 0),
                status,
                error,
                self._get_beijing_timestamp(),
            ),
        )
        conn.commit()
        return cursor.rowcount > 0

    def get_audit_logs(self, memory_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, memory_id, action, source_ai, action_type,
                   old_content, new_content, category, tags, session_id, details, created_at
            FROM memory_audit_log
            WHERE memory_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (memory_id, limit),
        )
        rows = cursor.fetchall() or []
        keys = [
            "id",
            "memory_id",
            "action",
            "source_ai",
            "action_type",
            "old_content",
            "new_content",
            "category",
            "tags",
            "session_id",
            "details",
            "created_at",
        ]
        results: List[Dict[str, Any]] = []
        for row in rows:
            item = dict(zip(keys, row))
            if item.get("details"):
                try:
                    item["details"] = json.loads(item["details"])
                except Exception:
                    pass
            results.append(item)
        return results

    def get_version_chain(self, memory_id: str, max_depth: int = 50) -> List[Dict[str, Any]]:
        """获取版本链（root -> ... -> latest），包含 invalid 的历史版本。"""
        if not memory_id:
            return []

        # 1) 回溯到 root
        root_id = memory_id
        visited = set()
        for _ in range(max_depth):
            if root_id in visited:
                break
            visited.add(root_id)
            current = self.get_by_id(root_id)
            if not current:
                break
            parent_id = current.get("parent_id")
            if not parent_id:
                break
            root_id = parent_id

        # 2) 从 root 沿 superseded_by 向前遍历
        chain: List[Dict[str, Any]] = []
        current_id = root_id
        visited.clear()
        for _ in range(max_depth):
            if not current_id or current_id in visited:
                break
            visited.add(current_id)
            current = self.get_by_id(current_id)
            if not current:
                break
            chain.append(current)
            current_id = current.get("superseded_by")
        return chain

    def _get_beijing_timestamp(self) -> str:
        beijing_tz = timezone(timedelta(hours=8))
        return datetime.now(beijing_tz).strftime('%Y-%m-%d %H:%M:%S')

    def get_all_for_dedup(self) -> List[Dict[str, Any]]:
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, content, category, status, is_pinned FROM memories
        """)
        rows = cursor.fetchall()
        return [{
            "id": row[0],
            "content": row[1],
            "category": row[2],
            "status": row[3],
            "is_pinned": row[4]
        } for row in rows]

    def _row_to_dict(self, row) -> Dict[str, Any]:
        keys = ["id", "content", "category", "layer", "level", "tags", "source",
                "confidence", "expires_at", "is_pinned", "metadata",
                "status", "processed_status", "parent_id", "file_path",
                "valid_at", "invalid_at", "superseded_by",
                "created_at", "updated_at", "access_count", "short_name"]
        result = dict(zip(keys, row))
        if len(row) > len(keys):
            result["memory_type"] = row[len(keys)]
        elif "memory_type" not in result:
            result["memory_type"] = "episodic"
        if result.get("tags"):
            try:
                result["tags"] = json.loads(result["tags"])
            except Exception:
                result["tags"] = []
        if result.get("metadata"):
            try:
                result["metadata"] = json.loads(result["metadata"])
            except Exception:
                result["metadata"] = {}
        return result

    def _category_row_to_dict(self, row) -> Dict[str, Any]:
        keys = ["id", "name", "layer", "level", "parent_id", "memory_count", "metadata",
                "status", "created_at", "updated_at"]
        result = dict(zip(keys, row))
        if result.get("metadata"):
            try:
                result["metadata"] = json.loads(result["metadata"])
            except Exception:
                result["metadata"] = {}
        return result
