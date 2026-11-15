import { useEffect, useState } from 'react'
import { fmtQty } from '../format'
import type { IncidentView, OpenView, ShippedTo } from '../types'
import { statusBorder, statusColor } from './StatusBadge'

// 연결망 (ui-guide.md "연결망" v17): 원료 로트 → 배치 → 고객을 표로 그린다. 줄 = 배치, 열 = 고객, 칸 = 그 배치 → 고객 연결.
// 선으로 그리면 배치 → 고객 선이 서로 엇갈려 어느 선이 어느 고객 것인지 읽기 어려워서 칸으로 바꿨다. 읽기 화면이라 액션은 없다.
// 로트·배치·고객·칸은 서버의 lots / batches / customers / network.used_in / network.shipped_to에 있는 것만 그린다.

export type Selection =
  | { kind: 'lot' | 'batch' | 'customer'; id: string }
  | { kind: 'link'; linkId: number }

/** 연결망에서 마지막으로 본 액션 기록 번호 (App이 들고 있다). null = 아직 기준 없음 */
export type SeenRef = { current: number | null }

type Props = { view: OpenView; onSelect(sel: Selection | null): void; selected: Selection | null; seen: SeenRef }

/** 가장 최근 액션 기록 번호. 사건이 없거나 기록이 없으면 0 */
export function lastSeq(view: IncidentView): number {
  if (!view.incident) return 0
  const rows = (view as OpenView).log.actions
  return rows.length ? rows[rows.length - 1].seq : 0
}

const UNCONFIRMED = ['미확인', '확인요청중']
/** 출하처 확인이 끝나지 않은 고객 ID (연결의 확인 수준에서 센다) */
export function unconfirmedCustomers(v: OpenView): string[] {
  return [...new Set(v.network.shipped_to.filter(l => UNCONFIRMED.includes(l.confirm)).map(l => l.dst.id))].sort()
}

// --- 확인 수준 → 칸 모양 (이 파일 한 곳) -----------------------------------
// 주황 점선은 아직 확인이 안 된 칸에만 쓴다. 나머지 칸은 회색 테두리로 조용히 둔다.
type CellStyle = { box: string; text: string; strong: string; legend: string }
const SOLID: CellStyle = { box: 'border-solid border-neutral-300 bg-white', text: 'text-neutral-500', strong: 'text-neutral-900', legend: '실선 = 확인·회신확인' }
const DASHED: CellStyle = { box: 'border-dashed border-amber-500 bg-amber-50', text: 'text-amber-800', strong: 'text-amber-900', legend: '점선 = 미확인·확인요청중' }
const FAINT: CellStyle = { box: 'border-solid border-neutral-200 bg-white', text: 'text-neutral-400', strong: 'text-neutral-400', legend: '옅은 회색 = 영향없음 (확인했더니 아님, 칸은 남김)' }
const CELL_BY_CONFIRM: Record<string, CellStyle> = {
  '확인': SOLID, '회신확인': SOLID,
  '미확인': DASHED, '확인요청중': DASHED,
  '영향없음': FAINT,
}
function cellStyle(confirm: string): CellStyle {
  return CELL_BY_CONFIRM[confirm] ?? DASHED
}

// --- 방금 바뀐 것 강조 (ui-guide.md "애니메이션") ------------------------------
// 바뀐 배치·칸만 고르는 규칙을 <style>로 잠깐 얹어 index.css의 keyframes(net-node-flash, net-cell-flash)를 한 번 돌린다.
const FLASH_MS = 1400
const NONE: ReadonlySet<string> = new Set()

function flashCss(keys: ReadonlySet<string>): string {
  const anim = (name: string) => `{animation:${name} ${FLASH_MS}ms ease-out}`
  return [...keys].map(k => {
    if (k.startsWith('link:')) return `[data-network] [data-link="${CSS.escape(k.slice('link:'.length))}"]${anim('net-cell-flash')}`
    if (k.startsWith('batch:')) return `[data-network] [data-node="${CSS.escape(k)}"]${anim('net-node-flash')}`
    return ''
  }).join('')
}

/** 기록 번호 since 뒤에 바뀐 배치·칸의 키 (`batch:ID`, `link:번호`). 새 클레임은 그 배치 → 고객 칸(건수가 바뀐다)으로 옮긴다 */
function changedKeys(v: OpenView, since: number): Set<string> {
  const keys = new Set<string>()
  for (const c of v.log.actions.filter(r => r.seq > since).flatMap(r => r.changes)) {
    const t = c.target
    keys.add(`${t.type}:${t.id}`)
    if (t.type === 'claim' && c.field === 'created') {
      const cl = v.claims.find(x => x.id === t.id)
      const l = cl && v.network.shipped_to.find(s => s.src.id === cl.batch_id && s.dst.id === cl.customer_id)
      if (l) keys.add(`link:${l.link_id}`)
    }
  }
  return keys
}

