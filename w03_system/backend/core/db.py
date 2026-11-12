"""SQLite 저장. 테이블 4개(objects, links, action_log, ai_log)뿐이다.

기준: brain/3-design/architecture.md "상태 관리", business-model.md §8-1·§8-4.
- 커밋하지 않는다. 트랜잭션의 시작·커밋·롤백은 호출하는 쪽(액션 실행기)이 한다.
- 줄 ID·순번은 1부터 순서대로 늘어난다(시각·난수 없음, 재현성).
- 규칙 판단을 넣지 않는다. 이름(타입·관계·출처·확인 수준·상태)이 ontology.py에 있는지만 확인한다.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from backend.core import ontology

SCHEMA = """
CREATE TABLE IF NOT EXISTS objects (
    type      TEXT NOT NULL,
    id        TEXT NOT NULL,
    attrs     TEXT NOT NULL,
    state     TEXT,
    source    TEXT NOT NULL,
    evidence  TEXT,
    PRIMARY KEY (type, id)
);
CREATE TABLE IF NOT EXISTS links (
    link_id       INTEGER PRIMARY KEY,
    rel           TEXT NOT NULL,
    src_type      TEXT NOT NULL,
    src_id        TEXT NOT NULL,
    dst_type      TEXT NOT NULL,
    dst_id        TEXT NOT NULL,
    attrs         TEXT NOT NULL,
    source        TEXT NOT NULL,
    confirm       TEXT NOT NULL,
    qty           REAL,
    qty_basis     TEXT,
    evidence      TEXT,
    applied_date  TEXT,
    recorded_date TEXT
);
CREATE TABLE IF NOT EXISTS action_log (
    seq          INTEGER PRIMARY KEY,
    action       TEXT NOT NULL,
    actor        TEXT NOT NULL,
    applied_date TEXT,
    inputs       TEXT NOT NULL,
    changes      TEXT NOT NULL,
    cause        TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ai_log (
    seq        INTEGER PRIMARY KEY,
    task       TEXT NOT NULL,
    model      TEXT NOT NULL,
    inputs     TEXT NOT NULL,
    output     TEXT NOT NULL,
    action_seq INTEGER
);
"""

TABLES = ("objects", "links", "action_log", "ai_log")

# JSON으로 저장하는 컬럼
_JSON_COLUMNS = {"attrs", "evidence", "inputs", "changes", "cause", "output"}

# update_link로 바꿀 수 있는 컬럼
_LINK_FIELDS = {"source", "confirm", "qty", "qty_basis", "attrs", "evidence", "applied_date", "recorded_date"}


def _dumps(value) -> str | None:
    return None if value is None else json.dumps(value, ensure_ascii=False)


def _row(row: sqlite3.Row | None) -> dict | None:
    if row is None:
        return None
    out = dict(row)
    for key in _JSON_COLUMNS & out.keys():
        if out[key] is not None:
            out[key] = json.loads(out[key])
    return out


def _check_source(source: str) -> None:
    if source not in ontology.SOURCES:
        raise ValueError(f"정의되지 않은 출처: {source}")


def _check_state(type_: str, state: str | None) -> None:
    if state is None:
        return
    machine = ontology.OBJECT_TYPES[type_]["state"]
    if machine is None:
        raise ValueError(f"{type_}에는 상태가 없다: {state}")
    if state not in ontology.STATE_MACHINES[machine["kind"]]["states"]:
        raise ValueError(f"{type_}의 상태가 아니다: {state}")


def connect(path) -> sqlite3.Connection:
    """파일 경로 또는 ':memory:'. 테이블이 없으면 만든다. 상위 폴더가 없으면 만든다."""
    if str(path) != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    # FastAPI는 연결 생성·라우트·정리를 서로 다른 스레드에서 돌릴 수 있다. 연결은 요청 하나만 쓴다.
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def reset(conn: sqlite3.Connection) -> None:
    """네 테이블을 모두 비운다. INTEGER PRIMARY KEY(AUTOINCREMENT 아님)라 번호도 1부터 다시 시작한다."""
    for table in TABLES:
        conn.execute(f"DELETE FROM {table}")


# ---------------------------------------------------------------------------
# objects
# ---------------------------------------------------------------------------


def put_object(conn, type, id, attrs, *, state=None, source, evidence=None) -> None:
    if type not in ontology.OBJECT_TYPES:
        raise ValueError(f"정의되지 않은 객체 타입: {type}")
    _check_source(source)
    _check_state(type, state)
    conn.execute(
        "INSERT INTO objects (type, id, attrs, state, source, evidence) VALUES (?, ?, ?, ?, ?, ?)",
        (type, id, _dumps(attrs or {}), state, source, _dumps(evidence)),
    )


def get_object(conn, type, id) -> dict | None:
    return _row(conn.execute("SELECT * FROM objects WHERE type = ? AND id = ?", (type, id)).fetchone())


def list_objects(conn, type=None) -> list[dict]:
    if type is None:
        rows = conn.execute("SELECT * FROM objects ORDER BY rowid").fetchall()
    else:
        rows = conn.execute("SELECT * FROM objects WHERE type = ? ORDER BY rowid", (type,)).fetchall()
    return [_row(r) for r in rows]


def update_object(conn, type, id, *, state=None, attrs=None) -> None:
    """state를 바꾸고 attrs를 기존 속성에 병합한다."""
    current = get_object(conn, type, id)
    if current is None:
        raise KeyError(f"객체 없음: {type} {id}")
    if state is not None:
        _check_state(type, state)
        conn.execute("UPDATE objects SET state = ? WHERE type = ? AND id = ?", (state, type, id))
    if attrs:
        merged = {**current["attrs"], **attrs}
        conn.execute("UPDATE objects SET attrs = ? WHERE type = ? AND id = ?", (_dumps(merged), type, id))


# ---------------------------------------------------------------------------
# links
# ---------------------------------------------------------------------------


def put_link(conn, rel, src, dst, *, source, confirm=ontology.DEFAULT_CONFIRMATION, qty=None, qty_basis=None,
             attrs=None, evidence=None, applied_date=None, recorded_date=None) -> int:
    """src/dst = (타입, ID). 새 줄 ID를 돌려준다."""
    rdef = ontology.RELATIONS.get(rel)
    if rdef is None:
        raise ValueError(f"정의되지 않은 관계: {rel}")
    if src[0] not in rdef["from"]:
        raise ValueError(f"{rel}의 출발 타입이 아니다: {src[0]}")
    if dst[0] not in rdef["to"] and dst[0] not in rdef["to_links"]:
        raise ValueError(f"{rel}의 도착 타입이 아니다: {dst[0]}")
    _check_source(source)
    if confirm not in ontology.CONFIRMATION_LEVELS:
        raise ValueError(f"정의되지 않은 확인 수준: {confirm}")
    if not rdef["uses_confirmation"] and confirm != ontology.DEFAULT_CONFIRMATION:
        raise ValueError(f"{rel}은 확인 수준을 쓰지 않는다")
    if qty_basis is not None and qty_basis not in ontology.QUANTITY_BASES:
        raise ValueError(f"정의되지 않은 수량 근거: {qty_basis}")
    if not rdef["uses_quantity"] and (qty is not None or qty_basis is not None):
        raise ValueError(f"{rel}은 수량을 쓰지 않는다")
    cur = conn.execute(
        "INSERT INTO links (rel, src_type, src_id, dst_type, dst_id, attrs, source, confirm, qty, qty_basis,"
        " evidence, applied_date, recorded_date) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (rel, src[0], src[1], dst[0], dst[1], _dumps(attrs or {}), source, confirm, qty, qty_basis,
         _dumps(evidence), applied_date, recorded_date),
    )
    return cur.lastrowid


def get_link(conn, link_id) -> dict | None:
    return _row(conn.execute("SELECT * FROM links WHERE link_id = ?", (link_id,)).fetchone())


def find_links(conn, rel=None, src=None, dst=None) -> list[dict]:
    """src/dst = (타입, ID). 주지 않은 조건은 거르지 않는다."""
    where, args = [], []
    if rel is not None:
        where.append("rel = ?")
        args.append(rel)
    if src is not None:
        where += ["src_type = ?", "src_id = ?"]
        args += list(src)
    if dst is not None:
        where += ["dst_type = ?", "dst_id = ?"]
        args += list(dst)
    sql = "SELECT * FROM links" + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY link_id"
    return [_row(r) for r in conn.execute(sql, args).fetchall()]


def update_link(conn, link_id, **fields) -> None:
    unknown = set(fields) - _LINK_FIELDS
    if unknown:
        raise ValueError(f"바꿀 수 없는 관계 필드: {sorted(unknown)}")
    if "source" in fields:
        _check_source(fields["source"])
    if "confirm" in fields and fields["confirm"] not in ontology.CONFIRMATION_LEVELS:
        raise ValueError(f"정의되지 않은 확인 수준: {fields['confirm']}")
    if fields.get("qty_basis") is not None and fields["qty_basis"] not in ontology.QUANTITY_BASES:
        raise ValueError(f"정의되지 않은 수량 근거: {fields['qty_basis']}")
    if get_link(conn, link_id) is None:
        raise KeyError(f"관계 줄 없음: {link_id}")
    for key, value in fields.items():
        stored = _dumps(value) if key in _JSON_COLUMNS else value
        conn.execute(f"UPDATE links SET {key} = ? WHERE link_id = ?", (stored, link_id))


# ---------------------------------------------------------------------------
# action_log / ai_log
# ---------------------------------------------------------------------------


def append_action_log(conn, *, action, actor, applied_date, inputs, changes, cause) -> int:
    """changes = [{대상, 필드, 이전, 이후}], cause = {규칙·이벤트·결정·앞선 순번}. 순번을 돌려준다."""
    cur = conn.execute(
        "INSERT INTO action_log (action, actor, applied_date, inputs, changes, cause) VALUES (?, ?, ?, ?, ?, ?)",
        (action, actor, applied_date, _dumps(inputs or {}), _dumps(changes or []), _dumps(cause or {})),
    )
    return cur.lastrowid


def list_action_log(conn) -> list[dict]:
    return [_row(r) for r in conn.execute("SELECT * FROM action_log ORDER BY seq").fetchall()]


def append_ai_log(conn, *, task, model, inputs, output, action_seq=None) -> int:
    cur = conn.execute(
        "INSERT INTO ai_log (task, model, inputs, output, action_seq) VALUES (?, ?, ?, ?, ?)",
        (task, model, _dumps(inputs), _dumps(output), action_seq),
    )
    return cur.lastrowid


def list_ai_log(conn) -> list[dict]:
    return [_row(r) for r in conn.execute("SELECT * FROM ai_log ORDER BY seq").fetchall()]
