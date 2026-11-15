import { Controls, Handle, Position, ReactFlow, type Edge, type Node, type NodeProps } from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { useEffect, useMemo, useState } from 'react'
import { fmtQty } from '../format'
import type { IncidentView, OpenView } from '../types'
import { statusBorder, statusColor } from './StatusBadge'

// 연결망 (ui-guide.md "연결망"): 원료 로트 → 배치 → 고객 3열 고정. 연결망 탭 너비에 맞춘 간격이다. 읽기 화면이라 액션은 없다.
// 노드·선은 서버의 lots / batches / customers / network.used_in / network.shipped_to에 있는 것만 그린다.

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
/** 출하처 확인이 끝나지 않은 고객 ID (선의 확인 수준에서 센다) */
export function unconfirmedCustomers(v: OpenView): string[] {
  return [...new Set(v.network.shipped_to.filter(l => UNCONFIRMED.includes(l.confirm)).map(l => l.dst.id))].sort()
}

// --- 확인 수준 → 선 모양 (이 파일 한 곳) -----------------------------------
type LineStyle = { dash?: string; stroke: string; legend: string }
const SOLID: LineStyle = { stroke: '#525252', legend: '실선 = 확인·회신확인' }
const DASHED: LineStyle = { dash: '6 4', stroke: '#b45309', legend: '점선 = 미확인·확인요청중' }
const FAINT: LineStyle = { stroke: '#d4d4d4', legend: '옅은 회색 = 영향없음 (확인했더니 아님, 선은 남김)' }
const LINE_BY_CONFIRM: Record<string, LineStyle> = {
  '확인': SOLID, '회신확인': SOLID,
  '미확인': DASHED, '확인요청중': DASHED,
  '영향없음': FAINT,
}
function lineStyle(confirm: string): LineStyle {
  return LINE_BY_CONFIRM[confirm] ?? DASHED
}

// --- 방금 바뀐 것 강조 (ui-guide.md "애니메이션") ------------------------------
// React Flow는 노드·선 값이 바뀌면 선을 다시 그려서 CSS transition이 끊긴다. 그래서 노드·선 값은 그대로 두고,
// 바뀐 것만 고르는 규칙을 <style>로 잠깐 얹어 index.css의 keyframes(net-node-flash, net-edge-flash)를 한 번 돌린다.
const FLASH_MS = 1400
const NONE: ReadonlySet<string> = new Set()

function flashCss(keys: ReadonlySet<string>): string {
  const anim = (name: string) => `{animation:${name} ${FLASH_MS}ms ease-out}`
  return [...keys].map(k => {
    const id = `[data-id="${CSS.escape(k)}"]`
    if (k.startsWith('link:')) return `[data-network] .react-flow__edge${id} .react-flow__edge-path${anim('net-edge-flash')}`
    if (k.startsWith('batch:')) return `[data-network] .react-flow__node${id} > div${anim('net-node-flash')}`
    return ''
  }).join('')
}

/** 기록 번호 since 뒤에 바뀐 노드·선의 키 (`batch:ID`, `link:번호`). 새 클레임은 그 배치 → 고객 선(라벨이 바뀐다)으로 옮긴다 */
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

// --- 고정 배치 ----------------------------------------------------------------
const COL_X = { lot: 0, batch: 320, customer: 900 }
const NODE_W = 215
const ROW_H = 84
const PAD = 24

type NodeData = {
  kind: 'lot' | 'batch' | 'customer'
  id: string
  /** 상태 글자 (배지) */
  state: string | null
  /** 보조 줄 */
  sub: string[]
  /** 주황 표시할 글자 (수주 급감 신호, 기점 로트) */
  flag: string | null
  border: string
  selected: boolean
}
type EntityNode = Node<NodeData, 'entity'>

