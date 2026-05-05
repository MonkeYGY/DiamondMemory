#!/bin/bash
# 钻石记忆系统 - macOS 彻底卸载脚本
# 该脚本将删除应用程序及所有相关的用户数据、配置和模型文件

echo "⚠️ 警告：这将彻底删除钻石记忆系统及所有记忆数据、大模型文件！"
echo "操作不可逆！如果需要保留数据，请按 Ctrl+C 取消。"
read -p "确认要彻底卸载吗？(y/N): " confirm

if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
    echo "已取消卸载。"
    exit 0
fi

echo "正在关闭可能运行中的进程..."
pkill -9 -f "DiamondMemory" 2>/dev/null || true
pkill -9 -f "DiamondMemoryBackend" 2>/dev/null || true
pkill -9 -f "ollama serve" 2>/dev/null || true

echo "正在删除应用程序..."
rm -rf "/Applications/DiamondMemory.app"
rm -rf "/Applications/钻石记忆系统.app"

echo "正在删除用户数据和配置文件..."
# Electron 默认 userData 路径
rm -rf "$HOME/Library/Application Support/DiamondMemory"
rm -rf "$HOME/Library/Application Support/钻石记忆系统"

# 缓存和状态文件
rm -rf "$HOME/Library/Caches/com.diamondmemory.app"
rm -rf "$HOME/Library/Caches/com.diamondmemory.app.ShipIt"
rm -rf "$HOME/Library/Preferences/com.diamondmemory.app.plist"
rm -rf "$HOME/Library/Saved Application State/com.diamondmemory.app.savedState"

# 旧版本或备用存储目录
rm -rf "$HOME/.diamondmemory"
rm -rf "$HOME/.diamond-memory"

echo "✅ 钻石记忆系统已彻底卸载完毕！"
