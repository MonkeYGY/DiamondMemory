"""重排序服务模块

提供基于 Cross-Encoder 的精排服务，如果未安装依赖或模型加载失败，则自动回退到直通（无重排序）。
"""
import os
import logging
from typing import List, Dict, Any
from app.config import settings

logger = logging.getLogger(__name__)

class RerankerService:
    """基于 Cross-Encoder 的重排序服务"""
    
    def __init__(self):
        self.model = None
        self.is_available = False
        self.model_name = getattr(settings, "reranker_model", "BAAI/bge-reranker-v2-m3")
        
        # 确保使用国内镜像，防止超时阻塞
        os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
        
        self._initialize_model()
        
    def _initialize_model(self):
        """初始化重排序模型"""
        try:
            from sentence_transformers import CrossEncoder
            # 延迟加载，仅在实际实例化时尝试
            self.model = CrossEncoder(self.model_name, max_length=512)
            self.is_available = True
            logger.info(f"重排序模型 {self.model_name} 加载成功")
        except ImportError:
            logger.warning("未安装 sentence-transformers，跳过 Cross-Encoder 重排序初始化。如果需要精排功能，请运行: pip install sentence-transformers")
        except Exception as e:
            logger.warning(f"重排序模型初始化失败，将自动降级（这不会影响系统基本功能）: {e}")
            
    def rerank(self, query: str, documents: List[Dict[str, Any]], top_k: int = None) -> List[Dict[str, Any]]:
        """对候选文档进行精排
        
        Args:
            query: 查询字符串
            documents: 候选文档列表，每个文档必须是包含 content 字段的字典
            top_k: 返回的顶级文档数量，默认返回全部
            
        Returns:
            精排后的文档列表
        """
        if not documents:
            return []
            
        # 如果模型不可用，直接返回按原有分数排序的结果
        if not self.is_available or not self.model:
            if top_k is not None:
                return documents[:top_k]
            return documents
            
        try:
            # 准备输入：构建 (query, doc) 组
            pairs = []
            for doc in documents:
                content = doc.get("content", "")
                # 清理掉前缀（如果有），让 reranker 更关注实际内容
                clean_content = content.split("]：\n")[-1] if "]：\n" in content else content
                pairs.append((query, clean_content))
                
            # 批量预测分数
            scores = self.model.predict(pairs)
            
            # 将新分数赋给原文档，并保留旧的 final_score 作为备用参考
            for i, doc in enumerate(documents):
                doc["rerank_score"] = float(scores[i])
                # 融合策略：可以用 rerank_score 替换或与原 final_score 加权
                # 这里简单采用 rerank_score 作为新的排序依据
                doc["final_score"] = doc["rerank_score"]
                
            # 根据新的 final_score 降序排序
            reranked_docs = sorted(documents, key=lambda x: x.get("final_score", 0.0), reverse=True)
            
            if top_k is not None:
                return reranked_docs[:top_k]
                
            return reranked_docs
            
        except Exception as e:
            logger.error(f"重排序预测失败，降级返回原顺序: {e}")
            if top_k is not None:
                return documents[:top_k]
            return documents

# 全局单例
reranker_service = RerankerService()
