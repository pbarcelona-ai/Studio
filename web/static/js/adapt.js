// studio/adapt.js - the "Film plan and screenplay" card: the scene plan, pilot choice, budget preview, and the screenplay editor with its approval.
// Classic script: uses $, api and cur() from core.js. core.js's renderProject() calls loadAdaptation(p). Server side: studio_app/adapt.py.
let adaptData = null, adaptTimer = null;

function aEl(tag, text, cls) { const e = document.createElement(tag); if (text !== undefined && text !== null) e.textContent = text; if (cls) e.className = cls; return e; }
function aBtn(text, fn, cls = "btn btn--ghost", label) { const b = aEl("button", text, cls); b.type = "button"; if (label) b.setAttribute("aria-label", label); b.addEventListener("click", fn); return b; }
function aErr(e) { $("adaptNote").textContent = e.message || String(e); }

function loadAdaptation(p) {
  clearTimeout(adaptTimer);
  adaptTimer = setTimeout(() => adaptFetch(p || cur()), 250);          // renderProject runs often; one request per burst
}

async function adaptFetch(p) {
  const note = $("adaptNote");
  if (!p || p.legacy || p.not_started || !p.chapters) {
    adaptData = null; $("adaptPlan").classList.add("hidden");
    note.textContent = !p ? "Pick a book first." : p.legacy ? "Imported books keep their own chapters and shots." : "Read the book first (Read book card), then plan the film here.";
    return;
  }
  try { adaptData = await api(`/api/adaptation?project=${encodeURIComponent(p.slug)}`); } catch (e) { return aErr(e); }
  adaptRender();
}

function adaptRender() {
  const d = adaptData;
  if (!d || !d.exists) {
    $("adaptPlan").classList.add("hidden");
    $("adaptNote").textContent = d ? `No film plan yet for this book (${d.chapters} chapters). Tick "Plan the film", choose the length, and press Import. Without a plan the film is made chapter by chapter, as before.` : "";
    return;
  }
  const plan = d.plan, rt = d.runtime;
  $("adaptPlan").classList.remove("hidden");
  $("adaptNote").textContent = plan.stale ? "The chapters were changed after this plan was made. Plan the film again before writing shots." : "";
  $("adaptLogline").textContent = `${plan.logline} Ends: ${plan.ending}`;
  const off = Math.abs(rt.difference_seconds) >= plan.clip_seconds;
  $("adaptRuntime").textContent = `${plan.scenes.length} scenes, ${d.active_clips} clips to make now (${rt.minutes} min planned of ${plan.runtime_minutes} min asked${off ? "; you changed the clip counts, so the length moved" : ""}).` +
    (plan.cut.length ? ` Left out: ${plan.cut.length} (chapters or scenes; see adaptation/treatment.md).` : "") +
    (plan.pilot && plan.pilot.kind !== "none" ? ` PILOT: only ${plan.pilot.scene_ids.length} scenes are made (${plan.pilot.kind}).` : "");
  adaptScenes(plan);
  $("pilotKind").value = (plan.pilot && plan.pilot.kind) || "none"; pilotShow();
  adaptBudget();
  spLoad();
  lockLoad();
  gradeLoad();
}

