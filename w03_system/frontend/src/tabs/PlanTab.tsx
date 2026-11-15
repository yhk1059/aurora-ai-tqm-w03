import { useEffect, useState } from 'react'
import { ActionDialog } from '../components/ActionForm'
import { Button } from '../components/Button'
import { Card } from '../components/Card'
import { actionName, actorName } from '../components/LastChange'
import { SourceBadge } from '../components/SourceBadge'
import { StatusBadge } from '../components/StatusBadge'
import { firstDueDate } from '../components/TaskList'
import { WarningLine } from '../components/WarningLine'
import { useApp } from '../context'
import { fmtDate, fmtQty } from '../format'
import type { OpenView, Plan, PlanDiff, Task } from '../types'

// 재공급 계획 탭 (ui-guide.md "레이아웃"). 순위·예상 월·지연 개월은 서버(R10, plan_diff)가 계산한 값을 그대로 그린다.
// 계획 줄은 고칠 수 없다. 사람은 결정(승인·거절)만 입력한다 (R12).
// 위에서 아래로: 결정(이 버전이 무엇을 바꾸는지 한 문장 + 결정 버튼)과 버전 → 표와 비교 → 출고 조건 (ui-guide.md v6, v8).
// 규칙 번호는 글에 쓰지 않고 툴팁에 둔다.

const th = 'px-2 h-8 text-left text-xs font-medium text-neutral-500 whitespace-nowrap'
const thNum = `${th} text-right`
const td = 'px-2 py-2 align-top whitespace-nowrap'
const tdNum = `${td} text-right tabular-nums`

/** evidence 중 가정 ID(A-xx)만 */
function assumptionIds(evidence: string[]): string[] {
  return evidence.filter(e => /^A-\d+$/.test(e))
}

type PlanTarget = {
  id: string
  can_approve?: boolean
  reason?: string
  /** 열린 출하 경위 확인이 있어 승인하려면 근거가 필수 (R11-1, 서버가 정한다) */
  approve_reason_required?: boolean
}

/** 근거 없이 승인하려 할 때 결정 창에 보일 안내 (R11-1, 가정 A-18) */
const HOLD_SHIPMENT_REASON_NOTE = '출하 경위 확인이 끝나지 않아, 승인하려면 근거를 적어야 합니다.'

export function PlanTab() {
  const { view } = useApp()
  if (!view.incident) {
    return <Card title="재공급 계획"><p className="text-sm text-neutral-500">재공급 계획이 아직 없습니다</p></Card>
  }
  return <PlanBody view={view as OpenView} />
}

function PlanBody({ view }: { view: OpenView }) {
  const plans = view.plans
  const latest = plans.length > 0 ? plans[plans.length - 1].id : null
  const [selectedId, setSelectedId] = useState<string | null>(latest)
  // 새 버전이 생기면 가장 최근 버전으로 옮긴다
  useEffect(() => { setSelectedId(latest) }, [latest])

  if (plans.length === 0) {
    return <Card title="재공급 계획"><p className="text-sm text-neutral-500">재공급 계획이 아직 없습니다</p></Card>
  }
  const plan = plans.find(p => p.id === selectedId) ?? plans[plans.length - 1]

  return (
    <div className="space-y-4">
      {/* 결정(왼쪽 2/3)과 버전(오른쪽 1/3)을 나란히 둔다 (ui-guide.md v8) */}
      <div className="grid grid-cols-3 gap-4 items-start">
        <DecisionCard view={view} plan={plan} />
        <VersionList plans={plans} selected={plan.id} onSelect={setSelectedId} />
      </div>
      <OrderDropWarning view={view} />
      <HoldShipmentWarning view={view} />
      <div className="grid grid-cols-5 gap-4 items-start">
        <PlanTable view={view} plan={plan} wide={plan.diff.length === 0} />
        {plan.diff.length > 0 && <DiffCard plan={plan} />}
      </div>
      <SupplyCard plan={plan} />
    </div>
  )
}

