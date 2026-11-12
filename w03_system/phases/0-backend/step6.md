# Step 6: view-scenarios

## 읽어야 할 파일

먼저 아래 파일들을 읽고 과제와 설계 의도를 파악하라:

- `/CLAUDE.md`
- `/w03_system/brain/status.md`
- `/w03_system/brain/3-design/architecture.md` (패턴 4 "화면은 서버가 준 것만 그린다", API 표의 `GET /incident`·`POST /scenarios/{name}`, 테스트 전략)
- `/w03_system/brain/3-design/demo-scenarios.md` — **전체.** 이 step의 기준 문서다
- `/w03_system/brain/3-design/business-model.md` §4-5, §8-3, §8-7
- `/w03_system/brain/3-design/ui-guide.md` ("레이아웃": 탭 4개와 연결망에 무엇이 나오는지. 뷰가 이 내용을 다 담아야 한다)
- `/w03_system/brain/1-brief/assignment.md` §4 "필수 시연 세부", "데이터 관리 규칙"
- `/w03_system/backend/core/actions.py`, `rules.py`, `db.py`, `loader.py`, `ontology.py`
- `/w03_system/backend/tests/test_actions_judgment.py`, `test_actions_recovery.py` (액션 입력 형식 참고)

이전 step에서 만들어진 코드를 꼼꼼히 읽고, 설계 의도를 이해한 뒤 작업하라.

## 작업

세 가지를 만든다: 사건 뷰(`core/view.py`), 시연 액션 목록(`w03_system/scenarios/*.json`), 시나리오 실행 함수(`core/scenario.py`).

### 1. `core/view.py` — 사건 뷰

```python
def incident_view(conn, actor: str | None = None) -> dict:
    """화면이 한 번에 받는 덩어리. JSON으로 직렬화할 수 있어야 한다. DB를 바꾸지 않는다."""
```

사건이 없을 때: `{"incident": None, "openable_batches": [...], "available_actions": [...]}`.

사건이 있을 때 담는 것 (키 이름은 재량이되 아래 내용이 모두 있어야 한다):

| 묶음 | 내용 |
|---|---|
| 사건 | ID, 사건 상태(`rules.incident_status`), 기점 로트, 개시일, 현재 적용일, 담당자 |
| 원료 로트 | 속성, 출처, 근거 참조 |
| 배치 | 속성, 판정 상태, 묶인 이유, `rules.batch_metrics` 전체, 그 배치의 경고 |
| 고객 | 속성, 수주 급감 신호(`rules.order_drop_signal`) |
| 클레임 | 속성, 상태, 출처(원본 / 모의) |
| 연결망 | 로트 → 배치(`USED_IN`), 배치 → 고객(`SHIPPED_TO`: 확인 수준, 수량, 수량 근거, 출처, 근거 참조, 그 배치·고객의 클레임 건수와 수량 합) |
| 작업 | 유형, 담당 부서, 상태, 기한, 회신 내용·결과, 대상, 허용 결과 목록, 만든 결정·규칙 |
| 결정 | 유형, 결정권자, 결과, 사유, 적용일, 대상 |
| 이벤트 | 유형, 발생일, 적용일, 내용, 출처 |
| 재공급 계획 | 버전마다: 상태, 줄(순위·고객·수량·수량 근거·하한 여부·예상 월), `rules.plan_diff`, 출고 조건과 `rules.supply_condition`, 여유 능력 값·출처, 재계산 원인. 보류 고객(`rules.held_customers`) |
| 경고 | `rules.warnings` |
| 가능한 액션 | `actions.available_actions(conn, actor)` (`actor`가 None이면 빈 목록) |
| 방금 바뀐 것 | 가장 최근 **사람 액션**과 그 뒤에 이어진 자동 처리의 변경 목록(대상, 이전 → 이후, 규칙) |
| 기록 | `action_log` 전체, `ai_log` 전체 |
| 기준값 | 화면이 숫자 옆에 붙일 규칙 기준값과 출처 (`ontology`에서) |

