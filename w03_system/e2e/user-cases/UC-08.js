// UC-08. 심사자가 설명 없이 배포 주소에 들어온다. 화면 안내와 예시만으로 사건을 열어 재공급 승인까지 간다.
// 단계마다 "다음에 무엇을 누를지"가 화면 글자로 읽히는지 본다. 스크립트는 화면에 보이는 버튼만 누른다.
await start(null);
await open();

// 1. 첫 화면: 무엇을 하는 곳이고 무엇부터 누르는지
const first = await text("main");
check("1-시작 안내", first.includes("사건 열기") && first.includes("배치를 골라 사건을 엽니다"), first.slice(0, 120));
check("1-첫 버튼", !!(await button("이 배치로 사건 열기", "main")));
observe("1-사건을 열면", (first.match(/사건을 열면.{0,160}/) || ["(안내 없음)"])[0]);
await click("이 배치로 사건 열기", "main");
check("1-사건 열림", await waitText("INC-001", "header"));

// 2. 사건이 열린 뒤: 다음 행동이 보이는가
const status = async () => (await text("main section")).slice(0, 260);
observe("2-사건 현황 (열린 직후)", await status());
check("2-다음 버튼", !!(await button("안건 상신", "main")));
await click("안건 상신", "main");
await click("안건 상신 실행", "main");
check("2-상신됨", await waitText("상신중", "main"));

// 3. 여기서 막힌다: 품질 담당자에게는 누를 결정 버튼이 없다. 역할을 바꾸라는 안내가 있는가
const waiting = await status();
observe("3-사건 현황 (상신 뒤)", waiting);
check("3-누가 결정하는지 보임", waiting.includes("위원회가 판정"), "사건 현황에 다음 결정권자(위원회)가 적혀 있어야 한다");
check("3-담당자에게 결정 버튼 없음", !(await button("위원회 결정 입력", "main")));
const hint3 = await text("main [data-role-hint]");
check("3-역할 전환 안내", hint3.includes("다음: 품질위원회 결정") && !!(await button("품질위원회 역할로 바꾸기", "main [data-role-hint]")), hint3);
await click("품질위원회 역할로 바꾸기", "main [data-role-hint]"); // 안내 줄의 버튼으로 역할을 바꾼다
await sleep(500);
check("3-역할 바뀜", (await page.$eval("header select", s => s.value)) === COMMITTEE);
check("3-위원회 버튼", !!(await button("위원회 결정 입력", "main")));
check("3-결정권자에게는 안내 없음", !(await page.$("main [data-role-hint]")));
await click("위원회 결정 입력", "main");
await page.waitForSelector(DIALOG);
check("3-예시 줄 없음", !(await has("시연용 예시", DIALOG)) && !!(await button("승인", DIALOG, false)));
await click("승인", DIALOG, false); // 결과 선택 버튼 '승인'
await click("승인 결정 실행", DIALOG);
check("3-회수 시작", await gone(DIALOG) && await waitText("회수진행", "main"));

// 4. 위원회 승인 뒤: 재공급 계획으로 가야 한다는 것이 보이는가
observe("4-사건 현황 (승인 뒤)", await status());
const navText = await text("nav");
observe("4-탭 표시", `탭 줄: "${navText}"`);
const hint4 = await text("main [data-role-hint]");
check("4-역할 전환 안내", hint4.includes("다음: SCM 결정") && hint4.includes("재공급 계획 탭"), hint4);
await setRole(SCM);
await tab("재공급 계획");
check("4-계획 초안", await waitText("계획 v1", "main") && !!(await button("결정 입력", "main")));
check("4-경고가 먼저 보임", await has("출하 경위 확인 대기", "main"));
await click("결정 입력", "main");
await page.waitForSelector(DIALOG);
await click("승인 (출고 조건 충족)", DIALOG);
await click("승인 결정 실행", DIALOG);
check("4-계획 확정", await gone(DIALOG) && planState(await view(SCM), 1) === "확정");

// 5. 끝났다는 것이 보이는가
await tab("사건");
observe("5-사건 현황 (계획 확정 뒤)", await status());
check("5-상태", await has("복구계획확정", "body"));
const v = await view();
observe("5-남은 일", `열린 작업 ${v.tasks.filter(t => t.state === "열림").length}건: ${v.tasks.filter(t => t.state === "열림").map(t => t.type).join(", ")}`);

await finish();
