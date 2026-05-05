import difflib
import re
from typing import Any, Dict, List

from app.storage import SQLiteStore
from app.config import settings


class CategoryNormalizationService:
    SOFT_PREFIXES = ("关于", "如何", "怎样", "浅析", "深入")
    SOFT_SUFFIXES = ("相关", "整理", "总结", "说明", "方案", "规范")
    CORE_SUFFIXES = ("自动化", "机制", "流程", "方法")
    SYNONYM_MAPPINGS = {
        "CONFIG": "配置",
        "DEPLOY": "部署",
        "发布": "部署",
        "BUG": "修复",
        "FIX": "修复",
        "ERROR": "报错",
        "ERR": "报错"
    }
    CATEGORY_LAYER_TO_MEMORY_LAYER = {3: 3, 5: 5}
    CATEGORY_LAYER_TO_CHILD_LAYER = {3: 4, 5: 6}

    def __init__(self):
        self.store = SQLiteStore()

    def _display_name(self, raw_name: str) -> str:
        cleaned = re.sub(r"[\s_\\/\-（）()]+", "", (raw_name or "").strip())
        return cleaned or "未分类"

    def _compare_key(self, raw_name: str) -> str:
        cleaned = self._display_name(raw_name).upper()
        
        # 剥离前缀
        for prefix in self.SOFT_PREFIXES:
            if cleaned.startswith(prefix) and len(cleaned) > len(prefix):
                cleaned = cleaned[len(prefix):]
                
        # 剥离软后缀
        for suffix in self.SOFT_SUFFIXES:
            if cleaned.endswith(suffix) and len(cleaned) > len(suffix) + 1:
                cleaned = cleaned[: -len(suffix)]
                
        # 剥离核心后缀
        for suffix in self.CORE_SUFFIXES:
            if cleaned.endswith(suffix) and len(cleaned) > len(suffix) + 1:
                cleaned = cleaned[: -len(suffix)]
                
        # 替换同义词根
        for syn_k, syn_v in self.SYNONYM_MAPPINGS.items():
            if syn_k in cleaned:
                cleaned = cleaned.replace(syn_k, syn_v)
                
        # 简单去除重复的重叠词（例如：修复修复 -> 修复）
        # 这里用一种简单的方式：如果字符串由两个相同的部分组成，就折叠。
        # 更通用的去重可以不做那么复杂，但为了应对上面的例子：
        half_len = len(cleaned) // 2
        if len(cleaned) > 1 and len(cleaned) % 2 == 0 and cleaned[:half_len] == cleaned[half_len:]:
            cleaned = cleaned[:half_len]
            
        return cleaned

    def _fuzzy_similarity(self, key_a: str, key_b: str) -> float:
        if not key_a or not key_b:
            return 0.0
        if key_a == key_b:
            return 1.0
        return difflib.SequenceMatcher(None, key_a, key_b).ratio()

    def resolve_category_name(self, candidate_name: str, category_layer: int) -> str:
        candidate_display = self._display_name(candidate_name)
        candidate_key = self._compare_key(candidate_display)
        existing_memories = self.store.get_by_layer(self.CATEGORY_LAYER_TO_MEMORY_LAYER[category_layer])

        for memory in existing_memories:
            existing_name = (memory.get("category") or "").strip()
            if existing_name and self._compare_key(existing_name) == candidate_key:
                return existing_name

        return candidate_display

    def build_merge_plan(self, category_layer: int) -> List[Dict[str, Any]]:
        category_memories = self.store.get_by_layer(self.CATEGORY_LAYER_TO_MEMORY_LAYER[category_layer])
        child_layer = self.CATEGORY_LAYER_TO_CHILD_LAYER[category_layer]

        items = []
        for memory in category_memories:
            category_name = (memory.get("category") or "").strip()
            if not category_name:
                continue
            items.append(memory)

        exact_groups: Dict[str, List[Dict[str, Any]]] = {}
        for item in items:
            ck = self._compare_key(item["category"])
            exact_groups.setdefault(ck, []).append(item)

        merge_plan = []
        for _, group in exact_groups.items():
            if len(group) >= 2:
                ranked = sorted(
                    group,
                    key=lambda item: (
                        -len(self.store.get_memories_by_category(item["category"], child_layer)),
                        len(item["category"]),
                        item["category"],
                    ),
                )
                target = ranked[0]
                redundant = ranked[1:]
                merge_plan.append(
                    {
                        "target_category": target["category"],
                        "target_category_id": target["id"],
                        "redundant_category_ids": [item["id"] for item in redundant],
                        "redundant_category_names": [item["category"] for item in redundant],
                        "child_layer": child_layer,
                    }
                )

        single_items = [
            item for group in exact_groups.values() if len(group) == 1
            for item in group
        ]
        if len(single_items) < 2:
            return merge_plan

        parent: Dict[int, int] = {i: i for i in range(len(single_items))}

        def find(x: int) -> int:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a: int, b: int):
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[rb] = ra

        keys = [self._compare_key(item["category"]) for item in single_items]
        for i in range(len(single_items)):
            for j in range(i + 1, len(single_items)):
                sim = self._fuzzy_similarity(keys[i], keys[j])
                if sim >= getattr(settings, 'category_fuzzy_similarity_threshold', 0.85):
                    union(i, j)

        fuzzy_groups: Dict[int, List[Dict[str, Any]]] = {}
        for idx in range(len(single_items)):
            root = find(idx)
            fuzzy_groups.setdefault(root, []).append(single_items[idx])

        for _, group in fuzzy_groups.items():
            if len(group) < 2:
                continue
            ranked = sorted(
                group,
                key=lambda item: (
                    -len(self.store.get_memories_by_category(item["category"], child_layer)),
                    len(item["category"]),
                    item["category"],
                ),
            )
            target = ranked[0]
            redundant = ranked[1:]
            merge_plan.append(
                {
                    "target_category": target["category"],
                    "target_category_id": target["id"],
                    "redundant_category_ids": [item["id"] for item in redundant],
                    "redundant_category_names": [item["category"] for item in redundant],
                    "child_layer": child_layer,
                }
            )

        return merge_plan


category_normalization_service = CategoryNormalizationService()
