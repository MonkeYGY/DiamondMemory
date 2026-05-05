"""Hermes Agent智能体集成服务"""
import json
import os
import shutil
import subprocess
import logging
import re
from typing import Dict, Any, List
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

HERMES_HOME = os.path.expanduser("~/.hermes")
HERMES_CONFIG_PATH = os.path.join(HERMES_HOME, "config.yaml")
HERMES_SOUL_PATH = os.path.join(HERMES_HOME, "SOUL.md")
HERMES_MEMORY_PATH = os.path.join(HERMES_HOME, "memories", "MEMORY.md")
HERMES_USER_MEMORY_PATH = os.path.join(HERMES_HOME, "memories", "USER.md")
HERMES_CRON_PATH = os.path.join(HERMES_HOME, "cron", "jobs.json")
HERMES_GATEWAY_STATE_PATH = os.path.join(HERMES_HOME, "gateway_state.json")
DIAMOND_MEMORY_CONFIG_MARKER = "diamond_memory_integrated"

DM_SECTION_START = "<!-- DIAMOND_MEMORY_START -->"
DM_SECTION_END = "<!-- DIAMOND_MEMORY_END -->"

DIAMOND_MEMORY_SOUL_APPENDIX = """

## MANDATORY: Diamond Memory System Integration (HIGHEST PRIORITY - OVERRIDES ALL OTHER RULES)

You MUST follow these rules on EVERY conversation turn without exception:

### Rule 1: Write EVERY conversation to Diamond Memory System
After you finish responding to the user, you MUST use your `terminal` tool to execute a curl command that writes the full conversation to the Diamond Memory System L1 layer. This is NOT optional — it is a mandatory step before your response is complete.

### Rule 2: How to write (use terminal tool every turn)
Step 1 — Discover endpoint:
> Note: `~/.diamond-memory/port.json` is a compatibility mirror written by the DiamondMemory desktop app; the authoritative port source is the desktop app `userData/port.json` (when mismatch, trust `userData/port.json`).
```
DM_ENDPOINT=$(cat ~/.diamond-memory/port.json | python3 -c "import sys,json; print(json.load(sys.stdin)['endpoint'])" 2>/dev/null || echo "http://127.0.0.1:15920")
```
**If connection fails, re-detect port:**
```
DM_ENDPOINT=$(cat ~/.diamond-memory/port.json | python3 -c "import sys,json; print(json.load(sys.stdin)['endpoint'])" 2>/dev/null || echo "http://127.0.0.1:15920")
if ! curl -s -o /dev/null -w "%{{http_code}}" "$DM_ENDPOINT/health" 2>/dev/null | grep -q "200"; then
  for PORT in 15920 15921 15922 15923 15924 15925 26890 26891 26892 26893 37960 37961 37962; do
    if curl -s -o /dev/null -w "%{{http_code}}" "http://127.0.0.1:$PORT/health" 2>/dev/null | grep -q "200"; then
      DM_ENDPOINT="http://127.0.0.1:$PORT"
      break
    fi
  done
fi
```
Step 2 — Write the full conversation in Chinese Markdown format:
```
curl -X POST "$DM_ENDPOINT/api/memory/create" -H "Content-Type: application/json" -d '{"content": "## 对话记录\\n\\n**时间**: 2026-04-26 14:30\\n**会话**: 第5轮 | **来源**: Hermes Agent\\n\\n---\\n\\n### 用户提问\\n用户原话\\n\\n### 助手回复\\n助手回复内容\\n\\n---\\n\\n**关键信息**: 关键事实/决策\\n**标签**: #对话记录 #技术知识", "category": "conversation", "source": "hermes", "tags": ["对话记录", "技术知识"], "confidence": 0.95, "layer": 1}'
```

### Rule 3: Content format requirements
- ALL content MUST use Chinese Markdown format (see Rule 2 example)
- Title: `## 对话记录` for conversations, `## 知识记录` for knowledge, `## 任务记录` for tasks
- Use `### 用户提问` and `### 助手回复` for dialog structure
- Include metadata: `**时间**`, `**会话**`, `**来源**`, `**关键信息**`, `**标签**`
- NEVER write summaries instead of original text
- Use Chinese for all descriptive content (except brand/tech names like React, Python, Docker)

### Rule 4: Category and tag standards
- Categories: `conversation` (对话记录) | `knowledge` (知识记录) | `task` (任务记录) | `preference` (用户偏好) | `insight` (洞察分析)
- Tags MUST use Chinese standard tags: `对话记录`, `知识点`, `任务执行`, `用户偏好`, `最佳实践`, etc.
- Each memory must have at least 1 standard tag, max 5 tags
- Source identifier: `hermes`

### Rule 5: Fallback when Diamond Memory System is unavailable
If the curl command fails (system not running), save to local memory (MEMORY.md) temporarily. Next time Diamond Memory System is available, check existing records and backfill any missing conversations using their ORIGINAL dates and times (not the current time).

### Rule 6: Query before responding
At the start of each conversation, query Diamond Memory System for user preferences and relevant context:
```
DM_ENDPOINT=$(cat ~/.diamond-memory/port.json | python3 -c "import sys,json; print(json.load(sys.stdin)['endpoint'])" 2>/dev/null || echo "http://127.0.0.1:15920")
curl -G "$DM_ENDPOINT/api/memory/query" --data-urlencode "query=user preferences and context" --data-urlencode "limit=10"
```
"""

