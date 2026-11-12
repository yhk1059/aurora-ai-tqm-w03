# architecture — W03 시스템 아키텍처

> 상태: **v1 (2026-11-12)**. 결정 근거는 `decisions.md`("Streamlit 취소", "아키텍처 v1")에 있다.
> 무엇을 만드는지는 `business-model.md`(객체·규칙·액션, §8 온톨로지)와 `demo-scenarios.md`가 기준이다. 이 문서는 **어디에 어떻게 두는지**만 정한다.

## 디렉토리 구조

```
w03_system/
  backend/
    core/        온톨로지 정의, DB, 원본 적재, 규칙, 액션 실행기
    ai/          Claude 호출, 프롬프트, 출력 형식
    api/         FastAPI 라우트 (얇게)
    tests/       pytest
  frontend/      React 화면 (Vite)
  scenarios/     시연용 모의 입력: 클레임, 회신 문장, 결정, 액션 목록  ← [모의]·[가정] 데이터는 여기에만
  data/          실행 중 생기는 SQLite 파일 (git 제외)
  .gitignore     data/, .env, .venv/, node_modules/, frontend/dist/ 제외
  brain/ phases/ scripts/   (기존)
```

- 원본은 `01_참가자_배포용/04_원본데이터/`에서 **읽기만** 한다. 복사본을 만들지 않는다.
- 루트 `.gitignore`는 고칠 수 없으므로(CLAUDE.md 금지 규칙) `w03_system/.gitignore`를 따로 둔다.

## 패턴

1. **온톨로지가 기준이다.** 객체 타입·속성·관계·액션·상태 전이표·규칙 기준값을 `core/ontology.py` 한 파일에 Python으로 선언한다. 적재·규칙·액션·API·화면은 이 정의를 읽어서 동작하고, 같은 내용을 다른 곳에 다시 쓰지 않는다.
2. **상태는 액션 실행기로만 바뀐다.** 모든 변경은 `core/actions.py`의 실행 함수 하나를 지난다. 여기서 권한·전제 조건·전이표를 검사하고 액션 기록을 남긴다.
3. **판정은 규칙, 설명은 AI.** 불량률·기준 비교·순서 계산은 코드로 하고 결과가 재현된다. AI는 요약·분류·설명·초안만 만들고, 어떤 액션도 직접 실행하지 않는다(R12).
4. **화면은 서버가 준 것만 그린다.** 어떤 버튼을 보여줄지(가능한 액션)도 서버가 정한다. 화면에 규칙을 다시 쓰지 않는다.

## 데이터 흐름

```
원본 CSV ──(적재: 사건에 필요한 행만, 출처·근거 참조 부착)──▶ SQLite
                                                              │
화면 ──조회──▶ API ──▶ core: 객체·관계 + 파생 속성 + 경고 + 가능한 액션 ──▶ 화면
화면 ──액션 실행(이름, 역할, 입력)──▶ API ──▶ 액션 실행기 ──▶ 규칙·자동 처리 ──▶ SQLite + 액션 기록
                                              └─▶ 바뀐 사건 뷰를 그대로 응답
화면 ──AI 요청──▶ API ──▶ ai: 사건 뷰에서 입력 구성 ──▶ Claude ──▶ AI 기록 ──▶ 화면 (사람이 검토 후 액션 입력으로 사용)
```

- 적재는 사건 범위만 한다(`business-model.md` §8-8). 적재한 모든 객체·관계에는 원본 파일과 행 ID가 붙는다.
- 파생 속성(불량률, 해제 예정일, 사건 상태 등)은 저장하지 않고 조회할 때 계산한다.

## 모듈 경계와 인터페이스

