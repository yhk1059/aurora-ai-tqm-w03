# Step 2: plan-ui

## 읽어야 할 파일

먼저 아래 파일들을 읽고 과제와 설계 의도를 파악하라:

- `/CLAUDE.md`
- `/w03_system/brain/status.md`
- `/w03_system/brain/3-design/architecture.md` (화면은 서버가 준 사건 뷰와 가능한 액션만 그린다)
- `/w03_system/brain/3-design/ui-guide.md` (디자인 원칙, 안티패턴, 색상, "결정 창", 재공급 계획 탭, 경고 표시, 규칙 번호·가정 ID는 툴팁으로)
- `/w03_system/brain/3-design/decisions.md` (맨 아래 2026-11-15 "재발 방지 고리 (R11-1)" 행)
- `/w03_system/brain/3-design/business-model.md` (§5의 R11-1, §8-5 "재공급 계획 결정 입력")
- `/w03_system/frontend/src/tabs/PlanTab.tsx` (`useOrderDropWaiting`, 영업 임원 확인 대기 주황 띠, `PlanEvidence`, `DecisionCard`, `PlanTarget`)
- `/w03_system/frontend/src/components/ActionForm.tsx` (`ActionDialog`의 `needReason`, `ConfirmDialog`에 넘기는 `note`·`confirmDisabled`)
- `/w03_system/frontend/src/components/TaskList.tsx` (열린 작업의 `기한 지남`·`연장됨 (처음 기한 …)` 표시)
- `/w03_system/frontend/src/components/WarningLine.tsx`, `/w03_system/frontend/src/components/SourceBadge.tsx`
- `/w03_system/frontend/src/types.ts`
- step 0에서 바뀐 파일: `/w03_system/backend/core/rules.py`(경고 `open_hold_shipment_check`), `/w03_system/backend/core/actions.py`(`approve_reason_required`)
- step 1에서 바뀐 파일: `/w03_system/scenarios/demo2.json`(단계 `2-4c`), `/w03_system/scenarios/reply-examples.json`

이전 step에서 만들어진 코드를 꼼꼼히 읽고, 설계 의도를 이해한 뒤 작업하라.

## 배경

서버에 규칙 R11-1이 들어갔다. 화면이 읽을 값은 세 가지다.

| 값 | 위치 | 뜻 |
|---|---|---|
| 경고 `open_hold_shipment_check` | `view.warnings` (`target` = 재공급 계획 초안, `evidence` = 열린 출하 경위 확인 작업 id) | 출하 경위 확인이 끝나지 않았다 |
| `approve_reason_required` | `view.available_actions`의 `plan_decision` 대상 항목 | 이 계획을 승인하려면 근거가 필수다 |
| 출하 경위 확인 작업 | `view.tasks` 중 `type === '출하 경위 확인'` (`state`, `due_date`, `reply`, `result`, `replied_date`) | 작업 상태와 회신 내용 |

지금 화면은 근거 없이 승인 버튼을 누를 수 있고, 서버가 거부하면 오류만 보인다. 이 step은 SCM이 **결정하기 전에** 상황을 알 수 있게 한다.

## 작업

이 step은 `frontend/src/`와 `ui-guide.md`만 다룬다.

### 1. 타입 (`types.ts`, `PlanTab.tsx`의 `PlanTarget`)

- `plan_decision` 대상 항목에 `approve_reason_required?: boolean`을 더한다.

### 2. 재공급 계획 탭의 경고 띠 (`PlanTab.tsx`)

- 초안 계획에 `open_hold_shipment_check` 경고가 있으면, 영업 임원 확인 대기 띠와 같은 모양(주황)의 띠를 하나 더 보인다.
- 문구: `출하 경위 확인 대기 N건` + 한 줄 설명 `QC 보류 배치가 출하된 경위가 아직 확인되지 않았습니다. 승인하려면 근거를 적어야 합니다.`
- 규칙 번호와 가정 ID(`규칙 R11-1 · 가정 A-18`)는 `title` 툴팁에 둔다. 본문에 쓰지 않는다.
- 건수는 서버 경고의 `evidence` 길이를 쓴다. 화면에서 작업 목록을 세어 경고 여부를 다시 판단하지 마라. 이유: 판단은 서버 규칙이 한다.

