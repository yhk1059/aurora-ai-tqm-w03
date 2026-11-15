"""core/actions.py (회수 이후): 시연 1-3 ~ 1-7, 2-3 ~ 2-5, 3-2 ~ 3-4·3-6, 모의 회신 목록과 대조."""

import pytest

from backend.core import db, rules
from backend.core.actions import ActionError, available_actions, execute
from backend.core.view import incident_view

HELD = ["B-02-2602-01", "B-02-2603-01"]
OWNER, COMMITTEE, SCM = "quality_owner", "quality_committee", "scm"
V1 = [("C-103", 83402, "2026-12"), ("C-102", 70984, "2027-05"), ("C-101", 56993, "2027-09"),
      ("C-104", 53345, "2027-12"), ("C-108", 34929, "2028-03")]


# ---------------------------------------------------------------------------
# 도우미
# ---------------------------------------------------------------------------


def _start(conn, result="승인", reason=None):
    execute(conn, "open_incident", OWNER, {"batch_id": HELD[0], "applied_date": "2026-07-01"})
    execute(conn, "submit_agenda", OWNER, {"batch_ids": HELD, "applied_date": "2026-07-01"})
    execute(conn, "committee_decision", COMMITTEE,
            {"batch_ids": HELD, "result": result, "reason": reason, "applied_date": "2026-07-02"})


def _reply(conn, task_id, result, d, text="회신"):
    return execute(conn, "apply_reply", OWNER,
                   {"task_id": task_id, "reply_text": text, "result": result, "applied_date": d})


def _plan_decide(conn, plan_id, result, d, reason=None, actor=SCM):
    return execute(conn, "plan_decision", actor,
                   {"plan_id": plan_id, "result": result, "reason": reason, "applied_date": d})


def _tasks(conn, type_):
    return [t for t in db.list_objects(conn, "task") if t["attrs"]["type"] == type_]


def _task(conn, type_, customer=None):
    ts = [t for t in _tasks(conn, type_) if customer is None or t["attrs"].get("customer_id") == customer]
    assert len(ts) == 1
    return ts[0]


def _plans(conn):
    return {p["id"]: p for p in db.list_objects(conn, "resupply_plan")}


def _lines(conn, plan_id):
    lines = [db.get_object(conn, "resupply_plan_line", l["src_id"])
             for l in db.find_links(conn, rel="LINE_OF", dst=("resupply_plan", plan_id))]
    return [(l["attrs"]["customer_id"], l["attrs"]["qty"], l["attrs"]["expected_month"])
            for l in sorted(lines, key=lambda x: x["attrs"]["rank"])]


def _state(conn, batch):
    return db.get_object(conn, "batch", batch)["state"]


def _c105_lines(conn):
    return [l for l in db.find_links(conn, rel="SHIPPED_TO") if l["dst_id"] == "C-105"]


def _snapshot(conn):
    return tuple([tuple(r) for r in conn.execute(f"SELECT * FROM {t} ORDER BY rowid")]
                 for t in ("objects", "links", "action_log"))


def _through_2_4(conn):
    """시연 1-3 ~ 1-6, 2-4까지."""
    _start(conn)
    _reply(conn, _task(conn, "안내 대상 결정")["id"], "회수 배치 고객만", "2026-07-02")
    _plan_decide(conn, "RP-v1", "승인", "2026-07-03", reason="출고 조건 충족")
    _reply(conn, _task(conn, "수주 급감 확인", "C-104")["id"], "순서 유지", "2026-07-09")
    _reply(conn, _task(conn, "수주 급감 확인", "C-101")["id"], "우선 공급 요청", "2026-07-09")


# ---------------------------------------------------------------------------
# 시연 1: 승인 → 초안 → 안내 대상 → SCM 승인 → 새 클레임
# ---------------------------------------------------------------------------


