// UC-10. 화면 품질: 아주 긴 회신 문장, 출처 표시, 입력 칸의 이름.
await start("demo1", { upto: "1-3" });
await open();

// 1. 띄어쓰기 없는 긴 문장을 회신으로 넣는다 (메일 본문을 통째로 붙여 넣은 경우)
const long = "회수배치고객다섯곳에만안내하고관찰해제배치고객은안내하지않기로영업본부장과합의함".repeat(8); // 약 330자
const row = await taskRow("안내 대상 결정");
await click("회신 입력", row);
await fill("회신 문장", long, row);
await choose("회신 결과", "회수 배치 고객만", row);
await click("회신 반영 실행", row);
await sleep(600);
check("1-반영됨", taskOf(await view(), "안내 대상 결정")?.state === "완료");
check("1-가로 넘침 없음", (await overflowX()) <= 0, `가로 넘침 ${await overflowX()}px`);
const rowOver = await page.evaluate(sel => { const li = document.querySelector(sel); const sec = li.closest("section"); return Math.round(li.scrollWidth - li.clientWidth) + "/" + Math.round(li.getBoundingClientRect().right - sec.getBoundingClientRect().right); }, await taskRow("안내 대상 결정"));
check("1-작업 줄 안에 들어감", rowOver.split("/").every(n => Number(n) <= 1), `줄 안 넘침/카드 밖 = ${rowOver}px`);
await tab("기록");
check("1-기록 탭 넘침 없음", (await overflowX()) <= 0, `가로 넘침 ${await overflowX()}px`);

// 2. 출처 표시: 가정·모의 값에 배지가 붙어 있고, 누르면 근거가 보인다
await tab("재공급 계획");
const badges = await page.evaluate(() => [...document.querySelectorAll("main button")].map(b => b.textContent.trim()).filter(t => /^(원본|도출|가정|모의|시스템)/.test(t)));
check("2-출처 배지", badges.some(b => b.startsWith("가정")) && badges.some(b => b === "원본" || b === "도출"), badges.join(", "));
// 근거가 있는 배지는 title이 '근거 보기'다. 하나를 눌러 근거가 펼쳐지는지 본다
const detail = await page.evaluate(() => {
  const all = [...document.querySelectorAll("main button")].filter(b => /^(원본|도출|가정|모의|시스템)/.test(b.textContent.trim()));
  const withDetail = all.filter(b => b.title === "근거 보기");
  document.querySelectorAll("[data-uc-badge]").forEach(b => b.removeAttribute("data-uc-badge"));
  if (withDetail[0]) withDetail[0].setAttribute("data-uc-badge", "1");
  return { first: withDetail[0]?.textContent.trim(), noDetail: all.filter(b => b.title !== "근거 보기").map(b => b.textContent.trim()) };
});
const beforeClick = await text("body");
await page.click("[data-uc-badge]");
await sleep(300);
const afterClick = await text("body");
check("2-배지를 누르면 근거", afterClick.length > beforeClick.length, `"${detail.first}" 누른 뒤 늘어난 글자 ${afterClick.length - beforeClick.length}자`);
observe("2-눌러도 근거가 없는 배지", detail.noDetail.length ? `재공급 계획 탭에 ${detail.noDetail.length}개: ${detail.noDetail.join(", ")} (가정 ID만 보이고 가정 내용은 펼쳐지지 않음)` : "없음");
await tab("사건");
const taskText = await text(await taskRow("안내 대상 결정"));
const taskBadges = await page.evaluate(sel => [...document.querySelectorAll(sel + " button")].map(b => b.textContent.trim()), await taskRow("안내 대상 결정"));
observe("2-회신의 출처", `손으로 넣은 회신 줄의 배지: [${taskBadges.join(", ")}] (모의 입력이라는 표시가 ${/모의/.test(taskText + taskBadges.join()) ? "있음" : "없음"})`);

// 3. 입력 칸의 이름 (화면 낭독기·자동화 도구가 칸을 이름으로 찾을 수 있는가)
await setRole(COMMITTEE);
await start("demo3a", { setupOnly: true });
await page.reload();
await sleep(700);
await setRole(COMMITTEE);
await click("위원회 결정 입력", "main");
await page.waitForSelector(DIALOG);
const unnamed = await page.evaluate(d => [...document.querySelectorAll(d + " input, " + d + " textarea, " + d + " select")]
  .filter(c => !c.getAttribute("aria-label") && !c.labels?.length && !c.getAttribute("aria-labelledby"))
  .map(c => c.tagName.toLowerCase() + ":" + (c.parentElement.innerText.replace(/\s+/g, " ").slice(0, 12) || "?")), DIALOG);
observe("3-이름 없는 입력 칸", unnamed.length ? `결정 창에 ${unnamed.length}개: ${unnamed.join(", ")}` : "없음");
const dlg = await page.evaluate(d => { const e = document.querySelector(d); return { labelled: !!(e.getAttribute("aria-label") || e.getAttribute("aria-labelledby")), focusInside: e.contains(document.activeElement) }; }, DIALOG);
observe("3-결정 창", `창 이름 ${dlg.labelled ? "있음" : "없음"}, 열렸을 때 초점이 창 안에 ${dlg.focusInside ? "있음" : "없음"}`);
await click("취소", DIALOG);

await finish();
