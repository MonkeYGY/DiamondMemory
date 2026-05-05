import os
import json
import uuid
from datetime import datetime
from app.config import settings

class ProcessService:
    def __init__(self):
        try:
            from .summarizer import Summarizer
            from .concept_extractor import ConceptExtractor
            from .classifier import Classifier
            from .relation_analyzer import RelationAnalyzer
            self.summarizer = Summarizer()
            self.concept_extractor = ConceptExtractor()
            self.classifier = Classifier()
            self.relation_analyzer = RelationAnalyzer()
        except ImportError:
            self.summarizer = None
            self.concept_extractor = None
            self.classifier = None
            self.relation_analyzer = None

    def _get_dirs(self):
        knowledge_dir = os.path.join(settings.storage_path, "knowledge")
        processed_dir = os.path.join(settings.storage_path, "processed")
        return processed_dir, knowledge_dir
    
    def process_content(self, file_id, progress_callback=None):
        if not self.summarizer:
            return {"success": False, "error": "处理组件未安装"}

        processed_dir, knowledge_dir = self._get_dirs()
        processed_path = os.path.join(processed_dir, f"{file_id}.json")
        if not os.path.exists(processed_path):
            return {"success": False, "error": "文件不存在"}
        
        with open(processed_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        text = data.get("text", "") or data.get("content", "")
        if not text:
            return {"success": False, "error": "文本内容为空"}
        
        if progress_callback:
            progress_callback(20, "开始生成摘要")
        
        summaries = self.summarizer.generate_multilevel_summary(text)
        
        if progress_callback:
            progress_callback(40, "提取关键概念")
        
        concepts = self.concept_extractor.extract_concepts(text)
        concept_pages = self.concept_extractor.create_concept_pages(concepts, text)
        
        if progress_callback:
            progress_callback(60, "进行分类")
        
        classification = self.classifier.classify(text)
        
        if progress_callback:
            progress_callback(80, "分析关联关系")
        
        relations = self.relation_analyzer.analyze_relations(text)
        
        if progress_callback:
            progress_callback(90, "保存处理结果")
        
        knowledge = {
            "file_id": file_id,
            "metadata": data.get("metadata", {}),
            "summaries": summaries,
            "concepts": concepts,
            "concept_pages": concept_pages,
            "classification": classification,
            "relations": relations,
            "processed_at": datetime.now().isoformat()
        }
        
        os.makedirs(knowledge_dir, exist_ok=True)
        knowledge_path = os.path.join(knowledge_dir, f"{file_id}.json")
        with open(knowledge_path, 'w', encoding='utf-8') as f:
            json.dump(knowledge, f, ensure_ascii=False, indent=2)
        
        if progress_callback:
            progress_callback(100, "处理完成")
        
        return {
            "success": True,
            "file_id": file_id,
            "knowledge_path": knowledge_path
        }
    
    def batch_process(self, file_ids, progress_callback=None):
        results = []
        total = len(file_ids)
        
        for i, file_id in enumerate(file_ids):
            if progress_callback:
                progress_callback(int((i / total) * 100), f"处理文件 {i+1}/{total}")
            
            result = self.process_content(file_id)
            results.append(result)
        
        return {
            "success": True,
            "results": results
        }

process_service = ProcessService()