핵심 규칙:
- **뷰는 읽기만 한다.** 호출 전후로 DB가 같아야 한다.
- 숫자·관계·기준값마다 **출처**(`원본` / `도출` / `가정` / `모의` / `시스템`)가 따라가야 한다. 이유: 화면이 출처 배지를 붙인다(완료 조건 5).
- 판정을 뷰에서 다시 계산하지 않는다. `rules.py`·`actions.py`가 준 것을 조립만 한다.
- 표시용 가공(천 단위 구분, % 변환, 색)은 하지 않는다. 화면의 일이다.

### 2. `w03_system/scenarios/*.json` — 시연 액션 목록

`demo-scenarios.md`의 단계를 액션 목록으로 옮긴다. **[모의] 입력은 이 폴더에만 둔다.**

| 파일 | 내용 |
|---|---|
| `demo1.json` | 시연 1: 1-1 ~ 1-7 |
| `demo2.json` | 시연 2: 출발 상태(1-1 ~ 1-6) + 2-1 ~ 2-5 |
| `demo3a.json` | 시연 3-A: 3-1(= 1-1, 1-2) ~ 3-4 |
| `demo3b.json` | 시연 3-B: 사건 열기·상신 + 3-5 ~ 3-6 (재상신까지) |
| `other-batch.json` | 범위 규칙 ①: 다른 배치 하나로 사건을 열어 "회수 대상 아님"으로 끝나는 경우 |

파일 형식 (의도):
```json
{
  "name": "demo2",
  "title": "시연 2. 조건 변경",
  "description": "…",
  "steps": [
    {"id": "1-1", "setup": true, "action": "open_incident", "actor": "quality_owner",
     "inputs": {"batch_id": "B-02-2602-01", "applied_date": "2026-07-01"},
     "source": "원본", "note": "담당자가 사건을 연다"},
    {"id": "2-4a", "action": "apply_reply", "actor": "quality_owner",
     "inputs": {"task": {"type": "수주 급감 확인", "customer_id": "C-104"},
                "reply_text": "C-104 특이사항 없음, 순서 유지", "result": "순서 유지", "applied_date": "2026-07-09"},
     "source": "모의", "note": "T-05b 회신"}
  ]
}
```

- 날짜, 고객, 수량, 회신 문장, 결과는 `demo-scenarios.md`의 값을 그대로 쓴다. 문서에 수량이 없는 입력(1-7의 신규 클레임)은 작은 값(예: C-102, 300 EA)을 정하고 `note`에 "[모의] 수량은 시연용으로 정함"이라고 적는다.
- 단계마다 `source`(`원본` / `모의`)와 `id`(문서의 단계 번호)를 적는다. `setup: true`는 "시연의 출발 상태를 만드는 단계"라는 표시다(시연 2의 1-1 ~ 1-6).
- 보도(2-1)의 `source_ref`는 `05_external/news/ext_news_quality_incident.md`이고 `occurred_date`는 비운다(원본에 발생일이 없다).
- 작업·클레임·계획처럼 실행 중에 ID가 정해지는 대상은 **조건으로 가리킬 수 있게** 한다(위 예의 `"task": {"type": …, "customer_id": …}`, 최신 초안 계획, 가장 최근 모의 클레임 등). 실행 함수가 실제 ID로 바꾼다. 이유: ID를 파일에 직접 적으면 액션이 하나만 늘어도 전부 어긋난다.
- 2-3은 액션이 없는 단계다("1-3에서 만들어진 확인 요청 2건이 아직 열려 있음"). 목록에 넣지 않거나 액션 없는 설명 단계로 둔다.
- `other-batch.json`의 배치는 `loader.openable_batches()`에서 고른다: 클레임이 있고, 사건을 열었을 때 묶이는 배치가 모두 기준 미달이어서 `incident_status`가 `관찰중`이 되는 배치. 후보가 여러 개면(원본 기준 100개 이상이다) **확정 클레임이 있으면서 기준 미달인 배치 중 불량률이 가장 높은 것**을 쓴다. 이유: "클레임은 있지만 기준에 못 미쳐 회수 대상이 아니다"를 보여주는 경우다. 고른 배치와 이유를 파일의 `description`에 적는다. 그런 배치가 하나도 없으면 blocked로 멈춘다.

### 3. `core/scenario.py` — 실행 함수

