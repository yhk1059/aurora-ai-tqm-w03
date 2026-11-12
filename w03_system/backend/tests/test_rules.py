"""core/rules.py: 시연 수치(demo-scenarios.md, lot-b2602p-incident.md)와 대조.

액션 실행기가 아직 없으므로 필요한 상태는 db.py 함수로 직접 만든다.
"""

import pytest

from backend.core import db, loader, rules

HELD = ["B-02-2602-01", "B-02-2603-01"]
PASSED = ["B-02-2602-02", "B-02-2602-03"]
ALL = sorted(HELD + PASSED)


def _snapshot(conn):
    return ([tuple(r) for r in conn.execute("SELECT * FROM objects ORDER BY type, id")],
            [tuple(r) for r in conn.execute("SELECT * FROM links ORDER BY link_id")])


def _open(conn, states=None):
    """사건 객체 + 배치 4개 PART_OF + 판정 상태."""
    db.put_object(conn, "incident", "INC-001", {"owner": "품질 담당자", "opened_date": "2026-07-01",
                                                 "current_date": "2026-07-01"}, source="시스템")
    for b in ALL:
        db.put_link(conn, "PART_OF", ("batch", b), ("incident", "INC-001"), source="시스템")
    for b, s in (states or {}).items():
        db.update_object(conn, "batch", b, state=s)


def _set(conn, batch_ids, state):
    for b in batch_ids:
        db.update_object(conn, "batch", b, state=state)


def _add_claim(conn, cid, batch, customer, qty, state, confirmed_date=None):
    db.put_object(conn, "claim", cid, {
        "received_date": "2026-07-07", "type": "피부트러블", "defect_confirmed": state == "확정",
        "qty": qty, "confirmed_date": confirmed_date, "source": "모의"}, state=state, source="모의")
    db.put_link(conn, "CLAIMED_ON", ("claim", cid), ("batch", batch), source="모의")
    db.put_link(conn, "CLAIMED_BY", ("claim", cid), ("customer", customer), source="모의")


def _priority_task(conn, tid, customer, result="우선 공급 요청", state="완료"):
    db.put_object(conn, "task", tid, {"type": "수주 급감 확인", "department": "영업 임원",
                                      "due_date": "2026-07-09", "result": result,
                                      "replied_date": "2026-07-09"}, state=state, source="시스템")
    db.put_link(conn, "TARGETS", ("task", tid), ("customer", customer), source="시스템")


# ---------------------------------------------------------------------------
# batch_metrics
# ---------------------------------------------------------------------------


def test_metrics_held_batches(loaded):
    _set(loaded, HELD, "기준초과(미상신)")
    m = rules.batch_metrics(loaded, "B-02-2602-01", "2026-07-01")
    assert m["confirmed_qty"] == 17900
    assert m["defect_rate"] == pytest.approx(0.1187, abs=5e-5)
    assert round(m["defect_rate"] * 100, 1) == 11.9
    assert m["defect_rate_shipped"] == pytest.approx(0.1227, abs=5e-5)
    assert m["over_threshold"] is True
    assert m["threshold_crossed_date"] == "2026-04-01"
    assert m["days_unsubmitted"] == 91
    assert m["pending_qty"] == 0 and m["rate_if_confirmed"] is None
    assert m["rules"]["defect_rate"] == "R1" and m["rules"]["over_threshold"] == "R2"

    m = rules.batch_metrics(loaded, "B-02-2603-01", "2026-07-01")
    assert m["confirmed_qty"] == 18622
    assert round(m["defect_rate"] * 100, 1) == 11.6
    assert m["threshold_crossed_date"] == "2026-05-11"
    assert m["days_unsubmitted"] == 51


def test_days_unsubmitted_only_when_unsubmitted(loaded):
    _set(loaded, ["B-02-2602-01"], "기준초과(미상신)")
    _set(loaded, ["B-02-2602-01"], "상신중")
    assert rules.batch_metrics(loaded, "B-02-2602-01", "2026-07-01")["days_unsubmitted"] is None


