"""兼容层 - 将旧 config.py 的常量映射到 settings

所有配置统一从 app.config.settings 获取，此文件仅做向后兼容。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.config.settings import settings

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = settings.data_directory
STORAGE_DIR = settings.storage_path
RAW_DIR = os.path.join(STORAGE_DIR, "raw")
PROCESSED_DIR = os.path.join(STORAGE_DIR, "processed")
KNOWLEDGE_DIR = os.path.join(STORAGE_DIR, "knowledge")
MODELS_DIR = os.path.join(DATA_DIR, "models")
INDEX_DIR = os.path.join(DATA_DIR, "index")
TEMP_DIR = os.path.join(DATA_DIR, "temp")

DATABASE_URL = "sqlite:///" + settings.database_path

API_HOST = settings.server_host
API_PORT = settings.server_port

LLM_MODEL_PATH = os.path.join(MODELS_DIR, "local_model.gguf")
LLM_CONTEXT_SIZE = settings.local_llm_max_tokens
LLM_TEMPERATURE = settings.local_llm_temperature

VECTOR_STORE_PATH = os.path.join(INDEX_DIR, "vector_store")
EMBEDDING_MODEL = settings.embedding_provider

for d in [RAW_DIR, PROCESSED_DIR, KNOWLEDGE_DIR, MODELS_DIR, INDEX_DIR, TEMP_DIR]:
    os.makedirs(d, exist_ok=True)
