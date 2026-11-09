// studio/models.js - look and suggested models, timeline, upscalers
// Classic script: shares globals with the other studio/*.js files; load order is set in index.html.
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
$("newSceneSeries").onchange = () => populateNewSceneChapters();     // called later: the function is defined in characters.js
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
$("bDirSend").onclick = () => dirSend();  // defined in direction.js, which loads after this file
$("bDirClear").onclick = () => dirClear();  // defined in direction.js, which loads after this file
$("bDirFollowup").onclick = () => dirFollowup();  // defined in direction.js, which loads after this file
// Allow Enter key in dirNotes to send (Shift+Enter for newline)
$("dirNotes").addEventListener("keydown", e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); dirSend(); } });
$("dirFollowup").addEventListener("keydown", e => { if (e.key === "Enter") { e.preventDefault(); dirFollowup(); } });

$("fvideo").onchange = () => { chooseFilmAudio(); renderFilmTable(); };
for (const [, id] of FILM_KINDS) $(id).onchange = renderFilmTable; $("bRuns").onclick = () => loadRuns(false); $("bFetch").onclick = () => loadRuns(true); $("bStop").onclick = () => api("/api/stop", {});
try { $("kuser").value = localStorage.getItem("kaggle_user") || ""; $("engine").value = localStorage.getItem("engine") || "claude"; $("cmodel").value = localStorage.getItem("claude_model") ?? "sonnet"; } catch (e) {}
$("kuser").addEventListener("change", () => { try { localStorage.setItem("kaggle_user", $("kuser").value); } catch (e) {} });
$("cmodel").addEventListener("change", () => { try { localStorage.setItem("claude_model", $("cmodel").value); } catch (e) {} });
$("engine").addEventListener("change", () => { try { localStorage.setItem("engine", $("engine").value); localStorage.setItem("claude_model", $("cmodel").value); } catch (e) {} });
