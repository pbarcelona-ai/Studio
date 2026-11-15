// Drives the "Film plan and screenplay" card in jsdom against a live server: shows the plan, changes a scene's clips, approves the screenplay,
// then edits a scene and sees the approval go. Prints JSON of what it saw.
const { JSDOM, ResourceLoader, VirtualConsole, CookieJar } = require("jsdom");
const url = process.argv[2];
const errors = [];
const vc = new VirtualConsole();
vc.on("jsdomError", e => errors.push("jsdomError: " + (e.detail && e.detail.stack || e.message).split("\n").slice(0, 3).join(" | ")));
class Loader extends ResourceLoader { fetch(u, o) { return u.includes("fonts.g") ? Promise.resolve(Buffer.from("")) : super.fetch(u, o); } }
const wait = ms => new Promise(r => setTimeout(r, ms));
JSDOM.fromURL(url, { beforeParse(w) { const N = class { observe() {} unobserve() {} disconnect() {} }; w.ResizeObserver = N; w.IntersectionObserver = N; w.scrollTo = () => {};
  w.matchMedia = w.matchMedia || (() => ({ matches: false, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {} }));
  w.fetch = (u, o) => fetch(new URL(u, url).href, o).then(r => { if (!r.ok) errors.push("HTTP " + r.status + " " + u); return r; }); },
  runScripts: "dangerously", resources: new Loader(), pretendToBeVisual: true, virtualConsole: vc, cookieJar: new CookieJar() }).then(async dom => {
  const w = dom.window, d = w.document;
  await wait(2500);
  const proj = d.getElementById("proj");
  proj.value = "demo"; proj.dispatchEvent(new w.Event("change"));
  await wait(2000);
  const out = { rows: d.querySelectorAll("#adaptScenes tbody tr").length, plan_hidden: d.getElementById("adaptPlan").classList.contains("hidden"),
                state0: d.getElementById("spState").textContent, budget: d.getElementById("adaptBudget").textContent.slice(0, 40) };
  const clips = d.querySelector("#adaptScenes tbody tr input[type=number]");
  clips.value = "9"; clips.dispatchEvent(new w.Event("change"));
  await wait(1500);
  out.runtime = d.getElementById("adaptRuntime").textContent;
  d.getElementById("spApprove").click();
  await wait(1500);
  out.state1 = d.getElementById("spState").textContent;
  const det = d.querySelector("#spScenes details"); det.open = true;
  const ta = det.querySelector("textarea"); ta.value = ta.value + "\nA: A new line.";
  [...det.querySelectorAll("button")].find(b => b.textContent === "Save this scene").click();
  await wait(1500);
  out.state2 = d.getElementById("spState").textContent;
  out.still_open = d.querySelector("#spScenes details").open;
  ta.value = "nonsense";
  out.errors = errors;
  console.log(JSON.stringify(out));
  process.exit(0);
}).catch(e => { console.log(JSON.stringify({ errors: ["load failed " + e.message] })); process.exit(1); });
