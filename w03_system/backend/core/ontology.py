"""W03 온톨로지 선언형 정의.

기준 문서: brain/3-design/business-model.md (§2 객체, §4 상태, §5 규칙, §8 온톨로지 4칸),
brain/3-design/assumptions.md (A-01 ~ A-17).

이 파일은 정의와 그것을 읽는 조회 함수만 가진다. 계산(core/rules.py), 실행(core/actions.py),
DB·네트워크·파일 접근은 여기에 두지 않는다. 상태·역할·출처·허용 결과의 값은 문서의 한국어 문자열
그대로이고, 화면이 그대로 보여준다. 액션·역할에만 영문 key를 둔다(URL·요청 본문용).
"""

from __future__ import annotations

import copy

# ---------------------------------------------------------------------------
# 공통 값
# ---------------------------------------------------------------------------

# 출처 (§8-4 관계 속성 "출처", 완료 조건 5)
SOURCES = ["원본", "도출", "가정", "모의", "시스템"]

# SHIPPED_TO 확인 수준 (§4-2). SHIPPED_TO 외 관계는 항상 "확인"
CONFIRMATION_LEVELS = ["확인", "미확인", "확인요청중", "회신확인", "영향없음"]
DEFAULT_CONFIRMATION = "확인"

# 회수·재공급 대상이 되는 확인 수준 (§4-2)
CONFIRMED_LEVELS = ["확인", "회신확인"]

# SHIPPED_TO 수량 근거 (§8-4)
QUANTITY_BASES = ["출하기록 합", "클레임 합(하한)", "없음"]

# 액션을 실행하는 역할 (§6, §8-5)
ROLES = {
    "quality_owner": {"name": "품질 담당자", "basis": "decisions 스코핑 ① 주 사용자"},
    "quality_committee": {"name": "품질위원회", "basis": "[원본] approval_authority_policy (품질 회수 = 품질위원회)"},
    "scm": {"name": "SCM", "basis": "[가정 A-01] 재공급 결정권자 = SCM"},
}

# 작업의 담당 부서 (회신만 하는 부서 포함, §6·§8-5 회신 반영 표)
DEPARTMENTS = ["품질", "생산", "물류", "영업", "영업 임원", "SCM"]

# 이벤트 = 밖에서 온 신호만 (§8-2)
EVENT_TYPES = ["클레임 접수", "보도", "회신"]

# 결정 (§2)
DECISION_TYPES = ["회수 범위", "재공급 순서"]
COMMITTEE_RESULTS = ["승인", "조건부", "거절"]
PLAN_DECISION_RESULTS = ["승인", "거절"]

# AI 회신 분류에서 맞는 허용 결과가 없을 때의 값. 허용 결과가 아니며 회신 반영 액션이 받지 않는다 (§8-5)
AI_UNINTERPRETABLE = "해석 불가"

# 작업 기한 (§4-3)
TASK_DEADLINE = {
    "value": 7,
    "unit": "일",
    "description": "작업 생성 적용일 + 7일. '확인 불가' 회신이면 회신 적용일 + 7일로 연장",
    "source": "가정",
    "ref": "A-17",
}

# ---------------------------------------------------------------------------
# 객체 타입 11개 (§2, §8-2, §8-3)
# ---------------------------------------------------------------------------
# stored: 저장 속성 / derived: 파생 속성(rules = 계산하는 규칙) / state: 상태 속성과 전이표 종류


def _a(key: str, name: str) -> dict:
    return {"key": key, "name": name}


def _d(key: str, name: str, rules: list[str], basis: str | None = None) -> dict:
    out = {"key": key, "name": name, "rules": rules}
    if basis:
        out["basis"] = basis
    return out


