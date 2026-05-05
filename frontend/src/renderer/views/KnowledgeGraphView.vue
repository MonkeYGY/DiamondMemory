<template>
  <div class="view-container">
    <div class="view-header">
      <div class="header-text">
        <h2>知识图谱</h2>
        <p class="subtitle">记忆关联网络可视化</p>
      </div>
      <div class="header-actions">
        <div class="filter-group">
          <div class="layer-buttons">
            <button
              class="btn-layer"
              :class="{ active: focusedLayer === null }"
              @click="setFocusedLayer(null)"
            >全部</button>
            <button
              v-for="l in [1,2,3,4,5,6]"
              :key="l"
              class="btn-layer"
              :class="{ active: focusedLayer === l }"
              :style="focusedLayer === l ? { background: getLayerColor(l) + '20', borderColor: getLayerColor(l), color: getLayerColor(l) } : {}"
              @click="setFocusedLayer(l)"
            >L{{ l }}</button>
          </div>
          <select v-model="filterCategory" class="filter-select" @change="fetchGraphData">
            <option :value="null">全部分类</option>
            <option v-for="cat in categories" :key="cat" :value="cat">{{ cat }}</option>
          </select>
          <button
            class="btn-toggle"
            :class="{ active: showEntities }"
            @click="toggleEntities"
            title="显示/隐藏实体节点"
          >
            {{ showEntities ? '● 实体' : '○ 实体' }}
          </button>
        </div>
        <button class="btn-refresh" @click="fetchGraphData" :disabled="loading">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M21.5 2v6h-6M2.5 22v-6h6M2 11.5a10 10 0 0 1 18.8-4.3M22 12.5a10 10 0 0 1-18.8 4.2"/>
          </svg>
          刷新
        </button>
      </div>
    </div>

    <div class="graph-stats" v-if="graphStats">
      <div class="graph-stat-item">
        <span class="graph-stat-value">{{ graphStats.memory_count }}</span>
        <span class="graph-stat-label">记忆节点</span>
      </div>
      <div class="graph-stat-item">
        <span class="graph-stat-value">{{ showEntities ? graphStats.entity_count : 0 }}</span>
        <span class="graph-stat-label">实体节点</span>
      </div>
      <div class="graph-stat-item">
        <span class="graph-stat-value">{{ displayEdgeCount }}</span>
        <span class="graph-stat-label">关联边</span>
      </div>
    </div>

    <div class="graph-wrapper" ref="graphWrapper">
      <div v-if="loading" class="graph-loading">
        <div class="loading-spinner"></div>
        <span>正在加载图谱数据...</span>
      </div>
      <div v-else-if="!graphData || graphData.nodes.length === 0" class="graph-empty">
        <div class="empty-icon">🕸️</div>
        <h3>暂无图谱数据</h3>
        <p>系统中还没有足够的记忆数据来构建知识图谱</p>
      </div>
      <canvas
        v-show="!loading && graphData && graphData.nodes.length > 0"
        ref="canvasRef"
        @mousedown="onCanvasMouseDown"
        @mousemove="onCanvasMouseMove"
        @mouseup="onCanvasMouseUp"
        @wheel="onCanvasWheel"
        @dblclick="onCanvasDblClick"
      ></canvas>
    </div>

    <div v-if="hoveredNode" class="node-tooltip" :style="tooltipStyle">
      <div class="tooltip-header">
        <span class="tooltip-type" :class="hoveredNode.type">{{ hoveredNode.type === 'memory' ? '记忆' : '实体' }}</span>
        <span v-if="hoveredNode.type === 'memory'" class="tooltip-layer" :style="{ color: getLayerColor(hoveredNode.layer || 1) }">L{{ hoveredNode.layer }}</span>
      </div>
      <div class="tooltip-content" v-if="hoveredNode.type === 'memory'">
        {{ hoveredNode.content_preview || '无内容预览' }}
      </div>
      <div class="tooltip-content" v-else>
        {{ hoveredNode.text || '未知实体' }}
      </div>
      <div class="tooltip-meta" v-if="hoveredNode.type === 'memory'">
        <span v-if="hoveredNode.category">{{ hoveredNode.category }}</span>
        <span>{{ hoveredNode.degree }} 个关联</span>
      </div>
    </div>

    <div v-if="selectedNode" class="detail-panel">
      <div class="detail-header">
        <h3>{{ selectedNode.type === 'memory' ? '记忆详情' : '实体详情' }}</h3>
        <button class="detail-close" @click="selectedNode = null">✕</button>
      </div>
      <div class="detail-body">
        <template v-if="selectedNode.type === 'memory'">
          <div class="detail-field">
            <span class="detail-label">层级</span>
            <span class="detail-value layer-badge" :style="{ background: getLayerColor(selectedNode.layer || 1) + '20', color: getLayerColor(selectedNode.layer || 1) }">L{{ selectedNode.layer }}</span>
          </div>
          <div class="detail-field" v-if="selectedNode.category">
            <span class="detail-label">分类</span>
            <span class="detail-value">{{ selectedNode.category }}</span>
          </div>
          <div class="detail-field">
            <span class="detail-label">内容</span>
            <span class="detail-value content-text">{{ selectedNode.content_preview || '无内容' }}</span>
          </div>
          <div class="detail-field" v-if="selectedNode.tags && selectedNode.tags.length">
            <span class="detail-label">标签</span>
            <div class="detail-tags">
              <span v-for="tag in selectedNode.tags" :key="tag" class="detail-tag">{{ tag }}</span>
            </div>
          </div>
          <div class="detail-field">
            <span class="detail-label">关联数</span>
            <span class="detail-value">{{ selectedNode.degree }}</span>
          </div>
          <div class="detail-field" v-if="selectedNode.created_at">
            <span class="detail-label">创建时间</span>
            <span class="detail-value">{{ selectedNode.created_at }}</span>
          </div>
          <button class="btn-related" @click="fetchRelatedMemories(selectedNode.id)" :disabled="loadingRelated">
            {{ loadingRelated ? '加载中...' : '查看关联记忆' }}
          </button>
          <div v-if="relatedMemories.length" class="related-list">
            <div
              v-for="mem in relatedMemories"
              :key="mem.id"
              class="related-item"
              :class="{ 'related-item-active': selectedNode?.id === mem.id }"
              @click="selectRelatedMemory(mem)"
            >
              <span class="related-layer" :style="{ color: getLayerColor(mem.layer || mem.level) }">L{{ mem.layer || mem.level }}</span>
              <span class="related-content">{{ getRelatedPreview(mem) }}</span>
            </div>
          </div>
        </template>
        <template v-else>
          <div class="detail-field">
            <span class="detail-label">实体名称</span>
            <span class="detail-value">{{ selectedNode.text }}</span>
          </div>
          <div class="detail-field" v-if="selectedNode.entity_type">
            <span class="detail-label">实体类型</span>
            <span class="detail-value">{{ selectedNode.entity_type }}</span>
          </div>
          <div class="detail-field">
            <span class="detail-label">关联记忆数</span>
            <span class="detail-value">{{ selectedNode.degree }}</span>
          </div>
        </template>
      </div>
    </div>

    <div class="graph-legend" v-if="graphData && graphData.nodes.length > 0">
      <div class="legend-item">
        <span class="legend-dot memory"></span>
        <span>记忆节点</span>
      </div>
      <div class="legend-item" v-if="showEntities">
        <span class="legend-dot entity"></span>
        <span>实体节点</span>
      </div>
      <div class="legend-separator"></div>
      <div class="legend-item" v-for="l in [1,2,3,4,5,6]" :key="l">
        <span class="legend-dot" :style="{ background: getLayerColor(l) }"></span>
        <span>L{{ l }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed, nextTick } from 'vue'
