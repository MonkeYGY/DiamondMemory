import os
import json
from app.config import settings

class MarkdownGenerator:
    def __init__(self):
        pass

    def _get_knowledge_dir(self):
        return os.path.join(settings.storage_path, "knowledge")
    
    def generate_markdown(self, file_id):
        knowledge_dir = self._get_knowledge_dir()
        knowledge_path = os.path.join(knowledge_dir, f"{file_id}.json")
        if not os.path.exists(knowledge_path):
            return {"success": False, "error": "知识文件不存在"}
        
        with open(knowledge_path, 'r', encoding='utf-8') as f:
            knowledge = json.load(f)
        
        markdown = []
        title = knowledge.get("metadata", {}).get("title", "Untitled")
        markdown.append(f"# {title}")
        markdown.append("")
        markdown.append("## 摘要")
        markdown.append(knowledge.get("summaries", {}).get("medium", ""))
        markdown.append("")
        markdown.append("## 关键概念")
        for concept_page in knowledge.get("concept_pages", []):
            markdown.append(f"### {concept_page['name']}")
            markdown.append(f"**类型:** {concept_page['type']}")
            markdown.append(concept_page['description'])
            if concept_page['related_concepts']:
                markdown.append(f"**相关概念:** {', '.join(concept_page['related_concepts'])}")
            markdown.append("")
        markdown.append("## 分类")
        markdown.append(f"**标签:** {', '.join(knowledge.get('classification', {}).get('tags', []))}")
        markdown.append("")
        markdown.append("## 关联关系")
        for relation in knowledge.get("relations", {}).get("relations", []):
            markdown.append(f"- {relation['source']} → {relation['relation']} → {relation['target']}")
        markdown.append("")
        markdown.append("## 元数据")
        metadata = knowledge.get("metadata", {})
        for key, value in metadata.items():
            if key != "text":
                markdown.append(f"- **{key}:** {value}")
        
        return {
            "success": True,
            "markdown": "\n".join(markdown),
            "file_id": file_id
        }
    
    def generate_batch_markdown(self, file_ids):
        results = []
        for file_id in file_ids:
            result = self.generate_markdown(file_id)
            results.append(result)
        
        return {
            "success": True,
            "results": results
        }
