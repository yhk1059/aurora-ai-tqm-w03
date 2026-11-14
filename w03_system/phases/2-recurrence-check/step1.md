# Step 1: scenarios

## 읽어야 할 파일

먼저 아래 파일들을 읽고 과제와 설계 의도를 파악하라:

- `/CLAUDE.md`
- `/w03_system/brain/status.md`
- `/w03_system/brain/3-design/architecture.md` (`scenarios/`의 역할, 시나리오 실행 방식)
- `/w03_system/brain/3-design/decisions.md` (맨 아래 2026-11-15 "재발 방지 고리 (R11-1)" 행)
- `/w03_system/brain/3-design/demo-scenarios.md` (시연 1의 1-6, 시연 2의 2-4c·2-5, "모의 회신 목록"의 T-01 행)
- `/w03_system/brain/3-design/business-model.md` (§5의 R11-1)
- `/w03_system/scenarios/demo1.json`, `/w03_system/scenarios/demo2.json`, `/w03_system/scenarios/reply-examples.json`
- `/w03_system/backend/core/scenario.py` (단계의 `task`·`plan` 선택자를 실제 ID로 바꾸는 방식, `setup` 단계)
- `/w03_system/backend/tests/test_scenarios.py`, `/w03_system/backend/tests/test_api.py` (모의 입력 예시 개수·목록을 확인하는 부분)
- step 0에서 바뀐 파일: `/w03_system/backend/core/ontology.py`, `/w03_system/backend/core/rules.py`, `/w03_system/backend/core/actions.py`

이전 step에서 만들어진 코드를 꼼꼼히 읽고, 설계 의도를 이해한 뒤 작업하라.

## 배경

step 0이 규칙 R11-1을 서버에 넣었다. "출하 경위 확인" 작업(T-01)이 열려 있으면 재공급 계획 초안에 경고 `open_hold_shipment_check`가 붙고, SCM이 승인하려면 근거가 필수다. "경위 확인됨" 회신이 오면 경고가 풀린다.

이 step은 시연 시나리오와 화면의 모의 입력 예시를 여기에 맞춘다. 시연에서 보일 것은 `demo-scenarios.md`가 기준이다.

- 시연 1의 1-6: T-01이 열린 채 SCM이 근거를 적고 승인한다.
- 시연 2의 2-4c(새 단계): T-01에 "경위 확인됨" 회신이 온다. 이어지는 2-5 재승인에는 경고가 없다.

## 작업

이 step은 `scenarios/`와 `backend/tests/`만 다룬다.

### 1. `scenarios/demo1.json`

- 단계 `1-6`(SCM 승인)의 `reason`을 `"출고 조건 충족. 출하 경위는 회신 후 재확인 (담당자 작성)"`으로 바꾼다.
- 같은 단계의 `note`에 "출하 경위 확인 대기 경고 속 승인, 근거 필수 (R11-1)"을 덧붙인다.

### 2. `scenarios/demo2.json`

- `setup` 단계 `1-6`의 `reason`을 demo1과 같은 문장으로 바꾼다.
- `2-4b` 뒤, `2-5` 앞에 단계 `2-4c`를 넣는다:

```json
{
  "id": "2-4c",
  "action": "apply_reply",
  "actor": "quality_owner",
  "inputs": {
    "task": {"type": "출하 경위 확인"},
    "reply_text": "QC 보류 표시가 출하 지시에 반영되지 않아 납기 일정대로 출고됨. 출하 전 확인표에 보류 배치 차단 항목 추가",
    "result": "경위 확인됨",
    "applied_date": "2026-07-09"
  },
  "source": "모의",
  "note": "T-01 생산·물류 회신 [모의] → T-01 완료, 계획 v2 초안의 출하 경위 확인 대기 경고 해제 (R11-1)"
}
```

- `task` 선택자에 `customer_id`가 없다. `scenario.py`가 이 형태를 받아 작업 하나를 찾는지 먼저 확인하라. 받지 못하면 `scenario.py`의 선택자 처리를 가장 작게 고친다(유형만으로 열린 작업이 정확히 하나일 때 그것을 고른다). 기존 선택자의 동작은 바꾸지 않는다.
- `setup` 단계 수(5개)는 그대로다.

### 3. `scenarios/reply-examples.json`

- `plan_decision`의 예시 `"승인 (출고 조건 충족)"`의 `reason`을 demo1의 1-6과 같은 문장으로 바꾼다. **`label`은 바꾸지 마라.** 이유: 브라우저 테스트가 이 이름으로 예시를 고른다.
- `apply_reply` · `task_type` `"출하 경위 확인"` 예시 2개를 더한다. 다른 예시와 같은 키 구조(`action`, `task_type`, `customer_id`, `label`, `tone`, `source`, `inputs`)를 쓴다.
  - 유리: `label` `"경위 확인됨 (보류 표시 미반영, 차단 항목 추가)"`, `result` `"경위 확인됨"`, `reply_text`는 demo2의 2-4c와 같은 문장
  - 불리: `label` `"확인 불가 (7일 추가 필요)"`, `result` `"확인 불가"`, `reply_text` `"출하 지시 기록 확인 불가, 7일 추가 필요"`
  - 둘 다 `source` `"모의"`, `customer_id` `null`
