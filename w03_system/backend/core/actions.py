"""액션 실행기: 상태는 여기서만 바뀐다.

기준: brain/3-design/architecture.md 패턴 2 "상태는 액션 실행기로만 바뀐다", 액션 실행기 시그니처,
business-model.md §4(상태), §5(규칙), §8-4(관계 속성), §8-5(액션·자동 처리·액션 기록), §8-6.

- 검사·실행 순서: 액션 정의 → 역할 → 입력 형식 → 전제 조건 → 실행(적용일 전진 → 효과 → 기록)
  → 자동 처리 연쇄(하나마다 기록) → 커밋. 어디서든 실패하면 롤백한다(액션 하나 = 트랜잭션 하나).
- 판단(불량률·해제 조건·출하처 공백·경고)은 core/rules.py에 묻는다. 여기서 다시 계산하지 않는다.
- 상태 전이는 모두 ontology.can_transition()을 지난다. 모든 변경은 changes에 이전 → 이후와 규칙으로 남는다.
- ID는 종류별 순번(INC-001, T-001, DEC-001, EV-001, QC-M-001)이다. 시각·난수를 쓰지 않는다.
  재공급 계획은 버전에서(RP-v1), 계획 줄은 버전·순위에서(RP-v1-01) 만든다.

확장 방법(다음 step):
- 사람 액션: `_SPECS[이름] = _Spec(check=..., apply=..., targets=...)` 한 줄을 더한다.
  check(ctx, inputs)는 전제 조건 위반 시 ActionError('precondition'), apply(ctx, inputs)는 효과를 낸다
  (ctx.create_object / set_state / set_attrs / create_link / set_confirm만 쓴다),
  targets(conn, actor)는 버튼 대상 dict 또는 None(지금 실행할 수 없음).
- 자동 처리: `AUTO_PROCESSES` 목록에 함수를 더한다. 함수는 ctx를 받아 **변경 하나**를 하고
  {'name', 'rule', 'reason'}을 돌려주거나, 할 것이 없으면 None을 돌려준다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Callable

from backend.core import db, loader, ontology, rules

SYSTEM_ACTOR = "시스템"
INCIDENT_ID = "INC-001"
MAX_AUTO_STEPS = 200  # 자동 처리 연쇄 안전 상한 (무한 전이 방지)

# 이름은 ontology 정의의 값을 그대로 쓴다
NORMAL, OBSERVE, RELEASED, OVER = rules.NORMAL, rules.OBSERVE, rules.RELEASED, rules.OVER
SUBMITTED, RECALL, PARTIAL, INVESTIGATE, RESUBMIT = (rules.SUBMITTED, rules.RECALL, rules.PARTIAL,
                                                      rules.INVESTIGATE, rules.RESUBMIT)
TASK_OPEN = rules.TASK_OPEN
CLAIM_RECEIVED, CLAIM_CONFIRMED = "접수", "확정"
UNCONFIRMED, REQUESTED = "미확인", "확인요청중"
NO_QTY_BASIS = ontology.QUANTITY_BASES[2]  # "없음"
EV_CLAIM, EV_NEWS = ontology.EVENT_TYPES[0], ontology.EVENT_TYPES[1]  # "클레임 접수", "보도"
APPROVE, CONDITIONAL, REJECT = ontology.COMMITTEE_RESULTS
TASK_HOLD_SHIPMENT = "출하 경위 확인"
TASK_SHIP_CHECK = "출하처 확인"
TASK_NOTICE = "안내 대상 결정"
TASK_INVESTIGATION = "원인 조사"
COMMITTEE_ROLE_NAME = ontology.ROLES["quality_committee"]["name"]
OWNER_ROLE_NAME = ontology.ROLES["quality_owner"]["name"]
R5_WARNINGS = ("held_batch_shipped", "held_lot_used", "record_conflict")
SUBMITTABLE = (OVER, RESUBMIT)
assert {CLAIM_RECEIVED, CLAIM_CONFIRMED} <= set(ontology.STATE_MACHINES["claim"]["states"])
assert {UNCONFIRMED, REQUESTED} <= set(ontology.CONFIRMATION_LEVELS)
assert all(ontology.task_type_def(t) for t in (TASK_HOLD_SHIPMENT, TASK_SHIP_CHECK, TASK_NOTICE,
                                               TASK_INVESTIGATION))

TASK_REPLIED, TASK_DONE = rules.TASK_REPLIED, rules.TASK_DONE
PLAN_DRAFT, PLAN_CONFIRMED, PLAN_REJECTED, PLAN_REPLACED = ontology.STATE_MACHINES["plan"]["states"]
REPLY_CONFIRMED, REPLY_NO_IMPACT = "회신확인", "영향없음"
CLAIM_QTY_BASIS = ontology.QUANTITY_BASES[1]  # "클레임 합(하한)"
EV_REPLY = ontology.EVENT_TYPES[2]  # "회신"
PLAN_APPROVE, PLAN_REJECT = ontology.PLAN_DECISION_RESULTS
TASK_RESUPPLY_REQ = "재공급 요청"
TASK_ORDER_DROP = rules.ORDER_DROP_TASK
TASK_CAPACITY = rules.CAPACITY_TASK
TASK_RESULT_NOTICE = "결과 통보"
SCM_ROLE_NAME = ontology.ROLES["scm"]["name"]
# 회신 결과 → 작업을 닫지 않고 기한만 연장하는 결과 (A-17)
EXTEND_RESULTS = {"확인 불가", "원인 미확인"}
assert {REPLY_CONFIRMED, REPLY_NO_IMPACT} <= set(ontology.CONFIRMATION_LEVELS)
assert all(ontology.task_type_def(t) for t in (TASK_RESUPPLY_REQ, TASK_ORDER_DROP, TASK_RESULT_NOTICE))
assert EXTEND_RESULTS <= {r["result"] for t in ontology.TASK_TYPES.values() for r in t["allowed_results"]}

ID_PREFIX = {"incident": "INC-", "task": "T-", "decision": "DEC-", "event": "EV-", "claim": "QC-M-"}


# ---------------------------------------------------------------------------
# 공개 타입
# ---------------------------------------------------------------------------


class ActionError(Exception):
    """code: 'unknown_action' | 'forbidden' | 'invalid_input' | 'precondition'. message: 사람이 읽는 한국어 사유."""

    def __init__(self, code: str, message: str):
        super().__init__(f"[{code}] {message}")
        self.code = code
        self.message = message


@dataclass
class ActionResult:
    seq: int                 # 이 액션의 action_log 순번 (reset은 기록이 비므로 0)
    auto_seqs: list[int]     # 뒤따른 자동 처리의 순번들
    changes: list[dict]      # 이 액션과 자동 처리가 바꾼 것 전체 (대상, 필드, 이전, 이후, 규칙)
    created: list[dict]      # 새로 만든 객체 (타입, ID)


# ---------------------------------------------------------------------------
# 실행 문맥: 모든 쓰기는 여기를 지난다
# ---------------------------------------------------------------------------


class _Ctx:
    def __init__(self, conn, applied_date: str | None):
        self.conn = conn
        self.applied_date = applied_date
        self.step_changes: list[dict] = []   # 지금 기록 중인 action_log 한 줄의 변경
        self.all_changes: list[dict] = []
        self.created: list[dict] = []

    # --- 기록 ---
    def _record(self, target: dict, field_: str, before, after, rule) -> None:
        ch = {"target": target, "field": field_, "before": before, "after": after, "rule": rule}
        self.step_changes.append(ch)
        self.all_changes.append(ch)

    def flush(self) -> list[dict]:
        out, self.step_changes = self.step_changes, []
        return out

    # --- 객체 ---
    def new_id(self, type_: str) -> str:
        prefix = ID_PREFIX[type_]
        nums = [int(o["id"][len(prefix):]) for o in db.list_objects(self.conn, type_)
                if o["id"].startswith(prefix) and o["id"][len(prefix):].isdigit()]
        return f"{prefix}{max(nums, default=0) + 1:03d}"

    def create_object(self, type_, id_, attrs, *, state=None, source, evidence=None, rule) -> None:
        machine = ontology.OBJECT_TYPES[type_]["state"]
        if state is not None and state not in ontology.STATE_MACHINES[machine["kind"]]["initial"]:
            raise AssertionError(f"초기 상태가 아니다: {type_} {state}")
        db.put_object(self.conn, type_, id_, attrs, state=state, source=source, evidence=evidence)
        self.created.append({"type": type_, "id": id_})
        self._record({"type": type_, "id": id_}, "created", None, state or "생성", rule)

    def set_state(self, type_, id_, to: str, rule) -> None:
        obj = db.get_object(self.conn, type_, id_)
        kind = ontology.OBJECT_TYPES[type_]["state"]["kind"]
        if not ontology.can_transition(kind, obj["state"], to):
            raise AssertionError(f"전이표에 없는 전이: {type_} {id_} {obj['state']} → {to}")
        db.update_object(self.conn, type_, id_, state=to)
        self._record({"type": type_, "id": id_}, "state", obj["state"], to, rule)

    def set_attrs(self, type_, id_, attrs: dict, rule) -> None:
        obj = db.get_object(self.conn, type_, id_)
        changed = {k: v for k, v in attrs.items() if obj["attrs"].get(k) != v}
        if not changed:
            return
        db.update_object(self.conn, type_, id_, attrs=changed)
        for k, v in changed.items():
            self._record({"type": type_, "id": id_}, k, obj["attrs"].get(k), v, rule)

    # --- 관계 ---
    def create_link(self, rel, src, dst, *, source, rule, **kw) -> int:
        link_id = db.put_link(self.conn, rel, src, dst, source=source, applied_date=self.applied_date,
                              recorded_date=self.applied_date, **kw)
        self._record({"type": "link", "rel": rel, "id": link_id,
                      "src": list(src), "dst": list(dst)}, "created", None,
                     kw.get("confirm", ontology.DEFAULT_CONFIRMATION), rule)
        return link_id

    def set_confirm(self, link_id: int, to: str, rule) -> None:
        link = db.get_link(self.conn, link_id)
        if not ontology.can_transition("shipped_to", link["confirm"], to):
            raise AssertionError(f"전이표에 없는 전이: 관계 {link_id} {link['confirm']} → {to}")
        db.update_link(self.conn, link_id, confirm=to, applied_date=self.applied_date)
        self._record({"type": "link", "rel": link["rel"], "id": link_id}, "confirm", link["confirm"], to, rule)

    def set_link_fields(self, link_id: int, fields: dict, rule) -> None:
        """관계 한 줄의 수량·수량 근거·근거 참조 등을 바꾼다 (확인 수준은 set_confirm으로만)."""
        link = db.get_link(self.conn, link_id)
        changed = {k: v for k, v in fields.items() if link[k] != v}
        if not changed:
            return
        db.update_link(self.conn, link_id, **changed)
        for k, v in changed.items():
            self._record({"type": "link", "rel": link["rel"], "id": link_id}, k, link[k], v, rule)


# ---------------------------------------------------------------------------
# 조회 도우미 (상태를 바꾸지 않는다)
# ---------------------------------------------------------------------------


def _incident(conn) -> dict | None:
    items = db.list_objects(conn, "incident")
    return items[0] if items else None


def _today(conn) -> str:
    return _incident(conn)["attrs"]["current_date"]


def _incident_batch_ids(conn) -> list[str]:
    return sorted({l["src_id"] for l in db.find_links(conn, rel="PART_OF")})


def _batches_in(conn, states) -> list[str]:
    return [b for b in _incident_batch_ids(conn) if db.get_object(conn, "batch", b)["state"] in states]


def _pending_claim_ids(conn) -> list[str]:
    in_scope = set(_incident_batch_ids(conn))
    out = []
    for c in db.list_objects(conn, "claim"):
        if not rules._is_pending(c):
            continue
        on = db.find_links(conn, rel="CLAIMED_ON", src=("claim", c["id"]))
        if on and on[0]["dst_id"] in in_scope:
            out.append(c["id"])
    return out


def _origin_lots(conn) -> list[str]:
    return list(_incident(conn)["attrs"].get("origin_lots") or [])


def _add_days(s: str, days: int) -> str:
    return (date.fromisoformat(s) + timedelta(days=days)).isoformat()


def _due(applied_date: str) -> str:
    return _add_days(applied_date, ontology.TASK_DEADLINE["value"])


def _customers_of(conn, batch_ids, levels) -> list[dict]:
    """배치들의 SHIPPED_TO 중 확인 수준이 levels인 고객 → [{customer_id, batch_ids}]."""
    agg: dict[str, set] = {}
    for b in batch_ids:
        for l in db.find_links(conn, rel="SHIPPED_TO", src=("batch", b)):
            if l["confirm"] in levels:
                agg.setdefault(l["dst_id"], set()).add(b)
    return [{"customer_id": c, "batch_ids": sorted(bs)} for c, bs in sorted(agg.items())]


# ---------------------------------------------------------------------------
# 공통 효과
# ---------------------------------------------------------------------------


def _create_task(ctx: _Ctx, task_type: str, extra: dict, *, targets: list[tuple], rule: str,
                 decision_id: str | None = None, evidence=None) -> str:
    tdef = ontology.task_type_def(task_type)
    tid = ctx.new_id("task")
    attrs = {
        "type": task_type,
        "code": tdef["code"],
        "department": "·".join(tdef["departments"]),
        "due_date": _due(ctx.applied_date),
        "reply": None,
        "result": None,
        "replied_date": None,
        "created_date": ctx.applied_date,
        "created_by": {"rule": rule, "decision": decision_id},
        **extra,
    }
    ctx.create_object("task", tid, attrs, state=TASK_OPEN, source="시스템", evidence=evidence, rule=rule)
    if decision_id:
        ctx.create_link("CREATES", ("decision", decision_id), ("task", tid), source="시스템", rule=rule,
                        evidence=[rule])
    for dst in targets:
        ctx.create_link("TARGETS", ("task", tid), dst, source="시스템", rule=rule)
    return tid


def _handle_unconfirmed_exposures(ctx: _Ctx) -> None:
    """R8: 클레임 고객이 그 배치의 출하처에 없음 → SHIPPED_TO(미확인) + 고객당 출하처 확인 작업 → 확인요청중."""
    by_customer: dict[str, list[tuple[int, dict]]] = {}
    for e in rules.unconfirmed_exposures(ctx.conn):
        link_id = ctx.create_link("SHIPPED_TO", ("batch", e["batch_id"]), ("customer", e["customer_id"]),
                                  source="도출", rule="R8", confirm=UNCONFIRMED, qty=None,
                                  qty_basis=NO_QTY_BASIS, evidence=e["claim_ids"],
                                  attrs={"claim_qty": e["claim_qty"]})
        by_customer.setdefault(e["customer_id"], []).append((link_id, e))
    for cust, items in sorted(by_customer.items()):
        _create_task(ctx, TASK_SHIP_CHECK, {
            "customer_id": cust,
            "batch_ids": [e["batch_id"] for _, e in items],
            "claim_ids": sorted(c for _, e in items for c in e["claim_ids"]),
        }, targets=[("SHIPPED_TO", str(link_id)) for link_id, _ in items], rule="R8",
            evidence=sorted(c for _, e in items for c in e["claim_ids"]))
        for link_id, _ in items:
            ctx.set_confirm(link_id, REQUESTED, "R8")


def _advance_date(ctx: _Ctx) -> None:
    inc = _incident(ctx.conn)
    if inc is not None:
        ctx.set_attrs("incident", inc["id"], {"current_date": ctx.applied_date}, "§4-5")


# ---------------------------------------------------------------------------
# 사람 액션: 전제 조건 · 효과 · 버튼 대상
# ---------------------------------------------------------------------------


def _require_incident(ctx: _Ctx) -> None:
    if _incident(ctx.conn) is None:
        raise ActionError("precondition", "열린 사건이 없다")


def _require_in_incident(ctx: _Ctx, batch_ids) -> None:
    missing = [b for b in batch_ids if b not in _incident_batch_ids(ctx.conn)]
    if missing:
        raise ActionError("precondition", f"사건에 묶이지 않은 배치: {', '.join(missing)}")


# --- open_incident ---

def _openable_ids(conn) -> list[str] | None:
    if _incident(conn) is not None:
        return None
    return [b["batch_id"] for b in loader.openable_batches()]


def _check_open(ctx, inp):
    ids = _openable_ids(ctx.conn)
    if ids is None:
        raise ActionError("precondition", "이미 열린 사건이 있다 (사건은 한 번에 하나)")
    if inp["batch_id"] not in ids:
        raise ActionError("precondition", f"클레임이 없는 배치는 사건을 열 수 없다: {inp['batch_id']}")


def _apply_open(ctx, inp):
    conn, start = ctx.conn, inp["batch_id"]
    scope = loader.load_incident_scope(conn, start)
    ctx.create_object("incident", INCIDENT_ID, {
        "owner": OWNER_ROLE_NAME,
        "opened_date": ctx.applied_date,
        "current_date": ctx.applied_date,
        "origin_lots": scope["origin_lots"],
        "start_batch": start,
    }, source="시스템", rule="R4")
    for b in scope["batches"]:
        reason = "클레임" if b == start else "로트 공유(R4)"
        ctx.create_link("PART_OF", ("batch", b), ("incident", INCIDENT_ID), source="시스템",
                        rule="R4", attrs={"reason": reason})

    # R5 (+ R5-1 근거): QC 보류 배치에 출하 기록 → 출하 경위 확인 작업 하나
    ws = [w for w in rules.warnings(conn, ctx.applied_date) if w["code"] in R5_WARNINGS]
    held = sorted({w["target"]["id"] for w in ws if w["code"] == "held_batch_shipped"})
    if held:
        basis = [{k: w[k] for k in ("code", "rule", "target", "message")} for w in ws]
        evidence = list(dict.fromkeys(e for w in ws for e in w["evidence"]))
        _create_task(ctx, TASK_HOLD_SHIPMENT, {"batch_ids": held, "basis_warnings": basis},
                     targets=[("batch", b) for b in held], rule="R5", evidence=evidence)

    _handle_unconfirmed_exposures(ctx)  # R8
    return {"rules": ["R4", "R5", "R5-1", "R8"], "scope": scope}


def _targets_open(conn, actor):
    ids = _openable_ids(conn)
    return None if ids is None else {"batch_id": ids}


# --- register_claim ---

def _check_register_claim(ctx, inp):
    _require_incident(ctx)
    _require_in_incident(ctx, [inp["batch_id"]])
    if db.get_object(ctx.conn, "customer", inp["customer_id"]) is None:
        raise ActionError("precondition", f"사건 범위에 없는 고객: {inp['customer_id']}")
    if inp["received_date"] > ctx.applied_date:
        raise ActionError("invalid_input", "접수일이 적용일보다 늦다")


def _apply_register_claim(ctx, inp):
    conn = ctx.conn
    confirmed = inp["status"] == CLAIM_CONFIRMED
    cid = ctx.new_id("claim")
    ctx.create_object("claim", cid, {
        "received_date": inp["received_date"],
        "type": inp.get("claim_type"),
        "defect_confirmed": confirmed,
        "qty": inp["qty"],
        "confirmed_date": ctx.applied_date if confirmed else None,
        "source": "모의",
    }, state=inp["status"], source="모의", rule="R7" if confirmed else "R7-1")
    claim = ("claim", cid)
    ctx.create_link("CLAIMED_ON", claim, ("batch", inp["batch_id"]), source="모의", rule="R7")
    ctx.create_link("CLAIMED_BY", claim, ("customer", inp["customer_id"]), source="모의", rule="R7")
    for lot in _origin_lots(conn):
        ctx.create_link("CLAIMED_LOT", claim, ("material_lot", lot), source="모의", rule="R4")

    ev = ctx.new_id("event")
    ctx.create_object("event", ev, {
        "type": EV_CLAIM, "occurred_date": inp["received_date"], "applied_date": ctx.applied_date,
        "content": f"{inp['batch_id']} {inp['customer_id']} {inp['qty']:,} EA ({inp['status']})",
        "source": "모의", "claim_id": cid,
    }, source="모의", rule="R7")
    ctx.create_link("TRIGGERS", ("event", ev), ("incident", INCIDENT_ID), source="모의", rule="R7")

    _handle_unconfirmed_exposures(ctx)  # R8 (그 고객이 그 배치의 출하처에 없을 때만 생긴다)
    return {"rules": ["R7", "R7-1", "R6-2", "R8"], "event": ev, "claim": cid}


def _targets_register_claim(conn, actor):
    if _incident(conn) is None:
        return None
    return {"batch_id": _incident_batch_ids(conn)}


# --- resolve_claim ---

def _check_resolve_claim(ctx, inp):
    _require_incident(ctx)
    if inp["claim_id"] not in _pending_claim_ids(ctx.conn):
        raise ActionError("precondition", f"미확정(접수·조사중) 클레임이 아니다: {inp['claim_id']}")


def _apply_resolve_claim(ctx, inp):
    cid, result = inp["claim_id"], inp["result"]
    rule = "R7" if result == CLAIM_CONFIRMED else "R6-2"
    ctx.set_state("claim", cid, result, rule)
    if result == CLAIM_CONFIRMED:
        ctx.set_attrs("claim", cid, {"defect_confirmed": True, "confirmed_date": ctx.applied_date}, rule)
    return {"rules": [rule]}


def _targets_resolve_claim(conn, actor):
    if _incident(conn) is None:
        return None
    ids = _pending_claim_ids(conn)
    return {"claim_id": ids} if ids else None


# --- register_news ---

def _check_news(ctx, inp):
    _require_incident(ctx)


def _apply_news(ctx, inp):
    conn = ctx.conn
    source_ref = inp.get("source_ref")
    ev = ctx.new_id("event")
    src = "원본" if source_ref else "모의"
    ctx.create_object("event", ev, {
        "type": EV_NEWS, "occurred_date": inp.get("occurred_date"), "applied_date": ctx.applied_date,
        "content": inp["content"], "source": src, "source_ref": source_ref,
    }, source=src, evidence=[source_ref] if source_ref else None, rule="R3")
    ctx.create_link("TRIGGERS", ("event", ev), ("incident", INCIDENT_ID), source=src, rule="R3")
    # R3: 판정은 바꾸지 않는다. 보도 전·후 판정 상태와 결론 유지 근거를 재검토 기록으로 남긴다
    states = [{"batch_id": b, "before": db.get_object(conn, "batch", b)["state"],
               "after": db.get_object(conn, "batch", b)["state"]} for b in _incident_batch_ids(conn)]
    r3 = ontology.rule_def("R3")
    return {"rules": ["R3"], "event": ev, "review": {
        "conclusion": "판정 유지",
        "batches": states,
        "basis": r3["summary"],
        "basis_source": r3["basis"],
    }}


def _targets_news(conn, actor):
    return None if _incident(conn) is None else {}


# --- submit_agenda ---

def _check_submit(ctx, inp):
    _require_incident(ctx)
    _require_in_incident(ctx, inp["batch_ids"])
    bad = [b for b in inp["batch_ids"] if db.get_object(ctx.conn, "batch", b)["state"] not in SUBMITTABLE]
    if bad:
        raise ActionError("precondition",
                          f"기준초과(미상신) 또는 재상신 후보가 아닌 배치: {', '.join(bad)}")


def _apply_submit(ctx, inp):
    for b in inp["batch_ids"]:
        ctx.set_state("batch", b, SUBMITTED, "R2")
    return {"rules": ["R2", "R12"], "agenda_summary": inp.get("agenda_summary"),
            "ai_log_id": inp.get("ai_log_id")}


def _targets_submit(conn, actor):
    if _incident(conn) is None:
        return None
    ids = _batches_in(conn, SUBMITTABLE)
    return {"batch_ids": ids} if ids else None


# --- committee_decision ---

def _check_committee(ctx, inp):
    _require_incident(ctx)
    _require_in_incident(ctx, inp["batch_ids"])
    bad = [b for b in inp["batch_ids"] if db.get_object(ctx.conn, "batch", b)["state"] != SUBMITTED]
    if bad:
        raise ActionError("precondition", f"상신중이 아닌 배치: {', '.join(bad)}")
    if inp["result"] == REJECT and not (inp.get("reason") or "").strip():
        raise ActionError("precondition", "거절은 사유가 필수다 (A-09)")


def _apply_committee(ctx, inp):
    conn, result, batch_ids = ctx.conn, inp["result"], inp["batch_ids"]
    dec = ctx.new_id("decision")
    ctx.create_object("decision", dec, {
        "type": ontology.DECISION_TYPES[0], "decider": COMMITTEE_ROLE_NAME, "result": result,
        "reason": inp.get("reason"), "applied_date": ctx.applied_date,
    }, source="모의", rule="R9")
    for b in batch_ids:
        ctx.create_link("DECIDES", ("decision", dec), ("batch", b), source="모의", rule="R9")

    to = {APPROVE: RECALL, CONDITIONAL: PARTIAL, REJECT: INVESTIGATE}[result]
    for b in batch_ids:
        ctx.set_state("batch", b, to, "R9")

    if result == REJECT:
        _create_task(ctx, TASK_INVESTIGATION, {"batch_ids": list(batch_ids), "reject_reason": inp["reason"]},
                     targets=[("batch", b) for b in batch_ids], rule="R9", decision_id=dec)
    else:
        # R9-1: 안내 후보만 제시하고 영업이 대상을 결정한다
        recall = _customers_of(conn, batch_ids, rules.CONFIRMED_LEVELS)
        watch = _customers_of(conn, _batches_in(conn, (OBSERVE, RELEASED)), rules.CONFIRMED_LEVELS)
        customers = sorted({c["customer_id"] for c in recall + watch})
        _create_task(ctx, TASK_NOTICE, {
            "batch_ids": list(batch_ids),
            "candidates": {"recall_batch_customers": recall, "watch_batch_customers": watch},
        }, targets=[("customer", c) for c in customers], rule="R9-1", decision_id=dec)
    return {"rules": ["R9", "R9-1", "R12"], "decision": dec}


def _targets_committee(conn, actor):
    if _incident(conn) is None:
        return None
    ids = _batches_in(conn, (SUBMITTED,))
    return {"batch_ids": ids} if ids else None


# --- apply_reply ---

def _allowed_results(task: dict) -> list[str]:
    return [r["result"] for r in ontology.task_type_def(task["attrs"]["type"])["allowed_results"]]


def _task_targets(conn, task_id: str, dst_type: str) -> list[str]:
    return [l["dst_id"] for l in db.find_links(conn, rel="TARGETS", src=("task", task_id))
            if l["dst_type"] == dst_type]


def _check_reply(ctx, inp):
    _require_incident(ctx)
    task = db.get_object(ctx.conn, "task", inp["task_id"])
    if task is None:
        raise ActionError("precondition", f"없는 작업: {inp['task_id']}")
    if task["state"] != TASK_OPEN:
        raise ActionError("precondition", f"열린 작업이 아니다: {task['id']} ({task['state']})")
    allowed = _allowed_results(task)
    if not allowed:
        raise ActionError("precondition", f"'{task['attrs']['type']}' 작업은 회신을 받지 않는다")
    if inp["result"] not in allowed:  # '해석 불가'도 여기서 거부된다 (R12)
        raise ActionError("precondition",
                          f"'{task['attrs']['type']}' 작업의 허용 결과가 아니다: {inp['result']} (허용: {allowed})")


def _apply_reply(ctx, inp):
    conn, tid, result = ctx.conn, inp["task_id"], inp["result"]
    task = db.get_object(conn, "task", tid)
    ttype = task["attrs"]["type"]
    rule = (ontology.task_type_def(ttype)["rules"] or ["R12"])[0]

    ev = ctx.new_id("event")
    ctx.create_object("event", ev, {
        "type": EV_REPLY, "occurred_date": ctx.applied_date, "applied_date": ctx.applied_date,
        "content": inp["reply_text"], "source": "모의", "task_id": tid, "result": result,
        "ai_log_id": inp.get("ai_log_id"),
    }, source="모의", rule=rule)
    ctx.create_link("ANSWERS", ("event", ev), ("task", tid), source="모의", rule=rule)
    ctx.create_link("TRIGGERS", ("event", ev), ("incident", INCIDENT_ID), source="모의", rule=rule)
    replies = list(task["attrs"].get("replies") or []) + [
        {"event": ev, "result": result, "applied_date": ctx.applied_date}]
    ctx.set_attrs("task", tid, {"reply": inp["reply_text"], "result": result,
                                "replied_date": ctx.applied_date, "replies": replies}, rule)

    if result in EXTEND_RESULTS:  # 작업은 열림 그대로, 기한만 연장 (A-17)
        ctx.set_attrs("task", tid, {"due_date": _due(ctx.applied_date)}, "A-17")
        return {"rules": [rule, "R12"], "event": ev, "task_id": tid, "result": result}

    ctx.set_state("task", tid, TASK_REPLIED, rule)
    if ttype == TASK_SHIP_CHECK:
        for lid in _task_targets(conn, tid, "SHIPPED_TO"):
            link = db.get_link(conn, int(lid))
            if result == "출하 확인":  # R10-2, A-14: 수량 기록이 없으므로 클레임 수량 합을 하한으로
                ctx.set_confirm(link["link_id"], REPLY_CONFIRMED, "R8")
                ctx.set_link_fields(link["link_id"], {
                    "qty": rules._claim_sum(conn, link["src_id"], link["dst_id"]),
                    "qty_basis": CLAIM_QTY_BASIS,
                    "evidence": list(link["evidence"] or []) + [ev],
                }, "R10-2")
            else:  # 영향없음: 줄을 지우지 않는다
                ctx.set_confirm(link["link_id"], REPLY_NO_IMPACT, "R8")
                ctx.set_link_fields(link["link_id"], {"evidence": list(link["evidence"] or []) + [ev]}, "R8")
    elif ttype == TASK_NOTICE:  # R9-1: 영업이 고른 범위로 안내 대상 확정
        cand = task["attrs"].get("candidates") or {}
        groups = ["recall_batch_customers"] + (["watch_batch_customers"] if result != "회수 배치 고객만" else [])
        targets = sorted({c["customer_id"] for g in groups for c in cand.get(g, [])})
        ctx.set_attrs("task", tid, {"notice_customers": targets}, "R9-1")
    elif ttype == TASK_INVESTIGATION and result == "원인 확인":
        for b in _task_targets(conn, tid, "batch"):
            if db.get_object(conn, "batch", b)["state"] == INVESTIGATE:
                ctx.set_state("batch", b, RESUBMIT, "R9")
    # 출하 경위 확인·수주 급감 확인·능력 확보 검토·결과 통보: 대상 변화 없음 (계획은 자동 처리가 다시 계산한다)
    ctx.set_state("task", tid, TASK_DONE, rule)
    return {"rules": [rule, "R12"], "event": ev, "task_id": tid, "result": result}


def _targets_reply(conn, actor):
    if _incident(conn) is None:
        return None
    items = [{"id": t["id"], "type": t["attrs"]["type"], "allowed_results": _allowed_results(t)}
             for t in db.list_objects(conn, "task") if t["state"] == TASK_OPEN and _allowed_results(t)]
    return {"task_id": items} if items else None


# --- plan_decision ---

def _check_plan_decision(ctx, inp):
    _require_incident(ctx)
    plan = db.get_object(ctx.conn, "resupply_plan", inp["plan_id"])
    if plan is None:
        raise ActionError("precondition", f"없는 재공급 계획: {inp['plan_id']}")
    if plan["state"] != PLAN_DRAFT:
        raise ActionError("precondition", f"초안이 아닌 계획: {plan['id']} ({plan['state']})")
    if inp["result"] == PLAN_REJECT and not (inp.get("reason") or "").strip():
        raise ActionError("precondition", "거절은 근거가 필수다")
    if inp["result"] == PLAN_APPROVE:
        cond = rules.supply_condition(ctx.conn, plan["id"])
        if not cond["met"]:
            raise ActionError("precondition", f"출고 조건(R11) 미충족: {cond['reason']}")
        open_hold = rules.open_hold_shipment_tasks(ctx.conn)
        if open_hold and not (inp.get("reason") or "").strip():
            raise ActionError("precondition",
                              f"출하 경위 확인 대기 {len(open_hold)}건: 승인하려면 근거가 필수다 (R11-1)")


def _apply_plan_decision(ctx, inp):
    conn, pid, result = ctx.conn, inp["plan_id"], inp["result"]
    hold_open = result == PLAN_APPROVE and bool(rules.open_hold_shipment_tasks(conn))  # R11-1
    dec = ctx.new_id("decision")
    ctx.create_object("decision", dec, {
        "type": ontology.DECISION_TYPES[1], "decider": SCM_ROLE_NAME, "result": result,
        "reason": inp.get("reason"), "applied_date": ctx.applied_date,
    }, source="모의", rule="R12")
    ctx.create_link("DECIDES", ("decision", dec), ("resupply_plan", pid), source="모의", rule="R12")
    ctx.set_state("resupply_plan", pid, PLAN_CONFIRMED if result == PLAN_APPROVE else PLAN_REJECTED,
                  "R11" if result == PLAN_APPROVE else "R12")
    if result == PLAN_APPROVE:  # 유효 계획은 하나: 이전 확정 버전은 대체됨
        for p in _plans(conn):
            if p["id"] != pid and p["state"] == PLAN_CONFIRMED:
                ctx.set_state("resupply_plan", p["id"], PLAN_REPLACED, "R12")
    if result == PLAN_REJECT:  # 구현 기본값 ③: 영업 임원에게 결과 통보
        _create_task(ctx, TASK_RESULT_NOTICE, {"plan_id": pid, "reject_reason": inp["reason"]},
                     targets=[("resupply_plan", pid)], rule="R12", decision_id=dec)
    for t in db.list_objects(conn, "task"):  # 구현 기본값 ②: 재공급 요청 자동 완료
        if t["attrs"].get("type") == TASK_RESUPPLY_REQ and t["state"] == TASK_OPEN:
            ctx.set_state("task", t["id"], TASK_REPLIED, "R9")
            ctx.set_state("task", t["id"], TASK_DONE, "R9")
    return {"rules": ["R11", "R11-1", "R12"] if hold_open else ["R11", "R12"], "decision": dec}


def _targets_plan_decision(conn, actor):
    if _incident(conn) is None:
        return None
    items = []
    reason_required = bool(rules.open_hold_shipment_tasks(conn))  # R11-1
    for p in db.list_objects(conn, "resupply_plan"):
        if p["state"] != PLAN_DRAFT:
            continue
        cond = rules.supply_condition(conn, p["id"])
        items.append({"id": p["id"], "version": p["attrs"]["version"], "supply_condition_met": cond["met"],
                      "can_approve": cond["met"], "reason": cond["reason"],
                      "approve_reason_required": reason_required})
    return {"plan_id": items} if items else None


# --- reset ---

def _apply_reset(ctx, inp):
    db.reset(ctx.conn)
    return {}


# ---------------------------------------------------------------------------
# 액션 등록
# ---------------------------------------------------------------------------


@dataclass
class _Spec:
    check: Callable[[_Ctx, dict], None]
    apply: Callable[[_Ctx, dict], dict]
    targets: Callable[[object, str], dict | None]
    needs_date: bool = True   # 적용일 전진·자동 처리 연쇄를 하는가 (reset만 False)
    extra_inputs: tuple = field(default_factory=tuple)  # 온톨로지 정의 밖의 선택 입력


def _no_check(ctx, inp):
    return None


_SPECS: dict[str, _Spec] = {
    "open_incident": _Spec(_check_open, _apply_open, _targets_open),
    "register_claim": _Spec(_check_register_claim, _apply_register_claim, _targets_register_claim,
                            extra_inputs=("claim_type",)),
    "resolve_claim": _Spec(_check_resolve_claim, _apply_resolve_claim, _targets_resolve_claim),
    "register_news": _Spec(_check_news, _apply_news, _targets_news, extra_inputs=("source_ref",)),
    "submit_agenda": _Spec(_check_submit, _apply_submit, _targets_submit, extra_inputs=("ai_log_id",)),
    "committee_decision": _Spec(_check_committee, _apply_committee, _targets_committee),
    "apply_reply": _Spec(_check_reply, _apply_reply, _targets_reply, extra_inputs=("ai_log_id",)),
    "plan_decision": _Spec(_check_plan_decision, _apply_plan_decision, _targets_plan_decision),
    "reset": _Spec(_no_check, _apply_reset, lambda conn, actor: {}, needs_date=False),
}


# ---------------------------------------------------------------------------
# 자동 처리
# ---------------------------------------------------------------------------


def _auto_name(frm: str, to: str) -> str:
    if to == RELEASED:
        return ontology.AUTO_PROCESSES["release_observation"]["name"]      # 관찰 해제
    if frm == RELEASED and to == OBSERVE:
        return ontology.AUTO_PROCESSES["return_to_observation"]["name"]    # 관찰 복귀
    if frm == PARTIAL:
        return ontology.AUTO_PROCESSES["complete_partial_recall"]["name"]  # 부분회수 완료 판정
    return ontology.AUTO_PROCESSES["recalculate_judgment"]["name"]         # 판정 재계산


def _auto_batch_judgment(ctx: _Ctx) -> dict | None:
    """사건에 묶인 배치 중 rules.target_batch_state()가 바뀔 상태를 주는 첫 배치를 한 번 바꾼다."""
    today = _today(ctx.conn)
    for b in _incident_batch_ids(ctx.conn):
        t = rules.target_batch_state(ctx.conn, b, today)
        if t is None:
            continue
        frm = db.get_object(ctx.conn, "batch", b)["state"]
        ctx.set_state("batch", b, t["to"], t["rule"])
        return {"name": _auto_name(frm, t["to"]), "rule": t["rule"], "reason": t["reason"],
                "target": {"type": "batch", "id": b}}
    return None


# --- 재공급 계획 (R10, R10-1, R10-2, R11) ---

def _plans(conn) -> list[dict]:
    return sorted(db.list_objects(conn, "resupply_plan"), key=lambda p: p["attrs"]["version"])


def _plan_id(version: int) -> str:
    return f"RP-v{version}"


def _line_id(version: int, rank: int) -> str:
    return f"RP-v{version}-{rank:02d}"


def _plan_lines(conn, plan_id: str) -> list[dict]:
    lines = [db.get_object(conn, "resupply_plan_line", l["src_id"])
             for l in db.find_links(conn, rel="LINE_OF", dst=("resupply_plan", plan_id))]
    return sorted(lines, key=lambda x: x["attrs"]["rank"])


def _line_key(lines: list[dict]) -> list[tuple]:
    """버전 비교 기준: (고객, 순위, 수량). 예상 월은 적용일에 따라 달라지므로 비교하지 않는다."""
    return [(l["customer_id"], l["rank"], l["qty"]) for l in lines]


def _last_human_action(conn) -> dict | None:
    rows = [r for r in db.list_action_log(conn) if r["actor"] != SYSTEM_ACTOR]
    return rows[-1] if rows else None


def _ensure_supply_batch(ctx: _Ctx, product: str) -> str | None:
    """R11: 같은 제품·다른 로트·QC 합격 중 가장 최근 배치를 객체로 싣는다 (사건에 묶지 않는다)."""
    sb = loader.latest_supply_batch(product, _origin_lots(ctx.conn))
    if sb is None:
        return None
    if db.get_object(ctx.conn, "batch", sb["batch_id"]) is None:
        ctx.create_object("batch", sb["batch_id"], {
            "product": sb["product_id"],
            "line": sb["row"].get("production_line"),
            "produced_date": sb["production_date"],
            "produced_qty": sb["produced_qty"],
            "qc_result": sb["qc_result"],
            "input_lot_ids": sb["input_lot_ids"],
            "role": "재공급 공급 배치",
        }, state=NORMAL, source="원본", evidence=sb["evidence"], rule="R11")
    return sb["batch_id"]


def _auto_plan_recalc(ctx: _Ctx) -> dict | None:
    """회수 범위·영업 임원 회신으로 R10 줄이 가장 최근 버전과 달라지면 새 버전(초안)을 만든다."""
    conn = ctx.conn
    today = _today(conn)
    lines = rules.resupply_lines(conn, today)
    if not lines:
        return None
    plans = _plans(conn)
    latest = plans[-1] if plans else None
    if latest is not None:
        before = [{"customer_id": l["attrs"]["customer_id"], "rank": l["attrs"]["rank"], "qty": l["attrs"]["qty"]}
                  for l in _plan_lines(conn, latest["id"])]
        if _line_key(before) == _line_key(lines):
            return None

    version = (latest["attrs"]["version"] + 1) if latest else 1
    pid = _plan_id(version)
    product = sorted({b["attrs"]["product"] for b in rules._recall_batches(conn)})[0]
    slack = loader.slack_capacity(product, today)
    trigger = _last_human_action(conn)
    tcause = (trigger or {}).get("cause") or {}
    rule_ids = ["R10"] + (["R10-2"] if any(l["lower_bound"] for l in lines) else [])
    lots = ", ".join(_origin_lots(conn))
    ctx.create_object("resupply_plan", pid, {
        "version": version,
        "product": product,
        "created_date": today,
        "release_condition": f"다른 원료 로트(≠ {lots}) AND 배치 QC 합격 (R11, 가정 A-10)",
        "recalc_cause": {
            "rules": rule_ids,
            "trigger_seq": trigger["seq"] if trigger else None,
            "trigger_action": trigger["action"] if trigger else None,
            "refs": [tcause[k] for k in ("decision", "event", "claim") if tcause.get(k)],
            "previous_version": latest["id"] if latest else None,
        },
        "slack_capacity": {k: slack[k] for k in ("value", "unit", "monthly_avg_produced", "utilization_pct",
                                                  "months", "source", "ref", "evidence")},
        "held_customers": [h["customer_id"] for h in rules.held_customers(conn)],
        "assumptions": ["A-03", "A-04"],
    }, state=PLAN_DRAFT, source="시스템", evidence=["A-03", "A-04"], rule="R10")
    ctx.create_link("PLAN_FOR", ("resupply_plan", pid), ("incident", INCIDENT_ID), source="시스템", rule="R10")
    for l in lines:
        lid = _line_id(version, l["rank"])
        ctx.create_object("resupply_plan_line", lid, {
            "rank": l["rank"], "customer_id": l["customer_id"], "qty": l["qty"], "qty_basis": l["qty_basis"],
            "lower_bound": l["lower_bound"], "expected_month": l["expected_month"],
            "priority_reason": l["priority_reason"],
        }, source="시스템", evidence=["A-03", "A-04"], rule="R10")
        ctx.create_link("LINE_OF", ("resupply_plan_line", lid), ("resupply_plan", pid), source="시스템", rule="R10")
        ctx.create_link("RESUPPLIES", ("resupply_plan_line", lid), ("customer", l["customer_id"]),
                        source="시스템", rule="R10", evidence=["A-03", "A-04"],
                        attrs={"assumptions": ["A-03", "A-04"]})
    sb = _ensure_supply_batch(ctx, product)
    if sb is not None:
        ctx.create_link("SOURCED_FROM", ("resupply_plan", pid), ("batch", sb), source="원본", rule="R11")
    if latest is not None and latest["state"] == PLAN_DRAFT:
        ctx.set_state("resupply_plan", latest["id"], PLAN_REPLACED, "R10")
    return {"name": ontology.AUTO_PROCESSES["recalculate_plan"]["name"], "rule": "R10",
            "reason": f"재공급 줄이 {latest['id'] if latest else '없음'}과 달라 {pid}(초안) 생성",
            "target": {"type": "resupply_plan", "id": pid}}


def _current_draft(conn) -> dict | None:
    drafts = [p for p in _plans(conn) if p["state"] == PLAN_DRAFT]
    return drafts[-1] if drafts else None


def _auto_order_drop_check(ctx: _Ctx) -> dict | None:
    """R10-1: 초안 줄의 고객 중 수주 급감 신호가 있고 확인 작업이 한 번도 없었던 고객 → 영업 임원 확인 요청."""
    conn = ctx.conn
    draft = _current_draft(conn)
    if draft is None:
        return None
    today = _today(conn)
    asked = {l["dst_id"] for t in db.list_objects(conn, "task") if t["attrs"].get("type") == TASK_ORDER_DROP
             for l in db.find_links(conn, rel="TARGETS", src=("task", t["id"])) if l["dst_type"] == "customer"}
    made = []
    for line in _plan_lines(conn, draft["id"]):
        cid = line["attrs"]["customer_id"]
        if cid in asked:
            continue
        sig = rules.order_drop_signal(conn, cid, today)
        if not sig["signal"]:
            continue
        made.append(_create_task(ctx, TASK_ORDER_DROP, {
            "customer_id": cid, "plan_id": draft["id"], "signal_months": sig["months"],
        }, targets=[("customer", cid)], rule="R10-1",
            evidence=db.get_object(conn, "customer", cid)["evidence"]))
    if not made:
        return None
    return {"name": ontology.AUTO_PROCESSES["request_order_drop_check"]["name"], "rule": "R10-1",
            "reason": f"수주 전년비 2개월 연속 기준 이하 고객 확인 요청 {', '.join(made)}",
            "target": {"type": "resupply_plan", "id": draft["id"]}}


def _auto_resupply_request(ctx: _Ctx) -> dict | None:
    """초안이 있고 열린 재공급 요청 작업이 없으면 SCM에 재공급 요청 작업을 만든다."""
    conn = ctx.conn
    draft = _current_draft(conn)
    if draft is None:
        return None
    if any(t["attrs"].get("type") == TASK_RESUPPLY_REQ and t["state"] == TASK_OPEN
           for t in db.list_objects(conn, "task")):
        return None
    tid = _create_task(ctx, TASK_RESUPPLY_REQ, {"plan_id": draft["id"]},
                       targets=[("resupply_plan", draft["id"])], rule="R9")
    return {"name": "재공급 요청 생성", "rule": "R9", "reason": f"{draft['id']} 초안 승인 요청 {tid}",
            "target": {"type": "task", "id": tid}}


def _auto_capacity_review(ctx: _Ctx) -> dict | None:
    """R10-3: 초안의 마지막 완료 예상이 기준 기간을 넘고 이 사건에 검토 작업이 한 번도 없었으면 생산에 능력 확보 검토 요청."""
    conn = ctx.conn
    draft = _current_draft(conn)
    if draft is None or any(t["attrs"].get("type") == TASK_CAPACITY for t in db.list_objects(conn, "task")):
        return None
    span = rules.recovery_span(conn, draft["id"])
    if not span["over"]:
        return None
    options = loader.capacity_options()
    tid = _create_task(ctx, TASK_CAPACITY, {
        "plan_id": draft["id"], "final_month": span["final_month"], "months": span["months"],
        "threshold_months": span["threshold_months"], "options": options,
    }, targets=[("resupply_plan", draft["id"])], rule="R10-3",
        evidence=["A-19"] + [e for o in options for e in o["evidence"]])
    return {"name": ontology.AUTO_PROCESSES["request_capacity_review"]["name"], "rule": "R10-3",
            "reason": f"{draft['id']} 마지막 완료 예상 {span['final_month']}({span['months']}번째 달)이 "
                      f"기준 {span['threshold_months']}개월을 넘어 생산에 검토 요청 {tid}",
            "target": {"type": "resupply_plan", "id": draft["id"]}}


# 순서대로 묻고, 하나가 변경을 하면 처음부터 다시 묻는다. 판정 → 계획 재계산 → 계획에 딸린 작업 순.
AUTO_PROCESSES: list[Callable[[_Ctx], dict | None]] = [
    _auto_batch_judgment, _auto_plan_recalc, _auto_order_drop_check, _auto_resupply_request, _auto_capacity_review]


def _run_auto(ctx: _Ctx, trigger_seq: int) -> list[int]:
    seqs = []
    for _ in range(MAX_AUTO_STEPS):
        for proc in AUTO_PROCESSES:
            done = proc(ctx)
            if done is not None:
                seqs.append(db.append_action_log(
                    ctx.conn, action=done["name"], actor=SYSTEM_ACTOR, applied_date=ctx.applied_date,
                    inputs={"target": done.get("target")}, changes=ctx.flush(),
                    cause={"rule": done["rule"], "reason": done["reason"], "after_seq": trigger_seq}))
                break
        else:
            return seqs
    raise RuntimeError(f"자동 처리 연쇄가 {MAX_AUTO_STEPS}번을 넘었다 (무한 전이 의심)")


# ---------------------------------------------------------------------------
# 입력 검사
# ---------------------------------------------------------------------------


def _is_date(v) -> bool:
    if not isinstance(v, str) or len(v) != 10:
        return False
    try:
        date.fromisoformat(v)
    except ValueError:
        return False
    return True


def _validate_inputs(conn, adef: dict, spec: _Spec, inputs: dict) -> dict:
    if not isinstance(inputs, dict):
        raise ActionError("invalid_input", "입력은 객체여야 한다")
    out = {}
    for d in adef["inputs"]:
        key, v = d["key"], inputs.get(d["key"])
        if v is None or v == "" or v == []:
            if d["required"]:
                raise ActionError("invalid_input", f"필수 입력 없음: {d['name']}({key})")
            out[key] = None
            continue
        t = d["type"]
        if t == "date" and not _is_date(v):
            raise ActionError("invalid_input", f"날짜 형식(YYYY-MM-DD)이 아니다: {d['name']} = {v}")
        if t == "int" and (not isinstance(v, int) or isinstance(v, bool) or v <= 0):
            raise ActionError("invalid_input", f"양의 정수가 아니다: {d['name']} = {v}")
        if t in ("text", "id") and not isinstance(v, str):
            raise ActionError("invalid_input", f"문자열이 아니다: {d['name']}")
        if t == "id_list":
            if not isinstance(v, list) or not all(isinstance(x, str) and x for x in v):
                raise ActionError("invalid_input", f"ID 목록이 아니다: {d['name']}")
            if len(set(v)) != len(v):
                raise ActionError("invalid_input", f"중복된 ID: {d['name']}")
        if t == "choice" and "choices" in d and v not in d["choices"]:
            raise ActionError("invalid_input", f"허용 값이 아니다: {d['name']} = {v} (허용: {d['choices']})")
        out[key] = v
    for key in spec.extra_inputs:
        if inputs.get(key) not in (None, ""):
            out[key] = inputs[key]

    inc = _incident(conn)
    if inc is not None and out.get("applied_date") and out["applied_date"] < inc["attrs"]["current_date"]:
        raise ActionError("invalid_input",
                          f"적용일 {out['applied_date']}이 사건의 현재 적용일 {inc['attrs']['current_date']}보다 이르다")
    return out


# ---------------------------------------------------------------------------
# 실행기
# ---------------------------------------------------------------------------


def execute(conn, action: str, actor: str, inputs: dict) -> ActionResult:
    """검사 순서: 액션 정의 → 역할 → 입력 형식 → 전제 조건 → 실행 → 자동 처리 연쇄 → 커밋. 실패하면 롤백."""
    adef, spec = ontology.action_def(action), _SPECS.get(action)
    if adef is None or spec is None:
        raise ActionError("unknown_action", f"없는 액션: {action}")
    if actor not in adef["roles"]:
        raise ActionError("forbidden", f"{actor} 역할은 '{adef['name']}'을(를) 실행할 수 없다")
    try:
        inp = _validate_inputs(conn, adef, spec, inputs or {})
        ctx = _Ctx(conn, inp.get("applied_date"))
        spec.check(ctx, inp)

        if not spec.needs_date:  # reset: 기록까지 비운다
            spec.apply(ctx, inp)
            conn.commit()
            return ActionResult(seq=0, auto_seqs=[], changes=[], created=[])

        _advance_date(ctx)
        cause = spec.apply(ctx, inp)
        seq = db.append_action_log(conn, action=action, actor=actor, applied_date=ctx.applied_date,
                                   inputs=inp, changes=ctx.flush(), cause=cause)
        auto_seqs = _run_auto(ctx, seq)
        conn.commit()
        return ActionResult(seq=seq, auto_seqs=auto_seqs, changes=ctx.all_changes, created=ctx.created)
    except BaseException:
        conn.rollback()
        raise


def available_actions(conn, actor: str) -> list[dict]:
    """지금 이 역할이 실행할 수 있는 액션과 그 대상. 화면 버튼의 근거다.
    대상은 전제 조건 검사와 같은 조회 함수에서 나온다. 키는 액션 입력 이름이다.
    예: {'action': 'submit_agenda', 'label': '안건 상신', 'targets': {'batch_ids': [...]}}"""
    out = []
    no_incident = _incident(conn) is None
    for name, spec in _SPECS.items():
        adef = ontology.action_def(name)
        if actor not in adef["roles"]:
            continue
        if no_incident and name not in ("open_incident", "reset"):
            continue
        targets = spec.targets(conn, actor)
        if targets is None:
            continue
        out.append({"action": name, "label": adef["name"], "targets": targets})
    return out
