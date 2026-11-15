import { useState, type ReactNode } from 'react'
import { useApp } from '../context'
import { fmtDate, fmtQty } from '../format'
import type { CapacityOption, IncidentView, Task, TaskTarget } from '../types'
import { ActionForm, targetIds, type FormApi, type FieldSlots } from './ActionForm'
import { Button } from './Button'
import { Card } from './Card'
import { SourceBadge } from './SourceBadge'
import { StatusBadge } from './StatusBadge'

// 작업 목록 (사건 탭 오른쪽, view.tasks). 열린 작업 먼저, 그다음 나머지.
// "회신 입력"은 서버가 apply_reply 대상으로 준 작업에만 붙는다.
type Props = {
  tasks: Task[]
  /** 회신 폼의 필드 위·아래 자리 ("AI로 분류" 블록). 폼 값을 읽고 채울 수 있다 */
  replySlots?: (task: Task, form: FormApi) => ReturnType<FieldSlots>
  /** 작업 아래 추가 자리 (안내문 초안 등) */
  taskExtra?: (task: Task) => ReactNode
}

function TargetLabel({ t }: { t: TaskTarget }) {
  const { ontology } = useApp()
  if (t.type === 'SHIPPED_TO') {
    return (
      <span className="inline-flex items-center gap-1.5">
        <span className="font-mono">{t.batch_id} → {t.customer_id}</span>
        <StatusBadge state={t.confirm} />
      </span>
    )
  }
  return (
    <span>
      <span className="text-neutral-500">{ontology.object_types[t.type]?.name ?? t.type} </span>
      <span className="font-mono">{t.id}</span>
    </span>
  )
}

/** 기한이 바뀐 적이 있으면 처음 기한을 액션 기록에서 찾는다 (확인 불가 회신 → 연장, A-17). 열린 작업에만 표시 (ui-guide.md v4).
 *  작업 목록과 재공급 계획 결정 창(출하 경위 줄)이 함께 쓴다 */
export function firstDueDate(view: IncidentView, task: Task): string | undefined {
  if (task.state !== '열림' || !view.incident) return undefined
  return view.log.actions.flatMap(a => a.changes)
    .find(c => c.target.type === 'task' && c.target.id === task.id && c.field === 'due_date' && c.before)?.before as string | undefined
}

