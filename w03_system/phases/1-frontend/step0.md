# Step 0: server-fixes

## 읽어야 할 파일

먼저 아래 파일들을 읽고 과제와 설계 의도를 파악하라:

- `/CLAUDE.md`
- `/w03_system/brain/status.md`
- `/w03_system/brain/3-design/architecture.md` (API 표, 모듈 경계)
- `/w03_system/brain/3-design/decisions.md` ("화면 구현 전 정리 4건" ①③④, "1-frontend step 설계" 행)
- `/w03_system/brain/3-design/demo-scenarios.md` (시연 3건, 맨 아래 "모의 회신 목록")
- `/w03_system/brain/3-design/business-model.md` §4 (배치 상태), R6·R6-1·R6-2
- `/w03_system/backend/core/rules.py` (`batch_metrics`, `target_batch_state`)
- `/w03_system/backend/core/view.py`, `/w03_system/backend/core/scenario.py`, `/w03_system/backend/core/ontology.py` (`TASK_TYPES`, `ACTIONS`)
- `/w03_system/backend/ai/tasks.py` (`_batch_facts`, `_agenda_input`)
- `/w03_system/backend/api/main.py`
- `/w03_system/scenarios/*.json` (시나리오 형식)
- `/w03_system/backend/tests/test_rules.py`, `test_scenarios.py`, `test_api.py`, `test_ai.py`

이전 phase(`0-backend`)에서 만들어진 코드를 꼼꼼히 읽고, 설계 의도를 이해한 뒤 작업하라.

## 작업

화면을 만들기 전에 서버에서 보완할 3가지를 한다. 화면 코드는 이 step에서 만들지 않는다.

### 1. 회수 대상 배치에 관찰 해제 예정일이 나가는 문제

현재 `rules.batch_metrics`는 배치 상태와 무관하게 `release_due_date`·`release_basis`를 돌려준다. 그래서 기준 초과·상신중·회수진행·부분회수·조사계속 배치에도 "관찰 해제 예정일"이 붙고, AI 안건 요약 입력(`ai/tasks.py`의 `_batch_facts`)에 섞여 들어간다 (2026-11-12 실제 호출에서 발견).

- 관찰 해제 예정일은 **관찰 대상인 배치**(상태 `관찰`, `관찰해제`)에만 의미가 있다. 그 밖의 상태에서는 `release_due_date`·`release_basis`가 `None`이어야 한다.
- 어디서 거를지는 코드를 읽고 정하라. 단, **`target_batch_state`의 전이 결과가 지금과 같아야 한다** (기존 시연 테스트가 그대로 통과).
- 값이 `None`이면 AI 입력(`_batch_facts`)에서 "관찰 해제 예정일"·"해제 기준" 키 자체를 뺀다. 이유: `null` 값도 모델이 "해제 예정일 미정"으로 읽고 요약에 쓴다.
- 테스트 추가: 사건을 연 직후 기준 초과 배치 2개(`B-02-2602-01`, `B-02-2603-01`)의 `release_due_date`가 `None`이고, 관찰해제 배치 2개는 값이 그대로다. `agenda_summary`의 `build_request` 입력에 "관찰 해제 예정일" 문자열이 없다.

### 2. 모의 입력 예시 제공

화면의 입력 폼은 예시를 골라 폼을 채우고, 사람이 고친 뒤 직접 실행한다 (`decisions.md` "화면 구현 전 정리 4건" ①). 예시는 `scenarios/` 아래에 두고 서버가 내려준다.

파일: `w03_system/scenarios/reply-examples.json`

```json
{
  "examples": [
    {
      "action": "apply_reply",
      "task_type": "출하처 확인",
      "customer_id": null,
      "label": "확인 불가 (7일 추가)",
      "tone": "불리",
      "source": "모의",
      "inputs": {"reply_text": "기록 확인 불가, 7일 추가 필요", "result": "확인 불가"}
    }
  ]
}
```

- `action`: 예시가 쓰이는 액션 (`apply_reply` / `committee_decision` / `plan_decision` / `register_claim` / `resolve_claim` / `register_news`).
- `task_type`: `apply_reply`일 때만. `customer_id`는 같은 유형의 작업이 고객별로 여러 개일 때만 쓴다(수주 급감 확인: C-101, C-104). 없으면 `null`.
- `tone`: `"유리"` / `"불리"`. `source`: `"모의"` 또는 `"원본"`(보도 내용처럼 원본에서 온 것).
- `inputs`: 그 액션 입력 중 **ID와 적용일을 뺀** 값만 넣는다. 이유: 작업·계획·클레임 ID는 실행 중에 정해지고, 적용일은 사람이 넣는다.
- 내용: `demo-scenarios.md`의 "모의 회신 목록" 표의 모든 칸(유리·불리)과 시연 표의 모의 입력(1-3, 1-5, 1-6, 1-7, 2-1, 2-2a, 2-2b, 2-4, 2-5, 3-2, 3-3, 3-4, 3-5, 3-6)을 덮는다. 문장은 기존 `scenarios/demo*.json`에 있는 것을 그대로 쓴다. 표에만 있고 문장이 없는 불리한 회신은 새로 쓰되 한 문장으로 짧게 쓴다.
- `apply_reply` 예시의 `result`는 반드시 `ontology.TASK_TYPES[task_type].allowed_results` 안에 있어야 한다. 테스트로 검사한다.

