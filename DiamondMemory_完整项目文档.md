# DiamondMemory 完整项目文档

## 📋 文档目录

1. [项目概述](#项目概述)
2. [目录结构](#目录结构)
3. [技术栈](#技术栈)
4. [API 完整文档](#api-完整文档)
5. [快速开始](#快速开始)
6. [核心流程](#核心流程)
7. [使用示例](#使用示例)
8. [配置信息](#配置信息)
9. [注意事项](#注意事项)

---

## 项目概述

DiamondMemory 是一个智能记忆系统，让 AI 拥有持久化记忆能力。

### 核心功能
- **记忆管理**：创建、查询、管理智能记忆
- **知识推理**：基于记忆的智能推理
- **智能检索**：基于语义的记忆检索
- **智能体集成**：与 OpenClaw 智能体无缝集成
- **多源数据摄取**：支持文档、网页、视频等多种数据源

### 主要特点
- 持久化存储记忆数据
- 支持多层级记忆分类
- 向量相似度搜索
- 智能问答系统
- OpenClaw 智能体集成

---

## 目录结构

```
DiamondMemory/
├── DiamondMemory/                    # 前端应用（SwiftUI）
│   ├── ContentView.swift             # 主内容视图
│   ├── DashboardView.swift           # 仪表盘视图
│   ├── MemoryManagementView.swift    # 记忆管理视图
│   ├── IngestCenterView.swift        # 摄取中心视图
│   ├── KnowledgeBaseView.swift       # 知识库视图
│   ├── QACenterView.swift            # 问答中心视图
│   ├── ExternalIntegrationView.swift # 外部集成视图
│   ├── ModelManagementView.swift     # 模型管理视图
│   ├── SettingsView.swift            # 系统设置视图
│   └── DiamondMemoryApp.swift        # 应用入口
├── backend/                          # 后端服务（FastAPI）
│   ├── app/                          # 应用核心
│   │   ├── api/                      # API 路由
│   │   │   ├── inference.py          # 推理服务 API
│   │   │   ├── memory_routes.py      # 记忆管理 API
│   │   │   ├── openclaw_routes.py    # OpenClaw API
│   │   │   ├── ingest.py             # 数据摄取 API
│   │   │   ├── process.py            # 数据处理 API
│   │   │   ├── output.py             # 输出服务 API
│   │   │   └── interface.py          # 接口服务 API
│   │   ├── services/                 # 业务逻辑
│   │   │   ├── memory_service.py     # 记忆管理服务
│   │   │   ├── retrieval_service.py  # 检索服务
│   │   │   ├── openclaw_service.py   # OpenClaw 服务
│   │   │   ├── embedding_service.py  # 嵌入服务
│   │   │   ├── inference/            # 推理服务
│   │   │   ├── ingest/               # 摄取服务
│   │   │   ├── process/              # 处理服务
│   │   │   └── output/               # 输出服务
│   │   ├── storage/                  # 存储层
│   │   │   ├── sqlite_store.py       # SQLite 存储
│   │   │   └── vector_store.py       # 向量存储
│   │   ├── models/                   # 数据模型
│   │   └── config/                   # 配置
│   ├── config.py                     # 配置文件
│   ├── main.py                       # 应用入口
│   └── requirements.txt              # Python 依赖
├── data/                             # 数据存储目录
│   ├── raw/                          # 原始数据
│   ├── processed/                    # 处理后数据
│   ├── knowledge/                    # 知识库
│   ├── models/                       # 模型文件
│   ├── index/                        # 索引文件
│   └── temp/                         # 临时文件
├── DiamondMemory.xcodeproj/          # Xcode 项目文件
├── API_DOCUMENTATION.md              # API 文档
├── PROJECT_QUICK_REFERENCE.md        # 项目快速参考
└── PROJECT_OPERATIONS.md             # 项目操作记录
```

---

## 技术栈

### 前端
| 技术 | 说明 |
|------|------|
| SwiftUI | 声明式 UI 框架 |
| macOS | 目标平台 |
| URLSession | 网络请求 |
| Combine | 响应式编程 |

### 后端
| 技术 | 说明 |
|------|------|
| Python 3.8+ | 开发语言 |
| FastAPI | Web 框架 |
| SQLite | 关系型数据库 |
| 向量存储 | 相似度搜索 |
| Uvicorn | ASGI 服务器 |

### 其他
| 技术 | 说明 |
|------|------|
| Ollama | 本地大模型服务 |
| OpenClaw | 智能体框架 |

---

## API 完整文档

### 服务器配置
- **主机**：0.0.0.0
- **端口**：8000
- **API 基础地址**：http://localhost:8000

---

### 1. 记忆管理 API

#### 1.1 创建记忆
| 项目 | 说明 |
|------|------|
| 方法 | POST |
| 路径 | /api/memory/create |
| 参数 | content (str, 必填), category (str), tags (List[str]), source (str), confidence (float, 默认1.0), ttl (str), is_pinned (bool, 默认False), metadata (Dict) |

#### 1.2 获取记忆
| 项目 | 说明 |
|------|------|
| 方法 | GET |
| 路径 | /api/memory/get/{memory_id} |
| 参数 | memory_id (str) |

#### 1.3 更新记忆
| 项目 | 说明 |
|------|------|
| 方法 | PUT |
| 路径 | /api/memory/update/{memory_id} |
| 参数 | memory_id (str), content (str), reason (str) |

#### 1.4 删除记忆
| 项目 | 说明 |
|------|------|
| 方法 | DELETE |
| 路径 | /api/memory/delete/{memory_id} |
| 参数 | memory_id (str) |

#### 1.5 标记为永久记忆
| 项目 | 说明 |
|------|------|
| 方法 | POST |
| 路径 | /api/memory/pin/{memory_id} |
| 参数 | memory_id (str) |

#### 1.6 取消永久标记
| 项目 | 说明 |
|------|------|
| 方法 | POST |
| 路径 | /api/memory/unpin/{memory_id} |
| 参数 | memory_id (str) |

#### 1.7 查询记忆
| 项目 | 说明 |
|------|------|
| 方法 | GET |
| 路径 | /api/memory/query |
| 参数 | query (str), categories (List[str]), limit (int, 默认10) |

#### 1.8 列出所有记忆
| 项目 | 说明 |
|------|------|
| 方法 | GET |
| 路径 | /api/memory/list |
| 参数 | limit (int, 默认100) |

#### 1.9 按关键词搜索
| 项目 | 说明 |
|------|------|
| 方法 | GET |
| 路径 | /api/memory/search/keyword |
| 参数 | keyword (str), limit (int, 默认20) |

#### 1.10 按标签搜索
| 项目 | 说明 |
|------|------|
| 方法 | GET |
| 路径 | /api/memory/search/tags |
| 参数 | tags (List[str]), limit (int, 默认10) |

#### 1.11 搜索近期记忆
| 项目 | 说明 |
|------|------|
| 方法 | GET |
| 路径 | /api/memory/search/recent |
| 参数 | days (int, 默认7), limit (int, 默认10), category (str) |

---

### 2. 推理服务 API

#### 2.1 列出模型
| 项目 | 说明 |
|------|------|
| 方法 | GET |
| 路径 | /api/inference/models |

#### 2.2 下载模型
| 项目 | 说明 |
|------|------|
| 方法 | POST |
| 路径 | /api/inference/models/download |
| 参数 | model_url (str), model_name (str) |

#### 2.3 删除模型
| 项目 | 说明 |
|------|------|
| 方法 | DELETE |
| 路径 | /api/inference/models/{model_name} |
| 参数 | model_name (str) |

#### 2.4 获取模型信息
| 项目 | 说明 |
|------|------|
| 方法 | GET |
| 路径 | /api/inference/models/{model_name} |
| 参数 | model_name (str) |

#### 2.5 生成文本
| 项目 | 说明 |
|------|------|
| 方法 | POST |
| 路径 | /api/inference/generate |
| 参数 | prompt (str), model_path (str), max_tokens (int, 默认100) |

#### 2.6 聊天完成
| 项目 | 说明 |
|------|------|
| 方法 | POST |
| 路径 | /api/inference/chat |
| 参数 | messages (list[dict]), model_path (str), max_tokens (int, 默认100) |

---

### 3. OpenClaw 智能体 API

#### 3.1 获取智能体列表
| 项目 | 说明 |
|------|------|
| 方法 | GET |
| 路径 | /api/openclaw/agents |

#### 3.2 获取智能体信息
| 项目 | 说明 |
|------|------|
| 方法 | GET |
| 路径 | /api/openclaw/agents/{agent_id} |
| 参数 | agent_id (str) |

#### 3.3 创建智能体
| 项目 | 说明 |
|------|------|
| 方法 | POST |
| 路径 | /api/openclaw/agents |
| 参数 | name (str), description (str), instructions (str), tools (List[Dict]) |

#### 3.4 运行智能体
| 项目 | 说明 |
|------|------|
| 方法 | POST |
| 路径 | /api/openclaw/agents/{agent_id}/run |
| 参数 | agent_id (str), message (str), context (Dict) |

#### 3.5 获取运行历史
| 项目 | 说明 |
|------|------|
| 方法 | GET |
| 路径 | /api/openclaw/agents/{agent_id}/history |
| 参数 | agent_id (str), limit (int, 默认10) |

#### 3.6 更新智能体
| 项目 | 说明 |
|------|------|
| 方法 | PUT |
| 路径 | /api/openclaw/agents/{agent_id} |
| 参数 | agent_id (str), **kwargs |

#### 3.7 删除智能体
| 项目 | 说明 |
|------|------|
| 方法 | DELETE |
| 路径 | /api/openclaw/agents/{agent_id} |
| 参数 | agent_id (str) |

#### 3.8 健康检查
| 项目 | 说明 |
|------|------|
| 方法 | GET |
| 路径 | /api/openclaw/health |

---

### 4. 根路径

#### 4.1 API 根路径
| 项目 | 说明 |
|------|------|
| 方法 | GET |
| 路径 | / |
| 返回 | API 信息 |

---

## 快速开始

### 启动后端服务

```bash
# 进入 backend 目录
cd /Users/gengyun/Desktop/DiamondMemory/backend

# 安装依赖
pip install -r requirements.txt

# 启动服务
python main.py

# 服务将在 http://localhost:8000 运行
```

### 运行前端应用

```
1. 使用 Xcode 打开 DiamondMemory.xcodeproj
2. 构建并运行应用
3. 应用将连接到本地后端服务
```

---

## 核心机制详解

### 1. 记忆架构的纵向流转逻辑 (L1-L6)
系统抛弃了传统的扁平化数据库，采用 **6 层知识提炼架构**，实现记忆从“发散的碎片”到“收敛的系统化知识”的自动物理演进：

*   **L1 (原始记录层)**：所有通过 API（包括外部 AI 如 OpenClaw）写入的记忆，默认都作为 L1 层存入。它的特点是**全量记录、不做任何修改**，状态标记为待处理。
*   **L2 (沉淀记忆层 / 去重层)**：后台自动提取 L1 的文本转化为向量，在向量数据库中进行语义检索。如果发现相似度超过阈值且已存在，该 L1 记忆会被直接丢弃（去重）；如果是不重复的新内容，则提拔为 L2 记忆。
*   **L3 (总结分类层)**：这是一个“虚拟层”，在数据库中代表 L4 总结文档的**父级目录**（对应本地文件系统中的“总结经验”下的各个文件夹）。
*   **L4 (总结层 / 经验文档)**：大模型将同分类下的多条 L2 碎片记忆进行归纳总结，生成一篇结构化的经验文档。这层记忆会被系统**外化导出**为真实的 `.md` 文件。
*   **L5 (技能分类层)**：虚拟层，代表 L6 技能文档的父级目录（对应本地文件系统中的“技能”文件夹）。
*   **L6 (技能层 / 结构化规范)**：大模型对 L4 的经验进行最高维度的提炼，提取出高度可复用的“SOP工作流、规则、参数配置”等硬核技能，同样导出为 `.md` 文件供 AI 随时严格调用。

> **驱动方式**：这套 L1->L6 的流转并非由后端 Python 常驻死循环执行，而是由 **Swift 前端（macOS 应用）**的后台静默 Timer 定期向后端发送同步请求来驱动的。

### 2. 记忆提取的横向检索与热度逻辑 (T1-T5)
当外部 AI（如 OpenClaw）提取记忆时（调用 `/api/memory/query`），系统并不会全量无脑搜索，而是采用一套极其精密的**混合检索与动态重排 (Reranking)** 机制：

#### A. 混合检索机制 (Hybrid Search)
*   **向量语义检索**：只查 **L3~L6 层**。通过大模型把问题变成向量，去匹配经过提炼的高维知识。L1/L2 作为原始碎片不参与此检索。
*   **全文关键词检索 (FTS5)**：全量查 **L1~L6 层**。使用 SQLite 的 FTS5 引擎硬匹配关键词，保证刚刚写入的 L1 碎片只要字面对上了也能被搜出来（兜底）。
*   **实体抽取检索**：全量查 **L1~L6 层**。提取 Query 里的实体词（如“数据库”）去匹配相关记忆。

#### B. 动态打分与热度等级 (T1-T5)
搜出结果后，系统会计算最终得分：`基础分 = (语义分×权重) + (关键词分×权重) + (实体分×权重)`。随后叠加以下 Buff：
*   **时间衰减 (Time Decay)**：越老的记忆，分数扣得越多。
*   **层级压制 (Layer Bonus)**：L6 技能层的分数天生比 L1 高，鼓励 AI 使用提炼后的知识。
*   **置顶特权 (Pinned)**：被手动标记为永久记忆的数据，总分直接 **× 1.5 倍**。
*   **热度加成与 T1-T5 评级**：
    系统的 T1-T5 是基于**访问频次**和**初始可信度**动态计算的综合得分：`综合得分 = (访问次数占比 * 0.6) + (可信度 * 0.4)`。得分越高，T 级越高（T5为最高热度），在搜索时获得的分数加成也越高。

> **⚠️ 关键设计：提取记忆是否会增加热度？**
> **单纯的 Query（搜索）不会增加记忆的热度**。只有当系统或 AI 明确调用 `/api/memory/get/{id}` 去获取某一条**具体记忆的详情**时，数据库里的 `access_count` 才会 +1，进而在下一次后台流转时提升它的 T 级。这防止了一次模糊搜索把大量不相关记忆刷成高热度。

### 3. 知识库的双向同步逻辑 (上行与下行)
DiamondMemory 不仅仅是一个黑盒数据库，它与本地操作系统的文件系统（Markdown 文件夹）深度打通，这被称为“知识库双向同步”。

#### ⬇️ 下行同步 (Database -> Markdown)
*   **触发与映射**：当系统提炼出 L4（总结）和 L6（技能）层级的高维记忆时，`MarkdownExportService` 会自动将它们导出为本地 `.md` 文件。L3/L4 存放在 `data/knowledge/总结经验/`，L5/L6 存放在 `data/knowledge/技能/`。
*   **格式化**：文件顶部会注入 YAML Frontmatter（包含 `memory_id`, `tags` 等元数据），正文自动排版。这使得用户可以直接用 Obsidian、VSCode 等工具像看普通笔记一样阅读和管理 AI 的记忆。

#### ⬆️ 上行同步 (Markdown -> Database)
*   **变更检测**：当用户在外部编辑器中直接修改了这些 `.md` 文件，或者在目录里新建了 `.md` 笔记。前端的定时器会触发后端的 `sync_knowledge_base`。
*   **摄取与向量化**：系统会扫描文件的修改时间 (mtime) 和 MD5 哈希值。发现变更后，自动解析文件内容和 Frontmatter，将其作为 L4/L6 知识**反向更新（摄取）回 SQLite 数据库**。
*   **实时生效**：更新回数据库的同时，系统会立刻调用 Embedding 模型为其重新生成向量。这意味着，**用户只要在本地改了 Markdown 文件，AI 下一秒就能通过语义检索感知到最新的知识**。

### 智能问答流程
```
用户提问 → 检索相关记忆 → 大模型生成回答 → 返回结果
```

### 数据摄取流程
```
上传文件/输入URL → 解析内容 → 处理数据 → 创建记忆 → 返回结果
```

---

## 使用示例

### 示例 1：创建记忆

```bash
curl -X POST http://localhost:8000/api/memory/create \
  -H "Content-Type: application/json" \
  -d '{
    "content": "测试记忆内容",
    "category": "测试",
    "tags": ["测试", "示例"]
  }'
```

### 示例 2：获取记忆列表

```bash
curl http://localhost:8000/api/memory/list
```

### 示例 3：聊天完成

```bash
curl -X POST http://localhost:8000/api/inference/chat \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {"role": "user", "content": "你好，告诉我一个关于人工智能的有趣事实"}
    ],
    "max_tokens": 200
  }'
```

### 示例 4：运行智能体

```bash
curl -X POST http://localhost:8000/api/openclaw/agents/{agent_id}/run \
  -H "Content-Type: application/json" \
  -d '{
    "message": "帮我分析一下这个问题",
    "context": {"key": "value"}
  }'
```

---

## 配置信息

### 服务器配置
| 配置项 | 值 |
|--------|-----|
| 主机 | 0.0.0.0 |
| 端口 | 8000 |
| API 基础地址 | http://localhost:8000 |

### 数据库配置
| 配置项 | 值 |
|--------|-----|
| 数据库类型 | SQLite |
| 数据库路径 | sqlite:///data/database.db |

### 数据目录
| 目录 | 说明 |
|------|------|
| data/raw/ | 原始数据 |
| data/processed/ | 处理后数据 |
| data/knowledge/ | 知识库 |
| data/models/ | 模型文件 |
| data/index/ | 索引文件 |
| data/temp/ | 临时文件 |

---

## 注意事项

1. 确保后端服务在前端应用启动前运行
2. 首次运行时会自动创建数据目录结构
3. 部分功能可能需要安装额外的依赖
4. 大模型相关功能需要下载对应的模型文件
5. 所有 API 调用均需要确保后端服务已启动
6. 对于 POST 和 PUT 请求，请使用 JSON 格式的请求体
7. 错误响应通常包含 `error` 字段，描述错误原因
8. 成功响应通常包含 `success` 字段，值为 `true`

---

## 扩展能力

- **自定义智能体**：通过 OpenClaw API 创建和管理智能体
- **多源数据摄取**：支持文档、网页、视频等多种数据源
- **知识推理**：基于记忆的智能推理能力
- **外部系统集成**：与其他系统的集成接口

---

**文档版本**：v1.0
**最后更新**：2026-04-22
