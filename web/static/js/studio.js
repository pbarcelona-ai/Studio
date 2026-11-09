// The server puts the access token into <meta name="studio-token"> of index.html (the JS files themselves are static).
const TOKEN = (document.querySelector('meta[name="studio-token"]') || {}).content || "__TOKEN__";
const $ = id => document.getElementById(id);

// Check if running via file:// protocol (token not replaced by server)
if (TOKEN === "__TOKEN__" && window.location.protocol === "file:") {
  alert("⚠️ You are opening this page directly via file:// protocol.\n\nThis will NOT work correctly because:\n1. The authentication token is not set (it's a placeholder)\n2. API calls to the server will fail\n3. Model selection and job monitoring won't work\n\nPlease access the page through the server URL printed when you start studio.py:\n  http://localhost:8775/?t=YOUR_TOKEN\n\nThe token is stored in .studio_session.json");
}
const hdr = { "X-Studio-Token": TOKEN };
const api = async (path, body) => {
  const r = await fetch(path, { method: body ? "POST" : "GET", headers: { ...hdr, "Content-Type": "application/json" }, body: body ? JSON.stringify(body) : undefined });
  const j = await r.json();
  if (!r.ok) throw new Error(j.error || r.statusText);
  return j;
};

// Delete previous notebooks before generating
async function deleteNotebooks() {
  try {
    // POST (an empty body is enough): the server only defines this route for POST, so a bodyless call became a GET and returned 404
    await api("/api/delete_notebooks", {});
  } catch (e) {
    console.warn("Could not delete notebooks:", e.message);
  }
}
const checked = name => [...document.querySelectorAll(`input[name=${name}]:checked`)].map(e => e.value);
const radio = name => (document.querySelector(`input[name=${name}]:checked`) || {}).value;

// ---------- keep the browsers' own autofill and suggestion lists out of our text boxes ----------
// Chrome ignores autocomplete="off" on boxes it takes for a name/address/login (an unknown value such as "nope" works there); Safari and Firefox
// honour "off" and may treat an unknown value as a hint. So the value depends on the browser.
function autofillValue(ua) { return /Chrome|CriOS|Chromium|Edg\//.test(ua) ? "nope" : "off"; }
document.querySelectorAll("[data-1p-ignore]").forEach(e => { e.setAttribute("autocomplete", autofillValue(navigator.userAgent)); e.setAttribute("autocorrect", "off"); });
// Our own suggestion list (a <datalist> is drawn by the browser, which mixes in its own entries).
function setupSuggest(input, getItems) {
  const box = document.createElement("div");
  box.className = "suggest hidden"; box.setAttribute("role", "listbox");
  input.parentNode.style.position = "relative"; input.parentNode.appendChild(box);
  input.setAttribute("aria-autocomplete", "list");
  let idx = -1;
  const list = () => { const v = input.value.trim().toLowerCase(); return getItems().filter(x => x !== v && x.includes(v)); };
  const paint = () => [...box.children].forEach((c, i) => c.classList.toggle("active", i === idx));
  const render = () => {
    const l = list(); idx = -1;
    box.textContent = "";
    l.forEach(x => { const d = document.createElement("div"); d.className = "suggest__item"; d.setAttribute("role", "option"); d.dataset.v = x; d.textContent = x; box.appendChild(d); });
    box.classList.toggle("hidden", !l.length);
  };
  const pick = v => { input.value = v; box.classList.add("hidden"); input.dispatchEvent(new Event("input", { bubbles: true })); input.dispatchEvent(new Event("change", { bubbles: true })); };
  input.addEventListener("input", render);
  input.addEventListener("focus", render);
  input.addEventListener("blur", () => setTimeout(() => box.classList.add("hidden"), 150));
  box.addEventListener("mousedown", e => { const it = e.target.closest("[data-v]"); if (it) { e.preventDefault(); pick(it.dataset.v); } });
  input.addEventListener("keydown", e => {
    const n = box.children.length;
    if (e.key === "ArrowDown" && n) { e.preventDefault(); box.classList.remove("hidden"); idx = (idx + 1) % n; paint(); }
    else if (e.key === "ArrowUp" && n) { e.preventDefault(); idx = (idx - 1 + n) % n; paint(); }
    else if (e.key === "Enter" && idx >= 0 && !box.classList.contains("hidden")) { e.preventDefault(); pick(box.children[idx].dataset.v); }
    else if (e.key === "Escape") box.classList.add("hidden");
  });
}
let ST = null, since = 0, building = false, loaded = false;
const CHAR_SHEET_VIEWS = ["front view, facing the camera, neutral plain background", "side profile view, neutral plain background", "seen from behind, neutral plain background",
                          "full body, standing, front view, neutral plain background", "extreme close-up portrait, face filling the frame, detailed eyes"];
let charGenReference = {};   // what Generate Character asks the server to start from
const charSlug = name => name.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "").slice(0, 40) || "book";   // as character_tokens.slugify on the server
const FIT_SYNCS = ["stretch", "gentle"];   // sync modes where a shot lasts as long as its narration
const stagesToText = stages => (stages || []).map(s => `${s.label} | ${s.chapters} | ${s.token}`).join("\n");
const textToStages = text => text.split("\n").map(l => l.trim()).filter(Boolean).map(l => {
  const [label = "", chapters = "", ...rest] = l.split("|").map(x => x.trim());
  return { label, chapters, token: rest.join(" | ") };
});
const cur = () => ST ? ST.projects.find(p => p.slug === $("proj").value) : undefined;   // ST is null until the first /api/status answer

function options() {
  if (radio("mode") === "prompts") return promptOptions();
  const p = cur(), sel = radio("msel");
  return {
    project: $("proj").value, pdf: $("pdf").value, granularity: radio("gran"),
    video_models: checked("vmodel"), audio: checked("audio"), service: radio("svc"), gpu: $("gpu").value,
    kaggle_user: $("kuser").value, batch: $("batch").value, range_start: $("rs").value, range_end: $("re").value,
    sync: $("sync").value, aspect: $("aspect").value, chain: $("chain").checked, music_bed: $("musicBed").checked, duck: $("duck").checked, loudnorm: $("loudnorm").checked, clip_seconds: $("clipsecs").value, scenes: $("b_scenes").checked,
    keep_going: $("keep").checked, vol: { narration: $("vn").value, sfx: $("vs").value, music: $("vm").value },
    narration: $("narration").value, engine: $("engine").value, force_write: $("b_force").checked, claude_model: $("cmodel").value, chapters: $("chs").value, words_per_shot: $("wps").value,
    min_shots: $("minshots").value, max_shots: $("maxshots").value, movie_minutes: $("mmin").value, workers: $("workers").value,
    enoch_chars: $("echars").value, look: radio("look") || "", keyframe_model: $("kfmodel").value, keyframe_refs: $("kfrefs").checked && !$("kfrefs").disabled, keyframe_series: $("kfseries").value,
    movies: sel === "ids" ? { mode: "ids", ids: checked("movie") } : sel === "first" ? { mode: "first", n: $("mfirst").value } : { mode: "all" },
    steps: { ingest: $("b_ingest").checked, continuity: $("b_continuity").checked, write: $("b_write").checked, build: $("b_build").checked,
             extract: $("s_extract").checked, keyframes: $("s_keyframes").checked, video: $("s_video").checked, audio: $("s_audio").checked, merge: $("s_merge").checked, mix: $("s_mix").checked },
  };
}

function fillGpus() {
  const svc = radio("svc");
  const gb = (ST.gpu_blockers || {})[svc] || {};
  $("gpu").innerHTML = ST.gpus[svc].map(([v, t]) => `<option value="${v}" ${gb[v] ? "disabled" : ""} title="${(gb[v] || "").replace(/"/g, "&quot;")}">${t}${gb[v] ? " - unavailable" : ""}</option>`).join("");
  const firstOk = [...$("gpu").options].find(o => !o.disabled); if (firstOk) $("gpu").value = firstOk.value;
  $("userbox").style.display = svc === "kaggle" ? "" : "none";
  $("gpuhint").textContent = svc === "kaggle" ? "Only the T4 is free for everyone; the others may be refused." : svc === "huggingface" ? "Hugging Face picks the GPU (ZeroGPU). Set HF_TOKEN in the environment to use your own account's daily quota."
    : svc === "computer" ? (ST.computer_why ? "Unavailable here: " + ST.computer_why : "Runs on the GPU listed above with scripts/run_local_model.py. The first run of each kind of model sets up its Python environment (a few GB, a few minutes).") : "Anything above T4 needs a paid Colab plan.";
  $("batchhint").textContent = svc === "kaggle" ? "Kaggle: 0-60 works; each run waits in Kaggle's queue." : svc === "huggingface" ? "Hugging Face: keep it small (3-5); the free daily GPU quota is a few minutes."
    : svc === "computer" ? "This computer: any size; a smaller batch just means the model loads more often." : "Colab: keep it small (5-10); the VM can vanish mid-run.";
  $("batch").value = svc === "kaggle" ? 40 : svc === "huggingface" ? 3 : svc === "computer" ? 20 : 5;
  if (typeof updatePRunsOn === "function") updatePRunsOn();
  if (typeof fillUpscalers === "function") fillUpscalers();
  if (typeof refreshSuggestions === "function" && ST.looks) refreshSuggestions();
  $("autoClean").checked = ST.auto_cleanup !== false;
}

// Models, grouped by family: [[title, [model, ...]], ...]. Models the server did not group go into "Other".
function groupModels(groups, all) {
  const placed = new Set(), out = [];
  for (const [title, ms] of groups || []) {
    const here = ms.filter(m => all.includes(m));
    here.forEach(m => placed.add(m));
    if (here.length) out.push([title, here]);
  }
  const rest = all.filter(m => !placed.has(m));
  if (rest.length) out.push(["Other", rest]);
  return out;
}
// The line under a model on the Models tab: its note without the leading "Experimental" (shown as a tag instead), cut at the end of the first
// real sentence. A short opener such as "Adult content." keeps the sentence after it.
function blurb(note) {
  if (!note) return "";
  const exp = /^Experimental/.test(note);
  let t = note.replace(/^Experimental\.\s*/, "").replace(/^Experimental, adult content, no filter\.\s*/, "Adult content. ").replace(/^Experimental, adult content possible\.\s*/, "Adult content possible. ");
  const sent = t.split(/(?<=\.)\s/);
  t = sent[0].length < 24 && sent[1] ? sent[0] + " " + sent[1] : sent[0];
  return (exp ? "experimental · " : "") + t;
}
const ADVANCED_NOTE = /experimental|not run on a gpu|adult|uncensored|nsfw/i;   // hidden from the model lists until asked for; a ticked one always shows
function modelGroupsHtml(name, groups, all) {
  return groupModels(groups, all).map(([title, ms]) => `<div class="model-group"><h3 class="model-group__title">${title}</h3><div class="model-list">` +
    ms.map(m => `<label class="opt"${ADVANCED_NOTE.test(MODEL_NOTES[m] || "") || /_lora$|_uc$|nsfw/.test(m) ? " data-advanced" : ""}><input type="checkbox" name="${name}" value="${m}" ${m === all[0] ? "checked" : ""}><span>${m}${MODEL_NOTES[m] ? `<small>${blurb(MODEL_NOTES[m])}</small>` : ""}</span></label>`).join("") +
    `</div></div>`).join("");
}

// Keyframe image models: every image model, newest proven ones first (FLUX.2 klein passed the Kaggle T4 regression in 6 minutes).
const KEYFRAME_FIRST = ["flux2_klein_4b", "flux1_schnell", "z_image_turbo", "sdxl"];
function fillKeyframeModels() {
  const all = ST.image_models || [], first = KEYFRAME_FIRST.filter(m => all.includes(m));
  const order = [...first, ...all.filter(m => !first.includes(m) && !/^tpu_/.test(m))];     // TPU image models cannot share a run with a GPU video model
  $("kfmodel").innerHTML = order.map(m => `<option value="${m}">${m}</option>`).join("");
  syncKeyframeRefs();
  if (typeof markSuggested === "function" && SUGG) markSuggested();
}
// Only some image models take reference pictures; for the others the option is greyed out and not sent.
const REF_IMAGE_MODELS = ["flux2_klein_4b"];
function syncKeyframeRefs() {
  const ok = REF_IMAGE_MODELS.includes($("kfmodel").value);
  $("kfrefs").disabled = !ok;
  $("kfseries").disabled = !ok || !$("kfrefs").checked;
  $("kfrefsNote").textContent = ok ? "Each character's reference picture (Characters tab) keeps their face and costume the same in every still."
                                   : `${$("kfmodel").value} cannot take reference pictures; choose ${REF_IMAGE_MODELS.join(" or ")} to use them.`;
}
$("kfmodel").addEventListener("change", syncKeyframeRefs);
$("kfrefs").addEventListener("change", () => { $("kfseries").disabled = !$("kfrefs").checked || $("kfrefs").disabled; });
// The series list, with the chosen book's own series picked when it has one (a new book gets a series named after it).
async function fillKeyframeSeries() {
  const p = cur(), sel = $("kfseries"), keep = sel.value;
  try {
    const { series } = await api("/api/characters?action=list_series");
    sel.innerHTML = series.map(s => `<option value="${escapeHtml(s)}">${escapeHtml(s)}</option>`).join("") || '<option value="">(no character series yet)</option>';
    const own = p && p.character_series;
    sel.value = series.includes(keep) ? keep : series.includes(own) ? own : (series[0] || "");
  } catch (e) { /* the option still works with the book's own series */ }
}

// Tick what the selected book needs next. Runs when you pick a book, after an upload and when a job ends.
function applyDefaults(p) {
  if (building || !p) return;
  const set = (id, v) => { $(id).checked = v; };
  document.querySelector('input[name=msel][value=first]').checked = true;      // a first run makes just movie 1
  $("mfirst").value = 1;
  set("b_force", false);
  if (p.legacy) {
    document.querySelector('input[name=gran][value=chapters]').checked = true;  // imported books: the cheap one-clip-per-chapter mode
    set("s_video", true); set("s_audio", true);
  } else {
    document.querySelector('input[name=gran][value=shots]').checked = true;     // new books: shots are allotted by chapter length
    const needIngest = p.not_started || !p.chapters;
    const needContinuity = needIngest || !p.continuity;
    const needWrite = needContinuity || p.scripts < p.chapters;
    const needBuild = needWrite || !p.built;
    set("b_ingest", needIngest); set("b_continuity", needContinuity); set("b_write", needWrite); set("b_build", needBuild);
    set("s_video", !needBuild); set("s_audio", !needBuild);                      // generate only once the prompts exist
  }
  renderMovies();
}

function showBookFile() {
  const e = $("bookFile"); if (!e) return;
  const slug = $("proj").value;
  e.textContent = slug ? `projects/books/${slug}/${slug}.json` : "the book's own .json file";
}
function renderProject(applyDef) {
  showBookFile();
  const p = cur();
  document.querySelectorAll(".bookstep").forEach(e => e.classList.toggle("hidden", !!(p && p.legacy)));
  $("legacypanel").classList.toggle("hidden", !(p && p.legacy));
  $("enochbox").classList.toggle("hidden", !(p && p.slug === "enoch"));
  updateEmptyStates();
  if (typeof updateMSummary === "function") updateMSummary();
  if (!p) { $("chips").innerHTML = ""; $("movies").innerHTML = ""; $("have").innerHTML = ""; return; }
  const chip = (t, d) => `<span class="chip ${d ? "done" : ""}">${d ? "✓ " : ""}${t}</span>`;
  $("chips").innerHTML = p.legacy ? chip("imported book", true) + chip(`${p.movies.shots.length} movies planned`, p.movies.shots.length) :
    (p.not_started ? chip("not started: tick 'Read the PDF' below and run it", false) : chip("PDF read", p.pdfs.length)) + chip(p.chapters ? `${p.chapters} chapters (split by ${p.split_method})` : "not split", p.chapters) +
    chip("continuity book", p.continuity) + chip(`${p.scripts} chapters scripted`, p.scripts) + chip("CSVs built", p.built);
  $("pdf").innerHTML = p.pdf_choices.map(c => `<option value="${c.value}">${c.label}</option>`).join("") || "<option value=''>(put a PDF in the books folder)</option>";
  if (applyDef) applyDefaults(p);
  renderMovies();
  const rows = Object.entries(p.have).filter(([, n]) => n);
  $("have").innerHTML = "<tr><th>folder</th><th>files</th></tr>" + (rows.map(([k, n]) => `<tr><td>${k}</td><td>${n}</td></tr>`).join("") || "<tr><td>nothing yet</td><td></td></tr>");
}

function renderMovies() {
  const p = cur(); if (!p) return;
  const list = p.movies[radio("gran")] || [];
  const kept = new Set(checked("movie"));
  $("movies").innerHTML = list.length ? list.map(m => `<label class="opt"><input type="checkbox" name="movie" value="${m.id}" ${kept.has(String(m.id)) ? "checked" : ""}><span>Movie ${m.id}: ${m.first_chapter} to ${m.last_chapter}<small>rows ${m.rows[0]}-${m.rows[1]} · ${m.clips} clips · about ${(m.est_seconds / 60).toFixed(1)} min</small></span></label>`).join("") :
    `<span class="warn">No movies planned yet for this mode. Run "Build the CSV files and plan the movies", with "the first N" selected above.</span>`;
  if (window.sbFillMovies) window.sbFillMovies();
}

async function loadStatus(applyDef) {
  const prev = $("proj").value;
  ST = await api("/api/status");
  $("tools").innerHTML = Object.entries(ST.tools).map(([t, ok]) => `<span class="${ok ? "ok" : "bad"}">${ok ? "✓" : "✗"} ${t}</span>`).join("") +
    `<span class="warn">${ST.tools.claude ? "" : "Claude Code missing (the default prompt writer). "}${ST.tools.colab ? "" : "Colab CLI missing. "}${ST.tools.kaggle ? "" : "Kaggle CLI missing. "}${ST.tools.uv ? "" : "uv missing (needed to read PDFs and merge)."}</span>`;
  $("proj").innerHTML = ST.projects.map(p => `<option value="${p.slug}">${p.slug}${p.legacy ? " (imported)" : p.not_started ? " (new, from books/)" : ""}</option>`).join("");
  $("libcount").textContent = `· ${ST.library.length} PDF(s) in books/`;
  if (prev && [...$("proj").options].some(o => o.value === prev)) $("proj").value = prev;
  if (!$("models").children.length) {
    fillModels();
    initLocalLlm(); engineNote();
    $("vmodels").innerHTML = modelGroupsHtml("vmodel", ST.video_groups, ST.video_models);
    $("imodels").innerHTML = modelGroupsHtml("imodel", ST.image_groups, ST.image_models || []);
    renderAudioModels();
    fillKeyframeModels();
    fillKeyframeSeries();
    updatePromptModels();
    fillGpus();
    initLooks();
  }
  renderProject(applyDef || !loaded);
  loaded = true;
  setMode();
  applyConstraints();

  // Load global parameters for the current project
  const proj = $("proj").value;
  if (proj) {
    await loadGlobalParams(proj);
  }
}

async function preview() {
  $("msg").textContent = ""; $("msg").className = "warn";
  try {
    const { steps } = await api("/api/plan", options());
    $("plan").innerHTML = `<p class="warn">${steps.length} step(s), run in this order:</p>` + steps.map(s => `<div class="step"><b>${s.label}</b><code>${s.cmd.replace(/</g, "&lt;")}</code></div>`).join("");
    return true;
  } catch (e) { $("plan").innerHTML = ""; $("msg").textContent = e.message; $("msg").className = "err"; return false; }
}

async function run() {
  if (!(await preview())) return;
  await deleteNotebooks();
  building = true;
  try { await api("/api/run", options()); since = 0; $("log").textContent = ""; poll(); } catch (e) { $("msg").textContent = e.message; $("msg").className = "err"; }
}

async function poll() {
  try {
    const j = await api(`/api/log?since=${since}`);
    if (j.lines.length) { const l = $("log"); const stick = l.scrollTop + l.clientHeight >= l.scrollHeight - 20; l.textContent += (l.textContent ? "\n" : "") + j.lines.join("\n"); if (stick) l.scrollTop = l.scrollHeight; }
    since = j.next; $("cur").textContent = j.running ? "· " + j.current : "";
    { const ml = $("mLog"); if (ml) { ml.textContent = $("log").textContent; ml.scrollTop = ml.scrollHeight; } }   // same log, shown in the Make the Movie card
    $("bRun").disabled = j.running; $("bStop").disabled = !j.running;
    document.querySelectorAll(".fetchbtn").forEach(b => { b.disabled = j.running; });
    jobRunning = j.running; updateFilmSummary();
    if (j.running) setTimeout(poll, 1500); else { building = false; loadStatus(true); loadGallery(); if (runsLoaded) loadRuns(false); }
  } catch (e) { $("msg").textContent = "lost connection to studio.py"; $("msg").className = "err"; }
}

async function estimate() {
  const pre = $("estimate"); pre.classList.remove("hidden"); pre.textContent = "working…";
  try { pre.textContent = (await api("/api/estimate", options())).text; } catch (e) { pre.textContent = e.message; }
}

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

// ---------- Make my film: the whole road from the book, and how far it has come ----------
const FILM_STAGES = [["chapters", "Read the book", s => s.chapters], ["continuity", "Continuity book", s => s.continuity ? "done" : 0], ["scripts", "Write shots", s => s.scripts && `${s.scripts} chapter(s), ${s.shots} shots`],
                     ["keyframes", "Keyframes", s => s.shots && s.keyframes && `${s.keyframes} of ${s.shots}`], ["clips", "Video clips", s => s.shots && s.clips && `${s.clips} of ${s.shots}`],
                     ["narration", "Narration", s => s.shots && s.narration && `${s.narration} of ${s.shots}`], ["cues", "Music", s => s.cues_wanted && s.cues && `${s.cues} of ${s.cues_wanted} cue(s)`],
                     ["films", "Finished film", s => (s.films || []).length]];
async function showFilmStatus(slug) {
  if (!slug) return;
  const s = await api(`/api/film_status?project=${encodeURIComponent(slug)}`);
  $("filmStages").innerHTML = FILM_STAGES.map(([, title, f]) => { const v = s.exists ? f(s) : 0; return `<li>${v ? "✓" : "○"} ${escapeHtml(title)}${v && v !== true ? ` <small>(${escapeHtml(String(v))})</small>` : ""}</li>`; }).join("");
  const film = (s.films || [])[0];
  $("filmDone").innerHTML = film ? `<p class="f" style="margin:0 0 4px">Newest film: ${escapeHtml(film.split("/").pop())}</p><video controls preload="metadata" style="width:100%;max-width:720px" src="/file/${film.split("/").map(encodeURIComponent).join("/")}?t=${TOKEN}"></video>` : "";
}
async function runFilm() {
  const btn = $("bFilm"), log = (m, bad) => appendLog($("filmLog"), m, bad), status = (t, cls = "warn") => { $("filmNow").textContent = t; $("filmNow").className = cls; };
  btn.disabled = true; $("filmLog").textContent = ""; $("filmLog").dataset.empty = "0";
  let timer = null;
  try {
    const up = await uploadChosenBook(log, status);
    if (up.error) throw new Error(up.error);
    if (!cur()) throw new Error("Choose a book in Read book below, or paste some text.");
    const o = options();
    o.film = true; o.film_space = $("filmSpace").checked; o.local_audio = $("filmLocalAudio").checked;
    if (up.uploaded) { const opt = [...$("pdf").options].find(x => x.value.endsWith("/" + up.uploaded)); if (opt) $("pdf").value = opt.value; }
    o.pdf = $("pdf").value;
    await api("/api/run", o);
    $("bFilmStop").disabled = false; status("Making your film. You can leave this page open.");
    const slug = o.project;
    timer = setInterval(() => { showFilmStatus(slug).catch(() => {}); api("/api/log?since=999999999").then(j => { if (j.current) status(`Step ${j.current}`); }).catch(() => {}); }, 5000);
    const lines = await followJob(log, 2000);
    await showFilmStatus(slug);
    const failed = lines.some(l => /^!! /.test(l)), done = lines.some(l => /^mixed \d+ clips/.test(l));
    if (done && !failed) status("Your film is ready.", "chip done");
    else if (done) status("A film was made, with some shots still missing or remade with the other model. See the log.", "warn");
    else status("It stopped before the end. What finished is kept: press Make my film again once the limit has passed.", "err");
  } catch (e) { log(`✗ ${e.message}`, true); status(e.message, "err"); }
  finally { if (timer) clearInterval(timer); $("bFilmStop").disabled = true; btn.disabled = false; await loadStatus(true).catch(() => {}); }
}

