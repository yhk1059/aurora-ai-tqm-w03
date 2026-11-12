# Step 3: rules

## 읽어야 할 파일

먼저 아래 파일들을 읽고 과제와 설계 의도를 파악하라:

- `/CLAUDE.md`
- `/w03_system/brain/status.md`
- `/w03_system/brain/3-design/architecture.md` (패턴 3 "판정은 규칙, 설명은 AI", 모듈 경계의 `core/rules.py`)
- `/w03_system/brain/3-design/business-model.md` §4(상태), §5·§5-1(규칙 R1 ~ R12), §8-3(파생 속성), §8-5("규칙의 자리"), §8-6
- `/w03_system/brain/3-design/assumptions.md` (A-03, A-04, A-07, A-12, A-13, A-14, A-16)
- `/w03_system/brain/3-design/demo-scenarios.md` (기대 숫자)
- `/w03_system/brain/2-findings/lot-b2602p-incident.md`
- `/w03_system/backend/core/ontology.py`, `/w03_system/backend/core/db.py`, `/w03_system/backend/core/loader.py`
- `/w03_system/backend/tests/conftest.py` (fixture `conn`, `loaded`)
- `/w03_system/scripts/lot_b2602p_incident.py` (재공급 완료 월 계산의 기준 구현: `plan()` 함수)

이전 step에서 만들어진 코드를 꼼꼼히 읽고, 설계 의도를 이해한 뒤 작업하라.

## 작업

`w03_system/backend/core/rules.py`를 만든다. 이 모듈은 **DB를 읽어 계산만 하고, 아무것도 쓰지 않는다.** 결과를 돌려주면 액션 실행기(step 4·5)가 상태를 바꾼다.

모든 함수는 "오늘"을 인자 `today`(사건의 현재 적용일, `YYYY-MM-DD`)로 받는다. 기준값(10%, 90일, −20% 등)은 `ontology.rule_def()`에서 읽는다. 숫자를 이 파일에 다시 적지 않는다.

### 함수 (이름과 돌려주는 것은 이대로, 내부 구현은 재량)

```python
def batch_metrics(conn, batch_id: str, today: str) -> dict:
    """배치의 파생 속성. 아래 표의 키를 모두 가진다."""

def target_batch_state(conn, batch_id: str, today: str) -> dict | None:
    """규칙상 지금 바뀌어야 할 판정 상태가 있으면 {'to': 상태, 'rule': 규칙 ID, 'reason': 한 줄 근거}, 없으면 None.
    현재 상태가 무엇인지에 따라 답이 달라진다 (아래 '판정 상태 규칙')."""

def unconfirmed_exposures(conn) -> list[dict]:
    """R8. 사건에 묶인 배치의 클레임 고객 중 그 배치의 SHIPPED_TO 줄이 없는 (배치, 고객).
    각 항목: batch_id, customer_id, 클레임 ID 목록, 클레임 수량 합."""

def warnings(conn, today: str) -> list[dict]:
    """화면에 보일 경고. 각 항목: code, rule, 대상(타입·ID), 문구, 근거 참조.
    code: 'held_batch_shipped'(R5), 'held_lot_used'(R5-1), 'record_conflict'(R5-1의 투입일 < 입고일),
          'pending_claim_over_threshold'(R7-1), 'unsubmitted_delay'(기준 초과 후 미상신 경과일),
          'open_sales_check'(승인 대기 초안이 있는데 열린 수주 급감 확인 작업이 있음)."""

def order_drop_signal(conn, customer_id: str, today: str) -> dict:
    """R10-1. today가 속한 달의 직전 2개 월 수주 전년비가 모두 기준 이하인지.
    {'signal': bool, 'months': [(월, 값), (월, 값)], 'rule': 'R10-1'}. 값이 없는 달이 있으면 signal은 False."""

def recall_quantities(conn) -> list[dict]:
    """고객별 회수량. 대상 = 판정 상태가 '회수진행' 또는 '부분회수'인 배치의 SHIPPED_TO 줄 중
    확인 수준이 '확인' 또는 '회신확인'인 줄. 고객별로 수량을 합친다.
    각 항목: customer_id, qty, qty_basis('출하기록 합' | '클레임 합(하한)' | 둘이 섞이면 둘 다 표시),
    lower_bound(bool), 근거가 된 줄 ID 목록."""

def resupply_lines(conn, today: str) -> list[dict]:
    """R10·R10-2. 재공급 계획 한 판의 줄을 계산한다 (저장하지 않는다).
    각 항목: rank, customer_id, qty, qty_basis, lower_bound, expected_month('YYYY-MM'), priority_reason."""

def held_customers(conn) -> list[dict]:
    """재공급에서 보류된 고객: 회수 배치에 '미확인'·'확인요청중' 줄만 있는 고객과 그 이유."""

def supply_condition(conn, plan_id: str) -> dict:
    """R11. 계획의 SOURCED_FROM 공급 배치가 기점 로트를 쓰지 않았고 QC가 '합격'인지.
    {'met': bool, 'batch_id', 'lots', 'qc_result', 'reason'}. 공급 배치가 없으면 met은 False."""

def incident_status(conn) -> str | None:
    """§4-5 표대로 도출. 사건이 없으면 None."""
```

