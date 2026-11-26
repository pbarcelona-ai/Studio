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
  const pickedStyle = ($("pStyleSel") && $("pStyleSel").value) ? $("pStyleSel").value.trim() : "";
  const lookVal = pickedStyle || ($("pLook").checked ? (radio("look") || "") : "");
  return {
    mode: "prompts", set: $("pset").value.trim().toLowerCase(), kind: t.kind, model: t.model, prompts: $("ptext").value,
    opts: { width: num("pw"), height: num("ph"), frames: num("pframes"), steps: num("psteps"), guidance: num("pguid"), seed: num("pseed"),
            variations: num("pvar") || 1, negative: $("pneg").value },
    look: lookVal,
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

// ---------- Single Prompts: Multi-Reference Cast Sheets / Sets + Visual Style Instant Image / Video ----------
let pUploadedRefDataUrl = "";
let pCastRefsList = [];
let pRefStackItems = []; // [{ kind: "rel"|"b64", label, rel_path, dataUrl, url }]

function renderPRefStack() {
  const stackEl = $("pRefStack");
  const lbl = $("pRefLabel");
  const btnClear = $("bPRefClear");
  const img = $("pRefPreview");
  if (stackEl) {
    stackEl.textContent = "";
    pRefStackItems.forEach((item, idx) => {
      const chip = document.createElement("div");
      chip.style.cssText = "display:inline-flex;align-items:center;gap:6px;padding:3px 7px;background:#0a0d14;border:1px solid #f59e0b;border-radius:6px;font-size:11px;color:#fde68a;";
      if (item.url) {
        const th = document.createElement("img");
        th.src = item.url;
        th.alt = item.label;
        th.style.cssText = "width:34px;height:34px;object-fit:cover;border-radius:4px;cursor:zoom-in;";
        th.onclick = () => window.open(item.url, "_blank");
        chip.appendChild(th);
      }
      const sp = document.createElement("span");
      sp.textContent = item.label;
      chip.appendChild(sp);
      const rm = document.createElement("button");
      rm.type = "button";
      rm.textContent = "✕";
      rm.style.cssText = "padding:1px 5px;font-size:10px;color:#f87171;";
      rm.onclick = () => {
        pRefStackItems.splice(idx, 1);
        renderPRefStack();
      };
      chip.appendChild(rm);
      stackEl.appendChild(chip);
    });
  }
  const hasAny = pRefStackItems.length > 0 || Boolean(pUploadedRefDataUrl) || Boolean($("pCastRef") && $("pCastRef").value);
  if (btnClear) btnClear.disabled = !hasAny;
  if (img) {
    if (pRefStackItems.length > 0) {
      img.style.display = "none";
    }
  }
  if (lbl) {
    if (pRefStackItems.length > 0) {
      lbl.textContent = `${pRefStackItems.length} reference image(s) stacked (Multi-Ref Hybrid active!)`;
    } else if (!pUploadedRefDataUrl && !($("pCastRef") && $("pCastRef").value)) {
      lbl.textContent = "Pick 1 or multiple cast sheets/sets from Step 08–11 or upload reference photo(s).";
    }
  }
}

function updatePRefPreview(url, labelText) {
  const img = $("pRefPreview");
  const lbl = $("pRefLabel");
  const btnClear = $("bPRefClear");
  if (img) {
    if (url && pRefStackItems.length === 0) {
      img.src = url;
      img.style.display = "block";
      img.onclick = () => window.open(url, "_blank");
    } else {
      img.src = "";
      img.style.display = "none";
      img.onclick = null;
    }
  }
  if (lbl) lbl.textContent = labelText || "Pick 1 or multiple cast sheets/sets from Step 08–11 or upload reference photo(s).";
  if (btnClear) btnClear.disabled = !(url || pRefStackItems.length > 0);
}

async function loadPCastRefs() {
  const sel = $("pCastRef");
  if (!sel) return;
  const slug = ($("proj") && $("proj").value) ? $("proj").value.trim() : "";
  const prev = sel.value;
  sel.textContent = "";
  const optNone = document.createElement("option");
  optNone.value = "";
  optNone.textContent = slug ? `None (text prompt only)` : `None (select a book to see cast refs)`;
  sel.appendChild(optNone);
  pCastRefsList = [];
  if (!slug) return;
  try {
    const data = await api(`/api/v2_cast_references?project=${encodeURIComponent(slug)}`);
    pCastRefsList = (data && Array.isArray(data.references)) ? data.references : [];
    pCastRefsList.forEach(ref => {
      const opt = document.createElement("option");
      opt.value = ref.rel_path;
      opt.dataset.url = ref.url;
      opt.textContent = ref.label || ref.character;
      sel.appendChild(opt);
    });
    if (prev && pCastRefsList.some(r => r.rel_path === prev)) {
      sel.value = prev;
    }
  } catch (e) {}
}
window.loadPCastRefs = loadPCastRefs;

let pStylesCatalog = [];
let pStyleCategories = [];
let pStyleActiveCat = "All";

function updatePStylePreview() {
  const sel = $("pStyleSel");
  const box = $("pStylePreviewBox");
  const img = $("pStylePreviewImg");
  const title = $("pStylePreviewTitle");
  const cat = $("pStylePreviewCat");
  const desc = $("pStylePreviewDesc");
  const sid = sel ? sel.value.trim() : "";
  const style = sid ? pStylesCatalog.find(s => s.id === sid) : null;

  document.querySelectorAll("#pStyleGrid .p-style-card").forEach(card => {
    const isSel = (card.dataset.styleId || "") === sid;
    card.classList.toggle("is-selected", isSel);
    card.setAttribute("aria-checked", String(isSel));
  });

  if (!box) return;
  if (!style) {
    box.style.display = "none";
    return;
  }
  box.style.display = "flex";
  if (img) {
    if (style.sample_url) {
      img.style.display = "block";
      img.src = style.sample_url;
      img.alt = `${style.name || style.label || style.id} preview`;
      img.onclick = () => window.open(style.sample_url, "_blank");
    } else {
      img.style.display = "none";
      img.src = "";
      img.onclick = null;
    }
  }
  if (title) title.textContent = `${style.icon ? style.icon + " " : ""}${style.name || style.label || style.id}${style.custom ? " ★" : ""}`;
  if (cat) cat.textContent = style.category || "Style";
  if (desc) desc.textContent = style.summary || style.positives || "";
}

function selectPStyle(styleId) {
  const sel = $("pStyleSel");
  if (sel) sel.value = styleId || "";
  updatePStylePreview();
}

function renderPStyleGallery() {
  const catsEl = $("pStyleCats");
  const gridEl = $("pStyleGrid");
  const searchEl = $("pStyleSearch");
  const btnToggle = $("bPStyleGalleryToggle");
  if (btnToggle && pStylesCatalog.length) {
    const isOpen = $("pStyleGalleryPanel") && $("pStyleGalleryPanel").style.display !== "none";
    btnToggle.textContent = isOpen
      ? `🎨 Hide Style Gallery (${pStylesCatalog.length})`
      : `🎨 Style Gallery (${pStylesCatalog.length})`;
  }
  if (!gridEl) return;

  const q = (searchEl ? searchEl.value : "").trim().toLowerCase();
  const catCounts = new Map();
  pStylesCatalog.forEach(s => {
    const c = s.category || "Custom";
    catCounts.set(c, (catCounts.get(c) || 0) + 1);
  });
  const catList = [
    "All",
    ...pStyleCategories.filter(c => catCounts.has(c)),
    ...[...catCounts.keys()].filter(c => !pStyleCategories.includes(c)),
  ];

  if (catsEl) {
    catsEl.textContent = "";
    catList.forEach(cat => {
      const b = document.createElement("button");
      b.type = "button";
      const active = pStyleActiveCat === cat;
      b.className = "btn " + (active ? "btn--primary" : "btn--ghost");
      b.style.cssText = "padding:3px 10px;font-size:11px;border-radius:999px;";
      const cnt = cat === "All" ? pStylesCatalog.length : (catCounts.get(cat) || 0);
      b.textContent = `${cat} (${cnt})`;
      b.addEventListener("click", () => {
        pStyleActiveCat = cat;
        renderPStyleGallery();
      });
      catsEl.appendChild(b);
    });
  }

  const curSid = ($("pStyleSel") && $("pStyleSel").value) ? $("pStyleSel").value.trim() : "";
  const filtered = pStylesCatalog.filter(s => {
    if (pStyleActiveCat !== "All" && (s.category || "Custom") !== pStyleActiveCat) return false;
    if (!q) return true;
    const hay = `${s.name || ""} ${s.label || ""} ${s.id || ""} ${s.category || ""} ${s.summary || ""} ${s.positives || ""}`.toLowerCase();
    return hay.includes(q);
  });

  gridEl.textContent = "";

  // "None" reset tile when viewing All without a search filter
  if (pStyleActiveCat === "All" && !q) {
    const noneBtn = document.createElement("button");
    noneBtn.type = "button";
    noneBtn.className = "p-style-card" + (!curSid ? " is-selected" : "");
    noneBtn.dataset.styleId = "";
    noneBtn.setAttribute("role", "radio");
    noneBtn.setAttribute("aria-checked", String(!curSid));
    const nt = document.createElement("span");
    nt.className = "deliverable-title";
    nt.textContent = "✏️ None (Prompt Only)";
    const np = document.createElement("p");
    np.className = "deliverable-desc";
    np.textContent = "Use your exact prompt wording without adding a preset visual style.";
    noneBtn.appendChild(nt);
    noneBtn.appendChild(np);
    noneBtn.addEventListener("click", () => selectPStyle(""));
    gridEl.appendChild(noneBtn);
  }

  if (!filtered.length) {
    const empty = document.createElement("div");
    empty.style.cssText = "grid-column:1/-1;color:#94a3b8;font-size:12px;padding:10px;";
    empty.textContent = "No visual styles match that filter.";
    gridEl.appendChild(empty);
    return;
  }

  filtered.forEach(s => {
    const btn = document.createElement("button");
    btn.type = "button";
    const isSel = curSid === s.id;
    btn.className = "p-style-card" + (isSel ? " is-selected" : "");
    btn.dataset.styleId = s.id;
    btn.setAttribute("role", "radio");
    btn.setAttribute("aria-checked", String(isSel));
    if (s.sample_url) {
      const thumb = document.createElement("img");
      thumb.src = s.sample_url;
      thumb.alt = `${s.name || s.label || s.id} style preview`;
      thumb.loading = "lazy";
      thumb.className = "v2-style-thumb";
      btn.appendChild(thumb);
    }
    const t = document.createElement("span");
    t.className = "deliverable-title";
    t.textContent = `${s.icon ? s.icon + " " : ""}${s.name || s.label || s.id}${s.custom ? " ★" : ""}`;
    const p = document.createElement("p");
    p.className = "deliverable-desc";
    p.textContent = s.summary || (s.positives || "").slice(0, 95);
    btn.appendChild(t);
    btn.appendChild(p);
    btn.addEventListener("click", () => selectPStyle(s.id));
    gridEl.appendChild(btn);
  });
}

async function loadPStyles() {
  const sel = $("pStyleSel");
  if (!sel) return;
  const prev = sel.value;
  try {
    const data = await api("/api/character_types");
    const styles = (data && Array.isArray(data.styles)) ? data.styles : [];
    const cats = (data && Array.isArray(data.style_categories)) ? data.style_categories : [];
    pStylesCatalog = styles;
    pStyleCategories = cats;
    sel.textContent = "";
    const optNone = document.createElement("option");
    optNone.value = "";
    optNone.textContent = "None (use prompt as written)";
    sel.appendChild(optNone);
    const byCat = new Map();
    styles.forEach(s => {
      const c = s.category || "Custom";
      if (!byCat.has(c)) byCat.set(c, []);
      byCat.get(c).push(s);
    });
    const order = cats.filter(c => byCat.has(c)).concat([...byCat.keys()].filter(c => !cats.includes(c)));
    order.forEach(cat => {
      const grp = document.createElement("optgroup");
      grp.label = cat;
      (byCat.get(cat) || []).forEach(s => {
        const opt = document.createElement("option");
        opt.value = s.id;
        opt.textContent = `${s.icon ? s.icon + " " : ""}${s.name || s.label || s.id}${s.custom ? " ★" : ""}`;
        grp.appendChild(opt);
      });
      sel.appendChild(grp);
    });
    if (prev) sel.value = prev;
    renderPStyleGallery();
    updatePStylePreview();
  } catch (e) {}
}
window.loadPStyles = loadPStyles;

async function runPRefGenerate(mode) {
  const statusEl = $("pRefStatus");
  const resultEl = $("pRefResult");
  const btnImg = $("bPRefGenImg");
  const btnVid = $("bPRefGenVid");
  const rawPrompts = ($("ptext")?.value || "").trim();
  const promptLines = rawPrompts.split(/\r?\n/).map(l => l.trim()).filter(Boolean);
  const prompt = promptLines[0] || "";
  if (!prompt) {
    if (statusEl) { statusEl.textContent = "Type a prompt in the Prompts box above first."; statusEl.className = "err"; }
    if ($("ptext")) $("ptext").focus();
    return;
  }
  const setFolder = ($("pset")?.value || "").trim().toLowerCase().replace(/[^a-z0-9_]+/g, "_") || "single_refs";
  if ($("pset") && !$("pset").value.trim()) $("pset").value = setFolder;
  const castRefPath = ($("pCastRef")?.value || "").trim();
  const styleId = ($("pStyleSel")?.value || "").trim();
  const aspect = ($("pRefAspect")?.value || "16:9").trim();
  const durationSec = Math.max(2, Math.min(12, parseInt($("pRefDur")?.value || "4", 10) || 4));
  const negative = ($("pneg")?.value || "").trim();

  if (btnImg) btnImg.disabled = true;
  if (btnVid) btnVid.disabled = true;
  const refPaths = pRefStackItems.filter(x => x.kind === "rel" && x.rel_path).map(x => x.rel_path);
  const b64List = pRefStackItems.filter(x => x.kind === "b64" && x.dataUrl).map(x => x.dataUrl);
  if (castRefPath && !refPaths.includes(castRefPath)) refPaths.push(castRefPath);
  if (pUploadedRefDataUrl && !b64List.includes(pUploadedRefDataUrl)) b64List.push(pUploadedRefDataUrl);
  const totalRefs = refPaths.length + b64List.length;

  const startedAt = Date.now();
  const modeLbl = mode === "video" ? "video" : "image";
  const refTag = totalRefs > 1
    ? `combining ${totalRefs} hybrid references`
    : (totalRefs === 1 ? "using reference picture" : "from prompt");
  const tick = () => {
    const sec = Math.floor((Date.now() - startedAt) / 1000);
    if (statusEl) {
      statusEl.className = "warn";
      statusEl.textContent = `⏳ Generating ${modeLbl} ${refTag}… (${sec}s elapsed)`;
    }
  };
  tick();
  const timer = setInterval(tick, 1000);
  pLog(`▶ Single Prompt ${modeLbl} render (${refTag}${styleId ? `, style=${styleId}` : ""}): ${prompt.slice(0, 120)}`);

  try {
    const payload = {
      set: setFolder,
      mode,
      prompt,
      negative_prompt: negative,
      style_id: styleId,
      aspect_ratio: aspect,
      duration: durationSec,
    };
    if (b64List.length) {
      payload.image_base64 = b64List[0];
      if (b64List.length > 1) payload.extra_images_base64 = b64List.slice(1);
    }
    if (refPaths.length) {
      payload.ref_paths = refPaths;
    }

    const res = await api("/api/v2_single_prompt_render", payload);
    clearInterval(timer);
    const elapsed = ((Date.now() - startedAt) / 1000).toFixed(1);
    const mediaUrl = res.video_url || res.image_url || res.url || "";
    const engineInfo = res.model || res.image_model || "local";
    if (statusEl) {
      statusEl.className = "chip done";
      statusEl.textContent = `✓ Generated ${modeLbl} in ${elapsed}s (${engineInfo}${res.used_reference ? ", reference locked" : ""}) — saved to projects/prompts/${setFolder}/`;
    }
    pLog(`✅ Saved ${mediaUrl} (${engineInfo}, ${elapsed}s)`);

    if (resultEl) {
      resultEl.textContent = "";
      const card = document.createElement("div");
      card.style.cssText = "display:flex;flex-wrap:wrap;gap:12px;align-items:flex-start;padding:10px;background:#0a0d14;border:1px solid #334155;border-radius:8px;";
      if (mode === "video" && mediaUrl) {
        const vid = document.createElement("video");
        vid.src = mediaUrl + "?t=" + Date.now();
        vid.controls = true;
        vid.autoplay = true;
        vid.loop = true;
        vid.playsInline = true;
        vid.style.cssText = "max-width:420px;width:100%;border-radius:6px;border:1px solid #475569;";
        card.appendChild(vid);
        if (res.start_frame_url) {
          const sf = document.createElement("img");
          sf.src = res.start_frame_url + "?t=" + Date.now();
          sf.alt = "Start frame";
          sf.title = "Generated start frame (click to open)";
          sf.style.cssText = "width:140px;border-radius:6px;border:1px solid #334155;cursor:zoom-in;";
          sf.onclick = () => window.open(res.start_frame_url, "_blank");
          card.appendChild(sf);
        }
      } else if (mediaUrl) {
        const img = document.createElement("img");
        img.src = mediaUrl + "?t=" + Date.now();
        img.alt = "Generated image";
        img.style.cssText = "max-width:420px;width:100%;border-radius:6px;border:1px solid #475569;cursor:zoom-in;";
        img.onclick = () => window.open(mediaUrl, "_blank");
        card.appendChild(img);
      }
      const meta = document.createElement("div");
      meta.style.cssText = "flex:1;min-width:180px;font-size:var(--text-xs);color:#cbd5e1;display:flex;flex-direction:column;gap:6px;";
      const link = document.createElement("a");
      link.href = mediaUrl;
      link.target = "_blank";
      link.textContent = `↗ Open full ${modeLbl}`;
      link.style.color = "#f59e0b";
      meta.appendChild(link);
      const info = document.createElement("div");
      info.textContent = `Engine: ${engineInfo}` + (res.style_id ? ` · Style: ${res.style_id}` : "") + (res.used_reference ? " · Reference: Active" : "");
      meta.appendChild(info);
      card.appendChild(meta);
      resultEl.appendChild(card);
    }
    if (typeof loadPGallery === "function") loadPGallery();
  } catch (err) {
    clearInterval(timer);
    if (statusEl) { statusEl.className = "err"; statusEl.textContent = "✗ " + (err.message || err); }
    pLog(`✗ Single Prompt ${modeLbl} render failed: ${err.message || err}`, true);
  } finally {
    if (btnImg) btnImg.disabled = false;
    if (btnVid) btnVid.disabled = false;
  }
}

(function initPRefTools() {
  const selCast = $("pCastRef");
  const btnAddRef = $("bPRefAdd");
  const btnReload = $("bPCastRefReload");
  const btnUpload = $("bPRefUpload");
  const fileIn = $("pRefFile");
  const btnClear = $("bPRefClear");
  const btnGenImg = $("bPRefGenImg");
  const btnGenVid = $("bPRefGenVid");

  if (selCast) {
    selCast.addEventListener("change", () => {
      const val = selCast.value;
      if (val) {
        const found = pCastRefsList.find(r => r.rel_path === val);
        if (pRefStackItems.length === 0) {
          pUploadedRefDataUrl = "";
          if (fileIn) fileIn.value = "";
          updatePRefPreview(found ? (found.url + "?t=" + Date.now()) : "", found ? `Active reference: ${found.label}` : "");
        }
      } else if (!pUploadedRefDataUrl && pRefStackItems.length === 0) {
        updatePRefPreview("", "");
      }
    });
  }
  if (btnAddRef && selCast) {
    btnAddRef.addEventListener("click", () => {
      const val = selCast.value;
      if (!val) return;
      if (pRefStackItems.some(x => x.rel_path === val)) return;
      const found = pCastRefsList.find(r => r.rel_path === val);
      pRefStackItems.push({
        kind: "rel",
        rel_path: val,
        label: found ? found.label : val.split("/").pop(),
        url: found ? (found.url + "?t=" + Date.now()) : "",
      });
      selCast.value = "";
      renderPRefStack();
    });
  }
  if (btnReload) btnReload.addEventListener("click", () => loadPCastRefs());
  if (btnUpload && fileIn) {
    btnUpload.addEventListener("click", () => fileIn.click());
    fileIn.addEventListener("change", () => {
      const files = [...(fileIn.files || [])];
      if (!files.length) return;
      files.forEach(f => {
        const reader = new FileReader();
        reader.onload = () => {
          const dataUrl = String(reader.result || "");
          pRefStackItems.push({
            kind: "b64",
            dataUrl,
            label: f.name,
            url: dataUrl,
          });
          pUploadedRefDataUrl = "";
          renderPRefStack();
        };
        reader.readAsDataURL(f);
      });
      fileIn.value = "";
    });
  }
  if (btnClear) {
    btnClear.addEventListener("click", () => {
      pUploadedRefDataUrl = "";
      pRefStackItems = [];
      if (fileIn) fileIn.value = "";
      if (selCast) selCast.value = "";
      renderPRefStack();
      updatePRefPreview("", "");
    });
  }
  if (btnGenImg) btnGenImg.addEventListener("click", () => runPRefGenerate("image"));
  if (btnGenVid) btnGenVid.addEventListener("click", () => runPRefGenerate("video"));

  // Style Gallery controls inside Single Prompts
  const selStyle = $("pStyleSel");
  const btnStyleToggle = $("bPStyleGalleryToggle");
  const galleryPanel = $("pStyleGalleryPanel");
  const styleSearch = $("pStyleSearch");
  const btnStyleClear = $("bPStyleClear");
  const btnStyleAppend = $("bPStyleAppend");
  if (selStyle) {
    selStyle.addEventListener("change", () => updatePStylePreview());
  }
  if (btnStyleToggle && galleryPanel) {
    btnStyleToggle.addEventListener("click", () => {
      const open = galleryPanel.style.display === "none" || !galleryPanel.style.display;
      galleryPanel.style.display = open ? "block" : "none";
      if (open && !pStylesCatalog.length) {
        loadPStyles();
      } else {
        renderPStyleGallery();
      }
    });
  }
  if (styleSearch) {
    styleSearch.addEventListener("input", () => renderPStyleGallery());
  }
  if (btnStyleClear) {
    btnStyleClear.addEventListener("click", () => selectPStyle(""));
  }
  if (btnStyleAppend) {
    btnStyleAppend.addEventListener("click", () => {
      const sid = selStyle ? selStyle.value.trim() : "";
      const style = sid ? pStylesCatalog.find(s => s.id === sid) : null;
      if (!style) return;
      const ptext = $("ptext");
      if (ptext && style.positives) {
        const curText = ptext.value.trim();
        if (!curText) {
          ptext.value = style.positives;
        } else if (!curText.toLowerCase().includes(style.positives.slice(0, 32).toLowerCase())) {
          ptext.value = curText.split(/\r?\n/).map(line => line.trim() ? `${line.trim()}, ${style.positives}` : line).join("\n");
        }
        ptext.focus();
      }
      const pneg = $("pneg");
      if (pneg && style.negatives && !pneg.value.trim()) {
        pneg.value = style.negatives;
      }
      if ($("pRefStatus")) {
        $("pRefStatus").className = "chip done";
        $("pRefStatus").textContent = `✓ Inserted "${style.name || style.label || style.id}" keywords into prompt.`;
      }
    });
  }

  const projSel = $("proj");
  if (projSel) projSel.addEventListener("change", () => loadPCastRefs());
  document.querySelectorAll('#tab-prompts, [data-tab="prompts"], [data-target="panel-prompts"]').forEach(btn => {
    btn.addEventListener("click", () => { loadPCastRefs(); loadPStyles(); });
  });

  setTimeout(() => { loadPCastRefs(); loadPStyles(); }, 400);
})();

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