OBJECT_TYPES = {
    "incident": {
        "name": "사건",
        "description": "품질 문제 한 건. 이번 범위는 LOT-B-2602-P 1건",
        "default_source": ["시스템"],
        "stored": [_a("id", "ID"), _a("owner", "담당자"), _a("opened_date", "개시일"),
                   _a("current_date", "현재 적용일")],
        "derived": [_d("incident_status", "사건 상태", [], "§4-5 (배치·계획 상태에서 도출, 저장하지 않음)")],
        "state": None,
    },
    "material_lot": {
        "name": "원료 로트",
        "description": "원료 입고 단위. 입고량·투입량은 싣지 않는다 (원본 한계, 범위 규칙 ①)",
        "default_source": ["원본"],
        "stored": [_a("id", "ID"), _a("material", "원료"), _a("vendor", "공급사"),
                   _a("received_date", "입고일"), _a("inspection_date", "검사일"),
                   _a("inspection_result", "입고검사 결과")],
        "derived": [_d("used_after_hold", "보류 후 투입 여부", ["R5-1"])],
        "state": None,
    },
    "batch": {
        "name": "배치",
        "description": "생산 단위 = 회수 판단 단위",
        "default_source": ["원본"],
        "stored": [_a("id", "ID"), _a("product", "제품"), _a("line", "라인"),
                   _a("produced_date", "생산일"), _a("produced_qty", "생산 수량"),
                   _a("qc_result", "QC 결과"), _a("judgment_status", "판정 상태")],
        "derived": [
            _d("confirmed_defect_qty", "확정 불량 수량", ["R1"]),
            _d("defect_rate_produced", "불량률 생산 기준", ["R1"]),
            _d("defect_rate_shipped", "불량률 출하 기준", ["R1"]),
            _d("over_threshold", "기준 초과 여부", ["R2"]),
            _d("defect_rate_if_confirmed", "확정 시 불량률", ["R7-1"]),
            _d("over_threshold_date", "기준 초과일", ["R1", "R2"]),
            _d("days_unsubmitted", "미상신 경과일", ["R2"], "§4-5 현재 적용일 기준"),
            _d("last_shipped_date", "마지막 출하일", ["R6"]),
            _d("release_due_date", "관찰 해제 예정일", ["R6", "R6-1", "R6-2"]),
        ],
        "state": {"attribute": "judgment_status", "kind": "batch"},
    },
    "claim": {
        "name": "클레임",
        "description": "고객 품질 신고. 원본 qc_claims_cv + 모의 신규 입력",
        "default_source": ["원본", "모의"],
        "stored": [_a("id", "ID"), _a("received_date", "접수일"), _a("type", "유형"),
                   _a("status", "상태"), _a("defect_confirmed", "불량 확정 여부"),
                   _a("qty", "수량"), _a("source", "출처")],
        "derived": [],
        "state": {"attribute": "status", "kind": "claim"},
    },
    "shipment": {
        "name": "출하 기록",
        "description": "배치→고객 출하 (SBL 행 그대로, SHIPPED_TO 한 줄의 근거). 원본은 불완전",
        "default_source": ["원본"],
        "stored": [_a("id", "ID"), _a("order_date", "주문일"), _a("shipped_date", "출하일"),
                   _a("qty", "수량")],
        "derived": [],
        "state": None,
    },
    "customer": {
        "name": "고객",
        "description": "B2B 고객",
        "default_source": ["원본"],
        "stored": [_a("id", "ID"), _a("revenue_share", "매출 비중"),
                   _a("booking_yoy", "월별 수주 전년비")],
        "derived": [_d("order_drop_signal", "수주 급감 신호", ["R10-1"])],
        "state": None,
    },
    "event": {
        "name": "이벤트",
        "description": "사건에 들어오는 밖의 신호 (클레임 접수, 보도, 회신 원문). 발생일과 적용일을 따로 기록",
        "default_source": ["원본", "모의"],
        "stored": [_a("id", "ID"), _a("type", "유형"), _a("occurred_date", "발생일"),
                   _a("applied_date", "적용일"), _a("content", "내용"), _a("source", "출처")],
        "derived": [],
        "state": None,
    },
    "decision": {
        "name": "결정",
        "description": "결정권자가 내린 결정 (결정 1 회수 범위, 결정 2 재공급 순서)",
        "default_source": ["모의"],
        "stored": [_a("id", "ID"), _a("type", "유형"), _a("decider", "결정권자"),
                   _a("result", "결과"), _a("reason", "사유"), _a("applied_date", "적용일")],
        "derived": [],
        "state": None,
    },
    "task": {
        "name": "작업",
        "description": "결정·규칙이 만든 후속 작업",
        "default_source": ["시스템"],
        "stored": [_a("id", "ID"), _a("type", "유형"), _a("department", "담당 부서"),
                   _a("status", "상태"), _a("due_date", "기한"), _a("reply", "회신 내용")],
        "derived": [],
        "state": {"attribute": "status", "kind": "task"},
    },
    "resupply_plan": {
        "name": "재공급 계획",
        "description": "재공급 계획 한 판(버전 단위)",
        "default_source": ["시스템", "가정"],
        "stored": [_a("id", "ID"), _a("version", "버전"), _a("status", "상태"),
                   _a("release_condition", "출고 조건"), _a("recalc_cause", "재계산 원인")],
        "derived": [_d("release_condition_met", "출고 조건 충족 여부", ["R11"])],
        "state": {"attribute": "status", "kind": "plan"},
    },
    "resupply_plan_line": {
        "name": "재공급 계획 줄",
        "description": "계획 안의 고객별 한 줄",
        "default_source": ["시스템", "가정"],
        "stored": [_a("rank", "순위"), _a("qty", "수량"), _a("expected_month", "예상 월")],
        "derived": [_d("delay_months", "이전 버전 대비 지연 개월", ["R10"])],
        "state": None,
    },
}

# ---------------------------------------------------------------------------
# 관계 17개 (§8-4)
# ---------------------------------------------------------------------------
# from/to = 객체 타입 key 목록. to_links = 관계 한 줄을 대상으로 가리킬 수 있는 관계 유형 (TARGETS → SHIPPED_TO)
# uses_confirmation / uses_quantity = 확인 수준·수량을 쓰는 관계 (SHIPPED_TO만)

