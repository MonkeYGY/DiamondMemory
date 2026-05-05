import sys
import os
import sqlite3
import shutil

sys.path.append(os.path.join(os.getcwd(), 'backend'))

from app.services.md_export_service import md_export_service
from app.storage.sqlite_store import SQLiteStore

store = SQLiteStore()

data_dir = "/Users/gengyun/Desktop/AI知识库"

# 先清空物理文件夹 总结经验 和 技能 以防旧文件残留
for folder in ['总结经验', '技能']:
    p = os.path.join(data_dir, folder)
    if os.path.exists(p):
        shutil.rmtree(p)
        os.makedirs(p)

print("Cleared existing folders.")

# 重新导出 L4 和 L6
for layer in [4, 6]:
    memories = store.get_by_layer(layer)
    for m in memories:
        try:
            path = md_export_service.export_memory_to_md(m)
            print(f"Re-exported L{layer} memory to: {path}")
        except Exception as e:
            print(f"Error exporting memory {m.get('id')}: {e}")

print("Re-export complete!")