import { apiRequest } from '../api/backend'
import { useInterval } from '../composables/useTimer'
import { APP_CONFIG } from '../config/constants'
import { GRAPH_REFRESH_EVENT } from '../utils/graph-events'

interface GraphNode {
  id: string
  type: 'memory' | 'entity'
  category?: string
  layer?: number
  content_preview?: string
  short_name?: string
  entity_type?: string
  text?: string
  degree: number
  created_at?: string
  is_pinned?: boolean
  tags?: string[]
}

interface GraphEdge {
  source: string
  target: string
}

interface SimNode extends GraphNode {
  x: number
  y: number
  vx: number
  vy: number
  radius: number
  fx?: number
  fy?: number
}

const canvasRef = ref<HTMLCanvasElement | null>(null)
const graphWrapper = ref<HTMLElement | null>(null)
const loading = ref(false)
const loadingRelated = ref(false)
const graphData = ref<{ nodes: GraphNode[]; edges: GraphEdge[]; stats: any } | null>(null)
const graphStats = ref<any>(null)
const filterLayer = ref<number | null>(null)
const focusedLayer = ref<number | null>(null)
const filterCategory = ref<string | null>(null)
const categories = ref<string[]>([])
const showEntities = ref(false)
const hoveredNode = ref<SimNode | null>(null)
const selectedNode = ref<SimNode | null>(null)
const relatedMemories = ref<any[]>([])

const simNodes = ref<SimNode[]>([])
const simEdges = ref<{ source: string; target: string }[]>([])
const nodeMap = ref<Map<string, SimNode>>(new Map())

let animFrameId = 0
let canvasWidth = 0
let canvasHeight = 0
let dpr = 1
let panX = 0
let panY = 0
let zoom = 1
let isDragging = false
let dragNode: SimNode | null = null
let isPanning = false
let lastMouseX = 0
let lastMouseY = 0
let mouseX = 0
let mouseY = 0
let dragStartX = 0
let dragStartY = 0
let dragOffsetX = 0
let dragOffsetY = 0
let panFromNonNavigable = false
let simulationAlpha = 1
let frameCount = 0
let prevSelectedNode: SimNode | null = null
let dragStarted = false

const displayEdgeCount = computed(() => {
  if (!showEntities.value && graphData.value) {
    const memIds = new Set(graphData.value.nodes.filter(n => n.type === 'memory').map(n => n.id))
    return simEdges.value.filter(e => memIds.has(e.source) && memIds.has(e.target)).length
  }
  return simEdges.value.length
})

const tooltipStyle = computed(() => {
  if (!hoveredNode.value) return { display: 'none' }
  const rect = graphWrapper.value?.getBoundingClientRect()
  if (!rect) return { display: 'none' }
  let left = mouseX - rect.left + 16
  let top = mouseY - rect.top - 10
  if (left + 280 > rect.width) left = mouseX - rect.left - 290
  if (top + 120 > rect.height) top = rect.height - 130
  return {
    left: `${left}px`,
    top: `${top}px`,
  }
})

function getLayerColor(layer: number): string {
  const colors: Record<number, string> = {
    1: '#6366f1',
    2: '#3b82f6',
    3: '#10b981',
    4: '#f59e0b',
    5: '#8b5cf6',
    6: '#ec4899',
  }
  return colors[layer] || '#64748b'
}

function getNodeRadius(node: GraphNode): number {
  if (node.type === 'entity') {
    return Math.max(3, Math.min(7, 2.5 + (node.degree || 0) * 0.4))
  }
  
  // 层级大小映射：L5 > L6 > L3 > L4 > L2 > L1
  const layer = node.layer || 1
  let baseRadius = 6 // 默认值
  let maxBonus = 2   // 限制关联度带来的最大加成，防止低层级因关联度过高而超过高层级
  switch (layer) {
    case 5: baseRadius = 24; maxBonus = 6; break // L5 最大
    case 6: baseRadius = 20; maxBonus = 5; break // L6
    case 3: baseRadius = 16; maxBonus = 4; break // L3
    case 4: baseRadius = 12; maxBonus = 3; break // L4
    case 2: baseRadius = 8;  maxBonus = 2; break // L2
    case 1: baseRadius = 5;  maxBonus = 1.5; break // L1 最小
  }
  
  // 基础大小占绝对主导，关联度（degree）的加成被严格限制在 maxBonus 以内
  // 使用对数增长（Math.log）来压制极端关联度（如 116 个关联）带来的膨胀
  const degreeBonus = Math.min(maxBonus, Math.log1p(node.degree || 0) * 0.8)
  return baseRadius + degreeBonus
}

