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

  const INSTALLABLE_ENGINES = [
    { key: "gemini-sdk", label: "Google Gemini SDK", pkgs: "google-genai", match: /google-genai|no module named ['"]?google\.genai/i },
    { key: "kokoro", label: "Kokoro-82M Neural TTS", pkgs: "kokoro, soundfile", match: /kokoro(?:-82m)?.*not installed|pip install kokoro|no module named ['"]?kokoro/i },
    { key: "huggingface", label: "Hugging Face Spaces Client", pkgs: "gradio_client, huggingface_hub", match: /gradio_client|huggingface_hub/i },
    { key: "pillow", label: "Pillow Image Library", pkgs: "pillow", match: /no module named ['"]?pil['"]?|pip install pillow/i },
  ];

  function showInstallApprovalModal(title, message) {
    return new Promise((resolve) => {
      const existing = $("v2InstallApprovalBackdrop");
      if (existing) existing.remove();

      const backdrop = document.createElement("div");
      backdrop.id = "v2InstallApprovalBackdrop";
      backdrop.style.cssText = "position:fixed;inset:0;background:rgba(2,6,23,0.78);backdrop-filter:blur(4px);display:flex;align-items:center;justify-content:center;z-index:9999;padding:16px;";

      const box = document.createElement("div");
      box.style.cssText = "background:#0f172a;border:1px solid #334155;border-radius:12px;max-width:460px;width:100%;padding:20px;box-shadow:0 20px 50px rgba(0,0,0,0.6);color:#f8fafc;";

      const h = document.createElement("h3");
      h.style.cssText = "margin:0 0 8px;font-size:16px;color:#f59e0b;";
      h.textContent = title;

      const p = document.createElement("p");
      p.style.cssText = "margin:0 0 18px;font-size:13px;line-height:1.5;color:#cbd5e1;white-space:pre-line;";
      p.textContent = message;

      const row = document.createElement("div");
      row.style.cssText = "display:flex;justify-content:flex-end;gap:10px;";

      const btnCancel = document.createElement("button");
      btnCancel.type = "button";
      btnCancel.className = "btn btn--ghost";
      btnCancel.textContent = "Cancel";

      const btnOk = document.createElement("button");
      btnOk.type = "button";
      btnOk.className = "btn btn--primary";
      btnOk.textContent = "OK";

      const cleanup = (val) => {
        backdrop.remove();
        resolve(val);
      };
      btnCancel.addEventListener("click", () => cleanup(false));
      btnOk.addEventListener("click", () => cleanup(true));
      backdrop.addEventListener("click", (e) => {
        if (e.target === backdrop) cleanup(false);
      });

      row.appendChild(btnCancel);
      row.appendChild(btnOk);
      box.appendChild(h);
      box.appendChild(p);
      box.appendChild(row);
      backdrop.appendChild(box);
      document.body.appendChild(backdrop);
      btnOk.focus();
    });
  }

  async function requestInstallWithApproval(engineKey, label, pkgs) {
    const ok = await showInstallApprovalModal(
      `Install ${label}?`,
      `This feature requires ${label} (${pkgs}) in Studio's Python environment.\n\nClick OK to install it automatically now, or Cancel to skip.`
    );
    if (!ok) return false;
    await rawCallApi("/api/v2_install_engine", { engine: engineKey, approved: true });
    return true;
  }

  async function rawCallApi(url, body, signal) {
    if (!signal && typeof window.api === "function") {
      return window.api(url, body);
    }
    const token = (document.querySelector('meta[name="studio-token"]') || {}).content || "";
    const headers = { "Content-Type": "application/json" };
    if (token && token !== "__TOKEN__") headers["X-Studio-Token"] = token;
    const opts = body !== undefined ? {
      method: "POST",
      headers,
      body: JSON.stringify(body),
      ...(signal ? { signal } : {})
    } : { method: "GET", headers, ...(signal ? { signal } : {}) };
    const r = await fetch(url, opts);
    const j = await r.json();
    if (!r.ok) throw new Error(j.error || j.detail || j.message || r.statusText);
    return j;
  }

  // ===== ACTIVE GENERATION VISUAL FEEDBACK (BUTTON + CARD + FLOATING LIVE PILL) =====
  let _v2LastClickedBtn = null;
  let _v2ActivityTimer = null;
  let _v2ActiveTasks = 0;

  document.addEventListener("click", (e) => {
    const btn = e.target && e.target.closest ? e.target.closest("button") : null;
    if (btn) _v2LastClickedBtn = btn;
  }, true);

  function _ensureActivityPill() {
    let pill = $("v2GlobalActivityPill");
    if (!pill) {
      pill = document.createElement("div");
      pill.id = "v2GlobalActivityPill";
      pill.setAttribute("role", "status");
      pill.setAttribute("aria-live", "polite");
      const sp = document.createElement("span");
      sp.className = "v2-pill-spinner";
      const txt = document.createElement("span");
      txt.id = "v2GlobalActivityText";
      pill.appendChild(sp);
      pill.appendChild(txt);
      document.body.appendChild(pill);
    }
    return pill;
  }

  function startBusyFeedback(btn, cards, label) {
    const targetBtn = btn || _v2LastClickedBtn;
    const cardList = Array.isArray(cards)
      ? cards.filter(Boolean)
      : cards
        ? [cards]
        : (targetBtn && targetBtn.closest ? [targetBtn.closest(".v2-dlg-card, .deliverable-card, .direct-story-card")].filter(Boolean) : []);

    let origText = null;
    let origDisabled = false;
    if (targetBtn && !targetBtn.classList.contains("v2-busy-btn")) {
      origText = targetBtn.textContent;
      origDisabled = targetBtn.disabled;
      targetBtn.classList.add("v2-busy-btn");
      targetBtn.disabled = true;
    }
    cardList.forEach(c => c.classList.add("v2-busy-card"));

    _v2ActiveTasks++;
    const pill = _ensureActivityPill();
    const txtEl = $("v2GlobalActivityText");
    const startedAt = Date.now();
    const baseLabel = label || "Working…";
    const updatePill = () => {
      const secs = Math.max(0, Math.floor((Date.now() - startedAt) / 1000));
      if (txtEl) txtEl.textContent = secs > 0 ? `${baseLabel} (${secs}s)` : baseLabel;
    };
    updatePill();
    pill.classList.add("visible");
    if (_v2ActivityTimer) clearInterval(_v2ActivityTimer);
    _v2ActivityTimer = setInterval(updatePill, 1000);

    return function stopBusyFeedback() {
      if (targetBtn && origText !== null) {
        targetBtn.classList.remove("v2-busy-btn");
        targetBtn.disabled = origDisabled;
        targetBtn.textContent = origText;
      }
      cardList.forEach(c => c.classList.remove("v2-busy-card"));
      _v2ActiveTasks = Math.max(0, _v2ActiveTasks - 1);
      if (_v2ActiveTasks === 0) {
        if (_v2ActivityTimer) { clearInterval(_v2ActivityTimer); _v2ActivityTimer = null; }
        pill.classList.remove("visible");
      }
    };
  }

  // ===== APP-WIDE "NEEDS ATTENTION" FLASHING ALERT HELPER (ANY STEP) =====
  function flagNeedsAttention(cardEl, reason) {
    if (!cardEl) return;
    cardEl.classList.add("v2-needs-attention");
    let banner = cardEl.querySelector(".v2-attention-banner");
    if (!banner) {
      banner = document.createElement("div");
      banner.className = "v2-attention-banner";
      banner.style.marginBottom = "6px";
      cardEl.insertBefore(banner, cardEl.firstChild);
    }
    banner.textContent = "⚠️ Needs Attention: " + (reason || "Please add a specific description");
  }

  function clearNeedsAttention(cardEl) {
    if (!cardEl) return;
    cardEl.classList.remove("v2-needs-attention");
    const banner = cardEl.querySelector(".v2-attention-banner");
    if (banner) banner.remove();
  }

  // ===== UPSTREAM FEEDBACK SYNC (LATER STEP -> EARLIER STEPS WITH USER PERMISSION) =====
  async function proposeUpstreamSync({ project, kind, affectedStepNums, title, message, payload, onSynced }) {
    if (!project || !kind) return false;
    const pills = (affectedStepNums || [])
      .map(n => document.querySelector(`.step-pill[data-step="${n}"]`))
      .filter(Boolean);
    pills.forEach(p => p.classList.add("v2-needs-attention"));
    try {
      const ok = await showInstallApprovalModal(
        title || "🔄 Update Earlier Step(s) to Match?",
        message + "\n\nClick OK to update the earlier step(s) automatically, or Cancel to leave them unchanged."
      );
      if (!ok) return false;
      const res = await rawCallApi("/api/v2_sync_upstream", { project, kind, approved: true, payload });
      if (typeof onSynced === "function") onSynced(res);
      return true;
    } catch (e) {
      return false;
    } finally {
      pills.forEach(p => p.classList.remove("v2-needs-attention"));
    }
  }

  const BUSY_API_LABELS = [
    [/\/api\/v2_dialogue_render/, "Generating dialogue audio…"],
    [/\/api\/v2_sound_design_render/, "Generating Score / Foley audio…"],
    [/\/api\/v2_keyframe_render/, "Generating storyboard keyframe…"],
    [/\/api\/v2_keyframe_edit/, "Modifying keyframe aspect…"],
    [/\/api\/v2_turnaround_render/, "Generating character turnaround…"],
    [/\/api\/v2_audio_mix_render/, "Mixing master audio stems…"],
    [/\/api\/v2_export_make/, "Building export deliverable…"],
    [/\/api\/save_story/, "Saving & reading book into chapters…"],
    [/\/api\/v2_ingest_book/, "Reading book & splitting chapters…"],
    [/\/api\/gemini_omni_generate/, "Generating video via Gemini Omni 1.2 Flash…"],
    [/\/api\/v2_install_engine/, "Installing package into Studio…"],
    [/\/api\/v2_voice_baseline_set/, "Saving character voice baseline…"],
    [/\/api\/v2_voice_profile_apply/, "Applying voice profile across all scenes…"],
    [/\/api\/v2_dialogue_upload/, "Uploading custom audio take…"],
    [/\/api\/redo_audio/, "Updating voice cast & dialect…"],
    [/\/api\/shot_list/, "Generating shot list…"],
    [/\/api\/continuity_bootstrap/, "Building continuity book…"],
    [/\/api\/continuity/, "Generating continuity book…"],
    [/\/api\/readin/, "Analyzing story & beats…"],
    [/\/api\/run/, "Running studio pipeline step…"],
  ];

  async function callApi(url, body) {
    let stopBusy = null;
    if (body !== undefined) {
      const hit = BUSY_API_LABELS.find(([re]) => re.test(url));
      if (hit) {
        stopBusy = startBusyFeedback(null, null, hit[1]);
      }
    }
    try {
      return await rawCallApi(url, body);
    } catch (err) {
      const msg = String((err && err.message) || err || "");
      if (url !== "/api/v2_install_engine") {
        const hit = INSTALLABLE_ENGINES.find(e => e.match.test(msg));
        if (hit) {
          if (stopBusy) { stopBusy(); stopBusy = null; }
          const installed = await requestInstallWithApproval(hit.key, hit.label, hit.pkgs);
          if (installed) {
            return await rawCallApi(url, body);
          }
        }
      }
      throw err;
    } finally {
      if (stopBusy) stopBusy();
    }
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
          statusMsg.textContent = `✓ Saved & read books/${res.filename} (${res.chapters || 1} chapter(s))`;
          statusMsg.className = "status-badge status-badge--synced";
        }

        // Auto-refresh the book dropdown with the exact ingested project slug
        const selProj = $("proj");
        if (selProj) {
          const optSlug = res.slug || res.filename.replace(/\.[^/.]+$/, "").toLowerCase().replace(/[^a-z0-9]+/g, "_");
          let found = false;
          for (let i = 0; i < selProj.options.length; i++) {
            if (selProj.options[i].value === optSlug) {
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
        if (typeof window.loadChapters === "function") {
          try { window.loadChapters(); } catch (e) {}
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

    // Also auto-ingest when a book file (.pdf, .epub, .docx, .txt) is picked in Step 01
    const fileInput = $("file");
    if (fileInput) {
      fileInput.addEventListener("change", async () => {
        const f = fileInput.files && fileInput.files[0];
        if (!f) return;
        const stopBusy = startBusyFeedback(null, fileInput.closest(".card"), `Uploading & reading ${f.name}…`);
        if (statusMsg) {
          statusMsg.textContent = `Uploading & reading ${f.name}…`;
          statusMsg.className = "status-badge status-badge--working";
        }
        try {
          const token = (document.querySelector('meta[name="studio-token"]') || {}).content || "";
          const headers = {};
          if (token && token !== "__TOKEN__") headers["X-Studio-Token"] = token;
          const upResp = await fetch(`/api/upload?name=${encodeURIComponent(f.name)}`, {
            method: "POST",
            headers,
            body: f,
          });
          const upJson = await upResp.json().catch(() => ({}));
          if (!upResp.ok) throw new Error(upJson.error || upResp.statusText);
          const uploadedName = upJson.saved || upJson.name || f.name;
          const ing = await callApi("/api/v2_ingest_book", { filename: uploadedName });
          const selProj = $("proj");
          if (selProj && ing.slug) {
            let found = false;
            for (let i = 0; i < selProj.options.length; i++) {
              if (selProj.options[i].value === ing.slug) { selProj.selectedIndex = i; found = true; break; }
            }
            if (!found) {
              const opt = document.createElement("option");
              opt.value = ing.slug;
              opt.text = uploadedName;
              opt.selected = true;
              selProj.add(opt);
            }
            selProj.dispatchEvent(new Event("change"));
          }
          if (typeof window.loadChapters === "function") {
            try { window.loadChapters(); } catch (e) {}
          }
          if (statusMsg) {
            statusMsg.textContent = `✓ Ingested "${uploadedName}" (${ing.chapters || 1} chapter(s) ready)`;
            statusMsg.className = "status-badge status-badge--synced";
          }
        } catch (err) {
          if (statusMsg) {
            statusMsg.textContent = "Ingest error: " + (err.message || err);
            statusMsg.className = "status-badge status-badge--drift";
          }
        } finally {
          stopBusy();
        }
      });
    }

    // Step 02: Manual "Read Book & Split Chapters" button for any unread book
    const btnIngest = $("bV2IngestBook");
    if (btnIngest) {
      btnIngest.addEventListener("click", async () => {
        const slug = ($("proj")?.value || "").trim();
        if (!slug) { alert("Select or upload a book in Step 01 first."); return; }
        const note = $("chapNote");
        if (note) note.textContent = `Reading & splitting chapters for "${slug}"…`;
        try {
          const res = await callApi("/api/v2_ingest_book", { project: slug });
          if (note) note.textContent = `✓ Read "${res.source || slug}" (${res.chapters || 1} chapter(s)).`;
          if (typeof window.loadChapters === "function") window.loadChapters();
        } catch (err) {
          if (note) note.textContent = "Could not read book: " + (err.message || err);
        }
      });
    }

    // Step 01: One-Click Autopilot "Make Full Film" button with Film Type & Voices Popup
    const btnAuto = $("bV2AutopilotFilm");
    if (btnAuto) {
      btnAuto.addEventListener("click", () => launchV2AutopilotFilm());
    }
  }

  // ===== ONE-CLICK AUTOPILOT: FULL FILM CREATION (STEPS 01 -> 22) =====
  function showAutopilotFilmModal(bookSlug) {
    return new Promise((resolve) => {
      const existing = $("v2AutopilotModalBackdrop");
      if (existing) existing.remove();

      const backdrop = document.createElement("div");
      backdrop.id = "v2AutopilotModalBackdrop";
      backdrop.style.cssText = "position:fixed;inset:0;background:rgba(2,6,23,0.82);backdrop-filter:blur(5px);display:flex;align-items:center;justify-content:center;z-index:9999;padding:16px;";

      const box = document.createElement("div");
      box.style.cssText = "background:#0f172a;border:1px solid #f59e0b;border-radius:14px;max-width:520px;width:100%;padding:22px;box-shadow:0 24px 60px rgba(0,0,0,0.7);color:#f8fafc;";
      box.innerHTML = `
        <h3 style="margin:0 0 6px;font-size:18px;color:#f59e0b">🚀 One-Click Full Film Autopilot</h3>
        <p style="margin:0 0 14px;font-size:13px;color:#cbd5e1;line-height:1.45">
          Automatically runs <strong>${bookSlug}</strong> from book ingest through chapters, screenplay, continuity, shot list, spoken dialogue, score &amp; foley, keyframes, audio mix, and final MP4 premiere.
        </p>
        <div style="display:flex;flex-direction:column;gap:10px;margin-bottom:18px">
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">
            <div>
              <label class="f" for="v2AutoLook">Film Visual Style / Type</label>
              <select id="v2AutoLook" style="width:100%;padding:8px;background:#0a0d14;color:#f8fafc;border:1px solid #334155;border-radius:6px;font-size:13px">
                <option value="pixar_3d" selected>Pixar 3D Animated Feature</option>
                <option value="pixar_disney">Classic 3D Storybook Feature</option>
                <option value="live_action">Cinematic Live Action (35mm)</option>
                <option value="claymation">Stop-Motion Claymation</option>
                <option value="travel_poster">Vintage Illustrated Travel Poster</option>
                <option value="cyberpunk_3d">Stylized 3D Sci-Fi / Cyberpunk</option>
              </select>
            </div>
            <div>
              <label class="f" for="v2AutoLength">Target Film Length</label>
              <select id="v2AutoLength" style="width:100%;padding:8px;background:#0a0d14;color:#f8fafc;border:1px solid #334155;border-radius:6px;font-size:13px">
                <option value="0" selected>Auto (Match Book Length)</option>
                <option value="2">2 min — Micro Short / Teaser</option>
                <option value="5">5 min — Short Film</option>
                <option value="10">10 min — Extended Short</option>
                <option value="15">15 min — Featurette</option>
                <option value="30">30 min — TV Episode</option>
                <option value="60">60 min — Feature Film</option>
                <option value="90">90 min — Full Cinema Feature</option>
              </select>
            </div>
          </div>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">
            <div>
              <label class="f" for="v2AutoVoiceEng">Voice Engine</label>
              <select id="v2AutoVoiceEng" style="width:100%;padding:8px;background:#0a0d14;color:#f8fafc;border:1px solid #334155;border-radius:6px;font-size:13px">
                <option value="gemini-tts" selected>✨ Gemini Neural TTS (Studio Final)</option>
                <option value="kokoro">🎙️ Kokoro-82M Local Neural</option>
                <option value="macos-say">⚡ Fast Scratch Preview (macOS)</option>
              </select>
            </div>
            <div>
              <label class="f" for="v2AutoDialect">Voice Dialect</label>
              <select id="v2AutoDialect" style="width:100%;padding:8px;background:#0a0d14;color:#f8fafc;border:1px solid #334155;border-radius:6px;font-size:13px">
                <option value="american" selected>🇺🇸 American English</option>
                <option value="british">🇬🇧 British RP</option>
              </select>
            </div>
          </div>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">
            <div>
              <label class="f" for="v2AutoScoreMood">Musical Score Mood</label>
              <select id="v2AutoScoreMood" style="width:100%;padding:8px;background:#0a0d14;color:#f8fafc;border:1px solid #334155;border-radius:6px;font-size:13px">
                <option value="wonder" selected>Wonder &amp; Discovery</option>
                <option value="epic">Epic Space Adventure</option>
                <option value="cozy">Warm &amp; Cozy Family</option>
                <option value="mysterious">Cosmic Mystery</option>
                <option value="playful">Playful &amp; Whimsical</option>
              </select>
            </div>
            <div>
              <label class="f" for="v2AutoKfLimit">Keyframes to Generate</label>
              <select id="v2AutoKfLimit" style="width:100%;padding:8px;background:#0a0d14;color:#f8fafc;border:1px solid #334155;border-radius:6px;font-size:13px">
                <option value="12" selected>First 12 Shots (Fast Film Cut)</option>
                <option value="30">First 30 Shots (Extended Cut)</option>
                <option value="9999">All Shots in Film</option>
              </select>
            </div>
          </div>
        </div>
        <div style="display:flex;justify-content:flex-end;gap:10px">
          <button type="button" class="btn btn--ghost" id="bV2AutoCancel">Cancel</button>
          <button type="button" class="btn btn--primary" id="bV2AutoStart">🚀 OK — Make Full Film</button>
        </div>
      `;
      backdrop.appendChild(box);
      document.body.appendChild(backdrop);

      const finish = (val) => { backdrop.remove(); resolve(val); };
      box.querySelector("#bV2AutoCancel").addEventListener("click", () => finish(null));
      backdrop.addEventListener("click", (e) => { if (e.target === backdrop) finish(null); });
      box.querySelector("#bV2AutoStart").addEventListener("click", () => {
        finish({
          look: box.querySelector("#v2AutoLook").value,
          lengthMin: parseInt(box.querySelector("#v2AutoLength").value, 10) || 0,
          voiceEngine: box.querySelector("#v2AutoVoiceEng").value,
          dialect: box.querySelector("#v2AutoDialect").value,
          scoreMood: box.querySelector("#v2AutoScoreMood").value,
          kfLimit: parseInt(box.querySelector("#v2AutoKfLimit").value, 10) || 12,
        });
      });
    });
  }

  function _sleepAbortable(ms, signal) {
    return new Promise((resolve) => {
      if (signal && signal.aborted) return resolve();
      const tid = setTimeout(() => {
        if (signal) signal.removeEventListener("abort", onAbort);
        resolve();
      }, ms);
      const onAbort = () => {
        clearTimeout(tid);
        resolve();
      };
      if (signal) signal.addEventListener("abort", onAbort, { once: true });
    });
  }

  async function waitForStudioJob(isCancelled, onLine, signal) {
    let since = 0;
    let idleStreak = 0;
    while (!isCancelled()) {
      await _sleepAbortable(1200, signal);
      if (isCancelled()) return false;
      try {
        const lg = await rawCallApi(`/api/log?since=${since}`, undefined, signal);
        since = lg.next || since;
        if (lg.lines && lg.lines.length && onLine) {
          onLine(String(lg.lines[lg.lines.length - 1] || "").slice(0, 120));
        }
        if (!lg.running && !(lg.queued > 0)) {
          idleStreak++;
          if (idleStreak >= 2) return true; // confirm job is truly idle before starting next stage
        } else {
          idleStreak = 0;
        }
      } catch (e) {
        if (isCancelled() || (e && e.name === "AbortError")) return false;
      }
    }
    return false;
  }

  let _v2AutopilotRunning = false;

  async function launchV2AutopilotFilm() {
    if (_v2AutopilotRunning) return;
    // If user typed a story in Step 01 but hasn't clicked Save yet, save & ingest it first!
    let slug = ($("proj")?.value || "").trim();
    const typedText = ($("storyInputText")?.value || "").trim();
    if (!slug && typedText) {
      const fn = ($("storyFilename")?.value || "my_story.txt").trim();
      const sv = await callApi("/api/save_story", { filename: fn, text: typedText });
      slug = sv.slug;
    }
    if (!slug) {
      alert("Paste a story, upload a book file, or select a book in Step 01 first.");
      return;
    }

    const cfg = await showAutopilotFilmModal(slug);
    if (!cfg) return;

    _v2AutopilotRunning = true;

    // Show live Autopilot progress overlay with graceful Stop button
    let cancelled = false;
    const ac = new AbortController();
    const makeCancelErr = () => {
      const e = new Error("Autopilot stopped by user");
      e.name = "AutopilotCancelled";
      return e;
    };
    const checkCancelled = () => {
      if (cancelled || ac.signal.aborted) throw makeCancelErr();
    };
    const autoApi = async (url, body) => {
      checkCancelled();
      const res = await rawCallApi(url, body, ac.signal);
      checkCancelled();
      return res;
    };

    const overlay = document.createElement("div");
    overlay.id = "v2AutopilotProgressOverlay";
    overlay.style.cssText = "position:fixed;inset:0;background:rgba(2,6,23,0.86);backdrop-filter:blur(6px);display:flex;align-items:center;justify-content:center;z-index:9999;padding:16px;";
    overlay.innerHTML = `
      <div style="background:#0f172a;border:1px solid #f59e0b;border-radius:14px;max-width:560px;width:100%;padding:22px;color:#f8fafc;box-shadow:0 24px 60px rgba(0,0,0,0.75)">
        <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;margin-bottom:10px">
          <h3 style="margin:0;color:#f59e0b;font-size:17px">🎬 Making Full Film: ${slug}</h3>
          <button type="button" class="btn btn--ghost" id="bV2AutoStop" style="color:#f87171;padding:4px 10px;font-size:12px">⏹ Stop</button>
        </div>
        <div id="v2AutoStageText" style="font-size:13px;color:#fde68a;font-weight:600;margin-bottom:8px">Starting Autopilot…</div>
        <div style="background:#1e293b;height:8px;border-radius:999px;overflow:hidden;margin-bottom:12px">
          <div id="v2AutoBar" style="height:100%;width:5%;background:linear-gradient(90deg,#f59e0b,#10b981);transition:width 0.35s"></div>
        </div>
        <pre id="v2AutoLog" style="background:#0a0d14;border:1px solid #1e293b;border-radius:8px;padding:10px;max-height:220px;overflow:auto;font-size:11px;color:#cbd5e1;white-space:pre-wrap;margin:0"></pre>
      </div>
    `;
    document.body.appendChild(overlay);
    const stageEl = overlay.querySelector("#v2AutoStageText");
    const barEl = overlay.querySelector("#v2AutoBar");
    const logEl = overlay.querySelector("#v2AutoLog");
    const btnStop = overlay.querySelector("#bV2AutoStop");
    const log = (msg) => {
      if (logEl) { logEl.textContent += msg + "\n"; logEl.scrollTop = logEl.scrollHeight; }
    };
    const setStage = (pct, msg) => {
      if (stageEl) stageEl.textContent = msg;
      if (barEl) barEl.style.width = `${pct}%`;
      log("▸ " + msg);
    };

    let canDismiss = false;
    const closeOverlay = () => {
      document.removeEventListener("keydown", onKeyDown);
      overlay.remove();
      try { activateStep(currentStep); } catch (e) {}
    };
    const onKeyDown = (e) => {
      if (e.key === "Escape" && canDismiss) closeOverlay();
    };
    document.addEventListener("keydown", onKeyDown);
    overlay.addEventListener("click", (e) => {
      if (e.target === overlay && canDismiss) closeOverlay();
    });

    const enableCloseButton = () => {
      canDismiss = true;
      btnStop.disabled = false;
      btnStop.textContent = "Close";
      btnStop.style.color = "#e2e8f0";
      btnStop.onclick = closeOverlay;
    };

    btnStop.onclick = () => {
      if (cancelled) return;
      cancelled = true;
      btnStop.disabled = true;
      btnStop.textContent = "Stopping safely…";
      if (stageEl) stageEl.textContent = "⏹ Stopping safely — halting active job…";
      if (barEl) barEl.style.background = "#64748b";
      log("⏹ Stop requested — halting current task safely…");
      // Tell backend to gracefully stop any running job and clear queued steps
      rawCallApi("/api/stop", {}).catch(() => {});
      // Abort any in-flight autopilot HTTP request immediately
      try { ac.abort(); } catch (e) {}
    };

    try {
      // 1. Ensure book is read & chapters split
      setStage(8, "Step 02: Reading book & splitting chapters…");
      try {
        const ch = await autoApi(`/api/chapters?project=${encodeURIComponent(slug)}`);
        if (!ch || !(ch.chapters || []).length) throw new Error("not read");
        log(`  ✓ ${ch.chapters.length} chapter(s) already ready.`);
      } catch (e) {
        if (cancelled || e?.name === "AbortError" || e?.name === "AutopilotCancelled") throw makeCancelErr();
        const ing = await autoApi("/api/v2_ingest_book", { project: slug });
        log(`  ✓ Book read & split into ${ing.chapters || 1} chapter(s).`);
      }
      checkCancelled();

      // 2. Save chosen film style & target runtime
      const lenLbl = cfg.lengthMin > 0 ? `${cfg.lengthMin} min` : "auto";
      setStage(16, `Step 09: Locking visual style (${cfg.look}) & target length (${lenLbl})…`);
      await autoApi("/api/global_params", {
        project: slug,
        look: cfg.look,
        ...(cfg.lengthMin > 0 ? { target_minutes: cfg.lengthMin } : {}),
      });
      checkCancelled();

      // 3. Ensure Coverage & Screenplay exist
      setStage(26, "Steps 03–06: Checking coverage, beats & screenplay…");
      let sp = null;
      try { sp = await autoApi(`/api/screenplay?project=${encodeURIComponent(slug)}`); } catch (e) {
        if (cancelled || e?.name === "AbortError" || e?.name === "AutopilotCancelled") throw makeCancelErr();
      }
      if (!sp || !(sp.scenes || []).length) {
        log(`  Writing coverage, beats & screenplay (target: ${lenLbl})…`);
        await autoApi("/api/read_it_in", {
          project: slug,
          ...(cfg.lengthMin > 0 ? { minutes: cfg.lengthMin } : {}),
        });
        const ok = await waitForStudioJob(() => cancelled, (ln) => log("  " + ln), ac.signal);
        if (!ok) throw makeCancelErr();
      } else {
        log(`  ✓ Screenplay ready (${sp.scenes.length} scenes).`);
      }
      checkCancelled();

      // 4. Continuity Book + Approve
      setStage(38, "Step 07: Building & approving continuity book…");
      let cb = null;
      try { cb = await autoApi(`/api/continuity_book?project=${encodeURIComponent(slug)}`); } catch (e) {
        if (cancelled || e?.name === "AbortError" || e?.name === "AutopilotCancelled") throw makeCancelErr();
      }
      if (!cb || !cb.book || !(cb.book.characters || []).length) {
        await autoApi("/api/continuity_bootstrap", { project: slug });
      }
      try { await autoApi("/api/continuity_approve", { project: slug }); } catch (e) {
        if (cancelled || e?.name === "AbortError" || e?.name === "AutopilotCancelled") throw makeCancelErr();
      }
      log("  ✓ Continuity book locked & approved.");
      checkCancelled();

      // 5. Shot List + Approve
      setStage(48, "Step 12: Checking & approving shot list…");
      let sl = null;
      try { sl = await autoApi(`/api/shot_list?project=${encodeURIComponent(slug)}`); } catch (e) {
        if (cancelled || e?.name === "AbortError" || e?.name === "AutopilotCancelled") throw makeCancelErr();
      }
      if (!sl || !sl.list || !(sl.list.scenes || []).length) {
        // Ensure any earlier background job has completely finished before starting shot_list
        const curJob = await autoApi("/api/log?since=0").catch(() => ({}));
        if (curJob && (curJob.running || curJob.queued > 0)) {
          log("  Waiting for active background job to finish before starting shot list…");
          const ok = await waitForStudioJob(() => cancelled, (ln) => log("  " + ln), ac.signal);
          if (!ok) throw makeCancelErr();
        }
        checkCancelled();
        log("  Generating shot list…");
        await autoApi("/api/shot_list", { project: slug, queue: true });
        const ok = await waitForStudioJob(() => cancelled, (ln) => log("  " + ln), ac.signal);
        if (!ok) throw makeCancelErr();
      }
      try { await autoApi("/api/shot_list_approve", { project: slug }); } catch (e) {
        if (cancelled || e?.name === "AbortError" || e?.name === "AutopilotCancelled") throw makeCancelErr();
      }
      log("  ✓ Shot list ready & approved.");
      checkCancelled();

      // 6. Voice Casting & Spoken Dialogue
      setStage(58, `Steps 14–15: Casting voices (${cfg.dialect}) & rendering dialogue via ${cfg.voiceEngine}…`);
      await autoApi("/api/redo_audio", { project: slug, mode: "dialogue", dialect: cfg.dialect });
      const dlg = await autoApi(`/api/v2_dialogue?project=${encodeURIComponent(slug)}`);
      const unrenderedDlg = (dlg.lines || []).filter(l => !l.has_audio);
      if (unrenderedDlg.length) {
        for (let i = 0; i < unrenderedDlg.length; i += 4) {
          checkCancelled();
          const batch = unrenderedDlg.slice(i, i + 4);
          log(`  Rendering dialogue lines ${i + 1}–${Math.min(i + 4, unrenderedDlg.length)} of ${unrenderedDlg.length}…`);
          await autoApi("/api/v2_dialogue_render", {
            project: slug,
            dialect: cfg.dialect,
            engine: cfg.voiceEngine,
            lines: batch,
          });
        }
      }
      log(`  ✓ Spoken dialogue ready (${(dlg.lines || []).length} lines).`);
      checkCancelled();

      // 7. Score & Foley
      setStage(70, `Step 16: Generating Foley & Cinematic Score (${cfg.scoreMood})…`);
      await autoApi("/api/v2_sound_design_render", { project: slug, kind: "foley", preset: "space_adventure", duration: 12 });
      await autoApi("/api/v2_sound_design_render", { project: slug, kind: "score", mood: cfg.scoreMood, duration: 15 });
      log("  ✓ Foley & Score tracks rendered.");
      checkCancelled();

      // 8. Storyboard Keyframes (up to chosen cap, skipping already rendered/locked)
      setStage(80, `Step 17: Rendering storyboard keyframes (up to ${cfg.kfLimit === 9999 ? "all" : cfg.kfLimit} shots)…`);
      const kf = await autoApi(`/api/v2_keyframes?project=${encodeURIComponent(slug)}`);
      const allShots = (kf.scenes || []).flatMap(sc => sc.shots || []);
      const todoShots = allShots.filter(s => !s.has_image && !s.locked).slice(0, cfg.kfLimit);
      for (let i = 0; i < todoShots.length; i++) {
        checkCancelled();
        const sh = todoShots[i];
        log(`  Rendering keyframe ${sh.id} (${i + 1}/${todoShots.length})…`);
        await autoApi("/api/v2_keyframe_render", { project: slug, id: sh.id, prompt: sh.prompt, aspect_ratio: "16:9" });
      }
      log(`  ✓ Keyframes ready.`);
      checkCancelled();

      // 9. Mix Master Audio
      setStage(90, "Step 21: Mixing Dialogue, Foley & Score stems…");
      await autoApi("/api/v2_audio_mix_render", { project: slug, dialogue_db: 0, foley_db: -3, score_db: -6, ducking: true });
      log("  ✓ Master audio mixed.");
      checkCancelled();

      // 10. Assemble Master MP4 & jump to Step 22 Premiere
      setStage(96, "Step 22: Assembling 16:9 Master Cinema MP4…");
      await autoApi("/api/v2_export_make", { project: slug, target: "master_mp4" });
      setStage(100, "🎉 Full Film Complete! Opening Cinema Premiere (Step 22)…");
      await new Promise(r => setTimeout(r, 900));
      document.removeEventListener("keydown", onKeyDown);
      overlay.remove();
      activateStep(22);
    } catch (err) {
      if (cancelled || err?.name === "AutopilotCancelled" || err?.name === "AbortError") {
        // Wait briefly for any backend job to finish winding down cleanly so Studio is immediately ready
        for (let k = 0; k < 8; k++) {
          try {
            const st = await rawCallApi("/api/log?since=0");
            if (!st || (!st.running && !(st.queued > 0))) break;
          } catch (e) { break; }
          await new Promise(r => setTimeout(r, 500));
        }
        log("✓ Stopped cleanly. All completed steps were saved — you can edit or resume from any step.");
        if (stageEl) stageEl.textContent = "⏹ Autopilot stopped cleanly — completed work saved";
        enableCloseButton();
        return;
      }
      log("❌ Autopilot paused on error: " + (err.message || err));
      if (stageEl) stageEl.textContent = "⚠️ Autopilot paused — see log below";
      enableCloseButton();
      return;
    } finally {
      _v2AutopilotRunning = false;
    }
  }

  // ===== SCROLL POSITION PRESERVATION =====
  function preserveScroll(container, fn) {
    const x = window.scrollX || 0;
    const y = window.scrollY || 0;
    let prevMinH = "";
    if (container && container.offsetHeight > 0) {
      prevMinH = container.style.minHeight || "";
      container.style.minHeight = container.offsetHeight + "px";
    }
    try {
      return fn();
    } finally {
      const restore = () => {
        window.scrollTo({ left: x, top: y, behavior: "instant" });
      };
      restore();
      requestAnimationFrame(() => {
        restore();
        if (container) container.style.minHeight = prevMinH;
      });
    }
  }

  // ===== NAVIGATION & TOP-TO-BOTTOM STEP CONTROLLER =====
  function activateStep(stepNum) {
    const prevStep = currentStep;
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

    // Only scroll to top when actually navigating to a different step
    if (prevStep !== currentStep) {
      window.scrollTo({ top: 0, behavior: "smooth" });
    }

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

    // If entering Step 8 (Cast & Characters), load all story characters
    if (currentStep === 8) {
      loadV2Cast();
    }

    // If entering Step 10 (Character Turnarounds), load all book characters' 3-view sheets
    if (currentStep === 10) {
      loadV2Turnarounds();
    }

    // If entering Step 11 (Locations & Sets), load all story locations/sets
    if (currentStep === 11) {
      loadV2Locations();
    }

    // If entering Step 12 (Shot List & Cinematography), load live shot list
    if (currentStep === 12) {
      loadV2ShotList();
    }

    // If entering Step 13 (Hardware) or Step 18 (Video), refresh Gemini & hardware status
    if (currentStep === 13 || currentStep === 18) {
      loadV2GeminiStatus();
    }

    // If entering Step 14 (Voice Casting & Dialects), load all story characters' voices
    if (currentStep === 14) {
      loadV2VoiceCast();
    }

    // If entering Step 15 (Spoken Dialogue Delivery), load all spoken lines from screenplay
    if (currentStep === 15) {
      loadV2Dialogue();
    }

    // If entering Step 16 (Score & Foley Sound Design), load saved prompts & rendered tracks
    if (currentStep === 16) {
      loadV2SoundDesign();
    }

    // If entering Step 17 (Storyboard Keyframes), load all scenes & shots filmstrip
    if (currentStep === 17) {
      loadV2Keyframes();
    }

    // If entering Steps 19-22 (Polish, Timeline, Mix, Premiere & Export), load dynamic post-production state
    if (currentStep >= 19 && currentStep <= 22) {
      loadV2PostProd();
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
  function collectV2VoiceCast() {
    const out = {};
    document.querySelectorAll(".v2-voice-select").forEach(sel => {
      if (sel.dataset.speaker && sel.value) out[sel.dataset.speaker] = sel.value;
    });
    return out;
  }

  async function triggerAudioRedo(mode, dialect, narratorVoice, cast, rows) {
    const selProj = $("proj");
    const slug = (selProj && selProj.value) || activeProject || "";
    const statusEl = $("v2VoiceStatus");
    if (!slug) {
      alert("Please select a story project first.");
      return;
    }

    const activeCast = cast || collectV2VoiceCast();
    if (statusEl) {
      statusEl.style.color = "#94a3b8";
      statusEl.textContent = `Updating voices (${dialect || "custom"})…`;
    }

    try {
      const res = await callApi("/api/redo_audio", {
        project: slug,
        mode: mode || "dialogue",
        dialect: dialect || null,
        narrator_voice: narratorVoice || null,
        cast: Object.keys(activeCast).length ? activeCast : null,
        rows: rows || null,
      });
      const r = res.result || {};
      if (statusEl) {
        statusEl.style.color = "#34d399";
        statusEl.textContent = `✓ Saved (${r.dialect || dialect || "custom"} · ${r.mode || "dialogue"} mode)${r.note ? " — " + r.note : ""}`;
      }
      if (currentStep === 14) await loadV2VoiceCast();
    } catch (err) {
      if (statusEl) {
        statusEl.style.color = "#f87171";
        statusEl.textContent = "Error updating audio: " + err.message;
      } else {
        alert("Error updating audio: " + err.message);
      }
    }
  }

  // ===== AUTOPILOT MODEL RECOMMENDATION =====
  async function loadStepAutopilot() {
    const stepMeta = V2_STEPS.find(s => s.num === currentStep);
    if (!stepMeta) return;

    const lookOpts = document.querySelector('input[name="look"]:checked');
    const look = (typeof v2SelectedLook === "string" && v2SelectedLook) || (lookOpts ? lookOpts.value : "live_action");
    const hw = (typeof v2SelectedHardware === "string" && v2SelectedHardware) ? v2SelectedHardware : "auto";

    try {
      const rec = await callApi(`/api/autopilot_recommend?look=${encodeURIComponent(look)}&step=${encodeURIComponent(stepMeta.id)}&hardware=${encodeURIComponent(hw)}`);
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

    // 0. Load continuity book & approval gate
    const cbStatusEl = $("v2ContBookStatus");
    const cbViewEl = $("v2ContBookView");
    const btnApproveCb = $("bV2ContApprove");
    try {
      const cb = await callApi(`/api/continuity_book?project=${encodeURIComponent(slug)}`);
      const book = cb && cb.book ? cb.book : null;
      const gate = (cb && cb.gate) || {};
      if (btnApproveCb) btnApproveCb.disabled = !book || Boolean(gate.approved);
      if (cbStatusEl) {
        if (!book) {
          cbStatusEl.textContent = `No continuity book written yet for "${slug}". Click ✨ Write Continuity Book to extract characters, locations, and props.`;
        } else {
          const nc = (book.characters || []).length, nl = (book.locations || []).length, np = (book.props || []).length;
          cbStatusEl.innerHTML = `<strong style="color:#f8fafc">${nc} characters, ${nl} locations, ${np} props</strong> · ` +
            (gate.approved ? `<span style="color:#34d399">✓ Approved ${gate.approved_at ? gate.approved_at.slice(0, 16).replace("T", " ") : ""}</span>` : `<span style="color:#fbbf24">Not approved yet — click ✓ Approve Continuity Book to unlock Shot List.</span>`);
        }
      }
      if (cbViewEl) {
        cbViewEl.textContent = "";
        if (book) {
          [["characters", "Characters"], ["locations", "Locations"], ["props", "Props"]].forEach(([kind, label]) => {
            const items = book[kind] || [];
            if (!items.length) return;
            const det = document.createElement("details");
            det.open = kind === "characters";
            det.style.cssText = "background:#0a0d14;border:1px solid #1e293b;border-radius:6px;padding:8px 10px;";
            const sum = document.createElement("summary");
            sum.style.cssText = "cursor:pointer;font-weight:700;color:#f59e0b;font-size:var(--text-xs);";
            sum.textContent = `${label} (${items.length})`;
            det.appendChild(sum);
            items.forEach(item => {
              const row = document.createElement("div");
              row.style.cssText = "display:flex;gap:8px;align-items:center;margin-top:6px;flex-wrap:wrap;";
              const nm = document.createElement("strong");
              nm.style.cssText = "min-width:110px;font-size:var(--text-xs);color:#f8fafc;";
              nm.textContent = item.name || "";
              const inp = document.createElement("input");
              inp.type = "text";
              inp.value = item.token || item.description || "";
              inp.style.cssText = "flex:1;min-width:180px;padding:4px 8px;background:#141b27;color:#e2e8f0;border:1px solid #334155;border-radius:4px;font-size:var(--text-xs);";
              const sv = document.createElement("button");
              sv.type = "button";
              sv.className = "btn btn--ghost";
              sv.style.cssText = "padding:3px 8px;font-size:var(--text-xs);";
              sv.textContent = "Save";
              sv.addEventListener("click", async () => {
                sv.disabled = true;
                try {
                  await callApi("/api/continuity_edit", { project: slug, kind, name: item.name, fields: { token: inp.value } });
                  sv.textContent = "✓";
                  setTimeout(() => { sv.textContent = "Save"; sv.disabled = false; }, 1000);
                  await loadV2Continuity();
                } catch (err) {
                  alert(err.message);
                  sv.disabled = false;
                }
              });
              row.appendChild(nm);
              row.appendChild(inp);
              row.appendChild(sv);
              det.appendChild(row);
            });
            cbViewEl.appendChild(det);
          });
        }
      }
    } catch (e) {
      if (cbStatusEl) cbStatusEl.textContent = "Could not load continuity book: " + e.message;
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

  let v2ContLogTimer = null;

  async function pollV2ContLog(sinceIdx) {
    const logEl = $("v2ContLog");
    const statusEl = $("v2ContBookStatus");
    clearTimeout(v2ContLogTimer);
    try {
      const r = await callApi(`/api/log?since=${sinceIdx || 0}`);
      if (logEl) {
        logEl.classList.remove("hidden");
        const lines = Array.isArray(r.lines) ? r.lines.join("\n") : (r.text || "");
        if (lines) {
          logEl.textContent = (sinceIdx ? logEl.textContent + "\n" : "") + lines;
          logEl.scrollTop = logEl.scrollHeight;
        }
      }
      if (r && r.running) {
        if (statusEl) statusEl.textContent = "⏳ Writing continuity book… (live log below)";
        v2ContLogTimer = setTimeout(() => pollV2ContLog(r.next || sinceIdx), 2000);
      } else {
        await loadV2Continuity();
      }
    } catch (e) {}
  }

  function initV2Continuity() {
    const btnReload = $("v2ContReload");
    const btnBootstrap = $("bV2ContBootstrap");
    const btnGenCb = $("bV2ContGenerate");
    const btnApproveCb = $("bV2ContApprove");
    const btnSaveRules = $("v2ContRulesSave");
    const btnSaveParams = $("v2ContParamsSave");
    const rulesEl = $("v2ContRules");
    const rulesMsg = $("v2ContRulesMsg");
    const posEl = $("v2ContPositives");
    const negEl = $("v2ContNegatives");
    const paramsMsg = $("v2ContParamsMsg");

    if (btnReload) btnReload.addEventListener("click", () => loadV2Continuity());

    if (btnBootstrap) {
      btnBootstrap.addEventListener("click", async () => {
        const selProj = $("proj");
        const slug = (selProj && selProj.value) || activeProject || "";
        if (!slug) { alert("Pick or save a book in Step 01 first."); return; }
        btnBootstrap.disabled = true;
        const statusEl = $("v2ContBookStatus");
        if (statusEl) statusEl.textContent = `Building continuity book instantly from "${slug}" script & coverage…`;
        try {
          await callApi("/api/continuity_bootstrap", { project: slug });
          await loadV2Continuity();
        } catch (err) {
          if (statusEl) statusEl.textContent = "Error: " + err.message;
        } finally {
          btnBootstrap.disabled = false;
        }
      });
    }

    if (btnGenCb) {
      btnGenCb.addEventListener("click", async () => {
        const selProj = $("proj");
        const slug = (selProj && selProj.value) || activeProject || "";
        if (!slug) { alert("Pick or save a book in Step 01 first."); return; }
        btnGenCb.disabled = true;
        const statusEl = $("v2ContBookStatus");
        const logEl = $("v2ContLog");
        if (statusEl) statusEl.textContent = `Starting continuity book generation for "${slug}"…`;
        if (logEl) { logEl.textContent = ""; logEl.classList.remove("hidden"); }
        try {
          const o = typeof window.options === "function" ? window.options() : {};
          await callApi("/api/continuity_book", {
            project: slug,
            engine: o.engine || "claude",
            claude_model: o.claude_model,
          });
          pollV2ContLog(0);
        } catch (err) {
          if (statusEl) statusEl.textContent = "Error: " + err.message;
        } finally {
          btnGenCb.disabled = false;
        }
      });
    }

    if (btnApproveCb) {
      btnApproveCb.addEventListener("click", async () => {
        const selProj = $("proj");
        const slug = (selProj && selProj.value) || activeProject || "";
        if (!slug) return;
        btnApproveCb.disabled = true;
        try {
          await callApi("/api/continuity_approve", { project: slug });
          await loadV2Continuity();
        } catch (err) {
          alert("Could not approve continuity book: " + err.message);
          btnApproveCb.disabled = false;
        }
      });
    }

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

  // ===== STEP 13 & STEP 18: HARDWARE SELECTION & GEMINI OMNI 1.2 FLASH =====
  const V2_HW_LABELS = {
    gemini: "Google Gemini API (Omni 1.2 Flash)",
    huggingface: "Hugging Face Spaces (ZeroGPU)",
    cloud_api: "Direct Cloud API (Fal / Replicate)",
    kaggle: "Kaggle Dual T4 / Colab",
    computer: "Local Computer GPU",
  };
  let v2SelectedHardware = "gemini";
  let v2OmniInteractions = {};

  function selectV2Hardware(hwKey) {
    const key = V2_HW_LABELS[hwKey] ? hwKey : "gemini";
    v2SelectedHardware = key;

    document.querySelectorAll(".v2-hw-card").forEach(card => {
      const active = card.dataset.hw === key;
      card.style.borderColor = active ? "#f59e0b" : "#232d3f";
      card.style.background = active ? "rgba(245, 158, 11, 0.10)" : "#141b27";
      card.style.boxShadow = active ? "0 0 14px rgba(245, 158, 11, 0.25)" : "none";
      const btn = card.querySelector(".v2-hw-select");
      if (btn) {
        btn.className = "btn v2-hw-select " + (active ? "btn--primary" : "btn--secondary");
        btn.textContent = active ? "✓ Selected" : `Use ${V2_HW_LABELS[card.dataset.hw].split(" (")[0]}`;
      }
      if (active && card.dataset.svc) {
        const svcRadio = document.querySelector(`input[name="svc"][value="${card.dataset.svc}"]`);
        if (svcRadio) {
          svcRadio.checked = true;
          svcRadio.dispatchEvent(new Event("change"));
        }
      }
    });

    const badge = $("v2HwBadge");
    if (badge) badge.textContent = `✓ Active: ${V2_HW_LABELS[key]}`;
    const status = $("v2HwStatus");
    if (status) {
      status.innerHTML = `<strong style="color:#f59e0b">Active Backend:</strong> ${V2_HW_LABELS[key]} &mdash; Autopilot and video/image runners will target this backend.`;
    }
    try { localStorage.setItem("studio_v2_hardware", key); } catch (e) {}
    loadStepAutopilot();
  }

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
          badge.textContent = "⬇ Key saved — Click to Install Gemini SDK";
          badge.className = "status-badge status-badge--drift";
          badge.style.cursor = "pointer";
          badge.onclick = async (e) => {
            e.stopPropagation();
            badge.textContent = "⏳ Installing google-genai…";
            try {
              const ok = await requestInstallWithApproval("gemini-sdk", "Google Gemini SDK", "google-genai");
              if (ok) {
                await loadV2GeminiStatus();
              } else {
                badge.textContent = "⬇ Key saved — Click to Install Gemini SDK";
              }
            } catch (err) {
              badge.textContent = "Install failed: " + (err.message || err);
            }
          };
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
    // Bind all 5 hardware backend cards and their Select buttons in Step 13
    document.querySelectorAll(".v2-hw-card").forEach(card => {
      card.addEventListener("click", (e) => {
        if (e.target && (e.target.tagName === "INPUT" || e.target.id === "bSaveGeminiKey")) return;
        selectV2Hardware(card.dataset.hw);
      });
    });
    document.querySelectorAll(".v2-hw-select").forEach(btn => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        selectV2Hardware(btn.dataset.hw);
      });
    });
    let savedHw = "gemini";
    try { savedHw = localStorage.getItem("studio_v2_hardware") || "gemini"; } catch (e) {}
    selectV2Hardware(savedHw);

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

  // ===== STEP 08: CAST & CHARACTERS =====
  async function loadV2Cast() {
    const selProj = $("proj");
    const slug = (selProj && selProj.value) || activeProject || "";
    const grid = $("v2CastGrid");
    const summaryEl = $("v2CastSummary");
    const badgeEl = $("v2CastBadge");

    if (!grid) return;

    if (!slug) {
      grid.textContent = "";
      if (summaryEl) summaryEl.textContent = "Pick or save a book in Step 01 first.";
      if (badgeEl) {
        badgeEl.textContent = "No Book Selected";
        badgeEl.className = "status-badge status-badge--drift";
      }
      return;
    }

    if (summaryEl) summaryEl.textContent = `Loading all characters for "${slug}"…`;
    if (badgeEl) {
      badgeEl.textContent = "Loading…";
      badgeEl.className = "status-badge status-badge--working";
    }

    // Gather characters from ALL sources for this book so none are ever missed:
    // 1. Saved character dossiers (/api/characters?action=list&series=<slug>)
    // 2. Story analyst coverage (/api/readin -> coverage.characters)
    // 3. Per-scene cast lock (/api/cast_lock -> scenes[].characters)
    // 4. Screenplay speaking characters (/api/screenplay -> scenes[].screenplay.elements)
    const merged = new Map(); // lowerName -> { name, role, description, visual_token, saved, rawChar, sources: Set }

    const upsert = (name, info, sourceLabel) => {
      const clean = String(name || "").trim();
      if (!clean) return;
      const key = clean.toLowerCase();
      const existing = merged.get(key) || {
        name: clean,
        role: "",
        description: "",
        visual_token: "",
        saved: false,
        rawChar: null,
        sources: new Set(),
      };
      existing.sources.add(sourceLabel);
      if (info.saved) {
        existing.saved = true;
        existing.name = clean;
      }
      if (info.role && !existing.role) existing.role = info.role;
      if (info.description && (!existing.description || info.saved)) existing.description = info.description;
      if (info.visual_token && (!existing.visual_token || info.saved)) existing.visual_token = info.visual_token;
      if (info.rawChar) existing.rawChar = info.rawChar;
      merged.set(key, existing);
    };

    // 1. Saved character dossiers
    try {
      const chList = await callApi(`/api/characters?action=list&series=${encodeURIComponent(slug)}`);
      const names = (chList && Array.isArray(chList.characters)) ? chList.characters : [];
      await Promise.all(names.map(async entry => {
        const name = typeof entry === "string" ? entry : (entry && entry.name);
        if (!name) return;
        let full = null;
        try {
          const got = await callApi(`/api/characters?action=get&series=${encodeURIComponent(slug)}&name=${encodeURIComponent(name)}`);
          full = got && got.character ? got.character : null;
        } catch (e) {}
        upsert(name, {
          saved: true,
          role: (full && (full.role || full.archetype)) || "",
          description: (full && (full.description || full.appearance || full.notes)) || "",
          visual_token: (full && (full.visual_token || full.token)) || "",
          rawChar: full,
        }, "Dossier");
      }));
    } catch (e) {}

    // 2. Coverage characters (from Read It In)
    try {
      const rd = await callApi(`/api/readin?project=${encodeURIComponent(slug)}`);
      const covChars = (rd && rd.coverage && Array.isArray(rd.coverage.characters)) ? rd.coverage.characters : [];
      covChars.forEach(c => {
        if (!c) return;
        upsert(c.name || c, {
          role: c.role || "",
          description: c.description || "",
        }, "Coverage");
      });
    } catch (e) {}

    // 3. Per-scene cast lock characters
    try {
      const lk = await callApi(`/api/cast_lock?project=${encodeURIComponent(slug)}`);
      const scenes = (lk && Array.isArray(lk.scenes)) ? lk.scenes : [];
      scenes.forEach(s => {
        (s.characters || []).forEach(c => {
          upsert(c.name, {
            visual_token: (c.locked && c.locked.token) || "",
          }, "Scenes");
        });
      });
    } catch (e) {}

    // 4. Screenplay speaking characters
    try {
      const sp = await callApi(`/api/screenplay?project=${encodeURIComponent(slug)}`);
      const scenes = (sp && Array.isArray(sp.scenes)) ? sp.scenes : [];
      scenes.forEach(s => {
        const els = (s.screenplay && Array.isArray(s.screenplay.elements)) ? s.screenplay.elements : [];
        els.forEach(el => {
          if (el && el.type === "dialogue" && el.character) {
            upsert(el.character, {}, "Screenplay");
          }
        });
      });
    } catch (e) {}

    // 5. Load per-character scene/location wardrobe states
    let wardrobeStatesMap = {};
    try {
      const ws = await callApi(`/api/v2_wardrobe_states?project=${encodeURIComponent(slug)}`);
      wardrobeStatesMap = (ws && ws.states) || {};
    } catch (e) {}

    const allChars = [...merged.values()].sort((a, b) =>
      String(a.name || "").localeCompare(String(b.name || ""), undefined, { sensitivity: "base" })
    );
    if (summaryEl) {
      summaryEl.innerHTML = `<strong style="color:#f59e0b">${allChars.length} character(s)</strong> found for <strong>${slug}</strong>` +
        (allChars.length ? " — edit any dossier inline, save, delete, or add missing characters." : " — click <strong>➕ Add Character</strong> or <strong>🔄 Sync from Book</strong> to populate your cast.");
    }
    if (badgeEl) {
      badgeEl.textContent = allChars.length ? `✓ ${allChars.length} Characters` : "No Characters Yet";
      badgeEl.className = "status-badge " + (allChars.length ? "status-badge--synced" : "status-badge--drift");
    }

    const castScrollY = window.scrollY || 0;
    const castPrevH = grid.offsetHeight;
    if (castPrevH > 0) grid.style.minHeight = castPrevH + "px";
    grid.textContent = "";
    requestAnimationFrame(() => {
      window.scrollTo({ top: castScrollY, behavior: "instant" });
      grid.style.minHeight = "";
    });

    if (!allChars.length) {
      const empty = document.createElement("div");
      empty.className = "direct-story-card";
      empty.style.cssText = "grid-column:1/-1;color:#94a3b8;font-size:var(--text-sm);";
      empty.textContent = "No characters extracted yet for this book. Click '🔄 Sync from Book' if you have a continuity book, or click '➕ Add Character' to add your cast manually.";
      grid.appendChild(empty);
      return;
    }

    allChars.forEach(c => {
      const card = document.createElement("div");
      card.className = "direct-story-card";

      const head = document.createElement("div");
      head.style.cssText = "display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap;";
      const title = document.createElement("strong");
      title.style.cssText = "font-size:var(--text-base);color:#f8fafc;";
      title.textContent = c.name + (c.role ? ` (${c.role})` : "");
      const srcBadge = document.createElement("span");
      srcBadge.className = "status-badge " + (c.saved ? "status-badge--synced" : "status-badge--working");
      srcBadge.style.fontSize = "0.7rem";
      srcBadge.textContent = c.saved ? "✓ Saved Dossier" : `From ${[...c.sources].join(" / ")}`;
      head.appendChild(title);
      head.appendChild(srcBadge);
      card.appendChild(head);

      const tokLabel = document.createElement("label");
      tokLabel.className = "f";
      tokLabel.textContent = "Visual Consistency Token";
      const tokInput = document.createElement("input");
      tokInput.type = "text";
      tokInput.value = c.visual_token || c.name.toLowerCase().replace(/[^a-z0-9]+/g, "_");
      tokInput.style.cssText = "width:100%;padding:6px 8px;background:#0a0d14;color:#f59e0b;border:1px solid #334155;border-radius:6px;font-family:var(--font-mono);font-size:var(--text-xs);";
      card.appendChild(tokLabel);
      card.appendChild(tokInput);

      const descLabel = document.createElement("label");
      descLabel.className = "f";
      descLabel.textContent = "Appearance, Wardrobe & Role";
      const descTa = document.createElement("textarea");
      descTa.rows = 3;
      descTa.value = c.description || "";
      descTa.placeholder = "Describe age, face, hair, clothing, and key visual traits…";
      descTa.style.cssText = "width:100%;padding:8px;background:#0a0d14;color:#f8fafc;border:1px solid #334155;border-radius:6px;font:inherit;font-size:var(--text-xs);";
      card.appendChild(descLabel);
      card.appendChild(descTa);

      // Scene / Location Wardrobe States (separate descriptions when character changes clothes or location)
      const wsKey = Object.keys(wardrobeStatesMap).find(k => k.toLowerCase() === c.name.toLowerCase());
      const charStates = Array.isArray(wsKey ? wardrobeStatesMap[wsKey] : null) ? wardrobeStatesMap[wsKey] : [];

      const combinedDesc = ((c.visual_token || "") + " " + (c.description || "")).trim();
      const hasSpecificState = charStates.some(st => st && String(st.wardrobe || "").trim().length >= 12);
      if (!hasSpecificState && (!combinedDesc || combinedDesc.length < 25 || /\bstriped\b/i.test(combinedDesc))) {
        const why = !combinedDesc || combinedDesc.length < 25
          ? "Add a specific visual & singular wardrobe description (exact solid colors for top, bottoms, shoes)"
          : "Vague pattern ('striped') may drift between shots — specify exact solid wardrobe colors or add a Scene Wardrobe State below";
        flagNeedsAttention(card, why);
      }

      const wsBox = document.createElement("div");
      wsBox.style.cssText = "margin-top:8px;padding:8px;background:#0a0d14;border:1px solid #232d3f;border-radius:6px;";
      const wsHdr = document.createElement("div");
      wsHdr.style.cssText = "display:flex;justify-content:space-between;align-items:center;gap:6px;margin-bottom:6px;flex-wrap:wrap;";
      const wsLbl = document.createElement("span");
      wsLbl.style.cssText = "font-size:11px;font-weight:700;color:#fde68a;";
      wsLbl.textContent = "👗 Wardrobe & Location Changes (by Scene)";
      const btnAddState = document.createElement("button");
      btnAddState.type = "button";
      btnAddState.className = "btn btn--ghost";
      btnAddState.style.cssText = "padding:2px 8px;font-size:11px;";
      btnAddState.textContent = "+ Add Outfit / Location";
      wsHdr.appendChild(wsLbl);
      wsHdr.appendChild(btnAddState);
      wsBox.appendChild(wsHdr);

      const wsRows = document.createElement("div");
      wsRows.style.cssText = "display:flex;flex-direction:column;gap:8px;";
      const appendStateRow = (st = { scenes: "", location: "", wardrobe: "" }) => {
        const r = document.createElement("div");
        r.className = "v2-ws-row";
        r.style.cssText = "display:flex;flex-direction:column;gap:5px;padding:6px;background:#0f172a;border:1px solid #1e293b;border-radius:6px;box-sizing:border-box;width:100%;min-width:0;";

        const topLine = document.createElement("div");
        topLine.style.cssText = "display:flex;gap:5px;align-items:center;width:100%;min-width:0;";
        const inSc = document.createElement("input");
        inSc.type = "text"; inSc.className = "v2-ws-scenes"; inSc.placeholder = "S001-S003"; inSc.value = st.scenes || "";
        inSc.style.cssText = "width:96px;min-width:0;padding:5px 6px;background:#0a0d14;color:#f59e0b;border:1px solid #334155;border-radius:4px;font-size:11px;box-sizing:border-box;";
        const inLoc = document.createElement("input");
        inLoc.type = "text"; inLoc.className = "v2-ws-loc"; inLoc.placeholder = "Location (e.g. Living Room)"; inLoc.value = st.location || "";
        inLoc.style.cssText = "flex:1;min-width:0;padding:5px 6px;background:#0a0d14;color:#cbd5e1;border:1px solid #334155;border-radius:4px;font-size:11px;box-sizing:border-box;";
        const bRm = document.createElement("button");
        bRm.type = "button"; bRm.className = "btn btn--ghost"; bRm.style.cssText = "padding:3px 7px;font-size:11px;color:#f87171;flex-shrink:0;"; bRm.textContent = "✕";
        bRm.title = "Remove this outfit state";
        bRm.addEventListener("click", () => r.remove());
        topLine.appendChild(inSc); topLine.appendChild(inLoc); topLine.appendChild(bRm);

        const inW = document.createElement("input");
        inW.type = "text"; inW.className = "v2-ws-wardrobe"; inW.placeholder = "Exact outfit (e.g. solid brown t-shirt, blue jeans, white socks)"; inW.value = st.wardrobe || "";
        inW.style.cssText = "width:100%;min-width:0;padding:6px 8px;background:#0a0d14;color:#f8fafc;border:1px solid #334155;border-radius:4px;font-size:12px;box-sizing:border-box;";

        r.appendChild(topLine);
        r.appendChild(inW);
        wsRows.appendChild(r);
      };
      charStates.forEach(st => appendStateRow(st));
      btnAddState.addEventListener("click", () => appendStateRow({ scenes: "S001-S003", location: "", wardrobe: "" }));
      wsBox.appendChild(wsRows);

      const wsFoot = document.createElement("div");
      wsFoot.style.cssText = "display:flex;justify-content:flex-end;margin-top:6px;";
      const btnSaveWs = document.createElement("button");
      btnSaveWs.type = "button";
      btnSaveWs.className = "btn btn--secondary";
      btnSaveWs.style.cssText = "padding:3px 10px;font-size:11px;";
      btnSaveWs.textContent = "💾 Save Wardrobe States";
      btnSaveWs.addEventListener("click", async () => {
        const states = [];
        wsRows.querySelectorAll(".v2-ws-row").forEach(r => {
          const scenes = (r.querySelector(".v2-ws-scenes")?.value || "").trim();
          const location = (r.querySelector(".v2-ws-loc")?.value || "").trim();
          const wardrobe = (r.querySelector(".v2-ws-wardrobe")?.value || "").trim();
          if (scenes || location || wardrobe) states.push({ scenes, location, wardrobe });
        });
        msg.textContent = "Saving wardrobe states…";
        try {
          await callApi("/api/v2_wardrobe_states_save", { project: slug, character: c.name, states });
          if (states.some(s => s.wardrobe.length >= 12)) clearNeedsAttention(card);
          msg.textContent = `✓ Saved ${states.length} wardrobe state(s)`;
          if (states.length && states[0].wardrobe) {
            proposeUpstreamSync({
              project: slug,
              kind: "character_to_continuity",
              affectedStepNums: [7],
              title: `🔄 Sync ${c.name}'s Wardrobe Back to Step 07?`,
              message: `You updated ${c.name}'s wardrobe in Step 08 ("${states[0].wardrobe.slice(0, 80)}").\n\nWould you like to update Step 07 (Continuity Book) so earlier steps match?`,
              payload: { name: c.name, token: `${c.name}: ${(descTa.value || "").trim().slice(0, 90)} | ${states[0].wardrobe}`.trim() },
            });
          }
        } catch (err) {
          msg.textContent = "Error: " + (err.message || err);
        }
      });
      wsFoot.appendChild(btnSaveWs);
      wsBox.appendChild(wsFoot);
      card.appendChild(wsBox);

      const actions = document.createElement("div");
      actions.style.cssText = "display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap;margin-top:4px;";
      const leftBtns = document.createElement("div");
      leftBtns.style.cssText = "display:flex;gap:6px;align-items:center;";
      const msg = document.createElement("span");
      msg.style.cssText = "font-size:var(--text-xs);color:#94a3b8;";

      const btnSave = document.createElement("button");
      btnSave.type = "button";
      btnSave.className = "btn btn--primary";
      btnSave.style.cssText = "padding:5px 12px;font-size:var(--text-xs);";
      btnSave.textContent = c.saved ? "💾 Save Changes" : "💾 Save Dossier";
      btnSave.addEventListener("click", async () => {
        btnSave.disabled = true;
        msg.textContent = "Saving…";
        try {
          if (c.saved && c.rawChar) {
            const updated = {
              ...c.rawChar,
              series: c.rawChar.series || slug,
              name: c.name,
              description: descTa.value.trim(),
              visual_token: tokInput.value.trim(),
            };
            await callApi("/api/characters", { action: "save", character: updated });
          } else {
            await callApi("/api/characters", {
              action: "create",
              series: slug,
              name: c.name,
              description: descTa.value.trim(),
              visual_token: tokInput.value.trim(),
            });
          }
          msg.textContent = "✓ Saved";
          await loadV2Cast();
        } catch (err) {
          msg.textContent = "Error: " + err.message;
        } finally {
          btnSave.disabled = false;
        }
      });
      leftBtns.appendChild(btnSave);

      if (c.saved) {
        const btnDel = document.createElement("button");
        btnDel.type = "button";
        btnDel.className = "btn btn--ghost";
        btnDel.style.cssText = "padding:5px 10px;font-size:var(--text-xs);color:#f87171;";
        btnDel.textContent = "🗑️ Delete";
        btnDel.addEventListener("click", async () => {
          if (!confirm(`Delete character dossier "${c.name}" from ${slug}?`)) return;
          btnDel.disabled = true;
          try {
            await callApi("/api/characters", { action: "delete", series: slug, name: c.name });
            await loadV2Cast();
          } catch (err) {
            msg.textContent = "Error: " + err.message;
            btnDel.disabled = false;
          }
        });
        leftBtns.appendChild(btnDel);
      }

      actions.appendChild(leftBtns);
      actions.appendChild(msg);
      card.appendChild(actions);
      grid.appendChild(card);
    });
  }

  function initV2Cast() {
    const btnToggle = $("bV2CastAddToggle");
    const btnCancel = $("bV2CastAddCancel");
    const form = $("v2CastAddForm");
    const btnCreate = $("bV2CastCreate");
    const btnSync = $("bV2CastSync");
    const btnReload = $("bV2CastReload");

    if (btnToggle && form) {
      btnToggle.addEventListener("click", () => {
        const show = form.classList.contains("hidden");
        form.classList.toggle("hidden", !show);
        form.style.display = show ? "flex" : "none";
        if (show && $("v2CastNewName")) $("v2CastNewName").focus();
      });
    }
    if (btnCancel && form) {
      btnCancel.addEventListener("click", () => {
        form.classList.add("hidden");
        form.style.display = "none";
      });
    }
    if (btnReload) btnReload.addEventListener("click", () => loadV2Cast());

    if (btnCreate) {
      btnCreate.addEventListener("click", async () => {
        const selProj = $("proj");
        const slug = (selProj && selProj.value) || activeProject || "";
        const name = ($("v2CastNewName") || {}).value ? $("v2CastNewName").value.trim() : "";
        const token = ($("v2CastNewToken") || {}).value ? $("v2CastNewToken").value.trim() : "";
        const desc = ($("v2CastNewDesc") || {}).value ? $("v2CastNewDesc").value.trim() : "";
        const msg = $("v2CastAddMsg");
        if (!slug) { alert("Pick or save a book in Step 01 first."); return; }
        if (!name) { alert("Enter a character name first."); return; }

        btnCreate.disabled = true;
        if (msg) msg.textContent = "Creating character…";
        try {
          await callApi("/api/characters", {
            action: "create",
            series: slug,
            name,
            description: desc,
            visual_token: token,
          });
          if ($("v2CastNewName")) $("v2CastNewName").value = "";
          if ($("v2CastNewToken")) $("v2CastNewToken").value = "";
          if ($("v2CastNewDesc")) $("v2CastNewDesc").value = "";
          if (form) { form.classList.add("hidden"); form.style.display = "none"; }
          if (msg) msg.textContent = "";
          await loadV2Cast();
        } catch (err) {
          if (msg) msg.textContent = "Error: " + err.message;
        } finally {
          btnCreate.disabled = false;
        }
      });
    }

    if (btnSync) {
      btnSync.addEventListener("click", async () => {
        const selProj = $("proj");
        const slug = (selProj && selProj.value) || activeProject || "";
        if (!slug) { alert("Pick or save a book in Step 01 first."); return; }
        btnSync.disabled = true;
        const summaryEl = $("v2CastSummary");
        if (summaryEl) summaryEl.textContent = `Syncing characters from "${slug}" continuity book…`;
        try {
          const res = await callApi("/api/characters", { action: "sync", project: slug, series: slug });
          await loadV2Cast();
          if (summaryEl) summaryEl.innerHTML += ` <span style="color:#34d399">(Synced ${res.count || 0} character(s))</span>`;
        } catch (err) {
          alert(err.message);
          await loadV2Cast();
        } finally {
          btnSync.disabled = false;
        }
      });
    }

    const selProj = $("proj");
    if (selProj) {
      selProj.addEventListener("change", () => {
        if (currentStep === 8) loadV2Cast();
      });
    }
  }

  // ===== STEP 09: ART DIRECTION & STYLE RECIPE =====
  const V2_STYLE_RECIPES = {
    live_action: {
      label: "Realistic Live Action",
      positives: "cinematic live-action film still, shot on a cinema camera, 35mm anamorphic lens, natural film grain, realistic skin texture, practical lighting, shallow depth of field",
      negatives: "cartoon, animated, 3d render, cgi, claymation, plasticine, illustration, anime, painting, drawing, doll-like, plastic skin",
    },
    claymation: {
      label: "Claymation",
      positives: "claymation stop-motion film, handcrafted plasticine figures, visible fingerprints and tool marks in the clay, miniature handmade sets, soft studio lighting, tactile textures",
      negatives: "photorealistic, live action, photograph, real people, smooth cgi, anime, 2d drawing, glossy plastic",
    },
    pixar_3d: {
      label: "3D Pixar",
      positives: "3d animated feature film style, stylised characters with large expressive eyes, soft rounded shapes, subsurface scattering, warm global illumination, rich saturated colour",
      negatives: "photorealistic, live action, photograph, real people, claymation, anime, flat 2d drawing, uncanny realistic skin",
    },
    pixar_disney: {
      label: "Pixar-Disney Hybrid",
      positives: "3d animated feature with a classic hand-drawn fairy-tale feel, painterly textures, storybook lighting, expressive faces, graceful character animation, lush colour",
      negatives: "photorealistic, live action, photograph, real people, claymation, anime, gritty, uncanny realistic skin",
    },
    travel_poster: {
      label: "Vintage Travel Poster",
      positives: "vintage travel poster style, 1930s art deco lithograph, flat bold shapes, limited colour palette, screen-print grain, strong silhouettes, sweeping perspective, sunlit sky gradients",
      negatives: "photorealistic, photograph, live action, 3d render, cgi, glossy, anime, cluttered detail, garbled lettering, watermark",
    },
    cyberpunk_3d: {
      label: "Cyberpunk Neon 3D",
      positives: "cyberpunk neon 3d render, night city, glowing magenta and cyan neon signs, rain-slick reflective streets, volumetric fog, holographic displays, rim lighting, high contrast",
      negatives: "daylight, pastoral, vintage, flat 2d drawing, watercolor, claymation, washed-out colours, low contrast",
    },
  };

  let v2SelectedLook = "live_action";

  function selectV2Style(lookKey) {
    const key = V2_STYLE_RECIPES[lookKey] ? lookKey : "live_action";
    v2SelectedLook = key;
    const recipe = V2_STYLE_RECIPES[key];

    document.querySelectorAll(".v2-style-card").forEach(card => {
      const isSelected = card.dataset.look === key;
      card.setAttribute("aria-checked", String(isSelected));
      card.style.borderColor = isSelected ? "#f59e0b" : "#232d3f";
      card.style.background = isSelected ? "rgba(245, 158, 11, 0.12)" : "#141b27";
      card.style.boxShadow = isSelected ? "0 0 14px rgba(245, 158, 11, 0.25)" : "none";
    });

    const badge = $("v2StyleBadge");
    if (badge) badge.textContent = `✓ ${recipe.label}`;
    const pos = $("v2StylePos");
    const neg = $("v2StyleNeg");
    if (pos) pos.value = recipe.positives;
    if (neg) neg.value = recipe.negatives;
    const msg = $("v2StyleMsg");
    if (msg) msg.textContent = `Selected "${recipe.label}" — click 💾 Apply Style to Book to save to your project.`;

    // Sync with hidden legacy look radio if present and persist in localStorage
    const legacyRadio = document.querySelector(`input[name="look"][value="${key}"]`);
    if (legacyRadio) {
      legacyRadio.checked = true;
      legacyRadio.dispatchEvent(new Event("change"));
    }
    try { localStorage.setItem("studio_v2_look", key); } catch (e) {}
    loadStepAutopilot();
  }

  function initV2Styles() {
    document.querySelectorAll(".v2-style-card").forEach(card => {
      card.addEventListener("click", () => selectV2Style(card.dataset.look));
    });

    const btnApply = $("bV2StyleApply");
    if (btnApply) {
      btnApply.addEventListener("click", async () => {
        const selProj = $("proj");
        const slug = (selProj && selProj.value) || activeProject || "";
        const msg = $("v2StyleMsg");
        if (!slug) { alert("Pick or save a book in Step 01 first."); return; }
        btnApply.disabled = true;
        if (msg) msg.textContent = "Applying style to project…";
        try {
          await callApi("/api/global_params", {
            project: slug,
            positives: ($("v2StylePos") || {}).value || "",
            negatives: ($("v2StyleNeg") || {}).value || "",
          });
          if (msg) msg.textContent = `✓ Applied "${V2_STYLE_RECIPES[v2SelectedLook].label}" to "${slug}".`;
        } catch (err) {
          if (msg) msg.textContent = "Error: " + err.message;
        } finally {
          btnApply.disabled = false;
        }
      });
    }

    let savedLook = "live_action";
    try { savedLook = localStorage.getItem("studio_v2_look") || "live_action"; } catch (e) {}
    selectV2Style(savedLook);
  }

  // ===== STEP 11: LOCATIONS & SETS =====
  function getCustomSets(slug) {
    try {
      const raw = localStorage.getItem(`studio_v2_sets_${slug}`);
      return raw ? JSON.parse(raw) : [];
    } catch (e) { return []; }
  }

  function saveCustomSet(slug, setObj) {
    try {
      const list = getCustomSets(slug).filter(x => x.name.toLowerCase() !== setObj.name.toLowerCase());
      list.push(setObj);
      localStorage.setItem(`studio_v2_sets_${slug}`, JSON.stringify(list));
    } catch (e) {}
  }

  async function loadV2Locations() {
    const selProj = $("proj");
    const slug = (selProj && selProj.value) || activeProject || "";
    const grid = $("v2LocGrid");
    const summaryEl = $("v2LocSummary");
    const badgeEl = $("v2LocBadge");

    if (!grid) return;

    if (!slug) {
      grid.textContent = "";
      if (summaryEl) summaryEl.textContent = "Pick or save a book in Step 01 first.";
      if (badgeEl) {
        badgeEl.textContent = "No Book Selected";
        badgeEl.className = "status-badge status-badge--drift";
      }
      return;
    }

    if (summaryEl) summaryEl.textContent = `Loading all locations & sets for "${slug}"…`;
    if (badgeEl) {
      badgeEl.textContent = "Loading…";
      badgeEl.className = "status-badge status-badge--working";
    }

    // Merge locations from ALL sources so every set in the story appears:
    // 1. Continuity book (/api/continuity_book -> book.locations)
    // 2. Scene cast_lock (/api/cast_lock -> scenes[].place)
    // 3. Screenplay sluglines (/api/screenplay -> INT./EXT. LOCATION - TIME)
    // 4. Custom sets saved locally for this book
    const merged = new Map();
    let hasContinuityBook = false;

    const upsert = (name, info, sourceLabel) => {
      const clean = String(name || "").trim();
      if (!clean) return;
      const key = clean.toLowerCase();
      const existing = merged.get(key) || {
        name: clean,
        description: "",
        lighting: "",
        inContinuity: false,
        sources: new Set(),
      };
      existing.sources.add(sourceLabel);
      if (info.inContinuity) {
        existing.inContinuity = true;
        existing.name = clean;
      }
      if (info.description && (!existing.description || info.inContinuity)) existing.description = info.description;
      if (info.lighting && (!existing.lighting || info.inContinuity)) existing.lighting = info.lighting;
      merged.set(key, existing);
    };

    // 1. Continuity book locations
    try {
      const cb = await callApi(`/api/continuity_book?project=${encodeURIComponent(slug)}`);
      const locs = (cb && cb.book && Array.isArray(cb.book.locations)) ? cb.book.locations : [];
      if (cb && cb.book) hasContinuityBook = true;
      locs.forEach(loc => {
        if (!loc) return;
        const name = typeof loc === "string" ? loc : (loc.name || loc.location || "");
        const desc = typeof loc === "object" ? (loc.description || loc.details || loc.visual_description || "") : "";
        const light = typeof loc === "object" ? (loc.lighting || loc.atmosphere || loc.time_of_day || "") : "";
        upsert(name, { inContinuity: true, description: desc, lighting: light }, "Continuity Book");
      });
    } catch (e) {}

    // 2. Scene cast_lock places
    try {
      const lk = await callApi(`/api/cast_lock?project=${encodeURIComponent(slug)}`);
      const scenes = (lk && Array.isArray(lk.scenes)) ? lk.scenes : [];
      scenes.forEach(s => {
        if (s.place && s.place.name) {
          upsert(s.place.name, { description: s.summary || "" }, "Scenes");
        }
      });
    } catch (e) {}

    // 3. Screenplay sluglines (INT. / EXT. LOCATION - TIME)
    try {
      const sp = await callApi(`/api/screenplay?project=${encodeURIComponent(slug)}`);
      const scenes = (sp && Array.isArray(sp.scenes)) ? sp.scenes : [];
      scenes.forEach(s => {
        const heading = (s.screenplay && s.screenplay.heading) || "";
        if (!heading) return;
        const m = heading.match(/^(?:INT\.\/EXT\.|EXT\.\/INT\.|INT\.|EXT\.)\s*(.+?)(?:\s*-\s*(.+))?$/i);
        const locName = m ? m[1].trim() : heading.trim();
        const tod = m && m[2] ? m[2].trim() : "";
        upsert(locName, { lighting: tod, description: s.summary || "" }, "Screenplay");
      });
    } catch (e) {}

    // 4. Locally added custom sets
    getCustomSets(slug).forEach(cs => {
      upsert(cs.name, { description: cs.description || "", lighting: cs.lighting || "" }, "Custom");
    });

    const allLocs = [...merged.values()];
    if (summaryEl) {
      summaryEl.innerHTML = `<strong style="color:#f59e0b">${allLocs.length} location(s) / set(s)</strong> found for <strong>${slug}</strong>` +
        (allLocs.length ? " — edit any set's details or lighting below, or add new sets." : " — click <strong>➕ Add Set</strong> or <strong>✨ Extract Sets from Script</strong> to populate your locations.");
    }
    if (badgeEl) {
      badgeEl.textContent = allLocs.length ? `✓ ${allLocs.length} Sets` : "No Sets Yet";
      badgeEl.className = "status-badge " + (allLocs.length ? "status-badge--synced" : "status-badge--drift");
    }

    const locScrollY = window.scrollY || 0;
    const locPrevH = grid.offsetHeight;
    if (locPrevH > 0) grid.style.minHeight = locPrevH + "px";
    grid.textContent = "";
    requestAnimationFrame(() => {
      window.scrollTo({ top: locScrollY, behavior: "instant" });
      grid.style.minHeight = "";
    });

    if (!allLocs.length) {
      const empty = document.createElement("div");
      empty.className = "direct-story-card";
      empty.style.cssText = "grid-column:1/-1;color:#94a3b8;font-size:var(--text-sm);";
      empty.textContent = "No locations found yet for this book. Click '✨ Extract Sets from Script' to generate a continuity book, or click '➕ Add Set' to define sets manually.";
      grid.appendChild(empty);
      return;
    }

    allLocs.forEach((loc, idx) => {
      const card = document.createElement("div");
      card.className = "direct-story-card";
      if (!loc.description || loc.description.trim().length < 15) {
        flagNeedsAttention(card, "Add specific set details, colors & layout so shots stay consistent in this location");
      }

      const head = document.createElement("div");
      head.style.cssText = "display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap;";
      const title = document.createElement("strong");
      title.style.cssText = "font-size:var(--text-base);color:#f8fafc;";
      title.textContent = `Set ${idx + 1}: ${loc.name}`;
      const srcBadge = document.createElement("span");
      srcBadge.className = "status-badge " + (loc.inContinuity ? "status-badge--synced" : "status-badge--working");
      srcBadge.style.fontSize = "0.7rem";
      srcBadge.textContent = loc.inContinuity ? "✓ Continuity Book" : `From ${[...loc.sources].join(" / ")}`;
      head.appendChild(title);
      head.appendChild(srcBadge);
      card.appendChild(head);

      const lightLabel = document.createElement("label");
      lightLabel.className = "f";
      lightLabel.textContent = "Lighting / Time / Atmosphere";
      const lightInput = document.createElement("input");
      lightInput.type = "text";
      lightInput.value = loc.lighting || "";
      lightInput.placeholder = "e.g. Warm golden hour, foggy twilight, soft interior glow…";
      lightInput.style.cssText = "width:100%;padding:6px 8px;background:#0a0d14;color:#f59e0b;border:1px solid #334155;border-radius:6px;font-size:var(--text-xs);";
      card.appendChild(lightLabel);
      card.appendChild(lightInput);

      const descLabel = document.createElement("label");
      descLabel.className = "f";
      descLabel.textContent = "Set Architecture, Landmarks & Visual Details";
      const descTa = document.createElement("textarea");
      descTa.rows = 3;
      descTa.value = loc.description || "";
      descTa.placeholder = "Describe terrain, architecture, key props, and colors to keep consistent…";
      descTa.style.cssText = "width:100%;padding:8px;background:#0a0d14;color:#f8fafc;border:1px solid #334155;border-radius:6px;font:inherit;font-size:var(--text-xs);";
      card.appendChild(descLabel);
      card.appendChild(descTa);

      const foot = document.createElement("div");
      foot.style.cssText = "display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-top:4px;";
      const btnSave = document.createElement("button");
      btnSave.type = "button";
      btnSave.className = "btn btn--primary";
      btnSave.style.cssText = "padding:5px 12px;font-size:var(--text-xs);";
      btnSave.textContent = "💾 Save Set";
      const msg = document.createElement("span");
      msg.style.cssText = "font-size:var(--text-xs);color:#94a3b8;";

      btnSave.addEventListener("click", async () => {
        btnSave.disabled = true;
        msg.textContent = "Saving…";
        const fields = { description: descTa.value.trim(), lighting: lightInput.value.trim() };
        saveCustomSet(slug, { name: loc.name, ...fields });
        try {
          if (hasContinuityBook && loc.inContinuity) {
            await callApi("/api/continuity_edit", {
              project: slug,
              kind: "locations",
              name: loc.name,
              fields,
            });
            msg.textContent = "✓ Saved to continuity book";
          } else {
            msg.textContent = "✓ Saved to project sets";
          }
        } catch (err) {
          msg.textContent = "✓ Saved locally (" + err.message + ")";
        } finally {
          btnSave.disabled = false;
        }
      });

      foot.appendChild(btnSave);
      foot.appendChild(msg);
      card.appendChild(foot);
      grid.appendChild(card);
    });
  }

  function initV2Locations() {
    const btnToggle = $("bV2LocAddToggle");
    const btnCancel = $("bV2LocAddCancel");
    const form = $("v2LocAddForm");
    const btnCreate = $("bV2LocCreate");
    const btnBuild = $("bV2LocBuild");
    const btnReload = $("bV2LocReload");

    if (btnToggle && form) {
      btnToggle.addEventListener("click", () => {
        const show = form.classList.contains("hidden");
        form.classList.toggle("hidden", !show);
        form.style.display = show ? "flex" : "none";
        if (show && $("v2LocNewName")) $("v2LocNewName").focus();
      });
    }
    if (btnCancel && form) {
      btnCancel.addEventListener("click", () => {
        form.classList.add("hidden");
        form.style.display = "none";
      });
    }
    if (btnReload) btnReload.addEventListener("click", () => loadV2Locations());

    if (btnCreate) {
      btnCreate.addEventListener("click", async () => {
        const selProj = $("proj");
        const slug = (selProj && selProj.value) || activeProject || "";
        const name = ($("v2LocNewName") || {}).value ? $("v2LocNewName").value.trim() : "";
        const lighting = ($("v2LocNewLight") || {}).value ? $("v2LocNewLight").value.trim() : "";
        const description = ($("v2LocNewDesc") || {}).value ? $("v2LocNewDesc").value.trim() : "";
        if (!slug) { alert("Pick or save a book in Step 01 first."); return; }
        if (!name) { alert("Enter a location / set name first."); return; }
        saveCustomSet(slug, { name, lighting, description });
        if ($("v2LocNewName")) $("v2LocNewName").value = "";
        if ($("v2LocNewLight")) $("v2LocNewLight").value = "";
        if ($("v2LocNewDesc")) $("v2LocNewDesc").value = "";
        if (form) { form.classList.add("hidden"); form.style.display = "none"; }
        await loadV2Locations();
      });
    }

    if (btnBuild) {
      btnBuild.addEventListener("click", async () => {
        const selProj = $("proj");
        const slug = (selProj && selProj.value) || activeProject || "";
        if (!slug) { alert("Pick or save a book in Step 01 first."); return; }
        btnBuild.disabled = true;
        const summaryEl = $("v2LocSummary");
        if (summaryEl) summaryEl.textContent = `Starting continuity book & set extraction for "${slug}"…`;
        try {
          const o = typeof window.options === "function" ? window.options() : {};
          await callApi("/api/continuity_book", { project: slug, engine: o.engine || "claude", claude_model: o.claude_model });
          if (summaryEl) summaryEl.textContent = `✓ Set extraction job started for "${slug}". Click ↻ Reload in a moment to view all sets.`;
        } catch (err) {
          if (summaryEl) summaryEl.textContent = "Could not start extraction: " + err.message;
        } finally {
          btnBuild.disabled = false;
        }
      });
    }

    const selProj = $("proj");
    if (selProj) {
      selProj.addEventListener("change", () => {
        if (currentStep === 11) loadV2Locations();
      });
    }
  }

  // ===== STEP 12: SHOT LIST & CINEMATOGRAPHY =====
  let v2ShotScenes = [];
  let v2ShotActiveSceneIdx = 0;
  let v2ShotSourceKind = "shot_list"; // "shot_list" | "storyboard"

  async function v2ShotEdit(sceneId, n, body) {
    const selProj = $("proj");
    const slug = (selProj && selProj.value) || activeProject || "";
    if (!slug) return;
    try {
      await callApi("/api/shot_edit", { project: slug, scene: sceneId, n, ...body });
      await loadV2ShotList();
    } catch (err) {
      alert("Could not edit shot: " + err.message);
    }
  }

  function renderV2ShotList() {
    const pills = $("v2ShotsPills");
    const noteEl = $("v2ShotsSceneNote");
    const tbody = $("v2ShotsBody");
    if (!pills || !tbody) return;

    preserveScroll(tbody.parentElement, () => {
      pills.textContent = "";
      tbody.textContent = "";
    });

    if (!v2ShotScenes.length) {
      if (noteEl) noteEl.textContent = "No shots found yet. Click '✨ Generate Shot List' above (after approving continuity), or build shots from your screenplay.";
      return;
    }

    v2ShotActiveSceneIdx = Math.max(0, Math.min(v2ShotScenes.length - 1, v2ShotActiveSceneIdx));
    v2ShotScenes.forEach((sc, idx) => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "step-pill" + (idx === v2ShotActiveSceneIdx ? " active" : "");
      b.textContent = `${sc.id}: ${(sc.heading || sc.title || "").slice(0, 26)} (${(sc.shots || []).length})`;
      b.addEventListener("click", () => {
        v2ShotActiveSceneIdx = idx;
        renderV2ShotList();
      });
      pills.appendChild(b);
    });

    const sc = v2ShotScenes[v2ShotActiveSceneIdx];
    const shots = sc.shots || [];
    if (noteEl) {
      const bd = sc.breakdown || {};
      const bits = [];
      if (sc.heading) bits.push(`<strong style="color:#f59e0b">${sc.id}</strong> ${sc.heading}`);
      if (bd.intent) bits.push(`<strong>Intent:</strong> ${bd.intent}`);
      if (bd.emotional_beat) bits.push(`<strong>Beat:</strong> ${bd.emotional_beat}`);
      if (bd.blocking) bits.push(`<strong>Blocking:</strong> ${bd.blocking}`);
      noteEl.innerHTML = bits.join(" &middot; ") || `${sc.id} — ${shots.length} shot(s)`;
    }

    shots.forEach((s, idx) => {
      const tr = document.createElement("tr");
      tr.style.borderBottom = "1px solid #1e293b";

      const tdN = document.createElement("td");
      tdN.style.cssText = "padding:8px;font-weight:700;color:#f59e0b;white-space:nowrap;";
      tdN.textContent = `Shot ${s.n || idx + 1}`;

      const tdFrame = document.createElement("td");
      tdFrame.style.cssText = "padding:8px;white-space:nowrap;";
      tdFrame.textContent = [s.type || "Shot", s.lens_mm ? `${s.lens_mm}mm` : ""].filter(Boolean).join(" · ");

      const tdCam = document.createElement("td");
      tdCam.style.cssText = "padding:8px;font-size:var(--text-xs);color:#94a3b8;min-width:160px;";
      tdCam.textContent = [s.height, s.movement, s.lighting].filter(Boolean).join(", ") || "Standard";

      const tdAct = document.createElement("td");
      tdAct.style.cssText = "padding:8px;min-width:240px;";
      if (v2ShotSourceKind === "shot_list") {
        const inp = document.createElement("input");
        inp.type = "text";
        inp.value = s.action || "";
        inp.style.cssText = "width:100%;padding:5px 8px;background:#0a0d14;color:#f8fafc;border:1px solid #334155;border-radius:4px;font-size:var(--text-xs);";
        inp.addEventListener("change", () => v2ShotEdit(sc.id, s.n, { action: "edit", fields: { action: inp.value } }));
        tdAct.appendChild(inp);
      } else {
        tdAct.textContent = s.action || s.prompt || "";
      }

      const tdSec = document.createElement("td");
      tdSec.style.padding = "8px";
      if (v2ShotSourceKind === "shot_list") {
        const secInp = document.createElement("input");
        secInp.type = "number";
        secInp.min = 1.5;
        secInp.max = 60;
        secInp.step = 0.5;
        secInp.value = s.seconds || 5;
        secInp.style.cssText = "width:60px;padding:4px;background:#0a0d14;color:#f8fafc;border:1px solid #334155;border-radius:4px;";
        secInp.addEventListener("change", () => v2ShotEdit(sc.id, s.n, { action: "edit", fields: { seconds: Number(secInp.value) } }));
        tdSec.appendChild(secInp);
      } else {
        tdSec.textContent = `${s.seconds || 5}s`;
      }

      const tdBtns = document.createElement("td");
      tdBtns.style.cssText = "padding:8px;white-space:nowrap;display:flex;gap:4px;";
      if (v2ShotSourceKind === "shot_list") {
        const mk = (lbl, fn, disabled = false) => {
          const b = document.createElement("button");
          b.type = "button";
          b.className = "btn btn--ghost";
          b.style.cssText = "padding:2px 7px;font-size:var(--text-xs);";
          b.textContent = lbl;
          b.disabled = disabled;
          b.addEventListener("click", fn);
          return b;
        };
        tdBtns.appendChild(mk("↑", () => v2ShotEdit(sc.id, s.n, { action: "move", to: s.n - 1 }), s.n <= 1));
        tdBtns.appendChild(mk("↓", () => v2ShotEdit(sc.id, s.n, { action: "move", to: s.n + 1 }), s.n >= shots.length));
        tdBtns.appendChild(mk("+", () => v2ShotEdit(sc.id, s.n, { action: "add" })));
        tdBtns.appendChild(mk("×", () => { if (confirm(`Delete shot ${s.n}?`)) v2ShotEdit(sc.id, s.n, { action: "delete" }); }, shots.length <= 1));
      } else {
        tdBtns.innerHTML = `<span style="font-size:var(--text-xs);color:#64748b">CSV shot</span>`;
      }

      [tdN, tdFrame, tdCam, tdAct, tdSec, tdBtns].forEach(td => tr.appendChild(td));
      tbody.appendChild(tr);
    });
  }

  async function loadV2ShotList() {
    const selProj = $("proj");
    const slug = (selProj && selProj.value) || activeProject || "";
    const summaryEl = $("v2ShotsSummary");
    const badgeEl = $("v2ShotsBadge");
    const btnApprove = $("bV2ShotsApprove");

    if (!summaryEl) return;
    v2ShotScenes = [];

    if (!slug) {
      summaryEl.textContent = "Pick or save a book in Step 01 first.";
      if (badgeEl) { badgeEl.textContent = "No Book Selected"; badgeEl.className = "status-badge status-badge--drift"; }
      renderV2ShotList();
      return;
    }

    summaryEl.textContent = `Loading shot list for "${slug}"…`;
    if (badgeEl) { badgeEl.textContent = "Loading…"; badgeEl.className = "status-badge status-badge--working"; }

    // 1. Primary: /api/shot_list
    try {
      const r = await callApi(`/api/shot_list?project=${encodeURIComponent(slug)}`);
      const L = r && r.list ? r.list : null;
      if (L && Array.isArray(L.scenes) && L.scenes.length > 0) {
        v2ShotScenes = L.scenes;
        v2ShotSourceKind = "shot_list";
        const totalShots = L.scenes.reduce((a, sc) => a + (sc.shots ? sc.shots.length : 0), 0);
        const mins = s => `${Math.floor((s || 0) / 60)}:${String(Math.round((s || 0) % 60)).padStart(2, "0")}`;
        summaryEl.innerHTML = `<strong style="color:#f59e0b">${totalShots} shot(s)</strong> across <strong>${L.scenes.length} scene(s)</strong> · Runtime ${mins(L.runtime_seconds)} / ${mins(L.target_seconds)}`;
        if (badgeEl) {
          const ok = r.gate && r.gate.approved;
          badgeEl.textContent = ok ? `✓ ${totalShots} Shots Approved` : `${totalShots} Shots (Review)`;
          badgeEl.className = "status-badge " + (ok ? "status-badge--synced" : "status-badge--working");
        }
        if (btnApprove) btnApprove.disabled = Boolean(r.gate && r.gate.approved);
        renderV2ShotList();
        return;
      }
    } catch (e) {}

    // 2. Fallback: /api/storyboard (shots built in all_shots.csv)
    try {
      const sb = await callApi(`/api/storyboard?project=${encodeURIComponent(slug)}`);
      const shots = (sb && Array.isArray(sb.shots)) ? sb.shots : [];
      if (shots.length > 0) {
        const byCh = new Map();
        shots.forEach((s, i) => {
          const key = s.chapter ? `Ch ${s.chapter}` : "All Shots";
          if (!byCh.has(key)) byCh.set(key, []);
          byCh.get(key).push({
            n: s.n || i + 1,
            type: s.shot_type || "Shot",
            movement: s.camera || "",
            action: s.prompt || s.action || s.narration || "",
            seconds: s.seconds || 5,
          });
        });
        v2ShotScenes = [...byCh.entries()].map(([id, list]) => ({ id, heading: id, shots: list }));
        v2ShotSourceKind = "storyboard";
        summaryEl.innerHTML = `<strong style="color:#f59e0b">${shots.length} shot(s)</strong> loaded from project storyboard for <strong>${slug}</strong>.`;
        if (badgeEl) { badgeEl.textContent = `✓ ${shots.length} Shots`; badgeEl.className = "status-badge status-badge--synced"; }
        if (btnApprove) btnApprove.disabled = true;
        renderV2ShotList();
        return;
      }
    } catch (e) {}

    summaryEl.textContent = `No shot list generated yet for "${slug}". Click ✨ Generate Shot List to break scenes into camera shots.`;
    if (badgeEl) { badgeEl.textContent = "Not Generated Yet"; badgeEl.className = "status-badge status-badge--drift"; }
    if (btnApprove) btnApprove.disabled = true;
    renderV2ShotList();
  }

  function initV2ShotList() {
    const btnReload = $("bV2ShotsReload");
    const btnBuild = $("bV2ShotsBuild");
    const btnApprove = $("bV2ShotsApprove");
    if (btnReload) btnReload.addEventListener("click", () => loadV2ShotList());

    if (btnBuild) {
      btnBuild.addEventListener("click", async () => {
        const selProj = $("proj");
        const slug = (selProj && selProj.value) || activeProject || "";
        if (!slug) { alert("Pick or save a book in Step 01 first."); return; }
        btnBuild.disabled = true;
        const summaryEl = $("v2ShotsSummary");
        if (summaryEl) summaryEl.textContent = `Starting director's shot list generation for "${slug}"…`;
        try {
          const o = typeof window.options === "function" ? window.options() : {};
          await callApi("/api/shot_list", { project: slug, engine: o.engine || "claude", claude_model: o.claude_model });
          if (summaryEl) summaryEl.textContent = `✓ Shot list generation started for "${slug}". Click ↻ Reload in a moment.`;
        } catch (err) {
          if (summaryEl) summaryEl.textContent = "Could not start shot list: " + err.message;
        } finally {
          btnBuild.disabled = false;
        }
      });
    }

    if (btnApprove) {
      btnApprove.addEventListener("click", async () => {
        const selProj = $("proj");
        const slug = (selProj && selProj.value) || activeProject || "";
        if (!slug) return;
        try {
          await callApi("/api/shot_list_approve", { project: slug });
          await loadV2ShotList();
        } catch (err) {
          alert(err.message);
        }
      });
    }

    const selProj = $("proj");
    if (selProj) {
      selProj.addEventListener("change", () => {
        v2ShotActiveSceneIdx = 0;
        if (currentStep === 12) loadV2ShotList();
      });
    }
  }

  // ===== STEP 14: VOICE CASTING & DIALECTS =====
  const KOKORO_VOICES = [
    ["am_puck", "am_puck (US Male · Youthful / Energetic)"],
    ["am_michael", "am_michael (US Male · Calm)"],
    ["am_adam", "am_adam (US Male · Warm)"],
    ["am_echo", "am_echo (US Male · Clear)"],
    ["am_eric", "am_eric (US Male · Resonant)"],
    ["am_fenrir", "am_fenrir (US Male · Bold)"],
    ["am_liam", "am_liam (US Male · Natural)"],
    ["am_onyx", "am_onyx (US Male · Deep)"],
    ["am_santa", "am_santa (US Male · Storytelling / Jolly)"],
    ["af_heart", "af_heart (US Female · Expressive)"],
    ["af_bella", "af_bella (US Female · Warm)"],
    ["af_alloy", "af_alloy (US Female · Crisp)"],
    ["af_aoede", "af_aoede (US Female · Melodic)"],
    ["af_jessica", "af_jessica (US Female · Friendly)"],
    ["af_kore", "af_kore (US Female · Firm)"],
    ["af_nicole", "af_nicole (US Female · Gentle / Soft)"],
    ["af_nova", "af_nova (US Female · Bright)"],
    ["af_river", "af_river (US Female · Calm)"],
    ["af_sarah", "af_sarah (US Female · Clear)"],
    ["af_sky", "af_sky (US Female · Light / Young)"],
    ["bm_fable", "bm_fable (UK Male · Expressive / Storytelling)"],
    ["bm_george", "bm_george (UK Male · Classic RP)"],
    ["bm_lewis", "bm_lewis (UK Male · Warm)"],
    ["bm_daniel", "bm_daniel (UK Male · Soft)"],
    ["bf_emma", "bf_emma (UK Female · Warm RP)"],
    ["bf_alice", "bf_alice (UK Female · Clear)"],
    ["bf_isabella", "bf_isabella (UK Female · Gentle)"],
    ["bf_lily", "bf_lily (UK Female · Bright)"],
  ];

  const GEMINI_VOICES = [
    ["Puck", "Puck — Upbeat, youthful & lively"],
    ["Zephyr", "Zephyr — Bright, airy & friendly"],
    ["Leda", "Leda — Youthful, light & clear"],
    ["Fenrir", "Fenrir — Excitable & energetic"],
    ["Aoede", "Aoede — Breezy & expressive"],
    ["Kore", "Kore — Firm, warm & steady"],
    ["Charon", "Charon — Deep & informative"],
    ["Orus", "Orus — Firm & grounded"],
    ["Callirrhoe", "Callirrhoe — Easy-going & relaxed"],
    ["Autonoe", "Autonoe — Bright & optimistic"],
    ["Enceladus", "Enceladus — Breathy & gentle"],
    ["Iapetus", "Iapetus — Clear & articulate"],
    ["Umbriel", "Umbriel — Easy-going & smooth"],
    ["Algieba", "Algieba — Smooth & warm"],
    ["Despina", "Despina — Smooth & poised"],
    ["Erinome", "Erinome — Clear & expressive"],
    ["Algenib", "Algenib — Gravelly & characterful"],
    ["Rasalgethi", "Rasalgethi — Informative & calm"],
    ["Laomedeia", "Laomedeia — Upbeat & cheerful"],
    ["Achernar", "Achernar — Soft & gentle"],
    ["Alnilam", "Alnilam — Firm & resonant"],
    ["Schedar", "Schedar — Even & steady"],
    ["Gacrux", "Gacrux — Mature & seasoned"],
    ["Pulcherrima", "Pulcherrima — Forward & lively"],
    ["Achird", "Achird — Friendly & approachable"],
    ["Zubenelgenubi", "Zubenelgenubi — Casual & conversational"],
    ["Vindemiatrix", "Vindemiatrix — Gentle & soothing"],
    ["Sadachbia", "Sadachbia — Lively & animated"],
    ["Sadaltager", "Sadaltager — Knowledgeable & warm"],
    ["Sulafat", "Sulafat — Warm & comforting"],
  ];

  async function loadV2VoiceCast() {
    const selProj = $("proj");
    const slug = (selProj && selProj.value) || activeProject || "";
    const grid = $("v2VoiceGrid");
    const summaryEl = $("v2VoiceSummary");
    const badgeEl = $("v2VoiceBadge");

    if (!grid) return;

    if (!slug) {
      grid.textContent = "";
      if (summaryEl) summaryEl.textContent = "Pick or save a book in Step 01 first.";
      return;
    }

    if (summaryEl) summaryEl.textContent = `Loading all characters for "${slug}"…`;

    // 1. Load saved voice_cast.json
    let savedCast = {}, savedDialect = "american", savedMode = "dialogue";
    try {
      const vc = await callApi(`/api/v2_voice_cast?project=${encodeURIComponent(slug)}`);
      savedCast = (vc && vc.cast) || {};
      savedDialect = (vc && vc.dialect) || "american";
      savedMode = (vc && vc.mode) || "dialogue";
    } catch (e) {}

    // 2. Discover ALL characters from continuity_book, readin/coverage, screenplay, and savedCast
    const chars = new Map(); // lower -> { name, hint, defaultVoice }
    const addChar = (name, hint) => {
      const clean = String(name || "").trim();
      if (!clean) return;
      const key = clean.toLowerCase();
      if (!chars.has(key)) {
        const low = (clean + " " + (hint || "")).toLowerCase();
        const isFemale = /\b(mom|mother|woman|girl|she|her|female|queen|princess|aunt|sister)\b/.test(low);
        const isYoung = /\b(boy|kid|child|5-year|young|doll|toy|puck)\b/.test(low);
        let def = isFemale ? (savedDialect === "british" ? "bf_emma" : "af_bella")
          : isYoung ? (savedDialect === "british" ? "bm_fable" : "am_puck")
          : (savedDialect === "british" ? "bm_george" : "am_michael");
        chars.set(key, { name: clean, hint: hint || "", defaultVoice: def });
      }
    };

    try {
      const cb = await callApi(`/api/continuity_book?project=${encodeURIComponent(slug)}`);
      ((cb && cb.book && cb.book.characters) || []).forEach(c => addChar(c.name, `${c.voice || ""} ${c.token || ""}`));
    } catch (e) {}
    try {
      const rd = await callApi(`/api/readin?project=${encodeURIComponent(slug)}`);
      ((rd && rd.coverage && rd.coverage.characters) || []).forEach(c => addChar(c.name || c, `${c.role || ""} ${c.description || ""}`));
    } catch (e) {}
    try {
      const sp = await callApi(`/api/screenplay?project=${encodeURIComponent(slug)}`);
      ((sp && sp.scenes) || []).forEach(s => {
        ((s.screenplay && s.screenplay.elements) || []).forEach(el => {
          if (el && el.type === "dialogue" && el.character) addChar(el.character, "");
        });
      });
    } catch (e) {}
    Object.keys(savedCast).forEach(name => addChar(name, ""));

    const list = [...chars.values()].sort((a, b) =>
      String(a.name || "").localeCompare(String(b.name || ""), undefined, { sensitivity: "base" })
    );
    if (summaryEl) {
      summaryEl.innerHTML = `<strong style="color:#f59e0b">${list.length} character(s)</strong> · Active dialect: <strong style="color:#f8fafc">${savedDialect}</strong> (${savedMode} mode)`;
    }
    if (badgeEl) {
      badgeEl.textContent = `✓ ${list.length} Voices · ${savedDialect === "british" ? "British RP" : "American"}`;
    }

    const vcScrollY = window.scrollY || 0;
    const vcPrevH = grid.offsetHeight;
    if (vcPrevH > 0) grid.style.minHeight = vcPrevH + "px";
    grid.textContent = "";
    requestAnimationFrame(() => {
      window.scrollTo({ top: vcScrollY, behavior: "instant" });
      grid.style.minHeight = "";
    });

    if (!list.length) {
      const empty = document.createElement("div");
      empty.className = "direct-story-card";
      empty.style.cssText = "grid-column:1/-1;color:#94a3b8;font-size:var(--text-sm);";
      empty.textContent = "No characters found yet. Run Step 07 (Continuity Book) or Step 08 (Cast) first.";
      grid.appendChild(empty);
      return;
    }

    // Rotate varied male/female defaults so characters sound distinct out of the box
    const malePool = savedDialect === "british" ? ["bm_fable", "bm_george", "bm_lewis", "bm_daniel"] : ["am_puck", "am_michael", "am_adam", "am_eric", "am_onyx"];
    const femPool = savedDialect === "british" ? ["bf_emma", "bf_alice", "bf_isabella", "bf_lily"] : ["af_bella", "af_sarah", "af_nicole", "af_heart"];
    let mIdx = 0, fIdx = 0;

    list.forEach(c => {
      // Find saved voice case-insensitively
      const savedKey = Object.keys(savedCast).find(k => k.toLowerCase() === c.name.toLowerCase());
      let assigned = savedKey ? savedCast[savedKey] : "";
      if (!assigned) {
        const isFem = c.defaultVoice.startsWith("af_") || c.defaultVoice.startsWith("bf_");
        assigned = isFem ? femPool[fIdx++ % femPool.length] : malePool[mIdx++ % malePool.length];
      }

      const card = document.createElement("div");
      card.className = "deliverable-card";

      const title = document.createElement("span");
      title.className = "deliverable-title";
      title.textContent = c.name.toUpperCase();
      card.appendChild(title);

      const desc = document.createElement("p");
      desc.className = "deliverable-desc";
      desc.textContent = c.hint ? c.hint.slice(0, 110) : "Spoken dialogue voice assignment";
      card.appendChild(desc);

      const row = document.createElement("div");
      row.style.cssText = "display:flex;gap:8px;margin-top:6px;";
      const sel = document.createElement("select");
      sel.className = "v2-voice-select";
      sel.dataset.speaker = c.name;
      sel.style.cssText = "padding:6px;background:#0f172a;color:#f8fafc;border:1px solid #334155;border-radius:4px;flex:1;font-size:var(--text-xs);";
      KOKORO_VOICES.forEach(([vid, vlabel]) => {
        const opt = document.createElement("option");
        opt.value = vid;
        opt.textContent = vlabel;
        if (vid === assigned) opt.selected = true;
        sel.appendChild(opt);
      });
      row.appendChild(sel);
      card.appendChild(row);
      grid.appendChild(card);
    });
  }

  function initV2VoiceCast() {
    const btnSave = $("bV2VoiceSave");
    const btnReload = $("bV2VoiceReload");
    if (btnReload) btnReload.addEventListener("click", () => loadV2VoiceCast());
    if (btnSave) {
      btnSave.addEventListener("click", () => {
        triggerAudioRedo("dialogue", null, null, collectV2VoiceCast());
      });
    }
    const selProj = $("proj");
    if (selProj) {
      selProj.addEventListener("change", () => {
        if (currentStep === 14) loadV2VoiceCast();
      });
    }
  }

  // ===== STEP 15: SPOKEN DIALOGUE DELIVERY =====
  let v2DialogueState = { project: "", lines: [], scenes: [], dialect: "american", activeScene: "ALL", engine: "gemini-tts", engines: {}, baselines: {} };

  function getCharacterBaseline(character) {
    const b = v2DialogueState.baselines || {};
    const k = Object.keys(b).find(x => x.toLowerCase() === String(character || "").toLowerCase());
    return k ? b[k] : null;
  }

  function renderV2DialogueBaselines() {
    const bar = $("v2DialogueBaselines");
    if (!bar) return;
    bar.innerHTML = "";

    const chars = [...new Set((v2DialogueState.lines || []).map(l => l.character).filter(Boolean))];
    if (!chars.length) return;

    const lbl = document.createElement("span");
    lbl.style.cssText = "font-size:var(--text-xs);color:#94a3b8;font-weight:600";
    lbl.textContent = "🎯 Character Voice Baselines:";
    bar.appendChild(lbl);

    chars.forEach(ch => {
      const base = getCharacterBaseline(ch);
      const pill = document.createElement("div");
      pill.style.cssText = "display:inline-flex;align-items:center;gap:6px;padding:4px 8px;border-radius:6px;font-size:var(--text-xs);border:1px solid " + (base ? "#f59e0b" : "#334155") + ";background:" + (base ? "rgba(245,158,11,0.12)" : "#0f172a");

      const nameEl = document.createElement("span");
      nameEl.style.color = base ? "#fde68a" : "#cbd5e1";
      const libTag = (base && base.saved_to_library) ? " · 📚 Saved for Future Films" : "";
      nameEl.textContent = base ? `${ch.toUpperCase()} (${base.source}${libTag})` : `${ch.toUpperCase()}: none`;
      pill.appendChild(nameEl);

      if (base && base.audio_url) {
        const playBtn = document.createElement("button");
        playBtn.type = "button";
        playBtn.className = "btn btn--ghost";
        playBtn.style.cssText = "padding:1px 6px;font-size:11px";
        playBtn.textContent = "▶";
        playBtn.title = "Play baseline reference clip";
        playBtn.addEventListener("click", () => {
          const a = new Audio(base.audio_url + (base.audio_url.includes("?") ? "&" : "?") + "t=" + Date.now());
          a.play().catch(() => {});
        });
        pill.appendChild(playBtn);

        const clearBtn = document.createElement("button");
        clearBtn.type = "button";
        clearBtn.className = "btn btn--ghost";
        clearBtn.style.cssText = "padding:1px 5px;font-size:11px;color:#f87171";
        clearBtn.textContent = "✕";
        clearBtn.title = "Clear baseline for " + ch;
        clearBtn.addEventListener("click", async () => {
          try {
            await callApi("/api/v2_voice_baseline_set", { project: v2DialogueState.project, character: ch, clear: true });
            Object.keys(v2DialogueState.baselines).forEach(k => {
              if (k.toLowerCase() === ch.toLowerCase()) delete v2DialogueState.baselines[k];
            });
            renderV2DialogueBaselines();
            renderV2DialogueList();
            setV2DialogueStatus(`Cleared voice baseline for ${ch}.`);
          } catch (err) {
            setV2DialogueStatus("Could not clear baseline: " + (err.message || err), true);
          }
        });
        pill.appendChild(clearBtn);
      }

      const upIn = document.createElement("input");
      upIn.type = "file";
      upIn.accept = "audio/*";
      upIn.style.display = "none";
      upIn.addEventListener("change", () => {
        const f = upIn.files && upIn.files[0];
        if (!f) return;
        const reader = new FileReader();
        reader.onload = async () => {
          setV2DialogueStatus(`Uploading baseline clip for ${ch}…`);
          try {
            const res = await callApi("/api/v2_voice_baseline_set", {
              project: v2DialogueState.project,
              character: ch,
              filename: f.name,
              audio_base64: reader.result,
            });
            v2DialogueState.baselines[ch] = res.baseline;
            renderV2DialogueBaselines();
            renderV2DialogueList();
            setV2DialogueStatus(`✓ Locked "${f.name}" as ${ch}'s voice baseline across all scenes.`);
          } catch (err) {
            setV2DialogueStatus("Upload failed: " + (err.message || err), true);
          }
        };
        reader.readAsDataURL(f);
      });

      const upBtn = document.createElement("button");
      upBtn.type = "button";
      upBtn.className = "btn btn--ghost";
      upBtn.style.cssText = "padding:1px 6px;font-size:11px";
      upBtn.textContent = base ? "⬆ Replace" : "⬆ Upload Clip";
      upBtn.title = "Upload a 5-15s voice sample clip as baseline for " + ch;
      upBtn.addEventListener("click", () => upIn.click());
      pill.appendChild(upBtn);
      pill.appendChild(upIn);
      bar.appendChild(pill);
    });
  }

  function renderV2DialogueEngineUI() {
    const active = v2DialogueState.engine || "gemini-tts";
    const eng = v2DialogueState.engines || {};
    const bGem = $("v2DlgEngBadgeGemini");
    const bKok = $("v2DlgEngBadgeKokoro");
    const bMac = $("v2DlgEngBadgeMacos");
    if (bGem) {
      bGem.textContent = eng.gemini_tts ? "✓ Ready (Studio Final)" : "Needs API Key";
      bGem.className = "status-badge " + (eng.gemini_tts ? "status-badge--synced" : "");
    }
    if (bKok) {
      bKok.textContent = eng.kokoro ? "✓ Installed" : "Not Installed";
      bKok.className = "status-badge " + (eng.kokoro ? "status-badge--synced" : "");
    }
    const btnInstKok = $("bV2InstallKokoro");
    if (btnInstKok) {
      btnInstKok.style.display = eng.kokoro ? "none" : "block";
    }
    if (bMac) {
      bMac.textContent = eng.macos_say ? "✓ Ready (Scratch)" : "Unavailable";
      bMac.className = "status-badge " + (eng.macos_say ? "status-badge--synced" : "");
    }
    document.querySelectorAll("#v2DialogueEngineBar .v2-dlg-engine-card").forEach(card => {
      const isSel = card.dataset.engine === active;
      card.style.borderColor = isSel ? "#f59e0b" : "";
      card.style.boxShadow = isSel ? "0 0 0 1px rgba(245,158,11,0.5)" : "";
      card.style.background = isSel ? "rgba(245,158,11,0.08)" : "";
    });
  }

  async function selectV2DialogueEngine(engine, persist = true) {
    v2DialogueState.engine = engine;
    renderV2DialogueEngineUI();
    renderV2DialogueList();
    const labels = {
      "gemini-tts": "✨ Gemini Neural TTS (30 Studio Voices + Persona)",
      "kokoro": "🎙️ Kokoro-82M Local Neural (28 Voices + Blending)",
      "macos-say": "⚡ Fast Scratch Preview (All Installed macOS Voices)",
    };
    setV2DialogueStatus(`Selected engine: ${labels[engine] || engine}. Voice menus updated below.`);
    if (persist && v2DialogueState.project) {
      try {
        await callApi("/api/v2_dialogue_save", { project: v2DialogueState.project, engine });
      } catch (e) {}
    }
  }

  function setV2DialogueStatus(msg, isErr) {
    const st = $("v2DialogueStatus");
    if (!st) return;
    st.textContent = msg || "";
    st.style.color = isErr ? "#f87171" : "#34d399";
  }

  function defaultGeminiForKokoro(kVoice) {
    const v = String(kVoice || "").toLowerCase();
    const map = {
      am_puck: "Puck", am_michael: "Charon", am_adam: "Fenrir", am_eric: "Orus", am_onyx: "Charon",
      bm_fable: "Puck", bm_george: "Charon", bm_lewis: "Orus", bm_daniel: "Fenrir",
      af_bella: "Aoede", af_sarah: "Kore", af_nicole: "Leda", af_heart: "Zephyr",
      bf_emma: "Aoede", bf_alice: "Kore", bf_isabella: "Leda", bf_lily: "Zephyr",
    };
    if (map[v]) return map[v];
    return (v.startsWith("af_") || v.startsWith("bf_")) ? "Aoede" : "Puck";
  }

  function extractCardPayload(card, line) {
    const eng = v2DialogueState.engine || "gemini-tts";
    const text = (card.querySelector(".v2-dlg-text")?.value || "").trim();
    const pickedVoice = card.querySelector(".v2-dlg-voice")?.value || "";
    const blend = card.querySelector(".v2-dlg-blend")?.value || "";
    const persona = (card.querySelector(".v2-dlg-persona")?.value || "").trim();
    const emotion = card.querySelector(".v2-dlg-emotion")?.value || "natural";
    const speed = parseFloat(card.querySelector(".v2-dlg-speed")?.value || "1.0") || 1.0;
    const note = (card.querySelector(".v2-dlg-note")?.value || "").trim();

    const payload = {
      id: line.id,
      character: line.character || "",
      text,
      voice: eng === "kokoro" ? pickedVoice : (line.kokoro_voice || line.voice || "am_puck"),
      gemini_voice: eng === "gemini-tts" ? pickedVoice : (line.gemini_voice || defaultGeminiForKokoro(line.voice)),
      kokoro_voice: eng === "kokoro" ? pickedVoice : (line.kokoro_voice || line.voice || "am_puck"),
      kokoro_blend: eng === "kokoro" ? blend : (line.kokoro_blend || ""),
      macos_voice: eng === "macos-say" ? pickedVoice : (line.macos_voice || ""),
      persona,
      emotion,
      speed,
      note,
    };
    return payload;
  }

  function collectVisibleDialogueEdits() {
    const out = [];
    document.querySelectorAll("#v2DialogueList .v2-dlg-card").forEach(card => {
      const id = card.dataset.lineId;
      const line = v2DialogueState.lines.find(l => l.id === id);
      if (!id || !line) return;
      out.push(extractCardPayload(card, line));
    });
    return out;
  }

  async function renderV2DialogueLines(linesToRender, autoPlayId, triggerBtn) {
    const proj = v2DialogueState.project;
    if (!proj || !linesToRender.length) return;
    const engine = v2DialogueState.engine || "gemini-tts";
    const activeCards = linesToRender
      .map(l => document.querySelector(`#v2DialogueList .v2-dlg-card[data-line-id="${l.id}"]`))
      .filter(Boolean);
    const label = linesToRender.length === 1
      ? `Rendering ${linesToRender[0].id} via ${engine}…`
      : `Rendering ${linesToRender.length} dialogue lines via ${engine}…`;
    const stopBusy = startBusyFeedback(triggerBtn || null, activeCards, label);
    setV2DialogueStatus(label);
    try {
      await callApi("/api/v2_dialogue_save", { project: proj, engine, lines: linesToRender });
      const res = await callApi("/api/v2_dialogue_render", {
        project: proj,
        dialect: v2DialogueState.dialect || "american",
        engine,
        lines: linesToRender,
      });
      const rendered = res.rendered || [];
      const ts = Date.now();
      rendered.forEach(r => {
        const entry = v2DialogueState.lines.find(l => l.id === r.id);
        if (entry) {
          entry.has_audio = true;
          entry.audio_url = r.audio_url + "?t=" + ts;
        }
        const edited = linesToRender.find(x => x.id === r.id);
        if (entry && edited) {
          Object.assign(entry, edited);
        }
      });
      renderV2DialogueList();
      setV2DialogueStatus(`✓ Rendered ${rendered.length} line${rendered.length === 1 ? "" : "s"} (${res.engine || engine})`);
      if (autoPlayId) {
        const audioEl = document.querySelector(`#v2DialogueList .v2-dlg-card[data-line-id="${autoPlayId}"] audio`);
        if (audioEl) {
          audioEl.currentTime = 0;
          audioEl.play().catch(() => {});
        }
      }
    } catch (e) {
      setV2DialogueStatus("Render failed: " + (e.message || e), true);
    } finally {
      stopBusy();
    }
  }

  function renderV2DialogueScenes() {
    const bar = $("v2DialogueScenes");
    if (!bar) return;
    bar.innerHTML = "";
    const scenes = v2DialogueState.scenes || [];
    const allBtn = document.createElement("button");
    allBtn.type = "button";
    allBtn.className = "btn " + (v2DialogueState.activeScene === "ALL" ? "btn--primary" : "btn--ghost");
    allBtn.style.cssText = "padding:4px 10px;font-size:var(--text-xs)";
    allBtn.textContent = `All Scenes (${v2DialogueState.lines.length} lines)`;
    allBtn.addEventListener("click", () => {
      v2DialogueState.activeScene = "ALL";
      renderV2DialogueScenes();
      renderV2DialogueList();
    });
    bar.appendChild(allBtn);

    scenes.forEach(sc => {
      const count = v2DialogueState.lines.filter(l => l.scene === sc).length;
      const b = document.createElement("button");
      b.type = "button";
      b.className = "btn " + (v2DialogueState.activeScene === sc ? "btn--primary" : "btn--ghost");
      b.style.cssText = "padding:4px 10px;font-size:var(--text-xs)";
      b.textContent = `${sc} (${count})`;
      b.addEventListener("click", () => {
        v2DialogueState.activeScene = sc;
        renderV2DialogueScenes();
        renderV2DialogueList();
      });
      bar.appendChild(b);
    });
  }

  function renderV2DialogueList() {
    const list = $("v2DialogueList");
    const summary = $("v2DialogueSummary");
    const badge = $("v2DialogueBadge");
    if (!list) return;
    const savedX = window.scrollX || 0;
    const savedY = window.scrollY || 0;
    const prevH = list.offsetHeight;
    if (prevH > 0) list.style.minHeight = prevH + "px";
    list.innerHTML = "";

    const eng = v2DialogueState.engine || "gemini-tts";
    const filtered = v2DialogueState.activeScene === "ALL"
      ? v2DialogueState.lines
      : v2DialogueState.lines.filter(l => l.scene === v2DialogueState.activeScene);

    const renderedCount = v2DialogueState.lines.filter(l => l.has_audio).length;
    if (summary) {
      summary.textContent = v2DialogueState.lines.length
        ? `${v2DialogueState.lines.length} spoken dialogue lines across ${v2DialogueState.scenes.length} scenes · ${renderedCount} rendered`
        : "No spoken dialogue lines found in screenplay yet. Complete Step 06 (Screenplay) first.";
    }
    if (badge) {
      badge.textContent = renderedCount > 0 ? `✓ ${renderedCount}/${v2DialogueState.lines.length} Rendered` : `${v2DialogueState.lines.length} Lines Ready`;
    }

    if (!filtered.length) {
      const empty = document.createElement("div");
      empty.className = "direct-story-card";
      empty.style.color = "#94a3b8";
      empty.textContent = "No dialogue lines in this selection.";
      list.appendChild(empty);
      return;
    }

    const macVoices = (v2DialogueState.macos_voices && v2DialogueState.macos_voices.length)
      ? v2DialogueState.macos_voices.map(v => [v.id, v.label])
      : [["Samantha", "Samantha (en_US)"], ["Alex", "Alex (en_US)"], ["Daniel", "Daniel (en_GB)"], ["Serena", "Serena (en_GB)"], ["Fred", "Fred (en_US)"]];

    filtered.forEach(line => {
      const card = document.createElement("div");
      card.className = "direct-story-card v2-dlg-card";
      card.dataset.lineId = line.id;

      // Header row
      const hdr = document.createElement("div");
      hdr.style.cssText = "display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;margin-bottom:8px";
      const left = document.createElement("div");
      left.style.cssText = "display:flex;align-items:center;flex-wrap:wrap;gap:8px";
      const strong = document.createElement("strong");
      strong.style.color = "#f59e0b";
      strong.textContent = `${line.id} · ${line.character.toUpperCase()}`;
      left.appendChild(strong);
      if (line.heading) {
        const sub = document.createElement("span");
        sub.style.cssText = "color:#94a3b8;font-size:var(--text-xs)";
        sub.textContent = line.heading;
        left.appendChild(sub);
      }
      const charBase = getCharacterBaseline(line.character);
      if (charBase && charBase.audio_url) {
        const baseWrap = document.createElement("span");
        baseWrap.style.cssText = "display:inline-flex;align-items:center;gap:5px;padding:2px 8px;border-radius:999px;background:rgba(245,158,11,0.14);border:1px solid rgba(245,158,11,0.55);color:#fde68a;font-size:11px;font-weight:600";
        const baseTxt = document.createElement("span");
        baseTxt.textContent = `🎯 Baseline: ${charBase.source}${charBase.saved_to_library ? " · 📚 Library" : ""}`;
        baseWrap.appendChild(baseTxt);

        const btnPlayBase = document.createElement("button");
        btnPlayBase.type = "button";
        btnPlayBase.className = "btn btn--ghost";
        btnPlayBase.style.cssText = "padding:1px 6px;font-size:11px;color:#fde68a;border-color:rgba(245,158,11,0.4)";
        btnPlayBase.textContent = "▶ Play Baseline";
        btnPlayBase.title = `Play ${line.character}'s locked voice baseline (${charBase.source})`;
        btnPlayBase.addEventListener("click", () => {
          const url = charBase.audio_url + (charBase.audio_url.includes("?") ? "&" : "?") + "t=" + Date.now();
          const a = new Audio(url);
          a.play().catch(() => {});
        });
        baseWrap.appendChild(btnPlayBase);
        left.appendChild(baseWrap);
      }
      hdr.appendChild(left);

      const actions = document.createElement("div");
      actions.style.cssText = "display:flex;gap:6px;flex-wrap:wrap;align-items:center";

      const btnPlay = document.createElement("button");
      btnPlay.type = "button";
      btnPlay.className = "btn btn--primary";
      btnPlay.style.cssText = "padding:4px 10px;font-size:var(--text-xs)";
      btnPlay.textContent = line.has_audio ? "▶ Play Line" : "▶ Render & Play";
      btnPlay.addEventListener("click", async () => {
        const existingAudio = card.querySelector("audio");
        const p = extractCardPayload(card, line);
        const curVoiceForEng = eng === "gemini-tts" ? (line.gemini_voice || defaultGeminiForKokoro(line.voice))
          : eng === "kokoro" ? (line.kokoro_voice || line.voice) : (line.macos_voice || "");
        const picked = card.querySelector(".v2-dlg-voice")?.value || "";
        const changed = p.text !== line.text || picked !== curVoiceForEng || p.persona !== (line.persona || "") || p.kokoro_blend !== (line.kokoro_blend || "") || Math.abs(p.speed - (line.speed || 1.0)) > 0.01;
        if (existingAudio && line.has_audio && !changed) {
          existingAudio.currentTime = 0;
          existingAudio.play().catch(() => {});
          return;
        }
        await renderV2DialogueLines([p], line.id);
      });

      const btnRedo = document.createElement("button");
      btnRedo.type = "button";
      btnRedo.className = "btn btn--ghost";
      btnRedo.style.cssText = "padding:4px 10px;font-size:var(--text-xs)";
      btnRedo.textContent = "↺ Redo Line";
      btnRedo.addEventListener("click", async () => {
        await renderV2DialogueLines([extractCardPayload(card, line)], line.id);
      });

      // Save voice profile for this character across ALL scenes (leaving per-scene tone alone!)
      const btnApplyAll = document.createElement("button");
      btnApplyAll.type = "button";
      btnApplyAll.className = "btn btn--secondary";
      btnApplyAll.style.cssText = "padding:4px 10px;font-size:var(--text-xs)";
      btnApplyAll.title = "Save this voice & persona for every scene spoken by " + line.character + " (leaves each scene's Tone untouched)";
      btnApplyAll.textContent = `📌 Save Voice for All ${line.character.toUpperCase()} Scenes`;
      btnApplyAll.addEventListener("click", async () => {
        const p = extractCardPayload(card, line);
        setV2DialogueStatus(`Applying ${line.character}'s voice profile across all scenes (preserving per-scene tones)…`);
        try {
          const res = await callApi("/api/v2_voice_profile_apply", {
            project: v2DialogueState.project,
            character: line.character,
            gemini_voice: p.gemini_voice,
            kokoro_voice: p.kokoro_voice,
            kokoro_blend: p.kokoro_blend,
            macos_voice: p.macos_voice,
            persona: p.persona,
          });
          // Update in-memory state for all lines of this character WITHOUT touching emotion/tone or note
          v2DialogueState.lines.forEach(l => {
            if (l.character.toLowerCase() === line.character.toLowerCase()) {
              l.gemini_voice = p.gemini_voice;
              l.kokoro_voice = p.kokoro_voice;
              l.kokoro_blend = p.kokoro_blend;
              l.macos_voice = p.macos_voice;
              l.voice = p.kokoro_voice;
              l.persona = p.persona;
            }
          });
          renderV2DialogueList();
          setV2DialogueStatus(`✓ Saved ${line.character}'s voice profile across ${res.updated_lines || 0} lines in all scenes (scene tones untouched).`);
        } catch (err) {
          setV2DialogueStatus("Could not apply voice profile: " + (err.message || err), true);
        }
      });

      // Upload Custom Take (.wav / .mp3 / .m4a)
      const fileIn = document.createElement("input");
      fileIn.type = "file";
      fileIn.accept = "audio/*";
      fileIn.style.display = "none";
      fileIn.addEventListener("change", () => {
        const f = fileIn.files && fileIn.files[0];
        if (!f) return;
        const reader = new FileReader();
        reader.onload = async () => {
          setV2DialogueStatus(`Uploading custom take for ${line.id}…`);
          try {
            const res = await callApi("/api/v2_dialogue_upload", {
              project: v2DialogueState.project,
              id: line.id,
              filename: f.name,
              audio_base64: reader.result,
            });
            line.has_audio = true;
            line.audio_url = res.audio_url + "?t=" + Date.now();
            renderV2DialogueList();
            setV2DialogueStatus(`✓ Uploaded custom take "${f.name}" for ${line.id}.`);
          } catch (err) {
            setV2DialogueStatus("Upload failed: " + (err.message || err), true);
          }
        };
        reader.readAsDataURL(f);
      });
      const btnUpload = document.createElement("button");
      btnUpload.type = "button";
      btnUpload.className = "btn btn--ghost";
      btnUpload.style.cssText = "padding:4px 8px;font-size:var(--text-xs)";
      btnUpload.textContent = "⬆ Upload Take";
      btnUpload.addEventListener("click", () => fileIn.click());

      actions.appendChild(btnPlay);
      actions.appendChild(btnRedo);

      if (line.has_audio) {
        const curBase = getCharacterBaseline(line.character);
        const isThisBase = curBase && curBase.source === line.id;
        const btnBase = document.createElement("button");
        btnBase.type = "button";
        btnBase.className = "btn " + (isThisBase ? "btn--primary" : "btn--secondary");
        btnBase.style.cssText = "padding:4px 10px;font-size:var(--text-xs)";
        btnBase.textContent = isThisBase ? `✓ ${line.character.toUpperCase()} Baseline` : `🎯 Set as ${line.character.toUpperCase()} Baseline`;
        btnBase.title = `Lock this exact rendered take as ${line.character}'s audio voice baseline for all other lines`;
        btnBase.addEventListener("click", async () => {
          setV2DialogueStatus(`Locking ${line.id} as ${line.character}'s audio voice baseline…`);
          try {
            const res = await callApi("/api/v2_voice_baseline_set", {
              project: v2DialogueState.project,
              character: line.character,
              from_line_id: line.id,
              text: (card.querySelector(".v2-dlg-text")?.value || line.text || "").trim(),
            });
            v2DialogueState.baselines[line.character] = res.baseline;
            renderV2DialogueBaselines();
            renderV2DialogueList();
            setV2DialogueStatus(`✓ Locked ${line.id} as ${line.character}'s permanent audio baseline. Future renders for ${line.character} will match this voice.`);
          } catch (err) {
            setV2DialogueStatus("Could not set baseline: " + (err.message || err), true);
          }
        });
        actions.appendChild(btnBase);
      }

      actions.appendChild(btnApplyAll);
      actions.appendChild(btnUpload);
      actions.appendChild(fileIn);
      hdr.appendChild(actions);
      card.appendChild(hdr);

      // Editable line textarea
      const ta = document.createElement("textarea");
      ta.className = "v2-dlg-text";
      ta.rows = 2;
      ta.value = line.text || "";
      ta.style.cssText = "width:100%;padding:8px 10px;background:#0a0d14;color:#f8fafc;border:1px solid #334155;border-radius:6px;font-size:var(--text-sm);margin-bottom:8px;resize:vertical;";
      card.appendChild(ta);

      // Row 1: Engine-specific Voice selector (+ Kokoro Blend selector) + Character Voice Persona
      const voiceRow = document.createElement("div");
      voiceRow.style.cssText = "display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-bottom:6px";

      const selVoice = document.createElement("select");
      selVoice.className = "v2-dlg-voice";
      selVoice.style.cssText = "padding:5px 8px;background:#0f172a;color:#f8fafc;border:1px solid #334155;border-radius:4px;font-size:var(--text-xs);min-width:210px";
      let voiceOpts = GEMINI_VOICES;
      let activeVal = line.gemini_voice || defaultGeminiForKokoro(line.voice);
      if (eng === "kokoro") {
        voiceOpts = KOKORO_VOICES;
        activeVal = line.kokoro_voice || line.voice || "am_puck";
      } else if (eng === "macos-say") {
        voiceOpts = macVoices;
        activeVal = line.macos_voice || (macVoices[0] && macVoices[0][0]) || "Samantha";
      }
      voiceOpts.forEach(([vid, vlabel]) => {
        const opt = document.createElement("option");
        opt.value = vid;
        opt.textContent = vlabel;
        if (vid === activeVal) opt.selected = true;
        selVoice.appendChild(opt);
      });
      voiceRow.appendChild(selVoice);

      if (eng === "kokoro") {
        const selBlend = document.createElement("select");
        selBlend.className = "v2-dlg-blend";
        selBlend.style.cssText = "padding:5px 8px;background:#0f172a;color:#cbd5e1;border:1px solid #334155;border-radius:4px;font-size:var(--text-xs)";
        const noneOpt = document.createElement("option");
        noneOpt.value = "";
        noneOpt.textContent = "Blend: None (single voice)";
        selBlend.appendChild(noneOpt);
        KOKORO_VOICES.forEach(([vid, vlabel]) => {
          const opt = document.createElement("option");
          opt.value = vid;
          opt.textContent = "Blend + " + vlabel;
          if (vid === (line.kokoro_blend || "")) opt.selected = true;
          selBlend.appendChild(opt);
        });
        voiceRow.appendChild(selBlend);
      }

      const personaIn = document.createElement("input");
      personaIn.type = "text";
      personaIn.className = "v2-dlg-persona";
      personaIn.placeholder = "Voice Persona (e.g. energetic 5-year-old boy, warm gentle mother, gravelly space captain)…";
      personaIn.value = line.persona || "";
      personaIn.style.cssText = "flex:1;min-width:220px;padding:5px 8px;background:#0f172a;color:#fde68a;border:1px solid #475569;border-radius:4px;font-size:var(--text-xs)";
      voiceRow.appendChild(personaIn);
      card.appendChild(voiceRow);

      // Row 2: Per-scene Tone, Speed, and Delivery Direction Note
      const ctrl = document.createElement("div");
      ctrl.style.cssText = "display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-bottom:8px";

      const selEmo = document.createElement("select");
      selEmo.className = "v2-dlg-emotion";
      selEmo.style.cssText = "padding:5px 8px;background:#0f172a;color:#f8fafc;border:1px solid #334155;border-radius:4px;font-size:var(--text-xs)";
      ["natural", "excited", "warm", "whisper", "dramatic", "sad", "curious", "playful", "urgent", "sleepy", "amazed"].forEach(em => {
        const opt = document.createElement("option");
        opt.value = em;
        opt.textContent = "Scene Tone: " + em;
        if (em === (line.emotion || "natural")) opt.selected = true;
        selEmo.appendChild(opt);
      });
      ctrl.appendChild(selEmo);

      const selSpd = document.createElement("select");
      selSpd.className = "v2-dlg-speed";
      selSpd.style.cssText = "padding:5px 8px;background:#0f172a;color:#f8fafc;border:1px solid #334155;border-radius:4px;font-size:var(--text-xs)";
      [0.8, 0.9, 1.0, 1.1, 1.2, 1.3].forEach(sp => {
        const opt = document.createElement("option");
        opt.value = String(sp);
        opt.textContent = `Speed: ${sp.toFixed(1)}x`;
        if (Math.abs(sp - (line.speed || 1.0)) < 0.05) opt.selected = true;
        selSpd.appendChild(opt);
      });
      ctrl.appendChild(selSpd);

      const noteIn = document.createElement("input");
      noteIn.type = "text";
      noteIn.className = "v2-dlg-note";
      noteIn.placeholder = "Scene delivery direction (e.g. waving to camera, soft whisper)…";
      noteIn.value = line.note || "";
      noteIn.style.cssText = "flex:1;min-width:160px;padding:5px 8px;background:#0f172a;color:#cbd5e1;border:1px solid #334155;border-radius:4px;font-size:var(--text-xs)";
      ctrl.appendChild(noteIn);
      card.appendChild(ctrl);

      // Audio player bar
      const playerWrap = document.createElement("div");
      playerWrap.style.cssText = "display:flex;align-items:center;gap:10px;background:#0a0d14;padding:6px 10px;border-radius:6px";
      if (line.has_audio && line.audio_url) {
        const aud = document.createElement("audio");
        aud.controls = true;
        aud.preload = "none";
        aud.src = line.audio_url;
        aud.style.cssText = "flex:1;height:30px";
        playerWrap.appendChild(aud);
      } else {
        const ph = document.createElement("span");
        ph.style.cssText = "flex:1;color:#64748b;font-size:var(--text-xs)";
        ph.textContent = "Not rendered yet — click ▶ Render & Play, 🎙️ Render Scene Audio, or ⬆ Upload Take";
        playerWrap.appendChild(ph);
      }
      card.appendChild(playerWrap);
      list.appendChild(card);
    });
    window.scrollTo({ left: savedX, top: savedY, behavior: "instant" });
    requestAnimationFrame(() => {
      window.scrollTo({ left: savedX, top: savedY, behavior: "instant" });
      list.style.minHeight = "";
    });
  }

  async function loadV2Dialogue() {
    const selProj = $("proj");
    const proj = selProj ? (selProj.value || "").trim() : "";
    const summary = $("v2DialogueSummary");
    const list = $("v2DialogueList");
    if (!list) return;
    if (!proj) {
      if (summary) summary.textContent = "Select a book in Step 01 first to load its spoken dialogue.";
      list.innerHTML = "";
      return;
    }
    if (summary) summary.textContent = "Loading spoken dialogue lines…";
    try {
      const data = await callApi(`/api/v2_dialogue?project=${encodeURIComponent(proj)}`);
      v2DialogueState.project = proj;
      v2DialogueState.lines = data.lines || [];
      v2DialogueState.scenes = data.scenes || [];
      v2DialogueState.dialect = data.dialect || "american";
      v2DialogueState.engine = data.engine || "gemini-tts";
      v2DialogueState.engines = data.engines || {};
      v2DialogueState.macos_voices = data.macos_voices || [];
      v2DialogueState.baselines = data.baselines || {};
      if (v2DialogueState.activeScene !== "ALL" && !v2DialogueState.scenes.includes(v2DialogueState.activeScene)) {
        v2DialogueState.activeScene = v2DialogueState.scenes[0] || "ALL";
      }
      renderV2DialogueEngineUI();
      renderV2DialogueScenes();
      renderV2DialogueBaselines();
      renderV2DialogueList();
    } catch (e) {
      setV2DialogueStatus("Could not load dialogue: " + (e.message || e), true);
    }
  }

  function initV2Dialogue() {
    document.querySelectorAll("#v2DialogueEngineBar .v2-dlg-engine-card").forEach(card => {
      card.addEventListener("click", (e) => {
        if (e.target && e.target.id === "bV2InstallKokoro") return;
        const eng = card.dataset.engine;
        if (eng) selectV2DialogueEngine(eng, true);
      });
    });
    const btnInstKok = $("bV2InstallKokoro");
    if (btnInstKok) {
      btnInstKok.addEventListener("click", async (e) => {
        e.stopPropagation();
        btnInstKok.disabled = true;
        btnInstKok.textContent = "⏳ Installing Kokoro-82M…";
        setV2DialogueStatus("Waiting for approval to install Kokoro-82M…");
        try {
          const ok = await requestInstallWithApproval("kokoro", "Kokoro-82M Neural TTS", "kokoro, soundfile");
          if (!ok) {
            btnInstKok.textContent = "⬇ Install Kokoro-82M (Approved)";
            setV2DialogueStatus("Installation cancelled.");
            return;
          }
          v2DialogueState.engines.kokoro = true;
          selectV2DialogueEngine("kokoro", true);
          setV2DialogueStatus("✓ Kokoro-82M installed and selected!");
        } catch (err) {
          setV2DialogueStatus("Install failed: " + (err.message || err), true);
          btnInstKok.textContent = "⬇ Install Kokoro-82M (Approved)";
        } finally {
          btnInstKok.disabled = false;
        }
      });
    }
    const btnReload = $("bV2DialogueReload");
    const btnSaveAll = $("bV2DialogueSaveAll");
    const btnRenderScene = $("bV2DialogueRenderScene");
    if (btnReload) btnReload.addEventListener("click", () => loadV2Dialogue());
    if (btnSaveAll) {
      btnSaveAll.addEventListener("click", async () => {
        const proj = v2DialogueState.project;
        if (!proj) return;
        const edits = collectVisibleDialogueEdits();
        if (!edits.length) return;
        setV2DialogueStatus("Saving dialogue edits…");
        try {
          const res = await callApi("/api/v2_dialogue_save", { project: proj, engine: v2DialogueState.engine, lines: edits });
          setV2DialogueStatus(`✓ Saved ${res.saved || edits.length} dialogue line edits.`);
          const textChanged = edits.filter(ed => {
            const orig = (v2DialogueState.lines || []).find(l => l.id === ed.id);
            return orig && ed.text && ed.text !== orig.text;
          });
          if (textChanged.length) {
            proposeUpstreamSync({
              project: proj,
              kind: "dialogue_to_screenplay",
              affectedStepNums: [6],
              title: "🔄 Sync Dialogue Edits Back to Step 06 (Screenplay)?",
              message: `You changed ${textChanged.length} spoken dialogue line(s) in Step 15.\n\nWould you like to update Step 06 (Screenplay) so the script matches your new lines?`,
              payload: { lines: textChanged },
              onSynced: () => {
                textChanged.forEach(ed => {
                  const orig = (v2DialogueState.lines || []).find(l => l.id === ed.id);
                  if (orig) orig.text = ed.text;
                });
                setV2DialogueStatus(`✓ Saved & synced ${textChanged.length} line edit(s) back to Step 06 (Screenplay).`);
              },
            });
          }
        } catch (e) {
          setV2DialogueStatus("Save failed: " + (e.message || e), true);
        }
      });
    }
    if (btnRenderScene) {
      btnRenderScene.addEventListener("click", async () => {
        const edits = collectVisibleDialogueEdits();
        if (!edits.length) return;
        await renderV2DialogueLines(edits, null);
      });
    }
    const selProj = $("proj");
    if (selProj) {
      selProj.addEventListener("change", () => {
        if (currentStep === 15) loadV2Dialogue();
        if (currentStep === 16) loadV2SoundDesign();
      });
    }
  }

  // ===== STEP 16: SCORE & FOLEY SOUND DESIGN =====
  let v2SoundState = { project: "", sfx_mode: "hybrid", scenes: [] };

  function renderV2SoundModeUI() {
    const active = v2SoundState.sfx_mode || "hybrid";
    document.querySelectorAll("#v2SoundModeBar .v2-sound-mode-card").forEach(card => {
      const isSel = card.dataset.mode === active;
      card.style.borderColor = isSel ? "#f59e0b" : "";
      card.style.boxShadow = isSel ? "0 0 0 1px rgba(245,158,11,0.55)" : "";
      card.style.background = isSel ? "rgba(245,158,11,0.08)" : "";
    });
  }

  function renderV2SoundScenesList() {
    const list = $("v2SoundScenesList");
    const summary = $("v2SoundScenesSummary");
    if (!list) return;
    const savedY = window.scrollY || 0;
    const prevH = list.offsetHeight;
    if (prevH > 0) list.style.minHeight = prevH + "px";
    list.innerHTML = "";

    const scenes = v2SoundState.scenes || [];
    if (summary) {
      const done = scenes.filter(s => s.has_sfx).length;
      summary.textContent = scenes.length
        ? `${scenes.length} scenes auto-cued from screenplay · ${done} custom SFX rendered`
        : "No screenplay scenes found yet.";
    }
    if (!scenes.length) {
      list.style.minHeight = "";
      return;
    }

    const PRESETS = [
      ["space_adventure", "Space & Cockpit"],
      ["action_launch", "Rocket Launch & Shake"],
      ["rainy_home", "Rainy Home & Room"],
      ["cosmic_storm", "Ice Rings & Wind"],
      ["forest_nature", "Quiet Night & Nature"],
    ];
    const MOODS = [
      ["wonder", "Score: Wonder"],
      ["epic", "Score: Epic"],
      ["cozy", "Score: Cozy"],
      ["mysterious", "Score: Mysterious"],
      ["playful", "Score: Playful"],
      ["none", "Score: Silent"],
    ];

    scenes.forEach(sc => {
      const row = document.createElement("div");
      row.className = "direct-story-card v2-sound-scene-row";
      row.dataset.sceneId = sc.scene;
      row.style.cssText = "padding:10px 12px;background:#0f172a;border:1px solid #232d3f;";

      const top = document.createElement("div");
      top.style.cssText = "display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;margin-bottom:6px";
      const titleWrap = document.createElement("div");
      const st = document.createElement("strong");
      st.style.color = "#f59e0b";
      st.textContent = `${sc.scene} · ${sc.heading || "Scene"}`;
      titleWrap.appendChild(st);
      if (sc.hint) {
        const hint = document.createElement("div");
        hint.style.cssText = "font-size:11px;color:#94a3b8;margin-top:2px";
        hint.textContent = sc.hint.slice(0, 120) + (sc.hint.length > 120 ? "…" : "");
        titleWrap.appendChild(hint);
      }
      top.appendChild(titleWrap);

      const btns = document.createElement("div");
      btns.style.cssText = "display:flex;gap:6px;flex-wrap:wrap";
      const btnRen = document.createElement("button");
      btnRen.type = "button";
      btnRen.className = "btn btn--primary";
      btnRen.style.cssText = "padding:4px 10px;font-size:var(--text-xs)";
      btnRen.textContent = sc.has_sfx ? "↺ Redo Scene SFX" : "✨ Render Scene SFX";

      const upIn = document.createElement("input");
      upIn.type = "file";
      upIn.accept = "audio/*";
      upIn.style.display = "none";
      const btnUp = document.createElement("button");
      btnUp.type = "button";
      btnUp.className = "btn btn--ghost";
      btnUp.style.cssText = "padding:4px 8px;font-size:var(--text-xs)";
      btnUp.textContent = "⬆ Upload";
      btnUp.addEventListener("click", () => upIn.click());

      btns.appendChild(btnRen);
      btns.appendChild(btnUp);
      btns.appendChild(upIn);
      top.appendChild(btns);
      row.appendChild(top);

      const ctrls = document.createElement("div");
      ctrls.style.cssText = "display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-bottom:6px";
      const cueIn = document.createElement("input");
      cueIn.type = "text";
      cueIn.className = "v2-sc-sfx-cue";
      cueIn.value = sc.sfx_cue || "";
      cueIn.placeholder = "Describe SFX needed for this scene (e.g. rockets burning, hull shaking)…";
      cueIn.style.cssText = "flex:1;min-width:200px;padding:5px 8px;background:#0a0d14;color:#f8fafc;border:1px solid #334155;border-radius:4px;font-size:var(--text-xs)";

      const selPre = document.createElement("select");
      selPre.className = "v2-sc-sfx-preset";
      selPre.style.cssText = "padding:5px 8px;background:#0a0d14;color:#f8fafc;border:1px solid #334155;border-radius:4px;font-size:var(--text-xs)";
      PRESETS.forEach(([k, l]) => {
        const o = document.createElement("option");
        o.value = k; o.textContent = l;
        if (k === sc.sfx_preset) o.selected = true;
        selPre.appendChild(o);
      });

      const selMood = document.createElement("select");
      selMood.className = "v2-sc-score-mood";
      selMood.style.cssText = "padding:5px 8px;background:#0a0d14;color:#cbd5e1;border:1px solid #334155;border-radius:4px;font-size:var(--text-xs)";
      MOODS.forEach(([k, l]) => {
        const o = document.createElement("option");
        o.value = k; o.textContent = l;
        if (k === sc.score_mood) o.selected = true;
        selMood.appendChild(o);
      });

      ctrls.appendChild(cueIn);
      ctrls.appendChild(selPre);
      ctrls.appendChild(selMood);
      row.appendChild(ctrls);

      const player = document.createElement("div");
      player.style.cssText = "background:#0a0d14;padding:4px 8px;border-radius:4px;font-size:11px;color:#64748b";
      if (sc.has_sfx && sc.sfx_url) {
        const aud = document.createElement("audio");
        aud.controls = true;
        aud.preload = "none";
        aud.src = sc.sfx_url + (sc.sfx_url.includes("?") ? "&" : "?") + "t=" + Date.now();
        aud.style.cssText = "width:100%;height:28px";
        player.appendChild(aud);
      } else {
        player.textContent = "Using video-aligned / master SFX — click ✨ Render Scene SFX or ⬆ Upload to customize this scene";
      }
      row.appendChild(player);

      btnRen.addEventListener("click", async () => {
        const stopBusy = startBusyFeedback(btnRen, row, `Rendering ${sc.scene} SFX…`);
        setV2SoundStatus(`Rendering custom SFX for ${sc.scene}…`);
        try {
          const res = await callApi("/api/v2_sound_design_render", {
            project: v2SoundState.project,
            kind: "foley",
            scene: sc.scene,
            prompt: cueIn.value.trim(),
            preset: selPre.value,
            duration: 8,
          });
          sc.sfx_cue = cueIn.value.trim();
          sc.sfx_preset = selPre.value;
          sc.score_mood = selMood.value;
          sc.has_sfx = true;
          sc.sfx_url = res.audio_url;
          renderV2SoundScenesList();
          setV2SoundStatus(`✓ Rendered custom SFX for ${sc.scene}!`);
          const newAud = document.querySelector(`#v2SoundScenesList .v2-sound-scene-row[data-scene-id="${sc.scene}"] audio`);
          if (newAud) newAud.play().catch(() => {});
        } catch (err) {
          setV2SoundStatus(`Scene ${sc.scene} SFX failed: ` + (err.message || err), true);
        } finally {
          stopBusy();
        }
      });

      upIn.addEventListener("change", () => {
        const f = upIn.files && upIn.files[0];
        if (!f) return;
        const reader = new FileReader();
        reader.onload = async () => {
          const stopBusy = startBusyFeedback(btnUp, row, `Uploading ${f.name} for ${sc.scene}…`);
          try {
            const res = await callApi("/api/v2_sound_design_render", {
              project: v2SoundState.project,
              kind: "foley",
              scene: sc.scene,
              filename: f.name,
              audio_base64: reader.result,
            });
            sc.has_sfx = true;
            sc.sfx_url = res.audio_url;
            renderV2SoundScenesList();
            setV2SoundStatus(`✓ Uploaded "${f.name}" for ${sc.scene}.`);
          } catch (err) {
            setV2SoundStatus("Upload failed: " + (err.message || err), true);
          } finally {
            stopBusy();
          }
        };
        reader.readAsDataURL(f);
      });

      list.appendChild(row);
    });

    window.scrollTo({ top: savedY, behavior: "instant" });
    requestAnimationFrame(() => {
      window.scrollTo({ top: savedY, behavior: "instant" });
      list.style.minHeight = "";
    });
  }

  function _renderV2SoundPlayer(containerId, audioUrl, emptyText) {
    const wrap = $(containerId);
    if (!wrap) return;
    wrap.innerHTML = "";
    if (audioUrl) {
      const aud = document.createElement("audio");
      aud.controls = true;
      aud.preload = "none";
      aud.src = audioUrl + (audioUrl.includes("?") ? "&" : "?") + "t=" + Date.now();
      aud.style.cssText = "width:100%;height:32px";
      wrap.appendChild(aud);
      return aud;
    }
    wrap.textContent = emptyText;
    return null;
  }

  function setV2SoundStatus(msg, isErr) {
    const el = $("v2SoundStatus");
    if (!el) return;
    el.textContent = msg || "";
    el.style.color = isErr ? "#f87171" : "#34d399";
  }

  async function loadV2SoundDesign() {
    const selProj = $("proj");
    const slug = selProj ? (selProj.value || "").trim() : "";
    if (!slug) return;
    try {
      const data = await callApi(`/api/v2_sound_design?project=${encodeURIComponent(slug)}`);
      v2SoundState.project = slug;
      v2SoundState.sfx_mode = data.sfx_mode || "hybrid";
      v2SoundState.scenes = data.scenes || [];
      renderV2SoundModeUI();
      renderV2SoundScenesList();
      const f = data.foley || {};
      const s = data.score || {};
      if ($("v2FoleyPrompt")) $("v2FoleyPrompt").value = f.prompt || "";
      if ($("v2FoleyPreset") && f.preset) $("v2FoleyPreset").value = f.preset;
      if ($("v2FoleyDuration") && f.duration) $("v2FoleyDuration").value = String(f.duration);
      if ($("v2ScorePrompt")) $("v2ScorePrompt").value = s.prompt || "";
      if ($("v2ScoreMood") && s.mood) $("v2ScoreMood").value = s.mood;
      if ($("v2ScoreDuration") && s.duration) $("v2ScoreDuration").value = String(s.duration);

      const bF = $("v2FoleyStatusBadge");
      if (bF) {
        bF.textContent = f.has_audio ? "✓ Rendered" : "Ready";
        bF.className = "status-badge " + (f.has_audio ? "status-badge--synced" : "");
      }
      const bS = $("v2ScoreStatusBadge");
      if (bS) {
        bS.textContent = s.has_audio ? "✓ Rendered" : "Ready";
        bS.className = "status-badge " + (s.has_audio ? "status-badge--synced" : "");
      }
      _renderV2SoundPlayer("v2FoleyPlayerWrap", f.has_audio ? f.audio_url : "", "Not rendered yet — click ✨ Generate & Preview Foley");
      _renderV2SoundPlayer("v2ScorePlayerWrap", s.has_audio ? s.audio_url : "", "Not rendered yet — click ✨ Generate & Preview Score");
    } catch (e) {
      setV2SoundStatus("Could not load sound plan: " + (e.message || e), true);
    }
  }

  function initV2SoundDesign() {
    const btnFoley = $("bV2RenderFoley");
    const btnScore = $("bV2RenderScore");
    const btnSave = $("bV2SaveSoundPlan");
    const btnReload = $("bV2ReloadSoundPlan");
    const btnUpFoley = $("bV2UploadFoley");
    const inUpFoley = $("v2UploadFoleyInput");
    const btnUpScore = $("bV2UploadScore");
    const inUpScore = $("v2UploadScoreInput");

    const getSlug = () => ($("proj")?.value || "").trim();

    document.querySelectorAll("#v2SoundModeBar .v2-sound-mode-card").forEach(card => {
      card.addEventListener("click", async () => {
        const mode = card.dataset.mode;
        if (!mode) return;
        v2SoundState.sfx_mode = mode;
        renderV2SoundModeUI();
        const names = {
          hybrid: "✨ Hybrid (Video-Aligned Shot SFX + Scene Cues)",
          video_aligned: "🎬 Video-Aligned Native SFX (Step 18 Auto)",
          scene_cues: "🎚️ Scene-by-Scene Custom SFX & Score Cues",
        };
        setV2SoundStatus(`Selected sound strategy: ${names[mode] || mode}`);
        const slug = getSlug();
        if (slug) {
          try { await callApi("/api/v2_sound_design_save", { project: slug, sfx_mode: mode }); } catch (e) {}
        }
      });
    });

    const FOLEY_PRESET_PROMPTS = {
      space_adventure: "Starship bridge hum, cockpit console telemetry chimes, and clean sci-fi instrumentation.",
      rainy_home: "Steady rain pattering on a living room window, individual droplets on glass, and soft distant thunder.",
      cosmic_storm: "Sweeping atmospheric wind gusts, sparkling ice-ring crystal chimes, and deep planetary resonance.",
      action_launch: "Building rocket engine roar, heavy sub-bass ignition rumble, and rising thruster turbine whine.",
      forest_nature: "Gentle evening breeze with rhythmic distant night crickets and quiet outdoor air.",
    };
    const selFoleyPreset = $("v2FoleyPreset");
    if (selFoleyPreset) {
      selFoleyPreset.addEventListener("change", () => {
        const p = FOLEY_PRESET_PROMPTS[selFoleyPreset.value];
        if (p && $("v2FoleyPrompt")) $("v2FoleyPrompt").value = p;
      });
    }

    const SCORE_MOOD_PROMPTS = {
      wonder: "Sweeping cinematic orchestral strings, warm French horns, and sparkling celesta arpeggios in major key.",
      epic: "Driving 120 BPM pulsing bass ostinato, bold heroic brass fifths, and deep booming timpani drums.",
      cozy: "Gentle 3/4 family waltz with warm Rhodes electric piano chords, soft bass, and delicate music-box twinkles.",
      mysterious: "Dark minor-key cosmic synth drone, eerie glass-harmonica shimmer, and sparse echoing metallic bells.",
      playful: "Bouncy 145 BPM pizzicato strings and cheerful staccato xylophone & glockenspiel adventure melody.",
    };
    const selScoreMood = $("v2ScoreMood");
    if (selScoreMood) {
      selScoreMood.addEventListener("change", () => {
        const p = SCORE_MOOD_PROMPTS[selScoreMood.value];
        if (p && $("v2ScorePrompt")) $("v2ScorePrompt").value = p;
      });
    }

    if (btnFoley) {
      btnFoley.addEventListener("click", async () => {
        const slug = getSlug();
        if (!slug) { setV2SoundStatus("Select a book in Step 01 first.", true); return; }
        const stopBusy = startBusyFeedback(btnFoley, $("v2FoleyCard"), "Generating Foley (SFX) track…");
        setV2SoundStatus("Generating Foley (SFX) track…");
        try {
          const res = await callApi("/api/v2_sound_design_render", {
            project: slug,
            kind: "foley",
            prompt: ($("v2FoleyPrompt")?.value || "").trim(),
            preset: $("v2FoleyPreset")?.value || "space_adventure",
            duration: parseInt($("v2FoleyDuration")?.value || "12", 10) || 12,
          });
          const aud = _renderV2SoundPlayer("v2FoleyPlayerWrap", res.audio_url, "");
          const bF = $("v2FoleyStatusBadge");
          if (bF) { bF.textContent = "✓ Rendered"; bF.className = "status-badge status-badge--synced"; }
          setV2SoundStatus(`✓ Generated ${res.duration || 12}s Foley track!`);
          if (aud) aud.play().catch(() => {});
        } catch (err) {
          setV2SoundStatus("Foley render failed: " + (err.message || err), true);
        } finally {
          stopBusy();
        }
      });
    }

    if (btnScore) {
      btnScore.addEventListener("click", async () => {
        const slug = getSlug();
        if (!slug) { setV2SoundStatus("Select a book in Step 01 first.", true); return; }
        const stopBusy = startBusyFeedback(btnScore, $("v2ScoreCard"), "Generating Cinematic Score…");
        setV2SoundStatus("Generating Cinematic Score track…");
        try {
          const res = await callApi("/api/v2_sound_design_render", {
            project: slug,
            kind: "score",
            prompt: ($("v2ScorePrompt")?.value || "").trim(),
            mood: $("v2ScoreMood")?.value || "wonder",
            duration: parseInt($("v2ScoreDuration")?.value || "12", 10) || 12,
          });
          const aud = _renderV2SoundPlayer("v2ScorePlayerWrap", res.audio_url, "");
          const bS = $("v2ScoreStatusBadge");
          if (bS) { bS.textContent = "✓ Rendered"; bS.className = "status-badge status-badge--synced"; }
          setV2SoundStatus(`✓ Generated ${res.duration || 12}s Cinematic Score!`);
          if (aud) aud.play().catch(() => {});
        } catch (err) {
          setV2SoundStatus("Score render failed: " + (err.message || err), true);
        } finally {
          stopBusy();
        }
      });
    }

    const bindUpload = (btn, input, kind, cardId, wrapId, badgeId) => {
      if (!btn || !input) return;
      btn.addEventListener("click", () => input.click());
      input.addEventListener("change", () => {
        const f = input.files && input.files[0];
        const slug = getSlug();
        if (!f || !slug) return;
        const reader = new FileReader();
        reader.onload = async () => {
          const stopBusy = startBusyFeedback(btn, $(cardId), `Uploading ${f.name}…`);
          setV2SoundStatus(`Uploading custom ${kind} "${f.name}"…`);
          try {
            const res = await callApi("/api/v2_sound_design_render", {
              project: slug,
              kind,
              filename: f.name,
              audio_base64: reader.result,
            });
            const aud = _renderV2SoundPlayer(wrapId, res.audio_url, "");
            const b = $(badgeId);
            if (b) { b.textContent = "✓ Custom Track"; b.className = "status-badge status-badge--synced"; }
            setV2SoundStatus(`✓ Uploaded "${f.name}" for ${kind}.`);
            if (aud) aud.play().catch(() => {});
          } catch (err) {
            setV2SoundStatus("Upload failed: " + (err.message || err), true);
          } finally {
            stopBusy();
          }
        };
        reader.readAsDataURL(f);
      });
    };
    bindUpload(btnUpFoley, inUpFoley, "foley", "v2FoleyCard", "v2FoleyPlayerWrap", "v2FoleyStatusBadge");
    bindUpload(btnUpScore, inUpScore, "score", "v2ScoreCard", "v2ScorePlayerWrap", "v2ScoreStatusBadge");

    if (btnSave) {
      btnSave.addEventListener("click", async () => {
        const slug = getSlug();
        if (!slug) return;
        setV2SoundStatus("Saving sound plan…");
        try {
          const scenesPayload = {};
          document.querySelectorAll("#v2SoundScenesList .v2-sound-scene-row").forEach(row => {
            const sid = row.dataset.sceneId;
            if (!sid) return;
            scenesPayload[sid] = {
              sfx_cue: (row.querySelector(".v2-sc-sfx-cue")?.value || "").trim(),
              sfx_preset: row.querySelector(".v2-sc-sfx-preset")?.value || "space_adventure",
              score_mood: row.querySelector(".v2-sc-score-mood")?.value || "wonder",
            };
          });
          await callApi("/api/v2_sound_design_save", {
            project: slug,
            sfx_mode: v2SoundState.sfx_mode || "hybrid",
            foley: {
              prompt: ($("v2FoleyPrompt")?.value || "").trim(),
              preset: $("v2FoleyPreset")?.value || "space_adventure",
              duration: parseInt($("v2FoleyDuration")?.value || "12", 10) || 12,
            },
            score: {
              prompt: ($("v2ScorePrompt")?.value || "").trim(),
              mood: $("v2ScoreMood")?.value || "wonder",
              duration: parseInt($("v2ScoreDuration")?.value || "12", 10) || 12,
            },
            scenes: scenesPayload,
          });
          setV2SoundStatus("✓ Saved Step 16 sound strategy, master tracks, and all scene cues.");
          const scorePrompt = ($("v2ScorePrompt")?.value || "").trim();
          if (scorePrompt) {
            proposeUpstreamSync({
              project: slug,
              kind: "score_to_continuity",
              affectedStepNums: [7],
              title: "🔄 Sync Score Theme Back to Step 07 (Continuity Book)?",
              message: `You updated the film's musical score in Step 16.\n\nWould you like to update Step 07 (Continuity Book music theme) to match?`,
              payload: { music_theme: scorePrompt },
              onSynced: () => setV2SoundStatus("✓ Saved Step 16 sound plan & synced music theme back to Step 07."),
            });
          }
        } catch (err) {
          setV2SoundStatus("Save failed: " + (err.message || err), true);
        }
      });
    }
    if (btnReload) btnReload.addEventListener("click", () => loadV2SoundDesign());
  }

  // ===== STEP 17: STORYBOARD KEYFRAMES =====
  let v2KfState = { project: "", scenes: [], activeSceneId: "", look: "", total_shots: 0, rendered_shots: 0 };

  function setV2KfStatus(msg, isErr) {
    const el = $("v2KfStatus");
    if (!el) return;
    el.textContent = msg || "";
    el.style.color = isErr ? "#f87171" : "#34d399";
  }

  function renderV2KfScenesBar() {
    const bar = $("v2KfScenes");
    if (!bar) return;
    bar.innerHTML = "";
    (v2KfState.scenes || []).forEach(sc => {
      const isAct = sc.id === v2KfState.activeSceneId;
      const done = (sc.shots || []).filter(s => s.has_image).length;
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "btn " + (isAct ? "btn--primary" : "btn--ghost");
      btn.style.cssText = "white-space:nowrap;padding:5px 12px;font-size:var(--text-xs)";
      btn.textContent = `${sc.id} (${done}/${(sc.shots || []).length})`;
      btn.title = sc.heading || sc.id;
      btn.addEventListener("click", () => {
        v2KfState.activeSceneId = sc.id;
        renderV2KfScenesBar();
        renderV2KfGrid();
      });
      bar.appendChild(btn);
    });
  }

  async function renderSingleKeyframe(shot, promptText, triggerBtn, cardEl) {
    const stopBusy = startBusyFeedback(triggerBtn, cardEl, `Generating keyframe ${shot.id}…`);
    setV2KfStatus(`Generating 16:9 keyframe for ${shot.id}…`);
    try {
      const res = await callApi("/api/v2_keyframe_render", {
        project: v2KfState.project,
        id: shot.id,
        prompt: promptText,
        aspect_ratio: "16:9",
      });
      shot.prompt = promptText;
      if (!shot.has_image) v2KfState.rendered_shots++;
      shot.has_image = true;
      shot.image_url = res.image_url + "?t=" + Date.now();
      if (res.physics_passed === false && res.physics_issues && res.physics_issues.length) {
        shot.needs_attention = true;
        shot.attention_reason = "Physics QA flagged: " + res.physics_issues.join("; ");
      } else {
        shot.needs_attention = false;
        shot.attention_reason = "";
      }
      renderV2KfScenesBar();
      renderV2KfGrid();
      const physTag = res.physics_repaired
        ? (res.physics_passed ? " · ✓ Physics auto-repaired" : " · ⚠️ Physics flagged (see card)")
        : (res.physics_passed === false ? " · ⚠️ Physics flagged (see card)" : " · ✓ Physics verified");
      setV2KfStatus(`✓ Rendered keyframe ${shot.id} (${res.model || "image"})${physTag}`, res.physics_passed === false);
    } catch (err) {
      setV2KfStatus(`Keyframe ${shot.id} failed: ` + (err.message || err), true);
    } finally {
      stopBusy();
    }
  }

  function renderV2KfGrid() {
    const grid = $("v2KfGrid");
    const summary = $("v2KfSummary");
    const badge = $("v2KfBadge");
    if (!grid) return;

    const savedY = window.scrollY || 0;
    const prevH = grid.offsetHeight;
    if (prevH > 0) grid.style.minHeight = prevH + "px";
    grid.innerHTML = "";

    const sc = (v2KfState.scenes || []).find(s => s.id === v2KfState.activeSceneId) || (v2KfState.scenes || [])[0];
    if (summary) {
      summary.textContent = v2KfState.total_shots
        ? `${v2KfState.scenes.length} scenes · ${v2KfState.total_shots} total shots · ${v2KfState.rendered_shots} keyframes rendered` + (sc ? ` · Viewing ${sc.id}: ${sc.heading}` : "")
        : "No shots found yet. Generate your Shot List in Step 12 first.";
    }
    if (badge) {
      badge.textContent = v2KfState.rendered_shots > 0
        ? `✓ ${v2KfState.rendered_shots}/${v2KfState.total_shots} Rendered`
        : `${v2KfState.total_shots} Shots Ready`;
    }

    if (!sc || !(sc.shots || []).length) {
      const empty = document.createElement("div");
      empty.className = "direct-story-card";
      empty.style.cssText = "grid-column:1/-1;color:#94a3b8";
      empty.textContent = "No shots in this scene yet.";
      grid.appendChild(empty);
      grid.style.minHeight = "";
      return;
    }

    sc.shots.forEach(shot => {
      const card = document.createElement("div");
      card.className = "deliverable-card v2-kf-card";
      card.dataset.shotId = shot.id;
      if (shot.needs_attention) {
        flagNeedsAttention(card, shot.attention_reason || "Specify exact character wardrobe/colors in Step 08");
      }

      // 16:9 Preview Box
      const preview = document.createElement("div");
      preview.style.cssText = "background:#000;aspect-ratio:16/9;border-radius:6px;overflow:hidden;display:flex;align-items:center;justify-content:center;color:#64748b;position:relative;border:1px solid #1e293b";
      if (shot.has_image && shot.image_url) {
        const img = document.createElement("img");
        img.src = shot.image_url;
        img.alt = `Keyframe ${shot.id}`;
        img.style.cssText = "width:100%;height:100%;object-fit:cover;cursor:zoom-in;display:block";
        img.title = "Click to view full-size keyframe";
        img.addEventListener("click", () => window.open(shot.image_url, "_blank"));
        preview.appendChild(img);
        if (shot.locked) {
          const lbadge = document.createElement("span");
          lbadge.style.cssText = "position:absolute;top:6px;right:6px;padding:2px 8px;border-radius:999px;background:rgba(16,185,129,0.92);color:#022c22;font-size:11px;font-weight:700;";
          lbadge.textContent = "🔒 Locked";
          preview.appendChild(lbadge);
          card.style.borderColor = "#10b981";
        }
      } else {
        const ph = document.createElement("span");
        ph.style.cssText = "font-size:var(--text-xs);padding:12px;text-align:center";
        ph.textContent = `[${shot.id} · ${shot.type} · Not rendered yet]`;
        preview.appendChild(ph);
      }
      card.appendChild(preview);

      // Title + Shot specs
      const title = document.createElement("strong");
      title.style.cssText = "color:#f59e0b;margin-top:6px;font-size:var(--text-sm)";
      title.textContent = `${shot.id} · ${shot.type} · ${shot.lens_mm}mm · ${shot.movement} (${shot.seconds}s)`;
      card.appendChild(title);

      // Editable visual prompt
      const ta = document.createElement("textarea");
      ta.className = "v2-kf-prompt";
      ta.rows = 3;
      ta.value = shot.prompt || "";
      ta.style.cssText = "width:100%;padding:6px 8px;background:#0a0d14;color:#e2e8f0;border:1px solid #334155;border-radius:4px;font-size:11px;resize:vertical;margin-top:4px";
      card.appendChild(ta);

      // Action buttons
      const row = document.createElement("div");
      row.style.cssText = "display:flex;gap:6px;flex-wrap:wrap;margin-top:6px";

      const btnGen = document.createElement("button");
      btnGen.type = "button";
      btnGen.className = "btn " + (shot.has_image ? "btn--secondary" : "btn--primary");
      btnGen.style.cssText = "padding:4px 10px;font-size:var(--text-xs);flex:1";
      btnGen.textContent = shot.locked ? "🔒 Locked" : (shot.has_image ? "↺ Re-roll" : "✨ Generate Keyframe");
      btnGen.disabled = Boolean(shot.locked);
      btnGen.addEventListener("click", () => renderSingleKeyframe(shot, ta.value.trim(), btnGen, card));

      const upIn = document.createElement("input");
      upIn.type = "file";
      upIn.accept = "image/*";
      upIn.style.display = "none";
      upIn.addEventListener("change", () => {
        const f = upIn.files && upIn.files[0];
        if (!f) return;
        const reader = new FileReader();
        reader.onload = async () => {
          const stopBusy = startBusyFeedback(btnUp, card, `Uploading ${f.name}…`);
          try {
            const res = await callApi("/api/v2_keyframe_render", {
              project: v2KfState.project,
              id: shot.id,
              prompt: ta.value.trim(),
              image_base64: reader.result,
            });
            if (!shot.has_image) v2KfState.rendered_shots++;
            shot.has_image = true;
            shot.image_url = res.image_url + "?t=" + Date.now();
            renderV2KfScenesBar();
            renderV2KfGrid();
            setV2KfStatus(`✓ Uploaded custom keyframe "${f.name}" for ${shot.id}.`);
          } catch (err) {
            setV2KfStatus("Upload failed: " + (err.message || err), true);
          } finally {
            stopBusy();
          }
        };
        reader.readAsDataURL(f);
      });

      const btnUp = document.createElement("button");
      btnUp.type = "button";
      btnUp.className = "btn btn--ghost";
      btnUp.style.cssText = "padding:4px 8px;font-size:var(--text-xs)";
      btnUp.textContent = "⬆ Upload";
      btnUp.disabled = Boolean(shot.locked);
      btnUp.addEventListener("click", () => upIn.click());

      row.appendChild(btnGen);
      row.appendChild(btnUp);

      if (shot.has_image) {
        const btnLock = document.createElement("button");
        btnLock.type = "button";
        btnLock.className = "btn " + (shot.locked ? "btn--primary" : "btn--ghost");
        btnLock.style.cssText = "padding:4px 8px;font-size:var(--text-xs)";
        btnLock.textContent = shot.locked ? "🔓 Unlock" : "🔒 Lock";
        btnLock.title = shot.locked ? `Unlock ${shot.id} so it can be re-rolled or deleted` : `Lock ${shot.id} to prevent accidental overwrite or deletion`;
        btnLock.addEventListener("click", async () => {
          const nextLock = !shot.locked;
          const stopBusy = nextLock ? startBusyFeedback(btnLock, card, `Locking ${shot.id} & cascading modifications into prompt…`) : () => {};
          try {
            const boxEdits = [...card.querySelectorAll(".v2-kf-mod-input")]
              .map(inp => (inp.value || "").trim())
              .filter(Boolean);
            const res = await callApi("/api/v2_keyframe_lock", {
              project: v2KfState.project,
              id: shot.id,
              locked: nextLock,
              prompt: ta.value.trim(),
              edits: boxEdits,
            });
            shot.locked = nextLock;
            if (res.updated_prompt) {
              shot.prompt = res.updated_prompt;
            }
            if (nextLock) {
              shot.pending_edits = [];
            }
            renderV2KfGrid();
            setV2KfStatus(
              nextLock
                ? (res.updated_prompt ? `🔒 Locked ${shot.id}, updated prompt from cascade, and cleared modification boxes!` : `🔒 Locked keyframe ${shot.id}.`)
                : `🔓 Unlocked keyframe ${shot.id}.`
            );
            if (nextLock && res.updated_prompt) {
              proposeUpstreamSync({
                project: v2KfState.project,
                kind: "keyframe_to_shotlist",
                affectedStepNums: [12],
                title: `🔄 Sync Locked ${shot.id} Prompt Back to Step 12?`,
                message: `Your cascaded modifications to ${shot.id} were merged into its prompt when locked.\n\nUpdate Step 12 (Shot List) to match?`,
                payload: { prompts: { [shot.id]: res.updated_prompt } },
              });
            }
          } catch (err) {
            setV2KfStatus("Lock toggle failed: " + (err.message || err), true);
          } finally {
            stopBusy();
          }
        });
        row.appendChild(btnLock);

        if (!shot.locked) {
          const btnDel = document.createElement("button");
          btnDel.type = "button";
          btnDel.className = "btn btn--ghost";
          btnDel.style.cssText = "padding:4px 8px;font-size:var(--text-xs);color:#f87171";
          btnDel.textContent = "🗑️";
          btnDel.title = `Delete keyframe ${shot.id} so it cannot be used as a reference`;
          btnDel.addEventListener("click", async () => {
            const ok = await showInstallApprovalModal(
              `Delete keyframe ${shot.id}?`,
              `This removes the generated image for ${shot.id} so it will NOT be used as a continuity reference for subsequent shots.\n\nClick OK to delete, or Cancel to keep it.`
            );
            if (!ok) return;
            try {
              await callApi("/api/v2_keyframe_delete", { project: v2KfState.project, id: shot.id });
              if (shot.has_image) v2KfState.rendered_shots = Math.max(0, v2KfState.rendered_shots - 1);
              shot.has_image = false;
              shot.image_url = "";
              renderV2KfScenesBar();
              renderV2KfGrid();
              setV2KfStatus(`✓ Deleted keyframe ${shot.id}.`);
            } catch (err) {
              setV2KfStatus("Delete failed: " + (err.message || err), true);
            }
          });
          row.appendChild(btnDel);
        }
      }

      row.appendChild(upIn);
      card.appendChild(row);

      // Separate Cascading Modification Boxes (clears automatically when 🔒 Lock is pushed)
      if (shot.has_image && !shot.locked) {
        const modBox = document.createElement("div");
        modBox.style.cssText = "margin-top:8px;padding:8px;background:#0a0d14;border:1px solid #232d3f;border-radius:6px;display:flex;flex-direction:column;gap:6px;";

        const modHdr = document.createElement("div");
        modHdr.style.cssText = "display:flex;justify-content:space-between;align-items:center;gap:6px;";
        const modTitle = document.createElement("span");
        modTitle.style.cssText = "font-size:11px;font-weight:700;color:#fde68a;";
        modTitle.textContent = "✏️ Modification Cascade (clears on Lock)";
        const btnAddMod = document.createElement("button");
        btnAddMod.type = "button";
        btnAddMod.className = "btn btn--ghost";
        btnAddMod.style.cssText = "padding:2px 7px;font-size:11px;";
        btnAddMod.textContent = "+ Add Box";
        modHdr.appendChild(modTitle);
        modHdr.appendChild(btnAddMod);
        modBox.appendChild(modHdr);

        const modList = document.createElement("div");
        modList.style.cssText = "display:flex;flex-direction:column;gap:5px;";

        const syncLocalEdits = () => {
          shot.pending_edits = [...modList.querySelectorAll(".v2-kf-mod-input")].map(i => i.value);
        };

        const addModRow = (val = "") => {
          const r = document.createElement("div");
          r.style.cssText = "display:flex;gap:5px;align-items:center;";
          const idxTag = document.createElement("span");
          idxTag.style.cssText = "font-size:10px;color:#94a3b8;min-width:16px;";
          idxTag.textContent = `${modList.children.length + 1}.`;
          const inp = document.createElement("input");
          inp.type = "text";
          inp.className = "v2-kf-mod-input";
          inp.value = val;
          inp.placeholder = "Describe one tweak (e.g. move tail onto rug, warm light)…";
          inp.style.cssText = "flex:1;min-width:0;padding:5px 7px;background:#0f172a;color:#fde68a;border:1px solid #475569;border-radius:4px;font-size:11px;box-sizing:border-box;";
          inp.addEventListener("input", syncLocalEdits);
          const bRm = document.createElement("button");
          bRm.type = "button";
          bRm.className = "btn btn--ghost";
          bRm.style.cssText = "padding:2px 6px;font-size:11px;color:#f87171;";
          bRm.textContent = "✕";
          bRm.addEventListener("click", () => {
            r.remove();
            [...modList.children].forEach((rowEl, i) => {
              const tag = rowEl.querySelector("span");
              if (tag) tag.textContent = `${i + 1}.`;
            });
            syncLocalEdits();
          });
          r.appendChild(idxTag);
          r.appendChild(inp);
          r.appendChild(bRm);
          modList.appendChild(r);
        };

        const initEdits = (Array.isArray(shot.pending_edits) && shot.pending_edits.length) ? shot.pending_edits : [""];
        initEdits.forEach(txt => addModRow(txt));
        btnAddMod.addEventListener("click", () => addModRow(""));
        modBox.appendChild(modList);

        const modFoot = document.createElement("div");
        modFoot.style.cssText = "display:flex;justify-content:flex-end;gap:6px;";
        const btnApplyCascade = document.createElement("button");
        btnApplyCascade.type = "button";
        btnApplyCascade.className = "btn btn--secondary";
        btnApplyCascade.style.cssText = "padding:4px 10px;font-size:11px;";
        btnApplyCascade.textContent = "✨ Apply Modifications";
        btnApplyCascade.addEventListener("click", async () => {
          const edits = [...modList.querySelectorAll(".v2-kf-mod-input")]
            .map(i => (i.value || "").trim())
            .filter(Boolean);
          if (!edits.length) {
            const first = modList.querySelector(".v2-kf-mod-input");
            if (first) first.focus();
            return;
          }
          const stopBusy = startBusyFeedback(btnApplyCascade, card, `Applying ${edits.length} modification(s) to ${shot.id}…`);
          setV2KfStatus(`Applying ${edits.length} cascaded modification(s) to ${shot.id}…`);
          try {
            const res = await callApi("/api/v2_keyframe_edit", {
              project: v2KfState.project,
              id: shot.id,
              edits,
              prompt: ta.value.trim(),
            });
            shot.image_url = res.image_url + "?t=" + Date.now();
            shot.pending_edits = res.pending_edits || edits;
            if (res.physics_passed === false && res.physics_issues && res.physics_issues.length) {
              shot.needs_attention = true;
              shot.attention_reason = "Physics QA flagged: " + res.physics_issues.join("; ");
            } else {
              shot.needs_attention = false;
              shot.attention_reason = "";
            }
            renderV2KfGrid();
            setV2KfStatus(`✓ Applied ${edits.length} modification(s) to ${shot.id}. Click 🔒 Lock when happy to update the prompt & clear boxes.`);
          } catch (err) {
            setV2KfStatus(`Modify ${shot.id} failed: ` + (err.message || err), true);
          } finally {
            stopBusy();
          }
        });
        modFoot.appendChild(btnApplyCascade);
        modBox.appendChild(modFoot);
        card.appendChild(modBox);
      }

      grid.appendChild(card);
    });

    window.scrollTo({ top: savedY, behavior: "instant" });
    requestAnimationFrame(() => {
      window.scrollTo({ top: savedY, behavior: "instant" });
      grid.style.minHeight = "";
    });
  }

  async function loadV2Keyframes() {
    const selProj = $("proj");
    const slug = selProj ? (selProj.value || "").trim() : "";
    const summary = $("v2KfSummary");
    const grid = $("v2KfGrid");
    if (!grid) return;
    if (!slug) {
      if (summary) summary.textContent = "Select a book in Step 01 first.";
      grid.innerHTML = "";
      return;
    }
    if (summary) summary.textContent = "Loading scenes & shots…";
    try {
      const data = await callApi(`/api/v2_keyframes?project=${encodeURIComponent(slug)}`);
      v2KfState.project = slug;
      v2KfState.scenes = data.scenes || [];
      v2KfState.look = data.look || "";
      v2KfState.total_shots = data.total_shots || 0;
      v2KfState.rendered_shots = data.rendered_shots || 0;
      if (!v2KfState.activeSceneId || !v2KfState.scenes.some(s => s.id === v2KfState.activeSceneId)) {
        v2KfState.activeSceneId = (v2KfState.scenes[0] && v2KfState.scenes[0].id) || "";
      }
      renderV2KfScenesBar();
      renderV2KfGrid();
    } catch (e) {
      setV2KfStatus("Could not load keyframes: " + (e.message || e), true);
    }
  }

  function initV2Keyframes() {
    const btnReload = $("bV2KfReload");
    const btnRenderScene = $("bV2KfRenderScene");
    const btnSavePrompts = $("bV2KfSavePrompts");
    const btnRebuildPrompts = $("bV2KfRebuildPrompts");
    if (btnReload) btnReload.addEventListener("click", () => loadV2Keyframes());
    if (btnRebuildPrompts) {
      btnRebuildPrompts.addEventListener("click", async () => {
        const sc = (v2KfState.scenes || []).find(s => s.id === v2KfState.activeSceneId);
        if (!sc) return;
        await loadV2Keyframes();
        const freshSc = (v2KfState.scenes || []).find(s => s.id === sc.id);
        if (!freshSc) return;
        const prompts = {};
        (freshSc.shots || []).forEach(sh => {
          if (sh.default_prompt) {
            sh.prompt = sh.default_prompt;
            prompts[sh.id] = sh.default_prompt;
          }
        });
        renderV2KfGrid();
        try {
          await callApi("/api/v2_keyframe_prompts_save", { project: v2KfState.project, prompts });
          setV2KfStatus(`✓ Synced ${Object.keys(prompts).length} prompts in ${sc.id} with latest locked wardrobes & locations.`);
        } catch (err) {
          setV2KfStatus("Sync failed: " + (err.message || err), true);
        }
      });
    }
    if (btnSavePrompts) {
      btnSavePrompts.addEventListener("click", async () => {
        const sc = (v2KfState.scenes || []).find(s => s.id === v2KfState.activeSceneId);
        if (!sc || !v2KfState.project) return;
        const prompts = {};
        document.querySelectorAll("#v2KfGrid .v2-kf-card").forEach(cardEl => {
          const sid = cardEl.dataset.shotId;
          const val = (cardEl.querySelector(".v2-kf-prompt")?.value || "").trim();
          if (sid) {
            prompts[sid] = val;
            const sh = (sc.shots || []).find(x => x.id === sid);
            if (sh) sh.prompt = val;
          }
        });
        setV2KfStatus(`Saving prompts for ${sc.id}…`);
        try {
          const res = await callApi("/api/v2_keyframe_prompts_save", { project: v2KfState.project, prompts });
          setV2KfStatus(`✓ Saved ${res.saved || Object.keys(prompts).length} prompt(s) for ${sc.id} (no images re-rendered).`);
          proposeUpstreamSync({
            project: v2KfState.project,
            kind: "keyframe_to_shotlist",
            affectedStepNums: [12],
            title: `🔄 Sync ${sc.id} Prompt Edits Back to Step 12 (Shot List)?`,
            message: `You edited keyframe shot description(s) in Step 17 for ${sc.id}.\n\nWould you like to update Step 12 (Shot List) so the shot descriptions match?`,
            payload: { prompts },
            onSynced: () => setV2KfStatus(`✓ Saved prompts & synced ${sc.id} back to Step 12 (Shot List).`),
          });
        } catch (err) {
          setV2KfStatus("Could not save prompts: " + (err.message || err), true);
        }
      });
    }
    if (btnRenderScene) {
      btnRenderScene.addEventListener("click", async () => {
        const sc = (v2KfState.scenes || []).find(s => s.id === v2KfState.activeSceneId);
        if (!sc || !(sc.shots || []).length) return;
        const skipDone = Boolean($("v2KfSkipRendered")?.checked);
        const targets = sc.shots.filter(s => !s.locked && (!skipDone || !s.has_image));
        if (!targets.length) {
          setV2KfStatus(`All ${sc.shots.length} shots in ${sc.id} already have keyframes! Uncheck "Skip already rendered" or click ↺ Re-roll on a specific shot.`);
          return;
        }
        const cards = targets
          .map(s => document.querySelector(`#v2KfGrid .v2-kf-card[data-shot-id="${s.id}"]`))
          .filter(Boolean);
        const stopBusy = startBusyFeedback(btnRenderScene, cards, `Generating ${targets.length} keyframe(s) for ${sc.id}…`);
        let okCount = 0;
        try {
          for (const shot of targets) {
            const cardEl = document.querySelector(`#v2KfGrid .v2-kf-card[data-shot-id="${shot.id}"]`);
            const promptText = (cardEl?.querySelector(".v2-kf-prompt")?.value || shot.prompt || "").trim();
            setV2KfStatus(`Generating ${shot.id} (${okCount + 1}/${targets.length})…`);
            try {
              const res = await callApi("/api/v2_keyframe_render", {
                project: v2KfState.project,
                id: shot.id,
                prompt: promptText,
                aspect_ratio: "16:9",
              });
              shot.prompt = promptText;
              if (!shot.has_image) v2KfState.rendered_shots++;
              shot.has_image = true;
              shot.image_url = res.image_url + "?t=" + Date.now();
              okCount++;
              renderV2KfScenesBar();
              renderV2KfGrid();
            } catch (err) {
              setV2KfStatus(`Stopped at ${shot.id}: ` + (err.message || err), true);
              break;
            }
          }
          if (okCount > 0) setV2KfStatus(`✓ Rendered ${okCount}/${targets.length} keyframe(s) for ${sc.id}!`);
        } finally {
          stopBusy();
        }
      });
    }
    const selProj = $("proj");
    if (selProj) {
      selProj.addEventListener("change", () => {
        if (currentStep === 17) loadV2Keyframes();
      });
    }
  }

  // ===== STEP 10: LOOK DEVELOPMENT & TURNAROUNDS =====
  let v2TurnState = { project: "", look: "pixar_3d", characters: [] };

  function setV2TurnStatus(msg, isErr) {
    const el = $("v2TurnStatus");
    if (!el) return;
    el.textContent = msg || "";
    el.style.color = isErr ? "#f87171" : "#34d399";
  }

  function renderV2Turnarounds() {
    const list = $("v2TurnList");
    const summary = $("v2TurnSummary");
    const badge = $("v2TurnBadge");
    if (!list) return;
    const savedY = window.scrollY || 0;
    const prevH = list.offsetHeight;
    if (prevH > 0) list.style.minHeight = prevH + "px";
    list.innerHTML = "";

    const chars = [...(v2TurnState.characters || [])].sort((a, b) =>
      String(a.name || "").localeCompare(String(b.name || ""), undefined, { sensitivity: "base" })
    );
    let totalViews = 0, doneViews = 0;
    chars.forEach(c => {
      const outfits = (c.outfits && c.outfits.length) ? c.outfits : [{ id: "default", scenes: "All Scenes", location: "", wardrobe: c.desc || "", views: c.views || {} }];
      outfits.forEach(of => {
        totalViews += 3;
        doneViews += ["front", "three_quarter", "profile"].filter(v => of.views && of.views[v] && of.views[v].has_image).length;
      });
    });
    if (summary) {
      summary.textContent = chars.length
        ? `${chars.length} character(s) synced from Step 08 · ${doneViews}/${totalViews} turnaround views locked · Style: ${v2TurnState.look}`
        : "No characters found yet. Run Step 07 (Continuity) or Step 08 (Cast) first.";
    }
    if (badge) badge.textContent = doneViews > 0 ? `✓ ${doneViews}/${totalViews} Views` : `${chars.length} Characters`;

    const VIEWS = [
      ["front", "Front View"],
      ["three_quarter", "3/4 Angle"],
      ["profile", "Side Profile"],
    ];

    chars.forEach(c => {
      const card = document.createElement("div");
      card.className = "direct-story-card v2-turn-card";
      const outfits = (c.outfits && c.outfits.length) ? c.outfits : [{ id: "default", scenes: "All Scenes", location: "", wardrobe: c.desc || "", views: c.views || {} }];

      const hdr = document.createElement("div");
      hdr.style.cssText = "display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;margin-bottom:8px";
      const title = document.createElement("strong");
      title.style.color = "#f59e0b";
      title.textContent = c.name.toUpperCase() + (outfits.length > 1 ? ` · ${outfits.length} Wardrobe Changes` : "");
      hdr.appendChild(title);
      if (c.desc) {
        const desc = document.createElement("span");
        desc.style.cssText = "color:#94a3b8;font-size:var(--text-xs)";
        desc.textContent = c.desc.slice(0, 140);
        hdr.appendChild(desc);
      }
      card.appendChild(hdr);

      outfits.forEach((of, ofIdx) => {
        const sec = document.createElement("div");
        if (ofIdx > 0) sec.style.cssText = "margin-top:12px;padding-top:12px;border-top:1px solid #232d3f;";

        const ofHdr = document.createElement("div");
        ofHdr.style.cssText = "display:flex;align-items:center;flex-wrap:wrap;gap:6px;margin-bottom:8px;font-size:12px;";
        const pill = document.createElement("span");
        pill.style.cssText = "padding:2px 8px;border-radius:999px;background:rgba(245,158,11,0.14);border:1px solid rgba(245,158,11,0.45);color:#fde68a;font-weight:600;font-size:11px;";
        pill.textContent = `👗 ${of.scenes || "All Scenes"}` + (of.location ? ` · ${of.location}` : "");
        ofHdr.appendChild(pill);
        const wTxt = document.createElement("span");
        wTxt.style.cssText = "color:#e2e8f0;font-size:11px;flex:1;";
        wTxt.textContent = of.wardrobe || "No specific wardrobe set in Step 08 yet";
        ofHdr.appendChild(wTxt);

        if (of.id && of.id !== "default") {
          const btnDelOf = document.createElement("button");
          btnDelOf.type = "button";
          btnDelOf.className = "btn btn--ghost";
          btnDelOf.style.cssText = "padding:2px 8px;font-size:11px;color:#f87171;margin-left:auto;";
          btnDelOf.textContent = "🗑️ Delete Outfit";
          btnDelOf.title = `Delete this wardrobe change for ${c.name} (also removes it from Step 08)`;
          btnDelOf.addEventListener("click", async () => {
            const ok = await showInstallApprovalModal(
              `Delete "${of.scenes || "Outfit"}" for ${c.name}?`,
              `This will remove this wardrobe change ("${(of.wardrobe || "").slice(0, 80)}") from Step 10 AND Step 08 (Cast & Characters), and delete its generated turnaround images.\n\nClick OK to delete, or Cancel to keep it.`
            );
            if (!ok) return;
            setV2TurnStatus(`Deleting outfit ${of.scenes} for ${c.name}…`);
            try {
              await callApi("/api/v2_wardrobe_state_delete", {
                project: v2TurnState.project,
                character: c.name,
                outfit_index: ofIdx,
              });
              await loadV2Turnarounds();
              setV2TurnStatus(`✓ Deleted outfit "${of.scenes}" for ${c.name} (synced back to Step 08).`);
            } catch (err) {
              setV2TurnStatus("Could not delete outfit: " + (err.message || err), true);
            }
          });
          ofHdr.appendChild(btnDelOf);
        }
        sec.appendChild(ofHdr);

        const grid = document.createElement("div");
        grid.style.cssText = "display:grid;grid-template-columns:repeat(auto-fit, minmax(200px, 1fr));gap:10px";

        VIEWS.forEach(([vk, vlabel]) => {
          const vinfo = (of.views && of.views[vk]) || {};
          const box = document.createElement("div");
          box.style.cssText = "background:#0a0d14;border:1px solid #232d3f;border-radius:8px;padding:8px;display:flex;flex-direction:column;gap:6px";

          const imgBox = document.createElement("div");
          imgBox.style.cssText = "aspect-ratio:1/1;background:#020617;border-radius:6px;overflow:hidden;display:flex;align-items:center;justify-content:center;color:#64748b;font-size:11px;text-align:center;padding:6px";
          if (vinfo.has_image && vinfo.image_url) {
            const img = document.createElement("img");
            img.src = vinfo.image_url;
            img.alt = `${c.name} ${of.scenes} ${vlabel}`;
            img.style.cssText = "width:100%;height:100%;object-fit:cover;cursor:zoom-in";
            img.addEventListener("click", () => window.open(vinfo.image_url, "_blank"));
            imgBox.appendChild(img);
          } else {
            imgBox.textContent = `${c.name} · ${of.scenes} · ${vlabel}`;
          }
          box.appendChild(imgBox);

          const row = document.createElement("div");
          row.style.cssText = "display:flex;gap:6px";
          const btnGen = document.createElement("button");
          btnGen.type = "button";
          btnGen.className = "btn " + (vinfo.has_image ? "btn--secondary" : "btn--primary");
          btnGen.style.cssText = "flex:1;padding:4px 8px;font-size:11px";
          btnGen.textContent = vinfo.has_image ? `↺ Re-roll` : `✨ Generate ${vlabel}`;
          btnGen.addEventListener("click", async () => {
            const stopBusy = startBusyFeedback(btnGen, box, `Generating ${c.name} (${of.scenes} · ${vlabel})…`);
            setV2TurnStatus(`Generating ${vlabel} for ${c.name} (${of.scenes})…`);
            try {
              const res = await callApi("/api/v2_turnaround_render", {
                project: v2TurnState.project,
                character: c.name,
                outfit_id: of.id || "default",
                view: vk,
                desc: c.desc,
                wardrobe: of.wardrobe || "",
                look: v2TurnState.look,
              });
              of.views[vk] = { has_image: true, image_url: res.image_url + "?t=" + Date.now() };
              renderV2Turnarounds();
              setV2TurnStatus(`✓ Generated ${vlabel} for ${c.name} (${of.scenes})!`);
            } catch (err) {
              setV2TurnStatus("Turnaround failed: " + (err.message || err), true);
            } finally {
              stopBusy();
            }
          });

          const upIn = document.createElement("input");
          upIn.type = "file";
          upIn.accept = "image/*";
          upIn.style.display = "none";
          upIn.addEventListener("change", () => {
            const f = upIn.files && upIn.files[0];
            if (!f) return;
            const reader = new FileReader();
            reader.onload = async () => {
              const stopBusy = startBusyFeedback(btnUp, box, `Uploading ${f.name}…`);
              try {
                const res = await callApi("/api/v2_turnaround_render", {
                  project: v2TurnState.project,
                  character: c.name,
                  outfit_id: of.id || "default",
                  view: vk,
                  image_base64: reader.result,
                });
                of.views[vk] = { has_image: true, image_url: res.image_url + "?t=" + Date.now() };
                renderV2Turnarounds();
                setV2TurnStatus(`✓ Uploaded ${vlabel} reference for ${c.name} (${of.scenes}).`);
              } catch (err) {
                setV2TurnStatus("Upload failed: " + (err.message || err), true);
              } finally {
                stopBusy();
              }
            };
            reader.readAsDataURL(f);
          });
          const btnUp = document.createElement("button");
          btnUp.type = "button";
          btnUp.className = "btn btn--ghost";
          btnUp.style.cssText = "padding:4px 8px;font-size:11px";
          btnUp.textContent = "📷";
          btnUp.title = `Upload custom ${vlabel} reference photo for ${of.scenes}`;
          btnUp.addEventListener("click", () => upIn.click());

          row.appendChild(btnGen);
          row.appendChild(btnUp);
          if (vinfo.has_image) {
            const btnDelPic = document.createElement("button");
            btnDelPic.type = "button";
            btnDelPic.className = "btn btn--ghost";
            btnDelPic.style.cssText = "padding:4px 8px;font-size:11px;color:#f87171";
            btnDelPic.textContent = "🗑️";
            btnDelPic.title = `Delete this ${vlabel} picture so it will not be used as a reference`;
            btnDelPic.addEventListener("click", async () => {
              const ok = await showInstallApprovalModal(
                `Delete ${c.name}'s ${vlabel} picture?`,
                `This removes the ${vlabel} image for ${of.scenes || "this outfit"} so it will NOT be used as a visual reference for future turnarounds or keyframes.\n\nClick OK to delete, or Cancel to keep it.`
              );
              if (!ok) return;
              try {
                await callApi("/api/v2_turnaround_delete", {
                  project: v2TurnState.project,
                  character: c.name,
                  outfit_id: of.id || "default",
                  view: vk,
                });
                of.views[vk] = { has_image: false, image_url: "" };
                renderV2Turnarounds();
                setV2TurnStatus(`✓ Deleted ${vlabel} image for ${c.name} (${of.scenes}).`);
              } catch (err) {
                setV2TurnStatus("Could not delete image: " + (err.message || err), true);
              }
            });
            row.appendChild(btnDelPic);
          }
          row.appendChild(upIn);
          box.appendChild(row);
          grid.appendChild(box);
        });

        sec.appendChild(grid);
        card.appendChild(sec);
      });

      list.appendChild(card);
    });

    window.scrollTo({ top: savedY, behavior: "instant" });
    requestAnimationFrame(() => {
      window.scrollTo({ top: savedY, behavior: "instant" });
      list.style.minHeight = "";
    });
  }

  async function loadV2Turnarounds() {
    const slug = ($("proj")?.value || "").trim();
    if (!slug) return;
    try {
      const data = await callApi(`/api/v2_turnarounds?project=${encodeURIComponent(slug)}`);
      v2TurnState = { project: slug, look: data.look || "pixar_3d", characters: data.characters || [] };
      renderV2Turnarounds();
    } catch (e) {
      setV2TurnStatus("Could not load turnarounds: " + (e.message || e), true);
    }
  }

  function initV2Turnarounds() {
    const btnRel = $("bV2TurnReload");
    if (btnRel) btnRel.addEventListener("click", () => loadV2Turnarounds());
    const selProj = $("proj");
    if (selProj) selProj.addEventListener("change", () => { if (currentStep === 10) loadV2Turnarounds(); });
  }

  // ===== STEPS 19-22: POLISH, TIMELINE, AUDIO MIX, PREMIERE & EXPORT =====
  let v2PostState = null;

  async function loadV2PostProd() {
    const slug = ($("proj")?.value || "").trim();
    if (!slug) return;
    try {
      const data = await callApi(`/api/v2_postprod?project=${encodeURIComponent(slug)}`);
      v2PostState = data;
      const c = data.counts || {};

      // Step 19: Polish
      if ($("v2PolishBadge")) $("v2PolishBadge").textContent = `${c.videos || 0} Clips · ${c.dialogue_wavs || 0} Dialogue WAVs`;
      if ($("v2PolishLipDesc")) $("v2PolishLipDesc").textContent = `${c.dialogue_wavs || 0} rendered dialogue lines and ${c.videos || 0} video clips ready for synchronization in "${data.title}".`;
      if ($("v2PolishLipMode") && data.polish) $("v2PolishLipMode").value = data.polish.lipsync_mode || "gemini_native";
      if ($("v2PolishUpscale") && data.polish) $("v2PolishUpscale").value = data.polish.upscale_target || "1080p";
      if ($("v2PolishDeflicker") && data.polish) $("v2PolishDeflicker").checked = Boolean(data.polish.deflicker);

      // Step 20: Timeline
      const tl = data.timeline || {};
      if ($("v2TlBadge")) $("v2TlBadge").textContent = `${(tl.scenes || []).length} Scenes · ${c.total_shots || 0} Shots`;
      if ($("v2TlSummary")) $("v2TlSummary").textContent = `"${data.title}" · ${c.total_shots || 0} shots (~${c.total_seconds || 0}s) · ${c.videos || 0} video clips · ${c.keyframes || 0} keyframes · ${c.dialogue_wavs || 0} dialogue tracks`;
      if ($("v2TlCrossfade")) $("v2TlCrossfade").value = String(tl.crossfade_sec ?? 0.5);
      const tracksEl = $("v2TlTracks");
      if (tracksEl) {
        tracksEl.innerHTML = "";
        const makeTrack = (label, color, items) => {
          const r = document.createElement("div");
          r.style.cssText = "background:#0f172a;padding:8px 12px;border-radius:4px;display:flex;align-items:center;gap:12px";
          const l = document.createElement("span");
          l.style.cssText = `font-weight:700;color:${color};min-width:110px;font-size:11px`;
          l.textContent = label;
          const bar = document.createElement("div");
          bar.style.cssText = "flex:1;background:#1e293b;min-height:26px;border-radius:4px;display:flex;gap:2px;overflow-x:auto;padding:2px";
          items.forEach(([txt, bg, flex]) => {
            const seg = document.createElement("div");
            seg.style.cssText = `flex:${flex};min-width:54px;background:${bg};padding:4px 6px;font-size:10px;color:#fff;border-radius:3px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis`;
            seg.textContent = txt;
            seg.title = txt;
            bar.appendChild(seg);
          });
          r.appendChild(l);
          r.appendChild(bar);
          tracksEl.appendChild(r);
        };
        const scSegs = (tl.scenes || []).length
          ? tl.scenes.map((s, i) => [`${s.id} (${s.shots}sh · ${s.seconds}s)`, i % 2 === 0 ? "#2563eb" : "#1d4ed8", Math.max(1, s.seconds)])
          : [["No shots yet (generate in Step 12)", "#334155", 1]];
        makeTrack("TRACK 1: VIDEO", "#f59e0b", scSegs);
        makeTrack("TRACK 2: DIALOGUE", "#10b981", [[`${c.dialogue_wavs || 0} rendered spoken dialogue WAV tracks`, c.dialogue_wavs ? "#059669" : "#334155", 1]]);
        makeTrack("TRACK 3: SCORE/SFX", "#a78bfa", [[`Foley: ${c.has_foley ? "Ready" : "Not rendered"} · Score: ${c.has_score ? "Ready" : "Not rendered"}`, (c.has_foley || c.has_score) ? "#7c3aed" : "#334155", 1]]);
      }

      // Step 21: Audio Mix
      const mx = data.mix || {};
      if ($("v2MixBadge")) $("v2MixBadge").textContent = mx.master_audio_url ? "✓ Master Mixed" : "Ready to Mix";
      if ($("v2MixDlgDesc")) $("v2MixDlgDesc").textContent = `${c.dialogue_wavs || 0} rendered dialogue WAV(s) found.`;
      if ($("v2MixFolDesc")) $("v2MixFolDesc").textContent = c.has_foley ? "✓ Foley master WAV ready." : "Not rendered yet (Step 16).";
      if ($("v2MixScoDesc")) $("v2MixScoDesc").textContent = c.has_score ? "✓ Score master WAV ready." : "Not rendered yet (Step 16).";
      if ($("v2MixDlgRange")) { $("v2MixDlgRange").value = String(mx.dialogue_db ?? 0); if ($("v2MixDlgLbl")) $("v2MixDlgLbl").textContent = `Volume: ${mx.dialogue_db ?? 0} dB`; }
      if ($("v2MixFolRange")) { $("v2MixFolRange").value = String(mx.foley_db ?? -3); if ($("v2MixFolLbl")) $("v2MixFolLbl").textContent = `Volume: ${mx.foley_db ?? -3} dB`; }
      if ($("v2MixScoRange")) { $("v2MixScoRange").value = String(mx.score_db ?? -6); if ($("v2MixScoLbl")) $("v2MixScoLbl").textContent = `Volume: ${mx.score_db ?? -6} dB`; }
      if ($("v2MixDucking")) $("v2MixDucking").checked = Boolean(mx.ducking ?? true);
      _renderV2SoundPlayer("v2MixPlayerWrap", mx.master_audio_url || "", "Not mixed yet — click 🎚️ Mix & Preview Master Audio");

      // Step 22: Premiere & Export
      const ex = data.exports || {};
      if ($("v2ExpBadge")) $("v2ExpBadge").textContent = ex.preview_video_url ? "✓ Video Ready" : `"${data.title}"`;
      const th = $("v2TheaterContent");
      if (th) {
        th.innerHTML = "";
        if (ex.preview_video_url) {
          const vid = document.createElement("video");
          vid.controls = true;
          vid.src = ex.preview_video_url + "?t=" + Date.now();
          vid.style.cssText = "width:100%;height:100%;max-height:480px;background:#000";
          th.appendChild(vid);
        } else {
          const p = document.createElement("p");
          p.style.cssText = "color:#e2e8f0;font-weight:600;margin:0;font-size:1.1rem";
          p.textContent = `${data.title} (Director's Cut)`;
          const sm = document.createElement("small");
          sm.style.cssText = "color:#94a3b8;margin-top:6px";
          sm.textContent = `${c.videos || 0} video clip(s), ${c.keyframes || 0} keyframe(s), ${c.dialogue_wavs || 0} dialogue line(s) — click "🎬 Build & Download MP4" below to assemble your preview.`;
          th.appendChild(p);
          th.appendChild(sm);
        }
      }
    } catch (e) {
      if ($("v2ExpStatus")) $("v2ExpStatus").textContent = "Could not load post-production state: " + (e.message || e);
    }
  }

  function initV2PostProd() {
    const getSlug = () => ($("proj")?.value || "").trim();

    // Step 19 Save
    const btnPolish = $("bV2PolishSave");
    if (btnPolish) {
      btnPolish.addEventListener("click", async () => {
        const slug = getSlug();
        if (!slug) return;
        const st = $("v2PolishStatus");
        try {
          await callApi("/api/v2_postprod_save", {
            project: slug,
            polish: {
              lipsync_mode: $("v2PolishLipMode")?.value || "gemini_native",
              upscale_target: $("v2PolishUpscale")?.value || "1080p",
              deflicker: Boolean($("v2PolishDeflicker")?.checked),
            },
          });
          if (st) { st.style.color = "#34d399"; st.textContent = "✓ Saved Step 19 Lip-Sync & Upscaling settings."; }
        } catch (err) {
          if (st) { st.style.color = "#f87171"; st.textContent = "Error: " + (err.message || err); }
        }
      });
    }

    // Step 21 live slider labels
    [
      ["v2MixDlgRange", "v2MixDlgLbl"],
      ["v2MixFolRange", "v2MixFolLbl"],
      ["v2MixScoRange", "v2MixScoLbl"],
    ].forEach(([rid, lid]) => {
      const r = $(rid), l = $(lid);
      if (r && l) r.addEventListener("input", () => { l.textContent = `Volume: ${r.value} dB`; });
    });

    const btnMix = $("bV2MixRender");
    if (btnMix) {
      btnMix.addEventListener("click", async () => {
        const slug = getSlug();
        if (!slug) return;
        const st = $("v2MixStatus");
        const stopBusy = startBusyFeedback(btnMix, $("v2MixCard"), "Mixing Dialogue, Foley & Score stems…");
        if (st) { st.style.color = "#34d399"; st.textContent = "Mixing stems into master_mix.wav…"; }
        try {
          const res = await callApi("/api/v2_audio_mix_render", {
            project: slug,
            dialogue_db: parseFloat($("v2MixDlgRange")?.value || "0"),
            foley_db: parseFloat($("v2MixFolRange")?.value || "-3"),
            score_db: parseFloat($("v2MixScoRange")?.value || "-6"),
            ducking: Boolean($("v2MixDucking")?.checked),
          });
          const aud = _renderV2SoundPlayer("v2MixPlayerWrap", res.audio_url, "");
          if ($("v2MixBadge")) $("v2MixBadge").textContent = `✓ Mixed (${res.duration_sec || 0}s)`;
          if (st) st.textContent = `✓ Mixed master audio (${res.duration_sec || 0}s)!`;
          if (aud) aud.play().catch(() => {});
        } catch (err) {
          if (st) { st.style.color = "#f87171"; st.textContent = "Mix failed: " + (err.message || err); }
        } finally {
          stopBusy();
        }
      });
    }

    // Export helper for Steps 20 & 22
    const triggerExport = async (target, btn, statusId) => {
      const slug = getSlug();
      if (!slug) return;
      const st = $(statusId);
      const stopBusy = startBusyFeedback(btn, null, `Building ${target}…`);
      if (st) { st.style.color = "#34d399"; st.textContent = `Building ${target} for "${slug}"…`; }
      try {
        const res = await callApi("/api/v2_export_make", { project: slug, target });
        if (st) st.textContent = `✓ Ready: ${target}`;
        if (res.video_url) await loadV2PostProd();
        if (res.download_url) window.open(res.download_url, "_blank");
      } catch (err) {
        if (st) { st.style.color = "#f87171"; st.textContent = "Export failed: " + (err.message || err); }
      } finally {
        stopBusy();
      }
    };

    const bindExp = (id, target, stId) => {
      const b = $(id);
      if (b) b.addEventListener("click", () => triggerExport(target, b, stId));
    };
    bindExp("bV2TlAssemble", "master_mp4", "v2TlStatus");
    bindExp("bV2TlEdl", "edl", "v2TlStatus");
    bindExp("bV2ExpMasterMp4", "master_mp4", "v2ExpStatus");
    bindExp("bV2ExpShorts", "shorts_9x16", "v2ExpStatus");
    bindExp("bV2ExpFountain", "fountain", "v2ExpStatus");
    bindExp("bV2ExpEdl", "edl", "v2ExpStatus");
    bindExp("bV2ExpStems", "stems_zip", "v2ExpStatus");

    const btnExpAud = $("bV2ExpAudio");
    if (btnExpAud) {
      btnExpAud.addEventListener("click", () => {
        const url = v2PostState && v2PostState.exports && v2PostState.exports.master_audio_url;
        if (url) {
          window.open(url, "_blank");
        } else {
          const st = $("v2ExpStatus");
          if (st) { st.style.color = "#f87171"; st.textContent = "Mix your master audio in Step 21 first."; }
        }
      });
    }

    const selProj = $("proj");
    if (selProj) {
      selProj.addEventListener("change", () => {
        if (currentStep >= 19 && currentStep <= 22) loadV2PostProd();
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
    initV2Cast();
    initV2Styles();
    initV2Turnarounds();
    initV2Locations();
    initV2ShotList();
    initV2VoiceCast();
    initV2Dialogue();
    initV2SoundDesign();
    initV2Keyframes();
    initV2PostProd();
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
      if (currentStep === 8) loadV2Cast();
      if (currentStep === 10) loadV2Turnarounds();
      if (currentStep === 11) loadV2Locations();
      if (currentStep === 12) loadV2ShotList();
      if (currentStep === 14) loadV2VoiceCast();
      if (currentStep === 15) loadV2Dialogue();
      if (currentStep === 16) loadV2SoundDesign();
      if (currentStep === 17) loadV2Keyframes();
      if (currentStep >= 19 && currentStep <= 22) loadV2PostProd();
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
    loadV2Cast,
    loadV2Turnarounds,
    loadV2Locations,
    loadV2ShotList,
    loadV2VoiceCast,
    loadV2Dialogue,
    loadV2SoundDesign,
    loadV2Keyframes,
    loadV2PostProd,
    loadV2GeminiStatus,
    triggerAudioRedo,
    triggerSelectiveStorylineRedo,
    checkStepStorylineDrift,
  };
})();