# 관계 한 줄이 가지는 속성 (§8-4)
LINK_ATTRIBUTES = [
    _a("source", "출처"),
    _a("confirmation", "확인 수준"),
    _a("qty", "수량"),
    _a("qty_basis", "수량 근거"),
    _a("evidence_ref", "근거 참조"),
    _a("applied_date", "적용일"),
    _a("recorded_date", "기록일"),
]


def _rel(frm, to, sources, basis, *, to_links=None, confirmation=False, quantity=False, attributes=None):
    return {
        "from": frm,
        "to": to,
        "to_links": to_links or [],
        "default_source": sources,
        "uses_confirmation": confirmation,
        "uses_quantity": quantity,
        "attributes": attributes or [],
        "basis": basis,
    }


RELATIONS = {
    "USED_IN": _rel(["material_lot"], ["batch"], ["원본"],
                    "production_material_consumption_cv / input_lot_ids (물량은 쓰지 않음)"),
    "CLAIMED_ON": _rel(["claim"], ["batch"], ["원본", "모의"], "qc_claims_cv.batch_id"),
    "CLAIMED_BY": _rel(["claim"], ["customer"], ["원본", "모의"], "qc_claims_cv.customer_id"),
    "CLAIMED_LOT": _rel(["claim"], ["material_lot"], ["원본", "모의"],
                        "qc_claims_cv.lot_id — R4의 기점 로트"),
    "SHIPPED_TO": _rel(["batch"], ["customer"], ["원본", "도출", "모의"],
                       "배치×고객당 한 줄 = 고객 영향. SBL 출하 기록 집계, 클레임만 있음(R8), 또는 물류 회신",
                       confirmation=True, quantity=True),
    "SHIPMENT_OF": _rel(["shipment"], ["batch"], ["원본"],
                        "shipment_batch_link_cv.batch_id — SHIPPED_TO 한 줄의 근거 행"),
    "SHIPMENT_FOR": _rel(["shipment"], ["customer"], ["원본"],
                         "shipment_batch_link_cv.customer_id — SHIPPED_TO 한 줄의 근거 행"),
    "PART_OF": _rel(["batch"], ["incident"], ["시스템"], "규칙 R4(로트 공유) 또는 클레임",
                    attributes=[_a("reason", "묶인 이유")]),
    "TRIGGERS": _rel(["event"], ["incident"], ["원본", "모의"], "이벤트 입력"),
    "DECIDES": _rel(["decision"], ["batch", "resupply_plan"], ["모의"],
                    "승인 입력. 결정 1 → 배치, 결정 2 → 재공급 계획 버전"),
    "CREATES": _rel(["decision"], ["task"], ["시스템"],
                    "결정·규칙 → 작업. 규칙이 만든 작업은 근거 참조에 규칙 ID를 남긴다"),
    "TARGETS": _rel(["task"], ["batch", "customer", "resupply_plan"], ["시스템"],
                    "작업 생성 시. 회신이 무엇을 바꿀지 정한다", to_links=["SHIPPED_TO"]),
    "ANSWERS": _rel(["event"], ["task"], ["모의"], "회신 입력"),
    "PLAN_FOR": _rel(["resupply_plan"], ["incident"], ["시스템"], "계획 생성 시"),
    "LINE_OF": _rel(["resupply_plan_line"], ["resupply_plan"], ["시스템"], "계획 생성 시"),
    "RESUPPLIES": _rel(["resupply_plan_line"], ["customer"], ["시스템", "가정"],
                       "규칙 R10 [가정 A-03·A-04]"),
    "SOURCED_FROM": _rel(["resupply_plan"], ["batch"], ["원본"], "규칙 R11 (공급 배치의 로트·QC)"),
}

# ---------------------------------------------------------------------------
# 상태 전이표 5종 (§4-1 ~ §4-6)
# ---------------------------------------------------------------------------
# initial = 객체(관계)가 처음 생길 때 가질 수 있는 상태. 나머지 상태는 transitions로만 도달한다


def _t(frm: str, to: str, by: str) -> dict:
    return {"from": frm, "to": to, "by": by}


