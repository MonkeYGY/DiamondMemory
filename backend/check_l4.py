import sys, os
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from app.storage.sqlite_store import SQLiteStore
from app.storage.vector_store import get_vector_store
import numpy as np

def cosine_similarity(v1, v2):
    return np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2))

store = SQLiteStore()
v_store = get_vector_store()

l4_memories = store.get_by_layer(4)

print("=== L4 Categories ===")
cats = {}
for m in l4_memories:
    cat = m.get("category", "None")
    cats[cat] = cats.get(cat, 0) + 1
for c, count in cats.items():
    print(f"[{c}]: {count}")

print("\n=== Similarity check for '健康检查' ===")
health_mems = [m for m in l4_memories if "健康检查" in m.get("content", "")]
for i, m1 in enumerate(health_mems):
    emb1 = v_store.get_embedding(m1["id"])
    if not emb1:
        print(f"Missing embedding for {m1['id']}")
        continue
    for j, m2 in enumerate(health_mems):
        if i >= j: continue
        emb2 = v_store.get_embedding(m2["id"])
        if not emb2: continue
        sim = cosine_similarity(emb1, emb2)
        print(f"SIM: {sim:.3f} | CAT1: '{m1.get('category')}' | CAT2: '{m2.get('category')}'")
        print(f" M1: {m1['content'][:40].replace(chr(10), ' ')}")
        print(f" M2: {m2['content'][:40].replace(chr(10), ' ')}")
        print("-")