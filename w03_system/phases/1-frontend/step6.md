# Step 6: ai-blocks

## 읽어야 할 파일

먼저 아래 파일들을 읽고 과제와 설계 의도를 파악하라:

- `/CLAUDE.md`
- `/w03_system/brain/status.md`
- `/w03_system/brain/3-design/architecture.md` (패턴 3, "AI 호출", API 표의 `/api/ai/*`)
- `/w03_system/brain/3-design/ui-guide.md` ("AI 초안 블록", 안티패턴의 AI 관련 행, "애니메이션")
- `/w03_system/brain/3-design/decisions.md` ("화면 구현 전 정리 4건" ②)
- `/w03_system/brain/3-design/business-model.md` R12 (AI는 제안만, 사람이 실행)
- `/w03_system/brain/3-design/demo-scenarios.md` (각 시연의 "AI" 열)
- `/w03_system/backend/ai/tasks.py` (task 4종의 `params`, 출력 스키마, `AiResult`, 오류 코드, `ValueError`가 나는 조건)
- `/w03_system/backend/api/main.py` (`POST /api/ai/{task}`, `GET /api/ai/status`)
- `/w03_system/backend/core/actions.py` (`submit_agenda`·`apply_reply`의 선택 입력 `ai_log_id`)
- `/w03_system/frontend/src/` 전부 (특히 `api.ts`의 `runAi`, `components/ActionForm.tsx`, `components/TaskList.tsx`, `components/LastChange.tsx`)

이전 step에서 만들어진 코드를 꼼꼼히 읽고, 설계 의도를 이해한 뒤 작업하라.

## 작업

AI 4종을 화면에 붙인다. AI는 **버튼을 눌러 요청**하고, 결과는 "AI 초안" 블록에 나오고, 사람이 "이 내용 사용"을 눌러야 액션 입력에 들어간다. AI는 어떤 액션도 실행하지 않는다.

### 공용 블록 `components/AiDraft.tsx`

```ts
type Props = {
  task: AiTask;                               // "agenda_summary" | "classify_reply" | "review_explanation" | "notice_draft"
  params: Record<string, unknown>;
  label: string;                              // 요청 버튼 글자 (예: "AI로 안건 요약")
  render(output: unknown): ReactNode;         // task별 출력 표시
  onUse?: (output: unknown, logId: number) => void;   // 있으면 "이 내용 사용" 버튼이 나온다
}
```

- 요청 전: Secondary 버튼 하나. 키가 없으면(`aiAvailable === false`) 버튼을 비활성화하고 옆에 "AI 키 없음" 글자. 이때도 나머지 화면은 그대로 동작한다.
- 요청 중: 버튼 비활성화 + "AI가 작성 중…" 글자만. 스피너·스켈레톤 애니메이션 없음. 안건 요약은 20초 넘게 걸릴 수 있다.
- 결과: `ui-guide.md`의 "AI 초안 블록" 스타일(점선 테두리), 머리에 **"AI 초안"** 라벨과 AI 기록 번호(`log_id`). 아래에 "이 내용 사용"(있을 때)과 "다시 요청".
- 실패(`ok: false`): 블록에 서버가 준 `message`를 보인다(`refusal`·`max_tokens`·`api_error`·`invalid_output`·`no_key`). 가짜 결과를 만들지 않는다. HTTP 422(`invalid_input`, 예: "설명할 최근 액션이 없다")도 메시지를 그대로 보인다.
- 결과는 화면 상태에만 둔다. 탭을 옮기거나 다른 액션을 실행하면 사라져도 된다(전체 입출력은 기록 탭에 남는다).

### 붙이는 곳

| task | 위치 | params | 표시 | "이 내용 사용" |
|---|---|---|---|---|
| `agenda_summary` | 안건 상신 폼 안, 안건 요약 필드 위 | `{batch_ids}` = 폼에서 고른 배치 | 요약, 근거 목록, 대안별 영향(전면 회수 / 부분 회수 / 조사계속), 불확실성 목록 | 폼의 `agenda_summary`에 넣고(사람이 고칠 수 있음) `ai_log_id`를 함께 보낸다 |
| `classify_reply` | 회신 입력 폼 안, 회신 문장 필드 아래 | `{task_id, reply_text}` = 폼에 지금 적힌 문장 | 분류 결과, 근거 문장, 메모 | 폼의 `result` 선택에 넣고 `ai_log_id`를 함께 보낸다 |
| `review_explanation` | "방금 바뀐 것" 카드 아래 | `{}` | 설명, 결론(유지/변경) | 없음 (읽기만) |
| `notice_draft` | 작업 목록의 "안내 대상 결정" 작업 아래 (회수 대상 배치가 있을 때) | `{}` | 안내문 초안, 수신 고객 목록 | 없음 (읽기만. 실제 발송은 범위 밖이라고 한 줄로 적는다) |

