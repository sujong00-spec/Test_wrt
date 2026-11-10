#!/usr/bin/env bash
# 小学生默写助手：在 Linux / macOS 上启动服务（Windows 用 start.bat）
set -e
cd "$(dirname "$0")"
exec python3 server.py "$@"