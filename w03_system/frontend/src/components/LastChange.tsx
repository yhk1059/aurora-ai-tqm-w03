import { ChevronDown, ChevronRight } from 'lucide-react'
import { useState } from 'react'
import { useApp } from '../context'
import type { Change, ChangeTarget, LastChange as LastChangeT, Ontology, OpenView } from '../types'
import { fmtDate } from '../format'
import { Card } from './Card'

// 방금 바뀐 것 (ui-guide.md 원칙 3): 사람 액션 1단계 + 이어진 자동 처리 단계의 이전 → 이후와 적용 규칙.
const FIELD_NAMES: Record<string, string> = { state: '상태', created: '생성', confirm: '확인 수준' }

export function actionName(ontology: Ontology, action: string): string {
  return ontology.actions[action]?.name ?? action
}

export function actorName(ontology: Ontology, actor: string): string {
  return ontology.roles[actor]?.name ?? actor
}

function targetLabel(ontology: Ontology, t: ChangeTarget): string {
  if (t.type === 'link') {
    const rel = t.rel ?? '관계'
    return t.src && t.dst ? `${rel} ${t.src[1]} → ${t.dst[1]}` : `${rel} #${t.id}`
  }
  return `${ontology.object_types[t.type]?.name ?? t.type} ${t.id}`
}

function fieldName(ontology: Ontology, t: ChangeTarget, field: string): string {
  const stored = ontology.object_types[t.type]?.stored.find(a => a.key === field)?.name
  const link = t.type === 'link' ? ontology.link_attributes.find(a => a.key === field)?.name : undefined
  return stored ?? link ?? FIELD_NAMES[field] ?? field
}

function value(v: unknown): string {
  if (v === null || v === undefined) return '—'
  if (typeof v === 'object') return JSON.stringify(v)
  return String(v)
}

export function ChangeRow({ ontology, c }: { ontology: Ontology; c: Change }) {
  return (
    <li className="text-sm leading-relaxed">
      <span className="font-mono text-neutral-900">{targetLabel(ontology, c.target)}</span>
      <span className="text-neutral-500"> · {fieldName(ontology, c.target, c.field)} · </span>
      <span className="text-neutral-500">{value(c.before)}</span>
      <span className="text-neutral-400"> → </span>
      <span className="text-neutral-900">{value(c.after)}</span>
      {c.rule && <span className="ml-1.5 font-mono text-[11px] text-neutral-500">{c.rule}</span>}
    </li>
  )
}

/** 요약 한 줄: 무엇이(kind + ids) 어떻게(before → after, 또는 새로 생김) */
type SummaryLine = { kind: string; ids: string[]; before: string | null; after: string }

/** 요약에 올리는 것 (ui-guide.md v5): 결과만 적는다.
 *  ① 객체의 상태 변화와 출하처 확인 수준 변화. 같은 대상의 연속 변화는 처음 → 끝으로 합치고, 같은 변화를 겪은 대상은 한 줄로 묶는다
 *  ② 새로 생긴 작업과 재공급 계획. 나머지(관계 생성, 속성 값)는 "자세히" 안에 둔다 */
function summarize(change: LastChangeT, ontology: Ontology, view: OpenView): SummaryLine[] {
  const chains = new Map<string, { kind: string; id: string; before: string; after: string }>()
  for (const c of change.changes) {
    if (c.before == null) continue
    const isState = c.target.type !== 'link' && c.field === 'state'
    const shipped = c.target.type === 'link' && c.field === 'confirm'
      ? view.network.shipped_to.find(l => String(l.link_id) === String(c.target.id))
      : undefined
    if (!isState && !shipped) continue
    const key = `${c.target.type}:${c.target.id}`
    const prev = chains.get(key)
    if (prev) prev.after = value(c.after)
    else chains.set(key, {
      kind: shipped ? '출하처' : ontology.object_types[c.target.type]?.name ?? c.target.type,
      id: shipped ? `${shipped.src.id} → ${shipped.dst.id}` : String(c.target.id),
      before: value(c.before),
      after: value(c.after),
    })
  }
  const lines = new Map<string, SummaryLine>()
  for (const x of chains.values()) {
    if (x.before === x.after) continue
    const key = `${x.kind}|${x.before}|${x.after}`
    const line = lines.get(key)
    if (line) line.ids.push(x.id)
    else lines.set(key, { kind: x.kind, ids: [x.id], before: x.before, after: x.after })
  }
  const created = (type: string) => change.changes.filter(c => c.target.type === type && c.field === 'created')
  const out = [...lines.values()]
  const tasks = created('task')
  if (tasks.length > 0) {
    // 유형별 개수: "수주 급감 확인 2"
    const types = new Map<string, number>()
    for (const c of tasks) {
      const type = view.tasks.find(t => t.id === c.target.id)?.type ?? String(c.target.id)
      types.set(type, (types.get(type) ?? 0) + 1)
    }
    out.push({ kind: `새 작업 ${tasks.length}건`, ids: [], before: null, after: [...types].map(([t, n]) => (n > 1 ? `${t} ${n}` : t)).join(', ') })
  }
  for (const c of created('resupply_plan')) {
    out.push({ kind: `새 ${ontology.object_types.resupply_plan?.name ?? '재공급 계획'}`, ids: [String(c.target.id)], before: null, after: value(c.after) })
  }
  return out
}

