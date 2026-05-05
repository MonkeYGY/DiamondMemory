#!/bin/bash

# ==========================================
# DiamondMemory Electron DMG 打包脚本
# ==========================================

set -e

export NVM_DIR="$HOME/.nvm"
export PATH="$HOME/.hermes/hermes-agent/.venv/bin:/opt/homebrew/bin:/opt/homebrew/sbin:/usr/local/bin:/usr/local/sbin:$HOME/.local/bin:$HOME/.npm-global/bin:$PATH"
if [ -d "$NVM_DIR/versions/node" ]; then
    export PATH="$(find "$NVM_DIR/versions/node" -maxdepth 2 -type d -name bin | head -n 1):$PATH"
fi
export ELECTRON_MIRROR="https://npmmirror.com/mirrors/electron/"
source ~/.bash_profile 2>/dev/null || true

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
FRONTEND_DIR="${PROJECT_DIR}/frontend"

echo "🚀 开始打包 DiamondMemory (Electron + Vue3) ..."

# 1. 下载 Ollama 二进制
echo "📦 0/4 正在准备 Ollama 二进制..."
cd "${PROJECT_DIR}"
bash scripts/download-ollama-mac.sh

# 2. 编译后端二进制 (Nuitka)
BACKEND_BINARY="${PROJECT_DIR}/dist/backend/DiamondMemoryBackend"
BACKEND_SRC_DIR="${PROJECT_DIR}/backend"

if [ -f "${BACKEND_BINARY}" ]; then
    CHANGED_FILES=$(find "${BACKEND_SRC_DIR}" -name "*.py" -newer "${BACKEND_BINARY}" 2>/dev/null | wc -l | tr -d ' ')
    if [ "${CHANGED_FILES}" -gt 0 ]; then
        echo "🔨 1/4 检测到 ${CHANGED_FILES} 个后端源码有改动，正在重新编译 (Nuitka)..."
        cd "${PROJECT_DIR}"
        bash scripts/build-backend.sh
    else
        echo "⚡ 1/4 后端源码无改动，跳过 Nuitka 编译（节省 5-15 分钟）"
        echo "   编译产物时间: $(stat -f '%Sm' "${BACKEND_BINARY}")"
    fi
else
    echo "🔨 1/4 首次编译 Python 后端 (Nuitka)..."
    cd "${PROJECT_DIR}"
    bash scripts/build-backend.sh
fi

# 3. 安装前端依赖并打包
echo "🔨 2/4 正在编译前端代码并打包 Electron 应用..."
cd "${FRONTEND_DIR}"
npm install

sed -i '' 's/- target: dir/- target: dmg/' electron-builder.yml

npm run electron:build-all

# 4. 复制生成的 DMG 到桌面
echo "📦 3/4 正在将 DMG 复制到桌面..."
DMG_FILE=$(ls ${FRONTEND_DIR}/dist/electron/*.dmg | head -n 1)
if [ -f "$DMG_FILE" ]; then
    # 可选：在 CI/干净机环境执行“装完即用”冒烟测试
    # 启用方式：RUN_SMOKE_TEST=1 bash DM开发辅助/create_dmg.sh
    if [ "${RUN_SMOKE_TEST:-0}" = "1" ]; then
        echo "🧪 3.5/4 RUN_SMOKE_TEST=1，开始执行 DMG 冒烟测试..."
        bash "${PROJECT_DIR}/scripts/smoke/smoke_mac_dmg.sh" "$DMG_FILE"
        echo "✅ DMG 冒烟测试通过"
    fi

    cp "$DMG_FILE" "$HOME/Desktop/"
    DMG_NAME=$(basename "$DMG_FILE")
    echo "✅ 打包完成！DMG 文件已保存到桌面: $HOME/Desktop/${DMG_NAME}"
else
    echo "❌ 错误: 未找到生成的 DMG 文件！"
    exit 1
fi

echo ""
echo "📋 打包内容说明："
echo "  ✅ Electron 前端 (Vue3 + TypeScript)"
echo "  ✅ Python 后端 (Nuitka 编译，无需安装 Python)"
echo "  ✅ Ollama 推理引擎 (内嵌，无需单独安装)"
echo "  ⚠️  大模型权重需在软件内手动下载"
echo ""
echo "🔄 使用流程："
echo "  1. 安装后启动软件"
echo "  2. 进入「模型管理」页面"
echo "  3. 点击下载推荐模型 (qwen3.5:4b + bge-m3)"
echo "  4. 下载完成后重启软件，模型自动常驻内存"
echo "  5. 或配置外部 API，保存后自动连接"
