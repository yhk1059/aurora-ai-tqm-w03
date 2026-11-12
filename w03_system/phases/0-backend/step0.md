# Step 0: project-setup

## 읽어야 할 파일

먼저 아래 파일들을 읽고 과제와 설계 의도를 파악하라:

- `/CLAUDE.md`
- `/w03_system/brain/status.md`
- `/w03_system/brain/3-design/architecture.md` (디렉토리 구조, 기술 스택, 환경과 명령어)
- `/w03_system/brain/3-design/decisions.md` ("아키텍처 v1", "구현 전 정리 4건" 행)

이 step은 서버 쪽 프로젝트 골격만 만든다. 업무 로직은 한 줄도 쓰지 않는다.

## 작업

모든 명령은 **프로젝트 루트**(`CLAUDE.md`가 있는 곳)에서 실행한다.

### 1. 디렉토리와 파일

```
w03_system/
  .gitignore            # 새로 만든다 (루트 .gitignore 아님)
  .env.example          # ANTHROPIC_API_KEY= 한 줄 (값 없음)
  pytest.ini            # pythonpath = .   testpaths = backend/tests
  backend/
    __init__.py
    requirements.txt
    core/__init__.py
    ai/__init__.py
    api/__init__.py
    tests/__init__.py
    tests/test_setup.py
  scenarios/.gitkeep
```

- `w03_system/.gitignore` 내용: `data/`, `.env`, `.venv/`, `node_modules/`, `frontend/dist/`, `__pycache__/`, `.pytest_cache/`.
- `w03_system/pytest.ini`는 프로젝트 루트에서 `pytest w03_system/backend/tests`를 실행했을 때 `import backend.core`가 되게 한다 (`pythonpath = .`은 ini 파일 위치 기준이다).
- `frontend/`와 `data/`는 만들지 않는다. `frontend/`는 다음 phase에서, `data/`는 서버가 실행 중에 만든다.

### 2. 의존성

`w03_system/backend/requirements.txt`에 아래 패키지를 **버전을 고정해** 적는다: `fastapi`, `uvicorn`, `anthropic`, `pytest`, `httpx`(FastAPI TestClient용).

- `architecture.md`의 버전 표(FastAPI 0.162.5, Anthropic SDK 2.8.0)를 먼저 시도한다. 그 버전이 설치되지 않으면 설치되는 최신 안정 버전으로 고정하고, `architecture.md`의 버전 표를 실제 설치된 버전으로 고친다.
- 그 밖의 패키지(ORM, pydantic-settings, python-dotenv 등)는 넣지 않는다.

### 3. 가상환경

```bash
uv venv w03_system/.venv
uv pip install -p w03_system/.venv -r w03_system/backend/requirements.txt
```

### 4. 확인용 테스트

`w03_system/backend/tests/test_setup.py`에 아래 세 가지만 확인하는 테스트를 쓴다.

- `backend.core`, `backend.ai`, `backend.api`가 import된다.
- `fastapi`, `anthropic`이 import된다.
- 원본 폴더 `01_참가자_배포용/04_원본데이터/01_corevia/quality/qc_claims_cv.csv`가 존재한다 (프로젝트 루트는 테스트 파일 위치에서 계산한다. 현재 작업 디렉토리에 기대지 않는다).

### 5. 문서

`architecture.md`의 "환경과 명령어" 절을 실제로 실행해 확인한 명령으로 맞춘다. 맨 위의 "아래 명령은 의도이고 …" 안내문은 "2026-11-12 step 0에서 실행해 확인했다"로 바꾼다. 화면(npm) 명령은 아직 확인할 수 없으므로 그대로 두고 "(1-frontend에서 확인)"이라고 적는다.

## Acceptance Criteria

```bash
test -x w03_system/.venv/bin/python
w03_system/.venv/bin/python -m pytest -q w03_system/backend/tests
git check-ignore -q w03_system/.venv
git check-ignore -q w03_system/.env
test -f w03_system/backend/requirements.txt
```

## 검증 절차

1. 위 AC 커맨드를 실행한다.
2. 아키텍처 체크리스트를 확인한다:
   - `3-design/architecture.md`의 디렉토리 구조를 따르는가?
   - `git status --short`에 `.venv`나 `__pycache__` 파일이 나오지 않는가?
   - CLAUDE.md 금지 규칙을 위반하지 않았는가?
3. 결과에 따라 `w03_system/phases/0-backend/index.json`의 step 0을 업데이트한다:
   - 성공 → `"status": "completed"`, `"summary"`에 만든 파일, 고정한 버전, 확정한 테스트 명령을 한 줄로 적는다
   - 수정 3회 시도 후에도 실패 → `"status": "error"`, `"error_message": "구체적 에러 내용"`
   - 네트워크가 막혀 패키지를 설치할 수 없는 경우 등 사용자 개입 필요 → `"status": "blocked"`, `"blocked_reason": "구체적 사유"` 후 즉시 중단

## 금지사항

- 루트 `.gitignore`, `.claude/`, `.codex/`, `.agents/`를 고치거나 지우지 마라. 이유: 대회 기록 키가 들어 있고 CLAUDE.md 금지 규칙이다.
- `01_참가자_배포용/04_원본데이터/`의 파일을 수정하지 마라. 이유: 원본 데이터는 대회 규칙상 수정 금지다.
- `core/`, `ai/`, `api/`에 `__init__.py` 외의 코드를 쓰지 마라. 이유: 각 모듈은 뒤 step이 맡는다.
- `.env` 파일을 만들거나 API 키를 어디에도 적지 마라. 이유: 키는 사용자가 직접 넣는다.
- `frontend/`를 만들거나 npm 명령을 실행하지 마라. 이유: 화면은 다음 phase다.
- git commit을 하지 마라. 이유: 커밋은 실행기가 한다.
