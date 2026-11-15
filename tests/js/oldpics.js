// Loads the Studio page in jsdom (url = argv[2]), opens the storyboard of "demo", presses "Old pictures" on shot 2 and uses the best one. Prints JSON.
const { JSDOM, ResourceLoader, VirtualConsole, CookieJar } = require("jsdom");
const url = process.argv[2];
const errors = [];
const vc = new VirtualConsole();
vc.on("jsdomError", e => errors.push("jsdomError: " + (e.detail && e.detail.stack || e.message).split("\n").slice(0, 3).join(" | ")));
class Loader extends ResourceLoader { fetch(u, o) { return u.includes("fonts.g") ? Promise.resolve(Buffer.from("")) : super.fetch(u, o); } }
const wait = ms => new Promise(r => setTimeout(r, ms));
JSDOM.fromURL(url, { beforeParse(w) { const N = class { observe() {} unobserve() {} disconnect() {} }; w.ResizeObserver = N; w.IntersectionObserver = N; w.scrollTo = () => {};
  w.Element.prototype.scrollIntoView = () => {}; w.confirm = () => true;
  w.matchMedia = w.matchMedia || (() => ({ matches: false, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {} }));
  w.fetch = (u, o) => fetch(new URL(u, url).href, o).then(r => { if (!r.ok && !String(u).startsWith("/thumb/")) errors.push("HTTP " + r.status + " " + u); return r; }); },
  runScripts: "dangerously", resources: new Loader(), pretendToBeVisual: true, virtualConsole: vc, cookieJar: new CookieJar() }).then(async dom => {
  const w = dom.window, d = w.document;
  w.HTMLMediaElement.prototype.play = () => Promise.resolve(); w.HTMLMediaElement.prototype.load = () => {};
  await wait(2500);
  if (d.body.classList.contains("flow")) d.getElementById("flowToggle").click();       // the classic tabs: no steps to finish first
  const proj = d.getElementById("proj"); proj.value = "demo"; proj.dispatchEvent(new w.Event("change"));
  await wait(1500);
  d.getElementById("sbLoad").click(); await wait(1500);
  d.querySelector('[data-oldpics="2"]').click(); await wait(1500);
  const dlg = d.getElementById("oldPicDialog");
  const out = { errors, open: dlg.open || dlg.hasAttribute("open"), title: d.getElementById("oldPicTitle").textContent,
                first: d.querySelector("#oldPicGrid figcaption") ? d.querySelector("#oldPicGrid figcaption").textContent : "", count: d.getElementById("oldPicCount").textContent };
  d.querySelector("#oldPicGrid button").click(); await wait(1500);
  out.status = d.getElementById("sbStatus").textContent; out.after = d.getElementById("oldPicCount").textContent;
  console.log(JSON.stringify(out));
  process.exit(0);
}).catch(e => { console.log(JSON.stringify({ errors: ["load failed " + e.message] })); process.exit(1); });
