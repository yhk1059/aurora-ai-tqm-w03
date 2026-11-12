import { useState, type ReactNode } from 'react'
import { ApiError } from '../api'
import { useApp } from '../context'
import type { ActionInput, IncidentView, OpenView } from '../types'
import { Button } from './Button'
import { ConfirmDialog } from './ConfirmDialog'
import { ExamplePicker } from './ExamplePicker'

// 액션 입력 폼. 필드는 온톨로지 정의(ontology.actions[action].inputs)에서 만들고,
// 고를 수 있는 후보는 서버의 available_actions[].targets에서 가져온다.
// 화면은 "필수 입력이 비었음"만 미리 막는다. 권한·전제 조건은 서버가 검사하고, 거부 메시지를 폼 안에 그대로 보인다.

type Values = Record<string, unknown>

/** 폼 바깥(AI 버튼 등)이 폼 값을 읽고 채울 때 쓰는 손잡이 */
export type FormApi = { values: Values; setValues: (patch: Values) => void }

/** 필드 위·아래 자리 (AI 초안 블록 등). 입력 key → 그 필드 앞뒤에 넣을 것 */
export type FieldSlots = (f: FormApi) => Record<string, { before?: ReactNode; after?: ReactNode }>

type Props = {
  action: string
  /** 이미 정해진 입력 (예: 이 작업의 task_id). 폼에 읽기 전용으로 보인다 */
  fixed?: Values
  /** 폼 초기값 (예시·AI 초안에서 채울 때) */
  initial?: Values
  onDone?: () => void
  onCancel?: () => void
  /** 폼 안 추가 자리 (다음 step의 "AI로 분류" 버튼 등). 함수면 폼 값을 읽고 채울 수 있다 */
  extra?: ReactNode | ((f: FormApi) => ReactNode)
  /** 확인 창에서 폼 위에 보일 안내 (예: 승인할 수 없는 계획의 이유) */
  before?: ReactNode
  /** 필드 위·아래 자리 */
  slots?: FieldSlots
}

/** 되돌릴 수 없는 결정: 확인 창 안에서 입력을 받는다 (ui-guide.md "버튼") */
const DIALOG_ACTIONS = new Set(['committee_decision', 'plan_decision'])

const inputCls = 'rounded-md bg-white border border-neutral-300 px-3 text-sm focus:border-neutral-900 focus:outline-none'

/** targets에 후보가 없는 id 입력은 사건 뷰의 객체 목록에서 고른다 (ref_type → 목록) */
const REF_LISTS: Record<string, (v: OpenView) => unknown[]> = {
  batch: v => v.batches.map(b => b.id),
  customer: v => v.customers.map(c => c.id),
  claim: v => v.claims.map(c => c.id),
  task: v => v.tasks.map(t => ({ id: t.id, code: t.code, type: t.type })),
  resupply_plan: v => v.plans.map(p => ({ id: p.id, state: p.state })),
}

function isEmpty(v: unknown): boolean {
  return v === undefined || v === null || v === '' || (Array.isArray(v) && v.length === 0)
}

/** targets 항목은 문자열이거나 {id, ...} 객체다. 객체면 짧은 문자·숫자 값을 설명으로 붙인다 */
function option(item: unknown): { id: string; label: string } {
  if (typeof item !== 'object' || item === null) return { id: String(item), label: String(item) }
  const o = item as Record<string, unknown>
  const id = String(o.id)
  const extra = Object.entries(o)
    .filter(([k, v]) => k !== 'id' && (typeof v === 'string' || typeof v === 'number') && String(v).length <= 30)
    .map(([, v]) => String(v))
  return { id, label: [id, ...extra].join(' · ') }
}

/** 서버가 이 액션의 입력 key에 대해 준 후보 ID. 액션이 없으면 null */
export function targetIds(view: IncidentView, action: string, key: string): string[] | null {
  const a = view.available_actions.find(x => x.action === action)
  if (!a) return null
  const list = a.targets[key]
  return Array.isArray(list) ? list.map(i => option(i).id) : []
}

function candidates(view: IncidentView, action: string, def: ActionInput): { id: string; label: string }[] {
  const a = view.available_actions.find(x => x.action === action)
  const list = a?.targets[def.key]
  if (Array.isArray(list)) return list.map(option)
  if (view.incident && def.ref_type && REF_LISTS[def.ref_type]) return REF_LISTS[def.ref_type](view as OpenView).map(option)
  return []
}

/** choice 선택지. choices_from(작업 유형의 허용 결과)이면 고른 작업의 allowed_results */
function choicesOf(view: IncidentView, action: string, def: ActionInput, values: Values): string[] {
  if (def.choices) return def.choices
  if (def.choices_from) {
    const tid = values.task_id
    const fromView = view.incident ? (view as OpenView).tasks.find(t => t.id === tid)?.allowed_results : undefined
    if (fromView) return fromView
    const a = view.available_actions.find(x => x.action === action)
    const item = (a?.targets.task_id as { id: string; allowed_results?: string[] }[] | undefined)?.find(t => t?.id === tid)
    return item?.allowed_results ?? []
  }
  return []
}

