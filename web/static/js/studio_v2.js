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
    const opts = body !== undefined ? {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body)
    } : { method: "GET" };
    const r = await fetch(url, opts);
    const j = await r.json();
    if (!r.ok) throw new Error(j.detail || j.message || r.statusText);
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

    // Check for storyline drift and load step autopilot
    checkStepStorylineDrift();
    loadStepAutopilot();
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

    setTimeout(checkStepStorylineDrift, 1200);
  });

  // Export methods for global access
  window.StudioV2 = {
    activateStep,
    triggerAudioRedo,
    triggerSelectiveStorylineRedo,
    checkStepStorylineDrift,
  };
})();
