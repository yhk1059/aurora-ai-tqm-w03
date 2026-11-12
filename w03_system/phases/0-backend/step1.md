# Step 1: ontology

## 읽어야 할 파일

먼저 아래 파일들을 읽고 과제와 설계 의도를 파악하라:

- `/CLAUDE.md`
- `/w03_system/brain/status.md`
- `/w03_system/brain/3-design/architecture.md` (패턴 1 "온톨로지가 기준이다", 모듈 경계)
- `/w03_system/brain/3-design/business-model.md` — **전체를 꼼꼼히.** 특히 §4(상태), §5·§5-1(규칙과 기준값), §8(온톨로지 4칸)
- `/w03_system/brain/3-design/assumptions.md` (A-01 ~ A-17)
- `/w03_system/brain/3-design/demo-scenarios.md` (정의가 시연을 다 덮는지 확인용)
- `/w03_system/backend/` (step 0에서 만든 골격), `/w03_system/pytest.ini`

## 작업

`w03_system/backend/core/ontology.py` 한 파일에 업무모델을 **선언형 정의**로 옮긴다. 이 파일은 데이터 정의와 그것을 읽는 작은 조회 함수만 가진다. 뒤 step의 적재·규칙·액션·API·화면이 모두 이 정의를 읽어 동작하므로, 같은 내용(상태 이름, 허용 결과, 기준값)이 다른 파일에 다시 적히지 않게 하는 것이 목적이다.

### 담아야 할 것

| 정의 | 내용 | 기준 문서 |
|---|---|---|
| 출처 | `원본` / `도출` / `가정` / `모의` / `시스템` | §8-4 |
| 확인 수준 | `확인` / `미확인` / `확인요청중` / `회신확인` / `영향없음` | §4-2 |
| 역할 | 액션을 실행하는 주체 3개: 품질 담당자 / 품질위원회 / SCM. 회신만 하는 부서(물류, 영업, 영업 임원, 생산)는 작업의 담당 부서 값으로 따로 둔다 | §6, §8-5 |
| 객체 타입 11개 | 타입마다 저장 속성, 파생 속성(어느 규칙이 계산하는지), 상태를 갖는지 | §2, §8-2, §8-3 |
| 관계 17개 | 방향(출발 타입 → 도착 타입), 기본 출처, 확인 수준·수량을 쓰는지 | §8-4 |
| 상태 전이표 5종 | 배치 판정 상태, 클레임 상태, 작업 상태, 재공급 계획 상태, `SHIPPED_TO` 확인 수준 | §4-1 ~ §4-6 |
| 사람 액션 9개 | 실행 가능한 역할, 입력 필드(이름·형식·필수 여부), 전제 조건 설명, 효과 설명, 관련 규칙 | §8-5 |
| 자동 처리 | 관찰 해제, 관찰 복귀, 판정 재계산, 부분회수 완료 판정, 재공급 계획 재계산, 수주 급감 확인 요청 + 재공급 요청 자동 완료, 결과 통보 생성 | §8-5 |
| 작업 유형 7개 | 담당 부서, 허용 결과 목록, 결과별 효과 설명 | §8-5 "회신 반영" 표 |
| 규칙 R1 ~ R12 | ID, 한 줄 설명, 자리(파생 속성 / 액션 효과 / 전제 조건 / 자동 처리 / 권한 원칙), 기준값·출처·근거 참조 | §5, §5-1, §8-5 "규칙의 자리" |
| 사건 상태 5개 | 이름과 도출 조건 설명 | §4-5 |

### 지켜야 할 값

- **상태·역할·출처·확인 수준·작업 유형·허용 결과의 값은 문서의 한국어 문자열을 그대로 쓴다** (예: `"기준초과(미상신)"`, `"회수진행"`, `"출하 확인"`). 화면이 이 값을 그대로 보여준다.
- **액션과 역할에는 영문 key를 따로 둔다.** URL(`POST /api/actions/{action}`)과 요청 본문에 쓰인다. 아래 key를 그대로 쓴다.

| 액션 (한국어 이름) | key | 실행 역할 key |
|---|---|---|
| 사건 열기 | `open_incident` | `quality_owner` |
| 클레임 등록 | `register_claim` | `quality_owner` |
| 클레임 판정 반영 | `resolve_claim` | `quality_owner` |
| 보도 등록 | `register_news` | `quality_owner` |
| 안건 상신 | `submit_agenda` | `quality_owner` |
| 위원회 결정 입력 | `committee_decision` | `quality_committee` |
| 회신 반영 | `apply_reply` | `quality_owner` |
| 재공급 계획 결정 입력 | `plan_decision` | `scm` |
| 초기화 | `reset` | 모든 역할 |

