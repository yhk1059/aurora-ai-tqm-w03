# Step 2: db-loader

## 읽어야 할 파일

먼저 아래 파일들을 읽고 과제와 설계 의도를 파악하라:

- `/CLAUDE.md`
- `/w03_system/brain/status.md`
- `/w03_system/brain/3-design/architecture.md` (데이터 흐름, 모듈 경계, 상태 관리: SQLite 테이블 4개)
- `/w03_system/brain/3-design/business-model.md` §2, §3, §8-3, §8-4, §8-8
- `/w03_system/brain/2-findings/lot-b2602p-incident.md` (적재 결과와 대조할 사실)
- `/w03_system/brain/1-brief/assignment.md` §4 "데이터 관리 규칙"
- `/w03_system/backend/core/ontology.py` (step 1 산출물. 타입·관계·출처 이름은 여기서 가져온다)
- `/w03_system/scripts/lot_b2602p_incident.py` (같은 원본을 읽는 기존 스크립트. 읽는 방법 참고)

이전 step에서 만들어진 코드를 꼼꼼히 읽고, 설계 의도를 이해한 뒤 작업하라.

## 작업

두 파일을 만든다: `w03_system/backend/core/db.py`, `w03_system/backend/core/loader.py`.

### 1. `core/db.py` — SQLite 저장

테이블은 **4개뿐**이다. 객체 타입마다 테이블을 만들지 않는다.

| 테이블 | 컬럼 (의도) |
|---|---|
| `objects` | 타입, ID, 속성(JSON), 상태, 출처, 근거 참조 — (타입, ID)가 기본 키 |
| `links` | 줄 ID, 관계 유형, 출발 타입·ID, 도착 타입·ID, 속성(JSON), 출처, 확인 수준, 수량, 수량 근거, 근거 참조, 적용일, 기록일 |
| `action_log` | 순번, 액션, 실행자, 적용일, 입력(JSON), 변경 목록(JSON: 대상, 필드, 이전 → 이후), 원인(JSON: 규칙·이벤트·결정·앞선 순번) |
| `ai_log` | 순번, task, 모델, 입력(JSON), 출력(JSON), 연결된 액션 기록 순번 |

```python
def connect(path) -> sqlite3.Connection:
    """파일 경로 또는 ':memory:'. 테이블이 없으면 만든다. 상위 폴더가 없으면 만든다. row를 dict처럼 읽을 수 있게 한다."""

def reset(conn) -> None                      # 네 테이블을 모두 비운다
def put_object(conn, type, id, attrs, *, state=None, source, evidence=None) -> None
def get_object(conn, type, id) -> dict | None
def list_objects(conn, type=None) -> list[dict]
def update_object(conn, type, id, *, state=None, attrs=None) -> None    # attrs는 병합
def put_link(conn, rel, src, dst, *, source, confirm="확인", qty=None, qty_basis=None,
             attrs=None, evidence=None, applied_date=None, recorded_date=None) -> int
def find_links(conn, rel=None, src=None, dst=None) -> list[dict]        # src/dst = (타입, ID)
def update_link(conn, link_id, **fields) -> None
def append_action_log(conn, *, action, actor, applied_date, inputs, changes, cause) -> int
def list_action_log(conn) -> list[dict]
def append_ai_log(conn, *, task, model, inputs, output, action_seq=None) -> int
def list_ai_log(conn) -> list[dict]
```

핵심 규칙:
- **`db.py`는 커밋하지 않는다.** 트랜잭션의 시작·커밋·롤백은 호출하는 쪽(액션 실행기)이 한다. 이유: 액션 하나가 한 트랜잭션이어야 한다.
- `put_object`·`put_link`는 타입·관계 이름이 `ontology.py`에 정의돼 있는지 확인하고, 없으면 예외를 낸다.
- 줄 ID와 순번은 1부터 순서대로 늘어난다. 시각이나 난수를 쓰지 않는다. 이유: 같은 액션 목록을 다시 실행하면 같은 상태가 나와야 한다.
- 규칙 판단을 넣지 않는다.

### 2. `core/loader.py` — 원본 읽기와 사건 범위 적재

원본 위치는 `<프로젝트 루트>/01_참가자_배포용/04_원본데이터/`이고, 루트는 이 파일의 위치에서 계산한다(현재 작업 디렉토리에 기대지 않는다). CSV는 UTF-8, 첫 행 헤더, **구분자 `|`** 다.

쓰는 원본 파일과 컬럼:

