import unittest
from pathlib import Path


class OpenDevModeOrderTests(unittest.TestCase):
    def test_frontend_launch_block_comes_before_backend_bootstrap_block(self):
        # 测试运行时 cwd 在 DM开发辅助/，因此脚本路径应为 open_dev_mode.sh
        script = Path("open_dev_mode.sh").read_text(encoding="utf-8")

        frontend_index = script.index('npm run electron:dev')
        # 新策略：默认只启动 Electron 管理的后端；如启用 DM_BACKEND_MODE=python，仍允许脚本启动源码后端
        if 'backend_bootstrap.py' in script:
            backend_index = script.index('backend_bootstrap.py')
            self.assertLess(frontend_index, backend_index)


if __name__ == "__main__":
    unittest.main()