function adaptScenes(plan) {
  const t = $("adaptScenes"); t.textContent = "";
  const head = aEl("tr"); ["Scene", "Title", "Act", "Chapters", "Clips", "Seconds", "What happens", "Actions"].forEach(h => head.appendChild(aEl("th", h)));
  const th = aEl("thead"); th.appendChild(head); t.appendChild(th);
  const body = aEl("tbody");
  const inPilot = new Set((plan.pilot && plan.pilot.scene_ids) || []);
  const pilotOn = plan.pilot && plan.pilot.kind !== "none";
  plan.scenes.forEach((s, i) => {
    const tr = aEl("tr"); if (pilotOn && !inPilot.has(s.id)) tr.style.opacity = "0.5";
    const title = aEl("input"); title.type = "text"; title.value = s.title; title.maxLength = 100; title.style.width = "100%"; title.setAttribute("aria-label", `Title of scene ${s.id}`);
    title.addEventListener("change", () => adaptDo({ action: "rename", id: s.id, title: title.value }));
    const clips = aEl("input"); clips.type = "number"; clips.min = 1; clips.max = 10000; clips.value = s.clips; clips.style.width = "70px"; clips.setAttribute("aria-label", `Clips in scene ${s.id}`);
    clips.addEventListener("change", () => adaptDo({ action: "set_clips", id: s.id, clips: Number(clips.value) }));
    const acts = aEl("td"); acts.className = "actions-col";
    if (i > 0) acts.appendChild(aBtn("Up", () => adaptDo({ action: "move", id: s.id, direction: -1 }), undefined, `Move scene ${s.id} up`));
    if (i + 1 < plan.scenes.length) {
      acts.appendChild(aBtn("Down", () => adaptDo({ action: "move", id: s.id, direction: 1 }), undefined, `Move scene ${s.id} down`));
      acts.appendChild(aBtn("Join next", () => { if (confirm("Join this scene with the next one? Its screenplay is written again.")) adaptDo({ action: "merge", id: s.id }); }, undefined, `Join scene ${s.id} with the next`));
    }
    acts.appendChild(aBtn("Drop", () => { if (confirm(`Leave out scene ${s.id}, "${s.title}"?`)) adaptDo({ action: "drop", id: s.id }); }, undefined, `Drop scene ${s.id}`));
    const tdT = aEl("td"); tdT.appendChild(title); const tdC = aEl("td"); tdC.appendChild(clips);
    [aEl("td", s.id), tdT, aEl("td", s.act), aEl("td", s.chapters.join(", ")), tdC, aEl("td", s.seconds),
     aEl("td", s.summary + (s.anchor_found === false ? " (starting phrase not found in the book: check)" : "")), acts].forEach(td => tr.appendChild(td));
    body.appendChild(tr);
  });
  t.appendChild(body);
}

async function adaptDo(body) {
  const p = cur(); if (!p) return;
  try { adaptData = await api("/api/adaptation_edit", { project: p.slug, ...body }); await loadStatus(); adaptRender(); } catch (e) { aErr(e); adaptFetch(p); }
}

function pilotShow() {
  const k = $("pilotKind").value;
  $("pilotSecBox").classList.toggle("hidden", k !== "trailer"); $("pilotChBox").classList.toggle("hidden", k !== "chapters");
}
$("pilotKind").addEventListener("change", pilotShow);
$("pilotApply").addEventListener("click", () => adaptDo({ action: "set_pilot", kind: $("pilotKind").value, seconds: Number($("pilotSeconds").value), first: Number($("pilotFirst").value), last: Number($("pilotLast").value) }));
$("adaptDiscard").addEventListener("click", () => { if (confirm("Delete the film plan and its screenplay (including your edits)? The chapters stay.")) adaptDo({ action: "discard" }); });

// ---- budget: priced for the video model, service and GPU chosen on the Models tab
async function adaptBudget() {
  const p = cur(); if (!p) return;
  try {
    const r = await api("/api/budget", { project: p.slug, model: (checked("vmodel")[0] || "ltx_video_fast_i2v"), service: radio("svc") || "kaggle", gpu: $("gpu").value || "NvidiaTeslaT4" });
    $("adaptBudget").textContent = r.text;
  } catch (e) { $("adaptBudget").textContent = e.message; }
}

// ---- screenplay: each scene as lines "A: ...", "D NAME (note): ...", "T: ..."
function spToLines(els) {
  return els.map(e => e.type === "dialogue" ? `D ${e.character}${e.note ? ` (${e.note})` : ""}: ${e.text}` : `${e.type === "transition" ? "T" : "A"}: ${e.text}`).join("\n");
}
function spFromLines(text) {
  const els = [];
  for (const raw of text.split("\n")) {
    const line = raw.trim(); if (!line) continue;
    let m;
    if ((m = line.match(/^A:\s*(.+)$/))) els.push({ type: "action", text: m[1] });
    else if ((m = line.match(/^T:\s*(.+)$/))) els.push({ type: "transition", text: m[1] });
    else if ((m = line.match(/^D\s+([^():]+?)\s*(?:\(([^)]*)\))?\s*:\s*(.+)$/))) els.push({ type: "dialogue", character: m[1], note: m[2] || undefined, text: m[3] });
    else throw new Error(`I cannot read this line (start it with A:, D NAME: or T:): ${line.slice(0, 60)}`);
  }
  return els;
}