/** 폼 상태와 필드·제출을 함께 쥔 훅. 인라인 폼과 확인 창이 같이 쓴다 */
function useActionForm(action: string, fixed: Values, initial: Values, slots?: FieldSlots) {
  const { view, ontology, run } = useApp()
  const defs = ontology.actions[action]?.inputs ?? []
  const defKeys = new Set(defs.map(d => d.key))

  const [values, setValuesState] = useState<Values>(() => {
    const v: Values = {}
    for (const d of defs) {
      if (d.type === 'date' && d.key === 'applied_date' && view.incident) v[d.key] = view.incident.current_date
      if (d.type === 'id_list') v[d.key] = candidates(view, action, d).map(o => o.id)
      if (d.type === 'id') {
        const c = candidates(view, action, d)
        if (c.length === 1) v[d.key] = c[0].id
      }
    }
    return { ...v, ...initial, ...fixed }
  })
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const setValues = (patch: Values) => {
    const p = { ...patch }
    for (const k of Object.keys(fixed)) delete p[k]
    setValuesState(prev => ({ ...prev, ...p }))
  }
  const set = (key: string, v: unknown) => setValues({ [key]: v })

  const missing = defs.filter(d => d.required && isEmpty(values[d.key]))
  // 정의 밖 입력(예시의 source_ref 등)은 그대로 함께 보낸다. 서버가 받을지 정한다
  const extras = Object.entries(values).filter(([k, v]) => !defKeys.has(k) && !isEmpty(v))

  async function submit(): Promise<boolean> {
    const payload: Values = Object.fromEntries(extras)
    for (const d of defs) {
      const v = values[d.key]
      if (isEmpty(v)) continue
      payload[d.key] = d.type === 'int' ? Number(v) : v
    }
    setBusy(true)
    setError(null)
    try {
      await run(action, payload)
      return true
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e))
      return false
    } finally {
      setBusy(false)
    }
  }

  // 예시 필터: apply_reply면 그 작업의 유형과 대상 고객
  const task = view.incident ? (view as OpenView).tasks.find(t => t.id === values.task_id) : undefined
  const customerIds = task
    ? task.targets.flatMap(t => (t.type === 'customer' ? [t.id] : t.customer_id ? [t.customer_id] : []))
    : []

  function field(d: ActionInput): ReactNode {
    const v = values[d.key]
    if (d.key in fixed) {
      return <span className="font-mono text-sm text-neutral-900">{String(v)}</span>
    }
    switch (d.type) {
      case 'date':
        return <input type="date" value={(v as string) ?? ''} onChange={e => set(d.key, e.target.value)} className={`${inputCls} h-9 tabular-nums`} />
      case 'text':
        return <textarea value={(v as string) ?? ''} onChange={e => set(d.key, e.target.value)} rows={3} className={`${inputCls} w-full py-2 leading-relaxed`} />
      case 'int':
        return <input type="number" min={1} step={1} value={(v as string | number) ?? ''} onChange={e => set(d.key, e.target.value)} className={`${inputCls} h-9 w-40 tabular-nums`} />
      case 'choice': {
        const cs = choicesOf(view, action, d, values)
        return (
          <select value={(v as string) ?? ''} onChange={e => set(d.key, e.target.value)} className={`${inputCls} h-9`}>
            <option value="">선택</option>
            {cs.map(c => <option key={c} value={c}>{c}</option>)}
          </select>
        )
      }
      case 'id': {
        const cs = candidates(view, action, d)
        return (
          <select value={(v as string) ?? ''} onChange={e => set(d.key, e.target.value)} className={`${inputCls} h-9 font-mono`}>
            <option value="">선택</option>
            {cs.map(c => <option key={c.id} value={c.id}>{c.label}</option>)}
          </select>
        )
      }
      case 'id_list': {
        const cs = candidates(view, action, d)
        const sel = new Set((v as string[]) ?? [])
        return (
          <div className="flex flex-wrap gap-x-4 gap-y-1">
            {cs.map(c => (
              <label key={c.id} className="inline-flex items-center gap-1.5 text-sm font-mono text-neutral-900">
                <input
                  type="checkbox"
                  checked={sel.has(c.id)}
                  onChange={e => set(d.key, cs.map(o => o.id).filter(id => (id === c.id ? e.target.checked : sel.has(id))))}
                />
                {c.label}
              </label>
            ))}
            {cs.length === 0 && <span className="text-sm text-neutral-500">후보 없음</span>}
          </div>
        )
      }
      default:
        return <input value={(v as string) ?? ''} onChange={e => set(d.key, e.target.value)} className={`${inputCls} h-9`} />
    }
  }

  const api: FormApi = { values, setValues }
  const around = slots?.(api) ?? {}

  const body = (
    <div className="space-y-3">
      <ExamplePicker
        action={action}
        taskType={task?.type ?? null}
        customerIds={customerIds}
        onPick={inputs => setValues(inputs)}
      />
      {defs.map(d => (
        <div key={d.key} className="space-y-1">
          <div className="text-xs text-neutral-500">
            {d.name}
            {d.required && !(d.key in fixed) && <span className="text-neutral-400"> · 필수</span>}
            {d.description && <span className="block text-neutral-400">{d.description}</span>}
          </div>
          {around[d.key]?.before}
          {field(d)}
          {around[d.key]?.after}
        </div>
      ))}
      {extras.length > 0 && (
        <div className="text-xs text-neutral-500">
          추가 입력: {extras.map(([k, v]) => <span key={k} className="font-mono break-all"> {k} = {String(v)}</span>)}
        </div>
      )}
      {error && (
        <div role="alert" className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>
      )}
    </div>
  )

  return { body, submit, busy, canSubmit: missing.length === 0, api }
}

