@echo off
chcp 65001 >nul
title Whisper 배치 전사 도구 - 설치

echo ============================================================
echo  🎬 Whisper 배치 전사 도구 - 자동 설치
echo ============================================================
echo.

REM ============================================================
REM 1. Python 설치 여부 확인
REM ============================================================
echo [1/4] Python 설치 확인 중...
python --version >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo.
    echo ❌ Python이 설치되어 있지 않습니다!
    echo.
    echo 📥 아래 링크에서 Python을 설치해주세요:
    echo    https://www.python.org/downloads/
    echo.
    echo ⚠️  설치 시 반드시 "Add Python to PATH" 체크!
    echo.
    echo 설치 후 이 스크립트를 다시 실행하세요.
    echo ============================================================
    pause
    exit /b 1
)

for /f "tokens=*" %%i in ('python --version 2^>^&1') do set PYTHON_VER=%%i
echo ✅ %PYTHON_VER% 확인됨

REM ============================================================
REM 2. ffmpeg 설치 여부 확인
REM ============================================================
echo.
echo [2/4] ffmpeg 설치 확인 중...
ffmpeg -version >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo.
    echo ⚠️  ffmpeg가 설치되어 있지 않습니다.
    echo    MKV 파일 처리를 위해 ffmpeg가 필요합니다.
    echo.
    echo 📥 설치 방법 (택 1^):
    echo    1. winget install ffmpeg    (Windows 11 터미널에서^)
    echo    2. https://ffmpeg.org/download.html 에서 다운로드
    echo.
    echo    설치 후 이 창을 닫고 다시 실행해도 됩니다.
    echo    지금은 WAV 파일만 처리 가능합니다.
    echo.
    set FFMPEG_OK=0
) else (
    echo ✅ ffmpeg 확인됨
    set FFMPEG_OK=1
)

REM ============================================================
REM 3. 가상환경 생성
REM ============================================================
echo.
echo [3/4] Python 가상환경 생성 중...

if exist "venv\Scripts\activate.bat" (
    echo ✅ 가상환경이 이미 존재합니다. 건너뛰기.
) else (
    python -m venv venv
    if %ERRORLEVEL% neq 0 (
        echo ❌ 가상환경 생성 실패!
        pause
        exit /b 1
    )
    echo ✅ 가상환경 생성 완료
)

REM ============================================================
REM 4. 패키지 설치
REM ============================================================
echo.
echo [4/4] 필요한 패키지 설치 중... (시간이 걸릴 수 있습니다)
echo.

call venv\Scripts\activate.bat

pip install --upgrade pip >nul 2>&1
pip install -r requirements.txt

if %ERRORLEVEL% neq 0 (
    echo.
    echo ❌ 패키지 설치 중 오류가 발생했습니다.
    echo    인터넷 연결을 확인하고 다시 시도해주세요.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo  ✅ 설치 완료!
echo ============================================================
echo.
echo  사용법:
echo    1. 이 폴더에 MKV 또는 WAV 파일을 넣으세요
echo    2. run.bat 을 더블클릭하세요
echo    3. 모델과 옵션을 선택하면 자동 전사됩니다
echo.
echo ============================================================
pause
