import { useEffect, useState, type ReactNode } from 'react'
import type { Batch, Threshold } from '../types'
import { fmtDate, fmtQty, fmtRate } from '../format'
import { SourceBadge } from './SourceBadge'
import { StatusBadge } from './StatusBadge'
import { WarningLine } from './WarningLine'

// 배치 판정 카드 (ui-guide.md "레이아웃" 사건 탭). 위에서 아래로 "지금 상태 → 근거 → 할 수 있는 일".
// 숫자는 모두 서버(rules.batch_metrics) 값이다. 화면은 다시 계산하지 않는다.
type Props = {
  batch: Batch
  /** 액션 버튼 자리 (다음 step이 채운다) */
  actions?: ReactNode
  /** 방금 바뀐 배치면 true. flashKey가 바뀔 때 배경 강조를 1회 한다 */
  flash?: boolean
  flashKey?: number | null
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

function Row({ label, children, rule }: { label: string; children: ReactNode; rule?: string }) {
  return (
    <div className="flex items-baseline gap-3 text-sm">
      <dt className="w-36 shrink-0 text-neutral-500">{label}</dt>
      <dd className="text-neutral-700 tabular-nums">
        {children}
        <Rule id={rule} />
      </dd>
    </div>
  )
}

export function BatchCard({ batch, actions, flash = false, flashKey = null }: Props) {
  const m = batch.metrics
  const r = m.rules
  const thr = m.threshold

  // 액션 뒤 바뀐 항목 강조: bg-amber-50 → 흰색, 1초, 1회 (ui-guide.md "애니메이션")
  const [lit, setLit] = useState(false)
  useEffect(() => {
    if (!flash) return
    setLit(true)
    const t = setTimeout(() => setLit(false), 30)
    return () => clearTimeout(t)
  }, [flash, flashKey])

  return (
    <section
      className={`rounded-lg border border-neutral-200 p-4 space-y-3 ${lit ? 'bg-amber-50' : 'bg-white transition-colors duration-1000'}`}
    >
      {/* 1. 지금 상태 */}
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-mono text-sm text-neutral-900">{batch.id}</span>
        <StatusBadge state={batch.state} />
        <span className="text-xs text-neutral-500">
          사건에 묶인 이유: {batch.part_of.reason ?? '—'}
        </span>
        <SourceBadge source={batch.part_of.source} evidence={[`PART_OF #${batch.part_of.link_id}`]} />
      </div>

      {/* 2. 핵심 숫자: 불량률과 회수 기준 */}
      <div className="flex flex-wrap items-end gap-x-4 gap-y-2">
        <div>
          <div className="text-xs font-medium text-neutral-500">
            불량률 (확정 ÷ 생산)<Rule id={r.defect_rate} />
          </div>
          <div className="text-2xl font-medium tabular-nums text-neutral-900">{fmtRate(m.defect_rate)}</div>
        </div>
        <div className="flex items-center gap-2 pb-1">
          <StatusBadge state={m.over_threshold ? '기준 초과' : '기준 미달'} />
          <span className="text-sm text-neutral-700 tabular-nums">
            회수 기준 {thr.description}
            <Rule id={r.over_threshold} />
          </span>
          <ThresholdSource threshold={thr} />
          <SourceBadge source={m.source} note="rules.batch_metrics에서 계산한 파생 값" />
        </div>
      </div>

      {/* 3. 근거 줄 (값이 없으면 줄을 그리지 않는다) */}
      <dl className="space-y-1">
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

      {/* 4. 경고 */}
      {batch.warnings.length > 0 && (
        <div className="space-y-1">
          {batch.warnings.map(w => (
            <WarningLine key={`${w.code}-${w.message}`} rule={w.rule}>{w.message}</WarningLine>
          ))}
        </div>
      )}

      {/* 5. 할 수 있는 일 */}
      {actions && <div className="flex flex-wrap gap-2 pt-1">{actions}</div>}
    </section>
  )
}
