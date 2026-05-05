import sys
import os
import shutil

sys.path.append(os.path.join(os.getcwd(), 'backend'))

# 清理 qdrant
p = "/Users/gengyun/Desktop/AI知识库/qdrant_storage"
if os.path.exists(p):
    shutil.rmtree(p)
print("qdrant cleared")
