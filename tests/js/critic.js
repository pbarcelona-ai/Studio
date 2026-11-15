// Loads the Studio page in jsdom (url = argv[2]), picks the book "demo", loads the storyboard, runs the critic and acts on a finding:
// show the shot, edit its prompt, save. Prints JSON.
const { JSDOM, ResourceLoader, VirtualConsole, CookieJar } = require("jsdom");
const url = process.argv[2];
const errors = [];
const vc = new VirtualConsole();
vc.on("jsdomError", e => errors.push("jsdomError: " + (e.detail && e.detail.stack || e.message).split("\n").slice(0, 3).join(" | ")));
class Loader extends ResourceLoader { fetch(u, o) { return u.includes("fonts.g") ? Promise.resolve(Buffer.from("")) : super.fetch(u, o); } }
const wait = ms => new Promise(r => setTimeout(r, ms));
JSDOM.fromURL(url, { beforeParse(w) { const N = class { observe() {} unobserve() {} disconnect() {} }; w.ResizeObserver = N; w.IntersectionObserver = N; w.scrollTo = () => {};
  w.Element.prototype.scrollIntoView = () => {};
  w.matchMedia = w.matchMedia || (() => ({ matches: false, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {} }));
  w.prompt = () => "too long"; w.confirm = () => true;
  w.fetch = (u, o) => fetch(new URL(u, url).href, o).then(r => { if (!r.ok) errors.push("HTTP " + r.status + " " + u); return r; }); },
  runScripts: "dangerously", resources: new Loader(), pretendToBeVisual: true, virtualConsole: vc, cookieJar: new CookieJar() }).then(async dom => {
  const w = dom.window, d = w.document;
  w.HTMLMediaElement.prototype.play = () => Promise.resolve(); w.HTMLMediaElement.prototype.load = () => {};
  await wait(2500);
  const proj = d.getElementById("proj");
  proj.value = "demo"; proj.dispatchEvent(new w.Event("change"));
  await wait(1500);
  d.getElementById("sbCritic").click();                                  // the critic first: its buttons must load the storyboard themselves
  await wait(1500);
  const out = { errors, buttons: [...d.querySelectorAll("#sbCriticList button")].map(b => b.dataset.crit + ":" + b.dataset.n), status: d.getElementById("sbStatus").textContent };
  out.layout = [...d.querySelectorAll("#sbCriticList li")].filter(li => li.querySelector(".crit-ctl")).map(li =>       // message, then the controls on their own line
    [...li.children].map(c => c.className).join("|") + "/" + li.querySelector(".crit-ctl").children.length);
  const btn = act => [...d.querySelectorAll("#sbCriticList button")].find(b => b.dataset.crit === act);
  const n = btn("edit").dataset.n;
  btn("edit").click(); await wait(1500);
  out.cardShown = !!d.getElementById("sbShot-" + n);
  const ta = d.getElementById("sbEp-" + n);
  out.editorOpen = !!ta;
  ta.value = "a brand new prompt for the shot";
  d.querySelector(`[data-edit-save="${n}"]`).click(); await wait(1500);
  out.afterSave = d.getElementById("sbStatus").textContent;
  out.verdict = d.getElementById("sbShot-" + n).dataset.status;
  const count = () => d.querySelectorAll("#sbCriticList li").length;
  const before = count();
  btn("dismiss").click();
  out.dismissed = before - count();
  console.log(JSON.stringify(out));
  process.exit(0);
}).catch(e => { console.log(JSON.stringify({ errors: ["load failed " + e.message] })); process.exit(1); });
