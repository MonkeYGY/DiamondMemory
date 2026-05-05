import unittest
from unittest.mock import patch


class MCPProductizationTests(unittest.TestCase):
    def test_mcp_create_memory_denied_when_source_blocked(self):
        from app.services.mcp_server_service import mcp_server_service

        with patch("app.services.source_access_control.source_access_control.is_source_blocked", return_value=True):
            resp = mcp_server_service.handle_tool_call(
                "create_memory",
                {"content": "hello", "source": "cursor"},
            )

        self.assertIn("error", resp)
        self.assertEqual(resp["error"].get("code"), "SOURCE_BLOCKED")

    def test_mcp_read_denied_when_read_switch_off(self):
        from app.services.mcp_server_service import mcp_server_service

        with patch("app.services.source_access_control.source_access_control.is_source_blocked", return_value=False), patch(
            "app.services.source_access_control.source_access_control.is_mcp_read_blocked", return_value=True, create=True
        ):
            resp = mcp_server_service.handle_tool_call(
                "search_memories",
                {"query": "hi", "filters": {"source": "cursor"}},
            )

        self.assertIn("error", resp)
        self.assertEqual(resp["error"].get("code"), "SOURCE_READ_BLOCKED")

    def test_self_check_degraded_when_ollama_down(self):
        from app.services import mcp_self_check_service

        class _VectorStore:
            def get_stats(self):
                return {"engine": "sqlite", "vector_count": 0}

        def _fake_get(url, timeout=5, **kwargs):
            # backend health ok；ollama 不可用
            if "/health" in url:
                return type("Resp", (), {"status_code": 200, "json": lambda self: {"status": "ok"}})()
            raise OSError("ollama down")

        with patch("app.storage.get_active_vector_store", return_value=_VectorStore(), create=True), patch(
            "requests.get", side_effect=_fake_get
        ), patch(
            "app.services.mcp_self_check_service._check_port_open", return_value=True
        ):
            result = mcp_self_check_service.run_self_check()

        self.assertEqual(result["overall_status"], "degraded")
        names = {c["name"]: c for c in result["checks"]}
        self.assertIn("ollama", names)
        self.assertIn(names["ollama"]["status"], ("fail", "degraded"))


if __name__ == "__main__":
    unittest.main()
