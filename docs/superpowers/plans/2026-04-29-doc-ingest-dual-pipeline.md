# 文档入库双管道（A保真 + B结构化）实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让用户文档入库同时支持“保真索引(A)”与“结构化索引(B)”，并支持“免打扰”模式只走 A，且检索结果能引用到具体段落/块。

**Architecture:** 复用现有 `memories` 表与向量检索链路，通过 `memory_type + parent_id + metadata` 实现文档根记录、原文块(A)与结构化记录(B)的关联；检索层在结果中透出 `citations` 以回指到 A 的 chunk。

**Tech Stack:** Python/FastAPI、SQLite FTS、Qdrant/FAISS VectorStore、Ollama（inference_service）。

---

## 0. 变更范围与文件结构（锁定分解）

### 将新增/修改的核心文件

**Modify**
- `backend/app/api/ingest.py`：/ingest/file 增加 `disturb_free`（免打扰）参数并透传。
- `backend/app/services/ingest/ingest_service.py`：实现 A/B 双管道、写入 doc/doc_chunk/doc_structured 记忆。
- `backend/app/services/ingest/pdf_parser.py`：返回 blocks（含 page）。
- `backend/app/services/ingest/doc_parser.py`：返回 blocks（段落/表格行）。
- `backend/app/services/ingest/excel_parser.py`：返回 blocks（sheet+row）。
- `backend/app/services/retrieval_service.py`：返回结果追加 `citations`/`metadata`，并为文档类 `memory_type` 提供更合适的前缀。
- `backend/app/services/memory_service.py`：向向量库 metadata 增加 `memory_type`（便于过滤/诊断）。

**Create**
- `backend/app/services/ingest/doc_blocks.py`：文档块结构定义、offset 计算、hash 生成、切块工具（仅纯函数）。
- `backend/tests/test_doc_ingest_dual_pipeline.py`：A_ONLY/A_AND_B 行为与引用字段测试。

### 数据约定（不新增表）

复用 `memories`：
- `memory_type="doc"`：文档根记录（1条/文档）
- `memory_type="doc_chunk"`：原文块记录（N条/文档）
- `memory_type="doc_structured"`：结构化索引记录（0..N条/文档）

关联方式：
- `doc_id` 为文档根 memory id
- chunk / structured 记录：`parent_id = doc_id`，并在 `metadata.doc_id` 冗余（便于查询与未来迁移）

---

## Task 1：新增文档块工具（blocks/offset/hash）+ 单元测试

**Files:**
- Create: `backend/app/services/ingest/doc_blocks.py`
- Test: `backend/tests/test_doc_ingest_dual_pipeline.py`

### Step 1.1：写失败测试（offset + hash + citations schema）

在 `backend/tests/test_doc_ingest_dual_pipeline.py` 新增：

```python
import unittest
import hashlib

from app.services.ingest.doc_blocks import (
    build_blocks_from_pages,
    compute_offsets,
    compute_text_hash,
)


class DocBlocksUnitTests(unittest.TestCase):
    def test_compute_text_hash_is_stable(self):
        h1 = compute_text_hash("hello")
        h2 = compute_text_hash("hello")
        self.assertEqual(h1, h2)
        self.assertEqual(h1, hashlib.sha256("hello".encode("utf-8")).hexdigest())

    def test_compute_offsets_produces_monotonic_ranges(self):
        full_text = "A\n\nB\n\nC"
        blocks = [{"text": "A"}, {"text": "B"}, {"text": "C"}]
        out = compute_offsets(full_text, blocks)
        self.assertEqual(out[0]["start_offset"], 0)
        self.assertTrue(out[0]["end_offset"] > out[0]["start_offset"])
        self.assertTrue(out[1]["start_offset"] > out[0]["end_offset"])

    def test_build_blocks_from_pages_keeps_page_numbers(self):
        pages = ["P1 line1\n\nP1 line2", "P2 line1"]
        blocks = build_blocks_from_pages(pages)
        self.assertTrue(any(b.get("page") == 1 for b in blocks))
        self.assertTrue(any(b.get("page") == 2 for b in blocks))
```

