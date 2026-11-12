"""core/actions.py (판정까지): 시연 1-1 ~ 1-3·1-7, 2-1 ~ 2-2b, 3-1 ~ 3-2·3-5와 대조."""

import pytest

from backend.core import db, rules
from backend.core.actions import ActionError, available_actions, execute

HELD = ["B-02-2602-01", "B-02-2603-01"]
PASSED = ["B-02-2602-02", "B-02-2602-03"]
OWNER, COMMITTEE = "quality_owner", "quality_committee"


def _open(conn, d="2026-07-01"):
    return execute(conn, "open_incident", OWNER, {"batch_id": "B-02-2602-01", "applied_date": d})


def _submit(conn, d="2026-07-01", batches=HELD):
    return execute(conn, "submit_agenda", OWNER, {"batch_ids": batches, "applied_date": d})


def _decide(conn, result, reason=None, d="2026-07-02", batches=HELD):
    return execute(conn, "committee_decision", COMMITTEE,
                   {"batch_ids": batches, "result": result, "reason": reason, "applied_date": d})


def _claim(conn, batch, customer, qty, status, d, received=None):
    return execute(conn, "register_claim", OWNER, {
        "batch_id": batch, "customer_id": customer, "qty": qty, "status": status,
        "received_date": received or d, "applied_date": d})


def _state(conn, batch):
    return db.get_object(conn, "batch", batch)["state"]


def _tasks(conn, type_=None):
    return [t for t in db.list_objects(conn, "task") if type_ is None or t["attrs"]["type"] == type_]


def _targets(conn, task_id):
    return db.find_links(conn, rel="TARGETS", src=("task", task_id))


def _c105_lines(conn):
    return [l for l in db.find_links(conn, rel="SHIPPED_TO") if l["dst_id"] == "C-105"]


def _snapshot(conn):
    return tuple([tuple(r) for r in conn.execute(f"SELECT * FROM {t} ORDER BY rowid")]
                 for t in ("objects", "links", "action_log"))


# ---------------------------------------------------------------------------
# 시연 1-1 사건 열기
# ---------------------------------------------------------------------------


def test_open_incident(conn):
    res = _open(conn)
    inc = db.get_object(conn, "incident", "INC-001")
    assert inc["attrs"]["current_date"] == "2026-07-01"
    assert inc["attrs"]["origin_lots"] == ["LOT-B-2602-P"]
    part_of = db.find_links(conn, rel="PART_OF")
    assert sorted(l["src_id"] for l in part_of) == sorted(HELD + PASSED)
    reasons = {l["src_id"]: l["attrs"]["reason"] for l in part_of}
    assert reasons["B-02-2602-01"] == "클레임" and reasons["B-02-2602-02"] == "로트 공유(R4)"

    for b in HELD:
        assert _state(conn, b) == "기준초과(미상신)"
    for b in PASSED:
        assert _state(conn, b) == "관찰해제"

    log = db.list_action_log(conn)
    assert log[0]["action"] == "open_incident" and log[0]["seq"] == res.seq
    transitions = {(c["target"]["id"], c["before"], c["after"]) for row in log[1:] for c in row["changes"]}
    for b in PASSED:
        assert (b, "정상", "관찰") in transitions
        assert (b, "관찰", "관찰해제") in transitions
    release_rows = [r for r in log if r["action"] == "관찰 해제"]
    assert len(release_rows) == 2 and all(r["actor"] == "시스템" and r["cause"]["rule"] == "R6"
                                          and r["cause"]["after_seq"] == res.seq for r in release_rows)
    assert res.auto_seqs == [r["seq"] for r in log[1:]]

    c105 = _c105_lines(conn)
    assert len(c105) == 2
    assert all(l["confirm"] == "확인요청중" and l["source"] == "도출" and l["qty"] is None
               and l["qty_basis"] == "없음" for l in c105)

    tasks = _tasks(conn)
    assert len(tasks) == 2
    assert all(t["state"] == "열림" and t["attrs"]["due_date"] == "2026-07-08" for t in tasks)
    hold = _tasks(conn, "출하 경위 확인")[0]
    assert sorted(l["dst_id"] for l in _targets(conn, hold["id"])) == HELD
    assert {w["code"] for w in hold["attrs"]["basis_warnings"]} >= {"held_batch_shipped", "held_lot_used",
                                                                     "record_conflict"}
    ship = _tasks(conn, "출하처 확인")[0]
    assert ship["attrs"]["customer_id"] == "C-105"
    assert sorted(l["dst_id"] for l in _targets(conn, ship["id"])) == sorted(str(l["link_id"]) for l in c105)
    assert all(l["dst_type"] == "SHIPPED_TO" for l in _targets(conn, ship["id"]))

    assert rules.incident_status(conn) == "열림"
    assert {"type": "incident", "id": "INC-001"} in res.created


