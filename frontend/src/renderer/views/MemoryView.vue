<template>
  <div class="view-container">
    <div class="view-header">
      <h2>记忆管理</h2>
      <div class="header-actions">
        <div class="search-box">
          <span class="search-icon">🔍</span>
          <input
            v-model="searchText"
            type="text"
            placeholder="搜索记忆..."
            class="search-input"
            @input="handleSearch"
          />
          <button v-if="searchText" @click="searchText = ''" class="clear-btn">✕</button>
        </div>
        <button @click="showAddDialog = true" class="btn-primary">+ 新建记忆</button>
        <button @click="normalizeCategories" :disabled="isNormalizingCategories" class="btn-secondary">
          {{ isNormalizingCategories ? '收敛中...' : '🧹 收敛分类' }}
        </button>
        <button @click="confirmOrganizeQuick" :disabled="isOrganizing || isQuickOrganizing" class="btn-organize btn-quick">
          {{ (isOrganizing || isQuickOrganizing) ? '整理中...' : '⚡ 快速整理' }}
        </button>
        <button @click="confirmOrganizeDeep" :disabled="isOrganizing || isQuickOrganizing" class="btn-organize">
          {{ (isOrganizing || isQuickOrganizing) ? '整理中...' : '🔄 深度整理' }}
        </button>
        <button v-if="filterLevel === '4'" @click="deduplicateL4" :disabled="isDeduplicatingL4" class="btn-organize btn-quick" style="background: #e6f7ff; color: #0066cc; border: 1px solid #91d5ff;">
          {{ isDeduplicatingL4 ? '归并中...' : '🔗 高相似归并' }}
        </button>
        <button @click="refreshMemories" :disabled="isLoading" class="btn-secondary">
          {{ isLoading ? '刷新中...' : '刷新' }}
        </button>
      </div>
    </div>

    <div class="filter-bar">
      <div class="level-buttons">
        <button class="level-btn" :class="{ active: filterLevel === '' }" @click="filterLevel = ''">全部</button>
        <button class="level-btn l1" :class="{ active: filterLevel === '1' }" @click="filterLevel = '1'">L1 原始数据</button>
        <button class="level-btn l2" :class="{ active: filterLevel === '2' }" @click="filterLevel = '2'">L2 沉淀层</button>
        <button class="level-btn l3" :class="{ active: filterLevel === '3' }" @click="filterLevel = '3'">L3 分类层</button>
        <button class="level-btn l4" :class="{ active: filterLevel === '4' }" @click="filterLevel = '4'">L4 总结记忆</button>
        <button class="level-btn l5" :class="{ active: filterLevel === '5' }" @click="filterLevel = '5'">L5 技能分类</button>
        <button class="level-btn l6" :class="{ active: filterLevel === '6' }" @click="filterLevel = '6'">L6 技能</button>
      </div>
      <div class="filter-controls">
        <select v-model="filterSource" class="filter-select">
          <option value="">全部来源</option>
          <option v-for="src in availableSources" :key="src" :value="src">{{ src }}</option>
        </select>
        <select v-if="filterLevel === '1' || filterLevel === '2'" v-model="filterStatus" class="filter-select">
          <option value="">全部状态</option>
          <option value="pending">未整理</option>
          <option value="processed">已归档</option>
        </select>
        <select v-model="filterCategory" class="filter-select">
          <option value="">全部分类</option>
          <option v-for="cat in availableCategories" :key="cat" :value="cat">{{ categoryMap[cat] || cat }}</option>
        </select>
        <select v-model="filterTag" class="filter-select">
          <option value="">全部标签</option>
          <option v-for="tag in availableTags" :key="tag" :value="tag">{{ tag }}</option>
        </select>
        <select v-model="sortBy" class="filter-select">
          <option value="newest">最新优先</option>
          <option value="oldest">最旧优先</option>
        </select>
      </div>
    </div>

    <div v-if="isLoading && memories.length === 0" class="memory-list skeleton-list">
      <div v-for="i in 5" :key="i" class="memory-card skeleton-card">
        <div class="memory-header">
          <div class="skeleton-block" style="width: 40px; height: 20px; border-radius: 4px;"></div>
          <div class="skeleton-block" style="width: 40%; height: 20px; border-radius: 4px;"></div>
        </div>
        <div class="skeleton-block" style="width: 100%; height: 14px; margin-bottom: 8px;"></div>
        <div class="skeleton-block" style="width: 80%; height: 14px; margin-bottom: 12px;"></div>
      </div>
    </div>

    <div v-else-if="memories.length === 0" class="empty-state">
      <div class="empty-icon">🧠</div>
      <p>暂无记忆数据</p>
      <button @click="showAddDialog = true" class="btn-primary">创建第一条记忆</button>
    </div>

    <div v-else class="memory-lists-container">
      <div v-if="mainMemories.length > 0" class="memory-list">
        <div v-for="memory in paginatedMainMemories" :key="memory.id" class="memory-card" @click="openDetail(memory)">
          <div class="memory-header">
            <span class="memory-level" :class="'l' + getLayer(memory)">{{ getLevelLabel(memory) }}</span>
            <span class="memory-title">{{ getTitle(memory) }}</span>
            <span v-if="memory.source" class="memory-source">{{ memory.source }}</span>
          </div>
          <p class="memory-content">{{ getContent(memory) }}</p>
          <div class="memory-footer">
            <span class="memory-tags">
              <span v-for="tag in getTags(memory)" :key="tag" class="tag">{{ tag }}</span>
              <span v-if="getParentLabel(memory)" class="tag parent-tag">{{ getParentLabelText(memory) }}</span>
              <span v-if="memory.category" class="tag category-tag">{{ categoryMap[memory.category] || memory.category }}</span>
            </span>
            <span class="memory-date">{{ formatDisplayTime(memory) }}</span>
          </div>
        </div>
      </div>

      <div v-if="mainMemories.length > 0" class="pagination-bar">
        <div class="pagination-left">
          <span class="pagination-total">共 {{ mainMemories.length }} 条</span>
          <select v-model="pageSize" class="page-size-select">
            <option :value="5">5条/页</option>
            <option :value="10">10条/页</option>
            <option :value="20">20条/页</option>
          </select>
        </div>
        <div class="pagination-right">
          <button class="page-btn" :disabled="mainCurrentPage <= 1" @click="mainCurrentPage = 1">首页</button>
          <button class="page-btn" :disabled="mainCurrentPage <= 1" @click="mainCurrentPage--">上一页</button>
          <span class="page-info">{{ mainCurrentPage }} / {{ mainTotalPages }}</span>
          <button class="page-btn" :disabled="mainCurrentPage >= mainTotalPages" @click="mainCurrentPage++">下一页</button>
          <button class="page-btn" :disabled="mainCurrentPage >= mainTotalPages" @click="mainCurrentPage = mainTotalPages">末页</button>
        </div>
      </div>

      <div v-if="mainMemories.length === 0 && archivedMemories.length === 0" class="empty-search-state">
        <div class="empty-icon">🔍</div>
        <p>没有匹配的记忆</p>
      </div>

      <div v-if="showArchivedSeparately && archivedMemories.length > 0" class="archived-section">
        <div class="archived-header" @click="isArchivedCollapsed = !isArchivedCollapsed">
          <div class="archived-header-left">
            <span class="archived-icon">📦</span>
            <span class="archived-title">已归档记忆 ({{ archivedMemories.length }})</span>
            <span class="archived-subtitle">已整理为更高维度的 L1/L2 记录</span>
          </div>
          <span class="archived-toggle">{{ isArchivedCollapsed ? '▼ 展开' : '▲ 收起' }}</span>
        </div>
        
        <div v-show="!isArchivedCollapsed" class="archived-content">
          <div class="memory-list">
            <div v-for="memory in paginatedArchivedMemories" :key="memory.id" class="memory-card archived-card" @click="openDetail(memory)">
              <div class="memory-header">
                <span class="memory-level" :class="'l' + getLayer(memory)">{{ getLevelLabel(memory) }}</span>
                <span class="memory-title">{{ getTitle(memory) }}</span>
                <span v-if="memory.source" class="memory-source">{{ memory.source }}</span>
              </div>
              <p class="memory-content">{{ getContent(memory) }}</p>
              <div class="memory-footer">
                <span class="memory-tags">
                  <span v-for="tag in getTags(memory)" :key="tag" class="tag">{{ tag }}</span>
                  <span v-if="getParentLabel(memory)" class="tag parent-tag">{{ getParentLabelText(memory) }}</span>
                  <span v-if="memory.category" class="tag category-tag">{{ categoryMap[memory.category] || memory.category }}</span>
                </span>
                <span class="memory-date">{{ formatDisplayTime(memory) }}</span>
              </div>
            </div>
          </div>
          
          <div class="pagination-bar">
            <div class="pagination-left">
              <span class="pagination-total">共 {{ archivedMemories.length }} 条</span>
              <select v-model="pageSize" class="page-size-select">
                <option :value="5">5条/页</option>
                <option :value="10">10条/页</option>
                <option :value="20">20条/页</option>
              </select>
            </div>
            <div class="pagination-right">
              <button class="page-btn" :disabled="archivedCurrentPage <= 1" @click="archivedCurrentPage = 1">首页</button>
              <button class="page-btn" :disabled="archivedCurrentPage <= 1" @click="archivedCurrentPage--">上一页</button>
              <span class="page-info">{{ archivedCurrentPage }} / {{ archivedTotalPages }}</span>
              <button class="page-btn" :disabled="archivedCurrentPage >= archivedTotalPages" @click="archivedCurrentPage++">下一页</button>
              <button class="page-btn" :disabled="archivedCurrentPage >= archivedTotalPages" @click="archivedCurrentPage = archivedTotalPages">末页</button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <transition name="modal-fade">
      <div v-if="showCategoryManageDialog" class="modal-overlay" @click.self="showCategoryManageDialog = false">
        <div class="modal">
          <h3>管理分类体系 (L3-L5)</h3>
          
          <div class="form-field" style="margin-bottom: 12px; display: flex; gap: 8px;">
            <select v-model="manageCategoryLayer" class="filter-select" @change="fetchCategories" style="flex: 1;">
              <option :value="3">L3 总结分类</option>
              <option :value="4">L4 经验总结</option>
              <option :value="5">L5 技能分类</option>
            </select>
            <button class="btn-secondary" @click="fetchCategories">刷新</button>
          </div>

          <div v-if="isLoadingCategories" class="loading" style="text-align: center; padding: 20px;">加载中...</div>
          <div v-else-if="manageCategories.length === 0" class="empty-state" style="padding: 20px; text-align: center; color: var(--color-text-secondary);">
            暂无该层级的分类数据
          </div>
          <div v-else class="category-manage-list" style="max-height: 300px; overflow-y: auto; border: 1px solid var(--color-border); border-radius: 4px; padding: 8px;">
            <div v-for="cat in manageCategories" :key="cat.id" class="category-manage-item" style="display: flex; align-items: center; justify-content: space-between; padding: 8px; border-bottom: 1px solid var(--color-border);">
              <div v-if="editingCategoryId === cat.id" style="display: flex; gap: 8px; flex: 1;">
                <input v-model="editingCategoryName" class="filter-select" style="flex: 1;" />
                <select v-model="editingCategoryParent" class="filter-select" style="width: 120px;">
                  <option value="">无父分类</option>
                  <option v-for="p in getPotentialParents(cat)" :key="p.id" :value="p.id">{{ p.name }}</option>
                </select>
                <button class="btn-primary" @click="saveCategory(cat)" style="padding: 2px 8px;">保存</button>
                <button class="btn-secondary" @click="editingCategoryId = ''" style="padding: 2px 8px;">取消</button>
              </div>
              <div v-else style="display: flex; justify-content: space-between; width: 100%; align-items: center;">
                <div style="display: flex; flex-direction: column; gap: 4px;">
                  <span style="font-weight: 500;">{{ cat.name }}</span>
                  <span v-if="cat.parent_id" style="font-size: 11px; color: var(--color-text-secondary);">
                    父分类: {{ getCategoryNameById(cat.parent_id) }}
                  </span>
                </div>
                <div style="display: flex; gap: 8px;">
                  <button class="btn-secondary" @click="startEditCategory(cat)" style="padding: 2px 8px;">编辑</button>
                  <button class="btn-danger" @click="deleteCategory(cat)" style="padding: 2px 8px;">删除</button>
                </div>
              </div>
            </div>
          </div>
          
          <div class="modal-actions" style="margin-top: 16px;">
            <button @click="showCategoryManageDialog = false" class="btn-primary">关闭</button>
          </div>
        </div>
      </div>
    </transition>

    <transition name="modal-fade">
      <div v-if="showAddDialog" class="modal-overlay" @click.self="showAddDialog = false">
        <div class="modal">
          <h3>新建记忆</h3>
          <div class="form-field">
            <label class="form-label">记忆层级</label>
            <div class="level-select-buttons">
              <button v-for="(label, idx) in levelLabels" :key="idx" class="level-select-btn" :class="['l' + (idx + 1), { active: newMemoryLayer === idx + 1 }]" @click="newMemoryLayer = idx + 1">{{ label }}</button>
            </div>
          </div>
          <div class="form-field">
            <label class="form-label">分类 (可选)</label>
            <div style="display: flex; gap: 8px;">
              <select v-model="newMemoryCategory" class="filter-select" style="flex: 1; border: 1px solid var(--color-border); border-radius: 4px; padding: 6px;">
                <option value="">未选择分类</option>
                <option v-for="cat in availableCategories" :key="cat" :value="cat">{{ categoryMap[cat] || cat }}</option>
              </select>
              <input v-model="newCategoryInput" placeholder="或输入新分类..." class="filter-select" style="flex: 1; border: 1px solid var(--color-border); border-radius: 4px; padding: 6px;" />
            </div>
            <div style="margin-top: 8px; display: flex; justify-content: flex-end;">
              <button @click.prevent="showCategoryManageDialog = true" class="btn-secondary" style="padding: 2px 8px; font-size: 11px;">管理已有分类...</button>
            </div>
          </div>
          <div class="form-field">
            <label class="form-label">记忆内容</label>
            <textarea v-model="newMemoryContent" placeholder="输入记忆内容..." class="memory-textarea"></textarea>
          </div>
          <div class="form-field">
            <label class="form-label">选择标签</label>
            <div class="tag-input-container">
              <span v-if="newMemoryTags.length === 0" class="text-secondary" style="font-size: 12px;">未选择标签</span>
              <span v-for="tag in newMemoryTags" :key="tag" class="tag-item">
                {{ tag }}
                <button class="tag-remove" @click="removeNewTag(tag)">×</button>
              </span>
            </div>
            
            <div class="tag-suggestions" style="margin-top: 10px;">
              <span class="tag-suggestion-label" style="display: block; width: 100%; margin-bottom: 4px;">系统默认标签：</span>
              <button v-for="tag in systemTags" :key="tag" class="tag-suggestion-btn" :class="{active: newMemoryTags.includes(tag)}" @click="toggleTag(tag)">{{ tag }}</button>
            </div>
            
            <div class="tag-suggestions" style="margin-top: 10px;">
              <span class="tag-suggestion-label" style="display: block; width: 100%; margin-bottom: 4px;">自定义用户标签：</span>
              <span v-if="userTags.length === 0" class="text-secondary" style="font-size: 11px; margin-left: 4px;">暂无</span>
              <button v-for="tag in userTags" :key="tag" class="tag-suggestion-btn" :class="{active: newMemoryTags.includes(tag)}" @click="toggleTag(tag)">
                {{ tag }}
                <span class="tag-remove-user" @click.stop="deleteUserTag(tag)">×</span>
              </button>
            </div>

            <div class="add-user-tag-container" style="margin-top: 12px; display: flex; gap: 8px;">
              <input v-model="tagInput" @keydown.enter.prevent="addUserTag" placeholder="新增自定义标签..." class="tag-input" style="border: 1px solid var(--color-border); padding: 4px 8px; border-radius: 4px; background: var(--color-bg); font-size: 12px; flex: 1;" />
              <button @click.prevent="addUserTag" class="btn-secondary" style="padding: 4px 12px; font-size: 12px;">添加</button>
            </div>
          </div>
          <div class="modal-actions">
            <button @click="showAddDialog = false" class="btn-secondary">取消</button>
            <button @click="createMemory" :disabled="!newMemoryContent.trim()" class="btn-primary">创建</button>
          </div>
        </div>
      </div>
    </transition>

    <transition name="modal-fade">
      <div v-if="selectedMemory && !showDeleteConfirm" class="modal-overlay" @click.self="selectedMemory = null">
        <div class="modal detail-modal">
          <div class="modal-header">
            <h3>{{ detailTitle }}</h3>
            <span class="memory-level" :class="'l' + getLayer(selectedMemory)">{{ getLevelLabel(selectedMemory) }}</span>
          </div>
          <div class="detail-metadata">
            <span v-if="detailTime" class="meta-item">⏰ {{ detailTime }}</span>
            <span v-if="detailSource" class="meta-item">🤖 {{ detailSource }}</span>
            <span v-if="detailSession" class="meta-item">🔄 {{ detailSession }}</span>
            <span v-if="detailCategory" class="meta-item">📂 {{ detailCategory }}</span>
            <span v-if="detailParentLabel" class="meta-item">🧭 {{ detailParentLabel }}</span>
            <span v-if="selectedMemory.confidence" class="meta-item">✅ 置信度: {{ Math.round(selectedMemory.confidence * 100) }}%</span>
          </div>
          <div class="memory-detail-content markdown-body" v-html="renderedContent"></div>
          <div v-if="detailChildSectionTitle" class="detail-related-section">
            <div class="detail-related-header">
              <span class="detail-related-title">{{ detailChildSectionTitle }}</span>
              <span class="detail-related-count">{{ detailChildItems.length }} 条</span>
            </div>
            <div v-if="detailChildItems.length > 0" class="detail-related-list">
              <button
                v-for="item in detailChildItems"
                :key="item.id"
                type="button"
                class="detail-related-item"
                @click="openDetail(item)"
              >
                <span class="detail-related-item-title">{{ getTitle(item) }}</span>
                <span class="detail-related-item-level">{{ getLevelLabel(item) }}</span>
              </button>
            </div>
            <div v-else class="detail-related-empty">暂无对应内容</div>
          </div>
          <div class="detail-footer" v-if="detailKeyInfo || detailTags.length > 0">
            <div v-if="detailKeyInfo" class="key-info">
              <span class="key-info-label">💡 关键信息:</span>
              <span class="key-info-value">{{ detailKeyInfo }}</span>
            </div>
            <div v-if="detailTags.length > 0" class="detail-tags">
              <span v-for="tag in detailTags" :key="tag" class="detail-tag">{{ tag }}</span>
            </div>
          </div>
          <div class="modal-actions space-between">
            <button @click="showDeleteConfirm = true" class="btn-danger">删除</button>
            <button @click="selectedMemory = null" class="btn-primary">关闭</button>
          </div>
        </div>
      </div>
    </transition>

    <transition name="modal-fade">
      <div v-if="showDeleteConfirm" class="modal-overlay" @click.self="showDeleteConfirm = false">
        <div class="modal modal-small">
          <h3>确认删除</h3>
          <p class="confirm-text">确定要删除这条记忆吗？此操作不可恢复。</p>
          <p class="confirm-preview">"{{ getContent(selectedMemory).slice(0, 50) }}..."</p>
          <div class="modal-actions">
            <button @click="showDeleteConfirm = false" class="btn-secondary">取消</button>
            <button @click="deleteMemory" class="btn-danger">确认删除</button>
          </div>
        </div>
      </div>
    </transition>

    <transition name="modal-fade">
      <div v-if="showOrganizeConfirmDialog" class="modal-overlay" @click.self="showOrganizeConfirmDialog = false">
        <div class="modal">
          <h3>{{ organizeType === 'quick' ? '⚡ 确认快速整理' : '🔄 确认深度整理' }}</h3>
          
          <div class="organize-info" v-if="organizeType === 'quick'">
            <div class="info-section">
              <h4>🎯 整理原理</h4>
              <p>仅处理<strong>新增的未整理（pending）记忆</strong>。系统会进行增量提炼，将新记录的 L1/L2 记忆升维到 L3-L6，不会重新计算和处理已经归档的历史数据。适合日常高频记录后的快速沉淀。</p>
            </div>
            <div class="info-section">
              <h4>⏱️ 预计耗时</h4>
              <p>基于当前电脑配置，调用本地内嵌的 <strong>Ollama (qwen系列)</strong> 和 <strong>bge-m3</strong> 模型进行推理。由于仅处理增量数据，平均每条新记忆耗时约 <strong>2 - 5 秒</strong>。整体过程通常在几秒到一分钟内完成。</p>
            </div>
          </div>
          
          <div class="organize-info" v-else>
            <div class="info-section">
              <h4>🎯 整理原理</h4>
              <p>对<strong>全量记忆数据</strong>进行分阶段回顾与结构重组。系统会逐步梳理知识图谱，修正分类体系（L3/L5），并慢速推进更高维度的经验（L4）和技能（L6）提炼。适合周期性的系统知识盘点。</p>
            </div>
            <div class="info-section warning">
              <h4>⏱️ 预计耗时 (低功耗慢速)</h4>
              <p>系统会分阶段慢速调用本地内嵌的 <strong>Ollama (qwen系列)</strong> 和 <strong>bge-m3</strong> 模型，主动降低 CPU 峰值，但整体耗时会更长。单次整理可能只推进一部分全库任务；若数据量较大，建议按需多次执行，让知识库逐步整理完成。</p>
            </div>
          </div>

          <div class="modal-actions">
            <button @click="showOrganizeConfirmDialog = false" class="btn-secondary">取消</button>
            <button @click="confirmOrganize" class="btn-primary">确认开始</button>
          </div>
        </div>
      </div>
    </transition>
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, ref, computed, watch } from 'vue'
import { apiRequest, rebuildKnowledgeMemoryExports, fetchCapabilities } from '../api/backend'
import { useToast } from '../composables/useToast'
import { useMemoryStore } from '../stores/memory'
import { useTasksStore } from '../stores/tasks'
import { requestKnowledgeTreeRefresh, syncKnowledgeTree } from '../utils/knowledge-tree-events'
import { renderMemoryDetailMarkdown } from '../utils/memory-detail-markdown'

