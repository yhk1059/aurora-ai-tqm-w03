# Step 8: serve-deploy

## 읽어야 할 파일

먼저 아래 파일들을 읽고 과제와 설계 의도를 파악하라:

- `/CLAUDE.md`
- `/w03_system/brain/status.md`
- `/w03_system/brain/3-design/architecture.md` (디렉토리 구조, API 표와 그 아래 "CORS·정적 파일·웹소켓은 없다" 줄, 환경과 명령어)
- `/w03_system/brain/3-design/decisions.md` ("배포 = AXHub" 행, "1-frontend step 설계" 행)
- `/w03_system/backend/api/main.py` (`GET /`의 임시 첫 화면, `/healthz`)
- `/w03_system/backend/tests/test_api.py`
- `/Dockerfile`, `/axhub.yaml`, `/.dockerignore`
- `/w03_system/frontend/package.json`, `/w03_system/frontend/vite.config.ts`

이전 step에서 만들어진 코드를 꼼꼼히 읽고, 설계 의도를 이해한 뒤 작업하라.

## 작업

배포본에서는 컨테이너 하나가 화면과 API를 모두 내보낸다. FastAPI가 React 빌드 결과(`w03_system/frontend/dist/`)를 서빙하게 하고, Docker 이미지가 화면을 빌드하게 한다. 개발할 때는 지금처럼 Vite 개발 서버의 프록시를 쓴다.

### 1. FastAPI가 빌드 결과를 서빙 (`backend/api/main.py`)

```python
def create_app(db_path: str | None = None, static_dir: str | None = None) -> FastAPI:
    """static_dir가 없으면 환경변수 W03_STATIC_DIR, 그것도 없으면 w03_system/frontend/dist."""
```

- `GET /`는 `dist/index.html`을 돌려준다. `dist/assets/*` 등 빌드 산출물도 같은 출처에서 나간다.
- **`dist`가 없어도 서버는 뜬다.** 이때 `GET /`는 지금의 임시 첫 화면 대신 "화면이 빌드되지 않았습니다. `npm --prefix w03_system/frontend run build`" 안내 한 줄을 돌려준다. 이유: pytest와 서버 단독 실행이 화면 빌드에 기대면 안 된다.
- **`/api/*`와 `/healthz`가 정적 파일보다 먼저다.** 없는 `/api/...` 경로는 JSON 404(`{"error": {...}}` 또는 FastAPI 기본)여야 하고 `index.html`이 나가면 안 된다.
- 화면에 라우터가 없으므로 임의 경로를 `index.html`로 돌리는 처리는 만들지 않는다.
- 테스트 추가(`test_api.py`): 임시 폴더에 `index.html`과 `assets/x.js`를 두고 `create_app(static_dir=...)` → `GET /`가 그 내용, `GET /assets/x.js` 200, `GET /api/incident` 정상, `GET /api/없는경로` 404이고 HTML이 아님. `static_dir`가 없는 폴더일 때 `GET /` 200(안내), `/healthz` 200.

### 2. Dockerfile

다단계 빌드로 바꾼다.

- 1단계(Node 22): `w03_system/frontend/`의 `package.json`·`package-lock.json`만 먼저 복사해 `npm ci`, 그다음 소스를 복사해 `npm run build`.
- 2단계(지금의 `python:3.14-slim`): 지금 내용 그대로 + 1단계의 `dist`를 `w03_system/frontend/dist`로 복사.
- `.dockerignore`에 `w03_system/frontend/dist`가 빠져 있으면 더한다(`**/node_modules`는 이미 있다). 이유: 로컬의 오래된 빌드가 이미지에 들어가면 안 된다.
- `CMD`, `PORT`, `axhub.yaml`의 `health_path`는 바꾸지 않는다.

Docker가 설치되어 있으면 실제로 빌드해 확인하고(`docker build -t aurora-ai-tqm-test .` → 컨테이너 실행 → `curl /healthz`, `curl /`, `curl /api/incident` → 컨테이너와 이미지 정리), 없으면 건너뛰고 summary에 "Docker 빌드 미확인"이라고 적는다.