def test_metrics_passed_batches_release(loaded):
    m2 = rules.batch_metrics(loaded, "B-02-2602-02", "2026-07-01")
    m3 = rules.batch_metrics(loaded, "B-02-2602-03", "2026-07-01")
    assert (m2["last_ship_date"], m2["release_due_date"]) == ("2026-03-03", "2026-06-01")
    assert (m3["last_ship_date"], m3["release_due_date"]) == ("2026-02-23", "2026-05-24")
    assert m2["release_basis"] == "마지막 출하일" and m2["rules"]["release_due_date"] == "R6"
    assert m2["confirmed_qty"] == 0 and m2["over_threshold"] is False


# ---------------------------------------------------------------------------
# target_batch_state
# ---------------------------------------------------------------------------


def test_target_from_normal(loaded):
    t = rules.target_batch_state(loaded, "B-02-2602-01", "2026-07-01")
    assert t["to"] == "기준초과(미상신)" and t["rule"] == "R2"
    t = rules.target_batch_state(loaded, "B-02-2602-02", "2026-07-01")
    assert t["to"] == "관찰" and t["rule"] == "R4"


def test_target_release_passed_batches(loaded):
    _set(loaded, PASSED, "관찰")
    for b in PASSED:
        t = rules.target_batch_state(loaded, b, "2026-07-01")
        assert t["to"] == "관찰해제" and t["rule"] == "R6"
    # 해제 예정일 전이면 해제하지 않는다
    assert rules.target_batch_state(loaded, "B-02-2602-02", "2026-05-31") is None


def test_late_claim_pending_then_confirmed(loaded):
    _open(loaded, {"B-02-2602-03": "관찰"})
    _set(loaded, ["B-02-2602-03"], "관찰해제")
    _add_claim(loaded, "QC-MOCK-1", "B-02-2602-03", "C-101", 800, "접수")

    m = rules.batch_metrics(loaded, "B-02-2602-03", "2026-07-07")
    assert m["pending_qty"] == 800
    assert m["rate_if_confirmed"] == pytest.approx(800 / 161592)
    assert m["rate_if_confirmed"] == pytest.approx(0.00495, abs=5e-6)
    assert m["over_threshold"] is False and m["defect_rate"] == 0
    assert m["release_due_date"] is None and m["release_basis"] == "미확정 클레임 대기"
    t = rules.target_batch_state(loaded, "B-02-2602-03", "2026-07-07")
    assert t["to"] == "관찰" and t["rule"] == "R6-2"

    _set(loaded, ["B-02-2602-03"], "관찰")
    assert rules.target_batch_state(loaded, "B-02-2602-03", "2026-07-07") is None  # 미확정 대기 중 해제 안 함

    db.update_object(loaded, "claim", "QC-MOCK-1", state="확정",
                     attrs={"defect_confirmed": True, "confirmed_date": "2026-07-08"})
    m = rules.batch_metrics(loaded, "B-02-2602-03", "2026-07-08")
    assert m["release_due_date"] == "2026-10-06" and m["release_basis"] == "마지막 클레임 확정일"
    assert m["over_threshold"] is False
    assert rules.target_batch_state(loaded, "B-02-2602-03", "2026-07-08") is None
    assert rules.target_batch_state(loaded, "B-02-2602-03", "2026-10-06")["to"] == "관찰해제"


def test_released_batch_over_threshold_goes_back_to_observe_first(loaded):
    _set(loaded, ["B-02-2602-03"], "관찰")
    _set(loaded, ["B-02-2602-03"], "관찰해제")
    _add_claim(loaded, "QC-MOCK-2", "B-02-2602-03", "C-101", 20000, "확정", "2026-07-08")
    t = rules.target_batch_state(loaded, "B-02-2602-03", "2026-07-08")
    assert t["to"] == "관찰" and t["rule"] == "R7"
    _set(loaded, ["B-02-2602-03"], "관찰")
    t = rules.target_batch_state(loaded, "B-02-2602-03", "2026-07-08")
    assert t["to"] == "기준초과(미상신)" and t["rule"] == "R7"


