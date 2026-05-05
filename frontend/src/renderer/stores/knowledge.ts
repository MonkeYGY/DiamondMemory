import { defineStore } from 'pinia'
import { ref } from 'vue'
import { apiRequest } from '../api/backend'

export interface KnowledgeItem {
  id: string
  title: string
  content: string
  tags: string[]
  createdAt: string
  created_at?: string
  summary?: string
  score?: number
  category?: string
}

export const useKnowledgeStore = defineStore('knowledge', () => {
  const knowledgeItems = ref<KnowledgeItem[]>([])
  const loading = ref(false)
  const searchQuery = ref('')

  async function fetchKnowledge() {
    loading.value = true
    try {
      knowledgeItems.value = await apiRequest('/api/knowledge')
    } catch (error) {
      console.error('获取知识列表失败:', error)
    } finally {
      loading.value = false
    }
  }

  async function searchKnowledge(query: string) {
    searchQuery.value = query
    try {
      knowledgeItems.value = await apiRequest(`/api/knowledge/search?q=${encodeURIComponent(query)}`)
    } catch (error) {
      console.error('搜索知识失败:', error)
    }
  }

  return {
    knowledgeItems,
    loading,
    searchQuery,
    fetchKnowledge,
    searchKnowledge
  }
})
