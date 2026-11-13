import { ChevronDown, ChevronRight, TriangleAlert } from 'lucide-react'
import { useEffect, useState, type ReactNode } from 'react'
import type { Batch, Threshold } from '../types'
import { fmtDate, fmtQty, fmtRate } from '../format'
import { SourceBadge } from './SourceBadge'
import { StatusBadge } from './StatusBadge'
import { WarningLine } from './WarningLine'

// 배치 판정 카드 (ui-guide.md "레이아웃" 사건 탭). 위에서 아래로 "지금 상태 → 근거 → 할 수 있는 일".
// 기준 초과 배치는 큰 빨간 숫자와 기준선 막대로 강조하고, compact 배치는 한 줄로 접어 둔다 (ui-guide.md v2).
// 규칙 번호와 출처 배지는 "근거·출처 보기"를 눌러야 나온다.
// 숫자는 모두 서버(rules.batch_metrics) 값이다. 화면은 다시 계산하지 않는다.
type Props = {
  batch: Batch
  /** 클레임 요약 자리 (접을 수 있는 고객별 확정/미확정) */
  claims?: ReactNode
  /** 액션 버튼 자리 */
  actions?: ReactNode
  /** 방금 바뀐 배치면 true. flashKey가 바뀔 때 배경 강조를 1회 한다 */
  flash?: boolean
  flashKey?: number | null
  /** true면 한 줄 요약으로 접어 두고, 누르면 펼친다 */
  compact?: boolean
}

/** 기준값 출처 배지. 가정이면 가정 ID(A-xx)를 배지에, 그 밖의 참조는 근거 설명에 둔다 */
function ThresholdSource({ threshold }: { threshold: Threshold }) {
  const isAssumptionId = /^A-\d+/.test(threshold.ref)
  return (
    <SourceBadge
      source={threshold.source}
      refId={isAssumptionId ? threshold.ref : null}
      note={isAssumptionId ? threshold.description : `${threshold.description} (${threshold.ref})`}
    />
  )
}

function Rule({ id }: { id: string | undefined }) {
  return id ? <span className="ml-1.5 font-mono text-[11px] text-neutral-400">{id}</span> : null
}

function Row({ label, children, rule }: { label: string; children: ReactNode; rule?: string | false }) {
  return (
    <div className="flex items-baseline gap-3 text-sm">
      <dt className="w-36 shrink-0 text-neutral-500">{label}</dt>
      <dd className="text-neutral-700 tabular-nums">
        {children}
        <Rule id={rule || undefined} />
      </dd>
    </div>
  )
}

/** 불량률 막대: 눈금 끝 = 기준의 1.5배, 세로선 = 회수 기준. 값은 서버 숫자 그대로다 */
function RateBar({ rate, threshold, over }: { rate: number; threshold: number; over: boolean }) {
  const pct = Math.min(rate / (threshold * 1.5), 1) * 100
  return (
    <div className="relative h-2 w-56 max-w-full rounded-full bg-neutral-100" aria-hidden="true">
      <div className={`h-2 rounded-full ${over ? 'bg-red-600' : 'bg-neutral-400'}`} style={{ width: `${pct}%` }} />
      <div className="absolute -top-1 h-4 w-0.5 bg-neutral-900" style={{ left: `${100 / 1.5}%` }} />
    </div>
  )
}

