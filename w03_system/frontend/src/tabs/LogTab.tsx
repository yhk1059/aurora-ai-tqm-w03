import { ChevronDown, ChevronRight } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { Card } from '../components/Card'
import { actionName, actorName, ChangeRow } from '../components/LastChange'
import { StatusBadge } from '../components/StatusBadge'
import { useApp } from '../context'
import { fmtDate } from '../format'
import type { ActionLogRow, AiLogRow, Ontology } from '../types'

// 기록 탭 (ui-guide.md 레이아웃): 액션 기록 전체와 AI 입출력 전체. 읽기 전용이다.
// 기록을 고치거나 지우는 길은 없다(초기화만). AI 입출력은 줄이지 않고 그대로 보인다.

const SYSTEM = '시스템'
const AI_TASK_NAMES: Record<string, string> = {
  agenda_summary: '안건 요약',
  classify_reply: '회신 분류',
  review_explanation: '재검토 설명',
  notice_draft: '안내 초안',
}

type Filter = 'all' | 'human' | 'auto'
const FILTERS: { key: Filter; label: string }[] = [
  { key: 'all', label: '전체' },
  { key: 'human', label: '사람 액션만' },
  { key: 'auto', label: '자동 처리만' },
]

function show(v: unknown): string {
  if (v === null || v === undefined) return '—'
  if (typeof v === 'object') return JSON.stringify(v)
  return String(v)
}

function Json({ value }: { value: unknown }) {
  return (
    <pre className="text-xs font-mono whitespace-pre-wrap break-all rounded-md bg-neutral-100 p-2 text-neutral-700">
      {typeof value === 'string' ? value : JSON.stringify(value, null, 2)}
    </pre>
  )
}