async function runImport() {
  const btn = $("bImport");
  btn.disabled = true;
  $("importLog").textContent = ""; $("importLog").dataset.empty = "0";
  const fail = msg => { impLog(`✗ ${msg}`, true); impStatus(msg, "err"); btn.disabled = false; };
  try {
    // 1. upload the PDF chosen above, if there is one
    const up = await uploadChosenBook(impLog, impStatus);
    if (up.error) return fail(up.error);
    const uploaded = up.uploaded;
    // 2. what to do with the chosen book
    const p = cur();
    if (!p) return fail("Pick a book above, choose a file to upload, or paste some text.");
    const o = options();
    // The steps ticked in the Read book, Continuity book, Write shots and Build CSVs cards; never video or audio, so nothing goes to Kaggle or Colab
    const tick = id => $(id).checked && !$(id).disabled;
    o.steps = p.legacy ? { extract: true, video: false, audio: false, merge: false, mix: false }
      : { ingest: tick("b_ingest") || !!uploaded, continuity: tick("b_continuity"), write: tick("b_write"), build: tick("b_build"), video: false, audio: false, merge: false, mix: false };
    if (uploaded && !tick("b_ingest")) impLog("A new book was uploaded, so Read book runs too (its chapters are needed by every later step).");
    if (!p.legacy && !["ingest", "continuity", "write", "build"].some(k => o.steps[k]))
      return fail("Tick at least one step: Read book, Continuity book, Write shots or Build CSVs.");
    if (!p.legacy) {
      if (uploaded) { const opt = [...$("pdf").options].find(x => x.value.endsWith("/" + uploaded)); if (opt) $("pdf").value = opt.value; }
      o.pdf = $("pdf").value;
      if (!o.pdf && o.steps.ingest) return fail("No book file found for this book. Choose one in Read book and press Import again.");
      if (p.chapters && !uploaded && (o.steps.ingest || o.steps.continuity) && !confirm(`${p.slug} is already imported (${p.chapters} chapters). This will ${[o.steps.ingest ? "split the book into chapters again (hand edits to chapters.json are lost)" : "", o.steps.continuity ? "write the continuity book again (the AI is called)" : ""].filter(Boolean).join(" and ")}. Continue?`)) {
        impLog("Cancelled: nothing was changed."); impStatus("Cancelled."); btn.disabled = false; return;
      }
    }
    impStatus("Planning...");
    const plan = await api("/api/plan", o);
    impLog(`✓ Plan: ${plan.steps.length} step(s)`);
    plan.steps.forEach(s => { impLog(`  ${s.label}`); impLog(`    $ ${s.cmd}`); });
    await api("/api/run", o);
    $("bImportStop").disabled = false;
    impStatus("Importing... (the AI is working; the log below updates as it goes)");
    const lines = await followJob(impLog, 1500);
    $("bImportStop").disabled = true;
    await loadStatus(true);
    const q = cur();
    const bad = lines.some(l => /Traceback|Error:|PDF not found/.test(l));
    if (bad) impLog("✗ A step failed. The work that finished is kept; fix the problem shown above and press Import again.", true);
    else if (q && !q.legacy && q.chapters) impLog(`✓ ${q.slug}: ${q.chapters} chapters (split by ${q.split_method}), continuity book ${q.continuity ? "written" : "missing"}, ${q.scripts} chapters scripted, CSVs ${q.built ? "built" : "not built"}.`);
    else if (q && q.legacy) impLog(`✓ ${q.slug}: prompt CSVs rebuilt, ${q.movies.shots.length} movies planned.`);
    impStatus(bad ? "Finished with errors. See the log." : "Done.", bad ? "err" : "chip done");
  } catch (e) {
    impLog(`✗ ${e.message}`, true); impStatus(e.message, "err");
    $("bImportStop").disabled = true;
  }
  btn.disabled = false;
}

async function importStop() {
  try { await api("/api/stop", {}); impLog("Stop requested..."); } catch (e) { impLog(`✗ ${e.message}`, true); }
}

// A warning pop-up with Continue and Cancel. Resolves true only for Continue; Cancel, Esc and a click outside all mean no.
// Focus starts on Cancel so a stray Enter never confirms a deletion.
function askContinue({ title, intro, items = [], note = "", danger = false }) {
  return new Promise(resolve => {
    const ov = $("warnModal"), cont = $("warnContinue"), canc = $("warnCancel"), before = document.activeElement;
    $("warnTitle").textContent = title;
    const body = $("warnBody"); body.textContent = "";
    const intro_ = document.createElement("p"); intro_.textContent = intro; body.appendChild(intro_);
    if (items.length) {
      const ul = document.createElement("ul"); ul.style.cssText = "max-height:220px;overflow:auto;margin:8px 0;padding-left:20px";
      items.forEach(t => { const li = document.createElement("li"); li.textContent = t; ul.appendChild(li); });
      body.appendChild(ul);
    }
    if (note) { const n = document.createElement("p"); n.className = danger ? "err" : "warn"; n.textContent = note; body.appendChild(n); }
    cont.style.background = danger ? "var(--danger)" : ""; cont.style.borderColor = danger ? "var(--danger)" : "";
    const done = ok => { ov.classList.remove("open"); cont.onclick = canc.onclick = ov.onclick = null; document.removeEventListener("keydown", onKey, true); if (before && before.focus) before.focus(); resolve(ok); };
    const onKey = e => {
      if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); done(false); }
      else if (e.key === "Tab") { e.preventDefault(); (document.activeElement === canc ? cont : canc).focus(); }       // keep focus inside the dialog
    };
    cont.onclick = () => done(true); canc.onclick = () => done(false);
    ov.onclick = e => { if (e.target === ov) done(false); };
    document.addEventListener("keydown", onKey, true);
    ov.classList.add("open"); canc.focus();
  });
}

// ---------- Import tab: clean up the Kaggle notebooks this tool pushed ----------
async function runKaggleCleanup() {
  const btns = [$("bCleanup"), $("bKaggleCleanup")];
  btns.forEach(b => b.disabled = true);
  $("cleanupLog").textContent = ""; $("cleanupLog").dataset.empty = "0";
  clnStatus("Asking Kaggle for your notebooks (this can take a few seconds)...");
  try {
    const r = await api("/api/kaggle_cleanup_scan");
    const line = n => `${n.slug}   (${n.status.toLowerCase()}, last run ${n.last_run || "?"} UTC)`;
    clnLog(`Kaggle notebooks made by this tool: ${r.keep.length + r.remove.length + r.busy.length}`);
    r.keep.forEach(n => clnLog(`  keep    ${line(n)}`));
    r.busy.forEach(n => clnLog(`  keep    ${line(n)}   (not finished: never deleted)`));
    r.remove.forEach(n => clnLog(`  delete  ${line(n)}`));
    if (!r.remove.length) { clnLog(`✓ Nothing to delete: only the newest ${r.keep_count} are kept and there are no older finished ones.`); clnStatus("Nothing to delete on Kaggle.", "chip done"); return; }
    clnStatus("Waiting for your answer...");
    const ok = await askContinue({
      title: `Delete ${r.remove.length} Kaggle notebook${r.remove.length === 1 ? "" : "s"}?`,
      intro: `These notebooks will be deleted from your Kaggle account. The ${r.keep_count} most recently run are kept.`,
      items: r.remove.map(line),
      note: "This cannot be undone. Images and videos you already downloaded stay in your project folders.",
      danger: true,
    });
    if (!ok) { clnLog("Cancelled: nothing was deleted from Kaggle."); clnStatus("Cancelled.", "warn"); return; }
    clnStatus("Deleting on Kaggle...");
    clnLog(`Deleting ${r.remove.length} notebook(s)...`);
    const d = await api("/api/kaggle_cleanup_delete", {});
    d.deleted.forEach(ref => clnLog(`  ✓ deleted ${ref}`));
    d.failed.forEach(f => clnLog(`  ✗ could not delete ${f.ref}: ${f.error}`, true));
    clnLog(d.failed.length ? `Finished: ${d.deleted.length} deleted, ${d.failed.length} failed.` : `✓ Deleted ${d.deleted.length} notebook(s) from Kaggle.`, !!d.failed.length);
    clnStatus(d.failed.length ? "Finished with errors. See the log." : "Done.", d.failed.length ? "err" : "chip done");
    if (typeof runsLoaded !== "undefined" && runsLoaded) loadRuns(false);
  } catch (e) {
    clnLog(`✗ ${e.message}`, true); clnStatus(e.message, "err");
  } finally {
    btns.forEach(b => b.disabled = false);
  }
}

// ---------- Import tab: Cleanup (scan, show the list, confirm, move to the Trash) ----------
const clnLog = (msg, isErr) => appendLog($("cleanupLog"), msg, isErr);
function clnStatus(text, cls = "warn") { $("cleanupStatus").textContent = text; $("cleanupStatus").className = cls; }
const fmtBytes = n => n >= 1048576 ? (n / 1048576).toFixed(1) + " MB" : n >= 1024 ? Math.round(n / 1024) + " KB" : n + " B";

async function runCleanup() {
  const btn = $("bCleanup");
  btn.disabled = true;
  $("cleanupLog").textContent = ""; $("cleanupLog").dataset.empty = "0";
  clnStatus("Looking for old files...");
  try {
    const { categories } = await api("/api/cleanup_scan");
    const picked = categories.filter(c => c.default && c.items.length);
    if (!picked.length) { clnLog("✓ Nothing to clean up."); clnStatus("Nothing to clean up.", "chip done"); return; }
    let count = 0, bytes = 0;
    picked.forEach(c => {
      clnLog(`${c.title}: ${c.items.length} item(s), ${fmtBytes(c.bytes)}`);
      c.items.slice(0, 40).forEach(i => clnLog(`    ${i.path}`));
      if (c.items.length > 40) clnLog(`    ... and ${c.items.length - 40} more`);
      count += c.items.length; bytes += c.bytes;
    });
    if (!confirm(`Move ${count} item(s) (${fmtBytes(bytes)}) to the Trash? You can put them back from the Trash.`)) {
      clnLog("Cancelled: nothing was moved."); clnStatus("Cancelled."); return;
    }
    clnStatus("Moving to the Trash...");
    const r = await api("/api/cleanup_delete", { categories: picked.map(c => c.id) });
    clnLog(r.moved ? `✓ Moved ${r.moved} item(s) (${fmtBytes(r.bytes)}) to the Trash: ${r.trash}` : "Nothing was moved (the files were already gone).");
    clnStatus(r.moved ? "Done." : "Nothing moved.", "chip done");
    loadStatus(true);
  } catch (e) {
    clnLog(`✗ ${e.message}`, true); clnStatus(e.message, "err");
  } finally {
    btn.disabled = false;
  }
}

function loadPGallery() {
  const proj = $("pset").value.trim().toLowerCase();
  $("pgalsrc").textContent = proj ? `· ${projPath(proj)}/` : "";
  return renderGallery($("pGallery"), proj, "Name a prompt set above to see its results.");
}

let promptTpuMode = false;
const onTpu = () => $("gpu").value.startsWith("Tpu");
// One line per model, shown under the model list on the Single Prompts tab and (first sentence) on the Models tab.
const MODEL_NOTES = {
  pika_h3_flex_i2v: "Runs on its public Hugging Face Space, within the free daily quota: 5 s clips at 832x480 from your keyframes. Choose Hugging Face under Where to run after making the keyframes on Kaggle.",
  cogvideox: "Size and length are fixed by the model (720x480, 6 s, choppy 8 fps).",
                  qwen_image_21_uc: "Experimental, adult content, no filter. Base Qwen-Image-2.1 plus the abenzerps uncensored LoRA (the quantized GGUF files in that repo are ComfyUI-only and not used). Clearly adult, fictional subjects only. Kaggle recommended.",
                  moss_image_sft_lora: "Experimental, adult content, no filter. MOSS-Image-SFT plus the axiomofmind NSFW LoRA (scale 0.8, 30 steps). Trigger moss_xvstyle is added for you. Clearly adult, fictional subjects only. 25 GB: Kaggle only, realistically.",
                  qwen_image_21: "Experimental. Qwen-Image-2.1 (7B, Qwen Research License): strong text and portraits; 40 steps, no negative prompt. Kaggle recommended.",
                  sd35_medium: "Experimental and gated: needs a Hugging Face token.", sdxl_turbo: "Fastest. Good for trying ideas.",
                  moss_image_sft: "Experimental. 25 GB model, 50 steps: slow on a T4 and tight on RAM (Kaggle only, realistically).", moss_image_base: "Experimental. The base model; moss_image_sft is the everyday one.",
                  ltx_video: "Fastest video model.", wan: "Better motion, slower. On a T4 keep it small (512x288, 33 frames): bigger sizes run out of memory.",
                  tpu_wan: "EXPERIMENT: Wan 14B video on Kaggle TPU v5e-8. Untested; same size and length for every row.",
                  tpu_mage_flow: "TEXT TO IMAGE ONLY. Mage-Flow-Turbo on the TPU: 4 images per prompt (the first is the main one). Width picks 512, 768 or 1024 (square). Untested.",
                  tpu_flux_jax: "TEXT TO IMAGE ONLY. FLUX.1-dev on the TPU via the diffuse library. Experimental and untested; may run out of memory.",
                  wan22_ti2v_5b: "Experimental. Wan 2.2 5B (Apache-2.0): better than Wan 2.1, 24 fps, default 704x384 (sizes in multiples of 32). Slow on a T4.",
                  wan22_t2v_a14b: "Experimental. Wan 2.2 14B as two 3-bit GGUF files: the best Wan quality, but it needs most of Kaggle's RAM (use the 5B if it runs out).",
                  wan22_t2v_a14b_lora: "Experimental, adult content, no filter. Wan 2.2 14B plus an adult LoRA pair (JERRYNPC). Clearly adult, fictional subjects only. Same RAM needs as the 14B.",
                  hunyuan_video: "Experimental. HunyuanVideo 13B as a 4-bit GGUF: realistic motion, 33 frames at 15 fps (480x272 on a T4), no negative prompt. Kaggle only (large text encoder).",
                  hunyuan_video_lora: "Experimental, adult content, no filter. HunyuanVideo plus the BigStationW adult LoRA; the trigger word nsfwsks is added for you. Clearly adult, fictional subjects only.",
                  cogvideox_5b: "Experimental. CogVideoX 5B: more detail than the 2B, fixed 720x480, 6 s, choppy 8 fps. Slow on a T4.",
                  flux1_schnell: "Experimental. FLUX.1-schnell from a public copy plus a 4-bit GGUF (no login needed). 4 steps, no negative prompt.",
                  flux1_dev: "Experimental. FLUX.1-dev from a public copy plus a 4-bit GGUF (no login needed; non-commercial licence). 28 steps, no negative prompt.",
                  sd35_large: "Experimental. Stable Diffusion 3.5 Large from a public copy plus a 4-bit GGUF (no login needed). 28 steps.",
                  sd35_large_turbo: "Experimental. Stable Diffusion 3.5 Large Turbo from a public copy plus a 4-bit GGUF (no login needed). 4 steps.",
                  flux2_klein_4b: "Experimental. FLUX.2 klein 4B (Apache-2.0): small and fast, 4 steps, no negative prompt.",
                  chroma1_hd: "Experimental, adult content, no filter. Chroma1-HD (Apache-2.0, 8.9B) as a 4-bit GGUF, 40 steps, slow on a T4. Clearly adult, fictional subjects only.",
                  qwen_image_21_lora: "Experimental, adult content, no filter. Qwen-Image-2.1 plus the f23gg adult LoRA. Clearly adult, fictional subjects only.",
                  noobai_xl: "Experimental, adult content, no filter. NoobAI-XL 1.1 (SDXL anime, trained on Danbooru and e621): tag prompts work best, add 'nsfw'. Runs on a free T4.",
                  realvisxl_v5: "Experimental, adult content possible. RealVisXL V5.0: photorealistic SDXL; normal sentences work. Runs on a free T4.",
                  illustrious_xl: "Experimental, adult content possible. Illustrious-XL 1.0 (SDXL anime): tag prompts work best. Runs on a free T4.",
};

function updatePromptModels() {
  const ts = promptTargets();
  promptTpuMode = onTpu();
  $("ptargets").textContent = ts.length ? ts.map(t => {
    const b = blurb(MODEL_NOTES[t.model] || "");
    return `${t.kind === "video" ? "Video" : "Image"}: ${t.model}` + (b ? "\n" + b.replace(/^experimental · /, "experimental\n") : "");
  }).join("\n\n") : "Nothing is ticked. Tick a video or image model on the Models tab.";
  const d = ts.length === 1 ? (ST.model_defaults[ts[0].model] || {}) : {};
  $("pw").placeholder = d.width || ""; $("ph").placeholder = d.height || ""; $("pframes").placeholder = d.frames || "";
  $("psteps").placeholder = d.steps || ""; $("pguid").placeholder = d.guidance ?? "";
  $("pframesbox").classList.toggle("hidden", !ts.some(t => t.kind === "video"));
  const fields = { width: "pw", height: "ph", frames: "pframes", steps: "psteps", guidance: "pguid", negative: "pneg" };
  for (const [name, id] of Object.entries(fields)) {
    const off = ts.length > 0 && ts.every(t => ((ST.model_defaults[t.model] || {}).locked || []).includes(name));
    $(id).disabled = off; if (off) $(id).value = "";
    $(id).title = off ? "the chosen model ignores this setting" : "";
    $(id).closest("div").style.opacity = off ? ".45" : "";
  }
}

// A card whose content is all hidden (Single Prompts mode, or an imported book that skips the PDF steps) would show only its title.
// Say why, and offer the switch.
function updateEmptyStates() {
  const prompts = radio("mode") === "prompts";
  const p = cur();
  document.querySelectorAll(".card").forEach(card => {
    const body = card.querySelector(":scope > .card__body");
    if (!body) return;
    if (card.dataset.autohidden) { card.classList.remove("hidden"); delete card.dataset.autohidden; }
    const old = body.querySelector(":scope > .empty-state");
    const kids = [...body.children].filter(c => !c.classList.contains("empty-state") && !c.classList.contains("step-nav"));
    const allHidden = kids.length > 0 && kids.every(c => c.classList.contains("hidden"));
    if (!allHidden) { if (old) old.remove(); return; }
    let text, label, target;
    if (kids.every(c => c.classList.contains("promptonly"))) {
      text = "This card is for Single Prompts mode."; label = "Switch to Single Prompts"; target = "prompts";
    } else if (prompts) {
      text = "This card is hidden because the mode is Single Prompts."; label = "Switch to Book from a PDF"; target = "book";
    } else if (p && p.legacy && body.querySelector(".bookstep")) {
      text = `${p.slug} is an imported book, so the PDF steps do not apply. Use Imported Book Tools, or pick another project in the Import tab.`;
    } else {
      card.classList.add("hidden"); card.dataset.autohidden = "1";   // nothing useful to say: hide the whole card
      if (old) old.remove();
      return;
    }
    const note = old || document.createElement("div");
    note.className = "empty-state";
    note.setAttribute("role", "status");
    note.textContent = "";
    const span = document.createElement("span");
    span.textContent = text;
    note.appendChild(span);
    if (target) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.textContent = label;
      btn.addEventListener("click", () => {
        const r = document.querySelector(`input[name=mode][value=${target}]`);
        if (r) { r.checked = true; setMode(); }
      });
      note.appendChild(btn);
    }
    if (!old) body.appendChild(note);
  });
}

function setMode() {
  if (typeof resetFilm === "function") resetFilm();
  const prompts = radio("mode") === "prompts";
  document.querySelectorAll(".bookonly").forEach(e => e.classList.toggle("hidden", prompts || (e.id === "legacypanel" && !(cur() && cur().legacy)) || (e.classList.contains("bookstep") && cur() && cur().legacy)));
  document.querySelectorAll(".promptonly").forEach(e => e.classList.toggle("hidden", !prompts));
  updateEmptyStates();
  loadGallery();
}

async function expandIdea() {
  const status = (text, cls = "warn") => { $("pIdeaStatus").textContent = text; $("pIdeaStatus").className = cls; };
  const idea = $("pidea").value.trim();
  if (!idea) { status("Write a short idea first.", "err"); $("pidea").focus(); return; }
  status("Asking the AI..."); $("bExpand").disabled = true;
  try {
    const first = promptTargets()[0] || { kind: "video", model: "" };                      // the prompts are written in the style of the first ticked model
    const j = await api("/api/expand", { kind: first.kind, target: first.model, idea, count: $("pcount").value, engine: $("engine").value, claude_model: $("cmodel").value });
    const cur_ = $("ptext").value.trim();
    $("ptext").value = (cur_ ? cur_ + "\n" : "") + j.prompts.join("\n");
    status(`Added ${j.prompts.length} prompt(s) to the box above. Edit them if you like.`);
  } catch (e) { status(e.message, "err"); }
  $("bExpand").disabled = false;
}

const galleryProject = () => radio("mode") === "prompts" ? $("pset").value.trim().toLowerCase() : ($("proj").value || "");
async function renderGallery(box, proj, emptyHint = "Pick a book or name a prompt set.") {
  if (!proj) { box.innerHTML = `<span class="warn">${emptyHint}</span>`; return; }
  try {
    const { items } = await api(`/api/gallery?project=${encodeURIComponent(proj)}`);
    box.innerHTML = items.length ? items.map(it => {
      const url = `/file/${proj}/${it.path.split("/").map(encodeURIComponent).join("/")}?t=${TOKEN}`;
      const media = it.kind === "image" ? `<a href="${url}" target="_blank" rel="noopener noreferrer"><img loading="lazy" src="${url}"></a>` : `<video controls preload="metadata" src="${url}"></video>`;
      const label = it.kind === "film" ? it.name : `${it.model} · row ${it.row}`;
      return `<div class="cell">${media}<div class="cap"><b>${label}</b><br>${(it.prompt || "").replace(/</g, "&lt;")}</div></div>`;
    }).join("") : '<span class="warn">Nothing generated here yet.</span>';
  } catch (e) { box.innerHTML = `<span class="err">${e.message}</span>`; }
}

async function loadGallery() {
  const proj = galleryProject();
  $("galsrc").textContent = proj ? `· ${projPath(proj)}/` : "";
  return renderGallery($("gallery"), proj);
}

// The audio list comes from the server (ST.audio_models), grouped by what the model makes; ticks are kept across redraws.
function renderAudioModels() {
  const el = $("amodels"); if (!el || !ST.audio_models) return;
  const keep = new Set([...document.querySelectorAll("input[name=audio]:checked")].map(i => i.value));
  const first = !el.children.length;
  el.innerHTML = Object.entries(ST.audio_roles || {}).map(([role, title]) => {
    const ms = Object.entries(ST.audio_models).filter(([, m]) => m.role === role);
    if (!ms.length) return "";
    return `<div class="model-group"><h3 class="model-group__title">${escapeHtml(title)}</h3><div class="model-list">` + ms.map(([k, m]) =>
      `<label class="opt"><input type="checkbox" name="audio" value="${k}" ${(first ? k === "kokoro" : keep.has(k)) ? "checked" : ""}><span>${escapeHtml(m.label)}<small>${escapeHtml(m.note)}</small></span></label>`).join("") + `</div></div>`;
  }).join("");
}

// ---------- grey out whatever cannot work, and say why ----------
function blockedWhy(name) {
  const b = ST.blockers[name]; if (!b) return null;
  return (b[radio("svc")] || {})[$("gpu").value] || null;
}
function setOff(input, why) {                 // disable an input inside a label.opt and show the reason; untick it if it was ticked
  const label = input.closest("label");
  const was = input.type === "checkbox" && input.checked && !!why;
  input.disabled = !!why;
  if (why && input.type === "checkbox") input.checked = false;
  if (label) {
    label.classList.toggle("off", !!why);
    label.title = why || "";
    let w = label.querySelector("small.why");
    if (why) {
      if (!w) { w = document.createElement("small"); w.className = "why"; w.style.display = "block"; (label.querySelector("span") || label).appendChild(w); }
      w.textContent = "Unavailable: " + why;
    } else if (w) w.remove();
  }
  return was;
}
function firstEnabled(sel) { return [...document.querySelectorAll(sel)].find(i => !i.disabled); }