핵심 규칙:
- **"해석 불가"는 사용할 수 없다.** `classify_reply`의 결과가 `해석 불가`(온톨로지 `ai_uninterpretable`)이면 "이 내용 사용" 버튼을 보이지 않고 "AI가 분류하지 못했습니다. 담당자가 직접 고르세요"를 보인다. 이유: 허용 결과가 아니므로 서버가 거부한다. 문자열은 온톨로지에서 가져온다.
- **"이 내용 사용"은 폼만 채운다. 액션 실행은 사람이 폼의 실행 버튼으로 한다.** (R12)
- **AI 결과를 폼에 넣은 뒤 사람이 고쳤는지와 무관하게 `ai_log_id`를 보낸다.** 이유: 어떤 AI 초안을 보고 결정했는지가 기록에 남아야 한다.
- 회신 문장이 비었으면 `classify_reply` 버튼을 비활성화한다.
- AI 출력에서 숫자를 뽑아 화면의 다른 값에 쓰지 않는다. 숫자의 기준은 항상 사건 뷰다.

### 키 없음 표시

상단 바 오른쪽에 AI 상태를 작은 글자로 보인다: "AI 사용 가능 (모델명)" 또는 "AI 키 없음". 장식 배지("Powered by AI" 류)는 만들지 않는다.

### 실행 확인

서버와 화면을 띄우고 확인한 뒤 종료한다:
- 키가 없는 상태(`ANTHROPIC_API_KEY` 없이 서버 실행, `w03_system/.env`가 있으면 환경변수로 가려서)에서 AI 버튼 4곳이 비활성화되고 "AI 키 없음"이 보이며, 안건 상신·회신 입력이 AI 없이 끝까지 된다.
- 키가 있으면(`GET /api/ai/status`가 `available: true`) 안건 요약을 한 번 요청해 블록 표시와 "이 내용 사용" → 상신 → 기록에 `ai_log_id`가 남는지 확인한다. 키가 없으면 이 항목은 건너뛰고 summary에 "실제 호출 미확인"이라고 적는다.

## Acceptance Criteria

```bash
npm --prefix w03_system/frontend run build
w03_system/.venv/bin/python -m pytest -q w03_system/backend/tests
```

## 검증 절차

1. 위 AC 커맨드를 실행한다.
2. 아키텍처 체크리스트를 확인한다:
   - `3-design/architecture.md` 패턴 3(판정은 규칙, 설명은 AI)을 따르는가?
   - `3-design/ui-guide.md`를 따르고 안티패턴을 쓰지 않았는가? (AI 출력은 항상 "AI 초안" 표시, 보라색·글로우·"Powered by AI" 없음)
   - `3-design/decisions.md` ②(버튼으로 요청, "이 내용 사용")를 따르는가?
   - CLAUDE.md 금지 규칙을 위반하지 않았는가?
3. 결과에 따라 `w03_system/phases/1-frontend/index.json`의 해당 step을 업데이트한다:
   - 성공 → `"status": "completed"`, `"summary": "산출물 한 줄 요약"` (실제 호출을 확인했는지 여부를 적는다)
   - 수정 3회 시도 후에도 실패 → `"status": "error"`, `"error_message": "구체적 에러 내용"`
   - 사용자 개입 필요 → `"status": "blocked"`, `"blocked_reason": "구체적 사유"` 후 즉시 중단

## 금지사항

- 액션 실행이나 화면 진입 때 AI를 자동으로 호출하지 마라. 이유: 응답이 20초 넘게 걸려 액션마다 화면이 멈추고, 키가 없을 때와 흐름이 달라진다(`decisions.md` ②).
- 키가 없거나 호출이 실패했을 때 대신 보여줄 예시 응답을 만들지 마라. 이유: 가짜 AI 응답은 금지다(`architecture.md` "AI 호출").
- AI 결과로 액션을 바로 실행하는 버튼("AI 제안대로 실행")을 만들지 마라. 이유: R12. AI는 제안만 하고 사람이 실행한다.
- 화면에서 Anthropic API를 직접 부르거나 키를 화면 코드·환경변수(`VITE_*`)에 넣지 마라. 이유: 키는 서버에만 있고 호출과 기록은 `backend/ai`가 한다.
- `w03_system/.env`를 읽어 출력하거나 고치지 마라. 이유: 개인 키가 들어 있다.
- 서버 코드(`w03_system/backend/`)를 고치지 마라. 이유: 이 step은 화면만 다룬다. 서버에 없는 값이 필요하면 `blocked`로 남겨라.
- `01_참가자_배포용/04_원본데이터/`의 파일을 수정하지 마라. 이유: 원본 데이터는 대회 규칙상 수정 금지다.
- 기존 테스트를 깨뜨리지 마라