async function spLoad() {
  const p = cur(); if (!p) return;
  let r;
  try { r = await api(`/api/screenplay?project=${encodeURIComponent(p.slug)}`); } catch (e) { return aErr(e); }
  const st = r.status;
  $("spState").textContent = st.approved ? `approved ${st.approved_at || ""}` : `${st.written} of ${st.total} scenes written, not approved`;
  $("spState").className = "chip" + (st.approved ? " done" : "");
  const flags = r.flags || {}, nflag = Object.values(flags).reduce((a, v) => a + v.length, 0);
  $("spApprove").disabled = st.approved && !nflag || st.missing.length > 0 || nflag > 0; $("spUnapprove").disabled = !st.approved;
  $("spFlagNote").textContent = nflag ? `The storyboard changed ${nflag} shot(s). The scenes they came from have a red outline: change the scene to match, or press "Keep it", then approve again.` : "";
  $("spFlagNote").classList.toggle("hidden", !nflag);
  const box = $("spScenes");
  const wasOpen = new Set([...box.querySelectorAll("details[open]")].map(d => d.dataset.id));      // keep the scenes you are reading open
  box.textContent = "";
  r.scenes.forEach(s => {
    const det = aEl("details"); det.dataset.id = s.id; det.open = wasOpen.has(s.id); det.appendChild(aEl("summary", `${s.id} ${s.title} (${s.seconds} s)${s.screenplay ? "" : " - not written yet"}`));
    det.appendChild(aEl("p", s.summary, "warn"));
    if (flags[s.id]) {                          // changed later, in the storyboard: show what changed, and let it be kept as it is
      det.classList.add("sp-flagged"); det.open = true;
      const box = aEl("div", "", "sp-flag");
      box.appendChild(aEl("strong", "Changed in the storyboard:"));
      const ul = aEl("ul");
      flags[s.id].forEach(f => ul.appendChild(aEl("li", f.kind === "moved" ? `shot ${f.n} was moved (${f.old}, ${f.new})` : `shot ${f.n}, ${f.field}: "${f.old}" became "${f.new}"`)));
      box.appendChild(ul);
      box.appendChild(aBtn("Keep it (the screenplay is fine as it is)", async () => {
        try { await api("/api/feedback_keep", { project: p.slug, scene: s.id }); spLoad(); } catch (e) { aErr(e); }
      }, "btn btn--ghost"));
      det.appendChild(box);
    }
    const head = aEl("input"); head.type = "text"; head.maxLength = 120; head.style.width = "100%"; head.value = s.screenplay ? s.screenplay.heading : ""; head.placeholder = "INT. PLACE - TIME";
    head.setAttribute("aria-label", `Scene heading of ${s.id}`);
    const ta = aEl("textarea"); ta.rows = 8; ta.style.width = "100%"; ta.spellcheck = false; ta.value = s.screenplay ? spToLines(s.screenplay.elements) : ""; ta.setAttribute("aria-label", `Screenplay of ${s.id}`);
    const msg = aEl("small", "", "warn");
    det.appendChild(head); det.appendChild(ta);
    det.appendChild(aBtn("Save this scene", async () => {
      try {
        await api("/api/screenplay_edit", { project: p.slug, action: "save_scene", scene: s.id, heading: head.value, elements: spFromLines(ta.value) });
        msg.textContent = "Saved. The approval was taken away; approve again when you have read it all."; await loadStatus(); spLoad();
      } catch (e) { msg.textContent = e.message; }
    }, "btn btn--secondary"));
    det.appendChild(msg);
    box.appendChild(det);
  });
}

$("spApprove").addEventListener("click", async () => {
  const p = cur(); if (!p) return;
  try { await api("/api/screenplay_edit", { project: p.slug, action: "approve" }); await loadStatus(); spLoad(); } catch (e) { aErr(e); }
});
$("spUnapprove").addEventListener("click", async () => {
  const p = cur(); if (!p) return;
  try { await api("/api/screenplay_edit", { project: p.slug, action: "unapprove" }); await loadStatus(); spLoad(); } catch (e) { aErr(e); }
});

