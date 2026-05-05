import builtins
import importlib
import os
import sys
from pathlib import Path


def _reload_settings_module():
    """
    某些测试需要在不同 argv 下重新 import settings。
    这里显式 reload，确保会重新执行 `settings = Settings()`。
    """
    # 注意：`app.config.__init__` 会 `from .settings import settings`，
    # 导致 `app.config.settings` 这个属性可能被绑定为 Settings 实例，
    # 直接 `import app.config.settings` 可能拿到的不是模块。
    settings_module = importlib.import_module("app.config.settings")
    return importlib.reload(settings_module)


def test_settings_respects_argv_data_dir(tmp_path, monkeypatch):
    """argv 中存在 --data-dir 时，import 阶段应使用该目录作为 data_directory。"""
    data_dir = tmp_path / "backend-data"
    monkeypatch.setattr(sys, "argv", ["backend", "--data-dir", str(data_dir)])

    settings_module = _reload_settings_module()
    settings = settings_module.settings

    assert os.path.abspath(settings.data_directory) == os.path.abspath(str(data_dir))
    assert os.path.abspath(settings.database_path) == os.path.abspath(str(data_dir / "memory.db"))


def test_write_storage_config_does_not_touch_project_root(tmp_path, monkeypatch):
    """任何写 storage_config.json 的行为都不得写入 project_root（安装目录）。"""
    data_dir = tmp_path / "backend-data"
    data_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(sys, "argv", ["backend", "--data-dir", str(data_dir)])

    settings_module = _reload_settings_module()
    project_root = Path(settings_module.__file__).resolve().parents[3]
    forbidden = os.path.abspath(str(project_root / "storage_config.json"))

    # 如果生产代码尝试写入 project_root/storage_config.json，直接让测试失败
    original_open = builtins.open

    def guarded_open(file, *args, **kwargs):  # noqa: ANN001
        try:
            if os.path.abspath(str(file)) == forbidden:
                raise AssertionError("禁止写入 project_root/storage_config.json（安装目录只读）")
        except TypeError:
            # file 可能是 fd 等非路径对象
            pass
        return original_open(file, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", guarded_open)

    # 主动触发写入（模拟修改存储路径）
    settings_module.update_storage_path(str(tmp_path / "workspace"))

    assert (data_dir / "storage_config.json").exists()
