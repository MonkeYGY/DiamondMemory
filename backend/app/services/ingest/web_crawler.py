import requests
from bs4 import BeautifulSoup
import re

class WebCrawler:
    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.3 Safari/605.1.15"
        }
    
    def crawl(self, url):
        """
        爬取网页内容，提取文本
        """
        try:
            response = requests.get(url, headers=self.headers, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # 提取标题
            title = soup.title.string if soup.title else "Untitled"
            
            # 移除脚本和样式
            for script in soup(["script", "style"]):
                script.decompose()
            
            # 提取正文
            text = soup.get_text(separator='\n', strip=True)
            
            # 清理文本
            text = re.sub(r'\n\s*\n', '\n\n', text)
            
            return {
                "text": text,
                "metadata": {
                    "url": url,
                    "title": title,
                    "status_code": response.status_code
                }
            }
        except Exception as e:
            return {
                "text": "",
                "metadata": {
                    "url": url,
                    "error": str(e)
                }
            }