# ---------------------------------------------------------------------------
# 시연 1-2, 1-3 상신·승인 / 1-7
# ---------------------------------------------------------------------------


def test_submit_and_approve(conn):
    _open(conn)
    _submit(conn)
    assert all(_state(conn, b) == "상신중" for b in HELD)
    assert rules.incident_status(conn) == "판정중"

    res = _decide(conn, "승인")
    assert all(_state(conn, b) == "회수진행" for b in HELD)
    decisions = db.list_objects(conn, "decision")
    assert [d["id"] for d in decisions] == ["DEC-001"]
    assert decisions[0]["attrs"]["result"] == "승인" and decisions[0]["source"] == "모의"
    assert sorted(l["dst_id"] for l in db.find_links(conn, rel="DECIDES")) == HELD
    notice = _tasks(conn, "안내 대상 결정")
    assert len(notice) == 1 and notice[0]["state"] == "열림" and notice[0]["attrs"]["due_date"] == "2026-07-09"
    cands = notice[0]["attrs"]["candidates"]
    assert [c["customer_id"] for c in cands["recall_batch_customers"]] == ["C-101", "C-102", "C-103", "C-104", "C-108"]
    assert [c["customer_id"] for c in cands["watch_batch_customers"]] == ["C-101", "C-102", "C-103"]
    assert db.find_links(conn, rel="CREATES", src=("decision", "DEC-001"))
    assert all(l["confirm"] == "확인요청중" for l in _c105_lines(conn))
    assert db.get_object(conn, "incident", "INC-001")["attrs"]["current_date"] == "2026-07-02"
    assert any(c["field"] == "current_date" for c in res.changes)


def test_new_claim_on_recalled_batch_keeps_state(conn):
    _open(conn)
    _submit(conn)
    _decide(conn, "승인")
    n_dec, n_tasks = len(db.list_objects(conn, "decision")), len(_tasks(conn))
    res = _claim(conn, "B-02-2602-01", "C-101", 500, "확정", "2026-07-06")
    assert _state(conn, "B-02-2602-01") == "회수진행"
    assert res.auto_seqs == []
    assert len(db.list_objects(conn, "decision")) == n_dec and len(_tasks(conn)) == n_tasks
    assert db.get_object(conn, "claim", "QC-M-001")["state"] == "확정"
    assert db.find_links(conn, rel="CLAIMED_LOT", src=("claim", "QC-M-001"))[0]["dst_id"] == "LOT-B-2602-P"


# ---------------------------------------------------------------------------
# 시연 3-2 조건부, 3-5 거절
# ---------------------------------------------------------------------------


def test_conditional_stays_partial(conn):
    _open(conn)
    _submit(conn)
    _decide(conn, "조건부")
    assert all(_state(conn, b) == "부분회수" for b in HELD)
    assert len(_tasks(conn, "안내 대상 결정")) == 1


def test_reject_requires_reason(conn):
    _open(conn)
    _submit(conn)
    before = _snapshot(conn)
    for reason in (None, "", "  "):
        with pytest.raises(ActionError) as e:
            _decide(conn, "거절", reason)
        assert e.value.code in ("precondition", "invalid_input")
        assert _snapshot(conn) == before

    _decide(conn, "거절", "원인 미규명")
    assert all(_state(conn, b) == "조사계속" for b in HELD)
    inv = _tasks(conn, "원인 조사")
    assert len(inv) == 1 and inv[0]["state"] == "열림"
    assert sorted(l["dst_id"] for l in _targets(conn, inv[0]["id"])) == HELD
    assert db.get_object(conn, "decision", "DEC-001")["attrs"]["reason"] == "원인 미규명"


def test_new_confirmed_claim_after_reject_allows_resubmit(conn):
    _open(conn)
    _submit(conn)
    _decide(conn, "거절", "원인 미규명")
    _claim(conn, "B-02-2602-01", "C-101", 300, "확정", "2026-07-03")
    assert _state(conn, "B-02-2602-01") == "재상신 후보"
    assert _state(conn, "B-02-2603-01") == "조사계속"
    acts = {a["action"]: a for a in available_actions(conn, OWNER)}
    assert acts["submit_agenda"]["targets"] == {"batch_ids": ["B-02-2602-01"]}
    _submit(conn, "2026-07-03", ["B-02-2602-01"])
    assert _state(conn, "B-02-2602-01") == "상신중"