```python
def list_scenarios() -> list[dict]:            # name, title, description, 단계 수
def run_scenario(conn, name: str, *, upto: str | None = None, setup_only: bool = False) -> list[dict]:
    """DB를 초기화(reset)한 뒤 단계를 순서대로 actions.execute로 실행한다.
    upto = 이 단계 id까지(포함) 실행. setup_only = setup 단계만 실행.
    단계별 결과(id, action, ActionResult 요약)를 돌려준다. 단계가 실패하면 어느 단계인지 담아 예외를 낸다."""
```

- 시나리오 실행은 **`actions.execute`만** 쓴다. DB를 직접 고쳐 상태를 만들지 않는다. 이유: 시연 출발 상태도 재현 가능한 액션 기록이어야 한다.
- `architecture.md`의 모듈 경계 표에 `core/scenario.py` 한 줄을 더한다("하는 일: `scenarios/`의 액션 목록을 순서대로 실행 / 하면 안 되는 것: DB 직접 수정").

### 테스트

`w03_system/backend/tests/test_view.py`, `w03_system/backend/tests/test_scenarios.py`. **시연을 끝까지 실행한 뒤 `incident_view`로 확인한다** (뷰와 시나리오를 함께 검증).

**시연 1 (`demo1`)**
- 1-1 뒤: 사건 상태 `열림`. 보류 배치 2개 `기준초과(미상신)`, 불량률 ≈ 11.9%·11.6%, 미상신 경과 91일·51일. 합격 배치 2개 `관찰해제`. 경고에 보류 배치 출하 2건, 보류 로트 투입(배치 3개), 원본 기록 충돌 1건. 연결망에 C-105 줄 2개(`확인요청중`, 출처 `도출`). "방금 바뀐 것"에 `정상 → 관찰 → 관찰해제`가 있다.
- 끝(1-7) 뒤: 사건 상태 `복구계획확정`. 보류 배치 2개 `회수진행`. 계획 v1 `확정`, 순서 C-103 → C-102 → C-101 → C-104 → C-108, 예상 월 2026-12 / 2027-05 / 2027-09 / 2027-12 / 2028-03. 결정 2건(위원회 승인, SCM 승인). 1-7의 클레임 뒤에도 결정·계획 버전 수가 늘지 않는다. 안내 대상 = 회수 배치 고객 5곳.

**시연 2 (`demo2`)**
- `setup_only=True`로 실행하면 계획 v1 `확정` 상태다.
- 2-1 뒤: 배치 상태가 2-1 전과 같고, 기록에 재검토 기록(R3)이 있다.
- 2-2a 뒤: `B-02-2602-03` = `관찰`, 확정 시 불량률 ≈ 0.5%, 기준 초과 아님, 해제 예정일 없음.
- 2-2b 뒤: 클레임 `확정`, 배치 `관찰`, 해제 예정일 2026-10-06.
- 2-4 뒤: 계획 v2 `초안`, 순서 C-101 → C-103 → C-102 → C-104 → C-108, C-103·C-102 지연 +4개월. 사건 상태 `회수진행`.
- 끝(2-5) 뒤: v2 `확정`, v1도 남아 있음, 사건 상태 `복구계획확정`.

**시연 3-A (`demo3a`)**
- 3-2 뒤: 보류 배치 2개 `부분회수`, 계획 v1 `초안`에 C-105 없음, 보류 고객에 C-105.
- 3-3 뒤: 출하처 확인 작업 `열림`, 기한 2026-07-15, C-105 줄 `확인요청중`, 배치 `부분회수`.
- 끝(3-4) 뒤: C-105 줄 `회신확인`, 수량 합 11,765, 하한 표시. 배치 `회수진행`. 계획 v2 `초안`, C-105 6번째, 예상 월 2028-04.

**시연 3-B (`demo3b`)**
- 3-5 뒤: 보류 배치 2개 `조사계속`, 원인 조사 작업 `열림`, 사건 상태 `판정중`, 결정에 거절 사유가 있다.
- 끝 뒤: 두 배치 `상신중`.

