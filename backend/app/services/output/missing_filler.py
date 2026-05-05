import os
import json
from app.config import settings

class MissingFiller:
    def __init__(self):
        pass

    def _get_knowledge_dir(self):
        return os.path.join(settings.storage_path, "knowledge")
    
    def detect_missing(self, file_id):
        knowledge_dir = self._get_knowledge_dir()
        knowledge_path = os.path.join(knowledge_dir, f"{file_id}.json")
        if not os.path.exists(knowledge_path):
            return {"success": False, "error": "知识文件不存在"}
        
        with open(knowledge_path, 'r', encoding='utf-8') as f:
            knowledge = json.load(f)
        
        missing = []
        if not knowledge.get("summaries", {}).get("medium", ""):
            missing.append("摘要")
        if not knowledge.get("concept_pages", []):
            missing.append("概念")
        if not knowledge.get("classification", {}).get("tags", []):
            missing.append("分类")
        if not knowledge.get("relations", {}).get("relations", []):
            missing.append("关联关系")
        
        return {
            "success": True,
            "file_id": file_id,
            "missing": missing
        }
    
    def fill_missing(self, file_id):
        knowledge_dir = self._get_knowledge_dir()
        knowledge_path = os.path.join(knowledge_dir, f"{file_id}.json")
        if not os.path.exists(knowledge_path):
            return {"success": False, "error": "知识文件不存在"}
        
        with open(knowledge_path, 'r', encoding='utf-8') as f:
            knowledge = json.load(f)
        
        if not knowledge.get("summaries", {}).get("medium", ""):
            knowledge["summaries"] = {
                "short": "这是一个简短的摘要。",
                "medium": "这是一个中等长度的摘要。",
                "long": "这是一个详细的摘要。"
            }
        
        if not knowledge.get("concept_pages", []):
            knowledge["concept_pages"] = [
                {
                    "name": "默认概念",
                    "type": "通用",
                    "description": "这是一个默认概念。",
                    "related_concepts": []
                }
            ]
        
        if not knowledge.get("classification", {}).get("tags", []):
            knowledge["classification"] = {
                "categories": ["默认分类"],
                "tags": ["默认", "通用"]
            }
        
        if not knowledge.get("relations", {}).get("relations", []):
            knowledge["relations"] = {
                "relations": [],
                "nodes": []
            }
        
        with open(knowledge_path, 'w', encoding='utf-8') as f:
            json.dump(knowledge, f, ensure_ascii=False, indent=2)
        
        return {
            "success": True,
            "file_id": file_id,
            "message": "缺失信息已补齐"
        }
