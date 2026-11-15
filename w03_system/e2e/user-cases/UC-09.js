// UC-09. 화면 폭을 바꿔 본다. 내용이 가장 많은 상태(시연 2 끝)에서 탭 5개가 가로로 넘치지 않는가.
await start("demo2"); // 시연 2 전체 실행: 계획 v1·v2, 기록 24건
const TABS = ["사건", "연결망", "재공급 계획", "기록", "온톨로지"];
// 1440 = 영상 촬영 크기, 1280 = 흔한 노트북. 이 둘은 합격 기준. 1024·768은 관찰만 한다
const WIDTHS = [[1440, 900, true], [1280, 720, true], [1024, 768, false], [768, 1024, false]];

/** 카드(section) 밖으로 나간 요소: 표가 카드 오른쪽으로 잘리는 경우를 잡는다 */
async function clipped() {
  return page.evaluate(() => {
    const out = [];
    for (const sec of document.querySelectorAll("main section")) {
      const box = sec.getBoundingClientRect();
      for (const el of sec.querySelectorAll("table, pre")) {
        const scroller = el.closest(".overflow-x-auto, .overflow-auto");
        const over = Math.round(el.getBoundingClientRect().right - box.right);
        if (over > 1) out.push(`${sec.querySelector("h2")?.innerText.replace(/\s+/g, " ").slice(0, 20) ?? "?"} +${over}px${scroller ? " (카드 안 가로 스크롤)" : " (잘림)"}`);
      }
    }
    return out;
  });
}

for (const [w, h, must] of WIDTHS) {
  await open(w, h);
  for (const t of TABS) {
    await tab(t);
    await sleep(300);
    const over = await overflowX();
    const cut = await clipped();
    const note = `가로 넘침 ${over}px` + (cut.length ? ` · ${cut.join(", ")}` : "");
    if (must) check(`${w}-${t}`, over <= 0, note);
    else observe(`${w}-${t}`, note);
    if (must && cut.length) observe(`${w}-${t} 카드 안`, cut.join(", "));
    await page.screenshot({ path: `data/e2e/uc/UC-09-${w}-${TABS.indexOf(t)}.png`, fullPage: true });
  }
}
await page.setViewport({ width: 1440, height: 900 });

await finish();
