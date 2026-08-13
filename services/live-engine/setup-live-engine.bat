@echo off
setlocal
chcp 65001 >nul

cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  py -3 -m venv .venv 2>nul || python -m venv .venv
  if errorlevel 1 exit /b 1
)

call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -r requirements-windows.txt
if errorlevel 1 exit /b 1

echo Live transcription runtime is ready.