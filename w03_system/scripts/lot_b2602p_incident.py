"""LOT-B-2602-P 사건 사실 — 2-findings/lot-b2602p-incident.md 의 근거 수치를 재현한다.
실행: python3 w03_system/scripts/lot_b2602p_incident.py  (프로젝트 루트에서)
원본은 읽기만 한다.
"""
import csv
import datetime as dt
import statistics
from pathlib import Path

RAW = Path(__file__).resolve().parents[2] / "01_참가자_배포용/04_원본데이터/01_corevia"
LOT = "LOT-B-2602-P"


def rd(rel):
    with open(RAW / rel, encoding="utf-8") as f:
        return list(csv.DictReader(f, delimiter="|"))


lots = [r for r in rd("procurement/material_lot_master_cv.csv") if r["lot_id"] == LOT]
cons = [r for r in rd("production/production_material_consumption_cv.csv") if r["lot_id"] == LOT]
batches = {r["batch_id"]: r for r in rd("production/prod_batch_log_cv.csv")}
sbl = rd("quality/shipment_batch_link_cv.csv")
claims = rd("quality/qc_claims_cv.csv")

print("로트:", lots)
print(f"투입 기록 {len(cons)}건, 투입량 합 {sum(float(r['consumed_qty']) for r in cons):,.1f} kg "
      f"(입고량 {lots[0]['received_qty']} kg), 투입일 {sorted(r['consumption_date'] for r in cons)}")

print("\n배치 | 생산일 | QC | 생산량 | SBL출하 | 첫출하 | 클레임 | 확정수량 | 불량률(생산) | 불량률(출하) | 출하처")
for b in sorted({r["batch_id"] for r in cons}):
    p = batches[b]
    s = [x for x in sbl if x["batch_id"] == b]
    shipped = sum(int(x["shipped_qty"]) for x in s)
    cs = [c for c in claims if c["batch_id"] == b]
    conf = sum(int(c["qty_affected"]) for c in cs if c["defect_confirmed"] == "True")
    cust = {}
    for x in s:
        cust[x["customer_id"]] = cust.get(x["customer_id"], 0) + int(x["shipped_qty"])
    print(f"{b} | {p['production_date']} | {p['qc_result']} | {int(p['produced_qty']):,} | {shipped:,} | "
          f"{min(x['ship_date'] for x in s)} | {len(cs)} | {conf:,} | {conf/int(p['produced_qty'])*100:.1f}% | "
          f"{conf/shipped*100:.1f}% | {dict(sorted(cust.items()))}")
    print(f"    클레임 고객: {sorted({c['customer_id'] for c in cs})}")

print("\n누적 확정 수량이 생산량의 10%를 넘은 날 (분모 = 생산 수량)")
for b in ("B-02-2602-01", "B-02-2603-01"):
    prod = int(batches[b]["produced_qty"])
    cum, crossed = 0, None
    cs = sorted((c for c in claims if c["batch_id"] == b and c["defect_confirmed"] == "True"),
                key=lambda c: c["claim_date"])
    for c in cs:
        cum += int(c["qty_affected"])
        if crossed is None and cum >= prod * 0.1:
            crossed = (c["claim_date"], cum)
    print(f"  {b}: 첫 확정 클레임 {cs[0]['claim_date']}, 10% 초과 {crossed}, 마지막 클레임 {cs[-1]['claim_date']}")

# 관찰 기간 근거: 클레임 접수일 - 해당 배치 첫 출하일 (전체 클레임)
first_ship, last_ship = {}, {}
for x in sbl:
    first_ship[x["batch_id"]] = min(first_ship.get(x["batch_id"], "9"), x["ship_date"])
    last_ship[x["batch_id"]] = max(last_ship.get(x["batch_id"], "0"), x["ship_date"])
D = dt.date.fromisoformat
lag = sorted((D(c["claim_date"]) - D(first_ship[c["batch_id"]])).days for c in claims if c["batch_id"] in first_ship)
print(f"\n클레임 - 첫 출하 경과일 (n={len(lag)}): 최소 {lag[0]}, 중앙값 {statistics.median(lag)}, "
      f"p95 {lag[int(len(lag)*.95)]}, 최대 {lag[-1]}")
for b in ("B-02-2602-02", "B-02-2602-03"):
    print(f"  {b}: 출하 {first_ship[b]}~{last_ship[b]}, 기준일까지 마지막 출하 후 {(D('2026-07-01') - D(last_ship[b])).days}일")

# 재공급 출고 조건 충족 가능성: 문제 로트 이후 M-B 로트, 다른 로트로 만든 PL-02 배치
print("\n2026년 M-B 로트:")
for r in rd("procurement/material_lot_master_cv.csv"):
    if r["material_id"] == "M-B" and r["receipt_date"] >= "2026-01":
        print(f"  {r['lot_id']} 입고 {r['receipt_date']} {r['inspection_result']}")
later = [v for v in batches.values() if v["product_id"] == "PL-02" and v["production_date"] > "2026-03-16"]
print(f"2026-03-17 이후 PL-02 배치 {len(later)}개, QC: {sorted({v['qc_result'] for v in later})}, "
      f"로트: {sorted({v['input_lot_ids'] for v in later})}")

# 시연 시나리오 수치: 고객별 회수량(SBL, 보류 배치 2개), 재공급 완료 예상 월 [가정 A-03·A-04]
import math
hot = ("B-02-2602-01", "B-02-2603-01")
recall = {}
for x in sbl:
    if x["batch_id"] in hot:
        recall[x["customer_id"]] = recall.get(x["customer_id"], 0) + int(x["shipped_qty"])
pl02 = [int(v["produced_qty"]) for v in batches.values()
        if v["product_id"] == "PL-02" and "2026-01" <= v["production_date"][:7] <= "2026-06"]
slack = sum(pl02) / 6 / 0.97 * 0.03  # A-04


def plan(order):
    cum, out = 0, []
    for c in order:
        cum += recall[c]
        m = math.ceil(cum / slack)  # 2026-07 = 1번째 달
        out.append(f"{c} {recall[c]:,} → {2026 + (6 + m - 1)//12}-{(6 + m - 1) % 12 + 1:02d}")
    return out


base = sorted(recall, key=lambda c: -recall[c])
print(f"\n여유 능력 월 {slack:,.0f} EA, 회수량 합 {sum(recall.values()):,} EA")
print("재공급 기본 순서:", plan(base))
print("C-101 우선:     ", plan(["C-101"] + [c for c in base if c != "C-101"]))
c105 = sum(int(c["qty_affected"]) for c in claims if c["batch_id"] in hot and c["customer_id"] == "C-105")
print(f"C-105 클레임 수량 합(최소 회수량, A-14): {c105:,} EA")

print("\n생산능력 (더마):", [r for r in rd("production/strat_capacity_cv.csv") if r["product_id"] == "PL-02"])
print("원료 M-B:", [r for r in rd("master/m_material_cv.csv") if r["material_id"] == "M-B"])
