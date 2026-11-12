"""시연 액션 목록(scenarios/*.json)을 끝까지 실행한 뒤 incident_view로 확인한다. 기대값 = demo-scenarios.md."""

import json

import pytest

from backend.core import db
from backend.core.scenario import SCENARIO_DIR, ScenarioError, list_scenarios, load_scenario, run_scenario
from backend.core.view import incident_view

HELD = ["B-02-2602-01", "B-02-2603-01"]
PASSED = ["B-02-2602-02", "B-02-2602-03"]
NAMES = ["demo1", "demo2", "demo3a", "demo3b", "other-batch"]


def _v(conn, upto=None, name=None, **kw):
    if name:
        run_scenario(conn, name, upto=upto, **kw)
    return incident_view(conn)


def _batch(v, bid):
    return next(b for b in v["batches"] if b["id"] == bid)


def _plan(v, version):
    return next(p for p in v["plans"] if p["version"] == version)


def _order(plan):
    return [l["attrs"]["customer_id"] for l in plan["lines"]]


def _c105(v):
    return [l for l in v["network"]["shipped_to"] if l["dst"]["id"] == "C-105"]


def _task(v, type_, customer=None):
    ts = [t for t in v["tasks"] if t["type"] == type_
          and (customer is None or t["attrs"].get("customer_id") == customer)]
    assert len(ts) == 1
    return ts[0]


# ---------------------------------------------------------------------------
# 파일
# ---------------------------------------------------------------------------


def test_files_listed():
    assert sorted(s["name"] for s in list_scenarios()) == sorted(NAMES)
    for n in NAMES:
        assert (SCENARIO_DIR / f"{n}.json").is_file()


def test_every_step_has_source_and_id():
    for n in NAMES:
        for s in load_scenario(n)["steps"]:
            assert s.get("id") and s.get("source") in ("원본", "모의", "시스템")
            if s.get("action"):
                assert s.get("actor")


def test_unknown_upto_and_failure_reports_step(conn):
    with pytest.raises(ValueError):
        run_scenario(conn, "demo1", upto="9-9")
    with pytest.raises(ValueError):
        run_scenario(conn, "no-such")


# ---------------------------------------------------------------------------
# 시연 1
# ---------------------------------------------------------------------------


def test_demo1_after_open(conn):
    v = _v(conn, "1-1", "demo1")
    assert v["incident"]["status"] == "열림"
    for bid, rate, days in [(HELD[0], 0.119, 91), (HELD[1], 0.116, 51)]:
        b = _batch(v, bid)
        assert b["state"] == "기준초과(미상신)"
        assert b["metrics"]["defect_rate"] == pytest.approx(rate, abs=0.0005)
        assert b["metrics"]["days_unsubmitted"] == days
    for bid in PASSED:
        assert _batch(v, bid)["state"] == "관찰해제"
    codes = [w["code"] for w in v["warnings"]]
    assert codes.count("held_batch_shipped") == 2
    assert len({w["target"]["id"] for w in v["warnings"] if w["code"] == "held_lot_used"}) == 3
    assert codes.count("record_conflict") == 1
    c105 = _c105(v)
    assert len(c105) == 2 and all(l["confirm"] == "확인요청중" and l["source"] == "도출" for l in c105)

    states = [(c["before"], c["after"]) for c in v["last_change"]["changes"]
              if c["field"] == "state" and c["target"] == {"type": "batch", "id": PASSED[0]}]
    assert states == [("정상", "관찰"), ("관찰", "관찰해제")]


def test_demo1_end(conn):
    v = _v(conn, None, "demo1")
    assert v["incident"]["status"] == "복구계획확정"
    for bid in HELD:
        assert _batch(v, bid)["state"] == "회수진행"
    assert len(v["plans"]) == 1
    p = _plan(v, 1)
    assert p["state"] == "확정"
    assert _order(p) == ["C-103", "C-102", "C-101", "C-104", "C-108"]
    assert [l["attrs"]["expected_month"] for l in p["lines"]] == [
        "2026-12", "2027-05", "2027-09", "2027-12", "2028-03"]
    assert sorted((d["type"], d["result"]) for d in v["decisions"]) == [("재공급 순서", "승인"), ("회수 범위", "승인")]
    assert _task(v, "안내 대상 결정")["attrs"]["notice_customers"] == ["C-101", "C-102", "C-103", "C-104", "C-108"]


