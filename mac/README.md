# 🎬 Whisper 배치 전사 도구 (Mac)

오디오/비디오 파일을 자동으로 텍스트로 변환하는 도구입니다.  
OpenAI Whisper를 사용하여 한국어 음성을 인식합니다.

## ✨ 주요 기능

- **배치 처리**: 폴더 안의 MKV/WAV 파일을 한 번에 전사
- **모델 선택**: tiny ~ large 모델 중 선택 (속도 vs 품질)
- **자동 반복 제거**: Whisper 환각(hallucination) 현상 자동 필터링
- **Apple Silicon 지원**: M1/M2/M3/M4 MPS 가속

## 📦 설치 방법

### 방법 1: .pkg 설치파일 (추천)

1. [Releases 페이지](../../releases)에서 `WhisperBatchTool_1.0.0.pkg` 다운로드
2. 더블클릭하여 설치
3. 자동으로 터미널이 열리며 환경 구성 시작

### 방법 2: 수동 설치

1. 이 저장소를 다운로드합니다 (Code → Download ZIP)
2. 압축을 풀고 터미널을 엽니다
3. 아래 명령어를 실행합니다:

```bash
chmod +x install.sh run.sh
./install.sh
```

## 🚀 사용 방법

1. 이 폴더에 **MKV 또는 WAV 파일**을 넣습니다
2. 터미널에서 실행합니다:

```bash
./run.sh
```

3. 안내에 따라 모델과 옵션을 선택합니다
4. 같은 폴더에 `.txt` 결과 파일이 생성됩니다

## 🍎 Apple Silicon 지원

| Mac 종류    | PyTorch  | 가속               |
| ----------- | -------- | ------------------ |
| M1/M2/M3/M4 | MPS 가속 | ✅ GPU 가속 (빠름) |
| Intel Mac   | CPU 전용 | ❌ CPU만 사용      |

설치 시 자동으로 감지하여 최적의 버전을 설치합니다.

## 🤖 모델 비교

| 모델   | 속도      | 품질      | 크기    | 추천 용도     |
| ------ | --------- | --------- | ------- | ------------- |
| tiny   | 매우 빠름 | 낮음      | ~39MB   | 빠른 테스트   |
| base   | 빠름      | 보통      | ~74MB   | 일반 회의     |
| small  | 보통      | 높음      | ~244MB  | **일반 추천** |
| medium | 느림      | 매우 높음 | ~769MB  | 정확도 중시   |
| large  | 매우 느림 | 최고      | ~1550MB | 최고 품질     |

## ❓ 문제 해결

| 증상                      | 해결 방법                         |
| ------------------------- | --------------------------------- |
| `permission denied`       | `chmod +x install.sh run.sh` 실행 |
| `brew: command not found` | [Homebrew 설치](https://brew.sh/) |
| 전사가 너무 느림          | 더 작은 모델 선택 (tiny, base)    |

## 📄 라이선스

이 프로젝트는 MIT 라이선스로 배포됩니다.  
[OpenAI Whisper](https://github.com/openai/whisper) 라이선스를 확인해주세요.
