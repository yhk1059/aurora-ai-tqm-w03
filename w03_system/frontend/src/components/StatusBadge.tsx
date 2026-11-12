// 상태 → 색 매핑은 이 파일 한 곳에만 둔다 (ui-guide.md "데이터/시맨틱 색상").
// 색은 상태의 뜻만 나타내고, 상태 글자는 항상 함께 보인다. 표에 없는 상태는 회색.
// 색 하나 = 글자·배경(배지) + 테두리(연결망 노드). 상태 → 색은 아래 COLORS 하나뿐이다.
type Tone = { badge: string; border: string }
const RED: Tone = { badge: 'text-red-700 bg-red-50', border: 'border-red-200' }
const AMBER: Tone = { badge: 'text-amber-700 bg-amber-50', border: 'border-amber-200' }
const BLUE: Tone = { badge: 'text-blue-700 bg-blue-50', border: 'border-blue-200' }
const GREEN: Tone = { badge: 'text-emerald-700 bg-emerald-50', border: 'border-emerald-200' }
const GRAY: Tone = { badge: 'text-neutral-600 bg-neutral-100', border: 'border-neutral-200' }

const COLORS: Record<string, Tone> = {
  // 빨강: 기준 초과, 회수 (배치 판정 상태, 사건 상태 '회수진행')
  '기준초과(미상신)': RED, '회수진행': RED, '부분회수': RED,
  // 배치 카드의 기준 비교 글자 (metrics.over_threshold, R2)
  '기준 초과': RED, '기준 미달': GRAY,
  // 주황: 경고, 확인 안 됨 (SHIPPED_TO 미확인, 미확정 클레임)
  '미확인': AMBER, '접수': AMBER, '조사중': AMBER,
  // 입고검사·QC 결과 '보류' (보류 로트 투입, 보류 출하 경고의 대상)
  '보류': AMBER,
  // 파랑: 사람의 응답을 기다리는 중 (상신중, 확인요청중, 조사계속, 계획 초안, 작업·사건 열림, 사건 판정중)
  '상신중': BLUE, '확인요청중': BLUE, '조사계속': BLUE, '초안': BLUE, '열림': BLUE, '판정중': BLUE,
  // 초록: 확인됨, 확정됨 (확인, 회신확인, 계획·클레임 확정, 작업 완료, 사건 복구계획확정)
  '확인': GREEN, '회신확인': GREEN, '확정': GREEN, '완료': GREEN, '복구계획확정': GREEN,
  // 회색: 문제 없음, 종료
  '정상': GRAY, '관찰': GRAY, '관찰해제': GRAY, '관찰중': GRAY, '영향없음': GRAY, '기각': GRAY, '대체됨': GRAY,
}

function tone(state: string | null | undefined): Tone {
  return (state && COLORS[state]) || GRAY
}

export function statusColor(state: string | null | undefined): string {
  return tone(state).badge
}

/** 같은 매핑의 테두리 색 (연결망 노드) */
export function statusBorder(state: string | null | undefined): string {
  return tone(state).border
}

export function StatusBadge({ state }: { state: string | null | undefined }) {
  return (
    <span className={`inline-flex items-center rounded px-2 h-6 text-xs font-medium whitespace-nowrap ${statusColor(state)}`}>
      {state ?? '—'}
    </span>
  )
}