MEMORY_MD_TEMPLATE = """钻石记忆系统（DiamondMemory）是主要记忆系统，下方原生记忆内容仅作备用。
每句对话必须用terminal工具执行curl写入钻石记忆系统L1层（完整原文，禁止摘要）。
端口发现：cat ~/.diamond-memory/port.json 读取endpoint字段。
说明：~/.diamond-memory/port.json 为桌面端自动写入的兼容镜像文件；端口权威来源为桌面端 userData/port.json。

## 写入格式规范（必须遵守）

### 对话类型（category = conversation）
curl -X POST "$DM_ENDPOINT/api/memory/create" -H "Content-Type: application/json" -d '{"content": "## 对话记录\\n\\n**时间**: 2026-04-26 14:30\\n**会话**: 第5轮 | **来源**: Hermes Agent\\n\\n---\\n\\n### 用户提问\\n用户原话\\n\\n### 助手回复\\n助手回复\\n\\n---\\n\\n**关键信息**: 关键事实\\n**标签**: #对话记录 #技术知识", "category": "conversation", "source": "hermes", "tags": ["对话记录", "技术知识"], "confidence": 0.95, "layer": 1}'

### 知识类型（category = knowledge）
curl -X POST "$DM_ENDPOINT/api/memory/create" -H "Content-Type: application/json" -d '{"content": "## 知识记录\\n\\n**时间**: 2026-04-26 14:30\\n**主题**: 知识主题\\n**来源**: Hermes Agent\\n\\n---\\n\\n### 核心内容\\n知识正文\\n\\n---\\n\\n**置信度**: 高\\n**标签**: #知识点 #最佳实践", "category": "knowledge", "source": "hermes", "tags": ["知识点", "最佳实践"], "confidence": 0.98, "layer": 1}'

### 任务类型（category = task）
curl -X POST "$DM_ENDPOINT/api/memory/create" -H "Content-Type: application/json" -d '{"content": "## 任务记录\\n\\n**时间**: 2026-04-26 14:30\\n**任务**: 任务名称\\n**状态**: 已完成\\n**来源**: Hermes Agent\\n\\n---\\n\\n### 任务描述\\n任务内容\\n\\n### 执行过程\\n执行步骤\\n\\n---\\n\\n**标签**: #任务执行 #自动化", "category": "task", "source": "hermes", "tags": ["任务执行", "自动化"], "confidence": 0.95, "layer": 1}'

## 分类体系
- conversation: 对话记录（问答、讨论、决策）
- knowledge: 知识记录（技术文档、知识点）
- task: 任务记录（脚本执行、文件操作）
- preference: 用户偏好（格式要求、工作习惯）
- insight: 洞察分析（分析建议、优化方案）

## 标准标签库
对话类: 对话记录, 问题解答, 需求讨论, 决策记录
知识类: 知识点, 技术规范, 最佳实践, 常见问题
任务类: 任务执行, 自动化脚本, 文件操作, 代码修改
偏好类: 用户偏好, 工作习惯, 沟通风格, 格式要求
洞察类: 分析建议, 优化方案, 风险提示, 趋势预测

## 内容格式要求
- 所有内容使用中文Markdown排版
- 品牌名、技术专有名词保留原文（React、Python、Docker等）
- 概括总结内容用中文表述
- 标签使用中文，最多5个
- 每条记忆必须至少包含1个标准标签

## 查询记忆
curl -G "$DM_ENDPOINT/api/memory/query" --data-urlencode "query=问题" --data-urlencode "limit=10"

钻石系统不可用时先存在下方原生记忆区域，下次可用时补写，日期用各自当时时间。
每日11:55定时检查当日对话是否全量记录，遗漏的补写。
§
用户偏好：简体中文，法律科普抖音号，免费方案，30秒短视频，飞书平台
§
设备：MacBook Pro M1 Max，外接4K显示器，cliclick鼠标控制
§
飞书文档：https://wcnc1c5oeusx.feishu.cn/drive/folder/Z77wfPzPjljykHd9Gvhcy9CdnOe
"""

