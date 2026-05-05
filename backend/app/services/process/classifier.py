from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.cluster import KMeans
import numpy as np

class Classifier:
    def __init__(self, n_clusters=5):
        """
        初始化分类器
        """
        self.n_clusters = n_clusters
        self.vectorizer = TfidfVectorizer(stop_words='english')
        self.clusterer = KMeans(n_clusters=n_clusters, random_state=42)
    
    def classify(self, text):
        """
        对文本进行分类
        """
        # 预处理文本
        sentences = text.split('.')
        sentences = [s.strip() for s in sentences if s.strip()]
        
        if not sentences:
            return {"categories": [], "tags": []}
        
        # 向量化
        X = self.vectorizer.fit_transform(sentences)
        
        # 聚类
        clusters = self.clusterer.fit_predict(X)
        
        # 为每个聚类提取关键词
        categories = []
        for i in range(self.n_clusters):
            # 获取聚类中的句子
            cluster_sentences = [sentences[j] for j in range(len(sentences)) if clusters[j] == i]
            if cluster_sentences:
                # 提取聚类的关键词
                cluster_text = " ".join(cluster_sentences)
                keywords = self._extract_keywords(cluster_text, top_n=3)
                if keywords:
                    category = " ".join(keywords)
                    categories.append(category)
        
        # 提取标签
        tags = self._extract_keywords(text, top_n=10)
        
        return {
            "categories": categories,
            "tags": tags
        }
    
    def _extract_keywords(self, text, top_n=5):
        """
        提取文本关键词
        """
        # 向量化
        X = self.vectorizer.transform([text])
        
        # 获取特征名称
        feature_names = self.vectorizer.get_feature_names_out()
        
        # 获取词频
        word_freq = np.array(X.sum(axis=0)).flatten()
        
        # 排序并获取前N个
        sorted_indices = np.argsort(word_freq)[::-1]
        top_keywords = [feature_names[i] for i in sorted_indices[:top_n] if word_freq[i] > 0]
        
        return top_keywords