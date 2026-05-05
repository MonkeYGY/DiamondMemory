import os
import json
from app.config import settings

class QASystem:
    def __init__(self, model_name="distilbert-base-uncased-distilled-squad"):
        self.model_name = model_name
        self.qa_pipeline = None

    def _get_knowledge_dir(self):
        return os.path.join(settings.storage_path, "knowledge")
    
    def _load_model(self):
        if self.qa_pipeline is None:
            from transformers import pipeline
            self.qa_pipeline = pipeline("question-answering", model=self.model_name)
    
    def answer_question(self, question, context=None):
        if not context:
            context = self._retrieve_context(question)
        
        if not context:
            return {"answer": "抱歉，我没有找到相关信息。", "confidence": 0.0}
        
        self._load_model()
        result = self.qa_pipeline(question=question, context=context)
        
        return {
            "answer": result["answer"],
            "confidence": result["score"],
            "context": context
        }
    
    def _retrieve_context(self, question, top_k=3):
        knowledge_dir = self._get_knowledge_dir()
        relevant_content = []
        
        if not os.path.exists(knowledge_dir):
            return ""
        
        for filename in os.listdir(knowledge_dir):
            if filename.endswith(".json"):
                file_path = os.path.join(knowledge_dir, filename)
                with open(file_path, 'r', encoding='utf-8') as f:
                    knowledge = json.load(f)
                
                text = knowledge.get("metadata", {}).get("text", "")
                if not text:
                    text = knowledge.get("summaries", {}).get("long", "")
                
                if any(keyword.lower() in text.lower() for keyword in question.lower().split()):
                    relevant_content.append(text)
                    if len(relevant_content) >= top_k:
                        break
        
        return " ".join(relevant_content)
