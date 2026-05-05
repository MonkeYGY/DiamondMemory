import asyncio
import json
import time
import unittest
from unittest.mock import patch

from app.api import config_routes


class _StreamResp:
    status_code = 200

    def __init__(self, lines):
        self._lines = lines

    def iter_lines(self, decode_unicode=True):
        for line in self._lines:
            yield line


class _SlowStreamResp:
    status_code = 200

    def iter_lines(self, decode_unicode=True):
        for i in range(1, 5000):
            yield json.dumps({"status": "downloading", "total": 5000, "completed": i})
            time.sleep(0.001)


class ModelPullApiTests(unittest.TestCase):
    def setUp(self):
        config_routes._pull_progress.clear()
        config_routes._pull_threads.clear()
        if hasattr(config_routes, "_pull_cancel_flags"):
            config_routes._pull_cancel_flags.clear()

    def _wait_for_status(self, model_name: str, status: str, timeout_s: float = 2.0):
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            with config_routes._pull_progress_lock:
                p = config_routes._pull_progress.get(model_name) or {}
                if p.get("status") == status:
                    return p
            time.sleep(0.01)
        with config_routes._pull_progress_lock:
            return config_routes._pull_progress.get(model_name) or {}

    def test_pull_model_updates_progress(self):
        resp = _StreamResp([
            json.dumps({"status": "downloading", "total": 100, "completed": 1}),
            json.dumps({"status": "downloading", "total": 100, "completed": 50}),
            json.dumps({"status": "success"}),
        ])

        with patch("requests.post", return_value=resp):
            asyncio.run(config_routes.pull_model(model_name="bge-m3"))
            p = self._wait_for_status("bge-m3", "completed", timeout_s=1.0)

        self.assertEqual(p.get("status"), "completed")
        self.assertEqual(p.get("total"), 100)
        self.assertGreaterEqual(p.get("completed", 0), 50)
        self.assertGreaterEqual(p.get("progress", 0), 50)

    def test_cancel_pull_stops_progress(self):
        with patch("requests.post", return_value=_SlowStreamResp()):
            asyncio.run(config_routes.pull_model(model_name="bge-m3"))

            time.sleep(0.03)
            with config_routes._pull_progress_lock:
                before = int((config_routes._pull_progress.get("bge-m3") or {}).get("completed") or 0)

            config_routes.cancel_pull(model_name="bge-m3")
            time.sleep(0.03)

            with config_routes._pull_progress_lock:
                after = int((config_routes._pull_progress.get("bge-m3") or {}).get("completed") or 0)
                status = (config_routes._pull_progress.get("bge-m3") or {}).get("status")

        self.assertEqual(status, "cancelled")
        self.assertEqual(after, before)

    def test_pull_two_models_in_parallel(self):
        def _post(_url, json=None, stream=None, timeout=None):
            name = (json or {}).get("name") or ""
            if name == "bge-m3":
                return _StreamResp([
                    json_module.dumps({"status": "downloading", "total": 10, "completed": 1}),
                    json_module.dumps({"status": "success"}),
                ])
            return _StreamResp([
                json_module.dumps({"status": "downloading", "total": 20, "completed": 2}),
                json_module.dumps({"status": "success"}),
            ])

        json_module = json

        with patch("requests.post", side_effect=_post):
            asyncio.run(config_routes.pull_model(model_name="bge-m3"))
            asyncio.run(config_routes.pull_model(model_name="qwen3.5:4b"))

            p1 = self._wait_for_status("bge-m3", "completed", timeout_s=1.0)
            p2 = self._wait_for_status("qwen3.5:4b", "completed", timeout_s=1.0)

        self.assertEqual(p1.get("status"), "completed")
        self.assertEqual(p2.get("status"), "completed")


if __name__ == "__main__":
    unittest.main()

