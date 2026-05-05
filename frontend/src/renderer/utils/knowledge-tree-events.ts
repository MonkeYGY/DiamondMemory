export const KNOWLEDGE_TREE_REFRESH_EVENT = 'dm:knowledge-tree-refresh'

export function requestKnowledgeTreeRefresh() {
  window.dispatchEvent(new CustomEvent(KNOWLEDGE_TREE_REFRESH_EVENT))
}

let knowledgeTreeSyncPromise: Promise<void> | null = null

export async function syncKnowledgeTree(
  rebuildKnowledgeMemoryExports: () => Promise<unknown>
) {
  if (knowledgeTreeSyncPromise) return knowledgeTreeSyncPromise

  knowledgeTreeSyncPromise = (async () => {
    await rebuildKnowledgeMemoryExports()
    requestKnowledgeTreeRefresh()
  })().finally(() => {
    knowledgeTreeSyncPromise = null
  })

  return knowledgeTreeSyncPromise
}
