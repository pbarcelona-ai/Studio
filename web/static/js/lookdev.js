// studio/lookdev.js - M5: the "Look development" card. For every chosen style: the style card (editable), the style translation of each
// character / location / prop (editable), the assembled prompt of a shot (to check), the look-development pictures (rendered on the GPU
// chosen in Make the Movie, with the keyframe image model) and "pick the best of 4", then the approval (a REVIEW GATE).
// Classic script: uses $, api, options() and poll() from core.js. Server: studio_app/styles_routes.py.
(function () {
  const body = $("ldBody");
  if (!body) return;
  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const CARD = ["prefix", "medium", "materials", "rendering", "lighting_language", "palette", "grade", "suffix", "negative"];
  let slug = "", timer = null;
  const note = (t, bad) => { $("ldNote").textContent = t; $("ldNote").style.color = bad ? "#d6455d" : ""; };

  async function watch() {
    clearTimeout(timer);
    await load();
    let running = false;
    try { running = (await api("/api/log?since=0")).running; } catch (e) { /* keep */ }
    if (running) timer = setTimeout(watch, 4000);
  }
  function styleHtml(s) {
    const ld = s.lookdev;
    const card = s.card ? `<table class="data-table" aria-label="${esc(s.name)} style card">${CARD.map(k => `<tr><th scope="row">${k.replace("_", " ")}</th>
      <td><input type="text" value="${esc(s.card[k])}" data-card="${esc(s.id)}" data-k="${k}" aria-label="${esc(s.name)} ${k.replace("_", " ")}" style="width:100%"></td></tr>`).join("")}</table>` : "<p class=\"warn\">No style card yet.</p>";
    const tr = s.translations ? ["characters", "locations", "props"].map(kind => Object.entries(s.translations[kind] || {}).map(([n, t]) => `<tr><td>${esc(n)}</td>
      <td><input type="text" value="${esc(t)}" data-tr="${esc(s.id)}" data-kind="${kind}" data-name="${esc(n)}" aria-label="${esc(n)} in ${esc(s.name)}" style="width:100%"></td></tr>`).join("")).join("") : "";
    const grid = ld.items.map(it => `<fieldset style="margin:6px 0"><legend>${esc(it.name)} · ${esc(it.view)}</legend><div class="row" style="gap:6px;flex-wrap:wrap">
      ${it.candidates.map(c => c.image ? `<label style="text-align:center"><img src="/thumb/${esc(ld.set)}/${esc(c.image)}" alt="${esc(it.name)} ${esc(it.view)}, variant ${c.variant}" width="128" height="128" loading="lazy" style="object-fit:cover;border-radius:6px"><br>
        <input type="radio" name="pick-${esc(s.id)}-${esc(it.key)}" value="${c.row}" data-pick="${esc(s.id)}" data-key="${esc(it.key)}"${it.pick === c.row ? " checked" : ""}> best</label>` : `<span class="warn">variant ${c.variant}: not rendered</span>`).join("")}</div></fieldset>`).join("");
    return `<details${s.master ? " open" : ""}><summary><b>${esc(s.name)}</b>${s.master ? " (master)" : ""}</summary>${card}
      ${tr ? `<h4 style="margin:8px 0 2px">How the cast and places are made in ${esc(s.name)}</h4><table class="data-table">${tr}</table>` : ""}
      ${ld.rows ? `<h4 style="margin:8px 0 2px">Character sheets and key art (${ld.rendered || 0} of ${ld.rows} pictures rendered)</h4>
        <button type="button" class="btn btn--secondary" data-render="${esc(s.id)}">Render the pictures</button>${grid}` : ""}</details>`;
  }
  async function load() {
    if (!slug) { body.innerHTML = ""; return; }
    let R;
    try { R = await api(`/api/styles?project=${encodeURIComponent(slug)}`); } catch (e) { return; }
    const g = R.gate;
    $("ldApprove").disabled = g.approved || !R.styles.some(s => s.card);
    note(g.approved ? `Approved ${g.approved_at.slice(0, 16).replace("T", " ")}.` : g.changed_since ? "Changed since it was approved: approve it again." : R.styles.length ? "Not approved yet." : "Choose the styles in the Format card first.");
    body.innerHTML = R.styles.map(styleHtml).join("");
    body.querySelectorAll("[data-card]").forEach(el => el.addEventListener("change", async () => {
      try { await api("/api/style_card_edit", { project: slug, style: el.dataset.card, fields: { [el.dataset.k]: el.value } }); note("Saved."); } catch (e) { note(e.message, true); }
    }));
    body.querySelectorAll("[data-tr]").forEach(el => el.addEventListener("change", async () => {
      try { await api("/api/style_translation_edit", { project: slug, style: el.dataset.tr, kind: el.dataset.kind, name: el.dataset.name, text: el.value }); note("Saved."); } catch (e) { note(e.message, true); }
    }));
    body.querySelectorAll("[data-pick]").forEach(el => el.addEventListener("change", async () => {
      try { await api("/api/lookdev_pick", { project: slug, style: el.dataset.pick, key: el.dataset.key, row: Number(el.value) }); load(); } catch (e) { note(e.message, true); }
    }));
    body.querySelectorAll("[data-render]").forEach(b => b.addEventListener("click", async () => {
      const o = typeof options === "function" ? options() : {};
      try {
        await api("/api/lookdev_render", { project: slug, style: b.dataset.render, service: o.service, gpu: o.gpu, kaggle_user: o.kaggle_user, image_model: o.keyframe_model });
        if (typeof poll === "function") { since = 0; $("log").textContent = ""; poll(); }
        note("Rendering: the pictures appear here as the run brings them back."); watch();
      } catch (e) { note(e.message, true); }
    }));
  }
  $("ldWrite").addEventListener("click", async () => {
    const o = typeof options === "function" ? options() : {};
    try { await api("/api/styles_write", { project: slug, engine: o.engine, claude_model: o.claude_model }); if (typeof poll === "function") { since = 0; $("log").textContent = ""; poll(); } watch(); }
    catch (e) { note(e.message, true); }
  });
  $("ldApprove").addEventListener("click", async () => { try { await api("/api/lookdev_approve", { project: slug }); load(); } catch (e) { note(e.message, true); } });
  window.loadLookDev = p => { slug = p && p.slug && !p.legacy && /^[a-z0-9_]{2,40}$/.test(p.slug) ? p.slug : ""; load(); };
})();
