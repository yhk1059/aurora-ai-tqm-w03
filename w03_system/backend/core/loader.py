"""원본 읽기와 사건 범위 적재.

기준: brain/3-design/architecture.md "데이터 흐름", business-model.md §3·§8-3·§8-4·§8-6(R4)·§8-8.
- 원본(01_참가자_배포용/04_원본데이터/)은 읽기 모드로만 연다. 복사본을 만들지 않는다.
- 사건 한 건에 필요한 객체·관계만 적재한다. 로트 입고량·투입량은 싣지 않는다(범위 규칙 ①).
- 사건·PART_OF·작업·이벤트, 클레임만 있는 고객의 SHIPPED_TO(R8)는 만들지 않는다 → 사건 열기 액션(step 4).
- 판정(불량률 기준 비교, 관찰·해제)을 하지 않는다 → core/rules.py.
- 커밋하지 않는다.

근거 참조 형식: "<원본 루트 기준 상대 경로>#<행 ID>" 문자열의 목록.
행 ID가 없는 파일(sales_customer_summary_cv, strat_capacity_cv)은 "#컬럼=값,..." 로 행을 가리킨다.
"""

from __future__ import annotations

import csv
import re
from collections import defaultdict
from pathlib import Path

from backend.core import db, ontology

# 이 파일: <root>/w03_system/backend/core/loader.py
PROJECT_ROOT = Path(__file__).resolve().parents[3]
RAW_ROOT = PROJECT_ROOT / "01_참가자_배포용" / "04_원본데이터"

LOT_MASTER = "01_corevia/procurement/material_lot_master_cv.csv"
CONSUMPTION = "01_corevia/production/production_material_consumption_cv.csv"
BATCH_LOG = "01_corevia/production/prod_batch_log_cv.csv"
CLAIMS = "01_corevia/quality/qc_claims_cv.csv"
SBL = "01_corevia/quality/shipment_batch_link_cv.csv"
CUSTOMERS = "01_corevia/master/m_customer_cv.csv"
CUSTOMER_SUMMARY = "01_corevia/sales/sales_customer_summary_cv.csv"
CAPACITY = "01_corevia/production/strat_capacity_cv.csv"
CAPEX_PLAN = "01_corevia/production/strat_capex_plan_cv.csv"

# 출처·상태 이름은 ontology 정의의 값만 쓴다
ORIGIN = "원본"
NORMAL = ontology.STATE_MACHINES["batch"]["initial"][0]  # "정상"
CONFIRMED, REJECTED = "확정", "기각"
QC_PASS = "합격"
SHIPPED_QTY_BASIS = ontology.QUANTITY_BASES[0]  # "출하기록 합"
NONE_CODE = "NONE"  # A05: 0과 다른 "해당 없음" 코드
assert ORIGIN in ontology.SOURCES
assert {CONFIRMED, REJECTED} <= set(ontology.STATE_MACHINES["claim"]["states"])


# ---------------------------------------------------------------------------
# 원본 읽기
# ---------------------------------------------------------------------------


def _raw_path(rel_path: str) -> Path:
    path = (RAW_ROOT / rel_path).resolve()
    if RAW_ROOT.resolve() not in path.parents:
        raise ValueError(f"원본 폴더 밖 경로: {rel_path}")
    return path


