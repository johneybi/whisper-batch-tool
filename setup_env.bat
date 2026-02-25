@echo off
chcp 65001 >nul

REM ============================================================
REM Inno Setup 설치 후 자동 실행되는 환경 구성 스크립트
REM ============================================================

set "INSTALL_DIR=%~1"
if "%INSTALL_DIR%"=="" set "INSTALL_DIR=%~dp0"

cd /d "%INSTALL_DIR%"

REM ── Python 확인 ──
python --version >nul 2>&1
if %ERRORLEVEL% neq 0 (
    REM Python이 없으면 자동 다운로드 시도
    echo Python이 설치되어 있지 않습니다.
    echo Python 다운로드 페이지를 엽니다...
    start https://www.python.org/downloads/
    
    echo.
    echo ⚠️  Python 설치 후 install.bat을 직접 실행해주세요.
    exit /b 1
)

REM ── 가상환경 생성 ──
if not exist "venv\Scripts\activate.bat" (
    python -m venv venv
    if %ERRORLEVEL% neq 0 exit /b 1
)

REM ── 패키지 설치 (CPU 기본) ──
call venv\Scripts\activate.bat
pip install --upgrade pip >nul 2>&1
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu >nul 2>&1
pip install openai-whisper ffmpeg-python >nul 2>&1

exit /b 0
