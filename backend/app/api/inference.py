from fastapi import APIRouter, HTTPException, Body
from fastapi.responses import StreamingResponse
from app.services.inference.model_manager import ModelManager
from app.services.inference.inference_service import InferenceService

router = APIRouter()

model_manager = ModelManager()
inference_service = InferenceService()

@router.get("/models")
async def list_models():
    """
    列出所有可用的模型
    """
    try:
        models = model_manager.list_models()
        return {"success": True, "models": models}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/models/download")
async def download_model(model_url: str, model_name: str):
    """
    下载模型
    """
    try:
        result = model_manager.download_model(model_url, model_name)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/models/{model_name}")
async def delete_model(model_name: str):
    """
    删除模型
    """
    try:
        result = model_manager.delete_model(model_name)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/models/{model_name}")
async def get_model_info(model_name: str):
    """
    获取模型信息
    """
    try:
        result = model_manager.get_model_info(model_name)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/generate")
async def generate_text(
    prompt: str = Body(..., description="生成文本的提示"),
    model_path: str = Body(None, description="模型路径"),
    max_tokens: int = Body(100, description="最大生成token数")
):
    """
    使用本地大模型生成文本
    """
    try:
        result = inference_service.generate_text(prompt, model_path, max_tokens)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/chat/stream")
async def chat_completion_stream(
    messages: list[dict] = Body(..., description="聊天消息列表"),
    model_path: str = Body(None, description="模型路径"),
    max_tokens: int = Body(2048, description="最大生成token数")
):
    """
    流式聊天完成功能（兼容Ollama前端解析格式）
    """
    try:
        generator = inference_service.chat_stream(messages, model_path, max_tokens)
        return StreamingResponse(generator, media_type="application/x-ndjson")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/chat")
async def chat_completion(
    messages: list[dict] = Body(..., description="聊天消息列表"),
    model_path: str = Body(None, description="模型路径"),
    max_tokens: int = Body(2048, description="最大生成token数")
):
    """
    聊天完成功能
    """
    try:
        result = inference_service.chat_completion(messages, model_path, max_tokens)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
