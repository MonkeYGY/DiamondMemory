# 端口与配置统一（port_config 与 `~/.diamond-memory/port.json` 兼容）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 统一端口发现的权威来源为 `userData/port.json`，并镜像写入 `~/.diamond-memory/port.json`，实现启动读取优先级（userData → home → default）与“避免旧文件误导”的同步/原子写策略。

**Architecture:** 将端口文件读写/同步逻辑抽成可测试的纯 Node 模块（不依赖 Electron `app`），由 `BackendManager` 仅负责提供 `userDataPath/homePath` 并调用该模块；外部工具继续读取 `~/.diamond-memory/port.json`，后端脚本文案补充“home 为镜像、userData 为权威”说明。

**Tech Stack:** Electron + Node.js（node:test）+ TypeScript；后端为 Python（仅文案/模板调整）

---

## 变更范围与文件职责（先锁定结构）

**Create**
- `frontend/src/main/port-file.ts`
  - 端口发现文件（`port.json`）的路径计算、读取优先级、原子写、镜像同步（纯 Node：传入 userDataPath/homePath）
- `frontend/src/main/__tests__/port-file.test.ts`
  - 覆盖读取优先级、坏 JSON 容错、镜像同步覆盖策略、原子写行为

**Modify**
- `frontend/src/main/backend-manager.ts`
  - 使用 `port-file.ts` 完成：写入 `userData/port.json` + 镜像写入 `~/.diamond-memory/port.json`
  - 启动流程增加“镜像同步”（以 userData 为准覆盖 home）以减少旧文件误导
  - （可选）当 `port_config.json` 缺失/损坏时，用 `port.json` 的端口回填 `preferred_port/last_used_port`
- `backend/app/services/openclaw_service.py`
- `backend/app/services/qclaw_service.py`
- `backend/app/services/hermes_service.py`
  - 更新说明：`~/.diamond-memory/port.json` 为兼容镜像，权威由桌面端维护在 userData

---

## 测试运行方式（本计划中每次改动都要可验证）

### 前端单测（node:test）
由于 main 进程代码会通过 `tsc -p tsconfig.electron.json` 编译到 `frontend/dist/`，测试需运行编译后的 JS：

1) 编译 main：
```bash
cd frontend
npm run electron:build-main
```

2) 执行 node:test：
```bash
node --test dist/main/__tests__/*.test.js
```

期望：所有测试 PASS。

### 编译验收（按项目惯例）
```bash
cd frontend
npm run build
```

---

## Task 1: 为端口文件模块编写失败测试（TDD）

**Files:**
- Create: `frontend/src/main/__tests__/port-file.test.ts`
- (暂不实现) Create: `frontend/src/main/port-file.ts`

- [ ] **Step 1: 写失败测试 - 读取优先级（userData 优先）**

```ts
import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'

import { readPortFilePreferUserData } from '../port-file.js'

test('readPortFilePreferUserData: prefers userData/port.json over home mirror', () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'dm-port-'))
  const userData = path.join(tmp, 'userData')
  const home = path.join(tmp, 'home')
  fs.mkdirSync(userData, { recursive: true })
  fs.mkdirSync(home, { recursive: true })

  fs.writeFileSync(path.join(userData, 'port.json'), JSON.stringify({ port: 15921, endpoint: 'http://127.0.0.1:15921' }), 'utf-8')
  fs.mkdirSync(path.join(home, '.diamond-memory'), { recursive: true })
  fs.writeFileSync(path.join(home, '.diamond-memory', 'port.json'), JSON.stringify({ port: 15920, endpoint: 'http://127.0.0.1:15920' }), 'utf-8')

  const data = readPortFilePreferUserData({ userDataPath: userData, homePath: home })
  assert.equal(data?.port, 15921)
})
```

- [ ] **Step 2: 写失败测试 - fallback 到 home 镜像**