function getRelatedPreview(mem: any): string {
  if (mem.short_name) return mem.short_name
  const content = mem.content || mem.content_preview || ''
  const layer = mem.layer ?? 0
  if (mem.title) return mem.title
  if (layer === 6) {
    const m = content.match(/技能名称[：:]\s*([^\n]+)/)
    if (m) return m[1].trim()
  }
  if (layer === 4) {
    const m = content.match(/主题[：:]\s*([^\n]+)/)
    if (m) return m[1].trim()
  }
  const lines = content.split('\n')
  for (const line of lines) {
    const stripped = line.trim()
    if (!stripped || stripped.startsWith('#') || stripped.startsWith('---') || stripped.startsWith('**')) continue
    if (/^(主题|技能名称|核心要点|详细记录|目标任务|触发条件|包含步骤|涉及工具|最佳实践|依赖|注意事项)[：:]/.test(stripped)) {
      return stripped.replace(/^(主题|技能名称|核心要点|详细记录|目标任务|触发条件|包含步骤|涉及工具|最佳实践|依赖|注意事项)[：:]\s*/, '')
    }
    return stripped.length > 80 ? stripped.slice(0, 80) + '...' : stripped
  }
  return content.substring(0, 80)
}

function setFocusedLayer(layer: number | null) {
  focusedLayer.value = layer
  selectNode(null)
  relatedMemories.value = []
}

function selectNode(node: SimNode | null) {
  if (prevSelectedNode && prevSelectedNode !== node) {
    prevSelectedNode.fx = undefined
    prevSelectedNode.fy = undefined
  }
  selectedNode.value = node
  if (node) {
    node.fx = node.x
    node.fy = node.y
  }
  prevSelectedNode = node
}

function computeNavigableNodeIds(): { ids: Set<string>; all: boolean } {
  if (focusedLayer.value === null) {
    return { ids: new Set(), all: true }
  }
  const ids = new Set<string>()
  const sel = selectedNode.value
  if (!sel) {
    for (const node of simNodes.value) {
      if (node.type === 'memory' && node.layer === focusedLayer.value) {
        ids.add(node.id)
      }
    }
  } else {
    ids.add(sel.id)
    for (const edge of simEdges.value) {
      if (edge.source === sel.id) ids.add(edge.target)
      if (edge.target === sel.id) ids.add(edge.source)
    }
  }
  return { ids, all: false }
}

function toggleEntities() {
  showEntities.value = !showEntities.value
  if (graphData.value) initSimulation(graphData.value.nodes, graphData.value.edges)
}

async function fetchGraphData(isBackground: boolean | Event = false, force = false) {
  const isBg = typeof isBackground === 'boolean' ? isBackground : false
  if (!isBg) loading.value = true
  try {
    let endpoint = '/api/memory/graph?limit=200&max_entities=80'
    if (filterLayer.value) endpoint += `&layer=${filterLayer.value}`
    if (filterCategory.value) endpoint += `&category=${encodeURIComponent(filterCategory.value)}`
    if (force) endpoint += '&force=1'
    const data = await apiRequest<{ nodes: GraphNode[]; edges: GraphEdge[]; stats: any }>(endpoint)
    graphData.value = data
    graphStats.value = data.stats
    if (isBg && simNodes.value.length > 0) {
      updateSimulationIncremental(data.nodes, data.edges)
    } else {
      initSimulation(data.nodes, data.edges)
    }
    extractCategories(data.nodes)
  } catch (error) {
    console.error('获取图谱数据失败:', error)
  } finally {
    if (!isBg) loading.value = false
  }
}

function extractCategories(nodes: GraphNode[]) {
  const cats = new Set<string>()
  for (const n of nodes) {
    if (n.type === 'memory' && n.category) cats.add(n.category)
  }
  categories.value = Array.from(cats).sort()
}

function initSimulation(nodes: GraphNode[], edges: GraphEdge[]) {
  prevSelectedNode = null
  selectedNode.value = null
  relatedMemories.value = []
  const cx = canvasWidth / 2
  const cy = canvasHeight / 2
  const newNodes: SimNode[] = []
  const newMap = new Map<string, SimNode>()

  const memNodes = nodes.filter(n => n.type === 'memory')
  const entNodes = showEntities.value ? nodes.filter(n => n.type === 'entity') : []

  const totalNodes = memNodes.length + entNodes.length
  let idx = 0
  for (const n of memNodes) {
    const angle = (idx / totalNodes) * Math.PI * 2 * 3
    const radiusBase = Math.min(canvasWidth, canvasHeight) * 0.32
    const dist = radiusBase + (idx % 7) * 25
    const sn: SimNode = {
      ...n,
      x: cx + Math.cos(angle) * dist,
      y: cy + Math.sin(angle) * dist,
      vx: 0,
      vy: 0,
      radius: getNodeRadius(n),
    }
    newNodes.push(sn)
    newMap.set(n.id, sn)
    idx++
  }

  for (const n of entNodes) {
    const angle = Math.random() * Math.PI * 2
    const dist = Math.random() * Math.min(canvasWidth, canvasHeight) * 0.35
    const sn: SimNode = {
      ...n,
      x: cx + Math.cos(angle) * dist,
      y: cy + Math.sin(angle) * dist,
      vx: 0,
      vy: 0,
      radius: getNodeRadius(n),
    }
    newNodes.push(sn)
    newMap.set(n.id, sn)
  }

  simNodes.value = newNodes
  simEdges.value = edges.filter(e => newMap.has(e.source) && newMap.has(e.target))
  nodeMap.value = newMap
  simulationAlpha = 1
  frameCount = 0
  panX = 0
  panY = 0
  zoom = 1
}

