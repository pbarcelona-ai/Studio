// studio/sound.js - M9: the "Voices, sound and music" card. The Voice Director's cast (change a voice or a character's usual emotion), the
// Sound Designer's effects and the Composer's cues, the REVIEW GATE, and the audiobook: read aloud with Kokoro on this computer, then joined
// into an M4B with a chapter per scene. Classic script: uses $, api, options() and poll() from core.js. Server: studio_app/sound_routes.py.
(function () {
  const body = $("sdBody");
  if (!body) return;
  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  let slug = "", timer = null;
  const note = (t, bad) => { $("sdNote").textContent = t; $("sdNote").style.color = bad ? "#d6455d" : ""; };
  const startLog = () => { if (typeof poll === "function") { since = 0; $("log").textContent = ""; poll(); } };

  async function watch() {
    clearTimeout(timer);
    await load();
    let running = false;
    try { running = (await api("/api/log?since=0")).running; } catch (e) { /* keep */ }
    if (running) timer = setTimeout(watch, 4000);
  }
  async function load() {
    if (!slug) { body.innerHTML = ""; return; }
    let R;
    try { R = await api(`/api/sound?project=${encodeURIComponent(slug)}`); } catch (e) { return; }
    const P = R.plan, g = R.gate, A = R.audiobook;
    $("sdApprove").disabled = !P || g.approved;
    $("sdAbRender").disabled = !A.chapters;
    $("sdAbMake").disabled = !g.approved || A.rendered < A.chapters;
    $("sdAbFile").innerHTML = A.file ? `<a class="btn btn--ghost" href="${esc(A.file)}" download>audiobook.m4b</a>` : A.chapters ? `<small class="warn">${A.rendered} of ${A.chapters} chapters read aloud</small>` : "";
    note(!P ? "Approve the shot list, then write the voices, sound and music." : g.approved ? `Approved ${g.approved_at.slice(0, 16).replace("T", " ")}.` : g.changed_since ? "Changed since it was approved." : "Not approved yet.");
    if (!P) { body.innerHTML = ""; return; }
    const row = (name, c) => `<tr><td>${esc(name)}</td><td><select data-who="${esc(name)}" data-f="voice" aria-label="Voice of ${esc(name)}">${R.voices.map(v => `<option${v === c.voice ? " selected" : ""}>${v}</option>`).join("")}</select></td>
      <td><select data-who="${esc(name)}" data-f="emotion" aria-label="Usual emotion of ${esc(name)}">${R.emotions.map(v => `<option${v === (c.emotion || "neutral") ? " selected" : ""}>${v}</option>`).join("")}</select></td><td><small>${esc(c.why || c.notes || "")}</small></td></tr>`;
    body.innerHTML = `<table class="data-table" aria-label="Voices"><tr><th>Who</th><th>Voice</th><th>Usually</th><th>Why</th></tr>${row("NARRATOR", P.narrator)}${Object.entries(P.cast).map(([n, c]) => row(n, c)).join("")}</table>
      <details><summary>Music cues (${P.cues.length})</summary><ul>${P.cues.map(c => `<li>${esc(c.first_scene)}–${esc(c.last_scene)}: ${esc(c.mood)}, ${c.tempo_bpm} bpm, ${esc(c.instrumentation)}</li>`).join("")}</ul></details>
      <details><summary>Effects and ambience</summary><ul>${Object.entries(P.effects).map(([sid, fx]) => `<li>${esc(sid)}: ${fx.map(e => `${e.n}. ${esc(e.sfx)}${e.ambience ? ` (${esc(e.ambience)})` : ""}`).join("; ")}</li>`).join("")}</ul></details>`;
    body.querySelectorAll("[data-who]").forEach(el => el.addEventListener("change", async () => {
      try { await api("/api/sound_cast", { project: slug, name: el.dataset.who, [el.dataset.f]: el.value }); load(); } catch (e) { note(e.message, true); }
    }));
  }
  $("sdPlan").addEventListener("click", async () => {
    const o = typeof options === "function" ? options() : {};
    try { await api("/api/sound_plan", { project: slug, engine: o.engine, claude_model: o.claude_model }); startLog(); watch(); } catch (e) { note(e.message, true); }
  });
  $("sdApprove").addEventListener("click", async () => { try { await api("/api/sound_approve", { project: slug }); load(); } catch (e) { note(e.message, true); } });
  $("sdAbRender").addEventListener("click", async () => { try { await api("/api/audiobook_render", { project: slug }); startLog(); watch(); } catch (e) { note(e.message, true); } });
  $("sdAbMake").addEventListener("click", async () => { try { await api("/api/audiobook_make", { project: slug }); startLog(); watch(); } catch (e) { note(e.message, true); } });
  window.loadSound = p => { slug = p && p.slug && !p.legacy && /^[a-z0-9_]{2,40}$/.test(p.slug) ? p.slug : ""; load(); };
})();
