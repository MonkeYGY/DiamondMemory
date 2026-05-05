"""Ollama 自动下载管理 API 路由"""
import logging

from fastapi import APIRouter, Body

from app.services.ollama_download_service import ollama_download_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ollama", tags=["ollama"])


@router.get("/install-status")
def get_install_status():
    return ollama_download_service.get_install_status()


@router.post("/download")
def start_download():
    result = ollama_download_service.start_download_async()
    return result


@router.get("/download-progress")
def get_download_progress():
    return ollama_download_service.get_download_progress()


@router.post("/cancel-download")
def cancel_download():
    return ollama_download_service.cancel_download()


@router.post("/start")
def start_ollama(port: int = Body(11434, embed=True)):
    if not (1 <= port <= 65535):
        return {"status": "failed", "message": "端口号必须在 1-65535 范围内"}
    if port < 1024:
        return {"status": "failed", "message": "不允许使用特权端口（<1024）"}
    success = ollama_download_service.start_ollama(port)
    if success:
        return {"status": "success", "message": f"Ollama 服务已启动（端口 {port}）"}
    return {"status": "failed", "message": "Ollama 服务启动失败"}


@router.post("/uninstall")
def uninstall_ollama():
    return ollama_download_service.uninstall()
