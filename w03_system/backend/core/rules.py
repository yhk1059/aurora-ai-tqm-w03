"""판단 규칙 R1 ~ R11: 파생 속성, 경고, 상태가 바뀌어야 할 곳을 계산한다.

기준: brain/3-design/business-model.md §4·§5·§5-1·§8-3·§8-5("규칙의 자리")·§8-6,
architecture.md 패턴 3 "판정은 규칙, 설명은 AI".
- DB를 읽기만 한다. 결과를 돌려주면 액션 실행기(core/actions.py)가 상태를 바꾼다.
- "오늘"은 인자 today(사건의 현재 적용일, YYYY-MM-DD)다. 실제 시계는 쓰지 않는다.
- 기준값(10%, 90일, −20%, 2개월)은 ontology.rule_def()에서 읽는다.
- 판정에는 확정 클레임과 생산 수량만 쓴다. 출하 기준 불량률·미확정 클레임은 참고값이다(R1, R7-1).
- 언론 보도 이벤트는 어떤 판정에도 쓰지 않는다(R3).

다른 step과의 약속(이 모듈이 읽는 값):
- 클레임 attrs: defect_confirmed, qty, confirmed_date(확정일)
- 결정 attrs: result(승인/조건부/거절), applied_date. DECIDES → 배치
- 작업 attrs: type(작업 유형 이름), result(허용 결과), replied_date. 상태 = 객체 state. TARGETS → 고객
- 공급 배치 객체 attrs: qc_result, input_lot_ids. 재공급 계획 —SOURCED_FROM→ 공급 배치
"""

from __future__ import annotations

import math
from datetime import date, timedelta

from backend.core import db, loader, ontology

# 상태 이름은 ontology 정의의 값을 그대로 쓴다
_BATCH_STATES = ontology.STATE_MACHINES["batch"]["states"]
NORMAL, OBSERVE, RELEASED, OVER, SUBMITTED, RECALL, PARTIAL, INVESTIGATE, RESUBMIT = _BATCH_STATES
UNCONFIRMED_CLAIM_STATES = ontology.STATE_MACHINES["claim"]["unconfirmed_states"]
TASK_OPEN, TASK_REPLIED, TASK_DONE = ontology.STATE_MACHINES["task"]["states"]
PLAN_DRAFT, PLAN_CONFIRMED = ontology.STATE_MACHINES["plan"]["states"][:2]
CONFIRMED_LEVELS = ontology.CONFIRMED_LEVELS
PENDING_LEVELS = ["미확인", "확인요청중"]
SHIPPED_BASIS, CLAIM_BASIS = ontology.QUANTITY_BASES[0], ontology.QUANTITY_BASES[1]
REJECT = "거절"
ORDER_DROP_TASK = "수주 급감 확인"
HOLD_SHIPMENT_TASK = "출하 경위 확인"
PRIORITY_RESULT = "우선 공급 요청"
QC_HOLD, QC_PASS = "보류", loader.QC_PASS  # 원본 qc_result·inspection_result 값
assert {REJECT} <= set(ontology.COMMITTEE_RESULTS)
assert set(PENDING_LEVELS) <= set(ontology.CONFIRMATION_LEVELS)
assert ontology.task_type_def(HOLD_SHIPMENT_TASK)
assert PRIORITY_RESULT in [r["result"] for r in ontology.task_type_def(ORDER_DROP_TASK)["allowed_results"]]

RECALL_STATES = [RECALL, PARTIAL]


# ---------------------------------------------------------------------------
# 공통 도우미
# ---------------------------------------------------------------------------


def _threshold(rule_id: str) -> dict:
    return ontology.rule_def(rule_id)["threshold"]


def _rate_threshold() -> float:
    return _threshold("R2")["value"] / 100


def _d(s: str) -> date:
    return date.fromisoformat(s)


def _add_days(s: str, days: int) -> str:
    return (_d(s) + timedelta(days=days)).isoformat()


def _shift_month(ym: str, k: int) -> str:
    """'YYYY-MM'에서 k개월 이동."""
    n = int(ym[:4]) * 12 + int(ym[5:7]) - 1 + k
    return f"{n // 12:04d}-{n % 12 + 1:02d}"


def _incident(conn) -> dict | None:
    items = db.list_objects(conn, "incident")
    return items[0] if items else None


