// studio/prompts.js - chapter shot counts, job helpers, Movies tab, presets, Single Prompts tab, regression test, book import
// Classic script: shares globals with the other studio/*.js files; load order is set in index.html.
// ---------- per-chapter shot counts (saved in the book's overrides.json) ----------
let CHS = [];
function autoShots(words) {
  const w = parseInt($("wps").value, 10) || ($("narration").value === "verbatim" ? 25 : 60);
  const lo = Math.max(1, parseInt($("minshots").value, 10) || 1), hi = Math.max(lo, parseInt($("maxshots").value, 10) || 12);
  return Math.max(lo, Math.min(hi, Math.ceil(words / Math.max(w, 1))));
}
function renderChShots() {
  const box = $("chShotsBody");
  if (!CHS.length) { box.textContent = "No chapters yet: read the book first."; return; }
  const t = document.createElement("table"); t.style.width = "100%";
  t.innerHTML = "<thead><tr><th style='text-align:left'>Ch</th><th style='text-align:left'>Title</th><th style='text-align:left'>Words</th><th style='text-align:left'>Auto</th><th style='text-align:left'>Shots</th></tr></thead>";
  const tb = document.createElement("tbody");
  for (const c of CHS) {
    const tr = document.createElement("tr"), td = (txt, left) => { const e = document.createElement("td"); e.textContent = txt; if (left) e.style.textAlign = "left"; tr.appendChild(e); return e; };
    td(c.n, true); td(c.title, true); td(c.words, true); const a = td(autoShots(c.words), true); a.className = "chAuto"; a.dataset.words = c.words;
    const cell = document.createElement("td"), inp = document.createElement("input");
    inp.type = "number"; inp.min = 1; inp.max = 500; inp.style.width = "70px"; inp.autocomplete = "off"; inp.dataset.n = c.n; inp.className = "chShotIn";
    inp.value = c.shots || ""; inp.placeholder = "auto"; cell.appendChild(inp); tr.appendChild(cell); tb.appendChild(tr);
  }
  t.querySelectorAll("th").forEach(h => { h.style.position = "sticky"; h.style.top = "0"; h.style.background = "var(--surface, var(--bg))"; h.style.zIndex = "1"; });   // header stays put while the chapters scroll
  t.appendChild(tb); box.replaceChildren(t);
}
function refreshAutoShots() { document.querySelectorAll("#chShotsBody .chAuto").forEach(e => { e.textContent = autoShots(+e.dataset.words); }); }
async function loadChShots() {
  const p = $("proj").value; $("chShotsMsg").textContent = "";
  if (!p || (cur() && (cur().legacy || !cur().chapters))) { CHS = []; renderChShots(); return; }
  try { CHS = (await api("/api/chapter_shots?project=" + encodeURIComponent(p))).chapters; } catch (e) { CHS = []; $("chShotsMsg").textContent = e.message; }
  renderChShots();
}
async function saveChShots(clear) {
  const shots = {};
  for (const c of CHS) shots[c.n] = "";
  if (!clear) document.querySelectorAll("#chShotsBody .chShotIn").forEach(i => { shots[i.dataset.n] = i.value.trim(); });
  try { CHS = (await api("/api/chapter_shots", { project: $("proj").value, shots })).chapters; renderChShots(); $("chShotsMsg").textContent = clear ? "Cleared; all chapters are automatic." : "Saved."; }
  catch (e) { $("chShotsMsg").textContent = e.message; }
}
$("chShots").addEventListener("toggle", () => { if ($("chShots").open) loadChShots(); });
$("proj").addEventListener("change", () => { if ($("chShots").open) loadChShots(); else $("chShotsBody").textContent = ""; });
for (const id of ["wps", "minshots", "maxshots", "narration"]) $(id).addEventListener("input", refreshAutoShots);
$("bChShotsSave").onclick = () => saveChShots(false);
$("bChShotsClear").onclick = () => saveChShots(true);