// ---- locked cast, costume and place per scene
async function lockLoad() {
  const p = cur(); if (!p) return;
  let r;
  try { r = await api(`/api/cast_lock?project=${encodeURIComponent(p.slug)}`); } catch (e) { return aErr(e); }
  const sm = r.summary;
  $("lockState").textContent = sm.characters || sm.locations ? `${sm.characters} costume(s), ${sm.locations} place(s) locked` : "nothing locked";
  const box = $("lockScenes");
  const wasOpen = new Set([...box.querySelectorAll("details[open]")].map(d => d.dataset.id));
  box.textContent = "";
  r.scenes.forEach(s => {
    const det = aEl("details"); det.dataset.id = s.id; det.open = wasOpen.has(s.id);
    det.appendChild(aEl("summary", `${s.id} ${s.title}${s.characters.some(c => c.locked.token || c.locked.reference) || s.place.locked.reference ? " - locked" : ""}`));
    const msg = aEl("small", "", "warn");
    const send = async (body, done) => { try { await api("/api/cast_lock", { project: p.slug, scene: s.id, ...body }); msg.textContent = done; await lockLoad(); } catch (e) { msg.textContent = e.message; } };
    if (!s.characters.length) det.appendChild(aEl("p", "No character of the continuity book is named in this scene.", "warn"));
    s.characters.forEach(c => {
      det.appendChild(aEl("strong", c.name));
      const ta = aEl("textarea"); ta.rows = 3; ta.style.width = "100%"; ta.maxLength = 400; ta.value = c.locked.token || c.current; ta.setAttribute("aria-label", `Description of ${c.name} in scene ${s.id}`);
      const sel = aEl("select"); sel.setAttribute("aria-label", `Reference picture of ${c.name} in scene ${s.id}`);
      sel.appendChild(new Option("(usual picture)", ""));
      c.references.forEach(ref => sel.appendChild(new Option(ref.split("/").slice(-2).join("/"), ref)));
      sel.value = c.locked.reference || "";
      det.appendChild(ta); det.appendChild(sel);
      det.appendChild(aBtn("Lock", () => send({ kind: "character", name: c.name, token: ta.value.trim() === c.current && !c.locked.token ? "" : ta.value, reference: sel.value }, `${c.name} locked for ${s.id}.`), "btn btn--secondary"));
      det.appendChild(aBtn("Unlock", () => send({ kind: "character", name: c.name }, `${c.name} unlocked for ${s.id}.`)));
    });
    const place = aEl("select"); place.setAttribute("aria-label", `Place picture of scene ${s.id}`);
    place.appendChild(new Option(`(usual picture of ${s.location || "the place"})`, ""));
    s.place.references.forEach(ref => place.appendChild(new Option(ref.split("/").slice(-1)[0], ref)));
    place.value = s.place.locked.reference || "";
    det.appendChild(aEl("strong", "Place")); det.appendChild(place);
    det.appendChild(aBtn("Lock place", () => send({ kind: "location", reference: place.value }, place.value ? "Place locked." : "Place unlocked."), "btn btn--secondary"));
    det.appendChild(msg);
    box.appendChild(det);
  });
}

// ---- colour grade per scene
async function gradeLoad() {
  const p = cur(); if (!p) return;
  let r;
  try { r = await api(`/api/grading?project=${encodeURIComponent(p.slug)}`); } catch (e) { return aErr(e); }
  const box = $("gradeScenes"); box.textContent = "";
  const row = (id, label, g) => {
    const wrap = aEl("div", undefined, "row"); wrap.style.cssText = "gap:8px;align-items:center;flex-wrap:wrap;margin:4px 0";
    wrap.appendChild(aEl("strong", label));
    const preset = aEl("select"); preset.setAttribute("aria-label", `Look of ${label}`);
    r.presets.forEach(x => preset.appendChild(new Option(x.replace(/_/g, " "), x))); preset.value = g.preset || "none";
    const num = (key, lab, step) => {
      const i = aEl("input"); i.type = "number"; i.step = step; i.min = r.limits[key][0]; i.max = r.limits[key][1]; i.style.width = "80px"; i.value = g[key] !== undefined ? g[key] : "";
      i.placeholder = lab; i.setAttribute("aria-label", `${lab} of ${label}`); return i;
    };
    const temp = num("temperature", "warmth", 0.05), sat = num("saturation", "saturation", 0.05), exp = num("exposure", "exposure", 0.02);
    const msg = aEl("small", "", "warn");
    const save = async spec => { try { await api("/api/grading", { project: p.slug, scene: id, grade: spec }); msg.textContent = "Saved."; } catch (e) { msg.textContent = e.message; } };
    wrap.append(preset, temp, sat, exp,
      aBtn("Save", () => { const spec = { preset: preset.value }; [["temperature", temp], ["saturation", sat], ["exposure", exp]].forEach(([k, el]) => { if (el.value !== "") spec[k] = Number(el.value); }); save(spec); }, "btn btn--secondary"),
      aBtn("Clear", () => { preset.value = "none"; temp.value = sat.value = exp.value = ""; save({}); }), msg);
    box.appendChild(wrap);
  };
  row("default", "Whole film", r.default || {});
  r.scenes.forEach(s => row(s.id, `${s.id} ${s.title}`, s.grade || {}));
}