def _incident_batches(conn) -> list[dict]:
    """사건에 묶인(PART_OF) 배치."""
    ids = sorted({l["src_id"] for l in db.find_links(conn, rel="PART_OF")})
    return [db.get_object(conn, "batch", i) for i in ids]


def _claims_of(conn, batch_id: str) -> list[dict]:
    links = db.find_links(conn, rel="CLAIMED_ON", dst=("batch", batch_id))
    return [db.get_object(conn, "claim", l["src_id"]) for l in links]


def _is_confirmed(claim: dict) -> bool:
    return bool(claim["attrs"].get("defect_confirmed"))


def _is_pending(claim: dict) -> bool:
    return not _is_confirmed(claim) and claim["state"] in UNCONFIRMED_CLAIM_STATES


def _confirmed_date(claim: dict) -> str:
    return claim["attrs"].get("confirmed_date") or claim["attrs"]["received_date"]


def _claim_customer(conn, claim_id: str) -> str | None:
    links = db.find_links(conn, rel="CLAIMED_BY", src=("claim", claim_id))
    return links[0]["dst_id"] if links else None


def _shipped_to(conn, batch_id: str) -> list[dict]:
    return db.find_links(conn, rel="SHIPPED_TO", src=("batch", batch_id))


def _target(type_: str, id_: str) -> dict:
    return {"type": type_, "id": id_}


# ---------------------------------------------------------------------------
# 배치 파생 속성 (R1, R2, R6, R6-1, R6-2, R7-1)
# ---------------------------------------------------------------------------


def batch_metrics(conn, batch_id: str, today: str) -> dict:
    """배치의 파생 속성. 비율은 0~1 값이고 % 표시는 화면이 한다."""
    batch = db.get_object(conn, "batch", batch_id)
    produced = batch["attrs"]["produced_qty"]
    claims = _claims_of(conn, batch_id)
    confirmed = sorted((c for c in claims if _is_confirmed(c)), key=lambda c: (_confirmed_date(c), c["id"]))
    pending = [c for c in claims if _is_pending(c)]
    thr = _rate_threshold()

    confirmed_qty = sum(c["attrs"]["qty"] for c in confirmed)
    pending_qty = sum(c["attrs"]["qty"] for c in pending)
    defect_rate = confirmed_qty / produced if produced else None
    shipped_qty = sum(l["qty"] or 0 for l in _shipped_to(conn, batch_id) if l["confirm"] in CONFIRMED_LEVELS)
    over = confirmed_qty > 0 and defect_rate is not None and defect_rate >= thr

    crossed, cum = None, 0
    for c in confirmed:
        cum += c["attrs"]["qty"]
        if produced and cum / produced >= thr:
            crossed = _confirmed_date(c)
            break

    ship_dates = [db.get_object(conn, "shipment", l["src_id"])["attrs"]["shipped_date"]
                  for l in db.find_links(conn, rel="SHIPMENT_OF", dst=("batch", batch_id))]
    last_ship = max(ship_dates) if ship_dates else None

    if pending:
        due, basis, rule = None, "미확정 클레임 대기", "R6-2"
    elif confirmed:
        last_conf = max(_confirmed_date(c) for c in confirmed)
        due, basis, rule = _add_days(last_conf, _threshold("R6-1")["value"]), "마지막 클레임 확정일", "R6-1"
    elif last_ship:
        due, basis, rule = _add_days(last_ship, _threshold("R6")["value"]), "마지막 출하일", "R6"
    else:
        due, basis, rule = None, None, "R6"

    # 해제 예정일은 관찰 대상(관찰·관찰해제, 그리고 묶이면 관찰이 될 정상)에만 의미가 있다.
    # 기준초과·상신중·회수·조사 계열 배치에는 내보내지 않는다. _decide는 관찰·관찰해제에서만 이 값을 쓴다.
    if batch["state"] not in (NORMAL, OBSERVE, RELEASED):
        due, basis = None, None

    days_unsubmitted = (_d(today) - _d(crossed)).days if batch["state"] == OVER and crossed else None

    return {
        "batch_id": batch_id,
        "produced_qty": produced,
        "confirmed_qty": confirmed_qty,
        "defect_rate": defect_rate,
        "defect_rate_shipped": confirmed_qty / shipped_qty if shipped_qty else None,
        "over_threshold": over,
        "threshold": _threshold("R2"),
        "pending_qty": pending_qty,
        "rate_if_confirmed": (confirmed_qty + pending_qty) / produced if pending and produced else None,
        "threshold_crossed_date": crossed,
        "days_unsubmitted": days_unsubmitted,
        "last_ship_date": last_ship,
        "release_due_date": due,
        "release_basis": basis,
        "rules": {
            "confirmed_qty": "R1", "defect_rate": "R1", "defect_rate_shipped": "R1",
            "over_threshold": "R2", "pending_qty": "R7-1", "rate_if_confirmed": "R7-1",
            "threshold_crossed_date": "R2", "days_unsubmitted": "R2", "last_ship_date": "R6",
            "release_due_date": rule, "release_basis": rule,
        },
    }