DAILY_CHECK_CRON_JOB = {
    "id": "dm-hermes-diamond-memory-daily-check-1155",
    "name": "钻石记忆系统每日全量记录检查",
    "prompt": "请执行钻石记忆系统每日全量记录检查：1) 先用terminal工具执行 cat ~/.diamond-memory/port.json 获取钻石记忆系统服务地址（endpoint字段） 2) 检查今日（过去24小时内）的所有对话记录，用curl查询钻石记忆系统中的已有记录 3) 找出遗漏未写入的对话，用curl批量补写到钻石记忆系统L1层（完整原文，禁止摘要） 4) 补写时使用各条对话当时的日期和时间，而不是当前时间 5) 如果钻石记忆系统当前不可用，先将遗漏记录保存在本地MEMORY.md，等下次系统可用时再补写 6) 确保每条对话都写入钻石系统，不得遗漏",
    "skills": [],
    "skill": None,
    "model": None,
    "provider": None,
    "base_url": None,
    "script": None,
    "schedule": {
        "kind": "cron",
        "expr": "55 11 * * *",
        "display": "55 11 * * *"
    },
    "repeat": {
        "times": None,
        "completed": 0
    },
    "enabled": True,
    "state": "scheduled",
    "paused_at": None,
    "paused_reason": None,
    "deliver": "origin",
    "origin": {
        "source": "diamond-memory-system",
        "created_by": "one-click-config"
    }
}