function EntityNodeView({ data }: NodeProps<EntityNode>) {
  return (
    <div
      className={`rounded-md bg-white border-2 px-3 py-2 text-left ${data.border} ${data.selected ? 'ring-2 ring-indigo-600' : ''}`}
      style={{ width: NODE_W }}
    >
      {data.kind !== 'lot' && <Handle type="target" position={Position.Left} isConnectable={false} className="!opacity-0" />}
      <div className="flex items-center justify-between gap-2">
        <span className="font-mono text-sm text-neutral-900 whitespace-nowrap">{data.id}</span>
        {data.state && (
          <span className={`inline-flex items-center rounded px-1.5 h-5 text-[11px] font-medium whitespace-nowrap ${statusColor(data.state)}`}>
            {data.state}
          </span>
        )}
      </div>
      {data.sub.map(s => <div key={s} className="text-xs text-neutral-500">{s}</div>)}
      {data.flag && <div className="text-xs font-medium text-amber-700">{data.flag}</div>}
      {data.kind !== 'customer' && <Handle type="source" position={Position.Right} isConnectable={false} className="!opacity-0" />}
    </div>
  )
}

const nodeTypes = { entity: EntityNodeView }

function isSel(sel: Selection | null, kind: Selection['kind'], key: string | number): boolean {
  if (!sel || sel.kind !== kind) return false
  return sel.kind === 'link' ? sel.linkId === key : sel.id === key
}

/** 한 열의 노드 y 좌표: 가장 긴 열 기준으로 가운데 정렬 */
function colY(i: number, n: number, maxN: number): number {
  return PAD + ((maxN - n) * ROW_H) / 2 + i * ROW_H
}

/** 서버 뷰 → React Flow 노드·선. 뷰와 고른 것이 같으면 같은 값을 다시 쓴다 (값이 바뀌면 React Flow가 선을 다시 그린다) */
function build(v: OpenView, selected: Selection | null): { nodes: EntityNode[]; edges: Edge[]; height: number } {
  const origin = new Set(v.incident.origin_lots)
  const { used_in, shipped_to } = v.network

  // 로트 열: 기점 로트 + 사건 배치에 투입된 로트 (서버 lots 중에서만)
  const usedLots = new Set(used_in.map(l => l.src.id))
  const lots = v.lots.filter(l => origin.has(l.id) || usedLots.has(l.id)).sort((a, b) => a.id.localeCompare(b.id))
  const batches = [...v.batches].sort((a, b) => a.id.localeCompare(b.id))
  const customers = [...v.customers].sort((a, b) => a.id.localeCompare(b.id))
  const maxN = Math.max(lots.length, batches.length, customers.length, 1)

  const nodes: EntityNode[] = []
  lots.forEach((l, i) => {
    const insp = (l.attrs.inspection_result as string | undefined) ?? null
    nodes.push({
      id: `lot:${l.id}`, type: 'entity', position: { x: COL_X.lot, y: colY(i, lots.length, maxN) },
      data: {
        kind: 'lot', id: l.id, state: insp,
        sub: [`원료 ${String(l.attrs.material ?? '—')} · 입고검사 ${insp ?? '—'}`],
        flag: origin.has(l.id) ? '기점 로트' : null,
        border: statusBorder(insp), selected: isSel(selected, 'lot', l.id),
      },
    })
  })
  batches.forEach((b, i) => {
    nodes.push({
      id: `batch:${b.id}`, type: 'entity', position: { x: COL_X.batch, y: colY(i, batches.length, maxN) },
      data: {
        kind: 'batch', id: b.id, state: b.state,
        sub: [`QC ${b.attrs.qc_result} · 생산 ${b.attrs.produced_date}`],
        flag: null, border: statusBorder(b.state), selected: isSel(selected, 'batch', b.id),
      },
    })
  })
  customers.forEach((c, i) => {
    const drop = c.order_drop_signal.signal
    nodes.push({
      id: `customer:${c.id}`, type: 'entity', position: { x: COL_X.customer, y: colY(i, customers.length, maxN) },
      data: {
        kind: 'customer', id: c.id, state: null,
        sub: [`매출 비중 ${c.attrs.revenue_share}%`],
        flag: drop ? '수주 급감 신호' : null,
        border: drop ? 'border-amber-200' : 'border-neutral-200',
        selected: isSel(selected, 'customer', c.id),
      },
    })
  })

  const edges: Edge[] = []
  for (const l of used_in) {
    const fromOrigin = origin.has(l.src.id)
    const sel = isSel(selected, 'link', l.link_id)
    edges.push({
      id: `link:${l.link_id}`, source: `lot:${l.src.id}`, target: `batch:${l.dst.id}`,
      style: { stroke: fromOrigin ? '#171717' : '#a3a3a3', strokeWidth: (fromOrigin ? 2 : 1) + (sel ? 1.5 : 0) },
    })
  }
  for (const l of shipped_to) {
    const ls = lineStyle(l.confirm)
    const sel = isSel(selected, 'link', l.link_id)
    const label = l.claims.count > 0 ? `${l.claims.count}건, ${fmtQty(l.claims.qty)}` : undefined
    edges.push({
      id: `link:${l.link_id}`, source: `batch:${l.src.id}`, target: `customer:${l.dst.id}`,
      style: { stroke: ls.stroke, strokeWidth: sel ? 3 : 1.5, strokeDasharray: ls.dash },
      label, labelStyle: { fontSize: 11, fill: '#404040' }, labelBgStyle: { fill: '#ffffff', fillOpacity: 0.9 },
    })
  }

  const height = PAD * 2 + maxN * ROW_H
  return { nodes, edges, height }
}

