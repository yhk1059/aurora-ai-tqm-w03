import { ClipboardList, History, Scale, Truck, Waypoints, X } from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { ApiError, getAiStatus, getIncident, getOntology, getScenarios, resetTo, runAction } from './api'
import { AppContext, type AppCtx } from './context'
import { targetIds } from './components/ActionForm'
import { lastSeq, unconfirmedCustomers } from './components/Network'
import { TopBar } from './components/TopBar'
import { IncidentTab, JUDGE_ACTIONS } from './tabs/IncidentTab'
import { LogTab } from './tabs/LogTab'
import { NetworkTab } from './tabs/NetworkTab'
import { OntologyTab } from './tabs/OntologyTab'
import { PlanTab } from './tabs/PlanTab'
import type { IncidentView, Ontology, OpenView, Role, ScenarioInfo } from './types'

const TABS = [
  { key: 'incident', label: '사건', icon: ClipboardList },
  { key: 'network', label: '연결망', icon: Waypoints },
  { key: 'plan', label: '재공급 계획', icon: Truck },
  { key: 'log', label: '기록', icon: History },
  { key: 'ontology', label: '업무 기준', icon: Scale },
] as const
type TabKey = (typeof TABS)[number]['key']

/** 탭 옆 배지 (ui-guide.md v12): 탭을 열지 않아도 어디에 볼 것이 있는지 보인다. 값은 서버가 준 뷰에서만 센다.
 *  todo = 이 역할이 지금 할 수 있는 일(행동 색으로 채운다), warn = 확인이 안 된 것(주황), 그 밖은 건수(회색) */
function tabBadges(view: IncidentView | null): Partial<Record<TabKey, { text: string; todo?: boolean; warn?: boolean }>> {
  if (!view?.incident) return {}
  const judge = view.available_actions.some(a => JUDGE_ACTIONS.includes(a.action)) ? 1 : 0
  const todo = judge + (targetIds(view, 'apply_reply', 'task_id')?.length ?? 0)
  const plans = targetIds(view, 'plan_decision', 'plan_id')?.length ?? 0
  const unconfirmed = unconfirmedCustomers(view as OpenView).length
  return {
    incident: todo > 0 ? { text: `할 일 ${todo}`, todo: true } : undefined,
    network: unconfirmed > 0 ? { text: `미확인 ${unconfirmed}`, warn: true } : undefined,
    plan: plans > 0 ? { text: `결정 ${plans}`, todo: true } : undefined,
    log: view.log.actions.length > 0 ? { text: String(view.log.actions.length) } : undefined,
  }
}

const DEFAULT_ROLE: Role = 'quality_owner'
/** 과제 기준일. 사건이 없을 때 적용일의 기본값 */
const BASE_DATE = '2026-07-01'

function message(e: unknown): string {
  return e instanceof Error ? e.message : String(e)
}

