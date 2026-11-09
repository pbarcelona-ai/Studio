// studio/direction.js - creative direction, voice cast, scene enhancement, new scene
// Classic script: shares globals with the other studio/*.js files; load order is set in index.html.
// ---- Creative Direction API ----
let dirConv = [];  // conversation history: [{role: "user"|"assistant", content: "..."}]

async function dirSend() {
  const notes = $("dirNotes").value.trim();
  if (!notes && dirConv.length === 0) {
    $("dirStatus").textContent = "write something first";
    $("dirStatus").className = "err";
    return;
  }
  $("dirStatus").textContent = "asking AI…";
  $("dirStatus").className = "warn";
  $("bDirSend").disabled = true;
  $("bDirFollowup").disabled = true;
  try {
    const proj = $("proj").value;
    const j = await api("/api/creative_direction", {
      project: proj,
      messages: [...dirConv, {role: "user", content: notes}],
      engine: $("engine").value, claude_model: $("cmodel").value
    });
    dirConv = j.messages;
    renderDirResponse();
    $("dirNotes").value = "";
    $("dirStatus").textContent = j.status || "done";
    $("dirStatus").className = "warn";
  } catch (e) {
    $("dirStatus").textContent = e.message;
    $("dirStatus").className = "err";
  }
  $("bDirSend").disabled = false;
  $("bDirFollowup").disabled = false;
}

async function dirFollowup() {
  const txt = $("dirFollowup").value.trim();
  if (!txt) return;
  $("dirFollowup").value = "";
  $("dirStatus").textContent = "asking AI…";
  $("dirStatus").className = "warn";
  $("bDirSend").disabled = true;
  $("bDirFollowup").disabled = true;
  try {
    const proj = $("proj").value;
    const j = await api("/api/creative_direction", {
      project: proj,
      messages: [...dirConv, {role: "user", content: txt}],
      engine: $("engine").value, claude_model: $("cmodel").value
    });
    dirConv = j.messages;
    renderDirResponse();
    $("dirStatus").textContent = j.status || "done";
    $("dirStatus").className = "warn";
  } catch (e) {
    $("dirStatus").textContent = e.message;
    $("dirStatus").className = "err";
  }
  $("bDirSend").disabled = false;
  $("bDirFollowup").disabled = false;
}

function dirClear() {
  dirConv = [];
  renderDirResponse();
  $("dirNotes").value = "";
  $("dirFollowup").value = "";
  $("dirStatus").textContent = "conversation cleared";
  $("dirStatus").className = "warn";
}

function renderDirResponse() {
  const box = $("dirResponse");
  if (!dirConv.length) {
    box.innerHTML = '<span class="warn">No conversation yet. Enter your direction above and click Send.</span>';
    $("dirSaved").classList.add("hidden");
    return;
  }
  box.innerHTML = dirConv.map(m => {
    const cls = m.role === "user" ? "dir-user" : "dir-assistant";
    const label = m.role === "user" ? "You" : "AI";
    return `<div class="${cls}" style="margin-bottom:8px;padding:6px 8px;background:${m.role==="user" ? "var(--accent)" : "var(--code)"};border-radius:6px;color:${m.role==="user" ? "var(--accent-ink)" : "var(--fg)"}">
      <b style="font-size:11px;opacity:0.7">${label}:</b>
      <div style="margin-top:2px;white-space:pre-wrap">${escapeHtml(m.content)}</div>
    </div>`;
  }).join("");
  box.scrollTop = box.scrollHeight;
  
  // Show saved direction (last assistant message that contains the finalized direction)
  const lastAssistant = [...dirConv].reverse().find(m => m.role === "assistant" && m.finalized);
  if (lastAssistant) {
    $("dirSaved").textContent = lastAssistant.content;
    $("dirSaved").classList.remove("hidden");
  } else {
    $("dirSaved").classList.add("hidden");
  }
}

