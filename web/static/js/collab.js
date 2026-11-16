// studio/collab.js - M12: the Producer chat panel (on every step; collapsible; it never hides the step path), the "Notes and history"
// card: notes to the crew on anything (threads; each goes into that role's next revision and is resolved when the step is approved), and the
// project history (back to a moment, branch from it, compare two books). Classic script: uses $, api, options() and poll() from core.js.
// Server: studio_app/collab_routes.py.
(function () {
  const log = $("chatLog");
  if (!log) return;
  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  let slug = "", timer = null;
  const o = () => (typeof options === "function" ? options() : {});

  // ------------------------------------------------------------ the chat
  function drawChat(C) {
    const w = C.working;
    $("chatWorking").textContent = w.running ? `· ${w.crew ? w.crew.roles.join(" + ").replace(/_/g, " ") + " working: " : ""}${w.step}` : C.stopped ? `· stopped: ${C.stopped.label}` : "";
    log.innerHTML = C.messages.map(m => `<p style="margin:6px 0"><b>${m.who === "owner" ? "You" : "Producer"}:</b> ${esc(m.text)}
      ${m.plan && m.status === "proposed" ? `<br><small>${esc([...(m.plan.steps || []).map(s => "run " + s.replace(/_/g, " ")), ...(m.plan.notes || []).map(n => "note on " + n.kind + " " + n.ref),
        ...Object.keys(m.plan.settings || {}).map(k => "change " + k)].join("; "))}${m.plan.estimate ? " · " + esc(m.plan.estimate) : ""}</small><br>
        <button type="button" class="btn btn--secondary" data-plan="${esc(m.id)}" data-ok="1">Accept</button> <button type="button" class="btn btn--ghost" data-plan="${esc(m.id)}" data-ok="">Not now</button>`
        : m.status ? ` <small class="warn">(${esc(m.status)})</small>` : ""}</p>`).join("");
    log.scrollTop = log.scrollHeight;
    log.querySelectorAll("[data-plan]").forEach(b => b.addEventListener("click", async () => {
      try { drawChat(await api("/api/producer_decide", { project: slug, id: b.dataset.plan, accept: Boolean(b.dataset.ok), engine: o().engine, claude_model: o().claude_model })); watch(); }
      catch (e) { alert(e.message); }
    }));
  }
  async function loadChat() {
    if (!slug) return;
    try { drawChat(await api(`/api/producer?project=${encodeURIComponent(slug)}`)); } catch (e) { /* nothing */ }
  }
  async function watch() {
    clearTimeout(timer);
    await loadChat();
    if (!$("chatBody").hidden) timer = setTimeout(watch, 4000);
  }
  $("chatToggle").addEventListener("click", () => {
    const open = $("chatBody").hidden;
    $("chatBody").hidden = !open;
    $("chatToggle").setAttribute("aria-expanded", String(open));
    if (open) watch();
  });
  const post = async (path, body) => { try { drawChat(await api(path, { project: slug, ...body })); } catch (e) { alert(e.message); } };
  $("chatSend").addEventListener("click", async () => {
    const t = $("chatText").value.trim();
    if (!t || !slug) return;
    $("chatText").value = "";
    await post("/api/producer", { text: t, engine: o().engine, claude_model: o().claude_model });
  });
  $("chatText").addEventListener("keydown", e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); $("chatSend").click(); } });
  $("chatStop").addEventListener("click", () => post("/api/producer_stop", {}));
  $("chatAdd").addEventListener("click", () => { const t = $("chatText").value.trim(); if (!t) return alert("Write the information in the box first."); $("chatText").value = ""; post("/api/producer_add", { text: t }); });
  $("chatGo").addEventListener("click", () => post("/api/producer_continue", {}));

  // ------------------------------------------------------------ notes
  async function loadNotes() {
    if (!slug) return;
    let N;
    try { N = await api(`/api/notes?project=${encodeURIComponent(slug)}`); } catch (e) { return; }
    const k = $("ntKind").value;
    $("ntKind").innerHTML = Object.keys(N.kinds).map(x => `<option${x === k ? " selected" : ""}>${x}</option>`).join("");
    if ($("ntRole").options.length <= 1) $("ntRole").innerHTML += N.roles.map(r => `<option value="${r}">${r.replace(/_/g, " ")}</option>`).join("");
    $("ntList").innerHTML = !N.notes.length ? '<p class="warn">No notes yet.</p>' : N.notes.slice().reverse().map(n => `<details${n.status === "open" ? " open" : ""}>
      <summary>${n.status === "open" ? "●" : "✓"} On ${esc(n.target.kind)} ${esc(n.target.ref)} · for the ${esc(n.role.replace(/_/g, " "))}</summary>
      ${n.messages.map(m => `<p style="margin:2px 0"><small>${esc(m.who)}, ${esc(m.at.slice(0, 16).replace("T", " "))}:</small> ${esc(m.text)}</p>`).join("")}
      <div class="row" style="gap:4px;flex-wrap:wrap"><input type="text" data-reply="${esc(n.id)}" aria-label="Reply to this note" placeholder="Reply…" style="flex:1">
        <button type="button" class="btn btn--ghost" data-status="${esc(n.id)}" data-to="${n.status === "open" ? "resolved" : "open"}">${n.status === "open" ? "Mark resolved" : "Open again"}</button></div></details>`).join("");
    const op = async (path, body) => { try { await api(path, { project: slug, ...body }); loadNotes(); } catch (e) { $("ntNote").textContent = e.message; } };
    $("ntList").querySelectorAll("[data-reply]").forEach(el => el.addEventListener("keydown", e => { if (e.key === "Enter" && el.value.trim()) op("/api/note_reply", { id: el.dataset.reply, text: el.value }); }));
    $("ntList").querySelectorAll("[data-status]").forEach(b => b.addEventListener("click", () => op("/api/note_status", { id: b.dataset.status, status: b.dataset.to })));
  }
  $("ntAdd").addEventListener("click", async () => {
    try { await api("/api/note_add", { project: slug, kind: $("ntKind").value, ref: $("ntRef").value, text: $("ntText").value, role: $("ntRole").value });
      $("ntText").value = ""; $("ntNote").textContent = "The note is with the crew: it goes into their next revision."; loadNotes(); } catch (e) { $("ntNote").textContent = e.message; }
  });

  // ------------------------------------------------------------ history
  async function loadHistory() {
    if (!slug) return;
    let H;
    try { H = await api(`/api/history?project=${encodeURIComponent(slug)}`); } catch (e) { return; }
    $("hsBranchOf").textContent = H.branch_of ? `A branch of ${H.branch_of.from} (${H.branch_of.label})` : "";
    $("hsList").innerHTML = !H.moments.length ? '<p class="warn">No moments yet: every approval and accepted chat request makes one.</p>' : `<ul>${H.moments.map(m => `<li>${esc(m.at.replace("T", " "))} · ${esc(m.label)}
      <button type="button" class="btn btn--ghost" data-back="${esc(m.id)}">Back to this moment</button> <button type="button" class="btn btn--ghost" data-branch="${esc(m.id)}">Branch from here</button></li>`).join("")}</ul>`;
    $("hsList").querySelectorAll("[data-back]").forEach(b => b.addEventListener("click", async () => {
      if (!confirm("Go back to this moment? The way things are now is saved as a moment first.")) return;
      try { await api("/api/moment_back", { project: slug, id: b.dataset.back }); loadHistory(); if (typeof refresh === "function") refresh(); } catch (e) { alert(e.message); }
    }));
    $("hsList").querySelectorAll("[data-branch]").forEach(b => b.addEventListener("click", async () => {
      const name = prompt("Name of the new book (lowercase letters, digits, _):", `${slug}_b`.slice(0, 40));
      if (!name) return;
      try { const j = await api("/api/branch", { project: slug, id: b.dataset.branch, name }); alert(`Made ${j.branch}. Pick it at the top of the page.`); if (typeof refresh === "function") refresh(); } catch (e) { alert(e.message); }
    }));
  }
  $("hsSave").addEventListener("click", async () => { try { await api("/api/moment", { project: slug, label: prompt("A name for this moment:", "saved by hand") || "saved by hand" }); loadHistory(); } catch (e) { alert(e.message); } });
  $("hsCompare").addEventListener("click", async () => {
    try {
      const R = await api(`/api/branch_compare?a=${encodeURIComponent(slug)}&b=${encodeURIComponent($("hsCmp").value.trim())}`);
      $("hsCompareOut").innerHTML = `<p class="warn">Runtime: ${R.runtime.a ?? "–"} s / ${R.runtime.b ?? "–"} s</p>
        <pre style="white-space:pre-wrap">${esc(R.script_diff.join("\\n") || "The screenplays are the same.")}</pre>
        <table class="data-table" aria-label="Storyboards side by side"><tr><th>Shot</th><th>${esc(R.a)}</th><th>${esc(R.b)}</th></tr>${R.storyboard.map(x => `<tr><td>${x.row}</td>
          ${["a", "b"].map(k => `<td>${x[k] && x[k].image ? `<img src="/thumb/${esc(x[k].set)}/${esc(x[k].image)}" alt="Shot ${x.row} in ${esc(R[k])}" width="120" height="68" loading="lazy">` : "–"}</td>`).join("")}</tr>`).join("")}</table>`;
    } catch (e) { $("hsCompareOut").textContent = e.message; }
  });

  window.loadCollab = p => { slug = p && p.slug && !p.legacy && /^[a-z0-9_]{2,40}$/.test(p.slug) ? p.slug : ""; loadChat(); loadNotes(); loadHistory(); };
})();