function VersionList({ plans, selected, onSelect }: { plans: Plan[]; selected: string; onSelect: (id: string) => void }) {
  const { ontology } = useApp()
  const cur = plans.find(p => p.id === selected)!
  const cause = cur.recalc_cause
  return (
    <Card title="버전">
      <div className="flex flex-wrap gap-2">
        {[...plans].reverse().map(p => (
          <button
            key={p.id}
            type="button"
            onClick={() => onSelect(p.id)}
            className={`inline-flex items-center gap-2 rounded-md border px-2.5 h-9 text-sm ${p.id === selected
              ? 'border-indigo-600 bg-indigo-50 text-neutral-900'
              : 'border-neutral-300 bg-white text-neutral-700 hover:bg-neutral-50'}`}
          >
            <span className="font-medium">v{p.version}</span>
            <StatusBadge state={p.state} />
            <span className="text-xs text-neutral-500 tabular-nums">{fmtDate(p.attrs.created_date as string | undefined)}</span>
          </button>
        ))}
      </div>
      {cause && (
        // 규칙 번호와 이벤트 ID는 글에서 빼고 툴팁에 둔다. 전체는 기록 탭에서 본다 (ui-guide.md v5)
        <p className="text-sm text-neutral-700" title={[`규칙 ${cause.rules.join(', ')}`, ...cause.refs].join(' · ')}>
          <span className="text-neutral-500">다시 계산된 이유 · </span>
          {cause.trigger_action && (
            <>계기 {actionName(ontology, cause.trigger_action)}
              {cause.trigger_seq !== null && <span className="text-neutral-500"> (기록 #{cause.trigger_seq})</span>}
              {' · '}
            </>
          )}
          이전 버전 <span className="font-mono text-xs">{cause.previous_version ?? '없음'}</span>
        </p>
      )}
    </Card>
  )
}

/** 열린 수주 급감 확인 작업 수와 대상 고객. 작업 유형 = 정의에서 R10-1이 만드는 작업 */
function useOrderDropWaiting(view: OpenView): { count: number; who: string[] } {
  const { ontology } = useApp()
  const types = new Set(Object.entries(ontology.task_types).filter(([, d]) => d.rules.includes('R10-1')).map(([k]) => k))
  const open = view.tasks.filter(t => types.has(t.type) && t.state === '열림')
  return { count: open.length, who: open.flatMap(t => t.targets.filter(x => x.type === 'customer').map(x => x.id)) }
}

function OrderDropWarning({ view }: { view: OpenView }) {
  const { count, who } = useOrderDropWaiting(view)
  if (count === 0) return null
  return (
    <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3" title="규칙 R10-1">
      <WarningLine>
        <span className="font-medium">영업 임원 확인 대기 {count}건</span>{who.length > 0 && <span className="font-mono text-xs"> ({who.join(', ')})</span>}.
        회신이 오면 새 버전이 만들어질 수 있음
      </WarningLine>
    </div>
  )
}

/** 출하 경위 확인 대기 띠 (R11-1). 경고 여부와 건수는 서버 경고(open_hold_shipment_check)를 그대로 쓴다 */
function HoldShipmentWarning({ view }: { view: OpenView }) {
  const w = view.warnings.find(x => x.code === 'open_hold_shipment_check')
  if (!w) return null
  return (
    <div data-hold-shipment className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3" title={`규칙 ${w.rule} · 가정 A-18`}>
      <WarningLine>
        <span className="font-medium">출하 경위 확인 대기 {w.evidence.length}건</span>.
        QC 보류 배치가 출하된 경위가 아직 확인되지 않았습니다. 승인하려면 근거를 적어야 합니다.
      </WarningLine>
    </div>
  )
}

/** 출하 경위 확인 작업 (작업 유형 = 정의에서 R11-1이 쓰는 작업). 열린 것이 있으면 그것, 없으면 마지막 것 */
function useHoldShipmentTask(view: OpenView): Task | undefined {
  const { ontology } = useApp()
  const types = new Set(Object.entries(ontology.task_types).filter(([, d]) => d.rules.includes('R11-1')).map(([k]) => k))
  const tasks = view.tasks.filter(t => types.has(t.type))
  return tasks.find(t => t.state === '열림') ?? tasks[tasks.length - 1]
}

/** 'YYYY-MM' → 달 번호 */
function monthIndex(ym: string): number {
  const [y, m] = ym.split('-').map(Number)
  return y * 12 + m
}

/** 우선순위 이유 앞의 규칙 번호("R10 ②")는 글에서 빼고 툴팁으로 돌린다 */
function splitRule(reason: string): [text: string, rule: string | undefined] {
  const m = reason.match(/^(R\d+(?:-\d+)?(?:\s*[①-⑳])?)\s+(.+)$/)
  return m ? [m[2], `규칙 ${m[1]}`] : [reason, undefined]
}

function Reason({ reason }: { reason: string }) {
  const [text, rule] = splitRule(reason)
  return <span title={rule}>{text}</span>
}

function LineSources({ line }: { line: Plan['lines'][number] }) {
  return (
    <span className="inline-flex gap-1">
      <SourceBadge source={line.source} />
      {assumptionIds(line.evidence).map(a => <SourceBadge key={a} source="가정" refId={a} />)}
    </span>
  )
}

function PlanTable({ view, plan, wide }: { view: OpenView; plan: Plan; wide: boolean }) {
  // 모든 줄의 출처가 같으면 열 대신 표 아래에 한 번만 보인다
  const sourceKey = (l: Plan['lines'][number]) => [l.source, ...assumptionIds(l.evidence)].join('|')
  const sameSource = plan.lines.length > 0 && plan.lines.every(l => sourceKey(l) === sourceKey(plan.lines[0]))
  const sameReason = plan.lines.length > 1 && plan.lines.every(l => l.attrs.priority_reason === plan.lines[0].attrs.priority_reason)
  // 완료 예상 월 막대: 계획을 만든 달 ~ 마지막 완료 월. 값은 서버가 준 월 그대로다
  const created = plan.attrs.created_date as string | undefined
  const start = created ? monthIndex(created.slice(0, 7)) : null
  const end = Math.max(...plan.lines.map(l => monthIndex(l.attrs.expected_month)))
  const span = start !== null && end > start ? end - start : null
  return (
    <Card title={`계획 v${plan.version} · 고객별 재공급 순서`} className={`${wide ? 'col-span-5' : 'col-span-3'} min-w-0`}>
      {/* 가로 스크롤은 표에만 건다. 카드 전체에 걸면 표 아래 출처 배지의 근거 창이 카드 아래에서 잘린다 */}
      <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead className="bg-neutral-100">
          <tr>
            <th className={thNum}>순위</th>
            <th className={th}>고객</th>
            <th className={thNum}>수량</th>
            <th className={th}>수량 근거</th>
            <th className={th}>완료 예상 월</th>
            {!sameReason && <th className={th}>우선순위 이유</th>}
            {!sameSource && <th className={th}>출처</th>}
          </tr>
        </thead>
        <tbody>
          {plan.lines.map(l => (
            <tr key={l.id} className="border-t border-neutral-200">
              <td className={tdNum}>{l.attrs.rank}</td>
              <td className={`${td} font-mono text-neutral-900`}>{l.attrs.customer_id}</td>
              <td className={tdNum}>{fmtQty(l.attrs.qty)}</td>
              <td className={td}>
                {l.attrs.qty_basis}
                {l.attrs.lower_bound && (
                  <span className="ml-1.5 inline-flex items-center rounded px-1.5 h-5 text-[11px] text-amber-800 bg-amber-100"
                    title="실제는 더 많을 수 있음 (R10-2, 가정 A-14)">하한</span>
                )}
              </td>
              <td className={`${td} tabular-nums`}>
                <span className="inline-flex items-center gap-2">
                  {l.attrs.expected_month}
                  {wide && span !== null && start !== null && (
                    <span className="h-2 w-40 rounded-full bg-neutral-100" aria-hidden="true">
                      <span className="block h-2 rounded-full bg-neutral-500" style={{ width: `${((monthIndex(l.attrs.expected_month) - start) / span) * 100}%` }} />
                    </span>
                  )}
                </span>
              </td>
              {!sameReason && <td className={td}><Reason reason={l.attrs.priority_reason} /></td>}
              {!sameSource && <td className={td}><LineSources line={l} /></td>}
            </tr>
          ))}
        </tbody>
      </table>
      </div>
      {(sameReason || sameSource) && (
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-neutral-500">
          {sameReason && <span>우선순위 이유 (모든 줄 같음) <span className="text-neutral-700"><Reason reason={plan.lines[0].attrs.priority_reason} /></span></span>}
          {sameSource && <span className="inline-flex items-center gap-2">출처 (모든 줄 같음) <LineSources line={plan.lines[0]} /></span>}
        </div>
      )}

      {view.held_customers.length > 0 && (
        <div className="space-y-1.5 border-t border-neutral-200 pt-3">
          <div className="text-xs font-medium text-neutral-500">계획에서 보류된 고객</div>
          {view.held_customers.map(h => (
            <div key={h.customer_id} className="flex flex-wrap items-center gap-2 text-sm" title={`규칙 ${h.rule}`}>
              <span className="font-mono text-neutral-900">{h.customer_id}</span>
              {h.confirmations.map(c => <StatusBadge key={c} state={c} />)}
              <span>{h.reason}</span>
              <span className="text-xs text-neutral-500">배치 <span className="font-mono">{h.batch_ids.join(', ')}</span></span>
            </div>
          ))}
        </div>
      )}
    </Card>
  )
}

function changeLabel(d: PlanDiff) {
  if (d.added) return <span className="text-sky-800">새로 추가</span>
  if (d.delay_months === null || d.delay_months === 0) return <span className="text-neutral-500">변화 없음</span>
  if (d.delay_months > 0) {
    return <span className="inline-flex items-center rounded px-2 h-6 text-xs font-medium text-red-800 bg-red-100">{d.delay_months}개월 지연</span>
  }
  return <span className="text-emerald-700">{-d.delay_months}개월 앞당김</span>
}

/** 이전 버전과 달라진 줄 (새로 추가, 앞당김, 지연). 값은 서버의 plan_diff 그대로다 */
function changedRows(plan: Plan): PlanDiff[] {
  return plan.diff.filter(d => d.added || (d.delay_months !== null && d.delay_months !== 0))
}

function DiffCard({ plan }: { plan: Plan }) {
  const base = plan.diff[0]?.base_plan_id
  // 바뀐 줄만 표에 올리고, 그대로인 고객은 한 줄로 묶는다
  const changed = changedRows(plan)
  const same = plan.diff.filter(d => !changed.includes(d))
  return (
    <Card title={base ? <>이전 버전과 비교 · 기준 <span className="font-mono">{base}</span></> : '이전 버전과 비교'} className="col-span-2 min-w-0" boxClassName="overflow-x-auto">
      {plan.diff.length === 0 ? (
        <p className="text-sm text-neutral-500">비교할 이전 버전 없음</p>
      ) : changed.length === 0 ? null : (
        <table className="w-full text-sm">
          <thead className="bg-neutral-100">
            <tr>
              <th className={th}>고객</th>
              <th className={thNum}>순위</th>
              <th className={th}>예상 월</th>
              <th className={th}>변화</th>
            </tr>
          </thead>
          <tbody>
            {changed.map(d => (
              <tr key={d.customer_id} className={`border-t border-neutral-200 ${d.delay_months !== null && d.delay_months > 0 ? 'bg-red-50/50' : ''}`}>
                <td className={`${td} font-mono text-neutral-900`}>{d.customer_id}</td>
                <td className={tdNum}>{d.rank_before ?? '—'} → {d.rank_after ?? '—'}</td>
                <td className={`${td} tabular-nums`}>{d.month_before ?? '—'} → {d.month_after ?? '—'}</td>
                <td className={td}>{changeLabel(d)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {same.length > 0 && (
        <p data-same className="text-sm text-neutral-500">
          변화 없음 {same.length}곳 <span className="font-mono text-xs">{same.map(d => d.customer_id).join(', ')}</span>
        </p>
      )}
    </Card>
  )
}

function SupplyCard({ plan }: { plan: Plan }) {
  const c = plan.supply_condition
  const s = plan.slack_capacity
  return (
    <Card title={<span title={`규칙 ${c.rule}`}>출고 조건</span>}>
      <div className="flex flex-wrap items-center gap-2">
        <span className={`inline-flex items-center rounded px-2 h-6 text-xs font-medium ${c.met ? 'text-emerald-800 bg-emerald-100' : 'text-amber-800 bg-amber-100'}`}>
          {c.met ? '충족' : '미충족'}
        </span>
        <span className="text-sm">{c.reason}</span>
        <SourceBadge source={c.source} />
      </div>
      {plan.release_condition && (() => {
        // 조건 글 끝의 "(R11, 가정 A-10)"은 툴팁으로 돌린다
        const m = plan.release_condition.match(/^(.*?)\s*\(([^()]*(?:R\d|A-\d)[^()]*)\)\s*$/)
        return <p className="text-sm text-neutral-500" title={m?.[2]}>{m ? m[1] : plan.release_condition}</p>
      })()}
      {/* 값이 짧은 항목 4개는 한 줄에 나란히 둔다 (ui-guide.md v8) */}
      <dl className="flex flex-wrap gap-x-8 gap-y-1.5 text-sm font-semibold">
        <div className="flex items-center gap-2">
          <dt className="text-xs font-normal text-neutral-500">공급 배치</dt>
          <dd className="flex items-center gap-2">
            <span className="font-mono text-neutral-900">{c.batch_id ?? '—'}</span>
            {plan.supply_batch && <SourceBadge source={plan.supply_batch.source} evidence={plan.supply_batch.evidence} />}
          </dd>
        </div>
        <div className="flex items-center gap-2">
          <dt className="text-xs font-normal text-neutral-500">원료 로트</dt>
          <dd className="font-mono text-neutral-900">{c.lots.length > 0 ? c.lots.join(', ') : '—'}</dd>
        </div>
        <div className="flex items-center gap-2">
          <dt className="text-xs font-normal text-neutral-500">QC 결과</dt>
          <dd>{c.qc_result ? <StatusBadge state={c.qc_result} /> : '—'}</dd>
        </div>
        <div className="flex items-center gap-2">
          <dt className="text-xs font-normal text-neutral-500">월 여유 능력</dt>
          <dd className="flex items-center gap-2">
            <span className="tabular-nums text-neutral-900">{s ? `${fmtQty(s.value)}/월` : '—'}</span>
            {s && (
              <SourceBadge
                source={s.source}
                refId={s.ref}
                evidence={s.evidence}
                note={`월평균 생산 ${fmtQty(s.monthly_avg_produced)} (${s.months[0]}~${s.months[s.months.length - 1]}) ÷ 가동률 ${s.utilization_pct}% × 여유분`}
              />
            )}
          </dd>
        </div>
      </dl>
    </Card>
  )
}

/** SCM 결정 창의 판단 근거: 창이 계획 표를 가리므로 결정에 필요한 것만 창 안에 다시 보인다 (ui-guide.md v5).
 *  값은 서버가 계산한 계획에서 고른 것이고, 화면은 다시 계산하지 않는다 */
function PlanEvidence({ view, plan }: { view: OpenView; plan: Plan }) {
  const { count, who } = useOrderDropWaiting(view)
  const hold = useHoldShipmentTask(view)
  const holdFirstDue = hold ? firstDueDate(view, hold) : undefined
  const end = plan.lines.map(l => l.attrs.expected_month).sort().pop()
  const changed = changedRows(plan)
  const c = plan.supply_condition
  const row = 'flex flex-wrap items-center gap-x-3 gap-y-1 px-3 py-2'
  const label = 'w-24 shrink-0 text-neutral-500'
  return (
    <div data-evidence className="space-y-1">
      <div className="text-xs text-neutral-500">판단 근거</div>
      <div className="rounded-md border border-neutral-200 divide-y divide-neutral-100">
        <div className={row}>
          <span className={label}>재공급 순서</span>
          <span className="font-mono text-neutral-900">{plan.lines.map(l => l.attrs.customer_id).join(' → ')}</span>
          {end && <span className="text-neutral-500">마지막 완료 예상 <span className="tabular-nums text-neutral-900">{end}</span></span>}
        </div>
        {plan.diff.length > 0 && (
          <div className={row}>
            <span className={label}>이전 버전 대비</span>
            {changed.length === 0
              ? <span className="text-neutral-500">변화 없음</span>
              : changed.map(d => (
                <span key={d.customer_id} className="inline-flex items-center gap-1.5">
                  <span className="font-mono text-neutral-900">{d.customer_id}</span>{changeLabel(d)}
                </span>
              ))}
          </div>
        )}
        <div className={row}>
          <span className={label}>출고 조건</span>
          <span className={`inline-flex items-center rounded px-2 h-6 text-xs font-medium ${c.met ? 'text-emerald-800 bg-emerald-100' : 'text-amber-800 bg-amber-100'}`}>
            {c.met ? '충족' : '미충족'}
          </span>
          <span>{c.reason}</span>
        </div>
        {hold && (
          // 출하 경위 (R11-1): 열림이면 확인 대기 + 기한(연장 표시), 끝났으면 확인됨 + 회신. 회신은 모의 입력이다
          <div data-hold-row={hold.state === '열림' ? 'waiting' : 'done'} className={row} title={`규칙 R11-1 · 가정 A-18 · 작업 ${hold.id}`}>
            <span className={label}>출하 경위</span>
            {hold.state === '열림' ? (
              <span className="text-amber-700">
                <span className="font-medium">확인 대기</span>
                <span className="text-neutral-500"> · 기한 <span className="tabular-nums text-neutral-900">{fmtDate(hold.due_date)}</span></span>
                {holdFirstDue && <span className="ml-1.5 font-medium">연장됨 (처음 기한 <span className="tabular-nums">{fmtDate(holdFirstDue)}</span>)</span>}
              </span>
            ) : (
              <span className="inline-flex items-center rounded px-2 h-6 text-xs font-medium text-emerald-800 bg-emerald-100">확인됨</span>
            )}
            {hold.reply && (
              <span className="inline-flex flex-wrap items-center gap-x-2 gap-y-1 basis-full pl-[6.75rem] text-neutral-700">
                <span className="leading-relaxed">{hold.reply}</span>
                {hold.replied_date && <span className="text-xs text-neutral-500 tabular-nums">{fmtDate(hold.replied_date)}</span>}
                <SourceBadge source="모의" />
              </span>
            )}
          </div>
        )}
        {count > 0 && (
          <div className={row}>
            <span className={label}>확인 대기</span>
            <span className="text-amber-700">영업 임원 확인 대기 {count}건{who.length > 0 && <span className="font-mono text-xs"> ({who.join(', ')})</span>}</span>
          </div>
        )}
      </div>
    </div>
  )
}

/** 이 버전이 무엇을 바꾸는지 한 문장. 이전 버전이 없으면 고객 수만 적는다. 값은 서버의 plan_diff에서 읽는다 */
function planHeadline(plan: Plan): string {
  if (plan.diff.length === 0) return `고객 ${plan.lines.length}곳에 차례로 재공급`
  const changed = changedRows(plan)
  if (changed.length === 0) return '이전 버전과 순서·예상 월이 같음'
  const parts = changed.map(d => {
    if (d.added) return `${d.customer_id} ${d.rank_after}순위로 추가`
    return d.delay_months! > 0 ? `${d.customer_id} ${d.delay_months}개월 지연` : `${d.customer_id} ${-d.delay_months!}개월 앞당김`
  })
  const same = plan.diff.length - changed.length
  return parts.join(', ') + (same > 0 ? ` · 나머지 ${same}곳 변화 없음` : '')
}

function DecisionCard({ view, plan }: { view: OpenView; plan: Plan }) {
  const { ontology } = useApp()
  const [open, setOpen] = useState(false)
  const end = plan.lines.map(l => l.attrs.expected_month).sort().pop()
  const c = plan.supply_condition
  const decisions = plan.decisions.map(id => view.decisions.find(d => d.id === id)).filter(d => d !== undefined)
  const action = view.available_actions.find(a => a.action === 'plan_decision')
  const target = (action?.targets.plan_id as PlanTarget[] | undefined)?.find(t => t.id === plan.id)

  return (
    <Card title="결정" className="col-span-2">
      <div className="space-y-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm font-medium text-neutral-900">계획 v{plan.version}</span>
          <StatusBadge state={plan.state} />
        </div>
        <div data-plan-headline className="text-xl font-semibold text-neutral-900">{planHeadline(plan)}</div>
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-neutral-500">
          {end && <span>마지막 완료 예상 <span className="font-semibold tabular-nums text-neutral-900">{end}</span></span>}
          <span>출고 조건 <span className={c.met ? 'text-emerald-700' : 'text-amber-700'}>{c.met ? '충족' : '미충족'}</span></span>
        </div>
      </div>
      {decisions.length === 0 ? (
        <p className="text-sm text-neutral-500">이 버전에 대한 결정 없음</p>
      ) : (
        <ul className="space-y-2">
          {decisions.map(d => (
            <li key={d.id} className="text-sm space-y-0.5">
              <div className="flex flex-wrap items-center gap-2" title={`결정 ${d.id}`}>
                <span className="font-medium text-neutral-900">{d.result}</span>
                <span className="text-neutral-500">{d.decider} · <span className="tabular-nums">{d.applied_date}</span></span>
                <SourceBadge source={d.source} />
              </div>
              {d.reason && <p className="text-neutral-700 leading-relaxed">{d.reason}</p>}
            </li>
          ))}
        </ul>
      )}

      {target && (
        <div className="space-y-2 border-t border-neutral-200 pt-3">
          {target.can_approve === false && (
            <div title="규칙 R11"><WarningLine>승인할 수 없는 계획: {target.reason}</WarningLine></div>
          )}
          <Button variant="primary" onClick={() => setOpen(true)}>결정 입력</Button>
          <span className="ml-2 text-xs text-neutral-500">
            {(ontology.actions.plan_decision?.roles ?? []).map(r => actorName(ontology, r)).join(', ')} 결정
          </span>
        </div>
      )}
      {open && target && (
        <ActionDialog
          action="plan_decision"
          fixed={{ plan_id: plan.id }}
          before={<>
            <PlanEvidence view={view} plan={plan} />
            {target.can_approve === false && <div title="규칙 R11"><WarningLine>승인할 수 없는 계획: {target.reason}</WarningLine></div>}
          </>}
          reasonRequired={target.approve_reason_required ? { 승인: HOLD_SHIPMENT_REASON_NOTE } : undefined}
          onDone={() => setOpen(false)}
          onCancel={() => setOpen(false)}
        />
      )}
    </Card>
  )
}
