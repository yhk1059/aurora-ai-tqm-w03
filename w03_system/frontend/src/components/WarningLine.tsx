import { TriangleAlert } from 'lucide-react'
import type { ReactNode } from 'react'

/** 경고 문장이 "핵심: 자세한 것" 또는 "핵심 (자세한 것)" 꼴이면 핵심만 굵게 그린다. 글자는 바꾸지 않는다 (ui-guide.md v11) */
function emphasize(text: ReactNode): ReactNode {
  if (typeof text !== 'string') return text
  const m = text.match(/^(.+?)(: | \()(.*)$/s)
  return m ? <><span className="font-semibold">{m[1]}</span>{m[2]}{m[3]}</> : text
}

export function WarningLine({ children, rule }: { children: ReactNode; rule?: string | null }) {
  return (
    <div className="flex items-start gap-2 text-sm text-amber-700">
      <TriangleAlert size={16} strokeWidth={1.5} className="mt-0.5 shrink-0" />
      <span>
        {emphasize(children)}
        {rule && <span className="ml-1.5 font-mono text-xs text-amber-600">{rule}</span>}
      </span>
    </div>
  )
}
