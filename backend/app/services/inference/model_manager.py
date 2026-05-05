import os
import logging
import requests
from app.config import settings

logger = logging.getLogger(__name__)


class ModelManager:
    def __init__(self):
        self.models_dir = settings.data_directory
        os.makedirs(self.models_dir, exist_ok=True)
        self._ollama_url = settings.local_llm_endpoint.rstrip("/")

    def list_models(self):
        models = []
        try:
            resp = requests.get(f"{self._ollama_url}/api/tags", timeout=5)
            if resp.status_code == 200:
                for m in resp.json().get("models", []):
                    models.append({
                        "name": m.get("name", ""),
                        "path": "",
                        "size": m.get("size", 0),
                        "ollama": True,
                        "details": m.get("details", {}),
                    })
        except Exception as e:
            logger.warning(f"[ModelManager] 获取 Ollama 模型列表失败: {e}")
        return models

    def download_model(self, model_url, model_name):
        return {"success": False, "error": "请使用 Ollama 命令行或 API 下载模型: ollama pull " + model_name}

    def delete_model(self, model_name):
        return {"success": False, "error": "请使用 Ollama 命令行删除模型: ollama rm " + model_name}

    def get_model_info(self, model_name):
        try:
            resp = requests.get(f"{self._ollama_url}/api/show", json={"name": model_name}, timeout=5)
            if resp.status_code == 200:
                return {"success": True, "model": {"name": model_name, **resp.json()}}
        except Exception as e:
            logger.warning(f"[ModelManager] 获取模型信息失败: {e}")
        return {"success": False, "error": "模型不存在或无法访问"}
