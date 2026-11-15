import { ChevronDown, ChevronRight } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { Card } from '../components/Card'
import { SourceBadge } from '../components/SourceBadge'
import { useApp } from '../context'
import type { Ontology, Threshold } from '../types'

// 업무 기준 탭 (ui-guide.md 레이아웃 v19, business-model.md §8): GET /api/ontology 응답을 두 층으로 보인다.
// 위 = 사건 담당자가 읽는 기준(규칙·액션·작업 유형·상태 전이·자동 처리). 한글 이름만 보이고 내부 키는 툴팁에 둔다.
// 아래 = 접힌 `시스템 정의`(객체 타입·관계·값 목록). 정의를 키와 함께 그대로 보인다.
// 구역 제목·열 이름 외의 글자는 전부 서버 응답에서 온다. 화면이 모르는 키는 버리지 않고 이름-값으로 보인다.

// 각 구역이 직접 그리는 최상위 키. 나머지는 '그 밖의 정의'에 그대로 나온다
const SHOWN_TOP = new Set([
  'object_types', 'link_attributes', 'relations', 'state_machines', 'incident_statuses', 'rule_places', 'rules',
  'task_deadline', 'actions', 'task_types', 'auto_processes', 'roles', 'sources', 'confirmation_levels',
  'confirmed_levels', 'quantity_bases', 'departments', 'event_types', 'decision_types', 'committee_results',
  'plan_decision_results', 'ai_uninterpretable',
])

type Dict = Record<string, unknown>

function show(v: unknown): string {
  if (v === null || v === undefined) return '—'
  if (Array.isArray(v)) return v.length ? v.map(show).join(', ') : '—'
  if (typeof v === 'boolean') return v ? '예' : '아니오'
  if (typeof v === 'object') return JSON.stringify(v)
  return String(v)
}

/** 화면이 그리지 않은 키를 이름-값으로 보인다 */
function Extra({ obj, known }: { obj: unknown; known: string[] }) {
  if (!obj || typeof obj !== 'object') return null
  const rest = Object.entries(obj as Dict).filter(([k]) => !known.includes(k))
  if (rest.length === 0) return null
  return (
    <dl className="mt-1 space-y-0.5 text-xs">
      {rest.map(([k, v]) => (
        <div key={k} className="flex gap-2">
          <dt className="font-mono text-neutral-500">{k}</dt>
          <dd className="text-neutral-700 break-all">{show(v)}</dd>
        </div>
      ))}
    </dl>
  )
}

function Ids({ ids }: { ids: string[] | undefined | null }) {
  if (!ids || ids.length === 0) return <span className="text-neutral-400">—</span>
  return <span className="font-mono text-xs">{ids.join(', ')}</span>
}

function Sources({ list }: { list: string[] | undefined }) {
  if (!list || list.length === 0) return <span className="text-neutral-400">—</span>
  return <span className="inline-flex flex-wrap gap-1">{list.map(s => <SourceBadge key={s} source={s} />)}</span>
}

function Table({ head, children }: { head: string[]; children: ReactNode }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="bg-neutral-100 text-left text-xs text-neutral-600">
            {head.map(h => <th key={h} className="px-2 py-1.5 font-medium whitespace-nowrap">{h}</th>)}
          </tr>
        </thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  )
}

const td = 'px-2 py-1.5 align-top border-t border-neutral-100'

/** 기준값 글자: 값+단위(연속 개월), 또는 식 */
function thresholdText(t: Threshold): string {
  const parts: string[] = []
  if (t.value !== undefined) parts.push(`${t.value}${t.unit}`)
  else if (t.formula) parts.push(`${t.formula} (${t.unit})`)
  if (t.consecutive_months) parts.push(`${t.consecutive_months}개월 연속`)
  return parts.join(', ')
}

