import sys
import os
import sqlite3
import shutil

sys.path.append(os.path.join(os.getcwd(), 'backend'))

data_dir = "/Users/gengyun/Desktop/AI知识库"
db_path = os.path.join(data_dir, "memory.db")

print("Cleaning up database:", db_path)

with sqlite3.connect(db_path) as conn:
    cursor = conn.cursor()
    cursor.execute("DELETE FROM memories WHERE layer >= 2 AND (metadata NOT LIKE '%\"bypassed_ai\": true%' OR metadata IS NULL)")
    cursor.execute("UPDATE memories SET processed_status = 'pending' WHERE layer = 1")
    conn.commit()

for folder in ['总结经验', '技能']:
    p = os.path.join(data_dir, folder)
    if os.path.exists(p):
        shutil.rmtree(p)
        os.makedirs(p)

print("Cleanup complete!")