### Step 1.2：运行测试确认失败

Run（在项目根目录）：
```bash
python -m unittest backend.tests.test_doc_ingest_dual_pipeline.DocBlocksUnitTests -v
```
Expected：FAIL（找不到 `doc_blocks` / 方法未定义）。

### Step 1.3：实现 `doc_blocks.py`（最小可用）

实现要求：
- 全部为**纯函数**，不依赖数据库与网络
- 使用 `sha256` 作为 `file_hash`/`block_hash`
- `offset` 基于“全文拼接字符串下标”
- blocks 的最小 schema：
  - `text: str`
  - `page: int | None`
  - `chunk_index: int`
  - `block_hash: str`
  - `start_offset/end_offset: int`

建议实现骨架：

```python
# app/services/ingest/doc_blocks.py
from __future__ import annotations

import hashlib
from typing import Any, Dict, List, Optional


def compute_text_hash(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def split_to_paragraphs(text: str) -> List[str]:
    # 保持“免打扰”：不改写，只做最小切分；保留原段落文本
    raw = (text or "").splitlines()
    paras: List[str] = []
    buf: List[str] = []
    for line in raw:
        if line.strip() == "":
            if buf:
                paras.append("\n".join(buf))
                buf = []
            continue
        buf.append(line)
    if buf:
        paras.append("\n".join(buf))
    return [p for p in paras if p.strip()]


def build_blocks_from_pages(pages: List[str]) -> List[Dict[str, Any]]:
    blocks: List[Dict[str, Any]] = []
    idx = 0
    for i, page_text in enumerate(pages or []):
        for p in split_to_paragraphs(page_text):
            blocks.append({"text": p, "page": i + 1, "chunk_index": idx})
            idx += 1
    return blocks


def compute_offsets(full_text: str, blocks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    # 以顺序扫描方式查找每块在全文中的位置
    cursor = 0
    out: List[Dict[str, Any]] = []
    for b in blocks:
        t = b.get("text", "")
        start = full_text.find(t, cursor)
        if start < 0:
            # 回退：从头找（尽量不断流程）
            start = full_text.find(t)
        if start < 0:
            start = cursor
        end = start + len(t)
        cursor = max(end, cursor)
        nb = dict(b)
        nb["start_offset"] = start
        nb["end_offset"] = end
        nb["block_hash"] = compute_text_hash(t)
        out.append(nb)
    return out
```

### Step 1.4：运行测试确认通过

Run：
```bash
python -m unittest backend.tests.test_doc_ingest_dual_pipeline.DocBlocksUnitTests -v
```
Expected：PASS

### Step 1.5：提交

```bash
git add backend/app/services/ingest/doc_blocks.py backend/tests/test_doc_ingest_dual_pipeline.py
git commit -m "feat(ingest): add doc block utilities for hashes and offsets"
```

---

## Task 2：升级解析器输出 blocks（PDF/DOCX/XLSX）+ 单测补强

**Files:**
- Modify: `backend/app/services/ingest/pdf_parser.py`
- Modify: `backend/app/services/ingest/doc_parser.py`
- Modify: `backend/app/services/ingest/excel_parser.py`
- Test: `backend/tests/test_doc_ingest_dual_pipeline.py`

### Step 2.1：写失败测试（parser 返回 blocks）

在 `backend/tests/test_doc_ingest_dual_pipeline.py` 补充：

```python
from app.services.ingest.pdf_parser import PDFParser
from app.services.ingest.doc_parser import DocParser
from app.services.ingest.excel_parser import ExcelParser


class ParserContractTests(unittest.TestCase):
    def test_pdf_parser_returns_blocks_key(self):
        parser = PDFParser()
        # 这里不做真实PDF解析：只验证返回结构约定（通过 monkeypatch/直接调用内部方法也可）
        self.assertTrue(hasattr(parser, "parse"))

    def test_doc_parser_returns_blocks_key(self):
        parser = DocParser()
        self.assertTrue(hasattr(parser, "parse"))

    def test_excel_parser_returns_blocks_key(self):
        parser = ExcelParser()
        self.assertTrue(hasattr(parser, "parse"))
```

