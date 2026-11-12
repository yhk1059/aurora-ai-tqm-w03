# Step 7: ai

## 읽어야 할 파일

먼저 아래 파일들을 읽고 과제와 설계 의도를 파악하라:

- `/CLAUDE.md`
- `/w03_system/brain/status.md`
- `/w03_system/brain/3-design/architecture.md` (패턴 3, 모듈 경계의 `ai/`, "AI 호출" 절)
- `/w03_system/brain/3-design/business-model.md` §6(역할 분담: AI가 하는 일 4가지), §8-5(회신 반영의 허용 결과, "AI는 어떤 액션도 직접 실행하지 않는다"), R3, R12
- `/w03_system/brain/3-design/demo-scenarios.md` ("AI" 열: 단계마다 AI가 무엇을 내는지)
- `/w03_system/brain/1-brief/assignment.md` §2 평가 기준("AI의 실제 역할"), §4 "운영 시스템에서 보여줄 관점"
- `/w03_system/backend/core/view.py`, `ontology.py`, `db.py`(`append_ai_log`, `list_ai_log`), `loader.py`(`read_text_source`)
- `/w03_system/backend/requirements.txt` (설치된 Anthropic SDK 버전)

이전 step에서 만들어진 코드를 꼼꼼히 읽고, 설계 의도를 이해한 뒤 작업하라.

**SDK 사용법은 추측하지 마라.** 코드를 쓰기 전에 Claude API 사용법을 확인한다: `claude-api` 스킬이 있으면 그것을 먼저 읽고, 없으면 공식 문서(platform.claude.com/docs) 또는 `w03_system/.venv`에 설치된 `anthropic` 패키지의 소스·타입 정의를 읽는다. 확인할 것: 메시지 생성 호출 형식, 구조화 출력(JSON 스키마로 출력 형식을 고정하는 방법), 응답의 `stop_reason` 값 종류, 모델 ID `claude-opus-5-5`에서 쓸 수 있는 파라미터.

## 작업

`w03_system/backend/ai/` 아래에 AI 단발 호출 4종을 만든다. AI는 **요약·분류·설명·초안만** 만든다. 판정은 이미 규칙이 했고, AI 출력은 사람이 검토한 뒤 액션의 입력으로 쓴다.

### 파일 (의도)

```
backend/ai/
  client.py     # 키 읽기, 사용 가능 여부, Claude 호출 한 곳, stop_reason 확인
  tasks.py      # task 4종: 입력 구성 → 호출 → 결과 정리 → ai_log 기록
  prompts.py    # 시스템 프롬프트와 task별 지시문
```

### 인터페이스

```python
MODEL = "claude-opus-5-5"

def is_available() -> bool:
    """ANTHROPIC_API_KEY가 있으면 True. 환경변수를 먼저 보고, 없으면 w03_system/.env 파일의 같은 이름을 읽는다."""

@dataclass
class AiResult:
    ok: bool
    task: str
    output: dict | None       # task별 형식 (아래)
    log_id: int | None        # ai_log 순번
    error: str | None         # 'no_key' | 'refusal' | 'max_tokens' | 'api_error' | 'invalid_output'
    message: str | None       # 사람이 읽는 한국어 설명

def run_task(conn, task: str, params: dict, *, client=None) -> AiResult:
    """task = 'agenda_summary' | 'classify_reply' | 'review_explanation' | 'notice_draft'.
    client를 넘기면 그것으로 호출한다 (테스트용 주입). 없으면 실제 SDK 클라이언트를 만든다."""
```

| task | params | 입력으로 넣는 것 (사건 뷰에서 뽑는다) | output |
|---|---|---|---|
| `agenda_summary` (안건 요약) | `batch_ids` | 배치별 불량률·기준·초과일·미상신 경과일, 경고, 미확인 고객, 정책 원문(`quality_policy_cv.md`), 이전 거절 결정이 있으면 그 사유와 이후 새 근거 | `summary`(글), `evidence`(근거 목록), `options`(대안: 전면 회수 / 부분 회수 / 조사계속과 각각의 영향), `uncertainties`(불확실성 목록) |
| `classify_reply` (회신 분류) | `task_id`, `reply_text` | 작업 유형, 대상, **그 유형의 허용 결과 목록**(`ontology.task_type_def`), 회신 원문 | `result`(허용 결과 중 하나 또는 `해석 불가`), `evidence_sentence`(회신 원문에서 뽑은 근거 문장), `note` |
| `review_explanation` (재검토 설명) | 없음 | 가장 최근 사람 액션과 뒤따른 자동 처리의 변경 목록, 적용된 규칙과 기준값, 변경 전후 판정 상태. 보도면 보도 원문 | `explanation`(무엇이 들어왔고, 무엇이 바뀌었거나 왜 유지됐는지), `conclusion`(`유지` / `변경`) |
| `notice_draft` (고객 안내 초안) | 없음 | 회수 배치, 확정된 안내 대상 고객(없으면 후보), 확정 사실만 | `draft`(글), `recipients`(고객 ID 목록) |

