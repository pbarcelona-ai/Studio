// studio/export.js - the "Export and credits" card. Uses $, api and cur() from core.js; core.js's renderProject() calls loadExports(p). Server: studio_app/export.py.
let exTimer = null;

function loadExports(p) {
  clearTimeout(exTimer);
  exTimer = setTimeout(() => exFetch(p || cur()), 300);
}

async function exFetch(p) {
  const note = $("exNote");
  if (!p || p.legacy || p.not_started) { $("exFilm").textContent = ""; note.textContent = p && p.legacy ? "Export is for books made from a file." : ""; return; }
  try {
    const [r, c] = await Promise.all([api(`/api/exports?project=${encodeURIComponent(p.slug)}`), api(`/api/credits?project=${encodeURIComponent(p.slug)}`)]);
    const keepFilm = $("exFilm").value, keepPreset = $("exPreset").value;
    $("exFilm").textContent = "";
    r.films.forEach(f => $("exFilm").appendChild(new Option(`${f.name}${f.seconds ? ` (${f.seconds.toFixed(0)} s)` : ""}${f.captions ? "" : " - no captions"}`, f.name)));
    if (!r.films.length) $("exFilm").appendChild(new Option("(make a film first)", ""));
    if ([...$("exFilm").options].some(o => o.value === keepFilm)) $("exFilm").value = keepFilm;
    $("exPreset").textContent = "";
    r.presets.forEach(x => { const o = new Option(x.label, x.id); o.title = x.note; $("exPreset").appendChild(o); });
    if (keepPreset) $("exPreset").value = keepPreset;
    note.textContent = r.presets.find(x => x.id === $("exPreset").value).note;
    exFillCredits(c);
    shLoad();
  } catch (e) { note.textContent = e.message; }
}

function exFillCredits(c) {
  const v = c.credits;
  $("crBased").value = v.based_on; $("crAuthor").value = v.author; $("crWritten").value = v.written_by; $("crDirected").value = v.directed_by;
  $("crNotes").value = v.content_notes; $("crRights").value = v.rights;
  $("crRating").textContent = ""; c.ratings.forEach(r => $("crRating").appendChild(new Option(r || "(none)", r))); $("crRating").value = v.rating;
  $("crCrew").value = v.crew.map(m => `${m.role} | ${m.name}`).join("\n");
  $("crPreview").textContent = c.preview.length ? c.preview.join("\n") : "(nothing to show yet)";
}

$("exPreset").addEventListener("change", () => { const o = $("exPreset").selectedOptions[0]; if (o) $("exNote").textContent = o.title; });
$("exRefresh").addEventListener("click", () => exFetch(cur()));
$("exGo").addEventListener("click", async () => {
  const p = cur(); if (!p) return;
  if (!$("exFilm").value) { $("exNote").textContent = "Make a film first (Make film), then export it here."; return; }
  try {
    await api("/api/export", { project: p.slug, film: $("exFilm").value, preset: $("exPreset").value, languages: $("exLangs").value, engine: $("engine").value, claude_model: $("cmodel").value, queue: true });
    $("exNote").textContent = "Exporting... the log shows progress and the file lands in the films folder.";
  } catch (e) { $("exNote").textContent = e.message; }
});
$("crSave").addEventListener("click", async () => {
  const p = cur(); if (!p) return;
  const crew = $("crCrew").value.split("\n").map(l => l.trim()).filter(Boolean).map(l => { const [role, ...rest] = l.split("|"); return rest.length ? { role: role.trim(), name: rest.join("|").trim() } : { role: "", name: role.trim() }; });
  try {
    const c = await api("/api/credits", { project: p.slug, credits: { based_on: $("crBased").value, author: $("crAuthor").value, written_by: $("crWritten").value, directed_by: $("crDirected").value,
      content_notes: $("crNotes").value, rights: $("crRights").value, rating: $("crRating").value, crew } });
    exFillCredits(c); $("crMsg").textContent = "Saved.";
  } catch (e) { $("crMsg").textContent = e.message; }
});

// ---- private preview links
async function shLoad() {
  const p = cur(); if (!p) return;
  try {
    const r = await api(`/api/shares?project=${encodeURIComponent(p.slug)}`);
    const ul = $("shList"); ul.textContent = "";
    r.links.forEach(l => {
      const li = document.createElement("li");
      const url = location.origin + l.path;
      const a = document.createElement("a"); a.href = l.path; a.target = "_blank"; a.rel = "noopener noreferrer"; a.textContent = `${l.title || l.film}`;
      li.append(a, ` - ${l.film}, ${l.views} view(s), ${l.expired ? "expired" : l.expires ? "until " + new Date(l.expires * 1000).toLocaleString() : "until revoked"} `);
      const copy = document.createElement("button"); copy.type = "button"; copy.className = "btn btn--ghost"; copy.textContent = "Copy link";
      copy.addEventListener("click", async () => { try { await navigator.clipboard.writeText(url); copy.textContent = "Copied"; } catch (e) { prompt("Copy this link:", url); } });
      const del = document.createElement("button"); del.type = "button"; del.className = "btn btn--ghost"; del.textContent = "Revoke";
      del.addEventListener("click", async () => { if (confirm("Revoke this link? Anyone who has it will lose access.")) { await api("/api/share_revoke", { project: p.slug, token: l.token }); shLoad(); } });
      li.append(copy, del); ul.appendChild(li);
    });
  } catch (e) { $("exNote").textContent = e.message; }
}
$("shMake").addEventListener("click", async () => {
  const p = cur(); if (!p) return;
  if (!$("exFilm").value) { $("exNote").textContent = "Make a film first, then make a link for it."; return; }
  try { await api("/api/share", { project: p.slug, film: $("exFilm").value, hours: Number($("shHours").value), title: $("shTitle").value }); $("shTitle").value = ""; shLoad(); }
  catch (e) { $("exNote").textContent = e.message; }
});
