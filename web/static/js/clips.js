// studio/clips.js - M11: the "Clips in every style" card. Motion prompts (once, for every style), the clips of the chosen style (the GPU and
// video model chosen in Make the Movie; a "from a picture" model), review against the Animation Supervisor's checklist, the REVIEW GATE,
// and the film of one style or of every style from the approved edit. Classic script: uses $, api, options() and poll() from core.js.
// Server: studio_app/clips_routes.py and /api/film_render (edit_routes.py).
(function () {
  const grid = $("clGrid");
  if (!grid) return;
  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  let slug = "", C = null, timer = null;
  const note = (t, bad) => { $("clNote").textContent = t; $("clNote").style.color = bad ? "#d6455d" : ""; };
  const opts = () => (typeof options === "function" ? options() : {});
  const startLog = () => { if (typeof poll === "function") { since = 0; $("log").textContent = ""; poll(); } };
  async function watch() {
    clearTimeout(timer);
    await load();
    let running = false;
    try { running = (await api("/api/log?since=0")).running; } catch (e) { /* keep */ }
    if (running) timer = setTimeout(watch, 5000);
  }
  function draw() {
    const sel = $("clStyle"), keep = sel.value || C.style;
    sel.innerHTML = C.styles.map(s => `<option${s === keep ? " selected" : ""}>${esc(s)}</option>`).join("");
    $("clApprove").disabled = !C.clips.length || C.gate.approved;
    note(!C.motion ? "Approve the master pictures, then write the motion prompts." : `${C.approved} of ${C.clips.length} clips approved. Check: ${C.checklist.join(", ")}.`
      + (C.gate.approved ? " Approved." : C.gate.changed_since ? " Changed since it was approved." : ""));
    grid.innerHTML = C.clips.map(c => `<div style="width:240px"><b><small>${esc(c.scene)} / ${c.shot}</small></b>
      ${c.clip ? `<video src="/file/${esc(c.base || C.set)}/${esc(c.clip)}" controls preload="none" width="240" height="135"></video>` : '<div class="warn" style="height:135px;display:grid;place-items:center;border:1px dashed var(--border)">no clip yet</div>'}
      <div class="row" style="gap:4px"><button type="button" class="btn btn--ghost" data-row="${c.row}" data-ok="${c.approved ? "" : "1"}"${c.clip ? "" : " disabled"}>${c.approved ? "Unapprove" : "Approve"}</button></div>
      <label class="f" for="clN${c.row}">Note</label><input type="text" id="clN${c.row}" value="${esc(c.note)}" data-note="${c.row}" style="width:100%"></div>`).join("");
    grid.querySelectorAll("[data-ok]").forEach(b => b.addEventListener("click", () => post({ row: Number(b.dataset.row), approved: Boolean(b.dataset.ok) })));
    grid.querySelectorAll("[data-note]").forEach(el => el.addEventListener("change", () => post({ row: Number(el.dataset.note), note: el.value })));
  }
  async function post(b) { try { C = await api("/api/clip_review", { project: slug, style: C.style, ...b }); draw(); } catch (e) { note(e.message, true); } }
  async function load() {
    if (!slug) { grid.innerHTML = ""; return; }
    const s = $("clStyle").value;
    try { C = await api(`/api/clips?project=${encodeURIComponent(slug)}${s ? `&style=${encodeURIComponent(s)}` : ""}`); draw(); } catch (e) { /* nothing */ }
  }
  $("clStyle").addEventListener("change", load);
  $("clMotion").addEventListener("click", async () => { const o = opts(); try { await api("/api/clips_motion", { project: slug, engine: o.engine, claude_model: o.claude_model }); startLog(); watch(); } catch (e) { note(e.message, true); } });
  $("clRender").addEventListener("click", async () => {
    const o = opts();
    const model = (o.video_models || []).find(m => /_i2v$/.test(m)) || "ltx_video_fast_i2v";
    try { await api("/api/clips_render", { project: slug, style: C.style, service: o.service, gpu: o.gpu, kaggle_user: o.kaggle_user, video_model: model }); startLog(); watch(); }
    catch (e) { note(e.message, true); }
  });
  $("clApprove").addEventListener("click", async () => { try { C = await api("/api/clips_approve", { project: slug, style: C.style }); draw(); } catch (e) { note(e.message, true); } });
  const film = async all => { try { await api("/api/film_render", { project: slug, style: all ? "" : C.style }); startLog(); note("The film is being cut: it appears in the Timeline editor's previews."); } catch (e) { note(e.message, true); } };
  $("clFilm").addEventListener("click", () => film(false));
  $("clFilmAll").addEventListener("click", () => film(true));
  window.loadClips = p => { slug = p && p.slug && !p.legacy && /^[a-z0-9_]{2,40}$/.test(p.slug) ? p.slug : ""; load(); };
})();