const toast = useToast()
const memoryStore = useMemoryStore()
const tasksStore = useTasksStore()
const memories = ref<any[]>([])
const isLoading = ref(false)
const searchText = ref('')
const filterLevel = ref('')
const sortBy = ref('newest')
const filterSource = ref('')
const filterCategory = ref('')
const filterTag = ref('')
const filterStatus = ref('')
const showAddDialog = ref(false)
const showCategoryManageDialog = ref(false)
const manageCategoryLayer = ref(3)
const isLoadingCategories = ref(false)
const manageCategories = ref<any[]>([])
const editingCategoryId = ref('')
const editingCategoryName = ref('')
const editingCategoryParent = ref('')

const newMemoryContent = ref('')
const newMemoryLayer = ref(1)
const newMemoryCategory = ref('')
const newCategoryInput = ref('')
const newMemoryTags = ref<string[]>([])
const tagInput = ref('')
const systemTags = ref<string[]>([])
const userTags = ref<string[]>([])
const levelLabels = ['L1 原始数据', 'L2 沉淀层', 'L3 分类层', 'L4 总结记忆', 'L5 技能分类', 'L6 技能']
const selectedMemory = ref<any>(null)
const showDeleteConfirm = ref(false)
const showOrganizeConfirmDialog = ref(false)
const organizeType = ref<'quick' | 'deep'>('quick')
const isOrganizing = computed(() => tasksStore.items.some(t => t.type === 'deep_organize' && (t.status === 'queued' || t.status === 'running')))
const isQuickOrganizing = computed(() => tasksStore.items.some(t => t.type === 'quick_organize' && (t.status === 'queued' || t.status === 'running')))
const isNormalizingCategories = ref(false)
const isDeduplicatingL4 = ref(false)
const pageSize = ref(10)
const mainCurrentPage = ref(1)
const archivedCurrentPage = ref(1)
const isArchivedCollapsed = ref(true)

