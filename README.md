# Aurora AI TQM — W03 품질 이슈와 공급 복구

가상 화장품 그룹 Aurora의 원료 로트 품질 사건(`LOT-B-2602-P`) 하나를 **판정 → 회수 범위 결정 → 재공급 계획**까지 이어 처리하는 업무 시스템입니다.

- 원료 로트에서 배치·출하·고객까지 영향 범위를 추적합니다.
- 규칙이 판정하고, 사람(품질위원회·SCM)이 승인하며, AI(Claude)는 안건 요약과 초안만 씁니다.
- 승인 결과가 상태로 남아 다음 결정(재공급 순서)의 입력이 됩니다.

**▶ [데모 영상 보기](https://github.com/yhk1059/aurora-ai-tqm-w03/releases/download/demo/w03-demo.mp4)** (5분 20초, 자막 포함)

## 구성

| 경로 | 내용 |
|---|---|
| `w03_system/backend` | FastAPI + SQLite. `core`(판정 규칙·상태), `api`, `ai`(Claude 호출) |
| `w03_system/frontend` | React + Vite + Tailwind 화면 |
| `w03_system/brain` | 설계 문서 — 업무모델, 결정 이력, 가정, 시연 시나리오 |
| `w03_system/scripts` | 사건 데이터 분석, 시연 녹화 스크립트 |

## 실행

> 대회 원본 데이터(`01_참가자_배포용/04_원본데이터/`)는 이 저장소에 없습니다. 실행하려면 그 폴더를 저장소 루트에 두어야 합니다.

```bash
cp w03_system/.env.example w03_system/.env   # ANTHROPIC_API_KEY 입력
uv venv -p 3.14 w03_system/.venv && uv pip install -p w03_system/.venv -r w03_system/backend/requirements.txt
npm --prefix w03_system/frontend install && npm --prefix w03_system/frontend run build
w03_system/.venv/bin/uvicorn backend.api.main:app --app-dir w03_system --port 8000
```

http://localhost:8000 을 엽니다. 테스트: `w03_system/.venv/bin/python -m pytest -q w03_system/backend/tests`
