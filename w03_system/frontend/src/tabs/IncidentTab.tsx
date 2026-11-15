import { useEffect, useRef, useState, type ReactNode } from 'react'
import { Check, Gavel, MessageSquareWarning, Newspaper } from 'lucide-react'
import { ApiError } from '../api'
import { ActionBar, targetIds, type ActionItem, type FieldSlots, type FormApi } from '../components/ActionForm'
import { AgendaOutput, AiDraft, ClassifyOutput, NoticeOutput, ReviewOutput, agendaText } from '../components/AiDraft'
import { BatchCard, RateBar } from '../components/BatchCard'
import { Button } from '../components/Button'
import { BoxLabel, Card } from '../components/Card'
import { ConfirmDialog } from '../components/ConfirmDialog'
import { ClaimSummary } from '../components/ClaimSummary'
import { LastChange, actionName, actorName } from '../components/LastChange'
import { unconfirmedCustomers } from '../components/Network'
import { TaskList } from '../components/TaskList'
import { StatusBadge } from '../components/StatusBadge'
import { WarningLine } from '../components/WarningLine'
import { useApp } from '../context'
import { fmtDate, fmtQty, fmtRate } from '../format'
import type { EmptyView, LastChange as LastChangeT, OpenView, OpenableBatch, Task } from '../types'

// 사건 탭 (ui-guide.md "레이아웃"): 사건이 없으면 사건 열기, 있으면 위에 사건 요약 띠, 아래 왼쪽 2/3 배치 카드·연결망 한 줄 · 오른쪽 1/3 바뀐 것·작업·기록.
// 회수 결정 뒤(작업 단계)에는 작업 목록이 왼쪽 큰 칸 맨 위로 오고 배치 카드는 한 줄로 접힌다 (v6).

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

/** 기준 미달 표의 불량률. 값이 0.0x%라 소수 둘째 자리까지 적는다 (서버가 %로 준다, loader.openable_batches) */
const fmtSmallRate = (v: number) => `${v.toFixed(2)}%`