export function LastChange({ change, ontology }: { change: LastChangeT; ontology: Ontology }) {
  const { view } = useApp()
  const [open, setOpen] = useState(false)
  const key = view.incident ? summarize(change, ontology, view as OpenView) : []
  // 결정·회신은 고른 결과가 곧 바뀐 내용이다 (승인, 출하 확인 등)
  const result = typeof change.inputs.result === 'string' ? change.inputs.result : null
  const Chevron = open ? ChevronDown : ChevronRight
  return (
    <Card title="방금 바뀐 것">
      <div>
        <div className="text-base font-medium text-neutral-900">
          {actorName(ontology, change.actor)} · {actionName(ontology, change.action)}{result && ` · ${result}`}
        </div>
        <div className="text-xs tabular-nums text-neutral-500">{fmtDate(change.applied_date)}</div>
      </div>
      {change.changes.length === 0 ? (
        <p className="text-sm text-neutral-500">상태 변화 없음</p>
      ) : (
        <>
          {key.length === 0 ? (
            <p className="text-sm text-neutral-500">판정·작업·계획의 상태는 그대로입니다 (기록만 남음)</p>
          ) : (
            <ul className="space-y-1">
              {key.map((l, i) => (
                <li key={i} className="text-sm leading-relaxed">
                  <span className="text-neutral-700">{l.kind}</span>{' '}
                  {l.ids.length > 0 && <span className="font-mono text-neutral-900">{l.ids.join(', ')}</span>}{' '}
                  {l.before !== null && <><span className="text-neutral-500">{l.before}</span><span className="text-neutral-400"> → </span></>}
                  <span className="font-medium text-neutral-900">{l.after}</span>
                </li>
              ))}
            </ul>
          )}
          <button
            type="button"
            aria-expanded={open}
            onClick={() => setOpen(o => !o)}
            className="inline-flex items-center gap-1 text-xs text-neutral-500 hover:text-neutral-900"
          >
            <Chevron size={16} strokeWidth={1.5} />
            변경 {change.changes.length}건과 적용 규칙 {open ? '접기' : '자세히'}
          </button>
          {open && (
            <ol className="space-y-3">
          {change.steps.filter(s => s.changes.length > 0).map(s => (
            <li key={s.seq} className="space-y-1">
              <div className="text-xs text-neutral-500">
                <span className="tabular-nums">#{s.seq}</span>{' '}
                {s.seq === change.seq ? (
                  actionName(ontology, s.action)
                ) : (
                  <>
                    <span className="inline-flex items-center rounded px-1.5 h-5 border border-neutral-300 text-[11px] text-neutral-600 mr-1">자동</span>
                    {actionName(ontology, s.action)}
                    {s.rule && <span className="ml-1.5 font-mono text-[11px] text-neutral-500">{s.rule}</span>}
                    {s.reason && <span className="block text-neutral-500">{s.reason}</span>}
                  </>
                )}
              </div>
              <ul className="space-y-0.5 pl-3 border-l border-neutral-200">
                {s.changes.map((c, j) => <ChangeRow key={j} ontology={ontology} c={c} />)}
              </ul>
            </li>
          ))}
            </ol>
          )}
        </>
      )}
    </Card>
  )
}
