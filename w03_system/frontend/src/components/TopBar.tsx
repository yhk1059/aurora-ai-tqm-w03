import { CalendarDays, ChevronDown, RotateCcw, Sparkles, UserRound } from 'lucide-react'
import { useState } from 'react'
import type { IncidentView, Ontology, Role, ScenarioInfo } from '../types'
import { Button } from './Button'
import { ConfirmDialog } from './ConfirmDialog'
import { StatusBadge } from './StatusBadge'

// 상단 바 (ui-guide.md "레이아웃"): 사건 ID · 사건 상태 · 기점 로트 │ AI 표시 · 적용일 · 역할 선택 · 초기화.
// 적용일은 모든 폼이 쓰는 값을 여기 한 곳에서 고른다. AI 모델·재생 모드는 툴팁으로만 보인다 (ui-guide.md v20)
type ResetTarget = { scenario: string | null; label: string }

type Props = {
  view: IncidentView
  actor: Role
  ontology: Ontology
  scenarios: ScenarioInfo[]
  onActorChange: (actor: Role) => void
  onReset: (scenario: string | null) => Promise<void>
  /** AI 상태 (GET /api/ai/status). 작은 글자로만 보인다 */
  ai: { available: boolean; model: string | null }
  /** 다음 입력의 적용일과 바꾸는 함수 */
  appliedDate: string
  onDateChange: (date: string) => void
}

export function TopBar({ view, actor, ontology, scenarios, onActorChange, onReset, ai, appliedDate, onDateChange }: Props) {
  const [menuOpen, setMenuOpen] = useState(false)
  const [target, setTarget] = useState<ResetTarget | null>(null)
  const [busy, setBusy] = useState(false)
  const inc = view.incident
  // 초기화 메뉴는 서버가 이 역할에 '초기화' 액션을 허용할 때만 보인다
  const canReset = view.available_actions.some(a => a.action === 'reset')
  const options: ResetTarget[] = [
    { scenario: null, label: '빈 상태 (S0, 사건 없음)' },
    ...scenarios.filter(s => s.setup_count > 0).map(s => ({ scenario: s.name, label: `${s.title} 출발 상태` })),
  ]

  async function confirmReset() {
    if (!target) return
    setBusy(true)
    try {
      await onReset(target.scenario)
      setTarget(null)
    } catch {
      // 오류 줄은 App이 띄운다. 창은 닫는다
      setTarget(null)
    } finally {
      setBusy(false)
    }
  }

  return (
    <header className="bg-indigo-100 border-b border-indigo-200">
      <div className="max-w-7xl mx-auto px-6 h-14 flex items-center gap-4">
        <span className="text-sm font-semibold text-indigo-900 mr-2">Aurora AI-TQM</span>
        {inc ? (
          <div className="flex items-center gap-3">
            <span className="text-lg font-medium text-neutral-900 font-mono">{inc.id}</span>
            <StatusBadge state={inc.status} />
            <span className="text-sm text-neutral-600">기점 로트</span>
            <span className="font-mono text-sm text-neutral-900">{inc.origin_lots.join(', ') || '—'}</span>
          </div>
        ) : (
          <span className="text-sm text-neutral-600">사건 없음</span>
        )}

        <div className="ml-auto flex items-center gap-4">
          <span
            data-ai-status
            title={ai.available ? `AI 사용 가능 (${ai.model ?? '—'})` : 'AI 키 없음'}
            className={`inline-flex items-center gap-1 text-xs ${ai.available ? 'text-violet-700' : 'text-neutral-400 line-through'}`}
          >
            <Sparkles size={14} strokeWidth={1.5} aria-hidden="true" />
            AI
          </span>
          <label className="flex items-center gap-1.5 text-sm text-neutral-700" title="다음 입력이 시스템에 반영되는 날. 시연에서 날짜를 넘길 때 바꿉니다">
            <CalendarDays size={16} strokeWidth={1.5} className="text-indigo-700" />
            <span className="sr-only">적용일</span>
            <input
              type="date"
              aria-label="적용일"
              value={appliedDate}
              onChange={e => onDateChange(e.target.value)}
              className="rounded-md bg-white border border-neutral-300 px-2 h-8 text-sm tabular-nums text-neutral-900 focus:border-indigo-600 focus:outline-none"
            />
          </label>
          <label className="flex items-center gap-1.5 text-sm text-neutral-700">
            <UserRound size={16} strokeWidth={1.5} className="text-indigo-700" />
            <span className="sr-only">역할</span>
            <select
              value={actor}
              onChange={e => onActorChange(e.target.value)}
              className="rounded-md bg-white border border-neutral-300 px-2 h-8 text-sm focus:border-indigo-600 focus:outline-none"
            >
              {Object.entries(ontology.roles).map(([key, r]) => (
                <option key={key} value={key}>{r.name}</option>
              ))}
            </select>
          </label>
          {canReset && (
            <div className="relative">
              <Button variant="secondary" onClick={() => setMenuOpen(o => !o)}>
                <RotateCcw size={16} strokeWidth={1.5} />
                초기화
                <ChevronDown size={16} strokeWidth={1.5} />
              </Button>
              {menuOpen && (
                <ul className="absolute right-0 top-9 z-30 w-72 rounded-md border border-neutral-200 bg-white py-1">
                  {options.map(o => (
                    <li key={o.scenario ?? '_empty'}>
                      <button
                        type="button"
                        className="w-full text-left px-3 py-2 text-sm text-neutral-700 hover:bg-neutral-100"
                        onClick={() => { setMenuOpen(false); setTarget(o) }}
                      >
                        {o.label}
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </div>
      </div>

      <ConfirmDialog
        open={target !== null}
        title="초기화"
        confirmLabel="초기화 실행"
        busy={busy}
        onConfirm={confirmReset}
        onCancel={() => setTarget(null)}
      >
        <p>지금 상태와 기록이 모두 지워집니다.</p>
        <p>출발 상태: <span className="font-medium text-neutral-900">{target?.label}</span></p>
        {target?.scenario && (
          <p className="text-neutral-500">시나리오의 출발 단계를 서버가 액션으로 실제 실행합니다. 실행 기록이 남습니다.</p>
        )}
      </ConfirmDialog>
    </header>
  )
}