function isSel(sel: Selection | null, kind: Selection['kind'], key: string | number): boolean {
  if (!sel || sel.kind !== kind) return false
  return sel.kind === 'link' ? sel.linkId === key : sel.id === key
}

const RING = 'ring-2 ring-indigo-600'
const byId = (a: { id: string }, b: { id: string }) => a.id.localeCompare(b.id)

export function Network({ view: v, onSelect, selected, seen }: Props) {
  // 탭을 열 때(그리고 열려 있는 동안 뷰가 바뀔 때) 마지막으로 본 뒤 바뀐 배치·칸을 한 번 강조한다.
  // since = 이 화면이 기준으로 삼는 기록 번호. 강조가 끝나면 지금 번호로 올린다
  const latest = lastSeq(v)
  const [since, setSince] = useState(seen.current)
  const [litSeq, setLitSeq] = useState<number | null>(null)
  useEffect(() => {
    seen.current = latest
    if (since !== null && latest <= since) return
    if (since === null) { setSince(latest); return }
    setLitSeq(latest)
    const t = setTimeout(() => { setLitSeq(null); setSince(latest) }, FLASH_MS + 100)
    return () => clearTimeout(t)
  }, [latest, since, seen])

  const lit = litSeq === latest && since !== null ? changedKeys(v, since) : NONE

  const origin = new Set(v.incident.origin_lots)
  const { used_in, shipped_to } = v.network
  // 로트: 기점 로트 + 사건 배치에 투입된 로트 (서버 lots 중에서만)
  const usedLots = new Set(used_in.map(l => l.src.id))
  const lots = v.lots.filter(l => origin.has(l.id) || usedLots.has(l.id)).sort(byId)
  const batches = [...v.batches].sort(byId)
  const customers = [...v.customers].sort(byId)
  // 칸: 배치 × 고객마다 그 사이의 연결 (보통 1개)
  const cells = new Map<string, ShippedTo[]>()
  for (const l of shipped_to) {
    const key = `${l.src.id}|${l.dst.id}`
    cells.set(key, [...(cells.get(key) ?? []), l])
  }

  /** 고른 것을 다시 누르면 고르기를 푼다 */
  function pick(sel: Selection, on: boolean) {
    onSelect(on ? null : sel)
  }

  return (
    <div className="space-y-3" data-network>
      {lit.size > 0 && <style>{flashCss(lit)}</style>}

      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs font-medium text-neutral-500">원료 로트</span>
        {lots.map(l => {
          const insp = (l.attrs.inspection_result as string | undefined) ?? null
          const on = isSel(selected, 'lot', l.id)
          return (
            <button
              key={l.id} type="button" data-node={`lot:${l.id}`}
              onClick={() => pick({ kind: 'lot', id: l.id }, on)}
              className={`flex flex-wrap items-center gap-x-2 rounded-md border-2 bg-white px-3 py-1.5 text-left hover:bg-neutral-50 ${statusBorder(insp)} ${on ? RING : ''}`}
            >
              <span className="font-mono text-sm text-neutral-900 whitespace-nowrap">{l.id}</span>
              {insp && <span className={`inline-flex items-center rounded px-1.5 h-5 text-xs font-medium whitespace-nowrap ${statusColor(insp)}`}>{insp}</span>}
              <span className="text-xs text-neutral-500">원료 {String(l.attrs.material ?? '—')} · 입고검사 {insp ?? '—'}</span>
              {origin.has(l.id) && <span className="text-xs font-medium text-amber-700">기점 로트</span>}
            </button>
          )
        })}
      </div>

      <div className="overflow-x-auto">
        <table className="w-full border-separate border-spacing-1.5 text-left">
          <thead>
            <tr>
              <th scope="col" className="w-60 px-1 align-bottom text-xs font-medium text-neutral-500">배치 ↓ · 고객 →</th>
              {customers.map(c => {
                const drop = c.order_drop_signal.signal
                const on = isSel(selected, 'customer', c.id)
                return (
                  <th key={c.id} scope="col" className="h-px min-w-28 p-0 font-normal">
                    <button
                      type="button" data-node={`customer:${c.id}`}
                      onClick={() => pick({ kind: 'customer', id: c.id }, on)}
                      className={`flex h-full w-full flex-col justify-start rounded-md border-2 bg-white px-2 py-1.5 text-left hover:bg-neutral-50 ${drop ? 'border-amber-200' : 'border-neutral-200'} ${on ? RING : ''}`}
                    >
                      <span className="font-mono text-sm text-neutral-900 whitespace-nowrap">{c.id}</span>
                      <span className="text-xs text-neutral-500">매출 비중 {c.attrs.revenue_share}%</span>
                      {drop && <span className="text-xs font-medium text-amber-700">수주 급감 신호</span>}
                    </button>
                  </th>
                )
              })}
            </tr>
          </thead>
          <tbody>
            {batches.map(b => {
              const on = isSel(selected, 'batch', b.id)
              return (
                <tr key={b.id}>
                  <th scope="row" className="p-0 align-top font-normal">
                    <button
                      type="button" data-node={`batch:${b.id}`}
                      onClick={() => pick({ kind: 'batch', id: b.id }, on)}
                      className={`block w-full rounded-md border-2 bg-white px-3 py-1.5 text-left hover:bg-neutral-50 ${statusBorder(b.state)} ${on ? RING : ''}`}
                    >
                      <span className="flex items-center justify-between gap-2">
                        <span className="font-mono text-sm text-neutral-900 whitespace-nowrap">{b.id}</span>
                        {b.state && <span className={`inline-flex items-center rounded px-1.5 h-5 text-xs font-medium whitespace-nowrap ${statusColor(b.state)}`}>{b.state}</span>}
                      </span>
                      <span className="block text-xs text-neutral-500">QC {b.attrs.qc_result} · 생산 {b.attrs.produced_date}</span>
                    </button>
                    {used_in.filter(l => l.dst.id === b.id).map(l => {
                      const linkOn = isSel(selected, 'link', l.link_id)
                      return (
                        <button
                          key={l.link_id} type="button" data-link={l.link_id}
                          onClick={() => pick({ kind: 'link', linkId: l.link_id }, linkOn)}
                          className={`mt-0.5 block rounded px-1 text-left text-xs text-neutral-500 hover:bg-neutral-100 ${linkOn ? RING : ''}`}
                        >
                          투입 로트 <span className={`font-mono ${origin.has(l.src.id) ? 'font-semibold text-neutral-900' : ''}`}>{l.src.id}</span>
                        </button>
                      )
                    })}
                  </th>
                  {customers.map(c => {
                    const links = cells.get(`${b.id}|${c.id}`)
                    return (
                      <td key={c.id} className="h-px p-0">
                        {links ? (
                          <div className="flex h-full flex-col gap-1">
                            {links.map(l => {
                              const cs = cellStyle(l.confirm)
                              const linkOn = isSel(selected, 'link', l.link_id)
                              return (
                                <button
                                  key={l.link_id} type="button" data-link={l.link_id}
                                  aria-label={`${b.id} → ${c.id}`}
                                  onClick={() => pick({ kind: 'link', linkId: l.link_id }, linkOn)}
                                  className={`flex min-h-14 w-full flex-1 flex-col items-center justify-center rounded-md border-2 px-1 py-1 text-center tabular-nums hover:brightness-95 ${cs.box} ${linkOn ? RING : ''}`}
                                >
                                  {l.claims.count > 0 && <span className={`text-sm font-semibold ${cs.strong}`}>{l.claims.count}건</span>}
                                  {l.claims.count > 0 && <span className={`text-xs ${cs.strong}`}>{fmtQty(l.claims.qty)}</span>}
                                  <span className={`text-xs ${cs.text}`}>{l.confirm}</span>
                                </button>
                              )
                            })}
                          </div>
                        ) : (
                          <div className="flex h-full min-h-14 items-center justify-center text-neutral-300" aria-label="연결 없음">–</div>
                        )}
                      </td>
                    )
                  })}
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      <ul className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-neutral-500">
        <li className="font-medium">칸 = 배치 → 고객 연결</li>
        {[SOLID, DASHED, FAINT].map(cs => (
          <li key={cs.legend} className="flex items-center gap-1.5">
            <span className={`inline-block h-3.5 w-5 rounded border-2 ${cs.box}`} aria-hidden="true" />{cs.legend}
          </li>
        ))}
        <li>굵은 글자 = 클레임 건수, 수량</li>
        <li>– = 연결 없음</li>
        <li>굵은 로트 ID = 기점 로트에서 투입 (R4)</li>
        <li>주황으로 잠깐 강조 = 방금 바뀐 배치·칸</li>
        <li>누르면 아래에 근거</li>
      </ul>
    </div>
  )
}