def test_approval_creates_draft_v1(conn):
    _start(conn)
    plans = _plans(conn)
    assert list(plans) == ["RP-v1"] and plans["RP-v1"]["state"] == "초안"
    assert plans["RP-v1"]["attrs"]["version"] == 1
    assert plans["RP-v1"]["attrs"]["slack_capacity"]["ref"] == "A-04"
    assert _lines(conn, "RP-v1") == V1
    assert [h["customer_id"] for h in rules.held_customers(conn)] == ["C-105"]
    assert [l["dst_id"] for l in db.find_links(conn, rel="PLAN_FOR")] == ["INC-001"]
    res = db.find_links(conn, rel="RESUPPLIES")
    assert len(res) == 5 and all(l["source"] == "시스템" and l["attrs"]["assumptions"] == ["A-03", "A-04"]
                                 for l in res)

    req = _tasks(conn, "재공급 요청")
    assert len(req) == 1 and req[0]["state"] == "열림" and req[0]["attrs"]["department"] == "SCM"
    drops = _tasks(conn, "수주 급감 확인")
    assert sorted(t["attrs"]["customer_id"] for t in drops) == ["C-101", "C-104"]
    assert all(t["state"] == "열림" and t["attrs"]["department"] == "영업 임원" for t in drops)

    src = db.find_links(conn, rel="SOURCED_FROM", src=("resupply_plan", "RP-v1"))
    assert len(src) == 1 and src[0]["source"] == "원본"
    supply = db.get_object(conn, "batch", src[0]["dst_id"])
    assert "LOT-B-2606-1" in supply["attrs"]["input_lot_ids"]
    assert not db.find_links(conn, rel="PART_OF", src=("batch", supply["id"]))
    assert rules.supply_condition(conn, "RP-v1")["met"]

    log = db.list_action_log(conn)
    auto = [r for r in log if r["actor"] == "시스템" and r["action"] == "재공급 계획 재계산"]
    assert len(auto) == 1 and auto[0]["cause"]["rule"] == "R10"
    assert rules.incident_status(conn) == "회수진행"


def test_notice_reply(conn):
    _start(conn)
    t = _task(conn, "안내 대상 결정")
    res = _reply(conn, t["id"], "회수 배치 고객만", "2026-07-02", "회수 배치 고객 5곳 안내, 해제 배치 고객은 안내 안 함")
    t = db.get_object(conn, "task", t["id"])
    assert t["state"] == "완료"
    assert t["attrs"]["notice_customers"] == ["C-101", "C-102", "C-103", "C-104", "C-108"]
    task_states = [(c["before"], c["after"]) for c in res.changes
                   if c["target"] == {"type": "task", "id": t["id"]} and c["field"] == "state"]
    assert task_states == [("열림", "회신받음"), ("회신받음", "완료")]
    ev = db.find_links(conn, rel="ANSWERS", dst=("task", t["id"]))
    assert len(ev) == 1
    event = db.get_object(conn, "event", ev[0]["src_id"])
    assert event["attrs"]["type"] == "회신" and event["source"] == "모의"
    assert db.find_links(conn, rel="TRIGGERS", src=("event", event["id"]))


def test_scm_approval(conn):
    _start(conn)
    assert any(w["code"] == "open_sales_check" for w in rules.warnings(conn, "2026-07-02"))
    _plan_decide(conn, "RP-v1", "승인", "2026-07-03", reason="출고 조건 충족")
    assert _plans(conn)["RP-v1"]["state"] == "확정"
    assert _task(conn, "재공급 요청")["state"] == "완료"
    assert all(t["state"] == "열림" for t in _tasks(conn, "수주 급감 확인"))
    dec = [d for d in db.list_objects(conn, "decision") if d["attrs"]["type"] == "재공급 순서"]
    assert len(dec) == 1 and dec[0]["attrs"]["result"] == "승인"
    assert db.find_links(conn, rel="DECIDES", src=("decision", dec[0]["id"]))[0]["dst_id"] == "RP-v1"
    assert rules.incident_status(conn) == "복구계획확정"


def test_new_claim_after_confirmed_plan(conn):
    _start(conn)
    _plan_decide(conn, "RP-v1", "승인", "2026-07-03", reason="출고 조건 충족")
    execute(conn, "register_claim", OWNER, {"batch_id": HELD[0], "customer_id": "C-101", "qty": 300,
                                             "status": "확정", "received_date": "2026-07-06",
                                             "applied_date": "2026-07-06"})
    assert list(_plans(conn)) == ["RP-v1"]
    assert _state(conn, HELD[0]) == "회수진행"