def test_demo1_late_claim_does_not_add_decision_or_plan(conn):
    before = _v(conn, "1-6", "demo1")
    after = _v(conn, None, "demo1")
    assert len(after["decisions"]) == len(before["decisions"]) == 2
    assert len(after["plans"]) == len(before["plans"]) == 1
    assert len(after["claims"]) == len(before["claims"]) + 1
    assert [_batch(after, b)["state"] for b in HELD] == ["회수진행", "회수진행"]


def test_committee_action_visible_only_to_committee(conn):
    run_scenario(conn, "demo1", upto="1-2")
    assert "committee_decision" in [a["action"] for a in incident_view(conn, "quality_committee")["available_actions"]]
    assert "committee_decision" not in [a["action"] for a in incident_view(conn, "scm")["available_actions"]]


# ---------------------------------------------------------------------------
# 시연 2
# ---------------------------------------------------------------------------


def test_demo2_setup_only(conn):
    v = _v(conn, None, "demo2", setup_only=True)
    assert [(p["version"], p["state"]) for p in v["plans"]] == [(1, "확정")]


def test_demo2_news_keeps_judgment(conn):
    before = {b["id"]: b["state"] for b in _v(conn, "1-6", "demo2")["batches"]}
    v = _v(conn, "2-1", "demo2")
    assert {b["id"]: b["state"] for b in v["batches"]} == before
    news = [r for r in v["log"]["actions"] if r["action"] == "register_news"]
    assert len(news) == 1 and "R3" in news[0]["cause"]["rules"]
    assert news[0]["cause"]["review"]["conclusion"] == "판정 유지"
    ev = [e for e in v["events"] if e["type"] == "보도"][0]
    assert ev["source"] == "원본" and ev["occurred_date"] is None


def test_demo2_pending_then_confirmed_claim(conn):
    v = _v(conn, "2-2a", "demo2")
    b = _batch(v, PASSED[1])
    assert b["state"] == "관찰"
    assert b["metrics"]["rate_if_confirmed"] == pytest.approx(800 / 161592)
    assert round(b["metrics"]["rate_if_confirmed"] * 100, 1) == 0.5
    assert b["metrics"]["over_threshold"] is False
    assert b["metrics"]["release_due_date"] is None

    v = _v(conn, "2-2b", "demo2")
    b = _batch(v, PASSED[1])
    claim = [c for c in v["claims"] if c["batch_id"] == PASSED[1]][0]
    assert claim["state"] == "확정" and claim["source"] == "모의"
    assert b["state"] == "관찰"
    assert b["metrics"]["release_due_date"] == "2026-10-06"


def test_demo2_sales_reply_reorders_plan(conn):
    v = _v(conn, "2-4b", "demo2")
    p = _plan(v, 2)
    assert p["state"] == "초안"
    assert _order(p) == ["C-101", "C-103", "C-102", "C-104", "C-108"]
    delays = {d["customer_id"]: d["delay_months"] for d in p["diff"]}
    assert delays["C-103"] == 4 and delays["C-102"] == 4
    assert v["incident"]["status"] == "회수진행"


def test_demo2_end(conn):
    v = _v(conn, None, "demo2")
    assert [(p["version"], p["state"]) for p in v["plans"]] == [(1, "확정"), (2, "확정")]
    assert v["incident"]["status"] == "복구계획확정"


# ---------------------------------------------------------------------------
# 시연 3-A
# ---------------------------------------------------------------------------


def test_demo3a_conditional(conn):
    v = _v(conn, "3-2", "demo3a")
    assert [_batch(v, b)["state"] for b in HELD] == ["부분회수", "부분회수"]
    p = _plan(v, 1)
    assert p["state"] == "초안" and "C-105" not in _order(p)
    assert [h["customer_id"] for h in v["held_customers"]] == ["C-105"]


