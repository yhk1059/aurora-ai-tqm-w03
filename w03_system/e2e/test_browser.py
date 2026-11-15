"""브라우저 테스트. 단계 번호와 기대 값은 brain/3-design/browser-test-scenarios.md 와 같다."""
import os
import re

import pytest
from playwright.sync_api import Page, expect

from e2e import helpers as h
from e2e.helpers import COMMITTEE, OWNER, SCM

S0 = "빈 상태 (S0, 사건 없음)"
START_2 = "시연 2. 조건 변경 출발 상태"
START_3A = "시연 3-A. 정보 부족 + 조건부 승인 출발 상태"
START_3B = "시연 3-B. 승인 거절 출발 상태"

B1, B2, B3, B4 = "B-02-2602-01", "B-02-2602-02", "B-02-2602-03", "B-02-2603-01"

PLAN_V1 = [("C-103", "2026-12"), ("C-102", "2027-05"), ("C-101", "2027-09"), ("C-104", "2027-12"), ("C-108", "2028-03")]
PLAN_V2_PRIORITY = [("C-101", "2026-10"), ("C-103", "2027-04"), ("C-102", "2027-09"), ("C-104", "2027-12"), ("C-108", "2028-03")]


def open_incident(page: Page, batch_id: str, date: str = "2026-07-01") -> None:
    """기준 초과 배치는 큰 카드의 버튼, 기준 미달 배치는 표 줄 끝의 버튼으로 연다."""
    main = page.locator("main")
    main.get_by_label("적용일", exact=True).fill(date)
    over = main.locator("article", has_text=batch_id)
    if over.count():
        h.execute(page, over, "이 배치로 사건 열기")
    else:
        main.get_by_label("배치 ID 검색").fill(batch_id)
        h.execute(page, main.locator("tr", has_text=batch_id), "사건 열기")


def c105_cells(page: Page) -> list[str]:
    """C-105 열에서 연결이 있는 칸의 테두리 모양 ('dashed' = 미확인·확인요청중, 'solid' = 그 밖)."""
    view = page.request.get("/api/incident", params={"actor": "quality_owner"}).json()
    ids = [l["link_id"] for l in view["network"]["shipped_to"] if l["dst"]["id"] == "C-105"]
    assert ids, "C-105로 가는 연결이 없음"
    h.network(page)  # 연결망 탭으로 옮겨 간다. 사건 탭에서 이어가려면 부른 쪽이 탭을 다시 고른다
    out = []
    for i in ids:
        cell = page.locator(f'[data-network] [data-link="{i}"]')
        out.append(cell.evaluate("e => getComputedStyle(e).borderTopStyle"))
    return out


# ---------------------------------------------------------------------------
# TC-00
# ---------------------------------------------------------------------------

def test_tc00_empty_state(page: Page):
    # 0-1
    for label in ["사건", "연결망", "재공급 계획", "기록", "온톨로지"]:
        expect(page.locator("nav").get_by_role("button", name=label, exact=True)).to_be_visible()
    expect(page.locator("header select")).to_have_value("quality_owner")
    # 0-2
    h.reset(page, S0)
    expect(page.locator("header")).to_contain_text("사건 없음")
    main = page.locator("main")
    expect(main.get_by_role("heading", name="사건 열기", exact=True)).to_be_visible()
    # 0-3
    expect(main.locator("article")).to_have_count(2)
    expect(main.locator("article", has_text=B1)).to_contain_text("11.9%")
    expect(main.locator("article", has_text=B4)).to_contain_text("11.6%")
    expect(h.card(page, "기준 미달 배치")).to_contain_text("105개")
    # 0-4, 0-5
    h.tab(page, "재공급 계획")
    expect(page.locator("main")).to_contain_text("재공급 계획이 아직 없습니다")
    h.tab(page, "기록")
    expect(page.locator("main")).to_contain_text("기록 없음")
    # 0-6
    h.tab(page, "사건")
    h.set_role(page, COMMITTEE)
    expect(page.locator("main")).to_contain_text("이 역할은 사건을 열 수 없습니다")
    expect(page.get_by_role("button", name=re.compile("사건 열기"))).to_have_count(0)
    h.set_role(page, OWNER)
    expect(page.get_by_role("button", name="이 배치로 사건 열기")).to_have_count(2)


# ---------------------------------------------------------------------------
# TC-01 시연 1
# ---------------------------------------------------------------------------