function updateSimulationIncremental(nodes: GraphNode[], edges: GraphEdge[]) {
  const cx = canvasWidth / 2
  const cy = canvasHeight / 2
  const nextNodes: SimNode[] = []
  const nextMap = new Map<string, SimNode>()

  const memNodes = nodes.filter(n => n.type === 'memory')
  const entNodes = showEntities.value ? nodes.filter(n => n.type === 'entity') : []
  const validNodes = [...memNodes, ...entNodes]

  let hasChanges = false
  const currentMap = nodeMap.value

  for (const n of validNodes) {
    let sn = currentMap.get(n.id)
    if (sn) {
      const oldDegree = sn.degree
      Object.assign(sn, n)
      sn.radius = getNodeRadius(n)
      if (oldDegree !== n.degree) hasChanges = true
      nextNodes.push(sn)
      nextMap.set(n.id, sn)
    } else {
      hasChanges = true
      const angle = Math.random() * Math.PI * 2
      const dist = Math.random() * Math.min(canvasWidth, canvasHeight) * 0.35
      sn = {
        ...n,
        x: cx + Math.cos(angle) * dist,
        y: cy + Math.sin(angle) * dist,
        vx: 0,
        vy: 0,
        radius: getNodeRadius(n)
      }
      nextNodes.push(sn)
      nextMap.set(n.id, sn)
    }
  }

  if (nextNodes.length !== currentMap.size) {
    hasChanges = true
  }

  const nextEdges = edges.filter(e => nextMap.has(e.source) && nextMap.has(e.target))
  if (nextEdges.length !== simEdges.value.length) {
    hasChanges = true
  }

  simNodes.value = nextNodes
  nodeMap.value = nextMap
  simEdges.value = nextEdges

  if (selectedNode.value && !nextMap.has(selectedNode.value.id)) {
    selectNode(null)
    relatedMemories.value = []
  } else if (selectedNode.value) {
    const updatedNode = nextMap.get(selectedNode.value.id)
    if (updatedNode) {
      selectedNode.value = updatedNode
      prevSelectedNode = updatedNode
    }
  }

  if (hasChanges) {
    simulationAlpha = Math.max(simulationAlpha, 0.3)
  }
}

function buildSpatialHash(nodes: SimNode[], cellSize: number): Map<string, SimNode[]> {
  const grid = new Map<string, SimNode[]>()
  for (const node of nodes) {
    const cx = Math.floor(node.x / cellSize)
    const cy = Math.floor(node.y / cellSize)
    const key = `${cx},${cy}`
    let bucket = grid.get(key)
    if (!bucket) { bucket = []; grid.set(key, bucket) }
    bucket.push(node)
  }
  return grid
}

function getNeighbors(grid: Map<string, SimNode[]>, x: number, y: number, cellSize: number): SimNode[] {
  const result: SimNode[] = []
  const cx = Math.floor(x / cellSize)
  const cy = Math.floor(y / cellSize)
  for (let dx = -1; dx <= 1; dx++) {
    for (let dy = -1; dy <= 1; dy++) {
      const bucket = grid.get(`${cx + dx},${cy + dy}`)
      if (bucket) result.push(...bucket)
    }
  }
  return result
}

function simulate() {
  if (simulationAlpha < 0.005) return

  const nodes = simNodes.value
  const edges = simEdges.value
  const nMap = nodeMap.value
  const cx = canvasWidth / 2
  const cy = canvasHeight / 2
  const alpha = simulationAlpha

  for (const edge of edges) {
    const source = nMap.get(edge.source)
    const target = nMap.get(edge.target)
    if (!source || !target) continue
    const dx = target.x - source.x
    const dy = target.y - source.y
    const distSq = dx * dx + dy * dy
    if (distSq < 1) continue
    const dist = Math.sqrt(distSq)
    const idealDist = 120 // 更紧凑的弹簧距离
    const force = ((dist - idealDist) / dist) * 0.08 * alpha // 更强的连线牵引力
    source.vx += dx * force
    source.vy += dy * force
    target.vx -= dx * force
    target.vy -= dy * force
  }

  const grid = buildSpatialHash(nodes, 200)
  const repulseStrength = 6000 * alpha // 更强的斥力避免节点聚成一坨

  for (const nodeA of nodes) {
    if (nodeA === dragNode) continue
    const nearby = getNeighbors(grid, nodeA.x, nodeA.y, 200)
    for (const nodeB of nearby) {
      if (nodeB === nodeA || nodeB.id <= nodeA.id) continue
      const dx = nodeB.x - nodeA.x
      const dy = nodeB.y - nodeA.y
      const distSq = dx * dx + dy * dy
      
      if (distSq >= 1 && distSq <= 120000) {
        const dist = Math.sqrt(distSq)
        const force = repulseStrength / (distSq * dist)
        const fx = (dx / dist) * force
        const fy = (dy / dist) * force
        nodeA.vx -= fx
        nodeA.vy -= fy
        nodeB.vx += fx
        nodeB.vy += fy
      }
    }
  }

  for (const node of nodes) {
    if (node.fx !== undefined && node.fy !== undefined) {
      node.x = node.fx
      node.y = node.fy
      node.vx = 0
      node.vy = 0
      continue
    }
    const dx = cx - node.x
    const dy = cy - node.y
    node.vx += dx * 0.0003 * alpha // 减弱向心力，让图谱可以自由舒展
    node.vy += dy * 0.0003 * alpha
    node.vx *= 0.85 // 增加摩擦力，减少抖动
    node.vy *= 0.85
    const speed = node.vx * node.vx + node.vy * node.vy
    if (speed > 250) { // 限制最大速度防止飞出
      const s = 15 / Math.sqrt(speed)
      node.vx *= s
      node.vy *= s
    }
    node.x += node.vx
    node.y += node.vy
  }

  simulationAlpha *= 0.96
}

