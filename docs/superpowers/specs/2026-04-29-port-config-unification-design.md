# 端口与配置统一：port_config 与 `~/.diamond-memory/port.json` 兼容（设计稿）

- 日期：2026-04-29
- 任务卡：#8（ID=8，P2）
- 目标：前端、后端、外部工具读取同一端口来源，不再各写各的

## 背景与现状

目前端口相关存在两类文件/用途：

1. **稳定端口策略配置**：`userData/port_config.json`
   - 保存 `preferred_port / consecutive_conflicts / last_used_port`
   - 用于“优先固定端口 + 冲突自动迁移”的策略决策

2. **对外端口发现文件**：`port.json`
   - 既存在于 `userData/port.json`，也可能存在于 `~/.diamond-memory/port.json`
   - 外部工具（如 OpenClaw/QClaw/Hermes）约定读取 `~/.diamond-memory/port.json` 的 `endpoint` 字段

问题：
- 缺少明确的“权威来源”与“读取优先级”，容易出现**旧文件误导**、双写不一致、外部工具读到过期端口。
- `port_config.json`（策略）与 `port.json`（发现）是两套体系，若未显式同步，容易出现割裂。

## 目标（Goals）

1. **确定唯一权威端口来源**：统一为 `userData/port.json`。
2. **向后兼容外部工具**：持续输出兼容文件到 `~/.diamond-memory/port.json`，内容与权威一致。
3. **启动时读取优先级清晰**：优先读 `userData/port.json`，失败再读 home 兼容文件。
4. **避免旧文件误导**：检测不一致时以权威覆盖镜像；写入使用原子写，减少半写入/损坏风险。
5. **端口变更后外部工具可读到真实端口**：端口切换后立即刷新双文件内容。

## 非目标（Non-goals）

- 不改变现有稳定端口策略（连续冲突阈值、候选端口列表等）的核心行为。
- 不要求外部工具改读取路径（仍按约定读取 `~/.diamond-memory/port.json`）。
- 不引入新的全局配置目录结构（仍使用 Electron `userData` 作为应用内部权威位置）。

## 设计总览

### 1) 权威文件与镜像文件

- **权威端口发现文件**：`<userData>/port.json`
- **兼容镜像文件**：`~/.diamond-memory/port.json`

两者 JSON 内容保持一致，建议字段如下（保持兼容现有外部工具读取）：

```json
{
  "port": 15920,
  "pid": 12345,
  "startedAt": "2026-04-29T12:34:56.000Z",
  "endpoint": "http://127.0.0.1:15920"
}
```

### 2) 启动读取优先级（端口发现）

应用内任何需要“当前实际运行端口”的逻辑，按以下顺序读取：

1. 读 `userData/port.json`
2. fallback 读 `~/.diamond-memory/port.json`
3. 再 fallback 到默认端口（15920）

说明：
- 该读取逻辑用于**端口发现/恢复**（尤其是启动早期、异常场景、或端口策略文件损坏时）。
- 稳定端口策略仍以 `userData/port_config.json` 为主；但当 `port_config.json` 缺失/损坏时，可用 `port.json` 的端口作为“合理恢复值”（例如回填 `preferred_port/last_used_port`）。

### 3) 写入策略（双写 + 原子写 + 自动同步）

写入时遵循以下规则：

1. **先写权威**：`userData/port.json`
2. **再写镜像**：`~/.diamond-memory/port.json`
3. 写入采用**原子写**：
   - 写到同目录临时文件（如 `port.json.tmp`）
   - `fs.renameSync`/等价方式替换正式文件

启动时额外做一次“镜像同步”以防旧文件误导：
- 如果检测到 `userData/port.json` 与 `~/.diamond-memory/port.json` 内容不一致：
  - **以 userData 为准覆盖 home 镜像**

### 4) `port_config.json` 的定位与联动

`userData/port_config.json` 仅承担“稳定端口策略元数据”职责（preferred_port / consecutive_conflicts / last_used_port）。

联动规则：
- 每次成功启动（获得实际端口）后：
  - 更新 `port.json`（权威 + 镜像）
  - 同时更新 `port_config.json.last_used_port`
- 当稳定端口迁移（preferred_port 改变）时：
  - 迁移完成并启动成功后，`port.json` 会自然写出新端口；外部工具读取即得到新端口。

### 5) OpenClaw/QClaw/Hermes（外部工具）兼容说明

保持外部工具端口发现方式不变：
- 仍读取 `~/.diamond-memory/port.json` 的 `endpoint` 字段。

但需要在后端服务脚本/说明中明确：
- `~/.diamond-memory/port.json` 为**兼容镜像**，由桌面端维护，权威来源为 `userData/port.json`。
- 当连接失败时允许重读该文件/扫描候选端口（现有文案已包含该策略，可保留）。

## 需要修改的模块（预期改动点）

> 以下为设计层面的“改动范围”，具体实现细节在 plan 阶段落地。

### 前端（Electron）

- `frontend/src/main/backend-manager.ts`
  - 新增/调整：端口文件路径解析、读优先级（userData -> home）、启动时镜像同步、原子写工具函数
  - 明确职责边界：
    - `port_config.json`：策略
    - `port.json`：发现（权威/镜像）

### 后端（服务脚本/集成说明）

- `backend/app/services/openclaw_service.py`
- `backend/app/services/qclaw_service.py`
- `backend/app/services/hermes_service.py`
  - 更新说明文字（port.json 的权威/镜像关系）
  - 如有硬编码 “仅 home 目录” 的表述，统一为“读取 home 镜像”（保持兼容）

## 验收标准（Acceptance Criteria）

1. 端口变更后（例如连续冲突触发迁移、或其他原因导致端口变化），`~/.diamond-memory/port.json` 能读到真实端口（endpoint/port 正确）。
2. 应用启动时优先读取 `userData/port.json`；若缺失/损坏，能 fallback 到 `~/.diamond-memory/port.json`；再不行才回退默认端口。
3. 不存在“旧文件误导”：
   - 若两份 port.json 不一致，最终以 `userData/port.json` 覆盖 `~/.diamond-memory/port.json`。
4. 端口文件写入过程尽量避免半写入/损坏（原子写）。
5. 不引入新的硬编码路径；遵循配置从配置层读取/集中管理的项目规范。

## 测试与验证建议

- 单元/集成测试（尽量自动化）：
  - 模拟 userData port.json 存在 / home port.json 存在 / 两者冲突 / 文件损坏（JSON parse 失败）
  - 验证读取优先级与同步覆盖逻辑
- 手动验收：
  - 启动应用，确认生成 `userData/port.json` 与 `~/.diamond-memory/port.json`
  - 强制占用 15920（触发冲突），观察迁移后两份文件更新
  - 外部工具读取 `~/.diamond-memory/port.json` 并能正确访问 `/health`

