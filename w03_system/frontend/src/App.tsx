import { X } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { ApiError, getAiStatus, getIncident, getOntology, getScenarios, resetTo, runAction } from './api'
import { AppContext, type AppCtx } from './context'
import { TopBar } from './components/TopBar'
import { IncidentTab } from './tabs/IncidentTab'
import { LogTab } from './tabs/LogTab'
import { OntologyTab } from './tabs/OntologyTab'
import { PlanTab } from './tabs/PlanTab'
import type { IncidentView, Ontology, Role, ScenarioInfo } from './types'

const TABS = [
  { key: 'incident', label: '사건' },
  { key: 'plan', label: '재공급 계획' },
  { key: 'log', label: '기록' },
  { key: 'ontology', label: '온톨로지' },
] as const
type TabKey = (typeof TABS)[number]['key']

const DEFAULT_ROLE: Role = 'quality_owner'

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
  const [error, setError] = useState<string | null>(null)

  // 정의·시나리오 목록·AI 상태: 처음 한 번
  useEffect(() => {
    getOntology().then(setOntology).catch(e => setError(message(e)))
    getScenarios().then(setScenarios).catch(e => setError(message(e)))
    getAiStatus().then(s => { setAiAvailable(s.available); setAiModel(s.model) }).catch(() => setAiAvailable(false))
  }, [])

  // 사건 뷰: 처음과 역할을 바꿀 때마다 (가능한 액션은 역할마다 서버가 정한다)
  useEffect(() => {
    let alive = true
    getIncident(actor)
      .then(v => { if (alive) setView(v) })
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

  const reset = useCallback(async (scenario: string | null) => {
    try {
      setView(await resetTo(scenario, actor))
      setError(null)
    } catch (e) {
      setError(message(e))
      throw e
    }
  }, [actor])

  const ctx = useMemo<AppCtx | null>(
    () => (view && ontology ? { view, actor, ontology, aiAvailable, run } : null),
    [view, actor, ontology, aiAvailable, run],
  )

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
        />
      ) : (
        <header className="bg-white border-b border-neutral-200">
          <div className="max-w-7xl mx-auto px-6 h-14 flex items-center text-sm text-neutral-500">불러오는 중…</div>
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

        <nav className="mt-4 flex gap-1 border-b border-neutral-200">
          {TABS.map(t => (
            <button
              key={t.key}
              type="button"
              onClick={() => setTab(t.key)}
              className={`px-3 h-9 text-sm -mb-px border-b-2 ${tab === t.key
                ? 'border-neutral-900 text-neutral-900 font-medium'
                : 'border-transparent text-neutral-500 hover:text-neutral-900'}`}
            >
              {t.label}
            </button>
          ))}
        </nav>

        <main className="py-4">
          {ctx && (
            <AppContext.Provider value={ctx}>
              {tab === 'incident' && <IncidentTab />}
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
