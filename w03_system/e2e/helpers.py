"""화면 조작·조회 도우미. 선택자는 화면 문구와 마크업(frontend/src)에 맞춘다."""
import re

from playwright.sync_api import Locator, Page, expect

OWNER, COMMITTEE, SCM = "품질 담당자", "품질위원회", "SCM"


def exact(text: str) -> re.Pattern:
    return re.compile(rf"^\s*{re.escape(text)}\s*$")


# --- 상단 바 ---------------------------------------------------------------

def reset(page: Page, label: str) -> None:
    """초기화 메뉴에서 출발 상태를 골라 실행한다."""
    header = page.locator("header")
    header.get_by_role("button", name="초기화", exact=True).click()
    header.locator("ul").get_by_role("button", name=label, exact=True).click()
    dlg = page.get_by_role("dialog")
    expect(dlg).to_contain_text("지금 상태와 기록이 모두 지워집니다")
    dlg.get_by_role("button", name="초기화 실행").click()
    expect(dlg).to_be_hidden()


def set_role(page: Page, name: str) -> None:
    with page.expect_response(lambda r: "/api/incident" in r.url):
        page.locator("header select").select_option(label=name)


def tab(page: Page, label: str) -> None:
    page.locator("nav").get_by_role("button", name=label, exact=True).click()


def card(page: Page, title) -> Locator:
    """제목(h2)으로 카드를 찾는다. title은 문자열(포함) 또는 정규식."""
    return page.locator("main section").filter(has=page.locator("h2", has_text=title))


# --- 폼 --------------------------------------------------------------------

def fill_date(scope: Locator, date: str) -> None:
    """폼의 적용일 (첫 날짜 칸)."""
    scope.locator("input[type=date]").first.fill(date)


def pick_example(scope: Locator, label: str) -> None:
    scope.locator("button").filter(has_text=re.compile(rf"^\s*{re.escape(label)}\s*·")).click()


def execute(page: Page, scope: Locator, button: str):
    """실행 버튼을 누르고 액션 응답을 기다린다."""
    with page.expect_response(lambda r: "/api/actions/" in r.url) as info:
        scope.get_by_role("button", name=button, exact=True).click()
    return info.value


def action_bar(page: Page) -> Locator:
    """사건 탭 맨 위 사건 요약 띠의 '판정 / 새 입력' 줄 (역할에 따라 한 줄만 보일 수 있다)."""
    return page.locator("main section").filter(
        has=page.locator("span", has_text=re.compile(r"^\s*(판정|새 입력)\s*$"))).first


def bar_action(page: Page, action: str, date: str, example: str | None = None) -> None:
    """액션 줄 버튼 → (예시) → 적용일 → 실행. 인라인 폼 액션용."""
    bar = action_bar(page)
    bar.get_by_role("button", name=action, exact=True).click()
    if example:
        pick_example(bar, example)
    fill_date(bar, date)
    execute(page, bar, f"{action} 실행")


def committee_decision(page: Page, date: str, example: str) -> None:
    action_bar(page).get_by_role("button", name="위원회 결정 입력", exact=True).click()
    dlg = page.get_by_role("dialog")
    pick_example(dlg, example)
    fill_date(dlg, date)
    execute(page, dlg, "결정 실행")
    expect(dlg).to_be_hidden()


def plan_decision(page: Page, date: str, example: str) -> None:
    card(page, exact("결정")).get_by_role("button", name="결정 입력").click()
    dlg = page.get_by_role("dialog")
    pick_example(dlg, example)
    fill_date(dlg, date)
    execute(page, dlg, "결정 실행")
    expect(dlg).to_be_hidden()


# --- 배치 카드 ---------------------------------------------------------------

def batch(page: Page, batch_id: str) -> Locator:
    """배치 카드. 한 줄로 접혀 있으면 펼친다 (기준 미달 배치)."""
    c = page.locator(f'main section[data-batch="{batch_id}"]')
    expect(c).to_be_visible()
    if c.get_attribute("data-collapsed"):
        c.get_by_role("button", name="펼치기").click()
    return c


def expect_batch(page: Page, batch_id: str, state: str, rate: str | None = None) -> None:
    c = batch(page, batch_id)
    expect(c.locator("> div").first.locator("span.rounded").first).to_have_text(state)
    if rate:
        expect(c.locator("[data-rate]")).to_have_text(rate)


# --- 작업 -------------------------------------------------------------------

def tasks(page: Page) -> Locator:
    """작업 카드. 끝난 작업이 접혀 있으면 펼친다."""
    c = card(page, re.compile(r"^작업 \("))
    expect(c).to_be_visible()
    more = c.get_by_role("button", name=re.compile(r"^끝난 작업 \d+건 보기$"))
    if more.count():
        more.click()
    return c


def last_change(page: Page) -> Locator:
    """방금 바뀐 것 카드. 자세한 변경이 접혀 있으면 펼친다."""
    c = card(page, exact("방금 바뀐 것"))
    expect(c).to_be_visible()
    more = c.locator('button[aria-expanded="false"]')
    if more.count():
        more.click()
    return c


def task(page: Page, type_: str, customer: str | None = None) -> Locator:
    li = tasks(page).locator("> ul > li").filter(has_text=type_)
    if customer:
        li = li.filter(has_text=customer)
    return li


def expect_task(li: Locator, state: str) -> None:
    expect(li.locator("> div").first.locator("span.rounded")).to_have_text(state)


def reply(page: Page, li: Locator, date: str, example: str) -> None:
    li.get_by_role("button", name="회신 입력").click()
    pick_example(li, example)
    fill_date(li, date)
    execute(page, li, "회신 반영 실행")


# --- 재공급 계획 --------------------------------------------------------------

def plan_rows(page: Page) -> Locator:
    return card(page, "고객별 재공급 순서").locator("tbody tr")


def expect_plan(page: Page, version: int, state: str, lines: list[tuple[str, str]]) -> None:
    """지금 보이는 계획의 버전·상태·(고객, 완료 예상 월) 순서."""
    expect(card(page, "고객별 재공급 순서").locator("h2")).to_contain_text(f"계획 v{version}")
    selected = card(page, exact("버전")).locator("button").filter(has_text=re.compile(rf"^\s*v{version}"))
    expect(selected.locator("span.rounded")).to_have_text(state)
    rows = plan_rows(page)
    expect(rows).to_have_count(len(lines))
    for i, (customer, month) in enumerate(lines):
        expect(rows.nth(i)).to_contain_text(customer)
        expect(rows.nth(i)).to_contain_text(month)


def version_count(page: Page) -> Locator:
    return card(page, exact("버전")).locator("div").first.locator("button")


# --- 기록 -------------------------------------------------------------------

def expect_log_count(page: Page, n: int) -> None:
    expect(card(page, re.compile(r"^액션 기록")).locator("h2")).to_have_text(f"액션 기록 ({n}개)")


def log_rows(page: Page) -> Locator:
    return card(page, re.compile(r"^액션 기록")).locator("> ul > li")


def no_error(page: Page) -> None:
    expect(page.locator("main").locator("xpath=..").locator("> div[role=alert]")).to_have_count(0)