# ---------------------------------------------------------------------------
# 시연 2: 영업 임원 회신 → v2 → SCM 재승인 / 거절
# ---------------------------------------------------------------------------


def test_sales_exec_reply_creates_v2(conn):
    _start(conn)
    _reply(conn, _task(conn, "안내 대상 결정")["id"], "회수 배치 고객만", "2026-07-02")
    _plan_decide(conn, "RP-v1", "승인", "2026-07-03", reason="출고 조건 충족")
    _reply(conn, _task(conn, "수주 급감 확인", "C-104")["id"], "순서 유지", "2026-07-09")
    assert list(_plans(conn)) == ["RP-v1"]
    _reply(conn, _task(conn, "수주 급감 확인", "C-101")["id"], "우선 공급 요청", "2026-07-09")

    plans = _plans(conn)
    assert plans["RP-v1"]["state"] == "확정" and plans["RP-v2"]["state"] == "초안"
    assert [(c, m) for c, _, m in _lines(conn, "RP-v2")] == [
        ("C-101", "2026-10"), ("C-103", "2027-04"), ("C-102", "2027-09"), ("C-104", "2027-12"),
        ("C-108", "2028-03")]
    assert _lines(conn, "RP-v1") == V1  # 이전 버전 줄은 그대로
    diff = {d["customer_id"]: d for d in rules.plan_diff(conn, "RP-v2")}
    assert diff["C-103"]["delay_months"] == 4 and diff["C-102"]["delay_months"] == 4
    assert diff["C-101"]["delay_months"] < 0 and diff["C-101"]["rank_before"] == 3
    assert diff["C-101"]["rank_after"] == 1 and not any(d["added"] for d in diff.values())
    assert rules.plan_diff(conn, "RP-v1") == []
    assert rules.incident_status(conn) == "회수진행"
    assert len(_tasks(conn, "수주 급감 확인")) == 2
    assert sum(t["state"] == "열림" for t in _tasks(conn, "재공급 요청")) == 1


def test_scm_reapproval_v2(conn):
    _through_2_4(conn)
    _plan_decide(conn, "RP-v2", "승인", "2026-07-09", reason="영업 임원 요청 반영")
    plans = _plans(conn)
    assert plans["RP-v2"]["state"] == "확정" and plans["RP-v1"]["state"] == "대체됨"  # 유효 계획은 하나
    assert rules.plan_diff(conn, "RP-v2")[0]["base_plan_id"] == "RP-v1"  # 비교 기준은 승인됐던 v1 그대로
    assert rules.incident_status(conn) == "복구계획확정"


def test_scm_rejects_v2(conn):
    _through_2_4(conn)
    with pytest.raises(ActionError) as e:
        _plan_decide(conn, "RP-v2", "거절", "2026-07-09")
    assert e.value.code == "precondition"
    _plan_decide(conn, "RP-v2", "거절", "2026-07-09", reason="기존 순서 유지")
    plans = _plans(conn)
    assert plans["RP-v2"]["state"] == "기각" and plans["RP-v1"]["state"] == "확정"
    notice = _tasks(conn, "결과 통보")
    assert len(notice) == 1 and notice[0]["state"] == "열림"
    assert db.find_links(conn, rel="TARGETS", src=("task", notice[0]["id"]))[0]["dst_id"] == "RP-v2"
    assert rules.incident_status(conn) == "복구계획확정"

    execute(conn, "register_news", OWNER, {"content": "보도", "applied_date": "2026-07-10"})
    assert sorted(_plans(conn)) == ["RP-v1", "RP-v2"]
    _reply(conn, notice[0]["id"], "확인함", "2026-07-10")
    assert sorted(_plans(conn)) == ["RP-v1", "RP-v2"]
    assert db.get_object(conn, "task", notice[0]["id"])["state"] == "완료"


