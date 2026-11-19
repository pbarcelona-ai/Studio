// studio_v2.js - Studio v2 Architecture: 20-Step Guided Pipeline + Creative Workbench,
// Top-to-Bottom Flow, Direct Story Input Saving, Audio Redo, Storyline Drift Sync,
// and Autopilot Model Recommendations.

(function () {
  "use strict";

  // ===== CONFIG & STATE =====
  const V2_STEPS = [
    { num: 1, id: "ingest", name: "01 Ingest", title: "Story Ingest & Source", phase: 1, phaseName: "Story & Script" },
    { num: 2, id: "format", name: "02 Format", title: "Format & Scope", phase: 1, phaseName: "Story & Script" },
    { num: 3, id: "coverage", name: "03 Coverage", title: "Coverage & Logline", phase: 1, phaseName: "Story & Script" },
    { num: 4, id: "structure", name: "04 Beats", title: "Story Structure & Beats", phase: 1, phaseName: "Story & Script" },
    { num: 5, id: "screenplay", name: "05 Script", title: "Screenplay Editor (Dialogue Default)", phase: 1, phaseName: "Story & Script" },

    { num: 6, id: "shots", name: "06 Shots", title: "Shot List & Cinematography", phase: 2, phaseName: "Cast & World" },
    { num: 7, id: "continuity", name: "07 Continuity", title: "Continuity & World Rules", phase: 2, phaseName: "Cast & World" },
    { num: 8, id: "cast", name: "08 Cast", title: "Cast & Characters", phase: 2, phaseName: "Cast & World" },
    { num: 9, id: "locations", name: "09 Sets", title: "Locations & Sets", phase: 2, phaseName: "Cast & World" },
    { num: 10, id: "look", name: "10 Look", title: "Art Direction & Style Recipe", phase: 2, phaseName: "Cast & World" },
    { num: 11, id: "lookdev", name: "11 Turnaround", title: "Look Development & Turnarounds", phase: 2, phaseName: "Cast & World" },

    { num: 12, id: "voices", name: "12 Voice Cast", title: "Voice Casting & Dialects", phase: 3, phaseName: "Sound & Voices" },
    { num: 13, id: "dialogue", name: "13 Dialogue", title: "Dialogue Delivery & Inflection", phase: 3, phaseName: "Sound & Voices" },
    { num: 14, id: "score", name: "14 Score & Foley", title: "Cinematic Score & MMAudio Foley", phase: 3, phaseName: "Sound & Voices" },

    { num: 15, id: "keyframes", name: "15 Keyframes", title: "Storyboard Keyframes (FLUX/SDXL)", phase: 4, phaseName: "Visuals & Motion" },
    { num: 16, id: "video", name: "16 Video", title: "Motion & Video Synthesis (Wan 2.1)", phase: 4, phaseName: "Visuals & Motion" },
    { num: 17, id: "polish", name: "17 Polish", title: "Lip-Sync & Real-ESRGAN Polish", phase: 4, phaseName: "Visuals & Motion" },

    { num: 18, id: "timeline", name: "18 Timeline", title: "Sequence Timeline Assembly", phase: 5, phaseName: "Post & Premiere" },
    { num: 19, id: "mix", name: "19 Audio Mix", title: "Stem Audio Mix (-16 LUFS)", phase: 5, phaseName: "Post & Premiere" },
    { num: 20, id: "premiere", name: "20 Premiere", title: "Cinema Premiere & Multi-Format Export", phase: 5, phaseName: "Post & Premiere" },
  ];

  let currentStep = 1;
  let activeProject = "";

  // Helper for DOM access
  function $(id) {
    return document.getElementById(id);
  }

  // Helper for JSON fetch
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

  // ===== DIRECT STORY INPUT BOX SAVING (User's feature request) =====
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
    currentStep = Math.max(1, Math.min(20, stepNum));

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

    // Update Phase Indicator Highlights
    document.querySelectorAll(".phase-group").forEach(group => {
      const phaseNum = parseInt(group.dataset.phase, 10);
      const stepMeta = V2_STEPS.find(s => s.num === currentStep);
      group.classList.toggle("phase-active", stepMeta && stepMeta.phase === phaseNum);
    });

    // Smooth scroll to top of workspace (Zero vertical hunting!)
    const activePanel = document.querySelector(`.step-panel[data-step="${currentStep}"]`);
    if (activePanel) {
      activePanel.scrollIntoView({ behavior: "smooth", block: "start" });
    }

    // Save step progress to localStorage
    try {
      localStorage.setItem("studio_v2_active_step", String(currentStep));
    } catch (e) { /* ignore in private window */ }

    // Check for storyline drift or load step autopilot
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
    } catch (e) {
      // Quiet fail if no book plan exists yet
    }
  }

  async function triggerSelectiveStorylineRedo() {
    const selProj = $("proj");
    const slug = (selProj && selProj.value) || activeProject || "";
    if (!slug) return;

    try {
      const res = await callApi("/api/redo_storyline", { project: slug });
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
    } catch (e) {
      // Offline or fallback
    }
  }

  // ===== CREATIVE WORKBENCH TOGGLE =====
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

    dropdown.querySelectorAll(".wb-tab-btn").forEach(wbBtn => {
      wbBtn.addEventListener("click", () => {
        const targetId = wbBtn.dataset.target;
        // Find existing advanced tab button or trigger click
        const tabBtn = document.querySelector(`.tab-btn[aria-controls="${targetId}"]`) ||
                       document.querySelector(`.tab-btn[data-tab="${targetId.replace('panel-', '')}"]`);
        if (tabBtn) {
          tabBtn.click();
        } else {
          // Switch manually
          document.querySelectorAll(".tab-panel").forEach(p => p.classList.remove("active"));
          const targetPanel = $(targetId);
          if (targetPanel) targetPanel.classList.add("active");
        }
        dropdown.classList.add("hidden");
      });
    });
  }

  // ===== INITIALIZATION & BINDING =====
  window.addEventListener("DOMContentLoaded", () => {
    initDirectStoryInput();
    initWorkbenchToggle();

    // Bind step pills in 5-phase bar
    document.querySelectorAll(".step-pill").forEach(pill => {
      pill.addEventListener("click", () => {
        const stepNum = parseInt(pill.dataset.step, 10);
        activateStep(stepNum);
      });
    });

    // Bind next/redo buttons in all step action docks
    document.querySelectorAll(".btn-step-next").forEach(btn => {
      btn.addEventListener("click", () => {
        activateStep(currentStep + 1);
      });
    });

    document.querySelectorAll(".btn-step-prev").forEach(btn => {
      btn.addEventListener("click", () => {
        activateStep(currentStep - 1);
      });
    });

    // Bind Re-sync storyline button
    document.querySelectorAll(".btn-resync-storyline").forEach(btn => {
      btn.addEventListener("click", triggerSelectiveStorylineRedo);
    });

    // Bind Audio Redo buttons (Dialogue default, Dialect switches)
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

    // Initial check
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
