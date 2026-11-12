# Step 5: plan-tab

## 읽어야 할 파일

먼저 아래 파일들을 읽고 과제와 설계 의도를 파악하라:

- `/CLAUDE.md`
- `/w03_system/brain/status.md`
- `/w03_system/brain/3-design/architecture.md` (패턴 4)
- `/w03_system/brain/3-design/ui-guide.md` ("레이아웃"의 재공급 계획 탭, "버튼", "타이포그래피")
- `/w03_system/brain/3-design/business-model.md` R10·R10-1·R10-2·R11, §4-3 (계획 상태), §8-5 (`plan_decision`)
- `/w03_system/brain/3-design/demo-scenarios.md` (1-3 ~ 1-6, 2-4 ~ 2-5, 3-2 ~ 3-4에서 계획이 어떻게 바뀌는지)
- `/w03_system/brain/3-design/assumptions.md` (A-01, A-03, A-04, A-13, A-14)
- `/w03_system/backend/core/view.py` (`plans[]`: `lines`·`diff`·`release_condition`·`supply_condition`·`supply_batch`·`slack_capacity`·`recalc_cause`·`decisions`, 그리고 `recall_quantities`, `held_customers`, `decisions`, `tasks`)
- `/w03_system/backend/core/rules.py` (`plan_diff`, `supply_condition`, `resupply_lines`, `held_customers`가 돌려주는 키)
- `/w03_system/backend/core/actions.py` (`_targets_plan_decision`)
- `/w03_system/frontend/src/` 전부 (특히 `components/ActionForm.tsx`, `components/ExamplePicker.tsx`, `components/ConfirmDialog.tsx`)

이전 step에서 만들어진 코드를 꼼꼼히 읽고, 설계 의도를 이해한 뒤 작업하라.

## 작업

재공급 계획 탭(`frontend/src/tabs/PlanTab.tsx`)을 만든다. 이 탭은 "다른 부서(영업)의 회신이 계획을 바꾸고, 그 대가로 누가 얼마나 밀리는지"를 보여주는 곳이다.

### 계획이 없을 때

"재공급 계획이 아직 없습니다" 한 줄. 왜 없는지는 화면이 추측하지 않는다.

### 버전 선택

- 계획은 여러 버전이 있다(`view.plans`, 버전순). 위쪽에 버전 목록: 버전 번호, 상태 배지(초안·확정·기각·대체됨), 만든 날. 기본 선택 = 가장 최근 버전.
- 선택한 버전의 "왜 다시 계산됐는지"(`recalc_cause`: 규칙, 계기가 된 액션, 이전 버전)를 한 줄로 보인다.

### 계획 표

선택한 버전의 줄(`lines`, 순위순): 순위 · 고객 ID와 이름 · 수량 · 수량 근거(`qty_basis`, 하한이면 "하한" 표시) · 완료 예상 월 · 우선순위 이유 · 출처 배지.

- 숫자 열은 오른쪽 정렬, `tabular-nums`.
- 줄의 출처·가정(`attrs.assumptions` 등 서버가 준 것)을 출처 배지로 붙인다(예: `가정 A-03`).
- 보류된 고객(`view.held_customers`)은 표 아래에 따로 "계획에서 보류된 고객"으로 이유와 함께 보인다(예: C-105 미확인).

### 이전 버전과 비교

`plans[].diff`(서버가 계산)가 있으면 표 옆에 나란히 보인다: 고객별 **이전 순위 → 지금 순위**, **이전 예상 월 → 지금 예상 월**, 지연 개월.

- 밀린 고객(`delay_months > 0`)은 빨강 시맨틱 색 + "N개월 지연" 글자로 강조한다. 앞당겨진 고객과 새로 추가된 고객(`added`)도 글자로 표시한다.
- 비교 기준이 어느 버전인지(`base_plan_id`) 적는다.
- 화면에서 버전 둘을 직접 비교해 차이를 계산하지 않는다. `diff`가 비어 있으면 "비교할 이전 버전 없음".