function resolveCollisions() {
  const nodes = simNodes.value
  if (nodes.length < 2) return
  const grid = buildSpatialHash(nodes, 200)

  for (const nodeA of nodes) {
    const nearby = getNeighbors(grid, nodeA.x, nodeA.y, 200)
    for (const nodeB of nearby) {
      if (nodeB === nodeA || nodeB.id <= nodeA.id) continue
      const dx = nodeB.x - nodeA.x
      const dy = nodeB.y - nodeA.y
      const distSq = dx * dx + dy * dy
      const minDist = nodeA.radius + nodeB.radius + 2
      if (distSq < minDist * minDist && distSq > 0.01) {
        const dist = Math.sqrt(distSq)
        const overlap = minDist - dist
        const nx = dx / dist
        const ny = dy / dist
        const pushX = nx * overlap * 0.5
        const pushY = ny * overlap * 0.5

        const aFixed = nodeA.fx !== undefined
        const bFixed = nodeB.fx !== undefined

        if (aFixed && bFixed) continue
        if (aFixed) {
          nodeB.x += pushX * 2
          nodeB.y += pushY * 2
        } else if (bFixed) {
          nodeA.x -= pushX * 2
          nodeA.y -= pushY * 2
        } else {
          nodeA.x -= pushX
          nodeA.y -= pushY
          nodeB.x += pushX
          nodeB.y += pushY
        }
      }
    }
  }
}

function render() {
  const canvas = canvasRef.value
  if (!canvas) return
  const ctx = canvas.getContext('2d')
  if (!ctx) return

  ctx.clearRect(0, 0, canvasWidth * dpr, canvasHeight * dpr)
  ctx.save()
  ctx.scale(dpr, dpr)
  ctx.translate(panX, panY)
  ctx.scale(zoom, zoom)

  const nMap = nodeMap.value
  const isDark = document.documentElement.getAttribute('data-theme') === 'dark'
  const currentFocusedLayer = focusedLayer.value
  const hasSelection = !!selectedNode.value
  const visibleMemIds = new Set(simNodes.value.filter(n => n.type === 'memory').map(n => n.id))

  const colorNodeIds = new Set<string>()
  if (hasSelection) {
    colorNodeIds.add(selectedNode.value!.id)
    for (const edge of simEdges.value) {
      if (edge.source === selectedNode.value!.id) colorNodeIds.add(edge.target)
      if (edge.target === selectedNode.value!.id) colorNodeIds.add(edge.source)
    }
  }

  const { ids: navigableIds, all: isAllNav } = computeNavigableNodeIds()

  const grayColor = isDark ? 'rgba(100,116,139,0.5)' : 'rgba(160,174,192,0.6)'
  const edgeDimColor = isDark ? 'rgba(100,116,139,0.06)' : 'rgba(148,163,184,0.10)'
  const edgeNormalColor = isDark ? 'rgba(100,116,139,0.12)' : 'rgba(148,163,184,0.20)'
  const edgeHighlightColor = isDark ? 'rgba(148,163,184,0.55)' : 'rgba(100,116,139,0.55)'

  for (const edge of simEdges.value) {
    const s = nMap.get(edge.source)
    const t = nMap.get(edge.target)
    if (!s || !t) continue
    if (!showEntities.value && !(visibleMemIds.has(edge.source) && visibleMemIds.has(edge.target))) continue

    const isEdgeActive = hasSelection && (edge.source === selectedNode.value!.id || edge.target === selectedNode.value!.id)
    const sShowsColor = hasSelection ? colorNodeIds.has(s.id) : (currentFocusedLayer === null || (s.type === 'memory' && s.layer === currentFocusedLayer))
    const tShowsColor = hasSelection ? colorNodeIds.has(t.id) : (currentFocusedLayer === null || (t.type === 'memory' && t.layer === currentFocusedLayer))

    ctx.beginPath()
    ctx.moveTo(s.x, s.y)
    ctx.lineTo(t.x, t.y)

    if (isEdgeActive) {
      ctx.strokeStyle = edgeHighlightColor
      ctx.lineWidth = 1.5
      ctx.globalAlpha = 1.0
    } else if (sShowsColor && tShowsColor) {
      ctx.strokeStyle = edgeNormalColor
      ctx.lineWidth = 0.6
      ctx.globalAlpha = 1.0
    } else {
      ctx.strokeStyle = edgeDimColor
      ctx.lineWidth = 0.4
      ctx.globalAlpha = 1.0
    }
    ctx.stroke()
    ctx.globalAlpha = 1.0
  }

  for (const node of simNodes.value) {
    const isSelected = selectedNode.value?.id === node.id
    const showsColor = hasSelection
      ? colorNodeIds.has(node.id)
      : (currentFocusedLayer === null || (node.type === 'memory' && node.layer === currentFocusedLayer))

    if (node.type === 'memory') {
      const color = showsColor ? getLayerColor(node.layer || 1) : grayColor
      const opacity = showsColor ? 1.0 : 0.28
      const r = node.radius

      ctx.beginPath()
      ctx.arc(node.x, node.y, r, 0, Math.PI * 2)
      ctx.globalAlpha = opacity
      ctx.fillStyle = isSelected ? color : (showsColor ? color + 'ee' : grayColor)
      ctx.fill()

      if (isSelected) {
        ctx.strokeStyle = color
        ctx.lineWidth = 2.5
        ctx.stroke()
        ctx.beginPath()
        ctx.arc(node.x, node.y, r + 6, 0, Math.PI * 2)
        ctx.strokeStyle = color + '50'
        ctx.lineWidth = 2.5
        ctx.stroke()
      } else if (currentFocusedLayer !== null && showsColor && !isAllNav && navigableIds.has(node.id)) {
        ctx.beginPath()
        ctx.arc(node.x, node.y, r + 4, 0, Math.PI * 2)
        ctx.globalAlpha = 0.6
        ctx.strokeStyle = color
        ctx.lineWidth = 1.5
        ctx.setLineDash([4, 3])
        ctx.stroke()
        ctx.setLineDash([])
        ctx.globalAlpha = 1.0
      }

      if (showsColor) {
        const rawText = getRelatedPreview(node)
        const labelText = node.short_name ? rawText : (rawText.length > 8 ? rawText.slice(0, 8) + '..' : rawText)
        ctx.fillStyle = isDark ? '#cbd5e1' : '#475569'
        ctx.font = isSelected ? `bold 11px -apple-system,sans-serif` : `10px -apple-system,sans-serif`
        ctx.textAlign = 'center'
        ctx.textBaseline = 'top'
        ctx.globalAlpha = Math.max(0.25, opacity)
        ctx.fillText(labelText, node.x, node.y + r + 4)
      }
      ctx.globalAlpha = 1.0

    } else if (showEntities.value) {
      const showsEntityColor = hasSelection && colorNodeIds.has(node.id)
      const opacity = showsEntityColor ? 0.8 : 0.18
      const r = node.radius

      ctx.beginPath()
      ctx.arc(node.x, node.y, r, 0, Math.PI * 2)
      ctx.globalAlpha = opacity
      ctx.fillStyle = showsEntityColor ? '#94a3b8' : grayColor
      ctx.fill()

      if (showsEntityColor) {
        const rawText = node.text || ''
        const labelText = rawText.length > 8 ? rawText.slice(0, 8) + '..' : rawText
        ctx.fillStyle = isDark ? '#cbd5e1' : '#475569'
        ctx.font = `9px -apple-system,sans-serif`
        ctx.textAlign = 'center'
        ctx.textBaseline = 'top'
        ctx.globalAlpha = Math.max(0.3, opacity)
        ctx.fillText(labelText, node.x, node.y + r + 4)
      }
      ctx.globalAlpha = 1.0
    }
  }

  ctx.restore()
}

