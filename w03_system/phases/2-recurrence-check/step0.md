# Step 0: core-rule

## 읽어야 할 파일

먼저 아래 파일들을 읽고 과제와 설계 의도를 파악하라:

- `/CLAUDE.md`
- `/w03_system/brain/status.md`
- `/w03_system/brain/3-design/architecture.md` (모듈 경계, 패턴: 모든 변경은 액션 실행기 하나를 지난다)
- `/w03_system/brain/3-design/decisions.md` (맨 아래 2026-11-15 "재발 방지 고리 (R11-1)" 행)
- `/w03_system/brain/3-design/assumptions.md` (A-18, A-17, A-09)
- `/w03_system/brain/3-design/business-model.md` (§5의 R5·R5-1·R11·R11-1, §8-5 "재공급 계획 결정 입력"과 "회신 반영" 표)
- `/w03_system/backend/core/ontology.py` (`RULES`의 R5-1·R11 항목, `TASK_TYPES["출하 경위 확인"]`, 액션 `plan_decision`)
- `/w03_system/backend/core/rules.py` (`warnings`, `_open_order_drop_tasks`, `ORDER_DROP_TASK`)
- `/w03_system/backend/core/actions.py` (`_check_plan_decision`, `_apply_plan_decision`, `_targets_plan_decision`, `_apply_reply`, `EXTEND_RESULTS`, `TASK_HOLD_SHIPMENT`)
- `/w03_system/backend/core/view.py` (`warnings`와 `available_actions`가 사건 뷰에 실리는 방식)
- `/w03_system/backend/tests/test_actions_recovery.py`, `/w03_system/backend/tests/test_rules.py`, `/w03_system/backend/tests/test_ontology.py`, `/w03_system/backend/tests/conftest.py`

기존 코드를 꼼꼼히 읽고, 설계 의도를 이해한 뒤 작업하라.

## 배경

지금은 "출하 경위 확인" 작업(T-01, QC 보류 배치가 출하된 경위를 생산·물류에 묻는 작업)의 회신이 아무것도 바꾸지 않는다. 그래서 보류 배치가 어떻게 나갔는지 모르는 채로 SCM이 같은 라인의 재공급 출하 계획을 승인할 수 있다. 이 phase는 규칙 **R11-1**을 넣어 그 고리를 닫는다.

**R11-1 (확정된 정의, 바꾸지 마라):**

1. "출하 경위 확인" 작업이 `열림`인 동안 재공급 계획 `초안`에 경고를 붙인다. 회신이 없는 경우와 "확인 불가" 회신으로 기한만 연장된 경우가 모두 `열림`이다.
2. 그 상태에서 SCM이 계획을 **승인하려면 근거(`reason`)가 필수**다. 승인 자체는 막지 않는다 [가정 A-18].
3. "경위 확인됨" 회신으로 작업이 끝나면 경고가 사라지고 근거는 다시 선택 입력이 된다.
4. 이미 `확정`된 계획은 T-01 회신이 와도 새 버전을 만들지 않는다.
5. 대상은 "출하 경위 확인" 작업뿐이다. "원인 조사"(T-06) 등 다른 작업은 묶지 않는다.

## 작업

이 step은 `backend/core/`와 `backend/tests/`만 다룬다.

### 1. 온톨로지 정의 (`backend/core/ontology.py`)

- `RULES`에 `"R11-1"`을 더한다. 형식은 바로 옆의 `R5-1`·`R11` 항목과 같게 한다. 근거는 가정 A-18이고 기준값(threshold)은 없다.
- `TASK_TYPES["출하 경위 확인"]`:
  - `rules`를 `["R5", "R5-1", "R11-1"]`로 한다. **`"R5"`가 맨 앞이어야 한다.** 이유: `_apply_reply`가 `rules[0]`을 회신 기록의 규칙으로 쓴다.
  - `allowed_results`의 효과 문구에 "재공급 계획 승인 경고 해제(R11-1)" / "경고와 승인 근거 필수 유지(R11-1)"를 반영한다. 허용 결과 이름(`경위 확인됨`, `확인 불가`)은 바꾸지 않는다.
