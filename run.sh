#!/usr/bin/env bash
# 猫况 CatCheck 一键启动
set -e
cd "$(dirname "$0")"
PY=${PYTHON:-python3}
if ! command -v "$PY" >/dev/null 2>&1; then
  echo "找不到 python3，请先安装 Python 3.9+"
  exit 1
fi
exec "$PY" server.py --open "$@"
