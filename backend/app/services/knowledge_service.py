"""知识库服务模块

功能：
1. 扫描知识库文件系统，构建文件树
2. 读取Markdown文件内容
3. 用户手动创建笔记，调用大模型解析后存入数据库
4. L3-L6层记忆的文件目录映射
"""
import logging
import os
import re
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any

from app.config import settings
from app.storage import SQLiteStore
from app.storage import get_active_vector_store
from app.services.embedding_service import embedding_service

logger = logging.getLogger(__name__)


class KnowledgeService:
    """知识库服务类"""

    # 系统隐藏文件和文件夹列表，不在UI中显示
    HIDDEN_ITEMS = {
        'backups', 'qdrant_storage', 'temp',
        'memory.db', 'storage_config.json', 'storage_config.js',
        '.obsidian', '.DS_Store', '.git', '.trash',
        '记忆总结', 'embeddings.pkl', 'embedding_index.pkl'
    }

    def __init__(self):
        self.store = SQLiteStore()
        self.beijing_tz = timezone(timedelta(hours=8))
        # 文件树扫描缓存：避免前端频繁刷新时反复全量递归（大目录卡顿）
        # key: (base_path, layer_filter) -> {"tree": ..., "signature": ..., "max_sync_mtime": ...}
        self._file_tree_cache: Dict[tuple, Dict[str, Any]] = {}

    # L3/L5 对应知识库目录映射（兼容旧目录名）
    LAYER_ROOT_FOLDERS: Dict[int, List[str]] = {
        3: ["总结经验", "记忆总结"],
        5: ["技能"],
    }

    def get_knowledge_base_path(self) -> str:
        """获取知识库路径 — 使用用户存储路径（与系统数据目录分离）"""
        path = settings.storage_path
        os.makedirs(path, exist_ok=True)
        return path

    def _safe_resolve_kb_path(self, relative_path: str) -> str:
        """安全拼接知识库相对路径，防止路径遍历/越界访问。"""
        if not isinstance(relative_path, str):
            raise ValueError("非法路径")
        normalized = relative_path.replace("\\", "/").lstrip("/")
        if not normalized or ".." in normalized.split("/"):
            raise ValueError("非法路径")

        base_path = self.get_knowledge_base_path()
        base_abs = os.path.abspath(base_path)
        full_path = os.path.abspath(os.path.join(base_abs, normalized))
        if not (full_path.startswith(base_abs + os.sep) or full_path == base_abs):
            raise ValueError("非法路径")
        return full_path

    def scan_file_tree(
        self,
        root_path: str = None,
        layer_filter: int = None,
        per_dir_limit: int = 500,
        max_depth: int = 20,
        force_rescan: bool = False,
    ) -> List[Dict[str, Any]]:
        """扫描知识库目录，返回树形结构

        Args:
            root_path: 扫描根路径，默认使用配置的知识库路径
            layer_filter: 只扫描指定层级的目录 (3-记忆总结, 5-技能)
            per_dir_limit: 单个目录最多返回的子项数量（超限将分页）
            max_depth: 最大递归深度（超限将停止展开子目录）
            force_rescan: 强制全量重扫（跳过缓存），用于缓存失效兜底

        Returns:
            树形结构列表
        """
        # 注意：scan_file_tree 支持传入 root_path（主要用于测试/工具场景）。
        # 安全边界应由 API 层控制：生产接口会限制 root_path 不得超出 settings.storage_path。
        base_path = os.path.abspath(root_path) if root_path else os.path.abspath(self.get_knowledge_base_path())

        if not os.path.exists(base_path):
            return []

        # 1) 计算本次扫描的根目录集合（支持按层过滤）
        scan_roots = self._resolve_scan_roots(base_path, layer_filter)

        # 2) 缓存命中：优先利用 file_sync 最大更新时间（O(1) DB 查询）避免反复扫描大目录。
        cache_key = (os.path.abspath(base_path), layer_filter or 0, int(per_dir_limit), int(max_depth))
        max_sync_mtime = self._get_max_file_sync_mtime_for_scan(base_path, layer_filter)

        cached = None if force_rescan else self._file_tree_cache.get(cache_key)
        if cached:
            cached_max = cached.get("max_sync_mtime")
            # file_sync 表可能为空；为空时退化为目录 mtime 签名
            if (max_sync_mtime is not None) and (cached_max is not None) and (max_sync_mtime <= cached_max):
                return cached.get("tree", [])

        signature = self._compute_root_mtime_signature(scan_roots, max_sync_mtime)
        if cached and cached.get("signature") == signature:
            return cached.get("tree", [])

        # 3) 未命中缓存：执行真实递归扫描（使用 scandir，性能更好）
        tree: List[Dict[str, Any]] = []
        for root in scan_roots:
            # 当 scan_roots 是 base_path 本身时，直接写入 tree；
            # 当 scan_roots 是 base_path 下的子目录时，在 tree 顶层保留该目录节点，避免前端路径混乱。
            if os.path.abspath(root) == os.path.abspath(base_path):
                self._scan_directory_fast(root, base_path, tree, depth=0, per_dir_limit=per_dir_limit, max_depth=max_depth)
            else:
                rel = os.path.relpath(root, base_path)
                node = {"name": os.path.basename(root), "type": "folder", "path": rel, "children": []}
                self._scan_directory_fast(root, base_path, node["children"], depth=0, per_dir_limit=per_dir_limit, max_depth=max_depth)
                tree.append(node)

        self._file_tree_cache[cache_key] = {"tree": tree, "signature": signature, "max_sync_mtime": max_sync_mtime}
        return tree

    def _resolve_scan_roots(self, base_path: str, layer_filter: Optional[int]) -> List[str]:
        """根据 layer_filter 解析实际扫描根目录集合（根目录级剪枝）。"""
        if not layer_filter:
            return [base_path]

        candidates = self.LAYER_ROOT_FOLDERS.get(int(layer_filter), [])
        roots: List[str] = []
        for folder in candidates:
            p = os.path.join(base_path, folder)
            if os.path.isdir(p):
                roots.append(p)
                break

        # 如果映射目录不存在，则退化为全量扫描（保持兼容）
        return roots or [base_path]

    def _compute_root_mtime_signature(self, scan_roots: List[str], max_sync_mtime: Optional[float]) -> str:
        """计算扫描根目录签名（不枚举子文件）。

        - 目录 mtime：能捕获新增/删除/重命名
        - file_sync 最大 last_modified：能捕获系统内增量同步导致的变更

        目标：避免大目录下每次刷新都做全量 scandir。
        """
        parts: List[str] = [f"fsync:{int(max_sync_mtime or 0)}"]
        for root in scan_roots:
            try:
                st = os.stat(root)
                parts.append(f"{os.path.abspath(root)}:{int(st.st_mtime)}")
            except OSError:
                parts.append(f"{os.path.abspath(root)}:!")
        return "|".join(parts)

    def _get_max_file_sync_mtime_for_scan(self, base_path: str, layer_filter: Optional[int]) -> Optional[float]:
        """利用 file_sync 表做增量判断：只要同步表中该前缀的最大 last_modified 未变化，可复用缓存。"""
        prefix = None
        if layer_filter:
            folders = self.LAYER_ROOT_FOLDERS.get(int(layer_filter), [])
            # 用第一个映射作为前缀（兼容多映射）
            if folders:
                prefix = folders[0] + os.sep
        try:
            getter = getattr(self.store, "get_max_file_sync_last_modified", None)
            if not getter:
                return None
            return getter(prefix)
        except Exception:
            return None

    def _scan_directory_fast(
        self,
        dir_path: str,
        base_path: str,
        tree: list,
        *,
        depth: int,
        per_dir_limit: int,
        max_depth: int,
        offset: int = 0,
        limit: Optional[int] = None,
    ):
        """递归扫描目录（scandir 版本），支持：

        - per_dir_limit：大目录分页，避免一次性构建上万节点导致卡顿
        - max_depth：递归深度保护
        - offset/limit：用于“加载更多”分页请求
        """
        if depth > max_depth:
            return {"has_more": False, "next_offset": None, "total": 0}

        try:
            # 为保证分页稳定性，仍然排序；如果未来需要进一步提速，可改成基于 cursor 的无排序分页。
            entries = sorted(os.scandir(dir_path), key=lambda e: e.name)
        except (PermissionError, FileNotFoundError, NotADirectoryError):
            return {"has_more": False, "next_offset": None, "total": 0}

        visible: List[os.DirEntry] = []
        for e in entries:
            name = e.name
            if name in self.HIDDEN_ITEMS or name.startswith("."):
                continue
            try:
                if e.is_dir(follow_symlinks=False) or (e.is_file(follow_symlinks=False) and name.endswith(".md")):
                    visible.append(e)
            except OSError:
                continue

        # 分页切片
        start = max(0, int(offset))
        page_limit = int(limit) if limit is not None else int(per_dir_limit)
        end = start + page_limit
        page_entries = visible[start:end]
        has_more = end < len(visible)

        for entry in page_entries:
            name = entry.name
            full_path = entry.path
            relative_path = os.path.relpath(full_path, base_path)

            try:
                if entry.is_dir(follow_symlinks=False):
                    node = {"name": name, "type": "folder", "path": relative_path, "children": []}
                    if depth >= max_depth:
                        node["children_truncated"] = True
                    else:
                        # 子目录也做分页保护：只返回 per_dir_limit 个子项，超限可通过 scan_tree_children 再加载
                        child_meta = self._scan_directory_fast(
                            full_path,
                            base_path,
                            node["children"],
                            depth=depth + 1,
                            per_dir_limit=per_dir_limit,
                            max_depth=max_depth,
                            offset=0,
                            limit=per_dir_limit,
                        )
                        if (child_meta or {}).get("has_more"):
                            node["has_more"] = True
                            node["next_offset"] = (child_meta or {}).get("next_offset")
                    tree.append(node)
                elif entry.is_file(follow_symlinks=False) and name.endswith(".md"):
                    st = entry.stat(follow_symlinks=False)
                    node = {
                        "name": name,
                        "type": "file",
                        "path": relative_path,
                        "size": st.st_size,
                        "modified_at": datetime.fromtimestamp(st.st_mtime, self.beijing_tz).strftime("%Y-%m-%d %H:%M:%S"),
                    }
                    tree.append(node)
            except OSError:
                continue
        return {"has_more": has_more, "next_offset": end if has_more else None, "total": len(visible)}

    def scan_tree_children(
        self,
        root_path: str,
        *,
        dir_path: str,
        offset: int = 0,
        limit: int = 200,
        layer_filter: Optional[int] = None,
        per_dir_limit: int = 500,
        max_depth: int = 20,
        force_rescan: bool = False,
    ) -> Dict[str, Any]:
        """分页获取某个目录的直接子项（用于前端“加载更多”）。

        Args:
            root_path: 知识库根目录
            dir_path: 相对于 root_path 的目录路径
            offset/limit: 分页参数
            layer_filter: 层过滤（用于安全/一致性）
            per_dir_limit/max_depth: 与 scan_file_tree 一致的扫描保护参数
            force_rescan: 强制跳过缓存（通常不需要）
        """
        base_path = root_path or self.get_knowledge_base_path()
        if not base_path or not os.path.isdir(base_path):
            return {"children": [], "has_more": False, "next_offset": None, "total": 0}

        # 安全：拒绝绝对路径与 .. 跳转
        if not dir_path or ".." in dir_path.replace("\\", "/").split("/"):
            return {"children": [], "has_more": False, "next_offset": None, "total": 0}

        # layer_filter：只能访问映射根目录下的路径（避免越界）
        scan_roots = self._resolve_scan_roots(base_path, layer_filter)
        abs_dir = os.path.abspath(os.path.join(base_path, dir_path))
        if not any(abs_dir.startswith(os.path.abspath(r) + os.sep) or abs_dir == os.path.abspath(r) for r in scan_roots):
            return {"children": [], "has_more": False, "next_offset": None, "total": 0}

        children: List[Dict[str, Any]] = []
        meta = self._scan_directory_fast(
            abs_dir,
            base_path,
            children,
            depth=0,
            per_dir_limit=per_dir_limit,
            max_depth=max_depth,
            offset=offset,
            limit=limit,
        )
        return {
            "children": children,
            "has_more": bool(meta.get("has_more")),
            "next_offset": meta.get("next_offset"),
            "total": meta.get("total", len(children)),
        }

    def _scan_directory(self, dir_path: str, base_path: str, tree: list):
        """递归扫描目录"""
        try:
            entries = sorted(os.listdir(dir_path))
        except PermissionError:
            return

        for entry in entries:
            if entry in self.HIDDEN_ITEMS or entry.startswith('.'):
                continue

            full_path = os.path.join(dir_path, entry)
            relative_path = os.path.relpath(full_path, base_path)

            if os.path.isdir(full_path):
                node = {
                    'name': entry,
                    'type': 'folder',
                    'path': relative_path,
                    'children': []
                }
                self._scan_directory(full_path, base_path, node['children'])
                tree.append(node)
            elif entry.endswith('.md'):
                file_stat = os.stat(full_path)
                node = {
                    'name': entry,
                    'type': 'file',
                    'path': relative_path,
                    'size': file_stat.st_size,
                    'modified_at': datetime.fromtimestamp(file_stat.st_mtime, self.beijing_tz).strftime('%Y-%m-%d %H:%M:%S'),
                }
                tree.append(node)

    def read_file(self, relative_path: str) -> Optional[Dict[str, Any]]:
        """读取Markdown文件内容

        Args:
            relative_path: 相对于知识库根目录的路径

        Returns:
            文件内容，包含frontmatter和body
        """
        try:
            full_path = self._safe_resolve_kb_path(relative_path)
        except Exception:
            return None

        if not os.path.exists(full_path) or not full_path.lower().endswith('.md'):
            return None

        try:
            with open(full_path, 'r', encoding='utf-8') as f:
                content = f.read()

            frontmatter = {}
            body = content

            frontmatter_match = re.match(r'^---\n(.*?)\n---\n(.*)', content, re.DOTALL)
            if frontmatter_match:
                fm_text = frontmatter_match.group(1)
                body = frontmatter_match.group(2).strip()
                for line in fm_text.split('\n'):
                    if ':' in line:
                        key, value = line.split(':', 1)
                        frontmatter[key.strip()] = value.strip()

            file_stat = os.stat(full_path)

            return {
                'name': os.path.basename(full_path),
                'path': relative_path,
                'frontmatter': frontmatter,
                'body': body,
                'raw': content,
                'size': file_stat.st_size,
                'modified_at': datetime.fromtimestamp(file_stat.st_mtime, self.beijing_tz).strftime('%Y-%m-%d %H:%M:%S'),
            }
        except Exception as e:
            logger.warning("[KnowledgeService] 读取文件失败: %s", e)
            return None

    def create_note(self, title: str, content: str, category: str = None, tags: List[str] = None, source: str = 'user') -> Dict[str, Any]:
        """用户手动创建笔记

        流程：
        1. 调用大模型对内容进行解析和分类
        2. 生成合适的文件路径
        3. 写入Markdown文件
        4. 存储到数据库供AI查询

        Args:
            title: 笔记标题
            content: 笔记内容
            category: 分类（可选，AI可自动判断）
            tags: 标签（可选）
            source: 来源标识，默认user

        Returns:
            创建结果
        """
        llm_category = category
        llm_tags = tags or []

        if not llm_category or not llm_tags:
            ai_result = self._ai_parse_note(title, content)
            if not llm_category:
                llm_category = ai_result.get('category', '未分类')
            if not llm_tags:
                llm_tags = ai_result.get('tags', [])

        safe_category = self._sanitize_filename(llm_category)
        kb_path = self.get_knowledge_base_path()
        folder_path = os.path.join(kb_path, safe_category)
        os.makedirs(folder_path, exist_ok=True)

        safe_title = self._sanitize_filename(title)
        file_name = f"{safe_title}.md"
        file_path = os.path.join(folder_path, file_name)

        now = datetime.now(self.beijing_tz).strftime('%Y-%m-%d %H:%M:%S')
        tags_str = ', '.join([f'"{t}"' for t in llm_tags])

        md_content = f"""---
title: {title}
category: {llm_category}
tags: [{tags_str}]
source: {source}
created_at: {now}
---

# {title}

{content}
"""

        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(md_content)

            memory_id = self._store_note_to_db(
                title=title,
                content=content,
                category=llm_category,
                tags=llm_tags,
                source=source,
                file_path=os.path.relpath(file_path, kb_path)
            )

            return {
                'memory_id': memory_id,
                'file_path': os.path.relpath(file_path, kb_path),
                'category': llm_category,
                'tags': llm_tags,
                'message': '笔记创建成功'
            }
        except Exception as e:
            logger.error("[KnowledgeService] 创建笔记失败: %s", e)
            return {
                'error': 'CREATE_FAILED',
                'message': str(e)
            }

    def update_note(self, relative_path: str, title: str, content: str, category: str = None, tags: List[str] = None) -> Dict[str, Any]:
        """更新笔记内容"""
        try:
            full_path = self._safe_resolve_kb_path(relative_path)
        except Exception:
            return {'error': 'INVALID_PATH', 'message': '非法文件路径'}

        if not os.path.exists(full_path):
            return {'error': 'FILE_NOT_FOUND', 'message': '文件不存在'}

        existing = self.read_file(relative_path)
        frontmatter = existing.get('frontmatter', {}) if existing else {}

        if category:
            frontmatter['category'] = category
        if tags:
            frontmatter['tags'] = ', '.join([f'"{t}"' for t in tags])

        fm_lines = ['---']
        for key, value in frontmatter.items():
            fm_lines.append(f'{key}: {value}')
        fm_lines.append('---')

        now = datetime.now(self.beijing_tz).strftime('%Y-%m-%d %H:%M:%S')
        fm_header = '\n'.join(fm_lines)
        md_content = fm_header + '\n\n# ' + title + '\n\n> 更新时间: ' + now + '\n\n' + content + '\n'

        try:
            with open(full_path, 'w', encoding='utf-8') as f:
                f.write(md_content)

            return {
                'file_path': relative_path,
                'message': '笔记更新成功'
            }
        except Exception as e:
            logger.error("[KnowledgeService] 更新笔记失败: %s", e)
            return {'error': 'UPDATE_FAILED', 'message': str(e)}

    def toggle_bypass_ai(self, relative_path: str, bypass_ai: bool) -> Dict[str, Any]:
        """切换文件的 bypass_ai 状态"""
        base_path = self.get_knowledge_base_path()
        try:
            full_path = self._safe_resolve_kb_path(relative_path)
        except Exception:
            return {'error': 'INVALID_PATH', 'message': '非法文件路径'}
        
        if not os.path.exists(full_path):
            return {'error': 'FILE_NOT_FOUND', 'message': '文件不存在'}
            
        try:
            with open(full_path, 'r', encoding='utf-8') as f:
                content = f.read()
                
            import re
            # 匹配 frontmatter
            frontmatter_pattern = re.compile(r'^---\s*\n(.*?)\n---\s*\n', re.DOTALL)
            match = frontmatter_pattern.search(content)
            
            if match:
                fm_content = match.group(1)
                # 移除旧的 bypass_ai
                fm_lines = [line for line in fm_content.split('\n') if not line.strip().startswith('bypass_ai:')]
                # 添加新的 bypass_ai
                fm_lines.append(f'bypass_ai: {str(bypass_ai).lower()}')
                
                new_fm = '---\n' + '\n'.join(fm_lines) + '\n---\n'
                new_content = content[:match.start()] + new_fm + content[match.end():]
            else:
                # 如果没有 frontmatter，添加一个
                new_fm = f'---\nbypass_ai: {str(bypass_ai).lower()}\n---\n\n'
                new_content = new_fm + content
                
            with open(full_path, 'w', encoding='utf-8') as f:
                f.write(new_content)
                
            normalized_path = relative_path.replace('\\', '/')
            if not bypass_ai and (normalized_path.startswith('总结经验/') or normalized_path.startswith('技能/')):
                # 尝试将其移动回根目录
                import shutil
                file_name = os.path.basename(relative_path)
                new_relative_path = file_name
                new_full_path = os.path.join(base_path, new_relative_path)
                
                # 如果根目录已有同名文件，加个时间戳
                if os.path.exists(new_full_path):
                    new_relative_path = f"demoted_{int(datetime.now().timestamp())}_{file_name}"
                    new_full_path = os.path.join(base_path, new_relative_path)
                    
                shutil.move(full_path, new_full_path)
                
                # 删除旧的同步记录
                self.store.delete_file_sync_info(relative_path)
                
                # 如果 frontmatter 中有 memory_id，则删除那个 L4/L6 记忆
                if match:
                    import yaml
                    try:
                        fm_dict = yaml.safe_load(match.group(1))
                        mem_id = fm_dict.get('memory_id')
                        if mem_id:
                            from app.services.memory_service import memory_service
                            memory_service.delete_memory(mem_id)
                    except: pass
                    
                relative_path = new_relative_path
                
            # 立即触发一次该文件的同步
            self.sync_knowledge_base()
                
            return {
                'file_path': relative_path,
                'bypass_ai': bypass_ai,
                'message': '状态更新成功'
            }
        except Exception as e:
            logger.error("[KnowledgeService] 更新 bypass_ai 状态失败: %s", e)
            return {'error': 'UPDATE_FAILED', 'message': str(e)}

    def delete_note(self, relative_path: str) -> Dict[str, Any]:
        """删除笔记文件"""
        try:
            full_path = self._safe_resolve_kb_path(relative_path)
        except Exception:
            return {'error': 'INVALID_PATH', 'message': '非法文件路径'}

        try:
            if os.path.exists(full_path):
                os.remove(full_path)
                return {'message': '笔记删除成功'}
            return {'error': 'FILE_NOT_FOUND', 'message': '文件不存在'}
        except Exception as e:
            logger.error("[KnowledgeService] 删除笔记失败: %s", e)
            return {'error': 'DELETE_FAILED', 'message': str(e)}

    def search_notes(self, query: str) -> List[Dict[str, Any]]:
        """搜索知识库笔记"""
        try:
            memories = self.store.search_by_keyword(query, limit=50)
            results = []
            for m in memories:
                if m.get('file_path'):
                    results.append({
                        'id': m['id'],
                        'title': m.get('category', '未分类'),
                        'content_preview': m['content'][:200],
                        'file_path': m['file_path'],
                        'layer': m.get('layer'),
                        'created_at': m.get('created_at'),
                    })
            return results
        except Exception as e:
            logger.error("[KnowledgeService] 搜索笔记失败: %s", e)
            return []

    def get_l3_l5_tree(self) -> Dict[str, List[Dict[str, Any]]]:
        """获取L3(记忆总结)和L5(技能)的分类树结构

        Returns:
            包含memory_summary和skills两个根节点的树
        """
        categories_l3 = self.store.get_categories_by_layer(3)
        categories_l5 = self.store.get_categories_by_layer(5)

        return {
            'memory_summary': self._build_category_tree(categories_l3),
            'skills': self._build_category_tree(categories_l5),
        }

    def get_category_files(self, category_name: str, layer: int) -> List[Dict[str, Any]]:
        """获取指定分类下的文件列表

        Args:
            category_name: 分类名称
            layer: 层级(3或5)

        Returns:
            文件列表
        """
        kb_path = self.get_knowledge_base_path()

        layer_folder = '总结经验' if layer in [3, 4] else '技能'
        folder_path = os.path.join(kb_path, layer_folder, category_name)

        if not os.path.exists(folder_path):
            return []

        files = []
        for entry in os.listdir(folder_path):
            full_path = os.path.join(folder_path, entry)
            if entry.endswith('.md') and os.path.isfile(full_path):
                stat = os.stat(full_path)
                files.append({
                    'name': entry,
                    'path': os.path.relpath(full_path, kb_path),
                    'size': stat.st_size,
                    'modified_at': datetime.fromtimestamp(stat.st_mtime, self.beijing_tz).strftime('%Y-%m-%d %H:%M:%S'),
                })

        return sorted(files, key=lambda x: x['modified_at'], reverse=True)

    def _ai_parse_note(self, title: str, content: str) -> Dict[str, Any]:
        """调用大模型解析笔记内容，返回分类和标签"""
        try:
            from app.services.inference.inference_service import inference_service

            prompt = f"""请分析以下笔记内容，返回合适的分类和标签。

标题: {title}
内容: {content[:500]}

请严格按照以下JSON格式返回，不要其他任何内容:
{{
  "category": "分类名称",
  "tags": ["标签1", "标签2"]
}}
"""
            result = inference_service.generate(prompt, model=settings.local_llm_model)

            import json
            json_match = re.search(r'\{.*\}', result, re.DOTALL)
            if json_match:
                parsed = json.loads(json_match.group())
                return {
                    'category': parsed.get('category', '未分类'),
                    'tags': parsed.get('tags', [])
                }
        except Exception as e:
            logger.warning("[KnowledgeService] AI解析笔记失败: %s", e)

        return {'category': '未分类', 'tags': []}

    def sync_knowledge_base(self) -> Dict[str, Any]:
        """自动上行：扫描知识库增量并摄取"""
        import hashlib
        from app.services.memory_service import memory_service
        
        base_path = self.get_knowledge_base_path()
        synced_count = 0
        error_count = 0
        errors = []
        
        logger.info("[Sync] 开始扫描知识库: %s", base_path)
        
        for root, dirs, files in os.walk(base_path):
            # 跳过隐藏目录
            dirs[:] = [d for d in dirs if not d.startswith('.') and d not in self.HIDDEN_ITEMS]
            
            for file in files:
                if not file.endswith('.md') or file.startswith('.'):
                    continue
                    
                full_path = os.path.join(root, file)
                relative_path = os.path.relpath(full_path, base_path)
                
                try:
                    file_stat = os.stat(full_path)
                    mtime = file_stat.st_mtime
                    
                    # 检查数据库中是否已存在该文件的同步记录
                    sync_info = self.store.get_file_sync_info(relative_path)
                    
                    # 如果记录存在且修改时间一致，说明未改动，跳过
                    if sync_info and abs(sync_info['last_modified'] - mtime) < 1.0:
                        continue
                        
                    # 计算文件哈希，以防只是碰了时间戳
                    with open(full_path, 'rb') as f:
                        file_hash = hashlib.md5(f.read()).hexdigest()
                        
                    if sync_info and sync_info['file_hash'] == file_hash:
                        # 更新时间戳记录以避免下次重复算哈希
                        self.store.update_file_sync_info(relative_path, mtime, file_hash)
                        continue
                        
                    logger.info("[Sync] 发现新增或修改的 MD 文件: %s", relative_path)
                    
                    # 读取并解析文件
                    file_data = self.read_file(relative_path)
                    if not file_data:
                        continue
                        
                    title = file_data['name'].replace('.md', '')
                    content = file_data['body']
                    frontmatter = file_data.get('frontmatter', {})
                    
                    # 检查是否是知识库内部生成的 L3/L4/L5/L6 文件
                    normalized_path = relative_path.replace('\\', '/')
                    is_system_folder = normalized_path.startswith('总结经验/') or normalized_path.startswith('技能/')
                    
                    if is_system_folder:
                        memory_id = frontmatter.get('memory_id')
                        from app.services.memory_service import memory_service
                        
                        if memory_id:
                            # 用户修改了系统生成的总结/技能文件，直接更新对应的记忆，不创建 L1
                            existing_memory = memory_service.store.get_by_id(memory_id)
                            if existing_memory:
                                memory_service.store.update(memory_id, content=content, reason="用户通过知识库文件手动修改")
                                try:
                                    from app.services.embedding_service import embedding_service
                                    embedding = embedding_service.embed_text(content, memory_id)
                                    meta = memory_service.vector_store.get_metadata(memory_id) or {}
                                    memory_service.vector_store.save_embedding(memory_id, embedding, meta)
                                except Exception as e:
                                    logger.warning("[KnowledgeService] 更新记忆向量失败: %s", e)
                                # 记录同步成功并跳过后续创建 L1 的步骤
                                self.store.update_file_sync_info(relative_path, mtime, file_hash)
                                synced_count += 1
                                continue
                        
                        # 如果放在总结经验/技能目录下但没有 memory_id，说明是用户手动放入该目录的新文件
                        # 我们将其直接视为 L4 或 L6
                        layer = 6 if normalized_path.startswith('技能/') else 4
                        bypass_ai = True
                    else:
                        # 优先使用 frontmatter 中的 bypass_ai 状态
                        bypass_ai = str(frontmatter.get('bypass_ai', 'false')).lower() == 'true'
                    
                    category = frontmatter.get('category')
                    tags_str = frontmatter.get('tags', '[]')
                    
                    tags = []
                    try:
                        import ast
                        if tags_str.startswith('['):
                            tags = ast.literal_eval(tags_str)
                        else:
                            tags = [t.strip() for t in tags_str.split(',')]
                    except Exception:
                        logger.debug("[KnowledgeService] tags 解析失败，使用空列表")
                    
                    # 将用户本地文档作为记录摄取
                    # 如果用户设置了 bypass_ai: true，则直接将其作为 L4 经验存储，避免被大模型破坏或删减
                    memory_id = str(uuid.uuid4())
                    from app.services.memory_service import memory_service
                    
                    full_content = f"文件名：{title}\n内容：\n{content}"
                    if not is_system_folder:
                        layer = 4 if bypass_ai else 1
                        level = 2 if bypass_ai else 1
                    
                    processed_status = 'pending'
                    
                    # 查找并清理之前该文件生成的旧记忆（避免重复摄取导致多条记录）
                    try:
                        all_memories = memory_service.store.list_all()
                        for m in all_memories:
                            meta = m.get('metadata', {})
                            if isinstance(meta, str):
                                import json
                                try: meta = json.loads(meta)
                                except: meta = {}
                            if meta.get('file_path') == relative_path:
                                memory_service.delete_memory(m['id'])
                    except Exception as e:
                        logger.warning("[KnowledgeService] 清理旧版本文件记忆失败: %s", e)
                    
                    sn = memory_service.generate_short_name(full_content, layer, category or "本地文档")
                    memory_service.store.create(
                        memory_id=memory_id,
                        content=full_content,
                        category=category or "本地文档",
                        layer=layer,
                        level=level,
                        tags=tags,
                        source="auto_sync",
                        confidence=1.0,
                        metadata={"file_path": relative_path, "user_created": True, "bypassed_ai": bypass_ai},
                        status="active",
                        processed_status=processed_status,
                        short_name=sn
                    )
                    
                    # 如果是 bypass_ai 的 L4 经验，自动为其补齐 L3 目录层
                    if bypass_ai:
                        cat_name = category or "本地文档"
                        l3_memories = memory_service.store.get_by_layer(3)
                        existing_l3 = next((m for m in l3_memories if m.get("category") == cat_name), None)
                        
                        if not existing_l3:
                            l3_id = str(uuid.uuid4())
                            sn = memory_service.generate_short_name(cat_name, 3, cat_name)
                            memory_service.store.create(
                                memory_id=l3_id,
                                content=cat_name,
                                category=cat_name,
                                layer=3,
                                level=2,
                                tags=[cat_name],
                                source="auto_sync",
                                confidence=1.0,
                                metadata={"summary_memory_id": memory_id},
                                status="active",
                                processed_status="processed",
                                short_name=sn
                            )
                            try:
                                from app.services.embedding_service import embedding_service
                                l3_embed = embedding_service.embed_text(cat_name, l3_id)
                                memory_service.vector_store.save_embedding(l3_id, l3_embed, {"category": cat_name, "layer": 3, "level": 2})
                            except Exception as e:
                                logger.warning("[KnowledgeService] L3记忆向量存储失败: %s", e)
                    
                    try:
                        from app.services.embedding_service import embedding_service
                        embedding = embedding_service.embed_text(full_content, memory_id)
                        memory_service.vector_store.save_embedding(memory_id, embedding, {
                            "category": category or "本地文档",
                            "layer": layer,
                            "level": level,
                            "tags": tags,
                            "title": title
                        })
                    except Exception as e:
                        logger.warning("[KnowledgeService] 记忆向量存储失败: %s", e)
                    
                    # 记录同步成功
                    self.store.update_file_sync_info(relative_path, mtime, file_hash)
                    synced_count += 1
                    
                    # 取消删除：不再自动删除用户在根目录下的源文件，也不将其强制移动
                    # 如果用户开启 bypass_ai，文件依然留在原位，同时数据库中生成一份 L4 记忆以供检索。
                    
                except Exception as e:
                    logger.error("[Sync] 处理文件 %s 失败: %s", relative_path, e)
                    error_count += 1
                    errors.append(f"{relative_path}: {str(e)}")
                    
        logger.info("[Sync] 触发全量知识库整理...")
        try:
            organize_results = memory_service.organize_entire_knowledge_base()
            logger.info("[Sync] 整理完成: %s", organize_results)
        except Exception as e:
            logger.error("[Sync] 整理过程中出现异常: %s", e)

        return {
            "status": "success",
            "synced_count": synced_count,
            "error_count": error_count,
            "errors": errors,
            "organize_results": organize_results if 'organize_results' in locals() else None
        }

    def sync_user_docs(self, *, only_folder: str = "用户文档") -> Dict[str, Any]:
        """一键同步：扫描“用户文档/”下的 PDF/Word/Excel 并入库（最小可行）。

        设计约束：
        - 仅扫描用户文档目录，避免扫到系统生成目录/大目录导致卡顿
        - 复用 file_sync 做增量判定（mtime + hash）
        - 默认 disturb_free=True：只做保真索引（更快/更稳），不做结构化提炼
        """
        import hashlib
        from app.services.ingest.ingest_service import ingest_service

        base_path = self.get_knowledge_base_path()
        target_root = os.path.join(base_path, only_folder)
        os.makedirs(target_root, exist_ok=True)

        exts = {".pdf", ".doc", ".docx", ".xls", ".xlsx"}
        skipped = ingested = failed = scanned = 0
        errors: List[str] = []

        for root, dirs, files in os.walk(target_root):
            # 跳过隐藏目录
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in self.HIDDEN_ITEMS]

            # 防止 ingest 自摄取：跳过 raw/processed（这两个目录由 IngestService 写入）
            rel_root = os.path.relpath(root, base_path).replace("\\", "/")
            if rel_root.startswith("raw/") or rel_root.startswith("processed/"):
                continue

            for name in files:
                scanned += 1
                if name.startswith("."):
                    skipped += 1
                    continue
                ext = os.path.splitext(name)[1].lower()
                if ext not in exts:
                    skipped += 1
                    continue

                full_path = os.path.join(root, name)
                relative_path = os.path.relpath(full_path, base_path)
                try:
                    st = os.stat(full_path)
                    mtime = st.st_mtime
                    sync_info = self.store.get_file_sync_info(relative_path)
                    if sync_info and abs(sync_info["last_modified"] - mtime) < 1.0:
                        skipped += 1
                        continue

                    with open(full_path, "rb") as f:
                        file_hash = hashlib.md5(f.read()).hexdigest()
                    if sync_info and sync_info.get("file_hash") == file_hash:
                        self.store.update_file_sync_info(relative_path, mtime, file_hash)
                        skipped += 1
                        continue

                    # 摄取入库：disturb_free=True（仅保真索引）
                    ingest_service.ingest_file(full_path, disturb_free=True)
                    self.store.update_file_sync_info(relative_path, mtime, file_hash)
                    ingested += 1
                except Exception as e:
                    failed += 1
                    errors.append(f"{relative_path}: {e}")

        return {
            "ok": True,
            "scanned": scanned,
            "ingested": ingested,
            "skipped": skipped,
            "failed": failed,
            "errors": errors,
        }

    def _store_note_to_db(self, title: str, content: str, category: str, tags: List[str], source: str, file_path: str) -> str:
        """将笔记存储到数据库"""
        from app.services.memory_service import memory_service as _memory_service
        memory_id = str(uuid.uuid4())
        full_content = f"{title}\n\n{content}"
        vector_store = get_active_vector_store()

        sn = _memory_service.generate_short_name(full_content, 4, category)
        self.store.create(
            memory_id=memory_id,
            content=full_content,
            category=category,
            layer=4,
            level=1,
            tags=tags,
            source=source,
            confidence=1.0,
            metadata={'title': title, 'user_created': True},
            status='active',
            processed_status='pending' if source == 'auto_sync' else 'processed',
            short_name=sn
        )

        self.store.update_memory_file_path(memory_id, file_path)

        try:
            embedding = embedding_service.embed_text(full_content, memory_id)
            metadata_dict = {
                'category': category,
                'layer': 4,
                'source': source,
                'tags': tags,
                'title': title,
            }
            vector_store.save_embedding(memory_id, embedding, metadata_dict)
            embedding_service.persist()
        except Exception as e:
            logger.warning("[KnowledgeService] 笔记向量存储失败: %s", e)

        return memory_id

    def _build_category_tree(self, categories: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """构建分类树"""
        root_cats = [c for c in categories if not c.get('parent_id')]
        child_cats = [c for c in categories if c.get('parent_id')]

        children_map = {}
        for child in child_cats:
            parent_id = child.get('parent_id')
            if parent_id not in children_map:
                children_map[parent_id] = []
            children_map[parent_id].append(child)

        tree = []
        for root in root_cats:
            node = self._build_tree_node(root, children_map)
            tree.append(node)

        return tree

    def _build_tree_node(self, category: Dict[str, Any], children_map: Dict) -> Dict[str, Any]:
        """构建树节点"""
        node = {
            'id': category['id'],
            'name': category['name'],
            'layer': category['layer'],
            'level': category['level'],
            'memory_count': category.get('memory_count', 0),
            'children': []
        }

        cat_id = category['id']
        if cat_id in children_map:
            for child in children_map[cat_id]:
                child_node = self._build_tree_node(child, children_map)
                node['children'].append(child_node)

        return node

    def _sanitize_filename(self, filename: str) -> str:
        """清理文件名非法字符"""
        illegal_chars = r'[<>:"/\\|?*\x00-\x1f]'
        sanitized = re.sub(illegal_chars, '', filename)
        sanitized = sanitized.strip()
        if len(sanitized) > 50:
            sanitized = sanitized[:50]
        return sanitized


knowledge_service = KnowledgeService()
