// UC-02. 역할마다 자기 일만 할 수 있다 (화면에 버튼이 없고, 서버도 막는다).
await start("demo3a", { setupOnly: true }); // 배치 2개 상신중, 위원회 결정 대기
await open();

// 1. 품질 담당자: 입력은 하지만 결정은 못 한다
check("1-담당자 결정 버튼 없음", !(await button("위원회 결정 입력", "main")));
check("1-담당자 회신 입력", !!(await button("회신 입력", "main")));
check("1-담당자 클레임 등록", !!(await button("클레임 등록", "main")));

// 2. 품질위원회: 결정만 한다
await setRole(COMMITTEE);
check("2-위원회 결정 버튼", !!(await button("위원회 결정 입력", "main")));
check("2-위원회 회신 입력 없음", !(await button("회신 입력", "main")));
check("2-위원회 클레임 등록 없음", !(await button("클레임 등록", "main")));

// 3. SCM: 지금은 할 일이 없다. 그 사실이 화면에서 읽히는가
await setRole(SCM);
check("3-SCM 결정 버튼 없음", !(await button("위원회 결정 입력", "main")));
check("3-SCM 회신 입력 없음", !(await button("회신 입력", "main")));
await tab("재공급 계획");
check("3-SCM 계획 없음", await waitText("재공급 계획이 아직 없습니다", "main"));
await tab("사건");
const main = await text("main");
const hint = main.match(/[^.·]{0,30}(할 일이 없|기다리|대기)[^.·]{0,30}/);
observe("3-SCM 할 일 없음 안내", hint ? `읽힐 만한 문구: "${hint[0].trim()}"` : "사건 탭에 'SCM이 지금 할 일이 없다'는 문구가 따로 없음 (버튼이 없을 뿐)");

// 4. 화면을 거치지 않고 서버에 직접 보내도 막힌다
const before = await view();
const r = await api("POST", "/api/actions/committee_decision", { actor: SCM, inputs: { result: "승인", applied_date: "2026-07-02" } });
check("4-서버 거부", r.status === 403 && r.data?.error?.code === "forbidden", `${r.status} ${JSON.stringify(r.data?.error)}`);
const after = await view();
check("4-상태 불변", logCount(before) === logCount(after) && batchState(after, "B-02-2602-01") === "상신중", batchState(after, "B-02-2602-01"));

await finish();
