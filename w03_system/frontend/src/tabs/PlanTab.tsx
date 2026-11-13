import { useEffect, useState } from 'react'
import { ActionDialog } from '../components/ActionForm'
import { Button } from '../components/Button'
import { Card } from '../components/Card'
import { actionName, actorName } from '../components/LastChange'
import { SourceBadge } from '../components/SourceBadge'
import { StatusBadge } from '../components/StatusBadge'
import { WarningLine } from '../components/WarningLine'
import { useApp } from '../context'
import { fmtDate, fmtQty } from '../format'
import type { OpenView, Plan, PlanDiff } from '../types'

// 재공급 계획 탭 (ui-guide.md "레이아웃"). 순위·예상 월·지연 개월은 서버(R10, plan_diff)가 계산한 값을 그대로 그린다.
// 계획 줄은 고칠 수 없다. 사람은 결정(승인·거절)만 입력한다 (R12).

const th = 'px-2 h-8 text-left text-xs font-medium text-neutral-500 whitespace-nowrap'
const thNum = `${th} text-right`
const td = 'px-2 py-2 align-top whitespace-nowrap'
const tdNum = `${td} text-right tabular-nums`

/** evidence 중 가정 ID(A-xx)만 */
function assumptionIds(evidence: string[]): string[] {
  return evidence.filter(e => /^A-\d+$/.test(e))
}

