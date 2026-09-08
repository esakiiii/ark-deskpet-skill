#!/bin/sh
# Debug-mode launcher for macOS / Linux (prints stderr / crashes inline).
# Mirrors 调试运行.bat (Windows).

set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
PY="$DIR/.venv/bin/python"

if [ ! -x "$PY" ]; then
    echo "venv python not found at $PY"
    exit 1
fi

cd "$DIR"
exec "$PY" "$DIR/main.py"