| 파일 (`01_corevia/` 아래) | 컬럼 |
|---|---|
| `procurement/material_lot_master_cv.csv` | `lot_id, material_id, supplier_id, receipt_date, inspection_date, inspection_result, received_qty` |
| `production/production_material_consumption_cv.csv` | `consumption_id, batch_id, lot_id, material_id, product_id, consumed_qty, applied_unit_cost_krw, consumption_date` |
| `production/prod_batch_log_cv.csv` | `batch_id, product_id, production_line, production_date, produced_qty, input_lot_ids, qc_result` |
| `quality/qc_claims_cv.csv` | `claim_id, claim_date, customer_id, product_id, batch_id, lot_id, claim_type, defect_confirmed, qty_affected, status` |
| `quality/shipment_batch_link_cv.csv` | `shipment_id, batch_id, customer_id, product_id, order_date, ship_date, shipped_qty` |
| `master/m_customer_cv.csv` | `customer_id, customer_name, channel_type, …, revenue_share_pct, effective_date` |
| `sales/sales_customer_summary_cv.csv` | `period_ym, customer_id, booking_amount_krw, shipment_revenue_krw, booking_yoy_pct` (값이 `NONE`인 행이 있다) |
| `production/strat_capacity_cv.csv` | `plant_id, line_id, product_id, capacity_qty, utilization_pct, snapshot_date` |

```python
def openable_batches() -> list[dict]:
    """사건이 없을 때 화면에 보일 목록. 원본에서 클레임이 1건 이상 있는 배치마다:
    batch_id, product_id, production_date, produced_qty, qc_result, 클레임 건수, 확정 수량, 불량률(생산 기준).
    DB를 쓰지 않는다."""

def load_incident_scope(conn, batch_id: str) -> dict:
    """고른 배치에서 관계를 따라가 사건 한 건에 필요한 객체·관계만 적재하고 요약을 돌려준다.
    돌려주는 것: 기점 로트 ID 목록, 묶인 배치 ID 목록, 고객 ID 목록, 클레임 수."""

def latest_supply_batch(product_id: str, exclude_lots: list[str]) -> dict | None:
    """R11용. 같은 제품에서 input_lot_ids가 exclude_lots와 겹치지 않고 qc_result가 '합격'인 배치 중
    생산일이 가장 늦은 것. 원본 행과 근거 참조를 함께 돌려준다."""

def slack_capacity(product_id: str, as_of: str) -> dict:
    """A-04. as_of 직전 6개월의 그 제품 월평균 생산량 ÷ (가동률/100) × (1 − 가동률/100).
    값(EA/월), 계산에 쓴 월평균·가동률, 근거 참조를 돌려준다. capacity_qty는 쓰지 않는다."""

def read_text_source(rel_path: str) -> str:
    """원본 문서(md) 읽기. 보도 등록과 AI 입력에 쓴다.
    예: '05_external/news/ext_news_quality_incident.md', '01_corevia/quality/quality_policy_cv.md',
    '00_common/approval_authority_policy.md'"""
```

**`load_incident_scope`가 따라가는 길** (`business-model.md` §8-6의 R4):

1. 고른 배치의 클레임 → 클레임에 적힌 `lot_id` = **기점 로트**. 배치의 다른 투입 로트는 따라가지 않는다.
2. 기점 로트를 쓴 모든 배치 (`production_material_consumption_cv.lot_id` 또는 `prod_batch_log_cv.input_lot_ids`).
3. 그 배치들의 클레임 전부, 출하 기록(SBL) 전부.
4. 출하 기록과 클레임에 나오는 고객 전부. 고객 속성에 매출 비중과 **월별 수주 전년비**(`period_ym → booking_yoy_pct`, `NONE`은 null)를 싣는다.

**적재하는 객체와 관계:**

| 적재 | 내용 |
|---|---|
| 원료 로트 | 기점 로트. 입고량·투입량은 **싣지 않는다** (원본 한계, 범위 규칙 ①) |
| 배치 | 판정 상태는 모두 `정상`으로 싣는다. 판정은 사건 열기 액션이 한다 |
| 클레임 | 상태는 §4-6 규칙으로 옮긴다: `종결`이면서 `defect_confirmed`가 참이 아니면 `기각`, `종결`이면서 참이면 `확정`. 확정 클레임의 확정일 = `claim_date`. 출처 `원본` |
| 출하 기록 | SBL 행 그대로 |
| 고객 | 위 4번 |
| `USED_IN`, `CLAIMED_ON`, `CLAIMED_BY`, `CLAIMED_LOT`, `SHIPMENT_OF`, `SHIPMENT_FOR` | 출처 `원본`, 확인 수준 `확인` |
| `SHIPPED_TO` | **배치×고객당 한 줄.** 수량 = 그 배치·고객의 SBL `shipped_qty` 합, 수량 근거 `출하기록 합`, 출처 `원본`, 확인 수준 `확인`, 근거 참조 = 합친 `shipment_id` 목록 |

핵심 규칙:
- **적재한 모든 객체·관계에 근거 참조(원본 파일 상대 경로 + 행 ID)를 붙인다.** 이유: 원본 행까지 추적할 수 있어야 한다(A05 §1, 완료 조건 5).
- 클레임만 있고 출하 기록이 없는 고객(예: C-105)의 `SHIPPED_TO` 줄은 **만들지 않는다.** 이유: 그 줄은 사건 열기 액션이 R8로 만든다(step 4).
- 사건 객체, `PART_OF` 관계, 작업, 이벤트도 만들지 않는다. 같은 이유다.
- `load_incident_scope`도 커밋하지 않는다.
- 클레임이 없는 배치로 호출하면 `ValueError`를 낸다.

### 테스트

