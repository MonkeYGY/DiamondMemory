import os
import sys

# 让 `import app...` 在 pytest 下稳定可用（兼容不同 import-mode / rootdir 推断）。
BACKEND_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