### 핵심 규칙

- **AI 모듈은 액션을 실행하지 않는다.** `backend.core.actions`를 import하지 않는다. DB 쓰기는 `db.append_ai_log` 하나뿐이다(커밋 포함. 이 모듈이 자기 기록을 커밋한다).
- **키가 없으면** 호출하지 않고 `AiResult(ok=False, error="no_key", …)`를 돌려준다. **가짜 응답을 만들지 않는다.** `ai_log`에도 남기지 않는다.
- **회신 분류는 구조화 출력**으로 받는다. `result`의 허용 값은 그 작업 유형의 허용 결과 + `해석 불가`이고, 이 목록은 호출할 때마다 `ontology`에서 만든다(코드에 다시 적지 않는다). 응답의 `result`가 목록에 없으면 `invalid_output`으로 처리한다.
- **`stop_reason`을 확인한다.** 정상 종료가 아니면(거절, 길이 초과 등) 결과로 쓰지 않고 `ok=False`와 해당 `error`를 돌려준다. 이 경우에도 `ai_log`에는 입력과 받은 내용을 남긴다(무슨 일이 있었는지 기록).
- **`ai_log`에 실제 입력과 출력을 그대로 남긴다:** task, 모델, 보낸 입력(시스템 프롬프트와 사용자 메시지), 받은 출력, 성공 여부. 이유: "AI의 실제 역할"이 평가 항목이고 기록 탭이 이것을 보여준다.
- **프롬프트에 넣을 원칙:** 주어진 사실만 쓴다. 숫자를 새로 계산하거나 추정하지 않는다. 판정을 바꾸거나 결정을 권고로 확정하지 않는다("회수해야 합니다"가 아니라 근거·대안·불확실성을 정리한다). 원본에서 확인한 것과 가정·모의를 구분해 쓴다. 원인이 확인되지 않은 것은 "미확인"이라고 쓴다. 한국어로 쓴다.
- 입력은 **사건 뷰와 `rules.py` 결과**에서 뽑는다. AI에게 원본 CSV를 통째로 넘기지 않는다.
- 에이전트 루프, 도구 호출, 멀티 에이전트를 만들지 않는다. task마다 호출 한 번이다.
- API 호출 예외(네트워크, 인증, 한도)는 잡아서 `api_error`로 돌려준다. 서버가 죽지 않게 한다.

### 테스트

`w03_system/backend/tests/test_ai.py`. **네트워크를 쓰지 않는다.** 호출 부분은 주입한 가짜 `client`로 대신한다(가짜 클라이언트는 테스트 파일 안에만 둔다).

- 키가 없을 때(환경변수를 지우고 `.env` 경로를 빈 임시 폴더로 돌린 상태): `is_available()` False, 네 task 모두 `error="no_key"`, `ai_log`에 행이 생기지 않는다.
- `classify_reply`의 입력: 출하처 확인 작업이면 허용 값이 `출하 확인`, `영향없음`, `확인 불가`, `해석 불가` 네 개다. 수주 급감 확인 작업이면 `순서 유지`, `우선 공급 요청`, `해석 불가`다.
- 가짜 클라이언트가 정상 응답을 주면: `ok=True`, `output` 형식이 표와 같고, `ai_log`에 task·모델·입력·출력이 남는다.
- 가짜 클라이언트가 허용 목록에 없는 `result`를 주면 `invalid_output`.
- 가짜 클라이언트가 거절 또는 길이 초과 `stop_reason`을 주면 `ok=False`이고 `output`을 쓰지 않는다.
- 가짜 클라이언트가 예외를 내면 `api_error`이고 예외가 밖으로 나오지 않는다.
- `agenda_summary`의 입력에 불량률, 기준 10%, 미상신 경과일, C-105 미확인이 들어 있다(시연 1-2 상태에서).
- `review_explanation`의 입력에, 보도 등록 뒤에는 R3과 "상태 변화 없음"이, 2-2a 뒤에는 R6-2·R7-1과 확정 시 불량률이 들어 있다.
- `run_task` 전후로 `objects`·`links`·`action_log`가 같다(바뀌는 것은 `ai_log`뿐).

