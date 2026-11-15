// Loads the Studio page in jsdom (url = argv[2]): storyboard and critic of "demo" side by side. A clip length changed in the critic shows on the
// card, one changed on the card shows in the critic, and "Match narration" in the critic clears the pacing finding. Prints JSON.
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
  if (d.body.classList.contains("flow")) d.getElementById("flowToggle").click();
  const proj = d.getElementById("proj"); proj.value = "demo"; proj.dispatchEvent(new w.Event("change"));
  await wait(1500);
  d.getElementById("sbLoad").click(); await wait(1500);
  d.getElementById("sbCritic").click(); await wait(1500);
  const pacing = () => [...d.querySelectorAll("#sbCriticList li")].filter(li => li.textContent.includes("(pacing)")).length;
  const out = { errors, critBox: !!d.getElementById("crLen-1"), pacing0: pacing() };
  const cb = d.getElementById("crLen-1"); cb.value = "5"; cb.dispatchEvent(new w.Event("change", { bubbles: true })); await wait(2000);
  out.cardAfterCritic = d.getElementById("sbLen-1").value;
  const card = d.getElementById("sbLen-1"); card.value = "5.5"; card.dispatchEvent(new w.Event("change", { bubbles: true })); await wait(2000);
  out.criticAfterCard = d.getElementById("crLen-1") ? d.getElementById("crLen-1").value : "(gone)";
  d.querySelector('[data-crlenmatch="1"]').click(); await wait(2000);
  out.pacing1 = pacing(); out.cardAfterMatch = d.getElementById("sbLen-1").value;
  console.log(JSON.stringify(out));
  process.exit(0);
}).catch(e => { console.log(JSON.stringify({ errors: ["load failed " + e.message] })); process.exit(1); });
