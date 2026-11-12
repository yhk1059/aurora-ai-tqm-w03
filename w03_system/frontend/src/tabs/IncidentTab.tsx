import { useEffect, useRef, useState } from 'react'
import { ApiError } from '../api'
import { BatchCard } from '../components/BatchCard'
import { Button } from '../components/Button'
import { Card } from '../components/Card'
import { LastChange, actionName, actorName } from '../components/LastChange'
import { WarningLine } from '../components/WarningLine'
import { useApp } from '../context'
import { fmtDate, fmtQty, fmtRate } from '../format'
import type { EmptyView, LastChange as LastChangeT, OpenView, OpenableBatch } from '../types'

// 사건 탭 (ui-guide.md "레이아웃"): 사건이 없으면 사건 열기, 있으면 왼쪽 2/3 배치 카드 · 오른쪽 1/3 바뀐 것·작업·기록.

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
  defect_rate_produced: { name: '불량률(생산)', fmt: v => fmtRate(v as number), num: true },
}

function EmptyIncident({ view }: { view: EmptyView }) {
  const { run } = useApp()
  const action = view.available_actions.find(a => a.action === 'open_incident')
  const [batchId, setBatchId] = useState('')
  const [date, setDate] = useState(BASE_DATE)
  const [busy, setBusy] = useState(false)

  const rows = view.openable_batches
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
                  className={`border-t border-neutral-100 ${action ? 'cursor-pointer hover:bg-neutral-50' : ''} ${batchId === b.batch_id ? 'bg-neutral-100' : ''}`}
                >
                  {columns.map(k => {
                    const col = OPENABLE_COLUMNS[k]
                    const v = (b as Record<string, unknown>)[k]
                    return (
                      <td key={k} className={`px-2 h-8 ${col?.num ? 'text-right' : ''} ${k === 'batch_id' ? 'font-mono' : ''}`}>
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

function OpenIncident({ view, flashIds, flashKey }: { view: OpenView; flashIds: Set<string>; flashKey: number | null }) {
  const { ontology } = useApp()
  const incidentWarnings = view.warnings.filter(w => w.target.type !== 'batch')
  const openTasks = view.tasks.filter(t => t.state === '열림').length
  const recent = view.log.actions.slice(-5).reverse()

  return (
    <div className="grid grid-cols-3 gap-4 items-start">
      {/* 왼쪽 2/3: 배치 판정 카드 → 사건 경고 (연결망은 다음 step) */}
      <div className="col-span-2 space-y-4">
        {view.batches.map(b => (
          <BatchCard key={b.id} batch={b} flash={flashIds.has(b.id)} flashKey={flashKey} />
        ))}
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

        {/* 작업 목록 자리: 다음 step(action-forms)이 회신 입력과 함께 채운다 */}
        <Card title="작업">
          <p className="text-sm text-neutral-700">
            열린 작업 <span className="tabular-nums font-medium text-neutral-900">{openTasks}</span>건
            <span className="text-neutral-500"> / 전체 {view.tasks.length}건</span>
          </p>
        </Card>

        <Card title="최근 기록">
          <ol className="space-y-1">
            {recent.map(r => (
              <li key={r.seq} className="flex gap-2 text-sm">
                <span className="w-8 shrink-0 tabular-nums text-neutral-400">#{r.seq}</span>
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
  )
}