export default function App() {
  const [view, setView] = useState<IncidentView | null>(null)
  const [actor, setActor] = useState<Role>(DEFAULT_ROLE)
  const [tab, setTab] = useState<TabKey>('incident')
  const [ontology, setOntology] = useState<Ontology | null>(null)
  const [scenarios, setScenarios] = useState<ScenarioInfo[]>([])
  const [aiAvailable, setAiAvailable] = useState(false)
  const [aiModel, setAiModel] = useState<string | null>(null)
  const [appliedDate, setAppliedDate] = useState(BASE_DATE)
  const [error, setError] = useState<string | null>(null)
  // 연결망 탭에서 마지막으로 본 액션 기록 번호. 탭을 열 때 그 뒤에 바뀐 배치·선을 강조한다.
  // 처음 불러올 때와 초기화 때 지금 번호로 맞춘다 (그 전에 있던 변경은 강조하지 않는다)
  const networkSeen = useRef<number | null>(null)

  // 정의·시나리오 목록·AI 상태: 처음 한 번
  useEffect(() => {
    getOntology().then(setOntology).catch(e => setError(message(e)))
    getScenarios().then(setScenarios).catch(e => setError(message(e)))
    getAiStatus().then(s => { setAiAvailable(s.available); setAiModel(s.replay ? '재생 모드 · API 호출 안 함' : s.model) }).catch(() => setAiAvailable(false))
  }, [])

  // 사건 뷰: 처음과 역할을 바꿀 때마다 (가능한 액션은 역할마다 서버가 정한다)
  useEffect(() => {
    let alive = true
    getIncident(actor)
      .then(v => { if (alive) { networkSeen.current ??= lastSeq(v); setView(v) } })
      .catch(e => { if (alive) setError(message(e)) })
    return () => { alive = false }
  }, [actor])

  const run = useCallback(async (action: string, inputs: Record<string, unknown>) => {
    try {
      const res = await runAction(action, actor, inputs)
      setView(res.view)
      setError(null)
    } catch (e) {
      setError(message(e))
      throw e instanceof ApiError ? e : new ApiError('unknown', message(e))
    }
  }, [actor])

  const refresh = useCallback(async () => {
    try {
      setView(await getIncident(actor))
    } catch (e) {
      setError(message(e))
    }
  }, [actor])

  const reset = useCallback(async (scenario: string | null) => {
    try {
      const v = await resetTo(scenario, actor)
      networkSeen.current = lastSeq(v)
      setView(v)
      setError(null)
    } catch (e) {
      setError(message(e))
      throw e
    }
  }, [actor])

  // 적용일은 사건의 현재 날짜를 따라간다. 시연에서 날짜를 넘길 때만 상단 바에서 바꾼다
  const currentDate = view?.incident ? view.incident.current_date : BASE_DATE
  useEffect(() => { setAppliedDate(currentDate) }, [currentDate])

  const openNetwork = useCallback(() => setTab('network'), [])

  const ctx = useMemo<AppCtx | null>(
    () => (view && ontology ? { view, actor, ontology, aiAvailable, appliedDate, run, refresh, setActor, openNetwork } : null),
    [view, actor, ontology, aiAvailable, appliedDate, run, refresh, openNetwork],
  )

  const badges = tabBadges(view)

  return (
    <div className="min-h-screen bg-neutral-50 text-neutral-700">
      {ctx ? (
        <TopBar
          view={ctx.view}
          actor={actor}
          ontology={ctx.ontology}
          scenarios={scenarios}
          onActorChange={setActor}
          onReset={reset}
          ai={{ available: aiAvailable, model: aiModel }}
          appliedDate={appliedDate}
          onDateChange={setAppliedDate}
        />
      ) : (
        <header className="bg-indigo-100 border-b border-indigo-200">
          <div className="max-w-7xl mx-auto px-6 h-14 flex items-center text-sm text-neutral-600">불러오는 중…</div>
        </header>
      )}

      <div className="max-w-7xl mx-auto px-6">
        {error && (
          <div role="alert" className="mt-4 flex items-start gap-2 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
            <span className="flex-1">{error}</span>
            <button type="button" aria-label="오류 닫기" onClick={() => setError(null)} className="text-red-700 hover:text-red-900">
              <X size={16} strokeWidth={1.5} />
            </button>
          </div>
        )}

        <nav className="mt-4 flex flex-wrap gap-1 border-b border-neutral-200">
          {TABS.map(t => {
            const on = tab === t.key
            const badge = badges[t.key]
            return (
              <button
                key={t.key}
                type="button"
                aria-current={on ? 'page' : undefined}
                onClick={() => setTab(t.key)}
                className={`-mb-px inline-flex items-center gap-2 rounded-t-lg border-b-[3px] px-3.5 h-11 text-[15px] ${on
                  ? 'border-indigo-500 bg-indigo-50 font-semibold text-indigo-900'
                  : 'border-transparent text-neutral-600 hover:bg-neutral-100 hover:text-neutral-900'}`}
              >
                <t.icon size={18} strokeWidth={1.5} aria-hidden="true" className={on ? 'text-indigo-600' : 'text-neutral-500'} />
                {t.label}
                {badge && (
                  <span className={`rounded-full px-2 text-xs leading-5 font-medium tabular-nums ${badge.todo ? 'bg-indigo-500 text-white' : badge.warn ? 'bg-amber-100 text-amber-800' : 'bg-neutral-200 text-neutral-700'}`}>
                    {badge.text}
                  </span>
                )}
              </button>
            )
          })}
        </nav>

        <main className="py-4">
          {ctx && (
            <AppContext.Provider value={ctx}>
              {tab === 'incident' && <IncidentTab />}
              {tab === 'network' && <NetworkTab seen={networkSeen} />}
              {tab === 'plan' && <PlanTab />}
              {tab === 'log' && <LogTab />}
              {tab === 'ontology' && <OntologyTab />}
            </AppContext.Provider>
          )}
        </main>
      </div>
    </div>
  )
}