let constraintDepth = 0;
function applyConstraints() {
  if (!ST || constraintDepth > 3) return;
  constraintDepth++;
  let again = false;                       // some controls below get rebuilt; check them once more afterwards
  const tools = ST.tools, p = cur(), prompts = radio("mode") === "prompts";
  // 1. tools that are not installed
  for (const o of $("engine").options) { o.disabled = !tools[o.value]; o.title = tools[o.value] ? "" : (o.value === "local" ? "Not available: " + ST.local_llm.reason : `${o.value} is not installed`); }
  if ($("engine").selectedOptions[0] && $("engine").selectedOptions[0].disabled) {
    const ok = [...$("engine").options].find(o => !o.disabled); if (ok) { $("engine").value = ok.value; engineChanged(); again = true; }
  }
  // Service radio buttons: show warning if CLI not installed, but don't disable - let user choose
  document.querySelectorAll("input[name=svc]").forEach(r => {
    const why = tools[r.value] ? null : r.value === "computer" ? (ST.computer_why || "no usable GPU found") : `the ${r.value} command is not installed`;
    const label = r.closest("label");
    if (label) {
      label.classList.toggle("off", !!why);
      label.title = why || "";
      let w = label.querySelector("small.why");
      if (why) {
        if (!w) { w = document.createElement("small"); w.className = "why"; w.style.display = "block"; (label.querySelector("span") || label).appendChild(w); }
        w.textContent = "Unavailable: " + why;
      } else if (w) w.remove();
    }
    // Don't disable the radio - let user select anyway; validation happens at run time
  });
  $("bExpand").disabled = ![...$("engine").options].some(o => !o.disabled);
  for (const id of ["bRuns", "bFetch"]) { $(id).disabled = !tools.kaggle; $(id).title = tools.kaggle ? "" : "the kaggle command is not installed"; }

  // 2. models that cannot run with the chosen service + GPU
  let lostVideo = false;
  document.querySelectorAll("input[name=vmodel]").forEach(i => { if (setOff(i, blockedWhy(i.value))) lostVideo = true; });
  if (lostVideo && !checked("vmodel").length) { const ok = firstEnabled("input[name=vmodel]"); if (ok) ok.checked = true; }
  let lostImage = false;
  document.querySelectorAll("input[name=imodel]").forEach(i => { if (setOff(i, blockedWhy(i.value))) lostImage = true; });
  if (lostImage && !checked("imodel").length) { const ok = firstEnabled("input[name=imodel]"); if (ok) ok.checked = true; }
  document.querySelectorAll("input[name=audio]").forEach(i => setOff(i, blockedWhy(i.value)));

  // 3. Single Prompts follows the models ticked on the Models tab
  updatePromptModels();

  // 4. book steps that need an earlier step first
  if (p && !p.legacy && !prompts) {
    const hasCh = p.chapters > 0;
    setOff($("b_ingest"), !tools.uv ? "uv is not installed (needed to read PDFs)" : (!p.pdf_choices.length ? "no PDF in the books folder" : null));
    setOff($("b_continuity"), (hasCh || $("b_ingest").checked) ? null : "read the PDF first (tick the step above)");
    setOff($("b_write"), (p.continuity || $("b_continuity").checked) ? null : "needs the continuity book first");
    setOff($("b_force"), $("b_write").checked ? null : "only applies when writing chapters");
    setOff($("b_build"), (p.scripts > 0 || $("b_write").checked) ? null : "needs written chapters first");
    const ready = p.built || $("b_build").checked;
    const noBuild = "the CSV files do not exist yet: tick 'Build the CSV files' (or run it once) first";
    setOff($("s_video"), ready ? null : noBuild);
    setOff($("s_audio"), ready ? null : noBuild);
    setOff($("s_merge"), !ready ? noBuild : (!tools.uv ? "uv is not installed" : null));
    setOff($("s_mix"), !ready ? noBuild : (!tools.uv ? "uv is not installed" : null));
    $("bEstimate").disabled = !hasCh;
    $("bEstimate").title = hasCh ? "" : "read the PDF first";
  } else if (p && p.legacy && !prompts) {
    for (const id of ["s_video", "s_audio"]) setOff($(id), null);        // imported books are already built; clear anything left over from another book
    setOff($("s_merge"), tools.uv ? null : "uv is not installed");
    setOff($("s_mix"), tools.uv ? null : "uv is not installed");
  }
  // 5. movies: only offer what exists (or will exist after the build step)
  if (p && !prompts) {
    const willBuild = !p.legacy && $("b_build").checked;
    document.querySelectorAll("input[name=gran]").forEach(r => setOff(r, (p.movies[r.value] || []).length || willBuild ? null : "no movies planned for this mode yet"));
    const gPicked = document.querySelector("input[name=gran]:checked");
    if (gPicked && gPicked.disabled) { const ok = firstEnabled("input[name=gran]"); if (ok) { ok.checked = true; renderMovies(); } }
    const list = p.movies[radio("gran")] || [];
    const idsRadio = document.querySelector("input[name=msel][value=ids]");
    setOff(idsRadio, list.length ? null : "no movies exist yet; choose 'the first N' to make them after the build step");
    if (idsRadio.disabled && idsRadio.checked) document.querySelector("input[name=msel][value=first]").checked = true;
  }
  if (again) applyConstraints();
  constraintDepth--;
}

// ---------- Kaggle runs: list them and fetch their results ----------
let runsLoaded = false;
async function loadRuns(scroll) {
  runsLoaded = true;
  const box = $("runs");
  box.innerHTML = '<span class="warn">asking Kaggle…</span>';
  if (scroll) { document.querySelector('[data-tab="results"]').click(); $("runspanel").scrollIntoView({ behavior: "smooth", block: "start" }); }
  try {
    const { runs } = await api("/api/kaggle_runs");
    if (!runs.length) { box.innerHTML = '<span class="warn">No notebooks made by this tool on your Kaggle account yet.</span>'; return; }
    const table = document.createElement("table");
    table.innerHTML = "<tr><th>notebook</th><th>status</th><th>last run (UTC)</th><th>project</th><th></th></tr>";
    for (const r of runs) {
      const tr = document.createElement("tr");
      const cell = t => { const td = document.createElement("td"); if (t instanceof Node) td.appendChild(t); else td.textContent = t; tr.appendChild(td); return td; };
      cell(r.slug);
      const st = cell(r.status); st.style.color = r.status === "COMPLETE" ? "var(--ok)" : r.status === "ERROR" ? "var(--bad)" : "var(--fg-muted)";
      cell(r.last_run);
      let sel = null;
      if (r.project) cell(r.project);
      else { sel = document.createElement("select"); sel.innerHTML = '<option value="">choose…</option>' + ST.projects.map(p => `<option>${p.slug}</option>`).join(""); sel.style.width = "auto"; cell(sel); }
      const going = r.status === "RUNNING" || r.status === "QUEUED";
      const b = document.createElement("button"); b.className = "fetchbtn"; b.style.padding = "2px 10px";
      b.textContent = going ? "Wait, then fetch" : "Fetch results";
      b.onclick = () => fetchRun(r.slug, sel ? sel.value : r.project, going);
      cell(b);
      table.appendChild(tr);
    }
    box.innerHTML = ""; box.appendChild(table);
  } catch (e) { box.innerHTML = `<span class="err">${e.message}</span>`; }
}

async function fetchRun(slug, project, wait) {
  $("msg").textContent = ""; $("msg").className = "warn";
  try {
    await api("/api/fetch", { slug, project: project || "", wait });
    since = 0; $("log").textContent = ""; building = true; poll();
    $("log").scrollIntoView({ behavior: "smooth", block: "center" });
  } catch (e) { $("msg").textContent = e.message; $("msg").className = "err"; }
}

// ---------- make the film from downloaded files ----------
let film = null, jobRunning = false;
const FILM_KINDS = [["narration", "fnarr"], ["sfx", "fsfx"], ["music", "fmusic"]];
const suffixOf = src => (src || "").endsWith("_chapters") ? "_chapters" : "";
function fillSelect(id, names, withNone) {
  $(id).innerHTML = (withNone ? '<option value="">(none)</option>' : "") + names.map(n => `<option value="${n}">${n}</option>`).join("");
}
// Where a project's folder is. Books, character image sets and Single Prompts sets live in different folders (see scripts/layout.py).
function projPath(slug) {
  if (!slug) return "";
  if (/^char_/.test(slug)) return `projects/characters/${slug}`;
  const isSet = !!ST && (ST.promptsets || []).some(x => x.slug === slug);
  return isSet ? `projects/prompts/${slug}` : `projects/books/${slug}`;
}

function resetFilm() { film = null; $("filmsrc").textContent = ""; $("filmmsg").textContent = ""; $("ftable").innerHTML = ""; }

async function loadFilm(scroll) {
  const proj = galleryProject();
  if (scroll) { document.querySelector('[data-tab="results"]').click(); $("filmpanel").scrollIntoView({ behavior: "smooth", block: "start" }); }
  if (!proj) { $("filmmsg").textContent = "pick a book or name a prompt set first"; $("filmmsg").className = "err"; return; }
  try {
    const inv = await api(`/api/media?project=${encodeURIComponent(proj)}`);
    film = { proj, inv };
    $("filmsrc").textContent = `· ${projPath(proj)}/`;
    const vids = Object.keys(inv.videos).sort((a, b) => inv.videos[b].length - inv.videos[a].length);
    if (!vids.length) { $("filmmsg").textContent = `no downloaded clips in ${projPath(proj)}/videos yet`; $("filmmsg").className = "err"; return; }
    $("filmmsg").textContent = "";
    fillSelect("fvideo", vids, false);
    chooseFilmAudio();
    renderFilmTable();
  } catch (e) { $("filmmsg").textContent = e.message; $("filmmsg").className = "err"; }
}

function chooseFilmAudio() {                  // default each audio folder to the one that matches the clips (same per-shot / per-chapter mode)
  const vs = $("fvideo").value;
  for (const [kind, id] of FILM_KINDS) {
    const names = Object.keys(film.inv[kind]);
    fillSelect(id, names, true);
    $(id).value = names.find(n => suffixOf(n) === suffixOf(vs)) || "";
  }
}

function renderFilmTable() {
  const inv = film.inv, vs = $("fvideo").value, rows = inv.videos[vs] || [];
  const have = {};
  for (const [kind, id] of FILM_KINDS) have[kind] = new Set($(id).value ? inv[kind][$(id).value] : []);
  const cols = [["video", "clip"], ["narration", "narration"], ["sfx", "effects"], ["music", "music"]];
  const table = document.createElement("table");
  const head = document.createElement("tr");
  head.innerHTML = "<th>order</th><th>row</th><th>what it shows</th><th title=\"Seconds cut off the start and end of the clip (the narration is not cut)\">trim start / end (s)</th>" + cols.map(([k, t]) => `<th><label style="cursor:pointer"><input type="checkbox" class="colall" data-col="${k}" checked> ${t}</label></th>`).join("");
  table.appendChild(head);
  for (const n of rows) {
    const tr = document.createElement("tr"); tr.dataset.row = n;
    const td = (content) => { const c = document.createElement("td"); c.innerHTML = content; tr.appendChild(c); return c; };
    td(`<span style="white-space:nowrap"><button type="button" class="fmove" data-dir="-1" aria-label="Move row ${n} earlier" style="padding:2px 8px">&uarr;</button><button type="button" class="fmove" data-dir="1" aria-label="Move row ${n} later" style="padding:2px 8px">&darr;</button></span>`);
    td(String(n));
    const t = td(""); t.textContent = inv.texts[vs][String(n)] || ""; t.style.maxWidth = "380px"; t.style.fontSize = "12px"; t.style.color = "var(--fg-muted)";
    td(`<span style="white-space:nowrap"><input type="number" class="ftrim" data-end="start" min="0" max="30" step="0.1" value="0" aria-label="Seconds cut from the start of row ${n}" style="width:64px"> <input type="number" class="ftrim" data-end="end" min="0" max="30" step="0.1" value="0" aria-label="Seconds cut from the end of row ${n}" style="width:64px"></span>`);
    for (const [k] of cols) {
      const available = k === "video" || have[k].has(n);
      const c = td(`<input type="checkbox" class="cell" data-col="${k}" ${available ? "checked" : "disabled"} title="${available ? "" : "no file for this row in the chosen folder"}">`);
      if (!available) c.style.opacity = ".4";
    }
    table.appendChild(tr);
  }
  $("ftable").innerHTML = ""; $("ftable").appendChild(table);
  table.addEventListener("click", ev => {          // move a row up or down: the film follows the table's order
    const b = ev.target.closest("button.fmove");
    if (!b) return;
    const tr = b.closest("tr"), dir = Number(b.dataset.dir);
    const other = dir < 0 ? tr.previousElementSibling : tr.nextElementSibling;
    if (!other || !other.dataset.row) return;
    if (dir < 0) other.before(tr); else other.after(tr);
    b.focus();
    updateFilmSummary();
  });
  table.addEventListener("change", ev => {
    const t = ev.target;
    if (t.classList.contains("colall")) table.querySelectorAll(`input.cell[data-col="${t.dataset.col}"]:not(:disabled)`).forEach(c => { c.checked = t.checked; });
    updateFilmSummary();
  });
  table.addEventListener("input", ev => { if (ev.target.classList.contains("ftrim")) renderTimeline(); });
  updateFilmSummary();
}

function filmSelection() {
  return [...document.querySelectorAll("#ftable tr[data-row]")].map(tr => {
    const get = k => tr.querySelector(`input.cell[data-col="${k}"]`).checked;
    const rowNum = Number(tr.dataset.row);
    const prompt = (film && film.inv && film.inv.texts && film.inv.texts[$("fvideo").value] && film.inv.texts[$("fvideo").value][String(rowNum)]) || "";
    const trim = k => Math.min(Math.max(Number(tr.querySelector(`input.ftrim[data-end="${k}"]`).value) || 0, 0), 30);
    return { n: rowNum, video: get("video"), narration: get("narration"), sfx: get("sfx"), music: get("music"), prompt, trim_start: trim("start"), trim_end: trim("end") };
  }).filter(r => r.video);
}

function updateFilmSummary() {
  if (!film) return;
  const sel = filmSelection(), count = k => sel.filter(r => r[k]).length;
  $("fsummary").textContent = `${sel.length} clip(s) · ${count("narration")} narration · ${count("sfx")} effects · ${count("music")} music`;
  const noUv = ST && !ST.tools.uv;
  $("bFilmMake").disabled = !sel.length || jobRunning || noUv;
  $("bFilmMake").title = noUv ? "uv is not installed (needed to run the video tool)" : (jobRunning ? "another job is running" : "");
  renderTimeline();
}

// ---------- the film's look and the suggested models for every step ----------
var SUGG = null, suggSeq = 0;              // var: loadStatus may call in before this line has run
var LOOK_KEY = "studio_look";
function lookOf(id) { return (ST.looks || []).find(l => l.id === id); }
function initLooks() {
  if (!ST.looks || $("lookOpts").children.length) return;
  $("lookOpts").innerHTML = ST.looks.map(l => `<label class="look-opt" title="${escapeHtml(l.about)}"><input type="radio" name="look" value="${l.id}"><span>${escapeHtml(l.label)}</span></label>`).join("");
  let saved = "";
  try { saved = localStorage.getItem(LOOK_KEY) || ""; } catch (e) {}
  const start = lookOf(saved) ? saved : ST.looks[0].id;
  document.querySelector(`input[name=look][value="${start}"]`).checked = true;
  document.querySelectorAll("input[name=look]").forEach(r => r.addEventListener("change", () => lookChanged(true)));
  lookChanged(false);
}
// Style words of every look are kept apart from the person's own words in the Global Parameters: switching looks swaps only the look's words.
function swapLookWords(text, field, look) {
  const mine = new Set((ST.looks || []).flatMap(l => l[field].split(",").map(w => w.trim().toLowerCase())));
  const kept = text.split(",").map(w => w.trim()).filter(w => w && !mine.has(w.toLowerCase()));
  return [...(look ? look[field].split(",").map(w => w.trim()) : []), ...kept].join(", ");
}
async function lookChanged(byPerson) {
  const id = radio("look"), l = lookOf(id);
  if (!l) return;
  try { localStorage.setItem(LOOK_KEY, id); } catch (e) {}
  $("lookAbout").textContent = l.about + " Suggested models and the style words in every prompt follow this choice.";
  $("pLookText").textContent = `Add the ${l.label} style words to my prompts`;
  if (byPerson && $("globalPositives") && $("globalNegatives")) {      // the look's words go into the Global Parameters (book prompts, character pictures)
    $("globalPositives").value = swapLookWords($("globalPositives").value, "positives", l);
    $("globalNegatives").value = swapLookWords($("globalNegatives").value, "negatives", l);
    const p = typeof cur === "function" ? cur() : null;
    if (p && !p.not_started) await saveGlobalParams();          // a book that exists keeps them; otherwise they wait in this browser until one does
    else { try { localStorage.setItem("globalPositives", $("globalPositives").value); localStorage.setItem("globalNegatives", $("globalNegatives").value); } catch (e) {} }
    $("msg").textContent = `Look: ${l.label}. Its style words are now in the Global Parameters (Movies tab). Prompts already written for a book keep their words until the book's shots are written again; keyframes made from now on take the new look.`;
    $("msg").className = "warn";
  }
  refreshSuggestions();
}
async function refreshSuggestions() {
  const look = radio("look"), svc = radio("svc"), gpu = $("gpu").value;
  if (!look || !svc) return;
  const seq = ++suggSeq;
  try {
    const r = await api(`/api/suggest?look=${encodeURIComponent(look)}&service=${encodeURIComponent(svc)}&gpu=${encodeURIComponent(gpu || "")}`);
    if (seq !== suggSeq) return;                      // a newer choice was made while this one loaded
    SUGG = r; renderSuggestions();
  } catch (e) {
    if (seq !== suggSeq) return;
    SUGG = null; $("suggestBody").textContent = e.message; markSuggested();
  }
}
function modelLabel(m) { return (ST.upscale_models && ST.upscale_models[m] && ST.upscale_models[m].label) || (ST.audio_models && ST.audio_models[m] && ST.audio_models[m].label) || m; }
function renderSuggestions() {
  const l = lookOf(SUGG.look);
  const gpuText = $("gpu").selectedOptions[0] ? $("gpu").selectedOptions[0].textContent : SUGG.gpu;
  $("suggestFor").textContent = `${l ? l.label : SUGG.look} · ${SUGG.service === "computer" ? "this computer" : SUGG.service} · ${gpuText}`;
  const box = (step, m, text, why, off) => `<label class="sugg-choice${off ? " off" : ""}"><input type="checkbox" class="sugg-pick" data-step="${step}" value="${escapeHtml(m)}"${off ? " disabled" : ""}>`
    + `<span>${text}<small>${escapeHtml(why)}</small></span></label>`;
  const rows = Object.entries(SUGG.steps).map(([step, st]) => {
    const pick = st.pick ? box(step, st.pick.model, `<b>${escapeHtml(modelLabel(st.pick.model))}</b>`, st.pick.why, !!st.note)
                         : `<span class="err">${escapeHtml(st.note || "nothing here can run with this choice of where to run")}</span>`;
    const alts = st.alternatives.map(a => box(step, a.model, escapeHtml(modelLabel(a.model)), a.blocked ? "not now: " + a.blocked : a.why, !!a.blocked || !!st.note)).join("") || "<small>none</small>";
    return `<tr><th scope="row">${escapeHtml(st.title)}<small>${escapeHtml(st.where)}</small></th><td>${pick}</td><td>${alts}</td></tr>`;
  }).join("");
  $("suggestBody").innerHTML = (SUGG.gpu_problem ? `<p class="err">${escapeHtml(SUGG.gpu_problem)}</p>` : "")
    + `<table class="sugg-table"><thead><tr><th scope="col">Step</th><th scope="col">Suggested</th><th scope="col">Other choices</th></tr></thead><tbody>${rows}</tbody></table>`;
  markSuggested();
  syncSuggestChecks();
}
// The ticks in the Suggested Models card are another view of the real choices: picture / video / audio models (Video & Audio Models card),
// the keyframe model with the keyframes step (Movies tab), and the upscaler (Make Film). Ticking here changes those; changing those re-ticks here.
const STEP_INPUT = { image: "imodel", video_i2v: "vmodel", video_t2v: "vmodel", narration: "audio", music: "audio" };
function modelInput(name, m) { return [...document.querySelectorAll(`input[name=${name}]`)].find(i => i.value === m); }
function suggestChosen(step, m) {
  if (STEP_INPUT[step]) { const i = modelInput(STEP_INPUT[step], m); return !!(i && i.checked); }
  if (step === "keyframe") return $("s_keyframes").checked && $("kfmodel").value === m;
  if (step === "upscale") return $("fupmodel").value === m;
  return false;
}
function syncSuggestChecks() {
  document.querySelectorAll("#suggestBody input.sugg-pick").forEach(c => {
    c.checked = suggestChosen(c.dataset.step, c.value);
    const target = STEP_INPUT[c.dataset.step] ? modelInput(STEP_INPUT[c.dataset.step], c.value) : null;
    const gone = STEP_INPUT[c.dataset.step] && (!target || target.disabled);          // not offered, or greyed out in the models card
    if (gone && !c.closest("label").classList.contains("off")) { c.disabled = true; c.title = target ? (target.closest("label") || {}).title || "unavailable here" : "not in the model lists"; }
  });
}
$("suggestBody").addEventListener("change", ev => {
  const c = ev.target.closest("input.sugg-pick"); if (!c) return;
  const step = c.dataset.step, m = c.value, on = c.checked;      // read first: the changes below re-sync these boxes
  if (STEP_INPUT[step]) {
    const i = modelInput(STEP_INPUT[step], m);
    if (i && !i.disabled) { i.checked = on; i.dispatchEvent(new Event("change", { bubbles: true })); }
  } else if (step === "keyframe") {               // one keyframe model: ticking one picks it and turns keyframes on; unticking turns them off
    if (on) { $("kfmodel").value = m; $("kfmodel").dispatchEvent(new Event("change")); }
    $("s_keyframes").checked = on; $("s_keyframes").dispatchEvent(new Event("change"));
  } else if (step === "upscale" && on) {          // one upscaler at a time
    $("fupmodel").value = m; showUpscaleNote();
  }
  if (typeof applyConstraints === "function") applyConstraints();
  if (typeof updatePromptModels === "function") updatePromptModels();
  markSuggested();
  syncSuggestChecks();
  $("suggestStatus").textContent = `${modelLabel(m)} ${suggestChosen(step, m) ? "selected" : "no longer selected"}`;
  $("suggestStatus").className = "warn";
});
["vmodels", "imodels", "amodels"].forEach(id => $(id).addEventListener("change", syncSuggestChecks));
["kfmodel", "s_keyframes", "fupmodel"].forEach(id => $(id).addEventListener("change", syncSuggestChecks));
function pickOf(step) { return SUGG && SUGG.steps[step] && SUGG.steps[step].pick ? SUGG.steps[step].pick.model : ""; }
function markSuggested() {                            // the "suggested" tag beside each suggested model, wherever models are chosen
  document.querySelectorAll(".sugg-tag[data-auto]").forEach(t => t.remove());
  const picks = new Set(SUGG ? Object.values(SUGG.steps).filter(s => s.pick).map(s => s.pick.model) : []);
  document.querySelectorAll("input[name=vmodel], input[name=imodel], input[name=audio]").forEach(i => {
    if (!picks.has(i.value)) return;
    const span = i.closest("label") && i.closest("label").querySelector("span");
    if (span) span.insertAdjacentHTML("beforeend", '<span class="sugg-tag" data-auto>suggested</span>');
  });
  for (const [sel, step] of [["kfmodel", "keyframe"], ["fupmodel", "upscale"]]) {
    for (const o of $(sel).options) { o.textContent = o.textContent.replace(/^★ /, ""); if (o.value === pickOf(step)) o.textContent = "★ " + o.textContent; }
  }
  const hint = (el, step, current, apply) => {
    const st = SUGG && SUGG.steps[step], p = st && st.pick;
    if (!p) { el.textContent = st && st.note ? st.note : ""; return; }
    if (p.model === current) { el.textContent = `★ Suggested for this look: ${modelLabel(p.model)}.`; return; }
    el.innerHTML = `Suggested for this look: <b>${escapeHtml(modelLabel(p.model))}</b> (${escapeHtml(p.why)}). <button type="button" class="sugg-use">Use it</button>`;
    el.querySelector("button").onclick = apply;
  };
  hint($("kfSuggest"), "keyframe", $("kfmodel").value, () => { $("kfmodel").value = pickOf("keyframe"); $("kfmodel").dispatchEvent(new Event("change")); markSuggested(); });
  hint($("upSuggest"), "upscale", $("fupmodel").value, () => { $("fupmodel").value = pickOf("upscale"); showUpscaleNote(); markSuggested(); });
}
function tickOnly(name, models) {                     // tick exactly these (when they can run); returns the ones ticked
  const done = [];
  document.querySelectorAll(`input[name=${name}]`).forEach(i => { i.checked = models.includes(i.value) && !i.disabled; if (i.checked) done.push(i.value); });
  return done;
}
function useSuggestions() {
  if (!SUGG) { $("suggestStatus").textContent = "no suggestions yet: choose a look and where to run"; $("suggestStatus").className = "err"; return; }
  const done = [];
  const img = pickOf("image"); if (img) done.push(...tickOnly("imodel", [img]));
  const kf = pickOf("keyframe"), i2v = pickOf("video_i2v"), t2v = pickOf("video_t2v");
  if (kf && i2v) {
    $("kfmodel").value = kf; $("kfmodel").dispatchEvent(new Event("change"));
    $("s_keyframes").checked = true; $("s_keyframes").dispatchEvent(new Event("change"));
    done.push(...tickOnly("vmodel", [i2v]), `keyframes ${kf}`);
  } else if (t2v) {
    $("s_keyframes").checked = false; $("s_keyframes").dispatchEvent(new Event("change"));
    done.push(...tickOnly("vmodel", [t2v]));
  }
  const keepSfx = [...document.querySelectorAll("input[name=audio]:checked")].map(i => i.value).filter(k => ST.audio_models[k] && ST.audio_models[k].role === "sfx");
  done.push(...tickOnly("audio", [pickOf("narration"), pickOf("music"), ...keepSfx].filter(Boolean)));
  const up = pickOf("upscale"); if (up && [...$("fupmodel").options].some(o => o.value === up && !o.disabled)) { $("fupmodel").value = up; showUpscaleNote(); done.push(`upscaler ${modelLabel(up)}`); }
  document.querySelectorAll("input[name=vmodel], input[name=imodel], input[name=audio]").forEach(i => i.dispatchEvent(new Event("change", { bubbles: true })));
  if (typeof applyConstraints === "function") applyConstraints();
  if (typeof updatePromptModels === "function") updatePromptModels();
  markSuggested();
  syncSuggestChecks();
  $("suggestStatus").textContent = done.length ? "Now using: " + done.map(modelLabel).join(", ") : "nothing could be selected here";
  $("suggestStatus").className = done.length ? "warn" : "err";
}
$("bUseSuggest").addEventListener("click", useSuggestions);
$("bLookSuggest").addEventListener("click", () => { document.querySelector('[data-tab="models"]').click(); $("suggestCard").scrollIntoView({ behavior: "smooth", block: "start" }); });
$("kfmodel").addEventListener("change", markSuggested);
$("fupmodel").addEventListener("change", markSuggested);
$("gpu").addEventListener("change", refreshSuggestions);      // a new service refreshes them from fillGpus, once its GPU list is filled

