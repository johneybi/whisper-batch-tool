#!/bin/bash
# Whisper 배치 전사 도구 - Mac 실행 스크립트

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# 가상환경 확인
if [ ! -d "venv" ]; then
    echo "❌ 가상환경이 없습니다. 먼저 설치를 실행하세요:"
    echo "   ./install.sh"
    exit 1
fi

# 가상환경 활성화 후 실행
source venv/bin/activate
python3 batch_whisper_transcriber.py
