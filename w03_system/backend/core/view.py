"""사건 뷰: 화면이 한 번에 받는 덩어리.

기준: brain/3-design/architecture.md 패턴 4 "화면은 서버가 준 것만 그린다", API `GET /incident`,
business-model.md §4-5·§8-3·§8-7, ui-guide.md "레이아웃"(탭 4개, 연결망).
- 읽기만 한다. 호출 전후로 DB가 같다.
- 판정을 다시 계산하지 않는다. rules.py·actions.py가 준 값을 조립만 한다.
- 숫자·관계·기준값마다 출처(원본/도출/가정/모의/시스템)를 함께 싣는다. 파생 값은 '도출'이다.
- 표시용 가공(천 단위, %, 색, 배지 문구)은 하지 않는다. 비율은 0~1 값 그대로다.
"""

from __future__ import annotations

from backend.core import actions, db, loader, ontology, rules

DERIVED = "도출"


def _obj(o: dict) -> dict:
    return {"id": o["id"], "attrs": o["attrs"], "state": o["state"], "source": o["source"],
            "evidence": o["evidence"] or []}


def _link(l: dict) -> dict:
    return {"link_id": l["link_id"], "rel": l["rel"],
            "src": {"type": l["src_type"], "id": l["src_id"]},
            "dst": {"type": l["dst_type"], "id": l["dst_id"]},
            "attrs": l["attrs"], "source": l["source"], "confirm": l["confirm"],
            "qty": l["qty"], "qty_basis": l["qty_basis"], "evidence": l["evidence"] or [],
            "applied_date": l["applied_date"], "recorded_date": l["recorded_date"]}


def _dst(conn, rel: str, src: tuple, dst_type: str | None = None) -> list[str]:
    return [l["dst_id"] for l in db.find_links(conn, rel=rel, src=src)
            if dst_type is None or l["dst_type"] == dst_type]


def _thresholds() -> dict:
    out = {rid: {**r["threshold"], "rule": rid, "summary": r["summary"]}
           for rid, r in ontology.RULES.items() if r.get("threshold")}
    out["task_deadline"] = dict(ontology.TASK_DEADLINE)
    return out


def _last_change(log: list[dict]) -> dict | None:
    """가장 최근 사람 액션과 그 뒤에 이어진 자동 처리의 변경."""
    human = [r for r in log if r["actor"] != actions.SYSTEM_ACTOR]
    if not human:
        return None
    h = human[-1]
    autos = [r for r in log if r["seq"] > h["seq"] and r["actor"] == actions.SYSTEM_ACTOR
             and (r["cause"] or {}).get("after_seq") == h["seq"]]
    steps = [{"seq": r["seq"], "action": r["action"], "actor": r["actor"],
              "rule": (r["cause"] or {}).get("rule"), "reason": (r["cause"] or {}).get("reason"),
              "changes": r["changes"]} for r in [h] + autos]
    return {"seq": h["seq"], "action": h["action"], "actor": h["actor"], "applied_date": h["applied_date"],
            "inputs": h["inputs"], "steps": steps,
            "changes": [c for s in steps for c in s["changes"]]}