| 모듈 | 하는 일 | 하면 안 되는 것 |
|---|---|---|
| `core/ontology.py` | 선언형 정의 | DB·네트워크 접근 |
| `core/db.py` | SQLite 연결, 테이블 4개 생성, 객체·관계 읽기/쓰기 | 규칙 판단 |
| `core/loader.py` | 원본 CSV(`|` 구분, UTF-8) 읽기. 사건이 없을 때 열 수 있는 배치 목록 조회, **사건 열기 때** 고른 배치에서 관계를 따라 필요한 객체·관계만 적재 | 원본 파일 쓰기 |
| `core/rules.py` | R1~R11: 파생 속성 계산, 경고, 자동 처리 판단 | DB 직접 수정 (결과를 실행기에 돌려준다) |
| `core/actions.py` | 액션 실행기, 자동 처리 연쇄, 액션 기록 | FastAPI·AI 호출 |
| `core/view.py` | 사건 뷰 조립 (화면이 한 번에 받는 덩어리) | 상태 변경 |
| `core/scenario.py` | `scenarios/`의 액션 목록을 순서대로 실행 (`actions.execute`만 사용) | DB 직접 수정 |
| `ai/` | 안건 요약, 회신 분류, 재검토 설명, 안내 초안 | `ai_log` 외의 DB 쓰기, 액션 실행 |
| `api/` | HTTP ↔ core·ai 연결, 입력 검증 | 규칙·전이 로직 |
| `frontend/` | 사건 뷰 표시, 액션·AI 요청 전송 | 판정·권한·전이 로직, 상태 복사본 보관 |

`core`는 `api`·`ai`를 import하지 않는다. 그래서 화면과 API 없이 pytest만으로 시연 3건을 끝까지 실행할 수 있다.

**API (전부 `/api` 아래)**
| 메서드·경로 | 역할 |
|---|---|
| `GET /incident` | 사건 뷰: 객체, 관계, 파생 속성, 경고, 작업, 계획 버전, 가능한 액션, 액션·AI 기록. 사건이 없으면 열 수 있는 배치 목록 |
| `POST /actions/{action}` | 본문 = 실행자 역할 + 입력. 실행 후 새 사건 뷰를 반환. 전제 조건 위반은 4xx와 사유 |
| `POST /ai/{task}` | task = 안건 요약 / 회신 분류 / 재검토 설명 / 안내 초안. 결과와 `ai_log` ID 반환 |
| `GET /ontology` | 선언형 정의 그대로 (화면의 "온톨로지" 탭) |
| `POST /scenarios/{name}` | 초기화 후 `scenarios/`의 액션 목록을 순서대로 실행 (시연 출발 상태 만들기) |

**액션 실행기 시그니처 (의도)**
```python
def execute(conn, action: str, actor: str, inputs: dict) -> ActionResult: ...
# 검사 순서: 액션 정의 존재 → actor 권한 → 전제 조건 → 실행 → 자동 처리 연쇄 → 액션 기록
# 하나의 트랜잭션. 중간에 실패하면 아무것도 바뀌지 않는다.
```

## 상태 관리

**SQLite 테이블 4개**
| 테이블 | 내용 |
|---|---|
| `objects` | 타입, ID, 속성(JSON), 상태, 출처, 근거 참조 |
| `links` | 관계 유형, 출발·도착(타입+ID), 출처, 확인 수준, 수량, 수량 근거, 근거 참조, 적용일, 기록일 |
| `action_log` | 순번, 액션, 실행자, 적용일, 입력(JSON), 변경 목록(대상, 이전→이후), 원인 |
| `ai_log` | 순번, task, 모델, 입력, 출력, 연결된 액션 기록 |

- 객체 타입마다 테이블을 만들지 않는다. 온톨로지 정의가 바뀌어도 스키마가 그대로다.
- **현재 적용일**은 사건 객체의 속성이고, 이벤트를 넣는 액션이 그 적용일로 전진시킨다. 실제 시계(`datetime.now()`)는 판단에 쓰지 않는다.
- **초기화** = 빈 DB로 되돌림(사건 없음). 원본 적재는 사건 열기 액션이 한다. **재현** = 액션 목록을 순서대로 다시 실행하면 같은 상태가 나온다.
- 화면(React)은 서버 응답을 그대로 그리고, 화면에만 있는 상태는 "지금 고른 역할", 열린 탭, 입력 중인 폼뿐이다.
- 로그인은 없다. 역할은 화면에서 고르고, 권한은 서버의 액션 정의로 검사한다.

## 기술 스택과 쓰지 않는 것