- **모든 액션의 입력에 `applied_date`(적용일, `YYYY-MM-DD`, 필수)를 둔다.** `reset`만 예외다. 사건의 현재 적용일은 이 값으로 전진한다(§4-5).
- **배치 판정 상태 9개:** `정상`, `관찰`, `관찰해제`, `기준초과(미상신)`, `상신중`, `회수진행`, `부분회수`, `조사계속`, `재상신 후보`. 전이표는 §4-1의 그림에 있는 화살표만 넣는다. 사건 열기에서 배치는 `정상 → 관찰` 또는 `정상 → 기준초과(미상신)`으로 간다.
- **재공급 계획 상태 4개:** `초안`, `확정`, `기각`, `대체됨` (§4-4).
- **규칙 기준값(§5-1)** 은 숫자와 출처를 함께 둔다: R2 `10%` [원본 `quality_policy_cv`], R6 `90일` [가정 A-07], R6-1 `90일` [가정 A-12], R10 여유 능력 계산식 `최근 6개월 월평균 생산 ÷ 가동률 × (1 − 가동률)` [가정 A-04], R10-1 `−20% 이하, 2개월 연속` [가정 A-13], 작업 기한 `7일` [가정 A-17].
- 작업 유형별 허용 결과는 §8-5 표와 같아야 한다. 재공급 요청은 허용 결과가 없다(자동 완료). AI 분류용 값 `해석 불가`는 허용 결과가 **아니다** (회신 반영 액션이 받지 않는다). 따로 상수로 둔다.

### 인터페이스 (의도)

정의를 담는 방식(dataclass, TypedDict, 일반 dict)은 재량이다. 아래 조회 함수는 이 이름으로 제공한다.

```python
def to_dict() -> dict:
    """정의 전체를 JSON으로 직렬화할 수 있는 dict로 돌려준다 (GET /api/ontology와 화면의 온톨로지 탭이 쓴다)."""

def can_transition(kind: str, from_state: str, to_state: str) -> bool:
    """kind = 'batch' | 'claim' | 'task' | 'plan' | 'shipped_to'. 전이표에 있는 전이만 True."""

def action_def(key: str) -> dict | None
def task_type_def(name: str) -> dict | None      # 허용 결과 포함
def rule_def(rule_id: str) -> dict | None         # 기준값·출처 포함
```

### 테스트

`w03_system/backend/tests/test_ontology.py`에 정의의 **일관성**을 확인하는 테스트를 쓴다.

- 객체 타입 11개, 관계 17개, 사람 액션 9개, 작업 유형 7개가 있다.
- 관계의 출발·도착 타입이 모두 정의된 객체 타입이다 (`TARGETS`처럼 대상이 여러 타입인 관계는 목록으로 표현한다).
- 전이표의 모든 상태가 그 종류의 상태 목록에 있다. 어디서도 도달할 수 없는 상태가 없다(시작 상태 제외).
- 액션의 실행 역할이 역할 목록에 있고, 모든 액션(초기화 제외)에 `applied_date` 입력이 있다.
- 액션·자동 처리·파생 속성이 가리키는 규칙 ID가 모두 규칙 정의에 있다. 출처가 `가정`인 기준값은 `A-xx` 참조를 갖는다.
- `can_transition("batch", "관찰해제", "관찰")`은 True, `can_transition("batch", "회수진행", "관찰")`은 False.
- `to_dict()` 결과가 `json.dumps(..., ensure_ascii=False)`로 직렬화된다.

## Acceptance Criteria

```bash
w03_system/.venv/bin/python -m pytest -q w03_system/backend/tests/test_ontology.py
w03_system/.venv/bin/python -m pytest -q w03_system/backend/tests
! grep -nE "^(import|from) +(sqlite3|fastapi|anthropic|httpx|urllib|requests)" w03_system/backend/core/ontology.py
```

## 검증 절차

1. 위 AC 커맨드를 실행한다.
2. 아키텍처 체크리스트를 확인한다:
   - `ontology.py`가 DB·네트워크·파일에 접근하지 않는가?
   - `business-model.md` §8의 객체·관계·액션·작업 유형 표와 한 줄씩 대조했을 때 빠진 것이 없는가?
   - 정의에 없는 것을 새로 만들어 넣지 않았는가? (문서에 없는 상태·액션·규칙)
3. 결과에 따라 `w03_system/phases/0-backend/index.json`의 step 1을 업데이트한다:
   - 성공 → `"status": "completed"`, `"summary"`에 정의의 구조(주요 이름, 조회 함수), 액션·역할 key를 한 줄로 적는다
   - 수정 3회 시도 후에도 실패 → `"status": "error"`, `"error_message": "구체적 에러 내용"`
   - 문서끼리 어긋나 정의를 정할 수 없는 경우 → `"status": "blocked"`, `"blocked_reason"`에 어긋난 두 곳을 적고 즉시 중단

## 금지사항

- 규칙의 **계산 로직**을 이 파일에 쓰지 마라. 이유: 계산은 `core/rules.py`(step 3)가 맡는다. 여기에는 기준값과 설명만 둔다.
- 액션의 실행 코드를 쓰지 마라. 이유: `core/actions.py`(step 4·5)가 맡는다.
- 문서에 없는 상태·액션·관계를 추가하지 마라. 이유: 온톨로지 정의는 `business-model.md`가 기준이고, 다르면 화면과 제출 설명이 어긋난다.
- `business-model.md` 등 brain 문서를 고치지 마라. 이유: 정의가 문서와 다르면 문서가 아니라 코드를 맞춘다. 문서 자체가 모순이면 blocked로 멈춘다.
- `01_참가자_배포용/04_원본데이터/`의 파일을 수정하지 마라. 이유: 원본 데이터는 대회 규칙상 수정 금지다.
- 기존 테스트를 깨뜨리지 마라.