### 3. SCM 결정 창의 판단 근거 (`PlanEvidence`)

`view.tasks`에 출하 경위 확인 작업이 있을 때만 `출하 경위` 줄을 더한다. 작업이 없는 사건에서는 줄을 그리지 않는다.

- 작업이 열림: 주황 글자 `확인 대기` + 기한. 기한 연장 표시는 `TaskList.tsx`가 이미 쓰는 방식을 재사용한다(필요하면 그 계산을 작은 함수로 빼서 두 곳에서 쓴다). 같은 계산을 두 번 구현하지 마라.
- "확인 불가" 회신으로 열려 있는 경우: 위 표시에 더해 마지막 회신 문장을 보인다.
- 작업이 완료: 초록 배지 `확인됨` + 회신 문장 + 회신 적용일. 회신은 모의 입력이므로 `SourceBadge`로 출처(`모의`)를 붙인다.

### 4. 근거 필수 (`ActionDialog`)

`ActionDialog`가 "어떤 결과에서 근거가 필수인지"를 밖에서 받게 한다.

```ts
/** 결과 이름 → 근거가 비었을 때 보일 안내 문구. 거절(A-09)은 기본으로 들어 있다 */
reasonRequired?: Partial<Record<string, string>>
```

- 지금의 `needReason`(거절 전용)을 이 prop과 합친다. 고른 결과가 여기에 있고 근거가 비어 있으면(공백만 있는 경우 포함) 실행 버튼을 끄고 안내 문구를 `note`에 보인다.
- `PlanTab`의 `DecisionCard`는 대상 항목의 `approve_reason_required`가 참일 때 `{ 승인: '출하 경위 확인이 끝나지 않아, 승인하려면 근거를 적어야 합니다.' }`를 넘긴다.
- 위원회 결정 창의 동작(거절은 사유 필수)은 그대로여야 한다.
- 서버 확인은 그대로 남아 있다. 화면의 버튼 끄기는 안내이고, 최종 확인은 서버가 한다.

### 5. 문서 (`brain/3-design/ui-guide.md`)

- SCM 결정 창과 재공급 계획 탭을 설명하는 자리에 위 2~4를 짧게 덧붙인다(띠 문구, `출하 경위` 줄의 세 가지 모양, 근거 필수 안내).
- 새 버전 번호를 만들거나 `decisions.md`에 행을 더하지 않는다. 이유: 결정은 2026-11-15 "재발 방지 고리" 행에 이미 기록됐다.

### 6. 직접 확인

화면을 빌드하고 서버 하나로 띄워 아래를 확인한 뒤 서버를 종료한다. 포트는 비어 있는 것을 쓴다.

```bash
npm --prefix w03_system/frontend run build
W03_DB_PATH=$(mktemp -d)/w03.sqlite w03_system/.venv/bin/uvicorn backend.api.main:app --app-dir w03_system --port 8010 &
curl -s -X POST "localhost:8010/api/scenarios/demo2?actor=scm&setup_only=true" | head -c 200
```

- 시나리오 실행 API의 인자 이름은 `backend/api/main.py`에서 확인하고 맞게 쓴다.
- 브라우저 도구를 쓸 수 있으면 재공급 계획 탭에서 띠, 결정 창의 `출하 경위` 줄, 근거를 비웠을 때 꺼진 승인 버튼을 눈으로 확인한다. 쓸 수 없으면 건너뛰고 summary에 "화면 눈 확인 안 함"이라고 적는다.

## Acceptance Criteria

저장소 루트에서 실행한다.

