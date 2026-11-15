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


def _hold_check(v):
    return [w for w in v["warnings"] if w["code"] == "open_hold_shipment_check"]


def _last_log(v, action):
    return [r for r in v["log"]["actions"] if r["action"] == action][-1]


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


def test_demo1_approve_with_reason_while_hold_check_open(conn):
    """1-6: 출하 경위 확인(T-01)이 열린 채 근거를 적고 승인한다 (R11-1)."""
    before = _v(conn, "1-5", "demo1")
    assert _hold_check(before)
    after = _v(conn, "1-6", "demo1")
    assert _plan(after, 1)["state"] == "확정"
    assert _task(after, "출하 경위 확인")["state"] == "열림"
    log = _last_log(after, "plan_decision")
    assert "R11-1" in log["cause"]["rules"]
    assert "출하 경위" in log["inputs"]["reason"]


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


def test_demo2_hold_check_reply_clears_warning(conn):
    """2-4c: 출하 경위 확인 회신 '경위 확인됨' → T-01 완료, 계획 v2 초안의 경고 해제 (R11-1)."""
    v = _v(conn, "2-4b", "demo2")
    assert _plan(v, 2)["state"] == "초안" and _hold_check(v)
    v = _v(conn, "2-4c", "demo2")
    t = _task(v, "출하 경위 확인")
    assert t["state"] == "완료"
    assert not _hold_check(v)
    assert _plan(v, 2)["state"] == "초안"
    assert _order(_plan(v, 2)) == ["C-101", "C-103", "C-102", "C-104", "C-108"]


def test_demo2_end(conn):
    v = _v(conn, None, "demo2")
    assert [(p["version"], p["state"]) for p in v["plans"]] == [(1, "대체됨"), (2, "확정")]
    assert v["incident"]["status"] == "복구계획확정"
    assert len(v["plans"]) == 2
    assert "R11-1" not in _last_log(v, "plan_decision")["cause"]["rules"]
    assert not _hold_check(v)


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


# ---------------------------------------------------------------------------
# 관찰 해제 예정일은 관찰 대상 배치에만 (1-frontend step 0)
# ---------------------------------------------------------------------------


def test_release_date_only_for_observed_batches(conn):
    from backend.core.view import incident_view
    run_scenario(conn, "demo1", upto="1-1")
    by_id = {b["id"]: b for b in incident_view(conn)["batches"]}
    for bid in ("B-02-2602-01", "B-02-2603-01"):
        assert by_id[bid]["state"] == "기준초과(미상신)"
        assert by_id[bid]["metrics"]["release_due_date"] is None
        assert by_id[bid]["metrics"]["release_basis"] is None
    for bid, due in (("B-02-2602-02", "2026-06-01"), ("B-02-2602-03", "2026-05-24")):
        assert by_id[bid]["state"] == "관찰해제"
        assert by_id[bid]["metrics"]["release_due_date"] == due
        assert by_id[bid]["metrics"]["release_basis"] == "마지막 출하일"


def test_release_date_hidden_in_recall_states(conn):
    from backend.core.view import incident_view
    run_scenario(conn, "demo1", upto="1-3")
    for b in incident_view(conn)["batches"]:
        if b["state"] in ("상신중", "회수진행", "부분회수", "조사계속", "재상신 후보", "기준초과(미상신)"):
            assert b["metrics"]["release_due_date"] is None, b["id"]


# ---------------------------------------------------------------------------
# 모의 입력 예시 (scenarios/reply-examples.json)
# ---------------------------------------------------------------------------

from backend.core import ontology  # noqa: E402
from backend.core.scenario import list_reply_examples  # noqa: E402

EXAMPLE_ACTIONS = {"apply_reply", "committee_decision", "plan_decision", "register_claim", "resolve_claim",
                   "register_news"}
RUNTIME_KEYS = {"task_id", "plan_id", "claim_id", "batch_ids", "applied_date", "task", "plan", "claim"}


