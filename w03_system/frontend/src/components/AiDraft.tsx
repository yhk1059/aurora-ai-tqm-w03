import { useState, type ReactNode } from 'react'
import { ApiError, runAi } from '../api'
import { useApp } from '../context'
import type { AiResult, AiTask } from '../types'
import { Button } from './Button'

// AI 초안 블록 (ui-guide.md "AI 초안 블록", decisions.md "화면 구현 전 정리 4건" ②).
// 버튼을 눌러야 요청한다. 결과는 화면 상태에만 두고, "이 내용 사용"은 폼만 채운다 (R12: 실행은 사람이 한다).
// 키가 없거나 호출이 실패하면 서버 메시지를 그대로 보인다. 대신 보여줄 예시 응답은 없다.

type Props = {
  task: AiTask
  params: Record<string, unknown>
  /** 요청 버튼 글자 (예: "AI로 안건 요약") */
  label: string
  /** task별 출력 표시 */
  render(output: unknown): ReactNode
  /** 있으면 "이 내용 사용" 버튼이 나온다 */
  onUse?: (output: unknown, logId: number) => void
  /** 이 출력을 쓸 수 있는가 (예: 회신 분류 "해석 불가"는 못 씀). 없으면 늘 쓸 수 있음 */
  canUse?: (output: unknown) => boolean
  /** 요청을 막는 이유 (예: 회신 문장이 비어 있음). 있으면 버튼을 비활성화한다 */
  disabledReason?: string
}

type State =
  | { kind: 'idle' }
  | { kind: 'busy' }
  | { kind: 'done'; res: AiResult }
  | { kind: 'error'; message: string }

