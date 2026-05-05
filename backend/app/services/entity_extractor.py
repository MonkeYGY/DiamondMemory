"""实体提取服务模块"""
import re
from typing import List, Dict, Any


class EntityExtractor:
    """实体提取类"""
    
    def __init__(self):
        """初始化实体提取器"""
        # 实体类型正则表达式
        self.entity_patterns = {
            "person": r'(?:张|王|李|赵|刘|陈|杨|黄|周|吴|徐|孙|马|朱|胡|郭|林|何|高|罗|郑|梁|谢|宋|唐|韩|邓|冯|曹|彭|曾|肖|田|董|袁|潘|于|蒋|蔡|余|杜|叶|程|苏|魏|吕|丁|任|沈|姚|卢|姜|崔|钟|谭|陆|汪|范|廖|石|金|贾|夏|韦|付|方|邹|熊|白|孟|秦|邱|侯|江|尹|薛|闫|雷|龙|史|陶|贺|顾|毛|郝|龚|邵|万|钱|严|覃|武|戴|莫|孔|向|汤)[\u4e00-\u9fff]{1,3}|[A-Z][a-z]+(?:\s[A-Z][a-z]+)+',
            "organization": r'(?:公司|集团|大学|学院|研究院|研究所|医院|银行|基金|协会|中心|部门|局|厅|委|处|办|室)[\u4e00-\u9fff]*|(?:[\u4e00-\u9fff]{2,6})(?:公司|集团|大学|学院|研究院|研究所|医院|银行|基金|协会|中心)|[A-Z][a-z]+(?:\s[A-Z][a-z]+)*(?:\s(?:Inc|Corp|Ltd|LLC|Co))',
            "location": r'(?:省|市|区|县|镇|乡|村|路|街|道|巷|弄|号|楼|层|室|广场|公园|湖|山|河|海|江|岛|洲|国|州)[\u4e00-\u9fff]*|(?:[\u4e00-\u9fff]{2,6})(?:省|市|区|县|镇|路|街|道|广场|公园|湖|山|河|海|江|国|州)|[A-Z][a-z]+(?:\s[A-Z][a-z]+)*',
            "date": r'\d{4}-\d{2}-\d{2}|\d{2}/\d{2}/\d{4}|\d{8}',  # 日期
            "time": r'\d{2}:\d{2}(:\d{2})?',  # 时间
            "number": r'\d+(?:\.\d+)?',  # 数字
            "email": r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}',  # 邮箱
            "phone": r'1[3-9]\d{9}',  # 手机号
            "url": r'https?://[\w\-]+(\.[\w\-]+)+([\w\-.,@?^=%&:/~\+#]*[\w\-@?^=%&/~\+#])?',  # URL
        }
    
    def extract(self, text: str) -> List[Dict[str, Any]]:
        if getattr(__import__('app.config', fromlist=['settings']).settings, 'entity_extraction_enhanced', True):
            try:
                from app.services.enhanced_entity_extractor import enhanced_entity_extractor
                return enhanced_entity_extractor.extract(text)
            except Exception:
                pass

        entities = []
        seen = set()
        
        # 使用正则表达式提取实体
        for entity_type, pattern in self.entity_patterns.items():
            matches = re.finditer(pattern, text)
            for match in matches:
                entity_text = match.group()
                # 去重
                if entity_text not in seen:
                    seen.add(entity_text)
                    entities.append({
                        "text": entity_text,
                        "type": entity_type
                    })
        
        # 尝试使用NLTK进行更高级的实体识别（如果安装了）
        try:
            import nltk
            from nltk import ne_chunk, pos_tag, word_tokenize
            from nltk.tree import Tree
            
            # 下载必要的资源
            nltk.download('punkt', quiet=True)
            nltk.download('averaged_perceptron_tagger', quiet=True)
            nltk.download('maxent_ne_chunker', quiet=True)
            nltk.download('words', quiet=True)
            
            # 分词和词性标注
            tokens = word_tokenize(text)
            tagged = pos_tag(tokens)
            
            # 命名实体识别
            tree = ne_chunk(tagged)
            
            # 提取实体
            for subtree in tree:
                if isinstance(subtree, Tree):
                    entity_text = ' '.join([word for word, tag in subtree.leaves()])
                    entity_type = subtree.label()
                    # 去重
                    if entity_text not in seen:
                        seen.add(entity_text)
                        # 映射NLTK实体类型到自定义类型
                        mapped_type = self._map_nltk_type(entity_type)
                        entities.append({
                            "text": entity_text,
                            "type": mapped_type
                        })
        except Exception:
            # NLTK不可用，使用正则表达式结果
            pass
        
        return entities
    
    def _map_nltk_type(self, nltk_type: str) -> str:
        """映射NLTK实体类型到自定义类型"""
        mapping = {
            "PERSON": "person",
            "ORGANIZATION": "organization",
            "GPE": "location",  # 地缘政治实体
            "LOCATION": "location",
            "DATE": "date",
            "TIME": "time",
            "MONEY": "number",
            "PERCENT": "number",
            "CARDINAL": "number",
            "ORDINAL": "number"
        }
        return mapping.get(nltk_type, "other")
    
    def extract_with_confidence(self, text: str) -> List[Dict[str, Any]]:
        """提取实体并添加置信度
        
        Args:
            text: 要提取实体的文本
            
        Returns:
            实体列表，每个实体包含text、type和confidence字段
        """
        entities = self.extract(text)
        
        # 为每个实体添加置信度
        for entity in entities:
            # 简单的置信度计算：基于实体长度和类型
            confidence = 0.5  # 基础置信度
            
            # 实体长度越长，置信度越高
            entity_length = len(entity["text"])
            if entity_length > 5:
                confidence += 0.3
            elif entity_length > 2:
                confidence += 0.1
            
            # 某些类型的实体置信度更高
            high_confidence_types = ["email", "phone", "url", "date", "time"]
            if entity["type"] in high_confidence_types:
                confidence += 0.2
            
            # 确保置信度在0-1之间
            entity["confidence"] = min(confidence, 1.0)
        
        return entities


# 全局实体提取器实例
entity_extractor = EntityExtractor()