조회 함수와 API:

```python
# backend/core/scenario.py
def list_reply_examples() -> list[dict]: ...   # 파일의 examples 그대로
```

| 메서드·경로 | 응답 |
|---|---|
| `GET /api/reply-examples` | `{"examples": [...]}` |

핵심 규칙:
- **이 파일이 시나리오 목록에 나오면 안 된다.** `scenario.list_scenarios()`와 `POST /api/scenarios/{name}`이 `reply-examples`를 시나리오로 취급하지 않게 하라(코드를 읽고 방법을 정하라). 테스트로 검사한다.
- 예시를 사건 뷰(`incident_view`)에 넣지 마라. 이유: 사건 뷰는 원본·도출·시스템 값이고, 모의 입력 예시는 아직 실행되지 않은 입력이다. 섞이면 출처 구분이 흐려진다.

### 3. 시나리오 목록에 출발 상태 정보

화면의 초기화 메뉴는 "빈 상태" 또는 "시나리오의 출발 상태"를 고른다 (`decisions.md` ③). 출발 상태는 `setup: true`인 단계까지 실행한 상태이고 `POST /api/scenarios/{name}?setup_only=true`가 이미 지원한다.

- `list_scenarios()`의 각 항목에 `setup_count`(setup 단계 중 액션이 있는 단계 수)를 더한다. 화면은 `setup_count > 0`인 시나리오만 출발 상태 메뉴에 보인다.

### 4. 문서

- `architecture.md` API 표에 `GET /api/reply-examples`를 더하고, `GET /api/scenarios` 응답 설명에 `setup_count`를 더한다.
- `status.md` "다음 할 일"에서 "AI 입력 정리: 회수 대상 배치의 관찰 해제 예정일 …" 항목을 지우고 "끝난 것"에 한 줄로 옮긴다.

## Acceptance Criteria

```bash
w03_system/.venv/bin/python -m pytest -q w03_system/backend/tests
```

기존 171개와 새 테스트가 모두 통과한다.

## 검증 절차

1. 위 AC 커맨드를 실행한다.
2. 아키텍처 체크리스트를 확인한다:
   - `3-design/architecture.md`의 디렉토리 구조·모듈 경계를 따르는가? (`core`는 `api`·`ai`를 import하지 않는다)
   - `3-design/decisions.md`의 기술 스택·설계 결정을 벗어나지 않았는가?
   - `3-design/business-model.md`의 객체·상태·판단 규칙과 일치하는가?
   - CLAUDE.md 금지 규칙(원본 데이터 수정 금지, 가정 데이터 분리 등)을 위반하지 않았는가?
3. 결과에 따라 `w03_system/phases/1-frontend/index.json`의 해당 step을 업데이트한다:
   - 성공 → `"status": "completed"`, `"summary": "산출물 한 줄 요약"` (예시 파일 형식, 새 API 경로, `setup_count`를 다음 step이 알 수 있게 적는다)
   - 수정 3회 시도 후에도 실패 → `"status": "error"`, `"error_message": "구체적 에러 내용"`
   - 사용자 개입 필요 → `"status": "blocked"`, `"blocked_reason": "구체적 사유"` 후 즉시 중단

## 금지사항

- 기존 테스트의 기대값(불량률 11.9%·11.6%, 해제 120·128일, 재공급 순서 등)을 바꾸지 마라. 이유: `demo-scenarios.md`의 숫자가 기준이고, 이 step은 표시 값만 고친다.
- 판정 규칙·전이표·액션 정의를 바꾸지 마라. 이유: 이 step의 범위는 해제 예정일 표시, 예시 제공, 목록 필드 추가뿐이다.
- `w03_system/frontend/`를 만들지 마라. 이유: 다음 step의 범위다.
- `01_참가자_배포용/04_원본데이터/`의 파일을 수정하지 마라. 이유: 원본 데이터는 대회 규칙상 수정 금지다.
- 기존 테스트를 깨뜨리지 마라