- 파일 맨 위 `description`의 규칙("`inputs`에는 실행 중에 정해지는 작업·계획·클레임 ID와 적용일을 넣지 않는다")을 지킨다.

### 4. 테스트 (`backend/tests/`)

- `test_scenarios.py`:
  - 시연 1: 1-6 직전에 `warnings`에 `open_hold_shipment_check`가 있고, 1-6 뒤 계획이 확정이며 그 액션 기록의 규칙에 `R11-1`이 있다.
  - 시연 2: 2-4b 뒤(계획 v2 초안)에 경고가 있고, 2-4c 뒤 출하 경위 확인 작업이 완료이고 경고가 없다. 2-5 뒤 계획 v2가 확정이고 그 액션 기록의 규칙에 `R11-1`이 없다. 계획 버전은 2개 그대로다.
  - 모의 입력 예시 목록 확인(`need` 집합)에 `("apply_reply", "출하 경위 확인", "경위 확인됨", "유리")`, `("apply_reply", "출하 경위 확인", "확인 불가", "불리")`를 더한다.
- 예시 개수(22 → 24)나 시나리오 단계 수를 숫자로 확인하는 테스트가 있으면 맞게 고친다.
- 시연 3-A·3-B와 `other-batch` 시나리오 파일은 바꾸지 않는다. 이 시나리오들에는 재공급 계획 승인 단계가 없다.

## Acceptance Criteria

저장소 루트에서 실행한다. `--deselect` 4건은 이 phase 이전부터 로컬 `w03_system/.env` 때문에 실패하던 테스트다.

명령은 한 줄에 하나씩 쓴다. 실행기(`execute.py`)가 이 블록을 줄마다 따로 실행하므로 줄 끝 `\`로 이어 쓰면 안 된다. `--deselect`의 테스트 이름은 pytest 기준 폴더(`w03_system`, `pytest.ini`)에서 본 경로다.

```bash
w03_system/.venv/bin/python -m pytest -q w03_system/backend/tests --deselect backend/tests/test_ai.py::test_no_key --deselect backend/tests/test_ai.py::test_classify_ok_and_logged --deselect backend/tests/test_ai.py::test_real_call_saves_answer_and_replay_returns_it_without_calling --deselect backend/tests/test_api.py::test_ai_no_key
python3 -c "import json; [json.load(open(f'w03_system/scenarios/{n}.json', encoding='utf-8')) for n in ('demo1','demo2','reply-examples')]"
```

## 검증 절차

1. 위 AC 커맨드를 실행한다. 실패 0건이어야 한다.
2. 체크리스트를 확인한다:
   - 시나리오의 문장·날짜·단계 번호가 `3-design/demo-scenarios.md`와 같은가? (1-6 근거, 2-4c 회신 문장, 07-09)
   - 새로 넣은 회신과 예시에 `"source": "모의"`가 붙어 있는가? (완료 조건 5: 원본과 가정 구분)
   - 불리한 회신 예시("확인 불가")가 함께 들어갔는가? (유리한 회신만으로 검증을 대신할 수 없다)
   - CLAUDE.md 금지 규칙을 위반하지 않았는가?
3. 결과에 따라 `w03_system/phases/2-recurrence-check/index.json`의 해당 step을 업데이트한다:
   - 성공 → `"status": "completed"`, `"summary": "산출물 한 줄 요약"` (다음 step이 쓸 것을 적는다: 새 단계 id `2-4c`, 새 예시 `label` 2개, 바뀐 근거 문장, `scenario.py`를 고쳤는지)
   - 수정 3회 시도 후에도 실패 → `"status": "error"`, `"error_message": "구체적 에러 내용"`
   - 사용자 개입 필요 → `"status": "blocked"`, `"blocked_reason": "구체적 사유"` 후 즉시 중단

## 금지사항

- `backend/core/`의 규칙·액션(`rules.py`, `actions.py`, `ontology.py`)을 고치지 마라. 이유: step 0에서 확정했다. 시나리오가 통과하지 않으면 시나리오 쪽을 맞춘다. 예외는 위에 적은 `scenario.py`의 선택자 처리뿐이다.
- 시연 1에 T-01 회신 단계를 넣지 마라. 이유: 시연 1은 "경위를 모르는 채 근거를 적고 승인"을 보이고, 회신으로 경고가 풀리는 것은 시연 2에서 보인다(decisions 2026-11-15 ④).
- `data/ai_replay.json`을 고치지 마라. 이유: 실제로 받은 AI 답을 저장한 파일이다.
- `frontend/`, `e2e/`를 고치지 마라. 이유: 다음 step들의 범위다.
- AI를 실제로 호출하는 테스트나 명령을 실행하지 마라. 이유: API 비용이 들고 이 step의 검증에 필요 없다.
- `01_참가자_배포용/04_원본데이터/`의 파일을 수정하지 마라. 이유: 원본 데이터는 대회 규칙상 수정 금지다.
- 기존 테스트를 깨뜨리지 마라.
