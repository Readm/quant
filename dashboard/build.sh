#!/bin/bash
# build.sh — 构建 Dashboard（在 WSL 中运行）
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"
echo "=== Building Dashboard ==="
npm run build 2>&1
echo "BUILD_DONE:exit_code=$?"