def incident_view(conn, actor: str | None = None) -> dict:
    """화면이 한 번에 받는 덩어리. JSON으로 직렬화할 수 있어야 한다. DB를 바꾸지 않는다."""
    available = actions.available_actions(conn, actor) if actor else []
    incs = db.list_objects(conn, "incident")
    if not incs:
        return {"incident": None, "openable_batches": loader.openable_batches(), "available_actions": available}

    inc = incs[0]
    today = inc["attrs"]["current_date"]
    warnings = rules.warnings(conn, today)

    # --- 배치 (사건에 묶인 것) ---
    batches = []
    for p in db.find_links(conn, rel="PART_OF"):
        b = db.get_object(conn, "batch", p["src_id"])
        batches.append({
            **_obj(b),
            "part_of": {"reason": p["attrs"].get("reason"), "source": p["source"], "link_id": p["link_id"]},
            "metrics": {**rules.batch_metrics(conn, b["id"], today), "source": DERIVED},
            "warnings": [w for w in warnings if w["target"] == {"type": "batch", "id": b["id"]}],
        })
    batches.sort(key=lambda x: x["id"])
    batch_ids = {b["id"] for b in batches}

    # --- 고객 ---
    customers = [{**_obj(c), "order_drop_signal": {**rules.order_drop_signal(conn, c["id"], today),
                                                   "source": DERIVED}}
                 for c in sorted(db.list_objects(conn, "customer"), key=lambda c: c["id"])]

    # --- 클레임 ---
    claims = []
    for c in sorted(db.list_objects(conn, "claim"), key=lambda c: c["id"]):
        claims.append({**_obj(c),
                       "batch_id": (_dst(conn, "CLAIMED_ON", ("claim", c["id"])) or [None])[0],
                       "customer_id": (_dst(conn, "CLAIMED_BY", ("claim", c["id"])) or [None])[0],
                       "lot_ids": _dst(conn, "CLAIMED_LOT", ("claim", c["id"])),
                       "pending": rules._is_pending(c)})

    # --- 연결망: 로트 → 배치, 배치 → 고객 ---
    used_in = [_link(l) for l in db.find_links(conn, rel="USED_IN") if l["dst_id"] in batch_ids]
    shipped_to = []
    for l in db.find_links(conn, rel="SHIPPED_TO"):
        cs = [c for c in claims if c["batch_id"] == l["src_id"] and c["customer_id"] == l["dst_id"]]
        conf = [c for c in cs if c["attrs"].get("defect_confirmed")]
        shipped_to.append({**_link(l),
                           "claims": {"count": len(cs), "qty": sum(c["attrs"]["qty"] for c in cs),
                                      "confirmed_count": len(conf),
                                      "confirmed_qty": sum(c["attrs"]["qty"] for c in conf),
                                      "claim_ids": [c["id"] for c in cs], "source": DERIVED}})

    # --- 작업 ---
    tasks = []
    for t in db.list_objects(conn, "task"):
        tdef = ontology.task_type_def(t["attrs"]["type"])
        targets = []
        for l in db.find_links(conn, rel="TARGETS", src=("task", t["id"])):
            tgt = {"type": l["dst_type"], "id": l["dst_id"]}
            if l["dst_type"] == "SHIPPED_TO":
                sl = db.get_link(conn, int(l["dst_id"]))
                tgt.update({"batch_id": sl["src_id"], "customer_id": sl["dst_id"], "confirm": sl["confirm"]})
            targets.append(tgt)
        a = t["attrs"]
        tasks.append({**_obj(t), "type": a["type"], "code": a.get("code"), "department": a.get("department"),
                      "due_date": a.get("due_date"), "reply": a.get("reply"), "result": a.get("result"),
                      "replied_date": a.get("replied_date"), "created_by": a.get("created_by"),
                      "targets": targets,
                      "allowed_results": [r["result"] for r in tdef["allowed_results"]]})

    # --- 결정 ---
    decisions = []
    for d in db.list_objects(conn, "decision"):
        a = d["attrs"]
        decisions.append({**_obj(d), "type": a["type"], "decider": a["decider"], "result": a["result"],
                          "reason": a.get("reason"), "applied_date": a["applied_date"],
                          "targets": [{"type": l["dst_type"], "id": l["dst_id"]}
                                      for l in db.find_links(conn, rel="DECIDES", src=("decision", d["id"]))],
                          "created_tasks": _dst(conn, "CREATES", ("decision", d["id"]))})

    # --- 이벤트 ---
    events = [{**_obj(e), "type": e["attrs"]["type"], "occurred_date": e["attrs"].get("occurred_date"),
               "applied_date": e["attrs"].get("applied_date"), "content": e["attrs"].get("content"),
               "answers": _dst(conn, "ANSWERS", ("event", e["id"]))}
              for e in db.list_objects(conn, "event")]

    # --- 재공급 계획 ---
    plans = []
    for p in sorted(db.list_objects(conn, "resupply_plan"), key=lambda p: p["attrs"]["version"]):
        lines = sorted((db.get_object(conn, "resupply_plan_line", l["src_id"])
                        for l in db.find_links(conn, rel="LINE_OF", dst=("resupply_plan", p["id"]))),
                       key=lambda x: x["attrs"]["rank"])
        supply = _dst(conn, "SOURCED_FROM", ("resupply_plan", p["id"]))
        sb = db.get_object(conn, "batch", supply[0]) if supply else None
        plans.append({
            **_obj(p), "version": p["attrs"]["version"],
            "lines": [_obj(l) for l in lines],
            "diff": rules.plan_diff(conn, p["id"]),
            "release_condition": p["attrs"].get("release_condition"),
            "supply_condition": {**rules.supply_condition(conn, p["id"]), "source": DERIVED},
            "supply_batch": _obj(sb) if sb else None,
            "slack_capacity": p["attrs"].get("slack_capacity"),
            "recovery": {**rules.recovery_span(conn, p["id"]), "source": DERIVED},
            "recalc_cause": p["attrs"].get("recalc_cause"),
            "decisions": [d["id"] for d in decisions
                          if {"type": "resupply_plan", "id": p["id"]} in d["targets"]],
        })

    log = db.list_action_log(conn)
    return {
        "incident": {"id": inc["id"], "status": rules.incident_status(conn), "status_source": DERIVED,
                     "origin_lots": inc["attrs"].get("origin_lots") or [],
                     "start_batch": inc["attrs"].get("start_batch"),
                     "opened_date": inc["attrs"]["opened_date"], "current_date": today,
                     "owner": inc["attrs"]["owner"], "source": inc["source"]},
        "lots": [_obj(l) for l in db.list_objects(conn, "material_lot")],
        "batches": batches,
        "customers": customers,
        "claims": claims,
        "network": {"used_in": used_in, "shipped_to": shipped_to},
        "tasks": tasks,
        "decisions": decisions,
        "events": events,
        "plans": plans,
        "recall_quantities": rules.recall_quantities(conn),
        "held_customers": rules.held_customers(conn),
        "warnings": warnings,
        "available_actions": available,
        "last_change": _last_change(log),
        "log": {"actions": log, "ai": db.list_ai_log(conn)},
        "thresholds": _thresholds(),
    }
