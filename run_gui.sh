#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if [ ! -x "venv/bin/python" ]; then
  echo "Virtual environment not found. Run ./install_gui.sh first."
  exit 1
fi

exec "venv/bin/python" whisper_gui.py