STATE_MACHINES = {
    "batch": {
        "name": "배치 판정 상태",
        "states": ["정상", "관찰", "관찰해제", "기준초과(미상신)", "상신중", "회수진행",
                   "부분회수", "조사계속", "재상신 후보"],
        "initial": ["정상"],
        "transitions": [
            _t("정상", "관찰", "사건 열기 (R4 로트 공유)"),
            _t("정상", "기준초과(미상신)", "사건 열기 (R1·R2 기준 초과)"),
            _t("관찰", "관찰해제", "관찰 해제 자동 처리 (R6·R6-1, 미확정 클레임 없음 R6-2)"),
            _t("관찰해제", "관찰", "관찰 복귀 자동 처리 (새 클레임, R6-2·R7)"),
            _t("관찰", "기준초과(미상신)", "판정 재계산 (확정 클레임으로 불량률 ≥ 10%, R7)"),
            _t("기준초과(미상신)", "상신중", "안건 상신"),
            _t("상신중", "회수진행", "위원회 승인 (R9)"),
            _t("상신중", "부분회수", "위원회 조건부 승인 (R9, A-08)"),
            _t("상신중", "조사계속", "위원회 거절 (R9, A-09)"),
            _t("부분회수", "회수진행", "부분회수 완료 판정 (미확인·확인요청중 관계 없음)"),
            _t("조사계속", "재상신 후보", "새 확정 클레임 또는 조사 회신 '원인 확인' (R9)"),
            _t("재상신 후보", "상신중", "안건 상신 (재상신)"),
        ],
    },
    "claim": {
        "name": "클레임 상태",
        "states": ["접수", "조사중", "확정", "기각"],
        # 원본 적재는 qc_claims_cv.status를 그대로 싣고(종결·미확정 = 기각), 클레임 등록은 접수/확정으로 만든다
        "initial": ["접수", "조사중", "확정", "기각"],
        "transitions": [
            _t("접수", "조사중", "원본 상태 진행"),
            _t("접수", "확정", "클레임 판정 반영"),
            _t("접수", "기각", "클레임 판정 반영"),
            _t("조사중", "확정", "클레임 판정 반영"),
            _t("조사중", "기각", "클레임 판정 반영"),
        ],
        "unconfirmed_states": ["접수", "조사중"],
    },
    "task": {
        "name": "작업 상태",
        "states": ["열림", "회신받음", "완료"],
        "initial": ["열림"],
        "transitions": [
            _t("열림", "회신받음", "회신 반영 (시스템이 규칙을 다시 돌린다)"),
            _t("회신받음", "완료", "회신 효과 반영 완료"),
        ],
    },
    "plan": {
        "name": "재공급 계획 상태",
        "states": ["초안", "확정", "기각", "대체됨"],
        "initial": ["초안"],
        "transitions": [
            _t("초안", "확정", "재공급 계획 결정 입력: 승인 (SCM)"),
            _t("초안", "기각", "재공급 계획 결정 입력: 거절 (SCM). 이전 확정 버전이 유효 계획으로 남는다"),
            _t("초안", "대체됨", "승인 전에 새 버전이 만들어짐 (시스템)"),
        ],
    },
    "shipped_to": {
        "name": "SHIPPED_TO 확인 수준",
        "states": list(CONFIRMATION_LEVELS),
        "initial": ["확인", "미확인"],
        "transitions": [
            _t("미확인", "확인요청중", "출하처 확인 작업(T-02) 생성"),
            _t("확인요청중", "회신확인", "회신 반영: 출하 확인"),
            _t("확인요청중", "영향없음", "회신 반영: 영향없음 (줄을 지우지 않음)"),
        ],
    },
}

# ---------------------------------------------------------------------------
# 사건 상태 5개 (§4-5, 저장하지 않고 도출)
# ---------------------------------------------------------------------------

INCIDENT_STATUSES = [
    {"name": "열림", "condition": "기준초과(미상신) 배치가 있고 아직 상신 전"},
    {"name": "관찰중", "condition": "묶인 배치가 모두 관찰 또는 관찰해제 (회수 대상 아님)"},
    {"name": "판정중", "condition": "상신중 또는 조사계속 배치가 있음"},
    {"name": "회수진행",
     "condition": "부분회수 또는 회수진행 배치가 있고, 확정된 재공급 계획이 없거나 승인 대기 중인 초안이 있음"},
    {"name": "복구계획확정", "condition": "확정 버전이 있고 승인 대기 중인 초안이 없음"},
]

# ---------------------------------------------------------------------------
# 규칙 R1 ~ R12 (§5, §5-1, §8-5 "규칙의 자리")
# ---------------------------------------------------------------------------
# places: 파생 속성 / 액션 효과 / 전제 조건 / 자동 처리 / 권한 원칙
# threshold: 기준값 · 출처 · 근거 참조 (화면의 판단 근거 옆에 그대로 표시)

PLACES = ["파생 속성", "액션 효과", "전제 조건", "자동 처리", "권한 원칙"]


def _r(summary, places, basis, *, extension=False, threshold=None):
    return {"summary": summary, "places": places, "basis": basis,
            "extension": extension, "threshold": threshold}


