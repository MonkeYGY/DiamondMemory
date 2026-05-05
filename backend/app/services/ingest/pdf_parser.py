import PyPDF2
import pdfplumber
import os
from typing import Any, Dict, List

from .doc_blocks import build_blocks_from_pages

class PDFParser:
    def __init__(self):
        pass
    
    def parse(self, file_path):
        """
        解析PDF文件，提取文本内容
        """
        pages: List[str] = []
        
        # 使用pdfplumber提取文本
        try:
            with pdfplumber.open(file_path) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text()
                    pages.append(page_text or "")
        except Exception as e:
            print(f"pdfplumber解析错误: {str(e)}")
        
        # 如果pdfplumber提取失败，尝试使用PyPDF2
        if not any(p.strip() for p in pages):
            try:
                with open(file_path, 'rb') as file:
                    reader = PyPDF2.PdfReader(file)
                    for page_num in range(len(reader.pages)):
                        page = reader.pages[page_num]
                        page_text = page.extract_text()
                        pages.append(page_text or "")
            except Exception as e:
                print(f"PyPDF2解析错误: {str(e)}")

        text = "\n".join([p for p in pages if p is not None]) + ("\n" if pages else "")
        blocks = build_blocks_from_pages(pages)
        
        return {
            "text": text,
            "metadata": {
                "file_name": os.path.basename(file_path),
                "file_size": os.path.getsize(file_path),
                "num_pages": len(pages),
            },
            "blocks": blocks,
        }
