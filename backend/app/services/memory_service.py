"""记忆管理服务模块

钻石记忆系统层级说明（增量更新架构）：
- L1: 原始数据层（AI软件全量记录，不去重，processed_status: pending->processed）
- L2: 沉淀层（L1去重得到，近似合并/无近似新增，processed_status: pending->summarized）
- L4: 总结记忆层（系统调用大模型整理L2内容合并总结得到，近似合并/无近似新增，processed_status: pending->skilled）
- L3: 分类层（L4层进行归类得到，目录层，类似文件夹）
- L6: 技能层（L4层进行技能提炼得到，近似合并/无近似新增）
- L5: 技能分类层（L6层进行归类得到，目录层，类似文件夹）

整理流程：
L1→L2: 去重（近似合并/无近似新增）
L2→L4: 大模型总结归纳（近似合并/无近似新增）
L4→L3: L4归类得到L3分类
L4→L6: 技能提炼（近似合并/无近似新增）
L6→L5: L6归类得到L5分类

增量更新原则：
- 新记忆与原有记忆近似 → 在原记忆中合并更新
- 原有记忆中无近似 → 直接新增

处理状态流转：
- L1写入: pending（待整理）
- L1->L2: processed（已整理）
- L2->L4: summarized（已总结）
- L4->L6: skilled（已提取技能）

时区说明：
- 所有时间戳统一使用Asia/Shanghai时区（北京时间，UTC+8）
"""
import uuid
import asyncio
import json
import re
import time
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any, Tuple
from app.storage import SQLiteStore
import app.storage as storage
from app.services.embedding_service import embedding_service
from app.services.category_normalization_service import category_normalization_service
from app.services.md_export_service import md_export_service
from app.services.memory_type_classifier import memory_type_classifier
from app.config import settings


