"""AI软件来源访问控制服务"""
import json
import os
import logging
from typing import List, Optional
from app.storage import SQLiteStore

logger = logging.getLogger(__name__)

SOURCE_BLOCKLIST_KEY = "blocked_sources"
MCP_READ_BLOCKLIST_KEY = "mcp_read_blocked_sources"
MCP_WRITE_BLOCKLIST_KEY = "mcp_write_blocked_sources"

SOURCE_ALIASES = {
    "openclaw": ["openclaw"],
    "hermes-agent": ["hermes-agent", "hermes"],
    "qclaw": ["qclaw"],
}


class SourceAccessControl:
    """控制AI软件来源对钻石记忆系统的访问权限"""

    def __init__(self):
        self._store = SQLiteStore()

    def block_source(self, source_id: str) -> bool:
        blocked = self.get_blocked_sources()
        aliases = SOURCE_ALIASES.get(source_id, [source_id])
        for alias in aliases:
            if alias not in blocked:
                blocked.append(alias)
        self._save_blocked_sources(blocked)
        logger.info(f"已阻止来源访问: {source_id} (aliases: {aliases})")
        return True

    def unblock_source(self, source_id: str) -> bool:
        blocked = self.get_blocked_sources()
        aliases = SOURCE_ALIASES.get(source_id, [source_id])
        blocked = [s for s in blocked if s not in aliases]
        self._save_blocked_sources(blocked)
        logger.info(f"已恢复来源访问: {source_id} (aliases: {aliases})")
        return True

    def is_source_blocked(self, source: Optional[str]) -> bool:
        if not source:
            return False
        blocked = self.get_blocked_sources()
        return source in blocked

    # ---------------------------
    # MCP 细粒度权限（读/写拆分）
    # 说明：
    # - SOURCE_BLOCKLIST_KEY：总开关（来源被禁用时，读写全禁）
    # - MCP_*_BLOCKLIST_KEY：MCP 专用附加开关（允许只禁读/只禁写）
    # ---------------------------
    def is_mcp_read_blocked(self, source: Optional[str]) -> bool:
        if not source:
            return False
        if self.is_source_blocked(source):
            return True
        return source in self.get_mcp_read_blocked_sources()

    def is_mcp_write_blocked(self, source: Optional[str]) -> bool:
        if not source:
            return False
        if self.is_source_blocked(source):
            return True
        return source in self.get_mcp_write_blocked_sources()

    def get_mcp_read_blocked_sources(self) -> List[str]:
        try:
            value = self._store.get_config(MCP_READ_BLOCKLIST_KEY)
            if value:
                return json.loads(value)
        except Exception:
            pass
        return []

    def get_mcp_write_blocked_sources(self) -> List[str]:
        try:
            value = self._store.get_config(MCP_WRITE_BLOCKLIST_KEY)
            if value:
                return json.loads(value)
        except Exception:
            pass
        return []

    def set_mcp_read_blocked_sources(self, sources: List[str]) -> bool:
        self._store.set_config(
            MCP_READ_BLOCKLIST_KEY,
            json.dumps(sources or [], ensure_ascii=False),
            "MCP：被禁止读取的来源列表（附加开关，SOURCE_BLOCKED 仍优先）",
        )
        return True

    def set_mcp_write_blocked_sources(self, sources: List[str]) -> bool:
        self._store.set_config(
            MCP_WRITE_BLOCKLIST_KEY,
            json.dumps(sources or [], ensure_ascii=False),
            "MCP：被禁止写入的来源列表（附加开关，SOURCE_BLOCKED 仍优先）",
        )
        return True

    def get_blocked_sources(self) -> List[str]:
        try:
            value = self._store.get_config(SOURCE_BLOCKLIST_KEY)
            if value:
                return json.loads(value)
        except Exception:
            pass
        return []

    def _save_blocked_sources(self, sources: List[str]):
        self._store.set_config(
            SOURCE_BLOCKLIST_KEY,
            json.dumps(sources, ensure_ascii=False),
            "被阻止访问的AI软件来源列表"
        )


source_access_control = SourceAccessControl()
