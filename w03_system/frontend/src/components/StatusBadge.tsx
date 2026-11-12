// 상태 → 색 매핑은 이 파일 한 곳에만 둔다 (ui-guide.md "데이터/시맨틱 색상").
// 색은 상태의 뜻만 나타내고, 상태 글자는 항상 함께 보인다. 표에 없는 상태는 회색.
const RED = 'text-red-700 bg-red-50'
const AMBER = 'text-amber-700 bg-amber-50'
const BLUE = 'text-blue-700 bg-blue-50'
const GREEN = 'text-emerald-700 bg-emerald-50'
const GRAY = 'text-neutral-600 bg-neutral-100'

const COLORS: Record<string, string> = {
  // 빨강: 기준 초과, 회수 (배치 판정 상태, 사건 상태 '회수진행')
  '기준초과(미상신)': RED, '회수진행': RED, '부분회수': RED,
  // 배치 카드의 기준 비교 글자 (metrics.over_threshold, R2)
  '기준 초과': RED, '기준 미달': GRAY,
  // 주황: 경고, 확인 안 됨 (SHIPPED_TO 미확인, 미확정 클레임)
  '미확인': AMBER, '접수': AMBER, '조사중': AMBER,
  // 파랑: 사람의 응답을 기다리는 중 (상신중, 확인요청중, 조사계속, 계획 초안, 작업·사건 열림, 사건 판정중)
  '상신중': BLUE, '확인요청중': BLUE, '조사계속': BLUE, '초안': BLUE, '열림': BLUE, '판정중': BLUE,
  // 초록: 확인됨, 확정됨 (확인, 회신확인, 계획·클레임 확정, 작업 완료, 사건 복구계획확정)
  '확인': GREEN, '회신확인': GREEN, '확정': GREEN, '완료': GREEN, '복구계획확정': GREEN,
  // 회색: 문제 없음, 종료
  '정상': GRAY, '관찰': GRAY, '관찰해제': GRAY, '관찰중': GRAY, '영향없음': GRAY, '기각': GRAY, '대체됨': GRAY,
}

export function statusColor(state: string | null | undefined): string {
  return (state && COLORS[state]) || GRAY
}

export function StatusBadge({ state }: { state: string | null | undefined }) {
  return (
    <span className={`inline-flex items-center rounded px-2 h-6 text-xs font-medium whitespace-nowrap ${statusColor(state)}`}>
      {state ?? '—'}
    </span>
  )
}
