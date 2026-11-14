# Step 3: e2e

## 읽어야 할 파일

먼저 아래 파일들을 읽고 과제와 설계 의도를 파악하라:

- `/CLAUDE.md`
- `/w03_system/brain/status.md`
- `/w03_system/brain/3-design/browser-test-scenarios.md` (TC-01, TC-02, 불리한 회신, "실행 방법", "실행 결과", "발견한 점")
- `/w03_system/brain/3-design/demo-scenarios.md` (시연 1의 1-6, 시연 2의 2-4c·2-5, "모의 회신 목록")
- `/w03_system/brain/3-design/decisions.md` (맨 아래 2026-11-15 "재발 방지 고리 (R11-1)" 행)
- `/w03_system/brain/3-design/business-model.md` (§5의 R11-1)
- `/w03_system/e2e/conftest.py`, `/w03_system/e2e/helpers.py`, `/w03_system/e2e/test_browser.py`
- step 1에서 바뀐 파일: `/w03_system/scenarios/demo1.json`, `/w03_system/scenarios/demo2.json`, `/w03_system/scenarios/reply-examples.json`
- step 2에서 바뀐 파일: `/w03_system/frontend/src/tabs/PlanTab.tsx`, `/w03_system/frontend/src/components/ActionForm.tsx`

이전 step에서 만들어진 코드를 꼼꼼히 읽고, 설계 의도를 이해한 뒤 작업하라. 화면의 정확한 문구와 `data-*` 속성은 step 2의 summary와 코드에서 확인한다.

## 배경

규칙 R11-1이 서버·시나리오·화면에 들어갔다.

- "출하 경위 확인" 작업(T-01)이 열려 있으면 재공급 계획 탭에 `출하 경위 확인 대기` 띠가 보이고, SCM 결정 창에서 승인을 고르면 근거를 적기 전까지 실행 버튼이 꺼진다.
- "경위 확인됨" 회신이 오면 띠가 사라지고, 결정 창의 `판단 근거`에 `출하 경위` 줄이 `확인됨`과 회신 문장으로 보인다.
- "확인 불가" 회신이면 작업이 열린 채 기한이 연장되고 띠가 남는다.

이 step은 브라우저 테스트와 테스트 문서를 여기에 맞추고, 진행 상태를 기록한다.

## 작업

이 step은 `e2e/`와 `brain/` 문서만 다룬다.

### 1. 브라우저 테스트 (`e2e/test_browser.py`, 필요하면 `e2e/helpers.py`)

- **TC-01 (시연 1), 1-6:**
  - 결정 전에 재공급 계획 탭에 `출하 경위 확인 대기` 띠가 보인다.
  - 결정 창에서 `승인`을 고르고 근거를 비우면 실행 버튼이 꺼져 있고 안내 문구가 보인다.
  - 예시 `승인 (출고 조건 충족)`을 고르면 근거가 채워지고 실행된다. 계획은 확정이다.
- **TC-02 (시연 2):**
  - 2-4b 뒤(계획 v2 초안)에 띠가 보인다.
  - 2-4c: 출하 경위 확인 작업에 예시 `경위 확인됨 (보류 표시 미반영, 차단 항목 추가)`으로 회신한다. 작업이 `완료`가 되고 띠가 사라진다. 계획 버전 수는 그대로 2개다.
  - 2-5: 결정 창의 `판단 근거`에 `출하 경위` 줄이 `확인됨`과 회신 문장으로 보인다. 승인하면 v2가 확정된다.
- **불리한 회신 (새 테스트 `test_tc02c_hold_check_unavailable`):** 시연 2 출발 상태에서, 출하 경위 확인 작업에 예시 `확인 불가 (7일 추가 필요)`로 회신한다. 작업이 열린 채 `연장됨` 표시가 붙는다. 영업 임원 회신으로 v2 초안을 만든 뒤 띠가 여전히 보이고, 근거 없는 승인 버튼이 꺼져 있다.
- 기존 도우미(`h.reply`, `h.plan_decision`, `h.task`, `h.pick_example`)를 재사용한다. 근거를 비운 상태를 확인하려면 결정 창을 여는 단계와 실행 단계를 나눈 작은 도우미가 필요할 수 있다. 기존 도우미의 동작은 바꾸지 않는다.
- TC-03 ~ TC-06은 재공급 계획 승인이 없어 바뀌지 않아야 한다. 깨지면 테스트를 고치기 전에 원인을 찾는다.
- TC-07(AI 실제 호출)은 손대지 않고 실행하지도 않는다.

### 2. 테스트 문서 (`brain/3-design/browser-test-scenarios.md`)