실제 API 호출은 자동 테스트에 넣지 않는다. 대신 **키가 있을 때만** 손으로 한 번 확인한다: `is_available()`이 True면 시연 1의 1-2 상태에서 `agenda_summary`를 한 번 호출해 `ok=True`인지 보고, 결과를 step summary에 "실제 호출 확인함"으로 적는다. 키가 없으면 "실제 호출 미확인(키 없음)"이라고 적는다. **키가 없다는 이유로 blocked 처리하지 않는다.**

## Acceptance Criteria

```bash
w03_system/.venv/bin/python -m pytest -q w03_system/backend/tests/test_ai.py
w03_system/.venv/bin/python -m pytest -q w03_system/backend/tests
! grep -rnE "backend\.core\.actions|from \.\.core import actions|from \.\.core\.actions|import actions" w03_system/backend/ai
! grep -rnE "^(import|from) +(fastapi|anthropic)|backend\.(api|ai)" w03_system/backend/core
! grep -rnE "sk-an[t]-" w03_system --include=*.py --include=*.json --include=*.md --include=*.txt --include=*.example
```

## 검증 절차

1. 위 AC 커맨드를 실행한다.
2. 아키텍처 체크리스트를 확인한다:
   - `ai/`가 액션을 실행하지 않고, DB 쓰기가 `ai_log`뿐인가?
   - `core/`가 `ai/`를 import하지 않는가?
   - 키가 없을 때 가짜 응답을 만들지 않는가?
   - 허용 결과 목록을 `ontology`에서 가져오는가?
   - `stop_reason`을 확인하는가?
   - 프롬프트가 AI에게 판정이나 결정을 시키지 않는가(R12)?
3. 결과에 따라 `w03_system/phases/0-backend/index.json`의 step 7을 업데이트한다:
   - 성공 → `"status": "completed"`, `"summary"`에 `run_task` 시그니처, task 이름 4개와 output 키, 오류 코드, 실제 호출 확인 여부를 한 줄로 적는다
   - 수정 3회 시도 후에도 실패 → `"status": "error"`, `"error_message": "구체적 에러 내용"`
   - SDK 사용법을 문서·패키지 소스 어디서도 확인할 수 없는 경우 → `"status": "blocked"`, `"blocked_reason": "구체적 사유"` 후 즉시 중단

## 금지사항

- API 키를 코드·테스트·문서·로그에 적지 마라. `.env` 파일을 만들거나 고치지 마라. 이유: 키는 사용자가 직접 넣고, 저장소에 남으면 안 된다.
- 키가 없을 때 미리 써 둔 문장을 AI 결과처럼 돌려주지 마라. 이유: 가짜 AI 응답은 실행 증거가 되지 못한다(`architecture.md`).
- AI 출력으로 상태를 바꾸거나 액션을 실행하지 마라. 이유: R12. AI는 입력을 준비하고 실행은 사람이 한다.
- 테스트에서 실제 API를 호출하지 마라. 이유: 테스트는 키와 네트워크 없이 통과해야 한다(`architecture.md` 테스트 전략).
- 모델 ID를 `claude-opus-5-5` 외의 것으로 바꾸지 마라. 이유: `architecture.md`에서 정했다. 이 모델에서 쓸 수 없는 파라미터가 있으면 파라미터를 빼라.
- LangChain 등 프레임워크나 패키지를 추가하지 마라. 이유: 단발 호출 4종에 과하다. Anthropic SDK만 쓴다.
- `core/`의 파일을 고치지 마라. 이유: 이 step의 범위는 `ai/`다. 뷰에 필요한 정보가 빠져 있으면 `ai/` 안에서 `rules.py`·`db.py`를 읽어 보충한다.
- `01_참가자_배포용/04_원본데이터/`의 파일을 수정하지 마라. 이유: 원본 데이터는 대회 규칙상 수정 금지다.
- 기존 테스트를 깨뜨리지 마라.