type PlanTarget = { id: string; can_approve?: boolean; reason?: string }

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
      <VersionList plans={plans} selected={plan.id} onSelect={setSelectedId} />
      <OrderDropWarning view={view} />
      <div className="grid grid-cols-5 gap-4 items-start">
        <PlanTable view={view} plan={plan} wide={plan.diff.length === 0} />
        {plan.diff.length > 0 && <DiffCard plan={plan} />}
      </div>
      <div className="grid grid-cols-2 gap-4 items-start">
        <SupplyCard plan={plan} />
        <DecisionCard view={view} plan={plan} />
      </div>
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
              ? 'border-neutral-900 bg-neutral-100 text-neutral-900'
              : 'border-neutral-300 bg-white text-neutral-700 hover:bg-neutral-50'}`}
          >
            <span className="font-medium">v{p.version}</span>
            <StatusBadge state={p.state} />
            <span className="text-xs text-neutral-500 tabular-nums">{fmtDate(p.attrs.created_date as string | undefined)}</span>
          </button>
        ))}
      </div>
      {cause && (
        <p className="text-sm text-neutral-700">
          <span className="text-neutral-500">다시 계산된 이유 · </span>
          규칙 <span className="font-mono text-xs">{cause.rules.join(', ')}</span>
          {cause.trigger_action && (
            <> · 계기 {actionName(ontology, cause.trigger_action)}
              {cause.trigger_seq !== null && <span className="text-neutral-500"> (기록 #{cause.trigger_seq})</span>}
              {cause.refs.length > 0 && <span className="font-mono text-xs"> {cause.refs.join(', ')}</span>}
            </>
          )}
          {' · '}이전 버전 <span className="font-mono text-xs">{cause.previous_version ?? '없음'}</span>
        </p>
      )}
    </Card>
  )
}

function OrderDropWarning({ view }: { view: OpenView }) {
  const { ontology } = useApp()
  // 수주 급감 확인 작업 유형 = 정의에서 R10-1이 만드는 작업
  const types = new Set(Object.entries(ontology.task_types).filter(([, d]) => d.rules.includes('R10-1')).map(([k]) => k))
  const open = view.tasks.filter(t => types.has(t.type) && t.state === '열림')
  if (open.length === 0) return null
  const who = open.flatMap(t => t.targets.filter(x => x.type === 'customer').map(x => x.id))
  return (
    <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3">
      <WarningLine rule="R10-1">
        <span className="font-medium">영업 임원 확인 대기 {open.length}건</span>{who.length > 0 && <span className="font-mono text-xs"> ({who.join(', ')})</span>}.
        회신이 오면 새 버전이 만들어질 수 있음
      </WarningLine>
    </div>
  )
}

/** 'YYYY-MM' → 달 번호 */
function monthIndex(ym: string): number {
  const [y, m] = ym.split('-').map(Number)
  return y * 12 + m
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
  // 완료 예상 월 막대: 계획을 만든 달 ~ 마지막 완료 월. 값은 서버가 준 월 그대로다
  const created = plan.attrs.created_date as string | undefined
  const start = created ? monthIndex(created.slice(0, 7)) : null
  const end = Math.max(...plan.lines.map(l => monthIndex(l.attrs.expected_month)))
  const span = start !== null && end > start ? end - start : null
  return (
    <Card title={`계획 v${plan.version} · 고객별 재공급 순서`} className={`${wide ? 'col-span-5' : 'col-span-3'} overflow-x-auto`}>
      <table className="w-full text-sm">
        <thead className="bg-neutral-100">
          <tr>
            <th className={thNum}>순위</th>
            <th className={th}>고객</th>
            <th className={thNum}>수량</th>
            <th className={th}>수량 근거</th>
            <th className={th}>완료 예상 월</th>
            <th className={th}>우선순위 이유</th>
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
                  <span className="ml-1.5 inline-flex items-center rounded px-1.5 h-5 text-[11px] text-amber-700 bg-amber-50"
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
              <td className={td}>{l.attrs.priority_reason}</td>
              {!sameSource && <td className={td}><LineSources line={l} /></td>}
            </tr>
          ))}
        </tbody>
      </table>
      {sameSource && (
        <div className="flex items-center gap-2 text-xs text-neutral-500">
          출처 (모든 줄 같음) <LineSources line={plan.lines[0]} />
        </div>
      )}

      {view.held_customers.length > 0 && (
        <div className="space-y-1.5 border-t border-neutral-200 pt-3">
          <div className="text-xs font-medium text-neutral-500">계획에서 보류된 고객</div>
          {view.held_customers.map(h => (
            <div key={h.customer_id} className="flex flex-wrap items-center gap-2 text-sm">
              <span className="font-mono text-neutral-900">{h.customer_id}</span>
              {h.confirmations.map(c => <StatusBadge key={c} state={c} />)}
              <span>{h.reason}</span>
              <span className="text-xs text-neutral-500">배치 <span className="font-mono">{h.batch_ids.join(', ')}</span></span>
              <span className="font-mono text-xs text-neutral-500">{h.rule}</span>
            </div>
          ))}
        </div>
      )}
    </Card>
  )
}

function changeLabel(d: PlanDiff) {
  if (d.added) return <span className="text-blue-700">새로 추가</span>
  if (d.delay_months === null || d.delay_months === 0) return <span className="text-neutral-500">변화 없음</span>
  if (d.delay_months > 0) {
    return <span className="inline-flex items-center rounded px-2 h-6 text-xs font-medium text-red-700 bg-red-50">{d.delay_months}개월 지연</span>
  }
  return <span className="text-emerald-700">{-d.delay_months}개월 앞당김</span>
}

function DiffCard({ plan }: { plan: Plan }) {
  const base = plan.diff[0]?.base_plan_id
  return (
    <Card title={base ? <>이전 버전과 비교 · 기준 <span className="font-mono">{base}</span></> : '이전 버전과 비교'} className="col-span-2 overflow-x-auto">
      {plan.diff.length === 0 ? (
        <p className="text-sm text-neutral-500">비교할 이전 버전 없음</p>
      ) : (
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
            {plan.diff.map(d => (
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
    </Card>
  )
}

function SupplyCard({ plan }: { plan: Plan }) {
  const c = plan.supply_condition
  const s = plan.slack_capacity
  return (
    <Card title={<>출고 조건 <span className="font-mono">{c.rule}</span></>}>
      <div className="flex flex-wrap items-center gap-2">
        <span className={`inline-flex items-center rounded px-2 h-6 text-xs font-medium ${c.met ? 'text-emerald-700 bg-emerald-50' : 'text-amber-700 bg-amber-50'}`}>
          {c.met ? '충족' : '미충족'}
        </span>
        <span className="text-sm">{c.reason}</span>
        <SourceBadge source={c.source} />
      </div>
      {plan.release_condition && <p className="text-sm text-neutral-500">{plan.release_condition}</p>}
      <dl className="grid grid-cols-[8rem_1fr] gap-y-1.5 text-sm">
        <dt className="text-neutral-500">공급 배치</dt>
        <dd className="flex items-center gap-2">
          <span className="font-mono text-neutral-900">{c.batch_id ?? '—'}</span>
          {plan.supply_batch && <SourceBadge source={plan.supply_batch.source} evidence={plan.supply_batch.evidence} />}
        </dd>
        <dt className="text-neutral-500">원료 로트</dt>
        <dd className="font-mono text-neutral-900">{c.lots.length > 0 ? c.lots.join(', ') : '—'}</dd>
        <dt className="text-neutral-500">QC 결과</dt>
        <dd>{c.qc_result ? <StatusBadge state={c.qc_result} /> : '—'}</dd>
        <dt className="text-neutral-500">월 여유 능력</dt>
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
      </dl>
    </Card>
  )
}

function DecisionCard({ view, plan }: { view: OpenView; plan: Plan }) {
  const { ontology } = useApp()
  const [open, setOpen] = useState(false)
  const decisions = plan.decisions.map(id => view.decisions.find(d => d.id === id)).filter(d => d !== undefined)
  const action = view.available_actions.find(a => a.action === 'plan_decision')
  const target = (action?.targets.plan_id as PlanTarget[] | undefined)?.find(t => t.id === plan.id)

  return (
    <Card title="결정">
      {decisions.length === 0 ? (
        <p className="text-sm text-neutral-500">이 버전에 대한 결정 없음</p>
      ) : (
        <ul className="space-y-2">
          {decisions.map(d => (
            <li key={d.id} className="text-sm space-y-0.5">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-medium text-neutral-900">{d.result}</span>
                <span className="text-neutral-500">{d.decider} · <span className="tabular-nums">{d.applied_date}</span></span>
                <span className="font-mono text-xs text-neutral-500">{d.id}</span>
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
            <WarningLine rule="R11">승인할 수 없는 계획: {target.reason}</WarningLine>
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
          before={target.can_approve === false
            ? <WarningLine rule="R11">승인할 수 없는 계획: {target.reason}</WarningLine>
            : null}
          onDone={() => setOpen(false)}
          onCancel={() => setOpen(false)}
        />
      )}
    </Card>
  )
}