### `batch_metrics`가 돌려주는 키

| 키 | 계산 | 규칙 |
|---|---|---|
| `confirmed_qty` | 불량 확정 클레임의 수량 합. "확정" = 불량 확정 여부가 참 (원본 상태가 종결이었어도 포함) | R1 |
| `defect_rate` | `confirmed_qty ÷ 생산 수량` (비율. 표시는 화면이 한다) | R1 |
| `defect_rate_shipped` | `confirmed_qty ÷ SHIPPED_TO 확인 줄의 출하 수량 합`. 출하 수량이 0이면 None. **참고값이고 판정에 쓰지 않는다** | R1 |
| `over_threshold` | `confirmed_qty > 0` 이고 `defect_rate ≥ 기준` | R2 |
| `pending_qty` | 미확정 클레임(불량 확정 아님, 상태 `접수`·`조사중`) 수량 합 | R7-1 |
| `rate_if_confirmed` | `(confirmed_qty + pending_qty) ÷ 생산 수량`. 미확정 클레임이 없으면 None | R7-1 |
| `threshold_crossed_date` | 확정 클레임을 확정일 순으로 누적했을 때 기준을 처음 넘은 날. 넘지 않았으면 None | R2 |
| `days_unsubmitted` | 판정 상태가 `기준초과(미상신)`일 때 `today − threshold_crossed_date`(일). 아니면 None | — |
| `last_ship_date` | 그 배치 출하 기록의 가장 늦은 출하일 | R6 |
| `release_due_date` | 아래 "관찰 해제 예정일" | R6, R6-1, R6-2 |
| `release_basis` | `'마지막 출하일'` / `'마지막 클레임 확정일'` / `'미확정 클레임 대기'` | 〃 |

**관찰 해제 예정일**
- 미확정 클레임이 걸려 있으면 예정일은 None, 근거는 `미확정 클레임 대기` (R6-2).
- 확정 클레임이 한 건도 없으면 `last_ship_date + 90일` (R6, A-07).
- 확정 클레임이 있으면 `마지막 클레임 확정일 + 90일` (R6-1, A-12).
- 날짜 계산은 달력 날짜 덧셈이다. 예: 2026-07-08 + 90일 = 2026-10-06.

### 판정 상태 규칙 (`target_batch_state`)

| 현재 상태 | 조건 | 바뀔 상태 | 규칙 |
|---|---|---|---|
| `정상`, `관찰`, `관찰해제` | `over_threshold` | `기준초과(미상신)` | R2, R7 |
| `정상` | 기준 미달 | `관찰` | R4 |
| `관찰` | 미확정 클레임 없음 AND `release_due_date ≤ today` | `관찰해제` | R6, R6-1 |
| `관찰해제` | 해제 뒤 새 클레임이 들어와 해제 조건이 깨짐 (미확정 클레임이 있거나 `release_due_date > today`) | `관찰` | R6-2, R7 |
| `조사계속` | 거절 결정의 적용일 이후에 확정된 클레임이 있음 | `재상신 후보` | R9, A-09 |
| `상신중`, `회수진행`, `부분회수`, `기준초과(미상신)`, `재상신 후보` | — | None (새 클레임이 와도 판정 상태는 그대로다) | 시연 1-7 |

