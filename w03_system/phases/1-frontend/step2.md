# Step 2: incident-tab

## 읽어야 할 파일

먼저 아래 파일들을 읽고 과제와 설계 의도를 파악하라:

- `/CLAUDE.md`
- `/w03_system/brain/status.md`
- `/w03_system/brain/3-design/architecture.md` (패턴 4, 모듈 경계의 `frontend/`)
- `/w03_system/brain/3-design/ui-guide.md` (전부. 특히 "레이아웃"의 사건 탭, "타이포그래피", "애니메이션")
- `/w03_system/brain/3-design/business-model.md` §4 (상태), §5 (규칙 R1~R8)
- `/w03_system/brain/3-design/demo-scenarios.md` (S0, 시연 1의 1-1 ~ 1-2에서 화면에 보여야 하는 것)
- `/w03_system/backend/core/view.py` (`incident_view`: `batches[].metrics`·`warnings`·`part_of`, `last_change`, `thresholds`, `openable_batches`)
- `/w03_system/backend/core/rules.py` (`batch_metrics`·`warnings`가 돌려주는 키)
- `/w03_system/frontend/src/` 전부 (이전 step에서 만든 `App.tsx`, `api.ts`, `types.ts`, `format.ts`, `components/`)

이전 step에서 만들어진 코드를 꼼꼼히 읽고, 설계 의도를 이해한 뒤 작업하라.

## 작업

사건 탭(`frontend/src/tabs/IncidentTab.tsx`)의 **읽기 부분**을 만든다. 액션 폼·작업 목록·연결망·AI는 다음 step들의 범위다. 이 step에서 실행되는 액션은 "사건 열기" 하나뿐이다.

### 사건이 없을 때 (S0)

- "사건 열기"와 열 수 있는 배치 목록(`view.openable_batches`)만 보인다. 목록은 표로 그리고 서버가 준 열을 그대로 쓴다.
- 적용일 입력(기본값 `2026-07-01` = 과제 기준일, 고칠 수 있음)과 배치 선택 후 실행 버튼. `available_actions`에 `open_incident`가 없는 역할에서는 버튼이 보이지 않고 "이 역할은 사건을 열 수 없습니다" 한 줄만 보인다.
- 실행은 `AppCtx.run("open_incident", {batch_id, applied_date})`.

### 사건이 있을 때: 레이아웃

`ui-guide.md` 그대로 왼쪽 2/3, 오른쪽 1/3.

**왼쪽: 배치 판정 카드** (`components/BatchCard.tsx`, 배치마다 하나, ID 순)

위에서 아래로 "지금 상태 → 근거 → 할 수 있는 일" 순서:

1. 배치 ID(`font-mono`), 판정 상태 배지, 사건에 묶인 이유(`part_of.reason`)와 출처 배지.
2. 핵심 숫자: 불량률(`metrics.defect_rate`)과 회수 기준(`metrics.threshold`), 기준값 옆에 출처 배지. 기준 초과면 빨강 시맨틱 색 + "기준 초과" 글자.
3. 근거 줄: 확정 불량 수량 / 생산 수량, 기준 초과일, 미상신 경과일(`days_unsubmitted`가 있으면 "기준 초과 후 N일 미상신"), 미확정 클레임 수량과 확정 시 불량률(`rate_if_confirmed`, "참고" 표시), 마지막 출하일, 관찰 해제 예정일과 해제 기준(값이 있을 때만).
4. 경고(`batch.warnings`): `WarningLine`으로 규칙 번호와 함께.
5. 액션 자리: 이 step에서는 비워 둔다. 다음 step이 여기에 버튼을 넣을 수 있게 `actions?: ReactNode` 같은 자리를 둔다.

- 숫자마다 어느 규칙에서 나왔는지(`metrics.rules`)를 작은 글자로 붙인다(예: `R1`).
- 값이 `null`인 항목은 줄 자체를 그리지 않는다. 이유: "해제 예정일 —"처럼 뜻 없는 줄이 회수 대상 배치에 보이면 안 된다.

**왼쪽 아래: 사건 경고** — 배치에 붙지 않은 경고(`view.warnings` 중 대상이 배치가 아닌 것)를 카드 하나에 모은다. 없으면 카드를 그리지 않는다.

