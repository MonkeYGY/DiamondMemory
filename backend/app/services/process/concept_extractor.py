import spacy
from collections import Counter

class ConceptExtractor:
    def __init__(self, model_name="en_core_web_sm"):
        """
        初始化概念提取器
        """
        self.model_name = model_name
        self.nlp = None
    
    def _load_model(self):
        """
        加载模型
        """
        if self.nlp is None:
            try:
                self.nlp = spacy.load(self.model_name)
            except:
                # 如果模型不存在，下载模型
                import subprocess
                subprocess.run(["python", "-m", "spacy", "download", self.model_name])
                self.nlp = spacy.load(self.model_name)
    
    def extract_concepts(self, text, top_n=10):
        """
        提取关键概念
        """
        # 加载模型
        self._load_model()
        
        doc = self.nlp(text)
        
        # 提取实体
        entities = []
        for ent in doc.ents:
            entities.append((ent.text, ent.label_))
        
        # 提取名词短语
        noun_phrases = []
        for chunk in doc.noun_chunks:
            noun_phrases.append(chunk.text)
        
        # 统计词频
        words = [token.text.lower() for token in doc if token.is_alpha and not token.is_stop]
        word_freq = Counter(words)
        top_words = word_freq.most_common(top_n)
        
        return {
            "entities": entities,
            "noun_phrases": noun_phrases,
            "top_words": top_words
        }
    
    def create_concept_pages(self, concepts, text):
        """
        为提取的概念创建概念页
        """
        concept_pages = []
        
        # 为每个实体创建概念页
        for entity, label in concepts["entities"][:5]:  # 只处理前5个实体
            concept_page = {
                "name": entity,
                "type": label,
                "description": self._generate_concept_description(entity, text),
                "related_concepts": self._find_related_concepts(entity, concepts["entities"])
            }
            concept_pages.append(concept_page)
        
        # 为高频词创建概念页
        for word, freq in concepts["top_words"][:5]:  # 只处理前5个高频词
            concept_page = {
                "name": word,
                "type": "高频词",
                "description": self._generate_concept_description(word, text),
                "related_concepts": []
            }
            concept_pages.append(concept_page)
        
        return concept_pages
    
    def _generate_concept_description(self, concept, text):
        """
        为概念生成描述
        """
        # 在文本中查找包含概念的句子
        sentences = text.split('.')
        related_sentences = []
        
        for sentence in sentences:
            if concept.lower() in sentence.lower():
                related_sentences.append(sentence.strip())
                if len(related_sentences) >= 3:
                    break
        
        if related_sentences:
            return " ".join(related_sentences) + "."
        else:
            return f"关于{concept}的信息。"
    
    def _find_related_concepts(self, concept, entities):
        """
        查找与概念相关的其他概念
        """
        related = []
        for entity, label in entities:
            if entity != concept and concept.lower() in entity.lower():
                related.append(entity)
        return related