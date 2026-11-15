import { useContext, useState } from 'react'
import { AppContext } from '../context'

// 출처 배지 (ui-guide.md "출처 배지"): 원본·도출·시스템 = 실선, 가정·모의 = 점선.
// 누르면 근거(원본 파일·행 ID, 가정 문구)가 펼쳐진다. 가정 ID가 있으면 그 가정의 내용과 이유를 가정 목록에서 찾아 보인다.
const DASHED = new Set(['가정', '모의'])

type Props = {
  source: string
  /** 가정 ID 등 배지에 함께 쓸 참조 (예: 'A-07') */
  refId?: string | null
  /** 근거 목록 (evidence) */
  evidence?: string[]
  /** 가정 문구 등 근거 설명 */
  note?: string | null
}

export function SourceBadge({ source, refId, evidence = [], note }: Props) {
  const [open, setOpen] = useState(false)
  const assumption = useContext(AppContext)?.ontology.assumptions.find(a => a.id === refId)
  const hasDetail = evidence.length > 0 || !!note || !!assumption
  const border = DASHED.has(source) ? 'border-dashed border-neutral-400' : 'border-solid border-neutral-300'
  const label = refId ? `${source} ${refId}` : source
  return (
    <span className="relative inline-flex">
      <button
        type="button"
        onClick={() => hasDetail && setOpen(o => !o)}
        className={`inline-flex items-center rounded px-1.5 h-5 text-[11px] text-neutral-600 border ${border} ${hasDetail ? 'cursor-pointer hover:text-neutral-900' : 'cursor-default'}`}
        title={hasDetail ? '근거 보기' : undefined}
      >
        {label}
      </button>
      {open && (
        <span className="absolute left-0 top-6 z-20 w-80 rounded-md border border-neutral-200 bg-white p-2 text-xs text-neutral-700 space-y-1">
          {assumption && <span className="block text-neutral-900">{assumption.text}</span>}
          {assumption && <span className="block text-neutral-600">원본에 없는 이유: {assumption.reason}</span>}
          {note && <span className="block">{note}</span>}
          {evidence.map(e => (
            <span key={e} className="block font-mono break-all text-neutral-600">{e}</span>
          ))}
        </span>
      )}
    </span>
  )
}
