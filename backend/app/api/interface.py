from fastapi import APIRouter, HTTPException, Header
from app.services.interface.interface_service import InterfaceService

router = APIRouter()

interface_service = InterfaceService()

@router.post("/generate-key")
async def generate_api_key(permissions: list[str] = None):
    try:
        result = interface_service.generate_api_key(permissions)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/validate-key")
async def validate_api_key(api_key: str):
    try:
        result = interface_service.validate_api_key(api_key)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/knowledge/{file_id}")
async def get_knowledge(file_id: str, api_key: str = Header(...)):
    try:
        result = interface_service.get_knowledge(api_key, file_id)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/knowledge")
async def get_all_knowledge(api_key: str = Header(...)):
    try:
        result = interface_service.get_knowledge(api_key)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/ask")
async def ask_question(question: str, context: str = None, api_key: str = Header(...)):
    try:
        result = interface_service.ask_question(api_key, question, context)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/ingest")
async def ingest_content(content_type: str, content: str, api_key: str = Header(...)):
    try:
        result = interface_service.ingest_content(api_key, content_type, content)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))