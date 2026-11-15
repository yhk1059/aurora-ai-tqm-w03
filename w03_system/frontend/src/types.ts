// 서버 응답 타입. backend/core/view.py · actions.py · ontology.py · scenario.py · ai/tasks.py가
// 실제로 돌려주는 키만 적는다. 화면은 이 값을 그대로 그린다(상태 복사본을 고쳐 쓰지 않는다).

/** 역할 키 (ontology ROLES의 키: quality_owner, quality_committee, scm). 목록은 GET /api/ontology에서 온다 */
export type Role = string

/** 출처: 원본 / 도출 / 가정 / 모의 / 시스템 */
export type Source = string

export type Ref = { type: string; id: string }

// ---------------------------------------------------------------------------
// 사건 뷰 (GET /api/incident, view.incident_view)
// ---------------------------------------------------------------------------

/** view._obj */
export type Obj<A = Record<string, unknown>> = {
  id: string
  attrs: A
  state: string | null
  source: Source
  evidence: string[]
}

export type AvailableAction = {
  action: string
  label: string
  /** 키 = 액션 입력 이름. 값 모양은 액션마다 다르다 (actions._targets_*) */
  targets: Record<string, unknown>
}

export type Warning = {
  code: string
  rule: string
  target: Ref
  message: string
  evidence: string[]
}

export type Threshold = {
  value?: number
  unit: string
  description: string
  source: Source
  ref: string
  formula?: string
  consecutive_months?: number
}

export type BatchMetrics = {
  batch_id: string
  produced_qty: number
  confirmed_qty: number
  defect_rate: number
  defect_rate_shipped: number | null
  over_threshold: boolean
  threshold: Threshold
  pending_qty: number
  rate_if_confirmed: number | null
  threshold_crossed_date: string | null
  days_unsubmitted: number | null
  last_ship_date: string | null
  release_due_date: string | null
  release_basis: string | null
  rules: Record<string, string>
  source: Source
}

export type Batch = Obj<{
  product: string
  line: string
  produced_date: string
  produced_qty: number
  qc_result: string
  input_lot_ids?: string[]
  role?: string
}> & {
  part_of: { reason: string | null; source: Source; link_id: number }
  metrics: BatchMetrics
  warnings: Warning[]
}

export type Customer = Obj<{ revenue_share: number; booking_yoy: Record<string, number | null> }> & {
  order_drop_signal: { signal: boolean; months: [string, number | null][]; rule: string; source: Source }
}

export type Claim = Obj<{
  received_date: string
  type: string
  defect_confirmed: boolean
  qty: number
  confirmed_date: string | null
  source: Source
}> & {
  batch_id: string | null
  customer_id: string | null
  lot_ids: string[]
  pending: boolean
}

/** view._link */
export type Link = {
  link_id: number
  rel: string
  src: Ref
  dst: Ref
  attrs: Record<string, unknown>
  source: Source
  confirm: string
  qty: number | null
  qty_basis: string | null
  evidence: string[]
  applied_date: string | null
  recorded_date: string | null
}

export type ShippedTo = Link & {
  claims: {
    count: number
    qty: number
    confirmed_count: number
    confirmed_qty: number
    claim_ids: string[]
    source: Source
  }
}

export type TaskTarget = Ref & { batch_id?: string; customer_id?: string; confirm?: string }

export type Task = Obj & {
  type: string
  code: string | null
  department: string | null
  due_date: string | null
  reply: string | null
  result: string | null
  replied_date: string | null
  created_by: { rule: string | null; decision: string | null } | null
  targets: TaskTarget[]
  allowed_results: string[]
}

export type Decision = Obj & {
  type: string
  decider: string
  result: string
  reason: string | null
  applied_date: string
  targets: Ref[]
  created_tasks: string[]
}

export type IncidentEvent = Obj & {
  type: string
  occurred_date: string | null
  applied_date: string | null
  content: string | null
  answers: string[]
}

export type SlackCapacity = {
  value: number
  unit: string
  monthly_avg_produced: number
  utilization_pct: number
  months: string[]
  source: Source
  ref: string
  evidence: string[]
}

export type RecalcCause = {
  rules: string[]
  trigger_seq: number | null
  trigger_action: string | null
  refs: string[]
  previous_version: number | null
}

