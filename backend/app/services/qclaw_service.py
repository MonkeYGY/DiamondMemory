"""Qclaw智能体集成服务"""
import requests
import json
import os
import shutil
import subprocess
import logging
import re
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)

QCLAW_HOME = os.path.join(os.path.expanduser("~"), ".qclaw")
QCLAW_CONFIG_PATH = os.path.join(QCLAW_HOME, "qclaw.json")
QCLAW_OPENCLAW_CONFIG_PATH = os.path.join(QCLAW_HOME, "openclaw.json")
QCLAW_WORKSPACE_PATH = os.path.join(QCLAW_HOME, "workspace")
QCLAW_CRON_PATH = os.path.join(QCLAW_HOME, "cron", "jobs.json")
QCLAW_MEMORY_MD_PATH = os.path.join(QCLAW_WORKSPACE_PATH, "MEMORY.md")
QCLAW_HEARTBEAT_MD_PATH = os.path.join(QCLAW_WORKSPACE_PATH, "HEARTBEAT.md")
QCLAW_AGENTS_MD_PATH = os.path.join(QCLAW_WORKSPACE_PATH, "AGENTS.md")
QCLAW_TOOLS_MD_PATH = os.path.join(QCLAW_WORKSPACE_PATH, "TOOLS.md")
QCLAW_SOUL_MD_PATH = os.path.join(QCLAW_WORKSPACE_PATH, "SOUL.md")

DM_SECTION_START = "<!-- DIAMOND_MEMORY_START -->"
DM_SECTION_END = "<!-- DIAMOND_MEMORY_END -->"

