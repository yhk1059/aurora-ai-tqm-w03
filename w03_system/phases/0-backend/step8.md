# Step 8: api

## 읽어야 할 파일

먼저 아래 파일들을 읽고 과제와 설계 의도를 파악하라:

- `/CLAUDE.md`
- `/w03_system/brain/status.md`
- `/w03_system/brain/3-design/architecture.md` (API 표, 모듈 경계의 `api/`, 상태 관리, 환경과 명령어)
- `/w03_system/brain/3-design/business-model.md` §8-5 (액션과 역할)
- `/w03_system/brain/3-design/ui-guide.md` ("레이아웃": 화면이 무엇을 요청할지 가늠용)
- `/w03_system/backend/core/actions.py` (`execute`, `available_actions`, `ActionError`의 code)
- `/w03_system/backend/core/view.py` (`incident_view`), `/w03_system/backend/core/scenario.py` (`list_scenarios`, `run_scenario`)
- `/w03_system/backend/core/ontology.py` (`to_dict`), `/w03_system/backend/core/db.py` (`connect`)
- `/w03_system/backend/ai/tasks.py`, `/w03_system/backend/ai/client.py` (`run_task`, `is_available`, `AiResult`)
- `/w03_system/backend/tests/test_scenarios.py` (core 쪽 기대값. API 테스트가 같은 값을 내는지 확인한다)

이전 step에서 만들어진 코드를 꼼꼼히 읽고, 설계 의도를 이해한 뒤 작업하라.

## 작업

`w03_system/backend/api/main.py`에 FastAPI 앱을 만든다. API는 **얇다**: HTTP 요청을 `core`·`ai` 함수 호출로 바꾸고 결과를 JSON으로 돌려줄 뿐이다. 규칙·전이·권한 판단을 여기에 쓰지 않는다.

### 앱

```python
def create_app(db_path: str | None = None) -> FastAPI:
    """db_path가 없으면 환경변수 W03_DB_PATH, 그것도 없으면 w03_system/data/w03.sqlite.
    경로는 이 파일 위치에서 계산한다 (현재 작업 디렉토리에 기대지 않는다)."""

app = create_app()     # uvicorn backend.api.main:app --app-dir w03_system
```

- DB 연결은 요청마다 열고 닫는다(또는 SQLite의 스레드 제약에 걸리지 않는 다른 방식). 테스트는 임시 파일 경로를 `create_app`에 넘긴다.
- 서버를 켰을 때 DB 파일이 없으면 빈 DB를 만든다(사건 없음).

### 라우트 (전부 `/api` 아래)

| 메서드·경로 | 요청 | 하는 일 | 응답 |
|---|---|---|---|
| `GET /api/incident?actor={역할 key}` | — | `view.incident_view(conn, actor)` | 사건 뷰 그대로. 사건이 없으면 열 수 있는 배치 목록이 든 뷰 |
| `POST /api/actions/{action}` | `{"actor": "...", "inputs": {...}}` | `actions.execute(conn, action, actor, inputs)` | `{"result": ActionResult 내용, "view": 실행 후 사건 뷰(같은 actor)}` |
| `POST /api/ai/{task}` | `{"params": {...}}` | `ai.run_task(conn, task, params)` | `AiResult` 내용. 키가 없으면 `ok: false, error: "no_key"` (HTTP 200) |
| `GET /api/ai/status` | — | `ai.is_available()` | `{"available": bool, "model": "..."}` |
| `GET /api/ontology` | — | `ontology.to_dict()` | 정의 그대로 |
| `GET /api/scenarios` | — | `scenario.list_scenarios()` | 목록 |
| `POST /api/scenarios/{name}?upto=&setup_only=&actor=` | — | `scenario.run_scenario(conn, name, upto=…, setup_only=…)` | `{"steps": 단계별 결과, "view": 실행 후 사건 뷰}` |

**오류 응답:** `ActionError`의 code를 HTTP 상태로 옮긴다. 본문은 `{"error": {"code": "...", "message": "..."}}`.

| code | HTTP |
|---|---|
| `unknown_action`, 없는 시나리오·AI task | 404 |
| `forbidden` | 403 |
| `invalid_input`, 본문 형식 오류 | 422 |
| `precondition` | 409 |