- 액션 `plan_decision`:
  - `precondition` 문구에 "열린 출하 경위 확인(T-01)이 있으면 경고를 보이고 승인에 근거가 필수다(R11-1)"를 더한다.
  - `choice_effects["승인"]` 문구에 근거 필수 조건을 한 구절로 더한다.
  - `rules`에 `"R11-1"`을 더한다.
  - `reason` 입력의 `required=False`는 그대로 둔다. 이유: 필수 여부는 사건 상태에 따라 달라지므로 입력 정의가 아니라 전제 조건 확인에서 건다.

### 2. 규칙 (`backend/core/rules.py`)

```python
def open_hold_shipment_tasks(conn) -> list[dict]:
    """유형이 '출하 경위 확인'이고 상태가 열림인 작업 목록 (R11-1)."""
```

- `warnings(conn, today)`에 경고를 더한다. 계획 `초안`마다, 위 목록이 비어 있지 않으면:

```python
{"code": "open_hold_shipment_check", "rule": "R11-1",
 "target": {"type": "resupply_plan", "id": <초안 계획 id>},
 "message": "출하 경위 확인 대기 N건 · 승인하려면 근거 필수",
 "evidence": [<열린 출하 경위 확인 작업 id>, ...]}
```

- 기존 `open_sales_check` 경고는 그대로 둔다. 두 경고가 같은 초안에 함께 붙을 수 있다.
- 작업 유형 이름 상수는 `rules.py`가 이미 `ORDER_DROP_TASK`를 두는 방식을 따른다. **`rules.py`에서 `actions.py`를 import하지 마라.** 이유: `actions.py`가 `rules.py`를 import하므로 순환 import가 된다.

### 3. 액션 (`backend/core/actions.py`)

- `_check_plan_decision`: 결과가 승인이고 `rules.open_hold_shipment_tasks(conn)`가 비어 있지 않은데 `reason`이 비어 있으면(공백만 있는 경우 포함) `ActionError("precondition", ...)`를 낸다. 메시지에 "출하 경위 확인"과 "R11-1"이 들어가야 한다. 기존 확인(초안 여부, 거절 근거 필수, 출고 조건 R11)은 그대로 둔다.
- `_apply_plan_decision`: 승인 시점에 열린 출하 경위 확인 작업이 있었으면 반환값의 `rules`에 `"R11-1"`을 더한다. 이유: 액션 기록에 "이 승인은 경위 미확인 상태에서 근거를 적고 이뤄졌다"가 규칙 번호로 남아야 한다. 상태 변경은 기존과 같다(계획 → 확정).
- `_targets_plan_decision`: 각 항목에 `"approve_reason_required": bool`을 더한다(열린 출하 경위 확인 작업이 있으면 `True`). 이유: 화면이 규칙을 다시 계산하지 않고 이 값만 읽는다.
- 판단은 `rules.py`에 묻는다. `actions.py`에서 작업 목록을 직접 훑어 다시 계산하지 마라.
- T-01 회신 처리(`_apply_reply`)는 바꾸지 않는다. "확인 불가"는 이미 작업을 열린 채로 두고 기한만 연장하며, "경위 확인됨"은 작업을 완료로 만든다. 경고는 저장하지 않고 `warnings()`가 매번 계산하므로 회신만으로 풀린다.

### 4. 사건 뷰 (`backend/core/view.py`)

- 코드 변경이 필요 없을 가능성이 높다. 새 경고가 `view["warnings"]`에, `approve_reason_required`가 `available_actions`의 `plan_decision` 대상 항목에 실제로 실리는지 테스트로 확인하고, 실리지 않을 때만 고친다.

### 5. 테스트 (`backend/tests/`)

기존 테스트 파일의 픽스처·도우미 방식을 그대로 쓴다. 최소한 아래를 확인한다.