명령은 한 줄에 하나씩 쓴다. 실행기(`execute.py`)가 이 블록을 줄마다 따로 실행하므로 줄 끝 `\`로 이어 쓰면 안 된다. `--deselect`의 테스트 이름은 pytest 기준 폴더(`w03_system`, `pytest.ini`)에서 본 경로다.

```bash
npm --prefix w03_system/frontend run build
test -f w03_system/frontend/dist/index.html
w03_system/.venv/bin/python -m pytest -q w03_system/backend/tests --deselect backend/tests/test_ai.py::test_no_key --deselect backend/tests/test_ai.py::test_classify_ok_and_logged --deselect backend/tests/test_ai.py::test_real_call_saves_answer_and_replay_returns_it_without_calling --deselect backend/tests/test_api.py::test_ai_no_key
```

## 검증 절차

1. 위 AC 커맨드를 실행한다. 빌드(`tsc` 포함)가 오류 없이 끝나야 한다.
2. 체크리스트를 확인한다:
   - `3-design/ui-guide.md`의 색 뜻을 지켰는가? (주황 = 경고·미확인, 초록 = 확인. 새 색을 만들지 않는다)
   - 안티패턴을 쓰지 않았는가? (장식용 그라데이션·글로우, 판단에 쓰이지 않는 차트)
   - 화면이 규칙을 다시 계산하지 않는가? (경고 여부와 근거 필수 여부는 서버 값만 읽는다)
   - 모의 회신 문장에 출처 표시가 붙었는가? (완료 조건 5)
   - CLAUDE.md 금지 규칙을 위반하지 않았는가?
3. 결과에 따라 `w03_system/phases/2-recurrence-check/index.json`의 해당 step을 업데이트한다:
   - 성공 → `"status": "completed"`, `"summary": "산출물 한 줄 요약"` (다음 step의 브라우저 테스트가 쓸 것을 적는다: 띠·줄·안내의 정확한 문구, 붙인 `data-*` 속성, 눈 확인 여부)
   - 수정 3회 시도 후에도 실패 → `"status": "error"`, `"error_message": "구체적 에러 내용"`
   - 사용자 개입 필요 → `"status": "blocked"`, `"blocked_reason": "구체적 사유"` 후 즉시 중단

## 금지사항

- `backend/`와 `scenarios/`를 고치지 마라. 이유: step 0·1에서 확정했다. 서버 값이 부족해 보이면 고치지 말고 `blocked`로 사유를 남겨라.
- `e2e/`를 고치지 마라. 이유: 다음 step의 범위다. 이 step 뒤에 브라우저 테스트 일부가 깨질 수 있고, 그것은 step 3이 맞춘다.
- 기존 요소의 글자와 구조(`결정 입력` 버튼, `판단 근거` 제목, 결과 선택 버튼, `… 결정 실행` 버튼 이름, 예시 선택 줄)를 바꾸지 마라. 이유: 브라우저 테스트 도우미(`e2e/helpers.py`)가 이 글자에 기대고 있다. 새 요소를 더하기만 한다.
- 사건 탭, 기록 탭, 온톨로지 탭의 배치를 바꾸지 마라. 이유: 이 step의 범위는 재공급 계획 탭과 결정 창이다. 새 경고는 사건 뷰의 `warnings`를 그리는 기존 자리에 자동으로 나타날 수 있고, 그것은 그대로 둔다.
- `frontend/dist/`를 git에 올리지 마라. 이유: 빌드 산출물이다.
- 배포 명령(`axhub deploy`, `git push`)을 실행하지 마라. 이유: `origin`의 `main`에 푸시하면 운영에 바로 배포된다. 배포는 사용자가 지시한다.
- `01_참가자_배포용/04_원본데이터/`의 파일을 수정하지 마라. 이유: 원본 데이터는 대회 규칙상 수정 금지다.
- 기존 서버 테스트를 깨뜨리지 마라.