export function BatchCard({ batch, claims, actions, flash = false, flashKey = null, compact = false }: Props) {
  const m = batch.metrics
  const thr = m.threshold
  const over = m.over_threshold
  const [refs, setRefs] = useState(false)
  const r: Record<string, string | false> = refs ? m.rules : {}
  const [open, setOpen] = useState(false)

  // 액션 뒤 바뀐 항목 강조: bg-amber-50 → 흰색, 1초, 1회 (ui-guide.md "애니메이션"). 접힌 배치가 바뀌면 펼친다
  const [lit, setLit] = useState(false)
  useEffect(() => {
    if (!flash) return
    setLit(true)
    setOpen(true)
    const t = setTimeout(() => setLit(false), 30)
    return () => clearTimeout(t)
  }, [flash, flashKey])

  const collapsed = compact && !open
  const Chevron = collapsed ? ChevronRight : ChevronDown

  return (
    <section
      data-batch={batch.id}
      data-collapsed={collapsed ? 'true' : undefined}
      className={`rounded-lg border ${collapsed ? 'px-4 py-2.5' : 'p-4 space-y-3'} ${over ? 'border-red-200' : 'border-neutral-200'} ${lit ? 'bg-amber-50' : 'bg-white transition-colors duration-1000'}`}
    >
      {/* 1. 지금 상태 */}
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-mono text-sm font-medium text-neutral-900">{batch.id}</span>
        <StatusBadge state={batch.state} />
        {collapsed && (
          <>
            <span data-rate className="text-sm tabular-nums text-neutral-900">{fmtRate(m.defect_rate)}</span>
            <span className="text-sm text-neutral-500">기준 미달</span>
            {batch.warnings.length > 0 && (
              <span className="inline-flex items-center gap-1 text-sm text-amber-700">
                <TriangleAlert size={16} strokeWidth={1.5} />
                경고 {batch.warnings.length}건
              </span>
            )}
          </>
        )}
        {refs && (
          <>
            <span className="text-xs text-neutral-500">
              사건에 묶인 이유: {batch.part_of.reason ?? '—'}
            </span>
            <SourceBadge source={batch.part_of.source} evidence={[`PART_OF #${batch.part_of.link_id}`]} />
          </>
        )}
        {compact && (
          <button
            type="button"
            aria-expanded={!collapsed}
            onClick={() => setOpen(o => !o)}
            className="ml-auto inline-flex items-center gap-1 text-xs text-neutral-500 hover:text-neutral-900"
          >
            <Chevron size={16} strokeWidth={1.5} />
            {collapsed ? '펼치기' : '접기'}
          </button>
        )}
      </div>

      {!collapsed && (
        <>
          {/* 2. 핵심 숫자: 불량률과 회수 기준 */}
          <div className="flex flex-wrap items-start gap-x-8 gap-y-3">
            <div className="space-y-2">
              <div className="text-xs font-medium text-neutral-500">
                불량률 (확정 ÷ 생산)<Rule id={r.defect_rate || undefined} />
              </div>
              <div className="flex items-baseline gap-2">
                <span data-rate className={`font-semibold tabular-nums leading-none ${over ? 'text-5xl text-red-700' : 'text-3xl text-neutral-900'}`}>
                  {fmtRate(m.defect_rate)}
                </span>
                <StatusBadge state={over ? '기준 초과' : '기준 미달'} />
              </div>
              {thr.value !== undefined && thr.unit === '%' && <RateBar rate={m.defect_rate} threshold={thr.value / 100} over={over} />}
              <div className="flex flex-wrap items-center gap-2 text-xs text-neutral-500 tabular-nums">
                <span>
                  회수 기준 {thr.description}
                  <Rule id={r.over_threshold || undefined} />
                </span>
                {refs && (
                  <>
                    <ThresholdSource threshold={thr} />
                    <SourceBadge source={m.source} note="rules.batch_metrics에서 계산한 파생 값" />
                  </>
                )}
              </div>
            </div>

            {/* 3. 근거 줄 (값이 없으면 줄을 그리지 않는다) */}
            <dl className="space-y-1 pt-1">
        <Row label="확정 불량 / 생산" rule={r.confirmed_qty}>
          {fmtQty(m.confirmed_qty)} / {fmtQty(m.produced_qty)}
        </Row>
        {m.defect_rate_shipped !== null && (
          <Row label="출하 기준 불량률" rule={r.defect_rate_shipped}>
            {fmtRate(m.defect_rate_shipped)} <span className="text-neutral-400">(참고)</span>
          </Row>
        )}
        {m.threshold_crossed_date !== null && (
          <Row label="기준 초과일" rule={r.threshold_crossed_date}>{fmtDate(m.threshold_crossed_date)}</Row>
        )}
        {m.days_unsubmitted !== null && (
          <Row label="미상신 경과" rule={r.days_unsubmitted}>기준 초과 후 {m.days_unsubmitted}일 미상신</Row>
        )}
        {m.pending_qty > 0 && (
          <Row label="미확정 클레임" rule={r.pending_qty}>{fmtQty(m.pending_qty)}</Row>
        )}
        {m.rate_if_confirmed !== null && (
          <Row label="확정 시 불량률" rule={r.rate_if_confirmed}>
            {fmtRate(m.rate_if_confirmed)} <span className="text-neutral-400">(참고, 판정 불변)</span>
          </Row>
        )}
        {m.last_ship_date !== null && (
          <Row label="마지막 출하일" rule={r.last_ship_date}>{fmtDate(m.last_ship_date)}</Row>
        )}
        {m.release_due_date !== null && (
          <Row label="관찰 해제 예정일" rule={r.release_due_date}>
            {fmtDate(m.release_due_date)}
            {m.release_basis && <span className="text-neutral-500"> ({m.release_basis} 기준)</span>}
          </Row>
        )}
        {m.release_due_date === null && m.release_basis !== null && (
          <Row label="관찰 해제" rule={r.release_basis}>{m.release_basis}</Row>
        )}
            </dl>
          </div>

          {/* 4. 경고 */}
          {batch.warnings.length > 0 && (
            <div className="space-y-1">
              {batch.warnings.map(w => (
                <WarningLine key={`${w.code}-${w.message}`} rule={refs ? w.rule : null}>{w.message}</WarningLine>
              ))}
            </div>
          )}

          {/* 5. 클레임 요약 */}
          {claims}

          <button type="button" aria-expanded={refs} onClick={() => setRefs(v => !v)} className="text-xs text-neutral-500 hover:text-neutral-900">
            {refs ? '근거·출처 숨기기' : '근거·출처 보기'}
          </button>

          {/* 6. 할 수 있는 일 */}
          {actions && <div className="flex flex-wrap gap-2 pt-1">{actions}</div>}
        </>
      )}
    </section>
  )
}
