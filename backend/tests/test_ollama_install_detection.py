import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.services.ollama_download_service import OllamaDownloadService


class OllamaInstallDetectionTests(unittest.TestCase):
    def test_default_install_dir_uses_dm_user_data_dir_env(self):
        with tempfile.TemporaryDirectory() as tmp_user_data:
            OllamaDownloadService.reset_instance()
            os.environ["DM_USER_DATA_DIR"] = tmp_user_data
            try:
                service = OllamaDownloadService(install_dir=None)
                self.assertEqual(str(service.install_dir), tmp_user_data)
            finally:
                os.environ.pop("DM_USER_DATA_DIR", None)
                OllamaDownloadService.reset_instance()

    @patch("app.services.ollama_download_service.OllamaDownloadService._find_system_ollama", return_value=None)
    def test_is_installed_true_when_bundled_exists_even_if_copy_fails(self, _mock_find_system):
        with tempfile.TemporaryDirectory() as tmp_resources, tempfile.TemporaryDirectory() as tmp_install:
            OllamaDownloadService.reset_instance()
            resources_path = Path(tmp_resources)
            bundled = resources_path / "ollama" / "ollama"
            bundled.parent.mkdir(parents=True, exist_ok=True)
            bundled.write_bytes(b"fake-ollama")
            bundled.chmod(0o755)

            install_dir = Path(tmp_install)
            install_dir.chmod(0o500)

            os.environ["RESOURCE_PATH"] = str(resources_path)
            try:
                service = OllamaDownloadService(install_dir=str(install_dir))
                self.assertTrue(service.is_installed())
            finally:
                os.environ.pop("RESOURCE_PATH", None)
                try:
                    install_dir.chmod(0o700)
                except Exception:
                    pass
                OllamaDownloadService.reset_instance()


if __name__ == "__main__":
    unittest.main()
