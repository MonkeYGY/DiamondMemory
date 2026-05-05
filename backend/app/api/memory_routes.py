"""记忆管理API路由"""
import logging
import re
import threading
import time
from fastapi import APIRouter, HTTPException, Query, Body, BackgroundTasks
from typing import List, Optional, Dict, Any
from app.services.memory_service import memory_service
from app.services.retrieval_service import retrieval_service
from app.services.source_access_control import source_access_control
from app.services.memory_graph import memory_graph_service
from app.config import settings
from app.services.task_queue_service import task_queue_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/memory", tags=["memory"])

_organize_status = {
    "running": False,
    "started_at": None,
    "result": None,
    "error": None,
}
_organize_lock = threading.Lock()


_quick_organize_status = {"running": False, "started_at": None, "result": None, "error": None}
_quick_organize_lock = threading.Lock()

def start_quick_organize_task():
    """触发快速整理任务（如果当前没有正在运行的任务）"""
    with _quick_organize_lock:
        if _quick_organize_status["running"]:
            return False
        _quick_organize_status["running"] = True
        _quick_organize_status["started_at"] = time.time()
        _quick_organize_status["result"] = None
        _quick_organize_status["error"] = None
    
    # 延迟导入以避免循环依赖，或者假设 _run_quick_organize_background 在本文件中定义
    thread = threading.Thread(target=_run_quick_organize_background, daemon=True)
    thread.start()
    return True

@router.post("/create")
def create_memory(
    content: str = Body(...),
    category: Optional[str] = Body(None),
    tags: Optional[List[str]] = Body(None),
    source: Optional[str] = Body(None),
    confidence: float = Body(1.0),
    ttl: Optional[str] = Body(None),
    is_pinned: bool = Body(False),
    metadata: Optional[Dict[str, Any]] = Body(None),
    layer: Optional[int] = Body(None),
    short_name: Optional[str] = Body(None),
    disturb_free: bool = Body(False),
    background_tasks: BackgroundTasks = None
):
    """创建记忆"""
    if source_access_control.is_source_blocked(source):
        raise HTTPException(status_code=403, detail={
            "error": "SOURCE_BLOCKED",
            "message": f"来源 '{source}' 已被管理员禁止访问钻石记忆系统。请在钻石记忆系统设置中开启该AI软件的集成开关。"
        })
    if disturb_free:
        metadata = metadata or {}
        # 前端“免打扰”语义：保留原文排版，不触发自动整理等 AI 流程
        metadata["disturb_free"] = True

    result = memory_service.create_memory(
        content=content,
        category=category,
        tags=tags,
        source=source,
        confidence=confidence,
        ttl=ttl,
        is_pinned=is_pinned,
        metadata=metadata,
        layer=layer if layer is not None else 1,
        level=1,
        short_name=short_name
    )
    
    if "error" in result:
        raise HTTPException(status_code=400, detail=result)
        
    # 根据内容量自动触发整理 (8K 上下文规则，输入阈值约 5000)
    # 当 L1 待处理的字符数，或者 L2 待处理的字符数达到阈值时触发
    # 读取前端开关
    # (在实际生产中，更好的做法是通过全局配置获取，这里我们提供一个可选拦截)
    # 免打扰模式：不自动触发整理（仍会入库、可检索）
    if background_tasks and not disturb_free:
        try:
            pending_l1 = memory_service.store.get_by_layer_and_status(1, 'pending')
            pending_l2 = memory_service.store.get_by_layer_and_status(2, 'pending')
            
            l1_chars = sum(len(m.get('content', '')) for m in pending_l1)
            l2_chars = sum(len(m.get('content', '')) for m in pending_l2)
            
            # 如果任一层级的待处理字符数超过 4000 (给上下文留余量)，自动触发快速整理
            if l1_chars > 4000 or l2_chars > 4000:
                logger.info("[Auto-Organize] 触发阈值: L1=%d字符, L2=%d字符", l1_chars, l2_chars)
                background_tasks.add_task(start_quick_organize_task)
        except Exception as e:
            logger.warning("[Auto-Organize] 检查触发条件失败: %s", e)
    
    return result


