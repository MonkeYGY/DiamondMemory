import unittest
from unittest.mock import patch

from app.api import config_routes


class StartupStatusApiTests(unittest.TestCase):
    def test_startup_status_marks_ollama_ready_when_service_reachable_but_no_models(self):
        endpoint = getattr(config_routes, "get_startup_status", None)
        self.assertTrue(callable(endpoint), "get_startup_status should exist")

        tags_payload = {"models": []}
        ps_payload = {"models": []}
        runtime_state = {
            "backend_ready": True,
            "ollama_ready": False,
            "warmup_phase": "starting_services",
            "llm_model_name": "qwen3.5:4b",
            "embedding_model_name": "bge-m3",
            "llm_loaded": False,
            "embedding_loaded": False,
            "last_error": "",
        }

        with patch("requests.get") as mock_get:
            mock_get.side_effect = [
                type("Resp", (), {"status_code": 200, "json": lambda self: tags_payload})(),
                type("Resp", (), {"status_code": 200, "json": lambda self: ps_payload})(),
            ]
            with patch.object(config_routes, "startup_runtime", runtime_state, create=True):
                response = endpoint()

        self.assertTrue(response["ollama_ready"])

    def test_startup_status_reports_installed_and_loaded_separately(self):
        endpoint = getattr(config_routes, "get_startup_status", None)
        self.assertTrue(callable(endpoint), "get_startup_status should exist")

        tags_payload = {
            "models": [
                {"name": "qwen3.5:4b"},
                {"name": "bge-m3"},
            ]
        }
        ps_payload = {
            "models": [
                {"name": "qwen3.5:4b"},
            ]
        }
        runtime_state = {
            "backend_ready": True,
            "ollama_ready": True,
            "warmup_phase": "warming_up",
            "llm_model_name": "qwen3.5:4b",
            "embedding_model_name": "bge-m3",
            "llm_loaded": False,
            "embedding_loaded": False,
            "last_error": "",
        }

        with patch("requests.get") as mock_get:
            mock_get.side_effect = [
                type("Resp", (), {"status_code": 200, "json": lambda self: tags_payload})(),
                type("Resp", (), {"status_code": 200, "json": lambda self: ps_payload})(),
            ]
            with patch.object(config_routes, "startup_runtime", runtime_state, create=True):
                response = endpoint()

        self.assertTrue(response["backend_ready"])
        self.assertTrue(response["ollama_ready"])
        self.assertTrue(response["llm_installed"])
        self.assertTrue(response["llm_loaded"])
        self.assertTrue(response["embedding_installed"])
        self.assertFalse(response["embedding_loaded"])
        self.assertEqual(response["warmup_phase"], "warming_up")

    def test_startup_status_reports_degraded_when_probe_fails(self):
        endpoint = getattr(config_routes, "get_startup_status", None)
        self.assertTrue(callable(endpoint), "get_startup_status should exist")

        runtime_state = {
            "backend_ready": True,
            "ollama_ready": False,
            "warmup_phase": "starting_services",
            "llm_model_name": "qwen3.5:4b",
            "embedding_model_name": "bge-m3",
            "llm_loaded": False,
            "embedding_loaded": False,
            "last_error": "",
        }

        with patch("requests.get", side_effect=Exception("boom")):
            with patch.object(config_routes, "startup_runtime", runtime_state, create=True):
                response = endpoint()

        self.assertFalse(response["ollama_ready"])
        self.assertEqual(response["warmup_phase"], "degraded")
        self.assertIn("boom", response["last_error"])


if __name__ == "__main__":
    unittest.main()
