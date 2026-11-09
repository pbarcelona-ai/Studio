// studio/film.js - Make my film, Kaggle/Cleanup tools, blockers, Kaggle runs, film from downloaded files
// Classic script: shares globals with the other studio/*.js files; load order is set in index.html.
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