// ---------- Make Film timeline: the table drawn to scale. Dragging here edits the table, which stays the one record of the film. ----------
const TL_CARD = 3.5;                                  // title and end cards last this long (mix_film.py CARD_SECONDS)
const pad4 = n => String(n).padStart(4, "0");
const filmFileUrl = rel => `/file/${film.proj}/${rel.split("/").map(encodeURIComponent).join("/")}?t=${TOKEN}`;
let tlScale = 40;                                     // pixels per second, chosen so the whole film fits the box
function tlRows() {                                   // the ticked clips in film order, with how long each one plays
  const vs = $("fvideo").value, ns = $("fnarr").value, secs = (film && film.inv.seconds) || {};
  return filmSelection().map(r => {
    const known = (secs[vs] || {})[String(r.n)];
    const clip = known || 4;                          // a clip whose length cannot be read is drawn as 4 s
    const narr = r.narration && ns ? ((secs[ns] || {})[String(r.n)] || 0) : 0;
    const shown = Math.max(clip - r.trim_start - r.trim_end, 0.1);
    const plays = FIT_SYNCS.includes($("fsync").value) ? Math.max(shown, narr) : shown;
    return { ...r, clip, narr, shown, plays, known: !!known };
  });
}
function tlRow(n) { return document.querySelector(`#ftable tr[data-row="${n}"]`); }
function tlTrimInput(n, end) { const tr = tlRow(n); return tr ? tr.querySelector(`input.ftrim[data-end="${end}"]`) : null; }
function tlMoveTo(n, index) {                         // put clip n at position index among the ticked clips (the table rows move)
  const order = tlRows().map(r => r.n).filter(x => x !== n);
  index = Math.max(0, Math.min(index, order.length));
  const tr = tlRow(n), next = order[index], prev = order[index - 1];
  if (!tr) return;
  if (next !== undefined) tlRow(next).before(tr); else if (prev !== undefined) tlRow(prev).after(tr);
  updateFilmSummary();
}
function renderTimeline() {
  const box = $("ftimeline");
  if (!box || !film) return;
  const rows = tlRows();
  if (!rows.length) { box.innerHTML = '<p class="warn" style="margin:4px">No clips ticked.</p>'; $("tlinfo").textContent = ""; return; }
  const title = $("ftitle").value.trim(), endT = $("fendtitle").value.trim();
  const total = rows.reduce((a, r) => a + r.plays, 0) + (title ? TL_CARD : 0) + (endT ? TL_CARD : 0);
  tlScale = Math.max(28, Math.min(90, (box.clientWidth - 24) / Math.max(total, 1)));
  const px = sec => Math.round(sec * tlScale);
  const width = px(total) + 4;
  const step = total > 240 ? 30 : total > 90 ? 10 : 5;
  let ruler = "";
  for (let t = 0; t <= total; t += step) ruler += `<span style="left:${px(t)}px">${Math.floor(t / 60)}:${String(Math.round(t % 60)).padStart(2, "0")}</span>`;
  let at = 0, clips = "", sound = "";
  if (title) { clips += `<div class="tl-card" style="left:0;width:${px(TL_CARD) - 2}px" title="Title card, ${TL_CARD} s"></div>`; at += TL_CARD; }
  for (const r of rows) {
    const w = Math.max(px(r.plays) - 2, 18);
    const lab = `Row ${r.n}: ${r.shown.toFixed(1)} s of ${r.clip.toFixed(1)} s${r.plays > r.shown + 0.05 ? `, stretched to ${r.plays.toFixed(1)} s` : ""}${r.known ? "" : " (length unknown)"}`;
    clips += `<button type="button" class="tl-clip" data-row="${r.n}" style="left:${px(at)}px;width:${w}px" title="${lab}" aria-label="${lab}. Arrow keys move it, Shift and an arrow trims its end."><span class="tl-handle l" data-end="start" aria-hidden="true"></span>${r.n}<small>${r.plays.toFixed(1)} s</small><span class="tl-handle r" data-end="end" aria-hidden="true"></span></button>`;
    if (r.narr) sound += `<div class="tl-audio${r.narr > r.shown + 0.05 && !FIT_SYNCS.includes($("fsync").value) ? " long" : ""}" style="left:${px(at)}px;width:${Math.max(px(Math.min(r.narr, r.plays)) - 2, 4)}px" title="Narration for row ${r.n}: ${r.narr.toFixed(1)} s${r.narr > r.shown + 0.05 && !FIT_SYNCS.includes($("fsync").value) ? " (longer than the clip: " + ($("fsync").value === "speed" ? "it is sped up" : "it is cut") + ")" : ""}">${r.narr.toFixed(1)} s</div>`;
    at += r.plays;
  }
  if (endT) clips += `<div class="tl-card" style="left:${px(at)}px;width:${px(TL_CARD) - 2}px" title="End card, ${TL_CARD} s"></div>`;
  box.innerHTML = `<div style="width:${width}px"><div class="tl-ruler">${ruler}</div><p class="tl-label">Picture</p><div class="tl-lane" id="tlclips">${clips}</div>`
    + `<p class="tl-label">Narration${$("fnarr").value ? "" : " (none chosen)"}</p><div class="tl-lane tl-sound">${sound}</div></div>`;
  const cards = box.querySelectorAll(".tl-card");     // card text is typed by the user: set as text, never as HTML
  if (title) cards[0].textContent = title;
  if (endT) cards[cards.length - 1].textContent = endT;
  $("tlinfo").textContent = `about ${Math.floor(total / 60)} min ${Math.round(total % 60)} s` + ($("ftrans").value === "fade" ? " (fades overlap a little)" : "");
}
function tlPreview(n) {                               // watch one clip, from its trimmed start to its trimmed end, with its narration
  const r = tlRows().find(x => x.n === n); if (!r) return;
  tlPlay.queue = [r]; tlPlay.i = -1; tlNext();
}
const tlPlay = { queue: [], i: -1, vDone: false, aDone: false, end: 0, timer: 0 };
function tlStop() {
  clearTimeout(tlPlay.timer); tlPlay.queue = []; tlPlay.i = -1;
  $("tlvideo").pause(); $("tlaudio").pause();
  document.querySelectorAll(".tl-clip.playing").forEach(b => b.classList.remove("playing"));
}
function tlNext() {
  document.querySelectorAll(".tl-clip.playing").forEach(b => b.classList.remove("playing"));
  tlPlay.i++;
  const item = tlPlay.queue[tlPlay.i];
  const v = $("tlvideo"), a = $("tlaudio");
  if (!item) { v.pause(); a.pause(); $("tlinfo").textContent = tlPlay.queue.length > 1 ? "preview finished" : ""; return; }
  if (item.card) { v.pause(); a.pause(); $("tlinfo").textContent = `card: ${item.card}`; tlPlay.timer = setTimeout(tlNext, TL_CARD * 1000); return; }
  const btn = document.querySelector(`.tl-clip[data-row="${item.n}"]`); if (btn) btn.classList.add("playing");
  tlPlay.vDone = false; tlPlay.aDone = !item.narr; tlPlay.end = item.clip - item.trim_end;
  v.style.display = "";
  v.preload = "auto";
  v.onloadedmetadata = () => { v.currentTime = item.trim_start; };
  v.src = filmFileUrl(`${$("fvideo").value}/shot-${pad4(item.n)}.mp4`);
  v.play().catch(() => {});                           // straight away, inside the click: the browser only lets a click start sound
  if (item.narr) { a.src = filmFileUrl(`${$("fnarr").value}/narration-${pad4(item.n)}.wav`); a.currentTime = 0; a.play().catch(() => {}); } else { a.pause(); a.removeAttribute("src"); }
  $("tlinfo").textContent = `playing row ${item.n}` + (tlPlay.queue.length > 1 ? ` (${tlPlay.i + 1} of ${tlPlay.queue.length})` : "");
}
function tlCheckDone() { if (tlPlay.i >= 0 && tlPlay.vDone && tlPlay.aDone) tlNext(); }
$("tlvideo").addEventListener("timeupdate", () => {
  const v = $("tlvideo");
  if (tlPlay.i >= 0 && !tlPlay.vDone && v.currentTime >= tlPlay.end - 0.03) { v.pause(); tlPlay.vDone = true; tlCheckDone(); }
});
$("tlvideo").addEventListener("ended", () => { if (tlPlay.i >= 0 && !tlPlay.vDone) { tlPlay.vDone = true; tlCheckDone(); } });
$("tlaudio").addEventListener("ended", () => { tlPlay.aDone = true; tlCheckDone(); });
$("bTlPlay").addEventListener("click", () => {
  if (!film) return;
  tlStop();
  const title = $("ftitle").value.trim(), endT = $("fendtitle").value.trim();
  tlPlay.queue = [...(title ? [{ card: title }] : []), ...tlRows(), ...(endT ? [{ card: endT }] : [])];
  tlPlay.i = -1; tlNext();
});
$("bTlStop").addEventListener("click", () => { tlStop(); $("tlinfo").textContent = "stopped"; });
(() => {                                              // dragging: move a clip, or trim it by its edges
  const box = $("ftimeline");
  let drag = null;
  box.addEventListener("pointerdown", ev => {
    const btn = ev.target.closest(".tl-clip"); if (!btn || ev.button !== 0) return;
    const n = Number(btn.dataset.row), handle = ev.target.closest(".tl-handle");
    const r = tlRows().find(x => x.n === n); if (!r) return;
    drag = { btn, n, r, x0: ev.clientX, left0: btn.offsetLeft, w0: btn.offsetWidth, end: handle ? handle.dataset.end : "", moved: false };
    btn.setPointerCapture(ev.pointerId);
    ev.preventDefault();                              // no text selection while dragging; this also skips the click's focus, so give it here
    btn.focus({ preventScroll: true });
  });
  box.addEventListener("pointermove", ev => {
    if (!drag) return;
    const dx = ev.clientX - drag.x0;
    if (Math.abs(dx) > 4) drag.moved = true;
    if (!drag.moved) return;
    if (drag.end) {                                   // trim: an edge moves, the clip's other end stays
      const r = drag.r, sec = dx / tlScale, room = r.clip - 0.1;
      const v = drag.end === "start" ? Math.min(Math.max(r.trim_start + sec, 0), 30, room - r.trim_end) : Math.min(Math.max(r.trim_end - sec, 0), 30, room - r.trim_start);
      const input = tlTrimInput(drag.n, drag.end); if (input) input.value = (Math.round(v * 10) / 10).toFixed(1);
      const shown = Math.max(r.clip - (drag.end === "start" ? v : r.trim_start) - (drag.end === "end" ? v : r.trim_end), 0.1);
      const w = Math.max(Math.round(shown * tlScale) - 2, 18);
      if (drag.end === "start") drag.btn.style.left = `${drag.left0 + drag.w0 - w}px`;
      drag.btn.style.width = `${w}px`;
      drag.btn.querySelector("small").textContent = `${shown.toFixed(1)} s`;
    } else {
      drag.btn.classList.add("dragging");
      drag.btn.style.transform = `translateX(${dx}px)`;
    }
  });
  const finish = ev => {
    if (!drag) return;
    const d = drag; drag = null;
    if (!d.moved) { if (!d.end) tlPreview(d.n); return; }
    if (d.end) { updateFilmSummary(); return; }
    const centre = d.left0 + d.w0 / 2 + (ev.clientX - d.x0);
    const others = [...$("ftimeline").querySelectorAll(".tl-clip")].filter(b => b !== d.btn);
    tlMoveTo(d.n, others.filter(b => b.offsetLeft + b.offsetWidth / 2 < centre).length);
    const again = document.querySelector(`.tl-clip[data-row="${d.n}"]`); if (again) again.focus();
  };
  box.addEventListener("pointerup", finish);
  let lastWidth = 0;                                  // drawn to fit the box: draw again when it gets wider or narrower (window, or its tab shown)
  new ResizeObserver(() => { if (box.clientWidth !== lastWidth) { lastWidth = box.clientWidth; if (film && !drag) renderTimeline(); } }).observe(box);
  box.addEventListener("pointercancel", () => { drag = null; renderTimeline(); });
  box.addEventListener("keydown", ev => {             // the same moves without a mouse
    const btn = ev.target.closest(".tl-clip"); if (!btn || !["ArrowLeft", "ArrowRight"].includes(ev.key)) return;
    ev.preventDefault();
    const n = Number(btn.dataset.row), rows = tlRows(), i = rows.findIndex(r => r.n === n), r = rows[i];
    if (ev.shiftKey) {
      const input = tlTrimInput(n, "end"); if (!input) return;
      const v = Math.min(Math.max(r.trim_end + (ev.key === "ArrowLeft" ? 0.1 : -0.1), 0), 30, r.clip - 0.1 - r.trim_start);
      input.value = (Math.round(v * 10) / 10).toFixed(1);
      updateFilmSummary();
    } else {
      tlMoveTo(n, i + (ev.key === "ArrowLeft" ? -1 : 1));
    }
    const again = document.querySelector(`.tl-clip[data-row="${n}"]`); if (again) again.focus();
  });
})();
["ftitle", "fendtitle"].forEach(id => $(id).addEventListener("input", renderTimeline));
["fsync", "ftrans"].forEach(id => $(id).addEventListener("change", renderTimeline));

// ---------- upscalers: which one, and how much GPU memory it needs ----------
function upscaleWhy(k) { const svc = radio("svc"), gpu = $("gpu").value; if (svc === "computer" && ST.computer_why) return ST.computer_why; return ((ST.gpu_blockers || {})[svc] || {})[gpu] || (((ST.blockers || {})[k] || {})[svc] || {})[gpu] || ""; }
function fillUpscalers() {
  if (!ST || !ST.upscale_models) return;
  const prev = $("fupmodel").value;
  $("fupmodel").innerHTML = Object.entries(ST.upscale_models).map(([k, u]) => `<option value="${k}" ${upscaleWhy(k) ? "disabled" : ""}>${u.label} (${u.short})${upscaleWhy(k) ? " - unavailable here" : ""}</option>`).join("");
  const ok = [...$("fupmodel").options].filter(o => !o.disabled);
  $("fupmodel").value = ok.some(o => o.value === prev) ? prev : (ok[0] || $("fupmodel").options[0] || {}).value || "";
  showUpscaleNote();
  if (typeof markSuggested === "function") markSuggested();
}
function showUpscaleNote() {
  const k = $("fupmodel").value, u = (ST.upscale_models || {})[k];
  const why = upscaleWhy(k);
  $("fupnote").textContent = u ? `${u.label}: ${u.memory}.` + (why ? ` Not with the Models tab's choice: ${why}.` : "") : "";
  $("fupnote").className = why ? "err" : "warn";
}
$("fupmodel").addEventListener("change", showUpscaleNote);
$("gpu").addEventListener("change", fillUpscalers);

function tickAll(on) {
  document.querySelectorAll("#ftable input.cell:not(:disabled), #ftable input.colall").forEach(c => { c.checked = on; });
  updateFilmSummary();
}

async function makeFilm() {
  const rows = filmSelection();
  const body = { project: film.proj, name: $("fname").value.trim(), video_source: $("fvideo").value,
                 sources: { narration: $("fnarr").value, sfx: $("fsfx").value, music: $("fmusic").value },
                 rows: rows.map(r => ({ n: r.n, narration: r.narration, sfx: r.sfx, music: r.music, trim_start: r.trim_start, trim_end: r.trim_end })), sync: $("fsync").value,
                 transition: $("ftrans").value, fade: $("ffade").value, title: $("ftitle").value.trim(), end_title: $("fendtitle").value.trim(), burn_captions: $("fburn").checked,
                 match_colour: $("fcolour").checked, music_bed: $("fbed").checked, duck: $("fduck").checked, loudnorm: $("fln").checked,
                 vol: { narration: $("fvn").value, sfx: $("fvs").value, music: $("fvm").value } };
  $("msg").textContent = ""; $("msg").className = "warn";
  try {
    await deleteNotebooks();
    await api("/api/make_film", body);
    since = 0; $("log").textContent = ""; building = true; poll();
    $("log").scrollIntoView({ behavior: "smooth", block: "center" });
  } catch (e) { $("msg").textContent = e.message; $("msg").className = "err"; }
}

document.querySelectorAll("input[name=svc]").forEach(e => e.addEventListener("change", fillGpus));
document.querySelectorAll("input[name=gran]").forEach(e => e.addEventListener("change", renderMovies));
function fillModels() {
  const e = $("engine").value;       // fcc-claude accepted a catalog name in my test (nemotron-3-ultra), so it gets both lists
  // codex now uses your OpenAI/ChatGPT login directly (no catalog); fcc-codex and fcc-claude can use the proxy catalog
  const list = e === "claude" ? ST.claude_models : e === "fcc-claude" ? [...ST.claude_models, ...ST.codex_models] : e === "fcc-codex" ? ST.codex_models
    : e === "hf" ? ST.hf_models : e === "local" ? (ST.local_llm.models || []) : [];
  $("models").innerHTML = list.map(m => `<option value="${m}">`).join("");
}
function engineNote() {
  const e = $("engine").value;
  $("engineNote").textContent = e === "hf" ? (ST.hf_token_set ? "Hugging Face: HF_TOKEN found. The first model is the default; vision features (describe a picture, review a result) use " + ST.hf_vision_models[0] + "."
      : "Hugging Face: HF_TOKEN is not set. Create a token at huggingface.co/settings/tokens with the permission \"Make calls to Inference Providers\", add  export HF_TOKEN=...  to ~/.zshrc and restart the Studio.")
    : e === "local" ? "Local model: " + (ST.local_llm.ready ? "answering at " + ST.local_llm.url + ". Nothing leaves this computer." : ST.local_llm.reason) : "";
}
function initLocalLlm() {                                     // the box looks greyed out until the computer qualifies (see local_llm_status in studio.py)
  const L = ST.local_llm, box = $("localLlm"), label = box.closest("label");
  box.setAttribute("aria-disabled", String(!L.ready));
  label.classList.toggle("is-off", !L.ready);
  $("localLlmNote").textContent = L.ready ? `Ready: a model server answers at ${L.url} with ${L.models.length} model(s). Ticking this uses it instead of the engine above.`
    : `Not available on this computer: ${L.reason}. Click the box to see what is needed.`;
  box.checked = L.ready && $("engine").value === "local";
}
// A real disabled checkbox swallows clicks, so this one only looks disabled: clicking it explains what is needed.
function showLocalDialog() {
  let d = $("localLlmDialog");
  if (!d) { d = document.createElement("dialog"); d.id = "localLlmDialog"; d.setAttribute("aria-labelledby", "localLlmTitle"); document.body.appendChild(d); }
  const L = ST.local_llm;
  d.innerHTML = `<h2 id="localLlmTitle">Run the writer on this computer</h2>
    <p>${L.ready ? "This computer qualifies and a local model server is answering." : "This is not available yet: <b>" + escapeHtml(L.reason || "unknown") + "</b>."}</p>
    <p>The box switches on by itself when all of these are true:</p>
    <ul>
      <li><b>A capable computer:</b> a Mac with Apple Silicon (M1 or newer), or a PC with an NVIDIA GPU.</li>
      <li><b>Enough memory:</b> 16 GB or more. 16 GB runs models of about 8 to 14 billion parameters; 32 GB or more is needed for 27B-class models such as Qwen3.8-27B. This computer has ${L.memory_gb || "?"} GB.</li>
      <li><b>A local model server running</b>, any one of:
        <ul>
          <li><b>Ollama</b> (ollama.com): install it, then run <code>ollama pull &lt;model&gt;</code>. It answers on port 11434, which the Studio checks by default.</li>
          <li><b>LM Studio</b> (lmstudio.ai): download a model and turn on the Local Server (port 1234).</li>
          <li><b>llama.cpp</b>: start <code>llama-server -m &lt;model.gguf&gt;</code> (port 8080).</li>
        </ul></li>
      <li><b>The right address:</b> the Studio looks at <code>${escapeHtml(L.url)}</code>. For LM Studio or llama.cpp add, for example, <code>export LOCAL_LLM_URL=http://127.0.0.1:1234/v1/chat/completions</code> to ~/.zshrc and restart the Studio.</li>
    </ul>
    <p>Nothing leaves your computer when a local model writes the prompts. The Studio re-checks when you open the Models tab, return to this window, or press Check again.</p>
    <div class="row"><button type="button" id="localLlmCheck">Check again</button><button type="button" id="localLlmClose">Close</button></div>
    <p id="localLlmResult" class="warn" role="status" aria-live="polite"></p>`;
  $("localLlmClose").onclick = () => d.close();
  $("localLlmCheck").onclick = async () => { await refreshLocalLlm(true); $("localLlmResult").textContent = ST.local_llm.ready ? "Ready: the box is now switched on." : "Still not available: " + ST.local_llm.reason + "."; };
  if (typeof d.showModal === "function") d.showModal(); else d.setAttribute("open", "");
}
// Ask the server again whether the computer and a model server qualify, and switch the box (and the engine choice) on or off to match.
async function refreshLocalLlm(force = false) {
  if (!ST) return;                                            // the page has not loaded its data yet (the saved tab is clicked at start-up)
  let L;
  try { L = await api("/api/local_llm" + (force ? "?fresh=1" : "")); } catch (e) { return; }
  if (!ST) return;
  const was = ST.local_llm && ST.local_llm.ready;
  ST.local_llm = L; ST.tools.local = L.ready;
  initLocalLlm();
  if (L.ready !== was) { applyConstraints(); engineNote(); if ($("engine").value === "local") fillModels(); }
}
$("localLlm").addEventListener("click", e => { if (ST && !ST.local_llm.ready) { e.preventDefault(); showLocalDialog(); } });
document.querySelector('[data-tab="models"]').addEventListener("click", () => refreshLocalLlm(false));
window.addEventListener("focus", () => refreshLocalLlm(false));
setInterval(() => { if (!document.hidden && ST && !ST.local_llm.ready) refreshLocalLlm(false); }, 60000);
function engineChanged() {
  fillModels();
  $("cmodel").value = $("engine").value === "claude" ? "sonnet" : $("engine").value === "hf" ? ST.hf_models[0] : $("engine").value === "local" ? ((ST.local_llm.models || [])[0] || "") : "";
  $("cmodel").placeholder = $("engine").value === "claude" ? "" : "blank = the tool's default";
  $("localLlm").checked = ST.local_llm.ready && $("engine").value === "local";
  engineNote();
}
let engineBeforeLocal = "claude";
$("localLlm").addEventListener("change", () => {
  if ($("localLlm").checked) { engineBeforeLocal = $("engine").value === "local" ? engineBeforeLocal : $("engine").value; $("engine").value = "local"; }
  else if ($("engine").value === "local") $("engine").value = engineBeforeLocal;
  engineChanged();
});
$("engine").onchange = engineChanged;
$("proj").onchange = () => { renderProject(true); loadGallery(); resetFilm(); populateNewSceneChapters(); loadGlobalParams($("proj").value); };
$("newSceneSeries").onchange = populateNewSceneChapters;
document.querySelectorAll("input[name=mode]").forEach(e => e.addEventListener("change", setMode));
["vmodels", "imodels"].forEach(id => $(id).addEventListener("change", updatePromptModels));
setupSuggest($("pset"), () => (typeof ST !== "undefined" && ST ? ST.promptsets : []).map(x => x.slug));
$("bCleanup").onclick = runCleanup; $("bKaggleCleanup").onclick = runKaggleCleanup; $("bImport").onclick = runImport; $("bImportStop").onclick = importStop; ["s_keyframes", "s_video", "s_audio", "s_merge", "s_mix", "proj"].forEach(id => $(id).addEventListener("change", updateMSummary)); updateMSummary(); $("pGenerate").onclick = pGenerate; $("pStop").onclick = pStop; $("bPGallery").onclick = loadPGallery; ["svc", "gpu", "kuser"].forEach(n => document.querySelectorAll(`[name=${n}], #${n}`).forEach(e => e.addEventListener("change", updatePRunsOn))); updatePRunsOn(); $("bExpand").onclick = expandIdea; $("bGallery").onclick = loadGallery; $("pset").addEventListener("change", () => { loadGallery(); resetFilm(); }); $("bPreview").onclick = preview; $("bRun").onclick = run;
$("bEstimate").onclick = estimate;
$("bFilmLoad").onclick = () => loadFilm(false); $("bMakeFilm").onclick = () => loadFilm(true); $("bFilmAll").onclick = () => tickAll(true); $("bFilmNone").onclick = () => tickAll(false);
$("bFilmMake").onclick = makeFilm;
$("bUpscale").addEventListener("click", async () => {      // the ticked rows' range of the chosen video folder, enlarged on Kaggle or this computer
  const rows = filmSelection().map(r => r.n);
  if (!film || !rows.length) { $("filmmsg").textContent = "load the files and tick the clips to upscale"; $("filmmsg").className = "err"; return; }
  const svc = radio("svc"), key = $("fupmodel").value, u = (ST.upscale_models || {})[key];
  if (!u) { $("filmmsg").textContent = "choose an upscaler"; $("filmmsg").className = "err"; return; }
  if (svc !== "kaggle" && svc !== "computer") { $("filmmsg").textContent = "upscaling runs on Kaggle or This computer: choose one in the Models tab"; $("filmmsg").className = "err"; return; }
  const why = upscaleWhy(key);
  if (why) { $("filmmsg").textContent = `${u.label}: ${why}`; $("filmmsg").className = "err"; return; }
  const src = $("fvideo").value, start = Math.min(...rows), end = Math.max(...rows);
  const out = `${src}_${key.replace(/^upscale_/, "")}`;
  const where = svc === "computer" ? "this computer" : "Kaggle";
  if (!confirm(`Upscale rows ${start}-${end} of ${src} 2x with ${u.label} on ${where}?\n\nGPU memory: ${u.memory}.\n\nThe bigger clips come back as ${out}, offered under "Video clips from".`)) return;
  try {
    await api("/api/upscale", { project: film.proj, source: src, start, end, model: key, service: svc, gpu: $("gpu").value, kaggle_user: $("kuser").value.trim() });
    $("filmmsg").textContent = "upscaling started: see the log"; $("filmmsg").className = "warn";
    since = 0; $("log").textContent = ""; building = true; poll();
  } catch (e) { $("filmmsg").textContent = e.message; $("filmmsg").className = "err"; }
});
$("bLipsync").addEventListener("click", async () => {      // comes back as a new video folder, like the upscalers
  const rows = filmSelection().map(r => r.n), svc = radio("svc");
  if (!film || !rows.length) { $("filmmsg").textContent = "load the files and tick the clips to lip-sync"; $("filmmsg").className = "err"; return; }
  if (svc !== "kaggle" && svc !== "computer") { $("filmmsg").textContent = "lip-sync runs on Kaggle or This computer: choose one in the Models tab"; $("filmmsg").className = "err"; return; }
  const src = $("fvideo").value, start = Math.min(...rows), end = Math.max(...rows);
  if (!confirm(`Lip-sync rows ${start}-${end} of ${src} to their Kokoro narration on ${svc === "computer" ? "this computer" : "Kaggle"}?\n\nThe first run downloads about 5 GB and takes longer. Best on close-ups: a small face has little mouth to redraw.\n\nThe clips come back as ${src}_lipsync, offered under Video source.`)) return;
  try {
    await api("/api/upscale", { project: film.proj, source: src, start, end, model: "upscale_lipsync", service: svc, gpu: $("gpu").value, kaggle_user: $("kuser").value.trim() });
    $("filmmsg").textContent = "lip-sync started: see the log"; $("filmmsg").className = "warn";
    since = 0; $("log").textContent = ""; building = true; poll();
  } catch (e) { $("filmmsg").textContent = e.message; $("filmmsg").className = "err"; }
});
$("bDirSend").onclick = dirSend;
$("bDirClear").onclick = dirClear;
$("bDirFollowup").onclick = dirFollowup;
// Allow Enter key in dirNotes to send (Shift+Enter for newline)
$("dirNotes").addEventListener("keydown", e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); dirSend(); } });
$("dirFollowup").addEventListener("keydown", e => { if (e.key === "Enter") { e.preventDefault(); dirFollowup(); } });

