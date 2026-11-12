# Step 4: actions-judgment

## 읽어야 할 파일

먼저 아래 파일들을 읽고 과제와 설계 의도를 파악하라:

- `/CLAUDE.md`
- `/w03_system/brain/status.md`
- `/w03_system/brain/3-design/architecture.md` (패턴 2 "상태는 액션 실행기로만 바뀐다", 액션 실행기 시그니처, 상태 관리)
- `/w03_system/brain/3-design/business-model.md` §4(상태), §5(규칙), §8-4(관계 속성), §8-5(액션·자동 처리·액션 기록), §8-6
- `/w03_system/brain/3-design/demo-scenarios.md` (시연 1의 1-1 ~ 1-3·1-7, 시연 2의 2-1 ~ 2-2b, 시연 3의 3-1 ~ 3-2·3-5)
- `/w03_system/brain/3-design/assumptions.md` (A-05, A-08, A-09, A-16, A-17)
- `/w03_system/backend/core/ontology.py`, `db.py`, `loader.py`, `rules.py`
- `/w03_system/backend/tests/conftest.py`, `/w03_system/backend/tests/test_rules.py` (상태를 손으로 만든 방식 참고)

이전 step에서 만들어진 코드를 꼼꼼히 읽고, 설계 의도를 이해한 뒤 작업하라.

## 작업

`w03_system/backend/core/actions.py`를 만든다. 이 step은 **실행기 뼈대 + 판정까지의 액션 7개 + 판정 자동 처리**를 맡는다. 회신 반영(`apply_reply`), 재공급 계획 결정(`plan_decision`), 재공급 계획 자동 처리는 다음 step이 같은 파일에 더한다. 그래서 액션 등록과 자동 처리 연쇄는 **뒤에서 항목을 추가하기 쉬운 구조**로 만든다.

### 1. 실행기

```python
class ActionError(Exception):
    """code: 'unknown_action' | 'forbidden' | 'invalid_input' | 'precondition'. message: 사람이 읽는 한국어 사유."""

@dataclass
class ActionResult:
    seq: int                 # 이 액션의 action_log 순번
    auto_seqs: list[int]     # 뒤따른 자동 처리의 순번들
    changes: list[dict]      # 이 액션과 자동 처리가 바꾼 것 전체 (대상, 필드, 이전, 이후, 규칙)
    created: list[dict]      # 새로 만든 객체 (타입, ID)

def execute(conn, action: str, actor: str, inputs: dict) -> ActionResult: ...

def available_actions(conn, actor: str) -> list[dict]:
    """지금 이 역할이 실행할 수 있는 액션과 그 대상. 화면 버튼의 근거다.
    예: {'action': 'submit_agenda', 'label': '안건 상신', 'targets': {'batch_ids': ['B-02-2602-01', 'B-02-2603-01']}}"""
```

**검사와 실행 순서 (바꾸지 마라):**
1. 액션 정의가 `ontology`에 있는가 → 없으면 `unknown_action`
2. `actor`가 그 액션의 실행 역할인가 → 아니면 `forbidden`
3. 입력 형식: 필수 필드, `applied_date` 형식, **`applied_date`가 사건의 현재 적용일보다 빠르지 않은가** → 아니면 `invalid_input`
4. 전제 조건 → 아니면 `precondition`
5. 실행: 사건의 현재 적용일을 `applied_date`로 전진 → 액션의 효과 → `action_log`에 한 줄
6. 자동 처리 연쇄: 더 바뀔 것이 없을 때까지 반복. 자동 처리 하나마다 `action_log`에 따로 한 줄 (실행자 `시스템`, 원인에 규칙 ID와 앞선 액션 순번)
7. 커밋

**핵심 규칙:**
- **액션 하나 = 트랜잭션 하나.** 1 ~ 6 중 어디서든 실패하면 롤백하고, DB는 호출 전과 완전히 같아야 한다 (`action_log`에도 남지 않는다).
- **모든 상태 변경은 `ontology.can_transition()`을 통과해야 한다.** 통과하지 못하는 전이를 하려 하면 예외를 낸다(구현 오류를 드러내기 위해서다).
- **모든 변경은 `changes`에 이전 → 이후 값과 규칙 ID로 남는다.** 기록 없이 `db.update_object`를 부르는 경로가 없어야 한다.
- **ID는 결정적이다.** 사건 `INC-001`, 작업 `T-001`…, 결정 `DEC-001`…, 이벤트 `EV-001`…, 모의 클레임 `QC-M-001`…처럼 종류별로 1부터 센다. 시각·난수·uuid를 쓰지 않는다. 이유: 같은 액션 목록을 다시 실행하면 같은 상태와 같은 ID가 나와야 한다.
- 실제 시계를 쓰지 않는다. 날짜는 전부 `applied_date`에서 온다.
- 판단은 `rules.py`에 묻는다. 불량률·해제 조건을 이 파일에서 다시 계산하지 않는다.
- 사건은 한 번에 하나만 있다.

