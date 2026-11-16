// studio/breakdown.js - M4: the "Cast, places and shot list" card. Writes the continuity book (style-neutral identity tokens and
// personality profiles) and the director's breakdown + shot list as jobs, shows them for review, lets the owner edit a token or a shot,
// reorder shots (drag, or the Up / Down buttons from the keyboard), add and delete shots, and approve each (a REVIEW GATE: any later change
// takes the approval away). Classic script: uses $, api, options() and poll() from core.js. Server: studio_app/breakdown_routes.py.
(function () {
  const cbBody = $("cbBody"), slBody = $("slBody");
  if (!cbBody || !slBody) return;
  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  let slug = "", timer = null;
  const gateText = g => g.approved ? `Approved ${g.approved_at.slice(0, 16).replace("T", " ")}.` : g.changed_since ? "Changed since it was approved: approve it again." : "Not approved yet.";

  async function job(path, extra) {
    const o = typeof options === "function" ? options() : {};
    await api(path, { project: slug, engine: o.engine, claude_model: o.claude_model, ...(extra || {}) });
    if (typeof poll === "function") { since = 0; $("log").textContent = ""; poll(); }
    watch();
  }
  async function watch() {
    clearTimeout(timer);
    await Promise.all([loadCb(), loadSl()]);
    let running = false;
    try { running = (await api("/api/log?since=0")).running; } catch (e) { /* keep */ }
    if (running) timer = setTimeout(watch, 3000);
  }

  // ------------------------------------------------------------ continuity book
  async function loadCb() {
    if (!slug) return;
    let R;
    try { R = await api(`/api/continuity_book?project=${encodeURIComponent(slug)}`); } catch (e) { return; }
    $("cbApprove").disabled = !R.book || R.gate.approved;
    $("cbNote").textContent = R.book ? gateText(R.gate) : "Press Read it in first, then write the continuity book.";
    if (!R.book) { cbBody.innerHTML = ""; return; }
    const B = R.book;
    const pers = p => p ? Object.entries(p).map(([k, v]) => `<b>${esc(k)}</b>: ${esc(v)}`).join("; ") : "";
    const row = (kind, c) => `<tr><td>${esc(c.name)}</td><td><textarea rows="2" style="width:100%" data-kind="${kind}" data-name="${esc(c.name)}" aria-label="Look of ${esc(c.name)}">${esc(c.token)}</textarea>
      ${kind === "characters" ? `<small class="warn">${pers(c.personality)} · voice: ${esc(c.voice)}</small>` : ""}</td>
      <td><button type="button" class="btn btn--ghost" data-save="${kind}|${esc(c.name)}">Save</button></td></tr>`;
    const table = (title, kind) => (B[kind] || []).length ? `<h4 style="margin:8px 0 2px">${title}</h4><table class="data-table" aria-label="${title}">
      <tr><th>Name</th><th>How they look (in every style)</th><th></th></tr>${B[kind].map(c => row(kind, c)).join("")}</table>` : "";
    cbBody.innerHTML = table("Characters", "characters") + table("Locations", "locations") + table("Props", "props");
    cbBody.querySelectorAll("[data-save]").forEach(b => b.addEventListener("click", async () => {
      const [kind, name] = b.dataset.save.split("|");
      const ta = [...cbBody.querySelectorAll("textarea")].find(t => t.dataset.kind === kind && t.dataset.name === name);
      try { await api("/api/continuity_edit", { project: slug, kind, name, fields: { token: ta.value } }); $("cbNote").textContent = `Saved ${name}.`; loadCb(); }
      catch (e) { $("cbNote").textContent = e.message; }
    }));
  }

  // ------------------------------------------------------------ shot list
  async function edit(scene, n, body) {
    try { await api("/api/shot_edit", { project: slug, scene, n, ...body }); loadSl(); } catch (e) { $("slNote").textContent = e.message; }
  }
  async function loadSl() {
    if (!slug) return;
    let R;
    try { R = await api(`/api/shot_list?project=${encodeURIComponent(slug)}`); } catch (e) { return; }
    const L = R.list;
    $("slApprove").disabled = !L || R.gate.approved;
    if (!L) { slBody.innerHTML = ""; $("slNote").textContent = "Approve the continuity book, then write the shot list."; return; }
    const mins = s => `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, "0")}`;
    const pace = (L.checks && L.checks.pacing) || {}, cont = (L.checks && L.checks.continuity) || [];
    $("slNote").textContent = `${gateText(R.gate)} Runtime ${mins(L.runtime_seconds)} of ${mins(L.target_seconds)} wanted. ${pace.note || ""}`;
    slBody.innerHTML = (cont.length ? `<details><summary>Script supervisor's continuity notes (${cont.length})</summary><ul>${cont.map(c => `<li>Scene ${esc(c.scene)} shot ${esc(c.shot)}: ${esc(c.issue)}${c.fixed ? " (fixed)" : ""}</li>`).join("")}</ul></details>` : "")
      + L.scenes.map(sc => `<details><summary>${esc(sc.id)} ${esc(sc.heading)} · ${sc.shots.length} shots</summary>
        <p class="warn"><b>Intent</b>: ${esc(sc.breakdown.intent)} · <b>Beat</b>: ${esc(sc.breakdown.emotional_beat)} · <b>Blocking</b>: ${esc(sc.breakdown.blocking)} · <b>Performance</b>: ${esc(sc.breakdown.performance)}</p>
        <table class="data-table" aria-label="Shots of scene ${esc(sc.id)}"><tr><th>#</th><th>Shot</th><th>Camera</th><th>Action</th><th>Seconds</th><th>Priority</th><th>Order</th></tr>
        ${sc.shots.map(s => `<tr draggable="true" data-scene="${esc(sc.id)}" data-n="${s.n}"><td>${s.n}</td><td>${esc(s.type)} ${s.lens_mm} mm</td>
          <td><small>${esc(s.height)}, ${esc(s.movement)}; ${esc(s.lighting)}</small></td>
          <td><input type="text" value="${esc(s.action)}" data-f="action" aria-label="Action of shot ${s.n}" style="width:100%"></td>
          <td><input type="number" min="1.5" max="60" step="0.5" value="${s.seconds}" data-f="seconds" aria-label="Seconds of shot ${s.n}" style="width:5em"></td>
          <td><select data-f="priority" aria-label="Priority of shot ${s.n}">${[1, 2, 3].map(p => `<option${p === s.priority ? " selected" : ""}>${p}</option>`).join("")}</select></td>
          <td><button type="button" class="btn btn--ghost" data-act="up" aria-label="Move shot ${s.n} up"${s.n === 1 ? " disabled" : ""}>↑</button>
            <button type="button" class="btn btn--ghost" data-act="down" aria-label="Move shot ${s.n} down"${s.n === sc.shots.length ? " disabled" : ""}>↓</button>
            <button type="button" class="btn btn--ghost" data-act="add" aria-label="Add a shot after shot ${s.n}">+</button>
            <button type="button" class="btn btn--ghost" data-act="delete" aria-label="Delete shot ${s.n}"${sc.shots.length === 1 ? " disabled" : ""}>×</button></td></tr>`).join("")}</table></details>`).join("");
    slBody.querySelectorAll("tr[data-scene]").forEach(tr => {
      const scene = tr.dataset.scene, n = Number(tr.dataset.n);
      tr.querySelectorAll("[data-f]").forEach(el => el.addEventListener("change", () => edit(scene, n, { action: "edit", fields: { [el.dataset.f]: el.dataset.f === "action" ? el.value : Number(el.value) } })));
      tr.querySelectorAll("[data-act]").forEach(b => b.addEventListener("click", () => {
        const a = b.dataset.act;
        if (a === "up" || a === "down") return edit(scene, n, { action: "move", to: a === "up" ? n - 1 : n + 1 });
        if (a === "delete" && !confirm(`Delete shot ${n}?`)) return;
        edit(scene, n, { action: a });
      }));
      tr.addEventListener("dragstart", e => { e.dataTransfer.setData("text/plain", `${scene}|${n}`); });
      tr.addEventListener("dragover", e => e.preventDefault());
      tr.addEventListener("drop", e => {
        e.preventDefault();
        const [fromScene, from] = e.dataTransfer.getData("text/plain").split("|");
        if (fromScene === scene && Number(from) !== n) edit(scene, Number(from), { action: "move", to: n });
      });
    });
  }

  $("cbMake").addEventListener("click", () => job("/api/continuity_book").catch(e => { $("cbNote").textContent = e.message; }));
  $("cbApprove").addEventListener("click", async () => { try { await api("/api/continuity_approve", { project: slug }); loadCb(); } catch (e) { $("cbNote").textContent = e.message; } });
  $("slMake").addEventListener("click", () => job("/api/shot_list").catch(e => { $("slNote").textContent = e.message; }));
  $("slApprove").addEventListener("click", async () => { try { await api("/api/shot_list_approve", { project: slug }); loadSl(); } catch (e) { $("slNote").textContent = e.message; } });
  window.loadBreakdown = p => { slug = p && p.slug && !p.legacy && /^[a-z0-9_]{2,40}$/.test(p.slug) ? p.slug : ""; cbBody.innerHTML = slBody.innerHTML = ""; loadCb(); loadSl(); };
})();
