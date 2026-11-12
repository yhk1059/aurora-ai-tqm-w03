# Step 1: frontend-setup

## 읽어야 할 파일

먼저 아래 파일들을 읽고 과제와 설계 의도를 파악하라:

- `/CLAUDE.md`
- `/w03_system/brain/status.md`
- `/w03_system/brain/3-design/architecture.md` (패턴 4, 모듈 경계의 `frontend/`, API 표, 오류 응답, 상태 관리, 기술 스택, 환경과 명령어)
- `/w03_system/brain/3-design/ui-guide.md` (전부)
- `/w03_system/brain/3-design/decisions.md` ("화면 구현 전 정리 4건")
- `/w03_system/backend/api/main.py` (라우트와 응답 형식)
- `/w03_system/backend/core/view.py` (`incident_view`가 돌려주는 키 전부)
- `/w03_system/backend/core/actions.py` (`ActionResult`, `available_actions`, 각 `_targets_*` 함수가 돌려주는 모양)
- `/w03_system/backend/core/ontology.py` (`ROLES`, `ACTIONS`의 `inputs`, `STATE_MACHINES`)
- `/w03_system/backend/core/scenario.py` (`list_scenarios`, `list_reply_examples`)
- `/w03_system/.gitignore`

이전 step에서 만들어진 코드를 꼼꼼히 읽고, 설계 의도를 이해한 뒤 작업하라.

## 작업

`w03_system/frontend/`에 React 화면의 골격을 만든다. 이 step이 끝나면 화면이 뜨고, 상단 바와 빈 탭 4개가 보이고, 역할 선택과 초기화가 서버와 실제로 통신한다. 탭 내용은 다음 step들이 채운다.

### 프로젝트

- Vite + React + TypeScript. 버전은 `architecture.md` 기술 스택 표(React 19, Vite 8, Tailwind CSS 4, Node 22)를 따른다. 설치된 실제 버전을 `package.json`에 고정한다(`^` 없이).
- Tailwind CSS 4는 Vite 플러그인(`@tailwindcss/vite`)으로 붙인다. 설정 방법은 추측하지 말고 설치된 패키지의 문서·README를 확인하라.
- 아이콘은 `lucide-react`. 그 밖의 UI 라이브러리·상태 라이브러리·라우터는 넣지 않는다.
- `vite.config.ts`: 개발 서버가 `/api`와 `/healthz`를 `http://localhost:8000`으로 프록시한다.
- `index.html`: `lang="ko"`, 제목 `Aurora AI-TQM`. 글꼴은 Pretendard를 우선 지정하되 외부 CDN에서 불러오지 않는다(없으면 시스템 한글 글꼴).
- npm 스크립트: `dev`, `build`(= 타입 검사 `tsc` + `vite build`), `preview`.

### 디렉토리 (이후 step이 이 구조에 파일을 더한다)

```
frontend/src/
  main.tsx, App.tsx, index.css
  api.ts          서버 호출 함수 전부
  types.ts        서버 응답 타입
  format.ts       표시 형식 (수량·비율·날짜)
  components/     공용 컴포넌트
  tabs/           IncidentTab.tsx, PlanTab.tsx, LogTab.tsx, OntologyTab.tsx
```

### `api.ts`

```ts
export class ApiError extends Error { code: string }          // 서버 오류 본문 {"error": {code, message}}
export function getIncident(actor: Role): Promise<IncidentView>
export function runAction(action: string, actor: Role, inputs: Record<string, unknown>): Promise<{ result: ActionResult; view: IncidentView }>
export function resetTo(scenario: string | null, actor: Role): Promise<IncidentView>
// null → POST /api/actions/reset, 이름 → POST /api/scenarios/{name}?setup_only=true&actor=
export function getScenarios(): Promise<ScenarioInfo[]>
export function getReplyExamples(): Promise<ReplyExample[]>
export function getOntology(): Promise<Ontology>
export function getAiStatus(): Promise<{ available: boolean; model: string }>
export function runAi(task: AiTask, params: Record<string, unknown>): Promise<AiResult>
```

- 2xx가 아니면 본문의 `error.code`·`error.message`로 `ApiError`를 던진다.
- `types.ts`의 타입은 `view.py`·`actions.py`·`ai/tasks.py`가 실제로 돌려주는 키에 맞춘다. 서버를 띄워 응답을 직접 확인하라(아래 "실행 확인"). 서버에 없는 필드를 타입에 만들지 마라.

### 앱 상태 (`App.tsx`)

화면에만 있는 상태는 **지금 고른 역할, 열린 탭, 입력 중인 폼**뿐이다. 사건 뷰는 서버 응답을 그대로 들고 있다가 그린다.

```ts
// App이 가진 것: view(IncidentView | null), actor(Role), tab, ontology, aiStatus, error
// 자식에게 넘기는 것 (React context 하나 또는 props. 외부 상태 라이브러리 금지)
type AppCtx = {
  view: IncidentView; actor: Role; ontology: Ontology; aiAvailable: boolean;
  run(action: string, inputs: Record<string, unknown>): Promise<void>;   // 성공하면 응답의 view로 교체
}
```

- 처음 열 때와 역할을 바꿀 때 `getIncident(actor)`를 다시 부른다. 이유: 가능한 액션은 역할마다 다르고 서버가 정한다.
- 액션이 성공하면 응답의 `view`로 교체한다. 화면에서 상태를 고쳐 쓰지 않는다.
- 액션이 실패하면(`ApiError`) 화면 위쪽에 오류 줄로 `message`를 보이고 뷰는 그대로 둔다.

