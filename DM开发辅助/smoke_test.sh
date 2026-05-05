#!/bin/bash

# ==========================================
# DiamondMemory 冒烟测试脚本（开发态优先）
# 用途：在不打包 App 的情况下，快速验证“核心链路是否可用”
# ==========================================

set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

ok() { echo -e "${GREEN}✓ $*${NC}"; }
warn() { echo -e "${YELLOW}! $*${NC}"; }
fail() { echo -e "${RED}✗ $*${NC}"; }

echo -e "${YELLOW}🧪 DiamondMemory 冒烟测试开始...${NC}"

check_backend_health() {
  local port="$1"
  local response
  response=$(curl -fsS --max-time 2 "http://127.0.0.1:${port}/health" 2>/dev/null || true)
  [[ "$response" == *'"service":"diamond_memory_backend"'* || "$response" == *'"service": "diamond_memory_backend"'* ]]
}

resolve_backend_port() {
  # 1) 15920（开发态）
  if check_backend_health 15920; then
    echo "15920"
    return 0
  fi

  # 2) 尝试读取兼容端口文件 ~/.diamond-memory/port.json
  local port_file="$HOME/.diamond-memory/port.json"
  if [ -f "$port_file" ]; then
    local p
    p=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["port"])' "$port_file" 2>/dev/null || true)
    if [[ "$p" =~ ^[0-9]+$ ]] && check_backend_health "$p"; then
      echo "$p"
      return 0
    fi
  fi

  # 3) 从后端进程反查监听端口（Electron/编译产物等）
  local pid=""
  pid=$(pgrep -f "DiamondMemoryBackend" 2>/dev/null | head -n 1 || true)
  if [ -z "$pid" ]; then
    pid=$(pgrep -f "uvicorn.*main:app" 2>/dev/null | head -n 1 || true)
  fi
  if [ -z "$pid" ]; then
    pid=$(pgrep -f "python.*main\.py.*--port" 2>/dev/null | head -n 1 || true)
  fi
  if [ -n "$pid" ]; then
    local p
    p=$(lsof -Pan -p "$pid" -iTCP -sTCP:LISTEN 2>/dev/null | grep LISTEN | awk -F':' '{print $NF}' | awk '{print $1}' | head -n 1 || true)
    if [[ "$p" =~ ^[0-9]+$ ]] && check_backend_health "$p"; then
      echo "$p"
      return 0
    fi
  fi

  return 1
}

BACKEND_PORT=""
if BACKEND_PORT=$(resolve_backend_port); then
  ok "后端健康检查通过（端口：${BACKEND_PORT}）"
else
  fail "未发现可用后端服务。请先点击「开发模式」启动后端（或确认端口/进程正常）"
  exit 1
fi

API="http://127.0.0.1:${BACKEND_PORT}"
FAILED=0

step() {
  echo -e "\n${YELLOW}==> $*${NC}"
}

run_check() {
  local name="$1"
  shift
  if "$@"; then
    ok "${name}"
  else
    fail "${name}"
    FAILED=$((FAILED + 1))
  fi
}

step "1/5 基础健康检查"
run_check "GET /health" curl -fsS --max-time 3 "${API}/health" >/dev/null

step "2/5 启动状态（允许 Ollama 缺失降级）"
if curl -fsS --max-time 5 "${API}/api/startup-status" >/dev/null 2>&1; then
  ok "GET /api/startup-status"
else
  warn "GET /api/startup-status 失败（不影响核心检索，但建议检查后端日志）"
fi

step "3/5 创建记忆 → 读取 → 查询"
SMOKE_CONTENT="【SMOKE_TEST】$(date '+%Y-%m-%d %H:%M:%S') 冒烟测试写入"
CREATE_RESP="$(curl -fsS --max-time 8 -X POST "${API}/api/memory/create" \
  -H "Content-Type: application/json" \
  -d "{\"content\":\"${SMOKE_CONTENT}\",\"category\":\"smoke\",\"source\":\"smoke_test\",\"tags\":[\"smoke\"],\"layer\":1}" 2>/dev/null || true)"

SMOKE_ID="$(python3 -c 'import json,sys;print(json.load(sys.stdin).get("id",""))' <<<"$CREATE_RESP" 2>/dev/null || true)"
if [ -n "$SMOKE_ID" ]; then
  ok "POST /api/memory/create（id=${SMOKE_ID}）"
else
  fail "POST /api/memory/create 失败（响应：${CREATE_RESP:0:200}）"
  FAILED=$((FAILED + 1))
fi

if [ -n "$SMOKE_ID" ]; then
  run_check "GET /api/memory/get/{id}" curl -fsS --max-time 5 "${API}/api/memory/get/${SMOKE_ID}" >/dev/null
  run_check "GET /api/memory/query?query=SMOKE_TEST" curl -fsS --max-time 8 "${API}/api/memory/query?query=SMOKE_TEST&limit=3" >/dev/null
fi

step "4/5 知识库树（可能较慢，慢则优先做 ID=6）"
if curl -fsS --max-time 8 "${API}/api/knowledge/tree" >/dev/null 2>&1; then
  ok "GET /api/knowledge/tree"
else
  warn "GET /api/knowledge/tree 超时/失败（如目录很大可先跳过，优先处理 ID=6 做增量扫描）"
fi

step "5/5 结果汇总"
if [ "$FAILED" -eq 0 ]; then
  ok "冒烟测试通过（核心链路可用）"
  echo -e "${GREEN}建议：继续用「DM开发辅助」做日常回归；仅在打包相关任务（ID=1/2/7）完成后再做 dmg/exe 冒烟。${NC}"
else
  fail "冒烟测试失败（失败项数量：$FAILED）"
  echo -e "${RED}建议：先查看后端日志输出，再逐项修复。${NC}"
  exit 1
fi