핵심 규칙:
- **액션 실행 응답에는 항상 실행 후 사건 뷰가 들어간다.** 이유: 화면은 상태 복사본을 갖지 않고 서버 응답을 그대로 그린다(`architecture.md` 패턴 4).
- **오류가 나면 DB는 그대로다.** (실행기가 롤백한다. API가 따로 무언가를 쓰지 않는다.)
- 입력 검증은 "본문에 `actor`와 `inputs`가 있는가" 정도만 한다. 액션별 필드 검사는 실행기가 한다. 액션마다 요청 모델 클래스를 따로 만들지 않는다. 이유: 액션 입력 정의는 온톨로지에 이미 있고, 여기 다시 쓰면 두 곳이 어긋난다.
- 로그인·세션·토큰이 없다. 역할은 요청이 알려주고, 권한은 실행기가 액션 정의로 검사한다.
- CORS 설정을 넣지 않는다. 이유: 화면은 Vite 개발 서버의 프록시로 `/api`를 호출할 예정이다(다음 phase).
- 정적 파일 서빙, 웹소켓, 백그라운드 작업을 넣지 않는다.

### 문서 갱신 (이 phase의 마지막 step)

1. `w03_system/brain/3-design/architecture.md`
   - API 표를 실제 라우트와 맞춘다(추가된 `GET /api/ai/status`, `GET /api/scenarios`, 쿼리 인자, 오류 코드 표).
   - "환경과 명령어"의 서버 실행 명령을 실제로 실행해 확인한 것으로 맞춘다.
2. `w03_system/brain/status.md`
   - "단계"를 "서버(0-backend) 구현 완료, 화면 구현 전"으로 고친다.
   - "끝난 것"에 한 줄: 서버 구현 완료(core·ai·api, 시연 3건 테스트 통과) → `w03_system/backend/`, `w03_system/scenarios/`.
   - "다음 할 일"을 고친다: ① `1-frontend` step 설계(`/harness` C단계) ② AI 실제 호출 확인(키 필요, step 7에서 확인하지 못했으면).
   - 그 밖의 내용은 건드리지 않는다.

### 테스트

`w03_system/backend/tests/test_api.py`. FastAPI `TestClient`와 임시 DB 파일을 쓴다. AI는 호출하지 않는다.

- `GET /api/incident`(빈 DB): `incident`가 null이고 열 수 있는 배치 목록에 `B-02-2602-01`이 있다.
- `POST /api/actions/open_incident`(`quality_owner`, 2026-07-01): 200, 응답의 `view`에 사건 `INC-001`, 보류 배치 2개 `기준초과(미상신)`. 이어서 `GET /api/incident?actor=quality_owner`가 같은 뷰를 준다.
- 권한: `quality_owner`로 `committee_decision` → 403, 본문에 code `forbidden`. 그 뒤 `GET /api/incident`가 실행 전과 같다.
- 전제 조건: 사건이 있는데 `open_incident` → 409. 없는 액션 → 404. `actor`가 빠진 본문 → 422. 사유 없는 거절 → 409 또는 422(실행기의 code를 따른다).
- 가능한 액션: 상신 후 `GET /api/incident?actor=quality_committee`의 가능한 액션에 `committee_decision`이 있고, `actor=scm`에는 없다.
- `GET /api/ontology`: 200, 액션 9개와 관계 17개가 있다.
- `GET /api/scenarios`: `demo1`, `demo2`, `demo3a`, `demo3b`, `other-batch`가 있다.
- `POST /api/scenarios/demo1`: 200, `view`의 사건 상태 `복구계획확정`, 계획 순서 C-103 → C-102 → C-101 → C-104 → C-108. **`core.scenario.run_scenario`를 직접 실행해 얻은 `incident_view`와 같다.**
- `POST /api/scenarios/demo2?setup_only=true`: 계획 v1 `확정`. 이어서 API로 시연 2의 나머지 액션(2-1 ~ 2-5)을 하나씩 실행하면 끝 상태가 `demo2` 전체 실행과 같다.
- `POST /api/scenarios/없는이름` → 404.
- `POST /api/actions/reset` 뒤 `GET /api/incident`의 `incident`가 null이다.
- `GET /api/ai/status`: `available`이 bool이다. 키가 없는 환경에서 `POST /api/ai/agenda_summary` → 200, `ok` false, `error` `no_key`. 없는 task → 404.
- 서로 다른 임시 DB를 쓰는 앱 두 개가 서로의 상태에 영향을 주지 않는다.

