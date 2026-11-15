// studio/results.js - "Get results" buttons: download what a Kaggle run made when the process that waited for it has ended (the Studio was
// closed, the laptop slept). One button per kind of result, wherever that kind is made: pictures (keyframes), images, video, sound.
// Server: /api/results and /api/get_results (studio_app/results.py). Classic script: uses $, api from core.js.
(function () {
  const WORDS = { keyframes: "pictures", image: "pictures", video: "video clips", audio: "sounds", any: "results" };
  async function getResults(kind, project, say) {
    project = project || $("proj").value;
    if (!project) { say("Pick your book first."); return; }
    say(`Looking on Kaggle for ${WORDS[kind]} that are not here yet...`);
    try {
      const d = await api(`/api/results?project=${encodeURIComponent(project)}&kind=${kind}`);
      if (!d.kaggle) { say("The kaggle program is not installed on this computer."); return; }
      const todo = d.runs.filter(r => r.needs);
      if (!d.runs.length) { say(`No Kaggle run of ${WORDS[kind]} was found for this book.`); return; }
      if (!todo.length) { say(`All ${WORDS[kind]} from Kaggle are already here (${d.runs.length} run(s) checked).`); return; }
      const r = await api("/api/get_results", { project, kind });
      const going = todo.filter(x => x.status === "RUNNING" || x.status === "QUEUED").length;
      say(`Getting ${todo.length} run(s): ` + todo.map(x => `rows ${x.rows[0]}-${x.rows[1]} (${x.have} of ${x.wanted} here, ${(x.status || "?").toLowerCase()})`).join(", ") +
        (going ? `. ${going} still going: it is waited for.` : ".") + (r.queued ? " (It waits for the job that is running now.)" : " Watch the log at the bottom."));
      if (window.flowWatch) window.flowWatch();
    } catch (e) { say(e.message || String(e)); }
  }
  window.getResults = getResults;

  // a button with its own status line, for a card
  function addButton(where, kind, label, projectOf) {
    const host = typeof where === "string" ? document.getElementById(where) : where;
    if (!host) return;
    const wrap = document.createElement("div"); wrap.className = "results-get";
    const b = document.createElement("button"); b.type = "button"; b.className = "btn btn--secondary"; b.textContent = label; b.dataset.results = kind;
    b.title = `Download the ${WORDS[kind]} a Kaggle run made, when the Studio was not there to bring them home`;
    const s = document.createElement("span"); s.className = "warn"; s.setAttribute("role", "status"); s.setAttribute("aria-live", "polite");
    b.addEventListener("click", () => getResults(kind, projectOf ? projectOf() : "", t => { s.textContent = t; }));
    wrap.append(b, s);
    host.append(wrap);
  }
  addButton("sbUpdateBox", "keyframes", "Get results: pictures");
  const va = document.querySelector("#videoAudioCard .card__body");
  if (va) { addButton(va, "keyframes", "Get results: pictures"); addButton(va, "video", "Get results: video"); addButton(va, "audio", "Get results: sound"); }
  const pr = document.getElementById("pGenerate");
  if (pr) addButton(pr.parentElement, "any", "Get results: images and video", () => $("pset").value.trim());
})();
