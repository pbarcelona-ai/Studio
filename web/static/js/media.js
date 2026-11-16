// studio/media.js - M13: the "Your footage and music" card. For each video / sound source: Watch and listen (shots, key frames, transcript, the
// story), then per shot: bind it (as a clip, a frame or a sound) to a character / location / shot / music cue, or use it as a real shot of the
// shot list; describe the footage's look for the AI shots; use a track as the score. And "Make a story from my clips".
// Classic script: uses $, api, options() and poll() from core.js. Server: studio_app/media_routes.py.
(function () {
  const list = $("mdList");
  if (!list) return;
  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  let slug = "";
  const o = () => (typeof options === "function" ? options() : {});
  const note = (t, bad) => { $("mdNote").textContent = t; $("mdNote").style.color = bad ? "#d6455d" : ""; };
  const post = async (path, body, msg) => { try { const j = await api(path, { project: slug, engine: o().engine, claude_model: o().claude_model, ...body }); draw(j); if (msg) note(msg(j)); } catch (e) { note(e.message, true); } };
  function draw(M) {
    list.innerHTML = !M.media.length ? '<p class="warn">No video or sound sources yet: add one in Add your sources.</p>' : M.media.map(m => `<details${m.understood ? "" : " open"}>
      <summary><b>${esc(m.title)}</b> (${esc(m.id)}) · ${m.understood ? `${m.shots.length} shot(s), ${m.transcript} transcript line(s)` : "not watched yet"}</summary>
      <div class="row" style="gap:6px;flex-wrap:wrap"><button type="button" class="btn btn--secondary" data-u="${esc(m.id)}">Watch and listen</button>
        <button type="button" class="btn btn--ghost" data-look="${esc(m.id)}"${m.understood ? "" : " disabled"}>Match the AI shots to this footage</button>
        <button type="button" class="btn btn--ghost" data-score="${esc(m.id)}">Use as the film's music</button></div>
      ${m.story ? `<p class="warn">${esc(m.story)}</p>` : ""}
      <table class="data-table" aria-label="Shots of ${esc(m.title)}">${m.shots.map(x => `<tr><td>${x.keyframe ? `<img src="/thumb/${esc(slug)}/${esc(x.keyframe)}" alt="Shot ${x.n}" width="96" height="54" loading="lazy">` : ""}</td>
        <td><small>${x.start.toFixed(1)}–${x.end.toFixed(1)} s</small><br>${esc(x.what || "")}${x.words ? `<br><small>“${esc(x.words)}”</small>` : ""}</td>
        <td><select data-what aria-label="Use shot ${x.n} as"><option value="clip">clip</option><option value="frame">frame</option><option value="audio">sound</option></select>
          <select data-kind aria-label="Bind shot ${x.n} to"><option>character</option><option>location</option><option>shot</option><option>music</option></select>
          <input type="text" data-target placeholder="MARA, the pier, S002/3…" aria-label="Bind shot ${x.n} to which" style="width:9em">
          <button type="button" class="btn btn--ghost" data-bind="${esc(m.id)}" data-s="${x.start}" data-e="${x.end}">Bind</button>
          <button type="button" class="btn btn--ghost" data-real="${esc(m.id)}" data-s="${x.start}" data-e="${x.end}">Use as a real shot…</button></td></tr>`).join("")}</table></details>`).join("")
      + (M.bindings.length ? `<details><summary>Bound pieces (${M.bindings.length})</summary><ul>${M.bindings.map(b => `<li>${esc(b.what)} ${b.start}–${b.end} s → ${esc(b.kind)} ${esc(b.target)}</li>`).join("")}</ul></details>` : "");
    list.querySelectorAll("[data-u]").forEach(b => b.addEventListener("click", async () => {
      try { await api("/api/media_understand", { project: slug, id: b.dataset.u, engine: o().engine, claude_model: o().claude_model }); if (typeof poll === "function") { since = 0; $("log").textContent = ""; poll(); } note("Watching and listening: see the job log."); }
      catch (e) { note(e.message, true); }
    }));
    list.querySelectorAll("[data-look]").forEach(b => b.addEventListener("click", () => post("/api/media_look", { id: b.dataset.look }, j => `Noted for the cinematographer: ${j.look.lens}; ${j.look.lighting}; ${j.look.colour}.`)));
    list.querySelectorAll("[data-score]").forEach(b => b.addEventListener("click", () => post("/api/media_score", { id: b.dataset.score }, j => `The film's music is set (${j.score.tempo_bpm} bpm): Snap to the beat in the Timeline editor.`)));
    list.querySelectorAll("[data-bind]").forEach(b => b.addEventListener("click", () => {
      const tr = b.closest("tr");
      post("/api/media_bind", { id: b.dataset.bind, start: Number(b.dataset.s), end: Number(b.dataset.e), what: tr.querySelector("[data-what]").value, kind: tr.querySelector("[data-kind]").value, target: tr.querySelector("[data-target]").value }, () => "Bound.");
    }));
    list.querySelectorAll("[data-real]").forEach(b => b.addEventListener("click", () => {
      const where = prompt("Which shot of the shot list should this be? (scene/shot, e.g. S002/3)");
      const m = where && where.match(/^(S\d{3})\/(\d+)$/i);
      if (!m) return;
      post("/api/media_footage", { id: b.dataset.real, start: Number(b.dataset.s), end: Number(b.dataset.e), scene: m[1].toUpperCase(), shot: Number(m[2]) }, () => `${m[1].toUpperCase()} shot ${m[2]} is now your footage, in every style.`);
    }));
  }
  async function load() { if (!slug) { list.innerHTML = ""; return; } try { draw(await api(`/api/media_sources?project=${encodeURIComponent(slug)}`)); } catch (e) { /* nothing */ } }
  $("mdAuto").addEventListener("click", () => { if (confirm("Make a new shot list from your clips? (The current one is kept in the history.)")) post("/api/media_autoedit", {}, j => `"${j.made.title}": ${j.made.shots} shots in ${j.made.scenes} scene(s). Next: the sound plan and the Timeline editor.`); });
  window.loadMedia = p => { slug = p && p.slug && !p.legacy && /^[a-z0-9_]{2,40}$/.test(p.slug) ? p.slug : ""; load(); };
})();
