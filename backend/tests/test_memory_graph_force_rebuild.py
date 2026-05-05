import unittest
from unittest.mock import patch


class MemoryGraphForceRebuildTests(unittest.TestCase):
    def test_graph_endpoint_accepts_force_and_passes_through(self):
        """
        回归：前端切换存储路径后，需要强制重建图谱以立刻反映最新数据。
        """
        from app.api import memory_routes

        endpoint = getattr(memory_routes, "get_memory_graph", None)
        self.assertTrue(callable(endpoint), "get_memory_graph should exist")

        with patch.object(memory_routes.memory_graph_service, "build_graph") as mock_build:
            # build_graph 的返回值需要满足后续 nodes()/edges() 调用；直接用 networkx 空图即可
            import networkx as nx

            mock_build.return_value = nx.Graph()

            # 如果 endpoint 不支持 force 参数，这里会抛 TypeError，从而用例失败（红灯）
            endpoint(category=None, layer=None, limit=200, max_entities=80, force=True)

            mock_build.assert_called()
            # 关键：必须把 force=True 传给 build_graph
            self.assertTrue(mock_build.call_args.kwargs.get("force"), "build_graph(force=True) should be called")


if __name__ == "__main__":
    unittest.main()