### 2. 사람 액션 7개

입력 필드 이름은 `ontology.py`의 액션 정의를 따른다(아래와 다르면 온톨로지 쪽이 기준이다).

| 액션 | 입력 | 전제 조건 | 효과 |
|---|---|---|---|
| `open_incident` | `batch_id` | 사건이 없음. 그 배치가 `loader.openable_batches()`에 있음 | ① `loader.load_incident_scope` ② 사건 `INC-001` 생성(담당자, 개시일 = 현재 적용일 = `applied_date`, 기점 로트) ③ 적재된 배치 전부에 `PART_OF`(속성: 묶인 이유 = `클레임` 또는 `로트 공유(R4)`) ④ R8: `rules.unconfirmed_exposures()`마다 `SHIPPED_TO` 줄 생성(출처 `도출`, 확인 수준 `미확인`, 수량 없음, 수량 근거 `없음`, 근거 참조 = 클레임 ID들) → **고객당 하나의** 출하처 확인 작업(담당 물류, `TARGETS` = 그 고객의 미확인 줄 전부) → 그 줄들 `미확인 → 확인요청중` ⑤ R5: QC `보류`인데 출하 줄이 있는 배치가 있으면 출하 경위 확인 작업 **하나**(담당 생산·물류, `TARGETS` = 해당 배치들, 근거에 R5-1 경고 포함) |
| `register_claim` | `batch_id`, `customer_id`, `qty`, `claim_date`, `status`(`접수` 또는 `확정`), `claim_type`(선택) | 배치가 사건에 묶여 있음 | 클레임 생성(출처 `모의`, 확정이면 불량 확정 참 + 확정일 = `applied_date`), `CLAIMED_ON`·`CLAIMED_BY`·`CLAIMED_LOT`(기점 로트), 이벤트(유형 `클레임 접수`, 발생일 = `claim_date`, 적용일) + `TRIGGERS`. 그 고객이 그 배치의 `SHIPPED_TO`에 없으면 `open_incident`의 ④와 같은 처리 |
| `resolve_claim` | `claim_id`, `result`(`확정` 또는 `기각`) | 클레임이 미확정(`접수`·`조사중`) | 클레임 상태 변경. 확정이면 불량 확정 참 + 확정일 = `applied_date` |
| `register_news` | `content`, `source_ref`(원본 경로), `occurred_date`(선택. 원본에 발생일이 없으면 비운다) | 사건이 있음 | 이벤트(유형 `언론 보도`) + `TRIGGERS`. **상태는 아무것도 바꾸지 않는다(R3).** 액션 기록의 원인에 재검토 기록을 남긴다: 배치별 판정 상태(보도 전 = 보도 후), 결론 유지 근거(R3 규칙 문구와 출처 `quality_policy_cv`) |
| `submit_agenda` | `batch_ids`(1개 이상), `summary`(선택: 안건 요약 글), `ai_log_id`(선택) | 모든 배치가 `기준초과(미상신)` 또는 `재상신 후보` | 배치 → `상신중` |
| `committee_decision` | `batch_ids`, `result`(`승인` / `조건부` / `거절`), `reason`(거절이면 필수, 빈 문자열 불가) | 모든 배치가 `상신중` | 결정 생성(유형 `회수 범위`, 결정권자 품질위원회, 결과, 사유, 적용일, 출처 `모의`) + `DECIDES`(배치마다). **승인** → `회수진행` + 안내 대상 결정 작업(담당 영업, 속성에 후보를 "회수 배치 고객"과 "관찰·해제 배치 고객"으로 나눠 담는다, R9-1). **조건부** → `부분회수` + 같은 작업. **거절** → `조사계속` + 원인 조사 작업(담당 품질·생산, `TARGETS` = 배치들) |
| `reset` | 없음 | 없음 | `db.reset`. 사건이 없는 빈 DB가 된다 |

- 작업을 만들 때: 상태 `열림`, 기한 = `applied_date` + 7일(A-17), `CREATES`(결정 또는 규칙 → 작업), `TARGETS`.
- `summary`가 없어도 상신할 수 있어야 한다. 이유: AI 키가 없어도 업무는 진행돼야 한다.
- 재공급 계획 초안과 재공급 요청 작업은 **이 step에서 만들지 않는다.** 다음 step이 자동 처리로 더한다.