RULES = {
    "R1": _r("불량률 = 확정 클레임 수량 합 ÷ 생산 수량. 출하 기준 값은 참고. 확정 = defect_confirmed 참(종결 포함)",
             ["파생 속성"], ["[원본] calculation_definitions §1.9", "decisions 불량률 분모"]),
    "R2": _r("회수 대상 = 확정 불량 있음 AND 불량률 ≥ 10% → 위원회 안건 생성",
             ["파생 속성"], ["[원본] quality_policy_cv"],
             threshold={"value": 10, "unit": "%", "description": "불량률 ≥ 10%",
                        "source": "원본", "ref": "quality_policy_cv"}),
    "R3": _r("언론 보도는 판정을 바꾸지 않는다. 재검토 기록과 결론 유지 근거를 남긴다",
             ["액션 효과"], ["[원본] quality_policy_cv"]),
    "R4": _r("클레임에 적힌 원료 로트 = 기점 로트. 기점 로트를 쓴 다른 배치를 사건에 묶고 관찰. 배치의 다른 투입 로트는 따라가지 않는다",
             ["액션 효과"], ["decisions 필수 확장", "decisions 온톨로지 쟁점 6"], extension=True),
    "R5": _r("QC 보류 배치에 출하 기록 있음 → 경고 + 생산·물류에 출하 경위 확인 작업",
             ["액션 효과"], ["decisions 업무모델 v1 ④"], extension=True),
    "R5-1": _r("기점 로트 입고검사 보류인데 검사일 이후 생산된 배치에 투입 → 경고 + T-01 근거 추가. 사건 자동 개시 안 함. 투입일 < 입고일은 원본 기록 충돌로 표시",
               ["액션 효과"], ["A-15", "A05 §4"], extension=True),
    "R6": _r("관찰 해제: 마지막 출하일 기준 90일 무클레임이면 관찰해제",
             ["파생 속성", "자동 처리"], ["A-07"],
             threshold={"value": 90, "unit": "일", "description": "마지막 출하일 기준 90일",
                        "source": "가정", "ref": "A-07"}),
    "R6-1": _r("재관찰 해제: 마지막 클레임 확정일 기준 90일 무클레임이면 해제",
               ["파생 속성", "자동 처리"], ["A-12"],
               threshold={"value": 90, "unit": "일", "description": "마지막 클레임 확정일 기준 90일",
                          "source": "가정", "ref": "A-12"}),
    "R6-2": _r("미확정 클레임이 걸린 배치는 해제하지 않는다. 관찰해제 배치에 미확정 클레임 → 관찰. 기각되면 R6 또는 R6-1로 재판단",
               ["자동 처리"], ["A-16"]),
    "R7": _r("사건에 묶인 배치(관찰·해제 포함)에 확정 클레임 → R1·R2 재계산",
             ["자동 처리"], ["decisions 합격 배치 = 관찰"]),
    "R7-1": _r("사건에 묶인 배치에 미확정 클레임 → 확정 시 불량률((확정 + 미확정) ÷ 생산 수량)을 참고 표시. 판정 불변. 10% 이상이면 '확정 시 기준 초과 예상' 경고",
               ["자동 처리"], ["A-16", "[원본] quality_policy_cv"]),
    "R8": _r("클레임 고객이 출하처에 없음 → SHIPPED_TO 미확인 + 물류 확인 요청 + 해당 고객 회수·재공급 보류",
             ["액션 효과"], ["범위 규칙 ④", "A-02"]),
    "R9": _r("위원회 결과: 승인 → 회수진행 + 안내 후보 + 재공급 요청 / 조건부 → 부분 회수 / 거절 → 사유 필수 + 조사계속 + 원인 조사 작업, 새 확정 클레임·조사 회신이면 재상신 후보",
             ["액션 효과"], ["A-08", "A-09"]),
    "R9-1": _r("고객 안내 범위: 시스템은 후보(회수 배치 고객 + 관찰·해제 배치 고객 구분)만 제시하고 영업이 결정",
               ["액션 효과"], ["A-11", "decisions 업무모델 v1 ⑦"]),
    "R10": _r("재공급 순서 = ① 확인 고객 → ② 회수 수량 → ③ 매출 비중. 여유 능력 안에서 순위대로 한 고객씩 배분, 완료 월 = 누적 수량 ÷ 월 여유 능력 올림(현재 적용일의 달이 1번째 달). 영업 임원 우선 공급 요청은 회신 순서대로 앞에 둔다",
              ["자동 처리"], ["A-03", "A-04", "decisions 구현 기본값 ⑤"],
              threshold={"formula": "최근 6개월 월평균 생산 ÷ 가동률 × (1 − 가동률)",
                         "unit": "EA/월", "description": "여유 능력 월 약 1.5만 EA (가동률 97%는 원본 strat_capacity_cv)",
                         "source": "가정", "ref": "A-04"}),
    "R10-1": _r("재공급 대상 고객 중 수주 전년비 최근 2개월 연속 −20% 이하 → 영업 임원 확인 요청 (원인 분석 안 함)",
                ["파생 속성", "자동 처리"], ["A-13", "범위 규칙 ④", "[원본] sales_customer_summary_cv.booking_yoy_pct"],
                threshold={"value": -20, "unit": "%", "consecutive_months": 2,
                           "description": "수주 전년비 −20% 이하, 2개월 연속",
                           "source": "가정", "ref": "A-13"}),
    "R10-2": _r("출하처가 회신으로 확인됐지만 수량 기록이 없는 고객 → 클레임 수량 합을 최소 회수량으로 사용하고 하한임을 표시",
                ["자동 처리"], ["A-14"]),
    "R11": _r("재공급 출고 조건 = 다른 원료 로트(≠ 기점 로트) AND 배치 QC 합격. 공급 배치 = 같은 제품에서 조건을 만족하는 가장 최근 생산 배치",
              ["파생 속성", "전제 조건"], ["A-10", "decisions 구현 기본값 ④"]),
    "R12": _r("시스템·AI는 결정을 확정하지 않는다. 결정은 결정권자의 승인으로만 일어난다",
              ["권한 원칙"], ["[원본] approval_authority_policy"]),
}

