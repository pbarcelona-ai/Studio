// studio/pictures.js - M6: the "Pictures in the master style" card. Makes the picture prompts from the approved shot list and look
// development, renders them (the GPU, user and keyframe image model chosen in Make the Movie), shows a grid with Approve, Note, Edit prompt,
// Regenerate (the old picture is kept as a version) and swap by drag and drop (or with the keyboard: "Swap with…" on a tile, then
// "Put here" on another), the REVIEW GATE, and the storyboard / illustrated book downloads.
// Classic script: uses $, api, options() and poll() from core.js. Server: studio_app/pictures_routes.py.
(function () {
  const grid = $("pxGrid");
  if (!grid) return;
  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  let slug = "", P = null, swapFrom = 0, timer = null;
  const note = (t, bad) => { $("pxNote").textContent = t; $("pxNote").style.color = bad ? "#d6455d" : ""; };
  const gpu = () => { const o = typeof options === "function" ? options() : {}; return { service: o.service, gpu: o.gpu, kaggle_user: o.kaggle_user, image_model: o.keyframe_model }; };
  const startLog = () => { if (typeof poll === "function") { since = 0; $("log").textContent = ""; poll(); } };

  async function act(row, action, extra) {
    try { P = await api("/api/picture_action", { project: slug, style: P.style, row, action, ...(extra || {}) }); draw(); if (action === "regenerate") { startLog(); watch(); } }
    catch (e) { note(e.message, true); }
  }
  function tile(s) {
    const img = s.image ? `<img src="/thumb/${esc(P.set)}/${esc(s.image)}?v=${esc(s.versions.length)}" alt="Scene ${esc(s.scene)} shot ${s.shot}" width="220" height="124" loading="lazy" style="object-fit:cover;border-radius:6px;display:block">`
      : `<div style="width:220px;height:124px;display:grid;place-items:center;border:1px dashed var(--border);border-radius:6px" class="warn">not rendered</div>`;
    return `<div class="tile" draggable="${s.image ? "true" : "false"}" data-row="${s.row}" style="width:220px;border:2px solid ${s.approved ? "#2e9e5b" : "transparent"};border-radius:8px;padding:4px">
      ${img}<small><b>${esc(s.scene)} / ${s.shot}</b>${s.approved ? " ✓ approved" : ""}${(P.consistency || {})[s.row] ? ` · match ${P.consistency[s.row].score}/10${P.consistency[s.row].flagged ? " ⚑ check it" : ""}` : ""}${s.versions.length ? ` · ${s.versions.length} older version(s)` : ""}</small>
      <div class="row" style="gap:4px;flex-wrap:wrap;margin-top:4px">
        <button type="button" class="btn btn--ghost" data-a="${s.approved ? "unapprove" : "approve"}"${s.image ? "" : " disabled"}>${s.approved ? "Unapprove" : "Approve"}</button>
        <button type="button" class="btn btn--ghost" data-a="regenerate">Regenerate</button>
        <button type="button" class="btn btn--ghost" data-a="swap"${s.image ? "" : " disabled"}>${swapFrom === s.row ? "Cancel swap" : swapFrom ? "Put here" : "Swap with…"}</button>
        <button type="button" class="btn btn--ghost" data-a="old">Old pictures that could fit</button></div><div class="pxOld" data-for="${s.row}"></div>
      <details><summary>Prompt and note</summary>
        <label class="f" for="pxP${s.row}">Prompt (leave empty for the crew's)</label><textarea id="pxP${s.row}" rows="3" style="width:100%" data-f="prompt">${esc(s.own_prompt)}</textarea>
        <small class="warn">${esc(s.prompt.slice(0, 300))}</small>
        <label class="f" for="pxN${s.row}">Note</label><input type="text" id="pxN${s.row}" value="${esc(s.note)}" data-f="note" style="width:100%"></details></div>`;
  }
  const s0 = row => P.shots.find(x => x.row === row);
  async function showOld(s, box) {
    try {
      const j = await api(`/api/shot_matches?project=${encodeURIComponent(slug)}&style=${encodeURIComponent(P.style)}&scene=${encodeURIComponent(s.scene)}&shot=${s.shot}`);
      box.innerHTML = !j.matches.length ? '<small class="warn">No old pictures yet.</small>' : `<small class="warn">${j.matches.filter(m => m.match >= 5).length} old picture(s) could fit</small>` +
        j.matches.slice(0, 6).map(m => `<div class="row" style="gap:4px;align-items:center;margin:3px 0"><img src="${esc(m.thumb)}" alt="Old picture: ${esc(m.group_name)}" width="72" height="40" style="object-fit:cover">
          <small>${m.match}/10${m.may_not_match ? " · may not match the continuity book" : ""}</small>
          ${["picture", "prompt", "layout"].map(h => `<button type="button" class="btn btn--ghost" data-reuse="${esc(m.key)}" data-how="${h}">${h === "picture" ? "Use this picture" : h === "prompt" ? "Use its prompt" : "Use its layout"}</button>`).join("")}</div>`).join("");
      box.querySelectorAll("[data-reuse]").forEach(b => b.addEventListener("click", async () => {
        try { await api("/api/shot_reuse", { project: slug, style: P.style, scene: s.scene, shot: s.shot, key: b.dataset.reuse, how: b.dataset.how }); load(); note("Reused."); } catch (e) { note(e.message, true); }
      }));
    } catch (e) { note(e.message, true); }
  }
  function draw() {
    const g = P.gate, sel = $("pxStyle");
    const want = sel.value || P.style;
    sel.innerHTML = (P.styles || [P.style]).map(id => `<option value="${esc(id)}"${id === want ? " selected" : ""}>${esc(id)}${id === P.master ? " (master)" : ""}</option>`).join("");
    const other = P.style && P.master && P.style !== P.master;
    $("pxCheck").classList.toggle("hidden", !other);
    const again = Object.values(P.consistency || {}).filter(c => c.pending).length;
    $("pxAgain").classList.toggle("hidden", !other || !again);
    $("pxAgain").textContent = `Render the ${again} failed one(s) again`;
    $("pxRender").disabled = !P.shots.length;
    $("pxAuto").disabled = !P.shots.some(x => !x.image);
    $("pxApprove").disabled = !P.shots.length || g.approved;
    note(!P.shots.length ? "Approve the shot list and the look development, then make the picture prompts." :
      `${P.approved} of ${P.shots.length} approved. ` + (g.approved ? `Approved ${g.approved_at.slice(0, 16).replace("T", " ")}.` : g.changed_since ? "Changed since it was approved." : ""));
    grid.innerHTML = P.shots.map(tile).join("");
    $("pxFiles").innerHTML = P.exports.map(f => `<a class="btn btn--ghost" href="${esc(f.url)}" download>${esc(f.name)}</a>`).join(" ");
    grid.querySelectorAll(".tile").forEach(t => {
      const row = Number(t.dataset.row);
      t.querySelectorAll("[data-a]").forEach(b => b.addEventListener("click", () => {
        const a = b.dataset.a;
        if (a === "old") return showOld(s0(row), t.querySelector(".pxOld"));
        if (a === "swap") {
          if (!swapFrom) { swapFrom = row; return draw(); }
          if (swapFrom === row) { swapFrom = 0; return draw(); }
          const from = swapFrom; swapFrom = 0;
          return act(from, "swap", { other: row });
        }
        act(row, a, a === "regenerate" ? gpu() : {});
      }));
      t.querySelectorAll("[data-f]").forEach(el => el.addEventListener("change", () => act(row, el.dataset.f, { text: el.value })));
      t.addEventListener("dragstart", e => e.dataTransfer.setData("text/plain", String(row)));
      t.addEventListener("dragover", e => e.preventDefault());
      t.addEventListener("drop", e => { e.preventDefault(); const from = Number(e.dataTransfer.getData("text/plain")); if (from && from !== row) act(from, "swap", { other: row }); });
    });
  }
  const styleQ = () => ($("pxStyle").value ? `&style=${encodeURIComponent($("pxStyle").value)}` : "");
  async function load() {
    if (!slug) { grid.innerHTML = ""; return; }
    try { P = await api(`/api/pictures?project=${encodeURIComponent(slug)}${styleQ()}`); draw(); } catch (e) { /* nothing yet */ }
  }
  $("pxStyle").addEventListener("change", () => { swapFrom = 0; load(); });
  $("pxAuto").addEventListener("click", async () => {
    try { const j = await api("/api/auto_reuse", { project: slug, style: P.style, min_score: Number($("pxMin").value) }); load();
      note(`${j.reused.length} shot(s) filled from the library, about ${Math.round(j.gpu_seconds_saved / 60)} GPU minute(s) saved.`); } catch (e) { note(e.message, true); }
  });
  $("pxCheck").addEventListener("click", async () => {
    const o = typeof options === "function" ? options() : {};
    try { await api("/api/consistency_check", { project: slug, style: P.style, engine: o.engine, claude_model: o.claude_model }); startLog(); watch(); } catch (e) { note(e.message, true); }
  });
  $("pxAgain").addEventListener("click", async () => {
    const o = typeof options === "function" ? options() : {};
    try { await api("/api/pictures_render_again", { project: slug, style: P.style, engine: o.engine, claude_model: o.claude_model, ...gpu() }); startLog(); watch(); } catch (e) { note(e.message, true); }
  });
  async function watch() {
    clearTimeout(timer);
    await load();
    let running = false;
    try { running = (await api("/api/log?since=0")).running; } catch (e) { /* keep */ }
    if (running) timer = setTimeout(watch, 5000);
  }
  $("pxPrompts").addEventListener("click", async () => { try { P = await api("/api/pictures_prompts", { project: slug, style: $("pxStyle").value }); draw(); note(`${P.made.rows} picture prompts made.`); } catch (e) { note(e.message, true); } });
  $("pxRender").addEventListener("click", async () => { try { await api("/api/pictures_render", { project: slug, style: P.style, ...gpu() }); startLog(); watch(); } catch (e) { note(e.message, true); } });
  $("pxApprove").addEventListener("click", async () => { try { P = await api("/api/pictures_approve", { project: slug, style: P.style }); draw(); } catch (e) { note(e.message, true); } });
  $("pxPages").addEventListener("click", async () => {
    const o = typeof options === "function" ? options() : {};
    note("Your illustrator is planning the pages…");
    try { const j = await api("/api/page_plan", { project: slug, style: P && P.style, engine: o.engine, claude_model: o.claude_model }); note(`${j.pages.length} pages planned.`); } catch (e) { note(e.message, true); }
  });
  $("pxExport").addEventListener("click", async () => { try { P = await api("/api/pictures_export", { project: slug, style: P && P.style }); draw(); } catch (e) { note(e.message, true); } });
  window.loadPictures = p => { slug = p && p.slug && !p.legacy && /^[a-z0-9_]{2,40}$/.test(p.slug) ? p.slug : ""; swapFrom = 0; load(); };
})();