def test_tc01_demo1_normal(page: Page):
    h.reset(page, S0)

    # 1-1
    open_incident(page, B1)
    header = page.locator("header")
    expect(header).to_contain_text("INC-001")
    expect(header).to_contain_text("LOT-B-2602-P")
    h.expect_batch(page, B1, "기준초과(미상신)", "11.9%")
    h.expect_batch(page, B4, "기준초과(미상신)", "11.6%")
    h.expect_batch(page, B2, "관찰해제")
    h.expect_batch(page, B3, "관찰해제")
    expect(h.batch(page, B1)).to_contain_text("후 91일 미상신")  # 경고 줄에 한 번만 나온다
    expect(h.batch(page, B4)).to_contain_text("후 51일 미상신")
    expect(h.batch(page, B1).get_by_text("91일 미상신")).to_have_count(1)
    main = page.locator("main")
    expect(main.get_by_text("QC 보류 배치가 출하됨")).to_have_count(2)
    expect(main.get_by_text("원본 기록 충돌")).to_have_count(1)
    expect(main.get_by_text("투입 경위 확인 필요")).to_have_count(3)
    expect(h.tasks(page).locator("h2")).to_have_text("작업 열림 2 / 전체 2")
    expect(h.task(page, "출하 경위 확인")).to_contain_text("생산·물류")
    expect(h.task(page, "출하처 확인")).to_contain_text("2026-07-08")
    expect(page.locator("main [data-open-network]")).to_be_visible()  # 사건 탭에는 연결망 한 줄과 탭으로 가는 링크만 있다
    expect(page.locator("nav")).to_contain_text("미확인 1")  # 연결망 탭 배지: 출하처 미확인 고객 수
    assert all(d == "dashed" for d in c105_cells(page)), "C-105 칸이 점선이 아님"
    h.tab(page, "사건")
    page.screenshot(path=str(_shot("tc01_1-1")), full_page=True)

    # 1-2
    bar = h.action_bar(page)
    bar.get_by_role("button", name="안건 상신", exact=True).click()
    expect(bar.locator("input[type=checkbox]:checked")).to_have_count(2)
    h.fill_date(bar, "2026-07-01")
    h.execute(page, bar, "안건 상신 실행")
    h.expect_batch(page, B1, "상신중")
    h.expect_batch(page, B4, "상신중")
    expect(page.get_by_role("button", name="안건 상신", exact=True)).to_have_count(0)

    # 1-3
    h.set_role(page, COMMITTEE)
    h.committee_decision(page, "2026-07-02", "승인")
    h.expect_batch(page, B1, "회수진행")
    h.expect_batch(page, B4, "회수진행")
    expect(h.tasks(page).locator("h2")).to_have_text("작업 열림 6 / 전체 6")
    expect(h.task(page, "안내 대상 결정")).to_contain_text("영업")
    expect(h.task(page, "수주 급감 확인")).to_have_count(2)
    expect(h.task(page, "재공급 요청")).to_contain_text("SCM")
    last = h.last_change(page)
    for auto in ["재공급 계획 재계산", "수주 급감 확인 요청", "재공급 요청 생성"]:
        expect(last).to_contain_text(auto)
    expect(last.get_by_text("자동", exact=True)).to_have_count(3)

    # 1-4
    h.tab(page, "재공급 계획")
    h.expect_plan(page, 1, "초안", PLAN_V1)
    rows = h.plan_rows(page)
    expect(rows.nth(0)).to_contain_text("83,402 EA")
    expect(rows.nth(4)).to_contain_text("34,929 EA")
    held = h.card(page, "고객별 재공급 순서")
    expect(held).to_contain_text("계획에서 보류된 고객")
    expect(held).to_contain_text("C-105")
    expect(page.locator("main")).to_contain_text("영업 임원 확인 대기 2건")
    cond = h.card(page, re.compile(r"^출고 조건"))
    expect(cond).to_contain_text("LOT-B-2606-1")
    expect(cond.get_by_text("충족", exact=True)).to_be_visible()
    page.screenshot(path=str(_shot("tc01_1-4")), full_page=True)

    # 1-5
    h.tab(page, "사건")
    h.set_role(page, OWNER)
    h.reply(page, h.task(page, "안내 대상 결정"), "2026-07-02", "회수 배치 고객만")
    t = h.task(page, "안내 대상 결정")
    h.expect_task(t, "완료")
    expect(t).to_contain_text("결과 회수 배치 고객만")

    # 1-6 출하 경위 확인(T-01)이 열려 있어 승인에 근거가 필수 (R11-1)
    h.set_role(page, SCM)
    h.tab(page, "재공급 계획")
    expect(h.hold_band(page)).to_contain_text("출하 경위 확인 대기 1건")
    expect(h.hold_band(page)).to_contain_text("승인하려면 근거를 적어야 합니다")
    dlg = h.open_plan_decision(page)
    expect(dlg.locator('[data-hold-row="waiting"]')).to_contain_text("확인 대기")
    dlg.locator("button[aria-pressed]").filter(has_text="승인").click()
    h.fill_date(dlg, "2026-07-03")
    run = dlg.get_by_role("button", name="결정 실행")
    expect(run).to_be_disabled()
    expect(dlg).to_contain_text("출하 경위 확인이 끝나지 않아, 승인하려면 근거를 적어야 합니다.")
    h.pick_example(dlg, "승인 (출고 조건 충족)")  # 근거가 채워진다
    expect(dlg.locator("textarea")).to_have_value(re.compile("출하 경위는 회신 후 재확인"))
    expect(run).to_be_enabled()
    h.execute(page, dlg, re.compile("결정 실행$"))
    expect(dlg).to_be_hidden()
    h.expect_plan(page, 1, "확정", PLAN_V1)
    dec = h.card(page, h.exact("결정"))
    expect(dec).to_contain_text("승인")
    expect(dec).to_contain_text("SCM")
    expect(dec).to_contain_text("출고 조건 충족")
    expect(header).to_contain_text("복구계획확정")
    expect(page.locator("main")).to_contain_text("영업 임원 확인 대기 2건")
    h.tab(page, "사건")
    h.expect_task(h.task(page, "재공급 요청"), "완료")

    # 1-7 바뀐 상태가 다음 판단에 쓰임
    h.set_role(page, OWNER)
    h.bar_action(page, "클레임 등록", "2026-07-06", "회수 배치 신규 확정 클레임 (C-102, 300 EA)")
    h.expect_batch(page, B1, "회수진행", "12.1%")
    expect(page.get_by_role("button", name="안건 상신", exact=True)).to_have_count(0)
    expect(h.tasks(page).locator("h2")).to_have_text("작업 열림 4 / 전체 6")
    expect(header).to_contain_text("복구계획확정")
    h.tab(page, "재공급 계획")
    expect(h.version_count(page)).to_have_count(1)
    page.screenshot(path=str(_shot("tc01_1-7_plan")), full_page=True)

    # 1-8
    h.tab(page, "기록")
    h.expect_log_count(page, 15)
    logc = h.card(page, re.compile(r"^액션 기록"))
    logc.get_by_role("button", name="사람 액션만").click()
    expect(h.log_rows(page)).to_have_count(6)
    logc.get_by_role("button", name="자동 처리만").click()
    expect(h.log_rows(page)).to_have_count(9)
    logc.get_by_role("button", name="전체", exact=True).click()
    # 전체 보기에서는 자동 처리 줄이 그것을 일으킨 사람 액션 아래에 접혀 있다
    expect(h.log_rows(page)).to_have_count(6)
    logc.get_by_role("button", name=re.compile(r"자동 처리 \d+건 보기")).first.click()
    expect(logc.get_by_role("button", name=re.compile(r"자동 처리 \d+건 접기"))).to_have_count(1)
    assert h.log_rows(page).count() > 6
    h.log_rows(page).filter(has_text="위원회 결정 입력").first.locator("button").first.click()
    expect(logc).to_contain_text("변경 (이전 → 이후)")

    # 1-9
    page.reload()
    expect(page.locator("header")).to_contain_text("복구계획확정")
    h.expect_batch(page, B1, "회수진행", "12.1%")


