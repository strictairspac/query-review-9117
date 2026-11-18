#!/usr/bin/env bash
# 提速复测后端验证：纯标准库，无需数据库/Redis/第三方依赖
set -euo pipefail
cd "$(dirname "$0")/../../backend"
python3 -m unittest discover -s tests -v