# ---------------------------------------------------------------------------
# 시연 3-A: 조건부 → 확인 불가 → 출하 확인 / 영향없음
# ---------------------------------------------------------------------------


def _conditional_then_unknown(conn):
    _start(conn, "조건부")
    t02 = _task(conn, "출하처 확인", "C-105")
    _reply(conn, t02["id"], "확인 불가", "2026-07-08", "기록 확인 불가, 7일 추가 필요")
    return t02["id"]


def test_conditional_then_cannot_confirm(conn):
    _start(conn, "조건부")
    assert [_state(conn, b) for b in HELD] == ["부분회수", "부분회수"]
    assert list(_plans(conn)) == ["RP-v1"] and _lines(conn, "RP-v1") == V1
    before = _snapshot(conn)
    t02 = _task(conn, "출하처 확인", "C-105")["id"]
    _reply(conn, t02, "확인 불가", "2026-07-08")
    t = db.get_object(conn, "task", t02)
    assert t["state"] == "열림" and t["attrs"]["due_date"] == "2026-07-15" and t["attrs"]["result"] == "확인 불가"
    assert all(l["confirm"] == "확인요청중" for l in _c105_lines(conn))
    assert [_state(conn, b) for b in HELD] == ["부분회수", "부분회수"]
    assert list(_plans(conn)) == ["RP-v1"]
    assert before != _snapshot(conn)


def test_shipment_confirmed(conn):
    t02 = _conditional_then_unknown(conn)
    _reply(conn, t02, "출하 확인", "2026-07-15", "C-105 출하 사실 확인, 수량 기록 없음")
    lines = _c105_lines(conn)
    assert len(lines) == 2 and all(l["confirm"] == "회신확인" for l in lines)
    assert all(l["qty_basis"] == "클레임 합(하한)" for l in lines)
    assert sum(l["qty"] for l in lines) == 11765
    assert all(any(e.startswith("EV-") for e in l["evidence"]) for l in lines)
    assert [_state(conn, b) for b in HELD] == ["회수진행", "회수진행"]
    assert db.get_object(conn, "task", t02)["state"] == "완료"

    plans = _plans(conn)
    assert plans["RP-v1"]["state"] == "대체됨" and plans["RP-v2"]["state"] == "초안"
    v2 = _lines(conn, "RP-v2")
    assert [c for c, _, _ in v2] == ["C-103", "C-102", "C-101", "C-104", "C-108", "C-105"]
    assert v2[5] == ("C-105", 11765, "2028-04")
    last = db.get_object(conn, "resupply_plan_line", "RP-v2-06")
    assert last["attrs"]["lower_bound"] is True
    assert _lines(conn, "RP-v1") == V1
    diff = {d["customer_id"]: d for d in rules.plan_diff(conn, "RP-v2")}
    assert diff["C-105"]["added"] is True and diff["C-105"]["delay_months"] is None


def test_shipment_no_impact(conn):
    t02 = _conditional_then_unknown(conn)
    _reply(conn, t02, "영향없음", "2026-07-15")
    lines = _c105_lines(conn)
    assert len(lines) == 2 and all(l["confirm"] == "영향없음" for l in lines)
    assert [_state(conn, b) for b in HELD] == ["회수진행", "회수진행"]
    assert list(_plans(conn)) == ["RP-v1"]
    assert "C-105" not in [c for c, _, _ in _lines(conn, "RP-v1")]


# ---------------------------------------------------------------------------
# 시연 3-B: 거절 → 원인 조사 회신
# ---------------------------------------------------------------------------


def test_investigation_confirmed_then_resubmit(conn):
    _start(conn, "거절", "원인 미규명")
    assert not _plans(conn)
    t06 = _task(conn, "원인 조사")["id"]
    _reply(conn, t06, "원인 확인", "2026-07-10", "원료 로트 LOT-B-2602-P 성분 규격이탈 확인")
    assert [_state(conn, b) for b in HELD] == ["재상신 후보", "재상신 후보"]
    assert db.get_object(conn, "task", t06)["state"] == "완료"
    assert {"action": "submit_agenda", "label": "안건 상신", "targets": {"batch_ids": HELD}} in \
        available_actions(conn, OWNER)
    execute(conn, "submit_agenda", OWNER, {"batch_ids": HELD, "applied_date": "2026-07-10"})
    assert [_state(conn, b) for b in HELD] == ["상신중", "상신중"]


