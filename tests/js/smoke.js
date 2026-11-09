// Loads the Studio page in jsdom (url = argv[2], with ?t=token), clicks every tab and prints JSON {tabs, errors}. Exit 1 on any script error.
const { JSDOM, ResourceLoader, VirtualConsole } = require("jsdom");
const url = process.argv[2];                      // http://127.0.0.1:PORT/?t=TOKEN
const errors = [];
const vc = new VirtualConsole();
vc.on("jsdomError", e => errors.push("jsdomError: " + (e.detail && e.detail.stack || e.message).split("\n").slice(0,3).join(" | ")));
vc.on("error", (...a) => errors.push("console.error: " + a.join(" ").slice(0, 300)));
class Loader extends ResourceLoader { fetch(u, o) { return u.includes("fonts.g") ? Promise.resolve(Buffer.from("")) : super.fetch(u, o); } }
JSDOM.fromURL(url, { beforeParse(w){ const N=class{observe(){}unobserve(){}disconnect(){}}; w.ResizeObserver=N; w.IntersectionObserver=N; w.matchMedia=w.matchMedia||(q=>({matches:false,addEventListener(){},removeEventListener(){},addListener(){},removeListener(){}})); w.scrollTo=()=>{}; w.fetch=(u,o)=>fetch(new URL(u,url).href,o).then(r=>{ if(!r.ok) errors.push('HTTP '+r.status+' '+u); return r; }); }, runScripts: "dangerously", resources: new Loader(), pretendToBeVisual: true, virtualConsole: vc, cookieJar: new (require("jsdom").CookieJar)() }).then(dom => {
  const w = dom.window;
  w.HTMLMediaElement.prototype.play = () => Promise.resolve(); w.HTMLMediaElement.prototype.load = () => {};
  setTimeout(() => {
    const tabs = w.document.querySelectorAll(".tab-btn").length;
    
    // click through every tab
    w.document.querySelectorAll(".tab-btn").forEach(b => b.click());
    setTimeout(() => { console.log(JSON.stringify({ tabs, errors: errors.slice(0, 12), title: w.document.title })); process.exit(errors.length ? 1 : 0); }, 2500);
  }, 3500);
}).catch(e => { console.log("load failed", e.message); process.exit(1); });
