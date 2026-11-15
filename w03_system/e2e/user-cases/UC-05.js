// UC-05. 날짜를 잘못 넣는다: 사건의 현재 날짜보다 앞선 날, 빈 날짜.
await start("demo1", { upto: "1-3" }); // 현재 적용일 2026-07-02
await open();
const before = await view();
check("0-출발 날짜", before.incident.current_date === "2026-07-02", before.incident.current_date);

// 1. 과거 날짜로 회신 반영
const row = await taskRow("안내 대상 결정");
await click("회신 입력", row);
await click("회수 배치 고객만", row, false);
await fill("적용일", "2026-06-30", row);
const run = await button("회신 반영 실행", row);
if (run && !run.disabled) {
  expectedApiErrors += 1;
  await click("회신 반영 실행", row);
  await sleep(600);
}
let v = await view();
check("1-과거 날짜 거부", taskOf(v, "안내 대상 결정")?.state === "열림" && logCount(v) === logCount(before),
  `작업 ${taskOf(v, "안내 대상 결정")?.state}, 기록 ${logCount(v)}건`);
const alert = await text("main [role=alert]");
check("1-이유가 보임", alert.length > 0 && /날짜|적용일|2026-07-02/.test(alert), `오류 문구: "${alert}"`);
observe("1-오류 문구", alert);

// 2. 날짜를 고치면 같은 폼에서 그대로 이어서 실행된다 (다시 쓰지 않아도 됨)
await fill("적용일", "2026-07-02", row);
await click("회신 반영 실행", row);
await sleep(600);
v = await view();
check("2-고친 뒤 실행", taskOf(v, "안내 대상 결정")?.state === "완료", taskOf(v, "안내 대상 결정")?.state);

// 3. 날짜를 비운다
await click("클레임 등록", "main");
await sleep(300);
const dateSel = await field("적용일", "main");
await page.$eval(dateSel, el => { const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set; set.call(el, ""); el.dispatchEvent(new Event("input", { bubbles: true })); el.dispatchEvent(new Event("change", { bubbles: true })); });
await sleep(200);
const reg = await button("클레임 등록 실행", "main");
observe("3-빈 날짜", `적용일을 비웠을 때 실행 버튼: ${reg ? (reg.disabled ? "꺼짐" : "켜짐") : "없음"}`);
check("3-빈 날짜로 기록 안 됨", logCount(await view()) === logCount(v));

await finish();
