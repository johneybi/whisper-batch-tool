@echo off
chcp 65001 >nul
title Whisper Batch Transcriber GUI Installer

cd /d "%~dp0"

echo ============================================================
echo  Whisper Batch Transcriber GUI - Windows installer
echo ============================================================
echo.

python --version >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo Python was not found. Install Python 3.10 or newer and enable "Add Python to PATH".
    echo https://www.python.org/downloads/
    pause
    exit /b 1
)

if not exist "venv\Scripts\python.exe" (
    python -m venv venv
    if %ERRORLEVEL% neq 0 (
        echo Failed to create virtual environment.
        pause
        exit /b 1
    )
)

call venv\Scripts\activate.bat
python -m pip install --upgrade pip

echo.
echo Select PyTorch install mode:
echo   1. CPU, safest default
echo   2. NVIDIA GPU, CUDA 12.6
set /p TORCH_CHOICE="Choice [1]: "
if "%TORCH_CHOICE%"=="" set TORCH_CHOICE=1

if "%TORCH_CHOICE%"=="2" (
    pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu126
) else (
    pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu
)
if %ERRORLEVEL% neq 0 (
    echo Failed to install PyTorch.
    pause
    exit /b 1
)

pip install -r requirements.txt
if %ERRORLEVEL% neq 0 (
    echo Failed to install Python dependencies.
    pause
    exit /b 1
)

echo.
echo Installation complete.
echo Run run_gui.bat to start the app.
pause