### 상단 바와 탭

`ui-guide.md` "레이아웃" 그대로:

- 상단 바(항상 보임): 사건 ID · 사건 상태 배지 · 기점 로트 │ 현재 적용일 · 역할 선택 · 초기화. 사건이 없으면 "사건 없음"만 보인다.
- 역할 선택: `GET /api/ontology`의 `roles`에서 이름을 가져온다(화면에 역할 목록을 다시 쓰지 않는다). 기본값 `quality_owner`.
- 초기화 메뉴: "빈 상태" + `GET /api/scenarios` 중 `setup_count > 0`인 시나리오의 "출발 상태"(제목 표시). 고르면 확인 창("지금 상태와 기록이 모두 지워집니다")을 띄우고 확인하면 실행한다.
- 탭 4개: 사건 / 재공급 계획 / 기록 / 온톨로지. 이 step에서는 각 탭이 제목과 "준비 중" 한 줄만 보인다.

### 공용 컴포넌트 (`components/`)

| 컴포넌트 | 내용 |
|---|---|
| `StatusBadge` | 상태 글자 + 시맨틱 색. **상태 → 색 매핑은 이 파일 한 곳에만 둔다** (`ui-guide.md` "데이터/시맨틱 색상" 표). 표에 없는 상태는 회색 |
| `SourceBadge` | 출처(원본·도출·시스템 = 실선, 가정·모의 = 점선). 누르면 근거(`evidence` 문자열 목록, 가정 문구)가 펼쳐진다 |
| `Card` | 카드 틀 + 카드 제목 |
| `WarningLine` | 경고 아이콘 + 문장 (+ 규칙 번호) |
| `Button` | Primary / Secondary / Text 세 가지 |
| `ConfirmDialog` | 확인 창. 내용(children)과 확인·취소 버튼 |

`format.ts`: 수량 = 천 단위 구분 + ` EA`, 비율 = 0~1 값을 소수 한 자리 %로, 날짜 = `YYYY-MM-DD` 그대로. 값이 `null`이면 `—`.

### 실행 확인

서버와 화면을 실제로 띄워 확인하고, 끝나면 둘 다 종료한다.

```bash
w03_system/.venv/bin/uvicorn backend.api.main:app --app-dir w03_system --port 8000 &
npm --prefix w03_system/frontend run dev &
curl -s localhost:5173/api/incident?actor=quality_owner | head -c 300   # 프록시 확인
```

### 문서

`architecture.md` "환경과 명령어"의 화면 명령 옆 "(1-frontend에서 확인)"을 실제로 확인한 날짜와 명령으로 고친다. 기술 스택 표의 화면 버전을 설치된 버전으로 맞춘다.

## Acceptance Criteria

```bash
npm --prefix w03_system/frontend install
npm --prefix w03_system/frontend run build
w03_system/.venv/bin/python -m pytest -q w03_system/backend/tests
```

## 검증 절차

1. 위 AC 커맨드를 실행한다.
2. 아키텍처 체크리스트를 확인한다:
   - `3-design/architecture.md`의 디렉토리 구조·모듈 경계를 따르는가?
   - `3-design/ui-guide.md`를 따르고 안티패턴을 쓰지 않았는가? (밝은 테마 하나, 보라·그라데이션·blur·그림자 글로우 없음, 중앙 정렬 없음)
   - `3-design/decisions.md`의 기술 스택·설계 결정을 벗어나지 않았는가?
   - CLAUDE.md 금지 규칙을 위반하지 않았는가?
3. 결과에 따라 `w03_system/phases/1-frontend/index.json`의 해당 step을 업데이트한다:
   - 성공 → `"status": "completed"`, `"summary": "산출물 한 줄 요약"` (파일 목록, `AppCtx` 모양, 공용 컴포넌트의 props, 고정한 버전을 적는다)
   - 수정 3회 시도 후에도 실패 → `"status": "error"`, `"error_message": "구체적 에러 내용"`
   - 사용자 개입 필요 → `"status": "blocked"`, `"blocked_reason": "구체적 사유"` 후 즉시 중단

## 금지사항

- 화면에 판정·권한·전이 규칙을 쓰지 마라(예: "기준초과면 상신 버튼 표시"). 이유: 어떤 버튼을 보일지는 서버의 `available_actions`가 정한다(`architecture.md` 패턴 4).
- Redux·Zustand·React Query·React Router 같은 라이브러리를 넣지 마라. 이유: 화면은 상태를 보관하지 않고 탭 4개뿐이다(`architecture.md` "쓰지 않는 것").
- 어두운 테마·테마 전환을 만들지 마라. 이유: `ui-guide.md` 안티패턴.
- 루트 `.gitignore`를 고치지 마라. 이유: CLAUDE.md 금지 규칙. `node_modules/`·`frontend/dist/`는 `w03_system/.gitignore`에 이미 있다.
- 서버 코드(`w03_system/backend/`)를 고치지 마라. 이유: 이 step은 화면 골격만 다룬다. 서버에 없는 값이 필요하면 `blocked`로 남겨라.
- `01_참가자_배포용/04_원본데이터/`의 파일을 수정하지 마라. 이유: 원본 데이터는 대회 규칙상 수정 금지다.
- 기존 테스트를 깨뜨리지 마라