function ThresholdCell({ t }: { t: Threshold | null | undefined }) {
  if (!t) return <span className="text-neutral-400">—</span>
  const assumed = t.source === '가정'
  return (
    <div className="space-y-1">
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="tabular-nums text-neutral-900">{thresholdText(t)}</span>
        <SourceBadge
          source={t.source}
          refId={assumed ? t.ref : null}
          note={t.description}
          evidence={assumed ? [] : [t.ref]}
        />
      </div>
      <div className="text-xs text-neutral-500">{t.description}</div>
      <Extra obj={t} known={['value', 'unit', 'formula', 'consecutive_months', 'description', 'source', 'ref']} />
    </div>
  )
}

/** 구역은 접힌 채로 시작한다. 제목 줄에는 정의 개수만 보인다 (ui-guide.md v3) */
function Section({ id, title, meta, open, onToggle, children }: {
  id: string; title: string; meta: string; open: boolean; onToggle(): void; children: ReactNode
}) {
  const Icon = open ? ChevronDown : ChevronRight
  return (
    <section id={id} className="space-y-3">
      <button type="button" onClick={onToggle} aria-expanded={open}
        className="flex w-full items-center gap-2 rounded-lg border border-neutral-200 bg-white px-4 h-11 text-left hover:bg-neutral-50">
        <Icon size={16} strokeWidth={1.5} className="shrink-0 text-neutral-500" />
        <h2 className="text-sm font-medium text-neutral-900">{title}</h2>
        <span className="text-sm tabular-nums text-neutral-500">{meta}</span>
      </button>
      {open && children}
    </section>
  )
}

function typeName(o: Ontology, key: string): string {
  return o.object_types[key]?.name ?? key
}

// ---------------------------------------------------------------------------
// 업무 기준: 한글 이름만 보인다. 내부 키는 이름의 툴팁(title)에 둔다
// ---------------------------------------------------------------------------

function Rules({ o }: { o: Ontology }) {
  return (
    <div className="space-y-4">
      <Card title="규칙">
        <Table head={['번호', '요약', '기준값과 출처', '근거']}>
          {Object.entries(o.rules).map(([id, r]) => (
            <tr key={id}>
              <td className={`${td} font-mono text-xs text-neutral-900 whitespace-nowrap`}>
                {id}
                {r.extension && <div className="text-[11px] text-neutral-500">확장</div>}
              </td>
              <td className={td}>{r.summary}<Extra obj={r} known={['summary', 'places', 'basis', 'extension', 'threshold']} /></td>
              <td className={`${td} min-w-56`}><ThresholdCell t={r.threshold} /></td>
              <td className={`${td} text-xs`}>{r.basis.map(b => <div key={b}>{b}</div>)}</td>
            </tr>
          ))}
        </Table>
      </Card>
      <Card title="그 밖의 기준값">
        <Table head={['기준', '기준값과 출처']}>
          <tr>
            <td className={`${td} whitespace-nowrap`} title="task_deadline">작업 기한</td>
            <td className={td}><ThresholdCell t={o.task_deadline} /></td>
          </tr>
        </Table>
      </Card>
    </div>
  )
}

