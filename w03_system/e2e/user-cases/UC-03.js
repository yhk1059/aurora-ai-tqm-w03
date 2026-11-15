// UC-03. 품질 담당자가 예시를 쓰지 않고, 받은 회신을 손으로 옮겨 적는다.
await start("demo1", { upto: "1-3" }); // 위원회 승인 뒤. 안내 대상 결정(영업) 작업이 열려 있다
await open();

const row = await taskRow("안내 대상 결정");
await click("회신 입력", row);

// 1. 문장만 쓰고 결과를 고르지 않으면 실행할 수 없다
await fill("회신 문장", "영업에서 전화로 회신: 회수 배치를 받은 고객 5곳에만 안내하기로 함", row);
let run = await button("회신 반영 실행", row);
check("1-결과 없이 실행 불가", run?.disabled === true, JSON.stringify(run));

// 2. 결과를 직접 고른다
const options = await page.$eval(await field("회신 결과", row), s => [...s.options].map(o => o.textContent.trim()));
check("2-선택지", options.includes("회수 배치 고객만") && options.length >= 3, options.join(" / "));
await choose("회신 결과", "회수 배치 고객만", row);
await fill("적용일", "2026-07-02", row);
run = await button("회신 반영 실행", row);
check("2-실행 가능", run?.disabled === false, JSON.stringify(run));
await click("회신 반영 실행", row);
await sleep(500);

// 3. 결과: 작업 완료, 손으로 쓴 문장이 그대로 남는다
const v = await view();
const t = taskOf(v, "안내 대상 결정");
check("3-작업 완료", t?.state === "완료" && t?.result === "회수 배치 고객만", `${t?.state} ${t?.result}`);
check("3-문장 보존", t?.reply?.includes("전화로 회신"), t?.reply);
const done = await text(await taskRow("안내 대상 결정"));
check("3-화면 표시", done.includes("완료") && done.includes("회수 배치 고객만"), done);
observe("3-손 입력의 출처 표시", `완료된 작업 줄: "${done}"`);

// 4. 끝난 작업에는 다시 회신할 수 없다
check("4-재회신 버튼 없음", !(await button("회신 입력", await taskRow("안내 대상 결정"))));
const r = await api("POST", "/api/actions/apply_reply", { actor: OWNER, inputs: { task_id: t.id, reply_text: "다시 보냄", result: "전체 고객", applied_date: "2026-07-02" } });
check("4-서버 거부", r.status >= 400, `${r.status} ${r.data?.error?.message}`);
check("4-결과 유지", taskOf(await view(), "안내 대상 결정")?.result === "회수 배치 고객만");

await finish();