function animationLoop() {
  frameCount++
  const simRunning = frameCount % 2 === 0 || simulationAlpha > 0.05
  if (simRunning) simulate()
  if (isDragging || simulationAlpha > 0.008) resolveCollisions()
  render()
  animFrameId = requestAnimationFrame(animationLoop)
}

function screenToGraph(sx: number, sy: number): { x: number; y: number } {
  return {
    x: (sx - panX) / zoom,
    y: (sy - panY) / zoom,
  }
}

function findNodeAt(gx: number, gy: number): SimNode | null {
  const hitRadius = 16
  for (let i = simNodes.value.length - 1; i >= 0; i--) {
    const node = simNodes.value[i]
    if (!showEntities.value && node.type === 'entity') continue
    const r = node.radius + hitRadius
    const dx = gx - node.x
    const dy = gy - node.y
    if (dx * dx + dy * dy <= r * r) return node
  }
  return null
}

function onCanvasMouseDown(e: MouseEvent) {
  const rect = canvasRef.value?.getBoundingClientRect()
  if (!rect) return
  const sx = e.clientX - rect.left
  const sy = e.clientY - rect.top
  const pos = screenToGraph(sx, sy)

  dragStartX = e.clientX
  dragStartY = e.clientY
  dragStarted = false

  const node = findNodeAt(pos.x, pos.y)
  if (node) {
    const { ids, all } = computeNavigableNodeIds()
    if (!all && !ids.has(node.id)) {
      isPanning = true
      panFromNonNavigable = true
      lastMouseX = e.clientX
      lastMouseY = e.clientY
      return
    }

    selectNode(node)
    relatedMemories.value = []
    dragNode = node
    isDragging = true
    dragOffsetX = node.x - pos.x
    dragOffsetY = node.y - pos.y
  } else {
    isPanning = true
  }
  lastMouseX = e.clientX
  lastMouseY = e.clientY
}

function onCanvasMouseMove(e: MouseEvent) {
  const rect = canvasRef.value?.getBoundingClientRect()
  if (!rect) return
  mouseX = e.clientX
  mouseY = e.clientY

  const sx = e.clientX - rect.left
  const sy = e.clientY - rect.top
  const pos = screenToGraph(sx, sy)

  if (isDragging && dragNode) {
    if (!dragStarted) {
      const dx = e.clientX - dragStartX
      const dy = e.clientY - dragStartY
      if (Math.sqrt(dx * dx + dy * dy) > 3) {
        dragStarted = true
        simulationAlpha = Math.max(simulationAlpha, 0.15)
      }
    }
    dragNode.fx = pos.x + dragOffsetX
    dragNode.fy = pos.y + dragOffsetY
    dragNode.x = dragNode.fx
    dragNode.y = dragNode.fy
    if (dragStarted) {
      simulationAlpha = Math.max(simulationAlpha, 0.08)
    }
    canvasRef.value!.style.cursor = 'grabbing'
  } else if (isPanning) {
    panX += e.clientX - lastMouseX
    panY += e.clientY - lastMouseY
    lastMouseX = e.clientX
    lastMouseY = e.clientY
    canvasRef.value!.style.cursor = 'move'
  } else {
    const node = findNodeAt(pos.x, pos.y)
    hoveredNode.value = node
    if (node) {
      const { ids, all } = computeNavigableNodeIds()
      if (all || ids.has(node.id)) {
        canvasRef.value!.style.cursor = 'pointer'
      } else {
        canvasRef.value!.style.cursor = 'not-allowed'
      }
    } else {
      canvasRef.value!.style.cursor = 'grab'
    }
  }
}