// ---------- single prompts (text to video / text to image) ----------
const num = id => $(id).value.trim();
// What a Single Prompts run makes comes from the Models tab: every ticked video model makes videos, every ticked image model makes images.
function promptTargets() {
  const on = n => [...document.querySelectorAll(`input[name=${n}]:checked`)].filter(e => !e.disabled).map(e => e.value);
  return [...on("vmodel").filter(m => !/_i2v$/.test(m)).map(model => ({ kind: "video", model })), ...on("imodel").map(model => ({ kind: "image", model }))];
}
function promptOptions(t = promptTargets()[0] || { kind: "video", model: "" }) {
  return {
    mode: "prompts", set: $("pset").value.trim().toLowerCase(), kind: t.kind, model: t.model, prompts: $("ptext").value,
    opts: { width: num("pw"), height: num("ph"), frames: num("pframes"), steps: num("psteps"), guidance: num("pguid"), seed: num("pseed"),
            variations: num("pvar") || 1, negative: $("pneg").value },
    look: $("pLook").checked ? (radio("look") || "") : "",
    service: radio("svc"), gpu: $("gpu").value, kaggle_user: $("kuser").value, batch: $("batch").value,
    engine: $("engine").value, claude_model: $("cmodel").value, keep_going: false,
  };
}

// ---------- shared job helpers (Characters, Single Prompts and Movies all use these) ----------
const sleepMs = ms => new Promise(resolve => setTimeout(resolve, ms));

// Follow the server's single job log until it stops. log(line) is called for each new non-empty line. Returns every line.
async function followJob(log, intervalMs = 3000) {
  let cursor = 0, errors = 0;
  const all = [];
  for (;;) {
    let j;
    try {
      j = await api(`/api/log?since=${cursor}`);
      errors = 0;
    } catch (e) {
      log(`  ⚠ Could not read the job log: ${e.message}`, true);
      if (++errors >= 20) return all;
      await sleepMs(intervalMs);
      continue;
    }
    j.lines.forEach(l => { all.push(l); if (l.trim()) log(`  ${l}`); });
    cursor = j.next;
    if (!j.running) return all;
    await sleepMs(intervalMs);
  }
}

// owner/slug of every Kaggle notebook the run script pushed ("== kernel pushed: https://www.kaggle.com/code/OWNER/SLUG")
function kaggleRefsFromLines(lines) {
  const refs = [];
  for (const l of lines) {
    const m = l.match(/kernel pushed:\s*https:\/\/www\.kaggle\.com\/code\/([^\s/]+\/[^\s/]+)/);
    if (m && !refs.includes(m[1])) refs.push(m[1]);
  }
  return refs;
}

// Copy a finished notebook's output into projects/<project>/ (the server's fetch job wants the slug WITHOUT the owner).
async function fetchIntoProject(ref, project, log) {
  log(`📥 Copying results of ${ref} into ${projPath(project)}/ ...`);
  try {
    await api("/api/fetch", { slug: ref.split("/").pop(), project, wait: true });
  } catch (e) {
    log(`  ⚠ Fetch failed: ${e.message}`, true);
    return false;
  }
  await followJob(log, 5000);
  return true;
}

// ---------- Movies tab: make the movie from the imported book ----------
function updateMSummary() {
  if (!ST) return;
  const p = cur();
  const steps = ["s_keyframes", "s_video", "s_audio", "s_merge", "s_mix"].filter(id => $(id) && $(id).checked)
    .map(id => { const sp = $(id).closest("label").querySelector("span"); return (sp.firstChild ? sp.firstChild.textContent : sp.textContent).trim().replace(/\s+/g, " "); });   // the label without its <small> help line
  const picked = selectedMovies(p);
  const clips = picked.reduce((a, m) => a + (m.clips || 0), 0), secs = picked.reduce((a, m) => a + (m.est_seconds || 0), 0);
  const planned = p && p.movies ? (p.movies[radio("gran")] || []).length : 0;
  const size = picked.length ? `${picked.length} movie(s), ${clips} clips, about ${(secs / 60).toFixed(1)} min of film`
             : planned ? "no movies picked yet" : "no movies planned yet (build the CSVs first)";
  $("mSummary").textContent = (p ? `Book: ${p.slug} · ${size}` : "No book selected") + " · " + (steps.length ? "steps: " + steps.join(", ") : "no steps ticked (choose them in Video and Audio above)");
}

// The planned movies the Which Movies card points at: the ticked ones, the first N, or all. Movies that do not exist yet are not counted.
function selectedMovies(p) {
  if (!p || !p.movies) return [];
  const list = p.movies[radio("gran")] || [], sel = radio("msel");
  if (sel === "all") return list;
  if (sel === "first") return list.slice(0, Math.max(0, parseInt($("mfirst").value, 10) || 0));
  const ids = new Set(checked("movie"));
  return list.filter(m => ids.has(String(m.id)));
}

