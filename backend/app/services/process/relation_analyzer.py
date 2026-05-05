import spacy
import networkx as nx

class RelationAnalyzer:
    def __init__(self, model_name="en_core_web_sm"):
        """
        初始化关联分析器
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
    
    def analyze_relations(self, text):
        """
        分析文本中的关联关系
        """
        # 加载模型
        self._load_model()
        
        doc = self.nlp(text)
        
        # 构建关系图
        G = nx.DiGraph()
        
        # 提取主谓宾关系
        for sent in doc.sents:
            for token in sent:
                if token.dep_ == "ROOT":
                    # 找到主语和宾语
                    subject = None
                    object_ = None
                    
                    for child in token.children:
                        if child.dep_ in ["nsubj", "nsubjpass"]:
                            subject = child
                        elif child.dep_ in ["dobj", "pobj"]:
                            object_ = child
                    
                    if subject and object_:
                        # 添加节点和边
                        G.add_node(subject.text, pos=subject.pos_)
                        G.add_node(object_.text, pos=object_.pos_)
                        G.add_edge(subject.text, object_.text, relation=token.text)
        
        # 提取实体间的关系
        entities = list(doc.ents)
        for i, ent1 in enumerate(entities):
            for ent2 in entities[i+1:]:
                # 检查两个实体是否在同一个句子中
                if ent1.sent == ent2.sent:
                    # 添加节点和边
                    G.add_node(ent1.text, type=ent1.label_)
                    G.add_node(ent2.text, type=ent2.label_)
                    G.add_edge(ent1.text, ent2.text, relation="关联")
        
        # 转换为关系列表
        relations = []
        for u, v, data in G.edges(data=True):
            relations.append({
                "source": u,
                "target": v,
                "relation": data.get("relation", "关联")
            })
        
        return {
            "relations": relations,
            "nodes": [{"id": node, "attributes": G.nodes[node]} for node in G.nodes]
        }