// UC-06. 두 사람이 같은 계획을 본다. 한 사람이 결정 창을 열어 둔 사이 다른 사람이 먼저 승인한다.
await start("demo1", { upto: "1-5" });
await open();
await setRole(SCM);
await tab("재공급 계획");

// 1. 내 화면: 결정 창을 열고 근거까지 써 둔다
await click("결정 입력", "main");
await page.waitForSelector(DIALOG);
await click("승인", DIALOG, false);
await fill("근거", "늦게 누르는 사람의 승인 근거", DIALOG);
await fill("적용일", "2026-07-03", "header");

// 2. 그 사이 다른 SCM 담당자가 먼저 승인한다 (다른 창을 API 호출로 대신한다)
const plan = (await view(SCM)).plans[0].id;
const other = await api("POST", "/api/actions/plan_decision", { actor: SCM, inputs: { plan_id: plan, result: "승인", reason: "먼저 누른 사람의 승인 근거", applied_date: "2026-07-03" } });
check("2-먼저 승인됨", other.status === 200, String(other.status));

// 3. 내 화면에서 늦게 실행한다: 거부되고, 이유가 보여야 한다
expectedApiErrors += 1;
await click("승인 결정 실행", DIALOG);
await sleep(700);
const stillOpen = await dialogOpen();
const msg = await text(stillOpen ? DIALOG + " [role=alert]" : "[role=alert]");
check("3-이유가 보임", msg.length > 0, `오류 문구: "${msg}" (창 ${stillOpen ? "열린 채" : "닫힘"})`);
observe("3-오류 문구", msg);

// 4. 결과: 결정은 한 번만 기록되고, 먼저 누른 사람의 근거가 남는다
const v = await view(SCM);
const decisions = v.log.actions.filter(a => a.action === "plan_decision");
check("4-결정 1건", decisions.length === 1 && v.plans.length === 1 && planState(v, 1) === "확정", `결정 ${decisions.length}건, 계획 ${v.plans.length}개 ${planState(v, 1)}`);
check("4-먼저 쓴 근거", JSON.stringify(decisions[0]).includes("먼저 누른 사람"));

// 5. 창을 닫고 새로고침하면 지금 상태가 보인다
if (stillOpen) { await click("취소", DIALOG); await gone(DIALOG); }
await page.reload();
await sleep(700);
await setRole(SCM);
await tab("재공급 계획");
check("5-새로고침 뒤", await waitText("먼저 누른 사람의 승인 근거", "main") && !(await button("결정 입력", "main")), "확정된 계획에 결정 입력 버튼이 없어야 한다");
observe("5-닫은 직후 화면", "취소로 닫은 직후(새로고침 전)에 화면이 옛 상태(초안)를 계속 보이는지는 캡처로 확인");

await finish();