function escapeHtml(s) {
  // escapes quotes too: the result is also used inside "..." attribute values
  return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

// Load saved direction on project change
$("proj").addEventListener("change", async () => {
  const proj = $("proj").value;
  if (!proj) return;
  try {
    const j = await api("/api/creative_direction_get", { project: proj });
    if (j.messages) {
      dirConv = j.messages;
      renderDirResponse();
    }
    // Also load global parameters for the new project
    await loadGlobalParams(proj);
  } catch (e) {
    // ignore
  }
});


// ---- Voice cast: one Kokoro voice per speaker; a character's voice overrides the narrator's ----
let castData = null;
function renderCast() {
  const t = $("castTable");
  if (!castData || !castData.speakers.length) {
    t.innerHTML = `<tr><td class="warn">${castData ? "No spoken lines in this book yet." : "Pick a book, then Load speakers."}</td></tr>`;
    return;
  }
  const opts = v => `<option value="">(leave as is)</option>` + castData.voices.map(x => `<option value="${x}"${x === v ? " selected" : ""}>${x}</option>`).join("")
    + (v && !castData.voices.includes(v) ? `<option value="${escapeHtml(v)}" selected>${escapeHtml(v)}</option>` : "");
  t.innerHTML = `<tr><th>Speaker</th><th>Lines</th><th>Voice now</th><th>Suggested</th><th>Cast voice</th></tr>` + castData.speakers.map((sp, i) =>
    `<tr><td>${escapeHtml(sp.name)}</td><td>${sp.lines}</td><td>${escapeHtml(sp.voice || "default")}</td>` +
    `<td>${escapeHtml(sp.suggest || sp.book || "")}</td>` +
    `<td><select data-cast="${i}" aria-label="Voice for ${escapeHtml(sp.name)}">${opts(sp.cast)}</select></td></tr>`).join("");
}
async function loadCast(body) {
  const proj = $("proj").value;
  if (!proj) { $("castStatus").textContent = "pick a book first"; return; }
  $("castStatus").textContent = body ? "saving..." : "loading...";
  try {
    const j = await api("/api/voice_cast", { project: proj, series: $("castSeries").value, ...(body || {}) });
    castData = j;
    renderCast();
    $("castStatus").textContent = body
      ? `Saved. ${j.changed.length} row(s) re-voiced` + (j.moved ? `, ${j.moved} old narration file(s) moved to the Trash` : "") + "."
      : `${j.speakers.length} speaker(s).`;
  } catch (e) {
    castData = null; renderCast();
    $("castStatus").textContent = e.message;
  }
}
$("bCastLoad").addEventListener("click", () => loadCast());
$("castSeries").addEventListener("change", () => { if (castData) loadCast(); });
$("bCastSuggest").addEventListener("click", () => {
  if (!castData) return;
  castData.speakers.forEach((sp, i) => {
    const sel = document.querySelector(`#castTable select[data-cast="${i}"]`);
    const want = sp.suggest || sp.book;
    if (sel && !sel.value && want && castData.voices.includes(want)) sel.value = want;
  });
});
$("bCastSave").addEventListener("click", () => {
  if (!castData) return;
  const cast = {};
  castData.speakers.forEach((sp, i) => { const sel = document.querySelector(`#castTable select[data-cast="${i}"]`); if (sel && sel.value) cast[sp.name] = sel.value; });
  loadCast({ cast, move_old: $("castMoveOld").checked });
});
$("proj").addEventListener("change", () => { castData = null; renderCast(); $("castStatus").textContent = ""; });


// ---- Scene Enhancement API ----
let enhConv = [];  // conversation history for enhancements
let enhSelection = [];  // array of selected clips: [{n, video, narration, sfx, music, prompt}]
let enhCurrentIndex = -1;  // current clip index in enhSelection

function getSelectedClips() {
  // Get selected clips from the film panel table
  const rows = filmSelection();
  if (!rows.length) return [];

  // Get prompts for each row from the project
  const proj = $("proj").value;
  return rows.map(r => ({
    n: r.n,
    video: r.video,
    narration: r.narration,
    sfx: r.sfx,
    music: r.music,
    prompt: r.prompt || ""
  }));
}

function updateEnhButtons() {
  const hasSelection = enhSelection.length > 0;
  const hasNotes = $("enhNotes").value.trim().length > 0;
  const isMulti = enhSelection.length > 1;

  $("bEnhPreview").disabled = !hasSelection || !hasNotes;
  $("bEnhUpdate").disabled = !hasSelection || !hasNotes;
  $("bEnhNext").disabled = !hasSelection || !isMulti || enhCurrentIndex >= enhSelection.length - 1;
  $("bEnhClear").disabled = !hasSelection;
}

function renderEnhResponse(html) {
  $("enhResponse").innerHTML = html;
}

function showEnhStatus(msg, isError = false) {
  $("enhStatus").textContent = msg;
  $("enhStatus").className = isError ? "err" : "warn";
}

async function loadClipPrompt(rowNum) {
  // Try to get the prompt for this clip from the project
  const proj = $("proj").value;
  try {
    const j = await api(`/api/clip_prompt?project=${encodeURIComponent(proj)}&row=${rowNum}`);
    return j.prompt || "";
  } catch (e) {
    return "";
  }
}

async function enhRefreshSelection() {
  enhSelection = getSelectedClips();
  if (enhSelection.length === 0) {
    enhCurrentIndex = -1;
    renderEnhResponse('<span class="warn">No clips selected. Select clips in the "Make the film" panel below, then return here.</span>');
    showEnhStatus("");
    updateEnhButtons();
    return;
  }

  // Load prompts for all selected clips
  for (let i = 0; i < enhSelection.length; i++) {
    if (!enhSelection[i].prompt) {
      enhSelection[i].prompt = await loadClipPrompt(enhSelection[i].n);
    }
  }

  enhCurrentIndex = 0;
  showCurrentEnhClip();
  updateEnhButtons();
}

function showCurrentEnhClip() {
  if (enhCurrentIndex < 0 || enhCurrentIndex >= enhSelection.length) return;
  const clip = enhSelection[enhCurrentIndex];
  const isMulti = enhSelection.length > 1;
  let html = `<div style="margin-bottom:8px"><b>Clip ${clip.n}</b> ${isMulti ? `(${enhCurrentIndex + 1} of ${enhSelection.length})` : ""}</div>`;
  html += `<div style="font-size:12px;color:var(--fg-muted);margin-bottom:8px">${clip.prompt || "No prompt available"}</div>`;
  if (enhConv.length) {
    html += enhConv.map(m => {
      const cls = m.role === "user" ? "dir-user" : "dir-assistant";
      const label = m.role === "user" ? "You" : "AI";
      return `<div class="${cls}" style="margin-bottom:6px;padding:6px 8px;background:${m.role==="user" ? "var(--accent)" : "var(--code)"};border-radius:6px;color:${m.role==="user" ? "var(--accent-ink)" : "var(--fg)"}">
        <b style="font-size:11px;opacity:0.7">${label}:</b>
        <div style="margin-top:2px;white-space:pre-wrap">${escapeHtml(m.content)}</div>
      </div>`;
    }).join("");
  }
  renderEnhResponse(html);
}

async function enhPreview() {
  if (enhCurrentIndex < 0 || enhCurrentIndex >= enhSelection.length) return;
  const notes = $("enhNotes").value.trim();
  if (!notes) return;

  const clip = enhSelection[enhCurrentIndex];
  showEnhStatus("Generating preview…");
  $("bEnhPreview").disabled = true;

  try {
    const proj = $("proj").value;
    const j = await api("/api/enhance_prompt", {
      project: proj,
      row: clip.n,
      original_prompt: clip.prompt,
      instruction: notes,
      preview_only: true
    });

    enhConv.push({role: "user", content: notes});
    enhConv.push({role: "assistant", content: j.preview || j.updated_prompt || "Preview generated"});
    showCurrentEnhClip();
    showEnhStatus(j.feedback || "Preview ready. Click Update to apply or Next for another clip.");
  } catch (e) {
    showEnhStatus(e.message, true);
  }
  $("bEnhPreview").disabled = false;
  updateEnhButtons();
}

async function enhUpdate() {
  if (enhCurrentIndex < 0 || enhCurrentIndex >= enhSelection.length) return;
  const notes = $("enhNotes").value.trim();
  if (!notes) return;

  const clip = enhSelection[enhCurrentIndex];
  showEnhStatus("Updating prompt…");
  $("bEnhUpdate").disabled = true;

  try {
    const proj = $("proj").value;
    const j = await api("/api/enhance_prompt", {
      project: proj,
      row: clip.n,
      original_prompt: clip.prompt,
      instruction: notes,
      preview_only: false
    });

    enhConv.push({role: "user", content: notes});
    enhConv.push({role: "assistant", content: j.updated_prompt || "Prompt updated", finalized: true});
    clip.prompt = j.updated_prompt || clip.prompt;
    showCurrentEnhClip();
    showEnhStatus("Prompt updated successfully.");
  } catch (e) {
    showEnhStatus(e.message, true);
  }
  $("bEnhUpdate").disabled = false;
  updateEnhButtons();
}

function enhNext() {
  if (enhCurrentIndex < enhSelection.length - 1) {
    enhCurrentIndex++;
    enhConv = []; // Clear conversation for next clip
    $("enhNotes").value = "";
    showCurrentEnhClip();
    showEnhStatus("");
    updateEnhButtons();
  }
}

function enhClear() {
  enhSelection = [];
  enhCurrentIndex = -1;
  enhConv = [];
  $("enhNotes").value = "";
  renderEnhResponse('<span class="warn">Select clip(s) from the film panel or prompts panel, then enter your enhancement above.</span>');
  showEnhStatus("");
  updateEnhButtons();
}

// ---- New Scene Functions ----
let newSceneConv = [];
let newSceneDraft = null;      // the last previewed shot, so Apply inserts exactly what was shown

async function newScenePreview() {
  const desc = $("newSceneDesc").value.trim();
  const series = $("newSceneSeries").value;
  const chapter = $("newSceneChapter").value;
  const position = $("newScenePos").value;

  if (!desc || !series || !chapter) return;

  showNewSceneStatus("Generating preview…");
  $("bNewScenePreview").disabled = true;

  try {
    const proj = $("proj").value;
    const j = await api("/api/new_scene", {
      project: proj,
      series: series,
      chapter: chapter,
      position: position,
      description: desc,
      preview_only: true,
      engine: $("engine").value, claude_model: $("cmodel").value
    });
    newSceneDraft = { prompt: j.prompt, narration: j.narration, desc };

    newSceneConv.push({role: "user", content: desc});
    newSceneConv.push({role: "assistant", content: j.preview || j.scene || "Preview generated"});
    showNewSceneResponse();
    showNewSceneStatus(j.feedback || "Preview ready. Click Apply & Insert to create the scene.");
  } catch (e) {
    showNewSceneStatus(e.message, true);
  }
  $("bNewScenePreview").disabled = false;
  updateNewSceneButtons();
}

async function newSceneApply() {
  const desc = $("newSceneDesc").value.trim();
  const series = $("newSceneSeries").value;
  const chapter = $("newSceneChapter").value;
  const position = $("newScenePos").value;

  if (!desc || !series || !chapter) return;

  showNewSceneStatus("Creating new scene…");
  $("bNewSceneApply").disabled = true;

  try {
    const proj = $("proj").value;
    const j = await api("/api/new_scene", {
      project: proj,
      series: series,
      chapter: chapter,
      position: position,
      description: desc,
      preview_only: false,
      prompt: newSceneDraft && newSceneDraft.desc === desc ? newSceneDraft.prompt : "",
      narration: newSceneDraft && newSceneDraft.desc === desc ? newSceneDraft.narration : ""
    });

    newSceneConv.push({role: "user", content: desc});
    newSceneConv.push({role: "assistant", content: j.scene || "Scene created", finalized: true});
    showNewSceneResponse();
    showNewSceneStatus("New scene inserted successfully.");
    // Reload the project to reflect changes
    await loadStatus(false);
  } catch (e) {
    showNewSceneStatus(e.message, true);
  }
  $("bNewSceneApply").disabled = false;
  updateNewSceneButtons();
}

function newSceneClear() {
  newSceneConv = [];
  $("newSceneDesc").value = "";
  showNewSceneResponse('<span class="warn">Select a series and chapter, then describe the new scene above.</span>');
  showNewSceneStatus("");
  updateNewSceneButtons();
}

function updateNewSceneButtons() {
  const desc = $("newSceneDesc").value.trim();
  const series = $("newSceneSeries").value;
  const chapter = $("newSceneChapter").value;
  const hasAll = desc && series && chapter;
  $("bNewScenePreview").disabled = !hasAll;
  $("bNewSceneApply").disabled = !hasAll;
  $("bNewSceneClear").disabled = !hasAll && newSceneConv.length === 0;
}

function showNewSceneResponse(html) {
  if (html) {
    $("newSceneResponse").innerHTML = html;
  } else if (newSceneConv.length) {
    let html = newSceneConv.map(m => {
      const cls = m.role === "user" ? "dir-user" : "dir-assistant";
      const label = m.role === "user" ? "You" : "AI";
      return `<div class="${cls}" style="margin-bottom:6px;padding:6px 8px;background:${m.role==="user" ? "var(--accent)" : "var(--code)"};border-radius:6px;color:${m.role==="user" ? "var(--accent-ink)" : "var(--fg)"}">
        <b style="font-size:11px;opacity:0.7">${label}:</b>
        <div style="margin-top:2px;white-space:pre-wrap">${escapeHtml(m.content)}</div>
      </div>`;
    }).join("");
    $("newSceneResponse").innerHTML = html;
  }
}

function showNewSceneStatus(msg, isError) {
  const el = $("newSceneStatus");
  el.textContent = msg;
  el.className = isError ? "err" : "warn";
}

// Wire up event listeners
$("bEnhPreview").onclick = enhPreview;
$("bEnhUpdate").onclick = enhUpdate;
$("bEnhNext").onclick = enhNext;
$("bEnhClear").onclick = enhClear;
$("enhNotes").addEventListener("input", updateEnhButtons);
$("enhNotes").addEventListener("keydown", e => { if (e.key === "Enter" && !e.shiftKey && !e.ctrlKey) { e.preventDefault(); if (!$("bEnhPreview").disabled) enhPreview(); } });

// New Scene event listeners
$("bNewScenePreview").onclick = newScenePreview;
$("bNewSceneApply").onclick = newSceneApply;
$("bNewSceneClear").onclick = newSceneClear;
$("newSceneDesc").addEventListener("input", updateNewSceneButtons);
$("newSceneDesc").addEventListener("keydown", e => { if (e.key === "Enter" && !e.shiftKey && !e.ctrlKey) { e.preventDefault(); if (!$("bNewScenePreview").disabled) newScenePreview(); } });
$("newSceneSeries").addEventListener("change", updateNewSceneButtons);
$("newSceneChapter").addEventListener("change", updateNewSceneButtons);
$("newScenePos").addEventListener("change", updateNewSceneButtons);

// Refresh enhancement selection when film panel selection changes
const origUpdateFilmSummary = updateFilmSummary;
updateFilmSummary = function() {
  origUpdateFilmSummary();
  if (typeof enhRefreshSelection === "function") enhRefreshSelection();
};

// Also refresh when project changes
$("proj").addEventListener("change", () => {
  enhClear();
});

// Expose for film panel to call
window.enhRefreshSelection = enhRefreshSelection;

document.addEventListener("change", applyConstraints);
loadStatus().then(poll).catch(e => { $("tools").textContent = "Cannot reach studio.py: " + e.message; });