`w03_system/backend/tests/test_db.py`, `w03_system/backend/tests/test_loader.py`. DB는 `:memory:`를 쓴다. 뒤 step도 쓰도록 `tests/conftest.py`에 fixture를 둔다: `conn`(빈 DB), `loaded`(`B-02-2602-01`로 `load_incident_scope`를 마친 DB).

`B-02-2602-01`로 적재했을 때 확인할 값 [도출: `lot-b2602p-incident.md`]:

- 기점 로트 = `["LOT-B-2602-P"]`, 입고검사 결과 `보류`, 검사일 `2026-02-09`. 로트 속성에 입고량이 없다.
- 배치 4개: `B-02-2602-01`, `B-02-2602-02`, `B-02-2602-03`, `B-02-2603-01`. 생산량 150,745 / 154,685 / 161,592 / 160,733. 상태는 모두 `정상`.
- 클레임 45건(22 + 23), 모두 상태 `확정`. 확정 수량 합 17,900과 18,622.
- `SHIPPED_TO` 15줄(4 + 3 + 3 + 5), 모두 `확인`. `B-02-2602-01 → C-103` 수량 55,211. `B-02-2603-01 → C-108` 수량 34,929.
- 고객 6곳: C-101, C-102, C-103, C-104, C-108, **C-105**(클레임만 있음, `SHIPPED_TO` 줄 없음).
- C-101의 수주 전년비 2026-05 = −22.0, 2026-06 = −33.7. C-104는 −27.2, −26.1.
- 모든 객체와 관계에 근거 참조가 있다.
- `latest_supply_batch("PL-02", ["LOT-B-2602-P"])`의 투입 로트에 `LOT-B-2606-1`이 있고 QC는 `합격`이다.
- `slack_capacity("PL-02", "2026-07-01")`의 값을 반올림하면 14,814다.
- `openable_batches()`에 `B-02-2602-01`(불량률 약 11.9%)과 `B-02-2603-01`(약 11.6%)이 있고, `B-02-2602-02`는 없다.
- 적재 전후로 원본 폴더 파일의 크기·수정 시각이 바뀌지 않는다.

## Acceptance Criteria

```bash
w03_system/.venv/bin/python -m pytest -q w03_system/backend/tests/test_db.py w03_system/backend/tests/test_loader.py
w03_system/.venv/bin/python -m pytest -q w03_system/backend/tests
! grep -rnE "^(import|from) +(fastapi|anthropic)|backend\.(api|ai)" w03_system/backend/core
git diff --quiet -- 01_참가자_배포용
```

## 검증 절차

1. 위 AC 커맨드를 실행한다.
2. 아키텍처 체크리스트를 확인한다:
   - 테이블이 4개뿐인가? 객체 타입별 테이블을 만들지 않았는가?
   - `loader.py`가 원본을 읽기 모드로만 여는가? 원본의 복사본을 다른 폴더에 만들지 않았는가?
   - 타입·관계·출처 이름을 `ontology.py`에서 가져오는가(문자열을 다시 적지 않았는가)?
   - 범위 밖 데이터(다른 로트의 배치, 회사 전체 클레임)를 적재하지 않는가?
3. 결과에 따라 `w03_system/phases/0-backend/index.json`의 step 2를 업데이트한다:
   - 성공 → `"status": "completed"`, `"summary"`에 `db.py`·`loader.py`의 공개 함수 이름, 근거 참조 형식, `conftest.py` fixture 이름을 한 줄로 적는다
   - 수정 3회 시도 후에도 실패 → `"status": "error"`, `"error_message": "구체적 에러 내용"`
   - 원본 값이 위 기대값과 다른 경우 → 기대값을 고치지 말고 `"status": "blocked"`, `"blocked_reason"`에 어느 값이 어떻게 다른지 적고 즉시 중단

## 금지사항

- `01_참가자_배포용/04_원본데이터/`의 파일을 수정·복사·이동하지 마라. 이유: 원본 데이터는 대회 규칙상 수정 금지이고, 복사본을 두지 않기로 했다(`architecture.md`).
- ORM(SQLAlchemy 등)이나 pandas를 추가하지 마라. 이유: 테이블 4개와 작은 CSV에 과하다. 표준 라이브러리 `sqlite3`, `csv`만 쓴다.
- 로트 입고량·투입량을 싣거나 계산에 쓰지 마라. 이유: 원본 기록이 맞지 않는다(투입 합이 입고의 약 35배, 투입일이 입고일보다 빠름).
- SBL에 없는 출하처를 추정해 채우지 마라. 이유: 범위 규칙 ④ "모르면 메우지 말고 확인 요청으로 바꾼다".
- 불량률 판정, 관찰·해제 판단을 `loader.py`에 넣지 마라. 이유: 규칙은 `core/rules.py`(step 3)가 맡는다. `openable_batches()`의 불량률은 목록 표시용 숫자일 뿐이다.
- `datetime.now()` / `date.today()`를 쓰지 마라. 이유: 판단은 사건의 현재 적용일로만 한다(재현성).
- 기존 테스트를 깨뜨리지 마라.