function TaskItem({ task, canReply, replySlots, taskExtra }: { task: Task; canReply: boolean } & Pick<Props, 'replySlots' | 'taskExtra'>) {
  const { view } = useApp()
  const [open, setOpen] = useState(false)
  const firstDue = firstDueDate(view, task)
  const overdue = task.state === '열림' && !!task.due_date && !!view.incident && task.due_date < view.incident.current_date
  const by = task.created_by
  // 대상이 고객 하나면 제목 옆에 둔다 (같은 유형의 작업을 구분)
  const only = task.targets.length === 1 && task.targets[0].type === 'customer' ? task.targets[0] : null
  // 작업을 만든 규칙·결정 번호는 글에서 빼고 툴팁에 둔다. 전체는 기록 탭에서 본다 (ui-guide.md v5)
  const origin = [by?.rule && `만든 규칙 ${by.rule}`, by?.decision && `결정 ${by.decision}`].filter(Boolean).join(' · ')
  return (
    <li data-task-state={task.state} className="space-y-2 border-t border-neutral-100 pt-3 first:border-t-0 first:pt-0">
      {/* 작업 한 건은 한 줄이다: 번호·유형·상태 → 담당·기한 → 대상 → 회신 입력. 칸이 좁으면 줄이 바뀐다 (ui-guide.md v8) */}
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 text-sm">
        <div data-task-head className="flex flex-wrap items-center gap-2" title={origin || undefined}>
          {/* 작업 이름이 먼저 읽힌다. 번호는 폼·기록과 같은 작업 번호(T-004)를 상태 뒤에 작게 둔다 (ui-guide.md v11) */}
          <span className="text-[15px] font-semibold text-neutral-900">{task.type}</span>
          {only && <span className="font-mono text-[15px] font-semibold text-neutral-900">{only.id}</span>}
          {/* 열린 작업이 기본이라 '열림'은 배지를 달지 않는다. 기한 지남·연장은 기한 옆에 적는다 (ui-guide.md v21) */}
          {task.state !== '열림' && <StatusBadge state={task.state} />}
          <span className="font-mono text-xs text-neutral-500">{task.id}</span>
        </div>
        <div className="text-xs text-neutral-500">
          {task.department ?? '—'} · 기한 <span className="text-sm font-medium tabular-nums text-neutral-900">{fmtDate(task.due_date)}</span>
          {overdue && <span data-due="overdue" className="ml-1.5 font-medium text-red-700">기한 지남</span>}
          {firstDue && <span data-due="extended" className="ml-1.5 font-medium text-amber-700">연장됨 (처음 기한 <span className="tabular-nums">{fmtDate(firstDue)}</span>)</span>}
        </div>
        {!only && task.targets.length > 0 && (
          <div className="flex flex-wrap gap-x-3 gap-y-1 text-neutral-700">
            {task.targets.map(t => <TargetLabel key={`${t.type}-${t.id}`} t={t} />)}
          </div>
        )}
        {canReply && !open && <Button variant="secondary" className="ml-auto" onClick={() => setOpen(true)}>회신 입력</Button>}
      </div>
      {task.reply && (
        <div className="space-y-0.5 border-l border-neutral-200 pl-3 text-sm text-neutral-700">
          <span className="block leading-relaxed">{task.reply}</span>
          <span className="block text-xs text-neutral-500">
            결과 <span className="text-neutral-900">{task.result ?? '—'}</span> · <span className="tabular-nums">{fmtDate(task.replied_date)}</span>
          </span>
        </div>
      )}
      {Array.isArray(task.attrs.options) && (
        // 능력 확보 검토 (R10-3)의 근거: 서버가 원본(strat_capex_plan_cv)에서 읽어 작업에 붙인 방안 그대로
        <div data-capacity-options className="space-y-1 border-l border-neutral-200 pl-3 text-sm text-neutral-700" title="규칙 R10-3 · 가정 A-19">
          <div className="text-xs text-neutral-500">
            마지막 완료 예상 <span className="tabular-nums text-neutral-900">{String(task.attrs.final_month)}</span> ({String(task.attrs.months)}번째 달, 기준 {String(task.attrs.threshold_months)}개월 초과) · 투자 승인은 CEO/이사회
          </div>
          {(task.attrs.options as CapacityOption[]).map(o => (
            <div key={o.option_id} className="flex flex-wrap items-center gap-x-3 gap-y-1">
              <span className="font-mono text-neutral-900">{o.option_id}</span>
              <span>{o.option_type} · {o.target_line}</span>
              <span className="text-xs text-neutral-500">리드타임 <span className="text-sm tabular-nums text-neutral-900">{o.lead_time_weeks}주</span></span>
              <span className="text-xs text-neutral-500" title="원본에 기간 단위 표기 없음">추가 능력 <span className="text-sm tabular-nums text-neutral-900">{fmtQty(o.added_capacity_qty)}</span></span>
              <span className="text-xs text-neutral-500">투자 <span className="text-sm tabular-nums text-neutral-900">{(o.capex_krw / 1e8).toLocaleString('ko-KR')}억원</span></span>
              <SourceBadge source="원본" evidence={o.evidence} note={o.note} />
            </div>
          ))}
        </div>
      )}
      {taskExtra?.(task)}
      {canReply && open && (
        <div className="rounded-md border border-indigo-300 p-3">
          <ActionForm
            action="apply_reply"
            fixed={{ task_id: task.id }}
            slots={replySlots ? f => replySlots(task, f) : undefined}
            onDone={() => setOpen(false)}
            onCancel={() => setOpen(false)}
          />
        </div>
      )}
    </li>
  )
}

export function TaskList({ tasks, replySlots, taskExtra }: Props) {
  const { view } = useApp()
  const [showDone, setShowDone] = useState(false)
  const replyable = new Set(targetIds(view, 'apply_reply', 'task_id') ?? [])
  // 먼저 보이는 것: 열린 작업과, 끝났어도 할 수 있는 일(안내문 초안 등)이 붙은 작업. 나머지는 접어 둔다
  const front = tasks.filter(t => t.state === '열림')
  const rest = tasks.filter(t => t.state !== '열림')
  const pinned = rest.filter(t => taskExtra?.(t))
  const folded = rest.filter(t => !pinned.includes(t))
  const shown = [...front, ...pinned, ...(showDone ? folded : [])]
  return (
    <Card title={<>작업 <span className="ml-1 text-xs font-normal text-neutral-500 tabular-nums">열림 <span className={front.length > 0 ? 'font-semibold text-sky-800' : ''}>{front.length}</span> / 전체 {tasks.length}</span></>}>
      {tasks.length === 0 ? (
        <p className="text-sm text-neutral-500">작업 없음</p>
      ) : (
        <>
          {shown.length > 0 && (
            <ul className="space-y-3">
              {shown.map(t => (
                <TaskItem key={t.id} task={t} canReply={replyable.has(t.id)} replySlots={replySlots} taskExtra={taskExtra} />
              ))}
            </ul>
          )}
          {folded.length > 0 && (
            <button type="button" aria-expanded={showDone} onClick={() => setShowDone(v => !v)} className="text-xs text-neutral-500 hover:text-neutral-900">
              {showDone ? '끝난 작업 접기' : `끝난 작업 ${folded.length}건 보기`}
            </button>
          )}
        </>
      )}
    </Card>
  )
}
