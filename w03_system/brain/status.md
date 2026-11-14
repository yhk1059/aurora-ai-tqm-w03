# status — 진행 상태

_마지막 갱신: 2026-11-15_

## 단계
**서버(0-backend)·화면(1-frontend) 구현 완료.** 과제 규칙·배경(`1-brief/`) 정리 완료. 2026-11-11 초기화 이후 다시 시작해, 2026-11-12에 근본 원인, W03 스코프(C안), 스코핑 6항목, 설계 전제 6건을 확정했다.

## 끝난 것
- 대회 목표·규칙·가이드라인 정리 → `1-brief/assignment.md`
- W03 업무 안내(흐름도·원본 규칙·미해결 지점·질문) 정리 → `1-brief/w03-task.md`
- 영업 회의록 vs 재무 메모 검증: C-101 수주 2026-04부터 급감, 출하는 아직 정상, 원인 미확인 → `2-findings/c101-order-vs-shipment.md` (스크립트 `w03_system/scripts/c101_order_trend.py`)
- 영업 회의록·재무 메모의 문제 구조 정리(선행/후행 지표, 범위 분리, 원인 미검증, 행동 부재, 품질 단절) → `2-findings/sales-finance-meeting-gap.md`
- 근본 원인 정의 확정 ("엇갈린 부서 신호를 결정으로 연결하는 주인이 없다") → `3-design/decisions.md`
- W03 스코프 C안("판정에서 복구까지 한 줄기")과 범위 규칙 4개 + 범위 밖 처리 확정 → `3-design/decisions.md`
- 대상 사건(`LOT-B-2602-P`, 배치 4개) 사실 정리 → `2-findings/lot-b2602p-incident.md` (10% 초과일: 04-01, 05-11 / 의결 기록 공백)
- 스코핑 6항목 확정: 사용자 = 품질팀 사건 담당자, 형태 = 로컬 웹 화면 외 → `3-design/decisions.md`

- 업무모델 v1 확정 (설계 인터뷰 2회, 결정 7건) → `3-design/business-model.md`, 가정 A-07~A-11
- 온톨로지 = B안(가벼운 온톨로지 층: 선언형 정의 + 관계 테이블, 관계별 출처·확인 수준) → `3-design/business-model.md` §8, `3-design/decisions.md`

- 시연 시나리오 v1 확정 (인터뷰 결정 4건, 가정 A-12~A-14) → `3-design/demo-scenarios.md`

- 온톨로지 정의 보완 6건 확정 (고객 영향 = `SHIPPED_TO` 관계, 수량·수량 근거, 계획 버전·줄, 현재 적용일·사건 상태 도출, 규칙 기준값 출처, 기점 로트 = 클레임 로트 + 보류 로트 투입 경고 R5-1) → `3-design/business-model.md`, `3-design/decisions.md`, 가정 A-15
- 온톨로지를 객체 타입·속성·관계·액션 4칸으로 재구성, 빠진 관계 5개 추가 → `3-design/business-model.md` §8
- 클레임 상태(접수·조사중·확정·기각)와 미확정 클레임 규칙 R6-2·R7-1, 상태 빈틈 3개(`관찰해제`, 부분회수 완료 조건, 사건 `관찰중`) 반영 → `3-design/business-model.md` §4, `3-design/demo-scenarios.md` 2-2a·2-2b, 가정 A-16
- 화면 기술 변경: Streamlit 취소 → React + FastAPI (코어는 Python + SQLite + Claude API 유지) → `3-design/decisions.md`
- 아키텍처 v1 작성 → `3-design/architecture.md`
- UI 가이드 v1 작성 → `3-design/ui-guide.md`
- 구현 전 정리 4건 확정 (phase 2개, T-05 생성 시점 = 계획 초안, 계획 상태 = 초안 → 확정/기각, 적재 시점 = 사건 열기) → `3-design/decisions.md`, 관련 문서 반영
- 구현 기본값 5건 확정 (작업 기한 A-17, T-04 자동 완료, 결과 통보 작업, 공급 배치 선택, 재공급 배분 방식) → `3-design/decisions.md`
- 서버 구현 완료(core·ai·api, 시연 3건 테스트 통과) → `w03_system/backend/`, `w03_system/scenarios/`
- AI 실제 호출 확인 (2026-11-12, `claude-opus-5-5`): 안건 요약·회신 분류(확인 불가 / 출하 확인 / 해석 불가)·재검토 설명·안내 초안 4종 모두 정상 응답, `ai_log` 기록 확인