/** 인라인 폼 (작업 회신, 클레임 판정, 새 입력 등) */
export function ActionForm({ action, fixed = {}, initial = {}, onDone, onCancel, extra, slots }: Props) {
  const { ontology } = useApp()
  const f = useActionForm(action, fixed, initial, slots)
  return (
    <div className="space-y-3">
      {f.body}
      {typeof extra === 'function' ? extra(f.api) : extra}
      <div className="flex gap-2">
        <Button variant="primary" disabled={f.busy || !f.canSubmit} onClick={async () => { if (await f.submit()) onDone?.() }}>
          {f.busy ? '실행 중…' : `${ontology.actions[action]?.name ?? action} 실행`}
        </Button>
        {onCancel && <Button variant="text" onClick={onCancel} disabled={f.busy}>취소</Button>}
      </div>
    </div>
  )
}

/** 확인 창 안의 폼 (위원회·SCM 결정). 실패하면 창을 닫지 않고 서버 메시지를 보인다 */
export function ActionDialog({ action, fixed = {}, initial = {}, onDone, onCancel, extra, before, slots }: Props) {
  const { ontology } = useApp()
  const f = useActionForm(action, fixed, initial, slots)
  return (
    <ConfirmDialog
      open
      title={ontology.actions[action]?.name ?? action}
      confirmLabel="결정 실행"
      busy={f.busy}
      confirmDisabled={!f.canSubmit}
      onConfirm={async () => { if (await f.submit()) onDone?.() }}
      onCancel={() => onCancel?.()}
    >
      {before}
      {f.body}
      {typeof extra === 'function' ? extra(f.api) : extra}
      <p className="text-xs text-neutral-500">결정은 되돌릴 수 없습니다. 결과와 사유가 결정 기록에 남습니다.</p>
    </ConfirmDialog>
  )
}

export type ActionItem = {
  action: string
  label?: string
  fixed?: Values
  initial?: Values
  extra?: Props['extra']
  slots?: FieldSlots
}

/** 액션 버튼 줄. available_actions에 있는 액션만 버튼을 그리고, 누르면 폼(또는 확인 창)이 열린다 */
export function ActionBar({ title, items }: { title?: string; items: ActionItem[] }) {
  const { view } = useApp()
  const [open, setOpen] = useState<number | null>(null)
  const shown = items
    .map((it, i) => ({ it, i, a: view.available_actions.find(a => a.action === it.action) }))
    .filter(x => x.a)
  if (shown.length === 0) return null
  const cur = shown.find(x => x.i === open)
  const close = () => setOpen(null)

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        {title && <span className="w-16 text-xs font-medium text-neutral-500">{title}</span>}
        {shown.map(({ it, i, a }) => (
          <Button key={i} variant="secondary" onClick={() => setOpen(o => (o === i ? null : i))}
            className={open === i ? 'bg-neutral-100' : ''}>
            {it.label ?? a!.label}
          </Button>
        ))}
      </div>
      {cur && (DIALOG_ACTIONS.has(cur.it.action) ? (
        <ActionDialog key={cur.i} action={cur.it.action} fixed={cur.it.fixed} initial={cur.it.initial}
          extra={cur.it.extra} slots={cur.it.slots} onDone={close} onCancel={close} />
      ) : (
        <div className="rounded-md border border-neutral-200 p-3">
          <ActionForm key={cur.i} action={cur.it.action} fixed={cur.it.fixed} initial={cur.it.initial}
            extra={cur.it.extra} slots={cur.it.slots} onDone={close} onCancel={close} />
        </div>
      ))}
    </div>
  )
}
