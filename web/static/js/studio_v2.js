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

    // If entering Step 6 (Screenplay), load all screenplay scenes
    if (currentStep === 6) {
      loadV2Screenplay();
    }

    // Check for storyline drift and load step autopilot
    checkStepStorylineDrift();
    loadStepAutopilot();
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

  // ===== INITIALIZATION & BINDING =====
  window.addEventListener("DOMContentLoaded", () => {
    // Pipeline mode is the default: hide all classic panels below
    document.body.classList.add("mode-pipeline");

    initDirectStoryInput();
    initWorkbenchToggle();
    initV2Screenplay();

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
      if (currentStep === 6) loadV2Screenplay();
    }, 1200);
  });

  // Export methods for global access
  window.StudioV2 = {
    activateStep,
    loadV2Screenplay,
    triggerAudioRedo,
    triggerSelectiveStorylineRedo,
    checkStepStorylineDrift,
  };
})();