# ---------------------------------------------------------------------------
# 시연 2-1 보도, 2-2a·2-2b 미확정 → 확정
# ---------------------------------------------------------------------------


def _all_states(conn):
    return ({b["id"]: b["state"] for b in db.list_objects(conn, "batch")},
            {l["link_id"]: l["confirm"] for l in db.find_links(conn, rel="SHIPPED_TO")},
            {t["id"]: t["state"] for t in _tasks(conn)})


def test_news_changes_nothing(conn):
    _open(conn)
    _submit(conn)
    _decide(conn, "승인")
    before = _all_states(conn)
    res = execute(conn, "register_news", OWNER, {
        "content": "피부 트러블 관련 보도 (제품·배치 미특정)", "applied_date": "2026-07-06",
        "source_ref": "05_external/news/ext_news_quality_incident.md"})
    assert _all_states(conn) == before
    events = db.list_objects(conn, "event")
    assert len(events) == 1 and events[0]["attrs"]["type"] == "보도"
    assert events[0]["attrs"]["occurred_date"] is None
    assert db.find_links(conn, rel="TRIGGERS", src=("event", events[0]["id"]))
    row = db.list_action_log(conn)[res.seq - 1]
    assert "R3" in row["cause"]["rules"]
    review = row["cause"]["review"]
    assert review["conclusion"] == "판정 유지"
    assert all(b["before"] == b["after"] for b in review["batches"])
    assert any("quality_policy_cv" in s for s in review["basis_source"])
    assert res.auto_seqs == []


def test_pending_claim_then_confirm(conn):
    _open(conn)
    res = _claim(conn, "B-02-2602-03", "C-101", 800, "접수", "2026-07-07")
    assert _state(conn, "B-02-2602-03") == "관찰"
    assert db.list_action_log(conn)[res.auto_seqs[0] - 1]["action"] == "관찰 복귀"
    m = rules.batch_metrics(conn, "B-02-2602-03", "2026-07-07")
    assert m["over_threshold"] is False and m["release_due_date"] is None
    assert abs(m["rate_if_confirmed"] - 800 / 161592) < 1e-9
    ev = db.list_objects(conn, "event")[0]
    assert ev["attrs"]["type"] == "클레임 접수" and ev["attrs"]["applied_date"] == "2026-07-07"

    execute(conn, "resolve_claim", OWNER, {"claim_id": "QC-M-001", "result": "확정",
                                           "applied_date": "2026-07-08"})
    claim = db.get_object(conn, "claim", "QC-M-001")
    assert claim["state"] == "확정" and claim["attrs"]["confirmed_date"] == "2026-07-08"
    assert _state(conn, "B-02-2602-03") == "관찰"
    assert rules.batch_metrics(conn, "B-02-2602-03", "2026-07-08")["release_due_date"] == "2026-10-06"


def test_pending_claim_rejected_returns_to_released(conn):
    _open(conn)
    _claim(conn, "B-02-2602-03", "C-101", 800, "접수", "2026-07-07")
    execute(conn, "resolve_claim", OWNER, {"claim_id": "QC-M-001", "result": "기각",
                                           "applied_date": "2026-07-08"})
    assert db.get_object(conn, "claim", "QC-M-001")["state"] == "기각"
    assert _state(conn, "B-02-2602-03") == "관찰해제"


def test_large_confirmed_claim_goes_over_threshold(conn):
    _open(conn)
    res = _claim(conn, "B-02-2602-03", "C-101", 20000, "확정", "2026-07-08")
    assert _state(conn, "B-02-2602-03") == "기준초과(미상신)"
    names = [db.list_action_log(conn)[s - 1]["action"] for s in res.auto_seqs]
    assert names == ["관찰 복귀", "판정 재계산"]


def test_claim_from_unshipped_customer_creates_check_task(conn):
    _open(conn)
    _claim(conn, "B-02-2602-02", "C-104", 100, "접수", "2026-07-03")
    line = [l for l in db.find_links(conn, rel="SHIPPED_TO", src=("batch", "B-02-2602-02")) if l["dst_id"] == "C-104"]
    assert len(line) == 1 and line[0]["confirm"] == "확인요청중" and line[0]["source"] == "도출"
    tasks = [t for t in _tasks(conn, "출하처 확인") if t["attrs"]["customer_id"] == "C-104"]
    assert len(tasks) == 1


# ---------------------------------------------------------------------------
# 권한·전제 조건·원자성·재현
# ---------------------------------------------------------------------------


def test_permissions_and_unknown(conn):
    _open(conn)
    _submit(conn)
    with pytest.raises(ActionError) as e:
        execute(conn, "committee_decision", OWNER,
                {"batch_ids": HELD, "result": "승인", "applied_date": "2026-07-02"})
    assert e.value.code == "forbidden"
    with pytest.raises(ActionError) as e:
        execute(conn, "no_such_action", OWNER, {})
    assert e.value.code == "unknown_action"