@pytest.mark.parametrize("state", ["상신중", "회수진행", "부분회수", "기준초과(미상신)", "재상신 후보"])
def test_no_change_after_submission(loaded, state):
    _add_claim(loaded, "QC-MOCK-3", "B-02-2602-01", "C-101", 500, "확정", "2026-07-06")
    db.update_object(loaded, "batch", "B-02-2602-01", state=state)
    if state == "부분회수":
        db.put_link(loaded, "SHIPPED_TO", ("batch", "B-02-2602-01"), ("customer", "C-105"),
                    source="도출", confirm="미확인", qty_basis="없음")
    assert rules.target_batch_state(loaded, "B-02-2602-01", "2026-07-06") is None


def test_partial_recall_completes_when_no_pending_lines(loaded):
    _set(loaded, ["B-02-2602-01"], "부분회수")
    lid = db.put_link(loaded, "SHIPPED_TO", ("batch", "B-02-2602-01"), ("customer", "C-105"),
                      source="도출", confirm="확인요청중", qty_basis="없음")
    assert rules.target_batch_state(loaded, "B-02-2602-01", "2026-07-08") is None
    db.update_link(loaded, lid, confirm="회신확인", qty=4000, qty_basis="클레임 합(하한)")
    t = rules.target_batch_state(loaded, "B-02-2602-01", "2026-07-15")
    assert t["to"] == "회수진행" and t["rule"] == "R9"


def test_investigation_to_resubmit_after_new_confirmed_claim(loaded):
    _set(loaded, ["B-02-2602-01"], "조사계속")
    db.put_object(loaded, "decision", "DEC-1", {"type": "회수 범위", "decider": "품질위원회", "result": "거절",
                                                "reason": "원인 미규명", "applied_date": "2026-07-02"}, source="모의")
    db.put_link(loaded, "DECIDES", ("decision", "DEC-1"), ("batch", "B-02-2602-01"), source="모의")
    assert rules.target_batch_state(loaded, "B-02-2602-01", "2026-07-05") is None  # 기존 클레임은 거절 전
    _add_claim(loaded, "QC-MOCK-4", "B-02-2602-01", "C-101", 300, "확정", "2026-07-06")
    t = rules.target_batch_state(loaded, "B-02-2602-01", "2026-07-06")
    assert t["to"] == "재상신 후보" and t["rule"] == "R9"


# ---------------------------------------------------------------------------
# 출하처 공백, 경고, 수주 급감
# ---------------------------------------------------------------------------


def test_unconfirmed_exposures(loaded):
    assert rules.unconfirmed_exposures(loaded) == []  # 사건 없음 → 묶인 배치 없음
    _open(loaded)
    ex = rules.unconfirmed_exposures(loaded)
    assert [(e["batch_id"], e["customer_id"]) for e in ex] == [("B-02-2602-01", "C-105"), ("B-02-2603-01", "C-105")]
    assert sum(e["claim_qty"] for e in ex) == 11765
    assert all(e["rule"] == "R8" and e["claim_ids"] for e in ex)


def test_warnings(loaded):
    _open(loaded, {b: "기준초과(미상신)" for b in HELD})
    w = rules.warnings(loaded, "2026-07-01")
    by = {}
    for x in w:
        by.setdefault(x["code"], []).append(x)
    assert sorted(x["target"]["id"] for x in by["held_batch_shipped"]) == HELD
    assert sorted(x["target"]["id"] for x in by["held_lot_used"]) == ["B-02-2602-02", "B-02-2602-03", "B-02-2603-01"]
    assert [x["target"]["id"] for x in by["record_conflict"]] == ["B-02-2602-01"]
    assert {x["target"]["id"]: x["message"] for x in by["unsubmitted_delay"]}.keys() == set(HELD)
    assert "91일" in [x for x in by["unsubmitted_delay"] if x["target"]["id"] == "B-02-2602-01"][0]["message"]
    assert "pending_claim_over_threshold" not in by and "open_sales_check" not in by
    assert all(x["rule"] and x["evidence"] is not None for x in w)


