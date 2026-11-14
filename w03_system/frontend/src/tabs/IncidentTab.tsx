import { useEffect, useRef, useState, type ReactNode } from 'react'
import { Check } from 'lucide-react'
import { ApiError } from '../api'
import { ActionBar, targetIds, type FieldSlots, type FormApi } from '../components/ActionForm'
import { AgendaOutput, AiDraft, ClassifyOutput, NoticeOutput, ReviewOutput, agendaText } from '../components/AiDraft'
import { BatchCard } from '../components/BatchCard'
import { Button } from '../components/Button'
import { Card } from '../components/Card'
import { ConfirmDialog } from '../components/ConfirmDialog'
import { ClaimSummary } from '../components/ClaimSummary'
import { LastChange, actionName, actorName } from '../components/LastChange'
import { Network, type Selection } from '../components/Network'
import { NetworkDetail } from '../components/NetworkDetail'
import { TaskList } from '../components/TaskList'
import { StatusBadge } from '../components/StatusBadge'
import { WarningLine } from '../components/WarningLine'
import { useApp } from '../context'
import { fmtDate, fmtQty, fmtRate } from '../format'
import type { EmptyView, LastChange as LastChangeT, OpenView, OpenableBatch, Task } from '../types'

// 사건 탭 (ui-guide.md "레이아웃"): 사건이 없으면 사건 열기, 있으면 위에 사건 요약 띠, 아래 왼쪽 2/3 배치 카드·연결망 · 오른쪽 1/3 바뀐 것·작업·기록.

/** 과제 기준일. 사건 열기 적용일의 기본값 */
const BASE_DATE = '2026-07-01'

/** 방금 바뀐 배치 ID (변경 대상이 배치이거나, 관계의 출발이 배치) */
function changedBatchIds(lc: LastChangeT | null): Set<string> {
  const ids = new Set<string>()
  for (const c of lc?.changes ?? []) {
    if (c.target.type === 'batch') ids.add(String(c.target.id))
    else if (c.target.src?.[0] === 'batch') ids.add(c.target.src[1])
  }
  return ids
}

export function IncidentTab() {
  const { view } = useApp()
  const lastChange = view.incident ? (view as OpenView).last_change : null
  const seq = lastChange?.seq ?? null

  // 액션으로 last_change가 바뀌었을 때만 강조한다 (탭을 처음 열거나 역할만 바꿀 때는 하지 않음)
  const prevSeq = useRef(seq)
  const [flashIds, setFlashIds] = useState<Set<string>>(new Set())
  useEffect(() => {
    if (prevSeq.current === seq) return
    prevSeq.current = seq
    setFlashIds(changedBatchIds(lastChange))
  }, [seq, lastChange])

  return view.incident
    ? <OpenIncident view={view as OpenView} flashIds={flashIds} flashKey={seq} />
    : <EmptyIncident view={view as EmptyView} />
}

// ---------------------------------------------------------------------------
// 사건이 없을 때 (S0)
// ---------------------------------------------------------------------------

const OPENABLE_COLUMNS: Record<string, { name: string; fmt?: (v: unknown) => string; num?: boolean }> = {
  batch_id: { name: '배치' },
  product_id: { name: '제품' },
  production_date: { name: '생산일' },
  produced_qty: { name: '생산 수량', fmt: v => fmtQty(v as number), num: true },
  qc_result: { name: 'QC' },
  claim_count: { name: '클레임 건수', num: true },
  confirmed_qty: { name: '확정 불량 수량', fmt: v => fmtQty(v as number), num: true },
  defect_rate_produced: { name: '불량률(생산)', fmt: v => fmtRate(v === null ? null : (v as number) / 100), num: true }, // 이 값만 서버가 %로 준다 (loader.openable_batches)
}

