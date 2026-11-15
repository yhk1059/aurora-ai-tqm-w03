// UC-01. SCM 담당자가 처음 들어와, 경고를 읽고 근거를 직접 써서 재공급 계획을 승인한다.
await start("demo1", { upto: "1-5" });
await open();
await setRole(SCM);

// 1. 사건 탭: 내 일이 무엇인지 보이는가
const row = await taskRow("재공급 요청");
check("1-내 작업", (await text(row)).includes("열림") && (await text(row)).includes("SCM"), await text(row));
check("1-남의 작업", !(await button("회신 입력", "main")), "SCM에게 회신 입력 버튼이 보이지 않아야 한다");

// 2. 재공급 계획 탭: 경고가 승인 전에 보이는가
await tab("재공급 계획");
check("2-경고 띠", await waitText("출하 경위 확인 대기 1건", "main [data-hold-shipment]"), await text("main [data-hold-shipment]"));

// 3. 결정 창: 근거 없이는 승인할 수 없다 (공백만 넣어도)
await click("결정 입력", "main");
check("3-판단 근거", await waitText("확인 대기", DIALOG) && await has("출하 경위", DIALOG));
await click("승인", DIALOG, false);
let run = await button("승인 결정 실행", DIALOG);
check("3-빈 근거", run?.disabled === true && await has("승인하려면 근거를 적어야 합니다", DIALOG), JSON.stringify(run));
await fill("근거", "   ", DIALOG);
run = await button("승인 결정 실행", DIALOG);
check("3-공백 근거", run?.disabled === true, JSON.stringify(run));

// 4. 예시가 아니라 자기 말로 근거를 쓴다
const reason = "대체 로트 QC 합격 확인. 출하 경위는 회신 오면 다시 본다 (SCM 직접 작성)";
await fill("근거", reason, DIALOG);
await fill("적용일", "2026-07-03", "header");
run = await button("승인 결정 실행", DIALOG);
check("4-버튼 켜짐", run?.disabled === false, JSON.stringify(run));
await click("승인 결정 실행", DIALOG);
check("4-창 닫힘", await gone(DIALOG));

// 5. 결과: 계획 확정, 내가 쓴 근거가 화면과 기록에 그대로 남는다
const v = await view(SCM);
check("5-계획 확정", planState(v, 1) === "확정", planState(v, 1));
check("5-화면 근거", await waitText(reason, "main"));
const last = v.log.actions.filter(a => a.action === "plan_decision").pop();
check("5-기록 규칙", JSON.stringify(last).includes("R11-1"), "승인 기록에 R11-1이 남아야 한다");
check("5-작업 완료", taskOf(v, "재공급 요청")?.state === "완료", taskOf(v, "재공급 요청")?.state);
await tab("기록");
check("5-기록 탭", await waitText("재공급 계획 결정 입력", "main"));

await finish();