- `부분회수 → 회수진행`(미확인·확인요청중 줄이 없어짐)도 이 함수가 답한다: 현재 `부분회수`이고 그 배치에 확인 수준 `미확인`·`확인요청중`인 `SHIPPED_TO` 줄이 없으면 `회수진행`.
- 돌려주는 전이는 반드시 `ontology.can_transition("batch", …)`이 참이어야 한다.

### 재공급 줄 계산 (`resupply_lines`)

1. 대상과 수량은 `recall_quantities()`다. 확인되지 않은 고객은 들어가지 않는다 (R10 ①).
2. 정렬: 회수 수량이 많은 순 (R10 ②), 같으면 매출 비중이 큰 순 (R10 ③).
3. 영업 임원 회신 반영: 상태가 `완료`이고 결과가 `우선 공급 요청`인 수주 급감 확인 작업의 대상 고객을 **회신이 반영된 순서대로 맨 앞에** 둔다. 나머지는 2번 순서를 유지한다. `priority_reason`에 그 작업 ID를 적는다.
4. 완료 예상 월: 순위대로 한 고객씩 채운다. `m = ceil(누적 수량 ÷ 월 여유 능력)`이고, `today`가 속한 달이 1번째 달이다. 월 여유 능력은 `loader.slack_capacity(제품, today)`의 값이다(반올림하지 않은 값으로 나눈다).
5. 수량 근거가 `클레임 합(하한)`인 줄은 `lower_bound = True`다 (R10-2, A-14).

작업·결정 객체가 아직 없는 DB에서도 이 함수들은 동작해야 한다(없으면 없는 대로 계산).

### 테스트

`w03_system/backend/tests/test_rules.py`. fixture `loaded`를 쓰고, 액션 실행기가 아직 없으므로 필요한 상태(사건 객체, `PART_OF`, 배치 판정 상태, 미확인 줄, 작업)는 **테스트 안에서 `db.py` 함수로 직접 만든다.**

기대값 [도출: `lot-b2602p-incident.md`, `demo-scenarios.md`]:

- `B-02-2602-01`: `confirmed_qty` 17,900, `defect_rate` ≈ 0.1187(표시 11.9%), `defect_rate_shipped` ≈ 0.1227, `over_threshold` True, `threshold_crossed_date` 2026-04-01. 상태를 `기준초과(미상신)`으로 두고 today = 2026-07-01이면 `days_unsubmitted` 91.
- `B-02-2603-01`: 18,622, ≈ 0.1159(11.6%), 초과일 2026-05-11, 경과 51일.
- `B-02-2602-02`: `last_ship_date` 2026-03-03, `release_due_date` 2026-06-01. `B-02-2602-03`: 2026-02-23, 2026-05-24. today = 2026-07-01, 상태 `관찰`이면 둘 다 `target_batch_state`가 `관찰해제`(R6).
- 상태 `정상`인 `B-02-2602-01`의 `target_batch_state`는 `기준초과(미상신)`, `B-02-2602-02`는 `관찰`.
- `관찰해제`인 `B-02-2602-03`에 미확정 클레임 800 EA(C-101)를 넣으면: `rate_if_confirmed` ≈ 0.00495, `over_threshold` False, `release_due_date` None, `target_batch_state` → `관찰`. 그 클레임을 확정(확정일 2026-07-08)으로 바꾸고 today = 2026-07-08, 상태 `관찰`이면: `release_due_date` 2026-10-06, `target_batch_state` None.
- `unconfirmed_exposures`: (`B-02-2602-01`, C-105)와 (`B-02-2603-01`, C-105) 2건, 수량 합 11,765.
- `warnings`(사건에 묶인 뒤): `held_batch_shipped` 2건(보류 배치 2개), `held_lot_used` 대상 배치 3개(02-10, 02-16, 03-16 생산), `record_conflict` 1건(`B-02-2602-01`: 생산일 02-05 < 입고일 02-06).
- `order_drop_signal`(today 2026-07-01): C-101 True, C-104 True, C-102·C-103·C-108 False.
- 보류 배치 2개를 `회수진행`으로 두면 `recall_quantities`: C-103 83,402 / C-102 70,984 / C-101 56,993 / C-104 53,345 / C-108 34,929 (합 299,653). C-105는 없다.
- `resupply_lines`(today 2026-07-02): 순서 C-103 → C-102 → C-101 → C-104 → C-108, 예상 월 2026-12 / 2027-05 / 2027-09 / 2027-12 / 2028-03.
- C-101 대상 수주 급감 확인 작업을 `완료` + `우선 공급 요청`으로 만들면: C-101 → C-103 → C-102 → C-104 → C-108, 예상 월 2026-10 / 2027-04 / 2027-09 / 2027-12 / 2028-03.
- C-105의 두 줄을 `회신확인`, 수량 = 배치별 클레임 합, 수량 근거 `클레임 합(하한)`으로 만들면: C-105가 6번째, 수량 11,765, `lower_bound` True, 예상 월 2028-04.
- `incident_status`: §4-5 표의 다섯 경우를 상태 조합별로 확인한다.
- 어떤 함수를 불러도 DB 내용이 바뀌지 않는다(호출 전후 `objects`·`links` 행이 같다).