export type PlanLine = Obj<{
  rank: number
  customer_id: string
  qty: number
  qty_basis: string
  lower_bound: boolean
  expected_month: string
  priority_reason: string
}>

export type PlanDiff = {
  customer_id: string
  base_plan_id: string
  rank_before: number | null
  rank_after: number | null
  month_before: string | null
  month_after: string | null
  delay_months: number | null
  added: boolean
}

export type Plan = Obj & {
  version: number
  lines: PlanLine[]
  diff: PlanDiff[]
  release_condition: string | null
  supply_condition: {
    met: boolean
    batch_id: string | null
    lots: string[]
    qc_result: string | null
    reason: string
    rule: string
    source: Source
  }
  supply_batch: Obj | null
  slack_capacity: SlackCapacity | null
  /** 복구 기간 (R10-3): 계획을 만든 달을 1번째 달로 센 마지막 완료 달과 기준(가정 A-19) 초과 여부 */
  recovery: { months: number; final_month: string; threshold_months: number; over: boolean; rule: string; source: Source }
  recalc_cause: RecalcCause | null
  decisions: string[]
}

/** 능력 확보 검토 작업(R10-3)의 근거: 원본 증설·전환안 (strat_capex_plan_cv) */
export type CapacityOption = {
  option_id: string
  option_type: string
  target_line: string
  capex_krw: number
  lead_time_weeks: number
  added_capacity_qty: number
  note: string
  evidence: string[]
}

export type RecallQuantity = {
  customer_id: string
  qty: number
  qty_basis: string
  lower_bound: boolean
  link_ids: number[]
  rule: string
}

export type HeldCustomer = {
  customer_id: string
  batch_ids: string[]
  confirmations: string[]
  link_ids: number[]
  reason: string
  rule: string
}

/** 변경 한 줄 (action_log.changes, ActionResult.changes) */
/** 변경 대상. 객체 = {type, id}. 관계 = {type: 'link', id: 관계 번호, rel, src?, dst?} */
export type ChangeTarget = {
  type: string
  id: string | number
  rel?: string
  src?: [string, string]
  dst?: [string, string]
}

export type Change = {
  target: ChangeTarget
  field: string
  before: unknown
  after: unknown
  rule: string | null
}

export type LastChangeStep = {
  seq: number
  action: string
  actor: string
  rule: string | null
  reason: string | null
  changes: Change[]
}

export type LastChange = {
  seq: number
  action: string
  actor: string
  applied_date: string | null
  inputs: Record<string, unknown>
  steps: LastChangeStep[]
  changes: Change[]
}

export type ActionLogRow = {
  seq: number
  action: string
  actor: string
  applied_date: string | null
  inputs: Record<string, unknown>
  changes: Change[]
  cause: Record<string, unknown>
}

export type AiLogRow = {
  seq: number
  task: string
  model: string
  inputs: Record<string, unknown>
  output: {
    ok: boolean
    received: unknown
    output: Record<string, unknown> | null
    error: string | null
    message: string | null
  }
  action_seq: number | null
}

export type Incident = {
  id: string
  status: string
  status_source: Source
  origin_lots: string[]
  start_batch: string | null
  opened_date: string
  current_date: string
  owner: string
  source: Source
}

/** 사건이 없을 때 열 수 있는 배치 (loader.openable_batches) */
export type OpenableBatch = {
  batch_id: string
  product_id: string
  production_date: string
  produced_qty: number
  qc_result: string
  claim_count: number
  confirmed_qty: number
  defect_rate_produced: number
  evidence: string[]
}

export type EmptyView = {
  incident: null
  openable_batches: OpenableBatch[]
  available_actions: AvailableAction[]
}

export type OpenView = {
  incident: Incident
  lots: Obj[]
  batches: Batch[]
  customers: Customer[]
  claims: Claim[]
  network: { used_in: Link[]; shipped_to: ShippedTo[] }
  tasks: Task[]
  decisions: Decision[]
  events: IncidentEvent[]
  plans: Plan[]
  recall_quantities: RecallQuantity[]
  held_customers: HeldCustomer[]
  warnings: Warning[]
  available_actions: AvailableAction[]
  last_change: LastChange | null
  log: { actions: ActionLogRow[]; ai: AiLogRow[] }
  thresholds: Record<string, Threshold & { rule?: string; summary?: string }>
}

