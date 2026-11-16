// studio/series.js - M14: the "Episodes, queue and marketing" card. Split the book into episodes (each a book of its own that shares the
// series' cast, looks and voices), pick an episode (it becomes the book the page works on), "Make next episode", the production queue with its
// total cost and finish estimate, and the marketing kit (trailer 16:9 and 9:16, three teasers, poster, thumbnail, captions) per style.
// Classic script: uses $, api, options() and poll() from core.js. Server: studio_app/series_routes.py.
(function () {
  const list = $("srList");
  if (!list) return;
  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  let slug = "";
  const o = () => (typeof options === "function" ? options() : {});
  const note = (t, bad) => { $("srNote").textContent = t; $("srNote").style.color = bad ? "#d6455d" : ""; };
  const startLog = () => { if (typeof poll === "function") { since = 0; $("log").textContent = ""; poll(); } };
  async function load() {
    if (!slug) { list.innerHTML = ""; return; }
    try {
      const S = await api(`/api/series?project=${encodeURIComponent(slug)}`);
      $("srPick").innerHTML = '<option value="">—</option>' + S.episodes.map(e => `<option value="${esc(e.slug)}"${e.slug === slug ? " selected" : ""}>${e.n}. ${esc(e.title)}</option>`).join("");
      list.innerHTML = S.episodes.length ? `<table class="data-table" aria-label="Episodes"><tr><th>#</th><th>Episode</th><th>Hook to cliffhanger</th><th>Now</th></tr>${S.episodes.map(e => `<tr><td>${e.n}</td><td>${esc(e.title)}<br><small>${esc(e.summary)}</small></td>
        <td><small>${esc(e.hook)} → ${esc(e.cliffhanger)}</small></td><td>${esc(e.state)}</td></tr>`).join("")}</table>` : "";
      note(S.series ? `This is an episode of ${S.series}.` : S.episodes.length ? `${S.episodes.length} episodes; next to make: ${S.next || "none"}.` : "");
      const Q = await api("/api/queue");
      $("srQueueOut").textContent = (Q.running ? `Running: ${Q.running.step}. ` : "") + (Q.waiting.length ? `${Q.waiting.length} waiting: ${Q.total.gpu_hours} GPU hours, $${Q.total.dollars.toFixed(2)}, done about ${Q.total.finish}.` : "Nothing waiting.");
      const M = await api(`/api/marketing?project=${encodeURIComponent(slug)}`);
      $("mkOut").innerHTML = (M.plan ? `<p class="warn"><b>${esc(M.plan.title)}</b>: ${esc(M.plan.logline)} <i>${esc(M.plan.tagline)}</i></p>` : "")
        + Object.entries(M.kits).map(([sid, files]) => `<details><summary>${esc(sid)} kit</summary><div class="row" style="gap:8px;flex-wrap:wrap">${files.map(f => f.text ? `<pre style="white-space:pre-wrap;max-width:420px">${esc(f.text)}</pre>`
          : f.name.endsWith(".png") ? `<img src="${esc(f.url)}" alt="${esc(f.name)}" width="160" loading="lazy">` : `<video src="${esc(f.url)}" controls preload="none" width="200"></video>`).join("")}</div></details>`).join("");
    } catch (e) { /* nothing yet */ }
  }
  const run = async (path, body, msg) => {
    try { const j = await api(path, { project: slug, engine: o().engine, claude_model: o().claude_model, ...(body || {}) }); startLog(); note(msg ? msg(j) : "Started: see the job log."); load(); }
    catch (e) { note(e.message, true); }
  };
  $("srSplit").addEventListener("click", () => run("/api/series_split", { episodes: Number($("srEpisodes").value) }));
  $("srNext").addEventListener("click", () => run("/api/series_next", {}, j => `Reading in ${j.episode}.`));
  $("srSync").addEventListener("click", async () => { try { const j = await api("/api/series_sync", { project: slug }); note(`Taken from the series: ${j.synced.join(", ")}.`); } catch (e) { note(e.message, true); } });
  $("srPick").addEventListener("change", () => {
    const v = $("srPick").value, sel = $("proj");
    if (!v || !sel) return;
    const go = () => { sel.value = v; sel.dispatchEvent(new Event("change")); };
    if (![...sel.options].some(x => x.value === v) && typeof refresh === "function") refresh().then(go); else go();
  });
  $("srQueueAdd").addEventListener("click", () => {
    const names = $("srQueue").value.split(",").map(x => x.trim()).filter(Boolean);
    if (names.length) run("/api/queue_add", { projects: names }, j => `Queued: ${j.queued.join(", ")}.`);
  });
  $("mkPlan").addEventListener("click", () => run("/api/marketing_plan", {}));
  $("mkRender").addEventListener("click", () => run("/api/marketing_render", {}));
  window.loadSeries = p => { slug = p && p.slug && !p.legacy && /^[a-z0-9_]{2,40}$/.test(p.slug) ? p.slug : ""; load(); };
})();