```ts
import { readPortFilePreferUserData } from '../port-file.js'

test('readPortFilePreferUserData: falls back to ~/.diamond-memory/port.json when userData missing', () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'dm-port-'))
  const userData = path.join(tmp, 'userData')
  const home = path.join(tmp, 'home')
  fs.mkdirSync(userData, { recursive: true })
  fs.mkdirSync(path.join(home, '.diamond-memory'), { recursive: true })

  fs.writeFileSync(path.join(home, '.diamond-memory', 'port.json'), JSON.stringify({ port: 15922, endpoint: 'http://127.0.0.1:15922' }), 'utf-8')

  const data = readPortFilePreferUserData({ userDataPath: userData, homePath: home })
  assert.equal(data?.port, 15922)
})
```

- [ ] **Step 3: 写失败测试 - 坏 JSON 容错**

```ts
test('readPortFilePreferUserData: ignores invalid JSON and returns null', () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'dm-port-'))
  const userData = path.join(tmp, 'userData')
  const home = path.join(tmp, 'home')
  fs.mkdirSync(userData, { recursive: true })
  fs.mkdirSync(path.join(home, '.diamond-memory'), { recursive: true })

  fs.writeFileSync(path.join(userData, 'port.json'), '{bad-json', 'utf-8')
  fs.writeFileSync(path.join(home, '.diamond-memory', 'port.json'), '{bad-json', 'utf-8')

  const data = readPortFilePreferUserData({ userDataPath: userData, homePath: home })
  assert.equal(data, null)
})
```

- [ ] **Step 4: 写失败测试 - 镜像同步（以 userData 覆盖 home）**

```ts
import { syncHomeMirrorFromUserData } from '../port-file.js'

test('syncHomeMirrorFromUserData: overwrites home mirror when mismatch', () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'dm-port-'))
  const userData = path.join(tmp, 'userData')
  const home = path.join(tmp, 'home')
  fs.mkdirSync(userData, { recursive: true })
  fs.mkdirSync(path.join(home, '.diamond-memory'), { recursive: true })

  fs.writeFileSync(path.join(userData, 'port.json'), JSON.stringify({ port: 15923, endpoint: 'http://127.0.0.1:15923' }), 'utf-8')
  fs.writeFileSync(path.join(home, '.diamond-memory', 'port.json'), JSON.stringify({ port: 15920, endpoint: 'http://127.0.0.1:15920' }), 'utf-8')

  syncHomeMirrorFromUserData({ userDataPath: userData, homePath: home })

  const mirrored = JSON.parse(fs.readFileSync(path.join(home, '.diamond-memory', 'port.json'), 'utf-8'))
  assert.equal(mirrored.port, 15923)
})
```

- [ ] **Step 5: 写失败测试 - 原子写（先 tmp 再 rename）**

```ts
import { writePortFileAtomic } from '../port-file.js'

test('writePortFileAtomic: writes the exact content to target path', () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'dm-port-'))
  const target = path.join(tmp, 'port.json')

  writePortFileAtomic({
    filePath: target,
    data: { port: 15924, pid: 1, startedAt: 'x', endpoint: 'http://127.0.0.1:15924' }
  })

  const saved = JSON.parse(fs.readFileSync(target, 'utf-8'))
  assert.equal(saved.port, 15924)
  assert.equal(saved.endpoint, 'http://127.0.0.1:15924')
})
```

- [ ] **Step 6: 运行测试，确认失败**

Run:
```bash
cd frontend
npm run electron:build-main
node --test dist/main/__tests__/port-file.test.js
```

Expected: FAIL（因为 `frontend/src/main/port-file.ts` 尚未实现 / 导出不存在）。

- [ ] **Step 7: Commit（只提交测试）**

```bash
git add frontend/src/main/__tests__/port-file.test.ts
git commit -m "test: add port file priority and sync cases"
```

---

## Task 2: 实现 `port-file.ts` 使测试通过（纯 Node）