@router.get("/get/{memory_id}")
def get_memory(memory_id: str):
    """获取记忆"""
    memory = memory_service.get_memory(memory_id)
    if not memory:
        raise HTTPException(status_code=404, detail="记忆不存在")
    return memory


@router.put("/update/{memory_id}")
def update_memory(
    memory_id: str,
    content: str = Body(...),
    reason: str = Body("")
):
    """更新记忆"""
    result = memory_service.update_memory(memory_id, content, reason)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result)
    if not result:
        raise HTTPException(status_code=404, detail="记忆不存在")
    return result


@router.delete("/delete/{memory_id}")
def delete_memory(memory_id: str):
    """删除记忆"""
    result = memory_service.delete_memory(memory_id)
    if isinstance(result, dict) and "error" in result:
        raise HTTPException(status_code=400, detail=result)
    if not result:
        raise HTTPException(status_code=404, detail="记忆不存在")
    return {"message": "记忆删除成功"}


@router.post("/pin/{memory_id}")
def pin_memory(memory_id: str):
    """标记为永久记忆"""
    result = memory_service.pin_memory(memory_id)
    if not result:
        raise HTTPException(status_code=404, detail="记忆不存在")
    return result


@router.post("/unpin/{memory_id}")
def unpin_memory(memory_id: str):
    """取消永久标记"""
    result = memory_service.unpin_memory(memory_id)
    if not result:
        raise HTTPException(status_code=404, detail="记忆不存在")
    return result


@router.get("/query")
def query_memory(
    query: str,
    categories: Optional[List[str]] = Query(None),
    limit: int = 10,
    source: Optional[str] = Query(None),
    include_history: bool = Query(False, description="仅管理/调试：允许召回历史版本（需开启 allow_history_query）"),
):
    """查询记忆"""
    if not query or not query.strip():
        raise HTTPException(status_code=400, detail="查询内容不能为空")
    if len(query) > 2000:
        raise HTTPException(status_code=400, detail="查询内容过长，最大2000字符")
    limit = min(limit, 100)
    if source_access_control.is_source_blocked(source):
        raise HTTPException(status_code=403, detail={
            "error": "SOURCE_BLOCKED",
            "message": f"来源 '{source}' 已被管理员禁止访问钻石记忆系统。请在钻石记忆系统设置中开启该AI软件的集成开关。"
        })
    effective_include_history = bool(include_history) and bool(getattr(settings, "allow_history_query", False))
    result = memory_service.query_memory(query, categories, limit, include_history=effective_include_history)
    return result


@router.get("/version_chain/{memory_id}")
def get_version_chain(
    memory_id: str,
    max_depth: int = Query(50, ge=1, le=200),
):
    """查询版本链（root -> ... -> latest）。仅管理/调试可用（allow_history_query）。"""
    if not bool(getattr(settings, "allow_history_query", False)):
        raise HTTPException(status_code=403, detail="历史版本查询未开启（allow_history_query=false）")
    chain = memory_service.get_version_chain(memory_id, max_depth=max_depth)
    return {"memory_id": memory_id, "chain": chain, "total": len(chain)}


@router.post("/set_status/{memory_id}")
def set_memory_status(
    memory_id: str,
    status: str = Body(..., embed=True),
    superseded_by: Optional[str] = Body(None),
    clear_invalid_fields: bool = Body(False),
):
    """切换有效状态（active/invalid/deleted）。仅管理/调试可用（allow_history_query）。"""
    if not bool(getattr(settings, "allow_history_query", False)):
        raise HTTPException(status_code=403, detail="状态切换未开启（allow_history_query=false）")
    if status not in ("active", "invalid", "deleted"):
        raise HTTPException(status_code=400, detail="status 必须为 active/invalid/deleted")
    ok = memory_service.set_memory_status(
        memory_id=memory_id,
        status=status,
        superseded_by=superseded_by,
        clear_invalid_fields=clear_invalid_fields,
    )
    if not ok:
        raise HTTPException(status_code=404, detail="记忆不存在或状态更新失败")
    return {"memory_id": memory_id, "status": status, "superseded_by": superseded_by}


