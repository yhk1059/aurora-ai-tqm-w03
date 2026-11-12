import { createContext, useContext } from 'react'
import type { IncidentView, Ontology, Role } from './types'

// 탭·폼이 받는 앱 문맥. 화면에만 있는 상태는 역할·탭·입력 중인 폼뿐이고,
// 사건 뷰는 서버 응답을 그대로 들고 있다가 그린다 (architecture.md "상태 관리").
export type AppCtx = {
  view: IncidentView
  actor: Role
  ontology: Ontology
  aiAvailable: boolean
  /** 액션 실행. 성공하면 응답의 view로 교체한다. 실패하면 위쪽 오류 줄에 message를 띄우고 ApiError로 reject한다(뷰는 그대로) */
  run(action: string, inputs: Record<string, unknown>): Promise<void>
}

export const AppContext = createContext<AppCtx | null>(null)

export function useApp(): AppCtx {
  const ctx = useContext(AppContext)
  if (!ctx) throw new Error('AppContext 밖에서 useApp을 불렀습니다')
  return ctx
}