function Actions({ o }: { o: Ontology }) {
  return (
    <Card title="사람이 실행하는 액션">
      <Table head={['액션', '실행 역할', '입력', '전제 조건', '효과', '관련 규칙', '만드는 작업']}>
        {Object.entries(o.actions).map(([key, a]) => (
          <tr key={key}>
            <td className={`${td} whitespace-nowrap text-neutral-900`} title={key}>{a.name}</td>
            <td className={`${td} text-xs`}>{a.roles.map(r => o.roles[r]?.name ?? r).join(', ')}</td>
            <td className={`${td} text-xs`}>
              {a.inputs.length === 0 ? <span className="text-neutral-400">—</span> : (
                <ul className="space-y-0.5">
                  {a.inputs.map(i => (
                    <li key={i.key} title={i.key}>
                      <span className="text-neutral-900">{i.name}</span>
                      {!i.required && <span className="text-neutral-500"> · 선택</span>}
                      {i.choices && !i.choice_effects && <span className="text-neutral-500"> · {i.choices.join(' / ')}</span>}
                      {i.description && <div className="text-neutral-500">{i.description}</div>}
                      {i.choices && i.choice_effects && (
                        <ul className="space-y-0.5 text-neutral-500">
                          {i.choices.map(c => (
                            <li key={c}><span className="text-neutral-900">{c}</span> <span className="text-neutral-400">→</span> {i.choice_effects?.[c] ?? '—'}</li>
                          ))}
                        </ul>
                      )}
                      <Extra obj={i} known={['key', 'name', 'type', 'required', 'ref_type', 'choices', 'choices_from', 'choice_effects', 'description']} />
                    </li>
                  ))}
                </ul>
              )}
            </td>
            <td className={`${td} text-xs`}>{a.precondition}</td>
            <td className={`${td} text-xs`}>{a.effect}</td>
            <td className={td}><Ids ids={a.rules} /></td>
            <td className={`${td} text-xs`}>
              {a.creates_tasks.length ? a.creates_tasks.join(', ') : <span className="text-neutral-400">—</span>}
              <Extra obj={a} known={['name', 'roles', 'inputs', 'precondition', 'effect', 'rules', 'creates_tasks']} />
            </td>
          </tr>
        ))}
      </Table>
    </Card>
  )
}

function TaskTypes({ o }: { o: Ontology }) {
  return (
    <Card title="작업 유형">
      <Table head={['코드', '유형', '담당 부서', '대상', '관련 규칙', '허용 결과 → 효과']}>
        {Object.entries(o.task_types).map(([name, t]) => (
          <tr key={name}>
            <td className={`${td} font-mono text-xs whitespace-nowrap`}>{t.code ?? '—'}</td>
            <td className={`${td} whitespace-nowrap text-neutral-900`}>{name}</td>
            <td className={`${td} text-xs`}>{t.departments.join(', ')}</td>
            <td className={`${td} text-xs`}>{t.targets.map(k => o.object_types[k] ? typeName(o, k) : k).join(', ')}</td>
            <td className={td}><Ids ids={t.rules} /></td>
            <td className={`${td} text-xs`}>
              {t.allowed_results.length === 0 ? <span className="text-neutral-500">(회신 없음)</span> : (
                <ul className="space-y-0.5">
                  {t.allowed_results.map(r => (
                    <li key={r.result}><span className="text-neutral-900">{r.result}</span> <span className="text-neutral-400">→</span> {r.effect}</li>
                  ))}
                </ul>
              )}
              {t.auto_complete && <div className="text-neutral-500">{t.auto_complete}</div>}
              {t.basis && <div className="text-neutral-500">근거: {t.basis}</div>}
              <Extra obj={t} known={['code', 'departments', 'targets', 'rules', 'allowed_results', 'auto_complete', 'basis']} />
            </td>
          </tr>
        ))}
      </Table>
    </Card>
  )
}

function States({ o }: { o: Ontology }) {
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-4">
        {Object.entries(o.state_machines).map(([key, m]) => (
          <Card key={key} title={<span title={key}>{m.name}</span>}>
            <div className="text-xs text-neutral-500">상태: <span className="text-neutral-700">{m.states.join(' · ')}</span></div>
            <div className="text-xs text-neutral-500">초기 상태: <span className="text-neutral-700">{m.initial.join(' · ')}</span></div>
            {m.unconfirmed_states && m.unconfirmed_states.length > 0 && (
              <div className="text-xs text-neutral-500">미확정으로 보는 상태: <span className="text-neutral-700">{m.unconfirmed_states.join(' · ')}</span></div>
            )}
            <Table head={['이전', '', '이후', '언제']}>
              {m.transitions.map((t, i) => (
                <tr key={i}>
                  <td className={`${td} whitespace-nowrap`}>{t.from}</td>
                  <td className={`${td} text-neutral-400`}>→</td>
                  <td className={`${td} whitespace-nowrap`}>{t.to}</td>
                  <td className={`${td} text-xs`}>{t.by}<Extra obj={t} known={['from', 'to', 'by']} /></td>
                </tr>
              ))}
            </Table>
            <Extra obj={m} known={['name', 'states', 'initial', 'transitions', 'unconfirmed_states']} />
          </Card>
        ))}
      </div>
      <Card title="사건 상태 (저장하지 않고 도출)">
        <Table head={['상태', '도출 조건']}>
          {o.incident_statuses.map(s => (
            <tr key={s.name}>
              <td className={`${td} whitespace-nowrap`}>{s.name}</td>
              <td className={td}>{s.condition}<Extra obj={s} known={['name', 'condition']} /></td>
            </tr>
          ))}
        </Table>
      </Card>
    </div>
  )
}