const availableSources = computed(() => {
  const sources = new Set<string>()
  memories.value.forEach(m => { if (m.source) sources.add(m.source) })
  return Array.from(sources).sort()
})

const availableCategories = computed(() => {
  const cats = new Set<string>()
  memories.value.forEach(m => { if (m.category) cats.add(m.category) })
  return Array.from(cats).sort()
})

const availableTags = computed(() => {
  return [...systemTags.value, ...userTags.value]
})

const filteredMemories = computed(() => {
  let result = [...memories.value]
  if (searchText.value.trim()) {
    const search = searchText.value.toLowerCase()
    result = result.filter(m => {
      const title = (getTitle(m) || '').toLowerCase()
      const content = (getContent(m) || '').toLowerCase()
      const tags = (getTags(m) || []).join(' ').toLowerCase()
      return title.includes(search) || content.includes(search) || tags.includes(search)
    })
  }
  if (filterLevel.value !== '') {
    result = result.filter(m => String(getLayer(m)) === filterLevel.value)
  }
  if (filterSource.value) {
    result = result.filter(m => m.source === filterSource.value)
  }
  if (filterCategory.value) {
    result = result.filter(m => m.category === filterCategory.value)
  }
  if (filterStatus.value && (filterLevel.value === '1' || filterLevel.value === '2')) {
    result = result.filter(m => m.processed_status === filterStatus.value)
  }
  if (filterTag.value) {
    result = result.filter(m => Array.isArray(m.tags) && m.tags.includes(filterTag.value))
  }
  result.sort((a, b) => {
    const dateA = new Date(getDisplayTime(a) || 0).getTime()
    const dateB = new Date(getDisplayTime(b) || 0).getTime()
    return sortBy.value === 'newest' ? dateB - dateA : dateA - dateB
  })
  return result
})

