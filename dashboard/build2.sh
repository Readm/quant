#!/bin/bash
# build2.sh — 安装依赖 + 构建 Dashboard（在 WSL 中运行）
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"
npm install @types/node --save-dev 2>&1
npm run build 2>&1
echo "BUILD_DONE:exit_code=$?"
