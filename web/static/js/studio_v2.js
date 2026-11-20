// studio_v2.js - Studio v2 Architecture: 22-Step Guided Pipeline + Creative Workbench,
// Strict Top-to-Bottom Flow (Zero Cards Below Approve), Direct Story Input Saving,
// Audio Redo, Storyline Drift Sync, Chapter Editing in Flow, and Autopilot Model Recommendations.

(function () {
  "use strict";

  // ===== COMPLETE 22-STEP GUIDED FLOW =====
  const V2_STEPS = [
    // Phase 1: Story & Script
    { num: 1, id: "ingest", name: "01 Ingest", title: "Story Ingest & Source", phase: 1, phaseName: "Story & Script" },
    { num: 2, id: "chapters", name: "02 Chapters", title: "Check & Split Chapters", phase: 1, phaseName: "Story & Script" },
    { num: 3, id: "coverage", name: "03 Coverage", title: "Coverage & Logline", phase: 1, phaseName: "Story & Script" },
    { num: 4, id: "format", name: "04 Scope", title: "Format & Runtime Scope", phase: 1, phaseName: "Story & Script" },
    { num: 5, id: "structure", name: "05 Beats", title: "Story Structure & Beats", phase: 1, phaseName: "Story & Script" },
    { num: 6, id: "screenplay", name: "06 Script", title: "Screenplay Editor (Dialogue Default)", phase: 1, phaseName: "Story & Script" },

    // Phase 2: Cast & World
    { num: 7, id: "continuity", name: "07 Continuity", title: "Continuity & World Rules", phase: 2, phaseName: "Cast & World" },
    { num: 8, id: "cast", name: "08 Cast", title: "Cast & Characters", phase: 2, phaseName: "Cast & World" },
    { num: 9, id: "look", name: "09 Style", title: "Art Direction & Style Recipe", phase: 2, phaseName: "Cast & World" },
    { num: 10, id: "lookdev", name: "10 Turnaround", title: "Look Development & Turnarounds", phase: 2, phaseName: "Cast & World" },
    { num: 11, id: "locations", name: "11 Sets", title: "Locations & Environment Sets", phase: 2, phaseName: "Cast & World" },

    // Phase 3: Cinematography & Hardware
    { num: 12, id: "shots", name: "12 Shots", title: "Shot List & Cinematography", phase: 3, phaseName: "Camera & Compute" },
    { num: 13, id: "hardware", name: "13 Hardware", title: "Hardware & Where to Run", phase: 3, phaseName: "Camera & Compute" },

    // Phase 4: Audio & Voices
    { num: 14, id: "voices", name: "14 Voice Cast", title: "Voice Casting & Dialects", phase: 4, phaseName: "Audio & Voices" },
    { num: 15, id: "dialogue", name: "15 Dialogue", title: "Spoken Dialogue Delivery", phase: 4, phaseName: "Audio & Voices" },
    { num: 16, id: "score", name: "16 Score & Foley", title: "Cinematic Score & Foley Sound Design", phase: 4, phaseName: "Audio & Voices" },

    // Phase 5: Visuals & Motion
    { num: 17, id: "keyframes", name: "17 Keyframes", title: "Storyboard Keyframes (FLUX/SDXL)", phase: 5, phaseName: "Visuals & Motion" },
    { num: 18, id: "video", name: "18 Video", title: "Motion & Video Synthesis (Wan 2.1)", phase: 5, phaseName: "Visuals & Motion" },
    { num: 19, id: "polish", name: "19 Polish", title: "Lip-Sync & Real-ESRGAN Polish", phase: 5, phaseName: "Visuals & Motion" },

    // Phase 6: Post & Premiere
    { num: 20, id: "timeline", name: "20 Timeline", title: "Sequence Timeline Assembly", phase: 6, phaseName: "Post & Premiere" },
    { num: 21, id: "mix", name: "21 Audio Mix", title: "Stem Audio Mix (-16 LUFS)", phase: 6, phaseName: "Post & Premiere" },
    { num: 22, id: "premiere", name: "22 Premiere", title: "Cinema Premiere & Multi-Format Export", phase: 6, phaseName: "Post & Premiere" },
  ];

  let currentStep = 1;
  let activeProject = "";

  function $(id) {
    return document.getElementById(id);
  }

  async function callApi(url, body) {
    if (typeof window.api === "function") {
      return window.api(url, body);
    }
    const token = (document.querySelector('meta[name="studio-token"]') || {}).content || "";
    const headers = { "Content-Type": "application/json" };
    if (token && token !== "__TOKEN__") headers["X-Studio-Token"] = token;
    const opts = body !== undefined ? {
      method: "POST",
      headers,
      body: JSON.stringify(body)
    } : { method: "GET", headers };
    const r = await fetch(url, opts);
    const j = await r.json();
    if (!r.ok) throw new Error(j.error || j.detail || j.message || r.statusText);
    return j;
  }

  // ===== DIRECT STORY INPUT BOX SAVING =====
  function initDirectStoryInput() {
    const btnSave = $("bSaveStory");
    const inputFn = $("storyFilename");
    const inputText = $("storyInputText");
    const statusMsg = $("storySaveStatus");

    if (!btnSave || !inputFn || !inputText) return;

    btnSave.addEventListener("click", async () => {
      const text = inputText.value.trim();
      let filename = inputFn.value.trim();

      if (!text) {
        alert("Please enter or paste your story text first.");
        inputText.focus();
        return;
      }

      if (!filename) {
        filename = prompt("Enter a filename for your story (saved to books/<filename>.txt):", "my_story.txt") || "";
        filename = filename.trim();
        if (!filename) return;
        inputFn.value = filename;
      }

      btnSave.disabled = true;
      if (statusMsg) {
        statusMsg.textContent = "Saving story to books/" + filename + "…";
        statusMsg.className = "status-badge status-badge--working";
      }

      try {
        const res = await callApi("/api/save_story", { filename, text });
        if (statusMsg) {
          statusMsg.textContent = `✓ Saved to books/${res.filename} (${res.bytes} characters)`;
          statusMsg.className = "status-badge status-badge--synced";
        }

        // Auto-refresh the book dropdown if present
        const selProj = $("proj");
        if (selProj) {
          const optSlug = res.filename.replace(/\.[^/.]+$/, "");
          let found = false;
          for (let i = 0; i < selProj.options.length; i++) {
            if (selProj.options[i].value === optSlug || selProj.options[i].text.includes(optSlug)) {
              selProj.selectedIndex = i;
              found = true;
              break;
            }
          }
          if (!found) {
            const opt = document.createElement("option");
            opt.value = optSlug;
            opt.text = res.filename;
            opt.selected = true;
            selProj.add(opt);
          }
          selProj.dispatchEvent(new Event("change"));
        }
      } catch (err) {
        if (statusMsg) {
          statusMsg.textContent = "Error saving story: " + err.message;
          statusMsg.className = "status-badge status-badge--drift";
        }
        alert("Could not save story: " + err.message);
      } finally {
        btnSave.disabled = false;
      }
    });
  }

  // ===== NAVIGATION & TOP-TO-BOTTOM STEP CONTROLLER =====
  function activateStep(stepNum) {
    currentStep = Math.max(1, Math.min(V2_STEPS.length, stepNum));

    // Ensure we are in pipeline mode so zero legacy cards render below the approve button
    document.body.classList.remove("mode-workbench");
    document.body.classList.add("mode-pipeline");

    // Update Step Pills
    document.querySelectorAll(".step-pill").forEach(pill => {
      const pNum = parseInt(pill.dataset.step, 10);
      const isCurrent = pNum === currentStep;
      const isDone = pNum < currentStep;
      pill.classList.toggle("active", isCurrent);
      pill.classList.toggle("done", isDone);
      pill.setAttribute("aria-selected", String(isCurrent));
    });

    // Update Step Panels
    document.querySelectorAll(".step-panel").forEach(panel => {
      const pNum = parseInt(panel.dataset.step, 10);
      const isCurrent = pNum === currentStep;
      panel.classList.toggle("active", isCurrent);
      panel.setAttribute("aria-hidden", String(!isCurrent));
    });

    // Update Phase Highlights
    document.querySelectorAll(".phase-group").forEach(group => {
      const phaseNum = parseInt(group.dataset.phase, 10);
      const stepMeta = V2_STEPS.find(s => s.num === currentStep);
      group.classList.toggle("phase-active", stepMeta && stepMeta.phase === phaseNum);
    });

    // Top-to-bottom rule: Always scroll to top of page when changing steps
    window.scrollTo({ top: 0, behavior: "smooth" });

    // Save step progress to localStorage
    try {
      localStorage.setItem("studio_v2_active_step", String(currentStep));
    } catch (e) {}

    // If entering Step 2 (Chapters), load chapter data
    if (currentStep === 2 && typeof window.loadChapters === "function") {
      try { window.loadChapters(); } catch (e) {}
    }

    // If entering Step 3 (Coverage & Logline), load active book's coverage
    if (currentStep === 3) {
      loadV2Coverage();
    }

    // If entering Step 4 (Format & Runtime Scope), load dynamic book-based scope options
    if (currentStep === 4) {
      loadV2Scope();
    }

    // If entering Step 5 (Story Structure & Beats), load full beat sheet & scene breakdown
    if (currentStep === 5) {
      loadV2StoryBreakdown();
    }

    // If entering Step 6 (Screenplay), load all screenplay scenes
    if (currentStep === 6) {
      loadV2Screenplay();
    }

    // If entering Step 7 (Continuity & World Rules), load rules, lighting/palette, and scene locks
    if (currentStep === 7) {
      loadV2Continuity();
    }

    // Check for storyline drift and load step autopilot
    checkStepStorylineDrift();
    loadStepAutopilot();
  }

  // ===== STEP 03: COVERAGE & LOGLINE =====
  async function loadV2Coverage() {
    const selProj = $("proj");
    const slug = (selProj && selProj.value) || activeProject || "";
    const loglineEl = $("v2Logline");
    const synopsisEl = $("v2Synopsis");
    const metaEl = $("v2CovMeta");
    const badgeEl = $("v2CovBadge");
    const extraEl = $("v2CovExtra");

    if (!loglineEl || !synopsisEl) return;

    // Immediately clear previous book's values so stale text never persists
    loglineEl.value = "";
    synopsisEl.value = "";
    if (extraEl) {
      extraEl.textContent = "";
      extraEl.classList.add("hidden");
    }

    if (!slug) {
      if (metaEl) metaEl.textContent = "Pick or save a book in Step 01 first.";
      if (badgeEl) {
        badgeEl.textContent = "No Book Selected";
        badgeEl.className = "status-badge status-badge--drift";
      }
      return;
    }

    if (metaEl) metaEl.textContent = `Loading coverage for "${slug}"…`;
    if (badgeEl) {
      badgeEl.textContent = "Loading…";
      badgeEl.className = "status-badge status-badge--working";
    }

    let readin = null, adapt = null;
    try { readin = await callApi(`/api/readin?project=${encodeURIComponent(slug)}`); } catch (e) {}
    try { adapt = await callApi(`/api/adaptation?project=${encodeURIComponent(slug)}`); } catch (e) {}

    const cov = readin && readin.coverage ? readin.coverage : null;
    const plan = adapt && adapt.exists ? adapt.plan : null;

    if (cov && (cov.logline || cov.genre || (cov.key_events && cov.key_events.length))) {
      loglineEl.value = cov.logline || (plan && plan.logline) || "";
      const synParts = [];
      if (readin && readin.treatment && readin.treatment.trim()) {
        synParts.push(readin.treatment.trim().slice(0, 1200));
      } else if (Array.isArray(cov.key_events) && cov.key_events.length) {
        synParts.push("Key Events:\n" + cov.key_events.map(e => `• ${e}`).join("\n"));
      } else if (plan && plan.ending) {
        synParts.push(`Ending: ${plan.ending}`);
      }
      synopsisEl.value = synParts.join("\n\n");

      const metaBits = [`Book: ${slug}`];
      if (cov.genre) metaBits.push(`Genre: ${cov.genre}`);
      if (cov.tone) metaBits.push(`Tone: ${cov.tone}`);
      if (cov.length) metaBits.push(`Target: ${cov.length}`);
      if (metaEl) metaEl.textContent = metaBits.join(" · ");

      if (extraEl) {
        const extras = [];
        if (Array.isArray(cov.themes) && cov.themes.length) {
          extras.push(`<div><strong style="color:#f59e0b">Themes:</strong> ${cov.themes.join(", ")}</div>`);
        }
        if (Array.isArray(cov.characters) && cov.characters.length) {
          extras.push(`<div><strong style="color:#f59e0b">Key Characters:</strong> ${cov.characters.map(c => `${c.name}${c.role ? ` (${c.role})` : ""}`).join(", ")}</div>`);
        }
        if (cov.filmable) {
          extras.push(`<div><strong style="color:#f59e0b">Filmability Notes:</strong> ${cov.filmable}</div>`);
        }
        if (extras.length) {
          extraEl.innerHTML = extras.join("");
          extraEl.classList.remove("hidden");
        }
      }

      if (badgeEl) {
        badgeEl.textContent = "✓ Coverage Loaded";
        badgeEl.className = "status-badge status-badge--synced";
      }
      return;
    }

    if (plan && (plan.logline || (plan.scenes && plan.scenes.length))) {
      loglineEl.value = plan.logline || "";
      const lines = [];
      if (plan.ending) lines.push(`Ending: ${plan.ending}`);
      if (Array.isArray(plan.scenes) && plan.scenes.length) {
        lines.push("Scenes Overview:\n" + plan.scenes.slice(0, 8).map(s => `• ${s.id} ${s.title}: ${s.summary || ""}`).join("\n"));
      }
      synopsisEl.value = lines.join("\n\n");
      if (metaEl) metaEl.textContent = `Book: ${slug} · Loaded from Film Plan (${(plan.scenes || []).length} scenes)`;
      if (badgeEl) {
        badgeEl.textContent = "✓ Plan Logline Loaded";
        badgeEl.className = "status-badge status-badge--synced";
      }
      return;
    }

    // No coverage or plan generated yet for this book
    if (metaEl) metaEl.textContent = `Book: "${slug}" — No coverage or logline generated yet. Click ✨ Generate Coverage to analyze this book.`;
    if (badgeEl) {
      badgeEl.textContent = "Not Generated Yet";
      badgeEl.className = "status-badge status-badge--drift";
    }
  }

  function initV2Coverage() {
    const btnReload = $("v2CovReload");
    const btnBuild = $("v2CovBuild");
    if (btnReload) btnReload.addEventListener("click", () => loadV2Coverage());
    if (btnBuild) {
      btnBuild.addEventListener("click", async () => {
        const selProj = $("proj");
        const slug = (selProj && selProj.value) || activeProject || "";
        if (!slug) { alert("Pick or save a book in Step 01 first."); return; }
        btnBuild.disabled = true;
        const metaEl = $("v2CovMeta");
        if (metaEl) metaEl.textContent = `Starting coverage analysis for "${slug}"…`;
        try {
          const o = typeof window.options === "function" ? window.options() : {};
          await callApi("/api/read_it_in", { project: slug, engine: o.engine || "claude", claude_model: o.claude_model });
          if (metaEl) metaEl.textContent = `✓ Coverage job started for "${slug}". Click ↻ Reload in a moment to view results.`;
        } catch (err) {
          if (metaEl) metaEl.textContent = "Could not start coverage: " + err.message;
        } finally {
          btnBuild.disabled = false;
        }
      });
    }

    const selProj = $("proj");
    if (selProj) {
      selProj.addEventListener("change", () => {
        activeProject = selProj.value || "";
        // Always refresh coverage & dynamic scope immediately on book change
        loadV2Coverage();
        loadV2Scope();
      });
    }
  }

  // ===== STEP 04: DYNAMIC BOOK-BASED FORMAT & RUNTIME SCOPE =====
  let v2ScopeChapters = [];
  let v2ScopeTotalWords = 0;

  function roundHalf(n) {
    return Math.max(0.5, Math.round(n * 2) / 2);
  }

  function updateV2ScopeEstimate() {
    const minEl = $("v2CustomMinutes");
    const clipEl = $("v2ClipSec");
    const aspectEl = $("v2Aspect");
    const modeEl = $("v2ScopeMode");
    const fromEl = $("v2ScopeFromCh");
    const toEl = $("v2ScopeToCh");
    const rangeBox = $("v2ScopeRangeBox");
    const estEl = $("v2ScopeEstimate");
    const badgeEl = $("v2ScopeBadge");

    const mode = modeEl ? modeEl.value : "full";
    if (rangeBox) {
      const showRange = mode === "range";
      rangeBox.classList.toggle("hidden", !showRange);
      rangeBox.style.display = showRange ? "flex" : "none";
    }

    const minutes = Math.max(0.5, parseFloat(minEl ? minEl.value : "5") || 5);
    const clipSec = Math.max(1, parseInt(clipEl ? clipEl.value : "5", 10) || 5);
    const aspect = aspectEl ? aspectEl.value : "16:9";
    const clips = Math.max(1, Math.ceil((minutes * 60) / clipSec));

    let scopeLabel = "Full Book";
    if (mode === "pilot_ch1") {
      scopeLabel = "Pilot (Chapter 1 only)";
    } else if (mode === "trailer") {
      scopeLabel = "Trailer / Key Highlights";
    } else if (mode === "range" && fromEl && toEl && fromEl.value && toEl.value) {
      scopeLabel = `Chapters ${fromEl.value}–${toEl.value}`;
    } else if (v2ScopeChapters.length > 0) {
      scopeLabel = `All ${v2ScopeChapters.length} chapter(s)`;
    }

    if (estEl) {
      estEl.textContent = `Estimated Output: ${minutes} min · ~${clips} video clips (at ${clipSec}s/clip) · ${aspect} · Scope: ${scopeLabel}`;
    }
    if (badgeEl) {
      badgeEl.textContent = `✓ ${minutes} min · ${aspect}`;
    }

    // Keep underlying legacy adaptation runtime box synced if present
    const legacyMin = $("adapt_minutes");
    if (legacyMin) legacyMin.value = String(Math.round(minutes));
  }

  function rebuildV2DurationOptions(slug, chapters, savedMinutes) {
    const sel = $("v2Duration");
    const minEl = $("v2CustomMinutes");
    const clipEl = $("v2ClipSec");
    if (!sel) return;

    const clipSec = Math.max(1, parseInt(clipEl ? clipEl.value : "5", 10) || 5);
    const mkClips = m => Math.max(1, Math.ceil((m * 60) / clipSec));
    const totalWords = chapters.reduce((acc, c) => acc + (Number(c.words) || 0), 0);
    v2ScopeChapters = chapters;
    v2ScopeTotalWords = totalWords;

    sel.textContent = "";

    // Group 1: Dynamic options computed directly from the current book's reading
    if (totalWords > 0) {
      const grpBook = document.createElement("optgroup");
      grpBook.label = `Dynamic Options for "${slug}" (${totalWords.toLocaleString()} words)`;

      const readMin = roundHalf(totalWords / 145);          // ~145 wpm spoken reading pace
      const faithfulMin = roundHalf(readMin * 0.7);         // ~70% dramatic adaptation
      const condensedMin = roundHalf(readMin * 0.3);        // ~30% fast-cut highlights
      const dynamicOpts = [
        { val: `book_faithful:${faithfulMin}`, min: faithfulMin, label: `🎬 Faithful Adaptation (~${faithfulMin} min · ~${mkClips(faithfulMin)} clips — 70% of this book)` },
        { val: `book_unabridged:${readMin}`, min: readMin, label: `📖 Unabridged / Full Reading (~${readMin} min · ~${mkClips(readMin)} clips — 100% of ${totalWords.toLocaleString()} words)` },
        { val: `book_condensed:${condensedMin}`, min: condensedMin, label: `⚡ Condensed Highlights (~${condensedMin} min · ~${mkClips(condensedMin)} clips — 30% fast cut)` },
      ];

      if (chapters.length > 1) {
        const epMin = roundHalf(faithfulMin / chapters.length);
        dynamicOpts.push({
          val: `book_episodic:${faithfulMin}`,
          min: faithfulMin,
          label: `📚 Episodic Series (${chapters.length} episodes × ~${epMin} min/ch · ${faithfulMin} min total)`
        });
        const ch1Words = Number(chapters[0].words) || Math.round(totalWords / chapters.length);
        const ch1Min = roundHalf(ch1Words / 145);
        dynamicOpts.push({
          val: `book_ch1:${ch1Min}`,
          min: ch1Min,
          label: `🎯 Chapter 1 Pilot (~${ch1Min} min · ~${mkClips(ch1Min)} clips — "${(chapters[0].title || "Chapter 1").slice(0, 32)}")`
        });
      }

      dynamicOpts.forEach(o => {
        const opt = document.createElement("option");
        opt.value = o.val;
        opt.dataset.minutes = String(o.min);
        opt.textContent = o.label;
        grpBook.appendChild(opt);
      });
      sel.appendChild(grpBook);
    }

    // Group 2: Standard film, short, episode, and feature formats
    const grpStd = document.createElement("optgroup");
    grpStd.label = "Standard Film & Short Formats";
    const stdOpts = [
      { id: "std_trailer", min: 1, label: `Trailer / Teaser (1 min · ~${mkClips(1)} clips)` },
      { id: "std_reel", min: 1.5, label: `Social Short / Reel (90 sec · ~${mkClips(1.5)} clips)` },
      { id: "std_mini", min: 3, label: `Mini-Short (3 min · ~${mkClips(3)} clips)` },
      { id: "std_short", min: 5, label: `Short Film (5 min · ~${mkClips(5)} clips)` },
      { id: "std_ext_short", min: 10, label: `Extended Short (10 min · ~${mkClips(10)} clips)` },
      { id: "std_ep22", min: 22, label: `Half-Hour Episode (22 min · ~${mkClips(22)} clips)` },
      { id: "std_ep45", min: 45, label: `Featurette / TV Hour (45 min · ~${mkClips(45)} clips)` },
      { id: "std_feature90", min: 90, label: `Feature Film (90 min · ~${mkClips(90)} clips)` },
      { id: "std_epic120", min: 120, label: `Epic Feature (120 min · ~${mkClips(120)} clips)` },
      { id: "custom", min: savedMinutes || 5, label: "✂️ Custom Minutes (enter exact runtime below)" },
    ];
    stdOpts.forEach(o => {
      const opt = document.createElement("option");
      opt.value = `${o.id}:${o.min}`;
      opt.dataset.minutes = String(o.min);
      opt.textContent = o.label;
      grpStd.appendChild(opt);
    });
    sel.appendChild(grpStd);

    // Select best default: saved plan minutes if present, otherwise Faithful Adaptation (or 5 min short)
    if (savedMinutes && savedMinutes > 0) {
      if (minEl) minEl.value = String(savedMinutes);
      sel.value = `custom:${savedMinutes}`;
    } else if (sel.options.length > 0) {
      sel.selectedIndex = 0;
      const pickedMin = parseFloat(sel.options[0].dataset.minutes || "5") || 5;
      if (minEl) minEl.value = String(pickedMin);
    }

    // Populate chapter range dropdowns from this book's chapters
    const fromEl = $("v2ScopeFromCh");
    const toEl = $("v2ScopeToCh");
    if (fromEl && toEl) {
      fromEl.textContent = "";
      toEl.textContent = "";
      chapters.forEach(c => {
        const label = `Ch ${c.n}: ${(c.title || "").slice(0, 28)} (${c.words || 0}w)`;
        const o1 = document.createElement("option");
        o1.value = String(c.n);
        o1.textContent = label;
        const o2 = document.createElement("option");
        o2.value = String(c.n);
        o2.textContent = label;
        fromEl.appendChild(o1);
        toEl.appendChild(o2);
      });
      if (chapters.length > 0) {
        fromEl.value = String(chapters[0].n);
        toEl.value = String(chapters[chapters.length - 1].n);
      }
    }

    updateV2ScopeEstimate();
  }

  async function loadV2Scope() {
    const selProj = $("proj");
    const slug = (selProj && selProj.value) || activeProject || "";
    const statsEl = $("v2ScopeBookStats");

    if (!slug) {
      if (statsEl) statsEl.textContent = "Pick or save a book in Step 01 to dynamically calculate runtime options from its text.";
      rebuildV2DurationOptions("", [], null);
      return;
    }

    if (statsEl) statsEl.textContent = `Reading "${slug}" word count and chapters…`;
    let chaps = [], savedMinutes = null;
    try {
      const ch = await callApi(`/api/chapters?project=${encodeURIComponent(slug)}`);
      if (ch && Array.isArray(ch.chapters)) chaps = ch.chapters;
    } catch (e) {}
    try {
      const ad = await callApi(`/api/adaptation?project=${encodeURIComponent(slug)}`);
      if (ad && ad.exists && ad.plan && ad.plan.runtime_minutes) {
        savedMinutes = Number(ad.plan.runtime_minutes);
      }
    } catch (e) {}

    const totalWords = chaps.reduce((acc, c) => acc + (Number(c.words) || 0), 0);
    if (statsEl) {
      if (totalWords > 0) {
        const readMin = roundHalf(totalWords / 145);
        statsEl.innerHTML = `<strong style="color:#f59e0b">${slug}</strong> · <strong>${chaps.length}</strong> chapter(s) · <strong>${totalWords.toLocaleString()}</strong> words · ~<strong>${readMin} min</strong> unabridged spoken reading time`;
      } else {
        statsEl.textContent = `Book "${slug}" has not been split into chapters yet — showing standard film formats. Run Read Book in Step 01/02 to unlock word-count-based options.`;
      }
    }

    rebuildV2DurationOptions(slug, chaps, savedMinutes);
  }

  function initV2Scope() {
    const sel = $("v2Duration");
    const minEl = $("v2CustomMinutes");
    const clipEl = $("v2ClipSec");
    const aspectEl = $("v2Aspect");
    const modeEl = $("v2ScopeMode");
    const fromEl = $("v2ScopeFromCh");
    const toEl = $("v2ScopeToCh");
    const btnReload = $("v2ScopeReload");

    if (sel) {
      sel.addEventListener("change", () => {
        const opt = sel.options[sel.selectedIndex];
        if (opt && opt.dataset.minutes && minEl) {
          minEl.value = opt.dataset.minutes;
        }
        // If user picks the Chapter 1 Pilot preset, auto-sync Scope Mode
        if (opt && opt.value.startsWith("book_ch1:") && modeEl) {
          modeEl.value = "pilot_ch1";
        } else if (opt && opt.value.startsWith("std_trailer:") && modeEl) {
          modeEl.value = "trailer";
        }
        updateV2ScopeEstimate();
      });
    }

    if (minEl) {
      minEl.addEventListener("input", updateV2ScopeEstimate);
    }
    if (clipEl) {
      clipEl.addEventListener("change", () => {
        const selProj = $("proj");
        const slug = (selProj && selProj.value) || activeProject || "";
        const curMin = parseFloat(minEl ? minEl.value : "5") || 5;
        rebuildV2DurationOptions(slug, v2ScopeChapters, curMin);
      });
    }
    [aspectEl, modeEl, fromEl, toEl].forEach(el => {
      if (el) el.addEventListener("change", updateV2ScopeEstimate);
    });
    if (btnReload) btnReload.addEventListener("click", () => loadV2Scope());
  }

  // ===== STEP 05: STORY STRUCTURE, BEATS & SCENE BREAKDOWN =====
  async function v2AdaptEdit(body) {
    const selProj = $("proj");
    const slug = (selProj && selProj.value) || activeProject || "";
    if (!slug) return;
    try {
      await callApi("/api/adaptation_edit", { project: slug, ...body });
      await loadV2StoryBreakdown();
      checkStepStorylineDrift();
    } catch (err) {
      alert("Could not update scene breakdown: " + err.message);
    }
  }

  async function loadV2StoryBreakdown() {
    const selProj = $("proj");
    const slug = (selProj && selProj.value) || activeProject || "";
    const summaryEl = $("v2BeatsSummary");
    const badgeEl = $("v2BeatsBadge");
    const emptyEl = $("v2BeatsEmpty");
    const gridEl = $("v2BeatsGrid");
    const tbody = $("v2BreakdownBody");
    const countEl = $("v2BreakdownCount");
    const treatDetails = $("v2TreatmentDetails");
    const treatText = $("v2TreatmentText");

    if (!gridEl || !tbody) return;
    if (!slug) {
      if (summaryEl) summaryEl.textContent = "Pick or save a story in Step 01 first.";
      if (emptyEl) emptyEl.classList.remove("hidden");
      gridEl.textContent = "";
      tbody.textContent = "";
      return;
    }

    if (summaryEl) summaryEl.textContent = "Loading story acts, beats, and scene breakdown…";
    let adapt = null, readin = null, chaps = null;
    try { adapt = await callApi(`/api/adaptation?project=${encodeURIComponent(slug)}`); } catch (e) {}
    try { readin = await callApi(`/api/readin?project=${encodeURIComponent(slug)}`); } catch (e) {}
    if (!adapt || !adapt.exists) {
      try { chaps = await callApi(`/api/chapters?project=${encodeURIComponent(slug)}`); } catch (e) {}
    }

    const plan = adapt && adapt.exists ? adapt.plan : null;
    const scenes = (plan && Array.isArray(plan.scenes)) ? plan.scenes : [];
    const beatsActs = (readin && readin.beats && Array.isArray(readin.beats.acts)) ? readin.beats.acts : [];
    const treatment = (readin && readin.treatment) ? readin.treatment.trim() : "";

    // Treatment panel
    if (treatDetails && treatText) {
      if (treatment) {
        treatText.textContent = treatment;
        treatDetails.classList.remove("hidden");
      } else {
        treatDetails.classList.add("hidden");
      }
    }

    // 1. Render Act-by-Act Beat Sheet
    gridEl.textContent = "";
    if (beatsActs.length > 0) {
      beatsActs.forEach((act, idx) => {
        const card = document.createElement("div");
        card.className = "deliverable-card";
        const pct = act.share ? ` (${Math.round(act.share * 100)}%)` : "";
        const h = document.createElement("span");
        h.className = "deliverable-title";
        h.textContent = `${act.name || `Act ${idx + 1}`}${pct}`;
        card.appendChild(h);

        if (act.purpose) {
          const p = document.createElement("p");
          p.className = "deliverable-desc";
          p.style.marginBottom = "8px";
          p.textContent = act.purpose;
          card.appendChild(p);
        }

        const ol = document.createElement("ol");
        ol.style.cssText = "margin:0;padding-left:18px;font-size:var(--text-xs);color:#cbd5e1;display:flex;flex-direction:column;gap:6px;";
        (act.beats || []).forEach(b => {
          const li = document.createElement("li");
          li.innerHTML = `<strong style="color:#f59e0b">${b.name || `Beat ${b.n}`}</strong>: ${b.description || ""}`;
          ol.appendChild(li);
        });
        card.appendChild(ol);
        gridEl.appendChild(card);
      });
    } else if (scenes.length > 0) {
      // Group plan scenes by Act so every story beat is visible even without readin beats
      const byAct = new Map();
      scenes.forEach(s => {
        const a = s.act || 1;
        if (!byAct.has(a)) byAct.set(a, []);
        byAct.get(a).push(s);
      });
      [...byAct.entries()].sort((a, b) => a[0] - b[0]).forEach(([actNum, actScenes]) => {
        const card = document.createElement("div");
        card.className = "deliverable-card";
        const h = document.createElement("span");
        h.className = "deliverable-title";
        const sec = actScenes.reduce((acc, s) => acc + (Number(s.seconds) || 0), 0);
        h.textContent = `Act ${actNum} · ${actScenes.length} scene(s) (${Math.round(sec)}s)`;
        card.appendChild(h);

        const ol = document.createElement("ol");
        ol.style.cssText = "margin:6px 0 0;padding-left:18px;font-size:var(--text-xs);color:#cbd5e1;display:flex;flex-direction:column;gap:6px;";
        actScenes.forEach(s => {
          const li = document.createElement("li");
          li.innerHTML = `<strong style="color:#f59e0b">${s.id} ${s.title || ""}</strong>: ${s.summary || ""}`;
          ol.appendChild(li);
        });
        card.appendChild(ol);
        gridEl.appendChild(card);
      });
    } else {
      const p = document.createElement("p");
      p.style.cssText = "color:#94a3b8;font-size:var(--text-sm);margin:0;";
      p.textContent = "No act/beat sheet generated yet. Click '✨ Generate / Rebuild Beats' above to analyze the book into acts and beats.";
      gridEl.appendChild(p);
    }

    // 2. Render Complete Scene-by-Scene Story Breakdown Table
    tbody.textContent = "";
    if (scenes.length > 0) {
      if (emptyEl) emptyEl.classList.add("hidden");
      const rt = adapt.runtime || {};
      const totalBeats = beatsActs.reduce((acc, a) => acc + (a.beats ? a.beats.length : 0), 0);
      if (summaryEl) {
        summaryEl.innerHTML = `<strong style="color:#f59e0b">${scenes.length} scenes</strong>` +
          (totalBeats ? ` · <strong>${totalBeats} story beats</strong>` : "") +
          ` · ${adapt.active_clips || 0} clips · ${rt.minutes || "?"} min planned` +
          (plan.logline ? `<div style="margin-top:4px;color:#94a3b8;font-size:var(--text-xs)">${plan.logline}</div>` : "");
      }
      if (badgeEl) {
        badgeEl.textContent = plan.stale ? "⚠️ Chapters Changed — Rebuild Recommended" : `✓ ${scenes.length} Scenes Planned`;
        badgeEl.className = "status-badge " + (plan.stale ? "status-badge--drift" : "status-badge--synced");
      }
      if (countEl) countEl.textContent = `Showing all ${scenes.length} scenes`;

      scenes.forEach((s, i) => {
        const tr = document.createElement("tr");
        tr.style.borderBottom = "1px solid #1e293b";

        const tdId = document.createElement("td");
        tdId.style.cssText = "padding:8px;font-weight:700;color:#f59e0b;white-space:nowrap;";
        tdId.textContent = s.id;

        const tdAct = document.createElement("td");
        tdAct.style.padding = "8px";
        tdAct.textContent = String(s.act || 1);

        const tdTitle = document.createElement("td");
        tdTitle.style.padding = "8px";
        const inpTitle = document.createElement("input");
        inpTitle.type = "text";
        inpTitle.value = s.title || "";
        inpTitle.maxLength = 100;
        inpTitle.style.cssText = "width:100%;min-width:140px;padding:4px 6px;background:#0a0d14;color:#f8fafc;border:1px solid #334155;border-radius:4px;";
        inpTitle.addEventListener("change", () => v2AdaptEdit({ action: "rename", id: s.id, title: inpTitle.value }));
        tdTitle.appendChild(inpTitle);

        const tdCh = document.createElement("td");
        tdCh.style.cssText = "padding:8px;white-space:nowrap;color:#94a3b8;";
        tdCh.textContent = Array.isArray(s.chapters) ? s.chapters.join(", ") : "";

        const tdClips = document.createElement("td");
        tdClips.style.padding = "8px";
        const inpClips = document.createElement("input");
        inpClips.type = "number";
        inpClips.min = 1;
        inpClips.max = 500;
        inpClips.value = s.clips || 1;
        inpClips.style.cssText = "width:58px;padding:4px;background:#0a0d14;color:#f8fafc;border:1px solid #334155;border-radius:4px;";
        inpClips.addEventListener("change", () => v2AdaptEdit({ action: "set_clips", id: s.id, clips: Number(inpClips.value) }));
        tdClips.appendChild(inpClips);

        const tdSec = document.createElement("td");
        tdSec.style.cssText = "padding:8px;white-space:nowrap;color:#94a3b8;";
        tdSec.textContent = `${s.seconds || 0}s`;

        const tdSum = document.createElement("td");
        tdSum.style.cssText = "padding:8px;color:#e2e8f0;min-width:220px;";
        tdSum.textContent = s.summary || "";

        const tdActs = document.createElement("td");
        tdActs.style.cssText = "padding:8px;white-space:nowrap;display:flex;gap:4px;flex-wrap:wrap;";
        const mkBtn = (label, fn, cls = "btn btn--ghost") => {
          const b = document.createElement("button");
          b.type = "button";
          b.className = cls;
          b.style.cssText = "padding:3px 7px;font-size:var(--text-xs);";
          b.textContent = label;
          b.addEventListener("click", fn);
          return b;
        };
        if (i > 0) tdActs.appendChild(mkBtn("↑", () => v2AdaptEdit({ action: "move", id: s.id, direction: -1 })));
        if (i + 1 < scenes.length) {
          tdActs.appendChild(mkBtn("↓", () => v2AdaptEdit({ action: "move", id: s.id, direction: 1 })));
          tdActs.appendChild(mkBtn("Join", () => {
            if (confirm(`Join ${s.id} with the next scene?`)) v2AdaptEdit({ action: "merge", id: s.id });
          }));
        }
        tdActs.appendChild(mkBtn("Drop", () => {
          if (confirm(`Drop scene ${s.id} ("${s.title}")?`)) v2AdaptEdit({ action: "drop", id: s.id });
        }));
        tdActs.appendChild(mkBtn("Script ➔", () => {
          spActiveIdx = i;
          spViewMode = "single";
          activateStep(6);
        }, "btn btn--secondary"));

        [tdId, tdAct, tdTitle, tdCh, tdClips, tdSec, tdSum, tdActs].forEach(td => tr.appendChild(td));
        tbody.appendChild(tr);
      });
    } else if (chaps && Array.isArray(chaps.chapters) && chaps.chapters.length > 0) {
      if (emptyEl) emptyEl.classList.remove("hidden");
      if (summaryEl) summaryEl.textContent = `No scene breakdown yet — showing ${chaps.chapters.length} source chapter(s) ready to be broken into beats & scenes.`;
      if (badgeEl) {
        badgeEl.textContent = `${chaps.chapters.length} Chapters (Plan Pending)`;
        badgeEl.className = "status-badge status-badge--working";
      }
      if (countEl) countEl.textContent = `${chaps.chapters.length} chapters`;
      chaps.chapters.forEach(c => {
        const tr = document.createElement("tr");
        tr.style.borderBottom = "1px solid #1e293b";
        tr.innerHTML = `<td style="padding:8px;font-weight:700;color:#f59e0b">CH${String(c.n).padStart(2, "0")}</td>` +
          `<td style="padding:8px">-</td>` +
          `<td style="padding:8px;color:#f8fafc">${c.title || `Chapter ${c.n}`}</td>` +
          `<td style="padding:8px">${c.n}</td>` +
          `<td style="padding:8px">-</td>` +
          `<td style="padding:8px">-</td>` +
          `<td style="padding:8px;color:#94a3b8">${c.starts_with || ""} (${c.words || 0} words)</td>` +
          `<td style="padding:8px;color:#64748b">Pending plan</td>`;
        tbody.appendChild(tr);
      });
    } else {
      if (emptyEl) emptyEl.classList.remove("hidden");
      if (summaryEl) summaryEl.textContent = "No breakdown found yet for this project.";
      if (badgeEl) {
        badgeEl.textContent = "Not Planned Yet";
        badgeEl.className = "status-badge status-badge--drift";
      }
      if (countEl) countEl.textContent = "0 scenes";
    }
  }

  function initV2StoryBreakdown() {
    const btnReload = $("v2BeatsReload");
    const btnBuild = $("v2BeatsBuild");
    if (btnReload) btnReload.addEventListener("click", () => loadV2StoryBreakdown());
    if (btnBuild) {
      btnBuild.addEventListener("click", async () => {
        const selProj = $("proj");
        const slug = (selProj && selProj.value) || activeProject || "";
        if (!slug) { alert("Pick or save a book in Step 01 first."); return; }
        btnBuild.disabled = true;
        const summaryEl = $("v2BeatsSummary");
        if (summaryEl) summaryEl.textContent = "Starting story breakdown & beat sheet generation…";
        try {
          const o = typeof window.options === "function" ? window.options() : {};
          await callApi("/api/read_it_in", { project: slug, engine: o.engine || "claude", claude_model: o.claude_model });
          if (summaryEl) summaryEl.textContent = "✓ Story breakdown job started! Reload in a moment to view updated beats and scenes.";
        } catch (err) {
          if (summaryEl) summaryEl.textContent = "Could not start breakdown: " + err.message;
        } finally {
          btnBuild.disabled = false;
        }
      });
    }

    const selProj = $("proj");
    if (selProj) {
      selProj.addEventListener("change", () => {
        if (currentStep === 5) loadV2StoryBreakdown();
      });
    }
  }

  // ===== STEP 06: MULTI-SCENE SCREENPLAY EDITOR =====
  let spScenesData = [];
  let spFlagsData = {};
  let spActiveIdx = 0;
  let spViewMode = "single"; // "single" | "all"
  let spSourceKind = "adaptation"; // "adaptation" | "readin" | "chapters"

  function spElementsToText(els) {
    if (!Array.isArray(els)) return "";
    return els.map(e => {
      if (e.type === "dialogue") {
        return `D ${e.character}${e.note ? ` (${e.note})` : ""}: ${e.text}`;
      }
      return `${e.type === "transition" ? "T" : "A"}: ${e.text}`;
    }).join("\n");
  }

  function spTextToElements(text) {
    const els = [];
    for (const raw of String(text || "").split("\n")) {
      const line = raw.trim();
      if (!line) continue;
      let m;
      if ((m = line.match(/^A:\s*(.+)$/))) {
        els.push({ type: "action", text: m[1] });
      } else if ((m = line.match(/^T:\s*(.+)$/))) {
        els.push({ type: "transition", text: m[1] });
      } else if ((m = line.match(/^D\s+([^():]+?)\s*(?:\(([^)]*)\))?\s*:\s*(.+)$/))) {
        els.push({ type: "dialogue", character: m[1].trim(), note: m[2] || undefined, text: m[3] });
      } else {
        // Treat plain lines as action so novices don't get blocked by syntax errors
        els.push({ type: "action", text: line });
      }
    }
    return els;
  }

  function renderV2Screenplay() {
    const pills = $("v2SpPills");
    const countEl = $("v2SpCount");
    const emptyEl = $("v2SpEmpty");
    const singleBox = $("v2SpSingleBox");
    const allBox = $("v2SpAllBox");
    const prevBtn = $("v2SpPrev");
    const nextBtn = $("v2SpNext");
    const btnSingle = $("v2SpViewSingle");
    const btnAll = $("v2SpViewAll");

    if (!pills || !countEl) return;

    if (!spScenesData.length) {
      pills.innerHTML = "";
      countEl.textContent = "0 scenes";
      if (emptyEl) emptyEl.classList.remove("hidden");
      if (singleBox) singleBox.classList.add("hidden");
      if (allBox) allBox.classList.add("hidden");
      if (prevBtn) prevBtn.disabled = true;
      if (nextBtn) nextBtn.disabled = true;
      return;
    }

    if (emptyEl) emptyEl.classList.add("hidden");
    spActiveIdx = Math.max(0, Math.min(spScenesData.length - 1, spActiveIdx));
    countEl.textContent = `Scene ${spActiveIdx + 1} of ${spScenesData.length}`;
    if (prevBtn) prevBtn.disabled = spActiveIdx <= 0;
    if (nextBtn) nextBtn.disabled = spActiveIdx >= spScenesData.length - 1;

    // Render scene pills
    pills.textContent = "";
    spScenesData.forEach((s, idx) => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "step-pill" + (idx === spActiveIdx && spViewMode === "single" ? " active" : "");
      const hasFlag = spFlagsData && spFlagsData[s.id] && spFlagsData[s.id].length > 0;
      b.textContent = `${s.id}: ${s.title || "Untitled"}${hasFlag ? " ⚠️" : ""}`;
      b.title = s.summary || s.title || s.id;
      b.addEventListener("click", () => {
        spActiveIdx = idx;
        spViewMode = "single";
        renderV2Screenplay();
      });
      pills.appendChild(b);
    });

    // View mode toggle buttons
    if (btnSingle) {
      btnSingle.className = "btn " + (spViewMode === "single" ? "btn--primary" : "btn--ghost");
    }
    if (btnAll) {
      btnAll.className = "btn " + (spViewMode === "all" ? "btn--primary" : "btn--ghost");
    }

    if (spViewMode === "single") {
      if (singleBox) singleBox.classList.remove("hidden");
      if (allBox) {
        allBox.classList.add("hidden");
        allBox.style.display = "none";
      }
      const s = spScenesData[spActiveIdx];
      const meta = $("v2SpSceneMeta");
      const heading = $("v2SpHeading");
      const body = $("v2SpBody");
      const saveBtn = $("v2SpSave");
      const saveMsg = $("v2SpSaveMsg");

      if (meta) {
        const dur = s.seconds ? ` · ${s.seconds}s` : "";
        const summary = s.summary ? ` — ${s.summary}` : "";
        meta.innerHTML = `<strong style="color:#f59e0b">${s.id}</strong>: <strong style="color:#f8fafc">${s.title || ""}</strong>${dur}${summary}`;
      }
      if (heading) {
        heading.value = (s.screenplay && s.screenplay.heading) || s.heading || "";
      }
      if (body) {
        body.value = s.screenplay
          ? spElementsToText(s.screenplay.elements)
          : (s.text || "");
      }
      if (saveBtn) {
        saveBtn.disabled = spSourceKind !== "adaptation";
        saveBtn.title = spSourceKind === "adaptation" ? "Save changes to this scene" : "Read-only preview (plan/write screenplay to edit)";
      }
      if (saveMsg) saveMsg.textContent = "";
    } else {
      if (singleBox) singleBox.classList.add("hidden");
      if (allBox) {
        allBox.classList.remove("hidden");
        allBox.style.display = "flex";
        allBox.textContent = "";
        spScenesData.forEach((s, idx) => {
          const card = document.createElement("div");
          card.style.cssText = "background:#0a0d14;border:1px solid #232d3f;border-radius:8px;padding:12px;";
          const headRow = document.createElement("div");
          headRow.style.cssText = "display:flex;justify-content:space-between;align-items:center;gap:8px;margin-bottom:6px;";
          const title = document.createElement("strong");
          title.style.color = "#f59e0b";
          title.textContent = `${s.id}: ${s.title || "Untitled"}${s.seconds ? ` (${s.seconds}s)` : ""}`;
          const editBtn = document.createElement("button");
          editBtn.type = "button";
          editBtn.className = "btn btn--secondary";
          editBtn.style.cssText = "padding:3px 10px;font-size:var(--text-xs)";
          editBtn.textContent = "Edit Scene";
          editBtn.addEventListener("click", () => {
            spActiveIdx = idx;
            spViewMode = "single";
            renderV2Screenplay();
          });
          headRow.appendChild(title);
          headRow.appendChild(editBtn);
          card.appendChild(headRow);

          const slugLine = document.createElement("div");
          slugLine.style.cssText = "font-family:var(--font-mono);font-size:var(--text-xs);color:#38bdf8;margin-bottom:6px;";
          slugLine.textContent = (s.screenplay && s.screenplay.heading) || s.heading || "(No heading yet)";
          card.appendChild(slugLine);

          const pre = document.createElement("pre");
          pre.style.cssText = "margin:0;white-space:pre-wrap;font-family:var(--font-mono);font-size:var(--text-xs);color:#e2e8f0;line-height:1.5;max-height:180px;overflow:auto;";
          pre.textContent = s.screenplay
            ? spElementsToText(s.screenplay.elements)
            : (s.text || s.summary || "(Not written yet)");
          card.appendChild(pre);
          allBox.appendChild(card);
        });
      }
    }
  }

  async function loadV2Screenplay() {
    const selProj = $("proj");
    const slug = (selProj && selProj.value) || activeProject || "";
    const countEl = $("v2SpCount");
    if (!slug) {
      spScenesData = [];
      renderV2Screenplay();
      return;
    }
    if (countEl) countEl.textContent = "Loading scenes…";

    // 1. Try /api/screenplay (adaptation film plan scenes)
    try {
      const r = await callApi(`/api/screenplay?project=${encodeURIComponent(slug)}`);
      if (r && Array.isArray(r.scenes) && r.scenes.length > 0) {
        spScenesData = r.scenes;
        spFlagsData = r.flags || {};
        spSourceKind = "adaptation";
        renderV2Screenplay();
        return;
      }
    } catch (e) { /* fall through */ }

    // 2. Fallback: try /api/readin script
    try {
      const rd = await callApi(`/api/readin?project=${encodeURIComponent(slug)}`);
      if (rd && rd.script && rd.script.trim()) {
        const blocks = rd.script.split(/\n(?=(?:INT\.|EXT\.|INT\/EXT\.|SCENE\s+\d+))/i).filter(b => b.trim());
        spScenesData = blocks.map((blk, i) => {
          const lines = blk.trim().split("\n");
          return {
            id: `S${String(i + 1).padStart(2, "0")}`,
            title: lines[0].slice(0, 60),
            heading: lines[0],
            text: lines.slice(1).join("\n").trim(),
            summary: ""
          };
        });
        spFlagsData = {};
        spSourceKind = "readin";
        renderV2Screenplay();
        return;
      }
    } catch (e) { /* fall through */ }

    // 3. Fallback: try /api/chapters so user can still browse every chapter/scene
    try {
      const ch = await callApi(`/api/chapters?project=${encodeURIComponent(slug)}`);
      if (ch && Array.isArray(ch.chapters) && ch.chapters.length > 0) {
        spScenesData = ch.chapters.map(c => ({
          id: `CH${String(c.n).padStart(2, "0")}`,
          title: c.title || `Chapter ${c.n}`,
          heading: `CHAPTER ${c.n}: ${c.title || ""}`,
          text: c.starts_with || "",
          summary: `${c.words || 0} words`
        }));
        spFlagsData = {};
        spSourceKind = "chapters";
        renderV2Screenplay();
        return;
      }
    } catch (e) { /* fall through */ }

    spScenesData = [];
    renderV2Screenplay();
  }

  function initV2Screenplay() {
    const prevBtn = $("v2SpPrev");
    const nextBtn = $("v2SpNext");
    const btnSingle = $("v2SpViewSingle");
    const btnAll = $("v2SpViewAll");
    const btnRefresh = $("v2SpRefresh");
    const btnSave = $("v2SpSave");

    if (prevBtn) prevBtn.addEventListener("click", () => { if (spActiveIdx > 0) { spActiveIdx--; spViewMode = "single"; renderV2Screenplay(); } });
    if (nextBtn) nextBtn.addEventListener("click", () => { if (spActiveIdx < spScenesData.length - 1) { spActiveIdx++; spViewMode = "single"; renderV2Screenplay(); } });
    if (btnSingle) btnSingle.addEventListener("click", () => { spViewMode = "single"; renderV2Screenplay(); });
    if (btnAll) btnAll.addEventListener("click", () => { spViewMode = "all"; renderV2Screenplay(); });
    if (btnRefresh) btnRefresh.addEventListener("click", () => loadV2Screenplay());

    if (btnSave) {
      btnSave.addEventListener("click", async () => {
        const selProj = $("proj");
        const slug = (selProj && selProj.value) || activeProject || "";
        const s = spScenesData[spActiveIdx];
        const msg = $("v2SpSaveMsg");
        if (!slug || !s || spSourceKind !== "adaptation") return;

        btnSave.disabled = true;
        if (msg) msg.textContent = "Saving scene…";
        try {
          const heading = ($("v2SpHeading") || {}).value || "";
          const elements = spTextToElements(($("v2SpBody") || {}).value || "");
          await callApi("/api/screenplay_edit", {
            project: slug,
            action: "save_scene",
            scene: s.id,
            heading,
            elements
          });
          if (msg) msg.textContent = `✓ Saved ${s.id}. Storyline drift updated.`;
          await loadV2Screenplay();
          await checkStepStorylineDrift();
        } catch (err) {
          if (msg) msg.textContent = "Error: " + err.message;
        } finally {
          btnSave.disabled = false;
        }
      });
    }

    // Reload scenes whenever the selected book changes
    const selProj = $("proj");
    if (selProj) {
      selProj.addEventListener("change", () => {
        spActiveIdx = 0;
        if (currentStep === 6) loadV2Screenplay();
        checkStepStorylineDrift();
      });
    }
  }

  // ===== STORYLINE CHANGE DETECTION & SELECTIVE REDO =====
  async function checkStepStorylineDrift() {
    const selProj = $("proj");
    const slug = (selProj && selProj.value) || activeProject || "";
    if (!slug) return;

    try {
      const data = await callApi(`/api/storyline_changes?project=${encodeURIComponent(slug)}`);
      const badges = document.querySelectorAll(".storyline-drift-badge");
      const redoBanners = document.querySelectorAll(".storyline-redo-banner");

      if (data && data.changed && data.changed_scene_ids && data.changed_scene_ids.length > 0) {
        const scenesList = data.changed_scene_ids.join(", ");
        badges.forEach(b => {
          b.textContent = `⚠️ Storyline modified: Scene(s) ${scenesList} need re-sync`;
          b.className = "status-badge status-badge--drift";
        });
        redoBanners.forEach(banner => {
          banner.classList.remove("hidden");
          const msg = banner.querySelector(".drift-msg");
          if (msg) msg.textContent = `Scenes [${scenesList}] have changed in the screenplay.`;
        });
      } else {
        badges.forEach(b => {
          b.textContent = "✓ Storyline in sync";
          b.className = "status-badge status-badge--synced";
        });
        redoBanners.forEach(banner => banner.classList.add("hidden"));
      }
    } catch (e) {}
  }

  async function triggerSelectiveStorylineRedo() {
    const selProj = $("proj");
    const slug = (selProj && selProj.value) || activeProject || "";
    if (!slug) return;

    try {
      await callApi("/api/redo_storyline", { project: slug });
      alert(`Storyline re-sync initiated for ${slug}. Invalidation updated.`);
      await checkStepStorylineDrift();
    } catch (err) {
      alert("Error re-syncing storyline: " + err.message);
    }
  }

  // ===== DUAL-LEVEL AUDIO REDO =====
  async function triggerAudioRedo(mode, dialect, narratorVoice, cast, rows) {
    const selProj = $("proj");
    const slug = (selProj && selProj.value) || activeProject || "";
    if (!slug) {
      alert("Please select a story project first.");
      return;
    }

    try {
      const res = await callApi("/api/redo_audio", {
        project: slug,
        mode: mode || "dialogue",
        dialect: dialect || null,
        narrator_voice: narratorVoice || null,
        cast: cast || null,
        rows: rows || null,
      });
      alert(`Audio reconfigured! Mode: ${res.result?.mode}, Dialect: ${dialect || 'kept'}.`);
    } catch (err) {
      alert("Error updating audio: " + err.message);
    }
  }

  // ===== AUTOPILOT MODEL RECOMMENDATION =====
  async function loadStepAutopilot() {
    const stepMeta = V2_STEPS.find(s => s.num === currentStep);
    if (!stepMeta) return;

    const lookOpts = document.querySelector('input[name="look"]:checked');
    const look = lookOpts ? lookOpts.value : "live_action";

    try {
      const rec = await callApi(`/api/autopilot_recommend?look=${encodeURIComponent(look)}&step=${encodeURIComponent(stepMeta.id)}`);
      const recBadges = document.querySelectorAll(`.step-panel[data-step="${currentStep}"] .autopilot-badge`);
      recBadges.forEach(b => {
        b.innerHTML = `✨ <strong>Autopilot Pick:</strong> ${rec.label} &mdash; <em>${rec.why}</em>`;
      });
    } catch (e) {}
  }

  // ===== CREATIVE WORKBENCH TOGGLE & RETURN BANNER =====
  function initWorkbenchToggle() {
    const btn = $("workbenchToggle");
    const dropdown = $("workbenchDropdown");
    if (!btn || !dropdown) return;

    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      dropdown.classList.toggle("hidden");
    });

    document.addEventListener("click", () => {
      dropdown.classList.add("hidden");
    });

    // Create persistent Return to Pipeline banner if not present
    let returnBanner = $("workbenchReturnBanner");
    if (!returnBanner) {
      returnBanner = document.createElement("div");
      returnBanner.id = "workbenchReturnBanner";
      returnBanner.className = "workbench-return-banner hidden";
      returnBanner.innerHTML = `
        <div><strong>🔬 Creative Workbench Mode Active</strong> &mdash; <span id="wbActiveName">Single Prompts</span></div>
        <button type="button" class="btn btn--primary" id="bReturnToPipeline" style="background:#f59e0b;color:#0b0e14;font-weight:700">🎬 Return to Guided Film Pipeline (Step ${currentStep})</button>
      `;
      document.body.insertBefore(returnBanner, document.body.firstChild);

      $("bReturnToPipeline").addEventListener("click", () => {
        document.body.classList.remove("mode-workbench");
        document.body.classList.add("mode-pipeline");
        returnBanner.classList.add("hidden");
        activateStep(currentStep);
      });
    }

    dropdown.querySelectorAll(".wb-tab-btn").forEach(wbBtn => {
      wbBtn.addEventListener("click", () => {
        const targetId = wbBtn.dataset.target;
        document.body.classList.remove("mode-pipeline");
        document.body.classList.add("mode-workbench");

        returnBanner.classList.remove("hidden");
        const nameSpan = $("wbActiveName");
        if (nameSpan) nameSpan.textContent = wbBtn.textContent;
        const returnBtn = $("bReturnToPipeline");
        if (returnBtn) returnBtn.textContent = `🎬 Return to Guided Film Pipeline (Step ${currentStep})`;

        // Show the workbench tab panel
        document.querySelectorAll(".tab-panel").forEach(p => p.classList.remove("active"));
        const targetPanel = $(targetId);
        if (targetPanel) {
          targetPanel.classList.add("active");
          targetPanel.scrollIntoView({ behavior: "smooth", block: "start" });
        }
        dropdown.classList.add("hidden");
      });
    });
  }

  // ===== STEP 07: CONTINUITY & WORLD RULES =====
  let v2ContRulesRev = 0;

  async function loadV2Continuity() {
    const selProj = $("proj");
    const slug = (selProj && selProj.value) || activeProject || "";
    const rulesEl = $("v2ContRules");
    const posEl = $("v2ContPositives");
    const negEl = $("v2ContNegatives");
    const badgeEl = $("v2ContBadge");
    const locksSum = $("v2ContLocksSummary");
    const locksList = $("v2ContLocksList");

    if (!rulesEl || !posEl || !negEl) return;

    // Clear previous book's continuity data immediately
    rulesEl.value = "";
    posEl.value = "";
    negEl.value = "";
    if (locksList) locksList.textContent = "";

    if (!slug) {
      if (badgeEl) {
        badgeEl.textContent = "No Book Selected";
        badgeEl.className = "status-badge status-badge--drift";
      }
      if (locksSum) locksSum.textContent = "Pick a book in Step 01 first.";
      return;
    }

    if (badgeEl) {
      badgeEl.textContent = "Loading…";
      badgeEl.className = "status-badge status-badge--working";
    }

    // 1. Load project rules
    try {
      const r = await callApi(`/api/project_rules?project=${encodeURIComponent(slug)}`);
      rulesEl.value = (r && r.body) || "";
      v2ContRulesRev = (r && typeof r.rev === "number") ? r.rev : 0;
    } catch (e) {
      v2ContRulesRev = 0;
    }

    // 2. Load global visual/lighting parameters
    try {
      const gp = await callApi(`/api/global_params?project=${encodeURIComponent(slug)}`);
      posEl.value = (gp && gp.positives) || "";
      negEl.value = (gp && gp.negatives) || "";
    } catch (e) {}

    // 3. Load scene-by-scene cast & location locks
    try {
      const lk = await callApi(`/api/cast_lock?project=${encodeURIComponent(slug)}`);
      const sm = (lk && lk.summary) || {};
      const scenes = (lk && Array.isArray(lk.scenes)) ? lk.scenes : [];
      if (locksSum) {
        locksSum.textContent = scenes.length
          ? `${scenes.length} scene(s) · ${sm.characters || 0} costume lock(s), ${sm.locations || 0} location lock(s)`
          : "No planned scenes yet for per-scene locks.";
      }
      if (locksList) {
        locksList.textContent = "";
        scenes.forEach(s => {
          const row = document.createElement("div");
          row.style.cssText = "padding:8px 10px;background:#0a0d14;border:1px solid #1e293b;border-radius:6px;display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap;";
          const chars = (s.characters || []).map(c => c.name).join(", ") || "No characters listed";
          const place = (s.place && s.place.name) ? s.place.name : "Unspecified set";
          const locked = (s.characters || []).some(c => c.locked && (c.locked.token || c.locked.reference)) || (s.place && s.place.locked && s.place.locked.reference);
          row.innerHTML = `<div><strong style="color:#f59e0b">${s.id}</strong> <strong style="color:#f8fafc">${s.title || ""}</strong> &mdash; <span>Cast: ${chars}</span> · <span>Set: ${place}</span></div>` +
            `<span class="status-badge ${locked ? "status-badge--synced" : ""}" style="font-size:0.7rem">${locked ? "✓ Locked" : "Unlocked"}</span>`;
          locksList.appendChild(row);
        });
      }
    } catch (e) {
      if (locksSum) locksSum.textContent = "Run Story Breakdown (Step 05) to populate per-scene locks.";
    }

    if (badgeEl) {
      badgeEl.textContent = `✓ Rules Loaded (${slug})`;
      badgeEl.className = "status-badge status-badge--synced";
    }
  }

  function initV2Continuity() {
    const btnReload = $("v2ContReload");
    const btnSaveRules = $("v2ContRulesSave");
    const btnSaveParams = $("v2ContParamsSave");
    const rulesEl = $("v2ContRules");
    const rulesMsg = $("v2ContRulesMsg");
    const posEl = $("v2ContPositives");
    const negEl = $("v2ContNegatives");
    const paramsMsg = $("v2ContParamsMsg");

    if (btnReload) btnReload.addEventListener("click", () => loadV2Continuity());

    // Quick-insert world rule chips
    document.querySelectorAll(".v2-cont-chip").forEach(chip => {
      chip.addEventListener("click", () => {
        if (!rulesEl) return;
        const snippet = chip.dataset.snippet || "";
        if (!snippet) return;
        if (!rulesEl.value.includes(snippet)) {
          rulesEl.value = (rulesEl.value.trim() ? rulesEl.value.trim() + "\n" : "") + snippet;
        }
        rulesEl.focus();
        if (rulesMsg) rulesMsg.textContent = "Added rule — click 💾 Save World Rules to persist.";
      });
    });

    // Quick lighting & palette preset buttons
    document.querySelectorAll(".v2-light-preset").forEach(btn => {
      btn.addEventListener("click", () => {
        if (!posEl) return;
        const preset = btn.dataset.pos || "";
        if (!preset) return;
        if (!posEl.value.toLowerCase().includes(preset.slice(0, 18).toLowerCase())) {
          posEl.value = (posEl.value.trim() ? posEl.value.trim().replace(/,\s*$/, "") + ", " : "") + preset;
        }
        posEl.focus();
        if (paramsMsg) paramsMsg.textContent = "Preset applied — click 💾 Save Lighting & Palette to persist.";
      });
    });

    if (btnSaveRules) {
      btnSaveRules.addEventListener("click", async () => {
        const selProj = $("proj");
        const slug = (selProj && selProj.value) || activeProject || "";
        if (!slug) { alert("Pick or save a book in Step 01 first."); return; }
        btnSaveRules.disabled = true;
        if (rulesMsg) rulesMsg.textContent = "Saving world rules…";
        try {
          const r = await callApi("/api/project_rules", {
            project: slug,
            body: rulesEl ? rulesEl.value : "",
            rev: v2ContRulesRev
          });
          if (r && typeof r.rev === "number") v2ContRulesRev = r.rev;
          if (rulesMsg) rulesMsg.textContent = "✓ World rules saved to project.";
        } catch (err) {
          if (rulesMsg) rulesMsg.textContent = "Error: " + err.message;
        } finally {
          btnSaveRules.disabled = false;
        }
      });
    }

    if (btnSaveParams) {
      btnSaveParams.addEventListener("click", async () => {
        const selProj = $("proj");
        const slug = (selProj && selProj.value) || activeProject || "";
        if (!slug) { alert("Pick or save a book in Step 01 first."); return; }
        btnSaveParams.disabled = true;
        if (paramsMsg) paramsMsg.textContent = "Saving lighting & palette…";
        try {
          await callApi("/api/global_params", {
            project: slug,
            positives: posEl ? posEl.value : "",
            negatives: negEl ? negEl.value : ""
          });
          if (paramsMsg) paramsMsg.textContent = "✓ Lighting & palette saved to project.";
        } catch (err) {
          if (paramsMsg) paramsMsg.textContent = "Error: " + err.message;
        } finally {
          btnSaveParams.disabled = false;
        }
      });
    }

    const selProj = $("proj");
    if (selProj) {
      selProj.addEventListener("change", () => {
        if (currentStep === 7) loadV2Continuity();
      });
    }
  }

  // ===== STEP 13 & STEP 18: GEMINI OMNI 1.2 FLASH =====
  let v2OmniInteractions = {};

  async function loadV2GeminiStatus() {
    const badge = $("v2GeminiKeyBadge");
    const omniBadge = $("v2OmniBadge");
    const selProj = $("proj");
    const slug = (selProj && selProj.value) || activeProject || "";
    try {
      const st = await callApi(`/api/gemini_omni_status?project=${encodeURIComponent(slug)}`);
      v2OmniInteractions = (st && st.interactions) || {};
      const ready = Boolean(st && st.configured && st.sdk_installed);
      if (badge) {
        if (ready) {
          badge.textContent = "✓ Gemini API Connected";
          badge.className = "status-badge status-badge--synced";
        } else if (st && st.configured && !st.sdk_installed) {
          badge.textContent = "⚠️ Key saved — install: pip install -U google-genai";
          badge.className = "status-badge status-badge--drift";
        } else {
          badge.textContent = "API Key Not Set";
          badge.className = "status-badge status-badge--drift";
        }
      }
      if (omniBadge) {
        omniBadge.textContent = ready ? "✓ Omni 1.2 Flash Ready" : "Configure GEMINI_API_KEY in Step 13";
        omniBadge.className = "status-badge " + (ready ? "status-badge--synced" : "status-badge--drift");
      }
      syncV2OmniInteractionId();
    } catch (e) {}
  }

  function syncV2OmniInteractionId() {
    const shotEl = $("v2OmniShot");
    const prevEl = $("v2OmniPrevId");
    if (!shotEl || !prevEl) return;
    const n = Math.max(1, parseInt(shotEl.value || "1", 10) || 1);
    const key = `shot-${String(n).padStart(3, "0")}`;
    const saved = v2OmniInteractions[key];
    if (saved && saved.interaction_id) {
      prevEl.value = saved.interaction_id;
    } else if (!prevEl.dataset.userTyped) {
      prevEl.value = "";
    }
  }

  function initV2GeminiOmni() {
    const btnKey = $("bSaveGeminiKey");
    const keyInput = $("v2GeminiKeyInput");
    const btnRun = $("bRunGeminiOmni");
    const shotEl = $("v2OmniShot");
    const prevEl = $("v2OmniPrevId");

    if (btnKey && keyInput) {
      btnKey.addEventListener("click", async () => {
        const apiKey = keyInput.value.trim();
        if (!apiKey) { alert("Paste your GEMINI_API_KEY from Google AI Studio first."); return; }
        btnKey.disabled = true;
        try {
          await callApi("/api/gemini_omni_key", { api_key: apiKey });
          keyInput.value = "";
          await loadV2GeminiStatus();
          loadStepAutopilot();
        } catch (err) {
          alert("Could not save Gemini API key: " + err.message);
        } finally {
          btnKey.disabled = false;
        }
      });
    }

    if (shotEl) shotEl.addEventListener("change", syncV2OmniInteractionId);
    if (prevEl) prevEl.addEventListener("input", () => { prevEl.dataset.userTyped = prevEl.value ? "1" : ""; });

    if (btnRun) {
      btnRun.addEventListener("click", async () => {
        const prompt = ($("v2OmniPrompt") || {}).value ? $("v2OmniPrompt").value.trim() : "";
        const statusEl = $("v2OmniStatus");
        if (!prompt) { alert("Enter a shot prompt or conversational edit instruction first."); return; }
        const selProj = $("proj");
        const slug = (selProj && selProj.value) || activeProject || "";
        const shot = parseInt(($("v2OmniShot") || {}).value || "1", 10) || 1;
        const duration = parseInt(($("v2OmniDuration") || {}).value || "10", 10) || 10;
        const resolution = ($("v2OmniResolution") || {}).value || "720p";
        const aspect_ratio = ($("v2OmniAspect") || {}).value || "16:9";
        const previous_interaction_id = (($("v2OmniPrevId") || {}).value || "").trim() || null;

        btnRun.disabled = true;
        if (statusEl) statusEl.textContent = `Generating Shot ${shot} (${duration}s @ ${resolution}) via Gemini Omni 1.2 Flash…`;
        try {
          const res = await callApi("/api/gemini_omni_generate", {
            project: slug,
            shot,
            prompt,
            duration,
            resolution,
            aspect_ratio,
            previous_interaction_id
          });
          if (res.interaction_id && prevEl) prevEl.value = res.interaction_id;
          if (statusEl) {
            statusEl.textContent = `✓ Saved ${res.output} (${Math.round((res.bytes || 0) / 1024)} KB) · Interaction ID: ${res.interaction_id || "none"}`;
          }
          await loadV2GeminiStatus();
        } catch (err) {
          if (statusEl) statusEl.textContent = "Error: " + err.message;
        } finally {
          btnRun.disabled = false;
        }
      });
    }
  }

  // ===== INITIALIZATION & BINDING =====
  window.addEventListener("DOMContentLoaded", () => {
    // Pipeline mode is the default: hide all classic panels below
    document.body.classList.add("mode-pipeline");

    initDirectStoryInput();
    initWorkbenchToggle();
    initV2Coverage();
    initV2Scope();
    initV2StoryBreakdown();
    initV2Screenplay();
    initV2Continuity();
    initV2GeminiOmni();

    // Bind step pills in 6-phase bar
    document.querySelectorAll(".step-pill").forEach(pill => {
      pill.addEventListener("click", () => {
        const stepNum = parseInt(pill.dataset.step, 10);
        activateStep(stepNum);
      });
    });

    // Bind next/prev buttons in all step action docks
    document.querySelectorAll(".btn-step-next").forEach(btn => {
      btn.addEventListener("click", (e) => {
        e.preventDefault();
        activateStep(currentStep + 1);
      });
    });

    document.querySelectorAll(".btn-step-prev").forEach(btn => {
      btn.addEventListener("click", (e) => {
        e.preventDefault();
        activateStep(currentStep - 1);
      });
    });

    // Bind Re-sync storyline button
    document.querySelectorAll(".btn-resync-storyline").forEach(btn => {
      btn.addEventListener("click", triggerSelectiveStorylineRedo);
    });

    // Bind Audio Redo buttons
    document.querySelectorAll(".btn-audio-dialect").forEach(btn => {
      btn.addEventListener("click", () => {
        const dialect = btn.dataset.dialect || "british";
        triggerAudioRedo("dialogue", dialect);
      });
    });

    // Restore saved step if available
    let savedStep = 1;
    try {
      savedStep = parseInt(localStorage.getItem("studio_v2_active_step") || "1", 10) || 1;
    } catch (e) {}
    activateStep(savedStep);

    setTimeout(() => {
      checkStepStorylineDrift();
      loadV2Coverage();
      loadV2Scope();
      loadV2GeminiStatus();
      if (currentStep === 5) loadV2StoryBreakdown();
      if (currentStep === 6) loadV2Screenplay();
      if (currentStep === 7) loadV2Continuity();
    }, 1200);
  });

  // Export methods for global access
  window.StudioV2 = {
    activateStep,
    loadV2Coverage,
    loadV2Scope,
    loadV2StoryBreakdown,
    loadV2Screenplay,
    loadV2Continuity,
    loadV2GeminiStatus,
    triggerAudioRedo,
    triggerSelectiveStorylineRedo,
    checkStepStorylineDrift,
  };
})();
