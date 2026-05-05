from __future__ import annotations

import hashlib
from typing import Any, Dict, List


def compute_text_hash(text: str) -> str:
    """计算文本 sha256 哈希（用于文件/块稳定指纹）。"""
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def split_to_paragraphs(text: str) -> List[str]:
    """最小切分：按空行分段，保持段内原始换行。

    说明：为满足“免打扰”要求，此处不做改写/归一化，仅做分段。
    """
    raw_lines = (text or "").splitlines()
    paragraphs: List[str] = []
    buf: List[str] = []

    for line in raw_lines:
        if line.strip() == "":
            if buf:
                paragraphs.append("\n".join(buf))
                buf = []
            continue
        buf.append(line)

    if buf:
        paragraphs.append("\n".join(buf))

    return [p for p in paragraphs if p.strip()]


def build_blocks_from_pages(pages: List[str]) -> List[Dict[str, Any]]:
    """把分页文本构建为 block 列表（每个 block 视作“可引用最小单元”）。"""
    blocks: List[Dict[str, Any]] = []
    chunk_index = 0
    for i, page_text in enumerate(pages or []):
        for paragraph in split_to_paragraphs(page_text):
            blocks.append(
                {
                    "text": paragraph,
                    "page": i + 1,
                    "chunk_index": chunk_index,
                }
            )
            chunk_index += 1
    return blocks


def compute_offsets(full_text: str, blocks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """基于“全文拼接字符串下标”计算每个 block 的 offset 区间。

    采用顺序扫描 find（从上一个 block 的末尾开始找），以减少重复段落带来的歧义。
    找不到时做降级处理：从全文头部找；仍找不到则使用游标位置兜底，确保流程可继续。
    """
    cursor = 0
    out: List[Dict[str, Any]] = []
    full = full_text or ""

    for b in blocks or []:
        t = (b.get("text") or "")
        start = full.find(t, cursor) if t else cursor
        if start < 0:
            start = full.find(t) if t else cursor
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

