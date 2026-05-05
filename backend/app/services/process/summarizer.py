from transformers import pipeline

class Summarizer:
    def __init__(self, model_name="facebook/bart-large-cnn"):
        """
        初始化摘要生成器
        """
        self.model_name = model_name
        self.summarizer = None
    
    def _load_model(self):
        """
        加载模型
        """
        if self.summarizer is None:
            self.summarizer = pipeline("summarization", model=self.model_name)
    
    def generate_summary(self, text, max_length=150, min_length=30):
        """
        生成文本摘要
        """
        try:
            # 加载模型
            self._load_model()
            
            # 处理长文本，分段生成摘要
            if len(text) > 1000:
                # 分段
                chunks = []
                chunk_size = 1000
                for i in range(0, len(text), chunk_size):
                    chunks.append(text[i:i+chunk_size])
                
                # 生成各段摘要
                chunk_summaries = []
                for chunk in chunks:
                    summary = self.summarizer(chunk, max_length=max_length, min_length=min_length, do_sample=False)[0]['summary_text']
                    chunk_summaries.append(summary)
                
                # 合并摘要
                combined_summary = " ".join(chunk_summaries)
                
                # 再次生成摘要，获得最终结果
                final_summary = self.summarizer(combined_summary, max_length=max_length, min_length=min_length, do_sample=False)[0]['summary_text']
                return final_summary
            else:
                # 直接生成摘要
                summary = self.summarizer(text, max_length=max_length, min_length=min_length, do_sample=False)[0]['summary_text']
                return summary
        except Exception as e:
            print(f"摘要生成错误: {str(e)}")
            return text[:200] + "..." if len(text) > 200 else text
    
    def generate_multilevel_summary(self, text):
        """
        生成多层次摘要
        """
        # 生成不同长度的摘要
        summaries = {
            "short": self.generate_summary(text, max_length=100, min_length=20),
            "medium": self.generate_summary(text, max_length=200, min_length=50),
            "long": self.generate_summary(text, max_length=300, min_length=100)
        }
        return summaries