- TC-01의 1-6, TC-02의 2-4c·2-5 줄, 불리한 회신(TC-02c)을 표에 반영한다. 기존 표의 열 구성과 문장 방식을 그대로 따른다.
- "실행 결과"에 이번 실행을 날짜와 함께 한 줄로 더한다(통과 수, TC-07은 돌리지 않음).
- 실행하다가 화면 문제를 발견하면 고치지 말고 "발견한 점"에 번호를 이어 적는다.

### 3. 진행 상태 (`brain/status.md`)

- "끝난 것"에 한 줄을 더한다: 재발 방지 고리(R11-1) 구현, 서버·시나리오·화면·브라우저 테스트, 테스트 결과, 배포 안 함, 관련 문서 링크.
- "다음 할 일"의 5번(재발 방지 고리 구현)을 지우고, 대신 "설계 설명 문항에 R11-1 반영(필수 확장 R5의 연장으로 서술)"과 "배포 여부 정하기"를 필요한 만큼 더한다.
- `_마지막 갱신_` 날짜를 맞춘다.
- 루트 `CLAUDE.md`는 고치지 않는다. 사용자가 관리한다.

## Acceptance Criteria

브라우저 테스트는 `w03_system/`에서 실행한다(테스트가 임시 DB로 서버를 따로 띄운다). 화면 빌드가 먼저다.

```bash
npm --prefix w03_system/frontend run build
(cd w03_system && .venv/bin/python -m pytest e2e)
(cd w03_system && .venv/bin/python -m pytest -q backend/tests \
  --deselect backend/tests/test_ai.py::test_no_key \
  --deselect backend/tests/test_ai.py::test_classify_ok_and_logged \
  --deselect backend/tests/test_ai.py::test_real_call_saves_answer_and_replay_returns_it_without_calling \
  --deselect backend/tests/test_api.py::test_ai_no_key)
```

세 줄 모두 저장소 루트에서 실행한다(괄호가 폴더 이동을 그 줄 안에 가둔다).

## 검증 절차

1. 위 AC 커맨드를 실행한다. 브라우저 테스트는 TC-07을 뺀 전부가 통과해야 한다(TC-07은 `E2E_AI`가 없으면 건너뛴다).
2. 체크리스트를 확인한다:
   - 테스트의 단계 번호와 기대 값이 `browser-test-scenarios.md`, `demo-scenarios.md`와 같은가?
   - 불리한 회신 테스트가 들어갔는가? (유리한 회신만으로 검증을 대신할 수 없다)
   - `status.md`에 같은 내용을 두 번 쓰지 않았는가? (상세는 링크로 연결한다)
   - CLAUDE.md 금지 규칙을 위반하지 않았는가?
3. 결과에 따라 `w03_system/phases/2-recurrence-check/index.json`의 해당 step을 업데이트한다:
   - 성공 → `"status": "completed"`, `"summary": "산출물 한 줄 요약"` (브라우저 테스트 통과 수, 추가·수정한 테스트 이름, 발견한 점이 있으면 번호)
   - 수정 3회 시도 후에도 실패 → `"status": "error"`, `"error_message": "구체적 에러 내용"`
   - 사용자 개입 필요 (Chromium이 설치되지 않음 등) → `"status": "blocked"`, `"blocked_reason": "구체적 사유"` 후 즉시 중단

## 금지사항

- 테스트를 통과시키려고 `backend/`, `scenarios/`, `frontend/`를 고치지 마라. 이유: 이전 step에서 확정했다. 화면이나 서버가 설계와 다르게 동작하면 테스트를 약하게 만들지 말고 `error`로 구체적 내용을 남겨라.
- 기존 테스트의 확인 항목을 지우거나 약하게 만들지 마라. 이유: 시연 3건의 회귀 확인이다. 화면 구조가 바뀌어 선택자가 맞지 않으면 선택자만 고친다.
- `E2E_AI=1`로 실행하지 마라. 이유: AI를 실제로 5회 호출해 비용이 든다. 이 phase는 AI 입출력을 바꾸지 않았다.
- `data/e2e/`의 화면 캡처를 git에 올리지 마라. 이유: git에 올리지 않는 폴더다.
- 배포 명령(`axhub deploy`, `git push`)을 실행하지 마라. 이유: `origin`의 `main`에 푸시하면 운영에 바로 배포된다. 배포는 사용자가 지시한다.
- `.claude` / `.codex` / `.agents` / `.gitignore`를 고치지 마라. 이유: CLAUDE.md 금지 규칙이다.
- `01_참가자_배포용/04_원본데이터/`의 파일을 수정하지 마라. 이유: 원본 데이터는 대회 규칙상 수정 금지다.
