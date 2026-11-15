// UC-07. 진행 중에 실수로 초기화를 누르거나, 폼을 쓰다가 새로고침한다.
await start("demo2", { setupOnly: true }); // 계획 v1 확정, 기록 15건
await open();
const before = await view();

// 1. 초기화 메뉴를 열고 출발 상태를 골랐다가 취소한다
await click("초기화", "header");
await click("빈 상태", "header ul", false);
await page.waitForSelector(DIALOG);
check("1-경고 문구", await has("지금 상태와 기록이 모두 지워집니다", DIALOG), await text(DIALOG));
await click("취소", DIALOG);
check("1-취소로 닫힘", await gone(DIALOG));
let v = await view();
check("1-기록 유지", logCount(v) === logCount(before) && v.incident?.id === before.incident.id, `기록 ${logCount(v)}건`);

// 2. 폼을 쓰다가 새로고침한다: 쓰던 글은 사라져도 사건 상태는 그대로다
await click("보도 등록", "main");
await sleep(300);
await page.reload();
await sleep(700);
v = await view();
check("2-새로고침 뒤 상태", logCount(v) === logCount(before) && await waitText(before.incident.id, "header"), `기록 ${logCount(v)}건`);
observe("2-역할", `새로고침 뒤 역할 선택: ${await page.$eval("header select", s => s.options[s.selectedIndex].textContent)}`);

// 3. 역할을 바꾼 채 새로고침하면 역할이 어떻게 되는가
await setRole(SCM);
await page.reload();
await sleep(700);
observe("3-역할 유지", `SCM으로 바꾸고 새로고침한 뒤: ${await page.$eval("header select", s => s.options[s.selectedIndex].textContent)}`);

// 4. 탭을 옮긴 채 새로고침
await tab("기록");
await page.reload();
await sleep(700);
const onLog = await has("액션 기록", "main");
observe("4-탭 유지", onLog ? "새로고침 뒤에도 기록 탭" : "새로고침 뒤 사건 탭으로 돌아감");

await finish();