export function Network({ view: v, onSelect, selected, seen }: Props) {
  // 탭을 열 때(그리고 열려 있는 동안 뷰가 바뀔 때) 마지막으로 본 뒤 바뀐 배치·선을 한 번 강조한다.
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
  const { nodes, edges, height } = useMemo(() => build(v, selected), [v, selected])

  function clickNode(_: unknown, n: Node) {
    const [kind, ...rest] = n.id.split(':')
    onSelect({ kind: kind as 'lot' | 'batch' | 'customer', id: rest.join(':') })
  }
  function clickEdge(_: unknown, e: Edge) {
    onSelect({ kind: 'link', linkId: Number(e.id.slice('link:'.length)) })
  }

  return (
    <div className="space-y-2" data-network>
      {lit.size > 0 && <style>{flashCss(lit)}</style>}
      <div className="rounded-md border border-neutral-200" style={{ height }}>
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          onNodeClick={clickNode}
          onEdgeClick={clickEdge}
          onPaneClick={() => onSelect(null)}
          fitView
          fitViewOptions={{ padding: 0.05 }}
          minZoom={0.3}
          maxZoom={2}
          nodesDraggable={false}
          nodesConnectable={false}
          nodesFocusable={false}
          edgesFocusable={false}
          edgesReconnectable={false}
          elementsSelectable={false}
          selectionOnDrag={false}
          selectionKeyCode={null}
          multiSelectionKeyCode={null}
          deleteKeyCode={null}
          connectOnClick={false}
          zoomOnDoubleClick={false}
          preventScrolling={false}
          zoomOnScroll={false}
        >
          <Controls showInteractive={false} />
        </ReactFlow>
      </div>
      <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-neutral-500">
        <li>배치 → 고객 선: {SOLID.legend}</li>
        <li>{DASHED.legend}</li>
        <li>{FAINT.legend}</li>
        <li>선 위 글자 = 클레임 건수, 수량</li>
        <li>로트 → 배치 굵은 선 = 기점 로트에서 투입 (R4)</li>
        <li>노드 테두리 = 상태 색 · 누르면 아래에 근거</li>
        <li>주황으로 잠깐 강조 = 방금 바뀐 배치·선</li>
      </ul>
    </div>
  )
}
