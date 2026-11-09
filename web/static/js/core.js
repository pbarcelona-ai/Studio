// studio/core.js - page basics: token, api(), $ helper, form helpers, autofill guard
// Classic script: shares globals with the other studio/*.js files; load order is set in index.html.
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
