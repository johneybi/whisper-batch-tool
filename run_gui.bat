@echo off
chcp 65001 >nul
title Whisper Batch Transcriber GUI

cd /d "%~dp0"

if not exist "venv\Scripts\python.exe" (
    echo Virtual environment not found. Run install_gui.bat first.
    pause
    exit /b 1
)

"venv\Scripts\python.exe" whisper_gui.py
if %ERRORLEVEL% neq 0 pause