**Files:**
- Create: `frontend/src/main/port-file.ts`
- Test: `frontend/src/main/__tests__/port-file.test.ts`

- [ ] **Step 1: 实现类型与路径计算**

```ts
// frontend/src/main/port-file.ts
import fs from 'node:fs'
import path from 'node:path'

export interface PortFileData {
  port: number
  pid?: number
  startedAt?: string
  endpoint?: string
}

export function getUserDataPortFilePath(userDataPath: string): string {
  return path.join(userDataPath, 'port.json')
}

export function getHomeMirrorPortFilePath(homePath: string): string {
  return path.join(homePath, '.diamond-memory', 'port.json')
}
```

- [ ] **Step 2: 实现读取（容错 + 最小校验）**

```ts
function _readJsonFile(filePath: string): any | null {
  try {
    if (!fs.existsSync(filePath)) return null
    const raw = fs.readFileSync(filePath, 'utf-8')
    const obj = JSON.parse(raw)
    return obj && typeof obj === 'object' ? obj : null
  } catch {
    return null
  }
}

export function readPortFilePreferUserData(opts: { userDataPath: string; homePath: string }): PortFileData | null {
  const userDataFile = getUserDataPortFilePath(opts.userDataPath)
  const homeFile = getHomeMirrorPortFilePath(opts.homePath)

  const userObj = _readJsonFile(userDataFile)
  if (userObj && typeof userObj.port === 'number') return userObj as PortFileData

  const homeObj = _readJsonFile(homeFile)
  if (homeObj && typeof homeObj.port === 'number') return homeObj as PortFileData

  return null
}
```

- [ ] **Step 3: 实现原子写（确保目录存在）**

```ts
export function writePortFileAtomic(opts: { filePath: string; data: PortFileData }): void {
  const dir = path.dirname(opts.filePath)
  fs.mkdirSync(dir, { recursive: true })
  const tmp = opts.filePath + '.tmp'
  fs.writeFileSync(tmp, JSON.stringify(opts.data, null, 2), 'utf-8')
  fs.renameSync(tmp, opts.filePath)
}
```

- [ ] **Step 4: 实现镜像同步（以 userData 为准）**

```ts
export function syncHomeMirrorFromUserData(opts: { userDataPath: string; homePath: string }): void {
  const userFile = getUserDataPortFilePath(opts.userDataPath)
  const homeFile = getHomeMirrorPortFilePath(opts.homePath)
  if (!fs.existsSync(userFile)) return

  const userObj = _readJsonFile(userFile)
  if (!userObj || typeof userObj.port !== 'number') return

  const homeObj = _readJsonFile(homeFile)
  const same = homeObj && JSON.stringify(homeObj) === JSON.stringify(userObj)
  if (!same) {
    writePortFileAtomic({ filePath: homeFile, data: userObj as PortFileData })
  }
}
```

- [ ] **Step 5: 运行测试，确认通过**