MEMORY_MD_TEMPLATE = """# 记忆系统

## 主要记忆：钻石记忆系统

本智能体使用**钻石记忆系统（DiamondMemory）**作为主要记忆存储和检索系统。

### ⚠️ 核心规则
- **每句对话都必须写入钻石记忆系统，不得遗漏！**
- **L1 层必须写入完整对话原文，禁止写摘要替代原文！**
- **所有内容使用中文Markdown格式**（品牌名、技术名词保留原文）
- 记忆写入是发送回复的前置条件
- 统一使用 HTTP API 进行交互

### 系统信息
- **服务地址**：动态读取 `~/.diamond-memory/port.json` 获取端口
- **端口发现**：`cat ~/.diamond-memory/port.json` 读取 JSON 中的 `endpoint` 字段
- **说明**：`~/.diamond-memory/port.json` 为桌面端自动写入的兼容镜像文件；端口权威来源为桌面端 `userData/port.json`，当两者不一致时以 `userData/port.json` 为准
- **数据存储**：本地 SQLite 数据库，完全隐私安全
- **来源标识**：`qclaw`
- **架构**：6 层知识提炼体系 (L1-L6)

### 端口发现（每次操作前必须执行）
```bash
DM_ENDPOINT=$(cat ~/.diamond-memory/port.json | python3 -c "import sys,json; print(json.load(sys.stdin)['endpoint'])" 2>/dev/null || echo "http://127.0.0.1:15920")
```

**连接失败时重新检测端口**：如果上述 endpoint 连接失败，执行以下命令重新检测：
```bash
# 1. 重新读取端口文件（可能端口已变更）
DM_ENDPOINT=$(cat ~/.diamond-memory/port.json | python3 -c "import sys,json; print(json.load(sys.stdin)['endpoint'])" 2>/dev/null || echo "http://127.0.0.1:15920")
# 2. 测试连接
curl -s -o /dev/null -w "%{{http_code}}" "$DM_ENDPOINT/health" 2>/dev/null
# 3. 如果仍然失败，尝试扫描常见端口
for PORT in 15920 15921 15922 15923 15924 15925 26890 26891 26892 26893 37960 37961 37962; do
  if curl -s -o /dev/null -w "%{{http_code}}" "http://127.0.0.1:$PORT/health" 2>/dev/null | grep -q "200"; then
    DM_ENDPOINT="http://127.0.0.1:$PORT"
    break
  fi
done
```

### 6 层知识提炼架构

| 层级 | 类型 | 说明 |
|------|------|------|
| **L1** | **原始数据层** | **AI软件全量写入完整对话原文**，不做任何压缩、摘要或去重，是所有记忆的源头 |
| **L2** | **沉淀层** | 系统自动从L1去重后迁移而来的有效记忆（近似合并/无近似新增） |
| **L4** | **总结记忆层** | 系统调用大模型整理L2内容合并总结得到（近似合并/无近似新增） |
| **L3** | **分类层** | L4层进行归类得到的分类目录层 |
| **L6** | **技能层** | L4层进行技能提炼得到的可复用技能（近似合并/无近似新增） |
| **L5** | **技能分类层** | L6层进行归类得到的技能目录层 |

> **重要**：AI软件只需写入L1层！L2-L6全部由系统自动从L1逐层提炼生成，AI软件禁止直接写入L2及以上层级！

### 写入格式规范（必须遵守）

#### 对话类型（category = conversation）
```bash
curl -X POST "$DM_ENDPOINT/api/memory/create" \\
  -H "Content-Type: application/json" \\
  -d '{{"content": "## 对话记录\\n\\n**时间**: 2026-04-28 14:30\\n**会话**: 第5轮 | **来源**: Qclaw\\n\\n---\\n\\n### 用户提问\\n用户原话\\n\\n### 助手回复\\n助手回复\\n\\n---\\n\\n**关键信息**: 关键事实\\n**标签**: #对话记录 #技术知识", "category": "conversation", "source": "qclaw", "layer": 1, "tags": ["对话记录", "技术知识"], "confidence": 0.95}}'
```

#### 知识类型（category = knowledge）
```bash
curl -X POST "$DM_ENDPOINT/api/memory/create" \\
  -H "Content-Type: application/json" \\
  -d '{{"content": "## 知识记录\\n\\n**时间**: 2026-04-28 14:30\\n**主题**: 知识主题\\n**来源**: Qclaw\\n\\n---\\n\\n### 核心内容\\n知识正文\\n\\n---\\n\\n**置信度**: 高\\n**标签**: #知识点 #最佳实践", "category": "knowledge", "source": "qclaw", "layer": 1, "tags": ["知识点", "最佳实践"], "confidence": 0.98}}'
```

#### 任务类型（category = task）
```bash
curl -X POST "$DM_ENDPOINT/api/memory/create" \\
  -H "Content-Type: application/json" \\
  -d '{{"content": "## 任务记录\\n\\n**时间**: 2026-04-28 14:30\\n**任务**: 任务名称\\n**状态**: 已完成\\n**来源**: Qclaw\\n\\n---\\n\\n### 任务描述\\n任务内容\\n\\n### 执行过程\\n执行步骤\\n\\n---\\n\\n**标签**: #任务执行 #自动化", "category": "task", "source": "qclaw", "layer": 1, "tags": ["任务执行", "自动化"], "confidence": 0.95}}'
```

### 分类体系

| 分类 | 用途 | 示例 |
|------|------|------|
| `conversation` | 对话记录 | 问答、讨论、决策 |
| `knowledge` | 知识记录 | 技术文档、知识点 |
| `task` | 任务记录 | 脚本执行、文件操作 |
| `preference` | 用户偏好 | 格式要求、工作习惯 |
| `insight` | 洞察分析 | 分析建议、优化方案 |

### 标准标签库
- 系统默认标签: `{system_tags}`
- 用户自定义标签: `{user_tags}`

**强制规则：每条记忆必须且只能从上述可用标签中选择标签！绝对禁止编造列表之外的标签！**

### 内容格式要求
- 所有内容使用中文Markdown排版
- 品牌名、技术专有名词保留原文（React、Python、Docker等）
- 概括总结内容用中文表述
- 标签使用中文，最多5个
- 每条记忆必须至少包含1个标准标签

### 记忆操作流程

#### 1. 写入记忆（HTTP API - 唯一方式，必须写入 L1 层）

```bash
DM_ENDPOINT=$(cat ~/.diamond-memory/port.json | python3 -c "import sys,json; print(json.load(sys.stdin)['endpoint'])" 2>/dev/null || echo "http://127.0.0.1:15920")
curl -X POST "$DM_ENDPOINT/api/memory/create" \\
  -H "Content-Type: application/json" \\
  -d '{{"content": "记忆内容", "category": "分类标识", "source": "qclaw", "layer": 1, "tags": ["标签1", "标签2"], "confidence": 0.95}}'
```

#### 2. 查询记忆

```bash
DM_ENDPOINT=$(cat ~/.diamond-memory/port.json | python3 -c "import sys,json; print(json.load(sys.stdin)['endpoint'])" 2>/dev/null || echo "http://127.0.0.1:15920")
curl -G "$DM_ENDPOINT/api/memory/query" --data-urlencode "query=查询问题" --data-urlencode "limit=10"
```

### 每日全量记录定时检查
- **任务内容**：每天 11:55 定时检查当天所有对话是否全量记录到钻石系统（完整原文）
- **兜底机制**：如钻石系统当时未开放/不可用，则在**下一次系统开放时**，于次日检查所有未记录的对话并全部补写进去
- **补写日期**：补写时使用各条对话当时的日期和时间，而不是记录当下的时间

### 使用规则

1. **对话前检索**：每次对话开始，先检索用户偏好和相关记忆
2. **任务前检索**：处理任务前，检索相关项目/环境信息
3. **每句对话写入**：**每句对话结束后立即写入**（核心规则）
4. **钻石系统不可用时**：先将记忆保存在本地原生记忆中（memory/YYYY-MM-DD.md），下次检测到钻石记忆系统开启后，检查数据库中已有内容，将未记录的内容补写进去
5. **更新优先**：发现记忆过时，优先更新而非新增
6. **分类准确**：根据内容选择正确的分类
7. **标签精简**：使用 3-5 个精准标签

---

## 备用记忆：原生记忆

当钻石记忆系统不可用时，使用下方原生记忆内容作为备用：
- 重要信息可临时记录在下方原生记忆区域（memory/YYYY-MM-DD.md）
- 系统恢复后需同步到钻石记忆系统

---

**最后更新**：{update_date}
"""

