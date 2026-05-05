#!/bin/bash

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

DM_BACKEND_MODE="${DM_BACKEND_MODE:-electron}" # electron | python
if [[ "$DM_BACKEND_MODE" != "electron" && "$DM_BACKEND_MODE" != "python" ]]; then
    echo -e "${RED}✗ DM_BACKEND_MODE 仅支持 electron 或 python，当前: ${DM_BACKEND_MODE}${NC}"
    exit 1
fi

echo -e "${YELLOW}🚀 正在启动开发模式 (DM_BACKEND_MODE=${DM_BACKEND_MODE})...${NC}"

# 标记：用于“一键清除”可靠关闭开发模式打开的 Terminal 窗口
DM_DEV_MARK="__DM_DEV_MODE_DIAMONDMEMORY__"

# 获取项目根目录 (上级目录)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# 1. 打开 IDE (Trae/Cursor/VSCode)
if command -v trae &> /dev/null; then
    echo -e "${GREEN}✓ 使用 Trae 打开项目${NC}"
    trae "$PROJECT_DIR"
elif command -v cursor &> /dev/null; then
    echo -e "${GREEN}✓ 使用 Cursor 打开项目${NC}"
    cursor "$PROJECT_DIR"
elif command -v code &> /dev/null; then
    echo -e "${GREEN}✓ 使用 VS Code 打开项目${NC}"
    code "$PROJECT_DIR"
else
    echo -e "${YELLOW}未检测到 Trae/Cursor/VS Code 命令行工具，尝试通过系统默认应用打开...${NC}"
    open "$PROJECT_DIR"
fi

# 2. 启动前端 Electron 服务 (跨平台新架构)
if [ -d "$PROJECT_DIR/frontend" ]; then
    echo -e "${GREEN}✓ 准备启动 Electron 跨平台前端...${NC}"
    # 关键约束：开发模式只允许一个后端权威来源，避免出现“双后端/双端口/双数据源”导致数据对不上。
    # - DM_BACKEND_MODE=electron（默认）：仅使用 Electron 主进程 BackendManager 拉起并管理后端（推荐）
    # - DM_BACKEND_MODE=python：由本脚本单独启动源码后端（15920），同时 Electron 禁止自启动后端（仅连接现有后端）
    if [[ "$DM_BACKEND_MODE" == "python" ]]; then
        osascript -e "tell application \"Terminal\" to do script \"printf '\\\\033]0;DM Dev Frontend\\\\007'; echo '$DM_DEV_MARK FRONTEND'; cd \\\"$PROJECT_DIR/frontend\\\" && DM_BACKEND_MODE=python DM_BACKEND_PORT=15920 npm run electron:dev\""
    else
        osascript -e "tell application \"Terminal\" to do script \"printf '\\\\033]0;DM Dev Frontend\\\\007'; echo '$DM_DEV_MARK FRONTEND'; cd \\\"$PROJECT_DIR/frontend\\\" && DM_BACKEND_MODE=electron npm run electron:dev\""
    fi
    echo -e "${GREEN}✓ 已调起新终端运行前端应用${NC}"
else
    echo -e "${YELLOW}未找到 frontend 目录，跳过前端启动。${NC}"
fi

# 3. 启动后端服务 (FastAPI) —— 仅在 DM_BACKEND_MODE=python 时启用
if [[ "$DM_BACKEND_MODE" != "python" ]]; then
    echo -e "${GREEN}✓ 后端由 Electron 管理（本脚本不再额外启动 FastAPI，避免双后端）${NC}"
    echo -e "\n${YELLOW}✅ 跨平台开发模式已就绪！${NC}"
    exit 0
fi

if ! command -v python3 >/dev/null 2>&1; then
    echo -e "${RED}✗ 未找到 python3，无法启动后端。请先安装 Python 3。${NC}"
    exit 1
fi

check_backend_health() {
    local port="$1"
    local response
    response=$(curl -fsS --max-time 2 "http://127.0.0.1:${port}/health" 2>/dev/null || true)
    [[ "$response" == *'"service":"diamond_memory_backend"'* || "$response" == *'"service": "diamond_memory_backend"'* ]]
}

PID_15920=$(lsof -ti:15920 2>/dev/null | head -n 1)
if check_backend_health 15920; then
    echo -e "${GREEN}✓ 后端服务 (15920端口) 已经在运行中 (PID: ${PID_15920:-unknown})${NC}"
elif [ -n "$PID_15920" ]; then
    echo -e "${RED}✗ 15920 端口已被其他进程占用，且不是 DiamondMemory 后端 (PID: $PID_15920)${NC}"
    echo -e "${YELLOW}请先释放 15920 端口，再重新点击“开发模式”。${NC}"
    exit 1
else
    echo -e "${GREEN}✓ 准备启动 FastAPI 后端服务...${NC}"
    BACKEND_LAUNCH_CMD=$(python3 "$SCRIPT_DIR/backend_bootstrap.py" --backend-dir "$PROJECT_DIR/backend" --installer-python "$(command -v python3)")
    if [ $? -ne 0 ] || [ -z "$BACKEND_LAUNCH_CMD" ]; then
        echo -e "${RED}✗ 后端环境准备失败，请检查上方日志。${NC}"
        exit 1
    fi
    osascript -e "tell application \"Terminal\" to do script \"printf '\\\\033]0;DM Dev Backend\\\\007'; echo '$DM_DEV_MARK BACKEND'; $BACKEND_LAUNCH_CMD\""
    echo -e "${GREEN}✓ 已调起新终端运行后端服务${NC}"
fi

echo -e "\n${YELLOW}✅ 跨平台开发模式已就绪！${NC}"
