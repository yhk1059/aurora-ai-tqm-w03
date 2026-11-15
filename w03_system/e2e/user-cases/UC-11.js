// UC-11. 품질 담당자가 AI 안건 요약을 받는다. 한 번은 쓰지 않고 상신하고, 한 번은 고쳐서 상신한다.
const FORM = "main [data-form-slot]";
async function askSummary() {
  await start("demo1", { upto: "1-1" });
  await open();
  await click("안건 상신", "main");
  await click("AI로 안건 요약", FORM);
  return waitText("이 내용 사용", FORM, AI_WAIT);
}
const lastSubmit = v => v.log.actions.filter(a => a.action === "submit_agenda").pop();

// --- A. 초안을 받았지만 쓰지 않는다 ---
check("A1-초안 도착", await askSummary());
const draft = await text("main [data-ai-draft]");
check("A1-AI 글이라는 표시", draft.includes("AI 초안") && draft.includes("검토 후 사용") && /AI 기록 #\d+/.test(draft), draft.slice(0, 80));
check("A1-수치는 시스템 값", draft.includes("배치 수치 · 시스템 계산값") && draft.includes("11.9%") && draft.includes("11.6%"));
let v = await view();
check("A1-요청만으로는 아무것도 안 바뀜", batchState(v, "B-02-2602-01") === "기준초과(미상신)" && !lastSubmit(v), batchState(v, "B-02-2602-01"));
check("A1-AI 기록 1건", aiCount(v) === 1, `AI 기록 ${aiCount(v)}건`);
// 초안을 그대로 둔 채 실행
await fill("적용일", "2026-07-01", FORM);
await click("안건 상신 실행", FORM);
await sleep(600);
v = await view();
const a = lastSubmit(v);
check("A2-상신됨", batchState(v, "B-02-2602-01") === "상신중", batchState(v, "B-02-2602-01"));
check("A2-초안이 안건에 들어가지 않음", !a?.inputs.agenda_summary && !a?.inputs.ai_log_id, JSON.stringify({ summary: a?.inputs.agenda_summary ?? null, ai_log_id: a?.inputs.ai_log_id ?? null }));
await tab("기록");
check("A2-기록에 AI 연결 없음", !(await has("연결된 AI 기록", "main")));
check("A2-AI 기록은 남음", await has("AI 기록 (1개)", "main"));

// --- B. 초안을 가져와 고쳐서 상신한다 ---
check("B1-초안 도착", await askSummary());
await click("이 내용 사용", FORM);
await page.waitForSelector(DIALOG);
const original = await page.$eval(DIALOG + " textarea", t => t.value);
check("B1-편집 창에 초안", original.length > 50, `${original.length}자`);
const edited = "담당자 수정본: 배치 2개 전면 회수를 상신함. C-105 출하처는 물류 확인 중.";
await page.fill(DIALOG + " textarea", edited);
await click("안건 상신 실행", DIALOG);
await gone(DIALOG);
await sleep(600);
v = await view();
const b = lastSubmit(v);
check("B2-상신됨", batchState(v, "B-02-2602-01") === "상신중", batchState(v, "B-02-2602-01"));
check("B2-고친 글이 올라감", b?.inputs.agenda_summary === edited, (b?.inputs.agenda_summary ?? "").slice(0, 60));
check("B2-AI 기록 연결", !!b?.inputs.ai_log_id, `ai_log_id = ${b?.inputs.ai_log_id}`);
await tab("기록");
check("B2-기록에 AI 연결 표시", await waitText("연결된 AI 기록", "main"));
observe("B2-고친 사실의 표시", (await has("수정", "main")) || (await has("고침", "main")) ? "기록 탭에 사람이 고쳤다는 글자가 있음" : "기록 탭에는 'AI 기록 연결'만 보이고, 사람이 초안을 고쳤다는 표시는 따로 없음 (입력 글과 AI 기록의 답을 비교해야 앎)");

await finish();