# ---------------------------------------------------------------------------
# TC-02 시연 2
# ---------------------------------------------------------------------------

def demo2_until_priority_reply(page: Page) -> None:
    """2-0 ~ 2-4b"""
    h.reset(page, START_2)
    header = page.locator("header")

    # 2-0
    expect(header).to_contain_text("복구계획확정")
    expect(h.task(page, "수주 급감 확인").get_by_role("button", name="회신 입력")).to_have_count(2)
    h.tab(page, "기록")
    h.expect_log_count(page, 14)
    h.tab(page, "재공급 계획")
    h.expect_plan(page, 1, "확정", PLAN_V1)
    h.tab(page, "사건")

    # 2-1 결론 유지
    h.bar_action(page, "보도 등록", "2026-07-06", "언론 보도 (미확정, 제품·배치 지목 없음)")
    last = h.last_change(page)
    expect(last).to_contain_text("보도 등록")
    expect(last).to_contain_text("EV-002")  # 보도 이벤트가 사건에 기록된다
    expect(last).to_contain_text("R3")
    expect(last).not_to_contain_text("배치")  # 배치 판정은 바뀌지 않는다
    h.expect_batch(page, B1, "회수진행")
    h.expect_batch(page, B4, "회수진행")
    h.expect_batch(page, B2, "관찰해제")
    h.expect_batch(page, B3, "관찰해제")

    # 2-2a 미확정 클레임 → 관찰 복귀
    h.bar_action(page, "클레임 등록", "2026-07-07", "해제 배치 늦은 클레임 접수 (C-101, 800 EA)")
    h.expect_batch(page, B3, "관찰", "0.0%")
    b3 = h.batch(page, B3)
    expect(b3).to_contain_text("800 EA")
    expect(b3).to_contain_text("0.5% (참고, 판정 불변)")
    expect(b3).not_to_contain_text("관찰 해제 예정일")
    expect(b3).to_contain_text("미확정 1건")
    expect(h.last_change(page)).to_contain_text("관찰 복귀")
    page.screenshot(path=str(_shot("tc02_2-2a")), full_page=True)

    # 2-2b 확정 → 재계산, 관찰 유지
    b3.get_by_role("button", name="판정 반영").click()
    h.pick_example(b3, "확정 → 재계산")
    h.fill_date(b3, "2026-07-08")
    h.execute(page, b3, "클레임 판정 반영 실행")
    h.expect_batch(page, B3, "관찰", "0.5%")
    expect(b3.get_by_text("기준 미달", exact=True)).to_be_visible()
    expect(b3).to_contain_text("2026-10-06")
    expect(b3).to_contain_text("마지막 클레임 확정일 기준")
    expect(b3).not_to_contain_text("미확정 1건")

    # 2-3
    h.expect_task(h.task(page, "수주 급감 확인", "C-101"), "열림")
    h.expect_task(h.task(page, "수주 급감 확인", "C-104"), "열림")

    # 2-4a 순서 유지 → 새 버전 없음
    h.reply(page, h.task(page, "수주 급감 확인", "C-104"), "2026-07-09", "C-104 순서 유지")
    h.expect_task(h.task(page, "수주 급감 확인", "C-104"), "완료")
    h.tab(page, "재공급 계획")
    expect(h.version_count(page)).to_have_count(1)
    h.tab(page, "사건")

    # 2-4b 우선 공급 요청 → 계획 v2 초안 (다른 부서 영향)
    h.reply(page, h.task(page, "수주 급감 확인", "C-101"), "2026-07-09", "C-101 우선 공급 요청")
    h.tab(page, "재공급 계획")
    h.expect_plan(page, 2, "초안", PLAN_V2_PRIORITY)
    expect(h.plan_rows(page).nth(0)).to_contain_text("영업 임원 우선 공급 요청")
    diff = h.card(page, "이전 버전과 비교")
    expect(diff.locator("h2")).to_contain_text("RP-v1")
    expect(diff.locator("tr", has_text="C-101")).to_contain_text("11개월 앞당김")
    expect(diff.locator("tr", has_text="C-103")).to_contain_text("4개월 지연")
    expect(diff.locator("tr", has_text="C-102")).to_contain_text("4개월 지연")
    expect(diff.locator("tbody tr")).to_have_count(3)  # 바뀐 줄만 표에 올린다
    expect(diff.locator("[data-same]")).to_contain_text("변화 없음 2곳")
    expect(diff.locator("[data-same]")).to_contain_text("C-104, C-108")
    expect(h.card(page, h.exact("결정")).locator("[data-plan-headline]")).to_have_text(
        "C-101 11개월 앞당김, C-103 4개월 지연, C-102 4개월 지연 · 나머지 2곳 변화 없음")
    expect(h.card(page, h.exact("버전"))).to_contain_text("계기 회신 반영")
    expect(h.hold_band(page)).to_contain_text("출하 경위 확인 대기 1건")  # T-01이 아직 열림 (R11-1)
    page.screenshot(path=str(_shot("tc02_2-4b")), full_page=True)