export type IncidentView = EmptyView | OpenView

// ---------------------------------------------------------------------------
// 액션 (POST /api/actions/{action}, actions.ActionResult)
// ---------------------------------------------------------------------------

export type ActionResult = {
  seq: number
  auto_seqs: number[]
  changes: Change[]
  created: Ref[]
}

// ---------------------------------------------------------------------------
// 시나리오·모의 입력 예시 (GET /api/scenarios, GET /api/reply-examples)
// ---------------------------------------------------------------------------

export type ScenarioInfo = {
  name: string
  title: string
  description: string
  step_count: number
  action_count: number
  setup_count: number
}

export type ReplyExample = {
  action: string
  task_type: string | null
  customer_id: string | null
  label: string
  tone: '유리' | '불리'
  source: Source
  inputs: Record<string, unknown>
}

// ---------------------------------------------------------------------------
// AI (POST /api/ai/{task}, ai.tasks.AiResult)
// ---------------------------------------------------------------------------

export type AiTask = 'agenda_summary' | 'classify_reply' | 'review_explanation' | 'notice_draft'

export type AiResult = {
  ok: boolean
  task: string
  output: Record<string, unknown> | null
  log_id: number | null
  error: string | null
  message: string | null
  /** 재생 모드(W03_AI_REPLAY): API를 부르지 않고 저장된 답을 돌려줬다 */
  replayed: boolean
}

// ---------------------------------------------------------------------------
// 온톨로지 (GET /api/ontology, ontology.to_dict)
// ---------------------------------------------------------------------------

export type ActionInput = {
  key: string
  name: string
  type: string
  required: boolean
  description?: string
  ref_type?: string
  choices?: string[]
  /** 선택지 → 고르면 일어나는 일 (결정 창의 선택 버튼 아래에 보인다) */
  choice_effects?: Record<string, string>
  choices_from?: string
}

export type ActionDef = {
  name: string
  roles: Role[]
  inputs: ActionInput[]
  precondition: string
  effect: string
  rules: string[]
  creates_tasks: string[]
}

export type RuleDef = {
  summary: string
  places: string[]
  basis: string[]
  extension: boolean
  threshold: Threshold | null
}

export type StateMachine = {
  name: string
  states: string[]
  initial: string[]
  transitions: { from: string; to: string; by: string }[]
  /** 아직 판정이 끝나지 않은 것으로 보는 상태 (클레임) */
  unconfirmed_states?: string[] | null
}

export type ObjectTypeDef = {
  name: string
  description: string
  default_source: Source[]
  stored: { key: string; name: string }[]
  derived: { key: string; name: string; rules: string[]; basis?: string }[]
  state: { attribute: string; kind: string } | null
}

export type RelationDef = {
  from: string[]
  to: string[]
  to_links: string[]
  default_source: Source[]
  uses_confirmation: boolean
  uses_quantity: boolean
  attributes: unknown[]
  basis: string
}

export type TaskTypeDef = {
  code: string
  departments: string[]
  targets: string[]
  rules: string[]
  allowed_results: { result: string; effect: string }[]
  basis?: string | null
  /** 회신 없이 끝나는 조건 */
  auto_complete?: string | null
}

export type Ontology = {
  sources: Source[]
  confirmation_levels: string[]
  confirmed_levels: string[]
  quantity_bases: string[]
  roles: Record<Role, { name: string; basis: string }>
  departments: string[]
  event_types: string[]
  decision_types: string[]
  committee_results: string[]
  plan_decision_results: string[]
  ai_uninterpretable: string
  task_deadline: Threshold
  object_types: Record<string, ObjectTypeDef>
  link_attributes: { key: string; name: string }[]
  relations: Record<string, RelationDef>
  state_machines: Record<string, StateMachine>
  incident_statuses: { name: string; condition: string }[]
  rule_places: string[]
  rules: Record<string, RuleDef>
  task_types: Record<string, TaskTypeDef>
  actions: Record<string, ActionDef>
  auto_processes: Record<string, { name: string; trigger: string; effect: string; rules: string[]; basis?: string | null }>
  /** 가정 목록 (brain/3-design/assumptions.md의 표 그대로): 가정, 원본에 없는 이유·근거, 출처 문서 */
  assumptions: { id: string; text: string; reason: string; doc: string }[]
}
