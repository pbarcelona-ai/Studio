// Loads the Studio page in jsdom (url = argv[2]), opens the storyboard of "demo", drags shot 1's picture onto shot 2's (the two swap), then
// shot 2's onto shot 3, which has none (it moves). Only those cards are drawn again. Prints JSON.
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
  const media = n => d.querySelector(`#sbShot-${n} .pz-media`);
  const ev = (el, type) => el.dispatchEvent(new w.Event(type, { bubbles: true, cancelable: true }));
  const drag = async (a, b) => { ev(media(a).querySelector("img") || media(a), "dragstart"); ev(media(b), "dragover"); out.highlighted = media(b).classList.contains("sb-drop"); ev(media(b), "drop"); await wait(1500); };
  const out = { errors, draggable: media(1).getAttribute("draggable"), emptyDrop: media(3).dataset.drop, src1: media(1).querySelector("img").getAttribute("src") };
  d.getElementById("sbShot-4").dataset.mark = "kept";
  w.__sbCalls = [];
  await drag(1, 2);
  out.status1 = d.getElementById("sbStatus").textContent;
  out.src1After = media(1).querySelector("img").getAttribute("src");
  await drag(2, 3);
  out.status2 = d.getElementById("sbStatus").textContent;
  out.has2 = !!media(2).querySelector("img"); out.has3 = !!media(3).querySelector("img");
  out.otherKept = d.getElementById("sbShot-4").dataset.mark === "kept";
  out.calls = w.__sbCalls.length;
  console.log(JSON.stringify(out));
  process.exit(0);
}).catch(e => { console.log(JSON.stringify({ errors: ["load failed " + e.message] })); process.exit(1); });
