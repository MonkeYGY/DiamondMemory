from fastapi import APIRouter, HTTPException, Query
from app.services.output.output_service import OutputService

router = APIRouter()

# 初始化输出服务
output_service = OutputService()

@router.post("/qa")
async def answer_question(question: str, context: str = None):
    """
    回答问题
    """
    try:
        result = output_service.answer_question(question, context)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/markdown/{file_id}")
async def generate_markdown(file_id: str):
    """
    生成Markdown
    """
    try:
        result = output_service.generate_markdown(file_id)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/markdown/batch")
async def batch_generate_markdown(file_ids: list[str] = Query(...)):
    """
    批量生成Markdown
    """
    try:
        result = output_service.generate_batch_markdown(file_ids)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/icon")
async def generate_icon(concept_name: str):
    """
    生成图标
    """
    try:
        result = output_service.generate_icon(concept_name)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/icons/{file_id}")
async def generate_icons(file_id: str):
    """
    为概念生成图标
    """
    try:
        result = output_service.generate_icons_for_concepts(file_id)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/health")
async def check_health():
    """
    检查健康状态
    """
    try:
        result = output_service.check_health()
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/missing/{file_id}")
async def detect_missing(file_id: str):
    """
    检测缺失信息
    """
    try:
        result = output_service.detect_missing(file_id)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/missing/{file_id}")
async def fill_missing(file_id: str):
    """
    补齐缺失信息
    """
    try:
        result = output_service.fill_missing(file_id)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))