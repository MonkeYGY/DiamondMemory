import os
import uuid
import json
import shutil
import logging
import hashlib
from datetime import datetime
from app.config import settings

logger = logging.getLogger(__name__)


class IngestService:
    def __init__(self):
        pass

    def _ensure_parsers(self):
        if hasattr(self, '_parsers_loaded'):
            return
        try:
            from .pdf_parser import PDFParser
            from .doc_parser import DocParser
            from .excel_parser import ExcelParser
            from .web_crawler import WebCrawler
            from .video_processor import VideoProcessor
            self.pdf_parser = PDFParser()
            self.doc_parser = DocParser()
            self.excel_parser = ExcelParser()
            self.web_crawler = WebCrawler()
            temp_dir = os.path.join(settings.data_directory, "temp")
            os.makedirs(temp_dir, exist_ok=True)
            self.video_processor = VideoProcessor(temp_dir)
            self._parsers_loaded = True
        except ImportError as e:
            logger.warning("[Ingest] 文件解析依赖未安装: %s", e)
            raise

    def _extract_content(self, result):
        if not result:
            return ""
        return result.get("content", "") or result.get("text", "")

    def _sha256_file(self, path: str, chunk_size: int = 1024 * 1024) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                h.update(chunk)
        return h.hexdigest()

    def ingest_file(self, file_path, progress_callback=None, disturb_free: bool = False):
        self._ensure_parsers()
        file_ext = os.path.splitext(file_path)[1].lower()
        result = None
        doc_id = str(uuid.uuid4())
        file_name = os.path.basename(file_path)
        raw_dir = os.path.join(settings.storage_path, "raw")
        processed_dir = os.path.join(settings.storage_path, "processed")
        os.makedirs(raw_dir, exist_ok=True)
        os.makedirs(processed_dir, exist_ok=True)

        dest_path = os.path.join(raw_dir, f"{doc_id}_{file_name}")
        try:
            shutil.copy2(file_path, dest_path)
        except Exception as e:
            logger.error("[Ingest] 复制文件失败: %s", e)
            return {"success": False, "error": f"复制文件失败: {e}"}

        if progress_callback:
            progress_callback(20, "开始解析文件")

        if file_ext in ['.pdf']:
            result = self.pdf_parser.parse(dest_path)
        elif file_ext in ['.docx', '.doc']:
            result = self.doc_parser.parse(dest_path)
        elif file_ext in ['.xlsx', '.xls']:
            result = self.excel_parser.parse(dest_path)
        else:
            return {"success": False, "error": "不支持的文件类型"}

        if progress_callback:
            progress_callback(80, "解析完成，保存结果")

        processed_path = os.path.join(processed_dir, f"{doc_id}.json")
        with open(processed_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        try:
            from app.storage import SQLiteStore
            from app.storage.vector_store import get_vector_store
            from app.services.embedding_service import embedding_service
            from app.services.ingest.doc_blocks import compute_offsets

            store = SQLiteStore()
            vector_store = get_vector_store()

            source_mtime = os.path.getmtime(dest_path)
            source_hash = self._sha256_file(dest_path)
            content_text = self._extract_content(result)

            # ===== A：保真索引（doc 根记录 + doc_chunk 块记录）=====
            doc_meta = {
                "memory_type": "doc",
                "title": file_name,
                "file_ext": file_ext,
                "source_path": dest_path,
                "source_mtime": source_mtime,
                "source_hash": source_hash,
            }
            store.create(
                memory_id=doc_id,
                content=file_name,
                category="user_doc",
                layer=1,
                level=1,
                source="file",
                confidence=1.0,
                metadata=doc_meta,
                status="active",
                processed_status="processed",
                memory_type="doc",
                short_name=file_name[:8] if file_name else "doc",
            )

            try:
                emb = embedding_service.embed_text(file_name or "", doc_id)
                vector_store.save_embedding(
                    doc_id,
                    emb,
                    {
                        "category": "user_doc",
                        "layer": 1,
                        "level": 1,
                        "source": "file",
                        "tags": [],
                        "confidence": 1.0,
                        "status": "active",
                        "memory_type": "doc",
                    },
                )
                embedding_service.persist()
            except Exception:
                pass

            raw_blocks = result.get("blocks") or [{"text": content_text, "page": None, "chunk_index": 0}]
            blocks = compute_offsets(content_text, raw_blocks)

            chunk_ids = {}
            for b in blocks:
                chunk_id = str(uuid.uuid4())
                chunk_ids[b.get("chunk_index")] = chunk_id
                meta = {
                    "memory_type": "doc_chunk",
                    "doc_id": doc_id,
                    "source_path": dest_path,
                    "source_mtime": source_mtime,
                    "source_hash": source_hash,
                    "chunk_index": b.get("chunk_index"),
                    "page": b.get("page"),
                    "start_offset": b.get("start_offset"),
                    "end_offset": b.get("end_offset"),
                    "block_hash": b.get("block_hash"),
                }
                store.create(
                    memory_id=chunk_id,
                    content=b.get("text", ""),
                    category="user_doc",
                    layer=1,
                    level=1,
                    source="file",
                    confidence=1.0,
                    metadata=meta,
                    status="active",
                    processed_status="processed",
                    memory_type="doc_chunk",
                    short_name="chunk",
                )

                try:
                    emb = embedding_service.embed_text(b.get("text", ""), chunk_id)
                    vector_store.save_embedding(
                        chunk_id,
                        emb,
                        {
                            "category": "user_doc",
                            "layer": 1,
                            "level": 1,
                            "source": "file",
                            "tags": [],
                            "confidence": 1.0,
                            "status": "active",
                            "memory_type": "doc_chunk",
                            "doc_id": doc_id,
                        },
                    )
                except Exception:
                    pass

            try:
                embedding_service.persist()
            except Exception:
                pass

            # ===== B：结构化索引（免打扰时不生成）=====
            structured_id = None
            if not disturb_free:
                try:
                    from app.services.inference.inference_service import inference_service

                    blocks_for_prompt = []
                    for b in blocks[:50]:
                        blocks_for_prompt.append(
                            f"[chunk_index={b.get('chunk_index')}, page={b.get('page')}, offset={b.get('start_offset')}-{b.get('end_offset')}]\n{b.get('text','')}"
                        )

                    prompt = (
                        "请从以下用户文档中提炼结构化信息（要点/结论/流程/技能草案均可），并输出严格 JSON。\n"
                        "要求：\n"
                        "1) 必须包含 keypoints 数组（可为空）；\n"
                        "2) citations 数组用于引用原文片段，元素至少包含 chunk_index；\n"
                        "3) 除 JSON 外不要输出任何其他文字。\n\n"
                        "文档片段：\n"
                        + "\n\n".join(blocks_for_prompt)
                        + "\n\n请返回 JSON，格式示例：\n"
                        + '{\n  "keypoints": ["要点1"],\n  "citations": [{"chunk_index": 0}]\n}'
                    )

                    llm_out = inference_service.generate(prompt, model=settings.local_llm_model)
                    # 宽松提取 JSON 体
                    import re
                    import json as _json

                    m = re.search(r"\{.*\}", llm_out or "", re.DOTALL)
                    parsed = _json.loads(m.group()) if m else {"keypoints": [], "citations": []}
                except Exception:
                    parsed = {"keypoints": [], "citations": []}

                # citations：chunk_index -> chunk_id + offset/page
                citations = []
                try:
                    for c in (parsed.get("citations") or []):
                        idx = c.get("chunk_index")
                        if idx is None:
                            continue
                        cid = chunk_ids.get(idx)
                        b = next((x for x in blocks if x.get("chunk_index") == idx), None)
                        if not cid or not b:
                            continue
                        citations.append(
                            {
                                "chunk_id": cid,
                                "chunk_index": idx,
                                "page": b.get("page"),
                                "start_offset": b.get("start_offset"),
                                "end_offset": b.get("end_offset"),
                                "source_path": dest_path,
                                "doc_id": doc_id,
                            }
                        )
                except Exception:
                    citations = []

                structured_id = str(uuid.uuid4())
                structured_meta = {
                    "memory_type": "doc_structured",
                    "doc_id": doc_id,
                    "schema_version": 1,
                    "citations": citations,
                }
                store.create(
                    memory_id=structured_id,
                    content=json.dumps(parsed, ensure_ascii=False, indent=2),
                    category="user_doc",
                    layer=2,
                    level=1,
                    source="file",
                    confidence=1.0,
                    metadata=structured_meta,
                    status="active",
                    processed_status="processed",
                    memory_type="doc_structured",
                    short_name="struct",
                )

                try:
                    emb = embedding_service.embed_text(json.dumps(parsed, ensure_ascii=False), structured_id)
                    vector_store.save_embedding(
                        structured_id,
                        emb,
                        {
                            "category": "user_doc",
                            "layer": 2,
                            "level": 1,
                            "source": "file",
                            "tags": [],
                            "confidence": 1.0,
                            "status": "active",
                            "memory_type": "doc_structured",
                            "doc_id": doc_id,
                        },
                    )
                    embedding_service.persist()
                except Exception:
                    pass
        except Exception as e:
            logger.warning("[Ingest] 数据库保存失败: %s", e)

        if progress_callback:
            progress_callback(100, "摄取完成")

        return {
            "success": True,
            "doc_id": doc_id,
            "file_id": doc_id,
            "file_name": file_name,
            "processed_path": processed_path
        }

    def ingest_url(self, url, progress_callback=None):
        self._ensure_parsers()
        if progress_callback:
            progress_callback(20, "开始爬取网页")

        result = self.web_crawler.crawl(url)

        if progress_callback:
            progress_callback(80, "爬取完成，保存结果")

        file_id = str(uuid.uuid4())
        processed_dir = os.path.join(settings.storage_path, "processed")
        os.makedirs(processed_dir, exist_ok=True)
        processed_path = os.path.join(processed_dir, f"{file_id}.json")
        with open(processed_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        try:
            from app.storage import SQLiteStore
            from app.services.memory_service import memory_service
            store = SQLiteStore()
            content_text = self._extract_content(result)
            sn = memory_service.generate_short_name(content_text, 3, "web_ingest")
            store.create(
                memory_id=file_id,
                content=content_text,
                category="web_ingest",
                layer=3,
                level=1,
                source="url",
                confidence=1.0,
                metadata={"title": result.get("metadata", {}).get("title", "Untitled"), "type": "url", "url": url},
                status='active',
                processed_status='processed',
                short_name=sn
            )
        except Exception as e:
            logger.warning("[Ingest] 数据库保存失败: %s", e)

        if progress_callback:
            progress_callback(100, "摄取完成")

        return {
            "success": True,
            "file_id": file_id,
            "url": url,
            "processed_path": processed_path
        }

    def ingest_video(self, video_source, progress_callback=None):
        self._ensure_parsers()
        if progress_callback:
            progress_callback(20, "开始处理视频")

        result = self.video_processor.process(video_source)

        if progress_callback:
            progress_callback(80, "处理完成，保存结果")

        file_id = str(uuid.uuid4())
        processed_dir = os.path.join(settings.storage_path, "processed")
        os.makedirs(processed_dir, exist_ok=True)
        processed_path = os.path.join(processed_dir, f"{file_id}.json")
        with open(processed_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        try:
            from app.storage import SQLiteStore
            from app.services.memory_service import memory_service
            store = SQLiteStore()
            content_text = self._extract_content(result)
            sn = memory_service.generate_short_name(content_text, 3, "video_ingest")
            store.create(
                memory_id=file_id,
                content=content_text,
                category="video_ingest",
                layer=3,
                level=1,
                source="video",
                confidence=1.0,
                metadata={"title": os.path.basename(video_source), "type": "video"},
                status='active',
                processed_status='processed',
                short_name=sn
            )
        except Exception as e:
            logger.warning("[Ingest] 数据库保存失败: %s", e)

        if progress_callback:
            progress_callback(100, "摄取完成")

        return {
            "success": True,
            "file_id": file_id,
            "video_source": video_source,
            "processed_path": processed_path
        }


ingest_service = IngestService()
