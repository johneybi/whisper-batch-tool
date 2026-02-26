#!/bin/bash
# Whisper 배치 전사 도구 - Mac 설치 스크립트

set -e

echo "============================================================"
echo " 🎬 Whisper 배치 전사 도구 - Mac 자동 설치"
echo "============================================================"
echo ""

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# ============================================================
# 1. Homebrew 확인
# ============================================================
echo "[1/5] Homebrew 확인 중..."
if ! command -v brew &> /dev/null; then
    echo ""
    echo "⚠️  Homebrew가 설치되어 있지 않습니다."
    echo "📥 설치하려면 아래 명령어를 터미널에 붙여넣으세요:"
    echo ""
    echo '   /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'
    echo ""
    echo "설치 후 이 스크립트를 다시 실행하세요."
    exit 1
fi
echo "✅ Homebrew 확인됨"

# ============================================================
# 2. Python 확인 / 설치
# ============================================================
echo ""
echo "[2/5] Python 확인 중..."
if ! command -v python3 &> /dev/null; then
    echo "🔄 Python3 설치 중..."
    brew install python3
fi
PYTHON_VER=$(python3 --version 2>&1)
echo "✅ $PYTHON_VER 확인됨"

# ============================================================
# 3. ffmpeg 확인 / 설치
# ============================================================
echo ""
echo "[3/5] ffmpeg 확인 중..."
if ! command -v ffmpeg &> /dev/null; then
    echo "🔄 ffmpeg 설치 중..."
    brew install ffmpeg
fi
echo "✅ ffmpeg 확인됨"

# ============================================================
# 4. PyTorch 옵션 선택 (Apple Silicon MPS / CPU)
# ============================================================
echo ""
echo "[4/5] PyTorch 설치 옵션 선택:"
echo ""

# Apple Silicon 감지
CHIP=$(uname -m)
if [ "$CHIP" = "arm64" ]; then
    echo "  🍎 Apple Silicon (M1/M2/M3/M4) 감지됨!"
    echo ""
    echo "  1: MPS 가속 버전 (Apple Silicon GPU 사용 — 추천)"
    echo "  2: CPU 전용 버전"
    echo ""
    read -p "선택 (기본 1): " TORCH_CHOICE
    TORCH_CHOICE=${TORCH_CHOICE:-1}
else
    echo "  💻 Intel Mac 감지됨 (CPU 버전으로 설치)"
    TORCH_CHOICE=2
fi

# ============================================================
# 5. 가상환경 + 패키지 설치
# ============================================================
echo ""
echo "[5/5] Python 가상환경 및 패키지 설치 중..."
echo "      (시간이 걸릴 수 있습니다)"
echo ""

# 가상환경 생성
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo "✅ 가상환경 생성 완료"
else
    echo "✅ 가상환경이 이미 존재합니다"
fi

# 활성화
source venv/bin/activate
pip install --upgrade pip > /dev/null 2>&1

# PyTorch 설치
if [ "$TORCH_CHOICE" = "1" ]; then
    echo "🍎 MPS 가속 버전 PyTorch 설치 중..."
    pip install torch torchvision torchaudio
else
    echo "💻 CPU 버전 PyTorch 설치 중..."
    pip install torch torchvision torchaudio
fi

# Whisper 설치
echo ""
echo "🎤 Whisper 및 기타 패키지 설치 중..."
pip install openai-whisper ffmpeg-python

# MPS 확인
if [ "$TORCH_CHOICE" = "1" ]; then
    echo ""
    echo "🔍 MPS 가속 확인 중..."
    python3 -c "import torch; print('MPS 사용 가능:', torch.backends.mps.is_available())"
fi

echo ""
echo "============================================================"
echo " ✅ 설치 완료!"
echo "============================================================"
echo ""
if [ "$TORCH_CHOICE" = "1" ]; then
    echo " 🍎 PyTorch: MPS 가속 버전 (Apple Silicon)"
else
    echo " 💻 PyTorch: CPU 버전"
fi
echo ""
echo " 사용법:"
echo "   1. run.sh를 실행하세요: ./run.sh"
echo "   2. 파일 선택 화면에서 MKV 또는 WAV 파일을 선택하세요"
echo "   3. 모델과 옵션을 선택하면 자동 전사됩니다"
echo ""
echo "============================================================"
