import { useState } from 'react'
import { Card } from '../components/Card'
import { Network, unconfirmedCustomers, type SeenRef, type Selection } from '../components/Network'
import { NetworkDetail } from '../components/NetworkDetail'
import { useApp } from '../context'
import type { OpenView } from '../types'

// 연결망 탭 (ui-guide.md "레이아웃" v16): 원료 로트 → 배치 → 고객을 화면 너비로 그린다. 읽기 화면이라 액션은 없다.
// 맨 위 한 줄에 범위 건수와 출하처 미확인 고객, 그 아래 연결망, 노드·선을 누르면 아래에 근거.

export function NetworkTab({ seen }: { seen: SeenRef }) {
  const { view } = useApp()
  const [selected, setSelected] = useState<Selection | null>(null)
  if (!view.incident) {
    return <Card title="연결망"><p className="text-sm text-neutral-500">사건이 아직 없습니다. 사건 탭에서 사건을 열면 원료 로트 → 배치 → 고객 연결이 그려집니다</p></Card>
  }
  const v = view as OpenView
  const unconfirmed = unconfirmedCustomers(v)
  return (
    <div className="space-y-4">
      <Card title={<>연결망 <span className="ml-1 text-xs font-normal text-neutral-500">원료 로트 → 배치 → 고객 (R4 원료 로트 기반 영향 추적)</span></>}>
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
          <span className="tabular-nums text-neutral-700">원료 로트 {v.lots.length}개 → 배치 {v.batches.length}개 → 고객 {v.customers.length}곳</span>
          {unconfirmed.length > 0 && (
            <span className="text-amber-700">출하처 미확인 {unconfirmed.length}곳 (<span className="font-mono">{unconfirmed.join(', ')}</span>)</span>
          )}
        </div>
        <Network view={v} selected={selected} onSelect={setSelected} seen={seen} />
      </Card>
      {selected && <NetworkDetail view={v} selected={selected} />}
    </div>
  )
}