# ---------------------------------------------------------------------------
# 판정 상태 (R2, R4, R6, R6-1, R6-2, R7, R9)
# ---------------------------------------------------------------------------


def _last_rejection_date(conn, batch_id: str) -> str | None:
    dates = []
    for l in db.find_links(conn, rel="DECIDES", dst=("batch", batch_id)):
        d = db.get_object(conn, "decision", l["src_id"])
        if d and d["attrs"].get("result") == REJECT:
            dates.append(d["attrs"]["applied_date"])
    return max(dates) if dates else None


def _decide(conn, batch: dict, today: str) -> dict | None:
    state, bid = batch["state"], batch["id"]
    m = batch_metrics(conn, bid, today)
    pct = f"{m['defect_rate'] * 100:.1f}%" if m["defect_rate"] is not None else "-"
    thr = f"{_threshold('R2')['value']}%"

    if state in (NORMAL, OBSERVE) and m["over_threshold"]:
        return {"to": OVER, "rule": "R2" if state == NORMAL else "R7",
                "reason": f"확정 불량률 {pct} ≥ 기준 {thr}"}
    if state == NORMAL:
        return {"to": OBSERVE, "rule": "R4", "reason": f"기점 로트를 공유하고 확정 불량률 {pct} < 기준 {thr}"}
    if state == OBSERVE:
        if m["pending_qty"] == 0 and m["release_due_date"] and m["release_due_date"] <= today:
            return {"to": RELEASED, "rule": m["rules"]["release_due_date"],
                    "reason": f"{m['release_basis']} 기준 해제 예정일 {m['release_due_date']} 경과, 미확정 클레임 없음"}
        return None
    if state == RELEASED:
        # 관찰해제 → 기준초과는 전이표에 없다. 관찰로 먼저 돌아가고, 다음 판단에서 R7이 적용된다
        if m["over_threshold"]:
            return {"to": OBSERVE, "rule": "R7", "reason": f"해제 뒤 확정 클레임으로 불량률 {pct} ≥ 기준 {thr}"}
        if m["pending_qty"] > 0:
            return {"to": OBSERVE, "rule": "R6-2", "reason": f"해제 뒤 미확정 클레임 {m['pending_qty']:,} EA 접수"}
        if m["release_due_date"] and m["release_due_date"] > today:
            return {"to": OBSERVE, "rule": "R7",
                    "reason": f"해제 뒤 확정 클레임, 재관찰 해제 예정일 {m['release_due_date']}"}
        return None
    if state == INVESTIGATE:
        rejected = _last_rejection_date(conn, bid)
        if rejected:
            late = [c for c in _claims_of(conn, bid) if _is_confirmed(c) and _confirmed_date(c) > rejected]
            if late:
                return {"to": RESUBMIT, "rule": "R9",
                        "reason": f"거절({rejected}) 뒤 확정 클레임 {len(late)}건"}
        return None
    if state == PARTIAL:
        if not any(l["confirm"] in PENDING_LEVELS for l in _shipped_to(conn, bid)):
            return {"to": RECALL, "rule": "R9", "reason": "미확인·확인요청중 출하처가 남아 있지 않음"}
        return None
    return None  # 상신중, 회수진행, 기준초과(미상신), 재상신 후보: 새 클레임이 와도 그대로 (시연 1-7)


