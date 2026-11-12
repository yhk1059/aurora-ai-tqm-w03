"""core/view.py: 읽기 전용, 사건 없음, 출처, 기준값, 탭·연결망에 필요한 묶음."""

import json

from backend.core.scenario import run_scenario
from backend.core.view import incident_view


def _snapshot(conn):
    return tuple([tuple(r) for r in conn.execute(f"SELECT * FROM {t} ORDER BY rowid")]
                 for t in ("objects", "links", "action_log", "ai_log"))


def test_no_incident(conn):
    v = incident_view(conn, "quality_owner")
    assert v["incident"] is None
    assert any(b["batch_id"] == "B-02-2602-01" for b in v["openable_batches"])
    assert [a["action"] for a in v["available_actions"]] == ["open_incident", "reset"]
    assert incident_view(conn)["available_actions"] == []


def test_view_is_read_only(conn):
    run_scenario(conn, "demo2", upto="2-4b")
    before = _snapshot(conn)
    for actor in (None, "quality_owner", "quality_committee", "scm"):
        incident_view(conn, actor)
    assert _snapshot(conn) == before


def test_view_contents_and_sources(conn):
    run_scenario(conn, "demo1")
    v = incident_view(conn, "scm")
    json.dumps(v, ensure_ascii=False)
    for key in ("incident", "lots", "batches", "customers", "claims", "network", "tasks", "decisions",
                "events", "plans", "held_customers", "warnings", "available_actions", "last_change",
                "log", "thresholds"):
        assert key in v
    assert v["incident"]["origin_lots"] == ["LOT-B-2602-P"]
    assert v["lots"][0]["source"] == "원본" and v["lots"][0]["evidence"]
    assert all(b["metrics"]["source"] == "도출" and b["part_of"]["reason"] for b in v["batches"])
    assert all(c["order_drop_signal"]["source"] == "도출" for c in v["customers"])
    assert all(l["source"] in ("원본", "도출", "모의") for l in v["network"]["shipped_to"])
    assert all("claims" in l and "qty_basis" in l for l in v["network"]["shipped_to"])
    assert len(v["network"]["used_in"]) == 4
    assert v["thresholds"]["R2"]["source"] == "원본" and v["thresholds"]["R2"]["value"] == 10
    assert v["thresholds"]["R6"]["ref"] == "A-07" and v["thresholds"]["R10"]["ref"] == "A-04"
    p = v["plans"][0]
    assert p["slack_capacity"]["source"] == "가정" and p["supply_condition"]["met"] is True
    assert p["supply_batch"]["source"] == "원본"
    assert all(l["source"] == "시스템" for l in p["lines"])
    t = [t for t in v["tasks"] if t["type"] == "출하처 확인"][0]
    assert t["allowed_results"] == ["출하 확인", "영향없음", "확인 불가"]
    assert all(x["type"] == "SHIPPED_TO" and x["customer_id"] == "C-105" for x in t["targets"])
    assert v["last_change"]["action"] == "register_claim"
    assert len(v["log"]["actions"]) > 0 and v["log"]["ai"] == []
