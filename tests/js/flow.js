// Loads the Studio page in jsdom (url = argv[2]) with the book "demo" (planned, screenplay approved, shots built) and drives the film path:
// 16 steps in order, locked steps, Next, the step buttons (server calls that would start work are answered here), the walk back after a
// storyboard change with the red outline on the screenplay, and "All tabs". Prints JSON.
const { JSDOM, ResourceLoader, VirtualConsole, CookieJar } = require("jsdom");
const url = process.argv[2];
const errors = [];
const vc = new VirtualConsole();
vc.on("jsdomError", e => errors.push("jsdomError: " + (e.detail && e.detail.stack || e.message).split("\n").slice(0, 3).join(" | ")));
class Loader extends ResourceLoader { fetch(u, o) { return u.includes("fonts.g") ? Promise.resolve(Buffer.from("")) : super.fetch(u, o); } }
const wait = ms => new Promise(r => setTimeout(r, ms));
const calls = [];
JSDOM.fromURL(url, { beforeParse(w) { const N = class { observe() {} unobserve() {} disconnect() {} }; w.ResizeObserver = N; w.IntersectionObserver = N; w.scrollTo = () => {};
  w.Element.prototype.scrollIntoView = () => {};
  w.matchMedia = w.matchMedia || (() => ({ matches: false, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {} }));
  w.confirm = () => true; w.prompt = () => "";
  const reply = j => Promise.resolve({ ok: true, status: 200, json: async () => j });
  w.fetch = (u, o) => {
    const path = String(u).split("?")[0], body = o && o.body ? JSON.parse(o.body) : null;
    if (path === "/api/plan") { calls.push(["plan", body && body.steps]); return reply({ steps: [] }); }
    if (path === "/api/run") { calls.push(["run", body && body.steps]); return reply({}); }
    return fetch(new URL(u, url).href, o).then(r => { if (!r.ok && !String(u).includes("/api/path_confirm")) errors.push("HTTP " + r.status + " " + u); return r; });
  }; },
  runScripts: "dangerously", resources: new Loader(), pretendToBeVisual: true, virtualConsole: vc, cookieJar: new CookieJar() }).then(async dom => {
  const w = dom.window, d = w.document;
  w.HTMLMediaElement.prototype.play = () => Promise.resolve(); w.HTMLMediaElement.prototype.load = () => {};
  await wait(2500);
  const chips = () => [...d.querySelectorAll("#flowList button")];
  const out = { errors, orphans: w.flowOrphans(), names: w.flowScreens(), steps: chips().length, flowOn: d.body.classList.contains("flow") };
  const proj = d.getElementById("proj"); out.firstBook = [proj.value, proj.options[0].textContent]; proj.value = "demo"; proj.dispatchEvent(new w.Event("change"));
  d.querySelector("input[name=svc][value=kaggle]").checked = true;
  const ku = d.getElementById("kuser"); ku.value = "pat"; ku.dispatchEvent(new w.Event("change"));
  await wait(1500); await w.flowRefresh();
  out.locked = chips().filter(b => b.disabled).map(b => b.dataset.step);
  chips()[0].click(); await wait(200);
  out.step1 = { title: d.getElementById("pathTitle").textContent, shown: w.flowStageTitles(), more: w.flowMoreTitles(), buttons: [...d.querySelectorAll("#pathActions button")].map(b => b.textContent) };
  [...d.querySelectorAll("#pathActions button")].find(b => b.textContent === "Start over…").click(); await wait(100);
  const over = d.getElementById("libOver");
  out.startOver = { open: !over.classList.contains("hidden"), underPath: over.previousElementSibling === d.getElementById("pathActions") };
  d.getElementById("libOverCancel").click();
  d.getElementById("flowNext").click(); await wait(300);
  out.afterNext = d.getElementById("pathTitle").textContent;
  chips()[2].click(); await wait(200); out.planStep = d.body.dataset.step;
  chips()[3].click(); await wait(800);
  out.screenplayButtons = [...d.querySelectorAll("#pathActions button")].map(b => b.textContent);
  chips()[10].click(); await wait(300);
  out.kfTitle = d.getElementById("pathTitle").textContent; out.kfNextDisabled = d.getElementById("flowNext").disabled; out.kfTodo = d.getElementById("pathTodo").textContent;
  out.kfPicker = !!d.getElementById("pathKf");
  d.querySelector('#pathActions [data-run="stills"]').click(); await wait(1500);
  out.stillsRun = calls.filter(c => c[0] === "run").map(c => c[1]);
  chips()[11].click(); await wait(200); out.refusedTodo = d.getElementById("pathTodo").textContent; out.stillAt = d.getElementById("pathTitle").textContent;
  // a change in the storyboard: the screenplay is flagged and the path walks back to it
  const h = { "X-Studio-Token": new URL(url).searchParams.get("t"), "Content-Type": "application/json" };
  await fetch(new URL("/api/prompt_save", url).href, { method: "POST", headers: h, body: JSON.stringify({ project: "demo", chapter: "1", shot: 2, fields: { narration: "a brand new line" } }) });
  await w.flowRefresh();
  out.again = chips().filter(b => b.classList.contains("again")).map(b => b.dataset.step);
  out.lockedAfter = chips().filter(b => b.disabled).map(b => b.dataset.step);
  out.alert = d.getElementById("pathAlerts").textContent;
  chips()[3].click(); await wait(1500);
  out.flagged = d.querySelectorAll("#spScenes details.sp-flagged").length;
  out.flagNote = d.getElementById("spFlagNote").textContent;
  out.approveDisabled = d.getElementById("spApprove").disabled;
  out.nextWhileFlagged = d.getElementById("flowNext").disabled;
  [...d.querySelectorAll("#spScenes details.sp-flagged button")].find(b => b.textContent.startsWith("Keep it")).click(); await wait(1200);
  await w.flowRefresh();
  out.flaggedAfterKeep = d.querySelectorAll("#spScenes details.sp-flagged").length;
  d.getElementById("flowNext").click(); await wait(1200);
  out.afterConfirm = d.getElementById("pathTitle").textContent;
  out.againAfter = chips().filter(b => b.classList.contains("again")).map(b => b.dataset.step);
  // All tabs: every card back where it lives
  d.getElementById("flowToggle").click(); await wait(200);
  out.restored = d.getElementById("stepRead").parentElement.id === "panel-project" && d.getElementById("stepAdapt").parentElement.id === "panel-project" && !d.querySelector("#flowShown > .card");
  out.groups = [...d.querySelectorAll(".svc-group__title")].map(x => x.textContent.trim());
  out.paid = d.querySelectorAll("#paidProviders li").length;
  d.getElementById("flowToggle").click(); await wait(200);
  out.backInFlow = d.body.classList.contains("flow");
  console.log(JSON.stringify(out));
  process.exit(0);
}).catch(e => { console.log(JSON.stringify({ errors: ["load failed " + e.message] })); process.exit(1); });
