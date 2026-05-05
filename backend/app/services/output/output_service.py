from .qa_system import QASystem
from .markdown_generator import MarkdownGenerator
from .icon_generator import IconGenerator
from .health_check import HealthCheck
from .missing_filler import MissingFiller

class OutputService:
    def __init__(self):
        """
        初始化输出服务
        """
        self.qa_system = QASystem()
        self.markdown_generator = MarkdownGenerator()
        self.icon_generator = IconGenerator()
        self.health_check = HealthCheck()
        self.missing_filler = MissingFiller()
    
    def answer_question(self, question, context=None):
        """
        回答问题
        """
        return self.qa_system.answer_question(question, context)
    
    def generate_markdown(self, file_id):
        """
        生成Markdown
        """
        return self.markdown_generator.generate_markdown(file_id)
    
    def generate_batch_markdown(self, file_ids):
        """
        批量生成Markdown
        """
        return self.markdown_generator.generate_batch_markdown(file_ids)
    
    def generate_icon(self, concept_name):
        """
        生成图标
        """
        return self.icon_generator.generate_icon(concept_name)
    
    def generate_icons_for_concepts(self, file_id):
        """
        为概念生成图标
        """
        return self.icon_generator.generate_icons_for_concepts(file_id)
    
    def check_health(self):
        """
        检查健康状态
        """
        return self.health_check.check_health()
    
    def detect_missing(self, file_id):
        """
        检测缺失信息
        """
        return self.missing_filler.detect_missing(file_id)
    
    def fill_missing(self, file_id):
        """
        补齐缺失信息
        """
        return self.missing_filler.fill_missing(file_id)