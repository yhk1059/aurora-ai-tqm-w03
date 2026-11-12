# Step 3: action-forms

## 읽어야 할 파일

먼저 아래 파일들을 읽고 과제와 설계 의도를 파악하라:

- `/CLAUDE.md`
- `/w03_system/brain/status.md`
- `/w03_system/brain/3-design/architecture.md` (패턴 2·4, API 표, 오류 응답)
- `/w03_system/brain/3-design/ui-guide.md` ("버튼", "입력 필드", "레이아웃")
- `/w03_system/brain/3-design/decisions.md` ("화면 구현 전 정리 4건" ①)
- `/w03_system/brain/3-design/business-model.md` §8-5 (액션과 역할), R9·R9-1·R12
- `/w03_system/brain/3-design/demo-scenarios.md` (시연 3건의 입력, "모의 회신 목록")
- `/w03_system/backend/core/ontology.py` (`ACTIONS`의 `inputs`: key·name·type·required·choices·description, `TASK_TYPES`)
- `/w03_system/backend/core/actions.py` (`available_actions`, `_targets_*`가 돌려주는 모양, `_SPECS`의 `extra_inputs`, `_validate_inputs`)
- `/w03_system/backend/core/view.py` (`tasks`, `claims`)
- `/w03_system/scenarios/reply-examples.json`
- `/w03_system/frontend/src/` 전부 (특히 `App.tsx`의 `AppCtx`, `tabs/IncidentTab.tsx`, `components/BatchCard.tsx`)

이전 step에서 만들어진 코드를 꼼꼼히 읽고, 설계 의도를 이해한 뒤 작업하라.

## 작업

사건 탭에서 사람이 액션을 실행할 수 있게 한다: 액션 버튼, 입력 폼, 확인 창, 작업 목록과 회신 입력. 재공급 계획 결정(`plan_decision`)의 화면은 계획 탭 step에서 붙이지만, **폼 자체는 이 step에서 만든 것을 그대로 쓸 수 있어야 한다**.

### 액션 폼은 온톨로지 정의에서 만든다

`components/ActionForm.tsx`

```ts
type Props = {
  action: string;                          // 액션 이름 (예: "submit_agenda")
  fixed?: Record<string, unknown>;         // 이미 정해진 입력 (예: 이 작업의 task_id). 폼에 읽기 전용으로 보인다
  initial?: Record<string, unknown>;       // 폼 초기값 (예시·AI 초안에서 채울 때)
  onDone?: () => void;
}
```

- 필드는 `ontology.actions[action].inputs`를 읽어 그린다: `date` → 날짜 입력, `text` → 여러 줄 입력, `int` → 숫자, `choice` → 선택(`choices`), `id`·`id_list` → 선택(후보는 `available_actions`의 그 액션 `targets[key]`). 필드 이름·필수 여부·설명도 정의에서 가져온다.
- `targets[key]`의 항목은 문자열일 수도 있고 객체(`{id, ...}`)일 수도 있다. 둘 다 처리한다.
- `targets`에 후보가 없는 `id` 입력(예: `register_claim`의 `customer_id`)은 사건 뷰의 해당 객체 목록(`view.customers`)에서 고른다.
- `apply_reply`의 `result` 선택지는 그 작업의 `allowed_results`다(`view.tasks[].allowed_results` 또는 `targets.task_id[].allowed_results`).
- 적용일 기본값 = 사건의 현재 적용일(`view.incident.current_date`). 고칠 수 있다.
- 실행은 `AppCtx.run(action, inputs)`. 서버가 거부하면(`ApiError`) 폼 안에 `message`를 보이고 입력을 유지한다. 화면에서 미리 막는 것은 "필수 입력이 비었음"뿐이다.

핵심 규칙:
- **버튼은 `view.available_actions`에 있는 액션만 그린다.** 지금 역할로 실행할 수 없는 액션은 보이지 않는다. 화면에 "이 상태면 이 버튼" 같은 조건을 쓰지 않는다.
- **온톨로지 정의에 액션이 하나 늘어도 이 컴포넌트는 그대로 동작해야 한다.** 액션 이름별 분기는 "어디에 버튼을 둘지"에만 쓴다.
- **되돌릴 수 없는 결정**(`committee_decision`, `plan_decision`)은 버튼을 누르면 `ConfirmDialog` 안에서 폼(결과·사유)을 받고 실행한다. 거절인데 사유가 비면 서버가 409로 거부한다. 그 메시지를 그대로 보인다.

### 모의 입력 예시

`components/ExamplePicker.tsx`: 폼 위에 "예시" 선택 줄을 둔다.

- `GET /api/reply-examples`에서 그 액션(그리고 `apply_reply`면 그 작업의 유형, `customer_id`가 있으면 작업 대상 고객)에 맞는 예시만 보인다.
- 각 예시에 `tone`(유리/불리)과 출처 배지(`모의`는 점선)를 붙인다.
- 고르면 폼의 해당 필드가 채워지고, **사람이 고칠 수 있다. 실행은 사람이 버튼으로 한다.** 예시를 고르는 것만으로 액션이 실행되면 안 된다.
- 맞는 예시가 없으면 줄을 그리지 않는다.

