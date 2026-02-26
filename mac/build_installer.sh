#!/bin/bash
# Whisper 배치 전사 도구 - Mac .pkg 설치파일 빌드 스크립트
#
# 사용법 (Mac에서 실행):
#   chmod +x build_installer.sh
#   ./build_installer.sh
#
# 결과물: WhisperBatchTool.pkg

set -e

APP_NAME="WhisperBatchTool"
VERSION="1.0.0"
IDENTIFIER="com.whisper.batchtool"
INSTALL_LOCATION="/Applications/WhisperBatchTool"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "============================================================"
echo " 📦 Whisper 배치 전사 도구 - Mac 설치파일 빌드"
echo "============================================================"
echo ""

# ── 1. 빌드 디렉토리 준비 ──
BUILD_DIR="$SCRIPT_DIR/build_pkg"
PAYLOAD_DIR="$BUILD_DIR/payload"
SCRIPTS_DIR="$BUILD_DIR/scripts"
OUTPUT_DIR="$SCRIPT_DIR/installer_output"

rm -rf "$BUILD_DIR"
mkdir -p "$PAYLOAD_DIR"
mkdir -p "$SCRIPTS_DIR"
mkdir -p "$OUTPUT_DIR"

echo "[1/3] 파일 준비 중..."

# 앱 파일 복사
cp batch_whisper_transcriber.py "$PAYLOAD_DIR/"
cp requirements.txt "$PAYLOAD_DIR/"
cp install.sh "$PAYLOAD_DIR/"
cp run.sh "$PAYLOAD_DIR/"
cp README.md "$PAYLOAD_DIR/"

chmod +x "$PAYLOAD_DIR/install.sh"
chmod +x "$PAYLOAD_DIR/run.sh"

# ── 2. 설치 후 실행 스크립트 ──
cat > "$SCRIPTS_DIR/postinstall" << 'POSTINSTALL'
#!/bin/bash
# 설치 후 자동 실행

INSTALL_DIR="/Applications/WhisperBatchTool"
cd "$INSTALL_DIR"

# 실행 권한 부여
chmod +x install.sh run.sh

# 실제 사용자 홈 디렉토리 찾기 (root가 아닌 실제 로그인 사용자)
if [ -n "$SUDO_USER" ]; then
    REAL_HOME=$(eval echo ~$SUDO_USER)
elif [ -n "$USER" ] && [ "$USER" != "root" ]; then
    REAL_HOME="$HOME"
else
    REAL_HOME=$(eval echo ~$(logname 2>/dev/null || echo $USER))
fi

DESKTOP="$REAL_HOME/Desktop"

# 바탕화면에 실행 바로가기 생성
if [ -d "$DESKTOP" ]; then
    cat > "$DESKTOP/Whisper 전사 도구.command" << SHORTCUT
#!/bin/bash
cd "/Applications/WhisperBatchTool"
./run.sh
SHORTCUT
    chmod +x "$DESKTOP/Whisper 전사 도구.command"
fi

# 터미널에서 환경 설치 실행
REAL_USER="${SUDO_USER:-$(logname 2>/dev/null || echo $USER)}"
sudo -u "$REAL_USER" osascript -e "tell application \"Terminal\" to do script \"cd /Applications/WhisperBatchTool && ./install.sh\""

exit 0
POSTINSTALL
chmod +x "$SCRIPTS_DIR/postinstall"

# ── 3. .pkg 빌드 ──
echo "[2/3] .pkg 빌드 중..."

pkgbuild \
    --root "$PAYLOAD_DIR" \
    --identifier "$IDENTIFIER" \
    --version "$VERSION" \
    --install-location "$INSTALL_LOCATION" \
    --scripts "$SCRIPTS_DIR" \
    "$OUTPUT_DIR/${APP_NAME}_${VERSION}.pkg"

echo "[3/3] 정리 중..."
rm -rf "$BUILD_DIR"

echo ""
echo "============================================================"
echo " ✅ 빌드 완료!"
echo "============================================================"
echo ""
echo " 📦 설치파일: $OUTPUT_DIR/${APP_NAME}_${VERSION}.pkg"
echo ""
echo " 이 .pkg 파일을 GitHub Releases에 업로드하세요."
echo " 사용자가 다운로드하여 더블클릭하면 설치됩니다."
echo "============================================================"