function AutoProcesses({ o }: { o: Ontology }) {
  return (
    <Card title="시스템 자동 처리">
      <Table head={['자동 처리', '언제', '바꾸는 것', '규칙']}>
        {Object.entries(o.auto_processes).map(([key, p]) => (
          <tr key={key}>
            <td className={`${td} whitespace-nowrap text-neutral-900`} title={key}>{p.name}</td>
            <td className={`${td} text-xs`}>{p.trigger}</td>
            <td className={`${td} text-xs`}>
              {p.effect}
              {p.basis && <div className="text-neutral-500">근거: {p.basis}</div>}
              <Extra obj={p} known={['name', 'trigger', 'effect', 'rules', 'basis']} />
            </td>
            <td className={td}><Ids ids={p.rules} /></td>
          </tr>
        ))}
      </Table>
    </Card>
  )
}

// ---------------------------------------------------------------------------
// 시스템 정의: 서버가 읽는 정의를 키와 함께 그대로 보인다
// ---------------------------------------------------------------------------

function Group({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="space-y-3">
      <h3 className="px-0.5 text-sm font-medium text-neutral-600">{title}</h3>
      {children}
    </div>
  )
}

function ObjectTypes({ o }: { o: Ontology }) {
  return (
    <div className="grid grid-cols-2 gap-4">
      {Object.entries(o.object_types).map(([key, t]) => {
        const sm = t.state ? o.state_machines[t.state.kind] : null
        return (
          <Card key={key} title={<span>{t.name} <span className="font-mono text-xs font-normal text-neutral-500">{key}</span></span>}>
            <p className="text-sm text-neutral-700">{t.description}</p>
            <div className="flex items-center gap-2 text-xs text-neutral-500">기본 출처 <Sources list={t.default_source} /></div>
            <Table head={['구분', '키', '이름', '관련 규칙']}>
              {t.stored.map(a => (
                <tr key={`s-${a.key}`}>
                  <td className={`${td} text-xs text-neutral-500`}>저장</td>
                  <td className={`${td} font-mono text-xs`}>{a.key}</td>
                  <td className={td}>{a.name}<Extra obj={a} known={['key', 'name']} /></td>
                  <td className={td}><span className="text-neutral-400">—</span></td>
                </tr>
              ))}
              {t.derived.map(a => (
                <tr key={`d-${a.key}`}>
                  <td className={`${td} text-xs text-neutral-500`}>파생</td>
                  <td className={`${td} font-mono text-xs`}>{a.key}</td>
                  <td className={td}>
                    {a.name}
                    {a.basis && <div className="text-xs text-neutral-500">{a.basis}</div>}
                    <Extra obj={a} known={['key', 'name', 'rules', 'basis']} />
                  </td>
                  <td className={td}><Ids ids={a.rules} /></td>
                </tr>
              ))}
            </Table>
            {t.state && (
              <div className="text-xs text-neutral-500 space-y-1">
                <div>상태 속성 <span className="font-mono">{t.state.attribute}</span> · 전이표 <span className="font-mono">{t.state.kind}</span>{sm && ` (${sm.name})`}</div>
                {sm && <div className="text-neutral-700">{sm.states.join(' · ')}</div>}
              </div>
            )}
            <Extra obj={t} known={['name', 'description', 'default_source', 'stored', 'derived', 'state']} />
          </Card>
        )
      })}
    </div>
  )
}

