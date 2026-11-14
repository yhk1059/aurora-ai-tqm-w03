import { useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
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

/** 폼 바깥(AI 버튼 등)이 폼 값을 읽고 채울 때 쓰는 손잡이. submit은 폼의 실행 버튼과 같다 (성공하면 폼을 닫는다) */
export type FormApi = {
  values: Values
  setValues: (patch: Values) => void
  submit: () => Promise<void>
  busy: boolean
  error: string | null
}

/** 필드 위·아래 자리 (AI 초안 블록 등). 입력 key → 그 필드 앞뒤에 넣을 것. replace가 있으면 기본 입력 칸 대신 그린다 */
export type FieldSlots = (f: FormApi) => Record<string, { before?: ReactNode; after?: ReactNode; replace?: ReactNode }>

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
  /** 머리 띠가 있는 폼 박스 안에 그릴 때: 입력은 안쪽 여백을 두고, 실행 줄은 박스 아래 띠로 그린다 (ui-guide.md v10) */
  framed?: boolean
  /** 실행 줄 왼쪽에 적는 "실행하면 생기는 일". framed일 때만 보인다 */
  outcome?: (f: FormApi) => ReactNode
  /** 확인 창(ActionDialog) 전용: 결과 이름 → 근거가 비었을 때 보일 안내 문구. 거절(A-09)은 기본으로 들어 있다 */
  reasonRequired?: Partial<Record<string, string>>
}

/** 근거(사유)가 필수인 결과. 거절은 사유 필수다 (A-09) */
const REASON_REQUIRED_DEFAULT: Partial<Record<string, string>> = { 거절: '거절은 사유를 적어야 실행할 수 있습니다.' }

/** 되돌릴 수 없는 결정: 확인 창 안에서 입력을 받는다 (ui-guide.md "버튼") */
const DIALOG_ACTIONS = new Set(['committee_decision', 'plan_decision'])

const inputCls = 'rounded-md bg-white border border-neutral-300 px-3 text-sm focus:border-indigo-600 focus:outline-none'

/** targets에 후보가 없는 id 입력은 사건 뷰의 객체 목록에서 고른다 (ref_type → 목록) */
const REF_LISTS: Record<string, (v: OpenView) => unknown[]> = {
  batch: v => v.batches.map(b => b.id),
  customer: v => v.customers.map(c => c.id),
  claim: v => v.claims.map(c => c.id),
  task: v => v.tasks.map(t => ({ id: t.id, code: t.code, type: t.type })),
  resupply_plan: v => v.plans.map(p => ({ id: p.id, state: p.state })),
}