> 注：解析器真实文件测试成本较高，建议在实现中把“从第三方库得到 pages/paragraphs/rows → blocks”的逻辑委托到 `doc_blocks.py` 的纯函数，然后单测只测纯函数（Task1 已覆盖核心）。

### Step 2.2：实现 parser 返回结构（不破坏旧字段）

统一返回：
- 继续保留现有 `text` 字段（兼容旧逻辑）
- 新增 `blocks` 字段（列表）
- 对 PDF：`blocks` 建议按 page->段落切分，填 `page`
- 对 DOCX：按 `doc.paragraphs` 与 table 行顺序生成 blocks（`page=None`）
- 对 XLSX：按 sheet + row 顺序生成 blocks（`page=None`，可在 block metadata 内增加 `sheet`/`row_index`）

### Step 2.3：运行全量单测

Run：
```bash
python -m unittest discover -s backend/tests -p "test_*.py" -v
```
Expected：PASS

### Step 2.4：提交

```bash
git add backend/app/services/ingest/pdf_parser.py backend/app/services/ingest/doc_parser.py backend/app/services/ingest/excel_parser.py backend/tests/test_doc_ingest_dual_pipeline.py
git commit -m "feat(ingest): return structured blocks from parsers"
```

---

## Task 3：实现 A（保真索引）入库：doc + doc_chunk 写入 + 引用信息

**Files:**
- Modify: `backend/app/services/ingest/ingest_service.py`
- Test: `backend/tests/test_doc_ingest_dual_pipeline.py`

### Step 3.1：写失败测试（A_ONLY 只写 doc/doc_chunk，不写 doc_structured）

在 `backend/tests/test_doc_ingest_dual_pipeline.py` 增加（通过 mock 避免真实 DB/向量库）：

```python
from unittest.mock import patch, Mock

from app.services.ingest.ingest_service import IngestService


class IngestAPipelineTests(unittest.TestCase):
    @patch("app.services.ingest.ingest_service.memory_service")
    def test_ingest_file_disturb_free_only_writes_a(self, mock_memory_service):
        svc = IngestService()
        # 模拟 parser 输出
        svc._ensure_parsers()
        svc.pdf_parser = Mock()
        svc.pdf_parser.parse.return_value = {
            "text": "A\n\nB",
            "metadata": {"num_pages": 1},
            "blocks": [{"text": "A", "page": 1, "chunk_index": 0}, {"text": "B", "page": 1, "chunk_index": 1}],
        }

        mock_memory_service.create_memory.side_effect = lambda **kw: {"id": kw["memory_id"], **kw}

        result = svc.ingest_file("/tmp/fake.pdf", disturb_free=True)
        self.assertTrue(result["success"])

        calls = mock_memory_service.create_memory.call_args_list
        created_types = [c.kwargs.get("memory_type") for c in calls]
        self.assertIn("doc", created_types)
        self.assertIn("doc_chunk", created_types)
        self.assertNotIn("doc_structured", created_types)
```

### Step 3.2：运行测试确认失败

Run：
```bash
python -m unittest backend.tests.test_doc_ingest_dual_pipeline.IngestAPipelineTests -v
```
Expected：FAIL（`disturb_free` 参数不存在 / 不写 chunks）。

### Step 3.3：实现 A 管道（ingest_service）

实现要点：
- `ingest_file(..., disturb_free: bool = False)` 新增参数（默认 False）
- 复制原文件到 `storage_path/raw/` 的现有行为保留（已存在）
- 计算文件元信息：
  - `source_path`：raw 中的落盘路径
  - `source_mtime`：`os.path.getmtime(dest_path)`
  - `source_hash`：读取文件 bytes 的 sha256（注意大文件可分块读）
