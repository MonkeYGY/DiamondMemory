import sys, os
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from app.storage.sqlite_store import SQLiteStore
from app.storage.vector_store import get_vector_store
import numpy as np

store = SQLiteStore()
v_store = get_vector_store()

l4_memories = store.get_by_layer(4)
print("Scanning L4 memories...")

for m1 in l4_memories:
    emb1 = v_store.get_embedding(m1["id"])
    if not emb1: continue
    
    similar = v_store.search_similar(emb1, k=10)
    for sim_id, score in similar:
        if sim_id != m1["id"] and score > 0.6:
            m2 = store.get_by_id(sim_id)
            if m2 and m2.get("layer") == 4 and m2.get("category") == m1.get("category"):
                print(f"FOUND MATCH for {m1['id']} -> {m2['id']} (Score: {score:.3f})")
                print(f"  M1: {m1['content'][:30].replace(chr(10), ' ')}")
                print(f"  M2: {m2['content'][:30].replace(chr(10), ' ')}")