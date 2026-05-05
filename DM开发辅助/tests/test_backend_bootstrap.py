import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[2]
HELPER_DIR = PROJECT_ROOT / "DM开发辅助"

if str(HELPER_DIR) not in sys.path:
    sys.path.insert(0, str(HELPER_DIR))

import backend_bootstrap


class BackendBootstrapTests(unittest.TestCase):
    def test_build_backend_launch_command_uses_project_venv(self):
        with tempfile.TemporaryDirectory() as tmp:
            backend_dir = Path(tmp) / "backend"
            venv_bin = backend_dir / "venv" / "bin"
            venv_bin.mkdir(parents=True)
            (backend_dir / "requirements.txt").write_text("fastapi\n", encoding="utf-8")
            (venv_bin / "python3").write_text("", encoding="utf-8")

            command = backend_bootstrap.build_backend_launch_command(backend_dir)

            self.assertIn(str(backend_dir / "venv" / "bin" / "python3"), command)
            self.assertIn("-m uvicorn main:app", command)
            self.assertIn("--host 127.0.0.1", command)
            # 默认稳定端口：15920（仅在冲突时由 Electron 侧迁移到其他端口）
            self.assertIn("--port 15920", command)
            self.assertIn("--reload", command)

    def test_ensure_backend_environment_creates_venv_and_installs_requirements(self):
        with tempfile.TemporaryDirectory() as tmp:
            backend_dir = Path(tmp) / "backend"
            backend_dir.mkdir(parents=True)
            (backend_dir / "requirements.txt").write_text("fastapi\npydantic-settings\n", encoding="utf-8")

            calls = []

            def fake_run(cmd, cwd=None):
                calls.append((cmd, cwd))
                if cmd[:3] == [sys.executable, "-m", "venv"]:
                    venv_python = backend_dir / "venv" / "bin" / "python3"
                    venv_python.parent.mkdir(parents=True, exist_ok=True)
                    venv_python.write_text("", encoding="utf-8")

            with patch.object(backend_bootstrap, "run_checked", side_effect=fake_run):
                python_path = backend_bootstrap.ensure_backend_environment(
                    backend_dir,
                    installer_python=sys.executable,
                )

            self.assertEqual(python_path, backend_dir / "venv" / "bin" / "python3")
            self.assertEqual(
                calls[0],
                ([sys.executable, "-m", "venv", str(backend_dir / "venv")], backend_dir),
            )
            self.assertEqual(
                calls[1],
                ([str(backend_dir / "venv" / "bin" / "python3"), "-m", "pip", "install", "-r", str(backend_dir / "requirements.txt")], backend_dir),
            )


if __name__ == "__main__":
    unittest.main()