HEARTBEAT_DIAMOND_SECTION = """
## ⚠️ 每日全量记录定时检查（钻石记忆系统集成）

**任务内容**：
1. **每日检查**：每天 11:55 将当天所有对话**全量记录**到钻石记忆系统（L1 层，完整原文，不做任何摘要或压缩）
2. **兜底补写**：如果当天钻石记忆系统未开放/不可用，在**下一次系统开放时**，于次日检查所有未记录的对话，**全部补写进去**
3. **补写日期**：补写时使用各条对话当时的日期和时间，而不是记录当下的时间

**执行标准**：
- 每日 11:55 自动执行
- 扫描当日全部会话日志，逐条对比钻石系统已有记录
- 发现遗漏立即补写，确保覆盖率 100%
- 补写必须使用完整原文，禁止写摘要替代原文

### ⚠️ 核心规则
- **每句对话都必须写入钻石记忆系统，不得遗漏！**
- 记忆写入是发送回复的前置条件
- 钻石记忆系统不可用时先保存在本地原生记忆中，下次检测到开启后补写

- **主要记忆**：钻石记忆系统（动态端口，读取 `~/.diamond-memory/port.json` 获取 endpoint）
- 所有记忆读写优先使用钻石系统
- 定时任务的重要信息也写入钻石系统
- 本地 `MEMORY.md` 仅在钻石系统不可用时作为备用
- **交互方式**：统一使用 HTTP API
- **架构**：6 层知识提炼体系 (L1-L6)
"""

DAILY_CHECK_CRON_JOB = {
    "id": "dm-qclaw-diamond-memory-daily-check-1155",
    "name": "钻石记忆系统每日全量记录检查",
    "enabled": True,
    "schedule": {
        "kind": "cron",
        "expr": "55 11 * * *",
        "tz": "Asia/Shanghai"
    },
    "triggers": [
        {
            "type": "network_recovery",
            "delay_seconds": 30,
            "description": "网络恢复后 30 秒自动执行"
        },
        {
            "type": "system_startup",
            "delay_seconds": 300,
            "description": "系统启动后 5 分钟自动执行"
        }
    ],
    "sessionTarget": "isolated",
    "wakeMode": "now",
    "payload": {
        "kind": "agentTurn",
        "message": "请执行钻石记忆系统每日全量记录检查：1) 先读取 ~/.diamond-memory/port.json 获取钻石记忆系统服务地址（endpoint字段） 2) 检查今日（过去 24 小时内）的所有对话记录，对比钻石记忆系统中的记录 3) 找出遗漏未写入的对话或重要信息，并批量补写到钻石记忆系统 L1 层（完整原文，禁止摘要） 4) 补写时使用各条对话当时的日期和时间，而不是当前时间 5) 如果钻石记忆系统当前不可用，先将遗漏记录保存在本地 memory/ 目录，等下次系统可用时再补写 6) 确保每条对话都写入钻石系统，不得遗漏"
    },
    "delivery": {
        "mode": "announce",
        "channel": "last"
    },
    "state": {
        "nextRunAtMs": 0,
        "lastRunAtMs": 0,
        "lastRunStatus": "pending",
        "consecutiveErrors": 0
    }
}


