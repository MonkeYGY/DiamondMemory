# 禁止运行时写安装目录（统一落到 userData）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 确保后端在打包安装后的只读安装目录下运行时，不会写入 `project_root`，所有运行时写入均落到 `--data-dir`（Electron `userData`）目录，且兼容旧配置读取并迁移写入到新位置。

**Architecture:** 在 `backend/app/config/settings.py` 的默认路径解析阶段（import 阶段）即可识别 `--data-dir`（以及可选环境变量兜底），从而把 `Settings` 初始化期间的目录创建、配置写入全部导向 `data_directory`。对旧配置文件仅做读取兼容，并在需要时迁移写入到新位置。

**Tech Stack:** Python 3.x, FastAPI, Pydantic Settings, Pytest

---

## Files to change

**Modify**
- `backend/app/config/settings.py`：data_dir 解析优先读取 argv/env；禁止写 `project_root/storage_config.json`；旧配置读取兼容与迁移写入
- `backend/tests/test_startup_status_api.py`（或新增测试文件）：补充“argv data-dir 优先”与“不会写 project_root”行为验证（按现有测试结构择一）

**Potentially modify (if needed after tests)**
- `backend/main.py`：保持现状（参数解析在 lifespan），一般无需改；仅在测试/回归发现边缘问题时调整

---

### Task 1: 为 settings data-dir 解析编写回归测试

**Files:**
- Create: `backend/tests/test_userdata_data_dir_resolution.py`
- Test: `backend/tests/test_userdata_data_dir_resolution.py`

- [ ] **Step 1: 写一个失败的测试：argv 中存在 `--data-dir` 时，settings 应使用该目录而不是 project_root/data**

```python
import importlib
import os
import sys
from pathlib import Path


def test_settings_respects_argv_data_dir(tmp_path, monkeypatch):
    # 模拟通过 argv 传入 --data-dir
    data_dir = tmp_path / "backend-data"
    monkeypatch.setattr(sys, "argv", ["backend", "--data-dir", str(data_dir)])

    # 重新加载 settings 模块，触发 import 阶段解析
    import app.config.settings as settings_module
    importlib.reload(settings_module)

    settings = settings_module.settings
    assert os.path.abspath(settings.data_directory) == os.path.abspath(str(data_dir))
    # 运行时系统文件路径应在 data_dir 下
    assert os.path.abspath(settings.database_path) == os.path.abspath(str(data_dir / "memory.db"))
```

- [ ] **Step 2: 运行测试，确认失败**

Run:
```bash
pytest -q backend/tests/test_userdata_data_dir_resolution.py::test_settings_respects_argv_data_dir
```

Expected: FAIL（当前实现会回退到 project_root/data 或其它默认逻辑）

- [ ] **Step 3: 写一个失败的测试：写入 storage_config 时不得写 project_root**

```python
import importlib
import os
import sys
from pathlib import Path


def test_write_storage_config_does_not_touch_project_root(tmp_path, monkeypatch):
    data_dir = tmp_path / "backend-data"
    data_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(sys, "argv", ["backend", "--data-dir", str(data_dir)])

    import app.config.settings as settings_module
    importlib.reload(settings_module)

    # 主动触发写入（模拟 data-dir / storage-path 更新）
    settings_module.update_storage_path(str(tmp_path / "workspace"))

    assert (data_dir / "storage_config.json").exists()
    # 关键断言：项目根目录不应该出现 storage_config.json
    project_root = Path(settings_module.__file__).resolve().parents[3]
    assert not (project_root / "storage_config.json").exists()
```

- [ ] **Step 4: 运行测试，确认失败**

Run:
```bash
pytest -q backend/tests/test_userdata_data_dir_resolution.py::test_write_storage_config_does_not_touch_project_root
```

Expected: FAIL（当前 `_write_storage_config` 会写 project_root/storage_config.json）

- [ ] **Step 5: Commit**

```bash
git add backend/tests/test_userdata_data_dir_resolution.py
git commit -m "test: add regression tests for userData data-dir resolution"
```

---

### Task 2: 实现 import 阶段识别 `--data-dir` 并统一写入到 data_dir

**Files:**
- Modify: `backend/app/config/settings.py`
- Test: `backend/tests/test_userdata_data_dir_resolution.py`

- [ ] **Step 1: 在 `settings.py` 中新增 argv/env 解析工具函数**

在文件顶部附近新增（示例代码，按项目风格微调）：

```python
def _get_data_dir_from_env_or_argv() -> Optional[str]:
    import sys

    env_dir = os.environ.get("DM_DATA_DIR") or os.environ.get("DIAMOND_MEMORY_DATA_DIR")
    if env_dir:
        return env_dir

    argv = list(getattr(sys, "argv", []) or [])
    for i, item in enumerate(argv):
        if item == "--data-dir" and i + 1 < len(argv):
            return argv[i + 1]
    return None
```

- [ ] **Step 2: 修改 `_resolve_data_dir()` 的优先级：先用 argv/env 的 data-dir**

目标行为：
- 若 argv/env 给出 data-dir：直接返回该目录（必要时创建目录由 Settings 统一处理）
- 仅当没有 data-dir 时，才允许回退到开发用 `project_root/data`

- [ ] **Step 3: 修改 `_write_storage_config()`：只写 data_dir/storage_config.json**

将以下逻辑删除/替换：
- `project_config_file = os.path.join(project_root, "storage_config.json")` 及其写入逻辑

保留写入：
- `os.path.join(data_dir, "storage_config.json")`

- [ ] **Step 4: 旧配置读取兼容但写入迁移**

实现要点：
- 新位置没有 `storage_config.json` 时，尝试只读读取旧位置配置
- 若读取成功，写入新位置（仅写新位置）

建议实现为独立函数，便于测试与避免重复：

```python
def _migrate_legacy_storage_config_if_needed(data_dir: str) -> None:
    ...
```

- [ ] **Step 5: 跑测试并修复直到通过**

Run:
```bash
pytest -q backend/tests/test_userdata_data_dir_resolution.py
```

Expected: PASS

- [ ] **Step 6: 跑后端关键测试（最小回归集）**

Run:
```bash
pytest -q backend/tests/test_startup_status_api.py backend/tests/test_storage_path_controlled_restart.py
```

Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add backend/app/config/settings.py
git commit -m "fix: avoid writing install dir by using --data-dir as runtime root"
```

---

### Task 3: 打包场景验证点（手工验收清单）

**Files:** 无（验证步骤）

- [ ] **Step 1: 干净机首次启动**
1. 安装后启动应用
2. 观察后端启动日志：`data_directory` 应指向 Electron `userData/backend-data`（或你实际命名的目录）
3. 确认无“权限不足/只读文件系统”类报错

- [ ] **Step 2: 重启验证**
1. 退出应用
2. 再次启动
3. 确认配置仍存在（`storage_path` 若有变更应保持）

- [ ] **Step 3: 可更改存储路径**
1. 在前端设置里修改存储路径
2. 确认后端 `update_storage_path()` 生效且 `storage_config.json` 仍在 `--data-dir` 下更新

---

## Self-review checklist (done by implementer)

- [ ] 搜索代码库，确认不再有 `project_root/storage_config.json` 的写入路径
- [ ] 确认所有运行时目录创建（db、索引、qdrant、temp、backups）均在 `settings.data_directory` 下
- [ ] 确认旧配置读取只用于兼容，不会在旧位置写回