def test_investigation_unconfirmed(conn):
    _start(conn, "거절", "원인 미규명")
    t06 = _task(conn, "원인 조사")["id"]
    _reply(conn, t06, "원인 미확인", "2026-07-10")
    t = db.get_object(conn, "task", t06)
    assert t["state"] == "열림" and t["attrs"]["due_date"] == "2026-07-17"
    assert [_state(conn, b) for b in HELD] == ["조사계속", "조사계속"]


def test_hold_shipment_replies(conn):
    _start(conn)
    t01 = _task(conn, "출하 경위 확인")["id"]
    _reply(conn, t01, "확인 불가", "2026-07-03")
    assert db.get_object(conn, "task", t01)["attrs"]["due_date"] == "2026-07-10"
    _reply(conn, t01, "경위 확인됨", "2026-07-04")
    assert db.get_object(conn, "task", t01)["state"] == "완료"
    assert [_state(conn, b) for b in HELD] == ["회수진행", "회수진행"]


# ---------------------------------------------------------------------------
# 검사: 허용 결과, R11, 권한, 재공급 요청
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("result", ["순서 유지", "해석 불가"])
def test_reply_result_must_be_allowed(conn, result):
    _start(conn, "조건부")
    t02 = _task(conn, "출하처 확인", "C-105")["id"]
    before = _snapshot(conn)
    with pytest.raises(ActionError) as e:
        _reply(conn, t02, result, "2026-07-08")
    assert e.value.code == "precondition"
    assert _snapshot(conn) == before


def test_resupply_request_takes_no_reply(conn):
    _start(conn)
    with pytest.raises(ActionError) as e:
        _reply(conn, _task(conn, "재공급 요청")["id"], "확인함", "2026-07-03")
    assert e.value.code == "precondition"


def test_reply_on_closed_task_rejected(conn):
    _start(conn)
    t = _task(conn, "안내 대상 결정")["id"]
    _reply(conn, t, "회수 배치 고객만", "2026-07-02")
    with pytest.raises(ActionError) as e:
        _reply(conn, t, "회수 배치 고객만", "2026-07-03")
    assert e.value.code == "precondition"


def test_supply_condition_blocks_approval(conn):
    _start(conn)
    link = db.find_links(conn, rel="SOURCED_FROM", src=("resupply_plan", "RP-v1"))[0]
    conn.execute("DELETE FROM links WHERE link_id = ?", (link["link_id"],))
    db.put_link(conn, "SOURCED_FROM", ("resupply_plan", "RP-v1"), ("batch", "B-02-2602-02"), source="원본")
    conn.commit()
    assert not rules.supply_condition(conn, "RP-v1")["met"]
    with pytest.raises(ActionError) as e:
        _plan_decide(conn, "RP-v1", "승인", "2026-07-03")
    assert e.value.code == "precondition"
    assert _plans(conn)["RP-v1"]["state"] == "초안"
    scm = {a["action"]: a for a in available_actions(conn, SCM)}
    assert scm["plan_decision"]["targets"]["plan_id"][0]["can_approve"] is False


def test_plan_decision_forbidden_for_owner(conn):
    _start(conn)
    with pytest.raises(ActionError) as e:
        _plan_decide(conn, "RP-v1", "승인", "2026-07-03", actor=OWNER)
    assert e.value.code == "forbidden"