**오른쪽 위: 방금 바뀐 것** (`components/LastChange.tsx`, `view.last_change`)

- 머리: 액션 이름(온톨로지 `actions[이름].name`), 실행자(역할 이름), 적용일.
- 단계별(`steps`: 사람 액션 1개 + 자동 처리들)로 변경 목록: 대상(타입·ID) · 필드 · **이전 → 이후** · 적용된 규칙. 자동 처리 단계에는 "자동" 표시와 이유(`reason`)를 보인다.
- 변경이 하나도 없으면 "상태 변화 없음"이라고 쓴다(시연 2-1에서 필요).
- `last_change`가 없으면 카드를 그리지 않는다.

**오른쪽: 작업 목록 자리** — 이 step에서는 카드 제목과 열린 작업 수만 보인다(다음 step이 채운다).

**오른쪽 아래: 최근 기록** — `view.log.actions`의 마지막 5개(순번, 액션 이름, 실행자, 적용일). "전체는 기록 탭에서" 한 줄.

### 바뀐 항목 강조

액션 뒤 `last_change.changes`의 대상에 해당하는 배치 카드의 배경을 `bg-amber-50`에서 투명으로 1초 동안 1회 바꾼다. `ui-guide.md`가 허용하는 유일한 애니메이션이다.

### 실행 확인

서버와 화면을 띄우고, 빈 상태에서 `B-02-2602-01`로 사건을 열어 다음을 눈으로 확인한 뒤 종료한다(브라우저를 쓸 수 없으면 `curl`로 같은 API 응답을 받아 화면이 쓰는 키가 실제로 있는지 대조한다):
- 배치 카드 4개, 기준 초과 2개에 11.9%·11.6%, "기준 초과 후 91일·51일 미상신".
- 관찰해제 배치 2개, 보류 배치 출하 경고와 보류 로트 투입 경고.
- "방금 바뀐 것"에 사건 열기와 자동 처리 단계.

## Acceptance Criteria

```bash
npm --prefix w03_system/frontend run build
w03_system/.venv/bin/python -m pytest -q w03_system/backend/tests
```

## 검증 절차

1. 위 AC 커맨드를 실행한다.
2. 아키텍처 체크리스트를 확인한다:
   - `3-design/architecture.md`의 디렉토리 구조·모듈 경계를 따르는가?
   - `3-design/ui-guide.md`를 따르고 안티패턴을 쓰지 않았는가? (차트 없음, 색만으로 상태 구분 없음)
   - `3-design/business-model.md`의 객체·상태·판단 규칙과 일치하는가?
   - CLAUDE.md 금지 규칙을 위반하지 않았는가?
3. 결과에 따라 `w03_system/phases/1-frontend/index.json`의 해당 step을 업데이트한다:
   - 성공 → `"status": "completed"`, `"summary": "산출물 한 줄 요약"` (새 컴포넌트와 props, 배치 카드의 액션 자리·작업 목록 자리가 어디인지 적는다)
   - 수정 3회 시도 후에도 실패 → `"status": "error"`, `"error_message": "구체적 에러 내용"`
   - 사용자 개입 필요 → `"status": "blocked"`, `"blocked_reason": "구체적 사유"` 후 즉시 중단

## 금지사항

- 화면에서 불량률·경과일·해제 예정일을 다시 계산하지 마라. 이유: 판정은 `rules.py`가 하고 화면은 서버 값을 그대로 그린다. 화면 계산은 서버와 어긋난다.
- 상태에 따라 화면이 판단하는 분기를 만들지 마라(예: `state === "기준초과"`이면 문구 추가). 이유: 같은 이유. 상태별로 달라지는 것은 `StatusBadge`의 색뿐이다.
- 불량률 추이 같은 차트를 넣지 마라. 이유: `ui-guide.md` 안티패턴("판단에 쓰이지 않는 차트").
- 서버 코드(`w03_system/backend/`)를 고치지 마라. 이유: 이 step은 화면만 다룬다. 서버에 없는 값이 필요하면 `blocked`로 남겨라.
- `01_참가자_배포용/04_원본데이터/`의 파일을 수정하지 마라. 이유: 원본 데이터는 대회 규칙상 수정 금지다.
- 기존 테스트를 깨뜨리지 마라