- 화면 구현 전 정리 4건 확정 (모의 회신 예시 선택, AI 버튼 요청, 초기화 메뉴의 출발 상태, 서버 보완은 `1-frontend` 첫 step) → `3-design/decisions.md`
- `1-frontend` step 설계 완료 (step 9개, 결정 3건: 배포본 화면 서빙, 모의 입력 예시 API, 배포본 DB 공유는 보류) → `phases/1-frontend/`, `3-design/decisions.md`
- `1-frontend` step 0 서버 보완, step 1 화면 골격 완료 (Vite + React + Tailwind, 상단 바·역할 선택·초기화 메뉴·빈 탭 4개, 공용 컴포넌트) → `w03_system/frontend/`

- `1-frontend` step 0 서버 보완: 관찰 해제 예정일은 관찰 대상 배치에만 내보내고 AI 안건 입력에서 뺌, 모의 입력 예시 `scenarios/reply-examples.json` + `GET /api/reply-examples`, 시나리오 목록에 `setup_count` → `w03_system/backend/`

- `1-frontend` step 2~8 완료: 사건·재공급 계획·기록·온톨로지 탭, 액션 폼, 연결망, AI 초안 블록, 배포용 화면 서빙(FastAPI가 `frontend/dist` 서빙, Dockerfile 다단계 빌드. Docker 이미지 빌드는 데몬이 꺼져 있어 미확인) → `w03_system/frontend/`, `w03_system/backend/api/main.py`, `Dockerfile`

- 브라우저 테스트 시나리오 작성과 Playwright 실행 (2026-11-13): TC-00 ~ TC-07 모두 통과, 발견한 점 6건 중 ①②④(AI 기록 갱신, 남는 분류 결과, 변경 설명의 내부 이름) 고침 → `3-design/browser-test-scenarios.md`, 코드 `w03_system/e2e/`
- 사건 탭 UI 가이드 v2 적용 (2026-11-13): 사건 요약 띠, 기준 초과 배치 강조, 기준 미달 배치·끝난 작업·변경 상세 접기. 브라우저 테스트 통과 → `3-design/ui-guide.md`, `3-design/decisions.md`
- 나머지 화면 UI 가이드 v2 적용 (2026-11-13): 결정 창(가운데, 큰 선택 버튼), 첫 화면(불량률 순·기준 초과 강조), 재공급 계획 탭(빈 비교 카드 숨김, 완료 월 막대, 출처 한 번 표시). 브라우저 테스트 통과 → `3-design/ui-guide.md`, `3-design/decisions.md`
- UI 가이드 v3 적용 (2026-11-13): 버튼 키보드 포커스 표시, 옅은 글자 대비 올림, 기록 탭 자동 처리 줄 접기, 온톨로지 탭 구역 접기. 브라우저 테스트 통과 → `3-design/ui-guide.md`, `3-design/decisions.md`
- UI 가이드 v4 적용 (2026-11-13): 결정 창에 판단 근거·결과별 효과 문구·취소/실행 버튼 순서. 시연 화면 캡처 20장으로 개선 대상 3곳(결정 창, 작업 목록·회신 입력, 사건 요약 띠)을 골라 모두 반영: 요약 띠 제목이 상태에 따라 바뀌고 진행 단계 4개가 붙음, 열린 작업에 `기한 지남`·`연장됨` 표시, 폼 안내 문구 2개 수정. 브라우저 테스트 통과 → `3-design/ui-guide.md`, `3-design/decisions.md`
- AI 안건 요약을 짧은 구조로 변경 (2026-11-14): 요지 한 문장·쟁점·대안 3칸·불확실성·접어 둔 근거(출처 배지), 배치 수치는 화면이 시스템 값으로 표시, 개수 상한은 서버 확인. 서버 테스트와 브라우저 테스트 7-1 통과 → `3-design/decisions.md`, `3-design/ui-guide.md`, `3-design/browser-test-scenarios.md`
- AI 변경 설명에 "§4-5"가 나오던 문제 고침 (2026-11-14): AI 입력에서 규칙 정의에 없는 `rule` 값을 뺀다. TC-07 전체 2회 통과 → `3-design/browser-test-scenarios.md` 실행 결과
- AI 안건 요약 초안에 구역 색 적용 (2026-11-14, 시안 A): 요지 카드, 번호 붙인 쟁점, 빨간 배치 수치, 결정 뒤 상태 색을 쓴 대안 칸, 주황 "확인 안 된 것" 구역, ID 칩. 화면 코드만 바꿈. 브라우저 테스트 TC-00 ~ TC-07 통과. AXHub에 배포 → `3-design/ui-guide.md`, `3-design/decisions.md`
- 개발용 AI 재생 모드 추가 (2026-11-14): `W03_AI_REPLAY=1`이면 API를 부르지 않고 마지막 실제 답을 돌려준다. 서버 테스트 3건 추가, 키 없이 재생되는 것 확인. AXHub에 배포(배포본에서는 켜지 않음) → `3-design/decisions.md`, `3-design/architecture.md` "AI 호출"
- 결정 창에서 사유 없는 거절 버튼 끔 (2026-11-15, 발견한 점 ⑥): 사유를 적기 전에는 실행 버튼이 꺼지고 안내 문구가 보인다. 서버 확인은 그대로 → `3-design/browser-test-scenarios.md`
- AI 안건 요약 편집 창 (2026-11-15): `이 내용 사용`을 누르면 큰 편집 창이 뜨고, 창에서 고친 뒤 바로 상신한다. 폼의 작은 안건 요약 칸은 없애고 창을 여는 버튼으로 바꿨다. 브라우저 테스트 TC-00 ~ TC-06 통과. TC-07은 재생 모드로 7-1·7-5까지 통과했다(7-2는 재생 답이 맞지 않아 멈춤, 실제 호출로는 다시 돌리지 않음). 배포 안 함 → `3-design/decisions.md`, `3-design/ui-guide.md`
- UI 가이드 v5 적용 (2026-11-15, 실무자 관점 검토의 제안 A·C): 결정 창(위원회 창은 요약 첫 줄만 보여 선택 버튼이 첫 화면에, SCM 창에 판단 근거), 작업 번호 통일(`T-004`), 규칙 번호·가정 ID는 툴팁으로, "방금 바뀐 것"은 결과 요약, `적용일`은 폼 맨 아래, `시연용 예시` 줄. 브라우저 테스트 TC-00 ~ TC-06 통과, TC-07은 재생 모드로 7-1·7-5까지. 배포 안 함 → `3-design/ui-guide.md`, `3-design/decisions.md`
- AXHub 재배포 (2026-11-14): 커밋 `4004d51`을 `origin`(AXHub 저장소)에 푸시하자 운영 배포가 자동으로 시작돼 성공했다. 배포본 확인: 상태 확인 경로·첫 화면 200, 화면 묶음이 로컬 빌드와 같은 파일, AI 사용 가능. 이후 `W03_AI_MODEL`을 AXHub 설정값으로 등록해 배포본도 로컬과 같은 `claude-sonnet-5-5`를 쓰게 했다(설정값은 다시 배포해야 반영된다). **`origin`에 `main`을 푸시하면 운영에 바로 배포된다.** 비공개 GitHub 저장소 `yhk1059/aurora-ai-tqm-w03`(원격 이름 `github`)에도 같은 커밋을 올렸다

