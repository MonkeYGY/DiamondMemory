import os
import unittest
from unittest.mock import MagicMock, patch

from app.services.inference.inference_service import InferenceService
from app.services.ollama_download_service import OllamaDownloadService


class OllamaAutostartGuardTests(unittest.TestCase):
    @patch("app.services.inference.inference_service.subprocess.Popen")
    @patch("app.services.inference.inference_service.requests.get")
    def test_inference_service_does_not_spawn_ollama_when_managed(self, mock_get, mock_popen):
        os.environ["DM_DISABLE_OLLAMA_AUTOSTART"] = "1"
        try:
            mock_get.side_effect = Exception("connection failed")
            service = InferenceService()
            ok = service.ensure_ollama_running()
            self.assertFalse(ok)
            mock_popen.assert_not_called()
        finally:
            os.environ.pop("DM_DISABLE_OLLAMA_AUTOSTART", None)

    @patch("app.services.ollama_download_service.subprocess.Popen")
    def test_ollama_download_service_does_not_spawn_when_managed(self, mock_popen):
        os.environ["DM_DISABLE_OLLAMA_AUTOSTART"] = "1"
        try:
            service = OllamaDownloadService(install_dir="/tmp/dm-test-ollama")
            service.is_installed = MagicMock(return_value=True)
            service.is_ollama_running = MagicMock(return_value=False)
            ok = service.start_ollama(11434)
            self.assertFalse(ok)
            mock_popen.assert_not_called()
        finally:
            os.environ.pop("DM_DISABLE_OLLAMA_AUTOSTART", None)


if __name__ == "__main__":
    unittest.main()

