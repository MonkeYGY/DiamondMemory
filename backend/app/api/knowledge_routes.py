"""知识库API路由"""
import logging
import os
from fastapi import APIRouter, HTTPException, Query, Body
from typing import List, Optional, Dict, Any
from app.services.knowledge_service import knowledge_service
from app.services.md_export_service import md_export_service
from app.services.task_queue_service import task_queue_service
from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


@router.get("/tree")
def get_file_tree(
    root_path: Optional[str] = Query(None),
    layer_filter: Optional[int] = Query(None),
    per_dir_limit: int = Query(500, ge=50, le=5000),
    max_depth: int = Query(20, ge=0, le=50),
    force_rescan: bool = Query(False),
):
    """获取知识库文件树结构"""
    try:
        # 安全：禁止将 root_path 指向知识库根目录之外（避免全盘扫描/越权读取）
        if root_path:
            base = os.path.abspath(settings.storage_path)
            rp = os.path.abspath(root_path)
            if not (rp.startswith(base + os.sep) or rp == base):
                raise HTTPException(status_code=400, detail="root_path 超出知识库范围")
        tree = knowledge_service.scan_file_tree(
            root_path=root_path,
            layer_filter=layer_filter,
            per_dir_limit=per_dir_limit,
            max_depth=max_depth,
            force_rescan=force_rescan,
        )
        return {
            "tree": tree,
            "total": len(tree),
            "meta": {"per_dir_limit": per_dir_limit, "max_depth": max_depth, "force_rescan": force_rescan},
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取文件树失败: {str(e)}")


@router.get("/tree/children")
def get_tree_children(
    dir_path: str = Query(..., description="相对于知识库根目录的目录路径"),
    root_path: Optional[str] = Query(None),
    layer_filter: Optional[int] = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(200, ge=1, le=5000),
    per_dir_limit: int = Query(500, ge=50, le=5000),
    max_depth: int = Query(20, ge=0, le=50),
    force_rescan: bool = Query(False),
):
    """分页获取某个目录的子项（用于大目录性能保护与“加载更多”）。"""
    try:
        if root_path:
            base = os.path.abspath(settings.storage_path)
            rp = os.path.abspath(root_path)
            if not (rp.startswith(base + os.sep) or rp == base):
                raise HTTPException(status_code=400, detail="root_path 超出知识库范围")
        return knowledge_service.scan_tree_children(
            root_path=root_path,
            dir_path=dir_path,
            offset=offset,
            limit=limit,
            layer_filter=layer_filter,
            per_dir_limit=per_dir_limit,
            max_depth=max_depth,
            force_rescan=force_rescan,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取目录子项失败: {str(e)}")


@router.get("/file")
def read_file(
    path: str = Query(...)
):
    """读取Markdown文件内容

    Args:
        path: 相对于知识库根目录的文件路径
    """
    normalized = (path or "").replace("\\", "/").lstrip("/")
    if not normalized or ".." in normalized.split("/") or os.path.isabs(path):
        raise HTTPException(status_code=400, detail="非法文件路径")
    try:
        result = knowledge_service.read_file(normalized)
        if not result:
            raise HTTPException(status_code=404, detail="文件不存在")
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"读取文件失败: {str(e)}")


@router.post("/note")
def create_note(
    title: str = Body(...),
    content: str = Body(...),
    category: Optional[str] = Body(None),
    tags: Optional[List[str]] = Body(None),
    source: str = Body("user")
):
    """用户手动创建笔记

    系统会自动调用大模型解析内容，生成合适的分类和标签，
    将笔记保存为Markdown文件，并存储到数据库供AI查询。
    """
    if not title or not title.strip():
        raise HTTPException(status_code=400, detail="笔记标题不能为空")
    if not content or not content.strip():
        raise HTTPException(status_code=400, detail="笔记内容不能为空")

    result = knowledge_service.create_note(
        title=title.strip(),
        content=content.strip(),
        category=category,
        tags=tags,
        source=source
    )

    if "error" in result:
        raise HTTPException(status_code=400, detail=result)

    return result


@router.put("/note")
def update_note(
    path: str = Body(...),
    title: str = Body(...),
    content: str = Body(...),
    category: Optional[str] = Body(None),
    tags: Optional[List[str]] = Body(None)
):
    """更新笔记内容"""
    if not path:
        raise HTTPException(status_code=400, detail="文件路径不能为空")

    result = knowledge_service.update_note(
        relative_path=path,
        title=title,
        content=content,
        category=category,
        tags=tags
    )

    if "error" in result:
        raise HTTPException(status_code=400, detail=result)

    return result


@router.put("/note/bypass_ai")
def toggle_bypass_ai(
    path: str = Body(...),
    bypass_ai: bool = Body(...)
):
    """切换免打扰AI状态"""
    if not path:
        raise HTTPException(status_code=400, detail="文件路径不能为空")
        
    result = knowledge_service.toggle_bypass_ai(path, bypass_ai)
    
    if "error" in result:
        raise HTTPException(status_code=400, detail=result)
        
    return result


@router.delete("/note")
def delete_note(
    path: str = Body(...)
):
    """删除笔记"""
    if not path:
        raise HTTPException(status_code=400, detail="文件路径不能为空")

    result = knowledge_service.delete_note(path)

    if "error" in result:
        raise HTTPException(status_code=400, detail=result)

    return result


@router.get("/search")
def search_notes(
    query: str = Query(...)
):
    """搜索知识库笔记"""
    if not query or not query.strip():
        raise HTTPException(status_code=400, detail="搜索词不能为空")

    results = knowledge_service.search_notes(query.strip())
    return {"results": results, "total": len(results)}


@router.get("/categories")
def get_l3_l5_categories():
    """获取L3(记忆总结)和L5(技能)的分类树"""
    try:
        tree = knowledge_service.get_l3_l5_tree()
        return tree
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取分类失败: {str(e)}")


@router.get("/category/files")
def get_category_files(
    category: str = Query(...),
    layer: int = Query(3, ge=3, le=5)
):
    """获取指定分类下的文件列表

    Args:
        category: 分类名称
        layer: 层级(3-记忆总结, 5-技能)
    """
    try:
        files = knowledge_service.get_category_files(category, layer)
        return {"files": files, "total": len(files)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取文件列表失败: {str(e)}")

@router.post("/sync")
def sync_knowledge_base():
    """手动触发“知识库同步”任务（异步，不阻塞 UI）。

    说明：
    - 最小可行：前端点击“同步知识库”后调用本接口
    - 接口职责：仅入队一个后台任务并返回 task_id
    - 真实扫描/摄取逻辑：由 task_queue worker 执行（type=knowledge_sync）
    """
    try:
        task_id = task_queue_service.enqueue(
            "knowledge_sync",
            requires_model=False,
            power_mode="normal",
            params={},
        )
        item = task_queue_service.store.get_task_queue_item(task_id) or {}
        return {"id": task_id, "status": item.get("status", "queued")}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"知识库同步失败: {str(e)}")


@router.post("/rebuild-memory-exports")
def rebuild_memory_exports():
    """按最新规则重建 L3-L6 到知识库的文件系统映射"""
    try:
        return md_export_service.rebuild_memory_exports()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"重建知识库导出失败: {str(e)}")


@router.get("/knowledge")
def get_all_knowledge():
    """获取所有知识库内容（前端兼容接口）"""
    try:
        all_files = knowledge_service.scan_file_tree(None, None)
        result = []
        
        file_list = all_files if isinstance(all_files, list) else all_files.get("tree", [])
        for file_info in file_list:
            try:
                content = knowledge_service.read_file(file_info.get("path", ""))
                if content:
                    result.append({
                        "id": content.get("path", ""),
                        "title": content.get("title", file_info.get("name", "无标题")),
                        "content": content.get("content", ""),
                        "tags": content.get("tags", []),
                        "category": content.get("category", ""),
                        "created_at": content.get("created_at", ""),
                        "type": content.get("type", "knowledge")
                    })
            except Exception:
                continue
        
        return result
    except Exception:
        return []
