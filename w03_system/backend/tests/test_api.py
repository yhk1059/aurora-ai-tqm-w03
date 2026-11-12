"""API 테스트: TestClient + 임시 DB 파일. AI는 호출하지 않는다.
core를 직접 실행한 결과와 API 결과가 같은지 확인한다."""

import json

import pytest
from fastapi.testclient import TestClient

from backend.ai import client as ai_client
from backend.api.main import create_app
from backend.core import db
from backend.core.scenario import load_scenario, resolve_inputs, run_scenario
from backend.core.view import incident_view

HELD = ["B-02-2602-01", "B-02-2603-01"]
OPEN = {"actor": "quality_owner", "inputs": {"batch_id": "B-02-2602-01", "applied_date": "2026-07-01"}}


def _make(tmp_path, name="a.sqlite"):
    return TestClient(create_app(str(tmp_path / name)))


@pytest.fixture
def client(tmp_path):
    return _make(tmp_path)


def _core_view(name, actor=None, **kw):
    """같은 시나리오를 core로 직접 실행한 사건 뷰 (JSON 왕복으로 형식을 맞춘다)."""
    conn = db.connect(":memory:")
    try:
        run_scenario(conn, name, **kw)
        return json.loads(json.dumps(incident_view(conn, actor)))
    finally:
        conn.close()


def _batch(v, bid):
    return next(b for b in v["batches"] if b["id"] == bid)


def _actions(v):
    return [a["action"] for a in v["available_actions"]]


def _err(r, status, code):
    assert r.status_code == status, r.text
    assert r.json()["error"]["code"] == code
    assert r.json()["error"]["message"]


def _open_and_submit(client):
    assert client.post("/api/actions/open_incident", json=OPEN).status_code == 200
    r = client.post("/api/actions/submit_agenda", json={
        "actor": "quality_owner", "inputs": {"batch_ids": HELD, "applied_date": "2026-07-01"}})
    assert r.status_code == 200, r.text


# ---------------------------------------------------------------------------
# 조회·액션
# ---------------------------------------------------------------------------


def test_empty_incident(client):
    v = client.get("/api/incident").json()
    assert v["incident"] is None
    assert "B-02-2602-01" in json.dumps(v["openable_batches"])


def test_open_incident_returns_view(client):
    r = client.post("/api/actions/open_incident", json=OPEN)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["result"]["seq"] >= 1
    v = body["view"]
    assert v["incident"]["id"] == "INC-001"
    for bid in HELD:
        assert _batch(v, bid)["state"] == "기준초과(미상신)"
    assert client.get("/api/incident", params={"actor": "quality_owner"}).json() == v


def test_forbidden_keeps_db(client):
    client.post("/api/actions/open_incident", json=OPEN)
    before = client.get("/api/incident").json()
    r = client.post("/api/actions/committee_decision", json={
        "actor": "quality_owner", "inputs": {"batch_ids": HELD, "result": "승인", "applied_date": "2026-07-02"}})
    _err(r, 403, "forbidden")
    assert client.get("/api/incident").json() == before


def test_error_codes(client):
    client.post("/api/actions/open_incident", json=OPEN)
    before = client.get("/api/incident").json()
    _err(client.post("/api/actions/open_incident", json=OPEN), 409, "precondition")
    _err(client.post("/api/actions/no_such", json=OPEN), 404, "unknown_action")
    _err(client.post("/api/actions/open_incident", json={"inputs": OPEN["inputs"]}), 422, "invalid_input")
    _err(client.post("/api/actions/open_incident", json={"actor": "quality_owner"}), 422, "invalid_input")
    assert client.get("/api/incident").json() == before

    r = client.post("/api/actions/submit_agenda", json={
        "actor": "quality_owner", "inputs": {"batch_ids": HELD, "applied_date": "2026-07-01"}})
    assert r.status_code == 200
    before = client.get("/api/incident").json()
    r = client.post("/api/actions/committee_decision", json={
        "actor": "quality_committee", "inputs": {"batch_ids": HELD, "result": "거절", "applied_date": "2026-07-02"}})
    assert r.status_code in (409, 422), r.text
    assert r.json()["error"]["code"] in ("precondition", "invalid_input")
    assert client.get("/api/incident").json() == before


def test_available_actions_by_actor(client):
    _open_and_submit(client)
    committee = client.get("/api/incident", params={"actor": "quality_committee"}).json()
    scm = client.get("/api/incident", params={"actor": "scm"}).json()
    assert "committee_decision" in _actions(committee)
    assert "committee_decision" not in _actions(scm)


