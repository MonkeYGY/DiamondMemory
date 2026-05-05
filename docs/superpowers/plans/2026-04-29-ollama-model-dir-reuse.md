# 复用旧 Ollama 模型目录 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 启动时自动复用用户已有 Ollama 模型目录（不迁移），让应用“无论模型在哪都能检测到”，且若无旧模型则下载到 `userData/ollama-models`。

**Architecture:** Electron 主进程在启动 `ollama serve` 前探测可复用的旧模型目录（优先 `OLLAMA_MODELS`，再按 OS 默认路径），若存在则把 `env.OLLAMA_MODELS` 指向旧目录；若不存在则使用 `userData/ollama-models`。若 Ollama 已在 11434 运行则直接复用，不干预目录。

**Tech Stack:** Electron main（Node.js/TypeScript）+ fs/path/os；Vitest（前端已有）。

---

## Files

- Modify: [backend-manager.ts](file:///Users/gengyun/Desktop/DiamondMemory/frontend/src/main/backend-manager.ts)
- Test: `frontend/src/main/__tests__/backend-manager.test.js`（若源文件在 TS，则调整对应测试文件；以仓库现有测试结构为准）

---

### Task 1: 增加“旧模型目录探测”函数

**Files:**
- Modify: [backend-manager.ts](file:///Users/gengyun/Desktop/DiamondMemory/frontend/src/main/backend-manager.ts)

- [ ] **Step 1: 编写最小工具函数（无副作用）**

新增函数（建议私有方法）：
- `private detectPreferredOllamaModelsDir(): string | null`

逻辑：
- 若 `process.env.OLLAMA_MODELS` 存在且有效（见下方判定），直接返回
- 按平台候选目录顺序查找第一个有效目录并返回
- 未找到返回 null

有效目录判定：
- `fs.existsSync(dir)` 且 `fs.statSync(dir).isDirectory()`
- 存在 `path.join(dir, 'manifests')` 子目录
- `fs.readdirSync(manifestsDir).length > 0`

候选目录：
- darwin/linux：
  - `${homedir}/.ollama/models`
  - `${homedir}/Library/Application Support/Ollama/models`（仅 darwin）
- win32：
  - `${USERPROFILE}\\.ollama\\models`
  - `${LOCALAPPDATA}\\Ollama\\models`

---

### Task 2: 调整 startOllama 的 env.OLLAMA_MODELS 策略（优先旧目录）

**Files:**
- Modify: [backend-manager.ts:startOllama](file:///Users/gengyun/Desktop/DiamondMemory/frontend/src/main/backend-manager.ts#L476-L559)

- [ ] **Step 1: 组装 env 时选择模型目录**

在即将 `spawn(ollamaExe, ['serve'], ...)` 前：
- 若 Ollama 不在运行（现有逻辑已判断）：
  - `const legacyDir = this.detectPreferredOllamaModelsDir()`
  - `const modelDir = legacyDir ?? this.getOllamaModelDir()`
  - 始终设置 `env.OLLAMA_MODELS = modelDir`

说明：该策略会让“系统 Ollama”与“内嵌 Ollama”在本 App 启动时都遵循同一目录选择逻辑；且你已确认“若有旧目录，新下载也放旧目录”，因此无需双端口策略。

- [ ] **Step 2: 失败回退**

如果 `waitForOllama()` 超时或启动失败，且本次使用的是旧目录：
- 关闭本次启动的进程（若存在）
- 改用 `this.getOllamaModelDir()` 作为 `OLLAMA_MODELS` 再启动一次

---

### Task 3: 单测覆盖（至少覆盖“旧目录优先”与“无旧目录回退到 userData”）

**Files:**
- Test: `frontend/src/main/__tests__/backend-manager.test.*`

- [ ] **Step 1: 增加测试夹具目录结构**

创建临时目录结构：
- `<tmp>/models/manifests/<dummy>`
- 并用 mock 的 `app.getPath('home')` / `process.env.OLLAMA_MODELS` 指向它

- [ ] **Step 2: Mock spawn 并捕获 env 参数**

目标断言：
- 当 `process.env.OLLAMA_MODELS` 指向有效目录时：spawn env 中 `OLLAMA_MODELS` 为该目录
- 当不存在旧目录时：spawn env 中 `OLLAMA_MODELS` 为 `app.getPath('userData') + '/ollama-models'`

Run:
```bash
cd /Users/gengyun/Desktop/DiamondMemory/frontend && npm test
```

Expected: PASS

---

### Task 4: 集成验证（开发模式）

- [ ] **Step 1: 停止本机 Ollama**

（手动）确保 11434 未被占用。

- [ ] **Step 2: 准备旧模型目录（如已存在可跳过）**

确保旧目录存在且 `manifests/` 非空。

- [ ] **Step 3: 启动 Electron dev 并观察模型列表**

Run:
```bash
cd /Users/gengyun/Desktop/DiamondMemory/frontend && npm run electron:dev
```

Expected:
- 模型页能看到旧模型（无需重新下载）
- 下载新模型后，依旧落在旧模型目录（非 userData）