Run:
```bash
cd frontend
npm run electron:build-main
node --test dist/main/__tests__/port-file.test.js
```

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add frontend/src/main/port-file.ts
git commit -m "feat: add port file atomic write and mirror sync"
```

---

## Task 3: `BackendManager` 接入新模块，形成“权威 + 镜像”完整闭环

**Files:**
- Modify: `frontend/src/main/backend-manager.ts`
- Test: `frontend/src/main/__tests__/port-file.test.ts`（回归）

- [ ] **Step 1: 在 `backend-manager.ts` 引入模块并替换写端口逻辑**

将原先 `writePortFile()` 中对 `fs.writeFileSync(userDataPortFile...)` / `fs.writeFileSync(dmPortFile...)` 的直接写入替换为：

```ts
import {
  getUserDataPortFilePath,
  getHomeMirrorPortFilePath,
  writePortFileAtomic,
  syncHomeMirrorFromUserData,
} from './port-file.js'
```

并在 `writePortFile()` 中：
- 先构造 `portDataObj`
- `writePortFileAtomic({ filePath: getUserDataPortFilePath(app.getPath('userData')), data: portDataObj })`
- `writePortFileAtomic({ filePath: getHomeMirrorPortFilePath(app.getPath('home')), data: portDataObj })`

- [ ] **Step 2: 在启动时增加一次镜像同步（避免旧文件误导）**

在启动流程中（例如 `startBackend()` 早期，或构造器中）调用：

```ts
syncHomeMirrorFromUserData({ userDataPath: app.getPath('userData'), homePath: app.getPath('home') })
```

说明：这里的同步用于“若两份历史文件不一致，以 userData 覆盖 home”，保证外部工具优先读到与应用一致的端口发现文件。

- [ ] **Step 3（可选但推荐）: `port_config.json` 缺失/损坏时从 `port.json` 回填**

在 `readPortConfig()` 中：
- 当 `port_config.json` 不存在或 JSON 解析失败时：
  - 调用 `readPortFilePreferUserData({ userDataPath, homePath })`
  - 若得到 `port`，将其作为 `preferred_port/last_used_port` 的恢复值（否则用默认 15920）

- [ ] **Step 4: 运行前端测试**

Run:
```bash
cd frontend
npm run electron:build-main
node --test dist/main/__tests__/*.test.js
```

Expected: PASS

- [ ] **Step 5: 前端构建验收**

Run:
```bash
cd frontend
npm run build
```

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add frontend/src/main/backend-manager.ts
git commit -m "fix: make port.json authoritative in userData with home mirror"
```

---

## Task 4: 后端服务脚本文案更新（openclaw/qclaw/hermes）

**Files:**
- Modify: `backend/app/services/openclaw_service.py`
- Modify: `backend/app/services/qclaw_service.py`
- Modify: `backend/app/services/hermes_service.py`

- [ ] **Step 1: 更新说明文案**

在各自的“端口发现说明”处补充类似表述（保持中文、简洁）：

> `~/.diamond-memory/port.json` 为兼容镜像文件，由桌面端自动写入与维护；权威端口来源为桌面端 `userData/port.json`，当两者不一致时以 `userData/port.json` 为准。

- [ ] **Step 2: Python 语法检查（轻量）**

Run:
```bash
python -m compileall backend/app/services/openclaw_service.py backend/app/services/qclaw_service.py backend/app/services/hermes_service.py
```

Expected: no SyntaxError

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/openclaw_service.py backend/app/services/qclaw_service.py backend/app/services/hermes_service.py
git commit -m "docs: clarify port.json authority and mirror behavior for agents"
```

---

## Task 5: 验收检查清单（手动）

- [ ] **Step 1: 启动桌面端，确认生成两份文件**
  - `<userData>/port.json`
  - `~/.diamond-memory/port.json`
  - 两者内容一致（至少 `port/endpoint` 一致）

- [ ] **Step 2: 制造端口占用触发迁移**
  - 占用 15920 后启动，观察切换到候选端口
  - 确认两份 `port.json` 更新到新端口

- [ ] **Step 3: 外部工具读取验证**
  - `cat ~/.diamond-memory/port.json | python3 -c "import sys,json;print(json.load(sys.stdin)['endpoint'])"`
  - 访问 `$endpoint/health` 返回 200

- [ ] **Step 4: 版本优化记录自动追加**
  - 将本次实现的任务记录追加到 `版本优化记录/版本优化0.9.1.md` 顶部（时间倒序），包含：任务类型/简述/修改文件/完成状态

---

## Plan 自检（对照 spec）

- Spec 要求的“权威位置 userData + home 兼容镜像 + 读优先级 + 避免旧文件误导 + 外部工具可读到真实端口”均有对应任务（Task 1-5）。
- 本计划无 TBD/TODO 占位；每个任务包含明确文件路径、命令与预期结果。

