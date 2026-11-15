// UC-13. AI가 끊기거나, 오류를 내거나, 늦게 답한다. 업무는 AI 없이도 이어져야 한다.
// 끊김·오류·지연은 브라우저에서 /api/ai/ 요청을 가로채 만든다 (마지막 단계만 실제 서버로 간다).
await start("demo1", { upto: "1-5" }); // 회수 승인·안내 대상 결정 뒤. 안내 대상 결정 작업에 AI로 안내문 초안 버튼이 있다
await open();
await interceptAi();
const before = await view();

// 1. 연결이 끊긴다
aiMode = "abort";
await click("AI로 안내문 초안", "main");
check("1-끊김 안내", await waitText("서버에 연결할 수 없습니다", "main [role=alert]"), await text("main [role=alert]"));
check("1-다시 요청할 수 있음", !!(await button("다시 요청", "main")));
let v = await view();
check("1-상태 불변", logCount(v) === logCount(before) && aiCount(v) === aiCount(before), `기록 ${logCount(v)}건, AI 기록 ${aiCount(v)}건`);

// 2. AI 쪽 오류 (서버가 500을 돌려준다)
aiMode = "error";
expectedApiErrors += 1;
await click("다시 요청", "main");
check("2-오류 안내", await waitText("API 오류", "main [role=alert]"), await text("main [role=alert]"));
check("2-초안을 지어내지 않음", !(await has("안내문 초안", "main [data-ai-draft]")), "오류일 때 초안 칸에 안내문이 보이면 안 된다");

// 3. AI 없이 업무를 계속한다
check("3-다른 입력은 그대로 가능", (await button("클레임 등록", "main"))?.disabled === false);

// 4. 늦게 답한다 (3초)
aiMode = 3000;
await click("다시 요청", "main");
await sleep(500);
const during = await text("main");
check("4-작성 중 표시", during.includes("AI가 작성 중"), during.match(/.{0,20}작성 중.{0,20}/)?.[0] ?? "(표시 없음)");
const again = await button("다시 요청", "main");
observe("4-기다리는 동안", `다시 요청 버튼: ${again ? (again.disabled ? "꺼짐" : "켜짐 (여러 번 누를 수 있음)") : "숨김"}, 클레임 등록 버튼: ${(await button("클레임 등록", "main"))?.disabled ? "꺼짐" : "켜짐"}`);
check("4-답 도착", await waitText("안내문 초안", "main [data-ai-draft]", AI_WAIT + 4000));
const draft = await text("main [data-ai-draft]");
check("4-수신 고객은 입력 그대로", /C-101, C-102, C-103, C-104, C-108/.test(draft), draft.slice(0, 120));
v = await view();
check("4-초안만으로 상태 불변", logCount(v) === logCount(before), `기록 ${logCount(v)}건`);
observe("4-AI 기록", `끊김 1회·오류 1회·성공 1회 뒤 AI 기록 ${aiCount(v) - aiCount(before)}건 (가로챈 실패는 서버에 닿지 않아 기록되지 않는다)`);
aiMode = "pass";

await finish();