/** 설명 끝의 가정 ID "(A-09)"는 글에서 빼고 툴팁으로 돌린다. 정의 그대로는 온톨로지 탭에서 본다 */
function splitRef(desc: string): [text: string, ref: string | undefined] {
  const m = desc.match(/^(.*?)\s*\((A-\d+)\)\s*$/)
  return m ? [m[1], `가정 ${m[2]}`] : [desc, undefined]
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
function useActionForm(action: string, fixed: Values, initial: Values, onDone?: () => void, slots?: FieldSlots, dialog = false) {
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
        return <input type="date" aria-label={d.name} value={(v as string) ?? ''} onChange={e => set(d.key, e.target.value)} className={`${inputCls} h-9 tabular-nums`} />
      case 'text':
        return <textarea value={(v as string) ?? ''} onChange={e => set(d.key, e.target.value)} rows={3} className={`${inputCls} w-full py-2 leading-relaxed`} />
      case 'int':
        return <input type="number" min={1} step={1} value={(v as string | number) ?? ''} onChange={e => set(d.key, e.target.value)} className={`${inputCls} h-9 w-40 tabular-nums`} />
      case 'choice': {
        const cs = choicesOf(view, action, d, values)
        // 되돌릴 수 없는 결정의 결과는 큰 선택 버튼으로 고른다 (ui-guide.md v2)
        if (DIALOG_ACTIONS.has(action) && d.choices) {
          return (
            <div className="flex gap-2">
              {cs.map(c => (
                <button
                  key={c}
                  type="button"
                  aria-pressed={v === c}
                  onClick={() => set(d.key, c)}
                  className={`flex-1 flex flex-col justify-start rounded-md border px-3 py-2.5 text-left ${v === c
                    ? 'border-indigo-600 bg-indigo-50 text-indigo-950 ring-1 ring-indigo-600'
                    : 'border-neutral-300 bg-white text-neutral-900 hover:bg-neutral-50'}`}
                >
                  <span className="block text-sm font-semibold">{c}</span>
                  {/* 고르면 일어나는 일 (정의의 choice_effects) */}
                  {d.choice_effects?.[c] && (
                    <span className={`mt-1 block text-xs leading-relaxed ${v === c ? 'text-indigo-900' : 'text-neutral-600'}`}>
                      {d.choice_effects[c]}
                    </span>
                  )}
                </button>
              ))}
            </div>
          )
        }
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
                  className="accent-indigo-600"
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

  const api: FormApi = { values, setValues, submit: async () => { if (await submit()) onDone?.() }, busy, error }
  const around = slots?.(api) ?? {}

  const examples = (
    <ExamplePicker
      action={action}
      taskType={task?.type ?? null}
      customerIds={customerIds}
      onPick={inputs => setValues(inputs)}
    />
  )
  // 적용일은 기본값(사건의 현재 날짜)을 그대로 쓰는 일이 많아 폼 맨 아래 한 줄로 내린다. 설명은 툴팁 (ui-guide.md v5)
  const dateDef = defs.find(d => d.key === 'applied_date' && d.type === 'date' && !(d.key in fixed))
  const aiLogId = extras.find(([k]) => k === 'ai_log_id')?.[1]
  // 인라인 폼에서는 실행 버튼과 같은 줄에 둔다 (ui-guide.md v7). 결정 창에서는 입력 아래 한 줄이다
  const dateRow = dateDef && (
    <div className="flex items-center gap-2 text-xs text-neutral-600" title={dateDef.description}>
      {dateDef.name}
      {field(dateDef)}
    </div>
  )
  function fieldBlock(d: ActionInput): ReactNode {
    const [desc, ref] = d.description ? splitRef(d.description) : []
    return (
      <div key={d.key} className="space-y-1">
        <div className="text-xs text-neutral-500">
          {d.name}
          {d.required && !(d.key in fixed) && <span className="text-neutral-500"> · 필수</span>}
          {/* 인라인 폼에서는 이름 옆에 잇는다 (줄 수를 줄인다). 결정 창에서는 아래 줄 */}
          {desc && <span className={dialog ? 'block text-neutral-500' : 'text-neutral-500'} title={ref}>{dialog ? desc : ` · ${desc}`}</span>}
        </div>
        {around[d.key]?.before}
        {around[d.key]?.replace ?? field(d)}
        {around[d.key]?.after}
      </div>
    )
  }
  // 인라인 폼에서 짧은 입력(선택·숫자·날짜·고정 값)이 이어지면 한 줄에 나란히 둔다 (ui-guide.md v7). 글·체크 목록·AI 자리가 붙은 입력은 줄을 다 쓴다
  const isShort = (d: ActionInput) => !dialog && !around[d.key] && (d.key in fixed || ['id', 'int', 'date', 'choice'].includes(d.type))
  const rows: ActionInput[][] = []
  for (const d of defs) {
    if (d === dateDef) continue
    const last = rows[rows.length - 1]
    if (last && isShort(d) && isShort(last[0])) last.push(d)
    else rows.push([d])
  }
  // 결정 창에서는 근거와 입력이 먼저 보이도록 예시를 입력 아래에 둔다 (ui-guide.md v4)
  const body = (
    <div className="space-y-3">
      {!dialog && examples}
      {rows.map(row => (row.length === 1 ? fieldBlock(row[0]) : (
        <div key={row[0].key} className="flex flex-wrap items-start gap-x-4 gap-y-3">{row.map(fieldBlock)}</div>
      )))}
      {dialog && examples}
      {dialog && dateRow}
      {/* 정의 밖 입력(예시의 source_ref 등)은 함께 보내지만 화면에는 내부 이름을 쓰지 않는다 */}
      {aiLogId != null && (
        <div className="text-xs text-neutral-500">AI 기록 #{String(aiLogId)}의 초안을 사용함 · 기록에 함께 남습니다</div>
      )}
      {error && (
        <div role="alert" className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>
      )}
    </div>
  )

  return { body, dateRow, submit, busy, canSubmit: missing.length === 0, api, values }
}

/** 인라인 폼 (작업 회신, 클레임 판정, 새 입력 등) */
export function ActionForm({ action, fixed = {}, initial = {}, onDone, onCancel, extra, slots, framed, outcome }: Props) {
  const { ontology } = useApp()
  const f = useActionForm(action, fixed, initial, onDone, slots)
  const inputs = (
    <>
      {f.body}
      {typeof extra === 'function' ? extra(f.api) : extra}
    </>
  )
  // 실행과 취소는 줄이 바뀌어도 함께 움직인다
  const buttons = (
    <div className={`flex items-center gap-3 ${framed ? 'ml-auto' : ''}`}>
      <Button variant="primary" className={framed ? 'h-10 px-5 font-medium' : ''} disabled={f.busy || !f.canSubmit} onClick={f.api.submit}>
        {f.busy ? '실행 중…' : `${ontology.actions[action]?.name ?? action} 실행`}
      </Button>
      {onCancel && <Button variant="text" onClick={onCancel} disabled={f.busy}>취소</Button>}
    </div>
  )
  if (framed) {
    return (
      <>
        <div className="space-y-3 px-4 py-3">{inputs}</div>
        <div data-form-foot className="flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-indigo-200 bg-indigo-50 px-4 py-3">
          {outcome && (
            <div className="min-w-48 flex-1 text-sm text-indigo-950">
              <span className="mr-1.5 text-xs font-medium text-indigo-700">실행하면</span>
              {outcome(f.api)}
            </div>
          )}
          {f.dateRow}
          {buttons}
        </div>
      </>
    )
  }
  return (
    <div className="space-y-3">
      {inputs}
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        {f.dateRow}
        {buttons}
      </div>
    </div>
  )
}

/** 확인 창 안의 폼 (위원회·SCM 결정). 실패하면 창을 닫지 않고 서버 메시지를 보인다 */
export function ActionDialog({ action, fixed = {}, initial = {}, onDone, onCancel, extra, before, slots, reasonRequired }: Props) {
  const { ontology } = useApp()
  const f = useActionForm(action, fixed, initial, onDone, slots, true)
  const result = typeof f.values.result === 'string' ? f.values.result : ''
  // 근거가 필수인 결과(거절 A-09, 출하 경위 확인 대기 중 승인 R11-1)는 적기 전에 버튼을 꺼 둔다. 최종 확인은 서버가 한다
  const required = { ...REASON_REQUIRED_DEFAULT, ...reasonRequired }
  const reasonNote = result ? required[result] : undefined
  const needReason = !!reasonNote && !String(f.values.reason ?? '').trim()
  return (
    <ConfirmDialog
      open
      wide
      title={ontology.actions[action]?.name ?? action}
      confirmLabel={result ? `${result} 결정 실행` : '결정 실행'}
      note={needReason ? reasonNote : '결정은 되돌릴 수 없습니다. 결과와 사유가 결정 기록에 남습니다.'}
      busy={f.busy}
      confirmDisabled={!f.canSubmit || needReason}
      onConfirm={f.api.submit}
      onCancel={() => onCancel?.()}
    >
      {before}
      {f.body}
      {typeof extra === 'function' ? extra(f.api) : extra}
    </ConfirmDialog>
  )
}

export type ActionItem = {
  action: string
  label?: string
  /** true면 주 버튼(행동 색)으로 그린다. 화면에 하나만 */
  primary?: boolean
  /** 옆 칸에 여는 폼 박스의 머리 띠: 제목(없으면 버튼 이름), 오른쪽 보조 글, 아이콘 */
  title?: string
  subtitle?: string
  icon?: ReactNode
  /** 폼 박스 아래 띠에 적는 "실행하면 생기는 일" */
  outcome?: Props['outcome']
  fixed?: Values
  initial?: Values
  extra?: Props['extra']
  /** 확인 창에서 폼 위에 보일 것 (판단 근거 등) */
  before?: ReactNode
  slots?: FieldSlots
}

/** 액션 버튼 줄(묶음마다 한 줄). available_actions에 있는 액션만 버튼을 그리고, 누르면 폼(또는 확인 창)이 열린다.
 *  폼은 한 번에 하나만 열린다. formTarget이 있으면 폼을 버튼 아래가 아니라 그 자리에 그린다 (요약 띠의 오른쪽 칸, ui-guide.md v9) */
export function ActionBar({ groups, formTarget }: { groups: { title?: string; items: ActionItem[] }[]; formTarget?: HTMLElement | null }) {
  const { view } = useApp()
  const [open, setOpen] = useState<string | null>(null)
  const shown = groups
    .map(g => ({
      title: g.title,
      items: g.items.map(it => ({ it, a: view.available_actions.find(a => a.action === it.action) })).filter(x => x.a),
    }))
    .filter(g => g.items.length > 0)
  if (shown.length === 0) return null
  const cur = shown.flatMap(g => g.items).find(x => x.it.action === open)
  const close = () => setOpen(null)
  const isDialog = !!cur && DIALOG_ACTIONS.has(cur.it.action)

  const form = cur && (isDialog ? (
    <ActionDialog key={cur.it.action} action={cur.it.action} fixed={cur.it.fixed} initial={cur.it.initial}
      extra={cur.it.extra} before={cur.it.before} slots={cur.it.slots} onDone={close} onCancel={close} />
  ) : (
    formTarget ? (
      // 옆 칸에 열 때: 칸을 채우는 박스. 머리 띠(행동 색)에 어느 버튼의 폼인지 적고, 아래 띠에 실행 줄을 둔다 (ui-guide.md v9·v10)
      <div data-form-box className="w-full overflow-hidden rounded-lg border border-indigo-300 bg-white">
        <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1 border-b border-indigo-200 bg-indigo-50 px-4 py-2.5">
          {cur.it.icon && <span className="text-indigo-600">{cur.it.icon}</span>}
          <span className="text-base font-semibold text-indigo-950">{cur.it.title ?? cur.it.label ?? cur.a!.label}</span>
          {cur.it.subtitle && <span className="ml-auto text-xs text-indigo-700">{cur.it.subtitle}</span>}
        </div>
        <ActionForm key={cur.it.action} framed action={cur.it.action} fixed={cur.it.fixed} initial={cur.it.initial}
          extra={cur.it.extra} slots={cur.it.slots} outcome={cur.it.outcome} onDone={close} onCancel={close} />
      </div>
    ) : (
      // 버튼 아래에 열 때는 폼 박스를 내용 너비에 맞춘다 (ui-guide.md v7)
      <div className="w-fit min-w-[32rem] max-w-full rounded-md border border-neutral-200 p-3">
        <ActionForm key={cur.it.action} action={cur.it.action} fixed={cur.it.fixed} initial={cur.it.initial}
          extra={cur.it.extra} slots={cur.it.slots} onDone={close} onCancel={close} />
      </div>
    )
  ))

  return (
    <div className="space-y-4">
      {shown.map(g => (
        <div key={g.title ?? g.items[0].it.action} className="flex flex-wrap items-center gap-2">
          {g.title && <span className="w-16 text-xs font-medium text-neutral-500">{g.title}</span>}
          {g.items.map(({ it, a }) => (
            <Button key={it.action} variant={it.primary ? 'primary' : 'secondary'} aria-expanded={open === it.action}
              onClick={() => setOpen(o => (o === it.action ? null : it.action))}
              className={it.primary ? 'h-10 px-5 font-medium' : open === it.action ? 'bg-neutral-100' : ''}>
              {it.label ?? a!.label}
            </Button>
          ))}
        </div>
      ))}
      {form && (formTarget && !isDialog ? createPortal(form, formTarget) : form)}
    </div>
  )
}
