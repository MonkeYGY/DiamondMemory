#!/bin/bash

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}正在尝试清理 DiamondMemory 相关后台服务进程...${NC}\n"

# ==========================================
# 1. 清理 Electron 主应用进程
# ==========================================
echo -e "${YELLOW}[1/6] 检查并清理 Electron 主应用进程...${NC}"
ELECTRON_PIDS=$(pgrep -f "DiamondMemory|Diamond Memory" 2>/dev/null)
if [ -n "$ELECTRON_PIDS" ]; then
    echo -e "${RED}发现 Electron 主应用进程: ${ELECTRON_PIDS}${NC}"
    for pid in $ELECTRON_PIDS; do
        kill -9 "$pid" 2>/dev/null
    done
    echo -e "${GREEN}✓ 已强行终止 Electron 主应用进程${NC}"
else
    echo -e "${GREEN}✓ 未发现 Electron 主应用进程${NC}"
fi

echo "----------------------------------------"

# ==========================================
# 2. 清理 15920 端口及 Backend 相关进程
# ==========================================
echo -e "${YELLOW}[2/6] 检查并清理 Backend API 服务（端口 15920 及动态端口）...${NC}"

PID_15920=$(lsof -ti:15920 2>/dev/null)
if [ -n "$PID_15920" ]; then
    echo -e "${RED}发现 15920 端口被以下进程占用: ${PID_15920}${NC}"
    kill -9 $PID_15920 2>/dev/null
    echo -e "${GREEN}✓ 已强行终止 15920 端口进程${NC}"
else
    echo -e "${GREEN}✓ 15920 端口目前空闲${NC}"
fi

# 清理所有 uvicorn / python 相关后端进程
BACKEND_PIDS=$(pgrep -f "DiamondMemoryBackend|uvicorn|python.*main\.py|python3.*main\.py" 2>/dev/null)
if [ -n "$BACKEND_PIDS" ]; then
    echo -e "${RED}发现后端进程残留: ${BACKEND_PIDS}${NC}"
    for pid in $BACKEND_PIDS; do
        kill -9 "$pid" 2>/dev/null
    done
    echo -e "${GREEN}✓ 已强行终止所有 Backend 进程${NC}"
else
    echo -e "${GREEN}✓ 未发现 Backend 进程残留${NC}"
fi

echo "----------------------------------------"

# ==========================================
# 3. 清理 11434 端口及 Ollama 主服务
# ==========================================
echo -e "${YELLOW}[3/6] 检查并清理 11434 端口 (Ollama 服务)...${NC}"

PID_11434=$(lsof -ti:11434 2>/dev/null)
if [ -n "$PID_11434" ]; then
    echo -e "${RED}发现 11434 端口被以下进程占用: ${PID_11434}${NC}"
    kill -9 $PID_11434 2>/dev/null
    echo -e "${GREEN}✓ 已强行终止 Ollama 主服务进程 ${PID_11434}${NC}"
else
    echo -e "${GREEN}✓ 11434 端口目前空闲${NC}"
fi

echo "----------------------------------------"

# ==========================================
# 4. 清理 Ollama Runner 子进程（极其消耗内存）
# ==========================================
echo -e "${YELLOW}[4/6] 扫描并清理残留的模型 Runner 进程...${NC}"

# 清理 ollama runner 进程
RUNNER_PIDS=$(pgrep -f "ollama.*runner" 2>/dev/null)
if [ -n "$RUNNER_PIDS" ]; then
    echo -e "${RED}发现模型 Runner 进程残留: ${RUNNER_PIDS}${NC}"
    for pid in $RUNNER_PIDS; do
        kill -9 "$pid" 2>/dev/null
    done
    echo -e "${GREEN}✓ 已彻底清理所有模型 Runner 进程${NC}"
else
    echo -e "${GREEN}✓ 未发现残留的模型 Runner 进程${NC}"
fi

# 清理可能残留的 ollama 子进程（更广泛的匹配）
OLLAMA_CHILD_PIDS=$(pgrep -f "ollama" 2>/dev/null)
if [ -n "$OLLAMA_CHILD_PIDS" ]; then
    echo -e "${RED}发现额外 Ollama 相关进程: ${OLLAMA_CHILD_PIDS}${NC}"
    for pid in $OLLAMA_CHILD_PIDS; do
        kill -9 "$pid" 2>/dev/null
    done
    echo -e "${GREEN}✓ 已清理额外 Ollama 相关进程${NC}"
fi

echo "----------------------------------------"

# ==========================================
# 5. 清理可能残留的 Node.js 子进程
# ==========================================
echo -e "${YELLOW}[5/6] 扫描并清理残留的 Node.js 子进程...${NC}"

# 清理可能与 Electron 相关的残留 node 进程
NODE_PIDS=$(ps aux 2>/dev/null | grep -i "diamond.*memory\|DiamondMemory" | grep -v grep | awk '{print $2}')
if [ -n "$NODE_PIDS" ]; then
    echo -e "${RED}发现残留 Node.js 相关进程: ${NODE_PIDS}${NC}"
    for pid in $NODE_PIDS; do
        kill -9 "$pid" 2>/dev/null
    done
    echo -e "${GREEN}✓ 已清理残留 Node.js 进程${NC}"
