// Loads the Studio page in jsdom (url = argv[2]) in the classic tabs and presses the Video and Audio card's own "Make the keyframes" button.
// Server calls that would start work are answered here. argv[3] = "waiting" when the book has pictures without a yes or no. Prints JSON.
const { JSDOM, ResourceLoader, VirtualConsole, CookieJar } = require("jsdom");
const url = process.argv[2];
const errors = [], calls = [];
const vc = new VirtualConsole();
vc.on("jsdomError", e => errors.push("jsdomError: " + (e.detail && e.detail.stack || e.message).split("\n").slice(0, 3).join(" | ")));
class Loader extends ResourceLoader { fetch(u, o) { return u.includes("fonts.g") ? Promise.resolve(Buffer.from("")) : super.fetch(u, o); } }
const wait = ms => new Promise(r => setTimeout(r, ms));
JSDOM.fromURL(url, { beforeParse(w) { const N = class { observe() {} unobserve() {} disconnect() {} }; w.ResizeObserver = N; w.IntersectionObserver = N; w.scrollTo = () => {};
  w.Element.prototype.scrollIntoView = () => {}; w.confirm = () => true;
  w.matchMedia = w.matchMedia || (() => ({ matches: false, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {} }));
  const reply = j => Promise.resolve({ ok: true, status: 200, json: async () => j });
  w.fetch = (u, o) => {
    const path = String(u).split("?")[0], body = o && o.body ? JSON.parse(o.body) : null;
    if (path === "/api/plan") { calls.push(["plan", body.steps]); return reply({ steps: [] }); }
    if (path === "/api/run") { calls.push(["run", body.steps]); return reply({}); }
    return fetch(new URL(u, url).href, o).then(r => { if (!r.ok && !String(u).startsWith("/thumb/")) errors.push("HTTP " + r.status + " " + u); return r; });
  }; },
  runScripts: "dangerously", resources: new Loader(), pretendToBeVisual: true, virtualConsole: vc, cookieJar: new CookieJar() }).then(async dom => {
  const w = dom.window, d = w.document;
  w.HTMLMediaElement.prototype.play = () => Promise.resolve(); w.HTMLMediaElement.prototype.load = () => {};
  await wait(2500);
  if (d.body.classList.contains("flow")) d.getElementById("flowToggle").click();
  const proj = d.getElementById("proj"); proj.value = "demo"; proj.dispatchEvent(new w.Event("change"));
  await wait(1500);
  const btn = d.getElementById("vaMakeStills");
  const out = { errors, inCard: !!btn && !!btn.closest("#videoAudioCard"), others: [!!d.getElementById("vaMakeVideo"), !!d.getElementById("vaMakeSound")] };
  btn.click(); await wait(2500);
  out.status = btn.parentElement.querySelector("[role=status]").textContent;
  out.runs = calls.filter(c => c[0] === "run").map(c => Object.keys(c[1]).filter(k => c[1][k]));
  out.stillClassic = !d.body.classList.contains("flow");
  console.log(JSON.stringify(out));
  process.exit(0);
}).catch(e => { console.log(JSON.stringify({ errors: ["load failed " + e.message] })); process.exit(1); });