### 서버 기동 확인 (손으로 한 번)

```bash
w03_system/.venv/bin/uvicorn backend.api.main:app --app-dir w03_system --port 8000
```
백그라운드로 띄우고 `curl -s localhost:8000/api/incident`가 JSON을 주는지 확인한 뒤 **반드시 서버를 종료한다.** `w03_system/data/`에 생긴 DB 파일은 git에 올라가지 않는지(`git status --short`) 확인한다.

## Acceptance Criteria

```bash
w03_system/.venv/bin/python -m pytest -q w03_system/backend/tests/test_api.py
w03_system/.venv/bin/python -m pytest -q w03_system/backend/tests
cd w03_system && .venv/bin/python -c "from backend.api.main import app; assert any(r.path == '/api/incident' for r in app.routes)"
! grep -rnE "^(import|from) +(fastapi|anthropic)|backend\.(api|ai)" w03_system/backend/core
! grep -rnE "can_transition|defect_rate|target_batch_state" w03_system/backend/api
git diff --quiet -- 01_참가자_배포용
grep -q "0-backend" w03_system/brain/status.md
```

## 검증 절차

1. 위 AC 커맨드를 실행한다.
2. 아키텍처 체크리스트를 확인한다:
   - `api/`에 규칙·전이·권한 로직이 없는가? (`core` 함수 호출과 오류 변환뿐인가)
   - `core/`가 `api/`·`ai/`를 import하지 않는가?
   - 액션 응답에 실행 후 사건 뷰가 들어가는가?
   - `architecture.md`의 API 표와 실제 라우트가 일치하는가?
   - 띄운 서버 프로세스가 남아 있지 않은가? (`lsof -i :8000`이 비어 있는가)
   - `git status --short`에 `data/`, `.venv/`, `.env`, `__pycache__`가 없는가?
3. 결과에 따라 `w03_system/phases/0-backend/index.json`의 step 8을 업데이트한다:
   - 성공 → `"status": "completed"`, `"summary"`에 라우트 목록, 요청·응답 형식, 오류 코드 매핑, 서버 실행 명령, DB 경로 규칙을 한 줄로 적는다(다음 phase의 화면 구현이 이 줄을 본다)
   - 수정 3회 시도 후에도 실패 → `"status": "error"`, `"error_message": "구체적 에러 내용"`
   - 사용자 개입 필요 → `"status": "blocked"`, `"blocked_reason": "구체적 사유"` 후 즉시 중단

## 금지사항

- `api/`에서 DB를 직접 고치지 마라(`db.put_object` 등). 이유: 모든 변경은 액션 실행기를 지난다(`architecture.md` 패턴 2).
- 액션별 전용 엔드포인트(`/api/submit-agenda` 등)를 만들지 마라. 이유: 액션은 온톨로지 정의에서 나오고, `POST /api/actions/{action}` 하나로 받는다. 액션이 늘어도 API가 그대로여야 한다.
- 가능한 액션을 API에서 다시 계산하거나 걸러내지 마라. 이유: 서버의 `available_actions`가 유일한 기준이다.
- 서버 프로세스를 띄운 채로 step을 끝내지 마라. 이유: 실행기가 step 종료를 기다리다 멈추고, 포트가 남는다.
- `core/`·`ai/`의 동작을 바꾸지 마라. 이유: 이미 검증된 층이다. API에 필요한 직렬화(예: dataclass → dict)는 `api/` 안에서 한다.
- 화면 코드(`frontend/`)를 만들지 마라. 이유: 다음 phase다.
- `status.md`·`architecture.md`에서 위에 적은 곳 외의 내용을 고치지 마라. 이유: 결정 기록은 사용자와 논의해 바꾼다.
- `01_참가자_배포용/04_원본데이터/`의 파일을 수정하지 마라. 이유: 원본 데이터는 대회 규칙상 수정 금지다.
- 기존 테스트를 깨뜨리지 마라.