function Relations({ o }: { o: Ontology }) {
  return (
    <div className="space-y-4">
      <Card title="관계 유형">
        <Table head={['관계', '출발 → 도착', '확인 수준', '수량', '기본 출처', '근거']}>
          {Object.entries(o.relations).map(([key, r]) => (
            <tr key={key}>
              <td className={`${td} font-mono text-xs text-neutral-900`}>{key}</td>
              <td className={`${td} whitespace-nowrap`}>
                {r.from.map(f => typeName(o, f)).join(', ')} → {r.to.map(t => typeName(o, t)).join(', ')}
                {r.to_links.length > 0 && <div className="text-xs text-neutral-500">관계 줄: <Ids ids={r.to_links} /></div>}
              </td>
              <td className={td}>{r.uses_confirmation ? '있음' : '없음'}</td>
              <td className={td}>{r.uses_quantity ? '있음' : '없음'}</td>
              <td className={td}><Sources list={r.default_source} /></td>
              <td className={`${td} text-xs`}>
                {r.basis}
                {Array.isArray(r.attributes) && r.attributes.length > 0 && (
                  <div className="text-neutral-500">속성: {show((r.attributes as { name?: string }[]).map(a => a.name ?? show(a)))}</div>
                )}
                <Extra obj={r} known={['from', 'to', 'to_links', 'default_source', 'uses_confirmation', 'uses_quantity', 'attributes', 'basis']} />
              </td>
            </tr>
          ))}
        </Table>
      </Card>
      <Card title="관계 한 줄이 가지는 속성">
        <Table head={['키', '이름']}>
          {o.link_attributes.map(a => (
            <tr key={a.key}>
              <td className={`${td} font-mono text-xs`}>{a.key}</td>
              <td className={td}>{a.name}<Extra obj={a} known={['key', 'name']} /></td>
            </tr>
          ))}
        </Table>
      </Card>
    </div>
  )
}

function ValueList({ label, values }: { label: string; values: unknown }) {
  return (
    <tr>
      <td className={`${td} whitespace-nowrap text-xs text-neutral-500`}>{label}</td>
      <td className={td}>{show(values)}</td>
    </tr>
  )
}

function Values({ o }: { o: Ontology }) {
  return (
    <div className="space-y-4">
      <Card title="역할">
        <Table head={['키', '이름', '근거']}>
          {Object.entries(o.roles).map(([key, r]) => (
            <tr key={key}>
              <td className={`${td} font-mono text-xs`}>{key}</td>
              <td className={td}>{r.name}</td>
              <td className={`${td} text-xs`}>{r.basis}<Extra obj={r} known={['name', 'basis']} /></td>
            </tr>
          ))}
        </Table>
      </Card>
      <Card title="규칙이 놓인 자리">
        <Table head={['자리', '규칙']}>
          {o.rule_places.map(p => (
            <tr key={p}>
              <td className={`${td} whitespace-nowrap`}>{p}</td>
              <td className={td}><Ids ids={Object.entries(o.rules).filter(([, r]) => r.places.includes(p)).map(([id]) => id)} /></td>
            </tr>
          ))}
        </Table>
      </Card>
      <Card title="값 목록">
        <Table head={['정의', '값']}>
          <tr>
            <td className={`${td} whitespace-nowrap text-xs text-neutral-500`}>출처 (sources)</td>
            <td className={td}><Sources list={o.sources} /></td>
          </tr>
          <ValueList label="확인 수준 (confirmation_levels)" values={o.confirmation_levels} />
          <ValueList label="회수·재공급 대상 확인 수준 (confirmed_levels)" values={o.confirmed_levels} />
          <ValueList label="수량 근거 (quantity_bases)" values={o.quantity_bases} />
          <ValueList label="부서 (departments)" values={o.departments} />
          <ValueList label="이벤트 유형 (event_types)" values={o.event_types} />
          <ValueList label="결정 유형 (decision_types)" values={o.decision_types} />
          <ValueList label="위원회 결과 (committee_results)" values={o.committee_results} />
          <ValueList label="재공급 계획 결정 결과 (plan_decision_results)" values={o.plan_decision_results} />
          <ValueList label="AI 해석 불가 값 (ai_uninterpretable)" values={o.ai_uninterpretable} />
        </Table>
      </Card>
    </div>
  )
}