// ---------- quality presets: tick the models for a quick test, a standard run or the best this GPU allows ----------
// Each list is tried in order; the first model that is not greyed out (blocked for this service and GPU) is used.
const QUALITY_PRESETS = {
  draft: { label: "Quick test", video: ["ltx_video", "wan"], narration: ["kokoro"], sfx: [], music: ["musicgen"] },
  standard: { label: "Standard", video: ["wan22_ti2v_5b", "wan", "ltx_video"], narration: ["qwen3_tts", "kokoro"], sfx: [], music: ["musicgen"] },
  best: { label: "Best", video: ["wan22_t2v_a14b_lightning", "hunyuan_video_15", "wan22_ti2v_5b", "wan"], narration: ["chatterbox_turbo", "qwen3_tts", "kokoro"], sfx: ["mmaudio"], music: ["musicgen"] },
};
function applyPreset(name) {
  const pr = QUALITY_PRESETS[name]; if (!pr || !ST) return;
  const boxes = sel => [...document.querySelectorAll(sel)];
  const usable = (all, wanted) => wanted.map(v => all.find(b => b.value === v)).find(b => b && !b.disabled);
  const vids = boxes("input[name=vmodel]"), auds = boxes("input[name=audio]");
  const roleOf = k => (ST.audio_models[k] || {}).role;
  const pickV = usable(vids, pr.video);
  const pickA = ["narration", "sfx", "music"].map(r => usable(auds.filter(b => roleOf(b.value) === r), pr[r])).filter(Boolean);
  const want = new Set([pickV, ...pickA].filter(Boolean));
  for (const b of [...vids, ...auds]) {
    const on = want.has(b);
    if (b.checked !== on) { b.checked = on; b.dispatchEvent(new Event("change", { bubbles: true })); }
  }
  document.querySelectorAll(".preset-btn").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.preset === name)));
  const names = [pickV, ...pickA].filter(Boolean).map(b => b.value);
  $("presetNote").textContent = pickV ? `${pr.label}: ${names.join(", ")}. Change any of these on the Models tab.`
                                      : `${pr.label}: no video model in this preset can run on the chosen service and GPU. Pick one on the Models tab.`;
  $("presetNote").className = pickV ? "warn" : "err";
  updateMSummary();
}
document.querySelectorAll(".preset-btn").forEach(b => b.addEventListener("click", () => applyPreset(b.dataset.preset)));
// Ticking a model by hand means no preset is in force any more.
document.addEventListener("change", e => {
  if (e.isTrusted && e.target.matches("input[name=vmodel], input[name=audio]")) document.querySelectorAll(".preset-btn").forEach(b => b.setAttribute("aria-pressed", "false"));
});

// ---------- volume sliders: show the number next to each one ----------
function showSliderValue(r) { const o = $(r.dataset.out); if (o) o.textContent = Number(r.value).toFixed(2); }
document.querySelectorAll("input[type=range][data-out]").forEach(r => { r.addEventListener("input", () => showSliderValue(r)); showSliderValue(r); });

// The summary follows the movie choices too (the movie checkboxes are redrawn, so listen on the panel).
$("panel-movies").addEventListener("change", e => { if (e.target.matches("input[name=movie], input[name=msel], input[name=gran]")) updateMSummary(); });
$("mfirst").addEventListener("input", updateMSummary);

// ---------- Single Prompts tab ----------
function appendLog(box, msg, isErr = false) {
  if (box.dataset.empty !== "0") { box.textContent = ""; box.dataset.empty = "0"; }
  const line = document.createElement("div");
  if (isErr) line.className = "err";
  line.textContent = msg;
  box.appendChild(line);
  box.scrollTop = box.scrollHeight;
}
const pLog = (msg, isErr) => appendLog($("pLog"), msg, isErr);

function pStatus(text, cls = "warn") {
  $("pStatus").textContent = text;
  $("pStatus").className = cls;
}

function updatePRunsOn() {
  const svc = radio("svc") || "kaggle";
  const who = svc === "kaggle" ? ` · ${$("kuser").value.trim() || "(enter your Kaggle username in the Models tab)"}` : "";
  $("pRunsOn").textContent = `Runs on ${svc === "huggingface" ? "Hugging Face" : svc === "computer" ? "this computer" : svc} · ${$("gpu").value || "(pick a GPU)"}${who}. Change this in the Models tab.`;
}

