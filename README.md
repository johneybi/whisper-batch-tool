# Whisper Batch Transcriber

Whisper 기반 오디오/비디오 배치 전사 데스크톱 앱입니다. 현재 저장소의 공식 제품 타깃은 `desktop/` 아래 Electron/React 앱입니다. 기존 `whisper_gui.py` 기반 Tk/PyInstaller 앱은 이전 릴리스를 유지하기 위한 legacy 경로로 남겨 둡니다.

## Current Target

- 공식 앱: Electron/React/shadcn desktop app in `desktop/`
- 공유 전사 코어: `transcriber_core.py`
- Electron worker: `desktop/python/worker.py`
- Legacy 앱: `whisper_gui.py`, `WhisperBatchTranscriber.spec`, 기존 PyInstaller release scripts

GitHub Releases에는 앞으로 Electron 앱 산출물을 올리는 것을 기준으로 합니다. 기존 PyInstaller 산출물은 새 공식 릴리스로 자동 게시하지 않습니다.

## Development

Windows에서 현재 공식 Electron 앱을 실행합니다.

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_desktop_dev_windows.ps1
```

처음 실행하거나 desktop 의존성을 다시 설치해야 하면 `-Install`을 붙입니다.

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_desktop_dev_windows.ps1 -Install
```

Electron 앱은 `WHISPER_PYTHON`이 있으면 그 값을 사용합니다. 없으면 루트의 `.release-venv`, `venv`, `C:\whisper\torch-env\Scripts\python.exe`, 시스템 Python 순서로 worker 실행 Python을 찾습니다.

## Verification

Python 코어 테스트:

```powershell
python -m unittest discover -s tests
```

Electron UI 빌드와 렌더 smoke:

```powershell
cd desktop
npm run build
npm run smoke:render
```

Worker self-test:

```powershell
python desktop\python\worker.py self-test
python desktop\python\worker.py runtime-info
```

## Distribution Direction

배포 기준은 Electron 앱입니다.

1. `desktop/` 앱을 공식 사용자 경험으로 유지합니다.
2. `transcriber_core.py`는 Electron worker와 legacy Tk 앱이 공유할 수 있지만, 새 기능은 Electron 경로에서 먼저 검증합니다.
3. GitHub Actions의 기본 CI는 Electron 앱 빌드와 worker self-test를 검증합니다.
4. 기존 PyInstaller release workflow는 legacy 수동 빌드로만 유지합니다.
5. Electron 패키징이 추가되기 전까지 GitHub Release에는 legacy PyInstaller 산출물을 새 공식 릴리스로 올리지 않습니다.

Electron 패키징을 제품 릴리스로 완성하려면 다음 단계에서 Windows installer/portable ZIP, macOS DMG/ZIP, Python runtime 포함 정책을 확정해야 합니다.

## Supported Inputs

ffmpeg가 처리할 수 있는 일반적인 오디오/비디오 파일을 대상으로 합니다.

- Audio: `mp3`, `wav`, `m4a`, `flac`, `aac`, `ogg`, `opus`, `wma`, `aiff`, `alac`, `amr`
- Video: `mp4`, `mov`, `mkv`, `webm`, `avi`, `wmv`, `m4v`, `flv`, `mpeg`, `mpg`, `m2ts`, `mts`, `ts`

## Output Formats

- `TXT`: 전체 텍스트와 세그먼트
- `SRT`: 일반 자막
- `VTT`: 웹 자막
- `JSON`: Whisper 결과에 가까운 구조화 데이터
- `TSV`: 세그먼트 표 데이터

## Legacy PyInstaller App

기존 Tk 앱은 유지보수와 이전 릴리스 재생성을 위해 남겨 둡니다.

Windows legacy 실행:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_dev_windows.ps1
```

Windows legacy 빌드:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build_release_windows.ps1
```

macOS legacy 빌드:

```bash
chmod +x build_macos.sh scripts/build_release_macos.sh
./build_macos.sh
```

이 경로는 더 이상 새 공식 UI 배포 경로가 아닙니다.

## Important Files

- `desktop/`: 공식 Electron/React 데스크톱 앱
- `desktop/electron/main.cjs`: Electron main process와 IPC
- `desktop/electron/preload.cjs`: renderer에 노출되는 안전 API 표면
- `desktop/python/worker.py`: Electron에서 호출하는 Python worker
- `desktop/src/`: React UI
- `transcriber_core.py`: Whisper 전사 코어, 출력 생성, ffmpeg 준비
- `runtime_manager.py`: legacy 앱의 runtime 선택/설치 관리
- `tests/`: 모델 다운로드 없이 빠르게 실행 가능한 코어 테스트
- `whisper_gui.py`: legacy Tk GUI
- `WhisperBatchTranscriber.spec`: legacy PyInstaller 설정
- `scripts/build_release_windows.ps1`: legacy Windows PyInstaller 빌드
- `.github/workflows/desktop-ci.yml`: 공식 Electron 타깃 CI
- `.github/workflows/build-release.yml`: legacy PyInstaller 수동 빌드
