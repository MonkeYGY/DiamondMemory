"""存储配置API路由"""
import logging
import os
import json
import subprocess
import sys

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from app.config import settings
from app.config.settings import update_data_directory, update_storage_path
from app.storage import SQLiteStore

logger = logging.getLogger(__name__)

router = APIRouter()

class StorageConfigRequest(BaseModel):
    data_directory: str

class StorageConfigResponse(BaseModel):
    success: bool
    message: str
    current_path: Optional[str] = None

# 系统必需文件夹（不在UI显示，且设置为系统隐藏属性）
SYSTEM_FOLDERS = ['backups', 'qdrant_storage', 'temp']

# 系统必需文件（设置为系统隐藏属性）
SYSTEM_FILES = ['memory.db', 'storage_config.json', 'storage_config.js']


def _set_platform_hidden(path: str):
    """跨平台隐藏属性设置"""
    import sys
    try:
        if sys.platform == 'win32':
            # shell=True + list 在不同平台/版本行为不一致，且不必要；关闭 shell 更安全
            subprocess.run(['attrib', '+h', path], capture_output=True, text=True, timeout=10, shell=False)
        else:
            subprocess.run(['chflags', 'hidden', path], capture_output=True, text=True, timeout=10)
    except Exception as e:
        logger.debug("[StorageRoutes] 设置隐藏属性失败 %s: %s", path, e)


def _validate_storage_path(input_path: str) -> str:
    if not isinstance(input_path, str):
        raise HTTPException(status_code=400, detail="路径无效")
    p = input_path.strip()
    if not p or "\0" in p:
        raise HTTPException(status_code=400, detail="路径无效")
    if not os.path.isabs(p):
        raise HTTPException(status_code=400, detail="路径必须为绝对路径")

    resolved = os.path.abspath(p)
    # 禁止根目录：误配置会导致扫描/索引全盘，且可能造成误删风险
    root = os.path.abspath(os.path.splitdrive(resolved)[0] + os.sep) if sys.platform == "win32" else os.path.abspath(os.sep)
    if os.path.abspath(resolved) == root:
        raise HTTPException(status_code=400, detail="禁止将存储路径设置为磁盘根目录")
    return resolved


@router.post("/config", response_model=StorageConfigResponse)
def configure_storage(request: StorageConfigRequest):
    """配置存储路径"""
    try:
        path = _validate_storage_path(request.data_directory)

        if not os.path.exists(path):
            os.makedirs(path, exist_ok=True)

        if not os.access(path, os.R_OK | os.W_OK):
            raise HTTPException(status_code=400, detail="路径无读写权限")

        update_storage_path(path)

        store = SQLiteStore()
        store.set_config('knowledge_base_path', path, '知识库存储路径')

        user_dirs = [
            os.path.join(path, "总结经验"),
            os.path.join(path, "技能"),
            os.path.join(path, "用户文档"),
        ]
        for d in user_dirs:
            os.makedirs(d, exist_ok=True)

        return StorageConfigResponse(
            success=True,
            message="存储路径配置成功",
            current_path=path
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"配置存储路径失败: {str(e)}")

@router.get("/config", response_model=StorageConfigResponse)
def get_storage_config():
    """获取当前存储配置"""
    return StorageConfigResponse(
        success=True,
        message="获取成功",
        current_path=settings.storage_path
    )
