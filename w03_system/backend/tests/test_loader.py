"""core/loader.py: B-02-2602-01 사건 범위 적재 결과를 2-findings/lot-b2602p-incident.md 사실과 대조."""

from pathlib import Path

import pytest

from backend.core import db, loader

BATCHES = ["B-02-2602-01", "B-02-2602-02", "B-02-2602-03", "B-02-2603-01"]


def test_summary(conn):
    s = loader.load_incident_scope(conn, "B-02-2602-01")
    assert s["origin_lots"] == ["LOT-B-2602-P"]
    assert s["batches"] == BATCHES
    assert s["customers"] == ["C-101", "C-102", "C-103", "C-104", "C-105", "C-108"]
    assert s["claim_count"] == 45


def test_origin_lot_without_quantities(loaded):
    lots = db.list_objects(loaded, "material_lot")
    assert [x["id"] for x in lots] == ["LOT-B-2602-P"]
    a = lots[0]["attrs"]
    assert a["inspection_result"] == "보류" and a["inspection_date"] == "2026-02-09"
    assert not {"received_qty", "consumed_qty"} & set(a)
    assert all("qty" not in (l["attrs"] or {}) and l["qty"] is None
               for l in db.find_links(loaded, rel="USED_IN"))
    assert len(db.find_links(loaded, rel="USED_IN")) == 4


def test_batches(loaded):
    batches = {b["id"]: b for b in db.list_objects(loaded, "batch")}
    assert sorted(batches) == BATCHES
    assert [batches[b]["attrs"]["produced_qty"] for b in BATCHES] == [150745, 154685, 161592, 160733]
    assert {b["state"] for b in batches.values()} == {"정상"}


def test_claims(loaded):
    claims = db.list_objects(loaded, "claim")
    assert len(claims) == 45
    assert {c["state"] for c in claims} == {"확정"}
    assert all(c["attrs"]["confirmed_date"] == c["attrs"]["received_date"] for c in claims)
    by_batch = {}
    for l in db.find_links(loaded, rel="CLAIMED_ON"):
        c = db.get_object(loaded, "claim", l["src_id"])
        by_batch.setdefault(l["dst_id"], []).append(c["attrs"]["qty"])
    assert {b: len(q) for b, q in by_batch.items()} == {"B-02-2602-01": 22, "B-02-2603-01": 23}
    assert sum(by_batch["B-02-2602-01"]) == 17900
    assert sum(by_batch["B-02-2603-01"]) == 18622
    assert len(db.find_links(loaded, rel="CLAIMED_BY")) == 45
    assert len(db.find_links(loaded, rel="CLAIMED_LOT", dst=("material_lot", "LOT-B-2602-P"))) == 45


def test_shipped_to(loaded):
    rows = db.find_links(loaded, rel="SHIPPED_TO")
    assert len(rows) == 15
    count = {}
    for r in rows:
        count[r["src_id"]] = count.get(r["src_id"], 0) + 1
    assert count == {"B-02-2602-01": 4, "B-02-2602-02": 3, "B-02-2602-03": 3, "B-02-2603-01": 5}
    assert {(r["confirm"], r["source"], r["qty_basis"]) for r in rows} == {("확인", "원본", "출하기록 합")}
    q = {(r["src_id"], r["dst_id"]): r["qty"] for r in rows}
    assert q[("B-02-2602-01", "C-103")] == 55211
    assert q[("B-02-2603-01", "C-108")] == 34929
    assert all(r["evidence"] and all(e.startswith(loader.SBL + "#SBL-") for e in r["evidence"]) for r in rows)
    # SHIPPED_TO 수량 = 그 배치·고객의 출하 기록 합
    for r in rows:
        ships = {l["src_id"] for l in db.find_links(loaded, rel="SHIPMENT_OF", dst=("batch", r["src_id"]))} & \
                {l["src_id"] for l in db.find_links(loaded, rel="SHIPMENT_FOR", dst=("customer", r["dst_id"]))}
        assert sum(db.get_object(loaded, "shipment", s)["attrs"]["qty"] for s in ships) == r["qty"]


def test_c105_claim_only_no_shipped_to(loaded):
    assert db.get_object(loaded, "customer", "C-105") is not None
    assert db.find_links(loaded, rel="SHIPPED_TO", dst=("customer", "C-105")) == []
    assert db.find_links(loaded, rel="CLAIMED_BY", dst=("customer", "C-105"))


def test_customer_booking_yoy(loaded):
    c101 = db.get_object(loaded, "customer", "C-101")["attrs"]
    c104 = db.get_object(loaded, "customer", "C-104")["attrs"]
    assert (c101["booking_yoy"]["2026-05"], c101["booking_yoy"]["2026-06"]) == (-22.0, -33.7)
    assert (c104["booking_yoy"]["2026-05"], c104["booking_yoy"]["2026-06"]) == (-27.2, -26.1)
    assert c101["booking_yoy"]["2024-01"] is None  # NONE → null
    assert c101["revenue_share"] == 30.0


def test_no_incident_side_objects(loaded):
    for t in ("incident", "task", "event", "decision"):
        assert db.list_objects(loaded, t) == []
    assert db.find_links(loaded, rel="PART_OF") == []


def test_every_object_and_link_has_evidence(loaded):
    for o in db.list_objects(loaded):
        assert o["evidence"], o
        assert o["source"] == "원본"
    for l in db.find_links(loaded):
        assert l["evidence"], l
        assert l["source"] == "원본" and l["confirm"] == "확인"


def test_no_commit(loaded):
    assert loaded.in_transaction


def test_batch_without_claims_raises(conn):
    with pytest.raises(ValueError):
        loader.load_incident_scope(conn, "B-02-2602-02")


def test_latest_supply_batch():
    s = loader.latest_supply_batch("PL-02", ["LOT-B-2602-P"])
    assert "LOT-B-2606-1" in s["input_lot_ids"]
    assert s["qc_result"] == "합격"
    assert s["evidence"] == [f"{loader.BATCH_LOG}#{s['batch_id']}"]


def test_slack_capacity():
    s = loader.slack_capacity("PL-02", "2026-07-01")
    assert round(s["value"]) == 14814
    assert s["utilization_pct"] == 97.0
    assert s["months"] == ["2026-01", "2026-02", "2026-03", "2026-04", "2026-05", "2026-06"]
    assert s["evidence"]


def test_openable_batches():
    rows = {r["batch_id"]: r for r in loader.openable_batches()}
    assert rows["B-02-2602-01"]["defect_rate_produced"] == pytest.approx(11.9, abs=0.05)
    assert rows["B-02-2603-01"]["defect_rate_produced"] == pytest.approx(11.6, abs=0.05)
    assert "B-02-2602-02" not in rows
    assert all(r["claim_count"] >= 1 for r in rows.values())


def test_read_text_source():
    assert loader.read_text_source("05_external/news/ext_news_quality_incident.md").strip()
    with pytest.raises(ValueError):
        loader.read_text_source("../../CLAUDE.md")


def _snapshot(root: Path) -> dict:
    return {str(p): (p.stat().st_size, p.stat().st_mtime_ns) for p in root.rglob("*") if p.is_file()}


def test_raw_files_untouched(conn):
    before = _snapshot(loader.RAW_ROOT)
    loader.openable_batches()
    loader.load_incident_scope(conn, "B-02-2602-01")
    loader.latest_supply_batch("PL-02", ["LOT-B-2602-P"])
    loader.slack_capacity("PL-02", "2026-07-01")
    loader.read_text_source("01_corevia/quality/quality_policy_cv.md")
    assert _snapshot(loader.RAW_ROOT) == before
