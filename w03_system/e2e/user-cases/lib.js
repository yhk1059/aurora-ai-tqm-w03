// 유저 케이스 공통 도우미 (brain/3-design/user-case-scenarios.md).
// run.sh가 `const BASE = "..."; const CASE = "UC-xx";`를 앞에 붙이고, 이 파일 뒤에 케이스 파일을 이어 붙여
// dev-browser에 넘긴다 (dev-browser 스크립트는 import를 쓸 수 없다).
// 화면 조작은 사람이 보는 글자(버튼 이름, 칸 이름)로 찾는다. 출발 상태 준비와 결과 대조만 API를 쓴다.

const sleep = ms => new Promise(r => setTimeout(r, ms));
const OWNER = "quality_owner", COMMITTEE = "quality_committee", SCM = "scm";

// --- 결과 기록 ----------------------------------------------------------------
const results = [];
/** 합격·불합격을 가르는 확인 */
function check(id, ok, note = "") { results.push({ id, kind: ok ? "통과" : "실패", note }); }
/** 합격·불합격이 아니라 사람이 보고 판단할 것 */
function observe(id, note) { results.push({ id, kind: "관찰", note }); }

// --- 화면 준비 ----------------------------------------------------------------
const page = await browser.getPage("w03-uc");
const consoleErrors = [], apiErrors = [];
let expectedApiErrors = 0; // 일부러 실패시키는 단계가 있는 케이스가 올린다
page.on("console", m => { if (m.type() === "error" && !m.text().includes("Failed to load resource")) consoleErrors.push(m.text()); });
page.on("pageerror", e => consoleErrors.push(String(e)));
page.on("response", r => { if (r.url().includes("/api/") && r.status() >= 400) apiErrors.push(`${r.status()} ${r.url().replace(BASE, "")}`); });

