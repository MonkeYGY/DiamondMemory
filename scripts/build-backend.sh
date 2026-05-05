#!/bin/bash
# 钻石记忆系统后端编译脚本 - Mac/Linux
# 使用Nuitka将Python后端编译为机器码

set -e

# 修复在 Mac 桌面端 App 内部运行 Shell 时环境变量缺失的问题
export NVM_DIR="$HOME/.nvm"
export PATH="$HOME/.hermes/hermes-agent/.venv/bin:/opt/homebrew/bin:/opt/homebrew/sbin:/usr/local/bin:/usr/local/sbin:$HOME/.local/bin:$HOME/.npm-global/bin:$PATH"
if [ -d "$NVM_DIR/versions/node" ]; then
    export PATH="$(find "$NVM_DIR/versions/node" -maxdepth 2 -type d -name bin | head -n 1):$PATH"
fi
# 不要 source .zshrc，里面可能有 bash 不兼容的语法，导致 set -e 下直接退出
source ~/.bash_profile 2>/dev/null || true

echo "🔨 开始编译Python后端..."

# 切换到项目根目录
cd "$(dirname "$0")/.."

# 检查Nuitka是否安装
if ! pip show nuitka > /dev/null 2>&1; then
    echo "📦 安装Nuitka..."
    pip install nuitka
fi

# 清理旧输出
echo "🧹 清理旧编译文件..."
rm -rf dist/backend

# 编译后端
echo "⚙️ Nuitka编译中（这可能需要几分钟）..."
python3 -m nuitka \
    --standalone \
    --output-dir=dist/backend \
    --include-package=fastapi \
    --include-package=uvicorn \
    --include-package=pydantic \
    --include-package=pydantic_settings \
    --include-package=faiss \
    --include-package=numpy \
    --include-module=main \
    --include-module=app \
    --include-data-dir=backend/app=./app \
    --include-data-dir=backend/data=./data \
    --output-filename=DiamondMemoryBackend \
    --assume-yes-for-downloads \
    --remove-output \
    backend/main.py

echo ""
echo "✅ 后端编译完成！"
echo "📁 输出位置: dist/backend/"
ls -lh dist/backend/