### 3. 자동 처리 (이 step의 범위)

사람 액션이 끝날 때마다, 사건에 묶인 배치 각각에 대해 `rules.target_batch_state()`를 물어 바뀔 상태가 있으면 바꾼다. 더 바뀔 것이 없을 때까지 반복한다.

| 자동 처리 이름 (`action_log.action`) | 전이 | 규칙 |
|---|---|---|
| `판정 재계산` | `정상 → 관찰`, `정상·관찰·관찰해제 → 기준초과(미상신)`, `조사계속 → 재상신 후보` | R2, R4, R7, R9 |
| `관찰 해제` | `관찰 → 관찰해제` | R6, R6-1 |
| `관찰 복귀` | `관찰해제 → 관찰` | R6-2, R7 |
| `부분회수 완료 판정` | `부분회수 → 회수진행` | §8-5 |

- 사건 열기 직후에도 이 연쇄가 돈다. 그래서 합격 배치는 `정상 → 관찰 → 관찰해제` 두 줄이 기록에 남는다(근거: 마지막 출하 후 120·128일 무클레임).
- 반복 횟수에 안전 상한을 두고, 넘으면 예외를 내 롤백한다(무한 전이 방지).

### 4. `available_actions`

전제 조건 검사와 **같은 코드**를 써서 답한다(버튼이 보이는데 누르면 거부되는 일이 없게). 이 step의 액션에 대해:
- 사건이 없으면: `open_incident`(대상 = 열 수 있는 배치 목록)만.
- `quality_owner`: `register_claim`, `register_news`, `submit_agenda`(상신할 수 있는 배치가 있을 때, 그 배치 목록), `resolve_claim`(미확정 클레임이 있을 때, 그 목록).
- `quality_committee`: `committee_decision`(상신중 배치가 있을 때, 그 목록).
- `reset`은 모든 역할.

### 테스트

`w03_system/backend/tests/test_actions_judgment.py`. DB는 `:memory:`, 사건은 `execute(conn, "open_incident", "quality_owner", {"batch_id": "B-02-2602-01", "applied_date": "2026-07-01"})`로 연다.

- **사건 열기 (시연 1-1):** 사건 `INC-001`, 현재 적용일 2026-07-01. 배치 4개 `PART_OF`. `B-02-2602-01`·`B-02-2603-01` = `기준초과(미상신)`, `B-02-2602-02`·`-03` = `관찰해제`(기록에 `정상 → 관찰`, `관찰 → 관찰해제` 두 전이가 모두 있음). C-105의 `SHIPPED_TO` 2줄 = `확인요청중`, 출처 `도출`. 작업 2개: 출하 경위 확인(대상 보류 배치 2개), 출하처 확인(대상 C-105 줄 2개), 둘 다 `열림`, 기한 2026-07-08. `rules.incident_status` = `열림`.
- **상신·결정 (1-2, 1-3):** `submit_agenda` 후 두 배치 `상신중`, 사건 `판정중`. `committee_decision` 승인(2026-07-02) 후 두 배치 `회수진행`, 결정 1건, 안내 대상 결정 작업 `열림`. C-105 줄은 여전히 `확인요청중`.
- **조건부 (3-2):** 두 배치 `부분회수`. (C-105 줄이 확인요청중이므로 `회수진행`으로 넘어가지 않는다.)
- **거절 (3-5):** `reason` 없이 거절하면 `ActionError(precondition 또는 invalid_input)`이고 DB가 그대로다. 사유가 있으면 두 배치 `조사계속`, 원인 조사 작업 `열림`.
- **거절 뒤 새 확정 클레임:** `조사계속` 배치에 확정 클레임을 등록하면 `재상신 후보`가 되고 다시 상신할 수 있다.
- **보도 (2-1):** `register_news` 전후로 모든 배치 상태와 `SHIPPED_TO` 확인 수준이 같다. 이벤트 1건이 생기고, 액션 기록에 재검토 기록과 R3이 있다.
- **미확정 클레임 (2-2a):** 2026-07-07, `B-02-2602-03`에 C-101 800 EA `접수` → 배치 `관찰해제 → 관찰`(자동 처리 `관찰 복귀`), `rules.batch_metrics`의 `over_threshold` False, `release_due_date` None.
- **확정 (2-2b):** 2026-07-08 `resolve_claim` 확정 → 클레임 `확정`, 배치 `관찰` 유지, `release_due_date` 2026-10-06.
- **기각:** 2-2a 뒤에 `기각`하면 배치가 `관찰해제`로 돌아간다.
- **큰 수량:** `관찰해제` 배치에 확정 클레임 20,000 EA를 등록하면 `기준초과(미상신)`이 된다.
- **회수진행 배치의 새 클레임 (1-7):** 승인 후 `B-02-2602-01`에 확정 클레임을 등록해도 배치는 `회수진행` 그대로이고 결정·안건이 새로 생기지 않는다.
- **권한:** `quality_owner`가 `committee_decision`을 실행하면 `forbidden`. 없는 액션은 `unknown_action`.
- **전제 조건:** 사건이 있는데 `open_incident` → `precondition`. `기준초과(미상신)`이 아닌 배치를 상신 → `precondition`. 현재 적용일보다 이른 `applied_date` → `invalid_input`.
- **원자성:** 실패한 액션 전후로 `objects`·`links`·`action_log` 행이 완전히 같다.
- **재현:** 같은 액션 목록을 빈 DB 두 개에 실행하면 `objects`·`links`·`action_log` 내용이 같다.
- **`available_actions`:** 사건 열기 직후 `quality_owner`에게 `submit_agenda`(배치 2개)가 있고 `quality_committee`에게는 `committee_decision`이 없다. 상신 후에는 반대다. 목록에 있는 액션을 그 대상으로 실행하면 거부되지 않는다.
- **`reset`:** 실행 후 `objects`·`links`·`action_log`가 비고, 다시 `open_incident`를 할 수 있다.

