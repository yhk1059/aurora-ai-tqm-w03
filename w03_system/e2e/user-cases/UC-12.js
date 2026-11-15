// UC-12. AI가 회신을 분류하지 못한다. 담당자가 직접 골라 반영한다.
await start("demo3a", { setupOnly: true }); // 출하처 확인(물류) 작업이 열려 있다
await open();
const row = await taskRow("출하처 확인");
await click("회신 입력", row);

// 1. 문장이 없으면 AI에 물을 수 없다
let ai = await button("AI로 회신 분류", row);
check("1-문장 없이는 AI 버튼 꺼짐", ai?.disabled === true && await has("회신 문장을 먼저 적으세요", row), JSON.stringify(ai));

// 2. 뜻이 없는 회신을 적고 AI에 묻는다
await fill("회신 문장", "점심 먹고 연락드릴게요", row);
await click("AI로 회신 분류", row);
check("2-분류 못함 안내", await waitText("AI가 분류하지 못했습니다", row, AI_WAIT), (await text(row)).slice(-200));
check("2-사용 버튼 없음", !(await button("이 내용 사용", row)));
const selected = await page.$eval(await field("회신 결과", row), s => s.value);
check("2-결과 칸은 비어 있음", selected === "", `"${selected}"`);
check("2-실행 버튼 꺼짐", (await button("회신 반영 실행", row))?.disabled === true);
check("2-작업은 그대로", taskOf(await view(), "출하처 확인")?.state === "열림");

// 3. 담당자가 직접 고른다
await choose("회신 결과", "확인 불가", row);
await fill("적용일", "2026-07-08", "header");
await click("회신 반영 실행", row);
await sleep(600);
const v = await view();
const t = taskOf(v, "출하처 확인");
check("3-사람이 고른 결과로 반영", t?.state === "열림" && t?.due_date === "2026-07-15", `${t?.state} 기한 ${t?.due_date}`);
const ev = v.events.filter(e => e.type === "회신").pop();
check("3-AI 기록과 연결되지 않음", ev && !ev.ai_log_id, `ai_log_id = ${ev?.ai_log_id}`);
check("3-AI 요청은 기록에 남음", aiCount(v) === 1, `AI 기록 ${aiCount(v)}건`);

await finish();
