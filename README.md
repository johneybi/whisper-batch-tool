# Whisper Batch Transcriber

Whisper 기반 오디오/비디오 배치 전사 GUI 앱입니다. 목표는 최종 사용자가 Python, pip, ffmpeg를 직접 설치하지 않고도 배포 파일을 받아 실행하게 만드는 것입니다.

## 최종 사용자에게 배포할 파일

배포자는 OS별로 빌드한 뒤 `release/` 폴더의 파일을 전달합니다.

- Windows: `WhisperBatchTranscriber-1.1.0-Windows-Setup.exe`
- Windows 대체 배포: `WhisperBatchTranscriber-1.1.0-Windows-x64.zip`
- macOS: `WhisperBatchTranscriber-1.1.0-macOS.dmg`
- macOS 대체 배포: `WhisperBatchTranscriber-1.1.0-macOS.zip`

최종 사용자는 위 파일만 받으면 됩니다. Python과 ffmpeg를 따로 설치하지 않아도 됩니다. Whisper 모델은 첫 사용 시 선택한 모델을 자동 다운로드하므로 인터넷 연결이 필요할 수 있습니다.

## 최종 사용자 사용법

Windows 설치 파일:

1. `WhisperBatchTranscriber-1.1.0-Windows-Setup.exe`를 실행합니다.
2. 시작 메뉴 또는 바탕화면 바로가기로 앱을 실행합니다.
3. `Add Files` 또는 `Add Folder`로 파일을 추가하고 `Start`를 누릅니다.

Windows ZIP:

1. ZIP을 압축 해제합니다.
2. `WhisperBatchTranscriber.exe`를 실행합니다.

배포 검증용으로는 다음 명령을 실행할 수 있습니다. 종료 코드가 `0`이면 앱 번들이 ffmpeg 런타임을 정상적으로 찾은 것입니다.

```bat
WhisperBatchTranscriber.exe --self-test
```

macOS DMG:

1. DMG를 열고 앱을 Applications 폴더로 옮깁니다.
2. `Whisper Batch Transcriber` 앱을 실행합니다.

## 지원 입력 포맷

앱은 ffmpeg 런타임을 번들에 포함하거나 자동 준비하도록 구성되어 있습니다. 대표적으로 다음 파일을 처리할 수 있습니다.

- 오디오: `mp3`, `wav`, `m4a`, `flac`, `aac`, `ogg`, `opus`, `wma`, `aiff`, `alac`, `amr`
- 비디오: `mp4`, `mov`, `mkv`, `webm`, `avi`, `wmv`, `m4v`, `flv`, `mpeg`, `mpg`, `m2ts`, `mts`, `ts`

목록에 없는 확장자도 ffmpeg가 읽을 수 있으면 처리 시도합니다.

## 출력 포맷

- `TXT`: 전체 텍스트와 시간대별 세그먼트
- `SRT`: 일반 자막
- `VTT`: 웹 자막
- `JSON`: Whisper 원본 결과에 가까운 구조화 데이터
- `TSV`: 세그먼트 표 데이터

## 배포자 빌드 방법

빌드는 OS별 네이티브 환경에서 진행합니다. Windows 앱은 Windows에서, macOS 앱은 macOS에서 빌드하는 방식이 가장 안정적입니다.

GitHub 저장소에서 배포한다면 Actions 탭의 `Build distributable apps` 워크플로를 수동 실행하거나 `v*` 태그를 푸시하면 Windows와 macOS 산출물을 자동으로 만들 수 있습니다.

릴리스 빌드는 개발용 `venv`와 분리된 `.release-venv`를 사용합니다. 깨끗한 환경에서 다시 만들려면 `WHISPER_CLEAN_RELEASE_VENV=1`을 지정합니다.

### Windows 릴리스 빌드

필요 도구:

- Python 3.10 이상
- 선택 사항: Inno Setup, 설치형 `.exe` 생성용

빌드:

```bat
build_windows.bat
```

Windows 배포 빌드는 기본적으로 CPU 전용 Torch를 포함합니다. 대부분의 사용자에게 가장 호환성이 좋습니다.

NVIDIA CUDA용 빌드를 따로 만들려면 다음처럼 실행합니다.

```bat
set WHISPER_RELEASE_TORCH=cuda
build_windows.bat
```

결과:

- 항상 생성: `release/WhisperBatchTranscriber-1.1.0-Windows-x64.zip`
- Inno Setup이 있으면 추가 생성: `release/WhisperBatchTranscriber-1.1.0-Windows-Setup.exe`

Windows ZIP을 배포하기 전에 다음 검증을 실행합니다. ZIP을 임시 폴더에 풀고, 시스템 ffmpeg가 없는 PATH에서 앱 self-test를 통과해야 성공합니다.

```bat
powershell -ExecutionPolicy Bypass -File scripts\verify_release_windows.ps1
```

### macOS 릴리스 빌드

필요 도구:

- Python 3.10 이상
- macOS 기본 `hdiutil`

빌드:

```bash
chmod +x build_macos.sh scripts/build_release_macos.sh
./build_macos.sh
```

결과:

- `release/WhisperBatchTranscriber-1.1.0-macOS.dmg`
- `release/WhisperBatchTranscriber-1.1.0-macOS.zip`

## 개발자 직접 실행

배포 파일을 만들지 않고 개발 환경에서 직접 실행할 때만 사용합니다.

Windows:

```bat
install_gui.bat
run_gui.bat
```

macOS:

```bash
chmod +x install_gui.sh run_gui.sh
./install_gui.sh
./run_gui.sh
```

## 주요 파일

- `whisper_gui.py`: GUI 진입점
- `transcriber_core.py`: 전사 코어, 출력 생성, ffmpeg 런타임 준비
- `WhisperBatchTranscriber.spec`: PyInstaller 앱 번들 설정
- `scripts/build_release_windows.ps1`: Windows 릴리스 빌드
- `scripts/verify_release_windows.ps1`: Windows ZIP 배포물 검증
- `scripts/build_release_macos.sh`: macOS 릴리스 빌드
- `packaging/windows_installer.iss`: Windows 설치 프로그램 설정