## Acceptance Criteria

```bash
w03_system/.venv/bin/python -m pytest -q w03_system/backend/tests/test_actions_judgment.py
w03_system/.venv/bin/python -m pytest -q w03_system/backend/tests
! grep -rnE "datetime\.now|date\.today|time\.time|uuid" w03_system/backend/core
! grep -rnE "^(import|from) +(fastapi|anthropic)|backend\.(api|ai)" w03_system/backend/core
git diff --quiet -- 01_참가자_배포용
```

## 검증 절차

1. 위 AC 커맨드를 실행한다.
2. 아키텍처 체크리스트를 확인한다:
   - 상태를 바꾸는 코드가 `actions.py` 밖에 없는가? (`rules.py`·`loader.py`가 판정 상태를 바꾸지 않는가)
   - 모든 전이가 `ontology.can_transition()`을 지나는가?
   - 액션 하나가 한 트랜잭션인가? 실패 시 롤백되는가?
   - 불량률·해제 조건을 `actions.py`에서 다시 계산하지 않고 `rules.py`에 묻는가?
   - `business-model.md` §8-5의 액션 표(주체·전제 조건·효과)와 일치하는가?
3. 결과에 따라 `w03_system/phases/0-backend/index.json`의 step 4를 업데이트한다:
   - 성공 → `"status": "completed"`, `"summary"`에 `execute`·`available_actions` 시그니처, 액션 등록·자동 처리 연쇄를 확장하는 방법(다음 step이 어디에 무엇을 더하면 되는지), ID 규칙을 한 줄로 적는다
   - 수정 3회 시도 후에도 실패 → `"status": "error"`, `"error_message": "구체적 에러 내용"`
   - 사용자 개입 필요 → `"status": "blocked"`, `"blocked_reason": "구체적 사유"` 후 즉시 중단

## 금지사항

- `apply_reply`, `plan_decision`, 재공급 계획 생성·재계산을 이 step에서 구현하지 마라. 이유: 다음 step(actions-recovery)의 범위다. 단, 두 액션이 `unknown_action`이 아니라 "아직 구현되지 않음"으로 구분되게 할 필요는 없다(다음 step이 채운다).
- 언론 보도로 배치 상태나 작업을 바꾸지 마라. 이유: R3. 보도는 회수 근거가 아니고, 재검토 기록만 남긴다.
- 미확정 클레임으로 `기준초과(미상신)`을 만들지 마라. 이유: R7-1, A-16.
- 시스템이 결정을 대신 내리지 마라(자동 상신, 자동 승인). 이유: R12. 상신은 담당자, 결정은 위원회의 액션으로만 일어난다.
- `SHIPPED_TO` 줄을 지우지 마라. 이유: "확인했더니 아니었다"는 이력을 남겨야 한다(§4-2).
- `rules.py`의 기존 함수 동작을 바꾸지 마라. 꼭 필요하면 함수를 추가하고, 기존 테스트가 그대로 통과해야 한다. 이유: step 3의 기대값이 확정된 시연 수치다.
- FastAPI·AI 호출을 넣지 마라. 이유: `core`는 `api`·`ai`를 import하지 않는다.
- `01_참가자_배포용/04_원본데이터/`의 파일을 수정하지 마라. 이유: 원본 데이터는 대회 규칙상 수정 금지다.
- 기존 테스트를 깨뜨리지 마라.
