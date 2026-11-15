// Loads the Studio page in jsdom (url = argv[2], with ?t=token), picks the book "demo" and drives the Chapters card:
// the table must list its chapters, "Join with next" must merge two, renaming must stick. Prints JSON {rows0, rows1, title, errors}.
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
  await wait(1500);
  const rows = () => d.querySelectorAll("#chapTable tbody tr").length;
  const rows0 = rows();
  const joinBtn = [...d.querySelectorAll("#chapTable button")].find(b => b.textContent === "Join with next");
  joinBtn.click();
  await wait(1500);
  const rows1 = rows();
  const title = d.querySelector("#chapTable tbody tr input[type=text]");
  title.value = "Renamed"; title.dispatchEvent(new w.Event("change"));
  await wait(1500);
  console.log(JSON.stringify({ rows0, rows1, title: d.querySelector("#chapTable tbody tr input[type=text]").value, summary: d.getElementById("chapSummary").textContent, errors }));
  process.exit(0);
}).catch(e => { console.log(JSON.stringify({ errors: ["load failed " + e.message] })); process.exit(1); });
