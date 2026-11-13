import { ChevronDown, ChevronRight } from 'lucide-react'
import { useState } from 'react'
import type { Change, ChangeTarget, LastChange as LastChangeT, Ontology } from '../types'
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
      {c.rule && <span className="ml-1.5 font-mono text-[11px] text-neutral-400">{c.rule}</span>}
    </li>
  )
}

/** 요약에 올리는 변경: 객체(관계 아님)의 상태 변화. 나머지는 "자세히" 안에 둔다 */
const KEY_LIMIT = 4

export function LastChange({ change, ontology }: { change: LastChangeT; ontology: Ontology }) {
  const [open, setOpen] = useState(false)
  const key = change.changes.filter(c => c.target.type !== 'link' && c.field === 'state' && c.before != null)
  const Chevron = open ? ChevronDown : ChevronRight
  return (
    <Card title="방금 바뀐 것">
      <div>
        <div className="text-base font-medium text-neutral-900">
          {actorName(ontology, change.actor)} · {actionName(ontology, change.action)}
        </div>
        <div className="text-xs tabular-nums text-neutral-500">{fmtDate(change.applied_date)}</div>
      </div>
      {change.changes.length === 0 ? (
        <p className="text-sm text-neutral-500">상태 변화 없음</p>
      ) : (
        <>
          {key.length > 0 && (
            <ul className="space-y-1">
              {key.slice(0, KEY_LIMIT).map((c, i) => (
                <li key={i} className="text-sm">
                  <span className="font-mono text-neutral-900">{targetLabel(ontology, c.target)}</span>{' '}
                  <span className="text-neutral-500">{value(c.before)}</span>
                  <span className="text-neutral-400"> → </span>
                  <span className="font-medium text-neutral-900">{value(c.after)}</span>
                </li>
              ))}
              {key.length > KEY_LIMIT && <li className="text-xs text-neutral-500">외 상태 변화 {key.length - KEY_LIMIT}건</li>}
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
                    {s.rule && <span className="ml-1.5 font-mono text-[11px] text-neutral-400">{s.rule}</span>}
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
