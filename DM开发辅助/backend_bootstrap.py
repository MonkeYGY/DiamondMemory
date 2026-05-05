#!/usr/bin/env python3

import argparse
import hashlib
import shlex
import subprocess
import sys
from pathlib import Path


REQUIRED_MODULES = ("fastapi", "uvicorn", "requests", "pydantic_settings")


def run_checked(cmd, cwd=None):
    subprocess.run(cmd, cwd=cwd, check=True)


def get_venv_python(backend_dir: Path) -> Path:
    return backend_dir / "venv" / "bin" / "python3"


def get_requirements_path(backend_dir: Path) -> Path:
    return backend_dir / "requirements.txt"


def get_install_stamp_path(backend_dir: Path) -> Path:
    return backend_dir / "venv" / ".requirements.installed"


def requirements_digest(requirements_path: Path) -> str:
    content = requirements_path.read_bytes()
    return hashlib.sha256(content).hexdigest()


def is_venv_ready(backend_dir: Path) -> bool:
    venv_python = get_venv_python(backend_dir)
    if not venv_python.exists():
        return False

    requirements_path = get_requirements_path(backend_dir)
    stamp_path = get_install_stamp_path(backend_dir)
    if not requirements_path.exists() or not stamp_path.exists():
        return False

    expected_digest = requirements_digest(requirements_path)
    if stamp_path.read_text(encoding="utf-8").strip() != expected_digest:
        return False

    check_code = "import " + ", ".join(REQUIRED_MODULES)
    result = subprocess.run(
        [str(venv_python), "-c", check_code],
        cwd=backend_dir,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return result.returncode == 0


def ensure_backend_environment(backend_dir: Path, installer_python: str = sys.executable) -> Path:
    requirements_path = get_requirements_path(backend_dir)
    if not requirements_path.exists():
        raise FileNotFoundError(f"未找到 requirements.txt: {requirements_path}")

    venv_dir = backend_dir / "venv"
    venv_python = get_venv_python(backend_dir)

    if not venv_python.exists():
        print(f"[bootstrap] 创建虚拟环境: {venv_dir}", file=sys.stderr)
        run_checked([installer_python, "-m", "venv", str(venv_dir)], cwd=backend_dir)

    if not is_venv_ready(backend_dir):
        print("[bootstrap] 安装/修复后端依赖...", file=sys.stderr)
        run_checked(
            [str(venv_python), "-m", "pip", "install", "-r", str(requirements_path)],
            cwd=backend_dir,
        )
        get_install_stamp_path(backend_dir).write_text(
            requirements_digest(requirements_path),
            encoding="utf-8",
        )
    else:
        print("[bootstrap] 后端虚拟环境已就绪，跳过依赖安装", file=sys.stderr)

    return venv_python


def build_backend_launch_command(backend_dir: Path) -> str:
    venv_python = get_venv_python(backend_dir)
    return "cd {backend} && {python} -m uvicorn main:app --host 127.0.0.1 --port 15920 --reload".format(
        backend=shlex.quote(str(backend_dir)),
        python=shlex.quote(str(venv_python)),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare backend venv and print launch command.")
    parser.add_argument("--backend-dir", required=True, help="Path to backend directory")
    parser.add_argument("--installer-python", default=sys.executable, help="Python executable used to create the venv")
    args = parser.parse_args()

    backend_dir = Path(args.backend_dir).resolve()
    venv_python = ensure_backend_environment(backend_dir, installer_python=args.installer_python)
    if not venv_python.exists():
        raise FileNotFoundError(f"虚拟环境 Python 不存在: {venv_python}")

    print(build_backend_launch_command(backend_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