function EmptyIncident({ view }: { view: EmptyView }) {
  const { run, ontology } = useApp()
  const action = view.available_actions.find(a => a.action === 'open_incident')
  // 회수 기준(R2, % 단위). 목록의 불량률도 서버가 %로 준다
  const thr = ontology.rules.R2?.threshold
  const limit = thr?.unit === '%' ? thr.value : undefined
  const isOver = (b: OpenableBatch) => limit !== undefined && b.defect_rate_produced >= limit
  const [batchId, setBatchId] = useState('')
  const [date, setDate] = useState(BASE_DATE)
  const [busy, setBusy] = useState(false)

  // 불량률 높은 순으로 보인다 (값은 서버 것 그대로, 순서만 바꾼다)
  const rows = [...view.openable_batches].sort((a, b) => b.defect_rate_produced - a.defect_rate_produced)
  const overCount = rows.filter(isOver).length
  const allowed = (action?.targets.batch_id as string[] | undefined) ?? []
  const columns = rows.length ? Object.keys(rows[0]).filter(k => k !== 'evidence') : []

  async function open() {
    setBusy(true)
    try {
      await run('open_incident', { batch_id: batchId, applied_date: date })
    } catch (e) {
      if (!(e instanceof ApiError)) throw e // 오류 줄은 App이 띄운다
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-4">
      <Card title="사건 열기">
        {action ? (
          <div className="flex flex-wrap items-end gap-3">
            <label className="space-y-1">
              <span className="block text-xs text-neutral-500">적용일</span>
              <input
                type="date"
                value={date}
                onChange={e => setDate(e.target.value)}
                className="rounded-md bg-white border border-neutral-300 px-3 h-9 text-sm tabular-nums focus:border-neutral-900 focus:outline-none"
              />
            </label>
            <label className="space-y-1">
              <span className="block text-xs text-neutral-500">배치 (아래 표에서 골라도 됨)</span>
              <select
                value={batchId}
                onChange={e => setBatchId(e.target.value)}
                className="rounded-md bg-white border border-neutral-300 px-3 h-9 text-sm font-mono focus:border-neutral-900 focus:outline-none"
              >
                <option value="">배치 선택</option>
                {allowed.map(id => <option key={id} value={id}>{id}</option>)}
              </select>
            </label>
            <Button variant="primary" onClick={open} disabled={busy || !batchId || !date}>
              {busy ? '실행 중…' : '사건 열기'}
            </Button>
          </div>
        ) : (
          <p className="text-sm text-neutral-500">이 역할은 사건을 열 수 없습니다</p>
        )}
      </Card>

      <Card title={`열 수 있는 배치 (클레임이 있는 배치 ${rows.length}개)`}>
        {thr && (
          <p className="text-sm text-neutral-700">
            불량률 높은 순.{' '}
            <span className={overCount > 0 ? 'font-semibold text-red-700' : ''}>회수 기준({thr.description}) 이상 {overCount}개</span>
          </p>
        )}
        <div className="max-h-[28rem] overflow-auto">
          <table className="w-full text-sm tabular-nums">
            <thead className="bg-neutral-100 sticky top-0">
              <tr>
                {columns.map(k => (
                  <th key={k} className={`px-2 h-8 font-medium text-xs text-neutral-500 ${OPENABLE_COLUMNS[k]?.num ? 'text-right' : 'text-left'}`}>
                    {OPENABLE_COLUMNS[k]?.name ?? k}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((b: OpenableBatch) => (
                <tr
                  key={b.batch_id}
                  onClick={action ? () => setBatchId(b.batch_id) : undefined}
                  title={b.evidence.join('\n')}
                  className={`border-t border-neutral-100 ${action ? 'cursor-pointer hover:bg-neutral-50' : ''} ${batchId === b.batch_id ? 'bg-neutral-100' : isOver(b) ? 'bg-red-50' : ''}`}
                >
                  {columns.map(k => {
                    const col = OPENABLE_COLUMNS[k]
                    const v = (b as Record<string, unknown>)[k]
                    return (
                      <td key={k} className={`px-2 h-8 ${col?.num ? 'text-right' : ''} ${k === 'batch_id' ? 'font-mono' : ''} ${k === 'defect_rate_produced' && isOver(b) ? 'font-semibold text-red-700' : ''}`}>
                        {col?.fmt ? col.fmt(v) : String(v ?? '—')}
                      </td>
                    )
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  )
}

// ---------------------------------------------------------------------------
// 사건이 있을 때
// ---------------------------------------------------------------------------

/** 판정 액션: 사건 요약 띠의 주 버튼 (화면에 하나) */
const JUDGE_ACTIONS = ['submit_agenda', 'committee_decision']
const INPUT_ACTIONS = ['register_claim', 'register_news']

// ---------------------------------------------------------------------------
// AI 초안 자리 (decisions.md "화면 구현 전 정리 4건" ②). 버튼으로만 요청하고, "이 내용 사용"은 폼만 채운다 (R12).
// 어떤 초안을 보고 결정했는지 남기도록, 사용하면 ai_log_id를 폼 값에 함께 넣는다 (사람이 고쳐도 그대로 보낸다).
// ---------------------------------------------------------------------------

/** 배치 한 줄 = 판정 수치. 시스템이 계산한 값이다 (위원회 결정 창의 판단 근거, AI 안건 요약 초안 안의 표) */
function BatchFactRows({ batches }: { batches: OpenView['batches'] }) {
  return (
    <>
      {batches.map(b => (
        <div key={b.id} className="flex flex-wrap items-center gap-x-3 gap-y-1 px-3 py-2">
          <span className="font-mono text-sm text-neutral-900">{b.id}</span>
          <span className={`text-xl font-semibold tabular-nums ${b.metrics.over_threshold ? 'text-red-700' : 'text-neutral-900'}`}>{fmtRate(b.metrics.defect_rate)}</span>
          <span className="tabular-nums text-neutral-700">{fmtQty(b.metrics.confirmed_qty)} / {fmtQty(b.metrics.produced_qty)}</span>
          <span className="flex-1" />
          <span className="text-neutral-500">기준 초과일 <span className="tabular-nums text-neutral-700">{fmtDate(b.metrics.threshold_crossed_date)}</span></span>
          {b.metrics.days_unsubmitted != null && <span className="text-neutral-500">미상신 <span className="tabular-nums font-semibold text-red-700">{b.metrics.days_unsubmitted}일</span></span>}
          {b.warnings.length > 0 && <span className="inline-flex items-center rounded border border-amber-200 bg-amber-50 px-2 h-6 text-xs font-medium text-amber-700">경고 {b.warnings.length}건</span>}
        </div>
      ))}
    </>
  )
}

/** 안건 상신 폼: 안건 요약 필드 위 */
const agendaSlots = (view: OpenView): FieldSlots => f => {
  const ids = (f.values.batch_ids as string[] | undefined) ?? []
  const picked = view.batches.filter(b => ids.includes(b.id))
  const over = picked.filter(b => b.metrics.over_threshold).length
  const facts = (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <span className={`inline-flex items-center rounded px-2 h-[22px] text-xs font-medium ${over > 0 ? 'bg-red-100 text-red-800' : 'bg-neutral-200 text-neutral-900'}`}>
          {over > 0 ? `기준 초과 배치 ${over}` : `안건 배치 ${picked.length}`}
        </span>
        <span className="text-xs text-neutral-600">배치 수치 · 시스템 계산값 (AI가 쓴 글이 아닙니다)</span>
      </div>
      <div className={`rounded-lg border bg-white divide-y ${over > 0 ? 'border-red-200 divide-red-100' : 'border-neutral-200 divide-neutral-100'}`}>
        <BatchFactRows batches={picked} />
      </div>
    </div>
  )
  return {
    agenda_summary: {
      before: (
        <AgendaDraft f={f} ids={ids} facts={facts} />
      ),
    },
  }
}

/** AI 안건 요약 초안. "이 내용 사용"을 누르면 폼에 넣고, 긴 글을 고치기 쉽게 큰 편집 창을 띄운다.
 *  창의 글은 폼의 안건 요약 칸과 같은 값이다. 취소하면 창만 닫히고 넣은 글은 폼에 남는다 */
function AgendaDraft({ f, ids, facts }: { f: FormApi; ids: string[]; facts: ReactNode }) {
  const [editing, setEditing] = useState(false)
  return (
    <>
      <AiDraft
        task="agenda_summary"
        params={{ batch_ids: ids }}
        label="AI로 안건 요약"
        disabledReason={ids.length === 0 ? '배치를 먼저 고르세요' : undefined}
        render={o => <AgendaOutput output={o} facts={facts} />}
        onUse={(o, logId) => { f.setValues({ agenda_summary: agendaText(o), ai_log_id: logId }); setEditing(true) }}
      />
      <ConfirmDialog
        open={editing}
        wide
        title="안건 요약 확인·수정"
        confirmLabel="안건 상신 실행"
        busy={f.busy}
        confirmDisabled={!String(f.values.agenda_summary ?? '').trim()}
        note={f.error ?? '고친 글이 안건 요약으로 위원회에 올라갑니다.'}
        onConfirm={f.submit}
        onCancel={() => setEditing(false)}
      >
        <textarea
          aria-label="안건 요약"
          value={String(f.values.agenda_summary ?? '')}
          onChange={e => f.setValues({ agenda_summary: e.target.value })}
          className="w-full h-[60vh] rounded-md bg-white border border-neutral-300 px-3 py-2 text-sm leading-relaxed text-neutral-900 focus:border-neutral-900 focus:outline-none"
        />
      </ConfirmDialog>
    </>
  )
}

/** 회신 입력 폼: 회신 문장 필드 아래 */
function replySlots(uninterpretable: string) {
  return (task: Task, f: FormApi) => {
    const text = String(f.values.reply_text ?? '').trim()
    return {
      reply_text: {
        after: (
          <AiDraft
            task="classify_reply"
            params={{ task_id: task.id, reply_text: text }}
            label="AI로 회신 분류"
            disabledReason={text ? undefined : '회신 문장을 먼저 적으세요'}
            render={o => <ClassifyOutput output={o} uninterpretable={uninterpretable} />}
            canUse={o => (o as { result?: unknown }).result !== uninterpretable}
            onRequest={() => { if (f.values.ai_log_id != null) f.setValues({ result: '', ai_log_id: undefined }) }}
            onUse={(o, logId) => f.setValues({ result: (o as { result: string }).result, ai_log_id: logId })}
          />
        ),
      },
    }
  }
}

/** 회수 대상 배치 상태 (ai/tasks.py RECALL_STATES와 같음). 안내문 초안은 이때만 요청할 수 있다 */
const RECALL_STATES = ['회수진행', '부분회수']
/** 안내 대상 결정 작업 유형 = 정의에서 R9-1이 만드는 작업 */
function noticeTaskTypes(ontology: { task_types: Record<string, { rules: string[] }> }): Set<string> {
  return new Set(Object.entries(ontology.task_types).filter(([, d]) => d.rules.includes('R9-1')).map(([k]) => k))
}

/** 출하처가 아직 확인되지 않은 관계의 확인 수준 */
const UNCONFIRMED = ['미확인', '확인요청중']

function Tile({ label, value, unit, tone }: { label: string; value: number; unit: string; tone?: string }) {
  return (
    <div className={`rounded-md px-3 py-2 ${tone ?? 'bg-neutral-100 text-neutral-900'}`}>
      <div className="text-xs">{label}</div>
      <div className="text-2xl font-semibold tabular-nums">
        {value}<span className="ml-1 text-sm font-normal">{unit}</span>
      </div>
    </div>
  )
}

/** 위원회 결정 창의 판단 근거: 화면이 창에 가려지므로 결정 대상 배치의 숫자·경고와 상신된 안건 요약을 창 안에 다시 보인다 (ui-guide.md v4) */
function CommitteeEvidence({ view }: { view: OpenView }) {
  const ids = targetIds(view, 'committee_decision', 'batch_ids') ?? []
  const batches = view.batches.filter(b => ids.includes(b.id))
  const unconfirmed = [...new Set(view.network.shipped_to.filter(l => UNCONFIRMED.includes(l.confirm)).map(l => l.dst.id))]
  const agenda = [...view.log.actions].reverse().find(a => a.action === 'submit_agenda')
  const summary = String(agenda?.inputs.agenda_summary ?? '').trim()
  return (
    <div data-evidence className="space-y-1">
      <div className="text-xs text-neutral-500">판단 근거</div>
      <div className="rounded-md border border-neutral-200 divide-y divide-neutral-100">
        <BatchFactRows batches={batches} />
        <div className="flex flex-wrap gap-x-3 px-3 py-2">
          <span className="w-20 shrink-0 text-neutral-500">관련 고객</span>
          <span className="tabular-nums">{view.customers.length}곳</span>
          {unconfirmed.length > 0 && (
            <span className="text-amber-700">출하처 미확인 {unconfirmed.length}곳 (<span className="font-mono">{unconfirmed.join(', ')}</span>)</span>
          )}
        </div>
        <div className="flex gap-x-3 px-3 py-2">
          <span className="w-20 shrink-0 text-neutral-500">안건 요약</span>
          <span className={`whitespace-pre-line ${summary ? '' : 'text-neutral-500'}`}>{summary || '안건 요약 없이 상신됨'}</span>
        </div>
      </div>
    </div>
  )
}

/** 사건의 주 경로. 사건 상태(정의의 incident_statuses 이름) → 단계 이름. 관찰중은 이 경로 밖이라 단계를 그리지 않는다 */
const STEPS: [status: string, label: string][] = [
  ['열림', '기준 초과 확인'], ['판정중', '위원회 판정'], ['회수진행', '회수'], ['복구계획확정', '재공급 계획 확정'],
]

/** 사건 상태에 맞는 제목 한 문장과, 주 경로에서 갈라진 경우의 보조 글자 (조사계속·부분회수) */
function headline(view: OpenView, over: number, thr?: string): { title: string; note?: string } {
  const has = (s: string) => view.batches.some(b => b.state === s)
  const recall = view.batches.filter(b => RECALL_STATES.includes(b.state ?? '')).length
  switch (view.incident.status) {
    case '판정중':
      return has('조사계속')
        ? { title: `위원회가 거절해 배치 ${over}개의 원인을 조사하는 중입니다`, note: '거절됨 · 원인 조사 뒤 다시 상신' }
        : { title: `배치 ${over}개의 회수 여부를 위원회가 판정하는 중입니다` }
    case '회수진행':
      return has('부분회수')
        ? { title: `배치 ${recall}개를 출하처가 확인된 고객부터 회수하는 중입니다`, note: '조건부 승인 · 미확인 고객은 보류' }
        : { title: `배치 ${recall}개를 회수하는 중입니다` }
    case '복구계획확정':
      return { title: `배치 ${recall}개를 회수하고 있고, 재공급 계획이 확정됐습니다` }
    default:
      return { title: over > 0 ? `배치 ${over}개가 회수 기준${thr ? `(${thr})` : ''}을 넘었습니다` : '회수 기준을 넘은 배치가 없습니다' }
  }
}

function Steps({ status, note }: { status: string; note?: string }) {
  const cur = STEPS.findIndex(([s]) => s === status)
  if (cur < 0) return null
  return (
    <ol data-steps className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm">
      {STEPS.map(([s, label], n) => (
        <li key={s} aria-current={n === cur ? 'step' : undefined} className="flex items-center gap-2">
          {n > 0 && <span className={`h-px w-8 ${n <= cur ? 'bg-neutral-900' : 'bg-neutral-300'}`} />}
          {n < cur
            ? <Check size={16} strokeWidth={1.5} className="text-neutral-900" aria-label="지남" />
            : <span className={`h-2.5 w-2.5 rounded-full border ${n === cur ? 'border-neutral-900 bg-neutral-900' : 'border-neutral-400'}`} />}
          <span className={n === cur ? 'font-semibold text-neutral-900' : n < cur ? 'text-neutral-700' : 'text-neutral-500'}>{label}</span>
          {n === cur && note && <span className="text-amber-700">({note})</span>}
        </li>
      ))}
    </ol>
  )
}

/** 사건 요약 띠: 지금 상태 한 문장 → 건수 4개 → 이 역할이 할 수 있는 액션. 건수는 뷰의 항목을 센 것이고 수량은 다시 계산하지 않는다 */
function IncidentSummary({ view }: { view: OpenView }) {
  const over = view.batches.filter(b => b.metrics.over_threshold)
  const thr = view.batches[0]?.metrics.threshold.description
  const unconfirmed = new Set(view.network.shipped_to.filter(l => UNCONFIRMED.includes(l.confirm)).map(l => l.dst.id))
  const openTasks = view.tasks.filter(t => t.state === '열림').length
  const judge = view.available_actions.find(a => JUDGE_ACTIONS.includes(a.action))
  const slotsOf = (a: string) => (a === 'submit_agenda' ? agendaSlots(view) : undefined)
  const head = headline(view, over.length, thr)
  const next = judge
    ? `이 역할이 지금 할 일: ${judge.label}`
    : openTasks > 0 ? `열린 작업 ${openTasks}건의 회신을 기다리는 중` : '이 역할이 지금 할 판정은 없습니다'

  return (
    <section className="rounded-lg bg-white border border-neutral-200 p-5 space-y-4">
      <div className="space-y-1">
        <StatusBadge state={view.incident.status} />
        <div className="text-2xl font-semibold text-neutral-900">{head.title}</div>
        <div className="text-sm text-neutral-500">{next}</div>
      </div>
      <Steps status={view.incident.status} note={head.note} />
      <div className="grid grid-cols-4 gap-3">
        <Tile label="기준 초과 배치" value={over.length} unit={`/ ${view.batches.length}`} tone={over.length > 0 ? 'bg-red-50 text-red-700' : undefined} />
        <Tile label="관련 고객" value={view.customers.length} unit="곳" />
        <Tile label="출하처 미확인 고객" value={unconfirmed.size} unit="곳" tone={unconfirmed.size > 0 ? 'bg-amber-50 text-amber-700' : undefined} />
        <Tile label="열린 작업" value={openTasks} unit="건" tone={openTasks > 0 ? 'bg-blue-50 text-blue-700' : undefined} />
      </div>
      <ActionBar title="판정" items={JUDGE_ACTIONS.map(action => ({
        action, primary: true, slots: slotsOf(action),
        before: action === 'committee_decision' ? <CommitteeEvidence view={view} /> : undefined,
      }))} />
      <ActionBar title="새 입력" items={INPUT_ACTIONS.map(action => ({ action }))} />
    </section>
  )
}

function OpenIncident({ view, flashIds, flashKey }: { view: OpenView; flashIds: Set<string>; flashKey: number | null }) {
  const { ontology } = useApp()
  const incidentWarnings = view.warnings.filter(w => w.target.type !== 'batch')
  const recent = view.log.actions.slice(-5).reverse()
  const [selected, setSelected] = useState<Selection | null>(null)
  const noticeTypes = noticeTaskTypes(ontology)
  const hasRecall = view.batches.some(b => RECALL_STATES.includes(b.state ?? ''))
  // 기준 초과 배치를 먼저, 크게. 기준 미달이고 미확정 클레임이 없는 배치는 한 줄로 접는다
  const batches = [...view.batches].sort((a, b) => Number(b.metrics.over_threshold) - Number(a.metrics.over_threshold))

  return (
    <div className="space-y-4">
    <IncidentSummary view={view} />
    <div className="grid grid-cols-3 gap-4 items-start">
      {/* 왼쪽 2/3: 배치 판정 카드 → 연결망 → 사건 경고 */}
      <div className="col-span-2 space-y-4">
        {batches.map(b => (
          <BatchCard
            key={b.id}
            batch={b}
            flash={flashIds.has(b.id)}
            flashKey={flashKey}
            compact={!b.metrics.over_threshold && b.metrics.pending_qty === 0}
            claims={<ClaimSummary claims={view.claims.filter(c => c.batch_id === b.id)} />}
          />
        ))}
        <Card title="연결망 — 원료 로트 → 배치 → 고객 (R4 원료 로트 기반 영향 추적)">
          <Network view={view} selected={selected} onSelect={setSelected} />
        </Card>
        {selected && <NetworkDetail view={view} selected={selected} />}
        {incidentWarnings.length > 0 && (
          <Card title="사건 경고">
            {incidentWarnings.map(w => (
              <WarningLine key={`${w.code}-${w.target.id}`} rule={w.rule}>{w.message}</WarningLine>
            ))}
          </Card>
        )}
      </div>

      {/* 오른쪽 1/3: 방금 바뀐 것 → 작업 목록 → 최근 기록 */}
      <div className="space-y-4">
        {view.last_change && <LastChange change={view.last_change} ontology={ontology} />}
        {view.last_change && view.last_change.action !== 'reset' && (
          <AiDraft
            key={view.last_change.seq}
            task="review_explanation"
            params={{}}
            label="AI로 변경 설명"
            render={o => <ReviewOutput output={o} />}
          />
        )}

        <TaskList
          tasks={view.tasks}
          replySlots={replySlots(ontology.ai_uninterpretable)}
          taskExtra={t => (noticeTypes.has(t.type) && hasRecall ? (
            <AiDraft task="notice_draft" params={{}} label="AI로 안내문 초안" render={o => <NoticeOutput output={o} />} />
          ) : null)}
        />

        <Card title="최근 기록">
          <ol className="space-y-1">
            {recent.map(r => (
              <li key={r.seq} className="flex gap-2 text-sm">
                <span className="w-8 shrink-0 tabular-nums text-neutral-500">#{r.seq}</span>
                <span className="flex-1 text-neutral-900">{actionName(ontology, r.action)}</span>
                <span className="text-neutral-500">{actorName(ontology, r.actor)}</span>
                <span className="tabular-nums text-neutral-500">{fmtDate(r.applied_date)}</span>
              </li>
            ))}
          </ol>
          <p className="text-xs text-neutral-500">전체는 기록 탭에서</p>
        </Card>
      </div>
    </div>
    </div>
  )
}
