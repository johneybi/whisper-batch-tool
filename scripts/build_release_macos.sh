#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

VERSION="1.1.3"
APP_NAME="WhisperBatchTranscriber"
VENV_DIR="${WHISPER_RELEASE_VENV:-.release-venv}"
RELEASE_DIR="release"
APP_PATH="dist/${APP_NAME}.app"
DMG_PATH="${RELEASE_DIR}/${APP_NAME}-${VERSION}-macOS.dmg"
ZIP_PATH="${RELEASE_DIR}/${APP_NAME}-${VERSION}-macOS.zip"

echo "WARNING: This builds the legacy Tk/PyInstaller app."
echo "WARNING: The official product target is the Electron app under desktop/."
echo "WARNING: Do not attach these artifacts to a new official GitHub Release unless it is explicitly marked as legacy."

mkdir -p "${RELEASE_DIR}"

if [ "${WHISPER_CLEAN_RELEASE_VENV:-0}" = "1" ] && [ -d "${VENV_DIR}" ]; then
  rm -rf "${VENV_DIR}"
fi

if [ ! -x "${VENV_DIR}/bin/python" ]; then
  python3 -m venv "${VENV_DIR}"
fi

"${VENV_DIR}/bin/python" -m pip install --upgrade pip
"${VENV_DIR}/bin/python" -m pip install torch
"${VENV_DIR}/bin/python" -m pip install -r requirements.txt pyinstaller
"${VENV_DIR}/bin/pyinstaller" --clean --noconfirm WhisperBatchTranscriber.spec

rm -f "${ZIP_PATH}"
ditto -c -k --sequesterRsrc --keepParent "${APP_PATH}" "${ZIP_PATH}"

rm -f "${DMG_PATH}"
hdiutil create -volname "Whisper Batch Transcriber" -srcfolder "${APP_PATH}" -ov -format UDZO "${DMG_PATH}"

echo "Release files are in: ${RELEASE_DIR}"