### 버튼 위치

| 액션 | 위치 |
|---|---|
| `submit_agenda`, `committee_decision` | 사건 탭 왼쪽 위 "판정" 줄에 버튼. 대상 배치는 폼에서 여러 개 고른다(기본값 = 후보 전부). 해당 배치 카드의 액션 자리에도 같은 폼을 여는 버튼을 둔다 |
| `register_claim`, `register_news` | 사건 탭 왼쪽 위 "새 입력" 줄 |
| `resolve_claim` | 미확정 클레임이 있는 배치 카드 안, 그 클레임 줄 옆 |
| `apply_reply` | 작업 목록의 각 작업 |

### 작업 목록

`components/TaskList.tsx` (사건 탭 오른쪽, `view.tasks`)

- 작업마다: 코드(T-01 등)·유형, 상태 배지, 담당 부서, 기한, 대상(배치·고객. 출하처 확인은 배치 → 고객과 확인 수준), 만든 근거(`created_by`의 규칙·결정).
- 열린 작업 먼저, 그다음 완료. 회신이 있으면 회신 문장과 결과, 회신일을 보인다.
- 회신할 수 있는 작업(`available_actions`의 `apply_reply.targets.task_id`에 있는 것)에만 "회신 입력" 버튼. 누르면 그 자리에서 `ActionForm`(`fixed = {task_id}`) + `ExamplePicker`가 펼쳐진다.
- 다음 step(AI)이 회신 문장 옆에 "AI로 분류" 버튼을 넣을 수 있게 폼에 자리(`extra?: ReactNode` 등)를 둔다.

### 배치 카드의 클레임

배치 카드 아래에 접을 수 있는 클레임 요약을 둔다: 고객별 건수·수량(확정/미확정). 미확정 클레임은 주황 시맨틱 색 + "미확정" 글자로 따로 보이고, `resolve_claim`이 가능하면 판정 버튼이 붙는다.

### 실행 확인

서버와 화면을 띄우고 시연 1의 1-1 → 1-2 → 1-3 → 1-5 → 1-7을 화면에서 직접 실행해 본 뒤 종료한다(역할을 바꿔 가며). 브라우저를 쓸 수 없으면 같은 입력을 `curl`로 보내 화면이 만드는 요청 본문이 서버에서 통과하는지 확인한다. 확인할 것:
- 품질 담당자에서 위원회 결정 버튼이 보이지 않고, 품질위원회로 바꾸면 보인다.
- 사유 없이 거절하면 폼에 서버 메시지가 뜨고 상태가 그대로다.
- 1-7(회수진행 배치에 새 확정 클레임)을 넣으면 새 안건 버튼이 생기지 않는다.

## Acceptance Criteria

```bash
npm --prefix w03_system/frontend run build
w03_system/.venv/bin/python -m pytest -q w03_system/backend/tests
```

## 검증 절차

1. 위 AC 커맨드를 실행한다.
2. 아키텍처 체크리스트를 확인한다:
   - `3-design/architecture.md`의 디렉토리 구조·모듈 경계를 따르는가? (화면에 판정·권한·전이 로직 없음)
   - `3-design/ui-guide.md`를 따르고 안티패턴을 쓰지 않았는가? (Primary 버튼은 화면당 하나, 모의 표시는 점선 배지)
   - `3-design/decisions.md`의 설계 결정을 벗어나지 않았는가? (예시는 채우기만, 실행은 사람)
   - CLAUDE.md 금지 규칙을 위반하지 않았는가?
3. 결과에 따라 `w03_system/phases/1-frontend/index.json`의 해당 step을 업데이트한다:
   - 성공 → `"status": "completed"`, `"summary": "산출물 한 줄 요약"` (`ActionForm`·`ExamplePicker`·`TaskList`의 props와 AI 버튼을 넣을 자리를 적는다)
   - 수정 3회 시도 후에도 실패 → `"status": "error"`, `"error_message": "구체적 에러 내용"`
   - 사용자 개입 필요 → `"status": "blocked"`, `"blocked_reason": "구체적 사유"` 후 즉시 중단

## 금지사항

- 시나리오 단계를 자동으로 재생하는 버튼("다음 단계 실행")을 만들지 마라. 이유: 준비한 결과를 순서대로 보여주는 것은 실행 증거가 약하다(`decisions.md` ①). 입력은 사람이 폼으로 넣는다.
- 액션별 입력 필드를 화면에 손으로 다시 정의하지 마라. 이유: 정의는 `ontology.py` 한 곳에만 있다(`architecture.md` 패턴 1).
- 화면에서 권한·전제 조건을 검사하지 마라(예: 역할이 SCM이면 숨김). 이유: 서버의 `available_actions`와 액션 실행기가 검사한다.
- 서버 코드(`w03_system/backend/`)와 `scenarios/`를 고치지 마라. 이유: 이 step은 화면만 다룬다. 서버에 없는 값이 필요하면 `blocked`로 남겨라.
- `01_참가자_배포용/04_원본데이터/`의 파일을 수정하지 마라. 이유: 원본 데이터는 대회 규칙상 수정 금지다.
- 기존 테스트를 깨뜨리지 마라
