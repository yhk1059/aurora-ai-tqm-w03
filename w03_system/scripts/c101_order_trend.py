"""C-101 수주 vs 출하 검증 — 2-findings/c101-order-vs-shipment.md 의 근거 수치를 재현한다.
실행: python3 w03_system/scripts/c101_order_trend.py  (프로젝트 루트에서)
원본은 읽기만 한다.
"""
import csv
import collections
import datetime as dt
import statistics
from pathlib import Path

RAW = Path(__file__).resolve().parents[2] / "01_참가자_배포용/04_원본데이터/01_corevia"


def rd(rel):
    with open(RAW / rel, encoding="utf-8") as f:
        return list(csv.DictReader(f, delimiter="|"))


orders = rd("sales/sales_orders_cv.csv")
ships = rd("sales/sales_shipments_cv.csv")
claims = rd("quality/qc_claims_cv.csv")
ar = rd("financials/fin_ar_aging_cv.csv")

# 1. 고객별 월 수주액·건수·건당 수량·단가 / 월 출하액 (2025-10 ~ 2026-06)
months = [f"2025-{m:02d}" for m in (10, 11, 12)] + [f"2026-{m:02d}" for m in range(1, 7)]
for cust in ("C-101", "C-102"):
    amt, qty, cnt, ship = (collections.defaultdict(float) for _ in range(4))
    for r in orders:
        if r["customer_id"] == cust:
            m = r["order_date"][:7]
            amt[m] += float(r["order_amount_krw"]); qty[m] += int(r["order_qty"]); cnt[m] += 1
    for r in ships:
        if r["customer_id"] == cust:
            ship[r["ship_date"][:7]] += float(r["revenue_krw"])
    print(f"\n{cust}  월 | 수주(억) | 건수 | 건당수량 | 단가 | 출하(억)")
    for m in months:
        print(f"  {m} | {amt[m]/1e8:6.1f} | {cnt[m]:4.0f} | {qty[m]/cnt[m]:6.0f} | {amt[m]/qty[m]:7.1f} | {ship[m]/1e8:6.1f}")

# 2. C-101 제품별 수주 (2026Q1 vs 2026Q2)
pq = collections.defaultdict(float)
for r in orders:
    if r["customer_id"] == "C-101" and r["order_date"] >= "2026-01":
        pq[(r["product_id"], "Q1" if r["order_date"] < "2026-04" else "Q2")] += float(r["order_amount_krw"])
print("\nC-101 제품별 수주 2026Q1→Q2 (억, 증감%)")
for p in sorted({k[0] for k in pq}):
    a, b = pq[(p, "Q1")], pq[(p, "Q2")]
    print(f"  {p}: {a/1e8:.1f} → {b/1e8:.1f} ({(b/a-1)*100:+.0f}%)")

# 3. 수주→출하 리드타임 (C-101)
od = {r["order_id"]: r["order_date"] for r in orders}
lag = sorted((dt.date.fromisoformat(r["ship_date"]) - dt.date.fromisoformat(od[r["order_id"]])).days
             for r in ships if r["customer_id"] == "C-101" and r["order_id"] in od)
print(f"\nC-101 수주→출하 리드타임: 중앙값 {statistics.median(lag)}일, p90 {lag[int(len(lag)*.9)]}일")

# 4. 확정 피부트러블 배치(B-02-2602-01, B-02-2603-01) 클레임의 고객 분포
hot = ("B-02-2602-01", "B-02-2603-01")
print("\n문제 배치 클레임 고객별:", dict(collections.Counter(r["customer_id"] for r in claims if r["batch_id"] in hot)))

# 5. 고객별 연체 잔액 (aging_days>0) 비중
d = collections.defaultdict(lambda: [0, 0, 0])
for r in ar:
    if r["customer_id"] == "NONE":
        continue
    o = int(r["outstanding_krw"]); d[r["customer_id"]][0] += int(r["amount_krw"])
    if int(r["aging_days"]) > 0: d[r["customer_id"]][1] += o
    if int(r["aging_days"]) > 90: d[r["customer_id"]][2] += o
print("\n고객 | 청구(억) | 연체(억) | 연체비중 | 90일초과(억)")
for c, (a, o, o90) in sorted(d.items()):
    print(f"  {c} | {a/1e8:5.0f} | {o/1e8:5.1f} | {o/a*100:4.1f}% | {o90/1e8:4.1f}")

# 6. C-101 주별 수주 (주 시작 월요일): 금액·건수·건당 수량 중앙값
def week(d):
    x = dt.date.fromisoformat(d)
    return (x - dt.timedelta(days=x.weekday())).isoformat()

