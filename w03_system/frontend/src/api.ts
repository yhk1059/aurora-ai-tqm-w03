// 서버 호출 함수 전부. 경로·본문 형식은 architecture.md API 표와 backend/api/main.py를 따른다.
import type {
  ActionResult, AiResult, AiTask, IncidentView, Ontology, ReplyExample, Role, ScenarioInfo,
} from './types'

/** 서버 오류 본문 {"error": {code, message}}. code: unknown_action / not_found / forbidden / invalid_input / precondition */
export class ApiError extends Error {
  code: string
  constructor(code: string, message: string) {
    super(message)
    this.name = 'ApiError'
    this.code = code
  }
}

async function request<T>(method: 'GET' | 'POST', path: string, body?: unknown): Promise<T> {
  let res: Response
  try {
    res = await fetch(path, {
      method,
      headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
    })
  } catch (e) {
    throw new ApiError('network', `서버에 연결할 수 없습니다 (${(e as Error).message})`)
  }
  const data = await res.json().catch(() => null)
  if (!res.ok) {
    const err = data?.error
    throw new ApiError(err?.code ?? `http_${res.status}`, err?.message ?? `서버 오류 (HTTP ${res.status})`)
  }
  return data as T
}

const q = encodeURIComponent

export function getIncident(actor: Role): Promise<IncidentView> {
  return request('GET', `/api/incident?actor=${q(actor)}`)
}

export function runAction(
  action: string, actor: Role, inputs: Record<string, unknown>,
): Promise<{ result: ActionResult; view: IncidentView }> {
  return request('POST', `/api/actions/${q(action)}`, { actor, inputs })
}

/** null → 빈 상태(초기화 액션), 이름 → 그 시나리오의 출발 상태(setup 단계만 실제 실행) */
export async function resetTo(scenario: string | null, actor: Role): Promise<IncidentView> {
  if (scenario === null) return (await runAction('reset', actor, {})).view
  const res = await request<{ steps: unknown[]; view: IncidentView }>(
    'POST', `/api/scenarios/${q(scenario)}?setup_only=true&actor=${q(actor)}`,
  )
  return res.view
}

export function getScenarios(): Promise<ScenarioInfo[]> {
  return request('GET', '/api/scenarios')
}

export async function getReplyExamples(): Promise<ReplyExample[]> {
  return (await request<{ examples: ReplyExample[] }>('GET', '/api/reply-examples')).examples
}

export function getOntology(): Promise<Ontology> {
  return request('GET', '/api/ontology')
}

export function getAiStatus(): Promise<{ available: boolean; model: string; replay: boolean }> {
  return request('GET', '/api/ai/status')
}

/** 키가 없으면 HTTP 200 + ok: false, error: "no_key" (오류로 던지지 않는다) */
export function runAi(task: AiTask, params: Record<string, unknown>): Promise<AiResult> {
  return request('POST', `/api/ai/${q(task)}`, { params })
}
