// 표시 형식 (ui-guide.md 타이포그래피): 수량 = 천 단위 + EA, 비율 = 소수 한 자리 %, 날짜 = YYYY-MM-DD 그대로.
// 값이 없으면 '—'.
const NONE = '—'

export function fmtQty(n: number | null | undefined): string {
  if (n === null || n === undefined) return NONE
  return `${Math.round(n).toLocaleString('ko-KR')} EA`
}

/** 0~1 값을 % 로 */
export function fmtRate(r: number | null | undefined): string {
  if (r === null || r === undefined) return NONE
  return `${(r * 100).toFixed(1)}%`
}

export function fmtDate(d: string | null | undefined): string {
  return d ?? NONE
}