/** 화면이 직접 그리지 않는 최상위 키 */
function otherKeys(o: Ontology): [string, unknown][] {
  return Object.entries(o as unknown as Dict).filter(([k]) => !SHOWN_TOP.has(k))
}

function System({ o }: { o: Ontology }) {
  const rest = otherKeys(o)
  return (
    <div className="space-y-6">
      <Group title="객체 타입"><ObjectTypes o={o} /></Group>
      <Group title="관계"><Relations o={o} /></Group>
      <Group title="역할·규칙의 자리·값 목록"><Values o={o} /></Group>
      {rest.length > 0 && (
        <Group title="그 밖의 정의">
          <Card>
            <Table head={['키', '값']}>
              {rest.map(([k, v]) => (
                <tr key={k}>
                  <td className={`${td} font-mono text-xs`}>{k}</td>
                  <td className={td}><pre className="text-xs font-mono whitespace-pre-wrap break-all">{JSON.stringify(v, null, 2)}</pre></td>
                </tr>
              ))}
            </Table>
          </Card>
        </Group>
      )}
    </div>
  )
}

export function OntologyTab() {
  const { ontology: o } = useApp()
  const [open, setOpen] = useState<Set<string>>(new Set())
  const size = (v: object) => Object.keys(v).length
  // 사건 담당자가 읽는 기준
  const criteria: { id: string; title: string; meta: string; body: ReactNode }[] = [
    { id: 'onto-rules', title: '규칙', meta: `${size(o.rules)}개`, body: <Rules o={o} /> },
    { id: 'onto-actions', title: '액션', meta: `${size(o.actions)}개`, body: <Actions o={o} /> },
    { id: 'onto-tasks', title: '작업 유형', meta: `${size(o.task_types)}개`, body: <TaskTypes o={o} /> },
    { id: 'onto-states', title: '상태 전이', meta: `${size(o.state_machines)}개`, body: <States o={o} /> },
    { id: 'onto-auto', title: '자동 처리', meta: `${size(o.auto_processes)}개`, body: <AutoProcesses o={o} /> },
  ]
  // 시스템이 읽는 정의. 기준 아래에 떨어뜨려 둔다
  const system = {
    id: 'onto-system', title: '시스템 정의',
    meta: `객체 타입 ${size(o.object_types)}개 · 관계 ${size(o.relations)}개`, body: <System o={o} />,
  }
  const sections = [...criteria, system]
  const allOpen = open.size === sections.length
  const toggle = (id: string) => setOpen(prev => {
    const next = new Set(prev)
    if (next.has(id)) next.delete(id); else next.add(id)
    return next
  })
  const render = (s: (typeof sections)[number]) => (
    <Section key={s.id} id={s.id} title={s.title} meta={s.meta} open={open.has(s.id)} onToggle={() => toggle(s.id)}>
      {s.body}
    </Section>
  )
  return (
    <div className="space-y-2">
      <div className="flex justify-end">
        <button type="button" className="text-sm text-neutral-500 hover:text-neutral-900"
          onClick={() => setOpen(allOpen ? new Set() : new Set(sections.map(s => s.id)))}>
          {allOpen ? '모두 접기' : '모두 펼치기'}
        </button>
      </div>
      {criteria.map(render)}
      <div className="pt-4">{render(system)}</div>
    </div>
  )
}

