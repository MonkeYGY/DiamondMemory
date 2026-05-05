# 复用旧 Ollama 模型目录（无论模型在哪都能检测到）设计

## 目标

- 无论用户之前的 Ollama 模型存放在何处（只要属于 Ollama 的模型目录），应用都能在启动后检测到“已安装模型”。
- 若检测到旧模型目录存在且可用：**直接复用（不迁移、不复制）**，后续新下载模型也落到旧目录。
- 若未检测到旧模型目录：新下载模型落到应用 `userData/ollama-models`。
- 不引入双 Ollama 实例，不引入双端口路由，保持系统行为可预测。

## 现状与问题

- 前后端判断“已安装模型”主要依赖 Ollama 的 `GET /api/tags`（由 Ollama 决定可见模型集合）。
- Electron 主进程启动内嵌 Ollama 时，会设置 `OLLAMA_MODELS=userData/ollama-models`（仅在“内嵌/下载的 Ollama”路径下设置），导致：
  - 用户原先在系统 Ollama 默认目录（如 `~/.ollama/models`）已安装的模型，可能被“新启动的内嵌 Ollama”隔离而不可见。

## 方案概述（推荐：单 Ollama，启动前自动选择模型目录）

当 `Ollama(127.0.0.1:11434)` 尚未运行时，主进程将启动 `ollama serve`，并在启动前选择一个“模型目录”：

1) 若发现旧模型目录（含 manifests 且非空）：
- 启动时设置 `env.OLLAMA_MODELS=<旧目录>`，使本次启动的 Ollama 直接复用旧模型（不迁移）。
- 后续通过 `/api/pull` 下载的模型也会保存到该旧目录（符合用户诉求）。

2) 若未发现旧模型目录：
- 设置 `env.OLLAMA_MODELS=<userData>/ollama-models`（保持当前逻辑）。

3) 若系统中已经有 Ollama 在运行：
- 不做目录干预，直接复用当前运行中的 Ollama 服务（以其自身的模型目录配置为准）。

## 旧模型目录发现规则

### 候选目录优先级

按以下顺序检测第一个“有效目录”：

1. `process.env.OLLAMA_MODELS`（若存在且有效）
2. macOS / Linux：`~/.ollama/models`
3. macOS 兼容兜底：`~/Library/Application Support/Ollama/models`
4. Windows：
   - `%USERPROFILE%\\.ollama\\models`
   - `%LOCALAPPDATA%\\Ollama\\models`

### 有效性判定

目录被认为“可复用”需满足：

- 路径存在且为目录；
- 目录下存在 `manifests/` 子目录；
- `manifests/` 下至少存在一个文件或子目录（非空）。

## 启动与回退策略

- 首选：若探测到旧目录，则使用旧目录启动。
- 若 `ollama serve` 启动失败，或启动后健康检查超时：
  - 自动回退到 `userData/ollama-models` 再尝试启动一次，避免卡死在启动阶段。

## 影响范围（预期修改文件）

- Modify: `frontend/src/main/backend-manager.ts`
  - 新增：`detectPreferredOllamaModelsDir()`（或同等命名）
  - 调整：`startOllama()` 内 `env.OLLAMA_MODELS` 的设置策略与失败回退

## 验证

### 场景 A：用户系统已有旧模型（例如 `~/.ollama/models`）

- 停止所有 ollama 进程
- 启动应用
- 预期：
  - 应用启动的 Ollama 复用旧目录
  - 模型管理页能立刻看到旧模型列表（`/api/tags` 返回旧模型）
  - 点击下载新模型，新模型文件落入旧目录

### 场景 B：用户无旧模型

- 删除/不存在上述候选目录，或其 manifests 为空
- 启动应用
- 预期：
  - 模型目录使用 `userData/ollama-models`
  - 下载模型后，模型落入 `userData/ollama-models`

### 场景 C：系统已运行 Ollama

- 先手动启动系统 Ollama（任意模型目录配置）
- 启动应用
- 预期：
  - 应用不重复拉起新的 Ollama
  - 直接复用已运行的 Ollama，其模型列表可见

