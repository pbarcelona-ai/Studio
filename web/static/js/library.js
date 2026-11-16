// studio/library.js - M8: the "Picture library and start over" card. Start over (keep: sources, settings, styles, continuity book,
// screenplay; everything else is archived, never deleted), earlier attempts (view, restore), and the picture library: assets with their
// versions (the liked one first), search, verdicts (liked / approved / rejected), purpose labels, and moving a version to another asset.
// Classic script: uses $ and api from core.js. Server: studio_app/library_routes.py.
(function () {
  const body = $("libBody");
  if (!body) return;
  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  let slug = "";
  const note = (t, bad) => { $("libNote").textContent = t; $("libNote").style.color = bad ? "#d6455d" : ""; };

  async function loadAttempts() {
    if (!slug) return;
    const j = await api(`/api/attempts?project=${encodeURIComponent(slug)}`);
    $("libAttempts").innerHTML = !j.attempts.length ? '<p class="warn">None yet.</p>' : `<ul>${j.attempts.map(a => `<li>${esc(a.label)} (kept: ${esc(a.keep.join(", ") || "nothing")})
      <button type="button" class="btn btn--ghost" data-view="${esc(a.id)}">Look inside</button> <button type="button" class="btn btn--ghost" data-restore="${esc(a.id)}">Bring it back</button>
      <div data-files="${esc(a.id)}"></div></li>`).join("")}</ul>`;
    $("libAttempts").querySelectorAll("[data-view]").forEach(b => b.addEventListener("click", async () => {
      const f = await api(`/api/attempt_files?project=${encodeURIComponent(slug)}&id=${encodeURIComponent(b.dataset.view)}`);
      $("libAttempts").querySelector(`[data-files="${b.dataset.view}"]`).innerHTML = `<pre style="max-height:200px;overflow:auto">${esc(f.files.join("\n"))}</pre>`;
    }));
    $("libAttempts").querySelectorAll("[data-restore]").forEach(b => b.addEventListener("click", async () => {
      if (!confirm("Bring this attempt back? The current version is archived first.")) return;
      try { const j2 = await api("/api/attempt_restore", { project: slug, id: b.dataset.restore }); note(`${j2.restored} is current again; the version before is ${j2.archived_current_as}.`); loadAttempts(); search(); if (typeof refresh === "function") refresh(); }
      catch (e) { note(e.message, true); }
    }));
  }
  async function search(again) {
    if (!slug) { body.innerHTML = ""; return; }
    const q = new URLSearchParams({ project: slug, q: $("libQ").value, style: $("libStyle").value, purpose: $("libPurpose").value, character: $("libChar").value, all_projects: $("libAll").checked ? "1" : "", refresh: again ? "1" : "" });
    let j;
    try { j = await api(`/api/picture_library?${q}`); } catch (e) { return note(e.message, true); }
    const sel = $("libStyle"), keep = sel.value;
    sel.innerHTML = '<option value="">any</option>' + j.styles.map(s => `<option${s === keep ? " selected" : ""}>${esc(s)}</option>`).join("");
    note(`${j.groups.length} asset(s), ${j.groups.reduce((n, g) => n + g.versions.length, 0)} version(s).`);
    body.innerHTML = j.groups.map(g => `<details><summary>${esc(g.name)} · ${g.versions.length} version(s)${g.project && g.project !== slug ? ` · ${esc(g.project)}` : ""}</summary>
      <div class="row" style="gap:8px;flex-wrap:wrap">${g.versions.map(v => `<div style="width:170px"><img src="${esc(v.thumb)}" alt="${esc(g.name)}, ${esc(v.attempt)}" width="160" height="90" loading="lazy" style="object-fit:cover;border-radius:6px">
        <small>${v.key === g.liked ? "★ liked · " : ""}${esc(v.attempt)}${v.score != null ? ` · match ${v.score}` : ""}</small>
        <div class="row" style="gap:3px;flex-wrap:wrap"><select data-verdict="${esc(v.key)}" aria-label="Verdict">${["", "liked", "approved", "rejected"].map(x => `<option value="${x}"${x === v.verdict ? " selected" : ""}>${x || "no verdict"}</option>`).join("")}</select>
        <select data-purpose="${esc(v.key)}" aria-label="Purpose">${j.purposes.map(x => `<option${x === v.purpose ? " selected" : ""}>${x}</option>`).join("")}</select>
        <button type="button" class="btn btn--ghost" data-own="${esc(v.key)}">Own asset</button></div></div>`).join("")}</div></details>`).join("");
    const post = async b => { try { await api("/api/library_item", { project: slug, ...b }); search(); } catch (e) { note(e.message, true); } };
    body.querySelectorAll("[data-verdict]").forEach(el => el.addEventListener("change", () => post({ key: el.dataset.verdict, verdict: el.value })));
    body.querySelectorAll("[data-purpose]").forEach(el => el.addEventListener("change", () => post({ key: el.dataset.purpose, purpose: el.value })));
    body.querySelectorAll("[data-own]").forEach(el => el.addEventListener("click", () => post({ key: el.dataset.own, own: true })));
  }
  $("libStartOver").addEventListener("click", () => $("libOver").classList.toggle("hidden"));
  $("libOverCancel").addEventListener("click", () => $("libOver").classList.add("hidden"));
  $("libOverGo").addEventListener("click", async () => {
    const keep = [...document.querySelectorAll("input[name=libKeep]:checked")].map(b => b.value);
    try { const j = await api("/api/start_over", { project: slug, keep }); $("libOver").classList.add("hidden"); note(`Started over. Everything made so far is in "${j.attempt.label}".`); loadAttempts(); search(); if (typeof refresh === "function") refresh(); }
    catch (e) { note(e.message, true); }
  });
  $("libRefresh").addEventListener("click", () => search(true));
  $("libSearch").addEventListener("click", () => search());
  $("libQ").addEventListener("keydown", e => { if (e.key === "Enter") search(); });
  window.loadLibrary = p => { slug = p && p.slug && !p.legacy && /^[a-z0-9_]{2,40}$/.test(p.slug) ? p.slug : ""; body.innerHTML = ""; loadAttempts().catch(() => {}); };
})();
