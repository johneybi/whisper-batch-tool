# Contributing

이 저장소는 개인 프로젝트이지만, 변경의 의도와 제품 방향이 기록으로 남도록 운영합니다. 작은 수정도 이슈·커밋·검증 명령이 서로 읽혀야 합니다.

## 시작하기

1. 이슈를 먼저 확인합니다. 제품 방향·범위 변경은 `product` 또는 `decision` 이슈에서 합의합니다.
2. `main`에서 작업 브랜치를 만듭니다.

```powershell
git switch main
git pull --ff-only
git switch -c feature/<short-topic>
```

3. 변경 범위를 기능 단위로 유지하고, 관련 없는 포맷 변경이나 산출물 커밋을 섞지 않습니다.
4. README·PRD·결정 기록 중 하나가 바뀌면 실제 코드 동작과 함께 링크를 갱신합니다.

## 브랜치 규칙

- `feature/<topic>` — 사용자에게 보이는 기능
- `fix/<topic>` — 재현 가능한 버그 수정
- `refactor/<topic>` — 동작을 유지하는 구조 개선
- `docs/<topic>` — 문서·이슈 템플릿·가이드
- `chore/<topic>` — 빌드·CI·의존성·개발 도구

브랜치는 짧게 유지하고 PR이 병합되면 삭제합니다. `main`은 Electron 공식 제품 라인입니다. legacy 변경은 브랜치와 커밋 본문에 호환성/재현 목적을 명시합니다.

## 커밋 메시지

Conventional Commit 형식을 사용합니다.

```text
<type>(optional-scope): imperative summary
```

허용 타입은 `feat`, `fix`, `refactor`, `docs`, `test`, `chore`, `build`, `ci`입니다. 제목은 짧은 명령형으로 쓰고, 본문에는 사용자 영향·선택 이유·검증 명령을 적습니다. 한 커밋은 하나의 기능 또는 하나의 문서 목적을 설명해야 합니다.

예시:

```text
feat(live): add per-run stop control
fix(worker): preserve completed outputs after cancellation
docs(repo): document Electron release boundary
```

과거 커밋을 날짜에 맞춰 다시 쓰지 않습니다. 이미 공개된 기록의 날짜·작성자·SHA를 바꾸면 링크와 협업자의 clone이 깨질 수 있기 때문입니다. 대신 이후 커밋은 실제 작업 날짜에 생성하고, 과거의 의도는 결정 기록으로 보완합니다.

## 이슈 작성

- 버그는 재현 단계, 기대/실제 결과, 환경, 로그를 포함합니다.
- 기능 제안은 문제, 사용자, 해결하지 않을 범위, 성공 기준을 포함합니다.
- 제품 선택·피봇은 `Product decision` 템플릿을 사용해 **맥락 → 선택 → trade-off → 수용 기준** 순으로 씁니다.
- 현재 상태를 복사하는 이슈 대신, 무엇을 집중하고 무엇을 포기하는지 제목에 드러냅니다.

## 검증

변경 종류에 맞춰 최소한 다음을 실행합니다.

```powershell
python -m unittest discover -s tests
cd desktop
npm ci
npm run test:security
npm run build
npm run smoke:render
```

문서만 바꾼 경우에는 경로·명령·파일명이 실제 저장소와 맞는지 확인하고, 실행하지 못한 검증은 PR에 명시합니다. 모델 다운로드가 필요한 정확도 테스트는 CI에 넣지 않습니다.

## Pull Request

PR 본문은 무엇을/왜/어떻게 검증했는지와 사용자 영향, 남은 한계를 설명합니다. 관련 이슈를 `Closes #N` 또는 `Refs #N`으로 연결하고, UI 변경에는 전후 스크린샷이나 smoke 결과를 첨부합니다.
