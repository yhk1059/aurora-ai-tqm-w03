# status — 진행 상태

_마지막 갱신: 2026-11-12_

## 단계
**업무모델·온톨로지·시연 시나리오·아키텍처 v1 확정, UI 가이드 작성 전, 구현 전.** 과제 규칙·배경(`1-brief/`) 정리 완료. 2026-11-11 초기화 이후 다시 시작해, 2026-11-12에 근본 원인, W03 스코프(C안), 스코핑 6항목, 설계 전제 6건을 확정했다.

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

## 다음 할 일
1. `3-design/ui-guide.md` 작성 (디자인 원칙, 색상, 화면 구성, 연결망 그림 방식)
2. 구현 step 설계 (`/harness` C단계): 서버(core → api)를 먼저, 화면은 그 뒤

- 미정 질문 6건 확정: 불량률 분모 = 생산 수량, 합격 배치 = 관찰, 재공급 규칙 3단계, 필수 확장 = 원료 로트 기반 영향 추적, 초기 상태 = 위원회 미상신, 스택 = Python + Streamlit + SQLite + Claude API(이후 화면은 React + FastAPI로 변경, 아래 참조) → `3-design/decisions.md`, 가정 A-01~A-06 → `3-design/assumptions.md`
- C-101 수주 감소는 원인 분석 없이 영업 임원 확인 요청으로 다루고, 그 회신이 재공급 순서를 바꾸는 "다른 부서 영향"으로 쓴다 (범위 규칙 ④ + 재공급 규칙 결정)

## 미정 질문
> 정해지면 `3-design/decisions.md`로 옮기고 여기서 지운다.
- (없음)