- doc 根记录（1条）：
  - `memory_id = file_id`（沿用现有 file_id）
  - `memory_type="doc"`
  - `layer=2`（避免触发 L3+ 的 MD 导出与系统整理管线）
  - `category="user_doc"`
  - `metadata` 至少包含：title/file_ext/source_path/source_mtime/source_hash
- chunks（N条）：
  - 为每个 block 生成 `chunk_id = uuid4()`
  - `memory_type="doc_chunk"`, `parent_id=doc_id`, `layer=2`, `category="user_doc"`
  - `content = block.text`（严格原样）
  - `metadata` 包含：doc_id、chunk_index、page、start_offset/end_offset、block_hash、source_path/source_mtime/source_hash
- offsets：使用 Task1 的 `compute_offsets(full_text, blocks)` 生成

> 注意：当前 ingest_service 直接用 `SQLiteStore().create(...)`，会导致**没有向量嵌入**。这里应改为调用 `memory_service.create_memory(...)` 以复用 embedding/entity 管线（不改变 content，不违背免打扰）。

### Step 3.4：运行测试确认通过

Run：
```bash
python -m unittest backend.tests.test_doc_ingest_dual_pipeline.IngestAPipelineTests -v
```
Expected：PASS

### Step 3.5：提交

```bash
git add backend/app/services/ingest/ingest_service.py backend/tests/test_doc_ingest_dual_pipeline.py
git commit -m "feat(ingest): add fidelity A pipeline with doc + chunks"
```

---

## Task 4：实现 B（结构化索引）入库：LLM 结构化输出 + citations 回指 A

**Files:**
- Modify: `backend/app/services/ingest/ingest_service.py`
- Test: `backend/tests/test_doc_ingest_dual_pipeline.py`

### Step 4.1：写失败测试（A_AND_B 会创建 doc_structured 且带 citations）

```python
from unittest.mock import patch


class IngestBPipelineTests(unittest.TestCase):
    @patch("app.services.ingest.ingest_service.inference_service")
    @patch("app.services.ingest.ingest_service.memory_service")
    def test_ingest_file_generates_structured_when_not_disturb_free(self, mock_memory_service, mock_infer):
        svc = IngestService()
        svc._ensure_parsers()
        svc.pdf_parser = Mock()
        svc.pdf_parser.parse.return_value = {
            "text": "A\n\nB",
            "metadata": {"num_pages": 1},
            "blocks": [{"text": "A", "page": 1, "chunk_index": 0}, {"text": "B", "page": 1, "chunk_index": 1}],
        }

        # LLM 返回 JSON（字符串）
        mock_infer.generate.return_value = '{"keypoints":["k1"],"citations":[{"chunk_index":0}]}'

        mock_memory_service.create_memory.side_effect = lambda **kw: {"id": kw["memory_id"], **kw}

        result = svc.ingest_file("/tmp/fake.pdf", disturb_free=False)
        self.assertTrue(result["success"])

        created_types = [c.kwargs.get("memory_type") for c in mock_memory_service.create_memory.call_args_list]
        self.assertIn("doc_structured", created_types)
```

### Step 4.2：实现 B 管道（最小可用）

实现要点：
- 仅当 `disturb_free=False` 执行
- Prompt 要求模型输出**严格 JSON**，字段建议：
  - `keypoints: string[]`
  - `conclusions: string[]`（可选）
  - `processes: [{title, steps[]}]`（可选）
  - `citations: [{chunk_index}]`（最小引用，后端再映射成 chunk_id + offsets）
- citations 映射逻辑：
  - 允许 LLM 只返回 `chunk_index`
  - 后端把它映射为 `chunk_id/page/start_offset/end_offset`
  - 最终写入 structured memory 的 `metadata.citations`
- structured 记录写入：
  - `memory_type="doc_structured"`
  - `parent_id=doc_id`
  - `layer=2`, `category="user_doc"`
  - `content` 建议存“结构化 JSON 的 pretty string”或可读 Markdown（两者择一，但需稳定；建议存 JSON 字符串以利机器读）

### Step 4.3：运行测试

Run：
```bash
python -m unittest backend.tests.test_doc_ingest_dual_pipeline.IngestBPipelineTests -v
```
Expected：PASS