# ---------------------------------------------------------------------------
# 작업 유형 7개 (§8-5 "회신 반영" 표)
# ---------------------------------------------------------------------------


def _res(result: str, effect: str) -> dict:
    return {"result": result, "effect": effect}


TASK_TYPES = {
    "출하 경위 확인": {
        "code": "T-01",
        "departments": ["생산", "물류"],
        "targets": ["batch"],
        "rules": ["R5", "R5-1"],
        "allowed_results": [
            _res("경위 확인됨", "작업 완료 (판정은 바꾸지 않음)"),
            _res("확인 불가", "작업 기한 연장 (판정은 바꾸지 않음)"),
        ],
    },
    "출하처 확인": {
        "code": "T-02",
        "departments": ["물류"],
        "targets": ["SHIPPED_TO"],
        "rules": ["R8"],
        "allowed_results": [
            _res("출하 확인", "SHIPPED_TO 확인 수준 → 회신확인 (수량 기록 없으면 클레임 합 하한, R10-2)"),
            _res("영향없음", "SHIPPED_TO 확인 수준 → 영향없음 (줄은 지우지 않음)"),
            _res("확인 불가", "확인 수준 유지 + 기한 연장"),
        ],
    },
    "안내 대상 결정": {
        "code": "T-03",
        "departments": ["영업"],
        "targets": ["customer"],
        "rules": ["R9-1"],
        "allowed_results": [
            _res("회수 배치 고객만", "안내 대상 기록"),
            _res("관찰·해제 배치 고객 포함", "안내 대상 기록"),
        ],
    },
    "재공급 요청": {
        "code": "T-04",
        "departments": ["SCM"],
        "targets": ["resupply_plan"],
        "rules": ["R9"],
        "allowed_results": [],
        "auto_complete": "SCM이 재공급 계획 결정을 입력하면 자동 완료",
    },
    "수주 급감 확인": {
        "code": "T-05",
        "departments": ["영업 임원"],
        "targets": ["customer"],
        "rules": ["R10-1"],
        "allowed_results": [
            _res("순서 유지", "변화 없음"),
            _res("우선 공급 요청", "재공급 계획 새 버전(초안)"),
        ],
    },
    "원인 조사": {
        "code": "T-06",
        "departments": ["품질", "생산"],
        "targets": ["batch"],
        "rules": ["R9"],
        "allowed_results": [
            _res("원인 확인", "배치 → 재상신 후보"),
            _res("원인 미확인", "조사계속 유지"),
        ],
    },
    "결과 통보": {
        "code": None,
        "departments": ["영업 임원"],
        "targets": ["resupply_plan"],
        "rules": [],
        "basis": "decisions 구현 기본값 ③ (SCM이 계획을 기각하면 생성)",
        "allowed_results": [
            _res("확인함", "작업 완료"),
        ],
    },
}

# ---------------------------------------------------------------------------
# 사람 액션 9개 (§8-5)
# ---------------------------------------------------------------------------
# inputs: key, name, type(date|text|int|id|id_list|choice), required, (ref_type | choices | choices_from)

ALL_ROLES = list(ROLES)


def _in(key, name, type_, required=True, **extra) -> dict:
    return {"key": key, "name": name, "type": type_, "required": required, **extra}


APPLIED_DATE = _in("applied_date", "적용일", "date", description="이 날짜에 일어난 일로 기록하고, 사건의 현재 날짜도 이 날짜로 넘어갑니다")