class MemoryService:

    def __init__(self):
        self.store = SQLiteStore()
        self.vector_store = storage.get_active_vector_store()
        self.beijing_tz = timezone(timedelta(hours=8))
    
    def generate_short_name(self, content: str, layer: int = 1, category: str = None) -> str:
        if not content:
            return category or '未命名'
        if layer == 6:
            m = re.search(r'技能名称[：:]\s*([^\n]+)', content)
            if m:
                name = m.group(1).strip()
                return name[:8] if len(name) > 8 else name
        if layer == 4:
            m = re.search(r'主题[：:]\s*([^\n]+)', content)
            if m:
                name = m.group(1).strip()
                return name[:8] if len(name) > 8 else name
        if layer in [3, 5] and category:
            return category[:8] if len(category) > 8 else category
        for line in content.split('\n'):
            stripped = line.strip()
            if not stripped or stripped.startswith('#') or stripped.startswith('---') or stripped.startswith('**') or stripped.startswith('[') or stripped.startswith('（') or stripped.startswith('('):
                continue
            if re.match(r'^(主题|技能名称|核心要点|详细记录|目标任务|触发条件|包含步骤|涉及工具|最佳实践|依赖|注意事项)[：:]', stripped):
                name = re.sub(r'^(主题|技能名称|核心要点|详细记录|目标任务|触发条件|包含步骤|涉及工具|最佳实践|依赖|注意事项)[：:]\s*', '', stripped)
                return name[:8] if len(name) > 8 else name
            return stripped[:8] if len(stripped) > 8 else stripped
        if category:
            return category[:8] if len(category) > 8 else category
        return content[:8] if len(content) > 8 else content

    def create_memory(self, content: str, category: str = None, tags: List[str] = None, 
                     source: str = None, confidence: float = 1.0, ttl: str = None, 
                     is_pinned: bool = False, metadata: Dict[str, Any] = None, layer: int = 1, level: int = 1,
                     short_name: str = None) -> Dict[str, Any]:
        """创建记忆，L1层全量写入不去重，L2+层增量合并"""
        if len(content) > settings.max_content_length:
            return {"error": "CONTENT_TOO_LONG", "message": f"内容超过最大长度{settings.max_content_length}"}
        
        if tags and len(tags) > settings.max_tags:
            return {"error": "INVALID_TAGS", "message": f"标签数量超过上限{settings.max_tags}"}
        
        # L1层记录不进行去重检查，全量写入
        # L2/L4/L6：去重命中后不再“拒绝”，而是按类型决定 merge 或 supersede（版本链可追溯）
        superseded_old_id: Optional[str] = None
        supersede_meta: Dict[str, Any] = {}
        if layer >= 2:
            conflicts = self._check_conflicts(content, layer)
            if conflicts:
                top_conflict = conflicts[0]
                score = top_conflict.get("conflict_score", 0)
                dedup_threshold = getattr(settings, "dedup_threshold", 0.85)
                conflict_threshold = getattr(settings, "conflict_threshold", 0.75)

                # 纠错/事实更新优先 supersede（哪怕相似度较高）
                is_correction = self._looks_like_correction(content)
                if is_correction or (conflict_threshold <= score < dedup_threshold):
                    superseded_old_id = top_conflict["id"]
                    supersede_meta = {
                        "layer": layer,
                        "score": score,
                        "is_correction": is_correction,
                        "rule": "is_correction" if is_correction else "mid_similarity_supersede",
                    }
                elif score >= dedup_threshold:
                    # merge：更新同条内容 + 审计
                    existing_id = top_conflict["id"]
                    existing_content = top_conflict.get("content", "") or ""
                    merged_content = self._merge_incremental_content(existing_content, content, layer)
                    final_category = category if category is not None else top_conflict.get("category")
                    updated_sn = self.generate_short_name(merged_content, layer, final_category)

                    updated = self.store.update(
                        existing_id,
                        merged_content,
                        category=final_category,
                        reason=f"去重命中：增量合并(L{layer})",
                        short_name=updated_sn,
                    )

                    # 更新 embedding（保持检索一致性）
                    try:
                        update_corpus = getattr(embedding_service, "update_corpus", None)
                        if callable(update_corpus):
                            update_corpus(existing_id, merged_content)
                        embedding = embedding_service.embed_text(merged_content, existing_id)
                        old_meta = self.vector_store.get_metadata(existing_id) or {}
                        old_meta["category"] = final_category
                        old_meta["layer"] = layer
                        old_meta["status"] = "active"
                        old_emb = self.vector_store.get_embedding(existing_id)
                        if embedding or old_emb:
                            self.vector_store.save_embedding(existing_id, embedding or old_emb, old_meta)
                        embedding_service.persist()
                    except Exception as e:
                        print(f"合并后 embedding 更新失败: {e}")

                    # 审计日志（若数据库支持）
                    try:
                        add_audit_log = getattr(self.store, "add_audit_log", None)
                        if callable(add_audit_log):
                            add_audit_log(
                                memory_id=existing_id,
                                action="merge",
                                old_content=existing_content,
                                new_content=merged_content,
                                details={"layer": layer, "score": score, "strategy": "merge"},
                                action_type=f"L{layer}_dedup_merge",
                                source_ai=source,
                            )
                    except Exception as e:
                        print(f"审计日志写入失败: {e}")

                    if layer >= 3:
                        try:
                            from app.services.md_export_service import md_export_service
                            latest = self.store.get_by_id(existing_id)
                            if latest:
                                md_export_service.export_memory_to_md(latest)
                        except Exception as e:
                            print(f"合并后的记忆导出失败: {e}")

                    return {**(updated or top_conflict), "action": "merged"}
                else:
                    # score < conflict_threshold：视为无冲突，走正常新增
                    pass
        
        memory_id = str(uuid.uuid4())
        
        if is_pinned:
            layer = 5
            level = 5

        memory_type = metadata.get('memory_type', None) if metadata else None
        if not memory_type:
            try:
                memory_type = memory_type_classifier.classify(content, layer, category, metadata)
            except Exception:
                memory_type = "episodic"
        
        expires_at = None
        if ttl:
            days = self._parse_ttl(ttl)
            expires_at = (datetime.now(self.beijing_tz) + timedelta(days=days)).replace(tzinfo=None).isoformat()
        
        # 创建记忆，L1层默认为pending状态
        processed_status = 'pending' if layer == 1 else 'processed'
        
        if not short_name:
            short_name = self.generate_short_name(content, layer, category)
        
        result = self.store.create(
            memory_id=memory_id,
            content=content,
            category=category,
            layer=layer,
            level=level,
            tags=tags,
            source=source,
            confidence=confidence,
            expires_at=expires_at,
            is_pinned=is_pinned,
            metadata=metadata,
            status="active",
            processed_status=processed_status,
            parent_id=superseded_old_id,
            memory_type=memory_type,
            short_name=short_name
        )
        
        # 生成嵌入
        embedding = embedding_service.embed_text(content, memory_id)
        metadata_dict = {
            "category": category,
            "layer": layer,
            "level": level,
            "source": source,
            "tags": tags,
            "confidence": confidence,
            "status": "active",
            "memory_type": memory_type,
        }
        self.vector_store.save_embedding(memory_id, embedding, metadata_dict)
        
        # 提取实体
        from app.services.entity_extractor import entity_extractor
        entities = entity_extractor.extract(content)
        if entities:
            self._save_entities(memory_id, entities)
            
        # 如果这是更新替代了旧记忆，则废止旧记忆（时序图谱逻辑）
        if superseded_old_id:
            self.store.invalidate_memory(superseded_old_id, memory_id)
            try:
                add_audit_log = getattr(self.store, "add_audit_log", None)
                if callable(add_audit_log):
                    details_old = {
                        **(supersede_meta or {}),
                        "strategy": "supersede",
                        "superseded_by": memory_id,
                    }
                    details_new = {
                        **(supersede_meta or {}),
                        "strategy": "supersede",
                        "supersedes": superseded_old_id,
                    }
                    add_audit_log(
                        memory_id=superseded_old_id,
                        action="superseded",
                        old_content=(self.store.get_by_id(superseded_old_id) or {}).get("content", ""),
                        new_content=content,
                        details=details_old,
                        action_type=f"L{layer}_dedup_supersede",
                        source_ai=source,
                    )
                    add_audit_log(
                        memory_id=memory_id,
                        action="supersede_create",
                        old_content=(self.store.get_by_id(superseded_old_id) or {}).get("content", ""),
                        new_content=content,
                        details=details_new,
                        action_type=f"L{layer}_dedup_supersede",
                        source_ai=source,
                    )
            except Exception as e:
                print(f"supersede 审计日志写入失败: {e}")
            # 可以选择从向量库中删除旧记忆或保留它，取决于检索策略
            # 此处保留在向量库中，但其 status 变为 invalid，在检索过滤时会被忽略
            # 如果使用 Qdrant 等，可能需要更新 metadata status
            old_meta = self.vector_store.get_metadata(superseded_old_id)
            if old_meta:
                old_meta["status"] = "invalid"
                old_emb = self.vector_store.get_embedding(superseded_old_id)
                if old_emb:
                    self.vector_store.save_embedding(superseded_old_id, old_emb, old_meta)
        
        # 持久化
        embedding_service.persist()
        
        # L3-L6层记忆实时导出为MD文件
        if layer >= 3:
            try:
                from app.services.md_export_service import md_export_service
                result_with_path = md_export_service.export_memory_to_md(result)
                result['file_path'] = result_with_path
            except Exception as e:
                print(f"MD文件导出失败: {e}")
        
        # L3/L5层自动创建子分类逻辑
        if layer in [3, 5] and category:
            try:
                self._auto_create_subcategory(memory_id, content, category, layer)
            except Exception as e:
                print(f"自动创建子分类失败: {e}")
        
        if superseded_old_id:
            return {**result, "action": "superseded", "superseded_old_id": superseded_old_id}
        return {**result, "action": "created"}

    def _looks_like_correction(self, content: str) -> bool:
        """启发式判断：是否为纠错/事实更新输入。"""
        if not content:
            return False
        markers = ("更正", "纠正", "修正", "改为", "不是", "应为", "事实上", "更新为", "替换为", "修订")
        return any(m in content for m in markers)

    def _merge_incremental_content(self, old_content: str, new_content: str, layer: int) -> str:
        """增量合并：尽量避免重复，保留可追溯的追加片段。"""
        old_content = (old_content or "").strip()
        new_content = (new_content or "").strip()
        if not new_content:
            return old_content
        if not old_content:
            return new_content
        if new_content in old_content:
            return old_content

        ts = datetime.now(self.beijing_tz).strftime("%Y-%m-%d %H:%M:%S") if getattr(self, "beijing_tz", None) else ""
        header = f"\n\n---\n\n[增量更新 L{layer} {ts}]\n" if ts else f"\n\n---\n\n[增量更新 L{layer}]\n"
        return f"{old_content}{header}{new_content}"
    
    def get_memory(self, memory_id: str) -> Optional[Dict[str, Any]]:
        """获取记忆"""
        memory = self.store.get_by_id(memory_id)
        if memory:
            self.store.increment_access(memory_id)
        return self._attach_parent_label(memory)

    def get_version_chain(self, memory_id: str, max_depth: int = 50) -> List[Dict[str, Any]]:
        """获取版本链（root -> ... -> latest），用于追溯历史版本。"""
        getter = getattr(self.store, "get_version_chain", None)
        if not callable(getter):
            return []
        return getter(memory_id, max_depth=max_depth)

    def set_memory_status(
        self,
        memory_id: str,
        status: str,
        superseded_by: Optional[str] = None,
        clear_invalid_fields: bool = False,
    ) -> bool:
        """管理用途：切换记忆状态，并同步向量库 metadata.status（如可用）。"""
        setter = getattr(self.store, "set_memory_status", None)
        if not callable(setter):
            return False

        ok = setter(
            memory_id=memory_id,
            status=status,
            superseded_by=superseded_by,
            clear_invalid_fields=clear_invalid_fields,
        )
        if not ok:
            return False

        try:
            meta = self.vector_store.get_metadata(memory_id) or {}
            meta["status"] = status
            emb = self.vector_store.get_embedding(memory_id)
            if emb is not None:
                self.vector_store.save_embedding(memory_id, emb, meta)
        except Exception:
            pass

        return True
    
    def update_memory(self, memory_id: str, content: str, reason: str = "") -> Optional[Dict[str, Any]]:
        """更新记忆"""
        old_memory = self.store.get_by_id(memory_id)
        if not old_memory:
            return {"error": "NOT_FOUND", "message": "记忆不存在"}
        
        # 更新记忆
        result = self.store.update(memory_id, content, reason)
        if result:
            # 更新嵌入
            embedding_service.update_corpus(memory_id, content)
            embedding = embedding_service.embed_text(content, memory_id)
            metadata_dict = {
                "category": old_memory.get("category"),
                "layer": old_memory.get("layer"),
                "level": old_memory.get("level"),
                "source": old_memory.get("source"),
                "status": old_memory.get("status", "active"),
            }
            self.vector_store.save_embedding(memory_id, embedding, metadata_dict)
            embedding_service.persist()

            if old_memory.get("layer", 0) >= 3:
                try:
                    from app.services.md_export_service import md_export_service
                    md_export_service.export_memory_to_md(result)
                except Exception as e:
                    print(f"更新后的记忆导出失败: {e}")
        
        return result

    def _move_child_memories_to_fallback(self, category_name: str, child_layer: int, fallback_category: str, reason: str) -> None:
        if not category_name:
            return

        child_memories = self.store.get_by_layer(child_layer)
        for child in child_memories:
            if child.get("category") != category_name:
                continue

            self.store.update(
                child["id"],
                child.get("content", ""),
                category=fallback_category,
                reason=reason
            )

            child_old_meta = self.vector_store.get_metadata(child["id"]) or {}
            child_old_meta["category"] = fallback_category
            current_embedding = self.vector_store.get_embedding(child["id"])
            if current_embedding:
                self.vector_store.save_embedding(child["id"], current_embedding, child_old_meta)

            updated_child = self.store.get_by_id(child["id"])
            if updated_child:
                try:
                    from app.services.md_export_service import md_export_service
                    md_export_service.export_memory_to_md(updated_child)
                except Exception as e:
                    print(f"重导出子记忆失败: {e}")

    def _get_default_category_name(self, layer: int) -> Optional[str]:
        if layer == 3:
            return "未归档"
        if layer == 5:
            return "未分类"
        return None

    def _ensure_default_category_exists(self, layer: int) -> Optional[Dict[str, Any]]:
        default_name = self._get_default_category_name(layer)
        if not default_name:
            return None

        for category in self.store.get_categories_by_layer(layer):
            if category.get("name") == default_name:
                return category

        return self.store.create_category(
            category_id=str(uuid.uuid4()),
            name=default_name,
            layer=layer,
            level=1,
            parent_id=None
        )

    def _ensure_default_layer_memory_exists(self, layer: int, source: Optional[str] = None) -> Optional[Dict[str, Any]]:
        default_name = self._get_default_category_name(layer)
        if not default_name:
            return None

        for memory in self.store.get_by_layer(layer):
            if (memory.get("category") or "").strip() == default_name:
                return memory

        memory_id = str(uuid.uuid4())
        sn = self.generate_short_name(default_name, layer, default_name)
        default_memory = self.store.create(
            memory_id=memory_id,
            content=default_name,
            category=default_name,
            layer=layer,
            level=1,
            tags=[default_name],
            source=source or "system",
            confidence=1.0,
            metadata={"system_default_category": True},
            status="active",
            processed_status="processed",
            short_name=sn
        )

        embedding = embedding_service.embed_text(default_name, memory_id)
        if embedding:
            self.vector_store.save_embedding(
                memory_id,
                embedding,
                {
                    "category": default_name,
                    "layer": layer,
                    "level": 1,
                    "source": source or "system",
                    "tags": [default_name],
                    "confidence": 1.0,
                    "status": "active",
                }
            )

        try:
            from app.services.md_export_service import md_export_service
            md_export_service.export_memory_to_md(default_memory)
        except Exception as e:
            print(f"默认分类记忆导出失败: {e}")

        return self.store.get_by_id(memory_id)

    def delete_managed_category(self, category_id: str) -> Dict[str, Any]:
        category = self.store.get_category_by_id(category_id)
        if not category:
            return {"error": "NOT_FOUND", "message": "分类不存在"}

        default_name = self._get_default_category_name(category.get("layer", 0))
        if default_name and category.get("name") == default_name:
            return {"error": "PROTECTED_CATEGORY", "message": "默认分类不可删除"}

        if category.get("layer") in (3, 5):
            default_category = self._ensure_default_category_exists(category["layer"])
            if not default_category:
                return {"error": "DEFAULT_CATEGORY_CREATE_FAILED", "message": "默认分类创建失败"}

        if category.get("layer") == 3:
            self._move_child_memories_to_fallback(
                category.get("name"),
                4,
                "未归档",
                "L3分类被删除，移入未归档"
            )
        elif category.get("layer") == 5:
            self._move_child_memories_to_fallback(
                category.get("name"),
                6,
                "未分类",
                "L5分类被删除，移入未分类"
            )

        deleted = self.store.delete_category(category_id)
        if not deleted:
            return {"error": "DELETE_FAILED", "message": "分类删除失败"}

        return {"message": "分类删除成功"}

    def normalize_similar_categories(self, category_layer: int, max_groups: Optional[int] = None) -> Dict[str, Any]:
        merge_plan = category_normalization_service.build_merge_plan(category_layer)
        if max_groups and max_groups > 0:
            merge_plan = merge_plan[:max_groups]
        merged_groups = 0
        moved_children = 0

        for group in merge_plan:
            for redundant_name, redundant_id in zip(
                group["redundant_category_names"],
                group["redundant_category_ids"],
            ):
                children = self.store.get_memories_by_category(redundant_name, group["child_layer"])
                for child in children:
                    self.store.update(
                        child["id"],
                        child["content"],
                        category=group["target_category"],
                        reason=f"L{category_layer}分类收敛合并",
                    )
                    updated_child = self.store.get_by_id(child["id"])
                    if updated_child:
                        md_export_service.export_memory_to_md(updated_child)
                    moved_children += 1
                self.delete_memory(redundant_id)
            merged_groups += 1

        cleanup_result = self.cleanup_empty_categories()

        return {
            "layer": category_layer,
            "detected_groups": len(merge_plan),
            "merged_groups": merged_groups,
            "moved_children": moved_children,
            "cleanup_details": cleanup_result,
            "directories_deleted": cleanup_result.get("directories_deleted", 0),
            "categories_deleted": cleanup_result.get("memories_deleted", 0),
        }
    
    def delete_memory(self, memory_id: str):
        """删除记忆"""
        memory = self.store.get_by_id(memory_id)
        if not memory:
            return False
            
        if memory.get("is_pinned"):
            return {"error": "PINNED_MEMORY", "message": "永久记忆需要特殊确认才能删除"}
        
        if memory.get("layer") == 3:
            category_name = memory.get("category")
            self._ensure_default_category_exists(3)
            self._ensure_default_layer_memory_exists(3, source=memory.get("source"))
            self._move_child_memories_to_fallback(category_name, 4, "未归档", "L3分类被删除，移入未归档")

        # 如果是 L5 层记忆（技能分类），将其下的 L6 技能移动到"未分类"
        if memory.get("layer") == 5:
            category_name = memory.get("category")
            self._ensure_default_category_exists(5)
            self._ensure_default_layer_memory_exists(5, source=memory.get("source"))
            self._move_child_memories_to_fallback(category_name, 6, "未分类", "L5分类被删除，移入未分类")

        if memory.get("layer", 0) >= 3:
            try:
                from app.services.md_export_service import md_export_service
                md_export_service.delete_memory_file(memory)
            except Exception as e:
                print(f"删除知识库映射失败: {e}")

        # 删除记忆
        result = self.store.delete(memory_id)
        if result:
            # 删除嵌入
            embedding_service.remove_from_corpus(memory_id)
            self.vector_store.remove_embedding(memory_id)
            embedding_service.persist()
        
        return result
    
    def pin_memory(self, memory_id: str) -> Optional[Dict[str, Any]]:
        old_memory = self.store.get_by_id(memory_id)
        if not old_memory:
            return None
        self.store.update_pin(memory_id, True, layer=5)
        return self.store.get_by_id(memory_id)
    
    def unpin_memory(self, memory_id: str) -> Optional[Dict[str, Any]]:
        old_memory = self.store.get_by_id(memory_id)
        if not old_memory:
            return None
        self.store.update_pin(memory_id, False)
        return self.store.get_by_id(memory_id)
    
    def query_memory(
        self,
        query: str,
        categories: List[str] = None,
        limit: int = 10,
        include_history: bool = False,
    ) -> Dict[str, Any]:
        from app.services.retrieval_service import retrieval_service
        result = retrieval_service.query(
            query_text=query,
            categories=categories,
            limit=limit,
            include_history=include_history,
        )
        return result
    
    def _get_beijing_timestamp(self) -> str:
        """获取北京时间戳"""
        return datetime.now(self.beijing_tz).replace(tzinfo=None).strftime('%Y-%m-%d %H:%M:%S')

    def _normalize_summary_category(self, candidate_name: str) -> str:
        return category_normalization_service.resolve_category_name(candidate_name, 3)

    def _normalize_skill_category(self, candidate_name: str) -> str:
        return category_normalization_service.resolve_category_name(candidate_name, 5)
    
    def _check_semantic_duplicate(self, content: str, threshold: float = None, filter_layer: int = None) -> Optional[Dict[str, Any]]:
        """语义去重检查 (兼容旧版逻辑)"""
        try:
            if threshold is None:
                threshold = settings.dedup_threshold
            
            query_embedding = embedding_service.embed_text(content)
            if not query_embedding:
                return None
            
            filter_metadata = None
            if filter_layer is not None:
                filter_metadata = {"layer": filter_layer}
            
            similar = self.vector_store.search_similar(query_embedding, k=10, filter_metadata=filter_metadata)
            
            for memory_id, score in similar:
                if score >= threshold:
                    memory = self.store.get_by_id(memory_id)
                    # 确保只考虑 active 状态的记忆
                    if memory and memory.get("status") == "active" and not (memory.get("invalid_at") or "").strip():
                        return {
                            "id": memory["id"],
                            "content": memory["content"],
                            "score": score
                        }
            
            return None
        except Exception as e:
            print(f"语义去重检查失败: {e}")
            return None

    def _check_conflicts(self, content: str, layer: int) -> List[Dict[str, Any]]:
        """检查冲突/更新的记忆"""
        try:
            threshold = getattr(settings, "conflict_threshold", 0.75)
            query_embedding = embedding_service.embed_text(content)
            if not query_embedding:
                return []
            
            # 只与同层级的 active 记忆进行冲突检查
            filter_metadata = {"layer": layer}
            similar = self.vector_store.search_similar(query_embedding, k=5, filter_metadata=filter_metadata)
            
            conflicts = []
            for memory_id, score in similar:
                if score >= threshold:
                    memory = self.store.get_by_id(memory_id)
                    if memory and memory.get("status") == "active" and not (memory.get("invalid_at") or "").strip():
                        memory["conflict_score"] = score
                        conflicts.append(memory)
            return conflicts
        except Exception as e:
            print(f"冲突检查失败: {e}")
            return []
    
    def _parse_ttl(self, ttl: str) -> float:
        """解析TTL字符串为天数"""
        if ttl.endswith("d"):
            return int(ttl[:-1])
        elif ttl.endswith("h"):
            return int(ttl[:-1]) / 24
        elif ttl.endswith("m"):
            return int(ttl[:-1]) / (24 * 60)
        return int(ttl)
    
    def _save_entities(self, memory_id: str, entities: List[Dict[str, Any]]):
        self.store.save_entities(memory_id, entities)

    def _build_parent_label_map(self, parent_layer: int) -> Dict[str, Dict[str, Any]]:
        parent_map: Dict[str, Dict[str, Any]] = {}
        for memory in self.store.get_by_layer(parent_layer):
            category = (memory.get("category") or "").strip()
            if not category or category in parent_map:
                continue
            parent_map[category] = {
                "layer": parent_layer,
                "name": category,
                "memory_id": memory.get("id")
            }
        return parent_map

    def _extract_title(self, memory: Dict[str, Any]) -> str:
        content = memory.get('content', '') or ''
        layer = memory.get('layer', 0)
        category = memory.get('category', '') or ''

        if layer == 6:
            m = re.search(r'技能名称[：:]\s*([^\n]+)', content)
            if m:
                return m.group(1).strip()

        if layer == 4:
            m = re.search(r'主题[：:]\s*([^\n]+)', content)
            if m:
                return m.group(1).strip()

        m = re.search(r'^##\s+(.+)$', content, re.MULTILINE)
        if m:
            return m.group(1).strip()

        if layer in (3, 5) and category:
            return category

        lines = content.split('\n')
        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith('---') or stripped.startswith('#') or stripped.startswith('**'):
                continue
            if re.match(r'^(主题|技能名称|核心要点|详细记录|目标任务|触发条件|包含步骤|涉及工具|最佳实践|依赖|注意事项)[：:]', stripped):
                continue
            title = stripped[:60]
            if len(stripped) > 60:
                last_punct = max(title.rfind(c) for c in '。！？；，、')
                if last_punct > 10:
                    title = title[:last_punct + 1]
            return title

        if category:
            return category
        return '无标题'

    def _attach_parent_label(
        self,
        memory: Optional[Dict[str, Any]],
        l3_parent_map: Optional[Dict[str, Dict[str, Any]]] = None,
        l5_parent_map: Optional[Dict[str, Dict[str, Any]]] = None
    ) -> Optional[Dict[str, Any]]:
        if not memory:
            return memory

        item = dict(memory)
        category = (item.get("category") or "").strip()
        layer = item.get("layer")

        if "title" not in item or not item["title"]:
            item["title"] = self._extract_title(item)

        if layer == 4 and category:
            l3_parent_map = l3_parent_map or self._build_parent_label_map(3)
            item["parent_label"] = l3_parent_map.get(category)
        elif layer == 6 and category:
            l5_parent_map = l5_parent_map or self._build_parent_label_map(5)
            item["parent_label"] = l5_parent_map.get(category)
        else:
            item["parent_label"] = None

        return item

    def _attach_parent_labels(self, memories: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not memories:
            return []

        l3_parent_map = self._build_parent_label_map(3)
        l5_parent_map = self._build_parent_label_map(5)

        return [
            self._attach_parent_label(
                memory,
                l3_parent_map=l3_parent_map,
                l5_parent_map=l5_parent_map
            )
            for memory in memories
        ]
    
    def list_memories(self, limit: int = 100) -> List[Dict[str, Any]]:
        """列出所有记忆"""
        memories = self.store.list_all(limit=limit)
        return self._attach_parent_labels(memories)

    def get_statistics(self) -> Dict[str, Any]:
        """获取记忆统计数据"""
        from datetime import datetime as dt
        all_memories = self.store.list_all(limit=100000)
        today = dt.now(self.beijing_tz).date()
        today_count = 0
        layer_counts = {0: 0, 1: 0, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0}
        categories = set()
        for m in all_memories:
            created = m.get("created_at", "")
            if created:
                try:
                    mem_date = dt.fromisoformat(created).date()
                    if mem_date == today:
                        today_count += 1
                except Exception:
                    pass
            layer = m.get("layer", 0)
            if layer in layer_counts:
                layer_counts[layer] += 1
            cat = m.get("category")
            if cat:
                categories.add(cat)
        return {
            "totalMemories": len(all_memories),
            "todayCount": today_count,
            "categoryCount": len(categories),
            "l0Count": layer_counts[0],
            "l1Count": layer_counts[1],
            "l2Count": layer_counts[2],
            "l3Count": layer_counts[3],
            "l4Count": layer_counts[4],
            "l5Count": layer_counts[5],
            "l6Count": layer_counts[6],
        }

    def reset_statistics(self) -> Dict[str, Any]:
        """重置统计数据（当前统计为实时计算，此接口保留兼容）"""
        return self.get_statistics()
    
    def search_by_keyword(self, keyword: str, limit: int = 20) -> List[Dict[str, Any]]:
        """按关键词搜索记忆"""
        return self.store.search_by_keyword(keyword, limit=limit)
    
    def process_l1_to_l2(self, batch_size: int = None, max_chars: int = None) -> Dict[str, Any]:
        """处理L1原始数据，自动去重后迁移到L2沉淀层（增量合并模式）"""
        if max_chars is None:
            max_chars = settings.l1_to_l2_max_chars
        
        try:
            all_pending_l1 = self.store.get_by_layer_and_status(1, 'pending')
            if not all_pending_l1:
                return {"message": "No pending L1 memories found", "processed": 0}
            
            batches = self._pack_memories_by_chars(all_pending_l1, max_chars)
            
            total_processed = 0
            total_duplicates = 0
            
            for batch in batches:
                batch_processed, batch_duplicates = self._process_l1_batch(batch)
                total_processed += batch_processed
                total_duplicates += batch_duplicates
            
            embedding_service.persist()
            
            return {
                "message": "L1 to L2 processing completed",
                "processed": total_processed,
                "duplicates": total_duplicates,
                "total": len(all_pending_l1),
                "batches": len(batches)
            }
        except Exception as e:
            print(f"Error processing L1 to L2: {e}")
            return {"error": "PROCESSING_ERROR", "message": str(e)}
    
    def _process_l1_batch(self, l1_memories: List[Dict]) -> Tuple[int, int]:
        """处理单个L1批次，返回(新增数, 合并数)
        
        增量更新策略：
        1. 批量计算所有embedding，避免重复计算
        2. 使用FAISS批量矩阵搜索，一次运算完成所有去重检查
        3. 近似记忆（score >= dedup_threshold）→ 合并更新到已有L2
        4. 无近似记忆 → 新增L2记录
        5. 缓存embedding结果，合并和保存时复用
        """
        new_count = 0
        merged_count = 0
        
        valid_memories = []
        embeddings_list = []
        for memory in l1_memories:
            content = memory["content"]
            embedding = embedding_service.embed_text(content)
            if embedding:
                valid_memories.append(memory)
                embeddings_list.append(embedding)
        
        if not valid_memories:
            for memory in l1_memories:
                self.store.update_processed_status(memory["id"], 'processed')
            return 0, len(l1_memories)
        
        batch_results = self.vector_store.search_similar_batch(embeddings_list, k=10)
        
        merge_map = {}
        for i, memory in enumerate(valid_memories):
            similar = batch_results[i]
            best_match = None
            best_score = 0
            for sim_id, score in similar:
                if score >= settings.dedup_threshold:
                    existing_memory = self.store.get_by_id(sim_id)
                    if existing_memory and existing_memory.get("layer", 0) >= 2:
                        if score > best_score:
                            best_match = (sim_id, existing_memory, score)
                            best_score = score
            if best_match:
                merge_map[i] = best_match
        
        for i, memory in enumerate(valid_memories):
            if i in merge_map:
                sim_id, existing_memory, score = merge_map[i]
                old_content = existing_memory.get("content", "")
                new_content = old_content.strip() + "\n\n" + memory["content"].strip()
                self.store.update(sim_id, new_content, reason="增量合并了相似的L1记录(L1->L2)")
                embedding = embedding_service.embed_text(new_content, sim_id)
                old_meta = self.vector_store.get_metadata(sim_id) or {}
                self.vector_store.save_embedding(sim_id, embedding, old_meta)
                merged_count += 1
            else:
                new_memory_id = str(uuid.uuid4())
                sn = self.generate_short_name(memory["content"], 2, memory.get("category"))
                self.store.create(
                    memory_id=new_memory_id,
                    content=memory["content"],
                    category=memory.get("category"),
                    layer=2,
                    level=1,
                    tags=memory.get("tags"),
                    source=memory.get("source"),
                    confidence=memory.get("confidence", 1.0),
                    metadata=memory.get("metadata"),
                    status="active",
                    processed_status='pending',
                    short_name=sn
                )
                embedding = embeddings_list[i]
                metadata_dict = {
                    "category": memory.get("category"),
                    "layer": 2,
                    "level": 1,
                    "source": memory.get("source"),
                    "tags": memory.get("tags"),
                    "confidence": memory.get("confidence", 1.0),
                }
                self.vector_store.save_embedding(new_memory_id, embedding, metadata_dict)
                new_count += 1
        
        for memory in l1_memories:
            self.store.update_processed_status(memory["id"], 'processed')
        
        return new_count, merged_count

    
    def process_l2_to_l4(self, max_chars: int = None) -> Dict[str, Any]:
        """处理L2沉淀记忆，调用本地大模型总结后迁移到L4总结记忆层"""
        if max_chars is None:
            max_chars = settings.l2_to_l4_max_chars
            
        llm_enabled = self.store.get_config("llm_enabled")
        llm_enabled = llm_enabled.lower() == "true" if llm_enabled else getattr(settings, "llm_enabled", True)
        
        if not llm_enabled:
            return {"message": "大模型处理已禁用，跳过L2到L4提炼", "processed": 0}
            
        try:
            all_l2_memories = self.store.get_by_layer_and_status(2, 'pending')
            if not all_l2_memories:
                return {"message": "No pending L2 memories found", "processed": 0}
            
            batches = self._pack_memories_by_chars(all_l2_memories, max_chars)
            
            total_processed = 0
            
            for batch in batches:
                batch_result = self._async_process_l2_batch(batch)
                if batch_result > 0:
                    total_processed += batch_result
            
            embedding_service.persist()
            
            return {
                "message": "L2 to L4 processing completed",
                "processed": total_processed,
                "total": len(all_l2_memories),
                "batches": len(batches)
            }
        except Exception as e:
            print(f"Error processing L2 to L4: {e}")
            return {"error": "PROCESSING_ERROR", "message": str(e)}
    
    def _async_process_l2_batch(self, l2_memories: List[Dict]) -> int:
        """异步处理单个L2批次"""
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(self._async_process_l2_batch_core(l2_memories))
        finally:
            loop.close()
    
    async def _async_process_l2_batch_core(self, l2_memories: List[Dict]) -> int:
        """异步核心处理L2批次"""
        from concurrent.futures import ThreadPoolExecutor, as_completed
        
        batch_result = self._batch_process_l2_to_l4(l2_memories)
        if batch_result != -1:
            return batch_result
        
        print("[Fallback] 切换为逐条处理 L2->L4")
        
        processed_count = 0
        for memory in l2_memories:
            result = self._process_single_l2_to_l4(memory)
            processed_count += result
        
        return processed_count
    
    def _process_single_l2_to_l4(self, memory: Dict) -> int:
        """处理单条L2到L4转换（增量合并模式，不创建L3）"""
        query_embedding = embedding_service.embed_text(memory["content"])
        related_l4_id = None
        related_l4_content = None
        
        if query_embedding:
            similar = self.vector_store.search_similar(query_embedding, k=5)
            for sim_id, score in similar:
                if score >= getattr(settings, 'l2_to_l4_similarity_threshold', 0.85):
                    existing_memory = self.store.get_by_id(sim_id)
                    if (
                        existing_memory
                        and existing_memory.get("layer") == 4
                        and existing_memory.get("status") == "active"
                    ):
                        related_l4_id = sim_id
                        related_l4_content = existing_memory["content"]
                        break
        
        if related_l4_id and related_l4_content:
            merged_summary = self._merge_summary(related_l4_content, memory["content"])
            if merged_summary:
                new_category = self._normalize_summary_category(self._generate_category(merged_summary))
                
                self.store.update(related_l4_id, merged_summary, category=new_category, reason="合并了新的相关记忆(L2->L4)")
                
                embedding = embedding_service.embed_text(merged_summary, related_l4_id)
                old_meta = self.vector_store.get_metadata(related_l4_id) or {}
                old_meta["category"] = new_category
                self.vector_store.save_embedding(related_l4_id, embedding, old_meta)
                
                try:
                    from app.services.md_export_service import md_export_service
                    l4_memory_dict = self.store.get_by_id(related_l4_id)
                    if l4_memory_dict:
                        md_export_service.export_memory_to_md(l4_memory_dict)
                except Exception as e:
                    print(f"更新后的L4记忆MD文件导出失败: {e}")
                
                self.store.update_processed_status(memory["id"], 'summarized')
                return 1
        else:
            summary = self._generate_summary(memory["content"])
            if summary:
                if "Mock summary" in summary or summary.strip() == "Mock summary":
                    print(f"[Warning] 拦截到大模型生成的无效总结(Mock summary)，跳过存储，保留 L2 原始状态供重试")
                    return 0
                    
                new_category = self._generate_category(summary)
                if "Mock" in new_category:
                    new_category = "综合记录"
                new_category = self._normalize_summary_category(new_category)
                
                summary_memory_id = str(uuid.uuid4())
                sn = self.generate_short_name(summary, 4, new_category)
                self.store.create(
                    memory_id=summary_memory_id,
                    content=summary,
                    category=new_category,
                    layer=4,
                    level=2,
                    tags=memory.get("tags"),
                    source=memory.get("source"),
                    confidence=memory.get("confidence", 0.8),
                    metadata={**memory.get("metadata", {}), "original_memory_id": memory["id"]},
                    status="active",
                    processed_status='pending',
                    short_name=sn
                )
                embedding = embedding_service.embed_text(summary, summary_memory_id)
                metadata_dict = {
                    "category": new_category,
                    "layer": 4,
                    "level": 2,
                    "source": memory.get("source"),
                    "tags": memory.get("tags"),
                    "confidence": memory.get("confidence", 0.8),
                }
                self.vector_store.save_embedding(summary_memory_id, embedding, metadata_dict)
                
                try:
                    from app.services.md_export_service import md_export_service
                    l4_memory_dict = self.store.get_by_id(summary_memory_id)
                    if l4_memory_dict:
                        md_export_service.export_memory_to_md(l4_memory_dict)
                except Exception as e:
                    print(f"L4记忆MD文件导出失败: {e}")
                
                self.store.update_processed_status(memory["id"], 'summarized')
                return 1
        return 0

    def process_l4_to_l3(self, progress_hook=None) -> Dict[str, Any]:
        """L4归类得到L3：扫描所有L4记录，按category归类，增量创建/更新L3分类
        
        增量更新原则：
        - L4的category已有对应L3 → 更新L3的memory_count等元数据
        - L4的category无对应L3 → 新增L3分类记录
        - 近似category的L3 → 合并归一（委托category_normalization_service）
        """
        try:
            l4_memories = self.store.get_by_layer(4)
            if not l4_memories:
                return {"message": "No L4 memories found", "created": 0, "updated": 0}
            
            l3_memories = self.store.get_by_layer(3)
            existing_l3_map = {}
            for l3 in l3_memories:
                cat = l3.get("category", "")
                if cat:
                    existing_l3_map[cat] = l3
            
            l4_category_map = {}
            for l4 in l4_memories:
                cat = l4.get("category", "")
                if cat:
                    if cat not in l4_category_map:
                        l4_category_map[cat] = []
                    l4_category_map[cat].append(l4)
            
            created_count = 0
            updated_count = 0
            
            total_cats = len(l4_category_map)
            done_cats = 0
            for cat, l4_list in l4_category_map.items():
                if cat in existing_l3_map:
                    l3 = existing_l3_map[cat]
                    l4_ids = [m["id"] for m in l4_list]
                    meta = l3.get("metadata", {})
                    if isinstance(meta, str):
                        try: meta = json.loads(meta)
                        except: meta = {}
                    meta["child_l4_ids"] = l4_ids
                    meta["memory_count"] = len(l4_list)
                    self.store.update(l3["id"], metadata=json.dumps(meta), reason="L4归类更新L3分类")
                    updated_count += 1
                else:
                    category_memory_id = str(uuid.uuid4())
                    l4_ids = [m["id"] for m in l4_list]
                    sn = self.generate_short_name(cat, 3, cat)
                    self.store.create(
                        memory_id=category_memory_id,
                        content=cat,
                        category=cat,
                        layer=3,
                        level=2,
                        tags=[cat],
                        source="l4_categorize",
                        confidence=0.9,
                        metadata={"child_l4_ids": l4_ids, "memory_count": len(l4_list)},
                        status="active",
                        processed_status='processed',
                        short_name=sn
                    )
                    category_embedding = embedding_service.embed_text(cat, category_memory_id)
                    category_metadata_dict = {
                        "category": cat,
                        "layer": 3,
                        "level": 2,
                        "tags": [cat],
                        "confidence": 0.9,
                    }
                    self.vector_store.save_embedding(category_memory_id, category_embedding, category_metadata_dict)
                    
                    try:
                        from app.services.md_export_service import md_export_service
                        l3_memory_dict = self.store.get_by_id(category_memory_id)
                        if l3_memory_dict:
                            md_export_service.export_memory_to_md(l3_memory_dict)
                    except Exception as e:
                        print(f"L3记忆MD文件导出失败: {e}")
                    
                    existing_l3_map[cat] = {"id": category_memory_id, "category": cat}
                    created_count += 1

                done_cats += 1
                if callable(progress_hook) and total_cats > 0:
                    try:
                        progress_hook(done_cats, total_cats)
                    except Exception:
                        # progress reporting should never break organize
                        pass
            
            orphan_l3_ids = set()
            for cat, l3 in existing_l3_map.items():
                if cat not in l4_category_map:
                    orphan_l3_ids.add(l3.get("id", ""))
            
            if orphan_l3_ids:
                for l3_id in orphan_l3_ids:
                    if l3_id:
                        l3_mem = self.store.get_by_id(l3_id)
                        if l3_mem:
                            meta = l3_mem.get("metadata", {})
                            if isinstance(meta, str):
                                try: meta = json.loads(meta)
                                except: meta = {}
                            child_ids = meta.get("child_l4_ids", [])
                            if not child_ids:
                                self.store.update(l3_id, status="archived", reason="L4归类清理孤立L3分类")
            
            embedding_service.persist()
            
            print(f"[L4→L3] 归类完成: 新增{created_count}个L3分类, 更新{updated_count}个L3分类")
            return {"created": created_count, "updated": updated_count, "total_l4": len(l4_memories)}
        except Exception as e:
            print(f"L4归类到L3失败: {e}")
            return {"created": 0, "updated": 0, "error": str(e)}

    def process_l6_to_l5(self, progress_hook=None) -> Dict[str, Any]:
        """L6归类得到L5：扫描所有L6记录，按category归类，增量创建/更新L5分类
        
        增量更新原则：
        - L6的category已有对应L5 → 更新L5的memory_count等元数据
        - L6的category无对应L5 → 新增L5分类记录
        - 近似category的L5 → 合并归一（委托category_normalization_service）
        """
        try:
            l6_memories = self.store.get_by_layer(6)
            if not l6_memories:
                return {"message": "No L6 memories found", "created": 0, "updated": 0}
            
            l5_memories = self.store.get_by_layer(5)
            existing_l5_map = {}
            for l5 in l5_memories:
                cat = l5.get("category", "")
                if cat:
                    existing_l5_map[cat] = l5
            
            l6_category_map = {}
            for l6 in l6_memories:
                cat = l6.get("category", "")
                if cat:
                    if cat not in l6_category_map:
                        l6_category_map[cat] = []
                    l6_category_map[cat].append(l6)
            
            created_count = 0
            updated_count = 0
            
            total_cats = len(l6_category_map)
            done_cats = 0
            for cat, l6_list in l6_category_map.items():
                if cat in existing_l5_map:
                    l5 = existing_l5_map[cat]
                    l6_ids = [m["id"] for m in l6_list]
                    meta = l5.get("metadata", {})
                    if isinstance(meta, str):
                        try: meta = json.loads(meta)
                        except: meta = {}
                    meta["child_l6_ids"] = l6_ids
                    meta["memory_count"] = len(l6_list)
                    self.store.update(l5["id"], metadata=json.dumps(meta), reason="L6归类更新L5分类")
                    updated_count += 1
                else:
                    category_memory_id = str(uuid.uuid4())
                    l6_ids = [m["id"] for m in l6_list]
                    sn = self.generate_short_name(cat, 5, cat)
                    self.store.create(
                        memory_id=category_memory_id,
                        content=cat,
                        category=cat,
                        layer=5,
                        level=3,
                        tags=[cat],
                        source="l6_categorize",
                        confidence=0.95,
                        metadata={"child_l6_ids": l6_ids, "memory_count": len(l6_list)},
                        status="active",
                        processed_status='processed',
                        short_name=sn
                    )
                    category_embedding = embedding_service.embed_text(cat, category_memory_id)
                    category_metadata_dict = {
                        "category": cat,
                        "layer": 5,
                        "level": 3,
                        "tags": [cat],
                        "confidence": 0.95,
                    }
                    self.vector_store.save_embedding(category_memory_id, category_embedding, category_metadata_dict)
                    
                    try:
                        from app.services.md_export_service import md_export_service
                        l5_memory_dict = self.store.get_by_id(category_memory_id)
                        if l5_memory_dict:
                            md_export_service.export_memory_to_md(l5_memory_dict)
                    except Exception as e:
                        print(f"L5记忆MD文件导出失败: {e}")
                    
                    existing_l5_map[cat] = {"id": category_memory_id, "category": cat}
                    created_count += 1

                done_cats += 1
                if callable(progress_hook) and total_cats > 0:
                    try:
                        progress_hook(done_cats, total_cats)
                    except Exception:
                        pass
            
            orphan_l5_ids = set()
            for cat, l5 in existing_l5_map.items():
                if cat not in l6_category_map:
                    orphan_l5_ids.add(l5.get("id", ""))
            
            if orphan_l5_ids:
                for l5_id in orphan_l5_ids:
                    if l5_id:
                        l5_mem = self.store.get_by_id(l5_id)
                        if l5_mem:
                            meta = l5_mem.get("metadata", {})
                            if isinstance(meta, str):
                                try: meta = json.loads(meta)
                                except: meta = {}
                            child_ids = meta.get("child_l6_ids", [])
                            if not child_ids:
                                self.store.update(l5_id, status="archived", reason="L6归类清理孤立L5分类")
            
            embedding_service.persist()
            
            print(f"[L6→L5] 归类完成: 新增{created_count}个L5分类, 更新{updated_count}个L5分类")
            return {"created": created_count, "updated": updated_count, "total_l6": len(l6_memories)}
        except Exception as e:
            print(f"L6归类到L5失败: {e}")
            return {"created": 0, "updated": 0, "error": str(e)}

    
    def reclassify_default_l4(self, limit: Optional[int] = None) -> Dict[str, Any]:
        """将临时归档下的L4经验重新分类"""
        try:
            l4_memories = self.store.get_by_layer(4)
            default_l4s = [m for m in l4_memories if m.get("category") in ["默认分类", "未归档", "综合记录"]]
            if limit and limit > 0:
                default_l4s = default_l4s[:limit]

            reclassified_count = 0
            
            for memory in default_l4s:
                new_category = self._generate_category(memory["content"])
                if new_category and new_category not in ["未分类", "默认分类", "未归档", "综合记录"]:
                    self.store.update(memory["id"], category=new_category, reason="从临时归档中重新分类")
                    reclassified_count += 1
                    
                    l4_old_meta = self.vector_store.get_metadata(memory["id"]) or {}
                    l4_old_meta["category"] = new_category
                    current_embedding = self.vector_store.get_embedding(memory["id"])
                    if current_embedding:
                        self.vector_store.save_embedding(memory["id"], current_embedding, l4_old_meta)
                        
                    l3_memories = self.store.get_by_layer(3)
                    existing_l3 = next((m for m in l3_memories if m.get("category") == new_category), None)
                    
                    if not existing_l3:
                        category_memory_id = str(uuid.uuid4())
                        sn = self.generate_short_name(new_category, 3, new_category)
                        self.store.create(
                            memory_id=category_memory_id,
                            content=new_category,
                            category=new_category,
                            layer=3,
                            level=2,
                            tags=[new_category],
                            confidence=0.9,
                            metadata={"summary_memory_id": memory["id"]},
                            status="active",
                            processed_status='processed',
                            short_name=sn
                        )
                        category_embedding = embedding_service.embed_text(new_category, category_memory_id)
                        category_metadata_dict = {
                            "category": new_category,
                            "layer": 3,
                            "level": 2,
                            "tags": [new_category],
                            "confidence": 0.9,
                        }
                        self.vector_store.save_embedding(category_memory_id, category_embedding, category_metadata_dict)
                        try:
                            from app.services.md_export_service import md_export_service
                            l3_memory_dict = self.store.get_by_id(category_memory_id)
                            if l3_memory_dict:
                                md_export_service.export_memory_to_md(l3_memory_dict)
                        except Exception as e:
                            print(f"L3记忆MD文件导出失败: {e}")
                    else:
                        meta = existing_l3.get("metadata", {})
                        if isinstance(meta, str):
                            import json
                            try: meta = json.loads(meta)
                            except: meta = {}
                        meta["summary_memory_id"] = memory["id"]
                        import json
                        self.store.update(existing_l3["id"], metadata=json.dumps(meta))
                        
                    try:
                        from app.services.md_export_service import md_export_service
                        md_export_service.delete_memory_file(memory)
                        updated_l4 = self.store.get_by_id(memory["id"])
                        if updated_l4:
                            md_export_service.export_memory_to_md(updated_l4)
                    except Exception as e:
                        print(f"重新分类L4导出MD失败: {e}")
                        
            embedding_service.persist()
            return {"reclassified": reclassified_count, "scanned": len(default_l4s)}
        except Exception as e:
            print(f"重分类默认L4失败: {e}")
            return {"reclassified": 0, "scanned": 0, "error": str(e)}

    def deduplicate_existing_l4(self, limit: Optional[int] = None) -> Dict[str, Any]:
        """对已有的 L4 层记忆进行全局去重合并"""
        try:
            print("[Deduplicate] 开始对 L4 经验进行去重检查...")
            l4_memories = [m for m in self.store.get_by_layer(4) if m.get("status", "active") == "active"]
            if not l4_memories:
                return {"merged": 0, "scanned": 0}
            
            # 自动补全可能丢失的向量
            missing_embeddings = 0
            for mem in l4_memories:
                if not self.vector_store.get_embedding(mem["id"]):
                    emb = embedding_service.embed_text(mem["content"], mem["id"])
                    if emb:
                        self.vector_store.save_embedding(
                            mem["id"], 
                            emb, 
                            {"layer": 4, "category": mem.get("category"), "status": mem.get("status", "active")}
                        )
                        missing_embeddings += 1
            if missing_embeddings > 0:
                print(f"[Deduplicate] 已自动补全 {missing_embeddings} 条缺失的 L4 向量")
                embedding_service.persist()
            
            processed_ids = set()
            merged_count = 0
            scanned_count = 0
            
            for i, current_mem in enumerate(l4_memories):
                if limit and limit > 0 and scanned_count >= limit:
                    break
                if current_mem["id"] in processed_ids:
                    continue

                scanned_count += 1
                
                current_embedding = self.vector_store.get_embedding(current_mem["id"])
                if not current_embedding:
                    continue
                    
                similar = self.vector_store.search_similar(current_embedding, k=10)
                
                duplicates = []
                for sim_id, score in similar:
                    if sim_id == current_mem["id"] or sim_id in processed_ids or score < getattr(settings, 'l4_dedup_threshold', 0.85):
                        continue
                    sim_mem = self.store.get_by_id(sim_id)
                    if (
                        sim_mem
                        and sim_mem.get("layer") == 4
                        and sim_mem.get("status", "active") == "active"
                        and sim_mem.get("category") == current_mem.get("category")
                    ):
                        duplicates.append(sim_mem)
                
                if duplicates:
                    print(f"[Deduplicate] 发现 {len(duplicates)} 条与 {current_mem['id']} 相似的 L4 记录，开始合并...")
                    merged_content = current_mem["content"]
                    
                    for dup in duplicates:
                        merged_content = self._merge_summary(merged_content, dup["content"])
                        try:
                            from app.services.md_export_service import md_export_service
                            md_export_service.delete_memory_file(dup)
                        except: pass
                        
                        processed_ids.add(dup["id"])
                        self.delete_memory(dup["id"])
                        merged_count += 1
                        
                    new_category = self._generate_category(merged_content)
                    self.store.update(current_mem["id"], content=merged_content, category=new_category, reason="自动全局去重合并")
                    
                    new_embedding = embedding_service.embed_text(merged_content, current_mem["id"])
                    meta = self.vector_store.get_metadata(current_mem["id"]) or {}
                    meta["category"] = new_category
                    self.vector_store.save_embedding(current_mem["id"], new_embedding, meta)
                    
                    try:
                        from app.services.md_export_service import md_export_service
                        updated_mem = self.store.get_by_id(current_mem["id"])
                        if updated_mem:
                            md_export_service.export_memory_to_md(updated_mem)
                    except Exception as e:
                        print(f"[Deduplicate] 重新导出 L4 失败: {e}")
                        
                processed_ids.add(current_mem["id"])
                
            print(f"[Deduplicate] L4 全局去重完成，共合并了 {merged_count} 条冗余记录。")
            embedding_service.persist()
            return {"merged": merged_count, "scanned": scanned_count}
        except Exception as e:
            print(f"[Deduplicate] L4 全局去重失败: {e}")
            return {"merged": 0, "scanned": 0, "error": str(e)}

    def deduplicate_existing_l6(self, limit: Optional[int] = None) -> Dict[str, Any]:
        """对已有的 L6 层技能记忆进行全局去重合并"""
        try:
            print("[Deduplicate] 开始对 L6 技能进行去重检查...")
            l6_memories = [m for m in self.store.get_by_layer(6) if m.get("status", "active") == "active"]
            if not l6_memories:
                return {"merged": 0, "scanned": 0}
            
            # 自动补全可能丢失的向量
            missing_embeddings = 0
            for mem in l6_memories:
                if not self.vector_store.get_embedding(mem["id"]):
                    emb = embedding_service.embed_text(mem["content"], mem["id"])
                    if emb:
                        self.vector_store.save_embedding(
                            mem["id"], 
                            emb, 
                            {"layer": 6, "category": mem.get("category"), "status": mem.get("status", "active")}
                        )
                        missing_embeddings += 1
            if missing_embeddings > 0:
                print(f"[Deduplicate] 已自动补全 {missing_embeddings} 条缺失的 L6 向量")
                embedding_service.persist()
            
            processed_ids = set()
            merged_count = 0
            scanned_count = 0
            
            for i, current_mem in enumerate(l6_memories):
                if limit and limit > 0 and scanned_count >= limit:
                    break
                if current_mem["id"] in processed_ids:
                    continue

                scanned_count += 1
                
                current_embedding = self.vector_store.get_embedding(current_mem["id"])
                if not current_embedding:
                    continue
                    
                similar = self.vector_store.search_similar(current_embedding, k=10)
                
                duplicates = []
                for sim_id, score in similar:
                    if sim_id != current_mem["id"] and sim_id not in processed_ids and score >= getattr(settings, 'l6_dedup_threshold', 0.85):
                        sim_mem = self.store.get_by_id(sim_id)
                        if (
                            sim_mem
                            and sim_mem.get("layer") == 6
                            and sim_mem.get("status") == "active"
                            and sim_mem.get("category") == current_mem.get("category")
                        ):
                            duplicates.append(sim_mem)
                
                if duplicates:
                    print(f"[Deduplicate] 发现 {len(duplicates)} 条与 {current_mem['id']} 相似的 L6 记录，开始合并...")
                    merged_content = current_mem["content"]
                    
                    for dup in duplicates:
                        merged_content = self._merge_skill(merged_content, dup["content"])
                        try:
                            from app.services.md_export_service import md_export_service
                            md_export_service.delete_memory_file(dup)
                        except: pass
                        
                        processed_ids.add(dup["id"])
                        self.delete_memory(dup["id"])
                        merged_count += 1
                        
                    new_category = self._generate_skill_category(merged_content)
                    self.store.update(current_mem["id"], content=merged_content, category=new_category, reason="自动全局去重合并(技能)")
                    
                    new_embedding = embedding_service.embed_text(merged_content, current_mem["id"])
                    meta = self.vector_store.get_metadata(current_mem["id"]) or {}
                    meta["category"] = new_category
                    self.vector_store.save_embedding(current_mem["id"], new_embedding, meta)
                    
                    try:
                        from app.services.md_export_service import md_export_service
                        updated_mem = self.store.get_by_id(current_mem["id"])
                        if updated_mem:
                            md_export_service.export_memory_to_md(updated_mem)
                    except Exception as e:
                        print(f"[Deduplicate] 重新导出 L6 失败: {e}")
                        
                processed_ids.add(current_mem["id"])
                
            print(f"[Deduplicate] L6 全局去重完成，共合并了 {merged_count} 条冗余记录。")
            embedding_service.persist()
            return {"merged": merged_count, "scanned": scanned_count}
        except Exception as e:
            print(f"[Deduplicate] L6 全局去重失败: {e}")
            return {"merged": 0, "scanned": 0, "error": str(e)}

    def remove_low_quality_memories(self, limit: Optional[int] = None) -> int:
        """扫描并删除低质量或无用的记忆记录"""
        print("[Cleanup] 开始扫描低质量记忆...")
        deleted_count = 0
        try:
            targets = self.store.get_by_layer(4) + self.store.get_by_layer(6)
            if limit and limit > 0:
                targets = targets[:limit]
            placeholders = ["待补充", "无有效内容", "Mock summary", "无有效技能", "MockCategory", "Mock Category"]
            
            for mem in targets:
                content = mem.get("content", "").strip()
                if len(content) < 15 or any(p in content for p in placeholders):
                    try:
                        from app.services.md_export_service import md_export_service
                        md_export_service.delete_memory_file(mem)
                    except: pass
                    self.delete_memory(mem["id"])
                    deleted_count += 1
                    
            print(f"[Cleanup] 已清理 {deleted_count} 条低质量/无用记忆。")
            return deleted_count
        except Exception as e:
            print(f"[Cleanup] 低质量记忆清理失败: {e}")
            return deleted_count

    def _get_positive_int_setting(self, name: str, default: int) -> int:
        """读取正整数配置，避免异常配置导致整理流程失控"""
        try:
            value = int(getattr(settings, name, default))
        except (TypeError, ValueError):
            return default
        return max(0, value)

    def _pause_between_deep_organize_stages(self):
        """自适应低功耗整理：根据系统负载动态调整暂停时间"""
        # 若用户显式配置了固定暂停（例如单测或“低功耗明显节流”场景），优先使用该值。
        pause_ms = self._get_positive_int_setting("deep_organize_stage_pause_ms", 0)
        if pause_ms > 0:
            time.sleep(pause_ms / 1000)
            return

        # 否则使用自适应策略（可选）
        try:
            from app.services.adaptive_organize_service import adaptive_organize_service
            adaptive_organize_service.adaptive_sleep()
        except Exception:
            return

    def _organize_entire_knowledge_base_low_power(self) -> Dict[str, Any]:
        """默认低功耗深度整理：单轮推进有限阶段工作量，避免持续满载
        
        整理流程：质量清理 → L4去重 → L6去重 → L4重分类 → L1→L2 → L2→L4 → L4→L3(归类) → L4→L6 → L6→L5(归类) → 空分类清理
        """
        print("[Organize] 进入低功耗深度整理模式")
        results = {}

        cleanup_memory_limit = self._get_positive_int_setting("deep_organize_cleanup_memory_limit", 12)
        dedup_limit = self._get_positive_int_setting("deep_organize_dedup_limit", 8)
        reclassify_limit = self._get_positive_int_setting("deep_organize_reclassify_limit", 6)
        cleanup_directory_limit = self._get_positive_int_setting("deep_organize_cleanup_directory_limit", 6)
        l1_batches_per_run = self._get_positive_int_setting("deep_organize_l1_batches_per_run", 1)
        l2_batches_per_run = self._get_positive_int_setting("deep_organize_l2_batches_per_run", 1)
        l4_batches_per_run = self._get_positive_int_setting("deep_organize_l4_batches_per_run", 1)

        results["cleanup_removed"] = self.remove_low_quality_memories(limit=cleanup_memory_limit)
        self._pause_between_deep_organize_stages()

        results["l4_dedup"] = self.deduplicate_existing_l4(limit=dedup_limit)
        self._pause_between_deep_organize_stages()

        results["l6_dedup"] = self.deduplicate_existing_l6(limit=dedup_limit)
        self._pause_between_deep_organize_stages()

        reclassify_res = self.reclassify_default_l4(limit=reclassify_limit)
        results["l4_reclassified"] = reclassify_res.get("reclassified", 0)
        results["reclassify_details"] = reclassify_res
        self._pause_between_deep_organize_stages()

        l1_res = self._batch_process_l1_to_l2_smart(max_batches=l1_batches_per_run)
        results["l1_to_l2"] = l1_res.get("processed", 0)
        results["l1_to_l2_details"] = l1_res
        self._pause_between_deep_organize_stages()

        l2_res = self._batch_process_l2_to_l4_smart(max_batches=l2_batches_per_run)
        results["l2_to_l4"] = l2_res.get("processed", 0)
        results["l2_to_l4_details"] = l2_res
        self._pause_between_deep_organize_stages()

        l4_res = self._batch_process_l4_to_l6_smart(max_batches=l4_batches_per_run)
        results["l4_to_l6"] = l4_res.get("processed", 0)
        results["l4_to_l6_details"] = l4_res
        self._pause_between_deep_organize_stages()

        cleanup_res = self.cleanup_empty_categories(
            memory_limit=cleanup_memory_limit,
            directory_limit=cleanup_directory_limit,
        )
        results["cleanup_details"] = cleanup_res

        return {"status": "success", "details": results}

    def organize_entire_knowledge_base(self) -> Dict[str, Any]:
        """【核心方法】执行全量知识库深度整理
        
        整理流程：质量清理 → L4/L6去重 → L1→L2 → L2→L4 → L4重分类 → L4→L3(归类) → L4→L6 → L6→L5(归类) → 空分类清理
        """
        print("[Organize] ================= 开始全量知识库深度整理 =================")
        if getattr(settings, "deep_organize_low_power_enabled", True):
            result = self._organize_entire_knowledge_base_low_power()
            print(f"[Organize] ================= 全量知识库整理完成 =================\n结果: {result.get('details', {})}")
            return result

        results = {}
        
        results["cleanup_removed"] = self.remove_low_quality_memories()
        
        results["l4_dedup"] = self.deduplicate_existing_l4()
        results["l6_dedup"] = self.deduplicate_existing_l6()
        
        l1_res = self._batch_process_l1_to_l2_smart()
        l2_res = self._batch_process_l2_to_l4_smart()
        results["l1_to_l2"] = l1_res.get("processed", 0)
        results["l2_to_l4"] = l2_res.get("processed", 0)
        
        reclassify_res = self.reclassify_default_l4()
        results["l4_reclassified"] = reclassify_res.get("reclassified", 0)
        results["reclassify_details"] = reclassify_res
        
        l4_to_l3_res = self.process_l4_to_l3()
        results["l4_to_l3"] = l4_to_l3_res.get("created", 0) + l4_to_l3_res.get("updated", 0)
        
        l4_res = self._batch_process_l4_to_l6_smart()
        results["l4_to_l6"] = l4_res.get("processed", 0)
        
        l6_to_l5_res = self.process_l6_to_l5()
        results["l6_to_l5"] = l6_to_l5_res.get("created", 0) + l6_to_l5_res.get("updated", 0)
        
        cleanup_res = self.cleanup_empty_categories()
        results["cleanup_details"] = cleanup_res
        
        print(f"[Organize] ================= 全量知识库整理完成 =================\n结果: {results}")
        return {"status": "success", "details": results}
    
    def quick_organize(self, progress_callback=None) -> Dict[str, Any]:
        """【快速整理】仅处理新增的pending记忆，增量处理
        
        整理流程：L1→L2 → L2→L4 → L4→L3(归类) → L4→L6 → L6→L5(归类)
        """
        print("[Quick Organize] 开始快速整理（仅处理新增）...")
        last_progress = -1

        def _report(p: int, msg: str):
            nonlocal last_progress
            try:
                p_int = int(p)
            except Exception:
                p_int = 0
            p_int = max(0, min(100, p_int))
            if p_int < last_progress:
                p_int = last_progress
            if callable(progress_callback) and (p_int != last_progress or msg):
                try:
                    progress_callback(p_int, msg)
                except Exception:
                    # progress reporting must not break the actual work
                    pass
            last_progress = p_int

        # 预留 95% 之后给 task_queue 做“收尾/完成”标记
        _report(5, "开始执行：快速整理")
        results = {}

        def _map_stage_progress(
            stage_start: int,
            stage_end: int,
            done: int,
            total: int,
            label: str,
        ):
            if total <= 0:
                _report(stage_end, f"{label}：无待处理数据")
                return
            ratio = max(0.0, min(1.0, done / total))
            p = stage_start + int((stage_end - stage_start) * ratio)
            _report(p, f"{label}：{done}/{total}")

        # 5% ~ 30%：L1 -> L2
        l1_res = self._batch_process_l1_to_l2_smart(
            progress_hook=lambda done, total: _map_stage_progress(5, 30, done, total, "L1→L2"),
        )
        results["l1_to_l2"] = l1_res.get("processed", 0)

        # 30% ~ 55%：L2 -> L4
        l2_res = self._batch_process_l2_to_l4_smart(
            progress_hook=lambda done, total: _map_stage_progress(30, 55, done, total, "L2→L4"),
        )
        results["l2_to_l4"] = l2_res.get("processed", 0)

        # 55% ~ 65%：L4 -> L3
        l4_to_l3_res = self.process_l4_to_l3(
            progress_hook=lambda done, total: _map_stage_progress(55, 65, done, total, "L4→L3(归类)"),
        )
        results["l4_to_l3"] = l4_to_l3_res.get("created", 0) + l4_to_l3_res.get("updated", 0)

        # 65% ~ 85%：L4 -> L6
        l4_res = self._batch_process_l4_to_l6_smart(
            progress_hook=lambda done, total: _map_stage_progress(65, 85, done, total, "L4→L6(技能提炼)"),
        )
        results["l4_to_l6"] = l4_res.get("processed", 0)

        # 85% ~ 95%：L6 -> L5
        l6_to_l5_res = self.process_l6_to_l5(
            progress_hook=lambda done, total: _map_stage_progress(85, 95, done, total, "L6→L5(归类)"),
        )
        results["l6_to_l5"] = l6_to_l5_res.get("created", 0) + l6_to_l5_res.get("updated", 0)

        _report(95, "快速整理完成：收尾中")

        print(f"[Quick Organize] 快速整理完成\n结果: {results}")
        return {"status": "success", "details": results}
    
    def _batch_process_l1_to_l2_smart(self, max_batches: Optional[int] = None, progress_hook=None) -> Dict[str, Any]:
        """智能分批处理L1→L2，根据数据量自动拆分批次（增量合并模式）"""
        from app.services.embedding_service import embedding_service
        
        all_pending_l1 = self.store.get_by_layer_and_status(1, 'pending')
        if not all_pending_l1:
            return {"message": "No pending L1 memories found", "processed": 0}
        
        total_chars = sum(len(m.get("content", "")) for m in all_pending_l1)
        avg_chars_per_memory = total_chars // len(all_pending_l1) if all_pending_l1 else 100
        batch_size = max(5, min(50, 3000 // avg_chars_per_memory))
        
        batches = [all_pending_l1[i:i + batch_size] for i in range(0, len(all_pending_l1), batch_size)]
        
        total_new = 0
        total_merged = 0
        
        print(f"[L1→L2] 总计{len(all_pending_l1)}条记录，拆分{len(batches)}批次处理")
        if max_batches and max_batches > 0:
            batches = batches[:max_batches]
        
        total_batches = len(batches)
        total_units = sum(len(b) for b in batches) if batches else 0
        done_units = 0
        for idx, batch in enumerate(batches):
            print(f"[L1→L2] 处理批次 {idx+1}/{len(batches)} ({len(batch)}条记录)")
            batch_new, batch_merged = self._process_l1_batch(batch)
            total_new += batch_new
            total_merged += batch_merged
            done_units += len(batch)
            if callable(progress_hook) and total_units > 0:
                try:
                    progress_hook(done_units, total_units)
                except Exception:
                    pass
        
        embedding_service.persist()
        
        return {
            "message": "L1 to L2 processing completed",
            "processed": total_new + total_merged,
            "new": total_new,
            "merged": total_merged,
            "total": len(all_pending_l1),
            "batches": len(batches)
        }
    
    def _split_text_with_overlap(self, text: str, max_chunk_size: int = None, overlap: int = None) -> List[str]:
        """将长文本切片，带有重叠区以保持上下文连贯（支持树状压缩）"""
        if max_chunk_size is None:
            max_chunk_size = getattr(settings, "compression_max_chunk_size", 3500)
        if overlap is None:
            overlap = getattr(settings, "compression_overlap", 300)

        if not text or len(text) <= max_chunk_size:
            return [text]

        if getattr(settings, "memory_compression_enabled", True):
            return self._tree_compress_split(text, max_chunk_size, overlap)

        return self._simple_split(text, max_chunk_size, overlap)

    def _tree_compress_split(self, text: str, max_chunk_size: int, overlap: int) -> List[str]:
        """树状摘要压缩：先按段落分割，再按语义边界切分"""
        paragraphs = text.split('\n\n')
        chunks = []
        current_chunk = ""

        for para in paragraphs:
            if not para.strip():
                continue

            if len(current_chunk) + len(para) + 2 <= max_chunk_size:
                current_chunk += ("\n\n" if current_chunk else "") + para
            else:
                if current_chunk:
                    chunks.append(current_chunk)
                if len(para) > max_chunk_size:
                    sub_chunks = self._simple_split(para, max_chunk_size, overlap)
                    chunks.extend(sub_chunks[:-1])
                    current_chunk = sub_chunks[-1] if sub_chunks else ""
                else:
                    current_chunk = para

        if current_chunk:
            chunks.append(current_chunk)

        tree_depth = getattr(settings, "compression_tree_depth", 2)
        if tree_depth > 1 and len(chunks) > 4:
            merged = []
            i = 0
            while i < len(chunks):
                group = chunks[i:i + tree_depth]
                if len(group) > 1:
                    merged_chunk = "\n\n---\n\n".join(group)
                    if len(merged_chunk) <= max_chunk_size * 1.5:
                        merged.append(merged_chunk)
                    else:
                        merged.extend(group)
                else:
                    merged.append(group[0])
                i += tree_depth
            chunks = merged

        return chunks

    def _simple_split(self, text: str, max_chunk_size: int, overlap: int) -> List[str]:
        """简单切片（原有逻辑）"""
        chunks = []
        start = 0
        text_len = len(text)

        while start < text_len:
            end = start + max_chunk_size
            if end < text_len:
                last_newline = text.rfind('\n', start, end)
                if last_newline != -1 and last_newline > start + (max_chunk_size // 2):
                    end = last_newline + 1

            chunks.append(text[start:end])
            start = end - overlap

            if start <= 0 or end >= text_len:
                start = end

        return chunks

    def _build_smart_batches(self, source_memories: List[Dict], target_layer: int, max_input_chars: int = 5000, template_chars: int = 1500) -> List[List[Dict]]:
        """
        动态累加分批：保证 (源记忆 + 对应相关目标层记忆 + prompt模板) 的总字符数 <= max_input_chars
        """
        from app.services.embedding_service import embedding_service
        import json

        # 1. 预计算所有的 embeddings 以便批量搜索
        valid_sources = []
        source_embeddings = []
        for mem in source_memories:
            emb = embedding_service.embed_text(mem["content"])
            valid_sources.append(mem)
            source_embeddings.append(emb)

        # 2. 批量搜索相关的上下文，以预估字符数
        search_list = [emb for emb in source_embeddings if emb is not None]
        related_map_per_source = [{} for _ in range(len(valid_sources))]
        
        if search_list:
            try:
                sim_threshold = getattr(settings, 'l2_to_l4_similarity_threshold', 0.85) if target_layer == 4 else getattr(settings, 'l4_to_l6_similarity_threshold', 0.85)
                batch_results = self.vector_store.search_similar_batch(search_list, k=3)
                res_idx = 0
                for i, emb in enumerate(source_embeddings):
                    if emb is not None:
                        similar = batch_results[res_idx]
                        res_idx += 1
                        for sim_id, score in similar:
                            if score >= sim_threshold:
                                existing = self.store.get_by_id(sim_id)
                                if existing and existing.get("layer") == target_layer:
                                    related_map_per_source[i][sim_id] = existing
            except Exception as e:
                print(f"[_build_smart_batches] 批量搜索相关上下文失败: {e}")

        # 3. 动态累加分批 (Greedy Accumulation)
        batches = []
        current_batch = []
        current_chars = 0
        
        for i, mem in enumerate(valid_sources):
            mem_json_chars = len(json.dumps({"id": mem["id"], "content": mem["content"]}, ensure_ascii=False))
            
            related_dict = related_map_per_source[i]
            related_json_list = [{"id": r["id"], "content": r["content"]} for r in related_dict.values()]
            related_chars = len(json.dumps(related_json_list, ensure_ascii=False)) if related_json_list else 0
            
            total = mem_json_chars + related_chars + template_chars
            
            # 单条数据超限的截断机制 (Edge Case)
            if total > max_input_chars:
                print(f"[Warning] 批次内遇到超大组合(总长{total} > {max_input_chars})，由于已启用分治切片，这里仅作安全隔离为单独批次")
                
                # 如果当前批次已有数据，先封批
                if current_batch:
                    batches.append(current_batch)
                    current_batch = []
                    current_chars = 0
                batches.append([mem])
                continue
                
            if current_chars + total > max_input_chars:
                if current_batch:
                    batches.append(current_batch)
                current_batch = [mem]
                current_chars = total
            else:
                current_batch.append(mem)
                current_chars += total
                
        if current_batch:
            batches.append(current_batch)
            
        return batches
    
    def _batch_process_l2_to_l4_smart(self, max_batches: Optional[int] = None, progress_hook=None) -> Dict[str, Any]:
        """智能分批处理L2→L4，根据字符数动态打包"""
        from app.services.embedding_service import embedding_service
        
        all_l2_memories = self.store.get_by_layer_and_status(2, 'pending')
        if not all_l2_memories:
            return {"message": "No pending L2 memories found", "processed": 0}
            
        # 预处理：长文本切片 (Map-Reduce 机制)
        expanded_mems = []
        for mem in all_l2_memories:
            content_len = len(mem.get("content", ""))
            if content_len > 4000:
                print(f"[长文本拆分] 发现超长L2记忆(ID:{mem['id']}), 长度:{content_len}字，执行分治切片")
                chunks = self._split_text_with_overlap(mem["content"], max_chunk_size=3500, overlap=300)
                for i, chunk in enumerate(chunks):
                    chunk_mem = mem.copy()
                    chunk_mem["content"] = f"[同源长文片段 {i+1}/{len(chunks)}]\n" + chunk
                    expanded_mems.append(chunk_mem)
            else:
                expanded_mems.append(mem)
        
        # 预留输出空间：输入上限设为 5000 字符 (~7500 tokens)
        batches = self._build_smart_batches(expanded_mems, target_layer=4, max_input_chars=5000, template_chars=1500)
        total_batches = len(batches)
        if max_batches and max_batches > 0:
            batches = batches[:max_batches]
        
        total_processed = 0
        print(f"[L2→L4] 总计{len(expanded_mems)}个切片(源自{len(all_l2_memories)}条)，动态拆分为{total_batches}批次，本轮执行{len(batches)}批次")
        
        total_units = sum(len(b) for b in batches) if batches else 0
        done_units = 0
        for idx, batch in enumerate(batches):
            print(f"[L2→L4] 处理批次 {idx+1}/{len(batches)} ({len(batch)}条)")
            batch_result = self._async_process_l2_batch(batch)
            total_processed += batch_result
            done_units += len(batch)
            if callable(progress_hook) and total_units > 0:
                try:
                    progress_hook(done_units, total_units)
                except Exception:
                    pass
        
        embedding_service.persist()
        
        return {
            "message": "L2 to L4 processing completed",
            "processed": total_processed,
            "total": len(all_l2_memories),
            "batches": len(batches),
            "remaining_batches": max(0, total_batches - len(batches))
        }
    
    def _batch_process_l4_to_l6_smart(self, max_batches: Optional[int] = None, progress_hook=None) -> Dict[str, Any]:
        """智能分批处理L4→L6，根据字符数动态打包"""
        from app.services.embedding_service import embedding_service
        
        all_l4_memories = self.store.get_by_layer_and_status(4, 'pending')
        if not all_l4_memories:
            return {"message": "No pending L4 memories found", "processed": 0}
            
        # 预处理：长文本切片 (Map-Reduce 机制)
        expanded_mems = []
        for mem in all_l4_memories:
            content_len = len(mem.get("content", ""))
            if content_len > 4000:
                print(f"[长文本拆分] 发现超长L4记忆(ID:{mem['id']}), 长度:{content_len}字，执行分治切片")
                chunks = self._split_text_with_overlap(mem["content"], max_chunk_size=3500, overlap=300)
                for i, chunk in enumerate(chunks):
                    chunk_mem = mem.copy()
                    chunk_mem["content"] = f"[同源长文片段 {i+1}/{len(chunks)}]\n" + chunk
                    expanded_mems.append(chunk_mem)
            else:
                expanded_mems.append(mem)
        
        # 预留输出空间：输入上限设为 5000 字符 (~7500 tokens)
        batches = self._build_smart_batches(expanded_mems, target_layer=6, max_input_chars=5000, template_chars=1500)
        total_batches = len(batches)
        if max_batches and max_batches > 0:
            batches = batches[:max_batches]
        
        total_processed = 0
        print(f"[L4→L6] 总计{len(expanded_mems)}个切片(源自{len(all_l4_memories)}条)，动态拆分为{total_batches}批次，本轮执行{len(batches)}批次")
        
        total_units = sum(len(b) for b in batches) if batches else 0
        done_units = 0
        for idx, batch in enumerate(batches):
            print(f"[L4→L6] 处理批次 {idx+1}/{len(batches)} ({len(batch)}条)")
            batch_result = self._async_process_l4_batch(batch)
            total_processed += batch_result
            done_units += len(batch)
            if callable(progress_hook) and total_units > 0:
                try:
                    progress_hook(done_units, total_units)
                except Exception:
                    pass
        
        embedding_service.persist()
        
        return {
            "message": "L4 to L6 processing completed",
            "processed": total_processed,
            "total": len(all_l4_memories),
            "batches": len(batches),
            "remaining_batches": max(0, total_batches - len(batches))
        }

    def _batch_process_l4_to_l6(self, l4_memories: List[Dict]) -> int:
        """尝试将一批L4记忆通过一次LLM调用进行全局提炼与合并(技能层)"""
        from app.services.embedding_service import embedding_service
        from app.services.inference.inference_service import inference_service
        import json
        import uuid
        
        # 1. 批量预计算所有L4的embedding（避免重复计算）
        l4_embeddings_list = []
        valid_l4_memories = []
        for mem in l4_memories:
            embedding = embedding_service.embed_text(mem["content"])
            if embedding:
                l4_embeddings_list.append(embedding)
                valid_l4_memories.append(mem)
        
        # 批量搜索相关L6（使用FAISS矩阵运算）
        related_l6_map = {}
        if l4_embeddings_list:
            batch_results = self.vector_store.search_similar_batch(l4_embeddings_list, k=3)
            for i, similar in enumerate(batch_results):
                for sim_id, score in similar:
                    if score >= getattr(settings, 'l4_to_l6_similarity_threshold', 0.85):
                        existing = self.store.get_by_id(sim_id)
                        if existing and existing.get("layer") == 6:
                            related_l6_map[sim_id] = existing
                            
        l4_json = [{"id": r["id"], "content": r["content"]} for r in l4_memories]
        l6_json = [{"id": r["id"], "category": r.get("category", "综合技能"), "content": r["content"]} for r in related_l6_map.values()]
        
        # 2. 组装全局 Prompt
        prompt = f"""你是一个高级技能提炼架构师。你的任务是将新的经验总结（待处理的新L4记录）合并提炼到现有的技能树（现有知识库参考）中，或者为它们创建新的技能结构。

【技能的本质定义】（参考ClawHub技能体系）
1. 技能是对**复杂工作流的打包**，不是简单的知识总结
2. 复杂技能可以**包含简单技能**（技能嵌套/组合）
3. 调用技能是为了**完成特定复杂工作**（如：部署项目、生成报告、分析数据、自动化测试）
4. 技能 = 触发条件 + 工作流步骤 + 子技能引用 + 工具定义 + 最佳实践

【现有知识库参考（L6记录）】
{json.dumps(l6_json, ensure_ascii=False, indent=2)}

【待处理的新记录（L4记录）】
{json.dumps(l4_json, ensure_ascii=False, indent=2)}

请仔细分析每一条待处理的新记录：
1. 技能是对经验的更高维度的抽象。如果新L4记录包含了可以增强现有L6技能的内容，请提取出新记录中的核心步骤或方法，作为**增量内容（Incremental Content）**追加到该L6记录中。注意：只提取新内容，绝对不要重复或概括现有L6记录中已经包含的内容。
2. 如果新L4记录包含全新的技能维度的知识，请为它创建一个新的L6记录，并起一个精准简短的中文分类名（2-8个字，使用动作导向名称，如"部署流程"、"代码审查"）。
3. 如果新记录只是普通的日记或陈述，没有包含任何"技能、步骤、法则、方法论"层面的价值，请将该记录判定为跳过。

【技能提炼标准】
✅ 应该提炼为技能的情况：
- 内容包含**多个步骤/流程**，可复用于完成特定复杂任务
- 内容描述了一个**完整的工作流**（从A到Z的完整过程）
- 内容涉及**调用其他技能/工具**来完成工作
- 用户明确要求"记住这个技能"、"以后这样操作"

❌ 不应提炼为技能的情况：
- 内容只是**单一事实/知识点**→ 保持为L4经验
- 内容是**日常对话/记录**→ 不提炼
- 内容是**一次性经验**→ 不提炼

【L5-L6中文命名强制规则】
1. 必须使用中文概括（技术名词可保留英文，如React、Python、Docker）
2. 严禁使用以下无意义名称："其他"、"通用"、"综合"、"未分类"、"默认"
3. 绝不允许在分类名中出现日期或时间（如"20260424"等）
4. 不使用下划线或连字符，直接用中文自然分隔
5. 避免使用缩写（如"dev"→"开发"、"config"→"配置"）
6. L6技能内容必须包含：技能名称、目标任务、触发条件、包含步骤/子技能、涉及工具、最佳实践、依赖的子技能、注意事项

你必须严格输出一个合法的 JSON 对象，不包含任何 Markdown 代码块包裹，也不包含任何其他文字解释。格式如下：
{{
  "updates": [
    {{
      "existing_id": "现有的L6记录ID",
      "new_category": "如果不变请保留原分类名，如果追加后技能范围变大可更新分类名（必须使用中文）",
      "incremental_content": "基于新记录提取出的、需要追加到现有L6记录末尾的新技能步骤或最佳实践（必须精简、干练，绝对不要包含或重复原有L6记录已经有的内容）"
    }}
  ],
  "inserts": [
    {{
      "category": "为新技能提取的简短中文分类名（2-8个字）",
      "content": "新提炼的技能内容（必须包含技能名称、目标任务、触发条件、步骤、工具、最佳实践、依赖子技能、注意事项的完整工作流）"
    }}
  ],
  "processed_l4_ids": ["成功提炼为技能（或被合并）的待处理L4记录的ID列表"],
  "skipped_l4_ids": ["那些不包含技能价值，被跳过提炼的L4记录的ID列表"]
}}
"""
        
        # 3. 调用大模型（对于推理模型，需预留充足的 max_tokens 以容纳 thinking 过程）
        local_max_tokens = min(8192, settings.local_llm_max_tokens)
        result = inference_service.generate_text(
            prompt, 
            model_path=settings.local_llm_model, 
            max_tokens=local_max_tokens,
            format="json"
        )
        
        if not result.get("success"):
            print(f"[Batch L4->L6] LLM 调用失败: {result.get('error')}")
            return -1
            
        generated_text = result.get("generated_text", "")
        
        # 4. 解析 JSON 并执行数据库操作
        try:
            parsed = self._parse_llm_json(generated_text)
            updates = parsed.get("updates", [])
            inserts = parsed.get("inserts", [])
            processed_l4_ids = parsed.get("processed_l4_ids", [])
            skipped_l4_ids = parsed.get("skipped_l4_ids", [])
            
            if not processed_l4_ids and not skipped_l4_ids and not updates and not inserts:
                print("[Batch L4->L6] LLM 返回了空的更新指令")
                return -1
                
            processed_count = 0
            
            # 处理 Updates
            for up in updates:
                l6_id = up.get("existing_id")
                incremental_content = up.get("incremental_content") or up.get("merged_content")
                new_cat = up.get("new_category")
                if not l6_id or not incremental_content: continue
                
                old_l6 = self.store.get_by_id(l6_id)
                if not old_l6: continue
                old_content = old_l6.get("content", "")
                
                new_content = old_content.strip() + "\n\n---\n\n" + incremental_content.strip()
                
                self.store.update(l6_id, new_content, category=new_cat, reason="批量追加了新的相关技能(L4->L6)")
                emb = embedding_service.embed_text(new_content, l6_id)
                old_meta = self.vector_store.get_metadata(l6_id) or {}
                if new_cat: old_meta["category"] = new_cat
                self.vector_store.save_embedding(l6_id, emb, old_meta)
                
                try:
                    from app.services.md_export_service import md_export_service
                    l6_dict = self.store.get_by_id(l6_id)
                    if l6_dict: md_export_service.export_memory_to_md(l6_dict)
                except: pass
                            
            # 处理 Inserts
            for ins in inserts:
                cat = ins.get("category", "综合技能")
                content = ins.get("content")
                if not content or "Mock summary" in content or "无有效技能" in content: continue
                if "Mock" in cat: cat = "综合技能"
                
                new_l6_id = str(uuid.uuid4())
                sn = self.generate_short_name(content, 6, cat)
                self.store.create(
                    memory_id=new_l6_id,
                    content=content,
                    category=cat,
                    layer=6, level=3, tags=[], source="batch_sync", confidence=0.9,
                    metadata={"batch_processed": True}, status="active", processed_status='processed',
                    short_name=sn
                )
                emb = embedding_service.embed_text(content, new_l6_id)
                self.vector_store.save_embedding(new_l6_id, emb, {"category": cat, "layer": 6, "level": 3})
                try:
                    from app.services.md_export_service import md_export_service
                    l6_dict = self.store.get_by_id(new_l6_id)
                    if l6_dict: md_export_service.export_memory_to_md(l6_dict)
                except: pass
                
            # 更新已处理的 L4 状态
            for l4_id in processed_l4_ids:
                self.store.update_processed_status(l4_id, 'skilled')
                processed_count += 1
                
            for l4_id in skipped_l4_ids:
                self.store.update_processed_status(l4_id, 'skipped')
                processed_count += 1
                
            return processed_count
            
        except json.JSONDecodeError as e:
            print(f"[Batch L4->L6] JSON 解析失败，将回退到逐条处理: {e}\n输出内容: {generated_text[:200]}...")
            return -1
        except Exception as e:
            print(f"[Batch L4->L6] 批量处理执行异常，将回退到逐条处理: {e}")
            return -1

    def process_l4_to_l6(self, max_chars: int = None) -> Dict[str, Any]:
        """处理L4总结记忆，调用本地大模型合并成技能后迁移到L6技能层"""
        if max_chars is None:
            max_chars = settings.l4_to_l6_max_chars
            
        llm_enabled = self.store.get_config("llm_enabled")
        llm_enabled = llm_enabled.lower() == "true" if llm_enabled else getattr(settings, "llm_enabled", True)
        
        if not llm_enabled:
            return {"message": "大模型处理已禁用，跳过L4到L6提炼", "processed": 0}
            
        try:
            self.reclassify_default_l4()
            
            all_l4_memories = self.store.get_by_layer_and_status(4, 'pending')
            if not all_l4_memories:
                return {"message": "No pending L4 memories found", "processed": 0}
            
            batches = self._pack_memories_by_chars(all_l4_memories, max_chars)
            
            total_processed = 0
            
            for batch in batches:
                batch_result = self._async_process_l4_batch(batch)
                if batch_result > 0:
                    total_processed += batch_result
            
            embedding_service.persist()
            
            return {
                "message": "L4 to L6 processing completed",
                "processed": total_processed,
                "total": len(all_l4_memories),
                "batches": len(batches)
            }
        except Exception as e:
            print(f"Error processing L4 to L6: {e}")
            return {"error": "PROCESSING_ERROR", "message": str(e)}
    
    def _async_process_l4_batch(self, l4_memories: List[Dict]) -> int:
        """异步处理单个L4批次"""
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(self._async_process_l4_batch_core(l4_memories))
        finally:
            loop.close()
    
    async def _async_process_l4_batch_core(self, l4_memories: List[Dict]) -> int:
        """异步核心处理L4批次"""
        batch_result = self._batch_process_l4_to_l6(l4_memories)
        if batch_result != -1:
            return batch_result
        
        print("[Fallback] 切换为逐条处理 L4->L6")
        
        processed_count = 0
        for memory in l4_memories:
            result = self._process_single_l4_to_l6(memory)
            processed_count += result
        
        return processed_count
    
    def _process_single_l4_to_l6(self, memory: Dict) -> int:
        """处理单条L4到L6转换（增量合并模式，不创建L5）"""
        query_embedding = embedding_service.embed_text(memory["content"])
        related_l6_id = None
        related_l6_content = None
        
        if query_embedding:
            similar = self.vector_store.search_similar(query_embedding, k=5)
            for sim_id, score in similar:
                if score >= getattr(settings, 'l4_to_l6_similarity_threshold', 0.85):
                    existing_memory = self.store.get_by_id(sim_id)
                    if (
                        existing_memory
                        and existing_memory.get("layer") == 6
                        and existing_memory.get("status") == "active"
                    ):
                        related_l6_id = sim_id
                        related_l6_content = existing_memory["content"]
                        break
        
        if related_l6_id and related_l6_content:
            merged_skill = self._merge_skill(related_l6_content, memory["content"])
            if merged_skill and "无有效技能" not in merged_skill and len(merged_skill) > 20:
                new_skill_category = self._normalize_skill_category(self._generate_skill_category(merged_skill))

                # L6 技能产品化：补齐/更新技能元数据（不破坏旧数据：可选字段 + 默认值）
                try:
                    existing = self.store.get_by_id(related_l6_id) or {}
                    old_meta = dict(existing.get("metadata") or {})
                    skill_meta = self._build_skill_metadata_from_content(
                        merged_skill,
                        base_meta=old_meta,
                        source_l4_id=memory.get("id"),
                    )
                    self.store.update(
                        related_l6_id,
                        merged_skill,
                        category=new_skill_category,
                        metadata=json.dumps(skill_meta, ensure_ascii=False),
                        reason="合并了新的相关技能(L4->L6)",
                    )
                except Exception:
                    # 元数据更新失败不影响主流程
                    self.store.update(related_l6_id, merged_skill, category=new_skill_category, reason="合并了新的相关技能(L4->L6)")
                
                embedding = embedding_service.embed_text(merged_skill, related_l6_id)
                vs_meta = self.vector_store.get_metadata(related_l6_id) or {}
                vs_meta["category"] = new_skill_category
                self.vector_store.save_embedding(related_l6_id, embedding, vs_meta)
                
                try:
                    from app.services.md_export_service import md_export_service
                    l6_memory_dict = self.store.get_by_id(related_l6_id)
                    if l6_memory_dict:
                        md_export_service.export_memory_to_md(l6_memory_dict)
                except Exception as e:
                    print(f"更新后的L6记忆MD文件导出失败: {e}")
                
                self.store.update_processed_status(memory["id"], 'skilled')
                return 1
            else:
                self.store.update_processed_status(memory["id"], 'skipped')
                return 0
        else:
            skill = self._generate_skill(memory["content"])
            
            if skill and "无有效技能" not in skill and len(skill) > 20:
                new_skill_category = self._normalize_skill_category(self._generate_skill_category(skill))
                
                skill_memory_id = str(uuid.uuid4())
                sn = self.generate_short_name(skill, 6, new_skill_category)

                # L6 技能产品化：为新技能补齐结构化元数据（来源/版本/适用条件/步骤/工具/预期产出）
                base_meta = dict(memory.get("metadata", {}) or {})
                base_meta["summary_memory_id"] = memory["id"]
                skill_meta = self._build_skill_metadata_from_content(
                    skill,
                    base_meta=base_meta,
                    source_l4_id=memory.get("id"),
                )

                self.store.create(
                    memory_id=skill_memory_id,
                    content=skill,
                    category=new_skill_category,
                    layer=6,
                    level=3,
                    tags=memory.get("tags"),
                    source=memory.get("source"),
                    confidence=memory.get("confidence", 0.9),
                    metadata=skill_meta,
                    status="active",
                    processed_status='processed',
                    short_name=sn
                )
                embedding = embedding_service.embed_text(skill, skill_memory_id)
                metadata_dict = {
                    "category": new_skill_category,
                    "layer": 6,
                    "level": 3,
                    "source": memory.get("source"),
                    "tags": memory.get("tags"),
                    "confidence": memory.get("confidence", 0.9),
                }
                self.vector_store.save_embedding(skill_memory_id, embedding, metadata_dict)
                
                try:
                    from app.services.md_export_service import md_export_service
                    l6_memory_dict = self.store.get_by_id(skill_memory_id)
                    if l6_memory_dict:
                        md_export_service.export_memory_to_md(l6_memory_dict)
                except Exception as e:
                    print(f"L6记忆MD文件导出失败: {e}")
                
                self.store.update_processed_status(memory["id"], 'skilled')
                return 1
            else:
                self.store.update_processed_status(memory["id"], 'skipped')
                return 0
        return 0

    def _build_skill_metadata_from_content(
        self,
        skill_content: str,
        base_meta: Optional[Dict[str, Any]] = None,
        source_l4_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        将技能文本解析为结构化元数据（写入 memory.metadata），并做默认值兜底以兼容旧数据。

        schema（MVP）：
        - skill_id, version, source_memory_ids, preconditions, tools, steps, expected_output
        - metrics（调用次数/最近调用/评分等）
        """
        meta = dict(base_meta or {})

        # skill_id / version
        if not meta.get("skill_id"):
            meta["skill_id"] = str(uuid.uuid4())
        try:
            meta["version"] = int(meta.get("version") or 1)
        except Exception:
            meta["version"] = 1

        # 来源链路（L4）
        source_ids = meta.get("source_memory_ids")
        if not isinstance(source_ids, list):
            source_ids = []
        if source_l4_id and source_l4_id not in source_ids:
            source_ids.append(source_l4_id)
        meta["source_memory_ids"] = source_ids

        # 解析结构化字段
        fields = self._extract_skill_fields(skill_content)
        meta.setdefault("preconditions", fields.get("preconditions", []))
        meta.setdefault("tools", fields.get("tools", []))
        meta.setdefault("steps", fields.get("steps", []))
        meta.setdefault("expected_output", fields.get("expected_output", ""))

        # 指标默认值（兼容旧数据）
        metrics = dict(meta.get("metrics") or {})
        metrics.setdefault("invoke_count", 0)
        metrics.setdefault("last_invoked_at", None)
        metrics.setdefault("rating_count", 0)
        metrics.setdefault("rating_sum", 0)
        metrics.setdefault("rating_avg", None)
        metrics.setdefault("negative_feedback_count", 0)
        metrics.setdefault("success_count", 0)
        metrics.setdefault("failure_count", 0)
        metrics.setdefault("last_feedback", None)
        meta["metrics"] = metrics

        return meta

    def _extract_skill_fields(self, skill_content: str) -> Dict[str, Any]:
        """
        从 LLM 生成的技能文本中提取：触发条件/步骤/工具/目标任务。
        解析失败时返回空默认值，保证不影响旧数据/主流程。
        """
        if not skill_content:
            return {"preconditions": [], "tools": [], "steps": [], "expected_output": ""}

        def _extract_block(header: str, next_headers: list[str]) -> str:
            import re

            pattern = rf"{re.escape(header)}\\s*\\n(?P<body>[\\s\\S]*?)\\n(?=(" + "|".join(re.escape(h) for h in next_headers) + r")|\\Z)"
            m = re.search(pattern, skill_content)
            return (m.group("body").strip() if m else "")

        import re

        expected_output = ""
        m_target = re.search(r"目标任务[：:]\s*([^\n]+)", skill_content)
        if m_target:
            expected_output = m_target.group(1).strip()

        trigger_block = _extract_block("触发条件：", ["包含步骤/子技能：", "涉及工具：", "最佳实践：", "依赖的子技能：", "注意事项："])
        preconditions = [re.sub(r"^\s*-\s*", "", line).strip() for line in trigger_block.splitlines() if line.strip().startswith("-")]

        tools_block = _extract_block("涉及工具：", ["最佳实践：", "依赖的子技能：", "注意事项："])
        tools = [re.sub(r"^\s*-\s*", "", line).strip() for line in tools_block.splitlines() if line.strip().startswith("-")]

        steps_block = _extract_block("包含步骤/子技能：", ["涉及工具：", "最佳实践：", "依赖的子技能：", "注意事项："])
        steps = []
        for line in steps_block.splitlines():
            line = line.strip()
            if re.match(r"^\d+\.", line):
                steps.append(line)

        return {
            "preconditions": preconditions,
            "tools": tools,
            "steps": steps,
            "expected_output": expected_output,
        }

    def _parse_llm_json(self, text: str) -> dict:
        import json
        import re
        if not text:
            return {}
            
        # 1. 移除 Markdown 代码块标记
        text = re.sub(r'^```(?:json)?\s*', '', text, flags=re.MULTILINE)
        text = re.sub(r'\s*```$', '', text, flags=re.MULTILINE)
        text = text.strip()
        
        # 2. 定位 JSON 边界 (兼容 {} 和 [])
        start_dict = text.find('{')
        end_dict = text.rfind('}')
        start_list = text.find('[')
        end_list = text.rfind(']')
        
        start_idx = min(s for s in [start_dict, start_list] if s != -1) if (start_dict != -1 or start_list != -1) else -1
        end_idx = max(e for e in [end_dict, end_list] if e != -1) if (end_dict != -1 or end_list != -1) else -1
        
        if start_idx != -1 and end_idx != -1 and end_idx >= start_idx:
            text = text[start_idx:end_idx+1]
            
        # 3. 修复常见的 JSON 格式错误：移除对象或数组末尾多余的逗号
        text = re.sub(r',\s*([\}\]])', r'\1', text)
        
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            print(f"[JSON Parse Error] 尝试解析失败: {str(e)} | 片段: {text[:200]}...")
            raise

    def _batch_process_l2_to_l4(self, l2_memories: List[Dict]) -> int:
        """尝试将一批L2记忆通过一次LLM调用进行全局提炼与合并"""
        from app.services.embedding_service import embedding_service
        from app.services.inference.inference_service import inference_service
        import json
        import uuid
        
        # 1. 批量预计算所有L2的embedding（避免重复计算）
        l2_embeddings_list = []
        valid_l2_memories = []
        for mem in l2_memories:
            embedding = embedding_service.embed_text(mem["content"])
            if embedding:
                l2_embeddings_list.append(embedding)
                valid_l2_memories.append(mem)
        
        # 批量搜索相关L4（使用FAISS矩阵运算）
        related_l4_map = {}
        if l2_embeddings_list:
            batch_results = self.vector_store.search_similar_batch(l2_embeddings_list, k=3)
            for i, similar in enumerate(batch_results):
                for sim_id, score in similar:
                    if score >= getattr(settings, 'l2_to_l4_similarity_threshold', 0.85):
                        existing = self.store.get_by_id(sim_id)
                        if existing and existing.get("layer") == 4:
                            related_l4_map[sim_id] = existing
                            
        l2_json = [{"id": r["id"], "content": r["content"]} for r in l2_memories]
        l4_json = [{"id": r["id"], "category": r.get("category", "未归档"), "content": r["content"]} for r in related_l4_map.values()]
        
        # 2. 组装全局 Prompt
        prompt = f"""你是一个高级知识架构师。你的任务是将新的碎片化记忆（待处理的新记录）合并整理到现有的经验总结（现有知识库参考）中，或者为它们创建新的经验总结分类。

【现有知识库参考（L4记录）】
{json.dumps(l4_json, ensure_ascii=False, indent=2)}

【待处理的新记录（L2记录）】
{json.dumps(l2_json, ensure_ascii=False, indent=2)}

请仔细分析每一条待处理的新记录：
1. 如果新记录的内容与某条现有L4记录高度相关，请提取出新记录中的核心经验/知识，作为**增量内容（Incremental Content）**追加到该L4记录中。注意：只提取新内容，绝对不要重复或概括现有L4记录中已经包含的内容。
2. 如果新记录包含全新的独立知识，不适合追加到任何现有L4中，请为它创建一个新的L4记录，并起一个精准简短的中文分类名（2-8个字，使用名词短语，如"Vue开发技巧"、"Docker配置"）。
3. 如果有多条新记录讲述同一个新主题，请将它们合并提取成一个全新的L4记录。

【L3-L6中文命名强制规则】
1. 必须使用中文概括（技术名词可保留英文，如React、Python、Docker）
2. 严禁使用以下无意义名称："其他"、"未分类"、"默认"、"综合"、"未归档"、"未知"
3. 绝不允许在分类名中出现日期或时间（如"20260424"等）
4. 不使用下划线或连字符，直接用中文自然分隔
5. 避免使用缩写（如"dev"→"开发"、"config"→"配置"）

你必须严格输出一个合法的 JSON 对象，不包含任何 Markdown 代码块包裹，也不包含任何其他文字解释。格式如下：
{{
  "updates": [
    {{
      "existing_id": "现有的L4记录ID",
      "new_category": "如果不变请保留原分类名，如果追加后主题有变可以更新分类名（必须使用中文）",
      "incremental_content": "基于新记录提取出的、需要追加到现有L4记录末尾的新经验总结（必须精简、干练，绝对不要包含或重复原有L4记录已经有的内容）"
    }}
  ],
  "inserts": [
    {{
      "category": "为新记录提取的简短中文分类名（2-8个字）",
      "content": "新记录的经验总结内容",
      "source_l2_ids": ["产生这条新总结的L2记录的ID列表"]
    }}
  ],
  "processed_l2_ids": ["你成功处理过的所有待处理L2记录的ID列表，未包含在内的将被视为处理失败"]
}}
"""
        
        # 3. 调用大模型（对于推理模型，需预留充足的 max_tokens 以容纳 thinking 过程）
        local_max_tokens = min(8192, settings.local_llm_max_tokens)
        result = inference_service.generate_text(
            prompt, 
            model_path=settings.local_llm_model, 
            max_tokens=local_max_tokens,
            format="json"
        )
        
        if not result.get("success"):
            print(f"[Batch L2->L4] LLM 调用失败: {result.get('error')}")
            return -1
            
        generated_text = result.get("generated_text", "")
        
        # 4. 解析 JSON 并执行数据库操作
        try:
            parsed = self._parse_llm_json(generated_text)
            updates = parsed.get("updates", [])
            inserts = parsed.get("inserts", [])
            processed_l2_ids = parsed.get("processed_l2_ids", [])
            
            if not processed_l2_ids and not updates and not inserts:
                print(f"[Batch L2->L4] LLM 返回了空的更新指令: {generated_text}")
                return -1
                
            processed_count = 0
            
            # 处理 Updates
            for up in updates:
                l4_id = up.get("existing_id")
                incremental_content = up.get("incremental_content") or up.get("merged_content")
                new_cat = up.get("new_category")
                if not l4_id or not incremental_content: continue
                
                old_l4 = self.store.get_by_id(l4_id)
                if not old_l4: continue
                old_content = old_l4.get("content", "")
                
                new_content = old_content.strip() + "\n\n---\n\n" + incremental_content.strip()
                
                self.store.update(l4_id, new_content, category=new_cat, reason="批量追加了新的相关记忆(L2->L4)")
                emb = embedding_service.embed_text(new_content, l4_id)
                old_meta = self.vector_store.get_metadata(l4_id) or {}
                if new_cat: old_meta["category"] = new_cat
                self.vector_store.save_embedding(l4_id, emb, old_meta)
                
                try:
                    from app.services.md_export_service import md_export_service
                    l4_dict = self.store.get_by_id(l4_id)
                    if l4_dict: md_export_service.export_memory_to_md(l4_dict)
                except: pass
                            
            # 处理 Inserts
            for ins in inserts:
                cat = ins.get("category", "综合记录")
                content = ins.get("content")
                if not content or "Mock summary" in content: continue
                if "Mock" in cat: cat = "综合记录"
                
                new_l4_id = str(uuid.uuid4())
                sn = self.generate_short_name(content, 4, cat)
                self.store.create(
                    memory_id=new_l4_id,
                    content=content,
                    category=cat,
                    layer=4, level=2, tags=[], source="batch_sync", confidence=0.8,
                    metadata={"batch_processed": True}, status="active", processed_status='pending',
                    short_name=sn
                )
                emb = embedding_service.embed_text(content, new_l4_id)
                self.vector_store.save_embedding(new_l4_id, emb, {"category": cat, "layer": 4, "level": 2})
                try:
                    from app.services.md_export_service import md_export_service
                    l4_dict = self.store.get_by_id(new_l4_id)
                    if l4_dict: md_export_service.export_memory_to_md(l4_dict)
                except: pass
                
            # 更新已处理的 L2 状态
            for l2_id in processed_l2_ids:
                self.store.update_processed_status(l2_id, 'summarized')
                processed_count += 1
                
            return processed_count
            
        except json.JSONDecodeError as e:
            print(f"[Batch L2->L4] JSON 解析失败，将回退到逐条处理: {e}\n输出内容: {generated_text[:200]}...")
            return -1
        except Exception as e:
            print(f"[Batch L2->L4] 批量处理执行异常，将回退到逐条处理: {e}")
            return -1

    def _merge_summary(self, old_content: str, new_content: str) -> str:
        """合并总结（保真拼接模式，对齐OpenClaw L1→L2策略）
        
        与OpenClaw的L1→L2合并策略一致：简单拼接，不调用LLM重写。
        旧内容完整保留，新内容直接追加，用分隔线隔开。
        信息保真由高阈值(0.85)保证：只有真正重复的内容才会走到合并路径。
        """
        return old_content.strip() + "\n\n---\n\n" + new_content.strip()
            
    def _generate_summary(self, content: str) -> str:
        """调用本地大模型生成总结"""
        try:
            from app.services.inference.inference_service import inference_service
            prompt = f"""你是一个高级的个人知识库整理专家。你的任务是将用户的日常对话、日志、笔记（L1/L2信息）完整地转化为长期记忆（L4经验总结）。

【核心原则：全量沉淀，拒绝遗漏】
1. L4代表的是日常生活中所有的有效记忆。因此，你必须像一个严谨的书记员，记录下原文中的所有有效信息、数据、名单和细节，只能去除纯粹的寒暄、毫无意义的语气词。
2. 绝对不能因为信息"太简单"或"不够高级"就丢弃它！即使是最普通的日常记录或新闻简报，也要原汁原味地保留它的完整事实和细节。
3. 如果原文包含列表、多个项目或详细的数据，必须在"详细记录"中完整重现，绝不允许只写一个概括性的短语。
4. 【命名强制规则】：主题名称必须是抽象的、可复用的名词短语（如"AI资讯简报"、"项目沟通记录"），**绝不允许**在"主题"中出现具体的日期或时间（如"20260424"等）。所有日期和时间必须且只能放在"核心要点"或"详细记录"中作为内容补充！
5. 【中文命名规则】：所有内容必须使用中文概括，技术名词可保留英文（React、Python、Docker等），不使用下划线、连字符或缩写。

要求必须使用以下结构输出：

主题: [抽象、可复用的核心主题，绝不含日期时间，不超过15个字，使用中文概括]

核心要点:
- [发生的时间/日期，如果原文有的话]
- [提取出所有有效信息]
- [不能遗漏原文的关键细节]

详细记录:
[用通顺的语言完整、详细地记录下原文表达的所有事情、数据、名单和事件。包含具体的日期。不要做抽象的概括，要保留事实的丰富度]

待总结内容：
{content}"""
            # 动态计算输出限制：根据输入长度动态放大输出上限
            # 最少给 2000，如果输入很长（比如 10000 字），就按输入长度的 0.8 倍作为最大输出限制
            dynamic_output_limit = max(2000, int(len(content) * 0.8))
            
            provider = self.store.get_config("llm_provider") or settings.llm_provider
            
            if provider == "external":
                # 对于外部计费API，严格限制上限，避免天价账单
                output_tokens = min(dynamic_output_limit, getattr(settings, 'external_llm_max_tokens', 8192))
            else:
                # 本地模型，按算力和配置上限分配
                output_tokens = min(dynamic_output_limit, settings.local_llm_max_tokens)
            
            result = inference_service.generate_text(prompt, model_path=settings.local_llm_model, max_tokens=output_tokens)
            if not result.get("success"):
                print(f"Warning: Model returned empty summary: {result.get('error')}. Falling back to content.")
                return content[:500]
            return result.get("generated_text", content[:500])
        except Exception as e:
            print(f"Error generating summary: {e}")
            return content[:500]  # 失败时返回内容的前500个字符
    
    def _generate_category(self, summary: str) -> str:
        """调用本地大模型生成分类"""
        try:
            from app.services.inference.inference_service import inference_service
            prompt = f"""请为以下总结内容生成一个简短的中文分类标签。

【强制命名规则】
1. 必须使用中文概括（技术名词可保留英文，如React、Python、Docker）
2. 长度限制：2-8个字，明确具体
3. 使用名词短语（如"Vue开发技巧"、"Linux运维指南"、"Docker配置"）
4. 严禁使用以下无意义名称："其他"、"未分类"、"默认"、"综合"、"未归档"、"未知"
5. 绝不允许出现日期或时间（如"20260424"等）
6. 不使用下划线或连字符，直接用中文自然分隔
7. 避免使用缩写（如"dev"→"开发"、"config"→"配置"）

只输出标签本身，不要输出其他任何多余的字符或标点符号：

{summary}"""
            result = inference_service.generate_text(prompt, model_path=settings.local_llm_model, max_tokens=50)
            
            if not result.get("success"):
                return "综合记录"
                
            # 清理和校验大模型输出
            text = result.get("generated_text", "").strip().replace('"', '').replace("'", "").replace(".", "").replace("_", "").replace("-", "")
            if not text or len(text) > 10 or "默认" in text or "其他" in text or "未归档" in text or "未分类" in text or "综合" in text:
                return "综合记录"
            return text
        except Exception as e:
            print(f"Error generating category: {e}")
            return "综合记录"
    
    def _merge_skill(self, old_content: str, new_content: str) -> str:
        """合并技能（保真拼接模式，对齐OpenClaw L1→L2策略）
        
        与OpenClaw的L1→L2合并策略一致：简单拼接，不调用LLM重写。
        旧技能完整保留，新内容直接追加，用分隔线隔开。
        信息保真由高阈值(0.85)保证：只有真正重复的技能才会走到合并路径。
        """
        return old_content.strip() + "\n\n---\n\n" + new_content.strip()

    def _generate_skill(self, content: str) -> str:
        """调用本地大模型提取技能

        技能定义（参考ClawHub技能体系）：
        - 技能是对复杂工作流的打包，不是简单的知识总结
        - 复杂技能可以包含简单技能（技能嵌套/组合）
        - 调用技能是为了完成特定复杂工作（如：部署项目、生成报告、分析数据）
        - 技能 = 触发条件 + 工作流步骤 + 子技能引用 + 工具定义 + 最佳实践
        """
        try:
            from app.services.inference.inference_service import inference_service
            prompt = f"""你是一个高级AI技能分析师。请评估以下内容是否包含足以构成一个"技能(Skill)"的知识。

【技能的本质定义】（参考ClawHub技能体系）
1. 技能是对**复杂工作流的打包**，不是简单的知识总结
2. 复杂技能可以**包含简单技能**（技能嵌套/组合）
3. 调用技能是为了**完成特定复杂工作**（如：部署项目、生成报告、分析数据、自动化测试）
4. 一个完整的技能必须包含：触发条件、工作流步骤、涉及工具、最佳实践

【技能提炼标准】
✅ 应该提炼为技能的情况：
- 内容包含**多个步骤/流程**，可复用于完成特定复杂任务
- 内容描述了一个**完整的工作流**（从A到Z的完整过程）
- 内容涉及**调用其他技能/工具**来完成工作
- 用户明确要求"记住这个技能"、"以后这样操作"
- 内容是**特定领域的最佳实践范式**（如：代码审查流程、发布流程）

❌ 不应提炼为技能的情况：
- 内容只是**单一事实/知识点**（如：Docker配置方法）→ 保持为L4经验
- 内容是**日常对话/记录**（如：今天开了个会）→ 不提炼
- 内容是**个人偏好**（如：我喜欢用VSCode）→ 保持为L4
- 内容是**一次性经验**，不具备复用价值 → 不提炼

【绝对强制规则】
如果待评估内容中明确包含"记住"、"生成技能"、"作为一个技能"、"这是一个技能"等类似的用户明确指令，你**必须**无条件将其提炼为一个技能，不得拒绝！

如果内容符合技能标准，请按以下结构输出：

技能名称：[清晰、动作导向的中文名称，2-8个字，如"前端项目部署全流程"、"技术文档自动生成"]

目标任务：[该技能解决的核心问题，描述清楚完成什么工作]

触发条件：
- [何时应该调用这个技能，如用户说"部署前端项目"]
- [需要什么前置条件]

包含步骤/子技能：
1. 【阶段名称】步骤描述
   - [具体操作1]
   - [具体操作2]
2. 【阶段名称】步骤描述（调用子技能：子技能名称）
   - [具体操作]
...

涉及工具：
- [工具1]（用途）
- [工具2]（用途）

最佳实践：
- [最佳实践1]
- [最佳实践2]

依赖的子技能：
- [子技能1名称]
- [子技能2名称]

注意事项：
- [注意事项1]
- [注意事项2]

如果该内容既没有用户的明确要求，也不包含足够形成上述复杂工作流技能的信息，请直接回复"无有效技能"。

待评估内容：
{content}"""
            dynamic_output_limit = max(3000, int(len(content) * 0.8))
            
            provider = self.store.get_config("llm_provider") or settings.llm_provider
            
            if provider == "external":
                output_tokens = min(dynamic_output_limit, getattr(settings, 'external_llm_max_tokens', 8192))
            else:
                output_tokens = min(dynamic_output_limit, settings.local_llm_max_tokens)
            
            result = inference_service.generate_text(prompt, model_path=settings.local_llm_model, max_tokens=output_tokens)
            if not result.get("success"):
                return "无有效技能"
            return result.get("generated_text", "无有效技能")
        except Exception as e:
            print(f"Error generating skill: {e}")
            return "无有效技能"
    
    def _generate_skill_category(self, skill: str) -> str:
        """调用本地大模型生成技能分类"""
        try:
            from app.services.inference.inference_service import inference_service
            prompt = f"""请为以下技能内容生成一个简短的中文分类标签。

【强制命名规则】
1. 必须使用中文概括（技术名词可保留英文，如React、Python、Docker）
2. 长度限制：2-6个字，明确具体
3. 使用动作导向名称（如"部署流程"、"代码审查"、"自动化测试"）
4. 严禁使用以下无意义名称："其他"、"通用"、"综合"、"未分类"、"默认"
5. 绝不允许出现日期或时间（如"20260424"等）
6. 不使用下划线或连字符，直接用中文自然分隔
7. 避免使用缩写（如"dev"→"开发"、"config"→"配置"）

只输出标签本身，不要输出其他任何多余的字符或标点符号：

{skill}"""
            result = inference_service.generate_text(prompt, model_path=settings.local_llm_model, max_tokens=settings.local_llm_max_tokens)
            
            if not result.get("success"):
                return "综合技能"
                
            # 清理和校验大模型输出
            text = result.get("generated_text", "").strip().replace('"', '').replace("'", "").replace(".", "").replace("_", "").replace("-", "")
            if not text or len(text) > 10 or "默认" in text or "通用" in text or "其他" in text or "综合" in text:
                return "综合技能"
            return text
        except Exception as e:
            print(f"Error generating skill category: {e}")
            return "综合技能"
    
    def _auto_create_subcategory(self, memory_id: str, content: str, category: str, layer: int):
        """自动创建子分类
        
        当分类下的记忆数量超过阈值时，AI自动创建子分类
        """
        import uuid
        
        # 获取该分类下的记忆数量
        existing_memories = self.store.get_memories_by_category(category, layer)
        memory_count = len(existing_memories)
        
        # 如果分类下已有记忆，尝试查找或创建子分类
        if memory_count > 0:
            # 获取该分类下的所有子分类
            parent_category = None
            categories = self.store.get_categories_by_layer(layer)
            for cat in categories:
                if cat.get('name') == category and not cat.get('parent_id'):
                    parent_category = cat
                    break
            
            # 如果找到父分类，检查是否需要创建子分类
            if parent_category:
                subcategories = self.store.get_categories_by_parent(parent_category['id'])
                
                # 当分类下记忆超过5条时，AI判断是否需要子分类
                if memory_count >= 5 and len(subcategories) == 0:
                    try:
                        from app.services.inference.inference_service import inference_service
                        
                        # 获取分类下的所有记忆内容
                        contents = [m['content'][:100] for m in existing_memories[:5]]
                        contents_text = '\n'.join([f"{i+1}. {c}" for i, c in enumerate(contents)])
                        
                        prompt = f"""请分析以下记忆内容，判断是否需要创建子分类来更好地组织这些记忆。

记忆内容：
{contents_text}

如果需要创建子分类，请返回子分类名称（每行一个，最多3个），如果不需要请返回"不需要"。

返回格式：
子分类1
子分类2
或
不需要"""
                        
                        result = inference_service.generate(prompt, model=settings.local_llm_model)
                        
                        if result and '不需要' not in result:
                            # 创建子分类
                            subcategories = [s.strip() for s in result.split('\n') if s.strip()]
                            for sub_name in subcategories[:3]:
                                sub_id = str(uuid.uuid4())
                                self.store.create_category(
                                    category_id=sub_id,
                                    name=sub_name,
                                    layer=layer,
                                    level=1,
                                    parent_id=parent_category['id']
                                )
                    except Exception as e:
                        print(f"AI创建子分类失败: {e}")

    def _pack_memories_by_chars(self, memories: List[Dict], max_chars: int) -> List[List[Dict]]:
        """按实际内容字数动态打包记忆，返回多个批次，每批不超过 max_chars 字符"""
        if not memories:
            return []
        
        batches = []
        current_batch = []
        current_chars = 0
        
        for mem in memories:
            mem_len = len(mem.get("content", ""))
            
            if not current_batch:
                current_batch.append(mem)
                current_chars += mem_len
            elif current_chars + mem_len <= max_chars:
                current_batch.append(mem)
                current_chars += mem_len
            else:
                batches.append(current_batch)
                current_batch = [mem]
                current_chars = mem_len
        
        if current_batch:
            batches.append(current_batch)
        
        return batches

    
    def update_memory_levels(self) -> Dict[str, Any]:
        """根据调用次数和可信度自动调整记忆的等级"""
        try:
            # 获取所有记忆
            all_memories = self.store.list_all(limit=10000)
            if not all_memories:
                return {"message": "No memories found", "updated": 0}
            
            updated_count = 0
            
            # 对每个记忆进行等级调整
            for memory in all_memories:
                # 只处理L3-L6层的记忆
                if memory["layer"] >= 3:
                    access_count = memory.get("access_count", 0)
                    confidence = memory.get("confidence", 1.0)
                    current_level = memory.get("level", 1)
                    
                    # 根据调用次数和可信度计算新等级
                    new_level = self._calculate_level(access_count, confidence)
                    
                    # 如果等级发生变化，更新等级
                    if new_level != current_level:
                        self.store.update_level(memory["id"], new_level)
                        updated_count += 1
            
            return {
                "message": "Memory levels updated successfully",
                "updated": updated_count,
                "total": len(all_memories)
            }
        except Exception as e:
            print(f"Error updating memory levels: {e}")
            return {"error": "UPDATE_ERROR", "message": str(e)}
    
    def _calculate_level(self, access_count: int, confidence: float) -> int:
        """根据调用次数和可信度计算记忆等级"""
        # 调用次数权重
        access_weight = min(access_count / 10, 1.0)  # 10次调用达到满分
        # 可信度权重
        confidence_weight = confidence
        # 综合得分
        score = (access_weight * 0.6) + (confidence_weight * 0.4)
        # 根据得分计算等级
        if score >= 0.9:
            return 5  # T5
        elif score >= 0.7:
            return 4  # T4
        elif score >= 0.5:
            return 3  # T3
        elif score >= 0.3:
            return 2  # T2
        else:
            return 1  # T1
            
    def cleanup_empty_categories(self, memory_limit: Optional[int] = None, directory_limit: Optional[int] = None) -> Dict[str, Any]:
        """清理无用的空分类(L3/L5)以及物理空文件夹"""
        print("[Cleanup] 开始执行知识库空分类与空目录清理...")
        results = {"memories_deleted": 0, "directories_deleted": 0}
        try:
            # 1. 查找孤立的L3和L5记忆（即该分类下没有任何L4或L6记忆）
            l3_memories = self.store.get_by_layer(3)
            l5_memories = self.store.get_by_layer(5)
            
            l4_categories = set(m.get("category") for m in self.store.get_by_layer(4) if m.get("category"))
            l6_categories = set(m.get("category") for m in self.store.get_by_layer(6) if m.get("category"))
            
            to_delete_ids = []
            
            for m in l3_memories:
                cat = m.get("category")
                # 如果这个L3分类在L4中不存在，或者是Mock脏数据
                if (cat and cat not in l4_categories) or "Mock" in str(cat) or "Mock" in str(m.get("content", "")):
                    to_delete_ids.append(m["id"])
                    
            for m in l5_memories:
                cat = m.get("category")
                # 如果这个L5分类在L6中不存在，或者是Mock脏数据
                if (cat and cat not in l6_categories) or "Mock" in str(cat) or "Mock" in str(m.get("content", "")):
                    to_delete_ids.append(m["id"])

            if memory_limit and memory_limit > 0:
                to_delete_ids = to_delete_ids[:memory_limit]
            
            # 删除这些无用的记忆和文件
            for mem_id in to_delete_ids:
                mem = self.store.get_by_id(mem_id)
                if mem:
                    try:
                        from app.services.md_export_service import md_export_service
                        md_export_service.delete_memory_file(mem)
                    except: pass
                    self.delete_memory(mem_id)
                    results["memories_deleted"] += 1
            
            # 2. 清理文件系统中的空文件夹
            import os
            from app.services.md_export_service import md_export_service
            base_path = md_export_service.get_knowledge_base_path()
            
            # 使用 topdown=False 从深层向浅层遍历
            for root, dirs, files in os.walk(base_path, topdown=False):
                for name in dirs:
                    if directory_limit and directory_limit > 0 and results["directories_deleted"] >= directory_limit:
                        break
                    # 跳过隐藏目录
                    if name.startswith('.'):
                        continue
                        
                    dir_path = os.path.join(root, name)
                    try:
                        # 如果目录下没有非隐藏文件
                        items = [i for i in os.listdir(dir_path) if not i.startswith('.')]
                        if not items:
                            import shutil
                            shutil.rmtree(dir_path)
                            results["directories_deleted"] += 1
                            print(f"[Cleanup] 已删除空目录: {dir_path}")
                    except Exception as e:
                        pass
                if directory_limit and directory_limit > 0 and results["directories_deleted"] >= directory_limit:
                    break
                        
            print(f"[Cleanup] 清理完成: 删除了 {results['memories_deleted']} 条空分类记忆，{results['directories_deleted']} 个空目录。")
            return results
        except Exception as e:
            print(f"[Cleanup] 清理失败: {e}")
            return results


# 全局记忆服务实例
memory_service = MemoryService()
