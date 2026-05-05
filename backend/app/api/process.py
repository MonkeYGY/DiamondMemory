from fastapi import APIRouter, HTTPException, Query
from app.services.process.process_service import ProcessService

router = APIRouter()

# 初始化处理服务
process_service = ProcessService()

@router.post("/{file_id}")
async def process_content(file_id: str):
    """
    处理指定文件的内容
    """
    try:
        result = process_service.process_content(file_id)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/batch")
async def batch_process(file_ids: list[str] = Query(...)):
    """
    批量处理多个文件
    """
    try:
        result = process_service.batch_process(file_ids)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))