function EmptyIncident({ view }: { view: EmptyView }) {
  const { run, ontology } = useApp()
  const action = view.available_actions.find(a => a.action === 'open_incident')
  // 회수 기준(R2, % 단위). 목록의 불량률도 서버가 %로 준다
  const thr = ontology.rules.R2?.threshold
  const limit = thr?.unit === '%' ? thr.value : undefined
  const isOver = (b: OpenableBatch) => limit !== undefined && b.defect_rate_produced >= limit
  const [date, setDate] = useState(BASE_DATE)
  const [busy, setBusy] = useState(false)
  const [query, setQuery] = useState('')

  // 불량률 높은 순으로 보인다 (값은 서버 것 그대로, 순서만 바꾼다)
  const rows = [...view.openable_batches].sort((a, b) => b.defect_rate_produced - a.defect_rate_produced)
  const over = rows.filter(isOver)
  const under = rows.filter(b => !isOver(b))
  const shownUnder = query ? under.filter(b => b.batch_id.toLowerCase().includes(query.trim().toLowerCase())) : under
  const allowed = new Set((action?.targets.batch_id as string[] | undefined) ?? [])
  const canOpen = (b: OpenableBatch) => !!action && allowed.has(b.batch_id)

  async function open(batchId: string) {
    setBusy(true)
    try {
      await run('open_incident', { batch_id: batchId, applied_date: date })
    } catch (e) {
      if (!(e instanceof ApiError)) throw e // 오류 줄은 App이 띄운다
    } finally {
      setBusy(false)
    }
  }

  // 기준 미달 배치 한눈에: 서버 값을 세기만 한다
  const stats: [string, string][] = under.length ? [
    ['최고 불량률', fmtSmallRate(Math.max(...under.map(b => b.defect_rate_produced)))],
    ['QC 합격', `${under.filter(b => b.qc_result === '합격').length}개`],
    ['확정 불량 있음', `${under.filter(b => b.confirmed_qty > 0).length}개`],
    ['클레임 1건뿐', `${under.filter(b => b.claim_count === 1).length}개`],
  ] : []

  return (
    <div className="space-y-4">
      {/* 제목 줄: 요약 문장 + 적용일 (ui-guide.md "사건이 없을 때", v14) */}
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <BoxLabel>사건 열기</BoxLabel>
          <p className="px-0.5 text-sm text-neutral-600">
            클레임이 있는 배치 <b className="text-neutral-900">{rows.length}개</b>
            {thr && <> 중 <b className={over.length ? 'text-red-700' : 'text-neutral-900'}>회수 기준({thr.description}) 이상 {over.length}개</b></>}.{' '}
            {action ? '배치를 골라 사건을 엽니다.' : '이 역할은 사건을 열 수 없습니다'}
          </p>
        </div>
        {action && (
          <label className="flex items-center gap-2 text-xs text-neutral-500">
            적용일
            <input
              type="date"
              value={date}
              onChange={e => setDate(e.target.value)}
              className="rounded-md bg-white border border-neutral-300 px-3 h-9 text-sm tabular-nums text-neutral-900 focus:border-indigo-600 focus:outline-none"
            />
          </label>
        )}
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        {/* 왼쪽 2/3: 기준 초과 배치는 큰 카드 */}
        <div className="grid gap-4 sm:grid-cols-2 lg:col-span-2">
          {over.map(b => (
            <article key={b.batch_id} title={b.evidence.join('\n')} className="flex flex-col rounded-lg border-2 border-red-300 bg-white p-5 shadow-lg/20">
              <div className="flex items-center justify-between gap-2">
                <span className="font-mono text-lg font-semibold text-neutral-900">{b.batch_id}</span>
                <span className="rounded bg-red-100 px-2 py-0.5 text-xs text-red-800">기준 초과</span>
              </div>
              <p className="text-xs text-neutral-500">
                {b.product_id} · 생산 {b.production_date} · QC <span className={b.qc_result === '보류' ? 'font-medium text-amber-700' : ''}>{b.qc_result}</span>
              </p>
              <p className="mt-3 text-5xl font-semibold tabular-nums text-red-700">{fmtRate(b.defect_rate_produced / 100)}</p>
              {limit !== undefined && (
                <div className="mt-3">
                  <RateBar rate={b.defect_rate_produced} threshold={limit} over />
                  <p className="mt-1 text-xs text-neutral-500">세로선 = 회수 기준 {limit}%</p>
                </div>
              )}
              <div className="mt-4 grid grid-cols-3 gap-3">
                {([['클레임', `${b.claim_count}건`], ['확정 불량', fmtQty(b.confirmed_qty)], ['생산 수량', fmtQty(b.produced_qty)]] as const).map(([k, v]) => (
                  <div key={k}>
                    <div className="text-xs text-neutral-500">{k}</div>
                    <div className="text-base font-semibold tabular-nums text-neutral-900">{v}</div>
                  </div>
                ))}
              </div>
              {canOpen(b) && (
                <div className="mt-auto pt-5">
                  {/* 평소에는 외곽선, 마우스를 올리면 행동 색으로 채운다 (ui-guide.md v14) */}
                  <button
                    type="button"
                    onClick={() => open(b.batch_id)}
                    disabled={busy || !date}
                    className="w-full h-10 rounded-md border border-indigo-300 bg-white text-sm font-medium text-indigo-700 transition-colors hover:border-indigo-500 hover:bg-indigo-500 hover:text-white disabled:opacity-40 disabled:pointer-events-none"
                  >
                    {busy ? '실행 중…' : '이 배치로 사건 열기'}
                  </button>
                </div>
              )}
            </article>
          ))}
        </div>

        {/* 오른쪽 1/3: 기준 미달 배치 한눈에 · 사건을 열면 */}
        <aside className="space-y-4">
          {stats.length > 0 && (
            <Card title={<>기준 미달 {under.length}개 <span className="text-xs font-normal text-neutral-500">한눈에</span></>}>
              <div className="grid grid-cols-2 gap-3">
                {stats.map(([k, v]) => (
                  <div key={k}>
                    <div className="text-xs text-neutral-500">{k}</div>
                    <div className="text-lg font-semibold tabular-nums text-neutral-900">{v}</div>
                  </div>
                ))}
              </div>
            </Card>
          )}
          <Card title="사건을 열면">
            <p className="text-xs text-neutral-500">고른 배치의 기점 원료 로트를 쓴 배치를 모두 묶고, 아래 순서로 진행합니다.</p>
            <ol className="space-y-2 text-sm text-neutral-900">
              {STEPS.map(([s, label], n) => (
                <li key={s} className="flex items-center gap-2">
                  <span className="grid h-5 w-5 place-items-center rounded-full border border-neutral-300 text-xs tabular-nums text-neutral-600">{n + 1}</span>
                  {label}
                </li>
              ))}
            </ol>
          </Card>
        </aside>
      </div>

      {/* 아래: 기준 미달 배치 표는 펼친 채로. 줄 끝 버튼으로 사건을 연다 */}
      {under.length > 0 && (
        <Card
          title={<>기준 미달 배치 <span className="text-xs font-normal text-neutral-500">{under.length}개 · 불량률 높은 순</span></>}
        >
          <input
            type="search"
            value={query}
            onChange={e => setQuery(e.target.value)}
            placeholder="배치 ID 검색 (B-02-2508-03)"
            aria-label="배치 ID 검색"
            className="rounded-md bg-white border border-neutral-300 px-3 h-8 w-72 max-w-full text-sm font-mono focus:border-indigo-600 focus:outline-none"
          />
          <div className="max-h-[28rem] overflow-auto">
            <table className="w-full text-sm tabular-nums">
              <thead className="bg-neutral-100 sticky top-0">
                <tr className="text-xs text-neutral-500">
                  <th className="px-2 h-8 text-left font-medium">배치</th>
                  <th className="px-2 text-left font-medium">제품</th>
                  <th className="px-2 text-left font-medium">생산일</th>
                  <th className="px-2 text-left font-medium">QC</th>
                  <th className="px-2 text-right font-medium">클레임</th>
                  <th className="px-2 text-right font-medium">확정 불량</th>
                  <th className="px-2 text-right font-medium">불량률(생산)</th>
                  {action && <th className="w-28" />}
                </tr>
              </thead>
              <tbody>
                {shownUnder.map(b => (
                  <tr key={b.batch_id} title={b.evidence.join('\n')} className="group border-t border-neutral-100 hover:bg-neutral-50">
                    <td className="px-2 h-8 font-mono">{b.batch_id}</td>
                    <td className="px-2">{b.product_id}</td>
                    <td className="px-2">{b.production_date}</td>
                    <td className="px-2">{b.qc_result}</td>
                    <td className="px-2 text-right">{b.claim_count}</td>
                    <td className="px-2 text-right">{fmtQty(b.confirmed_qty)}</td>
                    <td className="px-2 text-right">{fmtSmallRate(b.defect_rate_produced)}</td>
                    {action && (
                      <td className="px-2 text-right">
                        {canOpen(b) && (
                          <button
                            type="button"
                            onClick={() => open(b.batch_id)}
                            disabled={busy || !date}
                            className="text-xs text-indigo-700 opacity-0 group-hover:opacity-100 focus:opacity-100 hover:underline disabled:opacity-40"
                          >
                            사건 열기
                          </button>
                        )}
                      </td>
                    )}
                  </tr>
                ))}
                {shownUnder.length === 0 && (
                  <tr><td colSpan={8} className="px-2 h-10 text-neutral-500">'{query}'에 맞는 배치가 없습니다</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// 사건이 있을 때
// ---------------------------------------------------------------------------

/** 판정 액션: 사건 요약 띠의 주 버튼 (화면에 하나) */
export const JUDGE_ACTIONS = ['submit_agenda', 'committee_decision']
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
          {b.warnings.length > 0 && <span className="inline-flex items-center rounded bg-amber-100 px-2 h-6 text-xs font-medium text-amber-800">경고 {b.warnings.length}건</span>}
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
    batch_ids: { replace: <BatchPick view={view} f={f} /> },
    agenda_summary: {
      replace: <AgendaDraft f={f} ids={ids} facts={facts} />,
    },
  }
}

/** 안건 상신 폼의 배치 고르기: 체크 목록 대신 카드로 그린다. 무엇을 왜 올리는지(불량률, 미상신 일수)가 폼 안에서 보인다 (ui-guide.md v10).
 *  값은 배치 카드와 같은 서버 계산값이다 */
function BatchPick({ view, f }: { view: OpenView; f: FormApi }) {
  const ids = targetIds(view, 'submit_agenda', 'batch_ids') ?? []
  const sel = new Set((f.values.batch_ids as string[] | undefined) ?? [])
  const batches = view.batches.filter(b => ids.includes(b.id))
  if (batches.length === 0) return <span className="text-sm text-neutral-500">후보 없음</span>
  return (
    <div className="flex flex-wrap gap-2">
      {batches.map(b => {
        const on = sel.has(b.id)
        const days = b.metrics.days_unsubmitted
        return (
          <label key={b.id} className={`flex min-w-56 flex-1 cursor-pointer items-center gap-3 rounded-lg border px-3 py-2.5 ${on ? 'border-indigo-300 bg-indigo-50' : 'border-neutral-200 bg-white hover:bg-neutral-50'}`}>
            <input
              type="checkbox"
              className="h-4 w-4 accent-indigo-600"
              checked={on}
              onChange={e => f.setValues({ batch_ids: ids.filter(id => (id === b.id ? e.target.checked : sel.has(id))) })}
            />
            <span className="flex-1">
              <span className="block font-mono text-sm text-neutral-900">{b.id}</span>
              {days != null
                ? <span className="block text-xs font-medium text-red-700"><span className="tabular-nums">{days}</span>일 미상신</span>
                : <span className="block text-xs text-neutral-600">{b.state ?? '—'}</span>}
            </span>
            <span className={`text-xl font-semibold tabular-nums ${b.metrics.over_threshold ? 'text-red-700' : 'text-neutral-900'}`}>{fmtRate(b.metrics.defect_rate)}</span>
          </label>
        )
      })}
    </div>
  )
}

/** 안건 요약 입력. 작은 입력 칸 없이, 큰 편집 창에서만 쓰고 고친다.
 *  "이 내용 사용"을 누르면 AI 초안을 넣고 창을 띄운다. AI 없이 쓸 때는 버튼으로 창을 연다.
 *  창의 글은 폼 값이다. 취소하면 창만 닫히고 쓴 글은 폼에 남는다 */
function AgendaDraft({ f, ids, facts }: { f: FormApi; ids: string[]; facts: ReactNode }) {
  const [editing, setEditing] = useState(false)
  const text = String(f.values.agenda_summary ?? '').trim()
  return (
    <>
      {/* 두 버튼은 한 줄에 둔다. AI 초안이 나오면 초안 블록이 줄을 다 쓰고 버튼은 아래로 내려간다 */}
      <div className="flex flex-wrap items-center gap-x-2 gap-y-3">
        <AiDraft
          task="agenda_summary"
          params={{ batch_ids: ids }}
          label="AI로 안건 요약"
          disabledReason={ids.length === 0 ? '배치를 먼저 고르세요' : undefined}
          render={o => <AgendaOutput output={o} facts={facts} />}
          onUse={(o, logId) => { f.setValues({ agenda_summary: agendaText(o), ai_log_id: logId }); setEditing(true) }}
        />
        <Button variant="secondary" onClick={() => setEditing(true)}>{text ? '안건 요약 고치기' : '안건 요약 직접 쓰기'}</Button>
        <span className="text-xs text-neutral-500">{text ? `작성됨 · ${text.length}자` : '비어 있음'}</span>
      </div>
      <ConfirmDialog
        open={editing}
        wide
        title="안건 요약 확인·수정"
        confirmLabel="안건 상신 실행"
        busy={f.busy}
        confirmDisabled={!text}
        note={f.error ?? '고친 글이 안건 요약으로 위원회에 올라갑니다.'}
        onConfirm={f.submit}
        onCancel={() => setEditing(false)}
      >
        <textarea
          aria-label="안건 요약"
          value={String(f.values.agenda_summary ?? '')}
          onChange={e => f.setValues({ agenda_summary: e.target.value })}
          className="w-full h-[60vh] rounded-md bg-white border border-neutral-300 px-3 py-2 text-sm leading-relaxed text-neutral-900 focus:border-indigo-600 focus:outline-none"
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

/** 판정이 끝나 작업 회신이 주가 되는 사건 상태. 이때 본문은 작업 목록이 왼쪽 큰 칸을 쓰고 배치 카드는 한 줄로 접는다 (ui-guide.md v6) */
const TASK_STAGES = ['회수진행', '복구계획확정']

/** 출하처가 아직 확인되지 않은 관계의 확인 수준 */

/** 건수 칸. 칸 크기는 내용에 맞춘다 (같은 너비로 늘리지 않는다, ui-guide.md v7) */
function Tile({ label, value, unit, tone }: { label: string; value: number; unit: string; tone?: string }) {
  return (
    <div className={`inline-flex items-baseline gap-2 rounded-md px-3 py-1.5 ${tone ?? 'bg-neutral-100 text-neutral-900'}`}>
      <span className="text-xs">{label}</span>
      <span className="text-lg font-semibold tabular-nums">
        {value}<span className="ml-1 text-sm font-normal">{unit}</span>
      </span>
    </div>
  )
}

/** 위원회 결정 창의 판단 근거: 화면이 창에 가려지므로 결정 대상 배치의 숫자·경고와 상신된 안건 요약을 창 안에 다시 보인다 (ui-guide.md v4) */
function CommitteeEvidence({ view }: { view: OpenView }) {
  const ids = targetIds(view, 'committee_decision', 'batch_ids') ?? []
  const batches = view.batches.filter(b => ids.includes(b.id))
  const unconfirmed = unconfirmedCustomers(view)
  const agenda = [...view.log.actions].reverse().find(a => a.action === 'submit_agenda')
  const summary = String(agenda?.inputs.agenda_summary ?? '').trim()
  // 선택 버튼이 창의 첫 화면에 들어오도록 요약은 첫 줄(요지)만 보이고, 나머지는 눌러서 편다 (ui-guide.md v5)
  const [full, setFull] = useState(false)
  const [first, ...rest] = summary.split('\n')
  const hasMore = rest.some(l => l.trim())
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
          <div className="space-y-1">
            <span className={`block whitespace-pre-line ${summary ? '' : 'text-neutral-500'}`}>{(full ? summary : first) || '안건 요약 없이 상신됨'}</span>
            {hasMore && (
              <button type="button" aria-expanded={full} onClick={() => setFull(v => !v)} className="text-xs text-neutral-500 underline hover:text-neutral-900">
                {full ? '요약 접기' : `요약 전문 보기 (${summary.length}자)`}
              </button>
            )}
          </div>
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
          {n > 0 && <span className={`h-px w-8 ${n <= cur ? 'bg-indigo-500' : 'bg-neutral-300'}`} />}
          {n < cur
            ? <Check size={16} strokeWidth={1.5} className="text-indigo-500" aria-label="지남" />
            : <span className={`h-2.5 w-2.5 rounded-full border ${n === cur ? 'border-indigo-500 bg-indigo-500 ring-4 ring-indigo-100' : 'border-neutral-400'}`} />}
          <span className={n === cur ? 'font-semibold text-indigo-800' : n < cur ? 'text-neutral-700' : 'text-neutral-500'}>{label}</span>
          {n === cur && note && <span className="text-amber-700">({note})</span>}
        </li>
      ))}
    </ol>
  )
}

/** 안건 상신 폼 박스의 머리 띠와 아래 띠 (ui-guide.md v10). 실행 뒤 배치 상태는 액션 정의의 effect(배치 → 상신중)와 같다 */
const AGENDA_FORM_HEAD: Pick<ActionItem, 'title' | 'subtitle' | 'icon' | 'outcome'> = {
  title: '품질위원회에 안건 상신',
  subtitle: `${STEPS[0][1]} → ${STEPS[1][1]}`,
  icon: <Gavel size={20} strokeWidth={1.5} aria-hidden="true" />,
  outcome: f => {
    const n = ((f.values.batch_ids as string[] | undefined) ?? []).length
    return n > 0
      ? <>배치 <span className="font-semibold tabular-nums">{n}개</span>가 <span className="font-semibold">상신중</span>으로 바뀌고, 품질위원회의 결정을 기다립니다</>
      : '배치를 먼저 고르세요'
  },
}
const INPUT_ICONS: Record<string, ReactNode> = {
  register_claim: <MessageSquareWarning size={20} strokeWidth={1.5} aria-hidden="true" />,
  register_news: <Newspaper size={20} strokeWidth={1.5} aria-hidden="true" />,
}

/** 사건 요약 띠: 지금 상태 한 문장 → 건수 4개 → 이 역할이 할 수 있는 액션. 건수는 뷰의 항목을 센 것이고 수량은 다시 계산하지 않는다 */
function IncidentSummary({ view }: { view: OpenView }) {
  const over = view.batches.filter(b => b.metrics.over_threshold)
  const thr = view.batches[0]?.metrics.threshold.description
  const unconfirmed = new Set(unconfirmedCustomers(view))
  const openTasks = view.tasks.filter(t => t.state === '열림').length
  const judge = view.available_actions.find(a => JUDGE_ACTIONS.includes(a.action))
  const slotsOf = (a: string) => (a === 'submit_agenda' ? agendaSlots(view) : undefined)
  const head = headline(view, over.length, thr)
  // 이 역할이 지금 할 일: 판정 → 재공급 계획 결정 → 회신 입력 순으로 하나만 적는다. 서버가 준 가능한 액션에서 읽는다
  const replyIds = new Set(targetIds(view, 'apply_reply', 'task_id') ?? [])
  const mine = view.tasks.filter(t => replyIds.has(t.id))
  const firstDue = mine.map(t => t.due_date).filter(d => d !== null).sort()[0]
  const planCount = targetIds(view, 'plan_decision', 'plan_id')?.length ?? 0
  const next = judge ? `이 역할이 지금 할 일: ${judge.label}`
    : planCount > 0 ? '이 역할이 지금 할 일: 재공급 계획 결정 (재공급 계획 탭)'
    : mine.length > 0 ? `이 역할이 지금 할 일: 회신 입력 ${mine.length}건${firstDue ? ` · 가장 이른 기한 ${fmtDate(firstDue)}` : ''}`
    : openTasks > 0 ? `열린 작업 ${openTasks}건의 회신을 기다리는 중` : '이 역할이 지금 할 판정은 없습니다'
  // 다른 역할의 결정을 기다리는 중이면 누구 차례인지와 역할을 바꾸는 곳을 적는다.
  // 차례는 객체 상태(배치 상신중, 계획 초안)와 액션 정의의 역할에서 읽는다
  const { actor, ontology } = useApp()
  const waitFor = [
    { action: 'committee_decision', on: view.batches.some(b => b.state === '상신중'), where: '' },
    { action: 'plan_decision', on: view.plans.some(p => p.state === '초안'), where: ' · 재공급 계획 탭' },
  ].filter(w => w.on && !ontology.actions[w.action].roles.includes(actor))
  const recall = view.batches.filter(b => RECALL_STATES.includes(b.state ?? '')).length
  // 버튼을 누르면 폼은 띠의 오른쪽 빈 칸에 열린다 (ui-guide.md v9)
  const [formSlot, setFormSlot] = useState<HTMLDivElement | null>(null)

  return (
    <section className="space-y-2">
      <BoxLabel>사건 현황</BoxLabel>
      <div className="rounded-lg bg-white border-2 border-neutral-300 shadow-lg/20 p-5">
      <div className="flex flex-wrap items-start gap-x-6 gap-y-4">
      {/* 왼쪽: 상황과 버튼 */}
      <div className="min-w-0 max-w-xl space-y-4">
      <div className="space-y-1">
        <StatusBadge state={view.incident.status} />
        <div className="text-2xl font-semibold text-neutral-900">{head.title}</div>
        <div className="text-sm text-neutral-500">{next}</div>
        {waitFor.map(w => {
          const role = ontology.roles[ontology.actions[w.action].roles[0]].name
          return (
            <div key={w.action} data-role-hint className="text-sm text-neutral-700">
              다음 결정: <span className="font-semibold">{role}</span> ({ontology.actions[w.action].name}{w.where}). 화면 위 <span className="font-semibold">역할</span> 상자에서 {role} 역할을 고르면 입력할 수 있습니다
            </div>
          )
        })}
      </div>
      <Steps status={view.incident.status} note={head.note} />
      <div className="flex flex-wrap gap-2">
        {TASK_STAGES.includes(view.incident.status)
          ? <Tile label="회수 중 배치" value={recall} unit={`/ ${view.batches.length}`} />
          : <Tile label="기준 초과 배치" value={over.length} unit={`/ ${view.batches.length}`} tone={over.length > 0 ? 'bg-red-100 text-red-800' : undefined} />}
        <Tile label="관련 고객" value={view.customers.length} unit="곳" />
        <Tile label="출하처 미확인 고객" value={unconfirmed.size} unit="곳" tone={unconfirmed.size > 0 ? 'bg-amber-100 text-amber-800' : undefined} />
        <Tile label="열린 작업" value={openTasks} unit="건" tone={openTasks > 0 ? 'bg-sky-100 text-sky-800' : undefined} />
      </div>
      <ActionBar formTarget={formSlot} groups={[
        { title: '판정', items: JUDGE_ACTIONS.map(action => ({
          action, primary: true, slots: slotsOf(action),
          before: action === 'committee_decision' ? <CommitteeEvidence view={view} /> : undefined,
          ...(action === 'submit_agenda' ? AGENDA_FORM_HEAD : {}),
        })) },
        { title: '새 입력', items: INPUT_ACTIONS.map(action => ({ action, icon: INPUT_ICONS[action] })) },
      ]} />
      </div>
      {/* 오른쪽: 열린 폼 자리. 비어 있으면 자리를 차지하지 않는다. 화면이 좁으면 아래로 내려간다.
          AI 초안이 나오면 글이 길어 좁은 칸에 두면 왼쪽이 비므로, 그때만 아래 줄 전체를 쓴다 */}
      <div ref={setFormSlot} data-form-slot className="min-w-[26rem] flex-1 empty:hidden has-[[data-ai-draft]]:basis-full" />
      </div>
      </div>
    </section>
  )
}

function OpenIncident({ view, flashIds, flashKey }: { view: OpenView; flashIds: Set<string>; flashKey: number | null }) {
  const { ontology, openNetwork } = useApp()
  const incidentWarnings = view.warnings.filter(w => w.target.type !== 'batch')
  const recent = view.log.actions.slice(-5).reverse()
  const taskStage = TASK_STAGES.includes(view.incident.status)
  const unconfirmed = unconfirmedCustomers(view)
  const noticeTypes = noticeTaskTypes(ontology)
  const hasRecall = view.batches.some(b => RECALL_STATES.includes(b.state ?? ''))
  // 기준 초과 배치를 먼저, 크게. 기준 미달이고 미확정 클레임이 없는 배치는 한 줄로 접는다.
  // 작업 단계에서는 판정이 끝났으므로 기준 초과 배치도 접는다 (미확정 클레임이 있는 배치는 판정할 것이 있어 펼쳐 둔다)
  const batches = [...view.batches].sort((a, b) => Number(b.metrics.over_threshold) - Number(a.metrics.over_threshold))
  const taskList = (
    <TaskList
      tasks={view.tasks}
      replySlots={replySlots(ontology.ai_uninterpretable)}
      taskExtra={t => (noticeTypes.has(t.type) && hasRecall ? (
        <AiDraft task="notice_draft" params={{}} label="AI로 안내문 초안" render={o => <NoticeOutput output={o} />} />
      ) : null)}
    />
  )

  return (
    <div className="space-y-4">
    <IncidentSummary view={view} />
    <div className="grid grid-cols-3 gap-4 items-start">
      {/* 왼쪽 2/3: (작업 단계면 작업 목록 →) 배치 판정 카드 → 연결망 한 줄 → 사건 경고 */}
      <div className="col-span-2 space-y-4">
        {taskStage && taskList}
        {/* 배치 카드는 묶음 하나에 키워드를 한 번만 붙인다 (ui-guide.md v13) */}
        <div className="space-y-2">
          <BoxLabel>배치 <span className="ml-1 text-xs font-normal text-neutral-500 tabular-nums">{batches.length}개</span></BoxLabel>
          <div className="space-y-2">
            {batches.map(b => (
              <BatchCard
                key={b.id}
                batch={b}
                flash={flashIds.has(b.id)}
                flashKey={flashKey}
                compact={b.metrics.pending_qty === 0 && (taskStage || !b.metrics.over_threshold)}
                openOnChange={!taskStage}
                claims={<ClaimSummary claims={view.claims.filter(c => c.batch_id === b.id)} />}
              />
            ))}
          </div>
        </div>
        {/* 연결망은 연결망 탭에 그린다. 여기에는 범위 건수와 출하처 미확인 고객 한 줄만 적는다 (ui-guide.md v16) */}
        <Card title={<>연결망 <span className="ml-1 text-xs font-normal text-neutral-500">원료 로트 → 배치 → 고객 (R4 원료 로트 기반 영향 추적)</span></>}>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
            <span className="tabular-nums text-neutral-700">원료 로트 {view.lots.length}개 → 배치 {view.batches.length}개 → 고객 {view.customers.length}곳</span>
            {unconfirmed.length > 0 && (
              <span className="text-amber-700">출하처 미확인 {unconfirmed.length}곳 (<span className="font-mono">{unconfirmed.join(', ')}</span>)</span>
            )}
            <button type="button" data-open-network onClick={openNetwork} className="ml-auto text-xs text-neutral-500 underline hover:text-neutral-900">
              연결망 탭에서 보기
            </button>
          </div>
        </Card>
        {incidentWarnings.length > 0 && (
          <Card title="사건 경고">
            {incidentWarnings.map(w => (
              <WarningLine key={`${w.code}-${w.target.id}`} rule={w.rule}>{w.message}</WarningLine>
            ))}
          </Card>
        )}
      </div>

      {/* 오른쪽 1/3: 방금 바뀐 것 → (작업 단계가 아니면 작업 목록 →) 최근 기록 */}
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

        {!taskStage && taskList}

        <Card title={<>최근 기록 <span className="ml-1 text-xs font-normal text-neutral-500 tabular-nums">{view.log.actions.length}건</span></>}>
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