function onCanvasMouseUp() {
  if (isDragging && dragNode) {
    // Selected node stays fixed to prevent jitter on click
    // It will be unfixed when a different node is selected or deselected
  } else if (isPanning) {
    const dx = lastMouseX - dragStartX
    const dy = lastMouseY - dragStartY
    const panDist = Math.sqrt(dx * dx + dy * dy)
    if (panDist < 5 && !panFromNonNavigable) {
      selectNode(null)
      relatedMemories.value = []
    }
  }
  panFromNonNavigable = false
  dragNode = null
  isDragging = false
  isPanning = false
  dragStarted = false
  canvasRef.value!.style.cursor = 'grab'
}

function onCanvasWheel(e: WheelEvent) {
  e.preventDefault()
  const rect = canvasRef.value?.getBoundingClientRect()
  if (!rect) return
  const sx = e.clientX - rect.left
  const sy = e.clientY - rect.top
  const delta = e.deltaY > 0 ? 0.9 : 1.1
  const newZoom = Math.max(0.15, Math.min(6, zoom * delta))
  const ratio = newZoom / zoom
  panX = sx - (sx - panX) * ratio
  panY = sy - (sy - panY) * ratio
  zoom = newZoom
  
  // 缩放时稍微唤醒物理引擎，让节点有散开的动力
  if (simulationAlpha < 0.1) {
    simulationAlpha = 0.1
  }
}

function onCanvasDblClick(e: MouseEvent) {
  const rect = canvasRef.value?.getBoundingClientRect()
  if (!rect) return
  const sx = e.clientX - rect.left
  const sy = e.clientY - rect.top
  const pos = screenToGraph(sx, sy)
  const node = findNodeAt(pos.x, pos.y)
  if (node && node.type === 'memory') {
    const { ids, all } = computeNavigableNodeIds()
    if (!all && !ids.has(node.id)) return
    fetchRelatedMemories(node.id)
    selectNode(node)
  }
}

async function fetchRelatedMemories(memoryId: string) {
  loadingRelated.value = true
  try {
    const data = await apiRequest<{ related: any[]; total: number }>(`/api/memory/graph/related/${memoryId}?max_depth=2`)
    relatedMemories.value = data.related || []
  } catch (error) {
    console.error('获取关联记忆失败:', error)
    relatedMemories.value = []
  } finally {
    loadingRelated.value = false
  }
}

function selectRelatedMemory(mem: any) {
  const node = nodeMap.value.get(mem.id)
  if (node) {
    selectNode(node)
    focusedLayer.value = null
  }
}

function resizeCanvas() {
  const canvas = canvasRef.value
  const wrapper = graphWrapper.value
  if (!canvas || !wrapper) return
  dpr = Math.min(window.devicePixelRatio || 1, 2)
  const rect = wrapper.getBoundingClientRect()
  canvasWidth = rect.width
  canvasHeight = rect.height
  canvas.width = canvasWidth * dpr
  canvas.height = canvasHeight * dpr
  canvas.style.width = `${canvasWidth}px`
  canvas.style.height = `${canvasHeight}px`
}

const { start: startAutoRefresh, stop: stopAutoRefresh } = useInterval(async () => {
  try { await fetchGraphData(true) } catch {}
}, APP_CONFIG.BACKEND_STATUS_INTERVAL * 3)

const graphRefreshHandler = () => { void fetchGraphData(false, true) }

onMounted(async () => {
  await nextTick()
  resizeCanvas()
  window.addEventListener('resize', resizeCanvas)
  window.addEventListener(GRAPH_REFRESH_EVENT, graphRefreshHandler)
  await fetchGraphData(false)
  animationLoop()
  startAutoRefresh()
})

onUnmounted(() => {
  if (animFrameId) cancelAnimationFrame(animFrameId)
  window.removeEventListener('resize', resizeCanvas)
  window.removeEventListener(GRAPH_REFRESH_EVENT, graphRefreshHandler)
  stopAutoRefresh()
})
</script>

<style scoped>
.view-container {
  padding: 24px;
  height: 100%;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  position: relative;
}

.view-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 16px;
  flex-shrink: 0;
}

.header-text h2 {
  font-size: 24px;
  font-weight: 700;
  color: var(--color-text);
  margin: 0 0 4px 0;
}

