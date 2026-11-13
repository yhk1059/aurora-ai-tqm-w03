import { useState, type ReactNode } from 'react'
import { useApp } from '../context'
import { fmtDate } from '../format'
import type { Task, TaskTarget } from '../types'
import { ActionForm, targetIds, type FormApi, type FieldSlots } from './ActionForm'
import { Button } from './Button'
import { Card } from './Card'
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

function TaskItem({ task, canReply, replySlots, taskExtra }: { task: Task; canReply: boolean } & Pick<Props, 'replySlots' | 'taskExtra'>) {
  const [open, setOpen] = useState(false)
  const by = task.created_by
  // 대상이 고객 하나면 제목 옆에 둔다 (같은 유형의 작업을 구분)
  const only = task.targets.length === 1 && task.targets[0].type === 'customer' ? task.targets[0] : null
  return (
    <li className="space-y-2 border-t border-neutral-100 pt-3 first:border-t-0 first:pt-0">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-mono text-xs text-neutral-500">{task.code ?? task.id}</span>
        <span className="text-sm font-medium text-neutral-900">{task.type}</span>
        {only && <span className="font-mono text-sm text-neutral-900">{only.id}</span>}
        <StatusBadge state={task.state} />
      </div>
      <div className="text-sm text-neutral-700 space-y-1">
        <div className="text-neutral-500">
          <span className="text-neutral-700">{task.department ?? '—'}</span> · 기한 <span className="tabular-nums text-neutral-700">{fmtDate(task.due_date)}</span>
          {by?.rule && <span className="ml-1.5 font-mono text-[11px] text-neutral-400">{by.rule}</span>}
          {by?.decision && <span className="ml-1.5 font-mono text-[11px] text-neutral-400">{by.decision}</span>}
        </div>
        {!only && task.targets.length > 0 && (
          <div className="flex flex-wrap gap-x-3 gap-y-1">
            {task.targets.map(t => <TargetLabel key={`${t.type}-${t.id}`} t={t} />)}
          </div>
        )}
        {task.reply && (
          <div className="space-y-0.5 border-l border-neutral-200 pl-3">
            <span className="block leading-relaxed">{task.reply}</span>
            <span className="block text-xs text-neutral-500">
              결과 <span className="text-neutral-900">{task.result ?? '—'}</span> · <span className="tabular-nums">{fmtDate(task.replied_date)}</span>
            </span>
          </div>
        )}
      </div>
      {taskExtra?.(task)}
      {canReply && !open && <Button variant="secondary" onClick={() => setOpen(true)}>회신 입력</Button>}
      {canReply && open && (
        <div className="rounded-md border border-neutral-200 p-3">
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
    <Card title={`작업 (열림 ${front.length} / 전체 ${tasks.length})`}>
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
