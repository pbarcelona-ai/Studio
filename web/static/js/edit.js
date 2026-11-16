// studio/edit.js - M10: the "Timeline editor" card. Three tracks drawn to scale (video; voice and dialogue; music and effects) from the one
// EDL every style shares. Video clips: move left / right (keyboard) or drag, trim, split in two, ripple delete, cut or dissolve. Every item
// and track: volume. Alternative cuts, snap to the beat, music ducking, the Editor's notes (accept in one click), the REVIEW GATE, and the
// animatic in one style or all, with a preview player per style. Classic script: uses $, api, options() and poll() from core.js.
// Server: studio_app/edit_routes.py.
(function () {
  const tracks = $("edTracks");
  if (!tracks) return;
  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  let slug = "", E = null, timer = null;
  const note = (t, bad) => { $("edNote").textContent = t; $("edNote").style.color = bad ? "#d6455d" : ""; };
  const PX = 14;                                                  // pixels per second
  const mmss = s => `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, "0")}`;

  async function edit(body) { try { E = await api("/api/edl_edit", { project: slug, ...body }); draw(); } catch (e) { note(e.message, true); } }
  function block(x, label, extra, cls) {
    return `<div class="ed-item ${cls || ""}" style="position:absolute;left:${x.start * PX}px;width:${Math.max(18, (x.end - x.start) * PX - 2)}px;top:0;bottom:0;border-radius:5px;padding:2px 4px;overflow:hidden;font-size:11px;background:var(--bg-elevated, #2a2550);border:1px solid var(--border)" title="${esc(label)}">${esc(label)}${extra || ""}</div>`;
  }
  function draw() {
    if (!E.cut) { tracks.innerHTML = ""; note("Approve the shot list (and write the sound) to start the edit."); return; }
    const T = E.timeline, C = E.cut;
    $("edCut").innerHTML = E.cuts.map(c => `<option${c === E.current ? " selected" : ""}>${esc(c)}</option>`).join("");
    $("edDuck").value = C.duck_db;
    $("edApprove").disabled = E.gate.approved;
    const keepStyle = $("edStyle").value;
    $("edStyle").innerHTML = '<option value="">every style</option>' + E.styles.map(s => `<option${s === keepStyle ? " selected" : ""}>${esc(s)}</option>`).join("");
    note(`Runtime ${mmss(T.total)} · ${T.video.length} clips · ` + (E.gate.approved ? `approved ${E.gate.approved_at.slice(0, 16).replace("T", " ")}` : E.gate.changed_since ? "changed since it was approved" : "not approved yet"));
    const width = Math.ceil(T.total * PX) + 40;
    const vol = (target, v, what) => `<label style="font-size:11px">vol <input type="number" min="0" max="2" step="0.05" value="${v}" data-vol="${esc(target)}" aria-label="Volume of ${esc(what)}" style="width:4em"></label>`;
    tracks.innerHTML = `<div style="min-width:${width}px">
      ${["video", "voice", "music", "effects"].map(tr => `<div class="row" style="align-items:center;gap:6px;margin:4px 0"><b style="width:70px;font-size:12px">${tr}</b>${vol(tr, C.volumes[tr], tr + " track")}</div>
        <div style="position:relative;height:${tr === "video" ? 74 : 26}px;margin-bottom:4px">${T[tr].map(x => tr === "video"
          ? block(x, `${x.scene}/${x.shot} · ${x.seconds}s`, `<br><button type="button" data-mv="${esc(x.id)}" data-d="-1" aria-label="Move ${esc(x.id)} earlier">◀</button><button type="button" data-mv="${esc(x.id)}" data-d="1" aria-label="Move ${esc(x.id)} later">▶</button>
              <input type="number" min="0.5" max="600" step="0.1" value="${x.seconds}" data-trim="${esc(x.id)}" aria-label="Length of ${esc(x.id)}" style="width:3.6em">
              <button type="button" data-split="${esc(x.id)}" aria-label="Split ${esc(x.id)}">✂</button><button type="button" data-del="${esc(x.id)}" aria-label="Delete ${esc(x.id)}">×</button>
              <button type="button" data-tr="${esc(x.id)}" aria-label="Transition after ${esc(x.id)}: ${x.transition.kind}">${x.transition.kind === "dissolve" ? "◐" : "|"}</button>`, "")
          : block(x, `${x.id}${x.text ? " " + x.text : ""}`, " " + vol(x.id, x.volume, x.id), "")).join("")}</div>`).join("")}</div>`;
    tracks.querySelectorAll("[data-mv]").forEach(b => b.addEventListener("click", () => {
      const i = C.tracks.video.findIndex(v => v.id === b.dataset.mv), to = i + Number(b.dataset.d);
      if (to >= 0 && to < C.tracks.video.length) edit({ op: "move", id: b.dataset.mv, to });
    }));
    tracks.querySelectorAll("[data-trim]").forEach(el => el.addEventListener("change", () => edit({ op: "trim", id: el.dataset.trim, seconds: Number(el.value) })));
    tracks.querySelectorAll("[data-split]").forEach(b => b.addEventListener("click", () => { const v = C.tracks.video.find(x => x.id === b.dataset.split); edit({ op: "split", id: v.id, at: Math.round(v.seconds / 2 * 10) / 10 }); }));
    tracks.querySelectorAll("[data-del]").forEach(b => b.addEventListener("click", () => { if (confirm("Delete this clip? The rest closes up.")) edit({ op: "delete", id: b.dataset.del }); }));
    tracks.querySelectorAll("[data-tr]").forEach(b => b.addEventListener("click", () => { const v = C.tracks.video.find(x => x.id === b.dataset.tr); edit({ op: "transition", id: v.id, kind: v.transition.kind === "dissolve" ? "cut" : "dissolve" }); }));
    tracks.querySelectorAll("[data-vol]").forEach(el => el.addEventListener("change", () => edit({ op: "volume", target: el.dataset.vol, volume: Number(el.value) })));
    $("edSuggest").innerHTML = E.notes.length ? `<h4 style="margin:8px 0 2px">The editor's notes</h4><ul>${E.notes.map(n => `<li>${esc(n.op)} ${esc(n.id || "")}${n.seconds ? ` to ${n.seconds}s` : ""}: ${esc(n.why)}
      <button type="button" class="btn btn--ghost" data-note="${esc(n.nid)}" data-ok="1">Accept</button><button type="button" class="btn btn--ghost" data-note="${esc(n.nid)}" data-ok="">Dismiss</button></li>`).join("")}</ul>` : "";
    $("edSuggest").querySelectorAll("[data-note]").forEach(b => b.addEventListener("click", async () => {
      try { E = await api("/api/edl_note", { project: slug, nid: b.dataset.note, accept: Boolean(b.dataset.ok) }); draw(); } catch (e) { note(e.message, true); }
    }));
    $("edPreview").innerHTML = E.exports.map(f => `<figure style="margin:0"><video src="${esc(f.url)}" controls preload="none" width="320" height="180"></video><figcaption><small>${esc(f.name)}</small></figcaption></figure>`).join("");
  }
  async function load() {
    if (!slug) { tracks.innerHTML = ""; return; }
    try { E = await api(`/api/edl?project=${encodeURIComponent(slug)}`); draw(); } catch (e) { /* nothing yet */ }
  }
  async function watch() {
    clearTimeout(timer);
    await load();
    let running = false;
    try { running = (await api("/api/log?since=0")).running; } catch (e) { /* keep */ }
    if (running) timer = setTimeout(watch, 5000);
  }
  $("edCut").addEventListener("change", () => edit({ op: "use_cut", name: $("edCut").value }));
  $("edCopy").addEventListener("click", () => { const name = prompt("Name of the new cut (e.g. short, festival):"); if (name) edit({ op: "copy_cut", name }); });
  $("edSnap").addEventListener("click", () => edit({ op: "snap" }));
  $("edDuck").addEventListener("change", () => edit({ op: "duck", db: Number($("edDuck").value) }));
  $("edNotes").addEventListener("click", async () => {
    const o = typeof options === "function" ? options() : {};
    note("Your editor is watching the cut…");
    try { E = await api("/api/edl_suggest", { project: slug, engine: o.engine, claude_model: o.claude_model }); draw(); } catch (e) { note(e.message, true); }
  });
  $("edApprove").addEventListener("click", async () => { try { E = await api("/api/edl_approve", { project: slug }); draw(); } catch (e) { note(e.message, true); } });
  $("edAnimatic").addEventListener("click", async () => {
    try { await api("/api/animatic", { project: slug, style: $("edStyle").value, size: $("edSize").value, subtitles: $("edSubs").checked, cut: E && E.current });
      if (typeof poll === "function") { since = 0; $("log").textContent = ""; poll(); } watch(); } catch (e) { note(e.message, true); }
  });
  window.loadEdit = p => { slug = p && p.slug && !p.legacy && /^[a-z0-9_]{2,40}$/.test(p.slug) ? p.slug : ""; load(); };
})();