def target_batch_state(conn, batch_id: str, today: str) -> dict | None:
    """규칙상 지금 바뀌어야 할 판정 상태 {'to', 'rule', 'reason'}, 없으면 None.
    한 번에 한 전이만 돌려준다(관찰해제 → 관찰 → 기준초과처럼 두 번 필요할 수 있다)."""
    batch = db.get_object(conn, "batch", batch_id)
    out = _decide(conn, batch, today)
    if out is not None and not ontology.can_transition("batch", batch["state"], out["to"]):
        raise AssertionError(f"전이표에 없는 전이: {batch['state']} → {out['to']}")
    return out


# ---------------------------------------------------------------------------
# 출하처 공백 (R8)
# ---------------------------------------------------------------------------


def unconfirmed_exposures(conn) -> list[dict]:
    """사건에 묶인 배치의 클레임 고객 중 그 배치의 SHIPPED_TO 줄이 없는 (배치, 고객)."""
    out = []
    for b in _incident_batches(conn):
        shipped = {l["dst_id"] for l in _shipped_to(conn, b["id"])}
        by_cust: dict[str, list[dict]] = {}
        for c in _claims_of(conn, b["id"]):
            cust = _claim_customer(conn, c["id"])
            if cust and cust not in shipped:
                by_cust.setdefault(cust, []).append(c)
        for cust, cs in sorted(by_cust.items()):
            out.append({
                "batch_id": b["id"],
                "customer_id": cust,
                "claim_ids": sorted(c["id"] for c in cs),
                "claim_qty": sum(c["attrs"]["qty"] for c in cs),
                "rule": "R8",
            })
    return out


# ---------------------------------------------------------------------------
# 경고 (R5, R5-1, R7-1, 미상신 경과, 영업 임원 확인 대기, 출하 경위 확인 대기)
# ---------------------------------------------------------------------------


def _open_order_drop_tasks(conn) -> list[dict]:
    return [t for t in db.list_objects(conn, "task")
            if t["attrs"].get("type") == ORDER_DROP_TASK and t["state"] == TASK_OPEN]


def open_hold_shipment_tasks(conn) -> list[dict]:
    """유형이 '출하 경위 확인'이고 상태가 열림인 작업 목록 (R11-1)."""
    return [t for t in db.list_objects(conn, "task")
            if t["attrs"].get("type") == HOLD_SHIPMENT_TASK and t["state"] == TASK_OPEN]


def warnings(conn, today: str) -> list[dict]:
    """화면에 보일 경고. 각 항목: code, rule, target{type, id}, message, evidence."""
    out = []
    batches = _incident_batches(conn)

    for b in batches:  # R5
        ships = db.find_links(conn, rel="SHIPMENT_OF", dst=("batch", b["id"]))
        if b["attrs"]["qc_result"] == QC_HOLD and ships:
            out.append({"code": "held_batch_shipped", "rule": "R5", "target": _target("batch", b["id"]),
                        "message": f"QC 보류 배치가 출하됨 (출하 기록 {len(ships)}건)",
                        "evidence": (b["evidence"] or []) + [e for l in ships for e in (l["evidence"] or [])]})

    in_scope = {b["id"] for b in batches}
    for lot in db.list_objects(conn, "material_lot"):  # R5-1
        a = lot["attrs"]
        for l in db.find_links(conn, rel="USED_IN", src=("material_lot", lot["id"])):
            if l["dst_id"] not in in_scope:
                continue
            produced = db.get_object(conn, "batch", l["dst_id"])["attrs"]["produced_date"]
            ev = (lot["evidence"] or []) + (l["evidence"] or [])
            if a["inspection_result"] == QC_HOLD and produced > a["inspection_date"]:
                out.append({"code": "held_lot_used", "rule": "R5-1", "target": _target("batch", l["dst_id"]),
                            "message": f"입고검사 보류({a['inspection_date']}) 로트 {lot['id']}가 "
                                       f"{produced} 생산 배치에 투입됨, 투입 경위 확인 필요",
                            "evidence": ev})
            if produced < a["received_date"]:
                out.append({"code": "record_conflict", "rule": "R5-1", "target": _target("batch", l["dst_id"]),
                            "message": f"원본 기록 충돌: 생산일 {produced} < 로트 {lot['id']} 입고일 {a['received_date']}",
                            "evidence": ev})

    thr = _rate_threshold()
    for b in batches:
        m = batch_metrics(conn, b["id"], today)
        if m["rate_if_confirmed"] is not None and m["rate_if_confirmed"] >= thr:  # R7-1
            out.append({"code": "pending_claim_over_threshold", "rule": "R7-1", "target": _target("batch", b["id"]),
                        "message": f"확정 시 불량률 {m['rate_if_confirmed'] * 100:.1f}%, 확정 시 기준 초과 예상",
                        "evidence": b["evidence"] or []})
        if m["days_unsubmitted"] is not None:
            out.append({"code": "unsubmitted_delay", "rule": "R2", "target": _target("batch", b["id"]),
                        "message": f"기준 초과({m['threshold_crossed_date']}) 후 {m['days_unsubmitted']}일 미상신",
                        "evidence": b["evidence"] or []})

    drafts = [p for p in db.list_objects(conn, "resupply_plan") if p["state"] == PLAN_DRAFT]
    open_tasks = _open_order_drop_tasks(conn)
    for p in drafts:
        if open_tasks:
            out.append({"code": "open_sales_check", "rule": "R10-1", "target": _target("resupply_plan", p["id"]),
                        "message": f"영업 임원 수주 급감 확인 대기 {len(open_tasks)}건",
                        "evidence": [t["id"] for t in open_tasks]})
    hold_tasks = open_hold_shipment_tasks(conn) if drafts else []
    for p in drafts:  # R11-1
        if hold_tasks:
            out.append({"code": "open_hold_shipment_check", "rule": "R11-1",
                        "target": _target("resupply_plan", p["id"]),
                        "message": f"출하 경위 확인 대기 {len(hold_tasks)}건 · 승인하려면 근거 필수",
                        "evidence": [t["id"] for t in hold_tasks]})
    return out