// --- API (출발 상태 준비, 상태 대조) ---------------------------------------------
async function api(method, path, body) {
  const r = await fetch(BASE + path, {
    method,
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  return { status: r.status, data: await r.json().catch(() => null) };
}
/** 출발 상태. name = null이면 빈 상태, opts.upto = 그 단계까지, opts.setupOnly = 출발 단계만 */
async function start(name, opts = {}) {
  const r = name === null
    ? await api("POST", "/api/actions/reset", { actor: OWNER, inputs: {} })
    : await api("POST", `/api/scenarios/${name}?` + (opts.upto ? `upto=${opts.upto}` : `setup_only=${!!opts.setupOnly}`));
  if (r.status !== 200) throw new Error(`출발 상태 준비 실패: ${name} ${r.status}`);
}
async function view(actor = OWNER) { return (await api("GET", `/api/incident?actor=${actor}`)).data; }
const logCount = v => v.log.actions.length;
const batchState = (v, id) => v.batches.find(b => b.id === id)?.state;
const planState = (v, n) => v.plans.find(p => p.attrs.version === n)?.state;
const taskOf = (v, type, customer) => v.tasks.find(t => t.type === type && (!customer || JSON.stringify(t).includes(customer)));

async function open(width = 1440, height = 900) {
  await page.setViewport({ width, height });
  await page.goto(BASE + "/");
  await page.waitForSelector("main", { timeout: 8000 });
  await sleep(400);
}

// --- 찾기 --------------------------------------------------------------------
/** 화면에 보이는 글자 (scope 안) */
async function text(scope = "main") {
  return page.evaluate(s => { const el = document.querySelector(s); return el ? el.innerText.replace(/\s+/g, " ") : ""; }, scope);
}
async function has(str, scope = "body") { return (await text(scope)).includes(str); }
async function waitText(str, scope = "body", timeout = 5000) {
  try {
    await page.waitForFunction((s, t) => { const el = document.querySelector(s); return !!el && el.innerText.replace(/\s+/g, " ").includes(t); }, { timeout }, scope, str);
    return true;
  } catch { return false; }
}
async function gone(selector, timeout = 5000) {
  try { await page.waitForFunction(s => !document.querySelector(s), { timeout }, selector); return true; } catch { return false; }
}
/** 보이는 버튼 정보. 없으면 null. exact = false면 "이름으로 시작" */
async function button(name, scope = "body", exact = true) {
  return page.evaluate((name, scope, exact) => {
    const root = document.querySelector(scope);
    if (!root) return null;
    const norm = s => s.replace(/\s+/g, " ").trim();
    document.querySelectorAll("[data-uc-btn]").forEach(b => b.removeAttribute("data-uc-btn"));
    const b = [...root.querySelectorAll("button")].find(b => b.offsetParent !== null &&
      (exact ? norm(b.textContent) === name : norm(b.textContent).startsWith(name)));
    if (!b) return null;
    b.setAttribute("data-uc-btn", "1");
    return { disabled: b.disabled, text: norm(b.textContent) };
  }, name, scope, exact);
}
async function click(name, scope = "body", exact = true) {
  for (let i = 0; i < 25; i++) {
    const b = await button(name, scope, exact);
    if (b && !b.disabled) { await page.click("[data-uc-btn]"); await sleep(250); return; }
    await sleep(200);
  }
  throw new Error(`버튼을 누를 수 없음: "${name}" (${scope})`);
}
/** 칸 이름(앞 글자)으로 입력 칸을 찾아 표시하고 선택자를 돌려준다 */
async function field(label, scope = "body") {
  const ok = await page.evaluate((label, scope) => {
    const root = document.querySelector(scope);
    if (!root) return false;
    const norm = s => s.replace(/\s+/g, " ").trim();
    document.querySelectorAll("[data-uc-field]").forEach(e => e.removeAttribute("data-uc-field"));
    for (const c of root.querySelectorAll("input, textarea, select")) {
      if (c.offsetParent === null) continue;
      let p = c.parentElement;
      for (let d = 0; d < 3 && p; d++, p = p.parentElement) {
        if (p.querySelectorAll("input, textarea, select").length > 1) break;
        if (norm(p.innerText).startsWith(label)) { c.setAttribute("data-uc-field", "1"); return true; }
      }
    }
    return false;
  }, label, scope);
  if (!ok) throw new Error(`입력 칸 없음: "${label}" (${scope})`);
  return "[data-uc-field]";
}
async function fill(label, value, scope = "body") { await page.fill(await field(label, scope), value); await sleep(150); }
async function choose(label, option, scope = "body") {
  const sel = await field(label, scope);
  const value = await page.$eval(sel, (s, o) => [...s.options].find(x => x.textContent.trim() === o)?.value, option);
  if (value === undefined) throw new Error(`선택지 없음: "${option}" (${label})`);
  await page.select(sel, value);
  await sleep(150);
}

// --- 조작 --------------------------------------------------------------------
async function setRole(role) { await page.select("header select", role); await sleep(500); }
async function tab(label) { await click(label, "nav", false); await sleep(300); }
/** 작업 줄을 찾아 표시하고 선택자를 돌려준다 (끝난 작업이 접혀 있으면 펼친다) */
async function taskRow(type, customer) {
  const more = await button("끝난 작업", "main", false);
  if (more && more.text.endsWith("보기")) await click(more.text, "main");
  const ok = await page.evaluate((type, customer) => {
    document.querySelectorAll("[data-uc-task]").forEach(e => e.removeAttribute("data-uc-task"));
    const li = [...document.querySelectorAll("main li")].find(l => l.querySelector("[data-task-head]") &&
      l.innerText.includes(type) && (!customer || l.innerText.includes(customer)));
    if (li) li.setAttribute("data-uc-task", "1");
    return !!li;
  }, type, customer);
  if (!ok) throw new Error(`작업 줄 없음: ${type} ${customer ?? ""}`);
  return "[data-uc-task]";
}
const DIALOG = "[role=dialog]";
async function dialogOpen() { return !!(await page.$(DIALOG)); }
/** 가로로 넘치는 폭(px). 0이면 가로 스크롤 없음 */
async function overflowX() { return page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth); }

// --- 마무리 -------------------------------------------------------------------
async function finish() {
  check("공통-콘솔", consoleErrors.length === 0, consoleErrors.join(" | "));
  check("공통-API", apiErrors.length === expectedApiErrors, `기대 ${expectedApiErrors}건, 실제 ${apiErrors.length}건 ${apiErrors.join(", ")}`);
  await page.screenshot({ path: `data/e2e/uc/${CASE}.png`, fullPage: true });
  for (const r of results) console.log(`${r.kind}\t${CASE}\t${r.id}\t${r.note}`);
  const failed = results.filter(r => r.kind === "실패");
  if (failed.length) throw new Error(`${CASE}: 실패 ${failed.length}건 (${failed.map(f => f.id).join(", ")})`);
}