@router.get("/list")
def list_memories(limit: int = 100):
    """列出所有记忆"""
    limit = min(limit, 5000)
    memories = memory_service.list_memories(limit)
    return {"memories": memories, "total": len(memories)}


@router.get("/search/keyword")
def search_by_keyword(
    keyword: str,
    limit: int = 20
):
    """按关键词搜索记忆"""
    results = memory_service.search_by_keyword(keyword, limit)
    return {"memories": results, "total": len(results)}


@router.get("/search/tags")
def search_by_tags(
    tags: List[str] = Query(...),
    limit: int = 10
):
    """按标签搜索记忆"""
    result = retrieval_service.search_by_tags(tags, limit)
    return result


@router.get("/search/recent")
def search_recent(
    days: int = 7,
    limit: int = 10,
    category: Optional[str] = None
):
    """搜索近期记忆"""
    result = retrieval_service.search_recent(days, limit, category)
    return result


@router.get("/memories")
def get_all_memories(limit: int = 1000):
    """获取所有记忆列表（前端兼容接口）"""
    limit = min(limit, 5000)
    memories = memory_service.list_memories(limit)
    return memories


@router.get("/memories/stats")
def get_memory_stats():
    """获取记忆统计数据（前端兼容接口）"""
    from datetime import datetime, timedelta
    
    all_memories = memory_service.list_memories(10000)
    
    today = datetime.now().date()
    today_count = 0
    l0_count = 0
    l1_count = 0
    l2_count = 0
    l3_count = 0
    l4_count = 0
    l5_count = 0
    l6_count = 0
    categories = set()
    
    for m in all_memories:
        created = m.get("created_at", "")
        if created:
            try:
                mem_date = datetime.fromisoformat(created).date()
                if mem_date == today:
                    today_count += 1
            except Exception:
                pass
        
        layer = m.get("layer", 0)
        if layer == 0: l0_count += 1
        elif layer == 1: l1_count += 1
        elif layer == 2: l2_count += 1
        elif layer == 3: l3_count += 1
        elif layer == 4: l4_count += 1
        elif layer == 5: l5_count += 1
        elif layer == 6: l6_count += 1
        
        cat = m.get("category")
        if cat:
            categories.add(cat)
    
    return {
        "totalMemories": len(all_memories),
        "todayCount": today_count,
        "categoryCount": len(categories),
        "systemStatus": "ok",
        "l0Count": l0_count,
        "l1Count": l1_count,
        "l2Count": l2_count,
        "l3Count": l3_count,
        "l4Count": l4_count,
        "l5Count": l5_count,
        "l6Count": l6_count
    }


def _run_organize_background():
    global _organize_status
    try:
        result = memory_service.organize_entire_knowledge_base()
        _organize_status["result"] = result
        _organize_status["error"] = None
    except Exception as e:
        _organize_status["result"] = None
        _organize_status["error"] = str(e)
    finally:
        _organize_status["running"] = False

def _run_quick_organize_background():
    global _quick_organize_status
    try:
        result = memory_service.quick_organize()
        _quick_organize_status["result"] = result
        _quick_organize_status["error"] = None
    except Exception as e:
        _quick_organize_status["result"] = None
        _quick_organize_status["error"] = str(e)
    finally:
        _quick_organize_status["running"] = False


@router.post("/organize")
def organize_memories():
    """手动触发记忆整理（后台异步执行）：L1→L2→L4→L3/L6→L5 全量整理"""
    # 兼容层：若已有 queued/running 的 deep_organize，则返回 already_running
    active = [
        t for t in (task_queue_service.store.list_task_queue_items(statuses=["queued", "running"], limit=50) or [])
        if t.get("type") == "deep_organize"
    ]
    if active:
        return {"status": "already_running", "message": "整理任务正在执行中"}

    task_queue_service.enqueue("deep_organize", requires_model=True)
    return {"status": "started", "message": "整理任务已加入后台任务队列"}