function KeyValueTable({ data }: { data: Record<string, unknown> }) {
  const entries = Object.entries(data)
  if (entries.length === 0) return <p className="text-sm text-neutral-500">없음</p>
  return (
    <table className="w-full text-sm">
      <tbody>
        {entries.map(([k, v]) => (
          <tr key={k} className="border-t border-neutral-100 align-top">
            <td className="py-1 pr-3 w-48 font-mono text-xs text-neutral-500">{k}</td>
            <td className="py-1 text-neutral-700 break-all">{show(v)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function scrollTo(id: string) {
  document.getElementById(id)?.scrollIntoView({ block: 'center' })
}

/** 이 액션 기록과 연결된 AI 기록 순번: 입력·원인의 ai_log_id, 또는 AI 기록의 action_seq */
function linkedAi(row: ActionLogRow, ai: AiLogRow[]): number[] {
  const out = new Set<number>()
  for (const src of [row.inputs, row.cause]) {
    const id = src?.['ai_log_id']
    if (typeof id === 'number') out.add(id)
  }
  for (const a of ai) if (a.action_seq === row.seq) out.add(a.seq)
  return [...out].sort((a, b) => a - b)
}

/** 이 AI 기록과 연결된 액션 순번: action_seq, 또는 그 AI 기록을 ai_log_id로 쓴 액션 */
function linkedActions(a: AiLogRow, actions: ActionLogRow[]): number[] {
  const out = new Set<number>()
  if (a.action_seq !== null) out.add(a.action_seq)
  for (const r of actions) if (r.inputs?.['ai_log_id'] === a.seq || r.cause?.['ai_log_id'] === a.seq) out.add(r.seq)
  return [...out].sort((x, y) => x - y)
}

function ActionRow({ row, ontology, ai, open, onToggle, onJumpAi, autoCount = 0, groupOpen = false, onToggleGroup }: {
  row: ActionLogRow; ontology: Ontology; ai: AiLogRow[]; open: boolean; onToggle(): void; onJumpAi(seq: number): void
  autoCount?: number; groupOpen?: boolean; onToggleGroup?(): void
}) {
  const auto = row.actor === SYSTEM
  const cause = row.cause ?? {}
  const aiLinks = linkedAi(row, ai)
  const Icon = open ? ChevronDown : ChevronRight
  return (
    <li id={`action-${row.seq}`} className={`border-t border-neutral-100 py-2 ${auto ? 'pl-8' : ''}`}>
      <button type="button" onClick={onToggle} className="flex w-full items-start gap-2 text-left">
        <Icon size={16} strokeWidth={1.5} className="mt-0.5 shrink-0 text-neutral-400" />
        <span className="w-10 shrink-0 tabular-nums text-sm text-neutral-500">#{row.seq}</span>
        <span className="flex-1 space-y-0.5">
          <span className="block text-sm">
            {auto && (
              <span className="inline-flex items-center rounded px-1.5 h-5 border border-neutral-300 text-[11px] text-neutral-600 mr-1.5">자동</span>
            )}
            <span className="font-medium text-neutral-900">{actionName(ontology, row.action)}</span>
            <span className="text-neutral-500"> · {auto ? SYSTEM : actorName(ontology, row.actor)} · </span>
            <span className="tabular-nums">{fmtDate(row.applied_date)}</span>
            <span className="ml-2 text-xs text-neutral-500">변경 {row.changes.length}개</span>
          </span>
          {auto && (
            <span className="block text-xs text-neutral-500">
              {typeof cause.rule === 'string' && <span className="font-mono text-neutral-600 mr-1.5">{cause.rule}</span>}
              {typeof cause.reason === 'string' && cause.reason}
              {typeof cause.after_seq === 'number' && <span className="ml-1.5 text-neutral-500">(#{cause.after_seq} 뒤)</span>}
            </span>
          )}
        </span>
      </button>
      {aiLinks.length > 0 && (
        <div className="mt-1 ml-[4.5rem] text-xs text-neutral-500">
          연결된 AI 기록:{' '}
          {aiLinks.map(id => (
            <button key={id} type="button" onClick={() => onJumpAi(id)} className="mr-1.5 underline hover:text-neutral-900">AI #{id}</button>
          ))}
        </div>
      )}
      {autoCount > 0 && (
        <button type="button" onClick={onToggleGroup} aria-expanded={groupOpen}
          className="mt-1 ml-[4.5rem] text-xs text-neutral-500 underline hover:text-neutral-900">
          {groupOpen ? `자동 처리 ${autoCount}건 접기` : `이 액션 뒤 자동 처리 ${autoCount}건 보기`}
        </button>
      )}
      {open && (
        <div className="mt-2 ml-[4.5rem] space-y-3">
          <div className="space-y-1">
            <h3 className="text-xs font-medium text-neutral-500">입력</h3>
            <KeyValueTable data={row.inputs ?? {}} />
          </div>
          <div className="space-y-1">
            <h3 className="text-xs font-medium text-neutral-500">변경 (이전 → 이후)</h3>
            {row.changes.length === 0
              ? <p className="text-sm text-neutral-500">상태 변화 없음</p>
              : <ul className="space-y-0.5 pl-3 border-l border-neutral-200">
                  {row.changes.map((c, i) => <ChangeRow key={i} ontology={ontology} c={c} />)}
                </ul>}
          </div>
          {!auto && Object.keys(cause).length > 0 && (
            <div className="space-y-1">
              <h3 className="text-xs font-medium text-neutral-500">원인</h3>
              <KeyValueTable data={cause} />
            </div>
          )}
        </div>
      )}
    </li>
  )
}

function AiRow({ row, actions, open, onToggle, onJumpAction }: {
  row: AiLogRow; actions: ActionLogRow[]; open: boolean; onToggle(): void; onJumpAction(seq: number): void
}) {
  const ok = row.output?.ok === true
  const links = linkedActions(row, actions)
  const Icon = open ? ChevronDown : ChevronRight
  return (
    <li id={`ai-${row.seq}`} className="border-t border-neutral-100 py-2">
      <button type="button" onClick={onToggle} className="flex w-full items-center gap-2 text-left text-sm">
        <Icon size={16} strokeWidth={1.5} className="shrink-0 text-neutral-400" />
        <span className="w-10 shrink-0 tabular-nums text-neutral-500">#{row.seq}</span>
        <span className="font-medium text-neutral-900">{AI_TASK_NAMES[row.task] ?? row.task}</span>
        <span className="font-mono text-xs text-neutral-500">{row.model}</span>
        <StatusBadge state={ok ? '성공' : '실패'} />
        {!ok && row.output?.error && <span className="font-mono text-xs text-neutral-500">{row.output.error}</span>}
      </button>
      <div className="mt-1 ml-[4.5rem] text-xs text-neutral-500">
        연결된 액션:{' '}
        {links.length === 0 ? '없음' : links.map(s => (
          <button key={s} type="button" onClick={() => onJumpAction(s)} className="mr-1.5 underline hover:text-neutral-900">#{s}</button>
        ))}
      </div>
      {open && (
        <div className="mt-2 ml-[4.5rem] space-y-3">
          <div className="space-y-1">
            <h3 className="text-xs font-medium text-neutral-500">입력 (전체)</h3>
            <Json value={row.inputs} />
          </div>
          <div className="space-y-1">
            <h3 className="text-xs font-medium text-neutral-500">출력 (전체)</h3>
            <Json value={row.output} />
          </div>
        </div>
      )}
    </li>
  )
}

export function LogTab() {
  const { view, ontology } = useApp()
  const [filter, setFilter] = useState<Filter>('all')
  const [newestFirst, setNewestFirst] = useState(false)
  const [openActions, setOpenActions] = useState<Set<number>>(new Set())
  const [openAi, setOpenAi] = useState<Set<number>>(new Set())
  const [pendingJump, setPendingJump] = useState<string | null>(null)
  // 전체 보기에서는 자동 처리 줄을 그것을 일으킨 사람 액션 아래에 접어 둔다 (ui-guide.md v3)
  const [openGroups, setOpenGroups] = useState<Set<number>>(new Set())

  const log = view.incident ? view.log : null
  const rows = useMemo(() => {
    if (!log) return []
    const r = log.actions.filter(a =>
      filter === 'all' || (filter === 'auto' ? a.actor === SYSTEM : a.actor !== SYSTEM))
    return newestFirst ? [...r].reverse() : r
  }, [log, filter, newestFirst])

  // 자동 처리 줄 → 그것을 일으킨 사람 액션 순번 (cause.after_seq를 따라 올라간다). 없으면 접지 않는다
  const parentOf = useMemo(() => {
    const bySeq = new Map((log?.actions ?? []).map(a => [a.seq, a]))
    const out = new Map<number, number>()
    for (const a of log?.actions ?? []) {
      if (a.actor !== SYSTEM) continue
      let cur: ActionLogRow | undefined = a
      for (let i = 0; cur && cur.actor === SYSTEM && i < 50; i++) {
        const up: unknown = cur.cause?.['after_seq']
        cur = typeof up === 'number' ? bySeq.get(up) : undefined
      }
      if (cur) out.set(a.seq, cur.seq)
    }
    return out
  }, [log])
  const autoCounts = useMemo(() => {
    const out = new Map<number, number>()
    for (const p of parentOf.values()) out.set(p, (out.get(p) ?? 0) + 1)
    return out
  }, [parentOf])

  // 링크 이동: 펼친 상태가 그려진 뒤 스크롤한다
  useEffect(() => {
    if (pendingJump) { scrollTo(pendingJump); setPendingJump(null) }
  }, [pendingJump])

  if (!log) {
    return <Card title="기록"><p className="text-sm text-neutral-500">기록 없음</p></Card>
  }

  const toggle = (set: Set<number>, setter: (s: Set<number>) => void, id: number) => {
    const next = new Set(set)
    if (next.has(id)) next.delete(id); else next.add(id)
    setter(next)
  }
  // 다른 목록으로 가는 링크: 대상을 펼치고(액션은 거르기도 풀고) 그려진 뒤 스크롤한다
  const jumpAi = (seq: number) => { setOpenAi(s => new Set(s).add(seq)); setPendingJump(`ai-${seq}`) }
  const jumpAction = (seq: number) => {
    const parent = parentOf.get(seq)
    if (parent !== undefined) setOpenGroups(s => new Set(s).add(parent))
    setFilter('all'); setOpenActions(s => new Set(s).add(seq)); setPendingJump(`action-${seq}`)
  }
  const grouped = filter === 'all'
  const shown = grouped
    ? rows.filter(r => { const p = parentOf.get(r.seq); return p === undefined || openGroups.has(p) })
    : rows

  return (
    <div className="space-y-4">
      <Card title={`액션 기록 (${log.actions.length}개)`}>
        <div className="flex items-center gap-3">
          <div className="flex gap-1">
            {FILTERS.map(f => (
              <button
                key={f.key}
                type="button"
                onClick={() => setFilter(f.key)}
                className={`rounded-md px-3 h-8 text-sm border ${filter === f.key
                  ? 'border-neutral-900 text-neutral-900'
                  : 'border-neutral-300 text-neutral-500 hover:text-neutral-900'}`}
              >
                {f.label}
              </button>
            ))}
          </div>
          <button type="button" onClick={() => setNewestFirst(v => !v)} className="text-sm text-neutral-500 hover:text-neutral-900">
            {newestFirst ? '최신이 위' : '최신이 아래'} (바꾸기)
          </button>
        </div>
        {rows.length === 0 ? (
          <p className="text-sm text-neutral-500">기록 없음</p>
        ) : (
          <ul>
            {shown.map(r => (
              <ActionRow
                key={r.seq}
                row={r}
                ontology={ontology}
                ai={log.ai}
                open={openActions.has(r.seq)}
                onToggle={() => toggle(openActions, setOpenActions, r.seq)}
                onJumpAi={jumpAi}
                autoCount={grouped ? autoCounts.get(r.seq) ?? 0 : 0}
                groupOpen={openGroups.has(r.seq)}
                onToggleGroup={() => toggle(openGroups, setOpenGroups, r.seq)}
              />
            ))}
          </ul>
        )}
      </Card>

      <Card title={`AI 기록 (${log.ai.length}개)`}>
        {log.ai.length === 0 ? (
          <p className="text-sm text-neutral-500">AI 기록 없음</p>
        ) : (
          <ul>
            {log.ai.map(a => (
              <AiRow
                key={a.seq}
                row={a}
                actions={log.actions}
                open={openAi.has(a.seq)}
                onToggle={() => toggle(openAi, setOpenAi, a.seq)}
                onJumpAction={jumpAction}
              />
            ))}
          </ul>
        )}
      </Card>
    </div>
  )
}
