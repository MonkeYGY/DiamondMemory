"""
Ollama 自动下载管理器
首次启动时自动检测平台并下载对应版本的 Ollama
"""
import os
import sys
import platform
import subprocess
import time
import logging
import threading
import hashlib
from pathlib import Path
from typing import Optional, Callable

import requests

logger = logging.getLogger(__name__)

DOWNLOAD_URLS = {
    ("Darwin", "x86_64"): "https://ollama.com/download/ollama-darwin",
    ("Darwin", "AMD64"): "https://ollama.com/download/ollama-darwin",
    ("Darwin", "arm64"): "https://ollama.com/download/ollama-darwin-arm64",
    ("Darwin", "aarch64"): "https://ollama.com/download/ollama-darwin-arm64",
    ("Windows", "AMD64"): "https://ollama.com/download/ollama-windows-amd64.exe",
    ("Windows", "x86_64"): "https://ollama.com/download/ollama-windows-amd64.exe",
}

DOWNLOAD_MIRRORS = {
    ("Darwin", "x86_64"): [
        "https://ollama.com/download/ollama-darwin",
        "https://github.com/ollama/ollama/releases/latest/download/ollama-darwin",
        "https://mirror.ghproxy.com/https://github.com/ollama/ollama/releases/latest/download/ollama-darwin",
        "https://gh-proxy.com/https://github.com/ollama/ollama/releases/latest/download/ollama-darwin",
    ],
    ("Darwin", "arm64"): [
        "https://ollama.com/download/ollama-darwin-arm64",
        "https://github.com/ollama/ollama/releases/latest/download/ollama-darwin-arm64",
        "https://mirror.ghproxy.com/https://github.com/ollama/ollama/releases/latest/download/ollama-darwin-arm64",
        "https://gh-proxy.com/https://github.com/ollama/ollama/releases/latest/download/ollama-darwin-arm64",
    ],
    ("Windows", "AMD64"): [
        "https://ollama.com/download/ollama-windows-amd64.exe",
        "https://github.com/ollama/ollama/releases/latest/download/ollama-windows-amd64.exe",
        "https://mirror.ghproxy.com/https://github.com/ollama/ollama/releases/latest/download/ollama-windows-amd64.exe",
        "https://gh-proxy.com/https://github.com/ollama/ollama/releases/latest/download/ollama-windows-amd64.exe",
    ],
    ("Windows", "x86_64"): [
        "https://ollama.com/download/ollama-windows-amd64.exe",
        "https://github.com/ollama/ollama/releases/latest/download/ollama-windows-amd64.exe",
        "https://mirror.ghproxy.com/https://github.com/ollama/ollama/releases/latest/download/ollama-windows-amd64.exe",
        "https://gh-proxy.com/https://github.com/ollama/ollama/releases/latest/download/ollama-windows-amd64.exe",
    ],
}