HOLD_REPLY = "QC 보류 표시가 출하 지시에 반영되지 않아 납기 일정대로 출고됨. 출하 전 확인표에 보류 배치 차단 항목 추가"


def test_tc02_demo2_change(page: Page):
    demo2_until_priority_reply(page)

    # 2-4c 출하 경위 회신 → 경고가 풀린다 (R11-1). 계획 버전은 그대로
    h.tab(page, "사건")
    h.reply(page, h.task(page, "출하 경위 확인"), "2026-07-09", "경위 확인됨 (보류 표시 미반영, 차단 항목 추가)")
    h.expect_task(h.task(page, "출하 경위 확인"), "완료")
    h.tab(page, "재공급 계획")
    expect(h.hold_band(page)).to_have_count(0)
    expect(h.version_count(page)).to_have_count(2)

    # 2-5 판단 근거에 출하 경위 회신이 보이고, 경고 없이 승인
    h.set_role(page, SCM)
    dlg = h.open_plan_decision(page)
    done = dlg.locator('[data-hold-row="done"]')
    expect(done).to_contain_text("출하 경위")
    expect(done).to_contain_text("확인됨")
    expect(done).to_contain_text(HOLD_REPLY)
    dlg.get_by_role("button", name="취소").click()
    expect(dlg).to_be_hidden()
    h.plan_decision(page, "2026-07-09", "승인 (우선 공급 요청 반영)")
    h.expect_plan(page, 2, "확정", PLAN_V2_PRIORITY)
    versions = h.card(page, h.exact("버전"))
    versions.locator("button").filter(has_text=re.compile(r"^\s*v1")).click()
    h.expect_plan(page, 1, "확정", PLAN_V1)  # 관찰 항목: v1도 확정으로 남는다
    expect(h.card(page, h.exact("결정"))).to_contain_text("출고 조건 충족")
    h.tab(page, "기록")
    h.expect_log_count(page, 24)


def test_tc02b_scm_reject(page: Page):
    """2-5x 불리한 회신: SCM 거절 → v1 유지 + 결과 통보."""
    demo2_until_priority_reply(page)
    h.set_role(page, SCM)
    h.plan_decision(page, "2026-07-09", "거절 (기존 순서 유지)")
    h.expect_plan(page, 2, "기각", PLAN_V2_PRIORITY)
    h.card(page, h.exact("버전")).locator("button").filter(has_text=re.compile(r"^\s*v1")).click()
    h.expect_plan(page, 1, "확정", PLAN_V1)
    h.tab(page, "사건")
    expect(h.task(page, "결과 통보")).to_have_count(1)
    expect(h.task(page, "결과 통보")).to_contain_text("영업 임원")
    expect(page.locator("header")).to_contain_text("복구계획확정")


