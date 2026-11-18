#!/usr/bin/env bash
# 前端 ESM 语法检查 + 复测页渲染冒烟（需要 node）
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/../../frontend"
for f in $(find src -name '*.js'); do node --input-type=module --check < "$f"; done
echo "frontend syntax OK"
node "$SCRIPT_DIR/smoke-speed-page.mjs"