def test_demo3a_unfavorable_reply(conn):
    v = _v(conn, "3-3", "demo3a")
    t = _task(v, "출하처 확인", "C-105")
    assert t["state"] == "열림" and t["due_date"] == "2026-07-15"
    assert all(l["confirm"] == "확인요청중" for l in _c105(v))
    assert [_batch(v, b)["state"] for b in HELD] == ["부분회수", "부분회수"]


def test_demo3a_end(conn):
    v = _v(conn, None, "demo3a")
    c105 = _c105(v)
    assert all(l["confirm"] == "회신확인" for l in c105)
    assert sum(l["qty"] for l in c105) == 11765
    assert all(l["qty_basis"] == "클레임 합(하한)" for l in c105)
    assert [_batch(v, b)["state"] for b in HELD] == ["회수진행", "회수진행"]
    p = _plan(v, 2)
    assert p["state"] == "초안"
    last = p["lines"][5]["attrs"]
    assert last["customer_id"] == "C-105" and last["rank"] == 6
    assert last["expected_month"] == "2028-04" and last["lower_bound"] is True


# ---------------------------------------------------------------------------
# 시연 3-B
# ---------------------------------------------------------------------------


def test_demo3b_reject(conn):
    v = _v(conn, "3-5", "demo3b")
    assert [_batch(v, b)["state"] for b in HELD] == ["조사계속", "조사계속"]
    assert _task(v, "원인 조사")["state"] == "열림"
    assert v["incident"]["status"] == "판정중"
    d = [d for d in v["decisions"] if d["result"] == "거절"][0]
    assert d["reason"] == "원인 미규명"


def test_demo3b_end(conn):
    v = _v(conn, None, "demo3b")
    assert [_batch(v, b)["state"] for b in HELD] == ["상신중", "상신중"]


# ---------------------------------------------------------------------------
# 다른 배치, 재현, 직렬화, 모의 표시
# ---------------------------------------------------------------------------


def test_other_batch_not_recall(conn):
    v = _v(conn, None, "other-batch")
    assert v["incident"]["status"] == "관찰중"
    assert v["incident"]["start_batch"] == "B-02-2508-03"
    assert not any(b["state"] == "기준초과(미상신)" for b in v["batches"])
    assert all(b["metrics"]["over_threshold"] is False for b in v["batches"])
    assert "committee_decision" not in [
        a["action"] for a in incident_view(conn, "quality_committee")["available_actions"]]


@pytest.mark.parametrize("name", NAMES)
def test_reproducible_and_serializable(name):
    views = []
    for _ in range(2):
        c = db.connect(":memory:")
        run_scenario(c, name)
        views.append(json.dumps(incident_view(c, "quality_owner"), ensure_ascii=False, sort_keys=True))
        c.close()
    assert views[0] == views[1]


@pytest.mark.parametrize("name", NAMES)
def test_mock_inputs_marked(conn, name):
    v = _v(conn, None, name)
    for c in v["claims"]:
        if c["id"].startswith("QC-M-"):
            assert c["source"] == "모의"
    for d in v["decisions"]:
        assert d["source"] == "모의"
    for e in v["events"]:
        if e["type"] in ("회신", "클레임 접수"):
            assert e["source"] == "모의"


def test_failure_names_step(conn, tmp_path, monkeypatch):
    bad = {"name": "bad", "title": "t", "description": "d", "steps": [
        {"id": "B-1", "action": "submit_agenda", "actor": "quality_owner",
         "inputs": {"batch_ids": ["B-02-2602-01"], "applied_date": "2026-07-01"}, "source": "모의"}]}
    (tmp_path / "bad.json").write_text(json.dumps(bad), encoding="utf-8")
    monkeypatch.setattr("backend.core.scenario.SCENARIO_DIR", tmp_path)
    with pytest.raises(ScenarioError) as e:
        run_scenario(conn, "bad")
    assert e.value.step_id == "B-1"