wq = collections.defaultdict(list)
for r in orders:
    if r["customer_id"] == "C-101" and r["order_date"] >= "2026-02-23":
        wq[week(r["order_date"])].append(r)
print("\nC-101 주별 | 수주(억) | 건수 | 건당수량 중앙값")
for w in sorted(wq):
    rs = wq[w]
    print(f"  {w} | {sum(float(r['order_amount_krw']) for r in rs)/1e8:5.1f} | {len(rs):3d} | "
          f"{int(statistics.median(int(r['order_qty']) for r in rs))}")

# 7. 건당 수량 분위수 (p10/p50/p90) — C-101 vs C-102
for cust in ("C-101", "C-102"):
    mq = collections.defaultdict(list)
    for r in orders:
        if r["customer_id"] == cust and r["order_date"] >= "2026-01":
            mq[r["order_date"][:7]].append(int(r["order_qty"]))
    print(f"\n{cust} 건당 수량 p10/p50/p90")
    for m in sorted(mq):
        v = sorted(mq[m]); n = len(v)
        print(f"  {m} | {v[n//10]} / {v[n//2]} / {v[n*9//10]}")

# 8. C-101 제품 구성비 (수주액 기준)
mix = collections.defaultdict(lambda: collections.defaultdict(float))
for r in orders:
    if r["customer_id"] == "C-101" and r["order_date"] >= "2025-07":
        k = "2025H2" if r["order_date"] < "2026-01" else ("2026Q1" if r["order_date"] < "2026-04" else "2026Q2")
        mix[k][r["product_id"]] += float(r["order_amount_krw"])
print("\nC-101 제품 구성비")
for k in sorted(mix):
    t = sum(mix[k].values())
    print(f"  {k}: " + ", ".join(f"{p} {v/t*100:.0f}%" for p, v in sorted(mix[k].items())))

# 9. C-101 문제 배치 클레임 일자·수량 vs SBL 출하 수량
sbl = rd("quality/shipment_batch_link_cv.csv")
print("\nC-101 문제 배치: 클레임 일자(qty) / SBL 출하 EA")
for b in hot:
    cs = sorted((r["claim_date"], int(r["qty_affected"])) for r in claims
                if r["batch_id"] == b and r["customer_id"] == "C-101")
    sq = sum(int(x["shipped_qty"]) for x in sbl if x["batch_id"] == b and x["customer_id"] == "C-101")
    print(f"  {b}: {cs} 합 {sum(q for _, q in cs)} / 출하 {sq}")

# 10. 곁가지: 보류 배치 출하, 클레임 고객이 SBL 출하처에 없는 건수
batches = {r["batch_id"]: r for r in rd("production/prod_batch_log_cv.csv")}
print("\n보류 배치:")
for b, r in batches.items():
    if r["qc_result"] != "합격":
        s = [x for x in sbl if x["batch_id"] == b]
        print(f"  {b} 생산 {r['production_date']} {r['qc_result']} 로트 {r['input_lot_ids']} "
              f"출하 {sum(int(x['shipped_qty']) for x in s)} EA, 첫 출하 {min(x['ship_date'] for x in s)}")
rec = collections.defaultdict(set)
for x in sbl:
    rec[x["batch_id"]].add(x["customer_id"])
miss = sum(1 for c in claims if c["customer_id"] not in rec[c["batch_id"]])
print(f"클레임 고객이 해당 배치 SBL 출하처에 없음: {miss} / {len(claims)}건")

# 11. 미출하 수주로 본 7~8월 출하 예상 (주문일 + 60일 = 예상 출하월), 상반기 월평균 출하 대비
shipped_ids = {r["order_id"] for r in ships}
print("\n미출하 수주 기준 예상 출하(억) / 상반기 월평균 출하 대비")
for cust in ("C-101", "C-102"):
    exp = collections.defaultdict(float)
    for r in orders:
        if r["customer_id"] == cust and r["order_id"] not in shipped_ids and r["order_date"] >= "2026-03":
            m = (dt.date.fromisoformat(r["order_date"]) + dt.timedelta(days=60)).isoformat()[:7]
            exp[m] += float(r["order_amount_krw"])
    avg = sum(float(r["revenue_krw"]) for r in ships
              if r["customer_id"] == cust and "2026-01" <= r["ship_date"][:7] <= "2026-06") / 6
    print(f"  {cust} 월평균 {avg/1e8:.1f} | " +
          ", ".join(f"{m} {v/1e8:.1f} ({v/avg*100:.0f}%)" for m, v in sorted(exp.items()) if m >= "2026-07"))
