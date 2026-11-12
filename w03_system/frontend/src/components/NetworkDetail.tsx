import type { ReactNode } from 'react'
import { useApp } from '../context'
import { fmtDate, fmtQty } from '../format'
import type { Link, Obj, OpenView, ShippedTo } from '../types'
import { Card } from './Card'
import type { Selection } from './Network'
import { SourceBadge } from './SourceBadge'
import { StatusBadge } from './StatusBadge'

// 연결망 옆 패널: 고른 노드·선의 속성, 상태, 출처, 근거 원본 행을 서버 값 그대로 보인다. 읽기 전용.

const OBJ_TYPE = { lot: 'material_lot', batch: 'batch', customer: 'customer' } as const

/** 뷰의 link 키 → 온톨로지 link_attributes 키 */
const LINK_KEY: Record<string, string> = {
  source: 'source', confirm: 'confirmation', qty: 'qty', qty_basis: 'qty_basis',
  evidence: 'evidence_ref', applied_date: 'applied_date', recorded_date: 'recorded_date',
}

function fmtValue(v: unknown): ReactNode {
  if (v === null || v === undefined || v === '') return '—'
  if (Array.isArray(v)) return v.length ? v.map(String).join(', ') : '—'
  if (typeof v === 'object') {
    // 월별 수주 전년비처럼 키-값 묶음: 값이 있는 것만
    const entries = Object.entries(v as Record<string, unknown>).filter(([, x]) => x !== null && x !== undefined)
    return entries.length ? entries.map(([k, x]) => `${k}: ${String(x)}`).join(' · ') : '—'
  }
  if (typeof v === 'number') return v.toLocaleString('ko-KR')
  if (typeof v === 'boolean') return v ? '예' : '아니오'
  return String(v)
}

function Rows({ rows }: { rows: [string, ReactNode][] }) {
  return (
    <table className="w-full text-sm">
      <tbody>
        {rows.map(([k, v]) => (
          <tr key={k} className="border-t border-neutral-100 align-top">
            <th className="w-36 py-1 pr-2 text-left text-xs font-medium text-neutral-500">{k}</th>
            <td className="py-1 text-neutral-700 tabular-nums break-all">{v}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function Evidence({ items }: { items: string[] }) {
  if (!items.length) return <p className="text-xs text-neutral-500">근거 행 없음</p>
  return (
    <div className="space-y-0.5">
      <div className="text-xs font-medium text-neutral-500">근거</div>
      {items.map(e => <div key={e} className="font-mono text-xs text-neutral-600 break-all">{e}</div>)}
    </div>
  )
}

export function NetworkDetail({ view, selected }: { view: OpenView; selected: Selection }) {
  const { ontology } = useApp()

  if (selected.kind === 'link') {
    const st = view.network.shipped_to.find(l => l.link_id === selected.linkId)
    const ui = view.network.used_in.find(l => l.link_id === selected.linkId)
    const link: Link | undefined = st ?? ui
    if (!link) return null
    const name = (k: string) => ontology.link_attributes.find(a => a.key === (LINK_KEY[k] ?? k))?.name ?? k
    const rows: [string, ReactNode][] = []
    if (st) {
      rows.push([name('confirm'), <StatusBadge state={st.confirm} />])
      rows.push([name('qty'), fmtQty(st.qty)])
      rows.push([name('qty_basis'), <QtyBasis link={st} />])
      rows.push(['클레임 (확정/전체)', `${st.claims.confirmed_count} / ${st.claims.count}건 · ${fmtQty(st.claims.confirmed_qty)} / ${fmtQty(st.claims.qty)}`])
    }
    rows.push([name('applied_date'), fmtDate(link.applied_date)])
    rows.push([name('recorded_date'), fmtDate(link.recorded_date)])
    for (const [k, v] of Object.entries(link.attrs)) rows.push([k, fmtValue(v)])
    return (
      <Card title={`${link.rel} · ${link.src.id} → ${link.dst.id}`}>
        <div className="flex items-center gap-2 text-sm">
          <span className="text-xs text-neutral-500">{name('source')}</span>
          <SourceBadge source={link.source} />
          {st && <span className="text-xs text-neutral-500">클레임 합</span>}
          {st && <SourceBadge source={st.claims.source} note="클레임 건수·수량은 이 배치×고객 클레임의 합 (도출)" evidence={st.claims.claim_ids} />}
        </div>
        <Rows rows={rows} />
        <Evidence items={link.evidence} />
      </Card>
    )
  }

  const list: Obj[] = selected.kind === 'lot' ? view.lots : selected.kind === 'batch' ? view.batches : view.customers
  const obj = list.find(o => o.id === selected.id)
  if (!obj) return null
  const def = ontology.object_types[OBJ_TYPE[selected.kind]]
  const attrName = (k: string) => def?.stored.find(a => a.key === k)?.name ?? k
  const rows: [string, ReactNode][] = Object.entries(obj.attrs).map(([k, v]) => [attrName(k), fmtValue(v)])

  // 고객: 수주 급감 신호와 이 고객으로 가는 선의 합 (서버 shipped_to 값의 합계)
  let extra: ReactNode = null
  if (selected.kind === 'customer') {
    const c = view.customers.find(x => x.id === obj.id)!
    const lines = view.network.shipped_to.filter(l => l.dst.id === obj.id)
    const cnt = lines.reduce((s, l) => s + l.claims.count, 0)
    const qty = lines.reduce((s, l) => s + l.claims.qty, 0)
    rows.push(['수주 급감 신호', `${c.order_drop_signal.signal ? '있음' : '없음'} (${c.order_drop_signal.rule}: ${c.order_drop_signal.months.map(([m, x]) => `${m} ${x ?? '—'}%`).join(', ')})`])
    rows.push(['들어오는 선', lines.length ? lines.map(l => `${l.src.id} ${l.confirm}`).join(' · ') : '없음'])
    rows.push(['클레임 합 (전체 선)', `${cnt}건, ${fmtQty(qty)}`])
    extra = <SourceBadge source={c.order_drop_signal.source} />
  }
  if (selected.kind === 'batch') {
    const b = view.batches.find(x => x.id === obj.id)!
    rows.push(['사건에 묶인 이유', fmtValue(b.part_of.reason)])
  }

  return (
    <Card title={`${def?.name ?? selected.kind} · ${obj.id}`}>
      <div className="flex items-center gap-2 text-sm">
        <span className="text-xs text-neutral-500">상태</span>
        {obj.state ? <StatusBadge state={obj.state} /> : <span className="text-neutral-400">—</span>}
        <span className="text-xs text-neutral-500">출처</span>
        <SourceBadge source={obj.source} evidence={obj.evidence} />
        {extra}
      </div>
      <Rows rows={rows} />
      <Evidence items={obj.evidence} />
    </Card>
  )
}

function QtyBasis({ link }: { link: ShippedTo }) {
  const b = link.qty_basis
  if (b === '없음') return <span className="text-amber-700">없음 — 출하 기록 없음 (클레임만 있음)</span>
  if (b && b.includes('하한')) return <span className="text-amber-700">{b} — 실제는 더 많을 수 있음</span>
  return <>{b ?? '—'}</>
}
