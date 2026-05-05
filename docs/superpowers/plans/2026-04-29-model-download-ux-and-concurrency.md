# 模型下载（bge-m3）进度/取消/并发 + 首启缺模型提示 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复 bge-m3 下载进度长期 0% 的问题，支持取消下载与多模型并发下载，并在首次启动缺模型时弹窗提示下载（可跳过）。

**Architecture:** 后端统一改为通过 Ollama HTTP API `/api/pull` 的流式 JSON 输出采集进度，不再依赖 `ollama pull` 命令行与 stdout 解析；前端以“每模型一条下载任务状态”渲染进度/取消，移除“全局只允许一个下载”的限制，并在启动时基于 `/api/config/startup-status` 弹出缺模型提示。

**Tech Stack:** FastAPI + requests（streaming）+ threading；Vue3 + TypeScript。

---

## 变更文件总览

**Backend**
- Modify: [config_routes.py](file:///Users/gengyun/Desktop/DiamondMemory/backend/app/api/config_routes.py)
- Modify: [config_routes.py:get_startup_status](file:///Users/gengyun/Desktop/DiamondMemory/backend/app/api/config_routes.py#L324-L381)
- (Optional) Create: `backend/app/services/ollama_model_pull_service.py`（把线程/状态管理从路由中剥离，便于测试）
- Create: `backend/tests/test_model_pull_api.py`

**Frontend**
- Modify: [ModelView.vue](file:///Users/gengyun/Desktop/DiamondMemory/frontend/src/renderer/views/ModelView.vue)
- Modify: [SettingsView.vue](file:///Users/gengyun/Desktop/DiamondMemory/frontend/src/renderer/views/SettingsView.vue)（设置页也有“下载模型”入口）
- Modify: [App.vue](file:///Users/gengyun/Desktop/DiamondMemory/frontend/src/renderer/App.vue)
- Create: `frontend/src/renderer/components/ModelSetup.vue`（缺模型弹窗：下载/取消/跳过/去模型管理）

---

## 接口契约（用于前端）

### 1) 拉取模型
`POST /api/config/pull-model`

Request body:
```json
{ "model_name": "bge-m3" }
```

Response:
```json
{ "status": "started", "model": "bge-m3", "message": "开始拉取模型 bge-m3" }
```

### 2) 取消拉取
`POST /api/config/cancel-pull`

Request body:
```json
{ "model_name": "bge-m3" }
```

Response:
```json
{ "status": "cancelled", "model": "bge-m3", "message": "已取消下载 bge-m3" }
```

### 3) 拉取进度（全量）
`GET /api/config/pull-progress`

Response:
```json
{
  "pulls": {
    "bge-m3": {
      "status": "pulling",
      "progress": 12,
      "total": 123,
      "completed": 15,
      "status_detail": "downloading",
      "error": null,
      "started_at": 1710000000.1
    }
  }
}
```

### 4) 启动状态（修复 ollama_ready 语义）
`GET /api/config/startup-status`

- `ollama_ready` 必须表示 “Ollama 服务可达（tags/ps 任一接口 200）”，不能用 “是否安装过模型” 代替。
- `embedding_installed` 只代表 tags 里是否出现 bge-m3。

---

## Task 1: 后端—修复 startup-status 的 ollama_ready 判定

**Files:**
- Modify: [config_routes.py:get_startup_status](file:///Users/gengyun/Desktop/DiamondMemory/backend/app/api/config_routes.py#L324-L381)
- Test: `backend/tests/test_startup_status_api.py`（若已有覆盖则追加用例；否则新建小用例）

- [ ] **Step 1: 写一个失败用例（ollama 可达但无模型时 ollama_ready 应为 true）**

```python
import types
from unittest.mock import patch

def _resp(status_code: int, payload: dict):
    r = types.SimpleNamespace()
    r.status_code = status_code
    r.json = lambda: payload
    return r

def test_startup_status_ollama_ready_when_empty_models(client):
    with patch("app.api.config_routes.requests.get") as mget:
        mget.side_effect = [
            _resp(200, {"models": []}),  # /api/tags
            _resp(200, {"models": []}),  # /api/ps
        ]
        res = client.get("/api/config/startup-status")
        assert res.status_code == 200
        data = res.json()
        assert data["ollama_ready"] is True
```

- [ ] **Step 2: 运行测试，确认失败**

Run:
```bash
cd /Users/gengyun/Desktop/DiamondMemory/backend && pytest -q
```

Expected: 失败点在 `ollama_ready` 返回 False。

- [ ] **Step 3: 修改实现**

实现要点（不要引入新依赖）：
- `ollama_ready = (tags_resp.status_code == 200) or (ps_resp.status_code == 200)`
- `installed_models / loaded_models` 在各自 status_code==200 时才解析

- [ ] **Step 4: 再跑测试，确认通过**

Run:
```bash
cd /Users/gengyun/Desktop/DiamondMemory/backend && pytest -q
```

Expected: PASS

---

## Task 2: 后端—将 pull-model 改为使用 Ollama `/api/pull` 流式进度（修复进度 0%）

**Files:**
- Modify: [config_routes.py](file:///Users/gengyun/Desktop/DiamondMemory/backend/app/api/config_routes.py)
- Create: `backend/tests/test_model_pull_api.py`

- [ ] **Step 1: 写失败用例（解析 /api/pull JSON 行更新 progress/total/completed）**

```python
import json
from unittest.mock import patch

class _StreamResp:
    status_code = 200
    def iter_lines(self, decode_unicode=True):
        yield json.dumps({"status": "downloading", "total": 100, "completed": 1})
        yield json.dumps({"status": "downloading", "total": 100, "completed": 50})
        yield json.dumps({"status": "success"})

def test_pull_model_updates_progress(client):
    with patch("app.api.config_routes.requests.post") as mpost:
        mpost.return_value = _StreamResp()
        res = client.post("/api/config/pull-model", json={"model_name": "bge-m3"})
        assert res.status_code == 200

    # 等待线程推进（轮询 progress 接口，最多 2 秒）
    for _ in range(20):
        p = client.get("/api/config/pull-progress").json()["pulls"].get("bge-m3")
        if p and p.get("progress", 0) >= 50:
            break
        import time; time.sleep(0.1)

    p = client.get("/api/config/pull-progress").json()["pulls"]["bge-m3"]
    assert p["total"] == 100
    assert p["completed"] >= 50
    assert p["progress"] >= 50
```

- [ ] **Step 2: 修改 `/pull-model` 实现**

实现要求：
- 不再 `subprocess.Popen(["ollama","pull",...])`
- 改为 `requests.post(f"{ollama_url}/api/pull", json={"name": model_name, "stream": True}, stream=True, timeout=...)`
- 从 `resp.iter_lines()` 逐行解析 JSON，读取字段：
  - `status`（字符串）
  - `total` / `completed`（数字，可缺失）
  - 计算 `progress = int(completed/total*100)`，total=0 时 progress 保持上次值但 `status_detail` 必须更新
- 完成条件：
  - 收到 `{"status":"success"}`（或行内带 success 语义）则标记 completed
  - 连接异常/非 200 则标记 failed 并写入 error

- [ ] **Step 3: 运行后端测试**

Run:
```bash
cd /Users/gengyun/Desktop/DiamondMemory/backend && pytest -q
```

Expected: PASS

---

## Task 3: 后端—取消拉取（真正停止进度刷新 + 状态 cancelled）

**Files:**
- Modify: [config_routes.py](file:///Users/gengyun/Desktop/DiamondMemory/backend/app/api/config_routes.py)
- Modify: `backend/tests/test_model_pull_api.py`

- [ ] **Step 1: 追加失败用例（cancel 后 status=cancelled，且不再继续增长 completed）**

```python
import json
import time
from unittest.mock import patch

class _SlowStreamResp:
    status_code = 200
    def iter_lines(self, decode_unicode=True):
        for i in range(1, 1000):
            yield json.dumps({"status": "downloading", "total": 1000, "completed": i})
            time.sleep(0.01)

def test_cancel_pull_stops_progress(client):
    with patch("app.api.config_routes.requests.post") as mpost:
        mpost.return_value = _SlowStreamResp()
        client.post("/api/config/pull-model", json={"model_name": "bge-m3"})

    time.sleep(0.05)
    before = client.get("/api/config/pull-progress").json()["pulls"]["bge-m3"]["completed"]

    client.post("/api/config/cancel-pull", json={"model_name": "bge-m3"})
    time.sleep(0.05)

    after = client.get("/api/config/pull-progress").json()["pulls"]["bge-m3"]["completed"]
    status = client.get("/api/config/pull-progress").json()["pulls"]["bge-m3"]["status"]
    assert status == "cancelled"
    assert after == before
```

- [ ] **Step 2: 实现取消机制**

实现要点：
- 为每个 model_name 存一个 `threading.Event()` 作为 cancel token
- 读取 iter_lines 循环中检查 token，若 set：
  - 更新进度对象 status=cancelled
  - 立即 break 结束线程

接口返回统一结构：
```json
{ "status": "cancelled", "model": "bge-m3", "message": "已取消下载 bge-m3" }
```

- [ ] **Step 3: 运行测试**

Run:
```bash
cd /Users/gengyun/Desktop/DiamondMemory/backend && pytest -q
```

Expected: PASS

---

## Task 4: 后端—支持多模型并发拉取（并发上限 + 同模型幂等）

**Files:**
- Modify: [config_routes.py](file:///Users/gengyun/Desktop/DiamondMemory/backend/app/api/config_routes.py)
- Modify: `backend/tests/test_model_pull_api.py`

- [ ] **Step 1: 追加测试（两个不同模型同时 started，不互相覆盖进度）**

```python
import json
from unittest.mock import patch

class _StreamA:
    status_code = 200
    def iter_lines(self, decode_unicode=True):
        yield json.dumps({"status":"downloading","total":100,"completed":10})
        yield json.dumps({"status":"success"})

class _StreamB:
    status_code = 200
    def iter_lines(self, decode_unicode=True):
        yield json.dumps({"status":"downloading","total":200,"completed":20})
        yield json.dumps({"status":"success"})

def test_pull_two_models_in_parallel(client):
    with patch("app.api.config_routes.requests.post") as mpost:
        mpost.side_effect = [_StreamA(), _StreamB()]
        client.post("/api/config/pull-model", json={"model_name":"bge-m3"})
        client.post("/api/config/pull-model", json={"model_name":"qwen3.5:4b"})

    pulls = client.get("/api/config/pull-progress").json()["pulls"]
    assert "bge-m3" in pulls
    assert "qwen3.5:4b" in pulls
```

- [ ] **Step 2: 实现并发策略**

推荐策略：
- 同模型：若 status==pulling，返回 `already_pulling`
- 不同模型：允许并发
- 可选并发上限（避免网络/磁盘打满）：例如同时 pulling 超过 3 个则返回 429：
  - `{"status":"rejected","message":"同时下载任务过多，请稍后重试"}`

- [ ] **Step 3: 运行测试**

Run:
```bash
cd /Users/gengyun/Desktop/DiamondMemory/backend && pytest -q
```

Expected: PASS

---

## Task 5: 前端—ModelView 支持并发下载 + 取消按钮（不再全局禁用）

**Files:**
- Modify: [ModelView.vue](file:///Users/gengyun/Desktop/DiamondMemory/frontend/src/renderer/views/ModelView.vue)

- [ ] **Step 1: 调整交互约束**

把这些逻辑删掉/替换：
- `:disabled="isAnyPulling"`（下载按钮不再全局禁用）
- `pullCustomModel` 的 `isAnyPulling` 约束改为：只要该 custom model 自己不是 pulling 即可

新增能力：
- pulling 状态下显示 “取消” 按钮，调用 `POST /api/config/cancel-pull`

- [ ] **Step 2: 实现每卡片粒度的 disabled**

建议实现：
- `const isPulling = (name) => getPullStatus(name)?.status === 'pulling'`
- 下载按钮 disabled = `isPulling(name)` 或 `isModelInstalled(name)`
- 取消按钮仅在 `isPulling(name)` 时显示

- [ ] **Step 3: 手工验证**

Run:
```bash
cd /Users/gengyun/Desktop/DiamondMemory/frontend && npm test
```

如果项目未配置前端测试，则用开发模式手测：
- 同时点 bge-m3 与 qwen3.5:4b 两个“下载”，两条进度都应推进
- bge-m3 “取消”后，该卡片显示已取消/可重试，且进度不再变化

---

## Task 6: 前端—SettingsView 的下载区域同样支持并发 + 取消

**Files:**
- Modify: [SettingsView.vue](file:///Users/gengyun/Desktop/DiamondMemory/frontend/src/renderer/views/SettingsView.vue)

- [ ] **Step 1: 找到 SettingsView 内 defaultModels/pullModel/isAnyPulling 的实现并改为“每模型粒度”**

目标与 ModelView 一致：
- 不再全局只允许一个下载
- pulling 时显示取消按钮

- [ ] **Step 2: 手工验证**

在“设置 -> 模型管理”中：
- 同时下载两个模型不互相禁用
- 下载中可取消

---

## Task 7: 前端—首启缺模型弹窗（可跳过）

**Files:**
- Create: `frontend/src/renderer/components/ModelSetup.vue`
- Modify: [App.vue](file:///Users/gengyun/Desktop/DiamondMemory/frontend/src/renderer/App.vue)

- [ ] **Step 1: 新增 ModelSetup 组件**

组件行为：
- 显示条件（由 App 决定）：`ollama_ready=true` 且 (`embedding_installed=false` 或 `llm_installed=false`)
- 展示：
  - 缺 bge-m3：显示“下载 bge-m3 / 取消 / 查看进度”
  - 缺主模型：显示“下载当前主模型 / 取消 / 查看进度”
  - “去模型管理”（切换到 model tab 或打开 ModelView）
  - “跳过”（写入 localStorage，例如 `dm-model-setup-skipped=true`）

- [ ] **Step 2: App.vue 接入弹窗触发**

实现要点：
- 在 `checkStatus()` 成功拿到 `startupStatus` 后：
  - 若满足缺模型条件且未 `dm-model-setup-skipped`、未 `dm-model-setup-dismissed`：显示 ModelSetup
  - 若模型都已 installed：自动隐藏
- 关闭/跳过：
  - close：写 `dm-model-setup-dismissed=true`
  - skip：写 `dm-model-setup-skipped=true`

- [ ] **Step 3: 手工验证**

场景：
- 新安装无任何模型：启动后弹窗出现，点击下载 bge-m3 能推进进度
- 点击跳过：本次不再弹，顶部状态仍显示“未启动”
- 模型安装完毕后重启：不再弹窗

---

## Task 8: 全链路验证（开发模式）

- [ ] **Step 1: 启动后端**

Run:
```bash
cd /Users/gengyun/Desktop/DiamondMemory/backend && ./venv/bin/python3 main.py
```

- [ ] **Step 2: 启动前端**

Run:
```bash
cd /Users/gengyun/Desktop/DiamondMemory/frontend && npm run dev
```

- [ ] **Step 3: 验证点**

- bge-m3 点击下载后进度不再长期 0%
- 下载中存在“取消”按钮，取消后进度停止且状态变为 cancelled
- 同时下载两个模型都能推进进度
- 首启缺模型弹窗按预期出现且可跳过

