// studio/readin.js - M3: the "Read it in" card. Starts scripts/read_it_in.py as a job, shows its live progress ("Your story analyst is
// reading chapter 7 of 31"), then the screenplay, coverage, beat sheet, treatment and crew notes in tabs, and makes the downloads
// (screenplay PDF, Fountain, Word, Final Draft, and the notes PDF). Classic script: uses $, api, options() and poll() from core.js.
// Server: studio_app/readin_routes.py.
(function () {
  const start = $("riStart");
  if (!start) return;
  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  let slug = "", R = null, tab = "script", timer = null;

  const pane = {
    script: () => R.script || "No screenplay yet.",
    coverage: () => { const c = R.coverage; if (!c) return "No coverage yet."; return [`Logline: ${c.logline}`, `Genre: ${c.genre}   Tone: ${c.tone}`, `Themes: ${(c.themes || []).join(", ")}`, "",
      "Characters:", ...(c.characters || []).map(x => `  ${x.name} (${x.role || ""}): ${x.description || ""}`), "", "Key events:", ...(c.key_events || []).map(e => `  - ${e}`), "",
      `Filmable: ${c.filmable || ""}`, `Length for the target: ${c.length}`].join("\n"); },
    beats: () => !R.beats ? "No beat sheet yet." : R.beats.acts.map(a => `${a.name} (${Math.round((a.share || 0) * 100)}%): ${a.purpose || ""}\n` + a.beats.map(b => `  ${b.n}. ${b.name}: ${b.description}`).join("\n")).join("\n\n"),
    treatment: () => R.treatment || "No treatment yet.",
    notes: () => !R.critique.length ? "No crew notes yet." : R.critique.map(c => `Round ${c.round}\n  Script doctor: ${c.doctor.score}/10\n` + c.doctor.notes.map(n => `    scene ${n.scene || "all"}: ${n.note}`).join("\n")
      + `\n  Director: ${c.director.score}/10\n` + c.director.notes.map(n => `    scene ${n.scene || "all"}: ${n.note}`).join("\n")).join("\n\n"),
  };
  function draw() {
    const P = R.progress, S = R.summary;
    $("riProgress").textContent = S ? `Done: ${S.scenes} scenes, about ${S.minutes} minutes, ${S.rounds} critique round(s)` + (S.scores.script_doctor ? ` (script doctor ${S.scores.script_doctor}/10, director ${S.scores.director}/10).` : ".")
      : P ? `Step ${P.step} of ${P.steps}: ${P.text}` : "Add sources (or read a book), choose the format, then press Read it in.";
    const has = Boolean(R.script || R.coverage);
    $("riResult").classList.toggle("hidden", !has);
    if (!has) return;
    document.querySelectorAll("[data-ri]").forEach(b => { const on = b.dataset.ri === tab; b.setAttribute("aria-selected", String(on)); b.className = "btn " + (on ? "btn--secondary" : "btn--ghost"); });
    $("riPane").textContent = pane[tab]();
    $("riFiles").innerHTML = R.exports.map(f => `<a class="btn btn--ghost" href="${esc(f.url)}" download>${esc(f.name)}</a>`).join(" ");
  }
  async function load() {
    if (!slug) return;
    try { R = await api(`/api/readin?project=${encodeURIComponent(slug)}`); draw(); } catch (e) { $("riProgress").textContent = ""; }
  }
  async function watch() {
    clearTimeout(timer);
    await load();
    let running = false;
    try { running = (await api("/api/log?since=0")).running; } catch (e) { /* keep the last state */ }
    if (running) timer = setTimeout(watch, 3000);
  }
  document.querySelectorAll("[data-ri]").forEach(b => b.addEventListener("click", () => { tab = b.dataset.ri; if (R) draw(); }));
  start.addEventListener("click", async () => {
    if (!slug) return ($("riProgress").textContent = "Pick a book first.");
    const o = typeof options === "function" ? options() : {};
    try {
      await api("/api/read_it_in", { project: slug, engine: o.engine, claude_model: o.claude_model, force: $("riForce").checked });
      $("riProgress").textContent = "Your producer is gathering the sources…";
      if (typeof poll === "function") { since = 0; $("log").textContent = ""; poll(); }
      watch();
    } catch (e) { $("riProgress").textContent = e.message; }
  });
  $("riExport").addEventListener("click", async () => {
    try { const j = await api("/api/readin_export", { project: slug }); R.exports = j.exports; draw(); } catch (e) { $("riProgress").textContent = e.message; }
  });
  window.loadReadIn = p => { slug = p && p.slug && !p.legacy && /^[a-z0-9_]{2,40}$/.test(p.slug) ? p.slug : ""; R = null; $("riResult").classList.add("hidden"); load(); };
})();
