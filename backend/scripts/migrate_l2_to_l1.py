"""数据迁移脚本：将错误写入L2层的原始记录迁移到L1层"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.memory_service import memory_service
from app.storage.vector_store import get_vector_store
from app.services.embedding_service import embedding_service

def main():
    store = memory_service.store
    vector_store = get_vector_store()
    
    conn = store._get_conn()
    cursor = conn.cursor()
    
    # 查看迁移前状态
    print("=== 数据迁移前 ===")
    for layer in range(1, 7):
        cursor.execute("SELECT COUNT(*) FROM memories WHERE layer = ?", (layer,))
        count = cursor.fetchone()[0]
        print(f"L{layer}层: {count} 条")
    
    l2_before = cursor.execute("SELECT COUNT(*) FROM memories WHERE layer = 2").fetchone()[0]
    print(f"\n待迁移的L2记录数: {l2_before}")
    
    if l2_before == 0:
        print("没有需要迁移的记录")
        return
    
    # 执行迁移
    print("\n=== 执行迁移: L2 -> L1 ===")
    cursor.execute("UPDATE memories SET layer = 1, level = 1 WHERE layer = 2")
    migrated = cursor.rowcount
    conn.commit()
    print(f"已迁移 {migrated} 条记录从L2到L1")
    
    # 验证迁移结果
    print("\n=== 数据迁移后 ===")
    for layer in range(1, 7):
        cursor.execute("SELECT COUNT(*) FROM memories WHERE layer = ?", (layer,))
        count = cursor.fetchone()[0]
        print(f"L{layer}层: {count} 条")
    
    # 更新向量库元数据
    print("\n=== 更新向量库元数据 ===")
    cursor.execute("SELECT id FROM memories WHERE layer = 1")
    l1_ids = [row[0] for row in cursor.fetchall()]
    updated = 0
    for mem_id in l1_ids:
        meta = vector_store.get_metadata(mem_id)
        if meta and meta.get("layer") != 1:
            meta["layer"] = 1
            meta["level"] = 1
            embedding = vector_store.get_embedding(mem_id)
            if embedding:
                vector_store.save_embedding(mem_id, embedding, meta)
                updated += 1
    print(f"向量库元数据更新: {updated} 条")
    
    # 保存向量库
    embedding_service.persist()
    
    # 最终确认
    print("\n=== 最终确认 ===")
    for layer in range(1, 7):
        cursor.execute("SELECT COUNT(*) FROM memories WHERE layer = ?", (layer,))
        count = cursor.fetchone()[0]
        print(f"L{layer}层: {count} 条")
    
    print("\n迁移完成!")

if __name__ == "__main__":
    main()
