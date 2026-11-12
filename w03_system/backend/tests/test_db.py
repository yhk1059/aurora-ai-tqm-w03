"""core/db.py: 테이블 4개, 이름 검사, 순번 재현성, 커밋하지 않음."""

import pytest

from backend.core import db


def test_only_four_tables(conn):
    names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert names == {"objects", "links", "action_log", "ai_log"}


def test_connect_creates_parent_dir(tmp_path):
    path = tmp_path / "a" / "b" / "w03.sqlite"
    c = db.connect(path)
    c.close()
    assert path.is_file()


def test_object_put_get_update_merge(conn):
    db.put_object(conn, "batch", "B-1", {"produced_qty": 10, "qc_result": "합격"}, state="정상",
                  source="원본", evidence=["f.csv#B-1"])
    o = db.get_object(conn, "batch", "B-1")
    assert o["attrs"] == {"produced_qty": 10, "qc_result": "합격"}
    assert o["state"] == "정상" and o["source"] == "원본" and o["evidence"] == ["f.csv#B-1"]
    db.update_object(conn, "batch", "B-1", state="관찰", attrs={"note": "x"})
    o = db.get_object(conn, "batch", "B-1")
    assert o["state"] == "관찰"
    assert o["attrs"] == {"produced_qty": 10, "qc_result": "합격", "note": "x"}
    assert db.get_object(conn, "batch", "없음") is None
    assert [x["id"] for x in db.list_objects(conn, "batch")] == ["B-1"]
    assert db.list_objects(conn, "claim") == []


def test_names_must_be_in_ontology(conn):
    with pytest.raises(ValueError):
        db.put_object(conn, "unknown_type", "X", {}, source="원본")
    with pytest.raises(ValueError):
        db.put_object(conn, "batch", "X", {}, source="추측")
    with pytest.raises(ValueError):
        db.put_object(conn, "batch", "X", {}, state="없는상태", source="원본")
    with pytest.raises(ValueError):
        db.put_link(conn, "NOT_A_REL", ("batch", "A"), ("customer", "C"), source="원본")
    with pytest.raises(ValueError):
        db.put_link(conn, "SHIPPED_TO", ("customer", "C"), ("batch", "A"), source="원본")
    with pytest.raises(ValueError):
        db.put_link(conn, "SHIPPED_TO", ("batch", "A"), ("customer", "C"), source="원본", confirm="불완전")
    with pytest.raises(ValueError):
        db.put_link(conn, "USED_IN", ("material_lot", "L"), ("batch", "A"), source="원본", confirm="미확인")


def test_link_ids_sequential_and_find_update(conn):
    a = db.put_link(conn, "SHIPPED_TO", ("batch", "A"), ("customer", "C1"), source="원본",
                    qty=5, qty_basis="출하기록 합", evidence=["s#1"])
    b = db.put_link(conn, "SHIPPED_TO", ("batch", "A"), ("customer", "C2"), source="도출", confirm="미확인")
    c = db.put_link(conn, "USED_IN", ("material_lot", "L"), ("batch", "A"), source="원본")
    assert (a, b, c) == (1, 2, 3)
    assert len(db.find_links(conn, rel="SHIPPED_TO")) == 2
    assert len(db.find_links(conn, src=("batch", "A"))) == 2
    assert [x["link_id"] for x in db.find_links(conn, dst=("batch", "A"))] == [3]
    db.update_link(conn, b, confirm="확인요청중", qty=7, qty_basis="클레임 합(하한)", evidence=["T-02"])
    row = db.find_links(conn, dst=("customer", "C2"))[0]
    assert (row["confirm"], row["qty"], row["qty_basis"], row["evidence"]) == ("확인요청중", 7, "클레임 합(하한)", ["T-02"])
    with pytest.raises(ValueError):
        db.update_link(conn, b, rel="USED_IN")


def test_logs_and_reset_restart_numbering(conn):
    s1 = db.append_action_log(conn, action="open_incident", actor="quality_owner", applied_date="2026-07-01",
                              inputs={"batch_id": "B"}, changes=[{"target": "batch:B", "field": "state",
                                                                   "before": "정상", "after": "관찰"}],
                              cause={"rules": ["R4"]})
    s2 = db.append_ai_log(conn, task="agenda_summary", model="m", inputs={"a": 1}, output={"text": "요약"},
                          action_seq=s1)
    assert (s1, s2) == (1, 1)
    log = db.list_action_log(conn)
    assert log[0]["changes"][0]["after"] == "관찰" and log[0]["cause"] == {"rules": ["R4"]}
    assert db.list_ai_log(conn)[0]["output"] == {"text": "요약"}

    db.put_object(conn, "batch", "B", {}, source="원본")
    db.put_link(conn, "USED_IN", ("material_lot", "L"), ("batch", "B"), source="원본")
    db.reset(conn)
    for table in ("objects", "links", "action_log", "ai_log"):
        assert conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
    assert db.put_link(conn, "USED_IN", ("material_lot", "L"), ("batch", "B"), source="원본") == 1
    assert db.append_action_log(conn, action="reset", actor="scm", applied_date=None,
                                inputs={}, changes=[], cause={}) == 1


def test_db_does_not_commit(tmp_path):
    path = tmp_path / "w.sqlite"
    c = db.connect(path)
    db.put_object(c, "batch", "B", {}, source="원본")
    db.put_link(c, "USED_IN", ("material_lot", "L"), ("batch", "B"), source="원본")
    db.append_action_log(c, action="a", actor="x", applied_date=None, inputs={}, changes=[], cause={})
    assert c.in_transaction
    c.rollback()
    assert db.list_objects(c) == [] and db.find_links(c) == [] and db.list_action_log(c) == []
    c.close()