else
    echo -e "${GREEN}✓ 未发现残留 Node.js 进程${NC}"
fi

echo "----------------------------------------"

# ==========================================
# 6. 关闭开发模式打开的终端窗口
# ==========================================
echo -e "${YELLOW}[6/6] 检查并关闭开发模式打开的终端窗口...${NC}"

CLOSED_COUNT=0

# 说明：
# - 旧实现用逗号拼接 windowList，但 Terminal 输出内容可能含逗号，导致解析失败，进而无法自动关闭。
# - 新实现使用换行分隔；并优先通过 open_dev_mode.sh 写入的唯一标记来识别“开发模式窗口”。
DM_DEV_MARK="__DM_DEV_MODE_DIAMONDMEMORY__"

TERMINAL_WINDOWS=$(osascript -e '
tell application "Terminal"
    set windowList to {}
    repeat with w in windows
        try
            set cmdText to contents of selected tab of w
        on error
            set cmdText to ""
        end try
        set winId to id of w
        set end of windowList to (winId as text) & "|" & cmdText
    end repeat
    set AppleScript''s text item delimiters to linefeed
    return windowList as text
end tell
' 2>/dev/null)

if [ -n "$TERMINAL_WINDOWS" ]; then
    while IFS= read -r winInfo; do
        [ -z "$winInfo" ] && continue
        WIN_ID=$(echo "$winInfo" | cut -d'|' -f1 | xargs)
        WIN_CMD=$(echo "$winInfo" | cut -d'|' -f2-)

        # 优先：通过唯一标记识别由“开发模式”打开的窗口（最稳定）
        SHOULD_CLOSE=false
        if echo "$WIN_CMD" | grep -q "$DM_DEV_MARK" 2>/dev/null; then
            SHOULD_CLOSE=true
        # 兼容兜底：若标记缺失，再尝试匹配常见关键字（不保证 100%）
        elif echo "$WIN_CMD" | grep -q "uvicorn\|electron:dev\|DiamondMemoryBackend" 2>/dev/null; then
            SHOULD_CLOSE=true
        fi

        if [ "$SHOULD_CLOSE" = true ]; then
            osascript -e "tell application \"Terminal\" to close window id $WIN_ID saving no" 2>/dev/null
            if [ $? -eq 0 ]; then
                CLOSED_COUNT=$((CLOSED_COUNT + 1))
                echo -e "${GREEN}✓ 已关闭终端窗口 (ID: $WIN_ID)${NC}"
            else
                echo -e "${YELLOW}⚠ 关闭终端窗口失败 (ID: $WIN_ID)${NC}"
            fi
        fi
    done <<< "$TERMINAL_WINDOWS"
fi

if [ "$CLOSED_COUNT" -eq 0 ]; then
    echo -e "${GREEN}✓ 未发现开发模式打开的终端窗口${NC}"
else
    echo -e "${GREEN}✓ 共关闭 ${CLOSED_COUNT} 个开发模式终端窗口${NC}"
fi

echo "----------------------------------------"

# ==========================================
# 最终确认
# ==========================================
echo ""
echo -e "${YELLOW}=== 清理结果确认 ===${NC}"

REMAINING_15920=$(lsof -ti:15920 2>/dev/null)
REMAINING_11434=$(lsof -ti:11434 2>/dev/null)
REMAINING_BACKEND=$(pgrep -f "DiamondMemory|uvicorn|python.*main\.py" 2>/dev/null)
REMAINING_OLLAMA=$(pgrep -f "ollama" 2>/dev/null)

if [ -z "$REMAINING_15920" ] && [ -z "$REMAINING_11434" ] && [ -z "$REMAINING_BACKEND" ] && [ -z "$REMAINING_OLLAMA" ]; then
    echo -e "${GREEN}✓ 所有 DiamondMemory 相关进程已彻底清理！${NC}"
    echo -e "${GREEN}  - 15920 端口: 空闲${NC}"
    echo -e "${GREEN}  - 11434 端口: 空闲${NC}"
    echo -e "${GREEN}  - 无残留进程${NC}"
else
    echo -e "${RED}⚠ 仍有部分进程残留:${NC}"
    [ -n "$REMAINING_15920" ] && echo -e "${RED}  - 15920 端口进程: ${REMAINING_15920}${NC}"
    [ -n "$REMAINING_11434" ] && echo -e "${RED}  - 11434 端口进程: ${REMAINING_11434}${NC}"
    [ -n "$REMAINING_BACKEND" ] && echo -e "${RED}  - 后端进程: ${REMAINING_BACKEND}${NC}"
    [ -n "$REMAINING_OLLAMA" ] && echo -e "${RED}  - Ollama 进程: ${REMAINING_OLLAMA}${NC}"
    echo -e "${YELLOW}建议再次执行清除操作${NC}"
fi

echo -e "\n${YELLOW}所有 DiamondMemory 相关后台服务清理完毕。${NC}"