| 영역 | 사용 | 버전 (2026-11-12 확인, 설치는 첫 step에서 검증) |
|---|---|---|
| 서버 언어 | Python | 3.14.6 |
| 패키지 관리 | uv + `requirements.txt` | — |
| API | FastAPI + uvicorn | 0.162.5 |
| 저장 | SQLite (표준 라이브러리 `sqlite3`) | — |
| AI | Anthropic Python SDK | 2.8.0 |
| 테스트 | pytest | — |
| 화면 | React + TypeScript + Vite | 19.3.1 / 8.3.8 (Node 22.23.3, npm) |
| 스타일 | Tailwind CSS | 4.3.5 |

**AI 호출**
- 모델 `claude-opus-5-5`. 키는 환경변수 `ANTHROPIC_API_KEY`(`w03_system/.env`, 커밋하지 않음).
- 회신 분류는 구조화 출력으로 "작업 유형의 허용 결과 중 하나 + 근거 문장"만 받는다. 허용 목록은 온톨로지 정의에서 가져온다. 맞는 것이 없으면 "해석 불가"다.
- 응답의 `stop_reason`을 확인한다(거절·길이 초과를 정상 결과로 쓰지 않는다).
- **키가 없으면** AI 버튼만 비활성화하고 "키 없음"을 표시한다. 규칙·액션은 그대로 동작하고, 회신 반영은 담당자가 허용 결과를 직접 고른다. 가짜 AI 응답을 만들지 않는다.
- SDK 호출 방법은 추측하지 않고 구현 step에서 공식 문서를 확인한다.

**쓰지 않는 것**
| 쓰지 않는 것 | 이유 |
|---|---|
| Streamlit | 2026-11-12 취소 (`decisions.md`) |
| Next.js, 서버 렌더링 | 로컬 한 화면 앱이고 서버는 FastAPI가 맡는다. 서버가 둘이 된다 |
| ORM (SQLAlchemy 등) | 테이블 4개에 과하다 |
| 그래프 DB, OWL/RDF | 온톨로지 B안 결정 |
| 화면 전역 상태 라이브러리 (Redux 등) | 화면은 상태를 보관하지 않는다 |
| 로그인·권한 시스템, 실제 외부 발송 | 스코핑 ⑥ 제외 |
| AI 에이전트 루프, 멀티 에이전트 | AI는 단발 호출 4종으로 충분하다 |

## 환경과 명령어

> 2026-11-12 step 0에서 실행해 확인했다. 의존성 버전은 `w03_system/backend/requirements.txt`에 고정했다(fastapi 0.162.5, uvicorn 0.54.0, anthropic 2.8.0, pytest 9.2.0, httpx 0.28.1).

```bash
# 서버 준비 (프로젝트 루트에서). -p 3.14를 빼면 uv가 다른 Python(3.13)을 고를 수 있다
uv venv -p 3.14 w03_system/.venv && uv pip install -p w03_system/.venv -r w03_system/backend/requirements.txt

# 서버 실행 (backend/api/main.py는 api step에서 만든다 — 그때 확인)
w03_system/.venv/bin/uvicorn backend.api.main:app --app-dir w03_system --reload

# 화면 준비·실행 (1-frontend에서 확인)
npm --prefix w03_system/frontend install
npm --prefix w03_system/frontend run dev

# 검증 (pytest 설정: w03_system/pytest.ini, pythonpath = w03_system)
w03_system/.venv/bin/python -m pytest -q w03_system/backend/tests
npm --prefix w03_system/frontend run build    # 타입 검사 + 빌드 (1-frontend에서 확인)
```

**테스트 전략**
- 규칙 단위 테스트 + **시연 3건을 액션 목록으로 끝까지 실행하는 테스트 3개**. 기대값은 `demo-scenarios.md`의 숫자다(불량률 11.9%·11.6%, 120·128일 관찰해제, 재공급 순서 C-103 → C-102 → C-101 → C-104 → C-108, 미확정 800 EA 판정 불변, C-105 하한 11,765 EA).
- API 테스트: 조회·액션 실행이 core와 같은 결과를 내는지.
- 테스트는 AI를 호출하지 않는다.
- 화면은 자동 테스트 없이 타입 검사·빌드 통과로 검증하고, 동작은 브라우저에서 시연 순서대로 확인한다.

**구현 순서 원칙:** 서버(core → api)를 화면 없이 먼저 완성하고 테스트로 검증한 뒤 화면을 만든다.
