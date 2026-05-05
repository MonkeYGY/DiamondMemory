#!/bin/bash

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${YELLOW}开始检查 DiamondMemory 核心服务状态...${NC}\n"

check_backend_health() {
    local port="$1"
    local response
    response=$(curl -fsS --max-time 2 "http://127.0.0.1:${port}/health" 2>/dev/null || true)
    [[ "$response" == *'"service":"diamond_memory_backend"'* || "$response" == *'"service": "diamond_memory_backend"'* ]]
}

# 检查 DiamondMemory 后端 API 服务
echo -e "${YELLOW}检查 DiamondMemory 后端 API 服务:${NC}"

# 优先检测固定 15920 端口（开发脚本 uvicorn 启动）
BACKEND_PID=""
BACKEND_PORT=""

PID_15920=$(lsof -ti:15920 2>/dev/null)
if [ -n "$PID_15920" ]; then
    PID_15920=$(echo "$PID_15920" | head -n 1)
    if check_backend_health 15920; then
        BACKEND_PID="$PID_15920"
        BACKEND_PORT="15920"
    else
        echo -e "${YELLOW}! 15920 端口已被占用，但不是 DiamondMemory 后端 (PID: $PID_15920)${NC}"
    fi
fi

# 如果 15920 没有，则通过进程名匹配查找动态端口（Electron 启动）
if [ -z "$BACKEND_PID" ]; then
    BACKEND_PID=$(pgrep -f "DiamondMemoryBackend" 2>/dev/null)
    if [ -z "$BACKEND_PID" ]; then
        BACKEND_PID=$(pgrep -f "uvicorn.*main:app" 2>/dev/null)
    fi
    if [ -z "$BACKEND_PID" ]; then
        BACKEND_PID=$(pgrep -f "python.*main.py.*--port" 2>/dev/null)
    fi

    if [ -n "$BACKEND_PID" ]; then
        BACKEND_PID=$(echo "$BACKEND_PID" | head -n 1)
        BACKEND_PORT=$(lsof -Pan -p "$BACKEND_PID" -iTCP -sTCP:LISTEN 2>/dev/null | grep LISTEN | awk -F':' '{print $NF}' | awk '{print $1}' | head -n 1)
    fi
fi

if [ -n "$BACKEND_PID" ]; then
    echo -e "${GREEN}✓ 服务正在运行${NC}"
    if [ -n "$BACKEND_PORT" ]; then
        echo -e "${GREEN}✓ 监听端口: $BACKEND_PORT${NC}"
    fi
    echo "进程信息:"
    ps -p "$BACKEND_PID" -o pid=,user=,%cpu=,%mem=,command= 2>/dev/null | awk '{print "\033[0;32m"$0"\033[0m"}'
else
    echo -e "${RED}✗ 未检测到后端 API 服务运行${NC}"
fi
echo "----------------------------------------"

# 检查 11434 端口 (Ollama 服务)
echo -e "${YELLOW}检查 11434 端口 (Ollama 模型服务):${NC}"
PID_11434=$(lsof -ti:11434 2>/dev/null | head -n 1)
if [ -n "$PID_11434" ]; then
    echo -e "${GREEN}✓ 服务正在运行${NC}"
    echo "进程信息:"
    ps -p "$PID_11434" -o pid=,user=,%cpu=,%mem=,command= | awk '{print "\033[0;32m"$0"\033[0m"}'
    
    # 额外检查 ollama runner 进程
    echo -e "\n${YELLOW}相关 Runner 进程:${NC}"
    RUNNER_PIDS=$(pgrep -f "ollama.*runner" 2>/dev/null)
    if [ -n "$RUNNER_PIDS" ]; then
        while IFS= read -r pid; do
            ps -p "$pid" -o pid=,user=,%cpu=,%mem=,command= 2>/dev/null | awk '{print "\033[0;32m"$0"\033[0m"}'
        done <<< "$RUNNER_PIDS"
    else
        echo "未检测到活跃的模型 runner 进程"
    fi
else
    echo -e "${RED}✗ 未检测到服务运行在 11434 端口${NC}"
fi
echo -e "\n${YELLOW}检查完成。${NC}"
