# Step 4: network

## 읽어야 할 파일

먼저 아래 파일들을 읽고 과제와 설계 의도를 파악하라:

- `/CLAUDE.md`
- `/w03_system/brain/status.md`
- `/w03_system/brain/3-design/architecture.md` (패턴 4)
- `/w03_system/brain/3-design/ui-guide.md` ("레이아웃"의 "연결망", "데이터/시맨틱 색상", "출처 배지")
- `/w03_system/brain/3-design/business-model.md` §8 (관계 `USED_IN`·`SHIPPED_TO`, 확인 수준, 수량 근거), R4·R5·R5-1·R8
- `/w03_system/brain/3-design/decisions.md` (필수 확장 = 원료 로트 기반 영향 추적)
- `/w03_system/backend/core/view.py` (`lots`, `batches`, `customers`, `network.used_in`, `network.shipped_to`와 그 `claims`, `_link`·`_obj`의 키)
- `/w03_system/frontend/src/` 전부 (특히 `tabs/IncidentTab.tsx`, `components/StatusBadge.tsx`, `components/SourceBadge.tsx`)

이전 step에서 만들어진 코드를 꼼꼼히 읽고, 설계 의도를 이해한 뒤 작업하라.

## 작업

사건 탭 왼쪽, 배치 판정 카드 아래에 **연결망**을 넣는다. 이것이 과제의 "나만의 확장"(원료 로트 기반 영향 추적)이 화면에 보이는 곳이다: 원료 로트 하나에서 어떤 배치가 나왔고, 그 배치가 어느 고객에게 갔고, 그 관계를 얼마나 확신하는지.

### 라이브러리

`@xyflow/react`(React Flow)를 설치하고 버전을 `package.json`에 고정한다. 사용법은 추측하지 말고 설치된 패키지의 타입 정의·문서를 확인하라. 다른 그래프·배치 라이브러리(dagre, elk, d3-force 등)는 넣지 않는다.

### `components/Network.tsx`

```ts
type Props = { view: IncidentView; onSelect(sel: Selection | null): void; selected: Selection | null }
type Selection = { kind: "lot" | "batch" | "customer"; id: string } | { kind: "link"; linkId: number }
```

- **3열 고정 배치**: 원료 로트 → 배치 → 고객. 좌표는 열과 순번(ID 순)으로 계산한다. 자동 배치·물리 효과를 쓰지 않는다. 이유: 열 때마다 같은 모양이어야 시연 영상에서 전후 비교가 된다.
- **노드**: ID(`font-mono`)와 상태 글자. 테두리 색 = 상태의 시맨틱 색(`StatusBadge`와 같은 매핑을 쓴다. 매핑을 복사하지 말고 한 곳에서 가져온다). 로트는 입고검사 결과를, 고객은 이름을 함께 보인다. 수주 급감 신호가 있는 고객(`order_drop_signal.signal`)은 주황 표시와 "수주 급감 신호" 글자.
- **선 (로트 → 배치, `used_in`)**: 실선. 기점 로트(`incident.origin_lots`)에서 나온 선임이 보이게 한다.
- **선 (배치 → 고객, `shipped_to`)**: 모양 = 확인 수준. 실선 = `확인`·`회신확인`, 점선 = `미확인`·`확인요청중`, 옅은 회색 = `영향없음`. 확인 수준 → 선 모양 매핑은 이 파일 한 곳에 둔다.
- **선 위 글자**: 클레임이 있으면 "N건, 수량 EA"(`shipped_to[].claims`). 클레임은 노드로 그리지 않는다.
- 확대·이동은 허용, 노드 드래그·연결 편집·선택 상자는 끈다. React Flow의 기본 워터마크 처리는 라이브러리 라이선스 안내를 따른다.
- 높이는 고정(노드 수에 맞춰 계산)하고 처음에 전체가 보이게 맞춘다.
- 선 모양의 뜻을 설명하는 작은 범례를 연결망 아래에 글자로 둔다.

### 옆 패널 `components/NetworkDetail.tsx`

노드나 선을 누르면 연결망 오른쪽(또는 아래)에 패널이 나온다.

- 노드: 속성(`attrs`) 전체를 이름-값 표로, 상태, 출처 배지, 근거 원본 행(`evidence` 목록 그대로).
- 배치 → 고객 선: 확인 수준, 수량과 수량 근거(`qty`, `qty_basis`. 하한이면 "실제는 더 많을 수 있음"), 출처, 근거(출하 기록 ID 또는 회신 이벤트 ID), 적용일·기록일, 그 선의 클레임 건수·수량(확정/전체).
- 로트 → 배치 선: 속성, 출처, 근거.
- 속성 이름은 온톨로지 정의(`ontology.object_types[타입]`의 속성 이름, `link_attributes`)에 있으면 그 한국어 이름을 쓰고, 없으면 키를 그대로 쓴다.

### 실행 확인

서버와 화면을 띄워 사건을 열고(`B-02-2602-01`) 확인한 뒤 종료한다:
- 로트 `LOT-B-2602-P` 하나에서 배치 4개로 선이 나간다.
- C-105로 가는 선이 점선(미확인)이고, 누르면 "출하 기록 없음, 클레임 14건 11,765 EA"에 해당하는 값이 패널에 나온다.
- 다시 열어도 노드 위치가 같다.

## Acceptance Criteria

```bash
npm --prefix w03_system/frontend run build
w03_system/.venv/bin/python -m pytest -q w03_system/backend/tests
```

## 검증 절차

1. 위 AC 커맨드를 실행한다.
2. 아키텍처 체크리스트를 확인한다:
   - `3-design/architecture.md`의 디렉토리 구조·모듈 경계를 따르는가?
   - `3-design/ui-guide.md`의 "연결망" 항목을 전부 따르는가? 안티패턴을 쓰지 않았는가?
   - `3-design/business-model.md`의 관계·확인 수준과 일치하는가?
   - CLAUDE.md 금지 규칙을 위반하지 않았는가?
3. 결과에 따라 `w03_system/phases/1-frontend/index.json`의 해당 step을 업데이트한다:
   - 성공 → `"status": "completed"`, `"summary": "산출물 한 줄 요약"` (설치한 라이브러리 버전, 컴포넌트와 props를 적는다)
   - 수정 3회 시도 후에도 실패 → `"status": "error"`, `"error_message": "구체적 에러 내용"`
   - 사용자 개입 필요 → `"status": "blocked"`, `"blocked_reason": "구체적 사유"` 후 즉시 중단

## 금지사항

- 화면에서 관계를 추론해 선을 만들지 마라(예: 클레임이 있으니 출하 선 추가). 이유: 선은 서버의 `network.used_in`·`network.shipped_to`에 있는 것만 그린다. 미확인 관계도 서버가 줄로 내려준다.
- 자동 배치·물리 효과·노드 등장 애니메이션을 쓰지 마라. 이유: `ui-guide.md` "연결망"과 "애니메이션".
- 연결망에서 액션을 실행하게 만들지 마라. 이유: 연결망은 읽기 화면이고 액션은 판정 카드와 작업 목록에서 한다.
- 서버 코드(`w03_system/backend/`)를 고치지 마라. 이유: 이 step은 화면만 다룬다. 서버에 없는 값이 필요하면 `blocked`로 남겨라.
- `01_참가자_배포용/04_원본데이터/`의 파일을 수정하지 마라. 이유: 원본 데이터는 대회 규칙상 수정 금지다.
- 기존 테스트를 깨뜨리지 마라