export function AiDraft({ task, params, label, render, onUse, canUse, disabledReason }: Props) {
  const { aiAvailable } = useApp()
  const [state, setState] = useState<State>({ kind: 'idle' })
  const [used, setUsed] = useState(false)

  async function request() {
    setState({ kind: 'busy' })
    setUsed(false)
    try {
      setState({ kind: 'done', res: await runAi(task, params) })
    } catch (e) {
      // 422 invalid_input 등: 서버 메시지 그대로
      setState({ kind: 'error', message: e instanceof ApiError ? e.message : String(e) })
    }
  }

  const busy = state.kind === 'busy'
  const requestBtn = (text: string) => (
    <Button variant="secondary" onClick={request} disabled={!aiAvailable || busy || !!disabledReason}>{text}</Button>
  )

  if (state.kind === 'idle' || state.kind === 'busy') {
    return (
      <div className="flex flex-wrap items-center gap-2">
        {requestBtn(label)}
        {!aiAvailable && <span className="text-xs text-neutral-500">AI 키 없음</span>}
        {aiAvailable && busy && <span className="text-xs text-neutral-500">AI가 작성 중…</span>}
        {aiAvailable && !busy && disabledReason && <span className="text-xs text-neutral-500">{disabledReason}</span>}
      </div>
    )
  }

  const res = state.kind === 'done' ? state.res : null
  const ok = res?.ok && res.output != null && res.log_id != null
  const usable = ok && (canUse ? canUse(res!.output) : true)

  return (
    <div className="rounded-lg border border-dashed border-neutral-300 bg-neutral-50 p-4 space-y-3">
      <div className="flex items-center gap-2 text-xs">
        <span className="font-medium text-neutral-700">AI 초안</span>
        {res?.log_id != null && <span className="tabular-nums text-neutral-500">AI 기록 #{res.log_id}</span>}
        <span className="text-neutral-400">검토 후 사용</span>
      </div>

      {ok ? (
        <div className="text-sm text-neutral-700 leading-relaxed">{render(res!.output)}</div>
      ) : (
        <p role="alert" className="text-sm text-red-700">
          {state.kind === 'error' ? state.message : (res?.message ?? 'AI 결과가 없습니다')}
          {res?.error && <span className="ml-1.5 font-mono text-xs text-neutral-500">({res.error})</span>}
        </p>
      )}

      <div className="flex flex-wrap items-center gap-2">
        {usable && onUse && (
          <Button variant="secondary" onClick={() => { onUse(res!.output, res!.log_id!); setUsed(true) }}>
            이 내용 사용
          </Button>
        )}
        {requestBtn('다시 요청')}
        {used && <span className="text-xs text-neutral-500">폼에 넣었습니다. 고친 뒤 실행 버튼으로 실행하세요</span>}
        {!aiAvailable && <span className="text-xs text-neutral-500">AI 키 없음</span>}
        {busy && <span className="text-xs text-neutral-500">AI가 작성 중…</span>}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// task별 출력 표시 (ai/tasks.py 출력 스키마). 숫자를 뽑아 다른 화면 값에 쓰지 않는다.
// ---------------------------------------------------------------------------

type O = Record<string, unknown>
const list = (v: unknown): string[] => (Array.isArray(v) ? v.map(String) : [])

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="space-y-1">
      <div className="text-xs font-medium text-neutral-500">{title}</div>
      {children}
    </div>
  )
}

function Bullets({ items }: { items: string[] }) {
  if (items.length === 0) return <p className="text-neutral-500">—</p>
  return <ul className="list-disc pl-5 space-y-0.5">{items.map((s, i) => <li key={i}>{s}</li>)}</ul>
}

export function AgendaOutput({ output }: { output: unknown }) {
  const o = output as O
  const options = Array.isArray(o.options) ? (o.options as O[]) : []
  return (
    <div className="space-y-3">
      <Section title="요약"><p className="whitespace-pre-line">{String(o.summary ?? '')}</p></Section>
      <Section title="근거"><Bullets items={list(o.evidence)} /></Section>
      <Section title="대안별 영향">
        <ul className="space-y-1">
          {options.map((x, i) => (
            <li key={i}><span className="font-medium text-neutral-900">{String(x.option)}</span> — {String(x.impact)}</li>
          ))}
        </ul>
      </Section>
      <Section title="불확실성"><Bullets items={list(o.uncertainties)} /></Section>
    </div>
  )
}

/** 안건 요약 출력 → 폼의 안건 요약 글 */
export function agendaText(output: unknown): string {
  const o = output as O
  const options = Array.isArray(o.options) ? (o.options as O[]) : []
  return [
    String(o.summary ?? ''),
    '',
    '근거',
    ...list(o.evidence).map(s => `- ${s}`),
    '',
    '대안별 영향',
    ...options.map(x => `- ${String(x.option)}: ${String(x.impact)}`),
    '',
    '불확실성',
    ...list(o.uncertainties).map(s => `- ${s}`),
  ].join('\n')
}

export function ClassifyOutput({ output, uninterpretable }: { output: unknown; uninterpretable: string }) {
  const o = output as O
  const failed = o.result === uninterpretable
  return (
    <div className="space-y-2">
      <Section title="분류 결과"><p className="font-medium text-neutral-900">{String(o.result)}</p></Section>
      <Section title="근거 문장"><p>{String(o.evidence_sentence ?? '—')}</p></Section>
      {o.note ? <Section title="메모"><p>{String(o.note)}</p></Section> : null}
      {failed && <p className="text-amber-700">AI가 분류하지 못했습니다. 담당자가 직접 고르세요</p>}
    </div>
  )
}

export function ReviewOutput({ output }: { output: unknown }) {
  const o = output as O
  return (
    <div className="space-y-2">
      <Section title="결론"><p className="font-medium text-neutral-900">{String(o.conclusion)}</p></Section>
      <Section title="설명"><p className="whitespace-pre-line">{String(o.explanation ?? '')}</p></Section>
    </div>
  )
}

export function NoticeOutput({ output }: { output: unknown }) {
  const o = output as O
  return (
    <div className="space-y-2">
      <Section title="수신 고객"><p className="font-mono">{list(o.recipients).join(', ') || '—'}</p></Section>
      <Section title="안내문 초안"><p className="whitespace-pre-line">{String(o.draft ?? '')}</p></Section>
      <p className="text-xs text-neutral-500">실제 발송은 이 시스템의 범위 밖입니다. 초안만 보입니다.</p>
    </div>
  )
}