# ---------------------------------------------------------------------------
# 수주 급감 신호 (R10-1)
# ---------------------------------------------------------------------------


def order_drop_signal(conn, customer_id: str, today: str) -> dict:
    """today가 속한 달의 직전 n개월 수주 전년비가 모두 기준 이하인지."""
    thr = _threshold("R10-1")
    n = thr["consecutive_months"]
    yoy = db.get_object(conn, "customer", customer_id)["attrs"].get("booking_yoy") or {}
    months = [_shift_month(today[:7], -k) for k in range(n, 0, -1)]
    values = [(ym, yoy.get(ym)) for ym in months]
    signal = all(v is not None and v <= thr["value"] for _, v in values)
    return {"signal": signal, "months": values, "rule": "R10-1"}


# ---------------------------------------------------------------------------
# 회수량·재공급 (R8, R9, R10, R10-2, R11)
# ---------------------------------------------------------------------------


def _recall_batches(conn) -> list[dict]:
    return [b for b in db.list_objects(conn, "batch") if b["state"] in RECALL_STATES]


def _claim_sum(conn, batch_id: str, customer_id: str) -> int:
    return sum(c["attrs"]["qty"] for c in _claims_of(conn, batch_id)
               if _claim_customer(conn, c["id"]) == customer_id)


def recall_quantities(conn) -> list[dict]:
    """회수 배치(회수진행·부분회수)의 SHIPPED_TO 확인·회신확인 줄을 고객별로 합친다."""
    agg: dict[str, dict] = {}
    for b in _recall_batches(conn):
        for l in _shipped_to(conn, b["id"]):
            if l["confirm"] not in CONFIRMED_LEVELS:
                continue
            qty, basis = l["qty"], l["qty_basis"]
            if qty is None:  # R10-2: 수량 기록 없음 → 클레임 합을 하한으로
                qty, basis = _claim_sum(conn, b["id"], l["dst_id"]), CLAIM_BASIS
            a = agg.setdefault(l["dst_id"], {"qty": 0, "bases": [], "link_ids": []})
            a["qty"] += qty
            if basis not in a["bases"]:
                a["bases"].append(basis)
            a["link_ids"].append(l["link_id"])
    return [{
        "customer_id": cid,
        "qty": int(a["qty"]),
        "qty_basis": " + ".join(a["bases"]),
        "lower_bound": CLAIM_BASIS in a["bases"],
        "link_ids": a["link_ids"],
        "rule": "R10-2" if CLAIM_BASIS in a["bases"] else "R9",
    } for cid, a in sorted(agg.items())]