function isArchivedL1L2(memory: any) {
  const layer = getLayer(memory)
  if (layer === 1 || layer === 2) {
    return memory.processed_status && memory.processed_status !== 'pending'
  }
  return false
}

const showArchivedSeparately = computed(() => {
  return filterStatus.value === ''
})

const mainMemories = computed(() => {
  if (!showArchivedSeparately.value) return filteredMemories.value
  return filteredMemories.value.filter(m => !isArchivedL1L2(m))
})

const archivedMemories = computed(() => {
  if (!showArchivedSeparately.value) return []
  return filteredMemories.value.filter(m => isArchivedL1L2(m))
})

const mainTotalPages = computed(() => Math.max(1, Math.ceil(mainMemories.value.length / pageSize.value)))
const archivedTotalPages = computed(() => Math.max(1, Math.ceil(archivedMemories.value.length / pageSize.value)))

const paginatedMainMemories = computed(() => {
  const start = (mainCurrentPage.value - 1) * pageSize.value
  const end = start + pageSize.value
  return mainMemories.value.slice(start, end)
})

const paginatedArchivedMemories = computed(() => {
  const start = (archivedCurrentPage.value - 1) * pageSize.value
  const end = start + pageSize.value
  return archivedMemories.value.slice(start, end)
})

watch(mainMemories, () => {
  mainCurrentPage.value = 1
})

watch(archivedMemories, () => {
  archivedCurrentPage.value = 1
})

watch(isOrganizing, async (newVal, oldVal) => {
  if (oldVal === true && newVal === false) {
    const latest = tasksStore.items.find(t => t.type === 'deep_organize')
    if (latest?.status === 'failed') {
      toast.error('整理失败: ' + (latest?.error || '未知错误'))
      return
    }
    if (latest?.status === 'completed') {
      toast.success('深度整理完成！')
      await fetchMemories()
      await syncKnowledgeTreeAfterMutation('深度整理已完成')
    }
  }
})

watch(isQuickOrganizing, async (newVal, oldVal) => {
  if (oldVal === true && newVal === false) {
    const latest = tasksStore.items.find(t => t.type === 'quick_organize')
    if (latest?.status === 'failed') {
      toast.error('快速整理失败: ' + (latest?.error || '未知错误'))
      return
    }
    if (latest?.status === 'completed') {
      toast.success('快速整理完成！')
      await fetchMemories()
      await syncKnowledgeTreeAfterMutation('快速整理已完成')
    }
  }
})

async function fetchCategories() {
  isLoadingCategories.value = true
  try {
    const data = await apiRequest<any>(`/api/config/categories?layer=${manageCategoryLayer.value}`)
    const flattenCategories = (nodes: any[]): any[] => {
      let result: any[] = []
      for (const node of nodes) {
        result.push(node)
        if (node.children && node.children.length > 0) {
          result = result.concat(flattenCategories(node.children))
        }
      }
      return result
    }
    manageCategories.value = flattenCategories(data.categories || [])
  } catch (error: any) {
    toast.error('获取分类失败: ' + error.message)
  } finally {
    isLoadingCategories.value = false
  }
}

watch(showCategoryManageDialog, (val) => {
  if (val) fetchCategories()
})

function getCategoryNameById(id: string) {
  const cat = manageCategories.value.find(c => c.id === id)
  return cat ? cat.name : '未知'
}

function getPotentialParents(cat: any) {
  // 不能是自己，也不能是自己的子分类（简单起见，这里只排除自己）
  return manageCategories.value.filter(c => c.id !== cat.id)
}

function startEditCategory(cat: any) {
  editingCategoryId.value = cat.id
  editingCategoryName.value = cat.name
  editingCategoryParent.value = cat.parent_id || ''
}

async function saveCategory(cat: any) {
  if (!editingCategoryName.value.trim()) return
  try {
    await apiRequest(`/api/config/categories/${cat.id}`, {
      method: 'PUT',
      body: JSON.stringify({
        name: editingCategoryName.value.trim(),
        parent_id: editingCategoryParent.value || null
      })
    })
    toast.success('分类更新成功')
    editingCategoryId.value = ''
    await fetchCategories()
    await fetchMemories()
    await syncKnowledgeTreeAfterMutation('分类已更新')
  } catch (error: any) {
    toast.error('更新分类失败: ' + error.message)
  }
}

async function deleteCategory(cat: any) {
  const fallbackLabel = cat.layer === 3 ? '未归档' : cat.layer === 5 ? '未分类' : '默认分类'
  if (!confirm(`确定要删除分类 "${cat.name}" 吗？该分类下的内容不会被删除，但会自动移动到「${fallbackLabel}」下。`)) return
  try {
    await apiRequest(`/api/config/categories/${cat.id}`, {
      method: 'DELETE'
    })
    toast.success('分类删除成功')
    await fetchCategories()
    await fetchMemories()
    await syncKnowledgeTreeAfterMutation('分类已删除')
  } catch (error: any) {
    toast.error('删除分类失败: ' + error.message)
  }
}

async function fetchTags() {
  try {
    const data = await apiRequest<any>('/api/config/tags')
    systemTags.value = data.system_tags || []
    userTags.value = data.user_tags || []
  } catch (error) {
    console.error('获取标签列表失败:', error)
  }
}

onMounted(async () => {
  await fetchTags()
  await fetchMemories()
  window.addEventListener('keydown', handleKeydown)
  // Check backend status on mount to resume polling if organizing is running
  memoryStore.checkOrganizeStatus()
  memoryStore.checkQuickOrganizeStatus()
})

onUnmounted(() => {
  window.removeEventListener('keydown', handleKeydown)
})

function handleKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape') {
    if (showDeleteConfirm.value) showDeleteConfirm.value = false
    else if (showOrganizeConfirmDialog.value) showOrganizeConfirmDialog.value = false
    else if (selectedMemory.value) selectedMemory.value = null
    else if (showAddDialog.value) showAddDialog.value = false
  }
}

function getLayer(memory: any): number {
  if (memory === null || memory === undefined) return 0
  return memory.layer ?? memory.level ?? 0
}

function getLevelLabel(memory: any): string {
  const layer = getLayer(memory)
  const labels = ['', 'L1 原始数据', 'L2 沉淀层', 'L3 分类层', 'L4 总结记忆', 'L5 技能分类', 'L6 技能']
  return labels[layer] || '未知层级'
}