def test_available_actions(conn):
    _start(conn)
    owner = {a["action"]: a for a in available_actions(conn, OWNER)}
    items = {i["id"]: i for i in owner["apply_reply"]["targets"]["task_id"]}
    req = _task(conn, "재공급 요청")["id"]
    assert req not in items
    t02 = _task(conn, "출하처 확인", "C-105")["id"]
    assert items[t02]["type"] == "출하처 확인"
    assert items[t02]["allowed_results"] == ["출하 확인", "영향없음", "확인 불가"]
    scm = {a["action"]: a for a in available_actions(conn, SCM)}
    plan_items = scm["plan_decision"]["targets"]["plan_id"]
    assert [p["id"] for p in plan_items] == ["RP-v1"] and plan_items[0]["supply_condition_met"] is True
    _plan_decide(conn, "RP-v1", "승인", "2026-07-03", reason="출고 조건 충족")
    assert "plan_decision" not in {a["action"] for a in available_actions(conn, SCM)}


# ---------------------------------------------------------------------------
# 재현
# ---------------------------------------------------------------------------


def test_replay_is_deterministic():
    snaps = []
    for _ in range(2):
        c = db.connect(":memory:")
        _through_2_4(c)
        snaps.append(_snapshot(c))
        c.close()
    assert snaps[0] == snaps[1]


# ---------------------------------------------------------------------------
# R11-1: 출하 경위 확인(T-01)이 열려 있으면 경고 + 승인 근거 필수
# ---------------------------------------------------------------------------


def _hold_warnings(conn, d="2026-07-03"):
    return [w for w in rules.warnings(conn, d) if w["code"] == "open_hold_shipment_check"]


def _plan_item(conn, plan_id):
    scm = {a["action"]: a for a in available_actions(conn, SCM)}
    return {i["id"]: i for i in scm["plan_decision"]["targets"]["plan_id"]}[plan_id]


def _last_log(conn, action):
    return [r for r in db.list_action_log(conn) if r["action"] == action][-1]


def test_r11_1_warning_on_draft_while_hold_check_open(conn):
    _start(conn)
    t01 = _task(conn, "출하 경위 확인")
    ws = _hold_warnings(conn)
    assert len(ws) == 1
    assert ws[0]["rule"] == "R11-1"
    assert ws[0]["target"] == {"type": "resupply_plan", "id": "RP-v1"}
    assert ws[0]["evidence"] == [t01["id"]]
    assert "승인하려면 근거 필수" in ws[0]["message"]
    assert any(w["code"] == "open_sales_check" for w in rules.warnings(conn, "2026-07-03"))  # 함께 붙는다
    assert _plan_item(conn, "RP-v1")["approve_reason_required"] is True
    v = incident_view(conn, SCM)
    assert any(w["code"] == "open_hold_shipment_check" for w in v["warnings"])
    pd = next(a for a in v["available_actions"] if a["action"] == "plan_decision")
    assert pd["targets"]["plan_id"][0]["approve_reason_required"] is True


@pytest.mark.parametrize("reason", [None, "", "   "])
def test_r11_1_approve_without_reason_rejected(conn, reason):
    _start(conn)
    with pytest.raises(ActionError) as e:
        _plan_decide(conn, "RP-v1", "승인", "2026-07-03", reason=reason)
    assert e.value.code == "precondition"
    assert "출하 경위 확인" in str(e.value) and "R11-1" in str(e.value)
    assert _plans(conn)["RP-v1"]["state"] == "초안"
    assert not [d for d in db.list_objects(conn, "decision") if d["attrs"]["type"] == "재공급 순서"]


def test_r11_1_approve_with_reason_records_rule(conn):
    _start(conn)
    _plan_decide(conn, "RP-v1", "승인", "2026-07-03", reason="출고 조건 충족. 출하 경위는 회신 후 재확인")
    assert _plans(conn)["RP-v1"]["state"] == "확정"
    assert "R11-1" in _last_log(conn, "plan_decision")["cause"]["rules"]
    assert _hold_warnings(conn) == []  # 초안이 없으면 경고도 없다


def test_r11_1_cannot_confirm_keeps_warning(conn):
    _start(conn)
    t01 = _task(conn, "출하 경위 확인")
    before = t01["attrs"]["due_date"]
    _reply(conn, t01["id"], "확인 불가", "2026-07-03")
    t01 = _task(conn, "출하 경위 확인")
    assert t01["state"] == "열림" and t01["attrs"]["due_date"] > before
    assert len(_hold_warnings(conn)) == 1
    assert _plan_item(conn, "RP-v1")["approve_reason_required"] is True
    with pytest.raises(ActionError) as e:
        _plan_decide(conn, "RP-v1", "승인", "2026-07-03")
    assert e.value.code == "precondition"


