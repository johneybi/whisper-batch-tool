@echo off
chcp 65001 >nul
title Whisper 배치 전사 도구

REM 가상환경 존재 확인
if not exist "venv\Scripts\activate.bat" (
    echo ❌ 가상환경이 없습니다. install.bat을 먼저 실행해주세요.
    pause
    exit /b 1
)

REM 가상환경 활성화 후 스크립트 실행
call venv\Scripts\activate.bat
python batch_whisper_transcriber.py
