#!/bin/bash

# macOS DMG “干净机”冒烟测试入口
# 用法：bash scripts/smoke/smoke_mac_dmg.sh /path/to/xxx.dmg

set -euo pipefail

DMG_PATH="${1:-}"
if [ -z "${DMG_PATH}" ] || [ ! -f "${DMG_PATH}" ]; then
  echo "❌ 请输入有效 DMG 路径"
  echo "用法：bash scripts/smoke/smoke_mac_dmg.sh /path/to/xxx.dmg"
  exit 2
fi

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SMOKE_NODE_SCRIPT="${PROJECT_DIR}/scripts/smoke/smoke_app.mjs"

MOUNT_DIR="$(mktemp -d "/tmp/dm_dmg_mount.XXXXXX")"
WORK_DIR="$(mktemp -d "/tmp/dm_smoke_app.XXXXXX")"

cleanup() {
  set +e
  if mount | grep -q "${MOUNT_DIR}"; then
    hdiutil detach "${MOUNT_DIR}" -force >/dev/null 2>&1
  fi
  rm -rf "${MOUNT_DIR}" "${WORK_DIR}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "📦 挂载 DMG: ${DMG_PATH}"
hdiutil attach -nobrowse -noverify -noautoopen "${DMG_PATH}" -mountpoint "${MOUNT_DIR}" >/dev/null

APP_PATH="$(find "${MOUNT_DIR}" -maxdepth 2 -name "*.app" -print -quit)"
if [ -z "${APP_PATH}" ]; then
  echo "❌ 未在 DMG 中找到 .app"
  exit 1
fi

echo "📥 复制 .app 到临时目录（模拟安装）"
cp -R "${APP_PATH}" "${WORK_DIR}/"

COPIED_APP="$(find "${WORK_DIR}" -maxdepth 2 -name "*.app" -print -quit)"
if [ -z "${COPIED_APP}" ]; then
  echo "❌ 复制后未找到 .app"
  exit 1
fi

echo "🚦 运行冒烟测试..."
node "${SMOKE_NODE_SCRIPT}" --app "${COPIED_APP}"

echo "✅ macOS DMG 冒烟测试完成"