def test_tc02c_hold_check_unavailable(page: Page):
    """불리한 회신: 출하 경위 '확인 불가' → 작업은 열린 채 연장, v2 초안에도 경고와 근거 필수가 남는다 (R11-1)."""
    h.reset(page, START_2)
    t = h.task(page, "출하 경위 확인")
    h.reply(page, t, "2026-07-08", "확인 불가 (7일 추가 필요)")
    t = h.task(page, "출하 경위 확인")
    h.expect_task(t, "열림")
    expect(t.locator('[data-due="extended"]')).to_contain_text("연장됨 (처음 기한 2026-07-08)")
    expect(t).to_contain_text("2026-07-15")

    h.reply(page, h.task(page, "수주 급감 확인", "C-101"), "2026-07-09", "C-101 우선 공급 요청")
    h.tab(page, "재공급 계획")
    h.expect_plan(page, 2, "초안", PLAN_V2_PRIORITY)
    expect(h.hold_band(page)).to_contain_text("출하 경위 확인 대기 1건")

    h.set_role(page, SCM)
    dlg = h.open_plan_decision(page)
    waiting = dlg.locator('[data-hold-row="waiting"]')
    expect(waiting).to_contain_text("확인 대기")
    expect(waiting).to_contain_text("연장됨 (처음 기한 2026-07-08)")
    expect(waiting).to_contain_text("출하 지시 기록 확인 불가, 7일 추가 필요")
    dlg.locator("button[aria-pressed]").filter(has_text="승인").click()
    h.fill_date(dlg, "2026-07-09")
    expect(dlg.get_by_role("button", name="결정 실행")).to_be_disabled()
    expect(dlg).to_contain_text("출하 경위 확인이 끝나지 않아, 승인하려면 근거를 적어야 합니다.")
    dlg.get_by_role("button", name="취소").click()
    expect(dlg).to_be_hidden()
    h.expect_plan(page, 2, "초안", PLAN_V2_PRIORITY)


# ---------------------------------------------------------------------------
# TC-03 시연 3-A
# ---------------------------------------------------------------------------

def demo3a_until_conditional(page: Page) -> None:
    """3-1 ~ 3-2"""
    h.reset(page, START_3A)
    # 3-1
    h.expect_batch(page, B1, "상신중")
    h.expect_batch(page, B4, "상신중")
    h.expect_task(h.task(page, "출하처 확인"), "열림")
    assert all(d == "dashed" for d in c105_cells(page))
    page.locator('[data-node="customer:C-105"]').click()
    detail = h.card(page, h.exact("고객 · C-105"))
    expect(detail).to_contain_text("들어오는 선")
    expect(detail).to_contain_text("확인요청중")
    page.get_by_role("button", name=f"{B1} → C-105", exact=True).click()
    expect(h.card(page, f"{B1} → C-105")).to_contain_text("없음 — 출하 기록 없음 (클레임만 있음)")
    h.tab(page, "사건")
    # 3-2
    h.set_role(page, COMMITTEE)
    h.committee_decision(page, "2026-07-02", "조건부 승인 (확인 고객만 우선 회수)")
    h.expect_batch(page, B1, "부분회수")
    h.expect_batch(page, B4, "부분회수")
    h.tab(page, "재공급 계획")
    h.expect_plan(page, 1, "초안", PLAN_V1)
    expect(h.card(page, "고객별 재공급 순서")).to_contain_text("출하처 미확인 — 물류 회신까지 회수·재공급 보류")
    h.tab(page, "사건")
    h.set_role(page, OWNER)


def test_tc03_demo3a_missing_info(page: Page):
    demo3a_until_conditional(page)

    # 3-3 불리한 회신: 진행된 척하지 않음
    h.reply(page, h.task(page, "출하처 확인"), "2026-07-08", "확인 불가 (7일 추가)")
    t = h.task(page, "출하처 확인")
    h.expect_task(t, "열림")
    expect(t).to_contain_text("2026-07-15")
    h.expect_batch(page, B1, "부분회수")
    h.expect_batch(page, B4, "부분회수")
    assert all(d == "dashed" for d in c105_cells(page))
    h.tab(page, "재공급 계획")
    expect(h.version_count(page)).to_have_count(1)
    h.tab(page, "사건")
    page.screenshot(path=str(_shot("tc03_3-3")), full_page=True)

    # 3-4 확인되면 이어감
    h.reply(page, h.task(page, "출하처 확인"), "2026-07-15", "출하 확인 (수량 기록 없음)")
    h.expect_task(h.task(page, "출하처 확인"), "완료")
    h.expect_batch(page, B1, "회수진행")
    h.expect_batch(page, B4, "회수진행")
    expect(page.locator("header")).to_contain_text("회수진행")
    assert all(d == "solid" for d in c105_cells(page)), "C-105 칸이 실선이 아님"
    expect(page.locator("nav")).not_to_contain_text("미확인")
    h.tab(page, "재공급 계획")
    h.expect_plan(page, 2, "초안", PLAN_V1 + [("C-105", "2028-04")])
    last = h.plan_rows(page).nth(5)
    expect(last).to_contain_text("11,765 EA")
    expect(last).to_contain_text("하한")
    expect(last).to_contain_text("클레임 합(하한)")
    diff = h.card(page, "이전 버전과 비교")
    expect(diff.locator("tr", has_text="C-105")).to_contain_text("새로 추가")
    expect(diff.locator("tbody tr")).to_have_count(1)
    expect(diff.locator("[data-same]")).to_contain_text("변화 없음 5곳")
    expect(h.card(page, h.exact("결정")).locator("[data-plan-headline]")).to_have_text("C-105 6순위로 추가 · 나머지 5곳 변화 없음")
    expect(h.card(page, "고객별 재공급 순서")).not_to_contain_text("계획에서 보류된 고객")
    v1 = h.card(page, h.exact("버전")).locator("button").filter(has_text=re.compile(r"^\s*v1"))
    expect(v1.locator("span.rounded")).to_have_text("대체됨")
    h.tab(page, "기록")
    h.expect_log_count(page, 17)