ACTIONS = {
    "open_incident": {
        "name": "사건 열기",
        "roles": ["quality_owner"],
        "inputs": [APPLIED_DATE, _in("batch_id", "배치", "id", ref_type="batch")],
        "precondition": "그 배치에 클레임이 있음",
        "effect": "사건 생성, 배치 묶음(R4), 경고(R5, R5-1), 미확인 관계(R8), 작업 T-01·T-02",
        "rules": ["R4", "R5", "R5-1", "R8"],
        "creates_tasks": ["출하 경위 확인", "출하처 확인"],
    },
    "register_claim": {
        "name": "클레임 등록",
        "roles": ["quality_owner"],
        "inputs": [
            APPLIED_DATE,
            _in("batch_id", "배치", "id", ref_type="batch"),
            _in("customer_id", "고객", "id", ref_type="customer"),
            _in("qty", "수량", "int"),
            _in("received_date", "접수일", "date"),
            _in("status", "상태", "choice", choices=["접수", "확정"]),
        ],
        "precondition": "배치가 사건에 묶여 있음",
        "effect": "클레임·이벤트 생성 → 미확정이면 R7-1·R6-2, 확정이면 판정 재계산(R7)",
        "rules": ["R7", "R7-1", "R6-2"],
        "creates_tasks": [],
    },
    "resolve_claim": {
        "name": "클레임 판정 반영",
        "roles": ["quality_owner"],
        "inputs": [
            APPLIED_DATE,
            _in("claim_id", "클레임", "id", ref_type="claim"),
            _in("result", "판정", "choice", choices=["확정", "기각"]),
        ],
        "precondition": "클레임이 미확정",
        "effect": "클레임 상태 → 확정이면 판정 재계산(R7), 기각이면 해제 조건 재판단(R6-2)",
        "rules": ["R7", "R6-2"],
        "creates_tasks": [],
    },
    "register_news": {
        "name": "보도 등록",
        "roles": ["quality_owner"],
        "inputs": [
            APPLIED_DATE,
            _in("content", "보도 내용", "text"),
            _in("occurred_date", "발생일", "date", required=False),
        ],
        "precondition": "—",
        "effect": "이벤트 + 재검토 기록만 (R3, 상태 변화 없음)",
        "rules": ["R3"],
        "creates_tasks": [],
    },
    "submit_agenda": {
        "name": "안건 상신",
        "roles": ["quality_owner"],
        "inputs": [
            APPLIED_DATE,
            _in("batch_ids", "배치", "id_list", ref_type="batch"),
            _in("agenda_summary", "안건 요약", "text", required=False,
                description="비워 두어도 상신할 수 있습니다"),
        ],
        "precondition": "판정 상태 = 기준초과(미상신) 또는 재상신 후보",
        "effect": "배치 → 상신중",
        "rules": ["R2"],
        "creates_tasks": [],
    },
    "committee_decision": {
        "name": "위원회 결정 입력",
        "roles": ["quality_committee"],
        "inputs": [
            APPLIED_DATE,
            _in("batch_ids", "배치", "id_list", ref_type="batch"),
            _in("result", "결과", "choice", choices=list(COMMITTEE_RESULTS), choice_effects={
                "승인": "대상 배치 회수 시작 · 재공급 계획 초안 생성",
                "조건부": "출하처가 확인된 고객만 먼저 회수 · 미확인 고객은 회신까지 보류",
                "거절": "회수하지 않고 조사 계속 · 원인 조사 작업 생성 · 사유 필수",
            }),
            _in("reason", "사유", "text", required=False, description="거절이면 필수 (A-09)"),
        ],
        "precondition": "배치 = 상신중. 거절은 사유 필수",
        "effect": "결정 생성, 배치 → 회수진행 / 부분회수 / 조사계속, 작업 생성 (R9)",
        "rules": ["R9", "R9-1", "R12"],
        "creates_tasks": ["안내 대상 결정", "재공급 요청", "원인 조사"],
    },
    "apply_reply": {
        "name": "회신 반영",
        "roles": ["quality_owner"],
        "inputs": [
            APPLIED_DATE,
            _in("task_id", "작업", "id", ref_type="task"),
            _in("reply_text", "회신 문장", "text"),
            _in("result", "회신 결과", "choice", choices_from="task_type.allowed_results"),
        ],
        "precondition": "작업 = 열림. 결과가 그 작업 유형의 허용 목록에 있음",
        "effect": "이벤트 생성, 작업 상태, TARGETS 대상에 작업 유형별 효과",
        "rules": ["R8", "R9", "R9-1", "R10-1", "R10-2", "R12"],
        "creates_tasks": [],
    },
    "plan_decision": {
        "name": "재공급 계획 결정 입력",
        "roles": ["scm"],
        "inputs": [
            APPLIED_DATE,
            _in("plan_id", "재공급 계획", "id", ref_type="resupply_plan"),
            _in("result", "결과", "choice", choices=list(PLAN_DECISION_RESULTS), choice_effects={
                "승인": "계획 확정 · 출고 조건(R11) 충족 필요",
                "거절": "계획 기각 · 이전 확정 버전 유지 · 영업 임원에게 결과 통보 · 근거 필수",
            }),
            _in("reason", "근거", "text", required=False),
        ],
        "precondition": "계획 = 초안, 출고 조건 충족(R11). 열린 T-05가 있어도 승인할 수 있고 경고를 보인다",
        "effect": "결정 생성, 계획 → 확정 또는 기각(이전 확정 버전 유지)",
        "rules": ["R11", "R12"],
        "creates_tasks": ["결과 통보"],
    },
    "reset": {
        "name": "초기화",
        "roles": ALL_ROLES,
        "inputs": [],
        "precondition": "—",
        "effect": "빈 DB로 되돌림(사건 없음). 원본 적재는 사건 열기가 한다",
        "rules": [],
        "creates_tasks": [],
    },
}

