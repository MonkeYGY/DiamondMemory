import os
import json
from app.config import settings

class HealthCheck:
    def __init__(self):
        pass

    def _get_dirs(self):
        knowledge_dir = os.path.join(settings.storage_path, "knowledge")
        processed_dir = os.path.join(settings.storage_path, "processed")
        return knowledge_dir, processed_dir
    
    def check_health(self):
        knowledge_dir, processed_dir = self._get_dirs()
        processed_files = len([f for f in os.listdir(processed_dir) if f.endswith(".json")]) if os.path.exists(processed_dir) else 0
        knowledge_files = len([f for f in os.listdir(knowledge_dir) if f.endswith(".json")]) if os.path.exists(knowledge_dir) else 0
        
        unprocessed_files = processed_files - knowledge_files
        
        corrupted_files = []
        if os.path.exists(knowledge_dir):
            for filename in os.listdir(knowledge_dir):
                if filename.endswith(".json"):
                    file_path = os.path.join(knowledge_dir, filename)
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            json.load(f)
                    except Exception:
                        corrupted_files.append(filename)
        
        health_report = {
            "total_processed_files": processed_files,
            "total_knowledge_files": knowledge_files,
            "unprocessed_files": unprocessed_files,
            "corrupted_files": corrupted_files,
            "health_score": self._calculate_health_score(processed_files, knowledge_files, len(corrupted_files))
        }
        
        return {
            "success": True,
            "health_report": health_report
        }
    
    def _calculate_health_score(self, processed_files, knowledge_files, corrupted_files):
        if processed_files == 0:
            return 100
        processing_rate = knowledge_files / processed_files
        integrity_rate = (knowledge_files - corrupted_files) / knowledge_files if knowledge_files > 0 else 1
        health_score = processing_rate * 0.6 + integrity_rate * 0.4
        return int(health_score * 100)
