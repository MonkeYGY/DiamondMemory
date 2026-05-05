import os
import json
import uuid
from datetime import datetime, timedelta
from app.config import settings

class InterfaceService:
    def __init__(self):
        self._api_keys = {}

    def _get_knowledge_dir(self):
        return os.path.join(settings.storage_path, "knowledge")
    
    def generate_api_key(self, permissions=None):
        if permissions is None:
            permissions = ["read", "write", "execute"]
        
        api_key = str(uuid.uuid4())
        self._api_keys[api_key] = {
            "permissions": permissions,
            "created_at": datetime.now().isoformat(),
            "expires_at": (datetime.now() + timedelta(days=365)).isoformat()
        }
        
        return {
            "success": True,
            "api_key": api_key,
            "permissions": permissions,
            "expires_at": (datetime.now() + timedelta(days=365)).isoformat()
        }
    
    def validate_api_key(self, api_key):
        key_info = self._api_keys.get(api_key)
        if not key_info:
            return {"valid": False, "error": "API密钥不存在"}
        
        if datetime.fromisoformat(key_info["expires_at"]) < datetime.now():
            return {"valid": False, "error": "API密钥已过期"}
        
        return {"valid": True, "permissions": key_info["permissions"]}
    
    def get_knowledge(self, api_key, file_id=None):
        validation = self.validate_api_key(api_key)
        if not validation["valid"]:
            return validation
        
        if "read" not in validation["permissions"]:
            return {"success": False, "error": "没有读取权限"}
        
        if file_id:
            from app.services.output.output_service import OutputService
            output_service = OutputService()
            result = output_service.generate_markdown(file_id)
            return result
        else:
            knowledge_dir = self._get_knowledge_dir()
            knowledge_files = []
            if os.path.exists(knowledge_dir):
                for filename in os.listdir(knowledge_dir):
                    if filename.endswith(".json"):
                        knowledge_files.append(filename.split(".")[0])
            
            return {
                "success": True,
                "knowledge_files": knowledge_files
            }
    
    def ask_question(self, api_key, question, context=None):
        validation = self.validate_api_key(api_key)
        if not validation["valid"]:
            return validation
        
        if "execute" not in validation["permissions"]:
            return {"success": False, "error": "没有执行权限"}
        
        from app.services.output.output_service import OutputService
        output_service = OutputService()
        result = output_service.answer_question(question, context)
        return result
    
    def ingest_content(self, api_key, content_type, content):
        validation = self.validate_api_key(api_key)
        if not validation["valid"]:
            return validation
        
        if "write" not in validation["permissions"]:
            return {"success": False, "error": "没有写入权限"}
        
        from app.services.ingest.ingest_service import ingest_service
        
        if content_type == "url":
            result = ingest_service.ingest_url(content)
        elif content_type == "text":
            result = {"success": False, "error": "文本摄取功能尚未实现"}
        else:
            result = {"success": False, "error": "不支持的内容类型"}
        
        return result