def test_examples_not_a_scenario(conn):
    assert "reply-examples" not in [s["name"] for s in list_scenarios()]
    with pytest.raises(ValueError):
        load_scenario("reply-examples")
    with pytest.raises(ValueError):
        run_scenario(conn, "reply-examples")


def test_examples_shape():
    ex = list_reply_examples()
    assert ex
    for e in ex:
        assert set(e) == {"action", "task_type", "customer_id", "label", "tone", "source", "inputs"}, e
        assert e["action"] in EXAMPLE_ACTIONS
        assert e["tone"] in ("유리", "불리") and e["source"] in ("모의", "원본") and e["label"]
        assert not (set(e["inputs"]) & RUNTIME_KEYS), e
        if e["action"] == "apply_reply":
            allowed = [r["result"] for r in ontology.TASK_TYPES[e["task_type"]]["allowed_results"]]
            assert e["inputs"]["result"] in allowed, e
            assert e["inputs"]["reply_text"]
        else:
            assert e["task_type"] is None and e["customer_id"] is None
        if e["action"] in ("committee_decision", "plan_decision", "resolve_claim"):
            choices = next(i for i in ontology.ACTIONS[e["action"]]["inputs"] if i["key"] == "result")["choices"]
            assert e["inputs"]["result"] in choices


def test_examples_cover_mock_reply_table():
    """demo-scenarios.md '모의 회신 목록'의 모든 칸(유리·불리)을 덮는다."""
    have = {(e["action"], e["task_type"], e["inputs"].get("result"), e["tone"]) for e in list_reply_examples()}
    need = {
        ("committee_decision", None, "승인", "유리"), ("committee_decision", None, "조건부", "불리"),
        ("committee_decision", None, "거절", "불리"),
        ("apply_reply", "출하처 확인", "출하 확인", "유리"), ("apply_reply", "출하처 확인", "확인 불가", "불리"),
        ("apply_reply", "출하처 확인", "영향없음", "불리"),
        ("apply_reply", "안내 대상 결정", "회수 배치 고객만", "유리"),
        ("apply_reply", "안내 대상 결정", "관찰·해제 배치 고객 포함", "불리"),
        ("apply_reply", "수주 급감 확인", "순서 유지", "유리"),
        ("apply_reply", "수주 급감 확인", "우선 공급 요청", "불리"),
        ("plan_decision", None, "승인", "유리"), ("plan_decision", None, "거절", "불리"),
        ("apply_reply", "원인 조사", "원인 확인", "유리"), ("apply_reply", "원인 조사", "원인 미확인", "불리"),
        ("apply_reply", "출하 경위 확인", "경위 확인됨", "유리"), ("apply_reply", "출하 경위 확인", "확인 불가", "불리"),
        ("resolve_claim", None, "기각", "유리"), ("resolve_claim", None, "확정", "불리"),
    }
    assert need <= have
    acts = {e["action"] for e in list_reply_examples()}
    assert {"register_claim", "register_news"} <= acts
    for cid in ("C-101", "C-104"):
        assert any(e["task_type"] == "수주 급감 확인" and e["customer_id"] == cid for e in list_reply_examples())


def test_examples_use_scenario_sentences():
    """시연 표의 모의 입력 문장은 scenarios/demo*.json과 같다."""
    texts = {e["inputs"].get("reply_text") or e["inputs"].get("reason") or e["inputs"].get("content")
             for e in list_reply_examples()}
    for n in NAMES:
        for s in load_scenario(n)["steps"]:
            inp = s.get("inputs") or {}
            for k in ("reply_text", "reason", "content"):
                if s.get("action") in EXAMPLE_ACTIONS and inp.get(k):
                    assert inp[k] in texts, (n, s["id"], k)


def test_setup_count():
    counts = {s["name"]: s["setup_count"] for s in list_scenarios()}
    assert counts == {"demo1": 0, "demo2": 5, "demo3a": 2, "demo3b": 2, "other-batch": 0}