let pStopped = false;
async function pGenerate() {
  const base = promptOptions();
  if (!/^[a-z0-9_]{2,40}$/.test(base.set)) { pStatus("Name the prompt set: 2-40 lowercase letters, digits or underscores.", "err"); $("pset").focus(); return; }
  if (!base.prompts.trim()) { pStatus("Type at least one prompt.", "err"); $("ptext").focus(); return; }
  const targets = promptTargets();
  if (!targets.length) { pStatus("Tick a video or image model on the Models tab first.", "err"); return; }
  $("pGenerate").disabled = true; pStopped = false;
  $("pLog").textContent = ""; $("pLog").dataset.empty = "0";
  updatePRunsOn();
  let downloaded = false;
  for (const [i, t] of targets.entries()) {
    const o = promptOptions(t);
    if (targets.length > 1) pLog(`${i ? "\n" : ""}== ${i + 1}/${targets.length}: ${t.kind} with ${t.model}`);
    pStatus(`Planning ${t.model}...`);
    try {
      const plan = await api("/api/plan", o);        // the server answers 400 with the reason (unknown model, GPU not allowed, no Kaggle user...)
      pLog(`✓ Plan: ${plan.steps.length} step(s)`);
      plan.steps.forEach(s => pLog(`  ${s.label}`));
    } catch (e) {
      pLog(`✗ ${t.model}: ${e.message}`, true); pStatus(e.message, "err"); $("pGenerate").disabled = false; return;
    }
    try {
      await api("/api/run", o);
    } catch (e) {
      pLog(`✗ Could not start ${t.model}: ${e.message}`, true); pStatus(e.message, "err"); $("pGenerate").disabled = false; return;
    }
    $("pStop").disabled = false;
    pStatus(`Running ${t.model}... (a Kaggle run takes minutes; the log below updates as it goes)`);
    const lines = await followJob(pLog);
    $("pStop").disabled = true;
    downloaded = lines.some(l => l.includes("✅") && l.includes("files now in"));
    const refs = o.service === "kaggle" ? kaggleRefsFromLines(lines) : [];
    if (!downloaded && refs.length && !pStopped) {
      // The run script stopped before it fetched results (error, stop, lost connection): ask Kaggle directly.
      pLog("⚠ The run ended before results were downloaded. Checking Kaggle directly...", true);
      for (const ref of refs) {
        if ((await waitForKaggleAndDownload(ref, 90, pLog)) === "COMPLETE") await fetchIntoProject(ref, o.set, pLog);
      }
    }
    if (pStopped) { pLog("Stopped; the remaining models were skipped."); break; }
  }
  pStatus(downloaded ? "Done." : "Finished. See the log above.", downloaded ? "chip done" : "warn");
  $("pGenerate").disabled = false;
  await loadStatus(true);
  loadPGallery();
}

async function pStop() {
  pStopped = true;
  try { await api("/api/stop", {}); pLog("Stop requested..."); } catch (e) { pLog(`✗ ${e.message}`, true); }
}

