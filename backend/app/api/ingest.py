from fastapi import APIRouter, UploadFile, File, Form, HTTPException
import os
import tempfile
import logging
from urllib.parse import urlparse
import ipaddress
import socket
from app.services.ingest.ingest_service import ingest_service

logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("/file")
async def ingest_file(file: UploadFile = File(...), disturb_free: bool = Form(False)):
    """
    摄取本地文件
    """
    temp_file_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file.filename)[1]) as temp_file:
            content = await file.read()
            temp_file.write(content)
            temp_file_path = temp_file.name
        
        result = ingest_service.ingest_file(temp_file_path, disturb_free=disturb_free)
        
        try:
            if temp_file_path:
                os.unlink(temp_file_path)
        except Exception:
            pass
        
        return result
    except Exception as e:
        try:
            if temp_file_path:
                os.unlink(temp_file_path)
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/url")
async def ingest_url(url: str = Form(...)):
    """
    摄取网页URL
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(status_code=400, detail="仅支持 HTTP/HTTPS URL")
    if not parsed.hostname:
        raise HTTPException(status_code=400, detail="URL 缺少 host")

    # SSRF 防护（基础版）：禁止访问本机/内网地址
    host = parsed.hostname.strip().lower()
    if host in ("localhost",):
        raise HTTPException(status_code=400, detail="禁止抓取本机地址")

    def _is_private_ip(ip: str) -> bool:
        try:
            addr = ipaddress.ip_address(ip)
            return bool(
                addr.is_private
                or addr.is_loopback
                or addr.is_link_local
                or addr.is_multicast
                or addr.is_reserved
                or addr.is_unspecified
            )
        except ValueError:
            return False

    # 1) host 是 IP 字面量：直接判断
    if _is_private_ip(host):
        raise HTTPException(status_code=400, detail="禁止抓取内网/本机地址")

    # 2) host 是域名：解析后判断（best-effort）
    try:
        for family, _type, _proto, _canon, sockaddr in socket.getaddrinfo(host, parsed.port or 80):
            ip = sockaddr[0]
            if _is_private_ip(ip):
                raise HTTPException(status_code=400, detail="禁止抓取内网/本机地址")
    except HTTPException:
        raise
    except Exception:
        # DNS 失败：交由下游处理（不在此处直接 500）
        pass
    try:
        result = ingest_service.ingest_url(url)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/video")
async def ingest_video(video_source: str = Form(...)):
    """
    摄取视频文件或URL
    """
    try:
        result = ingest_service.ingest_video(video_source)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