def _read_csv(rel_path: str) -> list[dict]:
    """UTF-8, 첫 행 헤더, 구분자 '|'."""
    with open(_raw_path(rel_path), "r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f, delimiter="|"))


def read_text_source(rel_path: str) -> str:
    """원본 문서(md) 읽기. rel_path는 원본 루트 기준 (예: '05_external/news/ext_news_quality_incident.md')."""
    with open(_raw_path(rel_path), "r", encoding="utf-8") as f:
        return f.read()


def _ref(rel_path: str, row_id: str) -> str:
    return f"{rel_path}#{row_id}"


def _lots_of(batch_row: dict) -> list[str]:
    return [x for x in re.split(r"[;,\s]+", batch_row["input_lot_ids"]) if x]


def _is_confirmed(claim_row: dict) -> bool:
    return claim_row["defect_confirmed"] == "True"


def _claim_state(claim_row: dict) -> str:
    """§4-6: 원본 status 그대로. 종결이면 defect_confirmed로 확정/기각."""
    status = claim_row["status"]
    if status == "종결":
        return CONFIRMED if _is_confirmed(claim_row) else REJECTED
    return status


def _num(value: str) -> float | None:
    return None if value in ("", NONE_CODE) else float(value)


# ---------------------------------------------------------------------------
# 사건이 없을 때: 열 수 있는 배치 목록
# ---------------------------------------------------------------------------


def openable_batches() -> list[dict]:
    """원본에서 클레임이 1건 이상 있는 배치. 불량률은 목록 표시용 숫자(생산 기준)이고 판정이 아니다."""
    claims_by_batch = defaultdict(list)
    for c in _read_csv(CLAIMS):
        claims_by_batch[c["batch_id"]].append(c)
    out = []
    for b in _read_csv(BATCH_LOG):
        cs = claims_by_batch.get(b["batch_id"])
        if not cs:
            continue
        produced = int(b["produced_qty"])
        confirmed_qty = sum(int(c["qty_affected"]) for c in cs if _is_confirmed(c))
        out.append({
            "batch_id": b["batch_id"],
            "product_id": b["product_id"],
            "production_date": b["production_date"],
            "produced_qty": produced,
            "qc_result": b["qc_result"],
            "claim_count": len(cs),
            "confirmed_qty": confirmed_qty,
            "defect_rate_produced": confirmed_qty / produced * 100 if produced else None,
            "evidence": [_ref(BATCH_LOG, b["batch_id"])],
        })
    return sorted(out, key=lambda r: r["batch_id"])


# ---------------------------------------------------------------------------
# 사건 범위 적재 (R4가 따라가는 길)
# ---------------------------------------------------------------------------


def load_incident_scope(conn, batch_id: str) -> dict:
    """고른 배치 → 클레임의 lot_id(기점 로트) → 기점 로트를 쓴 배치 → 그 배치의 클레임·출하 기록 → 고객."""
    all_claims = _read_csv(CLAIMS)
    start_claims = [c for c in all_claims if c["batch_id"] == batch_id]
    if not start_claims:
        raise ValueError(f"클레임이 없는 배치: {batch_id}")

    # 1. 기점 로트 = 클레임에 적힌 lot_id (배치의 다른 투입 로트는 따라가지 않는다)
    origin_lots = sorted({c["lot_id"] for c in start_claims if c["lot_id"] not in ("", NONE_CODE)})

    # 2. 기점 로트를 쓴 모든 배치 (투입 기록 또는 input_lot_ids)
    batch_rows = {b["batch_id"]: b for b in _read_csv(BATCH_LOG)}
    used_in = defaultdict(list)  # (lot, batch) → 근거 참조
    for r in _read_csv(CONSUMPTION):
        if r["lot_id"] in origin_lots and r["batch_id"] in batch_rows:
            used_in[(r["lot_id"], r["batch_id"])].append(_ref(CONSUMPTION, r["consumption_id"]))
    for b in batch_rows.values():
        for lot in _lots_of(b):
            if lot in origin_lots:
                used_in[(lot, b["batch_id"])].append(_ref(BATCH_LOG, b["batch_id"]))
    scope_batches = sorted({batch for _, batch in used_in} | {batch_id})

    # 3. 그 배치들의 클레임 전부, 출하 기록(SBL) 전부
    claims = sorted((c for c in all_claims if c["batch_id"] in scope_batches), key=lambda c: c["claim_id"])
    shipments = sorted((s for s in _read_csv(SBL) if s["batch_id"] in scope_batches),
                       key=lambda s: s["shipment_id"])

    # 4. 출하 기록과 클레임에 나오는 고객 전부
    customer_ids = sorted({s["customer_id"] for s in shipments} | {c["customer_id"] for c in claims})
    masters = {r["customer_id"]: r for r in _read_csv(CUSTOMERS)}
    yoy = defaultdict(dict)
    for r in _read_csv(CUSTOMER_SUMMARY):
        if r["customer_id"] in customer_ids:
            yoy[r["customer_id"]][r["period_ym"]] = _num(r["booking_yoy_pct"])

    # --- 객체 ---
    lot_rows = {r["lot_id"]: r for r in _read_csv(LOT_MASTER)}
    for lot in origin_lots:
        r = lot_rows[lot]
        db.put_object(conn, "material_lot", lot, {
            "material": r["material_id"],
            "vendor": r["supplier_id"],
            "received_date": r["receipt_date"],
            "inspection_date": r["inspection_date"],
            "inspection_result": r["inspection_result"],
        }, source=ORIGIN, evidence=[_ref(LOT_MASTER, lot)])

    for bid in scope_batches:
        b = batch_rows[bid]
        db.put_object(conn, "batch", bid, {
            "product": b["product_id"],
            "line": b["production_line"],
            "produced_date": b["production_date"],
            "produced_qty": int(b["produced_qty"]),
            "qc_result": b["qc_result"],
        }, state=NORMAL, source=ORIGIN, evidence=[_ref(BATCH_LOG, bid)])

    for c in claims:
        state = _claim_state(c)
        db.put_object(conn, "claim", c["claim_id"], {
            "received_date": c["claim_date"],
            "type": c["claim_type"],
            "defect_confirmed": _is_confirmed(c),
            "qty": int(c["qty_affected"]),
            "confirmed_date": c["claim_date"] if state == CONFIRMED else None,
            "source": ORIGIN,
        }, state=state, source=ORIGIN, evidence=[_ref(CLAIMS, c["claim_id"])])

    for s in shipments:
        db.put_object(conn, "shipment", s["shipment_id"], {
            "order_date": s["order_date"],
            "shipped_date": s["ship_date"],
            "qty": int(s["shipped_qty"]),
        }, source=ORIGIN, evidence=[_ref(SBL, s["shipment_id"])])

    for cid in customer_ids:
        m = masters.get(cid)
        db.put_object(conn, "customer", cid, {
            "revenue_share": _num(m["revenue_share_pct"]) if m else None,
            "booking_yoy": dict(sorted(yoy[cid].items())),
        }, source=ORIGIN, evidence=[_ref(CUSTOMERS, cid), f"{CUSTOMER_SUMMARY}#customer_id={cid}"])

    # --- 관계 (출처 원본, 확인 수준 확인) ---
    for (lot, bid), refs in sorted(used_in.items()):
        db.put_link(conn, "USED_IN", ("material_lot", lot), ("batch", bid), source=ORIGIN, evidence=refs)

    for c in claims:
        ref = [_ref(CLAIMS, c["claim_id"])]
        claim = ("claim", c["claim_id"])
        db.put_link(conn, "CLAIMED_ON", claim, ("batch", c["batch_id"]), source=ORIGIN, evidence=ref)
        db.put_link(conn, "CLAIMED_BY", claim, ("customer", c["customer_id"]), source=ORIGIN, evidence=ref)
        if c["lot_id"] in origin_lots:
            db.put_link(conn, "CLAIMED_LOT", claim, ("material_lot", c["lot_id"]), source=ORIGIN, evidence=ref)

    shipped = defaultdict(lambda: {"qty": 0, "refs": []})  # (batch, customer) → 합
    for s in shipments:
        ref = [_ref(SBL, s["shipment_id"])]
        ship = ("shipment", s["shipment_id"])
        db.put_link(conn, "SHIPMENT_OF", ship, ("batch", s["batch_id"]), source=ORIGIN, evidence=ref)
        db.put_link(conn, "SHIPMENT_FOR", ship, ("customer", s["customer_id"]), source=ORIGIN, evidence=ref)
        agg = shipped[(s["batch_id"], s["customer_id"])]
        agg["qty"] += int(s["shipped_qty"])
        agg["refs"] += ref

    # SHIPPED_TO: 배치×고객당 한 줄, SBL 출하 기록이 있는 고객만 (클레임만 있는 고객은 R8이 만든다)
    for (bid, cid), agg in sorted(shipped.items()):
        db.put_link(conn, "SHIPPED_TO", ("batch", bid), ("customer", cid), source=ORIGIN,
                    confirm=ontology.DEFAULT_CONFIRMATION, qty=agg["qty"], qty_basis=SHIPPED_QTY_BASIS,
                    evidence=agg["refs"])

    return {
        "origin_lots": origin_lots,
        "batches": scope_batches,
        "customers": customer_ids,
        "claim_count": len(claims),
    }


# ---------------------------------------------------------------------------
# 재공급 계산에 쓰는 원본 조회 (R11, A-04)
# ---------------------------------------------------------------------------


def latest_supply_batch(product_id: str, exclude_lots: list[str]) -> dict | None:
    """R11: 같은 제품, 투입 로트가 exclude_lots와 겹치지 않음, QC 합격 중 생산일이 가장 늦은 배치."""
    excluded = set(exclude_lots)
    candidates = [b for b in _read_csv(BATCH_LOG)
                  if b["product_id"] == product_id and b["qc_result"] == QC_PASS
                  and not excluded & set(_lots_of(b))]
    if not candidates:
        return None
    b = max(candidates, key=lambda r: (r["production_date"], r["batch_id"]))
    return {
        "batch_id": b["batch_id"],
        "product_id": b["product_id"],
        "production_date": b["production_date"],
        "produced_qty": int(b["produced_qty"]),
        "input_lot_ids": _lots_of(b),
        "qc_result": b["qc_result"],
        "row": dict(b),
        "evidence": [_ref(BATCH_LOG, b["batch_id"])],
    }


def _prev_months(as_of: str, n: int) -> list[str]:
    """as_of(YYYY-MM-DD)가 속한 달 직전 n개월의 'YYYY-MM' 목록 (오래된 순)."""
    y, m = int(as_of[:4]), int(as_of[5:7])
    out = []
    for _ in range(n):
        m -= 1
        if m == 0:
            y, m = y - 1, 12
        out.append(f"{y:04d}-{m:02d}")
    return out[::-1]


def slack_capacity(product_id: str, as_of: str) -> dict:
    """A-04: 직전 6개월 월평균 생산량 ÷ (가동률/100) × (1 − 가동률/100). capacity_qty는 쓰지 않는다."""
    months = _prev_months(as_of, 6)
    produced = [b for b in _read_csv(BATCH_LOG)
                if b["product_id"] == product_id and b["production_date"][:7] in months]
    monthly_avg = sum(int(b["produced_qty"]) for b in produced) / len(months)

    snapshots = [r for r in _read_csv(CAPACITY) if r["product_id"] == product_id and r["snapshot_date"] <= as_of]
    if not snapshots:
        raise ValueError(f"가동률 기록 없음: {product_id} (≤ {as_of})")
    cap = max(snapshots, key=lambda r: r["snapshot_date"])
    util = float(cap["utilization_pct"]) / 100
    return {
        "value": monthly_avg / util * (1 - util),
        "unit": "EA/월",
        "monthly_avg_produced": monthly_avg,
        "utilization_pct": float(cap["utilization_pct"]),
        "months": months,
        "source": "가정",
        "ref": "A-04",
        "evidence": [
            f"{CAPACITY}#plant_id={cap['plant_id']},line_id={cap['line_id']},"
            f"product_id={product_id},snapshot_date={cap['snapshot_date']}",
            *[_ref(BATCH_LOG, b["batch_id"]) for b in sorted(produced, key=lambda r: r["batch_id"])],
        ],
    }


def capacity_options() -> list[dict]:
    """R10-3: 원본 증설·전환안 (strat_capex_plan_cv) 그대로. 검토 작업의 근거로만 쓰고 계산에 쓰지 않는다.
    added_capacity_qty는 원본에 기간 단위가 적혀 있지 않다."""
    return [{
        "option_id": r["option_id"],
        "option_type": r["option_type"],
        "target_line": r["target_line"],
        "capex_krw": int(r["capex_krw"]),
        "lead_time_weeks": int(r["lead_time_weeks"]),
        "added_capacity_qty": int(r["added_capacity_qty"]),
        "note": r["note"],
        "evidence": [_ref(CAPEX_PLAN, r["option_id"])],
    } for r in _read_csv(CAPEX_PLAN)]