class OllamaDownloadService:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, install_dir: Optional[str] = None):
        if hasattr(self, '_initialized') and self._initialized:
            return
        self._initialized = True

        self.install_dir = Path(install_dir) if install_dir else self._get_default_install_dir()
        self.ollama_dir = self.install_dir / "ollama"
        self.ollama_path = self._resolve_ollama_path()
        self.model_dir = self.install_dir / "ollama-models"

        self._ensure_bundled_ollama()

        self._download_progress = {
            "status": "idle",
            "progress": 0,
            "downloaded": 0,
            "total": 0,
            "speed": "0 B/s",
            "error": None,
            "started_at": None,
            "finished_at": None,
        }
        self._download_thread: Optional[threading.Thread] = None
        self._cancel_flag = threading.Event()

    @classmethod
    def reset_instance(cls):
        cls._instance = None

    def _get_default_install_dir(self) -> Path:
        env_user_data_dir = (
            os.environ.get("DM_USER_DATA_DIR")
            or os.environ.get("DIAMOND_MEMORY_USER_DATA_DIR")
        )
        if env_user_data_dir and str(env_user_data_dir).strip():
            return Path(str(env_user_data_dir).strip())

        system = platform.system()
        if system == "Darwin":
            base = Path(os.environ.get("HOME", str(Path.home())))
            return base / "Library" / "Application Support" / "钻石记忆系统"
        elif system == "Windows":
            app_data = os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming"))
            return Path(app_data) / "钻石记忆系统"
        else:
            return Path.home() / ".diamondmemory"

    def _resolve_ollama_path(self) -> Path:
        system = platform.system()
        if system == "Windows":
            return self.ollama_dir / "ollama.exe"
        else:
            return self.ollama_dir / "ollama"

    def _get_platform_key(self) -> tuple:
        system = platform.system()
        machine = platform.machine()
        return (system, machine)

    def get_download_urls(self) -> list:
        platform_key = self._get_platform_key()
        urls = DOWNLOAD_MIRRORS.get(platform_key, [])
        if not urls:
            url = DOWNLOAD_URLS.get(platform_key)
            if url:
                urls = [url]
        return urls

    def _get_bundled_ollama_path(self) -> Optional[Path]:
        resources_path = os.environ.get("RESOURCE_PATH", "") or os.environ.get("ELECTRON_RESOURCES_PATH", "")
        if not resources_path:
            return None
        try:
            p = Path(resources_path) / "ollama" / ("ollama.exe" if platform.system() == "Windows" else "ollama")
            if p.exists() and p.stat().st_size > 0:
                return p
        except Exception:
            return None
        return None

    def is_installed(self) -> bool:
        try:
            self._ensure_bundled_ollama()
        except Exception:
            pass
        if self.ollama_path.exists() and os.access(self.ollama_path, os.X_OK if platform.system() != "Windows" else os.R_OK):
            return True
        bundled = self._get_bundled_ollama_path()
        if bundled is not None:
            return True
        return self._find_system_ollama() is not None

    def _find_system_ollama(self) -> Optional[str]:
        try:
            result = subprocess.run(
                ["which", "ollama"] if platform.system() != "Windows" else ["where", "ollama"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                found_path = result.stdout.strip().splitlines()[0].strip()
                if found_path and Path(found_path).exists():
                    logger.info("[OllamaDownload] 系统已安装 Ollama: %s", found_path)
                    return found_path
        except Exception:
            pass
        return None

    def _ensure_bundled_ollama(self):
        if self.ollama_path.exists() and self.ollama_path.stat().st_size > 0:
            return
        if self.ollama_path.exists() and self.ollama_path.stat().st_size == 0:
            try:
                self.ollama_path.unlink()
                logger.info("[OllamaDownload] 清理空壳 Ollama 文件: %s", self.ollama_path)
            except Exception:
                pass
        bundled_paths = []
        resources_path = os.environ.get("RESOURCE_PATH", "") or os.environ.get("ELECTRON_RESOURCES_PATH", "")
        if resources_path:
            bundled = Path(resources_path) / "ollama" / ("ollama.exe" if platform.system() == "Windows" else "ollama")
            if bundled.exists():
                bundled_paths.append(bundled)
        dev_bundled = Path(__file__).resolve().parents[3] / "build" / "ollama" / "mac" / "ollama"
        if dev_bundled.exists():
            bundled_paths.append(dev_bundled)
        for src in bundled_paths:
            try:
                self.ollama_dir.mkdir(parents=True, exist_ok=True)
                import shutil
                shutil.copy2(str(src), str(self.ollama_path))
                if platform.system() != "Windows":
                    self.ollama_path.chmod(0o755)
                logger.info("[OllamaDownload] 从内置路径部署 Ollama: %s -> %s", src, self.ollama_path)
                return
            except Exception as e:
                logger.warning("[OllamaDownload] 内置 Ollama 部署失败 (%s): %s", src, e)

    def is_ollama_running(self, ollama_url: str = "http://127.0.0.1:11434") -> bool:
        try:
            resp = requests.get(f"{ollama_url.rstrip('/')}/api/tags", timeout=3)
            return resp.status_code == 200
        except Exception:
            return False

    def get_install_status(self) -> dict:
        platform_key = self._get_platform_key()
        system_ollama = self._find_system_ollama()
        return {
            "platform": platform_key[0],
            "architecture": platform_key[1],
            "installed": self.is_installed(),
            "system_ollama": system_ollama,
            "ollama_path": str(self.ollama_path),
            "model_dir": str(self.model_dir),
            "download_urls": self.get_download_urls(),
            "download_progress": self._download_progress.copy(),
        }

    def get_download_progress(self) -> dict:
        return self._download_progress.copy()

    def download(self, progress_callback: Optional[Callable] = None, max_retries: int = 3) -> bool:
        if self.is_installed():
            logger.info("[OllamaDownload] Ollama 已安装: %s", self.ollama_path)
            self._download_progress = {
                "status": "completed",
                "progress": 100,
                "downloaded": 0,
                "total": 0,
                "speed": "",
                "error": None,
                "started_at": self._download_progress.get("started_at"),
                "finished_at": time.time(),
            }
            return True

        if self._download_progress.get("status") == "downloading":
            logger.info("[OllamaDownload] 下载已在进行中")
            return False

        urls = self.get_download_urls()
        if not urls:
            error_msg = f"不支持的平台: {platform.system()} {platform.machine()}"
            logger.error("[OllamaDownload] %s", error_msg)
            self._download_progress = {
                "status": "failed",
                "progress": 0,
                "downloaded": 0,
                "total": 0,
                "speed": "",
                "error": error_msg,
                "started_at": time.time(),
                "finished_at": time.time(),
            }
            return False

        self._cancel_flag.clear()
        self._download_progress = {
            "status": "downloading",
            "progress": 0,
            "downloaded": 0,
            "total": 0,
            "speed": "",
            "error": None,
            "started_at": time.time(),
            "finished_at": None,
        }

        self.ollama_dir.mkdir(parents=True, exist_ok=True)

        last_error = None
        for attempt in range(max_retries):
            if self._cancel_flag.is_set():
                self._download_progress["status"] = "cancelled"
                self._download_progress["finished_at"] = time.time()
                logger.info("[OllamaDownload] 下载已取消")
                return False

            for url_idx, url in enumerate(urls):
                if self._cancel_flag.is_set():
                    self._download_progress["status"] = "cancelled"
                    self._download_progress["finished_at"] = time.time()
                    return False

                logger.info("[OllamaDownload] 尝试下载 (第%d次, 源%d): %s", attempt + 1, url_idx + 1, url)
                success = self._do_download(url, progress_callback)
                if success:
                    return True
                if self._cancel_flag.is_set():
                    self._download_progress["status"] = "cancelled"
                    self._download_progress["finished_at"] = time.time()
                    return False

            last_error = self._download_progress.get("error", "未知错误")
        is_network_error = any(kw in str(last_error).lower() for kw in ["timeout", "connection", "connect", "refused", "resolve", "ssl"])
        if attempt < max_retries - 1:
            wait_time = 3 * (attempt + 1)
            logger.info("[OllamaDownload] 等待 %d 秒后重试...", wait_time)
            time.sleep(wait_time)

        self._download_progress["status"] = "failed"
        if is_network_error and platform.system() == "Darwin":
            self._download_progress["error"] = f"网络不可达（所有下载源均无法连接）: {last_error}\n\n建议：打开终端运行 brew install ollama 安装"
        else:
            self._download_progress["error"] = f"下载失败（重试{max_retries}次）: {last_error}"
        self._download_progress["finished_at"] = time.time()
        return False

    def _do_download(self, url: str, progress_callback: Optional[Callable] = None) -> bool:
        try:
            session = requests.Session()
            session.max_redirects = 10
            response = session.get(url, stream=True, timeout=(15, 600), allow_redirects=True)
            response.raise_for_status()

            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0
            start_time = time.time()
            last_speed_time = start_time
            last_speed_downloaded = 0

            temp_path = self.ollama_path.with_suffix('.download')

            with open(temp_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=65536):
                    if self._cancel_flag.is_set():
                        self._download_progress["status"] = "cancelled"
                        self._download_progress["finished_at"] = time.time()
                        if temp_path.exists():
                            temp_path.unlink()
                        return False

                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)

                        now = time.time()
                        elapsed_since_last = now - last_speed_time
                        if elapsed_since_last >= 0.5:
                            bytes_diff = downloaded - last_speed_downloaded
                            speed = bytes_diff / elapsed_since_last
                            self._download_progress["speed"] = self._format_size(speed) + "/s"
                            last_speed_time = now
                            last_speed_downloaded = downloaded

                        self._download_progress["downloaded"] = downloaded
                        self._download_progress["total"] = total_size

                        if total_size > 0:
                            progress = min(int(downloaded / total_size * 100), 99)
                            self._download_progress["progress"] = progress
                            if progress_callback:
                                try:
                                    progress_callback(progress, downloaded, total_size)
                                except Exception:
                                    pass
                        else:
                            self._download_progress["progress"] = -1
                            if progress_callback:
                                try:
                                    progress_callback(-1, downloaded, 0)
                                except Exception:
                                    pass

            if platform.system() != "Windows":
                temp_path.chmod(0o755)

            if self.ollama_path.exists():
                self.ollama_path.unlink()
            temp_path.rename(self.ollama_path)

            self._download_progress["progress"] = 100
            self._download_progress["downloaded"] = downloaded
            self._download_progress["total"] = total_size
            self._download_progress["speed"] = ""
            logger.info("[OllamaDownload] 下载完成: %s", self.ollama_path)
            return True

        except requests.exceptions.RequestException as e:
            error_msg = f"网络错误: {str(e)}"
            logger.error("[OllamaDownload] 下载失败: %s", error_msg)
            self._download_progress["error"] = error_msg
            temp_path = self.ollama_path.with_suffix('.download')
            if temp_path.exists():
                temp_path.unlink()
            return False
        except Exception as e:
            error_msg = f"下载异常: {str(e)}"
            logger.error("[OllamaDownload] %s", error_msg)
            self._download_progress["error"] = error_msg
            temp_path = self.ollama_path.with_suffix('.download')
            if temp_path.exists():
                temp_path.unlink()
            return False

    def start_download_async(self) -> dict:
        if self._download_progress.get("status") == "downloading":
            return {"status": "already_downloading", "message": "Ollama 正在下载中"}

        if self.is_installed():
            return {"status": "already_installed", "message": "Ollama 已安装"}

        def _download_thread():
            self.download()

        self._download_thread = threading.Thread(target=_download_thread, daemon=True)
        self._download_thread.start()

        return {"status": "started", "message": "Ollama 下载已启动"}

    def cancel_download(self) -> dict:
        if self._download_progress.get("status") != "downloading":
            return {"status": "not_downloading", "message": "当前没有正在进行的下载"}

        self._cancel_flag.set()
        return {"status": "cancelling", "message": "正在取消下载..."}

    def start_ollama(self, port: int = 11434) -> bool:
        if not self.is_installed():
            logger.error("[OllamaDownload] Ollama 未安装，无法启动")
            return False

        if self.is_ollama_running(f"http://127.0.0.1:{port}"):
            logger.info("[OllamaDownload] Ollama 已在运行")
            return True

        disable_autostart = str(os.environ.get("DM_DISABLE_OLLAMA_AUTOSTART", "")).lower() in ("1", "true", "yes")
        if disable_autostart:
            logger.info("[OllamaDownload] 托管模式已开启，禁止从后端直接启动 Ollama")
            return False

        self.model_dir.mkdir(parents=True, exist_ok=True)

        env = os.environ.copy()
        env["OLLAMA_MODELS"] = str(self.model_dir)
        env["OLLAMA_HOST"] = f"127.0.0.1:{port}"

        logger.info("[OllamaDownload] 启动 Ollama 服务: %s", self.ollama_path)
        logger.info("[OllamaDownload] 模型目录: %s", self.model_dir)

        try:
            if platform.system() == "Windows":
                subprocess.Popen(
                    [str(self.ollama_path), "serve"],
                    env=env,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS,
                )
            else:
                subprocess.Popen(
                    [str(self.ollama_path), "serve"],
                    env=env,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )

            return self._wait_for_ready(port, timeout=30)

        except Exception as e:
            logger.error("[OllamaDownload] 启动 Ollama 失败: %s", e)
            return False

    def _wait_for_ready(self, port: int, timeout: int = 30) -> bool:
        start_time = time.time()
        url = f"http://127.0.0.1:{port}/api/tags"

        while time.time() - start_time < timeout:
            try:
                resp = requests.get(url, timeout=2)
                if resp.status_code == 200:
                    logger.info("[OllamaDownload] Ollama 服务已就绪 (端口 %d)", port)
                    return True
            except Exception:
                pass
            time.sleep(1)

        logger.error("[OllamaDownload] Ollama 启动超时")
        return False

    def uninstall(self) -> dict:
        if self.ollama_dir.exists():
            import shutil
            shutil.rmtree(self.ollama_dir)
            logger.info("[OllamaDownload] 已卸载 Ollama: %s", self.ollama_dir)
            return {"status": "success", "message": "Ollama 已卸载"}
        return {"status": "not_installed", "message": "Ollama 未安装"}

    @staticmethod
    def _format_size(bytes_size: float) -> str:
        if bytes_size < 1024:
            return f"{bytes_size:.0f} B"
        elif bytes_size < 1024 * 1024:
            return f"{bytes_size / 1024:.1f} KB"
        elif bytes_size < 1024 * 1024 * 1024:
            return f"{bytes_size / 1024 / 1024:.1f} MB"
        else:
            return f"{bytes_size / 1024 / 1024 / 1024:.2f} GB"


ollama_download_service = OllamaDownloadService()