$("fvideo").onchange = () => { chooseFilmAudio(); renderFilmTable(); };
for (const [, id] of FILM_KINDS) $(id).onchange = renderFilmTable; $("bRuns").onclick = () => loadRuns(false); $("bFetch").onclick = () => loadRuns(true); $("bStop").onclick = () => api("/api/stop", {});
try { $("kuser").value = localStorage.getItem("kaggle_user") || ""; $("engine").value = localStorage.getItem("engine") || "claude"; $("cmodel").value = localStorage.getItem("claude_model") ?? "sonnet"; } catch (e) {}
$("kuser").addEventListener("change", () => { try { localStorage.setItem("kaggle_user", $("kuser").value); } catch (e) {} });
$("cmodel").addEventListener("change", () => { try { localStorage.setItem("claude_model", $("cmodel").value); } catch (e) {} });
$("engine").addEventListener("change", () => { try { localStorage.setItem("engine", $("engine").value); localStorage.setItem("claude_model", $("cmodel").value); } catch (e) {} });

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

// ---- Character Management API ----
let charCurrentSeries = "";
let charCurrentCharacter = "";

async function loadCharSeries() {
  try {
    const j = await api("/api/characters?action=list_series");
    const series = j.series || [];
    $("charSeries").innerHTML = series.map(s => `<option value="${s}">${s}</option>`).join("");
    // Also populate the New Scene series dropdown
    $("newSceneSeries").innerHTML = series.map(s => `<option value="${s}">${s}</option>`).join("");
    $("castSeries").innerHTML = `<option value="">(none)</option>` + series.map(s => `<option value="${s}">${s}</option>`).join("");
    if (series.length) {
      $("charSeries").value = series[0];
      charCurrentSeries = series[0];
      await loadCharList();
    }
    updateCharButtons();
  } catch (e) {
    showCharStatus(e.message, true);
  }
}

async function loadCharList() {
  const series = $("charSeries").value;
  if (!series) {
    $("charList").innerHTML = "";
    updateCharButtons();
    return;
  }
  charCurrentSeries = series;
  try {
    const j = await api(`/api/characters?action=list&series=${encodeURIComponent(series)}`);
    const chars = j.characters || [];
    $("charList").innerHTML = '<option value="">(select a character)</option>' + chars.map(c => `<option value="${c.name}">${c.name}</option>`).join("");
    populateCharTable(chars, series);
    updateCharButtons();
    await loadCharAllTokens();
  } catch (e) {
    showCharStatus(e.message, true);
  }
  // Populate newSceneChapter with chapters from current project
  populateNewSceneChapters();

}

// Populate character data-table
function populateCharTable(characters, series) {
    const tbody = $('charTableBody');
    if (!tbody) return;
    if ($('charPickAll')) $('charPickAll').checked = false;
    
    if (!characters || characters.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;color:var(--fg-muted);padding:24px">No characters in this series</td></tr>';
        return;
    }
    
    tbody.innerHTML = characters.map(c => {
        const refCount = (c.reference_images || []).length;
        const hasLora = c.lora && (c.lora.repo || c.lora.trigger_word);
        return `
            <tr data-name="${escapeHtml(c.name)}" data-act="select-char" style="cursor:pointer">
                <td><input type="checkbox" class="charPick" data-name="${escapeHtml(c.name)}" data-act="pick-char" aria-label="Send ${escapeHtml(c.name)} to the book"></td>
                <td><strong>${escapeHtml(c.name)}</strong></td>
                <td>${escapeHtml(c.archetype || '—')}</td>
                <td><span class="badge ${refCount > 0 ? 'badge--success' : 'badge--neutral'}">${refCount}</span></td>
                <td><span class="badge ${hasLora ? 'badge--success' : 'badge--neutral'}">${hasLora ? '✓' : '—'}</span></td>
                <td>
                    <button class="btn btn-icon btn-ghost" data-act="edit-char" data-series="${escapeHtml(series)}" data-name="${escapeHtml(c.name)}" aria-label="Edit ${escapeHtml(c.name)}">✎</button>
                    <button class="btn btn-icon btn-ghost btn-danger" data-act="delete-char" data-series="${escapeHtml(series)}" data-name="${escapeHtml(c.name)}" aria-label="Delete ${escapeHtml(c.name)}">🗑</button>
                </td>
            </tr>
        `;
    }).join('');
}