def test_tc03b_no_impact(page: Page):
    """3-3x 불리한 회신: 영향없음 → 선은 옅은 회색으로 남고 계획에 안 들어감."""
    demo3a_until_conditional(page)
    h.reply(page, h.task(page, "출하처 확인"), "2026-07-08", "영향없음")
    h.expect_task(h.task(page, "출하처 확인"), "완료")
    view = page.request.get("/api/incident", params={"actor": "quality_owner"}).json()
    confirms = {l["confirm"] for l in view["network"]["shipped_to"] if l["dst"]["id"] == "C-105"}
    assert confirms == {"영향없음"}, confirms
    h.expect_batch(page, B1, "회수진행")
    h.expect_batch(page, B4, "회수진행")
    h.tab(page, "재공급 계획")
    expect(h.card(page, "고객별 재공급 순서")).not_to_contain_text("C-105")


# ---------------------------------------------------------------------------
# TC-04 시연 3-B
# ---------------------------------------------------------------------------

def test_tc04_demo3b_reject(page: Page):
    h.reset(page, START_3B)
    h.set_role(page, COMMITTEE)

    # 3-5a 거절은 사유 필수
    h.action_bar(page).get_by_role("button", name="위원회 결정 입력", exact=True).click()
    dlg = page.get_by_role("dialog")
    dlg.locator("button[aria-pressed]").filter(has_text="거절").click()
    h.fill_date(dlg, "2026-07-02")
    run = dlg.get_by_role("button", name="결정 실행")
    expect(run).to_be_disabled()
    expect(dlg).to_contain_text("거절은 사유를 적어야 실행할 수 있습니다")
    dlg.get_by_role("button", name="취소").click()
    h.expect_batch(page, B1, "상신중")

    # 3-5
    h.committee_decision(page, "2026-07-02", "거절 (원인 미규명)")
    h.expect_batch(page, B1, "조사계속")
    h.expect_batch(page, B4, "조사계속")
    expect(h.task(page, "원인 조사")).to_contain_text("품질·생산")
    h.tab(page, "재공급 계획")
    expect(page.locator("main")).to_contain_text("재공급 계획이 아직 없습니다")
    h.tab(page, "사건")

    # 3-6a
    h.set_role(page, OWNER)
    h.reply(page, h.task(page, "원인 조사"), "2026-07-10", "원인 확인")
    t = h.task(page, "원인 조사")
    h.expect_task(t, "완료")
    expect(t).to_contain_text("결과 원인 확인")
    bar = h.action_bar(page)
    expect(bar.get_by_role("button", name="안건 상신", exact=True)).to_be_visible()

    # 3-6b 재상신
    bar.get_by_role("button", name="안건 상신", exact=True).click()
    h.fill_date(bar, "2026-07-10")
    h.execute(page, bar, "안건 상신 실행")
    h.expect_batch(page, B1, "상신중")
    h.expect_batch(page, B4, "상신중")
    expect(page.locator("header")).to_contain_text("판정중")
    page.screenshot(path=str(_shot("tc04_3-6b")), full_page=True)

    # 3-6c 재상신 뒤 승인 → 시연 1의 흐름으로 이어짐
    h.set_role(page, COMMITTEE)
    h.committee_decision(page, "2026-07-11", "승인")
    h.expect_batch(page, B1, "회수진행")
    h.expect_batch(page, B4, "회수진행")
    h.tab(page, "재공급 계획")
    h.expect_plan(page, 1, "초안", PLAN_V1)
    h.tab(page, "기록")
    rows = h.log_rows(page).filter(has_text="위원회 결정 입력")
    expect(rows).to_have_count(2)


def test_tc04b_cause_not_found(page: Page):
    """3-6x 불리한 회신: 원인 미확인 → 조사계속 유지."""
    h.reset(page, START_3B)
    h.set_role(page, COMMITTEE)
    h.committee_decision(page, "2026-07-02", "거절 (원인 미규명)")
    h.set_role(page, OWNER)
    h.reply(page, h.task(page, "원인 조사"), "2026-07-10", "원인 미확인")
    h.expect_batch(page, B1, "조사계속")
    h.expect_batch(page, B4, "조사계속")


# ---------------------------------------------------------------------------
# TC-05 범위 규칙 ①
# ---------------------------------------------------------------------------