### 출고 조건 (R11)

카드 하나: 충족 여부(`supply_condition.met`: 초록 "충족" / 주황 "미충족" + `reason`), 공급 배치 ID, 원료 로트, QC 결과, 월 여유 능력(`slack_capacity`)과 출처 배지.

### 결정과 경고

- 이 계획에 대한 결정 이력(`plans[].decisions` → `view.decisions`): 결과, 근거, 결정자, 적용일.
- 열린 "수주 급감 확인" 작업이 있으면 경고 줄: "영업 임원 확인 대기 N건. 회신이 오면 새 버전이 만들어질 수 있음". 근거는 `view.tasks`의 열린 작업 목록이다.
- `available_actions`에 `plan_decision`이 있고 이 버전이 대상(`targets.plan_id`)이면 "결정 입력" 버튼(Primary). 누르면 `ConfirmDialog` 안에 `ActionForm`(`fixed = {plan_id}`) + `ExamplePicker`. 승인할 수 없는 계획(`can_approve: false`)이면 이유(`reason`)를 폼 위에 보인다. 실제 거부는 서버가 한다.

### 실행 확인

서버와 화면을 띄우고 초기화 메뉴에서 "시연 2 출발 상태"를 고른 뒤 확인하고 종료한다:
- v1 확정, 순서 C-103 → C-102 → C-101 → C-104 → C-108.
- 사건 탭에서 C-101 작업에 "우선 공급 요청" 회신을 넣으면 v2 초안이 생기고, 비교에 C-103·C-102 지연이 강조된다.
- 역할을 SCM으로 바꾸면 결정 버튼이 보이고, 승인하면 v2 확정·v1은 목록에 남는다.

## Acceptance Criteria

```bash
npm --prefix w03_system/frontend run build
w03_system/.venv/bin/python -m pytest -q w03_system/backend/tests
```

## 검증 절차

1. 위 AC 커맨드를 실행한다.
2. 아키텍처 체크리스트를 확인한다:
   - `3-design/architecture.md`의 디렉토리 구조·모듈 경계를 따르는가?
   - `3-design/ui-guide.md`를 따르고 안티패턴을 쓰지 않았는가? (차트·간트 없음, 표로 보인다)
   - `3-design/business-model.md`의 계획 상태·R10·R11과 일치하는가?
   - CLAUDE.md 금지 규칙을 위반하지 않았는가?
3. 결과에 따라 `w03_system/phases/1-frontend/index.json`의 해당 step을 업데이트한다:
   - 성공 → `"status": "completed"`, `"summary": "산출물 한 줄 요약"`
   - 수정 3회 시도 후에도 실패 → `"status": "error"`, `"error_message": "구체적 에러 내용"`
   - 사용자 개입 필요 → `"status": "blocked"`, `"blocked_reason": "구체적 사유"` 후 즉시 중단

## 금지사항

- 화면에서 순위·예상 월·지연 개월을 계산하지 마라. 이유: R10과 `plan_diff`는 서버에 있고, 화면 계산은 서버와 어긋난다.
- 일정 막대(간트)나 차트를 넣지 마라. 이유: `ui-guide.md` 안티패턴. 순위·월은 표로 충분하다.
- 계획 줄을 화면에서 고칠 수 있게 만들지 마라(순서 끌어 옮기기 등). 이유: 계획은 규칙이 계산하고 사람은 승인·거절만 한다(R10, R12).
- 서버 코드(`w03_system/backend/`)를 고치지 마라. 이유: 이 step은 화면만 다룬다. 서버에 없는 값이 필요하면 `blocked`로 남겨라.
- `01_참가자_배포용/04_원본데이터/`의 파일을 수정하지 마라. 이유: 원본 데이터는 대회 규칙상 수정 금지다.
- 기존 테스트를 깨뜨리지 마라
