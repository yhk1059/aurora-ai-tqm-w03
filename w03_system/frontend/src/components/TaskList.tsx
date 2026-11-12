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
  return (
    <li className="space-y-2 border-t border-neutral-100 pt-3 first:border-t-0 first:pt-0">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-mono text-sm text-neutral-900">{task.code ?? task.id}</span>
        <span className="text-sm text-neutral-900">{task.type}</span>
        <StatusBadge state={task.state} />
      </div>
      <dl className="text-sm text-neutral-700 space-y-0.5">
        <div className="flex gap-2"><dt className="w-14 shrink-0 text-neutral-500">담당</dt><dd>{task.department ?? '—'}</dd></div>
        <div className="flex gap-2"><dt className="w-14 shrink-0 text-neutral-500">기한</dt><dd className="tabular-nums">{fmtDate(task.due_date)}</dd></div>
        {task.targets.length > 0 && (
          <div className="flex gap-2">
            <dt className="w-14 shrink-0 text-neutral-500">대상</dt>
            <dd className="flex flex-wrap gap-x-3 gap-y-1">
              {task.targets.map(t => <TargetLabel key={`${t.type}-${t.id}`} t={t} />)}
            </dd>
          </div>
        )}
        {by && (by.rule || by.decision) && (
          <div className="flex gap-2">
            <dt className="w-14 shrink-0 text-neutral-500">근거</dt>
            <dd>
              {by.rule && <span className="font-mono text-xs text-neutral-500">{by.rule}</span>}
              {by.decision && <span className="ml-1.5 font-mono text-xs text-neutral-500">{by.decision}</span>}
            </dd>
          </div>
        )}
        {task.reply && (
          <div className="flex gap-2">
            <dt className="w-14 shrink-0 text-neutral-500">회신</dt>
            <dd className="space-y-0.5">
              <span className="block leading-relaxed">{task.reply}</span>
              <span className="block text-xs text-neutral-500">
                결과 <span className="text-neutral-900">{task.result ?? '—'}</span> · <span className="tabular-nums">{fmtDate(task.replied_date)}</span>
              </span>
            </dd>
          </div>
        )}
      </dl>
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
  const replyable = new Set(targetIds(view, 'apply_reply', 'task_id') ?? [])
  const openOnes = tasks.filter(t => t.state === '열림')
  const rest = tasks.filter(t => t.state !== '열림')
  return (
    <Card title={`작업 (열림 ${openOnes.length} / 전체 ${tasks.length})`}>
      {tasks.length === 0 ? (
        <p className="text-sm text-neutral-500">작업 없음</p>
      ) : (
        <ul className="space-y-3">
          {[...openOnes, ...rest].map(t => (
            <TaskItem key={t.id} task={t} canReply={replyable.has(t.id)} replySlots={replySlots} taskExtra={taskExtra} />
          ))}
        </ul>
      )}
    </Card>
  )
}