## 다음 할 일
0. 서버 테스트 실패 4건 확인 (2026-11-15 실행, `backend/tests/test_ai.py` 3건 + `test_api.py::test_ai_no_key`): 모델 이름을 `claude-opus-5-5`로 기대하는데 실행 환경은 `claude-sonnet-5-5`이고, 키 없음·재생 모드 테스트가 실행 환경의 키·재생 설정을 그대로 읽는다 (UI 변경과 무관, 서버 코드는 바꾸지 않음)
1. 브라우저 테스트에서 발견한 점 중 남은 ③⑤(계획 v1·v2 둘 다 확정, 계획 표 잘림) 고칠지 정하기 (`3-design/browser-test-scenarios.md` "발견한 점")
2. 배치 카드 출처 배지를 접어 둔 것, 작업 줄·폼의 규칙 번호·가정 ID를 툴팁으로 옮긴 것(v5)이 완료 조건 5에 충분한지 확인
3. UI 검토 제안 중 남은 B(사건 탭 본문을 단계에 따라 바꾸기)·D(재공급 계획 탭 정리)를 할지 정하기 (`3-design/decisions.md` 2026-11-15 "UI 가이드 v5")
4. 시연 영상 촬영

- 미정 질문 6건 확정: 불량률 분모 = 생산 수량, 합격 배치 = 관찰, 재공급 규칙 3단계, 필수 확장 = 원료 로트 기반 영향 추적, 초기 상태 = 위원회 미상신, 스택 = Python + Streamlit + SQLite + Claude API(이후 화면은 React + FastAPI로 변경, 아래 참조) → `3-design/decisions.md`, 가정 A-01~A-06 → `3-design/assumptions.md`
- C-101 수주 감소는 원인 분석 없이 영업 임원 확인 요청으로 다루고, 그 회신이 재공급 순서를 바꾸는 "다른 부서 영향"으로 쓴다 (범위 규칙 ④ + 재공급 규칙 결정)

## 미정 질문
> 정해지면 `3-design/decisions.md`로 옮기고 여기서 지운다.
- 배포본의 DB 공유: 배포 주소에서는 모든 접속자가 SQLite 파일 하나를 쓴다. 두 사람이 동시에 열면 한쪽의 초기화가 다른 쪽 상태를 지운다. 브라우저별로 나눌지, 그대로 두고 안내만 할지 (`1-frontend` 범위 밖)