# ---------------------------------------------------------------------------
# 시스템 자동 처리 (§8-5)
# ---------------------------------------------------------------------------

AUTO_PROCESSES = {
    "release_observation": {
        "name": "관찰 해제",
        "trigger": "현재 적용일이 전진할 때, 클레임이 기각될 때",
        "effect": "배치 관찰 → 관찰해제. 미확정 클레임이 있으면 하지 않음 (R6-2)",
        "rules": ["R6", "R6-1", "R6-2"],
    },
    "return_to_observation": {
        "name": "관찰 복귀",
        "trigger": "관찰해제 배치에 클레임이 등록될 때",
        "effect": "배치 관찰해제 → 관찰",
        "rules": ["R6-2", "R7"],
    },
    "recalculate_judgment": {
        "name": "판정 재계산",
        "trigger": "클레임이 등록되거나 확정될 때",
        "effect": "배치 판정 상태 (미확정 클레임은 확정 시 불량률만 표시)",
        "rules": ["R1", "R2", "R7", "R7-1"],
    },
    "complete_partial_recall": {
        "name": "부분회수 완료 판정",
        "trigger": "SHIPPED_TO 확인 수준이 바뀔 때",
        "effect": "그 배치에 미확인·확인요청중 관계가 없으면 배치 부분회수 → 회수진행",
        "rules": ["R9"],
    },
    "recalculate_plan": {
        "name": "재공급 계획 재계산",
        "trigger": "회수 범위나 영업 임원 회신이 바뀔 때",
        "effect": "계획 새 버전(초안). 승인 대기 초안이 있으면 그 초안 → 대체됨",
        "rules": ["R10", "R10-2"],
    },
    "request_order_drop_check": {
        "name": "수주 급감 확인 요청",
        "trigger": "계획 초안이 만들어질 때 (같은 고객에 열렸거나 회신된 작업이 이미 있으면 다시 만들지 않음)",
        "effect": "수주 급감 확인 작업 생성",
        "rules": ["R10-1"],
    },
    "complete_resupply_request": {
        "name": "재공급 요청 자동 완료",
        "trigger": "SCM이 재공급 계획 결정을 입력할 때",
        "effect": "재공급 요청 작업 완료",
        "rules": [],
        "basis": "decisions 구현 기본값 ②",
    },
    "create_result_notice": {
        "name": "결과 통보 생성",
        "trigger": "SCM이 재공급 계획을 기각할 때",
        "effect": "영업 임원 결과 통보 작업 생성",
        "rules": [],
        "basis": "decisions 구현 기본값 ③",
    },
}

# ---------------------------------------------------------------------------
# 조회 함수
# ---------------------------------------------------------------------------


def to_dict() -> dict:
    """정의 전체를 JSON으로 직렬화할 수 있는 dict로 돌려준다 (GET /api/ontology, 온톨로지 탭)."""
    return copy.deepcopy({
        "sources": SOURCES,
        "confirmation_levels": CONFIRMATION_LEVELS,
        "confirmed_levels": CONFIRMED_LEVELS,
        "quantity_bases": QUANTITY_BASES,
        "roles": ROLES,
        "departments": DEPARTMENTS,
        "event_types": EVENT_TYPES,
        "decision_types": DECISION_TYPES,
        "committee_results": COMMITTEE_RESULTS,
        "plan_decision_results": PLAN_DECISION_RESULTS,
        "ai_uninterpretable": AI_UNINTERPRETABLE,
        "task_deadline": TASK_DEADLINE,
        "object_types": OBJECT_TYPES,
        "link_attributes": LINK_ATTRIBUTES,
        "relations": RELATIONS,
        "state_machines": STATE_MACHINES,
        "incident_statuses": INCIDENT_STATUSES,
        "rule_places": PLACES,
        "rules": RULES,
        "task_types": TASK_TYPES,
        "actions": ACTIONS,
        "auto_processes": AUTO_PROCESSES,
    })


def can_transition(kind: str, from_state: str, to_state: str) -> bool:
    """kind = 'batch' | 'claim' | 'task' | 'plan' | 'shipped_to'. 전이표에 있는 전이만 True."""
    machine = STATE_MACHINES.get(kind)
    if machine is None:
        return False
    return any(t["from"] == from_state and t["to"] == to_state for t in machine["transitions"])


def action_def(key: str) -> dict | None:
    return ACTIONS.get(key)


def task_type_def(name: str) -> dict | None:
    """허용 결과 포함."""
    return TASK_TYPES.get(name)


def rule_def(rule_id: str) -> dict | None:
    """기준값·출처 포함."""
    return RULES.get(rule_id)
