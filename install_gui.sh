#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

echo "============================================================"
echo " Whisper Batch Transcriber GUI - macOS installer"
echo "============================================================"
echo

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 was not found. Install it from https://www.python.org/downloads/ or Homebrew."
  exit 1
fi

if [ ! -x "venv/bin/python" ]; then
  python3 -m venv venv
fi

source "venv/bin/activate"
python -m pip install --upgrade pip
pip install torch torchvision torchaudio
pip install -r requirements.txt

echo
echo "Installation complete."
echo "Run ./run_gui.sh to start the app."
