// Loads the Studio page in jsdom (url = argv[2]), opens the storyboard of "demo" and checks a card: Earlier/Later, then Edit prompt, then
// Retake keyframe and Old pictures, then the pictures the shot has had; clicking a take puts it on the shot and redraws only that card. Prints JSON.
const { JSDOM, ResourceLoader, VirtualConsole, CookieJar } = require("jsdom");
const url = process.argv[2];
const errors = [];
const vc = new VirtualConsole();
vc.on("jsdomError", e => errors.push("jsdomError: " + (e.detail && e.detail.stack || e.message).split("\n").slice(0, 3).join(" | ")));
class Loader extends ResourceLoader { fetch(u, o) { return u.includes("fonts.g") || u.includes("/thumb/") ? Promise.resolve(Buffer.from("")) : super.fetch(u, o); } }
const wait = ms => new Promise(r => setTimeout(r, ms));
JSDOM.fromURL(url, { beforeParse(w) { const N = class { observe() {} unobserve() {} disconnect() {} }; w.ResizeObserver = N; w.IntersectionObserver = N; w.scrollTo = () => {};
  w.Element.prototype.scrollIntoView = () => {}; w.confirm = () => true;
  w.matchMedia = w.matchMedia || (() => ({ matches: false, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {} }));
  w.fetch = (u, o) => { if (String(u).includes("/api/storyboard")) w.__sbCalls = (w.__sbCalls || []).concat(String(u));
    return fetch(new URL(u, url).href, o).then(r => { if (!r.ok && !String(u).startsWith("/thumb/")) errors.push("HTTP " + r.status + " " + u); return r; }); }; },
  runScripts: "dangerously", resources: new Loader(), pretendToBeVisual: true, virtualConsole: vc, cookieJar: new CookieJar() }).then(async dom => {
  const w = dom.window, d = w.document;
  w.HTMLMediaElement.prototype.play = () => Promise.resolve(); w.HTMLMediaElement.prototype.load = () => {};
  await wait(2500);
  if (d.body.classList.contains("flow")) d.getElementById("flowToggle").click();
  const proj = d.getElementById("proj"); proj.value = "demo"; proj.dispatchEvent(new w.Event("change"));
  await wait(1500);
  d.getElementById("sbLoad").click(); await wait(1500);
  const card = () => d.getElementById("sbShot-1");
  const rows = [...card().querySelectorAll(".sb-actions > *")].map(r => r.classList.contains("sb-pics") ? "pictures"
    : r.classList.contains("sb-editor") ? "editor" : [...r.querySelectorAll("button")].map(b => b.textContent.trim()).join(" + "));
  const src0 = card().querySelector(".pz-media img").getAttribute("src");
  const other = card().querySelector(".pz-tile .sb-pic__use") || card().querySelector(".sb-pic__use");
  const out = { errors, rows, nowShown: !!card().querySelector(".sb-pic--now"), takes: card().querySelectorAll(".sb-pic__use").length };
  const two = d.getElementById("sbShot-2"); two.dataset.mark = "kept";          // a card that must not be drawn again
  w.__sbCalls = [];
  other.click(); await wait(1500);
  out.status = d.getElementById("sbStatus").textContent;
  out.srcChanged = card().querySelector(".pz-media img").getAttribute("src") !== src0;
  out.otherKept = d.getElementById("sbShot-2").dataset.mark === "kept";
  out.calls = w.__sbCalls;
  console.log(JSON.stringify(out));
  process.exit(0);
}).catch(e => { console.log(JSON.stringify({ errors: ["load failed " + e.message] })); process.exit(1); });