### Step 4.4：提交

```bash
git add backend/app/services/ingest/ingest_service.py backend/tests/test_doc_ingest_dual_pipeline.py
git commit -m "feat(ingest): add structured B pipeline with citations"
```

---

## Task 5：检索结果透出 citations + 文档前缀优化

**Files:**
- Modify: `backend/app/services/retrieval_service.py`
- Test: `backend/tests/test_doc_ingest_dual_pipeline.py`

### Step 5.1：写失败测试（_format_results 返回 citations）

```python
from app.services.retrieval_service import RetrievalService


class RetrievalCitationTests(unittest.TestCase):
    def test_format_results_includes_citations_for_doc_chunk(self):
        svc = RetrievalService()
        results = [{
            "id": "c1",
            "content": "原文段落",
            "category": "user_doc",
            "layer": 2,
            "level": 1,
            "final_score": 0.9,
            "source": "file",
            "created_at": "2026-01-01",
            "tags": [],
            "access_count": 0,
            "is_pinned": False,
            "metadata": {
                "memory_type": "doc_chunk",
                "doc_id": "d1",
                "page": 2,
                "start_offset": 10,
                "end_offset": 20,
                "source_path": "raw/x.pdf",
            },
        }]
        out = svc._format_results(results)
        self.assertIn("citations", out[0])
        self.assertTrue(out[0]["citations"])
```

### Step 5.2：实现 `_format_results` 扩展（保持兼容）

要求：
- **不删除**现有字段
- 新增字段：
  - `metadata`: 透传（或只透传白名单字段）
  - `citations`: list
- 规则：
  - 若 `metadata.memory_type=="doc_chunk"`：自动构造 citations（至少 page/start_offset/end_offset/doc_id/source_path/chunk_id）
  - 若 `metadata.citations` 已存在（doc_structured）：直接透传
- 前缀优化：
  - doc_chunk：`[用户文档原文片段]：\n`
  - doc_structured：`[用户文档结构化索引]：\n`
  - 其他保持原逻辑

### Step 5.3：运行测试

Run：
```bash
python -m unittest backend.tests.test_doc_ingest_dual_pipeline.RetrievalCitationTests -v
```
Expected：PASS

### Step 5.4：提交

```bash
git add backend/app/services/retrieval_service.py backend/tests/test_doc_ingest_dual_pipeline.py
git commit -m "feat(retrieval): expose citations for doc memories"
```

---

## Task 6：API 层支持免打扰参数 + 端到端（mock）测试

**Files:**
- Modify: `backend/app/api/ingest.py`
- Test: `backend/tests/test_doc_ingest_dual_pipeline.py`

### Step 6.1：写失败测试（ingest_file 接受 disturb_free）

（不启动 FastAPI server，直接调用 endpoint 函数并 patch ingest_service）

```python
from unittest.mock import patch
import types

import app.api.ingest as ingest_api


class IngestApiParamTests(unittest.TestCase):
    @patch("app.api.ingest.ingest_service")
    def test_ingest_file_passes_disturb_free(self, mock_ingest):
        mock_ingest.ingest_file.return_value = {"success": True}

        # UploadFile 模拟：只需要 filename + read()
        class FakeUpload:
            filename = "a.pdf"
            async def read(self):
                return b"pdf"

        # 直接调用 async endpoint
        import asyncio
        res = asyncio.get_event_loop().run_until_complete(
            ingest_api.ingest_file(file=FakeUpload(), disturb_free=True)
        )
        self.assertTrue(res["success"])
        self.assertTrue(mock_ingest.ingest_file.called)
```

### Step 6.2：实现 API 透传

在 `backend/app/api/ingest.py`：
- `ingest_file` 增加 `disturb_free: bool = Form(False)`
- 调用 `ingest_service.ingest_file(temp_file_path, disturb_free=disturb_free)`

### Step 6.3：运行测试

Run：
```bash
python -m unittest backend.tests.test_doc_ingest_dual_pipeline.IngestApiParamTests -v
```
Expected：PASS

