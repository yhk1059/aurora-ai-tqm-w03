import { useEffect, useState } from 'react'
import { getReplyExamples } from '../api'
import type { ReplyExample } from '../types'
import { SourceBadge } from './SourceBadge'

// 모의 입력 예시 (decisions.md "화면 구현 전 정리 4건" ①). 고르면 폼을 채우기만 한다. 실행은 사람이 버튼으로 한다.
// 예시는 GET /api/reply-examples에서 한 번만 받아 둔다.
let cache: Promise<ReplyExample[]> | null = null
function loadExamples(): Promise<ReplyExample[]> {
  if (!cache) cache = getReplyExamples().catch(() => { cache = null; return [] })
  return cache
}

type Props = {
  action: string
  /** apply_reply: 그 작업의 유형. 예시의 task_type이 있으면 같아야 보인다 */
  taskType?: string | null
  /** 작업 대상 고객. 예시의 customer_id가 있으면 이 안에 있어야 보인다 */
  customerIds?: string[]
  onPick: (inputs: Record<string, unknown>) => void
}

export function ExamplePicker({ action, taskType = null, customerIds = [], onPick }: Props) {
  const [all, setAll] = useState<ReplyExample[]>([])
  const [picked, setPicked] = useState<number | null>(null)
  useEffect(() => {
    let alive = true
    loadExamples().then(xs => { if (alive) setAll(xs) })
    return () => { alive = false }
  }, [])

  const list = all.filter(ex =>
    ex.action === action
    && (ex.task_type === null || ex.task_type === taskType)
    && (ex.customer_id === null || customerIds.includes(ex.customer_id)))
  if (list.length === 0) return null

  // 실무 입력이 아니라 시연 장치임을 이름으로 드러낸다. 출처 배지는 묶음에 한 번, 유리·불리는 툴팁 (ui-guide.md v5)
  const sources = [...new Set(list.map(ex => ex.source))]
  return (
    <div className="flex flex-wrap items-center gap-2">
      <span className="inline-flex items-center gap-1 text-xs text-neutral-500">
        시연용 예시
        {sources.map(s => <SourceBadge key={s} source={s} note="예시 입력. 고르면 폼만 채우고, 실행은 버튼으로 한다" />)}
      </span>
      {list.map((ex, i) => (
        <button
          key={`${ex.label}-${i}`}
          type="button"
          title={`${ex.tone}한 경우의 예시`}
          onClick={() => { setPicked(i); onPick(ex.inputs) }}
          className={`inline-flex items-center rounded-md border px-2 h-7 text-xs ${picked === i
            ? 'border-neutral-900 text-neutral-900 bg-neutral-100'
            : 'border-neutral-300 text-neutral-700 bg-white hover:bg-neutral-50'}`}
        >
          {ex.label}
        </button>
      ))}
    </div>
  )
}