def test_preconditions(conn):
    _open(conn)
    with pytest.raises(ActionError) as e:
        _open(conn)
    assert e.value.code == "precondition"
    with pytest.raises(ActionError) as e:
        _submit(conn, batches=["B-02-2602-02"])
    assert e.value.code == "precondition"
    with pytest.raises(ActionError) as e:
        _submit(conn, d="2026-06-30")
    assert e.value.code == "invalid_input"
    with pytest.raises(ActionError) as e:
        execute(conn, "register_claim", OWNER, {"batch_id": "B-02-2602-01", "applied_date": "2026-07-01"})
    assert e.value.code == "invalid_input"


def test_open_incident_requires_claims(conn):
    with pytest.raises(ActionError) as e:
        execute(conn, "open_incident", OWNER, {"batch_id": "NO-SUCH", "applied_date": "2026-07-01"})
    assert e.value.code == "precondition"
    assert db.list_objects(conn) == [] and db.list_action_log(conn) == []


def test_atomic_rollback_on_failure(conn, monkeypatch):
    _open(conn)
    before = _snapshot(conn)
    with pytest.raises(ActionError):
        _decide(conn, "승인")  # 상신 전이므로 전제 조건 위반
    assert _snapshot(conn) == before

    # 효과 도중 실패해도 앞서 쓴 것까지 모두 되돌린다
    from backend.core import actions

    def boom(ctx):
        raise RuntimeError("자동 처리 실패")
    monkeypatch.setattr(actions, "AUTO_PROCESSES", [boom])
    with pytest.raises(RuntimeError):
        _submit(conn)
    assert _snapshot(conn) == before


def _demo(conn):
    _open(conn)
    _submit(conn)
    _decide(conn, "조건부")
    execute(conn, "register_news", OWNER, {"content": "보도", "applied_date": "2026-07-06"})
    _claim(conn, "B-02-2602-03", "C-101", 800, "접수", "2026-07-07")
    execute(conn, "resolve_claim", OWNER, {"claim_id": "QC-M-001", "result": "확정",
                                           "applied_date": "2026-07-08"})


def test_replay_is_deterministic():
    a, b = db.connect(":memory:"), db.connect(":memory:")
    _demo(a)
    _demo(b)
    assert _snapshot(a) == _snapshot(b)
    a.close()
    b.close()


# ---------------------------------------------------------------------------
# available_actions, reset
# ---------------------------------------------------------------------------


def _names(conn, actor):
    return {a["action"]: a for a in available_actions(conn, actor)}


def test_available_actions(conn):
    before = _names(conn, OWNER)
    assert set(before) == {"open_incident", "reset"}
    assert "B-02-2602-01" in before["open_incident"]["targets"]["batch_id"]
    assert set(_names(conn, COMMITTEE)) == {"reset"}

    _open(conn)
    owner = _names(conn, OWNER)
    assert owner["submit_agenda"]["targets"] == {"batch_ids": HELD}
    assert owner["submit_agenda"]["label"] == "안건 상신"
    assert {"register_claim", "register_news", "reset"} <= set(owner)
    assert "resolve_claim" not in owner and "open_incident" not in owner
    assert "committee_decision" not in _names(conn, COMMITTEE)

    execute(conn, "submit_agenda", OWNER, {**owner["submit_agenda"]["targets"], "applied_date": "2026-07-01"})
    assert "submit_agenda" not in _names(conn, OWNER)
    committee = _names(conn, COMMITTEE)
    assert committee["committee_decision"]["targets"] == {"batch_ids": HELD}
    execute(conn, "committee_decision", COMMITTEE,
            {**committee["committee_decision"]["targets"], "result": "승인", "applied_date": "2026-07-02"})

    _claim(conn, "B-02-2602-03", "C-101", 800, "접수", "2026-07-07")
    owner = _names(conn, OWNER)
    assert owner["resolve_claim"]["targets"] == {"claim_id": ["QC-M-001"]}
    execute(conn, "resolve_claim", OWNER, {"claim_id": owner["resolve_claim"]["targets"]["claim_id"][0],
                                           "result": "기각", "applied_date": "2026-07-07"})


def test_reset(conn):
    _open(conn)
    _submit(conn)
    execute(conn, "reset", COMMITTEE, {})
    for t in ("objects", "links", "action_log"):
        assert conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] == 0
    _open(conn)
    assert db.get_object(conn, "incident", "INC-001") is not None
