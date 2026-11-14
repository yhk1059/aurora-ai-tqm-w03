import { useState, type ReactNode } from 'react'
import { AlertTriangle } from 'lucide-react'
import { ApiError, runAi } from '../api'
import { useApp } from '../context'
import type { AiResult, AiTask } from '../types'
import { Button } from './Button'
import { SourceBadge } from './SourceBadge'

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
  /** 요청을 시작할 때 부른다 (예: 이전 초안에서 폼에 넣은 값을 비움) */
  onRequest?: () => void
}

type State =
  | { kind: 'idle' }
  | { kind: 'busy' }
  | { kind: 'done'; res: AiResult }
  | { kind: 'error'; message: string }

export function AiDraft({ task, params, label, render, onUse, canUse, disabledReason, onRequest }: Props) {
  const { aiAvailable, refresh } = useApp()
  const [state, setState] = useState<State>({ kind: 'idle' })
  const [used, setUsed] = useState(false)

  async function request() {
    setState({ kind: 'busy' })
    setUsed(false)
    onRequest?.()
    try {
      setState({ kind: 'done', res: await runAi(task, params) })
      void refresh() // 서버가 남긴 AI 기록이 기록 탭에 바로 보이게
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
        <span className="text-neutral-500">검토 후 사용</span>
        {res?.replayed && <span className="text-amber-700">저장된 답 재생 · API 호출 안 함</span>}
      </div>

      {ok ? (
        <div className="max-w-4xl text-sm text-neutral-700 leading-relaxed">{render(res!.output)}</div>
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

// 안건 요약의 구역 색 (ui-guide.md "AI 초안 블록"): 빨강 = 회수, 파랑 = 조사, 주황 = 확인 안 됨.
// 대안 칸의 색은 그 대안을 고른 뒤 배치가 되는 상태의 색이다.
const OPTION_TONE: Record<string, { state: string; card: string; head: string; badge: string }> = {
  '전면 회수': { state: '회수진행', card: 'border-red-200', head: 'bg-red-100', badge: 'bg-red-700 text-white' },
  '부분 회수': { state: '부분회수', card: 'border-red-200', head: 'bg-red-50', badge: 'bg-white border border-red-300 text-red-700' },
  '조사계속': { state: '조사계속', card: 'border-blue-200', head: 'bg-blue-50', badge: 'bg-blue-700 text-white' },
}
const NO_TONE = { state: '', card: 'border-neutral-200', head: 'bg-neutral-100', badge: '' }

const ID_RE = /(B-\d{2}-\d{4}-\d{2}|LOT-[A-Z]-\d{4}-[A-Z]|C-\d{3})/g

/** AI 글 안의 배치·로트·고객 ID를 칩으로 그린다. 글자는 바꾸지 않는다. */
function withIds(text: string, chip: string): ReactNode {
  return text.split(ID_RE).map((part, i) =>
    i % 2 === 1
      ? <span key={i} className={`rounded border px-1 py-px font-mono text-[13px] ${chip}`}>{part}</span>
      : part,
  )
}

function Tag({ tone, children }: { tone: string; children: ReactNode }) {
  return <span className={`inline-flex items-center rounded px-2 h-[22px] text-xs font-medium ${tone}`}>{children}</span>
}

/** 안건 요약: 요지 → 쟁점 → (화면이 넣는 시스템 수치 표) → 대안 3칸 → 확인 안 된 것 → 접어 둔 근거.
 *  배치 수치는 AI 글이 아니라 `facts`(시스템 값)로 보인다 (ai/prompts.py AGENDA_SUMMARY). */
export function AgendaOutput({ output, facts }: { output: unknown; facts?: ReactNode }) {
  const o = output as O
  const options = Array.isArray(o.options) ? (o.options as O[]) : []
  const evidence = Array.isArray(o.evidence) ? (o.evidence as O[]) : []
  const points = list(o.key_points)
  const uncertainties = list(o.uncertainties)
  const [showEvidence, setShowEvidence] = useState(false)
  const sourceCounts = new Map<string, number>()
  for (const e of evidence) sourceCounts.set(String(e.source), (sourceCounts.get(String(e.source)) ?? 0) + 1)
  return (
    <div className="space-y-4">
      <div className="rounded-lg border border-neutral-300 bg-white px-4 py-3.5 space-y-2">
        <Tag tone="bg-neutral-900 text-white">요지</Tag>
        <p className="text-lg font-semibold leading-relaxed text-neutral-900">{String(o.headline ?? '')}</p>
      </div>

      {points.length > 0 && (
        <div className="space-y-2">
          <div className="flex items-center gap-2">
            <Tag tone="bg-neutral-200 text-neutral-900">쟁점 {points.length}</Tag>
            <span className="text-xs text-neutral-600">결정 전에 알아야 할 것</span>
          </div>
          <ol className="rounded-lg border border-neutral-200 bg-white divide-y divide-neutral-100">
            {points.map((s, i) => (
              <li key={i} className="flex gap-3 px-3.5 py-2.5">
                <span className="w-5 shrink-0 font-semibold tabular-nums text-neutral-900">{i + 1}</span>
                <span>{withIds(s, 'border-neutral-200 bg-neutral-100 text-neutral-900')}</span>
              </li>
            ))}
          </ol>
        </div>
      )}

      {facts}

      <div className="space-y-2">
        <div className="flex items-center gap-2">
          <Tag tone="bg-neutral-200 text-neutral-900">대안 {options.length}</Tag>
          <span className="text-xs text-neutral-600">고르면 생기는 일 · 색은 결정 뒤 배치 상태</span>
        </div>
        <div className="grid gap-2.5 sm:grid-cols-3">
          {options.map((x, i) => {
            const tone = OPTION_TONE[String(x.option)] ?? NO_TONE
            return (
              <div key={i} className={`overflow-hidden rounded-lg border bg-white ${tone.card}`}>
                <div className={`flex items-center justify-between gap-2 px-3.5 py-2.5 ${tone.head}`}>
                  <span className="text-[15px] font-semibold text-neutral-900">{String(x.option)}</span>
                  {tone.state && <Tag tone={tone.badge}>→ {tone.state}</Tag>}
                </div>
                <div className="px-3.5 py-3"><Bullets items={list(x.impact_points)} /></div>
              </div>
            )
          })}
        </div>
      </div>

      <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3.5 space-y-2">
        <div className="flex items-center gap-2 text-amber-800">
          <AlertTriangle size={16} strokeWidth={1.5} aria-hidden="true" />
          <span className="text-[13px] font-semibold">확인 안 된 것 {uncertainties.length}</span>
          <span className="text-xs">결정에 영향을 줄 수 있음</span>
        </div>
        {uncertainties.length === 0 ? <p className="text-neutral-600">—</p> : (
          <ul className="grid gap-2 sm:grid-cols-2">
            {uncertainties.map((s, i) => (
              <li key={i} className="rounded-md border border-amber-200 bg-white px-3 py-2.5">
                {withIds(s, 'border-amber-200 bg-amber-50 text-amber-800')}
              </li>
            ))}
          </ul>
        )}
      </div>

      {evidence.length > 0 && (
        <div className="space-y-1.5">
          <div className="flex flex-wrap items-center gap-2 text-xs text-neutral-600">
            <button type="button" aria-expanded={showEvidence} onClick={() => setShowEvidence(v => !v)} className="underline hover:text-neutral-900">
              {showEvidence ? '근거 접기' : `근거 ${evidence.length}개 보기`}
            </button>
            {[...sourceCounts].map(([src, n]) => (
              <span key={src} className="inline-flex items-center rounded border border-neutral-300 bg-white px-1.5 h-5 tabular-nums">{src} {n}</span>
            ))}
          </div>
          {showEvidence && (
            <ul className="space-y-1">
              {evidence.map((e, i) => (
                <li key={i} className="flex items-start gap-2">
                  <span className="shrink-0 pt-0.5"><SourceBadge source={String(e.source)} /></span>
                  <span>{String(e.text)}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  )
}

/** 안건 요약 출력 → 폼의 안건 요약 글. 위원회 결정 창에 그대로 보이므로 짧게 넣는다.
 *  근거는 넣지 않는다: 상신 기록에 연결된 AI 기록(ai_log_id)에 출처와 함께 남아 있다. */
export function agendaText(output: unknown): string {
  const o = output as O
  const options = Array.isArray(o.options) ? (o.options as O[]) : []
  return [
    String(o.headline ?? ''),
    ...list(o.key_points).map(s => `- ${s}`),
    '',
    '대안별 영향',
    ...options.map(x => `- ${String(x.option)}: ${list(x.impact_points).join(' / ')}`),
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
