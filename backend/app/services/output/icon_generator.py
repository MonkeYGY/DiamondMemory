import os
import json
from app.config import settings

class IconGenerator:
    def __init__(self):
        pass

    def _get_knowledge_dir(self):
        return os.path.join(settings.storage_path, "knowledge")
    
    def generate_icon(self, concept_name):
        prompt = f"简洁的图标，代表{concept_name}，扁平化设计，白色背景"
        image_url = self._generate_image(prompt)
        return {
            "success": True,
            "concept_name": concept_name,
            "image_url": image_url
        }
    
    def generate_icons_for_concepts(self, file_id):
        knowledge_dir = self._get_knowledge_dir()
        knowledge_path = os.path.join(knowledge_dir, f"{file_id}.json")
        if not os.path.exists(knowledge_path):
            return {"success": False, "error": "知识文件不存在"}
        
        with open(knowledge_path, 'r', encoding='utf-8') as f:
            knowledge = json.load(f)
        
        icons = []
        for concept_page in knowledge.get("concept_pages", []):
            icon = self.generate_icon(concept_page["name"])
            icons.append(icon)
        
        return {
            "success": True,
            "file_id": file_id,
            "icons": icons
        }
    
    def _generate_image(self, prompt):
        return f"https://via.placeholder.com/200?text={prompt.replace(' ', '+')}"