// ---------- Models tab: regression test (the Single Prompts prompt on every model) ----------
let regStopped = false, regRunning = false;
const REG_STEPS_CAP = 6;                      // same cap as scripts/regress_kaggle.py: sizes stay at the defaults, only the steps are cut
function regLog(text, isErr = false) {
  const el = $("regLog"); el.textContent += text + "\n"; el.scrollTop = el.scrollHeight;
  if (isErr) el.dataset.err = "1";
}
function regSync() {
  $("regStart").disabled = !$("regOn").checked || regRunning;
  $("regStop").disabled = !regRunning || regStopped;
}
async function regStart() {
  if (regRunning || !$("regOn").checked) return;
  const base = promptOptions({ kind: "video", model: "" });
  if (!/^[a-z0-9_]{2,40}$/.test(base.set)) { $("regStatus").textContent = "Name the prompt set on the Single Prompts tab first (2-40 lowercase letters, digits or underscores)."; return; }
  if (!base.prompts.trim()) { $("regStatus").textContent = "Type a prompt on the Single Prompts tab first."; return; }
  const targets = [...(ST.image_models || []).filter(m => !m.startsWith("tpu_")).map(model => ({ kind: "image", model })),
                   ...(ST.video_models || []).filter(m => !m.startsWith("tpu_")).map(model => ({ kind: "video", model }))];
  regRunning = true; regStopped = false; $("regLog").textContent = ""; regSync();
  const results = [];
  for (const [i, t] of targets.entries()) {
    if (regStopped) { regLog("Stopped: no more requests were sent."); break; }
    $("regStatus").textContent = `${i + 1}/${targets.length}: ${t.model}`;
    const o = promptOptions(t);
    const d = ST.model_defaults[t.model] || {};
    if (!o.opts.steps && d.steps && !(d.locked || []).includes("steps")) o.opts.steps = String(Math.min(Number(d.steps), REG_STEPS_CAP));
    regLog(`== ${i + 1}/${targets.length}: ${t.kind} ${t.model}`);
    try { await api("/api/plan", o); } catch (e) { regLog(`  skipped: ${e.message}`); results.push([t.model, "skipped"]); continue; }
    try { await api("/api/run", o); } catch (e) { regLog(`  ✗ could not start: ${e.message}`, true); results.push([t.model, "not started"]); break; }
    const lines = await followJob(l => regLog(l));
    let done = lines.some(l => l.includes("✅") && l.includes("files now in"));
    const refs = o.service === "kaggle" ? kaggleRefsFromLines(lines) : [];
    if (!done && refs.length) {
      for (const ref of refs) {
        if ((await waitForKaggleAndDownload(ref, 90, regLog)) === "COMPLETE") { await fetchIntoProject(ref, o.set, regLog); done = true; }
      }
    }
    results.push([t.model, done ? "files downloaded" : "no files"]);
    regLog(`  ${done ? "✓" : "✗"} ${t.model}: ${done ? "files downloaded" : "no files came back"}`, !done);
  }
  regRunning = false; regSync();
  $("regStatus").textContent = `Finished: ${results.filter(r => r[1] === "files downloaded").length} of ${results.length} models made files.`;
  regLog("\nSummary:\n" + results.map(r => `  ${r[0]}: ${r[1]}`).join("\n"));
  await loadStatus(true);
  loadPGallery();
}
function regStop() {                          // deliberately does NOT call /api/stop: the running model finishes, nothing new is sent
  regStopped = true; regSync();
  $("regStatus").textContent = "Stopping after the model that is running...";
}
$("regOn").addEventListener("change", regSync);
$("regStart").addEventListener("click", regStart);
$("regStop").addEventListener("click", regStop);

// ---------- Import tab: upload (if needed), then read the book ----------
function updTextCount() { const n = $("impText").value.trim().split(/\s+/).filter(Boolean).length; $("impTextCount").textContent = n ? `${n.toLocaleString()} words pasted` : ""; }
$("impText").addEventListener("input", updTextCount);
const impLog = (msg, isErr) => appendLog($("importLog"), msg, isErr);
function impStatus(text, cls = "warn") { $("importStatus").textContent = text; $("importStatus").className = cls; }

// Saves the file chosen or text pasted in Read book to the books folder and makes it the chosen book. {uploaded: name or ""} or {error}.
async function uploadChosenBook(log, status) {
    let f = $("file").files[0];
    const pasted = $("impText").value.trim();
    if (!f && pasted) {                                           // pasted text becomes a small text book
      if (pasted.split(/\s+/).length < 5) return { error: "Paste at least a few words of text." };
      const nm = ($("impTitle").value.trim() || pasted.split(/\s+/).slice(0, 4).join(" ")).replace(/[^A-Za-z0-9._ -]/g, " ").replace(/\s+/g, " ").trim().slice(0, 50) || "pasted text";
      f = new File([pasted], nm + ".txt", { type: "text/plain" });
    } else if (f && pasted) { log("Both a file and pasted text were given; the file is used. Clear it to use the pasted text."); }
    let uploaded = "";
    if (f) {
      status("Uploading...");
      log(`Uploading ${f.name} (${(f.size / 1048576).toFixed(1)} MB) to the books folder...`);
      const r = await fetch(`/api/upload?filename=${encodeURIComponent(f.name)}`, { method: "POST", headers: { ...hdr, "Content-Type": f.type || "application/octet-stream" }, body: f });
      const j = await r.json();
      if (!r.ok) return { error: j.error || "upload failed" };
      log(`✓ Saved books/${j.filename}; the book is called "${j.project}"`);
      uploaded = j.filename;
      $("file").value = ""; if (pasted && f.type === "text/plain") { $("impText").value = ""; $("impTitle").value = ""; updTextCount(); }
      await loadStatus(); $("proj").value = j.project; renderProject(true);
    }
    return { uploaded };
}
