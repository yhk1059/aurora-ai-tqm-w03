// UC-04. 위원회가 결정 창에서 마음을 바꿔 닫는다. 닫는 방법 세 가지 모두 아무것도 바꾸지 않아야 한다.
await start("demo3a", { setupOnly: true });
await open();
await setRole(COMMITTEE);
const before = await view(COMMITTEE);
const typed = "원인이 규명되지 않아 보류 (작성 중)";

async function openAndType() {
  await click("위원회 결정 입력", "main");
  await page.waitForSelector(DIALOG);
  await click("거절", DIALOG, false);
  await fill("사유", typed, DIALOG);
}
async function unchanged(id) {
  const v = await view(COMMITTEE);
  check(id, logCount(v) === logCount(before) && batchState(v, "B-02-2602-01") === "상신중" && v.decisions.length === before.decisions.length,
    `기록 ${logCount(v)}건, 배치 ${batchState(v, "B-02-2602-01")}`);
}

// 1. 취소 버튼
await openAndType();
await click("취소", DIALOG);
check("1-취소로 닫힘", await gone(DIALOG));
await unchanged("1-상태 불변");

// 2. 다시 열면 쓰던 글이 남아 있는가 (합격·불합격 아님)
await click("위원회 결정 입력", "main");
await page.waitForSelector(DIALOG);
const kept = await page.evaluate(d => [...document.querySelectorAll(d + " textarea, " + d + " input[type=text]")].map(e => e.value).join("|"), DIALOG);
observe("2-다시 열었을 때", kept.includes("작성 중") ? "쓰던 사유가 남아 있음" : "쓰던 사유가 지워져 있음 (빈 창으로 다시 시작)");
await click("취소", DIALOG);
await gone(DIALOG);

// 3. 창 밖(어두운 배경) 클릭
await openAndType();
await page.mouse.click(20, 500);
await sleep(300);
const closedByBackdrop = !(await dialogOpen());
observe("3-창 밖 클릭", closedByBackdrop ? "창이 닫히고 쓰던 사유가 사라짐 (실수로 누르면 다시 써야 함)" : "창이 그대로 열려 있음");
await unchanged("3-상태 불변");
if (!closedByBackdrop) { await click("취소", DIALOG); await gone(DIALOG); }

// 4. Esc 키
await openAndType();
await page.keyboard.press("Escape");
await sleep(300);
const closedByEsc = !(await dialogOpen());
observe("4-Esc 키", closedByEsc ? "창이 닫힘" : "Esc로 닫히지 않음 (취소 버튼이나 창 밖 클릭으로만 닫힘)");
await unchanged("4-상태 불변");

await finish();