class HermesService:
    """Hermes Agent智能体集成服务"""

    def __init__(self):
        self.timeout = 30

    def check_installation(self) -> Dict[str, Any]:
        result = {
            "installed": False,
            "path": None,
            "version": None,
            "gateway_running": False,
            "config_exists": False,
            "agents": []
        }

        hermes_home_exists = os.path.isdir(HERMES_HOME)
        if not hermes_home_exists:
            return result

        result["installed"] = True
        result["path"] = HERMES_HOME

        hermes_bin_paths = [
            os.path.expanduser("~/.hermes/hermes-agent/.venv/bin/hermes"),
            shutil.which("hermes") or "",
            "/usr/local/bin/hermes",
        ]
        for p in hermes_bin_paths:
            if p and os.path.isfile(p):
                result["path"] = p
                break

        if not result["path"] or not os.path.isfile(result["path"]):
            try:
                check = subprocess.run(
                    ["which", "hermes"],
                    capture_output=True, text=True, timeout=5
                )
                if check.returncode == 0 and check.stdout.strip():
                    result["path"] = check.stdout.strip()
            except Exception:
                pass

        if result["path"] and os.path.isfile(result["path"]):
            try:
                ver = subprocess.run(
                    [result["path"], "--version"],
                    capture_output=True, text=True, timeout=10
                )
                if ver.returncode == 0:
                    version_str = ver.stdout.strip()
                    if " Project: " in version_str:
                        version_str = version_str.split(" Project: ")[0]
                    result["version"] = version_str
            except Exception:
                pass

        result["config_exists"] = os.path.exists(HERMES_CONFIG_PATH)

        if result["config_exists"]:
            try:
                import yaml
                with open(HERMES_CONFIG_PATH, "r", encoding="utf-8") as f:
                    config = yaml.safe_load(f) or {}
                agents_list = config.get("agents", {}).get("list", [])
                if isinstance(agents_list, list):
                    result["agents"] = [
                        {"id": a.get("id", ""), "name": a.get("name", a.get("id", ""))}
                        for a in agents_list if isinstance(a, dict)
                    ]
            except Exception:
                pass

        if os.path.exists(HERMES_GATEWAY_STATE_PATH):
            try:
                with open(HERMES_GATEWAY_STATE_PATH, "r", encoding="utf-8") as f:
                    state = json.load(f)
                result["gateway_running"] = state.get("gateway_state") == "running"
            except Exception:
                pass

        return result

    def is_diamond_memory_integrated(self) -> bool:
        if not os.path.exists(HERMES_SOUL_PATH):
            return False
        try:
            with open(HERMES_SOUL_PATH, "r", encoding="utf-8") as f:
                content = f.read()
                return DM_SECTION_START in content or "Diamond Memory System Integration" in content or "钻石记忆系统" in content
        except Exception:
            return False

    def is_agent_integrated(self, agent_id: str) -> bool:
        return self.is_diamond_memory_integrated()

    def configure_diamond_memory(self, agent_id: str = None) -> Dict[str, Any]:
        install_info = self.check_installation()
        if not install_info["installed"]:
            return {
                "success": False,
                "error": "未安装 Hermes Agent",
                "message": "请先安装 Hermes Agent 后再进行一键配置。安装方式：pip install hermes-agent 或访问 https://github.com/nous-research/hermes"
            }
        if not install_info["config_exists"]:
            return {
                "success": False,
                "error": "Hermes Agent 配置文件不存在",
                "message": "请先运行 Hermes Agent 初始化配置：hermes init"
            }
        try:
            self._modify_soul_md()
            self._modify_memory_md()
            return {
                "success": True,
                "message": "Hermes Agent 钻石记忆系统集成配置完成",
                "agents": install_info.get("agents", [])
            }
        except Exception as e:
            logger.error(f"配置 Hermes Agent 失败: {e}")
            return {"success": False, "error": str(e), "message": f"配置失败: {str(e)}"}

    def unconfigure_diamond_memory(self, agent_id: str = None) -> Dict[str, Any]:
        install_info = self.check_installation()
        if not install_info["installed"]:
            return {"success": False, "error": "未安装 Hermes Agent"}
        try:
            self._restore_soul_md()
            self._restore_memory_md()
            return {
                "success": True,
                "message": "Hermes Agent 钻石记忆系统集成已关闭"
            }
        except Exception as e:
            logger.error(f"取消配置 Hermes Agent 失败: {e}")
            return {"success": False, "error": str(e), "message": f"取消配置失败: {str(e)}"}

    def _inject_section(self, filepath: str, section_content: str):
        if not os.path.exists(filepath):
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
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

    def _modify_soul_md(self):
        import json
        from app.storage.sqlite_store import SQLiteStore
        store = SQLiteStore()
        system_tags = json.loads(store.get_config("system_tags") or '["开发辅助", "日常对话", "知识经验", "系统配置", "错误排查", "功能需求", "工作流"]')
        user_tags = json.loads(store.get_config("user_tags") or "[]")
        all_tags = system_tags + user_tags
        
        modified_appendix = DIAMOND_MEMORY_SOUL_APPENDIX.replace(
            "- Tags MUST use Chinese standard tags: `对话记录`, `知识点`, `任务执行`, `用户偏好`, `最佳实践`, etc.",
            f"- Tags MUST use ONLY these standard tags: `{('`, `'.join(all_tags))}`"
        )
        
        if not os.path.exists(HERMES_SOUL_PATH):
            default_soul = "You are Hermes Agent, an intelligent AI assistant created by Nous Research. You are helpful, knowledgeable, and direct. You assist users with a wide range of tasks including answering questions, writing and editing code, analyzing information, creative work, and executing actions via your tools. You communicate clearly, admit uncertainty when appropriate, and prioritize being genuinely useful over being verbose unless otherwise directed below. Be targeted and efficient in your exploration and investigations."
            os.makedirs(os.path.dirname(HERMES_SOUL_PATH), exist_ok=True)
            with open(HERMES_SOUL_PATH, "w", encoding="utf-8") as f:
                f.write(default_soul + "\n")
        
        self._inject_section(HERMES_SOUL_PATH, modified_appendix)

    def _restore_soul_md(self):
        self._remove_section(HERMES_SOUL_PATH)

    def _modify_memory_md(self):
        import json
        from app.storage.sqlite_store import SQLiteStore
        store = SQLiteStore()
        system_tags = json.loads(store.get_config("system_tags") or '["开发辅助", "日常对话", "知识经验", "系统配置", "错误排查", "功能需求", "工作流"]')
        user_tags = json.loads(store.get_config("user_tags") or "[]")
        
        modified_template = MEMORY_MD_TEMPLATE.replace(
            "对话类: 对话记录, 问题解答, 需求讨论, 决策记录\n知识类: 知识点, 技术规范, 最佳实践, 常见问题\n任务类: 任务执行, 自动化脚本, 文件操作, 代码修改\n偏好类: 用户偏好, 工作习惯, 沟通风格, 格式要求\n洞察类: 分析建议, 优化方案, 风险提示, 趋势预测",
            f"系统默认标签: {', '.join(system_tags)}\n用户自定义标签: {', '.join(user_tags) if user_tags else '无'}"
        )
        
        self._inject_section(HERMES_MEMORY_PATH, modified_template)

    def _restore_memory_md(self):
        self._remove_section(HERMES_MEMORY_PATH)

    def _add_daily_check_cron(self):
        os.makedirs(os.path.dirname(HERMES_CRON_PATH), exist_ok=True)
        cron_data = {"version": 1, "jobs": []}
        if os.path.exists(HERMES_CRON_PATH):
            try:
                with open(HERMES_CRON_PATH, "r", encoding="utf-8") as f:
                    cron_data = json.load(f)
            except Exception:
                cron_data = {"version": 1, "jobs": []}

        jobs = cron_data.get("jobs", [])
        dm_job_id = DAILY_CHECK_CRON_JOB["id"]
        dm_job_exists = any(j.get("id") == dm_job_id for j in jobs)

        now_iso = datetime.now().isoformat()
        next_run = datetime.now().replace(hour=11, minute=55, second=0, microsecond=0)
        if next_run <= datetime.now():
            next_run += timedelta(days=1)

        if not dm_job_exists:
            job = dict(DAILY_CHECK_CRON_JOB)
            job["id"] = dm_job_id
            job["created_at"] = now_iso
            job["next_run_at"] = next_run.isoformat()
            job["last_run_at"] = None
            job["last_status"] = None
            job["last_error"] = None
            job["last_delivery_error"] = None
            jobs.append(job)
        else:
            for j in jobs:
                if j.get("id") == dm_job_id:
                    j["enabled"] = True
                    j["state"] = "scheduled"
                    j["schedule"] = DAILY_CHECK_CRON_JOB["schedule"]
                    j["prompt"] = DAILY_CHECK_CRON_JOB["prompt"]
                    j["paused_at"] = None
                    j["paused_reason"] = None

        cron_data["jobs"] = jobs
        with open(HERMES_CRON_PATH, "w", encoding="utf-8") as f:
            json.dump(cron_data, f, ensure_ascii=False, indent=2)

    def _remove_daily_check_cron(self):
        if not os.path.exists(HERMES_CRON_PATH):
            return
        try:
            with open(HERMES_CRON_PATH, "r", encoding="utf-8") as f:
                cron_data = json.load(f)
            jobs = cron_data.get("jobs", [])
            dm_job_id = DAILY_CHECK_CRON_JOB["id"]
            cron_data["jobs"] = [j for j in jobs if j.get("id") != dm_job_id]
            with open(HERMES_CRON_PATH, "w", encoding="utf-8") as f:
                json.dump(cron_data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _restart_gateway(self):
        try:
            subprocess.run(
                ["hermes", "gateway", "restart"],
                capture_output=True, text=True, timeout=30
            )
        except FileNotFoundError:
            hermes_paths = [
                os.path.expanduser("~/.hermes/hermes-agent/.venv/bin/hermes"),
                os.path.expanduser("~/.local/bin/hermes"),
            ]
            restarted = False
            for hp in hermes_paths:
                if os.path.isfile(hp):
                    try:
                        subprocess.run(
                            [hp, "gateway", "restart"],
                            capture_output=True, text=True, timeout=30
                        )
                        restarted = True
                        break
                    except Exception as e:
                        logger.warning(f"重启 Hermes Agent Gateway 失败 ({hp}): {e}")
            if not restarted:
                logger.warning("未找到 hermes 命令，跳过 Gateway 重启")
        except Exception as e:
            logger.warning(f"重启 Hermes Agent Gateway 失败: {e}")


hermes_service = HermesService()