// The "Compare styles" card: one row per shot, one column per style.
(function () {
  const body = $("cmpBody");
  if (!body) return;
  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const slug = () => { const p = typeof cur === "function" ? cur() : null; return p && !p.legacy ? p.slug : ""; };
  $("cmpLoad").addEventListener("click", async () => {
    if (!slug()) return;
    const R = await api(`/api/style_compare?project=${encodeURIComponent(slug())}`);
    if (!R.rows.length) { body.innerHTML = '<p class="warn">No pictures yet.</p>'; return; }
    body.innerHTML = `<table class="data-table" aria-label="Every shot in every style"><tr><th>Shot</th>${R.styles.map(s => `<th>${esc(s.name)}${s.master ? " (master)" : ""}</th>`).join("")}</tr>
      ${R.rows.map(r => `<tr><td>${esc(r.scene)} / ${r.shot}</td>${R.styles.map(s => { const c = r.cells[s.id];
        return `<td>${c.image ? `<img src="/thumb/${esc(c.set)}/${esc(c.image)}" alt="${esc(r.scene)} shot ${r.shot} in ${esc(s.name)}" width="160" height="90" loading="lazy" style="object-fit:cover">` : '<span class="warn">none</span>'}
          <br><small>${c.approved ? "✓ " : ""}${c.score != null ? `match ${c.score}/10` : ""}${c.flagged ? " ⚑" : ""}${c.pending ? " (again)" : ""}</small></td>`; }).join("")}</tr>`).join("")}</table>`;
  });
  $("cmpPdf").addEventListener("click", async () => {
    try { const j = await api("/api/pictures_export", { project: slug(), kinds: ["comparison"] }); const f = j.exports.find(x => x.name === "style_comparison.pdf");
      $("cmpFile").innerHTML = f ? `<a class="btn btn--ghost" href="${esc(f.url)}" download>${esc(f.name)}</a>` : ""; } catch (e) { $("cmpFile").textContent = e.message; }
  });
})();