def test_warning_pending_over_threshold_and_open_sales_check(loaded):
    _open(loaded, {"B-02-2602-02": "관찰"})
    _add_claim(loaded, "QC-MOCK-5", "B-02-2602-02", "C-101", 16000, "접수")
    db.put_object(loaded, "resupply_plan", "PLAN-1", {"version": 1}, state="초안", source="시스템")
    _priority_task(loaded, "T-05a", "C-101", result=None, state="열림")
    codes = {(x["code"], x["target"]["id"]) for x in rules.warnings(loaded, "2026-07-07")}
    assert ("pending_claim_over_threshold", "B-02-2602-02") in codes
    assert ("open_sales_check", "PLAN-1") in codes
    # 미확정은 판정을 바꾸지 않는다
    assert rules.batch_metrics(loaded, "B-02-2602-02", "2026-07-07")["over_threshold"] is False


def test_order_drop_signal(loaded):
    expect = {"C-101": True, "C-104": True, "C-102": False, "C-103": False, "C-108": False}
    for cid, sig in expect.items():
        s = rules.order_drop_signal(loaded, cid, "2026-07-01")
        assert s["signal"] is sig, cid
        assert [m for m, _ in s["months"]] == ["2026-05", "2026-06"] and s["rule"] == "R10-1"
    assert rules.order_drop_signal(loaded, "C-101", "2026-07-01")["months"] == [("2026-05", -22.0), ("2026-06", -33.7)]


# ---------------------------------------------------------------------------
# 회수량·재공급
# ---------------------------------------------------------------------------


def test_recall_quantities(loaded):
    assert rules.recall_quantities(loaded) == []
    _set(loaded, HELD, "회수진행")
    db.put_link(loaded, "SHIPPED_TO", ("batch", "B-02-2602-01"), ("customer", "C-105"),
                source="도출", confirm="미확인", qty_basis="없음")
    q = {r["customer_id"]: r for r in rules.recall_quantities(loaded)}
    assert {c: r["qty"] for c, r in q.items()} == {
        "C-103": 83402, "C-102": 70984, "C-101": 56993, "C-104": 53345, "C-108": 34929}
    assert sum(r["qty"] for r in q.values()) == 299653
    assert all(r["qty_basis"] == "출하기록 합" and not r["lower_bound"] for r in q.values())
    held = rules.held_customers(loaded)
    assert [h["customer_id"] for h in held] == ["C-105"] and held[0]["rule"] == "R8"


def test_resupply_lines_base(loaded):
    _set(loaded, HELD, "회수진행")
    lines = rules.resupply_lines(loaded, "2026-07-02")
    assert [(l["rank"], l["customer_id"], l["expected_month"]) for l in lines] == [
        (1, "C-103", "2026-12"), (2, "C-102", "2027-05"), (3, "C-101", "2027-09"),
        (4, "C-104", "2027-12"), (5, "C-108", "2028-03")]
    assert all(l["rule"] == "R10" for l in lines)


def test_resupply_lines_priority_request(loaded):
    _set(loaded, HELD, "회수진행")
    _priority_task(loaded, "T-05a", "C-101")
    _priority_task(loaded, "T-05b", "C-104", result="순서 유지")
    lines = rules.resupply_lines(loaded, "2026-07-02")
    assert [(l["customer_id"], l["expected_month"]) for l in lines] == [
        ("C-101", "2026-10"), ("C-103", "2027-04"), ("C-102", "2027-09"),
        ("C-104", "2027-12"), ("C-108", "2028-03")]
    assert "T-05a" in lines[0]["priority_reason"]


def test_resupply_lines_c105_lower_bound(loaded):
    _set(loaded, HELD, "회수진행")
    for b in HELD:
        qty = rules._claim_sum(loaded, b, "C-105")
        db.put_link(loaded, "SHIPPED_TO", ("batch", b), ("customer", "C-105"), source="모의",
                    confirm="회신확인", qty=qty, qty_basis="클레임 합(하한)")
    lines = rules.resupply_lines(loaded, "2026-07-02")
    last = lines[-1]
    assert (last["rank"], last["customer_id"], last["qty"]) == (6, "C-105", 11765)
    assert last["lower_bound"] is True and last["qty_basis"] == "클레임 합(하한)"
    assert last["expected_month"] == "2028-04"
    assert rules.held_customers(loaded) == []