def _reply_order(conn) -> dict[str, int]:
    """회신 반영 액션 기록의 순번 (작업 ID → 첫 회신 순번)."""
    out = {}
    for row in db.list_action_log(conn):
        tid = (row["inputs"] or {}).get("task_id")
        if row["action"] == "apply_reply" and tid and tid not in out:
            out[tid] = row["seq"]
    return out


def _priority_requests(conn) -> list[tuple[str, str]]:
    """완료된 '우선 공급 요청' 수주 급감 확인 작업의 (고객, 작업 ID), 회신이 반영된 순서."""
    order = _reply_order(conn)
    tasks = [t for t in db.list_objects(conn, "task")
             if t["attrs"].get("type") == ORDER_DROP_TASK and t["state"] == TASK_DONE
             and t["attrs"].get("result") == PRIORITY_RESULT]
    tasks.sort(key=lambda t: (order.get(t["id"], math.inf), t["attrs"].get("replied_date") or "", t["id"]))
    out = []
    for t in tasks:
        for l in db.find_links(conn, rel="TARGETS", src=("task", t["id"])):
            if l["dst_type"] == "customer":
                out.append((l["dst_id"], t["id"]))
    return out


def resupply_lines(conn, today: str) -> list[dict]:
    """R10·R10-2 재공급 계획 한 판의 줄 (저장하지 않는다)."""
    recall = recall_quantities(conn)
    if not recall:
        return []
    products = sorted({b["attrs"]["product"] for b in _recall_batches(conn)})
    if len(products) != 1:
        raise ValueError(f"회수 배치의 제품이 하나가 아니다: {products}")
    slack = loader.slack_capacity(products[0], today)["value"]

    def share(cid):
        return db.get_object(conn, "customer", cid)["attrs"].get("revenue_share") or 0

    by_cust = {r["customer_id"]: r for r in recall}
    base = sorted(recall, key=lambda r: (-r["qty"], -share(r["customer_id"]), r["customer_id"]))
    reasons = {r["customer_id"]: "R10 ② 회수 수량" for r in base}
    front = []
    for cid, task_id in _priority_requests(conn):
        if cid in by_cust and cid not in front:
            front.append(cid)
            reasons[cid] = f"영업 임원 우선 공급 요청 ({task_id})"
    ordered = [by_cust[c] for c in front] + [r for r in base if r["customer_id"] not in front]

    out, cum = [], 0
    for rank, r in enumerate(ordered, start=1):
        cum += r["qty"]
        m = math.ceil(cum / slack)
        out.append({
            "rank": rank,
            "customer_id": r["customer_id"],
            "qty": r["qty"],
            "qty_basis": r["qty_basis"],
            "lower_bound": r["lower_bound"],
            "expected_month": _shift_month(today[:7], m - 1),
            "priority_reason": reasons[r["customer_id"]],
            "rule": "R10",
        })
    return out


def held_customers(conn) -> list[dict]:
    """재공급에서 보류된 고객: 회수 배치에 미확인·확인요청중 줄만 있는 고객."""
    pending: dict[str, list[dict]] = {}
    confirmed = set()
    for b in _recall_batches(conn):
        for l in _shipped_to(conn, b["id"]):
            if l["confirm"] in PENDING_LEVELS:
                pending.setdefault(l["dst_id"], []).append(l)
            elif l["confirm"] in CONFIRMED_LEVELS:
                confirmed.add(l["dst_id"])
    return [{
        "customer_id": cid,
        "batch_ids": sorted({l["src_id"] for l in ls}),
        "confirmations": sorted({l["confirm"] for l in ls}),
        "link_ids": [l["link_id"] for l in ls],
        "reason": "출하처 미확인 — 물류 회신까지 회수·재공급 보류",
        "rule": "R8",
    } for cid, ls in sorted(pending.items()) if cid not in confirmed]