### 3. 로컬 통합 확인

화면을 빌드하고 서버 하나만 띄워 확인한 뒤 종료한다.

```bash
npm --prefix w03_system/frontend run build
W03_DB_PATH=$(mktemp -d)/w03.sqlite w03_system/.venv/bin/uvicorn backend.api.main:app --app-dir w03_system --port 8010 &
curl -s localhost:8010/ | head -c 200            # React index.html
curl -s localhost:8010/healthz
curl -s -X POST "localhost:8010/api/scenarios/demo1?actor=quality_owner" | head -c 300
```

### 4. 문서

- `architecture.md`:
  - 디렉토리 구조와 모듈 경계 표에 "`api/`는 화면 빌드 결과를 서빙한다(배포용)"를 반영한다.
  - "CORS·정적 파일·웹소켓은 없다. 화면은 Vite 개발 서버의 프록시로 `/api`를 호출한다" 줄을 "개발: Vite 프록시 / 배포: FastAPI가 `frontend/dist` 서빙. CORS·웹소켓은 없다"로 고친다.
  - "환경과 명령어"에 빌드 후 서버 하나로 실행하는 명령을 더하고, 화면은 "브라우저에서 시연 순서대로 확인"이라는 테스트 전략 문장은 그대로 둔다.
- `status.md`: 단계를 "화면(1-frontend) 구현 완료"로, "끝난 것"에 한 줄, "다음 할 일"을 ① 브라우저에서 시연 3건 확인 ② AXHub 재배포 ③ 시연 영상 촬영으로 고친다. "미정 질문"의 배포본 DB 공유 항목은 그대로 둔다.
- 루트 `CLAUDE.md`의 "핵심 맥락" 마지막 문장("다음은 구현. 다음은 업무모델 설계")은 고치지 않는다. 사용자가 관리한다.

## Acceptance Criteria

```bash
w03_system/.venv/bin/python -m pytest -q w03_system/backend/tests
npm --prefix w03_system/frontend run build
test -f w03_system/frontend/dist/index.html
```

## 검증 절차

1. 위 AC 커맨드를 실행한다.
2. 아키텍처 체크리스트를 확인한다:
   - `3-design/architecture.md`의 모듈 경계를 따르는가? (`api/`에 규칙·전이 로직 없음)
   - `3-design/decisions.md`의 배포 결정(AXHub, Docker, 포트 8080, `/healthz`)을 벗어나지 않았는가?
   - CLAUDE.md 금지 규칙을 위반하지 않았는가?
3. 결과에 따라 `w03_system/phases/1-frontend/index.json`의 해당 step을 업데이트한다:
   - 성공 → `"status": "completed"`, `"summary": "산출물 한 줄 요약"` (Docker 빌드를 실제로 확인했는지 적는다)
   - 수정 3회 시도 후에도 실패 → `"status": "error"`, `"error_message": "구체적 에러 내용"`
   - 사용자 개입 필요 → `"status": "blocked"`, `"blocked_reason": "구체적 사유"` 후 즉시 중단

## 금지사항

- `axhub deploy` 등 실제 배포 명령을 실행하지 마라. 이유: 배포는 사용자가 화면을 확인한 뒤 직접 지시한다.
- `w03_system/frontend/dist/`를 git에 올리지 마라. 이유: 빌드 산출물이고 `w03_system/.gitignore`에 제외되어 있다. 이미지 안에서 빌드한다.
- 루트 `.gitignore`와 `.claude`·`.codex`·`.agents`를 고치지 마라. 이유: CLAUDE.md 금지 규칙.
- CORS 허용을 추가하지 마라. 이유: 개발은 프록시, 배포는 같은 출처라 필요 없다.
- 브라우저별로 DB를 나누는 처리(세션·쿠키)를 만들지 마라. 이유: 이번 phase 범위 밖으로 정했고 `status.md` 미정 질문에 있다.
- `01_참가자_배포용/04_원본데이터/`의 파일을 수정하지 마라. 이유: 원본 데이터는 대회 규칙상 수정 금지다.
- 기존 테스트를 깨뜨리지 마라