## Acceptance Criteria

```bash
w03_system/.venv/bin/python -m pytest -q w03_system/backend/tests/test_rules.py
w03_system/.venv/bin/python -m pytest -q w03_system/backend/tests
! grep -nE "datetime\.now|date\.today|time\.time" w03_system/backend/core/rules.py
! grep -nE "put_object|put_link|update_object|update_link|append_action_log|INSERT|UPDATE|DELETE" w03_system/backend/core/rules.py
! grep -rnE "^(import|from) +(fastapi|anthropic)|backend\.(api|ai)" w03_system/backend/core
```

## 검증 절차

1. 위 AC 커맨드를 실행한다.
2. 아키텍처 체크리스트를 확인한다:
   - `rules.py`가 DB를 쓰지 않고 읽기만 하는가?
   - 기준값(10%, 90일, −20%, 2개월)을 `ontology.py`에서 읽는가? 이 파일에 숫자로 다시 적지 않았는가?
   - 판정에 출하 기준 불량률이나 미확정 클레임을 쓰지 않았는가?
   - 각 결과에 규칙 ID가 붙어 화면이 근거를 보일 수 있는가?
3. 결과에 따라 `w03_system/phases/0-backend/index.json`의 step 3을 업데이트한다:
   - 성공 → `"status": "completed"`, `"summary"`에 공개 함수 이름과 돌려주는 형식의 요점을 한 줄로 적는다
   - 수정 3회 시도 후에도 실패 → `"status": "error"`, `"error_message": "구체적 에러 내용"`
   - 기대값이 원본에서 재현되지 않는 경우 → 기대값을 고치지 말고 `"status": "blocked"`, `"blocked_reason"`에 차이를 적고 즉시 중단

## 금지사항

- 테스트 기대값을 계산 결과에 맞춰 고치지 마라. 이유: 기대값은 확정된 시연 수치이고(`demo-scenarios.md`), 다르면 구현이나 해석이 틀린 것이다.
- 미확정 클레임을 불량률·판정에 넣지 마라. 이유: 정책상 회수 요건은 확정 불량이다(R7-1, A-16). 미확정은 참고값 `rate_if_confirmed`와 해제 정지에만 쓴다.
- 언론 보도 이벤트를 어떤 판정에도 쓰지 마라. 이유: R3. 보도는 회수 근거가 아니다.
- 확인 수준이 `미확인`·`확인요청중`·`영향없음`인 줄을 회수·재공급 수량에 넣지 마라. 이유: R8, R9 부분 회수.
- `strat_capacity_cv.capacity_qty`를 쓰지 마라. 이유: 단위가 맞지 않는 원본 불일치다(A-04). 가동률만 쓴다.
- 예측·최적화 로직을 넣지 마라. 이유: 재공급 규칙은 단순 3단계로 정했고(A-03), 예측 모델은 범위 밖이다.
- `01_참가자_배포용/04_원본데이터/`의 파일을 수정하지 마라. 이유: 원본 데이터는 대회 규칙상 수정 금지다.
- 기존 테스트를 깨뜨리지 마라.