def supply_condition(conn, plan_id: str) -> dict:
    """R11: 공급 배치가 기점 로트를 쓰지 않았고 QC가 합격인지."""
    links = db.find_links(conn, rel="SOURCED_FROM", src=("resupply_plan", plan_id))
    batch = db.get_object(conn, "batch", links[0]["dst_id"]) if links else None
    if batch is None:
        return {"met": False, "batch_id": None, "lots": [], "qc_result": None,
                "reason": "공급 배치 없음", "rule": "R11"}
    origin = {l["id"] for l in db.list_objects(conn, "material_lot")}
    lots = list(batch["attrs"].get("input_lot_ids") or [])
    lots += [l["src_id"] for l in db.find_links(conn, rel="USED_IN", dst=("batch", batch["id"]))
             if l["src_id"] not in lots]
    qc = batch["attrs"].get("qc_result")
    bad_lots = sorted(set(lots) & origin)
    reasons = []
    if not lots:
        reasons.append("투입 로트 기록 없음")
    if bad_lots:
        reasons.append(f"기점 로트 사용: {', '.join(bad_lots)}")
    if qc != QC_PASS:
        reasons.append(f"QC {qc}")
    met = not reasons
    return {"met": met, "batch_id": batch["id"], "lots": lots, "qc_result": qc,
            "reason": f"다른 로트({', '.join(lots)}) + QC {qc}" if met else "; ".join(reasons), "rule": "R11"}


def _month_index(ym: str) -> int:
    return int(ym[:4]) * 12 + int(ym[5:7]) - 1


def _plan_line_map(conn, plan_id: str) -> dict[str, dict]:
    out = {}
    for l in db.find_links(conn, rel="LINE_OF", dst=("resupply_plan", plan_id)):
        line = db.get_object(conn, "resupply_plan_line", l["src_id"])
        out[line["attrs"]["customer_id"]] = line["attrs"]
    return out


def plan_diff(conn, plan_id: str) -> list[dict]:
    """이 버전의 줄을 비교 기준 버전과 견준다. 비교 기준 = 이 버전보다 앞선 버전 중 가장 최근에 승인된 버전
    (지금 '확정'이거나, 확정됐다가 새 확정 버전에 밀려 '대체됨'이 된 버전), 없으면 바로 앞 버전, 그것도 없으면 빈 목록.
    각 항목: customer_id, rank_before, rank_after, month_before, month_after, delay_months(늦어지면 양수), added(bool)."""
    plan = db.get_object(conn, "resupply_plan", plan_id)
    earlier = sorted((p for p in db.list_objects(conn, "resupply_plan")
                      if p["attrs"]["version"] < plan["attrs"]["version"]), key=lambda p: p["attrs"]["version"])
    if not earlier:
        return []
    approve = ontology.PLAN_DECISION_RESULTS[0]
    confirmed = [p for p in earlier
                 if any(db.get_object(conn, "decision", l["src_id"])["attrs"]["result"] == approve
                        for l in db.find_links(conn, rel="DECIDES", dst=("resupply_plan", p["id"])))]
    base = (confirmed or earlier)[-1]
    before, after = _plan_line_map(conn, base["id"]), _plan_line_map(conn, plan_id)
    out = []
    for cid, a in sorted(after.items(), key=lambda kv: kv[1]["rank"]):
        b = before.get(cid)
        out.append({
            "customer_id": cid,
            "base_plan_id": base["id"],
            "rank_before": b["rank"] if b else None,
            "rank_after": a["rank"],
            "month_before": b["expected_month"] if b else None,
            "month_after": a["expected_month"],
            "delay_months": _month_index(a["expected_month"]) - _month_index(b["expected_month"]) if b else None,
            "added": b is None,
        })
    return out


# ---------------------------------------------------------------------------
# 사건 상태 (§4-5)
# ---------------------------------------------------------------------------


def incident_status(conn) -> str | None:
    """배치·계획 상태에서 도출. 사건이 없으면 None.
    판단 순서: 열림(미상신 기준초과) → 판정중(상신중·조사계속·재상신 후보) → 회수진행/복구계획확정 → 관찰중."""
    if _incident(conn) is None:
        return None
    states = {b["state"] for b in _incident_batches(conn)}
    plans = {p["state"] for p in db.list_objects(conn, "resupply_plan")}
    names = [s["name"] for s in ontology.INCIDENT_STATUSES]
    opened, observing, judging, recalling, restored = names
    if OVER in states:
        return opened
    if states & {SUBMITTED, INVESTIGATE, RESUBMIT}:
        return judging
    if states & set(RECALL_STATES):
        return restored if PLAN_CONFIRMED in plans and PLAN_DRAFT not in plans else recalling
    return observing
