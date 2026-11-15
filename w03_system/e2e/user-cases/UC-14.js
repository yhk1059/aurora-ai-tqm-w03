// UC-14. AI가 하지 않는 일: 결정하지 않고, 보내지 않고, 상태를 바꾸지 않는다.

// 1. 위원회 결정 창에는 AI 버튼이 없다
const aiButtons = scope => page.evaluate(s => [...document.querySelectorAll(s + " button")].filter(b => b.offsetParent && /AI/.test(b.textContent)).map(b => b.textContent.trim()), scope);
await start("demo3a", { setupOnly: true });
await open();
await setRole(COMMITTEE);
await click("위원회 결정 입력", "main");
await page.waitForSelector(DIALOG);
check("1-위원회 결정 창", (await aiButtons(DIALOG)).length === 0, (await aiButtons(DIALOG)).join(", "));
await click("취소", DIALOG);
await gone(DIALOG);

// 2. SCM 결정 창에도 없다
await start("demo1", { upto: "1-5" });
await page.reload();
await sleep(700);
await setRole(SCM);
await tab("재공급 계획");
await click("결정 입력", "main");
await page.waitForSelector(DIALOG);
check("2-SCM 결정 창", (await aiButtons(DIALOG)).length === 0, (await aiButtons(DIALOG)).join(", "));
await click("취소", DIALOG);
await gone(DIALOG);

// 3. 안내문 초안: 글만 만들고 보내지 않는다
await setRole(OWNER);
await tab("사건");
const before = await view();
await click("AI로 안내문 초안", "main");
check("3-초안 도착", await waitText("실제 발송은 이 시스템의 범위 밖입니다", "main", AI_WAIT));
const draft = await text("main [data-ai-draft]");
check("3-AI 글이라는 표시", draft.includes("AI 초안") && /AI 기록 #\d+/.test(draft), draft.slice(0, 60));
const expected = before.recall_quantities.map(r => r.customer_id).sort();
const shown = [...new Set((draft.match(/수신 고객.{0,80}/)?.[0] ?? "").match(/C-\d{3}/g) ?? [])].sort();
check("3-수신 고객 = 회수 대상 고객", JSON.stringify(shown) === JSON.stringify(expected), `화면 ${shown.join(",")} / 회수 대상 ${expected.join(",")}`);
check("3-보류 고객은 빠짐", !shown.includes("C-105"), "출하처 미확인 C-105는 수신 고객에 없어야 한다");
const send = await page.evaluate(() => [...document.querySelectorAll("main button")].filter(b => b.offsetParent && /발송|보내기|전송/.test(b.textContent)).map(b => b.textContent.trim()));
check("3-보내는 버튼 없음", send.length === 0, send.join(", "));
const v = await view();
check("3-상태 불변", logCount(v) === logCount(before) && v.tasks.filter(t => t.state === "열림").length === before.tasks.filter(t => t.state === "열림").length, `기록 ${logCount(v)}건`);
check("3-AI 요청은 기록에 남음", aiCount(v) === aiCount(before) + 1, `AI 기록 ${aiCount(v)}건`);

await finish();
