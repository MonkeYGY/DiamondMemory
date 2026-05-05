import logging
import requests
from app.config.settings import settings

logger = logging.getLogger(__name__)


class WebSearchService:
    def __init__(self):
        self.max_results = settings.web_search_max_results
        self.max_content_length = settings.web_search_max_content_length
        self.timeout = settings.web_search_timeout
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                          "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.3 Safari/605.1.15"
        }

    def search(self, query: str) -> dict:
        try:
            from ddgs import DDGS
        except ImportError:
            try:
                from duckduckgo_search import DDGS
            except ImportError:
                logger.warning("ddgs/duckduckgo-search 未安装，联网搜索不可用")
                return {"results": [], "context": "", "error": "联网搜索依赖未安装"}

        try:
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=self.max_results))
            if not results:
                return {"results": [], "context": ""}

            enriched = []
            for r in results:
                item = {
                    "title": r.get("title", ""),
                    "url": r.get("href", ""),
                    "snippet": r.get("body", ""),
                }
                if not item["snippet"] and not item["title"]:
                    continue
                content = self._fetch_page_content(item["url"])
                if content:
                    item["content"] = content[:self.max_content_length]
                enriched.append(item)

            context = self._build_context(enriched)
            return {"results": enriched, "context": context}
        except Exception as e:
            logger.warning(f"联网搜索失败: {e}")
            return {"results": [], "context": "", "error": str(e)}

    def _fetch_page_content(self, url: str) -> str:
        try:
            from bs4 import BeautifulSoup
            resp = requests.get(url, headers=self.headers, timeout=self.timeout)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.content, "html.parser")
            for tag in soup(["script", "style", "nav", "footer", "header"]):
                tag.decompose()
            text = soup.get_text(separator="\n", strip=True)
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            return "\n".join(lines)
        except Exception:
            return ""

    def _build_context(self, results: list) -> str:
        if not results:
            return ""
        parts = []
        for i, r in enumerate(results, 1):
            section = f"[{i}] {r['title']}\n来源: {r['url']}\n摘要: {r['snippet']}"
            if r.get("content"):
                section += f"\n内容: {r['content']}"
            parts.append(section)
        return "\n\n".join(parts)


web_search_service = WebSearchService()