function selectCharInTable(name) {
    // Update the select dropdown to match
    const select = $('charList');
    if (select) {
        for (let i = 0; i < select.options.length; i++) {
            if (select.options[i].value === name) {
                select.selectedIndex = i;
                select.dispatchEvent(new Event('change'));
                break;
            }
        }
    }
    // Highlight the row
    document.querySelectorAll('#charTableBody tr').forEach(tr => tr.style.background = '');
    const row = document.querySelector('#charTableBody tr[data-name="' + name.replace(/"/g, '\"') + '"]');
    if (row) row.style.background = 'var(--accent-light)';
}

function deleteCharacterConfirm(series, name) {
    if (confirm('Delete character "' + name + '" from series "' + series + '"? This cannot be undone.')) {
        // Call the existing delete function logic
        api('/api/characters', { action: 'delete', series: series, name: name }).then(() => {
            showToast('Character deleted', 'success');
            loadCharList();
            loadCharAllTokens();
        }).catch(e => showToast('Failed to delete: ' + e.message, 'error'));
    }
}


function populateNewSceneChapters() {
  const p = cur();
  if (!p || !p.chapters) {
    $("newSceneChapter").innerHTML = '<option value="">(no project selected or no chapters yet)</option>';
    return;
  }
  const chapterOptions = Array.from({ length: p.chapters }, (_, i) => i + 1)
    .map(ch => `<option value="${ch}">Chapter ${ch}</option>`).join("");
  $("newSceneChapter").innerHTML = '<option value="">(select a chapter)</option>' + chapterOptions;
}

async function loadCharAllTokens() {
  const series = $("charSeries").value;
  if (!series) return;
  try {
    const j = await api(`/api/characters?action=tokens&series=${encodeURIComponent(series)}`);
    if (j.tokens) {
      $("charAllTokens").textContent = j.tokens;
    } else {
      $("charAllTokens").innerHTML = '<span class="warn">No characters in this series yet.</span>';
    }
    $("bCharCopyAll").disabled = !j.tokens;
    $("bCharRefreshAll").disabled = false;
  } catch (e) {
    $("charAllTokens").innerHTML = `<span class="err">${e.message}</span>`;
  }
}


function updateRefDir() {
  const series = $("charSeries").value;
  const name = $("charName").value;
  if (series && name) {
    // This is the path structure used by character_tokens.py
    const refDir = `projects/characters/${series}/references/${charSlug(name)}/`;
    $("charRefDir").textContent = refDir;
    $("bCharOpenRefDir").disabled = false;
  } else {
    $("charRefDir").textContent = "";
    $("bCharOpenRefDir").disabled = true;
  }
}

function getCharFormData() {
  // Collect physical traits from dropdowns/inputs
  const physical_traits = {};
  const physicalFields = ["age", "height", "build", "skin", "hair", "facial_hair", "eyes", "expression", "ethnicity", "distinguishing_features"];
  for (const field of physicalFields) {
    const el = $(`trait_${field}`);
    if (el && el.value) physical_traits[field] = el.value;
  }

  // Collect LoRA info from dropdowns/inputs
  const lora = {};
  const loraFields = ["repo", "trigger_word", "base_model", "trained"];
  for (const field of loraFields) {
    const el = $(`lora_${field}`);
    if (el) {
      if (el.type === "checkbox") {
        lora[field] = el.checked;
      } else if (el.value) {
        lora[field] = el.value;
      }
    }
  }
  // Default LoRA values if not set
  if (!lora.trigger_word && $("charName").value) {
    lora.trigger_word = $("charName").value.toLowerCase().replace(/[^a-z0-9]/g, "_") + "_token";
  }
  if (!lora.base_model) lora.base_model = "LTX-Video";
  if (lora.trained === undefined) lora.trained = false;
  if (!lora.repo) lora.repo = "";

  return {
    name: $("charName").value.trim(),
    series: $("charSeries").value,
    archetype: $("charArchetype").value || undefined,
    visual_token: $("charVisualToken").value.trim(),
    trigger_words: $("charTriggerWords").value.split(",").map(s => s.trim()).filter(s => s),
    physical_traits: physical_traits,
    clothing: $("charClothing").value.trim(),
    voice: $("charVoice").value.trim(),
    lora: lora,
    reference_images: $("charRefImages").value.split("\n").map(s => s.trim()).filter(s => s),
    consistency_notes: $("charConsistency").value.trim(),
    stages: textToStages($("charStages").value)
  };
}

function updatePromptPreview() {
  const previewEl = $("charPromptPreview");
  if (!previewEl) return;

  // Read global parameters directly from saved localStorage (the saved file)
  const globalPositives = localStorage.getItem("globalPositives") || "";
  const globalNegatives = localStorage.getItem("globalNegatives") || "";

  // Build the base prompt parts
  const parts = [];

  // Visual token
  const visualToken = $("charVisualToken").value.trim();
  if (visualToken) parts.push(visualToken);

  // Physical traits from dropdowns/inputs
  const physicalFields = ["age", "height", "build", "skin", "hair", "facial_hair", "eyes", "expression", "ethnicity", "distinguishing_features"];
  const physicalTraits = {};
  for (const field of physicalFields) {
    const el = $(`trait_${field}`);
    if (el && el.value) physicalTraits[field] = el.value;
  }
  if (Object.keys(physicalTraits).length) {
    const desc = Object.entries(physicalTraits).map(([k, v]) => `${k}: ${v}`).join(", ");
    if (desc) parts.push(desc);
  }

  // Clothing
  const clothing = $("charClothing").value.trim();
  if (clothing) parts.push(`wearing ${clothing}`);

  // Consistency notes
  const consistency = $("charConsistency").value.trim();
  if (consistency) parts.push(consistency);

  // Global positives (from saved file)
  if (globalPositives) parts.push(globalPositives);


  const basePrompt = parts.join(", ");

  // Build negative prompt with global negatives (from saved file)
  const negativePrompt = globalNegatives;

  // Get view text from text input (not dropdown) and add to prompt if provided
  const viewText = $("charGenView") ? $("charGenView").value.trim() : "";
  const fullPrompt = viewText ? basePrompt + ", " + viewText : basePrompt;

  // Show just the exact prompt that will be sent
  previewEl.textContent = fullPrompt;
}

let charSavedAt = 0;
async function saveCharacter() {
  const data = getCharFormData();
  if (!data) return;
  if (!data.name) {
    showCharStatus("Character name is required", true);
    return;
  }
  if (!data.series) {
    showCharStatus("Series is required", true);
    return;
  }
  showCharStatus("Saving character…");
  $("bCharSave").disabled = true;
  try {
    const j = await api("/api/characters", { action: "save", character: data });
    showCharStatus("Character saved: " + j.path);
    charSavedAt = Date.now();             // reloading the character fires the archetype loader; its message must not hide this one
    await loadCharList();
    await loadCharAllTokens();
    await loadCharacter(data.series, data.name);
  } catch (e) {
    showCharStatus(e.message, true);
  }
  $("bCharSave").disabled = false;
}

async function deleteCharacter() {
  const series = $("charSeries").value;
  const name = $("charName").value;
  if (!series || !name) return;
  if (!confirm(`Delete character "${name}" from series "${series}"?`)) return;
  showCharStatus("Deleting character…");
  $("bCharDelete").disabled = true;
  try {
    await api("/api/characters", { action: "delete", series, name });
    showCharStatus("Character deleted");
    $("charName").value = "";
    $("charVisualToken").value = "";
    $("charTriggerWords").value = "";
    // Clear physical traits fields
    const physicalFields = ["age", "height", "build", "skin", "hair", "facial_hair", "eyes", "expression", "ethnicity", "distinguishing_features"];
    for (const field of physicalFields) {
      const el = $(`trait_${field}`);
      if (el) el.value = "";
    }
    $("charClothing").value = "";
    $("charVoice").value = "";
    // Clear LoRA fields
    const loraFields = ["repo", "trigger_word", "base_model", "trained"];
    for (const field of loraFields) {
      const el = $(`lora_${field}`);
      if (el) {
        if (el.type === "checkbox") el.checked = false;
        else el.value = "";
      }
    }
    $("charRefImages").value = "";
    $("charConsistency").value = "";
    $("charStages").value = "";
    charCurrentCharacter = "";
    await loadCharList();
    await loadCharAllTokens();
    updateRefDir();
  } catch (e) {
    showCharStatus(e.message, true);
  }
  $("bCharDelete").disabled = false;
}

async function newSeries() {
  const name = prompt("Enter new series name (lowercase, underscores):", "mcnally");
  if (!name) return;
  // Just select it - it will be created when first character is saved
  const options = [...$("charSeries").options].map(o => o.value);
  if (!options.includes(name)) {
    const opt = document.createElement("option");
    opt.value = name;
    opt.textContent = name;
    $("charSeries").appendChild(opt);
  }
  $("charSeries").value = name;
  await loadCharList();
}

async function newCharacter() {
  const series = $("charSeries").value;
  if (!series) {
    showCharStatus("Select a series first", true);
    return;
  }
  const name = prompt("Enter new character name:", "");
  if (!name) return;
  // Clear form for new character
  $("charName").value = name;
  $("charVisualToken").value = "";
  $("charTriggerWords").value = "";
  // Clear physical traits fields
  const physicalFields = ["age", "height", "build", "skin", "hair", "facial_hair", "eyes", "expression", "ethnicity", "distinguishing_features"];
  for (const field of physicalFields) {
    const el = $(`trait_${field}`);
    if (el) el.value = "";
  }
  $("charClothing").value = "";
  $("charVoice").value = "";
  // Clear and set default LoRA fields
  const loraFields = ["repo", "trigger_word", "base_model", "trained"];
  for (const field of loraFields) {
    const el = $(`lora_${field}`);
    if (el) {
      if (el.type === "checkbox") el.checked = false;
      else el.value = "";
    }
  }
  // Set default LoRA values
  const triggerEl = $("lora_trigger_word");
  if (triggerEl) triggerEl.value = name.toLowerCase().replace(/[^a-z0-9]/g, "_") + "_token";
  const baseModelEl = $("lora_base_model");
  if (baseModelEl) baseModelEl.value = "LTX-Video";
  const trainedEl = $("lora_trained");
  if (trainedEl && trainedEl.type === "checkbox") trainedEl.checked = false;
  $("charRefImages").value = "";
  $("charConsistency").value = "";
  $("charStages").value = "";
  charCurrentCharacter = name;
  updateRefDir();
  updateCharButtons();
  showCharStatus("Fill in the details and click Save Character");
}

async function syncFromProject() {
  const project = $("proj").value;
  const series = $("charSeries").value;
  if (!project || !series) {
    showCharStatus("Select a project and series first", true);
    return;
  }
  const overwrite = $("charSyncOverwrite").checked;
  $("bCharSync").disabled = true;
  try {
    if (overwrite) {                                   // count first, then ask: overwriting cannot be undone
      showCharStatus("Checking what would change…");
      const plan = await api("/api/characters", { action: "sync", project, series, overwrite: true, dry_run: true });
      if (!plan.updated) {
        showCharStatus(plan.added ? `Nothing to overwrite; ${plan.added} new character(s) will be added.` : `Nothing to sync: the continuity book's ${plan.total} character(s) are not in "${series}" yet or have no changes.`);
        if (!plan.added) { updateCharButtons(); return; }
      } else if (!confirm(`Update ${plan.updated} existing character(s) in "${series}" from ${project}'s continuity book` + (plan.added ? ` and add ${plan.added} new one(s)` : "") + `?\n\nThe continuity book's visual token, voice, clothing, traits and notes replace yours (only where the continuity has a value). Reference images, LoRA info and trigger words you added are kept.\n\nThis cannot be undone.`)) {
        showCharStatus("Sync cancelled; nothing was changed.");
        updateCharButtons();
        return;
      }
    }
    showCharStatus("Syncing from continuity book…");
    const j = await api("/api/characters", { action: "sync", project, series, overwrite });
    const parts = [];
    if (j.added) parts.push(`added ${j.added}`);
    if (j.updated) parts.push(`updated ${j.updated}`);
    if (j.skipped) parts.push(`${j.skipped} already in the series, left unchanged`);
    showCharStatus(parts.length ? `From ${project}'s continuity book: ${parts.join(", ")}.` : `Nothing to sync: ${project}'s continuity book has no characters.`);
    await loadCharList();
    await loadCharAllTokens();
  } catch (e) {
    showCharStatus(e.message, true);
  }
  updateCharButtons();
}

async function sendToBook() {
  const project = $("proj").value, series = $("charSeries").value;
  const names = [...document.querySelectorAll("#charTableBody .charPick:checked")].map(e => e.dataset.name);
  if (!project || !series || !names.length) { showCharStatus("Pick a book and a series, and tick at least one character", true); return; }
  $("bCharSend").disabled = true;
  try {
    showCharStatus("Checking what would change…");
    const plan = await api("/api/characters", { action: "send_to_book", project, series, names, dry_run: true });
    const miss = plan.missing.length ? ` (${plan.missing.join(", ")} cannot be sent: no visual token)` : "";
    if (!plan.updated && !plan.added) { showCharStatus(`Nothing to send: ${project}'s continuity book already matches${miss}.`); updateCharButtons(); return; }
    const what = [plan.updated ? `update ${plan.updated} character(s)` : "", plan.added ? `add ${plan.added} new one(s)` : ""].filter(Boolean).join(" and ");
    if (!confirm(`In ${project}'s continuity book, ${what} using the ${series} series' visual token and voice.\n\nChapters that are already written keep the old wording; chapters written afterwards use the new one.${miss}\n\nContinue?`)) {
      showCharStatus("Cancelled; the book was not changed."); updateCharButtons(); return;
    }
    const j = await api("/api/characters", { action: "send_to_book", project, series, names });
    showCharStatus(`Sent to ${project}: ${[j.updated ? `updated ${j.updated}` : "", j.added ? `added ${j.added}` : "", j.unchanged ? `${j.unchanged} already matched` : ""].filter(Boolean).join(", ")}${miss}.`);
  } catch (e) {
    showCharStatus(e.message, true);
  }
  updateCharButtons();
}

function copyAllTokens() {
  const text = $("charAllTokens").textContent;
  if (!text) return;
  navigator.clipboard.writeText(text).then(() => {
    showCharStatus("Copied to clipboard");
  }).catch(() => {
    showCharStatus("Failed to copy", true);
  });
}

// "Generate Prompt": show the current prompt in the Prompt Preview window; if there is nothing to build it from, say so there.
function showCharacterPrompt() {
  const preview = $("charPromptPreview");
  const hasName = !!$("charName").value.trim(), hasToken = !!$("charVisualToken").value.trim(), picked = !!$("charList").value;
  if (!$("charSeries").value) {
    preview.textContent = 'No series selected. Pick a Series above (or click New Series), then select a character under "Characters in this series".';
    return;
  }
  if (!picked && !hasName && !hasToken) {
    preview.textContent = 'No character selected. Choose one under "Characters in this series", or click New Character and enter a Character Name and Visual Token, then click Generate Prompt again.';
    return;
  }
  updatePromptPreview();          // shows the exact prompt that would be sent
  copyCharacterPrompt();          // and copies it to the clipboard, as before
}

function copyCharacterPrompt() {
  // Build the prompt (same logic as updatePromptPreview)
  // Read global parameters directly from saved localStorage (the saved file)
  const globalPositives = localStorage.getItem("globalPositives") || "";
  const globalNegatives = localStorage.getItem("globalNegatives") || "";

  const parts = [];

  const visualToken = $("charVisualToken").value.trim();
  if (visualToken) parts.push(visualToken);

  const physicalFields = ["age", "height", "build", "skin", "hair", "facial_hair", "eyes", "expression", "ethnicity", "distinguishing_features"];
  const physicalTraits = {};
  for (const field of physicalFields) {
    const el = $(`trait_${field}`);
    if (el && el.value) physicalTraits[field] = el.value;
  }
  if (Object.keys(physicalTraits).length) {
    const desc = Object.entries(physicalTraits).map(([k, v]) => `${k}: ${v}`).join(", ");
    if (desc) parts.push(desc);
  }

  const clothing = $("charClothing").value.trim();
  if (clothing) parts.push(`wearing ${clothing}`);

  const consistency = $("charConsistency").value.trim();
  if (consistency) parts.push(consistency);

  // Global positives (from saved file)
  if (globalPositives) parts.push(globalPositives);


  const basePrompt = parts.join(", ");

  // Get view text from text input (not dropdown) and add to prompt if provided
  const viewText = $("charGenView") ? $("charGenView").value.trim() : "";
  const fullPrompt = viewText ? basePrompt + ", " + viewText : basePrompt;

  // Copy to clipboard
  navigator.clipboard.writeText(fullPrompt).then(() => {
    showCharStatus("Prompt copied to clipboard");
  }).catch(() => {
    showCharStatus("Failed to copy prompt", true);
  });
}

async function openRefDir() {
  try {
    await api("/api/open_reference_folder", { series: $("charSeries").value, name: $("charName").value });
    showCharStatus("Reference folder opened");
  } catch (e) { showCharStatus(e.message, true); }
}

// The pictures of this character, with the one that stands for its face marked.
async function loadCharRefs() {
  const box = $("charRefThumbs"), series = $("charSeries").value, name = $("charName").value.trim();
  const klein = checked("imodel").includes("flux2_klein_4b");
  $("charKeepFaceNote").textContent = klein ? "Uses FLUX.2 klein, even if other image models are ticked." : `Only FLUX.2 klein can take a picture and it is not ticked on the Models tab, so ${checked("imodel")[0] || "the ticked model"} will work from the words alone.`;
  if (!series || !name) { box.innerHTML = ""; return; }
  try {
    const r = await api(`/api/characters?action=references&series=${encodeURIComponent(series)}&name=${encodeURIComponent(name)}`);
    const q = t => String(t).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
    const shown = r.pictures.filter(p => p.file);
    const lost = r.pictures.filter(p => !p.exists).length;
    box.innerHTML = shown.map(p => `<figure style="margin:0;width:112px;font-size:11px"><img src="/thumb/${p.file.split("/").map(encodeURIComponent).join("/")}?t=${TOKEN}" alt="Reference picture ${q(p.name)}" loading="lazy" width="112" height="112" style="object-fit:cover;border-radius:6px;${p.used ? "outline:3px solid var(--brand)" : ""}"><figcaption style="word-break:break-all">${q(p.name)}<br>${p.used ? "<b>This is the face</b>" : `<button type="button" class="btn btn-secondary" data-useref="${q(p.path)}" style="padding:2px 6px;font-size:11px">Use this face</button>`}</figcaption></figure>`).join("")
      + (shown.length ? "" : '<span class="warn">No pictures yet: generate one, or put one in the reference folder.</span>')
      + (lost ? `<span class="warn" style="width:100%">${lost} listed file(s) no longer exist and are skipped.</span>` : "");
  } catch (e) { box.innerHTML = `<span class="err">${q0(e.message)}</span>`; }
}
const q0 = t => String(t).replace(/</g, "&lt;");
function faceBadge(c, esc) {
  const f = c.face;
  if (!f) return "";
  const text = { ok: "✓ face matches", different: "⚠ may be someone else: look at this one", no_face: "no face found", skipped: "no reference picture to compare" }[f.status] || f.status;
  const scores = Object.entries(f.scores || {}).map(([k, v]) => `${k} ${v}`).join(", ");
  return `<span class="pz-cat" style="${f.status === "different" ? "color:var(--danger)" : ""}" title="${esc(scores)}">${esc(text)}</span>`;

}

// View definitions - shared between generation and preview
const CHAR_VIEWS = {
  face: { name: "Face (close-up)", add: "extreme close-up portrait, face filling frame, detailed eyes, skin texture, photorealistic" },
  eyes: { name: "Eyes (macro)", add: "macro close-up of eyes only, detailed iris, eyelashes, catch lights, photorealistic" },
  back_head: { name: "Back of Head", add: "back of head view, hair detail, neck, ear profile, photorealistic" },
  front_body: { name: "Front Whole Body", add: "full body front view, standing pose, head to toe, accurate proportions, photorealistic" },
  rear_body: { name: "Rear Whole Body", add: "full body rear view, standing pose, back of head to heels, accurate proportions, photorealistic" }
};

let charGenBusy = false;
async function generateCharacterImage() {
  const series = $("charSeries").value;
  const name = $("charList").value;
  if (!series || !name) {
    clearCharGenLog();
    logCharGen(!series ? "Select a Series first." : 'Select a character first: choose one under "Characters in this series" (or click New Character, fill in the form and Save Character), then click Generate.', true);
    return;
  }

  // Check which generation steps are enabled
  const genImages = $("charGenImages").checked;
  const genVoice = $("charGenVoice").checked;
  const genLora = $("charGenLora").checked;
  const genMovie = $("charGenMovie").checked;

  if (!genImages && !genVoice && !genLora && !genMovie) {
    logCharGen("Select at least one generation step", true);
    return;
  }

  // Check overwrite options
  const overwriteToken = $("charOverwriteToken").checked;
  const overwriteRefs = $("charOverwriteRefs").checked;

  const warnings = [];
  if (overwriteToken) warnings.push("• The visual token will be REPLACED with the generated prompts");
  if (overwriteRefs) warnings.push("• The new picture will be ADDED at the end of the Reference Images list (nothing is replaced)");
  if (genImages) {
    const viewText = $("charGenView") ? $("charGenView").value.trim() : "";
    const viewLabel = viewText || "custom view";
    warnings.push(`• Character Images: generates ${$("charSheet").checked ? "5 pictures (character sheet)" : "1 picture"} from the words on this page (view: ${viewLabel})${$("charKeepFace").checked ? ", starting from the face marked below if this model can use it" : ", without using any reference picture"}.`);
    if (!overwriteRefs) warnings.push("• The picture is saved in the reference folder and shown below, but not added to the Reference Images list");
  }
  if (genVoice) warnings.push("• Voice: generates voice samples (placeholder)");
  if (genLora) warnings.push("• LoRA: trains LoRA for character (placeholder)");
  if (genMovie) warnings.push("• Character Movie: generates short movie with voice (placeholder)");

  if (warnings.length && !confirm(`⚠️ WARNING: This will:\n\n${warnings.join("\n")}\n\nCharacter: ${name}\nSeries: ${series}\n\nAre you sure you want to continue?`)) {
    return;
  }

  // Delete previous notebooks before generating
  await deleteNotebooks();

  // Build the base prompt from the character data
  const visualToken = $("charVisualToken").value.trim();
  // Build physicalTraits from individual dropdown/input fields
  const physicalTraits = {};
  const physicalFields = ["age", "height", "build", "skin", "hair", "facial_hair", "eyes", "expression", "ethnicity", "distinguishing_features"];
  for (const field of physicalFields) {
    const el = $(`trait_${field}`);
    if (el && el.value) physicalTraits[field] = el.value;
  }
  const clothing = $("charClothing").value.trim();
  const consistency = $("charConsistency").value.trim();

  // Read global parameters directly from saved localStorage (the saved file)
  const globalPositives = localStorage.getItem("globalPositives") || "";
  const globalNegatives = localStorage.getItem("globalNegatives") || "";

  // Build base prompt (without angle-specific additions)
  const baseParts = [];
  if (visualToken) baseParts.push(visualToken);
  if (Object.keys(physicalTraits).length) {
    const desc = Object.entries(physicalTraits).filter(([_, v]) => v).map(([k, v]) => `${k}: ${v}`).join(", ");
    if (desc) baseParts.push(desc);
  }
  if (clothing) baseParts.push(`wearing ${clothing}`);
  if (consistency) baseParts.push(consistency);
  if (globalPositives) baseParts.push(globalPositives);

  const basePrompt = baseParts.join(", ");

  // Get view text from text input and add it to the prompt if provided
  const viewText = $("charGenView") ? $("charGenView").value.trim() : "";
  const fullPrompt = viewText ? basePrompt + ", " + viewText : basePrompt;

  const negative = globalNegatives;

  // One prompt, or one per view for a character sheet
  const sheet = $("charSheet").checked;
  const allPrompts = sheet ? CHAR_SHEET_VIEWS.map(v => `${fullPrompt}, ${v}`) : [fullPrompt];
  charGenReference = $("charKeepFace").checked ? { series, name } : { };   // the server decides whether this model and service can use a picture
  if (genImages && !fullPrompt.trim()) { logCharGen("Nothing to draw yet: fill in the character fields or the view box", true); return; }

  // Get generation parameters from the "Where to run" section
  const service = document.querySelector('input[name="svc"]:checked')?.value || "kaggle";
  const gpu = $("gpu").value;

  if (!gpu && (genImages || genVoice || genLora || genMovie)) {
    logCharGen("Select a GPU first in the 'Where to run' section", true);
    return;
  }

  // Use a prompt set name based on character (lowercase, underscores only)
  const setName = `char_${name.toLowerCase().replace(/[^a-z0-9]/g, "_")}`;

  clearCharGenLog();
  logCharGen(`Starting character generation for: ${name} (${series})`);
  if (genImages) {
    const viewLabel = viewText || "custom view";
    logCharGen(`→ Character Images: ${allPrompts.length} picture(s) (view: ${viewLabel}). ${$("charKeepFace").checked && checked("imodel").includes("flux2_klein_4b") ? "Starting from the face marked below." : "From the words alone."}`);
  }
  if (genVoice) logCharGen(`→ Voice Generation`);
  if (genLora) logCharGen(`→ LoRA Training`);
  if (genMovie) logCharGen(`→ Character Movie`);
  if (overwriteToken) logCharGen("⚠ Visual token will be overwritten");
  if (overwriteRefs) logCharGen("New pictures go at the end of the Reference Images list; the marked face stays until you press Use this face.");
  charGenBusy = true; $("bCharGenerate").disabled = true;

  try {
    // Step 1: Character Images (text-to-image)
    if (genImages) {
      await generateCharacterImages(setName, allPrompts, series, name, overwriteToken, overwriteRefs, service, gpu, negative);
    }

    // Step 2: Voice Generation (placeholder)
    if (genVoice) {
      logCharGen("\n🎤 Voice Generation - Not yet implemented");
      logCharGen("   This will generate voice samples using Kokoro TTS");
    }

    // Step 3: LoRA Training (placeholder)
    if (genLora) {
      logCharGen("\n🔧 LoRA Training - Not yet implemented");
      logCharGen("   This will train a LoRA on the reference images");
    }

    // Step 4: Character Movie (placeholder)
    if (genMovie) {
      logCharGen("\n🎬 Character Movie - Not yet implemented");
      logCharGen("   This will generate a short character movie with voice");
    }

    // Reload the character list and form if either was updated
    if (overwriteToken || overwriteRefs) {
      await loadCharList();
      await loadCharacter(series, name);
    }
  } catch (e) {
    logCharGen(`✗ Error: ${e.message}`, true);
  }
  charGenBusy = false; $("bCharGenerate").disabled = false;
  loadCharRefs();
}

async function generateCharacterImages(setName, allPrompts, series, name, overwriteToken, overwriteRefs, service, gpu, negative) {
  logCharGen("\n🖼️ Generating character image (text-to-image)...");

  // Use selected image model from "Where to run" section
  const selectedImageModels = checked("imodel");
  if (selectedImageModels.length === 0) {
    logCharGen("✗ No image model selected in 'Where to run' section", true);
    return;
  }
  // Keeping a face needs a model that takes a picture, so it goes first if it is ticked at all
  const imageModel = charGenReference.name && selectedImageModels.includes("flux2_klein_4b") ? "flux2_klein_4b" : selectedImageModels[0];
  logCharGen(`  Using image model: ${imageModel}`);
  const kind = "image";

  // Image generation parameters (use defaults from MODEL_DEFAULTS if available)
  const defaults = ST?.MODEL_DEFAULTS?.[imageModel] || {};
  const width = defaults.width || 1024;
  const height = defaults.height || 1024;
  const steps = defaults.steps || 20;
  const guidance = defaults.guidance !== undefined ? defaults.guidance : 4.0;

  // Create plan with single prompt
  let planResult;
  try {
    planResult = await api("/api/plan", {
      mode: "prompts",
      kind: kind,
      set: setName,
      model: imageModel,
      service: service,
      gpu: gpu,
      kaggle_user: service === "kaggle" ? ($("kuser").value || "") : "",
      prompts: allPrompts.join("\n"), // Single prompt
      opts: {
        negative: negative,
        width: width,
        height: height,
        steps: steps,
        guidance: guidance,
        reference: charGenReference,
        overwrite: true  // Overwrite CSV with single row for character generation
      }
    });
  } catch (e) {
    // The server answers 400 with the reason (unknown model, GPU not allowed for this model, missing Kaggle user...). Show it.
    logCharGen(`✗ The server rejected the plan for ${imageModel}: ${e.message}`, true);
    return;
  }

  if (!planResult.steps || planResult.steps.length === 0) {
    logCharGen("✗ Failed to create image generation plan", true);
    return;
  }

  logCharGen(`✓ Plan created with ${planResult.steps.length} step(s)`);
  logCharGen("Starting image generation job...");

  // Run the generation
  await api("/api/run", {
    mode: "prompts",
    kind: kind,
    set: setName,
    model: imageModel,
    service: service,
    gpu: gpu,
    kaggle_user: service === "kaggle" ? ($("kuser").value || "") : "",
    prompts: allPrompts.join("\n"),
    opts: {
      negative: negative,
      width: width,
      height: height,
      steps: steps,
      guidance: guidance,
      reference: charGenReference,
        overwrite: true  // Overwrite CSV with single row for character generation
    }
  });

  logCharGen("✓ Image generation job started");

  // Poll for job completion and download image (the run_kaggle_model.sh script already fetches results)
  await waitForImagesAndSaveRefs(setName, imageModel, allPrompts, series, name, overwriteToken, overwriteRefs);
}

// Poll `kaggle kernels status` every 15 s; on COMPLETE download to my_downloads and list what arrived.
// Returns "COMPLETE", "ERROR", "CANCEL_ACKNOWLEDGED" or "TIMEOUT".
async function waitForKaggleAndDownload(ref, maxMinutes = 90, log = logCharGen) {
  const POLL_MS = 15000;
  const FAILED = ["ERROR", "CANCEL_ACKNOWLEDGED", "CANCELACKNOWLEDGED"];
  let last = "";
  let unknownCount = 0;
  log(`\n⏳ Checking Kaggle status of ${ref} every 15 s...`);
  for (let waited = 0; waited < maxMinutes * 60000; waited += POLL_MS) {
    let status = "UNKNOWN";
    try {
      const r = await api(`/api/kernel_status?ref=${encodeURIComponent(ref)}`);
      status = r.status;
    } catch (e) {
      log(`  ⚠ Status check failed: ${e.message}`, true);
    }
    if (status !== last) {
      log(`  Kaggle status: ${status}`);
      last = status;
    }
    if (status === "COMPLETE") break;
    if (FAILED.includes(status)) {
      log(`✗ Kaggle run ${status.toLowerCase()}. Open the notebook on Kaggle to see the error.`, true);
      return status;
    }
    // UNKNOWN right after a push is normal; give up only after ~2 minutes of it
    unknownCount = status === "UNKNOWN" ? unknownCount + 1 : 0;
    if (unknownCount >= 8) {
      log("✗ Kaggle keeps reporting an unknown status; the notebook may not have been pushed.", true);
      return "ERROR";
    }
    await new Promise(resolve => setTimeout(resolve, POLL_MS));
  }
  if (last !== "COMPLETE") {
    log(`✗ Gave up after ${maxMinutes} minutes (last status: ${last || "none"}).`, true);
    return "TIMEOUT";
  }
  log("✓ Kaggle run finished. Downloading results...");
  try {
    const out = await api("/api/kernel_output", { ref });
    if (out.files.length) {
      log(`✓ ${out.files.length} file(s) found in ${out.dir}:`);
      out.files.forEach(f => log(`    ${f}`));
    } else {
      log(`  ⚠ No files found in destination ${out.dir}${out.message ? " (" + out.message + ")" : ""}`, true);
    }
  } catch (e) {
    log(`  ⚠ Download failed: ${e.message}`, true);
  }
  return "COMPLETE";
}

async function waitForImagesAndSaveRefs(setName, model, allPrompts, series, name, overwriteToken, overwriteRefs) {
  logCharGen("⏳ Waiting for image generation to complete...");
  logCharGen("   (This may take several minutes - check job log for progress)");

  let notebookSlug = null;
  let imageStart = 1;
  let imageEnd = 1;

  const jobLines = await followJob(logCharGen, 5000);
  const pushedRefs = kaggleRefsFromLines(jobLines);   // what the run script really pushed (owner/slug)
  logCharGen("✓ Job completed!");

  // Job completed - now search the FULL log for the generation line
  // Pattern: ===== [1/1] image sdxl_turbo: rows 1-3 $ PROJECT=char_abel ... scripts/run_kaggle_model.sh image_sdxl_turbo 1 3
  logCharGen("🔍 Searching job log for generation info...");
  try {
    const logResult = await api("/api/log?since=0");
    const fullLog = logResult.lines.join("\n");

    // More flexible regex - match the key parts even if spacing varies
    const match = fullLog.match(/=====\s*\[\d+\/\d+\]\s*image\s+(\S+):\s*rows\s+(\d+)\s*-\s*(\d+).*?\$\s*PROJECT\s*=\s*(\S+).*?run_kaggle_model\.sh\s+image_\S+\s+(\d+)\s+(\d+)/s);
    if (match) {
      const logModel = match[1];
      const start = parseInt(match[2], 10);
      const end = parseInt(match[3], 10);
      const project = match[4];
      const start2 = parseInt(match[5], 10);
      const end2 = parseInt(match[6], 10);

      // Verify the numbers match
      if (start === start2 && end === end2) {
        imageStart = start;
        imageEnd = end;
        // Build notebook slug: <project>-image-<model>-<start>-<end>   (no prefix; the run script's own "kernel pushed" line is preferred)
        // project and model need underscores -> dashes
        const slugProject = project.replace(/_/g, "-");
        const slugModel = logModel.replace(/_/g, "-");
        notebookSlug = `${slugProject}-image-${slugModel}-${start}-${end}`;
        // Add owner prefix (kaggle username from input or default)
        const kaggleUser = $("kuser").value;
        if (kaggleUser) notebookSlug = `${kaggleUser}/${notebookSlug}`;
        logCharGen(`  ✓ Found notebook info from log: ${notebookSlug} (images ${imageStart}-${imageEnd})`);
      }
    } else {
      // Try alternative pattern - just look for the notebook push message
      const pushMatch = fullLog.match(/pushing kernel\s+([^\s]+)/i);
      if (pushMatch) {
        notebookSlug = pushMatch[1];
        logCharGen(`  ✓ Found notebook slug from push log: ${notebookSlug}`);
        // Try to extract image range from slug
        const rangeMatch = notebookSlug.match(/-(\d+)-(\d+)$/);
        if (rangeMatch) {
          imageStart = parseInt(rangeMatch[1], 10);
          imageEnd = parseInt(rangeMatch[2], 10);
        }
      }

      // Try another alternative - look for the notebook slug format directly in the log
      // Format: <project>-image-<model>-<start>-<end> (with or without an owner prefix)
      if (!notebookSlug) {
        const slugMatch = fullLog.match(/(?:[a-zA-Z0-9_-]+\/)?([a-z0-9-]+?)-image-([a-z0-9-]+)-(\d+)-(\d+)/i);
        if (slugMatch) {
          const fullSlug = slugMatch[0]; // includes owner prefix if present
          const projectFromSlug = slugMatch[1].replace(/-/g, "_");
          const modelFromSlug = slugMatch[2].replace(/-/g, "_");
          const start = parseInt(slugMatch[3], 10);
          const end = parseInt(slugMatch[4], 10);
          notebookSlug = fullSlug;
          imageStart = start;
          imageEnd = end;
          logCharGen(`  ✓ Found notebook slug from direct log match: ${notebookSlug} (images ${imageStart}-${imageEnd})`);
        }
      }
    }
  } catch (e) {
    logCharGen(`  ⚠ Could not extract notebook info from log: ${e.message}`, true);
  }

  if (pushedRefs.length) {
    if (notebookSlug && notebookSlug !== pushedRefs[0]) logCharGen(`  ℹ Using the notebook the run script pushed: ${pushedRefs[0]}`);
    notebookSlug = pushedRefs[0];
  } else {
    logCharGen("  ⚠ The run script never reported pushing a Kaggle notebook (see the log above).", true);
  }

  // If we didn't find the log line, something is wrong
  if (!notebookSlug) {
    logCharGen(`  ⚠ Could not find generation log line in job output. This indicates the job may not have started properly.`, true);
    logCharGen(`  ℹ Expected log format: "===== [1/1] image <model>: rows <start>-<end> \$ PROJECT=<project> ..."`, true);
    logCharGen(`  ℹ Without this line, the notebook was not created on Kaggle. Check the job log for errors.`, true);
    // Still try to wait and fall back
    logCharGen("\n⏳ Waiting 3 minutes before fallback check...");
    await new Promise(resolve => setTimeout(resolve, 180000));
    return await fallbackDownloadImages(setName, model, series, name, overwriteToken, overwriteRefs, allPrompts, 1, 10, notebookSlug || "");
  }

  // Poll Kaggle until the notebook finishes, then download its output
  const kaggleState = await waitForKaggleAndDownload(notebookSlug);
  if (kaggleState !== "COMPLETE") return;

  // Retry mechanism: if notebook wasn't actually pushed to Kaggle, retry generation
  const maxRetries = 2;
  let retryCount = 0;

  async function attemptFetch() {
    // Use /api/fetch to pull results from Kaggle (uses kaggle kernels output internally)
    logCharGen(`\n📥 Fetching results from Kaggle for ${notebookSlug}... (attempt ${retryCount + 1}/${maxRetries + 1})`);
    logCharGen(`   (Expecting images ${imageStart} through ${imageEnd})`);
    try {
      await api("/api/fetch", {
        slug: notebookSlug.split("/").pop(),   // the server wants the notebook name without the owner
        project: setName,  // The prompt set project where images are generated
        wait: true  // Wait for the fetch to complete
      });
      logCharGen("✓ Fetch job started, waiting for completion...");
    } catch (e) {
      const errorMsg = e.message || "";
      logCharGen(`  ⚠ Fetch API error: ${errorMsg}`, true);

      // Check if the error indicates the notebook wasn't found on Kaggle
      if (errorMsg.toLowerCase().includes("not found") ||
          errorMsg.toLowerCase().includes("404") ||
          errorMsg.toLowerCase().includes("does not exist")) {

        if (retryCount < maxRetries) {
          retryCount++;
          logCharGen(`  🔄 Notebook not found on Kaggle. Retrying generation (attempt ${retryCount}/${maxRetries})...`, true);

          // Re-run the generation job
          try {
            await api("/api/run", {
              mode: "prompts",
              kind: "image",
              set: setName,
              model: model,
              service: service,
              gpu: gpu,
              kaggle_user: service === "kaggle" ? ($("kuser").value || "") : "",
              prompts: allPrompts.join("\n"),
              opts: {
                negative: negative,
                width: width,
                height: height,
                steps: steps,
                guidance: guidance,
                reference: charGenReference,
                overwrite: true
              }
            });
            logCharGen("✓ Retry generation job started");

            await followJob(logCharGen, 5000);
            logCharGen("✓ Retry job completed!");

            // Poll Kaggle until the retried notebook finishes
            if ((await waitForKaggleAndDownload(notebookSlug)) !== "COMPLETE") return;

            // Recursively attempt fetch again
            return await attemptFetch();
          } catch (retryError) {
            logCharGen(`  ✗ Retry generation failed: ${retryError.message}`, true);
            throw e; // Throw original fetch error
          }
        }
      }

      // If we get here, either max retries exceeded or error is not "not found"
      logCharGen(`  ⚠ Falling back to direct file check...`, true);
      return await fallbackDownloadImages(setName, model, series, name, overwriteToken, overwriteRefs, allPrompts, imageStart, imageEnd, notebookSlug);
    }

    // Poll for fetch job completion (check every 10 seconds for up to 4 minutes = 24 checks)
    logCharGen("  Checking for fetched results every 10s (max 4 minutes)...");
    let fetchComplete = false;
    for (let check = 0; check < 24 && !fetchComplete; check++) {
      await new Promise(resolve => setTimeout(resolve, 10000)); // 10 seconds

      try {
        const logResult = await api("/api/log?since=0");
        const recentLog = logResult.lines.slice(-20).join("\n");
        if (recentLog.includes("✅") && recentLog.includes("file(s) copied")) {
          fetchComplete = true;
          logCharGen("✓ Fetch completed - results downloaded");
          break;
        }
        if (recentLog.includes("ERROR") || recentLog.includes("error") || recentLog.includes("not found")) {
          logCharGen(`  ⚠ Fetch may have failed: ${recentLog.slice(-200)}`);
          // Continue checking, might recover
        }
      } catch (e) {
        logCharGen(`  ⚠ Could not check fetch status: ${e.message}`, true);
      }
    }

    if (!fetchComplete) {
      logCharGen(`  ⚠ Fetch did not complete within 4 minutes. Checking for downloaded files anyway...`);
    }

    // Now look for downloaded images in the project folder using the known image range
    return await fallbackDownloadImages(setName, model, series, name, overwriteToken, overwriteRefs, allPrompts, imageStart, imageEnd, notebookSlug);
  }

  // Start the fetch attempt with retry logic
  return await attemptFetch();
}

async function fallbackDownloadImages(setName, model, series, name, overwriteToken, overwriteRefs, allPrompts, imageStart, imageEnd, notebookSlug = "") {
  logCharGen("\n📥 Checking for generated images in project folder...");

  // Build the project directory path
  const projectDir = `images/${model}/`;
  let savedRefs = [];

  // Get existing reference images to determine starting index
  let maxIndex = 0;
  try {
    const charData = await api(`/api/characters?action=get&series=${encodeURIComponent(series)}&name=${encodeURIComponent(name)}`);
    if (charData.character && charData.character.reference_images) {
      for (const ref of charData.character.reference_images) {
        const match = ref.match(/_(\d+)\.png$/);
        if (match) {
          const idx = parseInt(match[1], 10);
          if (idx > maxIndex) maxIndex = idx;
        }
      }
    }
  } catch (e) {
    logCharGen(`  ⚠ Could not load existing references: ${e.message}`, true);
  }

  // Check for images in the project folder using the known image range (imageStart to imageEnd)
  // If range not known, default to 1-10
  const start = imageStart || 1;
  const end = imageEnd || 10;
  let imageFound = false;
  const wantAll = allPrompts.length > 1;      // a character sheet keeps every view
  for (let imgNum = start; imgNum <= end && (wantAll || !imageFound); imgNum++) {
    const imagePath = `${projectDir}image-${String(imgNum).padStart(4, '0')}.png`;
    logCharGen(`  Checking for image: ${imagePath}...`);

    try {
      const imageCheck = await fetch(`/file/${setName}/${imagePath}?t=${TOKEN}`, { method: "HEAD" });
      if (!imageCheck.ok) {
        logCharGen(`    ⚠ Image not found: ${imagePath}`, true);
        continue;
      }

      // Copy the image to the reference directory (under the book project/series)
      const newIndex = maxIndex + savedRefs.length + 1;
      const paddedIndex = String(newIndex).padStart(2, '0');
      const refName = `${charSlug(name)}_${paddedIndex}.png`;
      const refPath = `projects/characters/${series}/references/${charSlug(name)}/${refName}`;

      const copyResult = await api("/api/copy_file", {
        source: `${setName}/${imagePath}`,
        dest: refPath
      });

      if (copyResult.success) {
        savedRefs.push(refPath);
        logCharGen(`    ✓ Found and saved as: ${refPath} (was ${imagePath})`);
        imageFound = true;
      } else {
        logCharGen(`    ⚠ Failed to save image: ${copyResult.error}`, true);
      }
    } catch (e) {
      logCharGen(`    ⚠ Error processing image: ${e.message}`, true);
    }
  }

  // If still not found, try alternative model name (some models have different folder names)
  if (!imageFound) {
    logCharGen(`  Trying alternative paths...`);
    const altModels = [model, model.replace(/_/g, "-")];
    for (const altModel of altModels) {
      if (altModel === model) continue;
      const altProjectDir = `images/${altModel}/`;
      for (let imgNum = start; imgNum <= end && !imageFound; imgNum++) {
        const imagePath = `${altProjectDir}image-${String(imgNum).padStart(4, '0')}.png`;
        logCharGen(`  Checking alternative path: ${imagePath}...`);
        try {
          const imageCheck = await fetch(`/file/${setName}/${imagePath}?t=${TOKEN}`, { method: "HEAD" });
          if (!imageCheck.ok) continue;
          const newIndex = maxIndex + savedRefs.length + 1;
          const paddedIndex = String(newIndex).padStart(2, '0');
          const refName = `${charSlug(name)}_${paddedIndex}.png`;
          const refPath = `projects/characters/${series}/references/${charSlug(name)}/${refName}`;
          const copyResult = await api("/api/copy_file", {
            source: `${setName}/${imagePath}`,
            dest: refPath
          });
          if (copyResult.success) {
            savedRefs.push(refPath);
            logCharGen(`    ✓ Found and saved as: ${refPath} (was ${imagePath})`);
            imageFound = true;
          }
        } catch (e) {
          // ignore
        }
      }
    }
  }

  if (!imageFound) {
    logCharGen(`  ✗ Could not find any generated image in ${projectDir}image-${String(start).padStart(4, '0')}.png through image-${String(end).padStart(4, '0')}.png`, true);
    logCharGen(`  ℹ Check the job log for errors.`, true);
    logCharGen(`  ℹ If the generation log line was missing, the notebook may not have been created.`, true);
    logCharGen(`  ℹ Manual fetch: ./scripts/fetch_kaggle_run.sh ${notebookSlug || "<notebook-slug>"} --project ${setName} --wait`, true);
  }

  // Update character with new reference images
  if (overwriteRefs && savedRefs.length > 0) {
    try {
      const charData = await api(`/api/characters?action=get&series=${encodeURIComponent(series)}&name=${encodeURIComponent(name)}`);
      if (charData.character) {
        const updatedChar = {
          ...charData.character,
          reference_images: [...(charData.character.reference_images || []), ...savedRefs]
        };
        await api("/api/characters", { action: "save", character: updatedChar });
        logCharGen(`\n✓ Added ${savedRefs.length} reference image (auto-incremented)`);
        logCharGen(`  Saved refs: ${savedRefs.join(", ")}`);
      }
    } catch (e) {
      logCharGen(`⚠ Could not update character references: ${e.message}`, true);
    }
  }

  // Update visual token with the prompt if requested
  if (overwriteToken) {
    try {
      const charData = await api(`/api/characters?action=get&series=${encodeURIComponent(series)}&name=${encodeURIComponent(name)}`);
      if (charData.character) {
        const updatedChar = {
          ...charData.character,
          visual_token: allPrompts[0],
        };
        await api("/api/characters", { action: "save", character: updatedChar });
        logCharGen("✓ Visual token updated with prompt");
      }
    } catch (e) {
      logCharGen(`⚠ Could not update visual token: ${e.message}`, true);
    }
  }

  logCharGen(`\n✅ Character image generation complete!`);
  logCharGen(`   Saved ${savedRefs.length} reference image to: projects/characters/${series}/references/${charSlug(name)}/`);
  logCharGen(`   Image is in: ${projectDir}`);
}

// Log functions for the generation log box
function clearCharGenLog() {
  $("charGenLog").innerHTML = "";
}

function logCharGen(msg, isError = false) {
  const log = $("charGenLog");
  const line = document.createElement("div");
  line.style.marginBottom = "4px";
  line.style.color = isError ? "var(--danger)" : "var(--fg)";
  line.textContent = msg;
  log.appendChild(line);
  log.scrollTop = log.scrollHeight;
}

function showCharStatus(msg, isError = false) {
  $("charStatus").textContent = msg;
  $("charStatus").className = isError ? "err" : "warn";
}

function updateCharButtons() {
  const hasSeries = !!$("charSeries").value;
  const hasChar = !!$("charName").value;
  const hasSelection = !!$("charList").value;
  const hasVisualToken = !!$("charVisualToken").value;
  // Enable Generate Prompt when there's a character name or visual token (can generate from form)
  const canGeneratePrompt = hasChar || hasVisualToken;
  $("bCharNewSeries").disabled = false;
  $("bCharNew").disabled = !hasSeries;
  $("bCharSave").disabled = !hasChar || !hasSeries;
  $("bCharDelete").disabled = !hasSelection;
  $("bCharGenPrompt").disabled = false;   // always clickable: with nothing selected it explains what is missing in the Prompt Preview window
  $("bCharSync").disabled = !hasSeries || !$("proj").value;
  const picked = document.querySelectorAll("#charTableBody .charPick:checked").length;
  $("bCharSend").disabled = !hasSeries || !$("proj").value || !picked;
  $("bCharSend").textContent = picked ? `Send ${picked} ticked to the book` : "Send ticked to the book";
  $("bCharCopyAll").disabled = !$("charAllTokens").textContent || $("charAllTokens").textContent.startsWith("No characters");
  $("bCharRefreshAll").disabled = !hasSeries;
  $("bCharOpenRefDir").disabled = !$("charRefDir").textContent;
  $("bCharGenerate").disabled = charGenBusy;   // always clickable: with nothing selected it explains what is missing in the Generation Log
}

// ---- Theme Toggle ----
function initTheme() {
  const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
  const saved = localStorage.getItem("theme");
  const isDark = saved ? saved === "dark" : prefersDark;
  document.documentElement.classList.toggle("dark", isDark);
  updateThemeIcon(isDark);
}
function updateThemeIcon(isDark) {
  const btn = $("themeToggle");
  if (btn) btn.textContent = isDark ? "☀\uFE0E" : "🌙";   // \uFE0E = text form of the sun, so CSS colour applies
}
$("themeToggle").onclick = () => {
  const isDark = !document.documentElement.classList.contains("dark");
  document.documentElement.classList.toggle("dark", isDark);
  localStorage.setItem("theme", isDark ? "dark" : "light");
  updateThemeIcon(isDark);
};

// ---- Toast Notifications ----
function showToast(message, type = "info", duration = 4000) {
  const container = $("toast-container");
  const toast = document.createElement("div");
  toast.className = `toast ${type}`;
  toast.innerHTML = `<span>${escapeHtml(message)}</span><button class="close" aria-label="Dismiss">&times;</button>`;
  toast.querySelector(".close").onclick = () => toast.remove();
  container.appendChild(toast);
  if (duration > 0) setTimeout(() => toast.remove(), duration);
}

// ---- Character Archetype System ----
let charArchetypesData = null;

async function loadCharArchetypes() {
  try {
    const j = await api("/api/characters?action=archetypes");
    charArchetypesData = j.archetypes || {};
    const select = $("charArchetype");
    select.innerHTML = '<option value="">(select archetype)</option>' +
      Object.keys(charArchetypesData).map(a => `<option value="${a}">${a}</option>`).join("");
    select.onchange = () => onArchetypeChange();
  } catch (e) {
    showCharStatus("Failed to load archetypes: " + e.message, true);
  }
}

async function onArchetypeChange() {
  const archetype = $("charArchetype").value;
  if (!archetype || !charArchetypesData[archetype]) {
    clearArchetypeFields();
    return;
  }
  try {
    // Load fields schema for this archetype
    const fieldsRes = await api(`/api/characters?action=archetype_fields&archetype=${encodeURIComponent(archetype)}`);
    const fields = fieldsRes.fields || {};

    // Load valid values for dropdown fields
    const validRes = await api(`/api/characters?action=valid_values`);
    const validValues = validRes.valid_values || {};

    renderArchetypeFields(fields, validValues, archetype);
    if (Date.now() - charSavedAt > 4000) showCharStatus(`Loaded archetype: ${archetype}`);   // not right after a save: keep "Character saved"
  } catch (e) {
    showCharStatus("Failed to load archetype fields: " + e.message, true);
  }
}

function clearArchetypeFields() {
  $("physicalTraitsFields").innerHTML = "";
  $("loraFields").innerHTML = "";
}

function renderArchetypeFields(fields, validValues, archetype) {
  // Render physical traits fields
  const physicalContainer = $("physicalTraitsFields");
  const physicalFields = ["age", "height", "build", "skin", "hair", "facial_hair", "eyes", "expression", "ethnicity", "distinguishing_features"];
  physicalContainer.innerHTML = physicalFields.map(field => {
    const valid = validValues[field] || [];
    const isDropdown = valid.length > 0;
    const fieldDef = fields[field] || { type: "string", required: false };
    const required = fieldDef.required ? "required" : "";
    const placeholder = fieldDef.description || field;

    if (isDropdown) {
      return `<div class="char-trait-field">
        <label class="f">${field.charAt(0).toUpperCase() + field.slice(1).replace("_", " ")} ${required ? '<span style="color:var(--danger)">*</span>' : ''}</label>
        <select id="trait_${field}" ${required}>
          <option value="">(select)</option>
          ${valid.map(v => `<option value="${escapeHtml(v)}">${escapeHtml(v)}</option>`).join("")}
        </select>
      </div>`;
    } else {
      return `<div class="char-trait-field">
        <label class="f">${field.charAt(0).toUpperCase() + field.slice(1).replace("_", " ")} ${required ? '<span style="color:var(--danger)">*</span>' : ''}</label>
        <input type="text" id="trait_${field}" placeholder="${escapeHtml(placeholder)}" ${required} autocomplete="off">
      </div>`;
    }
  }).join("");

  // Render LoRA fields
  const loraContainer = $("loraFields");
  const loraFields = ["repo", "trigger_word", "base_model", "trained"];
  loraContainer.innerHTML = loraFields.map(field => {
    const valid = validValues[field] || [];
    const isDropdown = valid.length > 0;
    const fieldDef = fields[field] || { type: "string", required: false };
    const required = fieldDef.required ? "required" : "";
    const placeholder = fieldDef.description || field;

    if (isDropdown) {
      return `<div class="char-trait-field">
        <label class="f">${field.charAt(0).toUpperCase() + field.slice(1).replace("_", " ")} ${required ? '<span style="color:var(--danger)">*</span>' : ''}</label>
        <select id="lora_${field}" ${required}>
          <option value="">(select)</option>
          ${valid.map(v => `<option value="${escapeHtml(v)}">${escapeHtml(v)}</option>`).join("")}
        </select>
      </div>`;
    } else {
      return `<div class="char-trait-field">
        <label class="f">${field.charAt(0).toUpperCase() + field.slice(1).replace("_", " ")} ${required ? '<span style="color:var(--danger)">*</span>' : ''}</label>
        <input type="text" id="lora_${field}" placeholder="${escapeHtml(placeholder)}" ${required} autocomplete="off">
      </div>`;
    }
  }).join("");

  // Set default LoRA trigger_word if empty
  setTimeout(() => {
    const triggerInput = $("lora_trigger_word");
    if (triggerInput && !triggerInput.value && $("charName").value) {
      triggerInput.value = $("charName").value.toLowerCase().replace(/[^a-z0-9]/g, "_") + "_token";
    }
  }, 0);
}

function getCharFormData() {
  // Collect physical traits from dropdowns/inputs
  const physical_traits = {};
  const physicalFields = ["age", "height", "build", "skin", "hair", "facial_hair", "eyes", "expression", "ethnicity", "distinguishing_features"];
  for (const field of physicalFields) {
    const el = $(`trait_${field}`);
    if (el && el.value) physical_traits[field] = el.value;
  }

  // Collect LoRA info from dropdowns/inputs
  const lora = {};
  const loraFields = ["repo", "trigger_word", "base_model", "trained"];
  for (const field of loraFields) {
    const el = $(`lora_${field}`);
    if (el) {
      if (el.type === "checkbox") {
        lora[field] = el.checked;
      } else if (el.value) {
        lora[field] = el.value;
      }
    }
  }
  // Default LoRA values if not set
  if (!lora.trigger_word && $("charName").value) {
    lora.trigger_word = $("charName").value.toLowerCase().replace(/[^a-z0-9]/g, "_") + "_token";
  }
  if (!lora.base_model) lora.base_model = "LTX-Video";
  if (lora.trained === undefined) lora.trained = false;
  if (!lora.repo) lora.repo = "";

  return {
    name: $("charName").value.trim(),
    series: $("charSeries").value,
    archetype: $("charArchetype").value || undefined,
    visual_token: $("charVisualToken").value.trim(),
    trigger_words: $("charTriggerWords").value.split(",").map(s => s.trim()).filter(s => s),
    physical_traits: physical_traits,
    clothing: $("charClothing").value.trim(),
    voice: $("charVoice").value.trim(),
    lora: lora,
    reference_images: $("charRefImages").value.split("\n").map(s => s.trim()).filter(s => s),
    consistency_notes: $("charConsistency").value.trim(),
    stages: textToStages($("charStages").value)
  };
}

function setCharFormData(data) {
  // Set basic fields
  if (data.name) $("charName").value = data.name;
  if (data.visual_token) $("charVisualToken").value = data.visual_token;
  if (data.trigger_words) $("charTriggerWords").value = (data.trigger_words || []).join(", ");
  if (data.clothing) $("charClothing").value = data.clothing;
  if (data.voice) $("charVoice").value = data.voice;
  if (data.reference_images) $("charRefImages").value = (data.reference_images || []).join("\n");
  if (data.consistency_notes) $("charConsistency").value = data.consistency_notes;
  if (data.stages) $("charStages").value = stagesToText(data.stages);

  // Set archetype if present
  if (data.archetype && charArchetypesData && charArchetypesData[data.archetype]) {
    $("charArchetype").value = data.archetype;
    onArchetypeChange(); // This will populate fields

    // Wait for fields to render then set values
    setTimeout(() => {
      if (data.physical_traits) {
        for (const [field, value] of Object.entries(data.physical_traits)) {
          const el = $(`trait_${field}`);
          if (el) el.value = value;
        }
      }
      if (data.lora) {
        for (const [field, value] of Object.entries(data.lora)) {
          const el = $(`lora_${field}`);
          if (el) {
            if (el.type === "checkbox") el.checked = value;
            else el.value = value;
          }
        }
      }
      updateCharButtons();
    }, 100);
  } else {
    updateCharButtons();
  }
}

async function loadCharacter(series, name) {
  if (!series || !name) return;
  charCurrentSeries = series;
  charCurrentCharacter = name;
  try {
    const j = await api(`/api/characters?action=get&series=${encodeURIComponent(series)}&name=${encodeURIComponent(name)}`);
    const c = j.character;
    if (c) {
      setCharFormData(c);
      updateRefDir();
    }
    updateCharButtons();
  } catch (e) {
    showCharStatus(e.message, true);
  }
}

// ---- Global Parameters ----
async function loadGlobalParams(project) {
  // If no project specified, load from localStorage (fallback for initial load)
  if (!project) {
    const pos = localStorage.getItem("globalPositives") || "";
    const neg = localStorage.getItem("globalNegatives") || "";
    if ($("globalPositives")) $("globalPositives").value = pos;
    if ($("globalNegatives")) $("globalNegatives").value = neg;
    return;
  }

  // Load from server
  try {
    const result = await api(`/api/global_params?project=${encodeURIComponent(project)}`);
    if ($("globalPositives")) $("globalPositives").value = result.positives || "";
    if ($("globalNegatives")) $("globalNegatives").value = result.negatives || "";
    // Also cache in localStorage for offline/fallback use
    localStorage.setItem("globalPositives", result.positives || "");
    localStorage.setItem("globalNegatives", result.negatives || "");
  } catch (e) {
    // Fallback to localStorage if server fails
    const pos = localStorage.getItem("globalPositives") || "";
    const neg = localStorage.getItem("globalNegatives") || "";
    if ($("globalPositives")) $("globalPositives").value = pos;
    if ($("globalNegatives")) $("globalNegatives").value = neg;
  }
}

async function saveGlobalParams() {
  if (!$("globalPositives") || !$("globalNegatives")) return;
  const positives = $("globalPositives").value.trim();
  const negatives = $("globalNegatives").value.trim();

  // Validate format: comma-separated keywords, no newlines
  function validateFormat(value, fieldName) {
    if (!value) return { valid: true, value: "" };

    // Check for newlines (should be comma-separated)
    if (value.includes("\n")) {
      return { valid: false, error: `${fieldName}: newlines are not allowed. Use comma-separated values.` };
    }

    // Normalize: split by comma, trim each part, filter empty, rejoin with ", "
    const parts = value.split(",").map(s => s.trim()).filter(s => s);
    const normalized = parts.join(", ");

    // Check for potentially problematic characters
    const hasBadChars = /[<>|{}\[\]\\]/.test(normalized);
    if (hasBadChars) {
      return { valid: false, error: `${fieldName}: contains invalid characters (< > | { } [ ] \\).` };
    }

    return { valid: true, value: normalized };
  }

  const posValidation = validateFormat(positives, "Global Positives");
  const negValidation = validateFormat(negatives, "Global Negatives");

  if (!posValidation.valid || !negValidation.valid) {
    const statusEl = $("globalStatus");
    if (statusEl) {
      statusEl.textContent = (posValidation.error || "") + " " + (negValidation.error || "");
      statusEl.className = "err";
      setTimeout(() => { statusEl.textContent = ""; }, 5000);
    }
    return;
  }

  // Use normalized values
  const normalizedPositives = posValidation.value;
  const normalizedNegatives = negValidation.value;

  // Save to localStorage immediately for fast UI feedback
  localStorage.setItem("globalPositives", normalizedPositives);
  localStorage.setItem("globalNegatives", normalizedNegatives);

  // Update the textareas with normalized values
  $("globalPositives").value = normalizedPositives;
  $("globalNegatives").value = normalizedNegatives;

  // Save to server if we have a project
  const project = $("proj").value;
  if (project) {
    try {
      await api("/api/global_params", {
        project: project,
        positives: normalizedPositives,
        negatives: normalizedNegatives
      });
      const statusEl = $("globalStatus");
      if (statusEl) {
        statusEl.textContent = "Saved to project";
        statusEl.className = "ok";
        setTimeout(() => { statusEl.textContent = ""; }, 2000);
      }
    } catch (e) {
      const statusEl = $("globalStatus");
      if (statusEl) {
        statusEl.textContent = "Saved to browser only (server failed: " + e.message + ")";
        statusEl.className = "warn";
        setTimeout(() => { statusEl.textContent = ""; }, 3000);
      }
    }
  } else {
    const statusEl = $("globalStatus");
    if (statusEl) {
      statusEl.textContent = "Saved to browser storage (no project selected)";
      statusEl.className = "warn";
      setTimeout(() => { statusEl.textContent = ""; }, 2000);
    }
  }
}

// Load global params on startup (from localStorage)
loadGlobalParams();

async function loadGlobalParamsFromServer() {
  const project = $("proj").value;
  if (!project) {
    const statusEl = $("globalStatus");
    if (statusEl) {
      statusEl.textContent = "No project selected";
      statusEl.className = "warn";
      setTimeout(() => { statusEl.textContent = ""; }, 2000);
    }
    return;
  }

  const statusEl = $("globalStatus");
  if (statusEl) {
    statusEl.textContent = "Loading...";
    statusEl.className = "warn";
  }

  try {
    const result = await api(`/api/global_params?project=${encodeURIComponent(project)}`);
    if ($("globalPositives")) $("globalPositives").value = result.positives || "";
    if ($("globalNegatives")) $("globalNegatives").value = result.negatives || "";
    // Also cache in localStorage for offline/fallback use
    localStorage.setItem("globalPositives", result.positives || "");
    localStorage.setItem("globalNegatives", result.negatives || "");

    if (statusEl) {
      statusEl.textContent = "Loaded from project";
      statusEl.className = "ok";
      setTimeout(() => { statusEl.textContent = ""; }, 2000);
    }
  } catch (e) {
    if (statusEl) {
      statusEl.textContent = "Failed to load: " + e.message;
      statusEl.className = "err";
      setTimeout(() => { statusEl.textContent = ""; }, 3000);
    }
  }
}

// Wire up event listeners
$("charSeries").onchange = () => { loadCharList(); updateRefDir(); };
$("charList").onchange = () => { if ($("charList").value) loadCharacter($("charSeries").value, $("charList").value); updateCharButtons(); };
$("bCharNewSeries").onclick = newSeries;
$("bCharNew").onclick = newCharacter;
$("bCharSave").onclick = saveCharacter;
$("bCharDelete").onclick = deleteCharacter;
$("bCharGenPrompt").onclick = showCharacterPrompt;
$("bCharSync").onclick = syncFromProject;
$("bCharSend").onclick = sendToBook;
$("charPickAll").onchange = () => { document.querySelectorAll("#charTableBody .charPick").forEach(e => { e.checked = $("charPickAll").checked; }); updateCharButtons(); };
$("bCharCopyAll").onclick = copyAllTokens;
$("bCharRefreshAll").onclick = loadCharAllTokens;
$("bCharOpenRefDir").onclick = openRefDir;
$("charRefThumbs").addEventListener("click", async e => {
  const b = e.target.closest("[data-useref]");
  if (!b) return;
  try {
    await api("/api/characters", { action: "use_reference", series: $("charSeries").value, name: $("charName").value.trim(), path: b.dataset.useref });
    await loadCharacter($("charSeries").value, $("charName").value.trim());
    await loadCharRefs();
    showCharStatus("Face chosen");
  } catch (err) { showCharStatus(err.message, true); }
});
document.addEventListener("change", e => { if (e.target.name === "imodel") loadCharRefs(); });
$("autoClean").addEventListener("change", async e => {
  try { await api("/api/auto_cleanup", { on: e.target.checked }); }
  catch (err) { e.target.checked = !e.target.checked; clnStatus(err.message, "err"); }
});
$("bFilm").addEventListener("click", runFilm);
$("bFilmStop").addEventListener("click", () => api("/api/stop", {}).catch(() => {}));
$("proj").addEventListener("change", () => showFilmStatus($("proj").value).catch(() => {}));
$("showAdvanced").checked = localStorage.getItem("showAdvancedModels") === "1";
function applyShowAdvanced() { $("modelGrid").classList.toggle("hide-advanced", !$("showAdvanced").checked); }
$("showAdvanced").addEventListener("change", () => { localStorage.setItem("showAdvancedModels", $("showAdvanced").checked ? "1" : "0"); applyShowAdvanced(); });
applyShowAdvanced();
$("sbFaces").addEventListener("click", async () => {
  const series = $("kfseries").value;
  $("sbStatus").textContent = "Checking faces; see the log. Press Show storyboard when it ends.";
  try { await api("/api/face_check", { project: $("proj").value, series, look: radio("look") || "", ...(([s, e]) => s ? { start: s, end: e } : {})(($("sbMovie").value || "").split("-").map(Number)) }); }
  catch (err) { $("sbStatus").textContent = err.message; }
});
$("bCharGenerate").onclick = generateCharacterImage;
$("bGlobalRead").onclick = loadGlobalParamsFromServer;
$("bGlobalSave").onclick = saveGlobalParams;
$("charName").addEventListener("input", () => { updateRefDir(); updateCharButtons(); updatePromptPreview(); });
$("charVisualToken").addEventListener("input", () => { updateCharButtons(); updatePromptPreview(); });
$("charTriggerWords").addEventListener("input", updatePromptPreview);
$("charClothing").addEventListener("input", () => { updateCharButtons(); updatePromptPreview(); });
$("charVoice").addEventListener("input", updatePromptPreview);
$("charConsistency").addEventListener("input", updatePromptPreview);
$("charRefImages").addEventListener("input", updatePromptPreview);
$("charArchetype").addEventListener("change", updatePromptPreview);

// Add event listeners for dynamic physical traits and LoRA fields (delegated since they're created dynamically)
document.addEventListener("input", (e) => {
  if (e.target.id && (e.target.id.startsWith("trait_") || e.target.id.startsWith("lora_"))) {
    updatePromptPreview();
  }
});

// Add event listener for view dropdown to update preview
$("charGenView").addEventListener("change", updatePromptPreview);

// Load character series and archetypes on startup
loadCharSeries();
loadCharArchetypes();

// Initialize theme
initTheme();

// Update status badge when connected
const originalLoadStatus = loadStatus;
loadStatus = async function(applyDef) {
  await originalLoadStatus(applyDef);
  const badge = $("statusBadge");
  if (badge) {
    badge.className = "status-badge ok";
    badge.querySelector("span:last-child").textContent = "Connected";
  }
};


// ===== TAB NAVIGATION =====
function initTabs() {
    const tabBtns = document.querySelectorAll('.tab-btn');
    const tabPanels = document.querySelectorAll('.tab-panel');
    
    tabBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            const tabName = btn.dataset.tab;
            
            // Update buttons
            tabBtns.forEach(b => {
                b.classList.remove('active');
                b.setAttribute('aria-selected', 'false');
            });
            btn.classList.add('active');
            btn.setAttribute('aria-selected', 'true');
            
            // Update panels
            tabPanels.forEach(panel => {
                panel.classList.remove('active');
                panel.setAttribute('aria-hidden', 'true');
            });
            const activePanel = document.getElementById('panel-' + tabName);
            if (activePanel) {
                activePanel.classList.add('active');
                activePanel.setAttribute('aria-hidden', 'false');
            }
            
            // The book-to-film rail is about the chosen book; Single Prompts has nothing to do with it
            const offBook = tabName === 'prompts';
            document.getElementById('pipelineStepper')?.classList.toggle('hidden', offBook);
            document.getElementById('stepperHint')?.classList.toggle('hidden', offBook);

            // Save to localStorage
            try { localStorage.setItem('activeTab', tabName); } catch (e) { /* private window: the tab is just not remembered */ }
        });
    });
    
    // Restore active tab
    const savedTab = localStorage.getItem('activeTab') || 'project';
    const savedBtn = document.querySelector('.tab-btn[data-tab="' + savedTab + '"]');
    if (savedBtn) savedBtn.click();
}