**그 밖**
- `other-batch`: 사건 상태 `관찰중`, `기준초과(미상신)` 배치 없음, 위원회 결정 가능 액션 없음.
- **재현:** 같은 시나리오를 두 번 실행하면 `incident_view` 결과가 완전히 같다.
- **뷰는 읽기 전용:** `incident_view` 호출 전후로 `objects`·`links`·`action_log` 행이 같다.
- **직렬화:** 모든 시나리오 끝의 뷰가 `json.dumps(..., ensure_ascii=False)`를 통과한다.
- **가능한 액션:** 시연 1의 1-2 뒤 `actor="quality_committee"` 뷰에 `committee_decision`이 있고 `actor="scm"` 뷰에는 없다.
- **모의 표시:** 모든 시나리오 파일의 단계에 `source`가 있고, 시나리오로 만든 클레임·결정·회신 이벤트의 출처가 `모의`다.
- 테스트는 AI를 호출하지 않는다.

## Acceptance Criteria

```bash
w03_system/.venv/bin/python -m pytest -q w03_system/backend/tests/test_view.py w03_system/backend/tests/test_scenarios.py
w03_system/.venv/bin/python -m pytest -q w03_system/backend/tests
test -f w03_system/scenarios/demo1.json
test -f w03_system/scenarios/demo2.json
test -f w03_system/scenarios/demo3a.json
test -f w03_system/scenarios/demo3b.json
test -f w03_system/scenarios/other-batch.json
! grep -rnE "datetime\.now|date\.today|time\.time|uuid" w03_system/backend/core
! grep -rnE "^(import|from) +(fastapi|anthropic)|backend\.(api|ai)" w03_system/backend/core
git diff --quiet -- 01_참가자_배포용
```

## 검증 절차

1. 위 AC 커맨드를 실행한다.
2. 아키텍처 체크리스트를 확인한다:
   - `view.py`가 상태를 바꾸지 않는가? 판정을 다시 계산하지 않는가?
   - 시나리오 실행이 `actions.execute`만 쓰는가?
   - 모의 입력이 `scenarios/` 밖(코드, 테스트 fixture 제외)에 흩어져 있지 않은가?
   - `demo-scenarios.md`의 단계·날짜·회신 문장과 시나리오 파일이 일치하는가?
   - `ui-guide.md`의 탭 4개와 연결망이 요구하는 정보가 뷰에 다 있는가?
3. 결과에 따라 `w03_system/phases/0-backend/index.json`의 step 6을 업데이트한다:
   - 성공 → `"status": "completed"`, `"summary"`에 뷰의 최상위 키 목록, 시나리오 파일 이름과 형식(대상 지정 방식), `run_scenario` 시그니처, `other-batch`에 쓴 배치를 한 줄로 적는다
   - 수정 3회 시도 후에도 실패 → `"status": "error"`, `"error_message": "구체적 에러 내용"`
   - 시연 기대값이 재현되지 않아 설계 문서를 고쳐야 하는 경우 → `"status": "blocked"`, `"blocked_reason"`에 어느 단계의 어떤 값이 다른지 적고 즉시 중단

## 금지사항

- 시연을 통과시키려고 `actions.py`·`rules.py`에 특정 배치·고객 ID(`B-02-2602-01`, `C-101` 등)를 조건으로 넣지 마라. 이유: 정의는 다른 사건에도 같은 코드로 돌아야 한다(§8-8). `other-batch` 테스트가 이를 확인한다.
- 테스트 기대값을 실행 결과에 맞춰 고치지 마라. 이유: 기대값은 확정된 시연 수치다. 다르면 앞 step의 구현을 고치거나 blocked로 멈춘다.
- 유리한 회신만 넣지 마라. 이유: 과제 규칙이다. 3-3의 "확인 불가", 3-5의 거절은 반드시 포함한다.
- 시나리오 파일에 AI 출력(요약, 분류 결과 문장)을 지어내 넣지 마라. 이유: 가짜 AI 응답은 실행 증거가 되지 못한다. 회신의 `result`는 "담당자가 고른 값"으로 넣고, `summary`는 비우거나 "담당자 작성"임을 밝힌 짧은 글로 둔다.
- 뷰에 표시용 문자열 가공(색, 배지 문구, 천 단위 구분)을 넣지 마라. 이유: 화면의 일이다(`ui-guide.md`).
- `01_참가자_배포용/04_원본데이터/`의 파일을 수정하지 마라. 이유: 원본 데이터는 대회 규칙상 수정 금지다.
- 기존 테스트를 깨뜨리지 마라.
