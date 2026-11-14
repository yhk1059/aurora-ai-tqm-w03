import { ChevronDown, ChevronRight } from 'lucide-react'
import { useState } from 'react'
import { useApp } from '../context'
import { fmtDate, fmtQty } from '../format'
import type { Claim } from '../types'
import { ActionForm, targetIds } from './ActionForm'
import { Button } from './Button'
import { SourceBadge } from './SourceBadge'
import { StatusBadge } from './StatusBadge'

// 배치 카드 아래의 접을 수 있는 클레임 요약: 고객별 확정/미확정 건수·수량.
// 미확정 클레임(접수·조사중)은 따로 줄로 보이고, 서버가 resolve_claim 대상으로 준 클레임에만 판정 버튼이 붙는다.
type Group = { customer: string; confirmed: number; confirmedQty: number; pending: number; pendingQty: number; other: number }

function PendingRow({ c, canResolve }: { c: Claim; canResolve: boolean }) {
  const [open, setOpen] = useState(false)
  return (
    <li className="space-y-2">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span className="font-mono text-neutral-900">{c.id}</span>
        <StatusBadge state={c.state} />
        <span className="text-amber-700">미확정</span>
        <span className="font-mono text-neutral-700">{c.customer_id ?? '—'}</span>
        <span className="tabular-nums text-neutral-700">{fmtQty(c.attrs.qty)}</span>
        <span className="tabular-nums text-neutral-500">접수 {fmtDate(c.attrs.received_date)}</span>
        <SourceBadge source={c.source} evidence={c.evidence} />
        {canResolve && !open && <Button variant="secondary" onClick={() => setOpen(true)}>판정 반영</Button>}
      </div>
      {canResolve && open && (
        <div className="rounded-md border border-indigo-300 p-3">
          <ActionForm action="resolve_claim" fixed={{ claim_id: c.id }} onDone={() => setOpen(false)} onCancel={() => setOpen(false)} />
        </div>
      )}
    </li>
  )
}

export function ClaimSummary({ claims }: { claims: Claim[] }) {
  const { view } = useApp()
  const pending = claims.filter(c => c.pending)
  // 사람이 접고 펴기 전에는 미확정 클레임이 있을 때 펼친다
  const [toggled, setToggled] = useState<boolean | null>(null)
  const open = toggled ?? pending.length > 0
  if (claims.length === 0) return <p className="text-sm text-neutral-500">클레임 없음</p>

  const resolvable = new Set(targetIds(view, 'resolve_claim', 'claim_id') ?? [])
  const groups = new Map<string, Group>()
  for (const c of claims) {
    const k = c.customer_id ?? '—'
    const g = groups.get(k) ?? { customer: k, confirmed: 0, confirmedQty: 0, pending: 0, pendingQty: 0, other: 0 }
    if (c.attrs.defect_confirmed) { g.confirmed += 1; g.confirmedQty += c.attrs.qty }
    else if (c.pending) { g.pending += 1; g.pendingQty += c.attrs.qty }
    else g.other += 1
    groups.set(k, g)
  }
  const rows = [...groups.values()].sort((a, b) => a.customer.localeCompare(b.customer))
  const Icon = open ? ChevronDown : ChevronRight

  return (
    <div className="space-y-2">
      <button type="button" onClick={() => setToggled(!open)} className="inline-flex items-center gap-1 text-xs font-medium text-neutral-500 hover:text-neutral-900">
        <Icon size={16} strokeWidth={1.5} />
        클레임 {claims.length}건
        {pending.length > 0 && <span className="text-amber-700"> · 미확정 {pending.length}건</span>}
      </button>
      {open && (
        <>
          <table className="w-full text-sm tabular-nums">
            <thead className="bg-neutral-100">
              <tr className="text-xs text-neutral-500">
                <th className="px-2 h-7 text-left font-medium">고객</th>
                <th className="px-2 h-7 text-right font-medium">확정 건수</th>
                <th className="px-2 h-7 text-right font-medium">확정 수량</th>
                <th className="px-2 h-7 text-right font-medium">미확정 건수</th>
                <th className="px-2 h-7 text-right font-medium">미확정 수량</th>
                <th className="px-2 h-7 text-right font-medium">기각 등</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(g => (
                <tr key={g.customer} className="border-t border-neutral-100">
                  <td className="px-2 h-7 font-mono">{g.customer}</td>
                  <td className="px-2 h-7 text-right">{g.confirmed}</td>
                  <td className="px-2 h-7 text-right">{fmtQty(g.confirmedQty)}</td>
                  <td className={`px-2 h-7 text-right ${g.pending ? 'text-amber-700' : ''}`}>{g.pending}</td>
                  <td className={`px-2 h-7 text-right ${g.pending ? 'text-amber-700' : ''}`}>{fmtQty(g.pendingQty)}</td>
                  <td className="px-2 h-7 text-right text-neutral-500">{g.other}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {pending.length > 0 && (
            <ul className="space-y-2 rounded-md border border-amber-200 bg-amber-50 p-3">
              {pending.map(c => <PendingRow key={c.id} c={c} canResolve={resolvable.has(c.id)} />)}
            </ul>
          )}
        </>
      )}
    </div>
  )
}