1. 사건 열기 → 상신 → 위원회 승인으로 계획 초안이 생기면, `warnings`에 `open_hold_shipment_check`가 있고 `target`이 그 초안, `evidence`가 출하 경위 확인 작업 id다.
2. 그 상태에서 근거 없이(빈 문자열, 공백) 승인하면 `ActionError` `precondition`이고, 계획은 `초안` 그대로이며 결정 객체가 생기지 않는다.
3. 근거를 적고 승인하면 계획이 `확정`되고, 그 액션 기록의 규칙에 `R11-1`이 있다.
4. 출하 경위 확인에 "확인 불가"를 회신하면 작업이 열린 채 기한이 연장되고, 경고가 남고, 근거 없는 승인은 여전히 거부된다.
5. "경위 확인됨"을 회신하면 작업이 완료되고, 초안의 경고가 사라지고, `approve_reason_required`가 `False`이고, 근거 없이 승인할 수 있다. 이 승인의 규칙에는 `R11-1`이 없다.
6. 계획이 `확정`된 뒤 "경위 확인됨" 회신이 와도 계획 버전 수가 늘지 않는다.
7. 거절은 기존대로 근거가 필수이고, 열린 출하 경위 확인과 무관하게 동작한다.
8. 출하 경위 확인 작업이 없는 사건(QC 보류 배치가 없는 다른 배치로 연 사건)에는 새 경고가 없다.
9. `test_ontology.py`가 규칙 개수나 목록을 세고 있으면 `R11-1`에 맞게 고친다.

## Acceptance Criteria

저장소 루트에서 실행한다. `--deselect` 4건은 이 phase 이전부터 로컬 `w03_system/.env`(모델 이름·API 키·재생 모드 설정) 때문에 실패하던 테스트다.

```bash
w03_system/.venv/bin/python -m pytest -q w03_system/backend/tests \
  --deselect w03_system/backend/tests/test_ai.py::test_no_key \
  --deselect w03_system/backend/tests/test_ai.py::test_classify_ok_and_logged \
  --deselect w03_system/backend/tests/test_ai.py::test_real_call_saves_answer_and_replay_returns_it_without_calling \
  --deselect w03_system/backend/tests/test_api.py::test_ai_no_key
```

## 검증 절차

1. 위 AC 커맨드를 실행한다. 실패 0건이어야 한다.
2. 아키텍처 체크리스트를 확인한다:
   - `3-design/architecture.md`의 모듈 경계를 따르는가? (`core`는 `api`·`ai`에 의존하지 않는다. 판단은 `rules.py`, 상태 변경은 `actions.py`)
   - `3-design/business-model.md`의 R11-1 정의, §8-5 표와 일치하는가?
   - 경고를 DB에 저장하지 않았는가? (경고는 파생 값이다)
   - CLAUDE.md 금지 규칙을 위반하지 않았는가?
3. 결과에 따라 `w03_system/phases/2-recurrence-check/index.json`의 해당 step을 업데이트한다:
   - 성공 → `"status": "completed"`, `"summary": "산출물 한 줄 요약"` (다음 step이 쓸 이름을 적는다: 경고 코드 `open_hold_shipment_check`, 대상 항목 키 `approve_reason_required`, 오류 메시지 문구, 추가한 테스트 수)
   - 수정 3회 시도 후에도 실패 → `"status": "error"`, `"error_message": "구체적 에러 내용"`
   - 사용자 개입 필요 → `"status": "blocked"`, `"blocked_reason": "구체적 사유"` 후 즉시 중단

## 금지사항

- 승인을 막는 전제 조건으로 만들지 마라. 이유: "확인 불가" 회신이면 재공급이 무기한 멈춘다. 결정은 "경고 + 근거 필수"다(decisions 2026-11-15).
- 새 작업 유형, 새 객체 타입, 새 상태를 만들지 마라. 이유: 결정에서 "새 작업 유형은 만들지 않는다"로 정했다.
- T-01 회신이 왔다고 재공급 계획 새 버전을 만들지 마라. 이유: 회신은 순서·수량을 바꾸지 않는다.
- `scenarios/`, `frontend/`, `e2e/`, `backend/ai/`, `backend/api/`를 고치지 마라. 이유: 다음 step들의 범위다. 기존 시나리오 파일의 1-6 승인에는 이미 근거 문장이 있어 시나리오 테스트는 그대로 통과해야 한다. 통과하지 않으면 시나리오를 고치지 말고 원인을 찾아라.
- 위 `--deselect` 4건을 고치려고 서버 코드나 `.env`를 바꾸지 마라. 이유: 실행 환경 설정 문제이고 이 phase와 무관하다(`status.md` "다음 할 일" 0번).
- `01_참가자_배포용/04_원본데이터/`의 파일을 수정하지 마라. 이유: 원본 데이터는 대회 규칙상 수정 금지다.
- 기존 테스트를 깨뜨리지 마라.