function getTitle(memory: any): string {
  if (!memory) return '无标题'
  if (memory.short_name) return memory.short_name
  if (memory.title) return memory.title
  const content = memory.content || memory.raw_content || ''
  const layer = memory.layer ?? 0
  if (layer === 6) {
    const m = content.match(/技能名称[：:]\s*([^\n]+)/)
    if (m) return m[1].trim()
  }
  if (layer === 4) {
    const m = content.match(/主题[：:]\s*([^\n]+)/)
    if (m) return m[1].trim()
  }
  const headingMatch = content.match(/^##\s+(.+)$/m)
  if (headingMatch) return headingMatch[1].trim()
  if (layer === 3 || layer === 5) {
    if (memory.category) return memory.category
  }
  const lines = content.split('\n')
  for (const line of lines) {
    const stripped = line.trim()
    if (!stripped || stripped.startsWith('---') || stripped.startsWith('#') || stripped.startsWith('**')) continue
    if (/^(主题|技能名称|核心要点|详细记录|目标任务|触发条件|包含步骤|涉及工具|最佳实践|依赖|注意事项)[：:]/.test(stripped)) continue
    return stripped.length > 60 ? stripped.slice(0, 60) + '...' : stripped
  }
  if (memory.category) return memory.category
  return '无标题'
}

function getContent(memory: any): string {
  if (!memory) return ''
  const content = memory.content || memory.raw_content || ''
  if (!content) return ''
  const layer = memory.layer ?? 0
  let previewContent = content
  if (layer === 4) {
    const keyPointsMatch = content.match(/核心要点[：:]\s*\n([\s\S]*?)(?=\n详细记录[：:]|\n---|\n##|$)/)
    if (keyPointsMatch) {
      previewContent = keyPointsMatch[1].trim()
    } else {
      previewContent = content.replace(/^主题[：:][^\n]*\n*/, '').trim()
    }
  } else if (layer === 6) {
    const taskMatch = content.match(/目标任务[：:]\s*([^\n]*(?:\n(?!触发条件|包含步骤|涉及工具|最佳实践|依赖|注意事项)[^\n]+)*)/)
    if (taskMatch) {
      previewContent = taskMatch[1].trim()
    } else {
      previewContent = content.replace(/^技能名称[：:][^\n]*\n*/, '').trim()
    }
  }
  const metaPattern = /^\*\*(?:时间|会话|来源|主题|任务|状态|偏好类型|关键信息|标签|置信度)\*\*:\s*.*$/gm
  previewContent = previewContent.replace(metaPattern, '').trim()
  previewContent = previewContent.replace(/^---$/gm, '').trim()
  if (previewContent.length > 150) {
    const truncated = previewContent.slice(0, 150)
    const lastPunct = Math.max(
      truncated.lastIndexOf('。'),
      truncated.lastIndexOf('！'),
      truncated.lastIndexOf('？'),
      truncated.lastIndexOf('；'),
      truncated.lastIndexOf('，')
    )
    if (lastPunct > 30) {
      return truncated.slice(0, lastPunct + 1)
    }
    return truncated + '...'
  }
  return previewContent
}

function getTags(memory: any): string[] {
  if (!memory || !memory.tags) return []
  return Array.isArray(memory.tags) ? memory.tags.slice(0, 5) : []
}

function getParentLabel(memory: any): { layer: number; name: string } | null {
  const parentLabel = memory?.parent_label
  if (!parentLabel) return null

  const layer = Number(parentLabel.layer)
  const name = String(parentLabel.name || '').trim()
  if (!layer || !name) return null

  return { layer, name }
}

function getParentLabelText(memory: any): string {
  const parentLabel = getParentLabel(memory)
  if (!parentLabel) return ''
  return `L${parentLabel.layer}: ${parentLabel.name}`
}

async function fetchMemories() {
  isLoading.value = true
  try {
    const data = await apiRequest<any[]>('/api/memories')
    memories.value = Array.isArray(data) ? data : []
  } catch (error) {
    console.error('获取记忆列表失败:', error)
    memories.value = []
  } finally {
    isLoading.value = false
  }
}

function handleSearch() {
  // Search is automatically triggered by computed property
}

async function refreshMemories() {
  await fetchMemories()
}

async function normalizeCategories() {
  if (isNormalizingCategories.value) return
  isNormalizingCategories.value = true
  try {
    const result = await apiRequest<any>('/api/memory/organize/normalize-categories', {
      method: 'POST'
    })
    toast.success(`分类收敛完成：L3 ${result.l3.merged_groups} 组，L5 ${result.l5.merged_groups} 组`)
    await fetchMemories()
    requestKnowledgeTreeRefresh()
  } catch (error: any) {
    toast.error('分类收敛失败: ' + error.message)
  } finally {
    isNormalizingCategories.value = false
  }
}

function confirmOrganizeQuick() {
  organizeType.value = 'quick'
  showOrganizeConfirmDialog.value = true
}

function confirmOrganizeDeep() {
  organizeType.value = 'deep'
  showOrganizeConfirmDialog.value = true
}

async function confirmOrganize() {
  showOrganizeConfirmDialog.value = false
  if (organizeType.value === 'quick') {
    await quickOrganizeMemories()
  } else {
    await organizeMemories()
  }
}

async function deduplicateL4() {
  if (isDeduplicatingL4.value) return
  isDeduplicatingL4.value = true
  toast.info('正在归并 L4 相似内容...')
  try {
    const result = await apiRequest<any>('/api/memory/organize/deduplicate-l4', {
      method: 'POST'
    })
    if (result.status === 'success') {
      const { merged, scanned } = result.details
      toast.success(`L4 归并完成！扫描 ${scanned} 条，归并 ${merged} 条。`)
      await fetchMemories()
      await syncKnowledgeTreeAfterMutation('L4 高相似归并已完成')
    } else {
      toast.error('L4 归并失败: ' + (result.message || '未知错误'))
    }
  } catch (error: any) {
    toast.error('L4 归并失败: ' + error.message)
  } finally {
    isDeduplicatingL4.value = false
  }
}

async function organizeMemories() {
  toast.info('已加入后台任务队列：深度整理')
  try {
    // 预拉取能力状态（便于后续扩展更精确的提示）
    await fetchCapabilities()
  } catch {}
  const result = await tasksStore.enqueue('deep_organize', 'normal', {})
  if (result.status === 'blocked') {
    toast.info('需要模型：请先启动/安装 Ollama 并下载模型（任务已进入队列）')
  }
}

async function quickOrganizeMemories() {
  toast.info('已加入后台任务队列：快速整理')
  try {
    await fetchCapabilities()
  } catch {}
  const result = await tasksStore.enqueue('quick_organize', 'normal', {})
  if (result.status === 'blocked') {
    toast.info('需要模型：请先启动/安装 Ollama 并下载模型（任务已进入队列）')
  }
}

async function syncKnowledgeTreeAfterMutation(successMessage?: string) {
  try {
    await syncKnowledgeTree(rebuildKnowledgeMemoryExports)
  } catch (error: any) {
    const detail = error?.message || '未知错误'
    toast.error((successMessage || '操作已完成') + `，但知识库同步失败: ${detail}`)
  }
}

async function createMemory() {
  if (!newMemoryContent.value.trim()) return
  
  const finalCategory = newCategoryInput.value.trim() || newMemoryCategory.value || undefined
  
  try {
    await apiRequest('/api/memory/create', {
      method: 'POST',
      body: JSON.stringify({
        content: newMemoryContent.value,
        layer: newMemoryLayer.value,
        category: finalCategory,
        tags: newMemoryTags.value.length > 0 ? newMemoryTags.value : undefined
      })
    })
    newMemoryContent.value = ''
    newMemoryLayer.value = 1
    newMemoryCategory.value = ''
    newCategoryInput.value = ''
    newMemoryTags.value = []
    tagInput.value = ''
    showAddDialog.value = false
    toast.success('记忆创建成功')
    await fetchMemories()
  } catch (error: any) {
    toast.error('创建记忆失败: ' + error.message)
    return
  }

  await syncKnowledgeTreeAfterMutation('记忆已创建')
}

function removeNewTag(tag: string) {
  newMemoryTags.value = newMemoryTags.value.filter(t => t !== tag)
}

function toggleTag(tag: string) {
  if (newMemoryTags.value.includes(tag)) {
    newMemoryTags.value = newMemoryTags.value.filter(t => t !== tag)
  } else {
    newMemoryTags.value.push(tag)
  }
}

async function addUserTag() {
  const tag = tagInput.value.trim()
  if (!tag) return
  if (systemTags.value.includes(tag) || userTags.value.includes(tag)) {
    if (!newMemoryTags.value.includes(tag)) newMemoryTags.value.push(tag)
    tagInput.value = ''
    return
  }
  try {
    const data = await apiRequest<any>('/api/config/tags/user', {
      method: 'POST',
      body: JSON.stringify({ tag })
    })
    userTags.value = data.user_tags || []
    if (!newMemoryTags.value.includes(tag)) newMemoryTags.value.push(tag)
    tagInput.value = ''
    toast.success('自定义标签添加成功')
  } catch (error: any) {
    toast.error('添加用户标签失败: ' + error.message)
  }
}

async function deleteUserTag(tag: string) {
  if (!confirm(`确定要删除标签 "${tag}" 吗？`)) return
  try {
    const data = await apiRequest<any>(`/api/config/tags/user/${encodeURIComponent(tag)}`, {
      method: 'DELETE'
    })
    userTags.value = data.user_tags || []
    newMemoryTags.value = newMemoryTags.value.filter(t => t !== tag)
    toast.success('自定义标签删除成功')
  } catch (error: any) {
    toast.error('删除用户标签失败: ' + error.message)
  }
}

function openDetail(memory: any) {
  selectedMemory.value = memory
}

async function deleteMemory() {
  if (!selectedMemory.value) return
  try {
    await apiRequest(`/api/memory/delete/${selectedMemory.value.id}`, { method: 'DELETE' })
    toast.success('记忆已删除')
    selectedMemory.value = null
    showDeleteConfirm.value = false
    await fetchMemories()
    await syncKnowledgeTreeAfterMutation('记忆已删除')
  } catch (error: any) {
    toast.error('删除记忆失败: ' + error.message)
  }
}

function getDisplayTime(memory: any): string {
  const layer = getLayer(memory)
  if (layer <= 2) {
    return memory.created_at || memory.createdAt || ''
  } else {
    return memory.updated_at || memory.updatedAt || memory.created_at || memory.createdAt || ''
  }
}

function formatDisplayTime(memory: any): string {
  const dateStr = getDisplayTime(memory)
  if (!dateStr) return ''
  try {
    const date = new Date(dateStr)
    return date.toLocaleString('zh-CN', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    })
  } catch {
    return ''
  }
}

const categoryMap: Record<string, string> = {
  'conversation': '对话记录',
  'knowledge': '知识记录',
  'task': '任务记录',
  'preference': '用户偏好',
  'insight': '洞察分析'
}

const sourceMap: Record<string, string> = {
  'hermes': 'Hermes Agent',
  'openclaw': 'OpenClaw Agent',
  'hermes-agent': 'Hermes Agent'
}

const detailTitle = computed(() => {
  if (!selectedMemory.value) return '记忆详情'
  if (selectedMemory.value.title) return selectedMemory.value.title
  const content = selectedMemory.value.content || selectedMemory.value.raw_content || ''
  const layer = selectedMemory.value.layer ?? 0
  if (layer === 6) {
    const m = content.match(/技能名称[：:]\s*([^\n]+)/)
    if (m) return m[1].trim()
  }
  if (layer === 4) {
    const m = content.match(/主题[：:]\s*([^\n]+)/)
    if (m) return m[1].trim()
  }
  const match = content.match(/^## (.+)$/m)
  if (match) return match[1].trim()
  if (selectedMemory.value.category) {
    return categoryMap[selectedMemory.value.category] || selectedMemory.value.category
  }
  return '记忆详情'
})

const detailTime = computed(() => {
  if (!selectedMemory.value) return ''
  const content = selectedMemory.value.content || selectedMemory.value.raw_content || ''
  const match = content.match(/\*\*时间\*\*:\s*(.+)/)
  if (match) return match[1].trim()
  return formatDisplayTime(selectedMemory.value)
})

const detailSource = computed(() => {
  if (!selectedMemory.value) return ''
  const content = selectedMemory.value.content || selectedMemory.value.raw_content || ''
  const match = content.match(/\*\*来源\*\*:\s*(.+)/)
  if (match) return match[1].trim()
  const source = selectedMemory.value.source
  return source ? sourceMap[source] || source : ''
})

const detailSession = computed(() => {
  if (!selectedMemory.value) return ''
  const content = selectedMemory.value.content || selectedMemory.value.raw_content || ''
  const match = content.match(/\*\*会话\*\*:\s*(.+)/)
  if (match) return match[1].trim()
  const meta = selectedMemory.value.metadata
  if (meta?.turn_number) return `第${meta.turn_number}轮`
  return ''
})

const detailCategory = computed(() => {
  if (!selectedMemory.value) return ''
  const category = selectedMemory.value.category
  return category ? categoryMap[category] || category : ''
})

const detailParentLabel = computed(() => {
  if (!selectedMemory.value) return ''
  return getParentLabelText(selectedMemory.value)
})

const detailKeyInfo = computed(() => {
  if (!selectedMemory.value) return ''
  const content = selectedMemory.value.content || selectedMemory.value.raw_content || ''
  const match = content.match(/\*\*关键信息\*\*:\s*(.+)/)
  return match ? match[1].trim() : ''
})

const detailTags = computed(() => {
  if (!selectedMemory.value) return []
  const content = selectedMemory.value.content || selectedMemory.value.raw_content || ''
  const match = content.match(/\*\*标签\*\*:\s*(.+)/)
  if (match) {
    return match[1].trim().split(/\s+/).filter((t: string) => t.startsWith('#')).map((t: string) => t.replace('#', ''))
  }
  if (Array.isArray(selectedMemory.value.tags)) {
    return selectedMemory.value.tags.slice(0, 5)
  }
  return []
})

const detailChildTargetLayer = computed(() => {
  if (!selectedMemory.value) return 0
  const layer = getLayer(selectedMemory.value)
  if (layer === 3) return 4
  if (layer === 5) return 6
  return 0
})

const detailChildSectionTitle = computed(() => {
  if (detailChildTargetLayer.value === 4) return '该分类下的 L4 内容'
  if (detailChildTargetLayer.value === 6) return '该分类下的 L6 内容'
  return ''
})

const detailChildItems = computed(() => {
  if (!selectedMemory.value || !detailChildTargetLayer.value) return []
  const category = (selectedMemory.value.category || '').trim()
  if (!category) return []

  return memories.value
    .filter(memory => {
      return (
        memory.id !== selectedMemory.value.id &&
        getLayer(memory) === detailChildTargetLayer.value &&
        (memory.category || '').trim() === category
      )
    })
    .sort((a, b) => {
      const dateA = new Date(getDisplayTime(a) || 0).getTime()
      const dateB = new Date(getDisplayTime(b) || 0).getTime()
      return dateB - dateA
    })
})

const renderedContent = computed(() => {
  if (!selectedMemory.value) return ''
  const content = selectedMemory.value.content || selectedMemory.value.raw_content || ''
  return renderMemoryDetailMarkdown(content)
})
</script>

<style scoped>
.view-container { padding: 24px; height: 100%; overflow-y: auto; overflow-x: hidden; }
.view-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
.view-header h2 { font-size: 24px; font-weight: 700; color: var(--color-text); margin: 0; }
.header-actions { display: flex; gap: 10px; align-items: center; }
.search-box { display: flex; align-items: center; gap: 8px; padding: 8px 12px; width: 240px; background: var(--color-surface); border: 1px solid var(--color-border); border-radius: 8px; }
.search-icon { font-size: 13px; }
.search-input { flex: 1; border: none; outline: none; font-size: 13px; background: transparent; color: var(--color-text); }
.search-input::placeholder { color: var(--color-text-secondary); }
.clear-btn { background: none; border: none; cursor: pointer; font-size: 13px; color: var(--color-text-secondary); padding: 0; }
.clear-btn:hover { color: var(--color-text); }
.btn-primary { padding: 8px 16px; border: none; border-radius: 8px; background: var(--color-primary); color: var(--color-text-on-primary); font-size: 13px; cursor: pointer; font-weight: 500; }
.btn-primary:hover:not(:disabled) { background: var(--color-primary-hover, #2563eb); }
.btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-secondary { padding: 8px 16px; border: 1px solid var(--color-border); border-radius: 8px; background: var(--color-surface); color: var(--color-text); font-size: 13px; cursor: pointer; font-weight: 500; }
.btn-secondary:hover:not(:disabled) { background: var(--color-bg); }
.btn-secondary:disabled { opacity: 0.6; cursor: not-allowed; }
.btn-danger { padding: 8px 16px; border: none; border-radius: 8px; background: var(--color-error); color: var(--color-text-on-primary); font-size: 13px; cursor: pointer; font-weight: 500; }
.btn-danger:hover { background: var(--color-error-hover); }
.btn-organize { padding: 8px 16px; border: 1px solid var(--color-primary); border-radius: 8px; background: var(--color-primary-bg, rgba(59, 130, 246, 0.08)); color: var(--color-primary); font-size: 13px; cursor: pointer; font-weight: 500; transition: all 0.15s; }
.btn-organize:hover:not(:disabled) { background: var(--color-primary); color: var(--color-text-on-primary); }
.btn-organize:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-quick { border-color: var(--color-success); background: var(--color-success-bg, rgba(16, 185, 129, 0.08)); color: var(--color-success); }
.btn-quick:hover:not(:disabled) { background: var(--color-success); color: var(--color-text-on-primary); }

.filter-bar { display: flex; flex-direction: column; gap: 8px; margin-bottom: 20px; padding: 10px 14px; background: var(--color-surface); border-radius: 8px; border: 1px solid var(--color-border); }
.level-buttons { display: flex; gap: 6px; flex-wrap: wrap; }
.level-btn { padding: 5px 12px; border: 1px solid var(--color-border); border-radius: 6px; background: var(--color-surface); color: var(--color-text-secondary); font-size: 12px; cursor: pointer; font-weight: 500; transition: all 0.15s; white-space: nowrap; }
.level-btn:hover { border-color: var(--color-primary); color: var(--color-primary); }
.level-btn.active { background: var(--color-primary); color: var(--color-text-on-primary); border-color: var(--color-primary); }
.level-btn.l1.active { background: var(--color-level-1); border-color: var(--color-level-1); }
.level-btn.l2.active { background: var(--color-level-2); border-color: var(--color-level-2); }
.level-btn.l3.active { background: var(--color-level-3); border-color: var(--color-level-3); }
.level-btn.l4.active { background: var(--color-level-4); border-color: var(--color-level-4); }
.level-btn.l5.active { background: var(--color-level-5); border-color: var(--color-level-5); }
.level-btn.l6.active { background: var(--color-level-6); border-color: var(--color-level-6); }
.filter-controls { display: flex; gap: 8px; flex-wrap: wrap; }
.filter-select { padding: 5px 10px; border: 1px solid var(--color-border); border-radius: 6px; font-size: 12px; background: var(--color-surface); color: var(--color-text); outline: none; cursor: pointer; }

.empty-state { text-align: center; padding: 40px 20px; color: var(--color-text-secondary); }
.empty-icon { font-size: 36px; margin-bottom: 10px; }

.skeleton-block { background: linear-gradient(90deg, #f0f0f0 25%, #e0e0e0 50%, #f0f0f0 75%); background-size: 200% 100%; animation: shimmer 1.5s infinite linear; border-radius: 4px; }
@keyframes shimmer { 0% { background-position: 200% 0; } 100% { background-position: -200% 0; } }
.skeleton-card { pointer-events: none; border-color: transparent; }

.memory-list { display: flex; flex-direction: column; gap: 8px; }
.memory-lists-container { display: flex; flex-direction: column; gap: 8px; }
.empty-search-state { text-align: center; padding: 40px 20px; color: var(--color-text-secondary); background: var(--color-surface); border: 1px dashed var(--color-border); border-radius: 8px; margin-top: 10px; }
.archived-section { margin-top: 24px; }
.archived-header { display: flex; justify-content: space-between; align-items: center; padding: 12px 16px; background: var(--color-bg); border: 1px solid var(--color-border); border-radius: 8px; cursor: pointer; transition: all 0.2s; user-select: none; margin-bottom: 12px; }
.archived-header:hover { border-color: var(--color-primary); background: var(--color-surface); }
.archived-header-left { display: flex; align-items: center; gap: 8px; }
.archived-icon { font-size: 16px; }
.archived-title { font-weight: 600; color: var(--color-text); font-size: 14px; }
.archived-subtitle { font-size: 12px; color: var(--color-text-secondary); margin-left: 8px; }
.archived-toggle { font-size: 12px; color: var(--color-text-secondary); font-weight: 500; }
.archived-content { display: flex; flex-direction: column; gap: 8px; }
.archived-card { opacity: 0.85; background: var(--color-bg); }
.archived-card:hover { opacity: 1; background: var(--color-surface); }
.memory-card { background: var(--color-surface); border: 1px solid var(--color-border); border-radius: 8px; padding: 10px 14px; cursor: pointer; transition: all 0.2s; }
.memory-card:hover { border-color: var(--color-primary); box-shadow: 0 2px 8px rgba(99, 102, 241, 0.1); }
.memory-header { display: flex; align-items: center; gap: 8px; margin-bottom: 5px; }
.memory-level { background: var(--color-primary); color: var(--color-text-on-primary); padding: 1px 6px; border-radius: 4px; font-size: 11px; font-weight: 600; }
.memory-level.l1 { background: var(--color-level-1); }
.memory-level.l2 { background: var(--color-level-2); }
.memory-level.l3 { background: var(--color-level-3); }
.memory-level.l4 { background: var(--color-level-4); }
.memory-level.l5 { background: var(--color-level-5); }
.memory-level.l6 { background: var(--color-level-6); }
.memory-title { font-weight: 500; color: var(--color-text); flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 13px; }
.memory-source { font-size: 10px; color: var(--color-primary); background: var(--color-primary-bg, rgba(59, 130, 246, 0.08)); padding: 1px 6px; border-radius: 4px; white-space: nowrap; flex-shrink: 0; }
.memory-content { color: var(--color-text-secondary); font-size: 12px; margin: 0 0 6px; line-height: 1.45; }
.memory-footer { display: flex; justify-content: space-between; align-items: center; }
.memory-tags { display: flex; gap: 5px; flex-wrap: wrap; }
.tag { background: var(--color-bg); color: var(--color-text-secondary); padding: 1px 6px; border-radius: 4px; font-size: 11px; }
.parent-tag { background: var(--color-primary-bg, rgba(59, 130, 246, 0.08)); color: var(--color-primary); }
.category-tag { background: var(--color-primary-bg); color: var(--color-violet); }
.memory-date { font-size: 11px; color: var(--color-text-secondary); white-space: nowrap; flex-shrink: 0; margin-left: 8px; }

.pagination-bar { display: flex; justify-content: space-between; align-items: center; padding: 10px 0; margin-top: 8px; border-top: 1px solid var(--color-border); }
.pagination-left { display: flex; align-items: center; gap: 10px; }
.pagination-total { font-size: 12px; color: var(--color-text-secondary); }
.page-size-select { padding: 4px 8px; border: 1px solid var(--color-border); border-radius: 6px; font-size: 12px; background: var(--color-surface); color: var(--color-text); outline: none; cursor: pointer; }
.pagination-right { display: flex; align-items: center; gap: 6px; }
.page-btn { padding: 4px 10px; border: 1px solid var(--color-border); border-radius: 6px; background: var(--color-surface); color: var(--color-text); font-size: 12px; cursor: pointer; transition: all 0.15s; }
.page-btn:hover:not(:disabled) { border-color: var(--color-primary); color: var(--color-primary); }
.page-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.page-info { font-size: 12px; color: var(--color-text-secondary); min-width: 40px; text-align: center; }

.modal-overlay { position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: var(--color-overlay); display: flex; align-items: center; justify-content: center; z-index: 100; }
.modal-fade-enter-active, .modal-fade-leave-active { transition: opacity 0.2s ease; }
.modal-fade-enter-from, .modal-fade-leave-to { opacity: 0; }
.modal { background: var(--color-surface); border-radius: 12px; padding: 24px; width: 500px; max-width: 90vw; }
.modal.detail-modal { width: 700px; max-width: 90vw; }
.modal.modal-small { width: 400px; }
.modal h3 { margin: 0 0 16px; font-size: 18px; }
.modal-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.modal-header h3 { margin: 0; }
.memory-detail-content {
  max-height: 420px;
  overflow-y: auto;
  padding: 10px 0;
  background: transparent;
  border: none;
}

.markdown-body {
  font-size: 14px;
  line-height: 1.7;
  color: var(--color-text);
  word-break: break-word;
}

.markdown-body :deep(h1) {
  font-size: 22px;
  font-weight: 700;
  margin: 0 0 16px 0;
  padding-bottom: 8px;
  border-bottom: 2px solid var(--color-border);
  color: var(--color-text);
}

.markdown-body :deep(h2) {
  font-size: 18px;
  font-weight: 600;
  margin: 20px 0 12px 0;
  color: var(--color-text);
}

.markdown-body :deep(h3) {
  font-size: 16px;
  font-weight: 600;
  margin: 16px 0 10px 0;
  color: var(--color-text);
}

.markdown-body :deep(p) {
  margin: 0 0 14px 0;
}

.markdown-body :deep(ul),
.markdown-body :deep(ol) {
  margin: 0 0 14px 0;
  padding-left: 24px;
}

.markdown-body :deep(li) {
  margin-bottom: 6px;
}

.markdown-body :deep(blockquote) {
  margin: 0 0 16px 0;
  padding: 10px 16px;
  color: var(--color-text-secondary);
  background: var(--color-surface);
  border-left: 4px solid var(--color-primary);
  border-radius: 4px;
}

.markdown-body :deep(pre) {
  margin: 0 0 16px 0;
  padding: 16px;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 8px;
  overflow-x: auto;
}

.markdown-body :deep(code) {
  font-family: ui-monospace, SFMono-Regular, Consolas, "Liberation Mono", Menlo, monospace;
  font-size: 13px;
  padding: 2px 6px;
  background: var(--color-surface);
  border-radius: 4px;
}

.markdown-body :deep(pre code) {
  padding: 0;
  background: transparent;
}

.markdown-body :deep(a) {
  color: var(--color-primary);
  text-decoration: none;
}

.markdown-body :deep(a:hover) {
  text-decoration: underline;
}

.markdown-body :deep(table) {
  border-collapse: collapse;
  width: 100%;
  margin: 0 0 16px 0;
}

.markdown-body :deep(th),
.markdown-body :deep(td) {
  border: 1px solid var(--color-border);
  padding: 8px 12px;
  text-align: left;
}

.markdown-body :deep(th) {
  background: var(--color-surface);
  font-weight: 600;
}

.markdown-body :deep(hr) {
  height: 1px;
  background: var(--color-border);
  border: none;
  margin: 24px 0;
}
.detail-metadata { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 16px; padding: 0 0 16px 0; background: transparent; border-bottom: 1px solid var(--color-border); border-radius: 0; }
.detail-metadata .meta-item { font-size: 12px; color: var(--color-text-secondary); background: var(--color-bg); border: 1px solid var(--color-border); padding: 4px 12px; border-radius: 999px; white-space: nowrap; }
.detail-related-section { margin-top: 12px; padding-top: 12px; border-top: 1px solid var(--color-border); }
.detail-related-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px; }
.detail-related-title { font-size: 13px; font-weight: 600; color: var(--color-text); }
.detail-related-count { font-size: 12px; color: var(--color-text-secondary); }
.detail-related-list { display: flex; flex-direction: column; gap: 8px; }
.detail-related-item { width: 100%; display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 10px 12px; border: 1px solid var(--color-border); border-radius: 8px; background: var(--color-bg); color: var(--color-text); cursor: pointer; transition: all 0.15s; text-align: left; }
.detail-related-item:hover { border-color: var(--color-primary); background: var(--color-surface); }
.detail-related-item-title { flex: 1; font-size: 13px; font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.detail-related-item-level { font-size: 11px; color: var(--color-primary); background: var(--color-primary-bg, rgba(59, 130, 246, 0.08)); padding: 3px 8px; border-radius: 999px; white-space: nowrap; }
.detail-related-empty { padding: 12px; border: 1px dashed var(--color-border); border-radius: 8px; background: var(--color-bg); color: var(--color-text-secondary); font-size: 13px; text-align: center; }
.detail-footer { margin-top: 12px; padding-top: 12px; border-top: 1px solid var(--color-border); }
.key-info { margin-bottom: 10px; }
.key-info-label { font-size: 13px; color: var(--color-text-secondary); font-weight: 500; }
.key-info-value { font-size: 13px; color: var(--color-text); margin-left: 4px; }
.detail-tags { display: flex; flex-wrap: wrap; gap: 6px; }
.detail-tag { background: var(--color-primary-bg, rgba(59, 130, 246, 0.08)); color: var(--color-primary); padding: 3px 10px; border-radius: 6px; font-size: 12px; }
.detail-meta { display: flex; gap: 16px; margin-top: 10px; font-size: 12px; color: var(--color-text-secondary); }
.confirm-text { font-size: 14px; color: var(--color-text); margin: 0 0 8px; }
.confirm-preview { font-size: 13px; color: var(--color-text-secondary); background: var(--color-bg); padding: 8px 12px; border-radius: 6px; margin: 0 0 16px; }
.memory-textarea { width: 100%; min-height: 120px; padding: 12px; border: 1px solid var(--color-border); border-radius: 8px; font-size: 14px; resize: vertical; outline: none; font-family: inherit; }
.memory-textarea:focus { border-color: var(--color-primary); }
.modal-actions { display: flex; justify-content: flex-end; gap: 10px; margin-top: 16px; }
.modal-actions.space-between { justify-content: space-between; }

.organize-info { display: flex; flex-direction: column; gap: 16px; margin-bottom: 24px; }
.info-section { background: var(--color-bg); padding: 12px 16px; border-radius: 8px; border: 1px solid var(--color-border); }
.info-section h4 { margin: 0 0 8px 0; font-size: 14px; color: var(--color-text); display: flex; align-items: center; gap: 6px; }
.info-section p { margin: 0; font-size: 13px; color: var(--color-text-secondary); line-height: 1.6; }
.info-section.warning { background: var(--color-error-bg, rgba(239, 68, 68, 0.08)); border-color: rgba(239, 68, 68, 0.2); }
.info-section.warning h4 { color: var(--color-error); }
.info-section strong { color: var(--color-text); font-weight: 600; }
.info-section.warning strong { color: var(--color-error); }

.form-field { margin-bottom: 14px; }
.form-label { display: block; font-size: 13px; font-weight: 500; color: var(--color-text-secondary); margin-bottom: 6px; }
.level-select-buttons { display: flex; gap: 6px; flex-wrap: wrap; }
.level-select-btn { padding: 5px 12px; border: 1px solid var(--color-border); border-radius: 6px; background: var(--color-surface); color: var(--color-text-secondary); font-size: 12px; cursor: pointer; font-weight: 500; transition: all 0.15s; white-space: nowrap; }
.level-select-btn:hover { border-color: var(--color-primary); color: var(--color-primary); }
.level-select-btn.active { color: var(--color-text-on-primary); border-color: transparent; }
.level-select-btn.l1.active { background: var(--color-level-1); }
.level-select-btn.l2.active { background: var(--color-level-2); }
.level-select-btn.l3.active { background: var(--color-level-3); }
.level-select-btn.l4.active { background: var(--color-level-4); }
.level-select-btn.l5.active { background: var(--color-level-5); }
.level-select-btn.l6.active { background: var(--color-level-6); }
.tag-input-container { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; padding: 8px; border: 1px solid var(--color-border); border-radius: 8px; min-height: 38px; }
.tag-input-container:focus-within { border-color: var(--color-primary); }
.tag-item { display: flex; align-items: center; gap: 4px; background: var(--color-primary-bg, rgba(59, 130, 246, 0.08)); color: var(--color-primary); padding: 3px 8px; border-radius: 4px; font-size: 12px; }
.tag-remove { background: none; border: none; cursor: pointer; color: var(--color-primary); font-size: 14px; padding: 0; line-height: 1; }
.tag-remove:hover { color: var(--color-error); }
.tag-input { border: none; outline: none; font-size: 13px; flex: 1; min-width: 80px; background: transparent; color: var(--color-text); }
.tag-suggestions { margin-top: 6px; display: flex; flex-wrap: wrap; gap: 4px; align-items: center; }
.tag-suggestion-label { font-size: 11px; color: var(--color-text-secondary); }
.tag-suggestion-btn { position: relative; padding: 4px 10px; border: 1px solid var(--color-border); border-radius: 4px; background: var(--color-surface); color: var(--color-text-secondary); font-size: 11px; cursor: pointer; transition: all 0.15s; display: inline-flex; align-items: center; gap: 4px; }
.tag-suggestion-btn:hover { border-color: var(--color-primary); color: var(--color-primary); }
.tag-suggestion-btn.active { background: var(--color-primary-bg); color: var(--color-primary); border-color: var(--color-primary); }
.tag-remove-user { display: inline-block; margin-left: 2px; width: 14px; height: 14px; line-height: 12px; text-align: center; border-radius: 50%; color: var(--color-text-secondary); }
.tag-remove-user:hover { background: rgba(239, 68, 68, 0.1); color: var(--color-error); }
</style>
