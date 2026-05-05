"""记忆知识图谱服务模块（增强版）

基于 NetworkX 实现的记忆知识图谱，支持：
1. 实体-记忆关系图谱构建
2. Spreading Activation 传播激活算法
3. 社区检测（Louvain）
4. 路径查找与关联推荐
5. 图谱可视化数据生成
6. 自动增量更新与定期重建
"""
import time
import threading
import logging
from typing import List, Dict, Any, Optional, Set
from collections import defaultdict
import networkx as nx
from app.storage import SQLiteStore
from app.config import settings

logger = logging.getLogger(__name__)


class MemoryGraphService:
    def __init__(self):
        self.store = SQLiteStore()
        self._graph: Optional[nx.Graph] = None
        self._last_rebuild_time: float = 0
        self._lock = threading.Lock()
        self._entity_index: Dict[str, Set[str]] = defaultdict(set)
        self._category_index: Dict[str, Set[str]] = defaultdict(set)

    def build_graph(self, force: bool = False) -> nx.Graph:
        interval = getattr(settings, "graph_rag_rebuild_interval_minutes", 30) * 60
        now = time.time()

        if not force and self._graph is not None and (now - self._last_rebuild_time) < interval:
            return self._graph

        with self._lock:
            graph = nx.Graph()
            conn = self._get_conn()
            cursor = conn.cursor()

            cursor.execute("SELECT id, category, layer, status, confidence FROM memories WHERE status = 'active'")
            memories = cursor.fetchall()
            for mem in memories:
                mem_id, category, layer, status, confidence = mem
                graph.add_node(mem_id, type="memory", category=category, layer=layer, confidence=confidence or 1.0)
                if category:
                    self._category_index[category].add(mem_id)

            cursor.execute("SELECT memory_id, entity_text, entity_type FROM memory_entities")
            entities = cursor.fetchall()
            self._entity_index.clear()
            for ent in entities:
                mem_id, text, e_type = ent
                if graph.has_node(mem_id):
                    entity_node = f"entity:{text}"
                    if not graph.has_node(entity_node):
                        graph.add_node(entity_node, type="entity", entity_type=e_type, text=text)
                    graph.add_edge(mem_id, entity_node, edge_type="has_entity")
                    self._entity_index[text].add(mem_id)

            cursor.execute("""
                SELECT m1.id, m2.id
                FROM memories m1
                JOIN memories m2 ON m1.category = m2.category AND m1.layer != m2.layer AND m1.status = 'active' AND m2.status = 'active'
                WHERE m1.category IS NOT NULL AND m1.id < m2.id
            """)
            category_links = cursor.fetchall()
            for m1_id, m2_id in category_links:
                if graph.has_node(m1_id) and graph.has_node(m2_id):
                    if not graph.has_edge(m1_id, m2_id):
                        graph.add_edge(m1_id, m2_id, edge_type="same_category")

            self._graph = graph
            self._last_rebuild_time = time.time()
            logger.info(f"[MemoryGraph] 图谱构建完成: {graph.number_of_nodes()} 节点, {graph.number_of_edges()} 边")
            return graph

    def spreading_activation(self, seed_nodes: List[str], max_hops: int = None,
                              decay: float = None, min_activation: float = None) -> Dict[str, float]:
        if not seed_nodes:
            return {}

        if max_hops is None:
            max_hops = getattr(settings, "graph_rag_max_hops_enhanced", 3)
        if decay is None:
            decay = getattr(settings, "graph_rag_spreading_decay", 0.5)
        if min_activation is None:
            min_activation = getattr(settings, "graph_rag_min_activation", 0.1)

        graph = self.build_graph()
        if graph is None or graph.number_of_nodes() == 0:
            return {}

        activation_scores: Dict[str, float] = {}
        visited: Set[str] = set()

        queue = []
        for node in seed_nodes:
            if graph.has_node(node):
                queue.append((node, 1.0, 0))
                visited.add(node)

        while queue:
            current, current_score, hop = queue.pop(0)
            if hop >= max_hops:
                continue

            if current not in activation_scores or activation_scores[current] < current_score:
                activation_scores[current] = current_score

            for neighbor in graph.neighbors(current):
                if neighbor not in visited:
                    edge_data = graph.get_edge_data(current, neighbor, default={})
                    edge_type = edge_data.get("edge_type", "default")

                    if edge_type == "same_category":
                        edge_decay = decay * 0.8
                    elif edge_type == "has_entity":
                        edge_decay = decay
                    else:
                        edge_decay = decay * 0.6

                    new_score = current_score * edge_decay
                    if new_score >= min_activation:
                        visited.add(neighbor)
                        queue.append((neighbor, new_score, hop + 1))

        memory_activations = {}
        for node, score in activation_scores.items():
            if graph.nodes[node].get("type") == "memory":
                memory_activations[node] = score

        return memory_activations

    def get_related_memories(self, memory_id: str, max_depth: int = 2) -> List[Dict[str, Any]]:
        try:
            graph = self.build_graph()
            if not graph.has_node(memory_id):
                return []

            lengths = nx.single_source_shortest_path_length(graph, memory_id, cutoff=max_depth)

            related_ids = []
            for node, depth in lengths.items():
                if node != memory_id and graph.nodes[node].get("type") == "memory":
                    related_ids.append((node, depth))

            related_ids.sort(key=lambda x: x[1])

            results = []
            for r_id, depth in related_ids:
                mem = self.store.get_by_id(r_id)
                if mem and mem.get("status") == "active":
                    mem["graph_depth"] = depth
                    results.append(mem)

            return results
        except Exception as e:
            logger.error(f"图谱推理失败: {e}")
            return []

    def get_graph_boost_scores(self, query_entities: List[Dict[str, Any]]) -> Dict[str, float]:
        if not getattr(settings, "graph_rag_enabled", True):
            return {}

        graph = self.build_graph()
        if graph is None or graph.number_of_nodes() == 0:
            return {}

        seed_nodes = []
        for entity in query_entities:
            entity_text = entity.get("text", "")
            entity_node = f"entity:{entity_text}"
            if graph.has_node(entity_node):
                seed_nodes.append(entity_node)

        if not seed_nodes:
            return {}

        return self.spreading_activation(seed_nodes)

    def detect_communities(self) -> List[List[str]]:
        try:
            graph = self.build_graph()
            memory_nodes = [n for n in graph.nodes if graph.nodes[n].get("type") == "memory"]
            if len(memory_nodes) < 3:
                return []

            subgraph = graph.subgraph(memory_nodes)
            try:
                from networkx.algorithms.community import louvain_communities
                communities = louvain_communities(subgraph, resolution=1.0)
                return [list(c) for c in communities if len(c) >= 2]
            except ImportError:
                from networkx.algorithms.community import greedy_modularity_communities
                communities = greedy_modularity_communities(subgraph)
                return [list(c) for c in communities if len(c) >= 2]
        except Exception as e:
            logger.error(f"社区检测失败: {e}")
            return []

    def find_path(self, source_id: str, target_id: str) -> List[str]:
        try:
            graph = self.build_graph()
            if not graph.has_node(source_id) or not graph.has_node(target_id):
                return []
            path = nx.shortest_path(graph, source=source_id, target=target_id)
            return path
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return []
        except Exception as e:
            logger.error(f"路径查找失败: {e}")
            return []

    def get_graph_stats(self) -> Dict[str, Any]:
        graph = self.build_graph()
        if graph is None:
            return {"nodes": 0, "edges": 0}

        memory_nodes = sum(1 for n in graph.nodes if graph.nodes[n].get("type") == "memory")
        entity_nodes = sum(1 for n in graph.nodes if graph.nodes[n].get("type") == "entity")

        return {
            "nodes": graph.number_of_nodes(),
            "edges": graph.number_of_edges(),
            "memory_nodes": memory_nodes,
            "entity_nodes": entity_nodes,
            "categories": len(self._category_index),
            "unique_entities": len(self._entity_index),
            "density": round(nx.density(graph), 4) if graph.number_of_nodes() > 1 else 0,
        }

    def get_visualization_data(self, max_nodes: int = 100) -> Dict[str, Any]:
        graph = self.build_graph()
        if graph is None:
            return {"nodes": [], "edges": []}

        nodes = []
        edges = []
        memory_nodes = [n for n in graph.nodes if graph.nodes[n].get("type") == "memory"][:max_nodes]
        entity_nodes = [n for n in graph.nodes if graph.nodes[n].get("type") == "entity"][:max_nodes // 2]
        visible_nodes = set(memory_nodes + entity_nodes)

        for node_id in visible_nodes:
            node_data = graph.nodes[node_id]
            nodes.append({
                "id": node_id,
                "type": node_data.get("type"),
                "category": node_data.get("category", ""),
                "layer": node_data.get("layer"),
                "label": node_data.get("text", node_id[:8]),
            })

        for u, v in graph.edges():
            if u in visible_nodes and v in visible_nodes:
                edge_data = graph.get_edge_data(u, v, default={})
                edges.append({"source": u, "target": v, "type": edge_data.get("edge_type", "default")})

        return {"nodes": nodes, "edges": edges}

    def _get_conn(self):
        return self.store._get_conn()


memory_graph_service = MemoryGraphService()