@router.get("/organize/status")
def get_organize_status():
    """查询整理任务状态"""
    # 兼容层：返回最近一次 deep_organize 任务
    items = task_queue_service.store.list_task_queue_items(
        statuses=["queued", "running", "paused", "blocked", "completed", "failed", "cancelled"],
        limit=50,
    )
    deep_tasks = [t for t in (items or []) if t.get("type") == "deep_organize"]
    latest = deep_tasks[0] if deep_tasks else None
    if not latest:
        return {"running": False, "started_at": None, "result": None, "error": None}
    running = latest.get("status") in ("queued", "running")
    started_at = latest.get("started_at") or latest.get("created_at")
    result = latest.get("result") if latest.get("status") == "completed" else None
    error = latest.get("error") if latest.get("status") == "failed" else None
    return {"running": running, "started_at": started_at, "result": result, "error": error}

@router.post("/organize/quick")
def quick_organize_memories():
    """快速整理：仅处理新增的pending记忆，增量处理"""
    active = [
        t for t in (task_queue_service.store.list_task_queue_items(statuses=["queued", "running"], limit=50) or [])
        if t.get("type") == "quick_organize"
    ]
    if active:
        return {"status": "already_running", "message": "快速整理任务正在执行中"}

    task_queue_service.enqueue("quick_organize", requires_model=True)
    return {"status": "started", "message": "快速整理任务已加入后台任务队列"}

@router.get("/organize/quick/status")
def get_quick_organize_status():
    """查询快速整理任务状态"""
    items = task_queue_service.store.list_task_queue_items(
        statuses=["queued", "running", "paused", "blocked", "completed", "failed", "cancelled"],
        limit=50,
    )
    quick_tasks = [t for t in (items or []) if t.get("type") == "quick_organize"]
    latest = quick_tasks[0] if quick_tasks else None
    if not latest:
        return {"running": False, "started_at": None, "result": None, "error": None}
    running = latest.get("status") in ("queued", "running")
    started_at = latest.get("started_at") or latest.get("created_at")
    result = latest.get("result") if latest.get("status") == "completed" else None
    error = latest.get("error") if latest.get("status") == "failed" else None
    return {"running": running, "started_at": started_at, "result": result, "error": error}