// ===== no autofill anywhere =====
// The Studio never asks for personal details, but browsers and password managers offer saved names, e-mail addresses and logins (synced
// from their servers) in any box they guess at, even with autocomplete="off". Every typing box, including ones added later, is marked so
// that none of them do. Boxes that already say what they hold are left alone.
const NO_FILL = { autocomplete: "off", "data-lpignore": "true", "data-1p-ignore": "true", "data-bwignore": "true", "data-form-type": "other" };
const TYPING = 'input:not([type]), input[type=text], input[type=search], input[type=number], input[type=url], input[type=email], input[type=password], textarea';
function noAutofill(root) {                          // root: the document or one element (it and everything inside it)
    const els = [...(root.matches && root.matches(TYPING) ? [root] : []), ...root.querySelectorAll(TYPING)];
    for (const el of els)
        for (const [k, v] of Object.entries(NO_FILL)) if (!el.getAttribute(k)) el.setAttribute(k, el.type === "password" && k === "autocomplete" ? "new-password" : v);
}
noAutofill(document);
new MutationObserver(list => { for (const m of list) for (const n of m.addedNodes) if (n.nodeType === 1) noAutofill(n); }).observe(document.body, { childList: true, subtree: true });

// ===== STEPPER (book-to-film rail above the tabs) =====
// Each step is done when its files exist (from /api/status), not when a checkbox is ticked. "cast" is optional and never the current step.
const STEP_NEXT = {
    ingest: 'Next: Read book (Import tab).',
    continuity: 'Next: Continuity book (Import tab).',
    write: 'Next: Write shots (Import tab).',
    build: 'Next: Build CSVs (Import tab).',
    video: 'Next: Video (Movies tab, Video and Audio card; or make keyframes first and check them in Storyboard).',
    audio: 'Next: Audio (Movies tab, Video and Audio card).',
    film: 'Next: Final film (Results tab).',
};
function stepDone(p) {
    const have = p.have || {};
    const sum = pre => Object.entries(have).filter(([k]) => k.startsWith(pre)).reduce((a, [, n]) => a + (Number(n) || 0), 0);
    const old = !!p.legacy;                                           // imported books arrive with the book steps already done
    return {
        ingest: old || (!p.not_started && !!p.chapters),
        continuity: old || !!p.continuity,
        cast: Array.isArray(p.characters) && p.characters.length > 0,
        board: sum('keyframes/') > 0,
        write: old || (p.chapters > 0 && p.scripts >= p.chapters),
        build: old || !!p.built,
        video: sum('videos/') > 0,
        audio: sum('audio/') > 0,
        film: (Number(have.films) || 0) > 0,
        counts: { video: sum('videos/'), audio: sum('audio/'), films: Number(have.films) || 0 },
    };
}
function updateStepper(project) {
    const els = document.querySelectorAll('#pipelineStepper .stepper__step');
    const hint = $('stepperHint');
    els.forEach(el => { el.classList.remove('active', 'complete'); el.removeAttribute('aria-current'); });
    if (!project) { if (hint) hint.textContent = 'Choose a book on the Import tab, or import a new one.'; return; }
    const done = stepDone(project);
    const current = [...els].find(el => !el.classList.contains('optional') && !done[el.dataset.step]);
    els.forEach(el => {
        const label = el.querySelector('.stepper__label').textContent;
        if (done[el.dataset.step]) el.classList.add('complete');
        if (el === current) { el.classList.add('active'); el.setAttribute('aria-current', 'step'); }
        el.setAttribute('aria-label', `${label}: ${done[el.dataset.step] ? 'done' : el === current ? 'next step' : 'not done yet'}`);
    });
    const c = done.counts;
    const have = `${project.slug}: ${c.video} clip(s), ${c.audio} sound file(s), ${c.films} film(s).`;
    if (hint) hint.textContent = have + ' ' + (current ? STEP_NEXT[current.dataset.step] : 'Every step is done. Watch your film on the Results tab.');
}
function goToStep(el) {
    if (el.dataset.step === 'film') { loadFilm(true); return; }       // opens the Results tab and the Make film panel with the downloaded files
    const tab = document.querySelector(`.tab-btn[data-tab="${el.dataset.go}"]`);
    if (tab) tab.click();
    const target = el.dataset.target && $(el.dataset.target);
    if (target) target.scrollIntoView({ behavior: 'smooth', block: 'start' });
}
document.querySelectorAll('#pipelineStepper .stepper__step').forEach(el => el.addEventListener('click', () => goToStep(el)));
// Every step card gets "previous step / next step" buttons taken from the rail, so the cards can be followed forwards and backwards
// in the same order and with the same names as the rail. Steps that share a card (Video, Audio) share one bar.
(function addStepNav() {
    const steps = [...document.querySelectorAll('#pipelineStepper .stepper__step')];
    const name = el => el.querySelector('.stepper__label').textContent;
    const cards = [];
    steps.forEach((el, i) => {
        const card = el.dataset.target && $(el.dataset.target);
        if (!card) return;
        const last = cards[cards.length - 1];
        if (last && last.card === card) last.to = i; else cards.push({ card, from: i, to: i });
    });
    const names = c => steps.slice(c.from, c.to + 1).map(name).join(' and ');     // a shared card is named by all its steps ("Video and Audio")
    const optional = c => steps.slice(c.from, c.to + 1).every(el => el.classList.contains('optional'));
    // Beside an optional step the bar also offers the step after it, so it can be skipped: going forward the optional step is on top and
    // the next required one below it; going back the required one is on top and the optional one below it. An optional card links plainly.
    const around = (k, dir) => {
        const out = [];
        for (let j = k + dir; j >= 0 && j < cards.length; j += dir) {
            out.push(cards[j]);
            if (optional(cards[k]) || !optional(cards[j])) break;
        }
        return dir > 0 ? out : out.reverse().sort((a, b) => optional(a) - optional(b));
    };
    cards.forEach((c, k) => {
        const body = c.card.querySelector(':scope > .card__body') || c.card;
        const nav = document.createElement('nav');
        nav.className = 'step-nav';
        nav.setAttribute('aria-label', 'Book to film steps');
        const btn = (to, text) => { const b = document.createElement('button'); b.type = 'button'; b.textContent = text; b.addEventListener('click', () => goToStep(steps[to.from])); return b; };
        const col = (list, back) => {
            const d = document.createElement('div'); d.className = 'step-nav__col' + (back ? '' : ' step-nav__col--next');
            list.forEach(t => d.appendChild(btn(t, back ? '\u2190 ' + names(t) : names(t) + ' \u2192')));
            return d;
        };
        nav.appendChild(col(around(k, -1), true));
        const mid = document.createElement('span'); mid.className = 'step-nav__here'; mid.textContent = `Step: ${names(c)}`; nav.appendChild(mid);
        nav.appendChild(col(around(k, 1), false));
        body.appendChild(nav);
    });
})();

