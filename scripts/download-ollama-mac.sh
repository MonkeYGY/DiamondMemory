#!/bin/bash
# 下载 Ollama 二进制到 build 目录 - Mac 版
# 在打包前运行，确保 Ollama 二进制文件存在

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
BUILD_DIR="${PROJECT_DIR}/build/ollama/mac"

echo "📦 准备 Ollama 二进制文件 (macOS)..."

mkdir -p "${BUILD_DIR}"

if [ -f "${BUILD_DIR}/ollama" ]; then
    echo "✅ Ollama 二进制已存在: ${BUILD_DIR}/ollama"
    exit 0
fi

echo "⬇️  正在下载 Ollama for macOS..."

OLLAMA_URL="https://ollama.com/download/ollama-darwin"
TEMP_FILE="${BUILD_DIR}/ollama.tmp"

curl -L -o "${TEMP_FILE}" "${OLLAMA_URL}" || {
    echo "❌ 下载 Ollama 失败！"
    echo "请手动下载 Ollama 并放置到: ${BUILD_DIR}/ollama"
    echo "下载地址: https://ollama.com/download/mac"
    rm -f "${TEMP_FILE}"
    exit 1
}

mv "${TEMP_FILE}" "${BUILD_DIR}/ollama"
chmod +x "${BUILD_DIR}/ollama"

echo "✅ Ollama 下载完成: ${BUILD_DIR}/ollama"
ls -lh "${BUILD_DIR}/ollama"