def test_reset(client):
    client.post("/api/actions/open_incident", json=OPEN)
    r = client.post("/api/actions/reset", json={"actor": "quality_owner", "inputs": {}})
    assert r.status_code == 200, r.text
    assert r.json()["view"]["incident"] is None
    assert client.get("/api/incident").json()["incident"] is None


# ---------------------------------------------------------------------------
# 정의·시나리오
# ---------------------------------------------------------------------------


def test_ontology(client):
    r = client.get("/api/ontology")
    assert r.status_code == 200
    d = r.json()
    assert len(d["actions"]) == 9
    assert len(d["relations"]) == 17


def test_scenarios_list(client):
    names = {s["name"] for s in client.get("/api/scenarios").json()}
    assert {"demo1", "demo2", "demo3a", "demo3b", "other-batch"} <= names


def test_demo1_same_as_core(client):
    r = client.post("/api/scenarios/demo1")
    assert r.status_code == 200, r.text
    v = r.json()["view"]
    assert v["incident"]["status"] == "복구계획확정"
    plan = v["plans"][-1]
    assert [l["attrs"]["customer_id"] for l in plan["lines"]] == ["C-103", "C-102", "C-101", "C-104", "C-108"]
    assert v == _core_view("demo1")
    assert len(r.json()["steps"]) == len(load_scenario("demo1")["steps"])


def test_demo2_stepwise_same_as_full(client, tmp_path):
    r = client.post("/api/scenarios/demo2", params={"setup_only": "true"})
    assert r.status_code == 200, r.text
    plans = r.json()["view"]["plans"]
    assert len(plans) == 1 and plans[0]["state"] == "확정"

    for step in load_scenario("demo2")["steps"]:
        if step.get("setup") or not step.get("action"):
            continue
        conn = db.connect(tmp_path / "a.sqlite")  # 조건 → 실제 ID 변환만 (읽기)
        try:
            inputs = resolve_inputs(conn, step["inputs"])
        finally:
            conn.close()
        r = client.post(f"/api/actions/{step['action']}", json={"actor": step["actor"], "inputs": inputs})
        assert r.status_code == 200, (step["id"], r.text)

    assert client.get("/api/incident").json() == _core_view("demo2")


def test_scenario_errors(client):
    _err(client.post("/api/scenarios/없는이름"), 404, "not_found")
    _err(client.post("/api/scenarios/demo1", params={"upto": "9-9"}), 422, "invalid_input")


def test_scenario_actor_view(client):
    r = client.post("/api/scenarios/demo2", params={"setup_only": "true", "actor": "scm"})
    assert r.json()["view"]["available_actions"] == _core_view("demo2", "scm", setup_only=True)["available_actions"]


# ---------------------------------------------------------------------------
# AI (호출하지 않는다)
# ---------------------------------------------------------------------------


def test_ai_status(client):
    d = client.get("/api/ai/status").json()
    assert isinstance(d["available"], bool)
    assert d["model"] == ai_client.MODEL


def test_ai_no_key(client, monkeypatch):
    monkeypatch.setattr(ai_client, "is_available", lambda: False)
    client.post("/api/actions/open_incident", json=OPEN)
    r = client.post("/api/ai/agenda_summary", json={"params": {"batch_ids": HELD}})
    assert r.status_code == 200
    assert r.json()["ok"] is False and r.json()["error"] == "no_key"
    _err(client.post("/api/ai/no_such", json={"params": {}}), 404, "not_found")


# ---------------------------------------------------------------------------
# 앱 분리
# ---------------------------------------------------------------------------


def test_two_apps_isolated(tmp_path):
    a, b = _make(tmp_path, "a.sqlite"), _make(tmp_path, "b.sqlite")
    assert a.post("/api/actions/open_incident", json=OPEN).status_code == 200
    assert a.get("/api/incident").json()["incident"]["id"] == "INC-001"
    assert b.get("/api/incident").json()["incident"] is None


def test_reply_examples_endpoint(client):
    r = client.get("/api/reply-examples")
    assert r.status_code == 200
    ex = r.json()["examples"]
    assert ex and all("action" in e and "inputs" in e for e in ex)
    assert "reply-examples" not in {s["name"] for s in client.get("/api/scenarios").json()}
    _err(client.post("/api/scenarios/reply-examples"), 404, "not_found")
    # 예시는 사건 뷰에 섞이지 않는다
    assert "examples" not in client.get("/api/incident").json()


def test_scenarios_list_setup_count(client):
    counts = {s["name"]: s["setup_count"] for s in client.get("/api/scenarios").json()}
    assert counts["demo2"] == 5 and counts["demo1"] == 0
