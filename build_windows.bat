@echo off
chcp 65001 >nul
title Build Whisper Batch Transcriber Release

cd /d "%~dp0"

powershell -ExecutionPolicy Bypass -File scripts\build_release_windows.ps1

echo.
echo Build complete.
pause
