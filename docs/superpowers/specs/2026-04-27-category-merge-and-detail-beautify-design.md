# 分类归并细化与详情页阅读器美化 设计文档

## 目标
1. **归并规则细化**：提升 `CategoryNormalizationService` 的自动收敛能力，增加去前缀、以及中英文同义词根映射，使分类更加干净。
2. **详情页美化**：优化 `MemoryView.vue` 和 `memory-detail-markdown.ts`，让 L4/L6 的阅读体验更贴近现代文档阅读器（强化卡片式元数据、结构化正文排版、美化代码块和引用）。

## 架构与落点

### 1. 归并规则细化 (后端)
- **文件**: `backend/app/services/category_normalization_service.py`
- **逻辑变更**:
  - 增加 `SOFT_PREFIXES` (如: "关于", "如何", "怎样") 进行前缀剥离。
  - 增加 `SYNONYM_MAPPINGS` 字典，实现核心词根的映射。例如：
    - `Config`, `配置` -> `配置`
    - `Deploy`, `发布`, `部署` -> `部署`
    - `Bug`, `Fix`, `修复` -> `修复`
  - 在 `_compare_key` 中，依次执行：转大写（方便匹配） -> 去符号 -> 去前缀 -> 去软后缀 -> 去核心后缀 -> 映射同义词根。

### 2. 详情页美化 (前端)
- **文件**: `frontend/src/renderer/views/MemoryView.vue`
- **样式变更**:
  - **顶部区 (Header/Metadata)**: 
    - 弱化边框，增加阴影，背景色调整为淡一点的 surface 色。
    - 将 Meta 信息（来源、时间、会话等）改为类似 Badge 的胶囊卡片，带细微背景色。
  - **正文区 (Markdown Render)**:
    - 增大字体至 `15px`，行高增加至 `1.75`，提升阅读的呼吸感。
    - **代码块 (`pre code`)**: 增加深色/独立背景块，圆角，并增加上下边距。
    - **引用 (`blockquote`)**: 加宽左侧边框，调整背景色为极淡的主题色，文字颜色加深。
    - **表格 (`table`)**: 如果存在，增加基础边框折叠和表头背景。
- **文件**: `frontend/src/renderer/utils/memory-detail-markdown.ts`
- **逻辑变更**:
  - 确保 `marked` 渲染时开启了 `gfm`（GitHub Flavored Markdown）和 `breaks`，并能正确包裹 `pre > code` 以供前端写 CSS。

## 兼容性
- 纯规则和样式调整，不涉及数据库 Schema 变更，无需迁移数据。
- 后端改动由现有的 `test_category_normalization_service.py` 覆盖并追加新用例。