.subtitle {
  font-size: 13px;
  color: var(--color-text-secondary);
  margin: 0;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.filter-group {
  display: flex;
  gap: 8px;
  align-items: center;
}

.layer-buttons {
  display: flex;
  gap: 3px;
  background: var(--color-surface-secondary, #f1f5f9);
  border-radius: 6px;
  padding: 2px;
}

.btn-layer {
  padding: 4px 8px;
  border: 1px solid transparent;
  border-radius: 4px;
  background: transparent;
  color: var(--color-text-secondary);
  font-size: 11px;
  cursor: pointer;
  transition: all 0.15s;
  white-space: nowrap;
  font-weight: 500;
}
.btn-layer:hover { color: var(--color-text); background: var(--color-hover-bg, rgba(0,0,0,0.05)); }
.btn-layer.active {
  background: var(--color-primary-bg);
  border-color: var(--color-primary);
  color: var(--color-primary);
  font-weight: 600;
}

.filter-select {
  padding: 6px 10px;
  border: 1px solid var(--color-border);
  border-radius: 6px;
  background: var(--color-surface);
  color: var(--color-text);
  font-size: 12px;
  cursor: pointer;
  outline: none;
  transition: border-color 0.15s;
}
.filter-select:hover { border-color: var(--color-border-hover); }
.filter-select:focus { border-color: var(--color-primary); }

.btn-toggle {
  padding: 6px 10px;
  border: 1px solid var(--color-border);
  border-radius: 6px;
  background: var(--color-surface);
  color: var(--color-text-secondary);
  font-size: 12px;
  cursor: pointer;
  transition: all 0.15s;
  white-space: nowrap;
}
.btn-toggle:hover { border-color: var(--color-primary); color: var(--color-primary); }
.btn-toggle.active {
  background: var(--color-primary-bg);
  border-color: var(--color-primary);
  color: var(--color-primary);
}

.btn-refresh {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 6px 12px;
  border: 1px solid var(--color-border);
  border-radius: 6px;
  background: var(--color-surface);
  color: var(--color-text-secondary);
  font-size: 12px;
  cursor: pointer;
  transition: all 0.15s;
}
.btn-refresh:hover:not(:disabled) { border-color: var(--color-primary); color: var(--color-primary); background: var(--color-primary-bg); }
.btn-refresh:disabled { opacity: 0.5; cursor: not-allowed; }

.graph-stats {
  display: flex;
  gap: 16px;
  margin-bottom: 12px;
  flex-shrink: 0;
}
.graph-stat-item { display: flex; align-items: baseline; gap: 6px; }
.graph-stat-value { font-size: 18px; font-weight: 700; color: var(--color-text); }
.graph-stat-label { font-size: 12px; color: var(--color-text-secondary); }

.graph-wrapper {
  flex: 1;
  position: relative;
  border: 1px solid var(--color-border);
  border-radius: 12px;
  overflow: hidden;
  background: var(--color-surface);
}
.graph-wrapper canvas { display: block; cursor: grab; }

.graph-loading,
.graph-empty {
  position: absolute;
  top: 0; left: 0; right: 0; bottom: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  color: var(--color-text-secondary);
}
.loading-spinner {
  width: 32px; height: 32px;
  border: 3px solid var(--color-border);
  border-top-color: var(--color-primary);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }
.empty-icon { font-size: 48px; }
.graph-empty h3 { font-size: 16px; color: var(--color-text); margin: 0; }
.graph-empty p { font-size: 13px; margin: 0; }

.node-tooltip {
  position: absolute;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 8px;
  padding: 10px 12px;
  box-shadow: var(--shadow-hover);
  z-index: 100;
  max-width: 280px;
  pointer-events: none;
}
.tooltip-header { display: flex; align-items: center; gap: 6px; margin-bottom: 6px; }
.tooltip-type {
  font-size: 10px; font-weight: 600;
  padding: 1px 6px; border-radius: 4px; text-transform: uppercase;
}
.tooltip-type.memory { background: var(--color-indigo-bg-subtle); color: var(--color-indigo); border: 1px solid var(--color-indigo-border); }
.tooltip-type.entity { background: var(--color-cyan-bg-subtle); color: var(--color-cyan); border: 1px solid var(--color-cyan-border); }
.tooltip-layer { font-size: 11px; font-weight: 600; }
.tooltip-content { font-size: 12px; color: var(--color-text); line-height: 1.4; word-break: break-all; }
.tooltip-meta { display: flex; gap: 8px; margin-top: 6px; font-size: 11px; color: var(--color-text-tertiary); }

.detail-panel {
  position: absolute;
  right: 24px; top: 80px;
  width: 300px;
  max-height: calc(100% - 100px);
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 12px;
  box-shadow: var(--shadow-hover);
  z-index: 50;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.detail-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  border-bottom: 1px solid var(--color-border);
}
.detail-header h3 { font-size: 14px; font-weight: 600; color: var(--color-text); margin: 0; }
.detail-close {
  background: none; border: none;
  font-size: 16px; color: var(--color-text-secondary);
  cursor: pointer; padding: 2px 6px; border-radius: 4px; transition: all 0.15s;
}
.detail-close:hover { background: var(--color-hover-bg); color: var(--color-text); }
.detail-body { padding: 12px 16px; overflow-y: auto; flex: 1; }
.detail-field { margin-bottom: 12px; }
.detail-label { display: block; font-size: 11px; color: var(--color-text-tertiary); margin-bottom: 4px; text-transform: uppercase; letter-spacing: 0.5px; }
.detail-value { font-size: 13px; color: var(--color-text); }
.layer-badge { display: inline-block; padding: 2px 8px; border-radius: 4px; font-weight: 600; font-size: 12px; }
.content-text { line-height: 1.5; word-break: break-all; }
.detail-tags { display: flex; flex-wrap: wrap; gap: 4px; }
.detail-tag { font-size: 11px; padding: 2px 8px; border-radius: 4px; background: var(--color-primary-bg); color: var(--color-primary); border: 1px solid var(--color-indigo-border); }
.btn-related {
  width: 100%; padding: 8px;
  border: 1px solid var(--color-border); border-radius: 6px;
  background: var(--color-surface-secondary); color: var(--color-text);
  font-size: 12px; cursor: pointer; transition: all 0.15s; margin-top: 4px;
}
.btn-related:hover:not(:disabled) { border-color: var(--color-primary); color: var(--color-primary); }
.btn-related:disabled { opacity: 0.5; cursor: not-allowed; }
.related-list { margin-top: 10px; display: flex; flex-direction: column; gap: 6px; }
.related-item { display: flex; gap: 8px; padding: 6px 8px; border-radius: 6px; background: var(--color-surface-secondary); font-size: 12px; align-items: flex-start; cursor: pointer; transition: all 0.15s; border: 1px solid transparent; }
.related-item:hover { background: var(--color-hover-bg, rgba(0,0,0,0.04)); border-color: var(--color-border); }
.related-item-active { background: var(--color-primary-bg, rgba(99,102,241,0.08)); border-color: var(--color-primary-border, rgba(99,102,241,0.3)); }
.related-layer { font-weight: 600; font-size: 11px; flex-shrink: 0; margin-top: 1px; }
.related-content { color: var(--color-text-secondary); line-height: 1.4; word-break: break-all; }

.graph-legend {
  position: absolute;
  bottom: 32px; left: 24px;
  display: flex; align-items: center; gap: 10px;
  padding: 8px 14px;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 8px;
  box-shadow: var(--shadow);
  font-size: 11px; color: var(--color-text-secondary);
  z-index: 50;
}
.legend-item { display: flex; align-items: center; gap: 4px; }
.legend-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.legend-dot.memory { background: var(--color-indigo); }
.legend-dot.entity { background: #64748b; border-radius: 50%; }
.legend-separator { width: 1px; height: 14px; background: var(--color-border); }
</style>
