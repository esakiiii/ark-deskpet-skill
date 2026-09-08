#!/bin/sh
# Launch the deskpet on macOS / Linux.
# Mirrors 启动桌宠.bat (Windows).

set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
PY="$DIR/.venv/bin/python"

if [ ! -x "$PY" ]; then
    echo "venv python not found at $PY"
    echo "Run setup_env.py first (or: python3 -m venv .venv && .venv/bin/pip install PySide6)"
    exit 1
fi

cd "$DIR"
exec "$PY" "$DIR/main.py"