def test_r11_1_confirmed_reply_lifts_warning(conn):
    _start(conn)
    _reply(conn, _task(conn, "출하 경위 확인")["id"], "경위 확인됨", "2026-07-03")
    assert _task(conn, "출하 경위 확인")["state"] == "완료"
    assert _hold_warnings(conn) == []
    assert _plan_item(conn, "RP-v1")["approve_reason_required"] is False
    assert rules.open_hold_shipment_tasks(conn) == []
    _plan_decide(conn, "RP-v1", "승인", "2026-07-03")
    assert _plans(conn)["RP-v1"]["state"] == "확정"
    assert "R11-1" not in _last_log(conn, "plan_decision")["cause"]["rules"]


def test_r11_1_reply_after_confirmed_plan_no_new_version(conn):
    _start(conn)
    _plan_decide(conn, "RP-v1", "승인", "2026-07-03", reason="출고 조건 충족")
    _reply(conn, _task(conn, "출하 경위 확인")["id"], "경위 확인됨", "2026-07-06")
    assert list(_plans(conn)) == ["RP-v1"]
    assert _plans(conn)["RP-v1"]["state"] == "확정"


def test_r11_1_reject_still_needs_reason_regardless(conn):
    _start(conn)
    _reply(conn, _task(conn, "출하 경위 확인")["id"], "경위 확인됨", "2026-07-03")
    with pytest.raises(ActionError) as e:
        _plan_decide(conn, "RP-v1", "거절", "2026-07-03")
    assert e.value.code == "precondition" and "R11-1" not in str(e.value)
    _plan_decide(conn, "RP-v1", "거절", "2026-07-03", reason="기존 순서 유지")
    assert _plans(conn)["RP-v1"]["state"] == "기각"
    assert "R11-1" not in _last_log(conn, "plan_decision")["cause"]["rules"]


def test_r11_1_ignores_investigation_task(conn):
    _start(conn, result="거절", reason="원인 미규명")
    _reply(conn, _task(conn, "출하 경위 확인")["id"], "경위 확인됨", "2026-07-03")
    assert _task(conn, "원인 조사")["state"] == "열림"
    assert rules.open_hold_shipment_tasks(conn) == []


def test_r11_1_no_warning_without_hold_check_task(conn):
    execute(conn, "open_incident", OWNER, {"batch_id": "B-02-2508-03", "applied_date": "2026-07-01"})
    assert _tasks(conn, "출하 경위 확인") == []
    assert rules.open_hold_shipment_tasks(conn) == []
    assert _hold_warnings(conn, "2026-07-01") == []


# ---------------------------------------------------------------------------
# R10-3: 재공급 완료 예상이 기준 기간(12개월, A-19)을 넘으면 생산에 능력 확보 검토 요청
# ---------------------------------------------------------------------------

CAPACITY = "능력 확보 검토"


def _cap_warnings(conn, d="2026-07-03"):
    return [w for w in rules.warnings(conn, d) if w["code"] == "open_capacity_review"]


