# Demo Guide

이 저장소의 README hero 이미지는 `npm run smoke:render`가 생성한 Electron 화면 캡처입니다. 실제 사용자 미디어나 모델 결과를 저장소에 넣지 않고, UI가 실행 가능한지와 핵심 표면이 렌더되는지만 재현 가능한 방식으로 보여 줍니다.

![Electron smoke render](assets/desktop-smoke.png)

## What the screenshot proves

- Electron 앱이 `Whisper Studio` 화면을 렌더한다.
- 일반 파일 전사/실시간 전사 작업 전환이 노출된다.
- 파일 추가, 모델 preset, 출력 결과 preview, FFmpeg 상태 표면이 존재한다.
- smoke 보고서에는 `hasDropzone`, `hasSetup`, `hasResultPreview`, `hasFfmpegReady`와 버튼 목록이 함께 기록된다.

## Reproduce the batch demo

```powershell
cd desktop
npm ci
npm run build
npm run smoke:render
```

실사용 batch demo는 앱에서 오디오/비디오 파일을 추가하고 모델, 언어, 장치, 출력 포맷을 선택한 뒤 진행률과 생성 파일을 확인합니다. 모델 다운로드와 실제 미디어는 환경마다 다르므로 예제 파일을 커밋하지 않습니다.

## Reproduce the live demo

1. `services/live-engine`의 `.venv`, `uvicorn`, FFmpeg, 모델을 준비합니다.
2. 필요하면 `WHISPER_LIVE_ENGINE_ROOT`로 호환 외부 런타임 경로를 지정합니다.
3. Electron 앱에서 `실시간 전사`를 선택하고 YouTube URL, 시작 지점, 청크 길이를 입력합니다.
4. 실행 상태·문단 출력·중지 동작과 `data/knowledge` 저장을 확인합니다.

라이브 데모는 외부 URL과 모델/GPU 환경이 필요하므로 CI smoke에 포함하지 않습니다. 저장소의 기본 runtime과 이 범위의 trade-off는 [제품 결정 기록](DECISIONS.md)과 [Issue #2](https://github.com/johneybi/whisper-batch-tool/issues/2)에 기록되어 있습니다.

## Product evolution visual

Script → Tk GUI → batch utility → shared core → Electron/React → focused live workspace의 흐름은 [PRODUCT_EVOLUTION.md](PRODUCT_EVOLUTION.md)의 Mermaid diagram과 decision table에서 확인할 수 있습니다. 이 자료는 “무엇을 만들었나”보다 “어떤 문제를 보고 어떤 범위를 선택했나”를 설명합니다.

## Asset policy

- smoke screenshot은 제품 UI만 포함하며 사용자 파일·전사 결과·자격 증명을 포함하지 않습니다.
- 실제 media/GPU benchmark와 live source는 로컬 환경에서만 사용합니다.
- 새 screenshot을 갱신할 때는 `npm run smoke:render` 결과와 생성 시점을 함께 확인합니다.