@router.post("/organize/deduplicate")
def deduplicate_memories():
    """仅执行去重整理：L1→L2"""
    try:
        result = memory_service.process_l1_to_l2(batch_size=50)
        return {"status": "success", "details": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/organize/deduplicate-l4")
def deduplicate_l4_memories():
    """仅执行 L4 经验总结的高相似自动归并"""
    try:
        result = memory_service.deduplicate_existing_l4()
        return {"status": "success", "details": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/organize/categorize-l4-to-l3")
def categorize_l4_to_l3():
    """L4归类得到L3：扫描所有L4记录，按category归类创建/更新L3分类"""
    try:
        result = memory_service.process_l4_to_l3()
        return {"status": "success", "details": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/organize/categorize-l6-to-l5")
def categorize_l6_to_l5():
    """L6归类得到L5：扫描所有L6记录，按category归类创建/更新L5分类"""
    try:
        result = memory_service.process_l6_to_l5()
        return {"status": "success", "details": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/organize/summarize")
def summarize_memories():
    """仅执行LLM归纳分类：L2→L4→L3/L6→L5"""
    try:
        l2_res = memory_service.process_l2_to_l4(max_chars=4000)
        l4_to_l3_res = memory_service.process_l4_to_l3()
        l4_res = memory_service.process_l4_to_l6(max_chars=3000)
        l6_to_l5_res = memory_service.process_l6_to_l5()
        return {
            "status": "success",
            "details": {
                "l2_to_l4": l2_res.get("processed", 0),
                "l4_to_l3": l4_to_l3_res.get("created", 0) + l4_to_l3_res.get("updated", 0),
                "l4_to_l6": l4_res.get("processed", 0),
                "l6_to_l5": l6_to_l5_res.get("created", 0) + l6_to_l5_res.get("updated", 0)
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/organize/normalize-categories")
def normalize_categories():
    """收敛明显近义的 L3/L5 分类，并迁移其下 L4/L6 内容"""
    try:
        return {
            "status": "success",
            "layer": "all",
            "l3": memory_service.normalize_similar_categories(3),
            "l5": memory_service.normalize_similar_categories(5),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/organize/categories/merge")
def merge_categories(
    layer: int | str = Body("all"),
    max_groups: int = Body(10),
):
    """按层级手动归并明显近义的 L3/L5 分类"""
    try:
        if layer == "all":
            return {
                "status": "success",
                "layer": "all",
                "l3": memory_service.normalize_similar_categories(3, max_groups=max_groups),
                "l5": memory_service.normalize_similar_categories(5, max_groups=max_groups),
            }

        target_layer = int(layer)
        if target_layer not in (3, 5):
            raise HTTPException(status_code=400, detail="layer 仅支持 3、5 或 all")

        return {
            "status": "success",
            "layer": target_layer,
            "result": memory_service.normalize_similar_categories(target_layer, max_groups=max_groups),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/graph")
def get_memory_graph(
    category: Optional[str] = Query(None),
    layer: Optional[int] = Query(None),
    limit: int = Query(200),
    max_entities: int = Query(80),
    force: bool = Query(False, description="强制重建图谱（忽略缓存）"),
):
    graph = memory_graph_service.build_graph(force=force)

    nodes = []
    edges = []
    node_index = {}

    memory_nodes = [n for n in graph.nodes() if graph.nodes[n].get("type") == "memory"]
    entity_nodes = [n for n in graph.nodes() if graph.nodes[n].get("type") == "entity"]

    filtered_memory_ids = set()
    for n in memory_nodes:
        attrs = graph.nodes[n]
        if category and attrs.get("category") != category:
            continue
        if layer and attrs.get("layer") != layer:
            continue
        filtered_memory_ids.add(n)

    entity_degree_list = []
    for n in entity_nodes:
        neighbors = list(graph.neighbors(n))
        if any(nb in filtered_memory_ids for nb in neighbors):
            entity_degree_list.append((n, graph.degree(n)))

    entity_degree_list.sort(key=lambda x: x[1], reverse=True)
    filtered_entity_ids = set(e[0] for e in entity_degree_list[:max_entities])

    all_filtered = filtered_memory_ids | filtered_entity_ids

    if len(filtered_memory_ids) > limit:
        sorted_memories = sorted(
            filtered_memory_ids,
            key=lambda n: graph.degree(n),
            reverse=True
        )
        filtered_memory_ids = set(sorted_memories[:limit])
        entity_degree_list = []
        for n in entity_nodes:
            neighbors = list(graph.neighbors(n))
            if any(nb in filtered_memory_ids for nb in neighbors):
                entity_degree_list.append((n, graph.degree(n)))
        entity_degree_list.sort(key=lambda x: x[1], reverse=True)
        filtered_entity_ids = set(e[0] for e in entity_degree_list[:max_entities])
        all_filtered = filtered_memory_ids | filtered_entity_ids

    for n in filtered_memory_ids:
        attrs = graph.nodes[n]
        mem = memory_service.store.get_by_id(n)
        content_preview = ""
        short_name_val = None
        if mem and mem.get("content"):
            short_name_val = mem.get("short_name")
            raw = mem["content"]
            layer = mem.get("layer", 0)
            if layer == 6:
                skill_m = re.search(r'技能名称[：:]\s*([^\n]+)', raw)
                if skill_m:
                    content_preview = skill_m.group(1).strip()
            elif layer == 4:
                topic_m = re.search(r'主题[：:]\s*([^\n]+)', raw)
                if topic_m:
                    content_preview = topic_m.group(1).strip()
            if not content_preview:
                for line in raw.split("\n"):
                    stripped = line.strip()
                    if not stripped or stripped.startswith("[") or stripped.startswith("（") or stripped.startswith("(") or stripped.startswith("#") or stripped.startswith("---") or stripped.startswith("**"):
                        continue
                    if re.match(r'^(主题|技能名称|核心要点|详细记录|目标任务|触发条件|包含步骤|涉及工具|最佳实践|依赖|注意事项)[：:]', stripped):
                        continue
                    content_preview = stripped[:60]
                    break
            if not content_preview:
                content_preview = raw[:60]

        node_data = {
            "id": n,
            "type": "memory",
            "category": attrs.get("category", ""),
            "layer": attrs.get("layer", 1),
            "content_preview": content_preview,
            "short_name": short_name_val or content_preview[:8],
            "degree": graph.degree(n),
        }
        if mem:
            node_data["created_at"] = mem.get("created_at", "")
            node_data["is_pinned"] = mem.get("is_pinned", False)
            node_data["tags"] = mem.get("tags", [])
        nodes.append(node_data)
        node_index[n] = len(nodes) - 1

    for n in filtered_entity_ids:
        attrs = graph.nodes[n]
        nodes.append({
            "id": n,
            "type": "entity",
            "entity_type": attrs.get("entity_type", ""),
            "text": attrs.get("text", ""),
            "degree": graph.degree(n),
        })
        node_index[n] = len(nodes) - 1

    for u, v in graph.edges():
        if u in node_index and v in node_index:
            edges.append({"source": u, "target": v})

    return {
        "nodes": nodes,
        "edges": edges,
        "stats": {
            "memory_count": len(filtered_memory_ids),
            "entity_count": len(filtered_entity_ids),
            "edge_count": len(edges),
        }
    }


@router.get("/graph/related/{memory_id}")
def get_related_memories(memory_id: str, max_depth: int = Query(2, le=5)):
    result = memory_graph_service.get_related_memories(memory_id, max_depth)
    return {"related": result, "total": len(result)}


@router.get("/graph/stats")
def get_graph_stats(force: bool = Query(False, description="强制重建图谱（忽略缓存）")):
    from app.services.memory_graph import memory_graph_service
    if force:
        memory_graph_service.build_graph(force=True)
    return memory_graph_service.get_graph_stats()


@router.get("/decay/stats")
def get_decay_stats():
    from app.services.memory_decay_service import memory_decay_service
    all_memories = memory_service.list_memories(10000)
    return memory_decay_service.get_decay_stats(all_memories)


@router.get("/cache/stats")
def get_cache_stats():
    from app.services.retrieval_cache_service import retrieval_cache_service
    return retrieval_cache_service.get_stats()


@router.post("/cache/clear")
def clear_cache():
    from app.services.retrieval_cache_service import retrieval_cache_service
    retrieval_cache_service.clear_all()
    return {"status": "cleared"}


@router.get("/adaptive/stats")
def get_adaptive_stats():
    from app.services.adaptive_organize_service import adaptive_organize_service
    return adaptive_organize_service.get_stats()


@router.get("/vector/stats")
def get_vector_stats():
    from app.storage import get_active_vector_store
    store = get_active_vector_store()
    return store.get_stats()


@router.post("/backfill-short-name")
def backfill_short_name():
    """为所有缺少 short_name 的记忆回填短名"""
    try:
        conn = memory_service.store._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT id, content, layer, category, short_name FROM memories WHERE short_name IS NULL OR short_name = ''")
        rows = cursor.fetchall()
        updated = 0
        for row in rows:
            mem_id, content, layer, category, _ = row
            sn = memory_service.generate_short_name(content or '', layer or 1, category)
            cursor.execute("UPDATE memories SET short_name = ? WHERE id = ?", (sn, mem_id))
            updated += 1
        conn.commit()
        return {"status": "ok", "updated": updated, "total_scanned": len(rows)}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.get("/mcp/tools")
def get_mcp_tools():
    from app.services.mcp_server_service import mcp_server_service
    return {"tools": mcp_server_service.get_tools_schema()}