class QclawService:
    """Qclaw智能体集成服务"""

    def __init__(self):
        self.base_url = "http://127.0.0.1:28789"
        self.api_key = None
        self.timeout = 30
        self._load_config()

    def _load_config(self):
        if os.path.exists(QCLAW_OPENCLAW_CONFIG_PATH):
            try:
                with open(QCLAW_OPENCLAW_CONFIG_PATH, "r", encoding="utf-8") as f:
                    config = json.load(f)
                auth = config.get("gateway", {}).get("auth", {})
                if auth.get("mode") == "token" and auth.get("token"):
                    self.api_key = auth["token"]
                gateway_port = config.get("gateway", {}).get("port")
                if gateway_port:
                    self.base_url = f"http://127.0.0.1:{gateway_port}"
            except Exception:
                pass
        if os.path.exists(QCLAW_CONFIG_PATH):
            try:
                with open(QCLAW_CONFIG_PATH, "r", encoding="utf-8") as f:
                    config = json.load(f)
                port = config.get("port")
                if port:
                    self.base_url = f"http://127.0.0.1:{port}"
            except Exception:
                pass

    def check_installation(self) -> Dict[str, Any]:
        result = {
            "installed": False,
            "path": None,
            "version": None,
            "gateway_running": False,
            "config_exists": False,
            "agents": []
        }

        qclaw_home_exists = os.path.isdir(QCLAW_HOME)
        if not qclaw_home_exists:
            return result

        result["installed"] = True
        result["path"] = QCLAW_HOME

        if os.path.exists(QCLAW_CONFIG_PATH):
            result["config_exists"] = True
            try:
                with open(QCLAW_CONFIG_PATH, "r", encoding="utf-8") as f:
                    config = json.load(f)
                app_version = config.get("sharedParams", {}).get("appVersion")
                if app_version:
                    result["version"] = f"v{app_version}"
            except Exception:
                pass

        if os.path.exists(QCLAW_OPENCLAW_CONFIG_PATH):
            try:
                with open(QCLAW_OPENCLAW_CONFIG_PATH, "r", encoding="utf-8") as f:
                    config = json.load(f)
                agents_list = config.get("agents", {}).get("list", [])
                result["agents"] = [
                    {"id": a.get("id", ""), "name": a.get("name", a.get("id", ""))}
                    for a in agents_list if isinstance(a, dict)
                ]
            except Exception:
                pass

        try:
            health_resp = requests.get(f"{self.base_url}/health", timeout=3)
            result["gateway_running"] = health_resp.status_code == 200
        except Exception:
            pass

        return result

    def is_diamond_memory_integrated(self) -> bool:
        if not os.path.exists(QCLAW_MEMORY_MD_PATH):
            return False
        try:
            with open(QCLAW_MEMORY_MD_PATH, "r", encoding="utf-8") as f:
                content = f.read()
                return DM_SECTION_START in content or "钻石记忆系统" in content or "DiamondMemory" in content
        except Exception:
            return False

    def is_agent_integrated(self, agent_id: str) -> bool:
        return self.is_diamond_memory_integrated()

    def configure_diamond_memory(self, agent_id: str = None) -> Dict[str, Any]:
        install_info = self.check_installation()
        if not install_info["installed"]:
            return {
                "success": False,
                "error": "未安装 Qclaw",
                "message": "请先安装 Qclaw 后再进行一键配置。"
            }
        if not install_info["config_exists"]:
            return {
                "success": False,
                "error": "Qclaw 配置文件不存在",
                "message": "请先运行 Qclaw 初始化配置。"
            }
        try:
            self._modify_memory_md()
            self._modify_heartbeat_md()
            self._modify_agents_md()
            self._modify_tools_md()
            return {
                "success": True,
                "message": "Qclaw 钻石记忆系统集成配置完成",
                "agents": install_info.get("agents", [])
            }
        except Exception as e:
            logger.error(f"配置 Qclaw 失败: {e}")
            return {"success": False, "error": str(e), "message": f"配置失败: {str(e)}"}

    def unconfigure_diamond_memory(self, agent_id: str = None) -> Dict[str, Any]:
        install_info = self.check_installation()
        if not install_info["installed"]:
            return {"success": False, "error": "未安装 Qclaw"}
        try:
            self._restore_workspace_files()
            return {
                "success": True,
                "message": "Qclaw 钻石记忆系统集成已关闭"
            }
        except Exception as e:
            logger.error(f"取消配置 Qclaw 失败: {e}")
            return {"success": False, "error": str(e), "message": f"取消配置失败: {str(e)}"}

    def _inject_section(self, filepath: str, section_content: str):
        if not os.path.exists(filepath):
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(f"{DM_SECTION_START}\n{section_content}\n{DM_SECTION_END}\n")
            return
        backup = filepath + ".dm-backup"
        if not os.path.exists(backup):
            shutil.copy2(filepath, backup)
        with open(filepath, "r", encoding="utf-8") as f:
            original_content = f.read()
        if DM_SECTION_START in original_content:
            remaining = re.sub(
                re.escape(DM_SECTION_START) + r'.*?' + re.escape(DM_SECTION_END),
                '', original_content, flags=re.DOTALL
            ).strip()
            full_content = f"{DM_SECTION_START}\n{section_content}\n{DM_SECTION_END}\n\n{remaining}\n"
        else:
            full_content = f"{DM_SECTION_START}\n{section_content}\n{DM_SECTION_END}\n\n{original_content}\n"
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(full_content)

    def _remove_section(self, filepath: str):
        if not os.path.exists(filepath):
            return
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        if DM_SECTION_START in content:
            remaining = re.sub(
                re.escape(DM_SECTION_START) + r'.*?' + re.escape(DM_SECTION_END),
                '', content, flags=re.DOTALL
            ).strip()
            with open(filepath, "w", encoding="utf-8") as f:
                f.write((remaining + "\n") if remaining else "")
        else:
            backup = filepath + ".dm-backup"
            if os.path.exists(backup):
                shutil.copy2(backup, filepath)

    def _modify_memory_md(self):
        from datetime import datetime
        import json as _json
        from app.storage.sqlite_store import SQLiteStore

        store = SQLiteStore()
        system_tags = _json.loads(store.get_config("system_tags") or '["开发辅助", "日常对话", "知识经验", "系统配置", "错误排查", "功能需求", "工作流"]')
        user_tags = _json.loads(store.get_config("user_tags") or "[]")

        update_date = datetime.now().strftime("%Y-%m-%d")
        section_content = MEMORY_MD_TEMPLATE.format(
            system_tags=", ".join(system_tags),
            user_tags=", ".join(user_tags) if user_tags else "无",
            update_date=update_date
        )

        self._inject_section(QCLAW_MEMORY_MD_PATH, section_content)

    def _modify_heartbeat_md(self):
        if not os.path.exists(QCLAW_HEARTBEAT_MD_PATH):
            return
        self._inject_section(QCLAW_HEARTBEAT_MD_PATH, HEARTBEAT_DIAMOND_SECTION)

    def _modify_agents_md(self):
        if not os.path.exists(QCLAW_AGENTS_MD_PATH):
            return

        backup = QCLAW_AGENTS_MD_PATH + ".dm-backup"
        if not os.path.exists(backup):
            shutil.copy2(QCLAW_AGENTS_MD_PATH, backup)

        with open(QCLAW_AGENTS_MD_PATH, "r", encoding="utf-8") as f:
            content = f.read()

        content = self._replace_hardcoded_port(content)

        with open(QCLAW_AGENTS_MD_PATH, "w", encoding="utf-8") as f:
            f.write(content)

    def _modify_tools_md(self):
        if not os.path.exists(QCLAW_TOOLS_MD_PATH):
            return

        backup = QCLAW_TOOLS_MD_PATH + ".dm-backup"
        if not os.path.exists(backup):
            shutil.copy2(QCLAW_TOOLS_MD_PATH, backup)

        with open(QCLAW_TOOLS_MD_PATH, "r", encoding="utf-8") as f:
            content = f.read()

        content = self._replace_hardcoded_port(content)

        with open(QCLAW_TOOLS_MD_PATH, "w", encoding="utf-8") as f:
            f.write(content)

    def _replace_hardcoded_port(self, content: str) -> str:
        endpoint_expr = '$(cat ~/.diamond-memory/port.json 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get(\\"endpoint\\") or (\\"http://127.0.0.1:%s\\" % d.get(\\"port\\",15920)))" 2>/dev/null || echo "http://127.0.0.1:15920")'
        content = re.sub(
            r'http://127\.0\.0\.1:8000',
            endpoint_expr,
            content
        )
        content = re.sub(
            r'http://127\.0\.0\.1:8080/api/v1/memory',
            f'{endpoint_expr}/api/memory',
            content
        )
        content = re.sub(
            r'http://127\.0\.0\.1:8080',
            endpoint_expr,
            content
        )
        return content

    def _restore_workspace_files(self):
        for filepath in [QCLAW_MEMORY_MD_PATH, QCLAW_HEARTBEAT_MD_PATH]:
            self._remove_section(filepath)
        for filepath in [QCLAW_AGENTS_MD_PATH, QCLAW_TOOLS_MD_PATH]:
            backup = filepath + ".dm-backup"
            if os.path.exists(backup):
                shutil.copy2(backup, filepath)

    def _add_daily_check_cron(self):
        os.makedirs(os.path.dirname(QCLAW_CRON_PATH), exist_ok=True)
        cron_data = {"version": 1, "jobs": []}
        if os.path.exists(QCLAW_CRON_PATH):
            try:
                with open(QCLAW_CRON_PATH, "r", encoding="utf-8") as f:
                    cron_data = json.load(f)
            except Exception:
                cron_data = {"version": 1, "jobs": []}

        jobs = cron_data.get("jobs", [])
        dm_job_exists = any(j.get("id") == DAILY_CHECK_CRON_JOB["id"] for j in jobs)

        if not dm_job_exists:
            import time
            job = dict(DAILY_CHECK_CRON_JOB)
            job["createdAtMs"] = int(time.time() * 1000)
            job["updatedAtMs"] = int(time.time() * 1000)
            job["state"]["nextRunAtMs"] = int(time.time() * 1000) + 3600000
            jobs.append(job)
            cron_data["jobs"] = jobs
        else:
            for j in jobs:
                if j.get("id") == DAILY_CHECK_CRON_JOB["id"]:
                    j["enabled"] = True
                    j["schedule"] = DAILY_CHECK_CRON_JOB["schedule"]
                    j["payload"] = DAILY_CHECK_CRON_JOB["payload"]

        with open(QCLAW_CRON_PATH, "w", encoding="utf-8") as f:
            json.dump(cron_data, f, ensure_ascii=False, indent=2)

    def _remove_daily_check_cron(self):
        if not os.path.exists(QCLAW_CRON_PATH):
            return
        try:
            with open(QCLAW_CRON_PATH, "r", encoding="utf-8") as f:
                cron_data = json.load(f)
            jobs = cron_data.get("jobs", [])
            cron_data["jobs"] = [j for j in jobs if j.get("id") != DAILY_CHECK_CRON_JOB["id"]]
            with open(QCLAW_CRON_PATH, "w", encoding="utf-8") as f:
                json.dump(cron_data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _restart_gateway(self):
        try:
            subprocess.run(
                ["openclaw", "gateway", "restart"],
                capture_output=True, text=True, timeout=30,
                env={**os.environ, "OPENCLAW_HOME": QCLAW_HOME}
            )
        except FileNotFoundError:
            openclaw_mjs = None
            if os.path.exists(QCLAW_CONFIG_PATH):
                try:
                    with open(QCLAW_CONFIG_PATH, "r", encoding="utf-8") as f:
                        config = json.load(f)
                    openclaw_mjs = config.get("cli", {}).get("openclawMjs")
                except Exception:
                    pass
            if openclaw_mjs and os.path.exists(openclaw_mjs):
                try:
                    node_binary = None
                    if os.path.exists(QCLAW_CONFIG_PATH):
                        with open(QCLAW_CONFIG_PATH, "r", encoding="utf-8") as f:
                            config = json.load(f)
                        node_binary = config.get("cli", {}).get("nodeBinary")
                    if node_binary and os.path.exists(node_binary):
                        subprocess.run(
                            [node_binary, openclaw_mjs, "gateway", "restart"],
                            capture_output=True, text=True, timeout=30,
                            env={**os.environ, "OPENCLAW_HOME": QCLAW_HOME}
                        )
                except Exception as e:
                    logger.warning(f"重启 Qclaw Gateway 失败: {e}")
            else:
                logger.warning("未找到 Qclaw 的 openclaw 命令，跳过 Gateway 重启")
        except Exception as e:
            logger.warning(f"重启 Qclaw Gateway 失败: {e}")

    def health_check(self) -> bool:
        try:
            url = f"{self.base_url}/health"
            response = requests.get(url, timeout=5)
            return response.status_code == 200
        except Exception:
            return False


qclaw_service = QclawService()
