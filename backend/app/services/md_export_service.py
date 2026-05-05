"""MD文件导出服务模块

功能：
1. 将记忆导出为Markdown文件
2. 实时同步数据库与文件系统
3. 支持自定义模板格式化
4. 维护知识库目录结构
"""
import hashlib
import logging
import os
import re
import shutil
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List
from app.config import settings
from app.storage import SQLiteStore

logger = logging.getLogger(__name__)


class MarkdownExportService:
    """Markdown文件导出服务"""
    
    def __init__(self):
        """初始化导出服务"""
        self.store = SQLiteStore()
        self.beijing_tz = timezone(timedelta(hours=8))
    
    def get_knowledge_base_path(self) -> str:
        """获取知识库路径 — 使用用户存储路径（与系统数据目录分离）"""
        from app.config import settings
        path = settings.storage_path
        os.makedirs(path, exist_ok=True)
        return path
    
    def set_knowledge_base_path(self, path: str) -> bool:
        """设置知识库路径"""
        os.makedirs(path, exist_ok=True)
        return self.store.set_config('knowledge_base_path', path, '知识库存储路径')

    def _get_root_folder(self, layer: int) -> str:
        if layer in (3, 4):
            return '总结经验'
        if layer in (5, 6):
            return '技能'
        return '其他'

    def _get_category_folder_name(self, memory: Dict[str, Any], category_path: str = None) -> str:
        if category_path:
            return category_path

        layer = memory.get('layer', 3)
        category = (memory.get('category') or '').strip()
        if not category:
            if layer == 4:
                category = '未归档'
            elif layer == 6:
                category = '未分类'
            else:
                category = '未分类'
        return self._sanitize_filename(category)

    def _get_target_folder_path(self, memory: Dict[str, Any], category_path: str = None) -> str:
        kb_path = self.get_knowledge_base_path()
        root_folder = self._get_root_folder(memory.get('layer', 3))
        folder_name = self._get_category_folder_name(memory, category_path)
        return os.path.join(kb_path, root_folder, folder_name)

    def _update_file_sync_info(self, relative_path: str, full_path: str) -> None:
        with open(full_path, 'rb') as f:
            file_hash = hashlib.md5(f.read()).hexdigest()
        self.store.update_file_sync_info(relative_path, os.path.getmtime(full_path), file_hash)

    def _delete_existing_export(self, relative_path: Optional[str]) -> None:
        if not relative_path:
            return

        kb_path = self.get_knowledge_base_path()
        full_path = os.path.join(kb_path, relative_path)

        try:
            if os.path.isfile(full_path):
                os.remove(full_path)
                self.store.delete_file_sync_info(relative_path)
            elif os.path.isdir(full_path):
                shutil.rmtree(full_path, ignore_errors=True)
        except Exception as e:
            logger.warning("[MdExport] 删除旧导出失败: %s", e)

    def _cleanup_empty_parent_dirs(self, start_dir: str, stop_dir: str) -> None:
        current_dir = start_dir
        stop_dir = os.path.abspath(stop_dir)
        while current_dir and os.path.abspath(current_dir).startswith(stop_dir):
            if os.path.abspath(current_dir) == stop_dir:
                break
            if not os.path.isdir(current_dir):
                break
            try:
                if os.listdir(current_dir):
                    break
                os.rmdir(current_dir)
                current_dir = os.path.dirname(current_dir)
            except OSError:
                break

    def _cleanup_legacy_category_index(self, memory: Dict[str, Any], folder_path: str) -> None:
        legacy_file_name = self._generate_filename(memory)
        legacy_file_path = os.path.join(folder_path, legacy_file_name)
        if not os.path.isfile(legacy_file_path):
            return

        try:
            os.remove(legacy_file_path)
            relative_path = os.path.relpath(legacy_file_path, self.get_knowledge_base_path())
            self.store.delete_file_sync_info(relative_path)
        except Exception as e:
            logger.warning("[MdExport] 清理旧目录索引失败: %s", e)
    
    def export_memory_to_md(self, memory: Dict[str, Any], category_path: str = None) -> str:
        """将单条记忆导出为MD文件
        
        Args:
            memory: 记忆数据字典
            category_path: 分类路径（可选，默认使用记忆的分类）
            
        Returns:
            文件路径
        """
        kb_path = self.get_knowledge_base_path()
        layer = memory.get('layer', 3)
        root_folder = self._get_root_folder(layer)
        folder_path = self._get_target_folder_path(memory, category_path)
        previous_relative_path = memory.get('file_path')
        os.makedirs(folder_path, exist_ok=True)

        if layer in (3, 5):
            if previous_relative_path:
                self._delete_existing_export(previous_relative_path)
            self._cleanup_legacy_category_index(memory, folder_path)
            self.store.update_memory_file_path(memory['id'], None)
            return folder_path

        # 生成文件名
        file_name = self._generate_filename(memory)
        file_path = os.path.join(folder_path, file_name)
        relative_path = os.path.relpath(file_path, kb_path)

        old_full_path = None
        if previous_relative_path:
            old_full_path = os.path.join(kb_path, previous_relative_path)
            if previous_relative_path != relative_path:
                self._delete_existing_export(previous_relative_path)

        # 生成MD内容
        content = self._generate_md_content(memory)

        # 写入文件
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)

        # 更新数据库中的文件路径
        self.store.update_memory_file_path(memory['id'], relative_path)
        self._update_file_sync_info(relative_path, file_path)

        if old_full_path and old_full_path != file_path:
            self._cleanup_empty_parent_dirs(os.path.dirname(old_full_path), os.path.join(kb_path, root_folder))
        return file_path
    
    
    def export_with_llm_format(self, memory: Dict[str, Any], model: str = None, 
                                prompt_template: str = None) -> str:
        """使用大模型格式化后导出MD文件
        
        Args:
            memory: 记忆数据字典
            model: 使用的大模型
            prompt_template: 格式化模板
            
        Returns:
            文件路径
        """
        # 获取配置
        if not model:
            model = self.store.get_config('llm_model') or 'qwen3.5:4b'
        
        if not prompt_template:
            prompt_template = self.store.get_config('md_export_format') or 'default'
        
        # 如果模板是'default'，使用默认导出
        if prompt_template == 'default':
            return self.export_memory_to_md(memory)
        
        # 使用大模型格式化内容
        try:
            from app.services.inference.inference_service import inference_service
            
            # 构建提示词
            prompt = prompt_template.format(
                content=memory.get('content', ''),
                category=memory.get('category', ''),
                tags=', '.join(memory.get('tags', [])),
                layer=memory.get('layer', 3),
                level=memory.get('level', 1)
            )
            
            # 调用大模型
            formatted_content = inference_service.generate(prompt, model=model)
            
            # 更新记忆内容
            memory['content'] = formatted_content
            
            # 导出
            return self.export_memory_to_md(memory)
        except Exception as e:
            logger.warning("[MdExport] 大模型格式化失败: %s", e)
            # 降级为默认导出
            return self.export_memory_to_md(memory)
    
    def _generate_filename(self, memory: Dict[str, Any]) -> str:
        """生成文件名"""
        content = memory.get('content', '')
        created_at = memory.get('created_at', '')
        
        title = ""
        # 尝试提取结构化输出的标题
        skill_match = re.search(r'技能名称:\s*([^\n]+)', content)
        if skill_match:
            title = skill_match.group(1).strip()
        else:
            summary_match = re.search(r'主题[：:]\s*([^\n]+)', content)
            if summary_match:
                title = summary_match.group(1).strip()
                
        # 提取失败则回退到直接截取第一行非空文字
        if not title:
            lines = [line.strip() for line in content.split('\n') if line.strip() and not line.startswith('---') and not line.startswith('#')]
            if lines:
                title = lines[0][:15]
            else:
                title = content[:15]
        
        # 清理文件名中的非法字符、markdown符号等
        safe_content = self._sanitize_filename(title)
        
        # 截取前15个字符作为命名（给足主题的空间）
        if len(safe_content) > 15:
            safe_content = safe_content[:15]
        
        # 优化：不再添加日期前缀，使用更简洁的命名
        file_name = f"{safe_content}.md"
        
        # 确保文件名不为空
        if not file_name or file_name == '.md':
            file_name = f"记录_{memory.get('id', 'unknown')[:4]}.md"
            
        return file_name
    
    def _sanitize_filename(self, filename: str) -> str:
        """清理文件名中的非法字符"""
        # 移除Windows/Linux/macOS文件名中的非法字符，以及常见的Markdown标记和标点符号
        illegal_chars = r'[<>:"/\\|?*\x00-\x1f#*`~\[\]{}()=+-]'
        sanitized = re.sub(illegal_chars, '', filename)
        # 移除常见的标点符号
        punctuation = r'[，。！？、；：""''（）【】《》\s]'
        sanitized = re.sub(punctuation, '', sanitized)
        # 移除首尾空格和换行符
        sanitized = sanitized.strip()
        # 限制长度
        if len(sanitized) > 50:
            sanitized = sanitized[:50]
        # 如果全被移除了，返回默认名
        return sanitized if sanitized else "记录"
    
    def _generate_md_content(self, memory: Dict[str, Any]) -> str:
        """生成MD文件内容"""
        # 生成Frontmatter元数据
        frontmatter = self._generate_frontmatter(memory)
        
        # 生成正文
        content = memory.get('content', '')
        category = memory.get('category', '')
        tags = memory.get('tags', [])
        level = memory.get('level', 1)
        layer = memory.get('layer', 3)
        
        # 提取结构化标题
        extracted_title = ""
        skill_match = re.search(r'技能名称:\s*([^\n]+)', content)
        if skill_match:
            extracted_title = skill_match.group(1).strip()
        else:
            summary_match = re.search(r'主题:\s*([^\n]+)', content)
            if summary_match:
                extracted_title = summary_match.group(1).strip()
                
        # 生成标题
        if extracted_title:
            title = f"# {extracted_title}"
        elif category:
            title = f"# {category}"
        else:
            title = "# 记忆"
        
        # 生成标签
        tag_line = ""
        if tags:
            tag_line = " ".join([f"`{tag}`" for tag in tags])
        
        # 等级标识
        level_badge = f"📊 等级: T{level}"
        
        # 层级标识
        layer_map = {
            1: 'L1 原始数据',
            2: 'L2 沉淀层',
            3: 'L3 分类层',
            4: 'L4 总结记忆',
            5: 'L5 技能分类',
            6: 'L6 技能'
        }
        layer_name = layer_map.get(layer, f'L{layer}')
        
        # 创建时间
        created_at = memory.get('created_at', '')
        
        # 处理状态
        processed_status = memory.get('processed_status', 'pending')
        status_map = {
            'pending': '⏳ 待处理',
            'processed': '✅ 已处理',
            'summarized': '📝 已总结',
            'skilled': '🎯 已提取技能'
        }
        status_text = status_map.get(processed_status, processed_status)
        
        # 组装完整内容
        md_content = f"""{frontmatter}

{title}

---

{level_badge} | 📁 {layer_name} | {status_text}

{tag_line}

> 📅 创建时间: {created_at}

---

{content}
"""
        return md_content
    
    def _generate_frontmatter(self, memory: Dict[str, Any]) -> str:
        """生成Frontmatter"""
        lines = ['---']
        lines.append(f'memory_id: {memory.get("id", "")}')
        lines.append(f'layer: {memory.get("layer", 3)}')
        lines.append(f'level: {memory.get("level", 1)}')
        
        category = memory.get('category', '')
        if category:
            lines.append(f'category: {category}')
        
        tags = memory.get('tags', [])
        if tags:
            lines.append(f'tags: [{", ".join(tags)}]')
        
        lines.append(f'confidence: {memory.get("confidence", 1.0)}')
        lines.append(f'created_at: {memory.get("created_at", "")}')
        lines.append(f'processed_status: {memory.get("processed_status", "pending")}')
        lines.append('---')
        
        return '\n'.join(lines)
    
    def delete_memory_file(self, memory: Dict[str, Any]) -> bool:
        """删除记忆对应的MD文件"""
        file_path = memory.get('file_path')
        
        kb_path = self.get_knowledge_base_path()
        layer = memory.get('layer', 3)

        try:
            if file_path:
                full_path = os.path.join(kb_path, file_path)
                if os.path.isfile(full_path):
                    os.remove(full_path)
                    self.store.delete_file_sync_info(file_path)
                    self._cleanup_empty_parent_dirs(
                        os.path.dirname(full_path),
                        os.path.join(kb_path, self._get_root_folder(layer))
                    )
                    return True

            if layer in (3, 5):
                folder_path = self._get_target_folder_path(memory)
                self._cleanup_legacy_category_index(memory, folder_path)
                if os.path.isdir(folder_path) and not os.listdir(folder_path):
                    os.rmdir(folder_path)
                return True

            if file_path and os.path.isdir(os.path.join(kb_path, file_path)):
                shutil.rmtree(os.path.join(kb_path, file_path), ignore_errors=True)
                return True
        except Exception as e:
            logger.error("[MdExport] 删除MD文件失败: %s", e)
            return False
        
        return False

    def rebuild_memory_exports(self) -> Dict[str, Any]:
        """按最新规则重建所有 L3-L6 的知识库映射"""
        rebuilt_count = 0
        failed_count = 0
        errors: List[str] = []

        all_memories = self.store.list_all(limit=100000)
        exportable_memories = [memory for memory in all_memories if memory.get('layer') in (3, 4, 5, 6)]

        for memory in sorted(exportable_memories, key=lambda item: (item.get('layer', 0), item.get('category', ''), item.get('id', ''))):
            try:
                self.export_memory_to_md(memory)
                rebuilt_count += 1
            except Exception as e:
                failed_count += 1
                errors.append(f"{memory.get('id')}: {e}")
                logger.warning("[MdExport] 重建导出失败: %s", e)

        deleted_memory_ids = self._cleanup_stale_system_exports()

        return {
            "status": "success",
            "message": "memory exports rebuilt",
            "rebuilt_count": rebuilt_count,
            "failed_count": failed_count,
            "deleted_memory_ids": deleted_memory_ids,
            "errors": errors[:20]
        }

    def _cleanup_stale_system_exports(self) -> List[str]:
        kb_path = self.get_knowledge_base_path()
        deleted_memory_ids: List[str] = []

        for root_folder in ('总结经验', '技能'):
            root_path = os.path.join(kb_path, root_folder)
            if not os.path.isdir(root_path):
                continue

            for current_root, _, files in os.walk(root_path, topdown=False):
                for file_name in files:
                    if not file_name.endswith('.md'):
                        continue

                    full_path = os.path.join(current_root, file_name)
                    relative_path = os.path.relpath(full_path, kb_path)

                    try:
                        with open(full_path, 'r', encoding='utf-8') as f:
                            content = f.read()
                    except Exception as e:
                        logger.warning("[MdExport] 读取系统导出文件失败: %s", e)
                        continue

                    memory_id_match = re.search(r'^memory_id:\s*(.+)$', content, re.MULTILINE)
                    if not memory_id_match:
                        continue

                    memory_id = memory_id_match.group(1).strip()
                    existing_memory = self.store.get_by_id(memory_id)
                    if existing_memory:
                        continue

                    try:
                        os.remove(full_path)
                        self.store.delete_file_sync_info(relative_path)
                        deleted_memory_ids.append(memory_id)
                    except Exception as e:
                        logger.warning("[MdExport] 删除失效系统导出失败: %s", e)

                if current_root != root_path and os.path.isdir(current_root):
                    try:
                        if not os.listdir(current_root):
                            os.rmdir(current_root)
                    except OSError:
                        pass

        return deleted_memory_ids
    
    def export_category_tree(self, layer: int) -> List[Dict[str, Any]]:
        """导出分类树结构（用于知识库页面展示）
        
        Args:
            layer: 层级（3或5）
            
        Returns:
            分类树结构
        """
        # 获取该层级的所有分类
        categories = self.store.get_categories_by_layer(layer)
        
        # 构建树结构
        tree = self._build_category_tree(categories)
        
        return tree
    
    def _build_category_tree(self, categories: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """构建分类树"""
        # 分离根分类和子分类
        root_categories = [c for c in categories if not c.get('parent_id')]
        child_categories = [c for c in categories if c.get('parent_id')]
        
        # 构建子分类映射
        children_map = {}
        for child in child_categories:
            parent_id = child.get('parent_id')
            if parent_id not in children_map:
                children_map[parent_id] = []
            children_map[parent_id].append(child)
        
        # 构建树
        tree = []
        for root in root_categories:
            node = self._build_tree_node(root, children_map)
            tree.append(node)
        
        return tree
    
    def _build_tree_node(self, category: Dict[str, Any], children_map: Dict) -> Dict[str, Any]:
        """构建单个树节点"""
        node = {
            'id': category['id'],
            'name': category['name'],
            'layer': category['layer'],
            'level': category['level'],
            'memory_count': category.get('memory_count', 0),
            'children': []
        }
        
        # 添加子分类
        category_id = category['id']
        if category_id in children_map:
            for child in children_map[category_id]:
                child_node = self._build_tree_node(child, children_map)
                node['children'].append(child_node)
        
        return node


# 全局导出服务实例
md_export_service = MarkdownExportService()