def test_supply_condition(loaded):
    db.put_object(loaded, "resupply_plan", "PLAN-1", {"version": 1}, state="초안", source="시스템")
    assert rules.supply_condition(loaded, "PLAN-1")["met"] is False  # 공급 배치 없음

    s = loader.latest_supply_batch("PL-02", ["LOT-B-2602-P"])
    db.put_object(loaded, "batch", s["batch_id"], {"product": "PL-02", "produced_date": s["production_date"],
                                                   "produced_qty": s["produced_qty"], "qc_result": s["qc_result"],
                                                   "input_lot_ids": s["input_lot_ids"]},
                  state="정상", source="원본")
    db.put_link(loaded, "SOURCED_FROM", ("resupply_plan", "PLAN-1"), ("batch", s["batch_id"]), source="원본")
    r = rules.supply_condition(loaded, "PLAN-1")
    assert r["met"] is True and r["qc_result"] == "합격" and "LOT-B-2602-P" not in r["lots"]
    assert "LOT-B-2606-1" in r["lots"]

    db.put_object(loaded, "resupply_plan", "PLAN-2", {"version": 2}, state="초안", source="시스템")
    db.put_link(loaded, "SOURCED_FROM", ("resupply_plan", "PLAN-2"), ("batch", "B-02-2602-02"), source="원본")
    r = rules.supply_condition(loaded, "PLAN-2")
    assert r["met"] is False and "LOT-B-2602-P" in r["lots"]


# ---------------------------------------------------------------------------
# 사건 상태 §4-5
# ---------------------------------------------------------------------------


def test_incident_status(loaded):
    assert rules.incident_status(loaded) is None
    _open(loaded, {b: "기준초과(미상신)" for b in HELD} | {b: "관찰" for b in PASSED})
    assert rules.incident_status(loaded) == "열림"

    _set(loaded, PASSED, "관찰해제")
    _set(loaded, HELD, "상신중")
    assert rules.incident_status(loaded) == "판정중"

    _set(loaded, HELD, "회수진행")
    assert rules.incident_status(loaded) == "회수진행"
    db.put_object(loaded, "resupply_plan", "PLAN-1", {"version": 1}, state="초안", source="시스템")
    assert rules.incident_status(loaded) == "회수진행"
    db.update_object(loaded, "resupply_plan", "PLAN-1", state="확정")
    assert rules.incident_status(loaded) == "복구계획확정"
    db.put_object(loaded, "resupply_plan", "PLAN-2", {"version": 2}, state="초안", source="시스템")
    assert rules.incident_status(loaded) == "회수진행"


def test_incident_status_observing(loaded):
    _open(loaded, {b: "관찰" for b in ALL})
    _set(loaded, PASSED, "관찰해제")
    assert rules.incident_status(loaded) == "관찰중"


def test_incident_status_investigation(loaded):
    _open(loaded, {b: "기준초과(미상신)" for b in HELD})
    _set(loaded, HELD, "상신중")
    _set(loaded, HELD, "조사계속")
    assert rules.incident_status(loaded) == "판정중"


# ---------------------------------------------------------------------------
# 읽기 전용
# ---------------------------------------------------------------------------


def test_rules_do_not_write(loaded):
    _open(loaded, {b: "회수진행" for b in HELD} | {b: "관찰" for b in PASSED})
    db.put_object(loaded, "resupply_plan", "PLAN-1", {"version": 1}, state="초안", source="시스템")
    _priority_task(loaded, "T-05a", "C-101")
    before = _snapshot(loaded)
    for b in ALL:
        rules.batch_metrics(loaded, b, "2026-07-02")
        rules.target_batch_state(loaded, b, "2026-07-02")
    rules.unconfirmed_exposures(loaded)
    rules.warnings(loaded, "2026-07-02")
    rules.order_drop_signal(loaded, "C-101", "2026-07-02")
    rules.recall_quantities(loaded)
    rules.resupply_lines(loaded, "2026-07-02")
    rules.held_customers(loaded)
    rules.supply_condition(loaded, "PLAN-1")
    rules.incident_status(loaded)
    assert _snapshot(loaded) == before