def test_tc05_other_batch(page: Page):
    h.reset(page, S0)
    open_incident(page, "B-02-2508-03")
    header = page.locator("header")
    expect(header).to_contain_text("LOT-B-2508-1")
    expect(header).to_contain_text("관찰중")
    for b in ["B-02-2508-01", "B-02-2508-03"]:
        h.expect_batch(page, b, "관찰해제")
        expect(h.batch(page, b).get_by_text("기준 미달", exact=True)).to_be_visible()
    expect(page.get_by_role("button", name="안건 상신", exact=True)).to_have_count(0)
    h.tab(page, "재공급 계획")
    expect(page.locator("main")).to_contain_text("재공급 계획이 아직 없습니다")


# ---------------------------------------------------------------------------
# TC-06 읽기 화면
# ---------------------------------------------------------------------------

def test_tc06_read_screens(page: Page):
    page.request.post("/api/scenarios/demo2")  # 2-5까지 마친 상태
    page.reload()

    # 6-1
    net = h.network(page)
    node = lambda key: net.locator(f'[data-node="{key}"]')
    expect(node("lot:LOT-B-2602-P")).to_contain_text("기점 로트")
    expect(node("customer:C-101")).to_contain_text("수주 급감 신호")
    expect(node("customer:C-104")).to_contain_text("수주 급감 신호")
    expect(node("customer:C-103")).not_to_contain_text("수주 급감 신호")
    expect(net.locator("tbody tr")).to_have_count(4)
    expect(net.get_by_role("button", name=f"{B1} → C-101", exact=True)).to_contain_text("건")
    expect(net.get_by_role("button", name=f"{B1} → C-108", exact=True)).to_have_count(0)
    for legend in ["실선 = 확인·회신확인", "점선 = 미확인·확인요청중", "옅은 회색 = 영향없음"]:
        expect(net).to_contain_text(legend)

    # 6-2
    node("customer:C-101").click()
    detail = h.card(page, h.exact("고객 · C-101"))
    expect(detail).to_contain_text("들어오는 선")
    expect(detail).to_contain_text("클레임 합 (전체 선)")
    expect(detail).to_contain_text("수주 급감 신호")
    node(f"batch:{B1}").click()
    expect(h.card(page, h.exact(f"배치 · {B1}"))).to_contain_text("사건에 묶인 이유")
    net.get_by_role("button", name=f"{B1} → C-101", exact=True).click()
    expect(h.card(page, f"{B1} → C-101")).to_contain_text("클레임 (확정/전체)")
    page.screenshot(path=str(_shot("tc06_network")), full_page=True)

    # 6-3
    h.tab(page, "기록")
    h.expect_log_count(page, 24)
    logc = h.card(page, re.compile(r"^액션 기록"))
    logc.get_by_role("button", name="사람 액션만").click()
    human = h.log_rows(page).count()
    logc.get_by_role("button", name="자동 처리만").click()
    auto = h.log_rows(page).count()
    assert human + auto == 24, (human, auto)
    expect(h.log_rows(page).first).to_contain_text(re.compile(r"\(#\d+ 뒤\)"))
    first = h.log_rows(page).first.inner_text()
    logc.get_by_role("button", name=re.compile("바꾸기")).click()
    assert h.log_rows(page).first.inner_text() != first

    # 6-4
    h.tab(page, "온톨로지")
    for title in ["객체 타입", "관계", "상태 전이", "규칙", "액션", "작업 유형", "자동 처리", "역할·출처·확인 수준", "그 밖의 정의"]:
        expect(page.locator("main").get_by_role("heading", name=title, exact=True).first).to_be_visible()
    page.locator("main").get_by_role("button", name=re.compile(r"^규칙")).click()  # 구역은 접힌 채로 시작한다
    rules = h.card(page, h.exact("규칙"))
    expect(rules.locator("tr", has_text=re.compile(r"^\s*R4")).first).to_contain_text("확장")
    page.screenshot(path=str(_shot("tc06_ontology")), full_page=True)


# ---------------------------------------------------------------------------
# TC-07 AI (E2E_AI=1일 때만 실제 호출)
# ---------------------------------------------------------------------------

ai = pytest.mark.skipif(os.environ.get("E2E_AI") != "1", reason="E2E_AI=1일 때만 AI를 실제로 호출한다")
AI_TIMEOUT = 90_000