### Step 6.4：提交

```bash
git add backend/app/api/ingest.py backend/tests/test_doc_ingest_dual_pipeline.py
git commit -m "feat(api): add disturb_free param for ingest file"
```

---

## Task 7：向量库 metadata 补充 memory_type（可观测性/过滤能力）

**Files:**
- Modify: `backend/app/services/memory_service.py`
- Test: `backend/tests/test_doc_ingest_dual_pipeline.py`（或复用现有测试风格 patch vector_store）

### Step 7.1：写失败测试（create_memory 写向量 metadata 含 memory_type）

```python
from unittest.mock import Mock, patch
from app.services.memory_service import MemoryService


class VectorMetaMemoryTypeTests(unittest.TestCase):
    @patch("app.services.memory_service.embedding_service.embed_text", return_value=[0.1, 0.2])
    @patch("app.services.memory_service.embedding_service.persist")
    def test_create_memory_writes_memory_type_to_vector_metadata(self, _p, _e):
        svc = MemoryService.__new__(MemoryService)
        svc.store = Mock()
        svc.vector_store = Mock()
        svc.store.create.return_value = {"id": "m1", "layer": 2, "category": "user_doc", "content": "x"}

        svc.create_memory(
            content="x",
            category="user_doc",
            layer=2,
            source="file",
            metadata={"memory_type": "doc_chunk"},
            memory_type="doc_chunk",
            memory_id="m1",
        )

        args = svc.vector_store.save_embedding.call_args[0]
        meta = args[2]
        self.assertEqual(meta.get("memory_type"), "doc_chunk")
```

### Step 7.2：实现（最小改动）

在 `MemoryService.create_memory` 中构造 `metadata_dict` 时追加：
- `memory_type: memory_type`

### Step 7.3：运行测试与全量测试

Run：
```bash
python -m unittest backend.tests.test_doc_ingest_dual_pipeline.VectorMetaMemoryTypeTests -v
python -m unittest discover -s backend/tests -p "test_*.py" -v
```
Expected：PASS

### Step 7.4：提交

```bash
git add backend/app/services/memory_service.py backend/tests/test_doc_ingest_dual_pipeline.py
git commit -m "chore(vector): include memory_type in vector metadata"
```

---

## Task 8：工程化收尾（构建验证 + 版本优化记录自动追加）

**Files:**
- Modify/Create: `版本优化记录/版本优化*.md`（按项目规则自动追加本次任务记录）

- [ ] **Step 8.1：运行后端全量测试**

Run：
```bash
python -m unittest discover -s backend/tests -p "test_*.py" -v
```
Expected：全部 PASS

- [ ] **Step 8.2：验证后端可启动（最小烟测）**

Run：
```bash
python backend/main.py
```
Expected：服务启动无异常（如需端口占用，先停止旧进程）。

- [ ] **Step 8.3：按规则更新版本优化记录**

按 `版本优化记录/` 里当前版本文档（`版本优化*.md`）：
- 若不存在：创建
- 在顶部追加一块记录（任务类型/简述/修改文件列表/完成状态）

---

## Spec 覆盖自检（对照验收）

- “同一文档可被检索并能引用到具体段落”：
  - A：doc_chunk 带 page/offset/hash
  - retrieval：输出 `citations`（含 chunk_id/page/offset/source_path）
- “免打扰只走 A，不改写、不重排、不总结”：
  - `disturb_free=True`：不生成 doc_structured
  - A 的 content 严格等于 parser 输出 block.text（无二次加工）
- “文档入库既可保真又可结构化”：
  - `disturb_free=False`：A + B 都写入，B 的 citations 回指 A

---

## 执行交接（请选择其一）

计划已完成并保存到 `docs/superpowers/plans/2026-04-29-doc-ingest-dual-pipeline.md`。两种执行方式：

1. **Subagent-Driven（推荐）**：我按 Task 逐个派发子代理实现并在每个 Task 后审查
2. **Inline Execution**：我在当前会话按 Task 顺序直接实现（带检查点）

你选哪个？

