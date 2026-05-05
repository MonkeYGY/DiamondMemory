#!/bin/bash

# ==========================================
# 项目完整备份脚本（写入项目根目录/项目备份）
#
# 设计目标：
# - 一键生成“完整项目备份”
# - 默认排除可再生/体积巨大的目录（node_modules、dist、venv 等）
# - 自动保留最近 10 个备份
# ==========================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
BACKUP_DIR="${PROJECT_DIR}/项目备份"

mkdir -p "$BACKUP_DIR"

timestamp="$(date -u '+%Y-%m-%dT%H-%M-%SZ')"
archive_name="Project-backup-${timestamp}.zip"
archive_path="${BACKUP_DIR}/${archive_name}"

cd "$PROJECT_DIR"

# 说明：
# - 这里用 zip 而不是 tar.gz：跨平台双击更友好；同时便于 Windows 用户解压
# - 排除规则尽量覆盖大目录，但不影响源码与配置可追溯
zip -r "$archive_path" . \
  -x ".git/*" \
  -x "**/.git/*" \
  -x "frontend/node_modules/*" \
  -x "frontend/dist/*" \
  -x "frontend/.vite/*" \
  -x "backend/venv/*" \
  -x "backend/__pycache__/*" \
  -x "**/__pycache__/*" \
  -x "**/*.pyc" \
  -x "dist/*" \
  -x ".nuitka/*" \
  -x "**/.DS_Store" \
  -x "data/qdrant_storage/*" \
  -x "data/*.db*" \
  -x "data/faiss_*" \
  -x "data/embedding_*" \
  >/dev/null

echo "✅ 项目备份已生成：${archive_path}"

# 仅保留最近 10 个
count="$(ls -1 "${BACKUP_DIR}"/Project-backup-*.zip 2>/dev/null | wc -l | tr -d ' ')"
if [ "${count}" -gt 10 ]; then
  echo "🧹 备份数量 ${count} > 10，开始清理旧备份..."
  ls -1t "${BACKUP_DIR}"/Project-backup-*.zip | tail -n +11 | xargs rm -f
  echo "✅ 清理完成（已保留最近 10 个）"
fi