@ai
def test_tc07_ai_drafts(page: Page):
    expect(page.locator("header")).to_contain_text("AI 사용 가능")

    # 7-1 안건 요약
    page.request.post("/api/scenarios/demo1", params={"upto": "1-1"})
    page.reload()
    bar = h.action_bar(page)
    bar.get_by_role("button", name="안건 상신", exact=True).click()
    bar.get_by_role("button", name="AI로 안건 요약").click()
    use = bar.get_by_role("button", name="이 내용 사용")
    expect(use).to_be_visible(timeout=AI_TIMEOUT)
    draft = bar.locator("div.border-dashed").filter(has_text="AI 초안").first
    for part in ["요지", "전면 회수", "부분 회수", "조사계속", "→ 회수진행", "→ 부분회수", "→ 조사계속"]:
        expect(draft.get_by_text(part, exact=True).first).to_be_visible()
    for part in ["쟁점 ", "대안 3", "확인 안 된 것 ", "기준 초과 배치 2"]:  # 구역 라벨 (뒤에 개수가 붙는다)
        expect(draft).to_contain_text(part)
    # 배치 수치는 AI 글이 아니라 시스템 값으로 초안 안에 보인다
    expect(draft).to_contain_text("배치 수치 · 시스템 계산값")
    for s in ["11.9%", "11.6%", "미상신 91일", "미상신 51일"]:
        expect(draft).to_contain_text(s)
    expect(bar).to_contain_text(re.compile(r"AI 기록 #\d+"))
    use.click()
    # 안건 요약은 작은 입력 칸 없이 큰 편집 창에서만 고친다. 취소하면 창만 닫히고 글은 폼 값에 남는다
    dialog = page.get_by_role("dialog")
    expect(dialog.get_by_role("heading", name="안건 요약 확인·수정")).to_be_visible()
    filled = dialog.get_by_label("안건 요약").input_value()
    assert len(filled) > 50 and "대안별 영향" in filled and "불확실성" in filled
    page.screenshot(path=str(_shot("tc07_agenda_edit")), full_page=True)
    dialog.get_by_role("button", name="취소").click()
    expect(dialog).to_have_count(0)
    expect(bar).to_contain_text("폼에 넣었습니다")
    expect(bar.locator("textarea")).to_have_count(0)
    bar.get_by_role("button", name="안건 요약 고치기").click()
    assert dialog.get_by_label("안건 요약").input_value() == filled
    dialog.get_by_role("button", name="취소").click()
    page.screenshot(path=str(_shot("tc07_agenda")), full_page=True)
    # 근거는 접혀 있고, 펼치면 출처 배지와 함께 보인다
    draft.get_by_role("button", name=re.compile(r"근거 \d+개 보기")).click()
    expect(draft.get_by_role("button", name="근거 접기")).to_be_visible()
    page.screenshot(path=str(_shot("tc07_agenda_evidence")), full_page=True)
    h.fill_date(bar, "2026-07-01")
    h.execute(page, bar, "안건 상신 실행")

    # 7-5 안내문 초안 (승인 뒤)
    h.set_role(page, COMMITTEE)
    h.committee_decision(page, "2026-07-02", "승인")
    h.set_role(page, OWNER)
    page.get_by_role("button", name="AI로 안내문 초안").click()
    expect(page.locator("main")).to_contain_text("실제 발송은 이 시스템의 범위 밖입니다", timeout=AI_TIMEOUT)
    expect(page.locator("main")).to_contain_text("수신 고객")

    # 7-2 회신 분류
    t = h.task(page, "출하처 확인")
    t.get_by_role("button", name="회신 입력").click()
    t.locator("textarea").fill("기록 확인 불가, 7일 추가 필요")
    t.get_by_role("button", name="AI로 회신 분류").click()
    use = t.get_by_role("button", name="이 내용 사용")
    expect(use).to_be_visible(timeout=AI_TIMEOUT)
    expect(t).to_contain_text("분류 결과")
    use.click()
    expect(t.locator("select")).to_have_value("확인 불가")

    # 7-3 해석할 수 없는 회신
    t.locator("textarea").fill("점심 먹고 연락드릴게요")
    t.get_by_role("button", name="다시 요청").click()
    expect(t).to_contain_text("AI가 분류하지 못했습니다", timeout=AI_TIMEOUT)
    expect(t.get_by_role("button", name="이 내용 사용")).to_have_count(0)
    # 다시 요청하면 이전 초안에서 넣은 결과와 AI 기록 연결이 비워져야 한다
    expect(t.locator("select")).to_have_value("")
    expect(t).not_to_contain_text("초안을 사용함")
    expect(t.get_by_role("button", name="회신 반영 실행")).to_be_disabled()
    page.screenshot(path=str(_shot("tc07_classify")), full_page=True)

    # 7-4 변경 설명 (보도 뒤 결론 유지)
    h.bar_action(page, "보도 등록", "2026-07-06", "언론 보도 (미확정, 제품·배치 지목 없음)")
    page.get_by_role("button", name="AI로 변경 설명").click()
    side = page.locator("main")
    expect(side.get_by_text("결론", exact=True)).to_be_visible(timeout=AI_TIMEOUT)
    expect(side.get_by_text("설명", exact=True)).to_be_visible()
    draft = side.locator("div.border-dashed").filter(has_text="결론").first
    expect(draft.get_by_text("유지", exact=True)).to_be_visible()
    for internal in ["quality_owner", "register_news", "current_date", "source_ref", "§"]:
        expect(draft).not_to_contain_text(internal)
    page.screenshot(path=str(_shot("tc07_review")), full_page=True)

    # 7-6 AI 기록
    # AI 요청 뒤 새로고침 없이 기록 탭에 바로 보여야 한다
    h.tab(page, "기록")
    expect(h.card(page, re.compile(r"^AI 기록")).locator("h2")).to_have_text("AI 기록 (5개)")
    expect(h.log_rows(page).filter(has_text="안건 상신").first).to_contain_text("연결된 AI 기록")


def _shot(name: str):
    from e2e.conftest import SHOTS
    SHOTS.mkdir(parents=True, exist_ok=True)
    return SHOTS / f"{name}.png"