// ===== COMMAND PALETTE =====
const COMMANDS = [
    { id: 'new-project', label: 'New Project', desc: 'Create a new book project', keys: '⌘N', action: () => $('file').click() },
    { id: 'run-pipeline', label: 'Run Pipeline', desc: 'Execute the full pipeline', keys: '⌘R', action: () => $('bRun').click() },
    { id: 'preview-commands', label: 'Preview Commands', desc: 'Show what will be executed', keys: '⌘P', action: () => $('bPreview').click() },
    { id: 'fetch-results', label: 'Fetch Kaggle Results', desc: 'Download completed runs', keys: '⌘F', action: () => $('bFetch').click() },
    { id: 'make-film', label: 'Make Film', desc: 'Assemble clips into final film', keys: '⌘M', action: () => $('bMakeFilm').click() },
    { id: 'switch-project', label: 'Switch Project', desc: 'Change active project', keys: '⌘1', action: () => $('proj').focus() },
    { id: 'characters', label: 'Manage Characters', desc: 'Open characters tab', keys: '⌘2', action: () => document.querySelector('[data-tab="characters"]').click() },
    { id: 'models', label: 'Configure Models', desc: 'Open models tab', keys: '⌘3', action: () => document.querySelector('[data-tab="models"]').click() },
    { id: 'creative-direction', label: 'Creative Direction', desc: 'Open creative direction (Movies tab)', keys: '⌘4', action: () => { document.querySelector('[data-tab="movies"]').click(); $('dirNotes')?.scrollIntoView({block:'center'}); } },
    { id: 'toggle-theme', label: 'Toggle Theme', desc: 'Switch light/dark mode', keys: '⌘D', action: () => $('themeToggle').click() },
    { id: 'open-results', label: 'Open Results', desc: 'Open results gallery', keys: '⌘5', action: () => document.querySelector('[data-tab="results"]').click() },
    { id: 'generate-characters', label: 'Generate Character Images', desc: 'Generate reference images for selected character', keys: '', action: () => { document.querySelector('[data-tab="characters"]').click(); $('bCharGenerate')?.click(); } },
    { id: 'save-global-params', label: 'Save Global Params', desc: 'Save global prompt parameters', keys: '', action: () => $('bGlobalSave')?.click() },
    { id: 'load-global-params', label: 'Load Global Params', desc: 'Load global prompt parameters', keys: '', action: () => $('bGlobalRead')?.click() },
];

function initCommandPalette() {
    const palette = $('cmd-palette');
    const input = palette.querySelector('input');
    const list = palette.querySelector('.cmd-list');
    
    function renderCommands(filter = '') {
        const filtered = COMMANDS.filter(cmd => 
            cmd.label.toLowerCase().includes(filter.toLowerCase()) ||
            cmd.desc.toLowerCase().includes(filter.toLowerCase()) ||
            cmd.id.includes(filter.toLowerCase())
        );
        list.innerHTML = filtered.map(cmd => `
            <div class="cmd-item" data-id="${cmd.id}">
                <span class="cmd-item__icon">${getCommandIcon(cmd.id)}</span>
                <div>
                    <div class="cmd-item__label">${cmd.label}</div>
                    <div class="cmd-item__desc">${cmd.desc}</div>
                </div>
                <kbd class="cmd-item__keys">${cmd.keys}</kbd>
            </div>
        `).join('');
        
        // Add click handlers
        list.querySelectorAll('.cmd-item').forEach(item => {
            item.addEventListener('click', () => {
                const cmd = COMMANDS.find(c => c.id === item.dataset.id);
                if (cmd) {
                    cmd.action();
                    closePalette();
                }
            });
        });
    }
    
    function openPalette() {
        palette.classList.add('open');
        input.value = '';
        renderCommands();
        input.focus();
    }
    
    function closePalette() {
        palette.classList.remove('open');
        input.value = '';
    }
    
    function getCommandIcon(id) {
        const icons = {
            'new-project': '📄',
            'run-pipeline': '▶️',
            'preview-commands': '👁️',
            'fetch-results': '⬇️',
            'make-film': '🎬',
            'switch-project': '📁',
            'characters': '👥',
            'models': '🤖',
            'creative-direction': '🎨',
            'toggle-theme': '🌓',
            'open-results': '📊',
            'generate-characters': '🖼️',
            'save-global-params': '💾',
            'load-global-params': '📥',
        };
        return icons[id] || '⚡';
    }
    
    // Keyboard shortcut: Cmd/Ctrl + K
    document.addEventListener('keydown', (e) => {
        if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
            e.preventDefault();
            openPalette();
        }
        if (e.key === 'Escape') {
            closePalette();
        }
    });
    
    input.addEventListener('input', (e) => {
        renderCommands(e.target.value);
    });
    
    input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            const firstItem = list.querySelector('.cmd-item');
            if (firstItem) {
                const cmd = COMMANDS.find(c => c.id === firstItem.dataset.id);
                if (cmd) {
                    cmd.action();
                    closePalette();
                }
            }
        }
        if (e.key === 'ArrowDown') {
            e.preventDefault();
            const items = list.querySelectorAll('.cmd-item');
            const active = list.querySelector('.cmd-item:hover, .cmd-item:focus');
            let next = items[0];
            if (active) {
                const idx = Array.from(items).indexOf(active);
                next = items[(idx + 1) % items.length];
            }
            next.focus();
        }
        if (e.key === 'ArrowUp') {
            e.preventDefault();
            const items = list.querySelectorAll('.cmd-item');
            const active = list.querySelector('.cmd-item:hover, .cmd-item:focus');
            let prev = items[items.length - 1];
            if (active) {
                const idx = Array.from(items).indexOf(active);
                prev = items[(idx - 1 + items.length) % items.length];
            }
            prev.focus();
        }
    });
    
    // Click outside to close
    palette.addEventListener('click', (e) => {
        if (e.target === palette) closePalette();
    });
}

// ===== TOAST HISTORY =====
const toastHistory = [];

function showToast(message, type = 'info', duration = 4000) {
    const container = $('toast-container');
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.innerHTML = `<span>${escapeHtml(message)}</span><button class="close" aria-label="Dismiss">&times;</button>`;
    toast.querySelector('.close').onclick = () => toast.remove();
    container.appendChild(toast);
    
    // Add to history
    toastHistory.unshift({
        message,
        type,
        time: new Date().toLocaleTimeString()
    });
    if (toastHistory.length > 50) toastHistory.pop();
    updateToastHistory();
    
    if (duration > 0) setTimeout(() => toast.remove(), duration);
}

function updateToastHistory() {
    const list = document.querySelector('.toast-history__list');
    if (list) {
        list.innerHTML = toastHistory.map(t => `
            <div class="toast-history__item">
                <div class="toast-history__time">${t.time}</div>
                <div class="toast toast-${t.type}" style="margin:0;box-shadow:none;border:none;padding:0">${escapeHtml(t.message)}</div>
            </div>
        `).join('');
    }
}

function initToastHistory() {
    // Create history button and panel
    const historyBtn = document.createElement('button');
    historyBtn.className = 'toast-history__btn';
    historyBtn.innerHTML = '📋';
    historyBtn.setAttribute('aria-label', 'Notification history');
    historyBtn.title = 'Notification history (click to open)';
    
    const panel = document.createElement('div');
    panel.className = 'toast-history__panel';
    panel.innerHTML = `
        <div class="toast-history__header">
            <span>Notifications</span>
            <button class="modal__close" aria-label="Close">&times;</button>
        </div>
        <div class="toast-history__list"></div>
    `;
    
    const wrapper = document.createElement('div');
    wrapper.className = 'toast-history';
    wrapper.appendChild(historyBtn);
    wrapper.appendChild(panel);
    document.body.appendChild(wrapper);
    
    historyBtn.onclick = () => panel.classList.toggle('open');
    panel.querySelector('.modal__close').onclick = () => panel.classList.remove('open');
    
    // Close on click outside
    document.addEventListener('click', (e) => {
        if (!wrapper.contains(e.target)) panel.classList.remove('open');
    });
    
    updateToastHistory();
}

// ===== SETTINGS MODAL =====
function initSettingsModal() {
    // Create modal if not exists
    if ($('settingsModal')) return;
    
    const modalHtml = `
        <div class="modal-overlay" id="settingsModal" role="dialog" aria-modal="true" aria-labelledby="settingsTitle">
            <div class="modal">
                <div class="modal__header">
                    <h2 class="modal__title" id="settingsTitle">Settings</h2>
                    <button class="modal__close" aria-label="Close">&times;</button>
                </div>
                <div class="modal__body">
                    <div style="display:grid;gap:24px">
                        <div>
                            <h3 style="margin:0 0 12px;font-size:var(--text-lg)">Appearance</h3>
                            <label class="opt" style="display:flex;align-items:center;gap:8px;margin-bottom:8px">
                                <input type="checkbox" id="settingCompact" style="width:auto">
                                <span>Compact mode (denser spacing)</span>
                            </label>
                            <label class="opt" style="display:flex;align-items:center;gap:8px">
                                <input type="checkbox" id="settingAnimations" checked style="width:auto">
                                <span>Enable animations</span>
                            </label>
                        </div>
                        <div>
                            <h3 style="margin:0 0 12px;font-size:var(--text-lg)">Defaults</h3>
                            <div class="row" style="gap:12px;align-items:flex-end">
                                <div style="min-width:200px">
                                    <label class="f">Default GPU</label>
                                    <select id="settingDefaultGpu"></select>
                                </div>
                                <div style="min-width:150px">
                                    <label class="f">Default Batch Size</label>
                                    <input type="number" id="settingDefaultBatch" min="0" value="40" autocomplete="off">
                                </div>
                            </div>
                        </div>
                        <div>
                            <h3 style="margin:0 0 12px;font-size:var(--text-lg)">Keyboard Shortcuts</h3>
                            <div class="data-table" style="font-size:var(--text-sm)">
                                <table class="data-table">
                                    <thead><tr><th>Shortcut</th><th>Action</th></tr></thead>
                                    <tbody>
                                        <tr><td><kbd>⌘K</kbd></td><td>Open Command Palette</td></tr>
                                        <tr><td><kbd>⌘R</kbd></td><td>Run Pipeline</td></tr>
                                        <tr><td><kbd>⌘P</kbd></td><td>Preview Commands</td></tr>
                                        <tr><td><kbd>⌘F</kbd></td><td>Fetch Results</td></tr>
                                        <tr><td><kbd>⌘M</kbd></td><td>Make Film</td></tr>
                                        <tr><td><kbd>⌘D</kbd></td><td>Toggle Theme</td></tr>
                                        <tr><td><kbd>1-7</kbd></td><td>Switch Tabs</td></tr>
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    </div>
                </div>
                <div class="modal__footer">
                    <button class="btn btn-secondary" id="settingsCancel">Cancel</button>
                    <button class="btn btn-primary" id="settingsSave">Save</button>
                </div>
            </div>
        </div>
    `;
    
    document.body.insertAdjacentHTML('beforeend', modalHtml);
    
    const modal = $('settingsModal');
    const closeBtn = modal.querySelector('.modal__close');
    const cancelBtn = $('settingsCancel');
    const saveBtn = $('settingsSave');
    
    function openModal() {
        modal.classList.add('open');
        // Populate GPU options
        if (ST?.gpus) {
            const svc = radio('svc');
            const gpus = ST.gpus[svc] || [];
            $('settingDefaultGpu').innerHTML = gpus.map(([v, t]) => `<option value="${v}">${t}</option>`).join('');
        }
    }
    
    function closeModal() {
        modal.classList.remove('open');
    }
    
    // Open with ⌘,
    document.addEventListener('keydown', (e) => {
        if ((e.metaKey || e.ctrlKey) && e.key === ',') {
            e.preventDefault();
            openModal();
        }
    });
    
    closeBtn.onclick = closeModal;
    cancelBtn.onclick = closeModal;
    saveBtn.onclick = () => {
        // Save settings to localStorage
        localStorage.setItem('settingCompact', $('settingCompact').checked);
        localStorage.setItem('settingAnimations', $('settingAnimations').checked);
        localStorage.setItem('settingDefaultGpu', $('settingDefaultGpu').value);
        localStorage.setItem('settingDefaultBatch', $('settingDefaultBatch').value);
        closeModal();
        showToast('Settings saved', 'success');
    };
    
    modal.onclick = (e) => { if (e.target === modal) closeModal(); };
    
    // Load saved settings
    if (localStorage.getItem('settingCompact') === 'true') {
        document.documentElement.classList.add('compact');
    }
    if (localStorage.getItem('settingAnimations') === 'false') {
        document.documentElement.classList.add('reduce-motion');
    }
}

// ===== KEYBOARD SHORTCUTS FOR TABS =====
function initTabShortcuts() {
    document.addEventListener('keydown', (e) => {
        // Number keys 1-6 for the 6 tabs (when not in input)
        if (e.key >= '1' && e.key <= '6' && !['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement.tagName)) {
            const tabs = document.querySelectorAll('.tab-btn');
            const idx = parseInt(e.key) - 1;
            if (tabs[idx]) tabs[idx].click();
        }
    });
}

// ===== DRAG & DROP FOR FILE UPLOAD =====
function initDropZone() {
    const fileInput = $('file');
    if (!fileInput) return;
    
    // Find the parent container
    const container = fileInput.closest('div');
    if (!container) return;
    
    // Create drop zone
    const dropZone = document.createElement('div');
    dropZone.className = 'drop-zone';
    dropZone.innerHTML = `
        <div class="drop-zone__icon">📄</div>
        <div style="font-weight:500;margin-bottom:4px">Drop a PDF or text file here, or click to browse</div>
        <div style="font-size:var(--text-sm);color:var(--fg-muted)">Supports .pdf, .txt and .md files</div>
    `;
    
    // Insert before the file input
    container.insertBefore(dropZone, fileInput);
    fileInput.style.display = 'none';
    
    dropZone.onclick = () => fileInput.click();
    
    dropZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropZone.classList.add('drag-over');
    });
    
    dropZone.addEventListener('dragleave', () => {
        dropZone.classList.remove('drag-over');
    });
    
    dropZone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropZone.classList.remove('drag-over');
        if (e.dataTransfer.files.length) {
            fileInput.files = e.dataTransfer.files;
            fileInput.dispatchEvent(new Event('change'));
        }
    });
    
    fileInput.addEventListener('change', () => {
        if (fileInput.files.length) {
            dropZone.innerHTML = `
                <div class="drop-zone__icon">✅</div>
                <div style="font-weight:500;margin-bottom:4px">${escapeHtml(fileInput.files[0].name)}</div>
                <div style="font-size:var(--text-sm);color:var(--success)">Ready: press Import</div>
            `;
            dropZone.style.borderColor = 'var(--success)';
        }
    });
}

// ===== COPY TO CLIPBOARD HELPER =====
function copyToClipboard(text, label = 'Copied') {
    navigator.clipboard.writeText(text).then(() => {
        showToast(label, 'success');
    }).catch(() => {
        showToast('Failed to copy', 'error');
    });
}

// Add copy buttons to code/pre elements
function initCopyButtons() {
    document.querySelectorAll('pre, .cell code').forEach(el => {
        if (el.querySelector('.copy-btn')) return;
        const btn = document.createElement('button');
        btn.className = 'btn btn-icon copy-btn';
        btn.innerHTML = '📋';
        btn.title = 'Copy to clipboard';
        btn.style.position = 'absolute';
        btn.style.top = '8px';
        btn.style.right = '8px';
        btn.onclick = () => copyToClipboard(el.textContent);
        el.style.position = 'relative';
        el.appendChild(btn);
    });
}

// ===== INITIALIZE ALL =====
document.addEventListener('DOMContentLoaded', () => {
    initTabs();
    initCommandPalette();
    initToastHistory();
    initSettingsModal();
    initTabShortcuts();
    initDropZone();
    initCopyButtons();
    
    // Hook into loadStatus to update stepper
    const originalLoadStatus = loadStatus;
    loadStatus = async function(applyDef) {
        await originalLoadStatus(applyDef);
        updateStepper(cur());
        
        // Update status badge
        const badge = $('statusBadge');
        if (badge) {
            badge.className = 'status-badge ok';
            badge.querySelector('span:last-child').textContent = 'Connected';
        }
    };
    
    // The rail shows the chosen book, so redraw it when another book is picked
    $('proj').addEventListener('change', () => updateStepper(cur()));
});

// Override showToast to use new implementation
const originalShowToast = showToast;
showToast = function(message, type, duration) {
    originalShowToast(message, type, duration);
};

// Character table: one delegated listener instead of inline onclick handlers (the page's Content-Security-Policy forbids those).
document.addEventListener("click", ev => {
  const el = ev.target.closest("[data-act]");
  if (!el) return;
  const act = el.dataset.act;
  if (act === "pick-char") { ev.stopPropagation(); updateCharButtons(); }
  else if (act === "edit-char") { ev.stopPropagation(); loadCharacter(el.dataset.series, el.dataset.name); }
  else if (act === "delete-char") { ev.stopPropagation(); deleteCharacterConfirm(el.dataset.series, el.dataset.name); }
  else if (act === "select-char") selectCharInTable(el.dataset.name);
});