def test_r10_3_long_recovery_creates_capacity_review(conn):
    _start(conn)
    assert rules.recovery_span(conn, "RP-v1") == {
        "months": 21, "final_month": "2028-03", "threshold_months": 12, "over": True, "rule": "R10-3"}
    t = _task(conn, CAPACITY)
    assert t["state"] == "열림" and t["attrs"]["code"] == "T-07" and t["attrs"]["department"] == "생산"
    assert t["attrs"]["created_by"]["rule"] == "R10-3"
    assert (t["attrs"]["months"], t["attrs"]["final_month"], t["attrs"]["threshold_months"]) == (21, "2028-03", 12)
    # 작업 근거 = 원본 증설·전환안 그대로
    assert [(o["option_id"], o["lead_time_weeks"], o["added_capacity_qty"]) for o in t["attrs"]["options"]] == [
        ("OPT-01", 36, 1600000), ("OPT-02", 7, 600000)]
    assert t["evidence"][0] == "A-19" and all("strat_capex_plan_cv" in e for e in t["evidence"][1:])
    assert [l["dst_id"] for l in db.find_links(conn, rel="TARGETS", src=("task", t["id"]))] == ["RP-v1"]
    auto = [r for r in db.list_action_log(conn) if r["action"] == "능력 확보 검토 요청"]
    assert len(auto) == 1 and auto[0]["actor"] == "시스템" and auto[0]["cause"]["rule"] == "R10-3"

    ws = _cap_warnings(conn)
    assert len(ws) == 1 and ws[0]["rule"] == "R10-3" and ws[0]["evidence"] == [t["id"]]
    assert ws[0]["target"] == {"type": "resupply_plan", "id": "RP-v1"} and "2028-03" in ws[0]["message"]
    v = incident_view(conn, SCM)
    assert v["plans"][0]["recovery"] == {**rules.recovery_span(conn, "RP-v1"), "source": "도출"}
    assert any(w["code"] == "open_capacity_review" for w in v["warnings"])


def test_r10_3_does_not_block_or_require_reason(conn):
    _start(conn)
    _reply(conn, _task(conn, "출하 경위 확인")["id"], "경위 확인됨", "2026-07-03")  # R11-1 근거 필수 해제
    assert _plan_item(conn, "RP-v1")["approve_reason_required"] is False
    _plan_decide(conn, "RP-v1", "승인", "2026-07-03")  # 검토 작업이 열려 있어도 근거 없이 승인된다
    assert _plans(conn)["RP-v1"]["state"] == "확정"
    assert _task(conn, CAPACITY)["state"] == "열림"
    assert _cap_warnings(conn) == []  # 초안이 없으면 경고도 없다


@pytest.mark.parametrize("result", ["확보 방안 있음", "확보 방안 없음"])
def test_r10_3_reply_closes_task_without_changing_plan(conn, result):
    _start(conn)
    t = _task(conn, CAPACITY)
    res = _reply(conn, t["id"], result, "2026-07-03", "증설안은 투자 승인 사항이라 CEO/이사회 상신 필요")
    t = _task(conn, CAPACITY)
    assert t["state"] == "완료" and t["attrs"]["result"] == result
    assert _cap_warnings(conn) == []
    assert list(_plans(conn)) == ["RP-v1"] and _lines(conn, "RP-v1") == V1  # 계획 숫자는 그대로
    assert res.auto_seqs == []
    assert rules.recovery_span(conn, "RP-v1")["over"] is True  # 신호 자체는 계획에 남는다


def test_r10_3_cannot_confirm_extends_and_keeps_warning(conn):
    _start(conn)
    t = _task(conn, CAPACITY)
    _reply(conn, t["id"], "확인 불가", "2026-07-06")
    t = _task(conn, CAPACITY)
    assert t["state"] == "열림" and t["attrs"]["due_date"] == "2026-07-13"
    assert len(_cap_warnings(conn, "2026-07-06")) == 1


def test_r10_3_asked_once_per_incident(conn):
    _start(conn)
    _reply(conn, _task(conn, CAPACITY)["id"], "확보 방안 없음", "2026-07-03")
    _reply(conn, _task(conn, "수주 급감 확인", "C-101")["id"], "우선 공급 요청", "2026-07-09")
    assert list(_plans(conn)) == ["RP-v1", "RP-v2"]
    assert len(_tasks(conn, CAPACITY)) == 1  # v2도 12개월을 넘지만 다시 묻지 않는다
    assert rules.recovery_span(conn, "RP-v2")["over"] is True


def test_r10_3_no_request_within_threshold(conn, monkeypatch):
    from backend.core import ontology
    monkeypatch.setitem(ontology.RULES["R10-3"]["threshold"], "value", 21)
    _start(conn)
    assert rules.recovery_span(conn, "RP-v1")["over"] is False  # 21번째 달 = 기준과 같으면 넘지 않은 것
    assert _tasks(conn, CAPACITY) == []
    assert _cap_warnings(conn) == []

