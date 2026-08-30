# Product Decision Records

이 문서는 구현 목록이 아니라, 제품이 무엇을 선택했고 무엇을 의도적으로 미뤘는지 기록합니다. 상세한 논의와 완료 조건은 연결된 GitHub 이슈에서 이어갑니다.

## 2026-08 — Electron/React를 공식 데스크톱 제품으로

- **상태:** Accepted
- **이슈:** [#1](https://github.com/johneybi/whisper-batch-tool/issues/1)
- **결정:** `desktop/` Electron/React 앱을 새 기능과 공식 릴리스의 기준으로 삼고, `whisper_gui.py`는 legacy 호환 경로로 유지한다.
- **이유:** 작업 전환·진행률·취소·라이브 전사를 하나의 제품 경험으로 설명하고 검증하기 위해서다.
- **영향:** 공통 Python 코어는 유지하지만 UI 기능은 Electron 우선으로 구현한다. legacy는 새 제품 기능을 따라가지 않는다.

## 2026-08 — 라이브 전사는 좁고 관찰 가능한 범위로 시작

- **상태:** Accepted
- **이슈:** [#2](https://github.com/johneybi/whisper-batch-tool/issues/2)
- **결정:** YouTube 라이브/영상 URL, 명시적 시작점, 청크 처리, 실행별 중지, 누적 지식을 1차 범위로 한다.
- **이유:** 무제한 스트림보다 GPU 자원 경쟁과 프로세스 소유권을 예측 가능하게 관리하는 것이 먼저다.
- **영향:** 앱 세션의 동시 실행 수를 제한하고, 네이티브 런타임 오류를 UI에서 설명해야 한다.

## 2026-08 — Electron 패키징 전까지 공식 릴리스 보류

- **상태:** Accepted
- **이슈:** [#3](https://github.com/johneybi/whisper-batch-tool/issues/3)
- **결정:** Electron installer/portable/DMG/ZIP과 runtime 전달 정책이 검증되기 전까지 legacy PyInstaller 산출물을 새 제품 릴리스로 게시하지 않는다.
- **이유:** 빌드 가능한 산출물과 사용자가 설치해야 할 공식 제품을 혼동하지 않기 위해서다.
- **영향:** legacy release workflow는 수동·재현용으로 남고, CI의 기본 경로는 Electron과 worker를 검증한다.

## 2026-08 — 정확도 주장보다 실패 복구성을 먼저 검증

- **상태:** Proposed
- **이슈:** [#4](https://github.com/johneybi/whisper-batch-tool/issues/4)
- **결정:** 모델별 보편 정확도 수치를 약속하기보다, 환경 진단·결과 보존·부분 실패 재실행·모델/장치별 재현 가능한 벤치마크를 우선한다.
- **이유:** 실제 품질은 음질·언어·모델·장치에 크게 좌우되고, 사용자가 운영 중 겪는 실패를 설명할 수 있어야 한다.
- **다음 검증:** fixture 기반 출력 테스트와 작은 benchmark matrix를 추가한다.
