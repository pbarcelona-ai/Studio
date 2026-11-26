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

  // ===== LIVE INLINE AI JOB PROGRESS WIDGET (REUSABLE ACROSS STEPS 03, 05, 07, 11, 12) =====
  const _v2JobWatchers = new Map();

  function _ensureV2JobProgressStyles() {
    if (document.getElementById("v2JobProgressStyles")) return;
    const st = document.createElement("style");
    st.id = "v2JobProgressStyles";
    st.textContent = `
      @keyframes v2JobPulse { 0%, 100% { opacity: 1; transform: scale(1); } 50% { opacity: 0.45; transform: scale(0.85); } }
      @keyframes v2JobShimmer { 0% { background-position: 0% 0%; } 100% { background-position: 40px 0%; } }
      .v2-job-panel { margin-top: 10px; padding: 10px 12px; background: #070b12; border: 1px solid #263248; border-radius: 8px; display: flex; flex-direction: column; gap: 8px; }
      .v2-job-head { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; font-size: 12px; }
      .v2-job-dot { width: 8px; height: 8px; border-radius: 999px; background: #f59e0b; flex: 0 0 auto; animation: v2JobPulse 1.3s ease-in-out infinite; }
      .v2-job-dot.done { background: #10b981; animation: none; }
      .v2-job-dot.err { background: #ef4444; animation: none; }
      .v2-job-dot.stopped { background: #94a3b8; animation: none; }
      .v2-job-title { font-weight: 600; color: #f8fafc; flex: 1; min-width: 180px; }
      .v2-job-meta { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 11px; color: #fbbf24; background: rgba(245,158,11,0.12); border: 1px solid rgba(245,158,11,0.32); padding: 2px 7px; border-radius: 999px; }
      .v2-job-meta.done { color: #6ee7b7; background: rgba(16,185,129,0.12); border-color: rgba(16,185,129,0.32); }
      .v2-job-meta.err { color: #fca5a5; background: rgba(239,68,68,0.12); border-color: rgba(239,68,68,0.35); }
      .v2-job-track { width: 100%; height: 8px; background: #111827; border-radius: 999px; overflow: hidden; border: 1px solid #1f2937; }
      .v2-job-fill { height: 100%; width: 10%; border-radius: 999px; transition: width 0.5s ease, background 0.3s ease; background: repeating-linear-gradient(-45deg, #f59e0b 0px, #f59e0b 10px, #fbbf24 10px, #fbbf24 20px); background-size: 40px 40px; animation: v2JobShimmer 1.1s linear infinite; }
      .v2-job-fill.done { background: #10b981; animation: none; }
      .v2-job-fill.err { background: #ef4444; animation: none; }
      .v2-job-fill.stopped { background: #64748b; animation: none; }
      .v2-job-log-card { margin-top: 14px; padding: 10px 12px; background: #070b12; border: 1px solid #263248; border-radius: 8px; display: flex; flex-direction: column; gap: 6px; }
      .v2-job-log-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; font-size: 11px; color: #94a3b8; font-weight: 600; }
      .v2-job-log { margin: 0; padding: 8px 10px; background: #020617; color: #cbd5e1; border: 1px solid #1e293b; border-radius: 6px; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 11px; line-height: 1.45; max-height: 220px; overflow-y: auto; white-space: pre-wrap; word-break: break-word; }
    `;
    document.head.appendChild(st);
  }

  function _fmtElapsed(sec) {
    const s = Math.max(0, Math.floor(sec || 0));
    const m = Math.floor(s / 60);
    const rem = s % 60;
    return `${String(m).padStart(2, "0")}:${String(rem).padStart(2, "0")}`;
  }

  function _inferJobProgressPct(logText, elapsedSec, stepIdx, stepTotal) {
    const txt = String(logText || "");
    // Explicit percentage in log (e.g. "45%")
    const pctMatches = [...txt.matchAll(/(\d{1,3})\s*%/g)];
    if (pctMatches.length) {
      const last = parseInt(pctMatches[pctMatches.length - 1][1], 10);
      if (Number.isFinite(last) && last > 0 && last <= 99) return last;
    }
    // Explicit fraction (e.g. "scene 3/12", "round 2 of 3", "4 / 10")
    const fracMatches = [...txt.matchAll(/(?:scene|chapter|round|step|shot|pass|part)?\s*(\d{1,3})\s*(?:\/|of)\s*(\d{1,3})/gi)];
    for (let i = fracMatches.length - 1; i >= 0; i--) {
      const a = parseInt(fracMatches[i][1], 10);
      const b = parseInt(fracMatches[i][2], 10);
      if (b > 1 && a >= 0 && a <= b) {
        return Math.max(8, Math.min(95, Math.round((a / b) * 95)));
      }
    }
    if (stepTotal > 1 && stepIdx > 0) {
      return Math.max(10, Math.min(92, Math.round((stepIdx / stepTotal) * 90)));
    }
    // Smooth asymptotic estimate while AI is thinking (12% -> 92%)
    return Math.min(92, Math.max(10, Math.round(12 + 80 * (1 - Math.exp(-(elapsedSec || 0) / 50)))));
  }

  function watchV2JobProgress(cfg) {
    const key = cfg.key;
    const anchor = cfg.anchorEl || (cfg.buttonEl && cfg.buttonEl.closest(".direct-story-card"));
    if (!key || !anchor) return;
    _ensureV2JobProgressStyles();

    // Stop any previous watcher on this step key
    const prev = _v2JobWatchers.get(key);
    if (prev) {
      clearInterval(prev.tickTimer);
      clearTimeout(prev.pollTimer);
    }

    let panel = anchor.querySelector(`.v2-job-panel[data-job-key="${key}"]`);
    if (!panel) {
      panel = document.createElement("div");
      panel.className = "v2-job-panel";
      panel.dataset.jobKey = key;
      panel.innerHTML = `
        <div class="v2-job-head">
          <span class="v2-job-dot"></span>
          <span class="v2-job-title"></span>
          <span class="v2-job-meta">⏱ 00:00 · 10%</span>
          <button type="button" class="btn btn--ghost v2-job-stop" style="padding:2px 8px;font-size:11px;color:#f87171">⏹ Stop</button>
          <button type="button" class="btn btn--ghost v2-job-toggle" style="padding:2px 8px;font-size:11px">Hide Log</button>
          <button type="button" class="btn btn--ghost v2-job-close hidden" style="padding:2px 7px;font-size:11px" title="Dismiss">✕</button>
        </div>
        <div class="v2-job-track"><div class="v2-job-fill"></div></div>
      `;
      anchor.appendChild(panel);
    }
    panel.classList.remove("hidden");

    // Mount the live AI log window at the bottom of the respective step tab (inside .step-zone-workspace, above .step-zone-dock)
    const stepPanel = anchor.closest(".step-panel");
    const logHost = (stepPanel && stepPanel.querySelector(".step-zone-workspace")) || stepPanel || anchor;
    let logCard = logHost.querySelector(`.v2-job-log-card[data-job-key="${key}"]`);
    if (!logCard) {
      logCard = document.createElement("div");
      logCard.className = "v2-job-log-card";
      logCard.dataset.jobKey = key;
      logCard.innerHTML = `
        <div class="v2-job-log-head">
          <span>📟 Live AI Log Output</span>
          <span class="v2-job-log-status">Streaming…</span>
        </div>
        <pre class="v2-job-log">Starting AI worker…</pre>
      `;
      logHost.appendChild(logCard);
    } else {
      // Ensure the log window always sits at the very bottom of the step workspace
      logHost.appendChild(logCard);
    }
    logCard.classList.remove("hidden");

    const dotEl = panel.querySelector(".v2-job-dot");
    const titleEl = panel.querySelector(".v2-job-title");
    const metaEl = panel.querySelector(".v2-job-meta");
    const fillEl = panel.querySelector(".v2-job-fill");
    const logEl = logCard.querySelector(".v2-job-log");
    const logStatusEl = logCard.querySelector(".v2-job-log-status");
    const btnStop = panel.querySelector(".v2-job-stop");
    const btnToggle = panel.querySelector(".v2-job-toggle");
    const btnClose = panel.querySelector(".v2-job-close");

    dotEl.className = "v2-job-dot";
    metaEl.className = "v2-job-meta";
    fillEl.className = "v2-job-fill";
    fillEl.style.width = "10%";
    titleEl.textContent = cfg.title || "Running AI job…";
    if (logStatusEl) logStatusEl.textContent = "Streaming…";
    if (cfg.fresh !== false) logEl.textContent = "Starting AI worker…";
    btnToggle.textContent = "Hide Log";
    btnStop.classList.remove("hidden");
    btnStop.disabled = false;
    btnClose.classList.add("hidden");

    if (cfg.buttonEl) cfg.buttonEl.disabled = true;
    if (cfg.badgeEl) {
      cfg.badgeEl.textContent = "⏳ AI Working…";
      cfg.badgeEl.className = "status-badge status-badge--working";
    }

    const state = {
      active: true,
      since: 0,
      startedMs: Date.now(),
      lastStepIdx: 0,
      lastStepTotal: 1,
      hasLines: false,
      tickTimer: null,
      pollTimer: null,
    };
    _v2JobWatchers.set(key, state);

    btnToggle.onclick = () => {
      const hidden = logCard.classList.toggle("hidden");
      btnToggle.textContent = hidden ? "Show Log" : "Hide Log";
      if (!hidden) logCard.scrollIntoView({ behavior: "smooth", block: "nearest" });
    };
    btnClose.onclick = () => {
      panel.classList.add("hidden");
      logCard.classList.add("hidden");
    };
    btnStop.onclick = async () => {
      btnStop.disabled = true;
      titleEl.textContent = "Stopping AI job…";
      try { await callApi("/api/stop", {}); } catch (e) {}
    };

    const renderTimer = () => {
      if (!state.active) return;
      const elapsed = Math.max(0, (Date.now() - state.startedMs) / 1000);
      const pct = _inferJobProgressPct(state.hasLines ? logEl.textContent : "", elapsed, state.lastStepIdx, state.lastStepTotal);
      metaEl.textContent = `⏱ ${_fmtElapsed(elapsed)} · ${pct}%`;
      fillEl.style.width = `${pct}%`;
    };
    renderTimer();
    state.tickTimer = setInterval(renderTimer, 1000);

    const poll = async () => {
      if (!state.active) return;
      try {
        const r = await callApi(`/api/log?since=${state.since}`);
        if (!state.active) return;
        if (typeof r.elapsed_sec === "number" && r.elapsed_sec > 0) {
          state.startedMs = Date.now() - r.elapsed_sec * 1000;
        }
        state.lastStepIdx = Number(r.step_index || 0);
        state.lastStepTotal = Number(r.step_total || 1);
        if (r.current) {
          titleEl.textContent = r.current;
          if (cfg.statusEl) cfg.statusEl.textContent = `⏳ ${r.current}…`;
        }
        const newLines = Array.isArray(r.lines) ? r.lines.filter(x => x !== null && x !== undefined) : [];
        if (newLines.length) {
          const stick = logEl.scrollTop + logEl.clientHeight >= logEl.scrollHeight - 24;
          const chunk = newLines.join("\n");
          logEl.textContent = state.hasLines ? `${logEl.textContent}\n${chunk}` : chunk;
          state.hasLines = true;
          if (stick) logEl.scrollTop = logEl.scrollHeight;
        }
        if (typeof r.next === "number" && r.next > state.since) {
          state.since = r.next;
        }

        if (r.running) {
          renderTimer();
          state.pollTimer = setTimeout(poll, 1500);
          return;
        }

        // Job finished (or stopped / failed)
        state.active = false;
        clearInterval(state.tickTimer);
        clearTimeout(state.pollTimer);
        _v2JobWatchers.delete(key);

        const elapsed = typeof r.elapsed_sec === "number" && r.elapsed_sec > 0
          ? r.elapsed_sec
          : Math.max(0, (Date.now() - state.startedMs) / 1000);
        const stopped = String(r.status || "").toLowerCase() === "stopped" || logEl.textContent.includes("(stopped)");
        const failed = !stopped && ((typeof r.exit_code === "number" && r.exit_code !== 0) || /\n!!\s|^!!\s/.test(logEl.textContent));

        btnStop.classList.add("hidden");
        btnClose.classList.remove("hidden");
        if (cfg.buttonEl) cfg.buttonEl.disabled = false;

        if (stopped) {
          dotEl.className = "v2-job-dot stopped";
          metaEl.className = "v2-job-meta";
          metaEl.textContent = `⏹ Stopped · ${_fmtElapsed(elapsed)}`;
          fillEl.className = "v2-job-fill stopped";
          fillEl.style.width = "100%";
          titleEl.textContent = "Job stopped";
          if (logStatusEl) logStatusEl.textContent = `Stopped (${_fmtElapsed(elapsed)})`;
          if (cfg.statusEl) cfg.statusEl.textContent = `⏹ Stopped after ${_fmtElapsed(elapsed)}.`;
          if (cfg.badgeEl) {
            cfg.badgeEl.textContent = "Stopped";
            cfg.badgeEl.className = "status-badge status-badge--drift";
          }
        } else if (failed) {
          dotEl.className = "v2-job-dot err";
          metaEl.className = "v2-job-meta err";
          metaEl.textContent = `✗ Error · ${_fmtElapsed(elapsed)}`;
          fillEl.className = "v2-job-fill err";
          fillEl.style.width = "100%";
          titleEl.textContent = typeof r.exit_code === "number" ? `AI job exited with code ${r.exit_code}` : "AI job encountered an error";
          if (logStatusEl) logStatusEl.textContent = `Failed (${_fmtElapsed(elapsed)})`;
          if (cfg.statusEl) cfg.statusEl.textContent = "✗ AI job failed — check live log at the bottom of this tab.";
          if (cfg.badgeEl) {
            cfg.badgeEl.textContent = "Error";
            cfg.badgeEl.className = "status-badge status-badge--drift";
          }
        } else {
          dotEl.className = "v2-job-dot done";
          metaEl.className = "v2-job-meta done";
          metaEl.textContent = `✓ Done · ${_fmtElapsed(elapsed)} · 100%`;
          fillEl.className = "v2-job-fill done";
          fillEl.style.width = "100%";
          titleEl.textContent = `${cfg.doneTitle || "AI generation complete"} — reloaded automatically`;
          if (logStatusEl) logStatusEl.textContent = `Completed (${_fmtElapsed(elapsed)})`;
          if (typeof cfg.onComplete === "function") {
            try { await cfg.onComplete(); } catch (e) {}
          }
        }
      } catch (e) {
        if (state.active) {
          state.pollTimer = setTimeout(poll, 2500);
        }
      }
    };
    poll();
  }

  function _v2JobConfigForStep(stepNum) {
    if (stepNum === 3) {
      return {
        key: "step3_coverage",
        anchorEl: $("v2CovBuild") && $("v2CovBuild").closest(".direct-story-card"),
        buttonEl: $("v2CovBuild"),
        statusEl: $("v2CovMeta"),
        badgeEl: $("v2CovBadge"),
        title: "Analyzing book & generating coverage…",
        doneTitle: "Coverage & logline ready",
        scripts: ["read_it_in.py"],
        onComplete: () => loadV2Coverage(),
      };
    }
    if (stepNum === 5) {
      return {
        key: "step5_beats",
        anchorEl: $("v2BeatsBuild") && $("v2BeatsBuild").closest(".direct-story-card"),
        buttonEl: $("v2BeatsBuild"),
        statusEl: $("v2BeatsSummary"),
        badgeEl: $("v2BeatsBadge"),
        title: "Generating story breakdown & beat sheet…",
        doneTitle: "Story breakdown ready",
        scripts: ["read_it_in.py"],
        onComplete: () => loadV2StoryBreakdown(),
      };
    }
    if (stepNum === 7) {
      return {
        key: "step7_continuity",
        anchorEl: $("bV2ContGenerate") && $("bV2ContGenerate").closest(".direct-story-card"),
        buttonEl: $("bV2ContGenerate"),
        statusEl: $("v2ContBookStatus"),
        badgeEl: $("v2ContBadge"),
        title: "Writing continuity book from screenplay…",
        doneTitle: "Continuity book ready",
        scripts: ["continuity_book.py"],
        onComplete: () => loadV2Continuity(),
      };
    }
    if (stepNum === 11) {
      return {
        key: "step11_sets",
        anchorEl: $("bV2LocBuild") && $("bV2LocBuild").closest(".direct-story-card"),
        buttonEl: $("bV2LocBuild"),
        statusEl: $("v2LocSummary"),
        badgeEl: $("v2LocBadge"),
        title: "Extracting locations & sets from script…",
        doneTitle: "Locations & sets extracted",
        scripts: ["continuity_book.py"],
        onComplete: () => loadV2Locations(),
      };
    }
    if (stepNum === 12) {
      return {
        key: "step12_shots",
        anchorEl: $("bV2ShotsBuild") && $("bV2ShotsBuild").closest(".direct-story-card"),
        buttonEl: $("bV2ShotsBuild"),
        statusEl: $("v2ShotsSummary"),
        badgeEl: $("v2ShotsBadge"),
        title: "Writing director's breakdown & shot list…",
        doneTitle: "Shot list ready",
        scripts: ["shot_list.py"],
        onComplete: () => loadV2ShotList(),
      };
    }
    return null;
  }

  async function resumeV2JobIfRunning(cfg) {
    if (!cfg || !cfg.key || _v2JobWatchers.has(cfg.key)) return;
    try {
      const r = await callApi("/api/log?since=0");
      if (!r || !r.running) return;
      const selProj = $("proj");
      const slug = (selProj && selProj.value) || activeProject || "";
      if (r.project && slug && r.project !== slug) return;
      const allowed = Array.isArray(cfg.scripts) ? cfg.scripts : [];
      if (allowed.length && r.script && !allowed.includes(r.script)) return;
      watchV2JobProgress({ ...cfg, fresh: false, title: r.current || cfg.title });
    } catch (e) {}
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

  // ===== BI-DIRECTIONAL WORKFLOW SYNC QUEUE & PERSISTENT TOP BANNER =====
  let v2WorkflowState = { project: "", queue: { active: false, items: [] }, banner: { active: false } };
  let v2FurthestStep = 1;
  let v2BiDirCompleteTimer = null;

  // Map every Studio tool/edit endpoint to its owning step so running tools or making edits
  // automatically updates the persistent bi-directional top banner.
  const V2_API_WORKFLOW_MAP = [
    [/\/api\/save_story|\/api\/v2_ingest_book/, { step: 1, label: "Updated story source", isEdit: true }],
    [/\/api\/chapters_save|\/api\/chapter_shots/, { step: 2, label: "Updated chapters", isEdit: true }],
    [/\/api\/readin|\/api\/read_it_in|\/api\/v2_coverage_save/, { step: 3, label: "Updated coverage", isEdit: true }],
    [/\/api\/v2_scope_save/, { step: 4, label: "Updated format & runtime scope", isEdit: true }],
    [/\/api\/v2_beats_save|\/api\/v2_story_breakdown|\/api\/adaptation/, { step: 5, label: "Updated story structure & beats", isEdit: true }],
    [/\/api\/v2_screenplay_save|\/api\/screenplay|\/api\/v2_humanize_script/, { step: 6, label: "Updated screenplay", isEdit: true }],
    [/\/api\/v2_continuity_save|\/api\/continuity_book|\/api\/continuity_bootstrap|\/api\/continuity_edit|\/api\/continuity_approve|\/api\/project_rules/, { step: 7, label: "Updated continuity book", isEdit: true }],
    [/\/api\/characters(?:\?|$)|\/api\/cast_lock|\/api\/v2_cast_save|\/api\/v2_character_ref_upload|\/api\/v2_character_identity_link|\/api\/v2_wardrobe_states_save|\/api\/v2_wardrobe_save|\/api\/character_token/, { step: 8, label: "Updated cast / wardrobe", isEdit: true, includeUpstream: true }],
    [/\/api\/global_params|\/api\/v2_style_apply/, { step: 9, label: "Updated visual style recipe", isEdit: true }],
    [/\/api\/v2_turnaround_render|\/api\/v2_turnaround_sheet|\/api\/v2_turnaround_restyle/, { step: 10, label: "Updated character turnaround", isEdit: true }],
    [/\/api\/v2_set_render|\/api\/v2_set_ref_upload|\/api\/v2_set_baseline|\/api\/v2_set_analyze_sync|\/api\/v2_set_save|\/api\/v2_set_view_save|\/api\/v2_set_order/, { step: 11, label: "Updated location / set plate", isEdit: true }],
    [/\/api\/shot_list|\/api\/shot_list_approve|\/api\/shot_edit|\/api\/v2_shots_save|\/api\/v2_shot_continuity_audit/, { step: 12, label: "Updated shot list", isEdit: true }],
    [/\/api\/v2_voice_cast_save|\/api\/redo_audio|\/api\/v2_voice_profile_apply/, { step: 14, label: "Updated voice casting", isEdit: true }],
    [/\/api\/v2_dialogue_render|\/api\/v2_dialogue_upload|\/api\/v2_dialogue_save|\/api\/v2_voice_baseline_set/, { step: 15, label: "Updated spoken dialogue", isEdit: true, includeUpstream: false }],
    [/\/api\/v2_sound_design_render|\/api\/v2_sound_design_save|\/api\/v2_sound_preset_save|\/api\/v2_sound_sfx_propagate/, { step: 16, label: "Updated score / foley SFX", isEdit: true, includeUpstream: false }],
    [/\/api\/v2_keyframe_render|\/api\/v2_keyframe_sync_prompts|\/api\/v2_keyframe_clone_edit|\/api\/v2_keyframe_mask_inpaint|\/api\/v2_keyframe_angle_shift|\/api\/v2_keyframe_hybrid_pass|\/api\/v2_keyframe_edit/, { step: 17, label: "Updated storyboard keyframe", isEdit: true, includeUpstream: false }],
    [/\/api\/v2_video_render|\/api\/v2_local_video_render|\/api\/gemini_omni_generate/, { step: 18, label: "Updated video clip", isEdit: true }],
    [/\/api\/v2_postprod_save|\/api\/v2_editing_style_analyze|\/api\/v2_code_drawn_render/, { step: 20, label: "Updated timeline sequence", isEdit: false }],
    [/\/api\/v2_audio_mix_render|\/api\/v2_lufs_normalize/, { step: 21, label: "Updated audio stem mix", isEdit: true }],
    [/\/api\/v2_export_make/, { step: 22, label: "Exported premiere video", isEdit: false }],
  ];

  function _activeBookSlug() {
    const selProj = $("proj");
    return (selProj && selProj.value) ? selProj.value.trim() : (activeProject || "");
  }

  function renderV2BiDirBanner(overrideBlockedMsg = "") {
    const el = $("v2BiDirBanner");
    if (!el) return;

    // Clear all previous step-pill attention & approve pulse states
    document.querySelectorAll(".step-pill.v2-needs-attention").forEach(p => p.classList.remove("v2-needs-attention"));
    document.querySelectorAll(".btn-step-next.v2-approve-pulse").forEach(b => b.classList.remove("v2-approve-pulse"));

    const q = (v2WorkflowState && v2WorkflowState.queue) || { active: false, items: [] };
    const items = Array.isArray(q.items) ? q.items : [];
    const pending = items.filter(it => it && it.status !== "done");
    if (!q.active || !pending.length) {
      if (!el.classList.contains("phase-completed")) {
        el.style.display = "none";
      }
      return;
    }

    // Highlight every pending step pill in the top phase navigation bar
    pending.forEach(it => {
      const pill = document.querySelector(`.step-pill[data-step="${it.step}"]`);
      if (pill) pill.classList.add("v2-needs-attention");
    });

    const target = pending[0];
    const tStep = Number(target.step);
    const doneCount = items.length - pending.length;
    const originStep = Number(q.origin_step || tStep);
    const onTarget = currentStep === tStep;
    const phase = !onTarget ? "go_to_step" : (target.status === "needs_approve" ? "needs_approve" : "needs_run");

    el.className = "v2-bidir-banner phase-" + phase + (overrideBlockedMsg ? " is-blocked-flash" : "");
    el.style.display = "flex";
    el.textContent = "";

    const top = document.createElement("div");
    top.className = "v2-bidir-banner__top";

    const copy = document.createElement("div");
    copy.className = "v2-bidir-banner__copy";

    const headline = document.createElement("div");
    headline.className = "v2-bidir-banner__headline";
    const pill = document.createElement("span");
    pill.className = "v2-bidir-banner__pill";
    pill.textContent = `Sync ${doneCount + 1}/${items.length} · Return → Step ${String(originStep).padStart(2, "0")}`;
    const hText = document.createElement("span");
    if (phase === "needs_approve") {
      hText.textContent = `✅ Step ${String(tStep).padStart(2, "0")} (${target.title}) Completed — Click the Approval Button to Continue!`;
    } else if (phase === "needs_run") {
      hText.textContent = `⚡ Action Required on Step ${String(tStep).padStart(2, "0")}: ${target.title}`;
    } else {
      hText.textContent = `🔄 Bi-Directional Update Required — Go to Step ${String(tStep).padStart(2, "0")} (${target.title})`;
    }
    headline.appendChild(pill);
    headline.appendChild(hText);

    const inst = document.createElement("div");
    inst.className = "v2-bidir-banner__inst";
    if (overrideBlockedMsg) {
      inst.textContent = overrideBlockedMsg;
    } else if (phase === "needs_approve") {
      const nextAfter = pending[1];
      const nextDesc = nextAfter
        ? `Step ${String(nextAfter.step).padStart(2, "0")} (${nextAfter.title})`
        : `finish syncing and return to Step ${String(originStep).padStart(2, "0")}`;
      inst.textContent = `Tool run complete! Now click the "Approve & Next ➔" button at the bottom of Step ${String(tStep).padStart(2, "0")} to proceed to ${nextDesc}.`;
    } else if (phase === "needs_run") {
      inst.textContent = `${target.action}. When it finishes, this banner will prompt you to click the Approval button to move to the next step.`;
    } else {
      const reasonTxt = target.reason || q.change_summary || "a recent modification";
      const chainTxt = pending.map(it => `Step ${String(it.step).padStart(2, "0")} (${it.title})`).join(" ➔ ");
      inst.textContent = `Because of "${reasonTxt}", complete these steps in order: ${chainTxt}. Start now on Step ${String(tStep).padStart(2, "0")} (${target.action}), then click Approve & Next at each step.`;
    }

    copy.appendChild(headline);
    copy.appendChild(inst);

    const actions = document.createElement("div");
    actions.className = "v2-bidir-banner__actions";
    if (phase === "go_to_step") {
      const btnGo = document.createElement("button");
      btnGo.type = "button";
      btnGo.className = "btn btn--primary";
      btnGo.style.cssText = "padding:6px 13px;font-size:12px;font-weight:700;";
      btnGo.textContent = `⬅ Go to Step ${String(tStep).padStart(2, "0")} Now`;
      btnGo.addEventListener("click", () => activateStep(tStep));
      actions.appendChild(btnGo);
    } else if (phase === "needs_run") {
      const btnReviewed = document.createElement("button");
      btnReviewed.type = "button";
      btnReviewed.className = "btn btn--secondary";
      btnReviewed.style.cssText = "padding:6px 12px;font-size:12px;font-weight:600;";
      btnReviewed.textContent = "✓ Reviewed — No Changes Needed";
      btnReviewed.title = `Confirm you reviewed Step ${String(tStep).padStart(2, "0")} and no re-render is needed, unlocking Approve & Next.`;
      btnReviewed.addEventListener("click", async () => {
        const slug = _activeBookSlug();
        if (!slug) return;
        btnReviewed.disabled = true;
        await v2WorkflowMarkToolDone(slug, tStep, `Reviewed Step ${String(tStep).padStart(2, "0")} (no changes needed)`);
      });
      actions.appendChild(btnReviewed);
    } else if (phase === "needs_approve") {
      const activePanel = document.querySelector(`.step-panel[data-step="${currentStep}"]`);
      const nextBtn = activePanel ? activePanel.querySelector(".btn-step-next") : null;
      if (nextBtn) nextBtn.classList.add("v2-approve-pulse");
      const btnJumpApprove = document.createElement("button");
      btnJumpApprove.type = "button";
      btnJumpApprove.className = "btn btn--primary";
      btnJumpApprove.style.cssText = "padding:6px 13px;font-size:12px;font-weight:700;background:#10b981;border-color:#34d399;color:#022c22;";
      btnJumpApprove.textContent = "⬇ Jump to Approval Button";
      btnJumpApprove.addEventListener("click", () => {
        if (nextBtn) {
          nextBtn.scrollIntoView({ behavior: "smooth", block: "center" });
          nextBtn.focus();
        }
      });
      actions.appendChild(btnJumpApprove);
    }

    top.appendChild(copy);
    top.appendChild(actions);
    el.appendChild(top);

    // Ordered step-by-step catch-up breadcrumb strip
    const strip = document.createElement("div");
    strip.className = "v2-bidir-steps";
    items.forEach((it, idx) => {
      const ch = document.createElement("button");
      ch.type = "button";
      const isCurTarget = it.step === tStep && it.status !== "done";
      ch.className = "v2-bidir-chip" +
        (it.status === "done" ? " is-done" : (isCurTarget ? (it.status === "needs_approve" ? " is-approve" : " is-active") : ""));
      const icon = it.status === "done" ? "✓" : (it.status === "needs_approve" ? "✔ Approve" : (isCurTarget ? "●" : "○"));
      ch.textContent = `${icon} ${it.short || ("Step " + it.step)}`;
      ch.title = `${it.title}: ${it.status === "done" ? "Completed & Approved" : (it.status === "needs_approve" ? "Tool done — click Approve & Next" : it.action)}`;
      ch.addEventListener("click", () => activateStep(Number(it.step)));
      strip.appendChild(ch);
      if (idx < items.length - 1) {
        const arr = document.createElement("span");
        arr.style.cssText = "color:#94a3b8;font-size:11px";
        arr.textContent = "➔";
        strip.appendChild(arr);
      }
    });
    el.appendChild(strip);
  }

  function showV2BiDirCompletedBanner(originStep) {
    const el = $("v2BiDirBanner");
    if (!el) return;
    if (v2BiDirCompleteTimer) clearTimeout(v2BiDirCompleteTimer);
    el.className = "v2-bidir-banner phase-completed";
    el.style.display = "flex";
    el.textContent = "";
    const row = document.createElement("div");
    row.className = "v2-bidir-banner__top";
    const msg = document.createElement("div");
    msg.className = "v2-bidir-banner__headline";
    msg.textContent = `✅ Bi-Directional Sync Complete — All required steps were re-run & approved! You are back at Step ${String(originStep || currentStep).padStart(2, "0")}.`;
    const btnOk = document.createElement("button");
    btnOk.type = "button";
    btnOk.className = "btn btn--ghost";
    btnOk.style.cssText = "padding:4px 10px;font-size:11px;color:#ecfdf5;";
    btnOk.textContent = "Done";
    btnOk.addEventListener("click", () => {
      el.classList.remove("phase-completed");
      el.style.display = "none";
    });
    row.appendChild(msg);
    row.appendChild(btnOk);
    el.appendChild(row);
    v2BiDirCompleteTimer = setTimeout(() => {
      if (el.classList.contains("phase-completed")) {
        el.classList.remove("phase-completed");
        el.style.display = "none";
      }
    }, 7000);
  }

  async function loadV2WorkflowSync(slugOverride = "") {
    const slug = slugOverride || _activeBookSlug();
    if (!slug) {
      v2WorkflowState = { project: "", queue: { active: false, items: [] }, banner: { active: false } };
      renderV2BiDirBanner();
      return;
    }
    try {
      const res = await rawCallApi(`/api/v2_workflow_sync?project=${encodeURIComponent(slug)}&current_step=${currentStep}`);
      v2WorkflowState = {
        project: slug,
        queue: (res && res.queue) || { active: false, items: [] },
        banner: (res && res.banner) || { active: false },
      };
      renderV2BiDirBanner();
    } catch (e) {}
  }

  async function v2WorkflowRecordModification(slug, stepNum, summary, { includeUpstream = false, upstreamSteps = null, originStep = null, showPlanPopup = false } = {}) {
    if (!slug || !stepNum) return null;
    try {
      const prevPendingSteps = ((v2WorkflowState && v2WorkflowState.queue && v2WorkflowState.queue.items) || [])
        .filter(it => it && it.status !== "done")
        .map(it => Number(it.step))
        .join(",");
      const payload = {
        project: slug,
        action: "modify",
        step: stepNum,
        current_step: currentStep,
        summary: summary || `Modified Step ${String(stepNum).padStart(2, "0")}`,
        origin_step: originStep || Math.max(v2FurthestStep, currentStep, stepNum),
        include_upstream: Boolean(includeUpstream),
      };
      if (Array.isArray(upstreamSteps)) payload.upstream_steps = upstreamSteps;
      const res = await rawCallApi("/api/v2_workflow_sync_event", payload);
      if (res && res.queue) {
        v2WorkflowState = { project: slug, queue: res.queue, banner: res.banner || { active: false } };
        renderV2BiDirBanner();
        const newPending = (res.queue.items || []).filter(it => it && it.status !== "done");
        const newPendingSteps = newPending.map(it => Number(it.step)).join(",");
        if (showPlanPopup && newPending.length > 0 && newPendingSteps !== prevPendingSteps && Array.isArray(res.plan_lines) && res.plan_lines.length) {
          const firstStep = Number(newPending[0].step);
          const roadmap = res.plan_lines.join("\n");
          const goNow = await showInstallApprovalModal(
            `🔄 Bi-Directional Update Required (${newPending.length} Step${newPending.length === 1 ? "" : "s"})`,
            `Because you updated Step ${String(stepNum).padStart(2, "0")} (${summary || "change"}), complete these steps in order:\n\n${roadmap}\n\nClick OK to jump to Step ${String(firstStep).padStart(2, "0")} now, or Cancel to stay here (the top banner will stay pinned until all steps are completed & approved).`
          );
          if (goNow && firstStep && firstStep !== currentStep) {
            activateStep(firstStep);
          }
        }
      }
      return res;
    } catch (e) {
      return null;
    }
  }

  async function v2WorkflowMarkToolDone(slug, stepNum, toolLabel = "") {
    if (!slug || !stepNum) return;
    try {
      const res = await rawCallApi("/api/v2_workflow_sync_event", {
        project: slug,
        action: "tool_done",
        step: stepNum,
        current_step: currentStep,
        tool_label: toolLabel,
      });
      if (res && res.queue) {
        v2WorkflowState = { project: slug, queue: res.queue, banner: res.banner || { active: false } };
        renderV2BiDirBanner();
      }
    } catch (e) {}
  }

  async function handleV2ApproveNextClick() {
    const slug = _activeBookSlug();
    const q = (v2WorkflowState && v2WorkflowState.queue) || { active: false, items: [] };
    if (slug && q.active) {
      try {
        const res = await rawCallApi("/api/v2_workflow_sync_event", {
          project: slug,
          action: "approve",
          step: currentStep,
          current_step: currentStep,
        });
        if (res && res.queue) {
          v2WorkflowState = { project: slug, queue: res.queue, banner: res.banner || { active: false } };
        }
        if (res && res.blocked_needs_run) {
          const reqItem = ((res.queue && res.queue.items) || []).find(it => Number(it.step) === Number(currentStep));
          const reqAction = (res.required_action || (reqItem && reqItem.action) || "").trim();
          renderV2BiDirBanner(
            reqAction
              ? `⚠️ Action needed before approving Step ${String(currentStep).padStart(2, "0")}: ${reqAction} — or click "✓ Reviewed — No Changes Needed" if everything here already matches.`
              : `⚠️ Complete the required update on Step ${String(currentStep).padStart(2, "0")} BEFORE clicking Approve & Next!`
          );
          const banner = $("v2BiDirBanner");
          if (banner) banner.scrollIntoView({ behavior: "smooth", block: "start" });
          return;
        }
        if (res && res.completed) {
          renderV2BiDirBanner();
          const retStep = Number(res.origin_step || (currentStep + 1));
          activateStep(retStep);
          showV2BiDirCompletedBanner(retStep);
          return;
        }
        if (res && res.advanced && res.next_step) {
          activateStep(Number(res.next_step));
          return;
        }
      } catch (e) {}
    }
    activateStep(currentStep + 1);
  }

  // ===== UPSTREAM FEEDBACK SYNC (LATER STEP -> EARLIER STEPS WITH FULL TRANSITIVE ROADMAP POPUP) =====
  async function proposeUpstreamSync({ project, kind, affectedStepNums, title, message, payload, onSynced }) {
    if (!project || !kind) return false;
    // Preview the FULL transitive chain (e.g. Step 17 -> Step 12 -> Step 07 -> Step 12 -> Step 17) BEFORE showing the popup!
    let previewLines = [];
    let allAffectedNums = Array.isArray(affectedStepNums) ? affectedStepNums.slice() : [];
    try {
      const prev = await rawCallApi("/api/v2_workflow_sync_event", {
        project,
        action: "preview",
        step: currentStep,
        current_step: currentStep,
        origin_step: currentStep,
        summary: title || `Modified Step ${String(currentStep).padStart(2, "0")}`,
        upstream_steps: affectedStepNums || [],
      });
      if (prev && Array.isArray(prev.plan_lines) && prev.plan_lines.length) {
        previewLines = prev.plan_lines;
      }
      if (prev && prev.queue && Array.isArray(prev.queue.items)) {
        allAffectedNums = prev.queue.items.map(it => Number(it.step)).filter(Boolean);
      }
    } catch (e) {}

    const pills = allAffectedNums
      .map(n => document.querySelector(`.step-pill[data-step="${n}"]`))
      .filter(Boolean);
    pills.forEach(p => p.classList.add("v2-needs-attention"));

    const roadmapBlock = previewLines.length
      ? `\n\nFull step-by-step action plan required:\n${previewLines.join("\n")}`
      : "";
    try {
      const ok = await showInstallApprovalModal(
        title || "🔄 Bi-Directional Update Required",
        message +
          roadmapBlock +
          "\n\nClick OK to sync upstream data and start this guided catch-up (or Cancel to leave these steps queued in the top banner for manual update)."
      );
      if (!ok) {
        await v2WorkflowRecordModification(project, currentStep, title || "Upstream change requires step update", {
          upstreamSteps: affectedStepNums || [],
          originStep: currentStep,
        });
        return false;
      }
      const res = await rawCallApi("/api/v2_sync_upstream", { project, kind, approved: true, payload });
      if (typeof onSynced === "function") onSynced(res);
      const qRes = await v2WorkflowRecordModification(project, currentStep, title || "Synced upstream change", {
        upstreamSteps: affectedStepNums || [],
        originStep: currentStep,
      });
      const firstPending = qRes && qRes.queue && (qRes.queue.items || []).find(it => it && it.status !== "done");
      if (firstPending && Number(firstPending.step) !== currentStep) {
        activateStep(Number(firstPending.step));
      }
      return true;
    } catch (e) {
      return false;
    } finally {
      pills.forEach(p => p.classList.remove("v2-needs-attention"));
      renderV2BiDirBanner();
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

  let _v2SyncToastTimer = null;
  function _showV2SyncToast(report) {
    if (!report || typeof report !== "object") return;
    const steps = Array.isArray(report.updated_steps) ? report.updated_steps.filter(Boolean) : [];
    const preserved = Array.isArray(report.preserved) ? report.preserved.filter(Boolean) : [];
    if (!steps.length && !preserved.length) return;
    let el = document.getElementById("v2RealTimeSyncToast");
    if (!el) {
      el = document.createElement("div");
      el.id = "v2RealTimeSyncToast";
      el.style.cssText = "position:fixed;right:18px;bottom:18px;z-index:9999;max-width:440px;padding:10px 14px;border-radius:10px;background:#0f172a;border:1px solid rgba(16,185,129,0.55);box-shadow:0 10px 28px rgba(0,0,0,0.45);color:#e2e8f0;font-size:12px;line-height:1.45;transition:opacity 0.25s ease;";
      document.body.appendChild(el);
    }
    const parts = [];
    if (steps.length) parts.push(`<strong style="color:#34d399">🔄 Synced real-time:</strong> ${steps.join(" · ")}`);
    if (preserved.length) parts.push(`<span style="color:#94a3b8;font-size:11px">🔒 Preserved untouched: ${preserved.slice(0, 3).join(", ")}${preserved.length > 3 ? ` (+${preserved.length - 3} more)` : ""}</span>`);
    el.innerHTML = parts.join("<br>");
    el.style.opacity = "1";
    el.style.display = "block";
    if (_v2SyncToastTimer) clearTimeout(_v2SyncToastTimer);
    _v2SyncToastTimer = setTimeout(() => {
      el.style.opacity = "0";
      setTimeout(() => { if (el.style.opacity === "0") el.style.display = "none"; }, 260);
    }, 5200);
  }

  async function callApi(url, body) {
    let stopBusy = null;
    if (body !== undefined) {
      const hit = BUSY_API_LABELS.find(([re]) => re.test(url));
      if (hit) {
        stopBusy = startBusyFeedback(null, null, hit[1]);
      }
    }
    try {
      const res = await rawCallApi(url, body);
      if (body !== undefined && res && res.sync_report) {
        _showV2SyncToast(res.sync_report);
      }
      if (body !== undefined && !url.includes("/api/v2_workflow_sync")) {
        const wfHit = V2_API_WORKFLOW_MAP.find(([re]) => re.test(url));
        const slugForWf = (body && (body.project || body.slug)) || _activeBookSlug();
        if (wfHit && slugForWf) {
          const meta = wfHit[1];
          const q = (v2WorkflowState && v2WorkflowState.queue) || { active: false, items: [] };
          const isPendingThisStep = Boolean(
            q.active && (q.items || []).some(it => it && Number(it.step) === meta.step && it.status === "needs_run")
          );
          if (isPendingThisStep) {
            v2WorkflowMarkToolDone(slugForWf, meta.step, meta.label);
          } else if (meta.isEdit) {
            v2WorkflowRecordModification(slugForWf, meta.step, meta.label, {
              includeUpstream: Boolean(meta.includeUpstream),
              showPlanPopup: true,
            });
          }
        }
      }
      return res;
    } catch (err) {
      const msg = String((err && err.message) || err || "");
      if (url !== "/api/v2_install_engine") {
        const hit = INSTALLABLE_ENGINES.find(e => e.match.test(msg));
        if (hit) {
          if (stopBusy) { stopBusy(); stopBusy = null; }
          const installed = await requestInstallWithApproval(hit.key, hit.label, hit.pkgs);
          if (installed) {
            const retryRes = await rawCallApi(url, body);
            if (body !== undefined && retryRes && retryRes.sync_report) {
              _showV2SyncToast(retryRes.sync_report);
            }
            return retryRes;
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
    const btnClear = $("bClearStory");
    if (btnClear && inputText) btnClear.addEventListener("click", () => { inputText.value = ""; });
    const btnApproveMaster = $("bApproveMaster");
    if (btnApproveMaster) btnApproveMaster.addEventListener("click", () => { alert("Film generation complete! All deliverables ready."); });

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

    // Step 01: Firecrawl MCP Research Buttons
    const btnResearch = $("bStep1Research");
    const btnResearchGenre = $("bStep1ResearchGenre");
    const btnResearchScreenplay = $("bStep1ResearchScreenplay");
    const researchInput = $("step1ResearchQuery");
    const researchResults = $("step1ResearchResults");

    if (btnResearch && researchInput && researchResults) {
      btnResearch.addEventListener("click", async () => {
        const query = researchInput.value.trim();
        if (!query) { alert("Enter a research query first."); return; }
        try {
          btnResearch.disabled = true;
          btnResearch.textContent = "🔍 Searching…";
          researchResults.style.display = "block";
          researchResults.textContent = "Searching…";
          const result = await callApi("/api/mcp/firecrawl/search", { query, limit: 10 });
          if (result.error) throw new Error(result.error);
          researchResults.innerHTML = formatFirecrawlResults(result);
        } catch (err) {
          console.error("Firecrawl search failed:", err);
          researchResults.textContent = "Error: " + err.message;
        } finally {
          btnResearch.disabled = false;
          btnResearch.textContent = "🔍 Search";
        }
      });
    }

    if (btnResearchGenre && researchResults) {
      btnResearchGenre.addEventListener("click", async () => {
        const genre = prompt("Enter film genre (e.g., sci-fi, thriller, romance, action):", "sci-fi");
        if (!genre) return;
        const year = prompt("Enter year (optional):", "");
        try {
          btnResearchGenre.disabled = true;
          btnResearchGenre.textContent = "🎬 Loading…";
          researchResults.style.display = "block";
          researchResults.textContent = "Researching comparable films…";
          const result = await callApi("/api/mcp/firecrawl/research_comparables", { genre, year: year ? parseInt(year) : null });
          if (result.error) throw new Error(result.error);
          researchResults.innerHTML = formatFirecrawlResults(result);
        } catch (err) {
          console.error("Firecrawl genre research failed:", err);
          researchResults.textContent = "Error: " + err.message;
        } finally {
          btnResearchGenre.disabled = false;
          btnResearchGenre.textContent = "🎬 Film Comparables";
        }
      });
    }

    if (btnResearchScreenplay && researchResults) {
      btnResearchScreenplay.addEventListener("click", async () => {
        const title = prompt("Enter film title for screenplay analysis:", "");
        if (!title) return;
        try {
          btnResearchScreenplay.disabled = true;
          btnResearchScreenplay.textContent = "📝 Analyzing…";
          researchResults.style.display = "block";
          researchResults.textContent = "Analyzing screenplay structure…";
          const result = await callApi("/api/mcp/firecrawl/research_screenplay", { title });
          if (result.error) throw new Error(result.error);
          researchResults.innerHTML = formatFirecrawlResults(result);
        } catch (err) {
          console.error("Firecrawl screenplay research failed:", err);
          researchResults.textContent = "Error: " + err.message;
        } finally {
          btnResearchScreenplay.disabled = false;
          btnResearchScreenplay.textContent = "📝 Screenplay Analysis";
        }
      });
    }

    function formatFirecrawlResults(result) {
      // Firecrawl returns different formats depending on the tool
      if (result.data && Array.isArray(result.data)) {
        return result.data.map(item => `
          <div style="margin-bottom:12px;padding:10px;background:#0a0d14;border:1px solid #1e293b;border-radius:6px">
            <div style="font-weight:600;color:#f59e0b;margin-bottom:4px">${escapeHtml(item.title || item.url || "Result")}</div>
            <div style="font-size:var(--text-xs);color:#94a3b8;margin-bottom:4px">${escapeHtml(item.url || "")}</div>
            <div style="color:#cbd5e1;font-size:var(--text-sm)">${escapeHtml(item.description || item.content || item.markdown || JSON.stringify(item)).slice(0, 500)}</div>
          </div>
        `).join("");
      }
      if (result.results && Array.isArray(result.results)) {
        return result.results.map(item => `
          <div style="margin-bottom:12px;padding:10px;background:#0a0d14;border:1px solid #1e293b;border-radius:6px">
            <div style="font-weight:600;color:#f59e0b;margin-bottom:4px">${escapeHtml(item.title || item.url || "Result")}</div>
            <div style="font-size:var(--text-xs);color:#94a3b8;margin-bottom:4px">${escapeHtml(item.url || "")}</div>
            <div style="color:#cbd5e1;font-size:var(--text-sm)">${escapeHtml(item.description || item.content || item.snippet || JSON.stringify(item)).slice(0, 500)}</div>
          </div>
        `).join("");
      }
      return `<pre style="color:#cbd5e1;font-size:var(--text-xs);white-space:pre-wrap">${escapeHtml(JSON.stringify(result, null, 2))}</pre>`;
    }

    function escapeHtml(text) {
      const div = document.createElement("div");
      div.textContent = text;
      return div.innerHTML;
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
                <option value="kokoro" selected>🎙️ Kokoro-82M Local Neural (Default)</option>
                <option value="gemini-tts">✨ Gemini Neural TTS (Cloud)</option>
                <option value="macos-say">⚡ Fast Scratch Preview (macOS)</option>
              </select>
            </div>
            <div>
              <label class="f" for="v2AutoVisualEng">Visual &amp; Keyframe Engine</label>
              <select id="v2AutoVisualEng" style="width:100%;padding:8px;background:#0a0d14;color:#f8fafc;border:1px solid #334155;border-radius:6px;font-size:13px">
                <option value="local" selected>💻 Local GPU (ComfyUI / sd-cli)</option>
                <option value="gemini">✨ Google Gemini API</option>
              </select>
            </div>
          </div>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">
            <div>
              <label class="f" for="v2AutoDialect">Voice Dialect</label>
              <select id="v2AutoDialect" style="width:100%;padding:8px;background:#0a0d14;color:#f8fafc;border:1px solid #334155;border-radius:6px;font-size:13px">
                <option value="american" selected>🇺🇸 American English</option>
                <option value="british">🇬🇧 British RP</option>
              </select>
            </div>
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
          visualEngine: box.querySelector("#v2AutoVisualEng")?.value || "local",
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
      document.removeEventListener("keydown", handleKeyDown);
      overlay.remove();
      try { activateStep(currentStep); } catch (e) {}
    };
    const handleKeyDown = (e) => {
      if (e.key === "Escape" && canDismiss) closeOverlay();
    };
    document.addEventListener("keydown", handleKeyDown);
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
        log(`  Rendering keyframe ${sh.id} (${i + 1}/${todoShots.length}) via ${cfg.visualEngine || "local"}…`);
        await autoApi("/api/v2_keyframe_render", {
          project: slug,
          id: sh.id,
          prompt: sh.prompt,
          aspect_ratio: "16:9",
          engine: cfg.visualEngine || "local",
        });
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
    if (currentStep > v2FurthestStep) v2FurthestStep = currentStep;

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
      resumeV2JobIfRunning(_v2JobConfigForStep(3));
    }

    // If entering Step 4 (Format & Runtime Scope), load dynamic book-based scope options
    if (currentStep === 4) {
      loadV2Scope();
    }

    // If entering Step 5 (Story Structure & Beats), load full beat sheet & scene breakdown
    if (currentStep === 5) {
      loadV2StoryBreakdown();
      resumeV2JobIfRunning(_v2JobConfigForStep(5));
    }

    // If entering Step 6 (Screenplay), load all screenplay scenes
    if (currentStep === 6) {
      loadV2Screenplay();
    }

    // If entering Step 7 (Continuity & World Rules), load rules, lighting/palette, and scene locks
    if (currentStep === 7) {
      loadV2Continuity();
      resumeV2JobIfRunning(_v2JobConfigForStep(7));
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
      resumeV2JobIfRunning(_v2JobConfigForStep(11));
    }

    // If entering Step 12 (Shot List & Cinematography), load live shot list
    if (currentStep === 12) {
      loadV2ShotList();
      resumeV2JobIfRunning(_v2JobConfigForStep(12));
    }

    // If entering Step 13 (Hardware) or Step 18 (Video), refresh Gemini & hardware status
    if (currentStep === 13 || currentStep === 18) {
      loadV2GeminiStatus();
      if (currentStep === 18) loadV2VideoClips();
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

    // Check for storyline drift, update bi-directional top banner, and load step autopilot
    checkStepStorylineDrift();
    renderV2BiDirBanner();
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
        const cfg = _v2JobConfigForStep(3);
        if (metaEl) metaEl.textContent = `Starting coverage analysis for "${slug}"…`;
        try {
          const o = typeof window.options === "function" ? window.options() : {};
          await callApi("/api/read_it_in", { project: slug, engine: o.engine || "claude", claude_model: o.claude_model });
          watchV2JobProgress({ ...cfg, fresh: true });
        } catch (err) {
          if (/already running/i.test(String(err.message || ""))) {
            watchV2JobProgress({ ...cfg, fresh: false });
          } else {
            if (metaEl) metaEl.textContent = "Could not start coverage: " + err.message;
            btnBuild.disabled = false;
          }
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
          const titleEl = document.createElement("strong");
          titleEl.style.color = "#f59e0b";
          titleEl.textContent = b.name || `Beat ${b.n}`;
          li.appendChild(titleEl);
          li.appendChild(document.createTextNode(`: ${b.description || ""}`));
          if (b.viewer_expectation || b.open_loop) {
            const meta = document.createElement("div");
            meta.style.cssText = "margin-top:3px;padding-left:8px;border-left:2px solid #334155;color:#94a3b8;font-size:11px;display:flex;flex-direction:column;gap:2px";
            if (b.viewer_expectation) {
              const ex = document.createElement("span");
              ex.textContent = `👁 Expects: ${b.viewer_expectation}`;
              meta.appendChild(ex);
            }
            if (b.open_loop) {
              const lp = document.createElement("span");
              lp.style.color = "#38bdf8";
              lp.textContent = `🪝 Open loop: ${b.open_loop}`;
              meta.appendChild(lp);
            }
            li.appendChild(meta);
          }
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
        const cfg = _v2JobConfigForStep(5);
        if (summaryEl) summaryEl.textContent = "Starting story breakdown & beat sheet generation…";
        try {
          const o = typeof window.options === "function" ? window.options() : {};
          await callApi("/api/read_it_in", { project: slug, engine: o.engine || "claude", claude_model: o.claude_model });
          watchV2JobProgress({ ...cfg, fresh: true });
        } catch (err) {
          if (/already running/i.test(String(err.message || ""))) {
            watchV2JobProgress({ ...cfg, fresh: false });
          } else {
            if (summaryEl) summaryEl.textContent = "Could not start breakdown: " + err.message;
            btnBuild.disabled = false;
          }
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
  let spFilter = "D"; // "A" | "D" | "T" | "AD" | "AT" | "DT" | "ADT" - default to Dialogue only

  function spElementsToText(els, filter) {
    if (!Array.isArray(els)) return "";
    const f = (filter || spFilter).toUpperCase();
    // Parse filter: can be single letters (A, D, T) or combinations (AD, AT, DT, ADT)
    const allowed = new Set(f.split(""));
    return els.filter(e => {
      const typeChar = e.type === "dialogue" ? "D" : (e.type === "transition" ? "T" : "A");
      return allowed.has(typeChar);
    }).map(e => {
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
          ? spElementsToText(s.screenplay.elements, spFilter)
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
            ? spElementsToText(s.screenplay.elements, spFilter)
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
    const btnExport = $("spExport");
    const btnImportFile = $("spImportFile");
    const filesSpan = $("spFiles");
    const filterSelect = $("v2SpFilter");
    const btnRewrite = $("v2SpRewrite");
    const btnClearInstructions = $("v2SpClearInstructions");
    const instructionsArea = $("v2SpInstructions");

    if (prevBtn) prevBtn.addEventListener("click", () => { if (spActiveIdx > 0) { spActiveIdx--; spViewMode = "single"; renderV2Screenplay(); } });
    if (nextBtn) nextBtn.addEventListener("click", () => { if (spActiveIdx < spScenesData.length - 1) { spActiveIdx++; spViewMode = "single"; renderV2Screenplay(); } });
    if (btnSingle) btnSingle.addEventListener("click", () => { spViewMode = "single"; renderV2Screenplay(); });
    if (btnAll) btnAll.addEventListener("click", () => { spViewMode = "all"; renderV2Screenplay(); });
    if (btnRefresh) btnRefresh.addEventListener("click", () => loadV2Screenplay());

    // Filter dropdown: element type filter
    if (filterSelect) {
      filterSelect.addEventListener("change", () => {
        spFilter = filterSelect.value;
        renderV2Screenplay();
      });
    }

    // Clear instructions button
    if (btnClearInstructions && instructionsArea) {
      btnClearInstructions.addEventListener("click", () => {
        instructionsArea.value = "";
        instructionsArea.focus();
      });
    }

    // Update Scene (AI Rewrite) button
    if (btnRewrite && instructionsArea) {
      btnRewrite.addEventListener("click", async () => {
        const instructions = instructionsArea.value.trim();
        if (!instructions) {
          alert("Please enter additional instructions for the AI rewrite.");
          return;
        }
        const selProj = $("proj");
        const slug = (selProj && selProj.value) || activeProject || "";
        if (!slug) {
          alert("Pick a book first.");
          return;
        }
        const s = spScenesData[spActiveIdx];
        if (!s) {
          alert("No scene selected.");
          return;
        }

        btnRewrite.disabled = true;
        btnRewrite.textContent = "✨ Rewriting…";
        const saveMsg = $("v2SpSaveMsg");
        if (saveMsg) saveMsg.textContent = "AI rewriting scene…";

        try {
          await callApi("/api/screenplay_edit", {
            project: slug,
            action: "rewrite_scene",
            scene: s.id,
            instructions: instructions
          });
          if (saveMsg) saveMsg.textContent = `✓ Scene ${s.id} rewritten. Refreshing…`;
          instructionsArea.value = ""; // Clear instructions after successful rewrite
          await loadV2Screenplay();
          await checkStepStorylineDrift();
        } catch (err) {
          console.error("Rewrite failed:", err);
          if (saveMsg) saveMsg.textContent = "Error: " + err.message;
        } finally {
          btnRewrite.disabled = false;
          btnRewrite.textContent = "✨ Update Scene (AI)";
        }
      });
    }

    // Export screenplay (creates .fdx, .fountain, .docx, .pdf)
    if (btnExport) {
      btnExport.addEventListener("click", async () => {
        const selProj = $("proj");
        const slug = (selProj && selProj.value) || activeProject || "";
        if (!slug) return;
        try {
          btnExport.disabled = true;
          btnExport.textContent = "Exporting…";
          const result = await callApi("/api/readin_export", { project: slug, formats: ["fdx", "fountain", "docx", "pdf"] });
          if (result && result.exports) {
            filesSpan.innerHTML = result.exports.map(f => `<a class="btn btn--ghost" href="${f.url}" download>${f.name}</a>`).join(" ");
          }
          btnExport.textContent = "Export downloads (.fdx, .fountain, .docx, .pdf)";
        } catch (err) {
          console.error("Export failed:", err);
          btnExport.textContent = "Export downloads (.fdx, .fountain, .docx, .pdf)";
        } finally {
          btnExport.disabled = false;
        }
      });
    }

    // Import screenplay (.fdx or .fountain)
    if (btnImportFile) {
      btnImportFile.addEventListener("change", async () => {
        const file = btnImportFile.files[0];
        if (!file) return;
        const selProj = $("proj");
        const slug = (selProj && selProj.value) || activeProject || "";
        if (!slug) {
          alert("Pick a book first.");
          btnImportFile.value = "";
          return;
        }
        if (!confirm("Import will replace the current screenplay. Continue?")) {
          btnImportFile.value = "";
          return;
        }
        try {
          btnImportFile.disabled = true;
          const progressEl = $("riProgress") || $("v2SpSaveMsg");
          if (progressEl) progressEl.textContent = `Importing ${file.name}…`;
          const base64 = await fileToBase64(file);
          const result = await callApi("/api/readin_import", {
            project: slug,
            file: { name: file.name, content_base64: base64 }
          });
          if (progressEl) progressEl.textContent = `Imported ${result.imported} of ${result.total_plan_scenes} scenes. Refreshing…`;
          btnImportFile.value = "";
          await loadV2Screenplay();
          await checkStepStorylineDrift();
        } catch (err) {
          console.error("Import failed:", err);
          const progressEl = $("riProgress") || $("v2SpSaveMsg");
          if (progressEl) progressEl.textContent = err.message || "Import failed";
          btnImportFile.value = "";
        } finally {
          btnImportFile.disabled = false;
        }
      });
    }

    // MCP Integration: Send to Premiere Pro
    const btnMcpPremiere = $("spMcpPremiere");
    const btnMcpBlender = $("spMcpBlender");
    const btnMcpFinalDraft = $("spMcpFinalDraft");
    const mcpStatus = $("spMcpStatus");

    // MCP Integration helper: render status message + clickable download/open links
    function setSpMcpResult(msg, links = [], isErr = false) {
      if (!mcpStatus) return;
      mcpStatus.style.color = isErr ? "#f87171" : "#34d399";
      mcpStatus.textContent = "";
      const span = document.createElement("span");
      span.textContent = msg;
      mcpStatus.appendChild(span);
      links.forEach(({ label, href, external }) => {
        if (!href) return;
        const a = document.createElement("a");
        a.href = href;
        a.textContent = label;
        a.style.cssText = "margin-left:8px;color:#38bdf8;text-decoration:underline;font-weight:600";
        if (external) {
          a.target = "_blank";
          a.rel = "noopener noreferrer";
        } else {
          a.download = "";
        }
        mcpStatus.appendChild(a);
      });
    }

    if (btnMcpPremiere) {
      btnMcpPremiere.addEventListener("click", async () => {
        const selProj = $("proj");
        const slug = (selProj && selProj.value) || activeProject || "";
        if (!slug) { alert("Pick a book first."); return; }
        try {
          btnMcpPremiere.disabled = true;
          btnMcpPremiere.textContent = "🎬 Exporting for Premiere…";
          setSpMcpResult("Auto-exporting FDX & Premiere Pro XML…", [], false);
          const result = await callApi("/api/mcp/premiere/import_fdx", { project: slug });
          if (result.error) throw new Error(result.error);
          const links = [];
          if (result.xml_url) links.push({ label: "⬇ Download Premiere XML", href: result.xml_url });
          if (result.fdx_url) links.push({ label: "⬇ Download .fdx", href: result.fdx_url });
          setSpMcpResult(`✓ ${result.message || "Ready for Premiere Pro"}`, links, false);
        } catch (err) {
          console.error("Premiere MCP failed:", err);
          setSpMcpResult("Error: " + (err.message || err), [], true);
        } finally {
          btnMcpPremiere.disabled = false;
          btnMcpPremiere.textContent = "🎬 Send to Premiere Pro";
        }
      });
    }

    // MCP Integration: Generate Previs with Blender
    if (btnMcpBlender) {
      btnMcpBlender.addEventListener("click", async () => {
        const selProj = $("proj");
        const slug = (selProj && selProj.value) || activeProject || "";
        if (!slug) { alert("Pick a book first."); return; }
        const s = spScenesData[spActiveIdx];
        if (!s) { alert("Select a scene first."); return; }
        try {
          btnMcpBlender.disabled = true;
          btnMcpBlender.textContent = "🎯 Generating…";
          setSpMcpResult(`Generating 3D previs for ${s.id}…`, [], false);
          const result = await callApi("/api/mcp/blender/generate_previs", { project: slug, scene_id: s.id });
          if (result.error) throw new Error(result.error);
          const links = [];
          if (result.script_url) links.push({ label: `⬇ Download previs_${s.id}.py`, href: result.script_url });
          setSpMcpResult(`✓ ${result.message || "Previs generated"}`, links, false);
        } catch (err) {
          console.error("Blender MCP failed:", err);
          setSpMcpResult("Error: " + (err.message || err), [], true);
        } finally {
          btnMcpBlender.disabled = false;
          btnMcpBlender.textContent = "🎯 Generate Previs (Blender)";
        }
      });
    }

    // MCP Integration: Open in Final Draft Web via Playwright
    if (btnMcpFinalDraft) {
      btnMcpFinalDraft.addEventListener("click", async () => {
        const selProj = $("proj");
        const slug = (selProj && selProj.value) || activeProject || "";
        if (!slug) { alert("Pick a book first."); return; }
        try {
          btnMcpFinalDraft.disabled = true;
          btnMcpFinalDraft.textContent = "📝 Preparing Final Draft…";
          setSpMcpResult("Auto-exporting FDX for Final Draft…", [], false);
          const result = await callApi("/api/mcp/playwright/finaldraft_import", { project: slug, project_title: slug });
          if (result.error) throw new Error(result.error);
          const links = [];
          if (result.fdx_url) links.push({ label: "⬇ Download screenplay.fdx", href: result.fdx_url });
          if (result.open_url) links.push({ label: "↗ Open Final Draft", href: result.open_url, external: true });
          setSpMcpResult(`✓ ${result.message || "Ready for Final Draft"}`, links, false);
        } catch (err) {
          console.error("Playwright MCP failed:", err);
          setSpMcpResult("Error: " + (err.message || err), [], true);
        } finally {
          btnMcpFinalDraft.disabled = false;
          btnMcpFinalDraft.textContent = "📝 Open in Final Draft Web";
        }
      });
    }

    // Helper: convert File to base64
    function fileToBase64(file) {
      return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result.split(",")[1] || "");
        reader.onerror = reject;
        reader.readAsDataURL(file);
      });
    }

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

        // Show the workbench tab panel (and mount lazy workspace widgets if needed)
        const wsMap = { "panel-apps": "apps", "panel-compare": "canvas-compare", "panel-models": "models-hardware" };
        if (wsMap[targetId] && typeof window.activateWorkspaceTab === "function") {
          window.activateWorkspaceTab(wsMap[targetId], true);
        }
        document.querySelectorAll(".tab-panel").forEach(p => {
          const isMatch = p.id === targetId;
          p.classList.toggle("active", isMatch);
          if (isMatch) p.classList.remove("hidden");
        });
        const targetPanel = $(targetId);
        if (targetPanel) {
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

    // 3. Load & render interactive scene-by-scene cast & location continuity locks
    const renderV2ContLocks = (lkData) => {
      const sm = (lkData && lkData.summary) || {};
      const scenes = (lkData && Array.isArray(lkData.scenes)) ? lkData.scenes : [];
      const allChars = (lkData && Array.isArray(lkData.all_characters)) ? lkData.all_characters : [];
      if (locksSum) {
        locksSum.textContent = scenes.length
          ? `${scenes.length} scene(s) · ${sm.characters || 0} costume lock(s), ${sm.locations || 0} location lock(s)`
          : "No planned scenes yet for per-scene locks.";
      }
      if (!locksList) return;
      const wasOpen = new Set([...locksList.querySelectorAll("details[open]")].map(d => d.dataset.sceneId));
      locksList.textContent = "";

      const refToPreviewUrl = (refPath) => {
        const clean = String(refPath || "").replace(/^\/+/, "");
        const prefix = `projects/books/${slug}/`;
        if (clean.startsWith(prefix)) return `/file/${slug}/${clean.slice(prefix.length)}`;
        return "";
      };

      scenes.forEach(s => {
        const det = document.createElement("details");
        det.dataset.sceneId = s.id;
        det.open = wasOpen.has(s.id);
        det.style.cssText = "background:#0a0d14;border:1px solid #1e293b;border-radius:8px;padding:8px 10px;";

        const charsTxt = (s.characters || []).map(c => c.name).join(", ") || "No characters listed";
        const placeName = s.location || (s.place && s.place.name) || "Unspecified set";
        const lockedCharCount = (s.characters || []).filter(c => c.locked && (c.locked.token || c.locked.reference)).length;
        const placeLocked = Boolean(s.place && s.place.locked && s.place.locked.reference);
        const anyLocked = lockedCharCount > 0 || placeLocked;

        const sum = document.createElement("summary");
        sum.style.cssText = "cursor:pointer;display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap;list-style:none;";
        const sumLeft = document.createElement("div");
        sumLeft.innerHTML = `<strong style="color:#f59e0b">${s.id}</strong> <strong style="color:#f8fafc">${s.title || ""}</strong> &mdash; <span style="color:#cbd5e1">Cast: ${charsTxt}</span> · <span style="color:#94a3b8">Set: ${placeName}</span>`;
        const sumBadge = document.createElement("span");
        sumBadge.className = "status-badge " + (anyLocked ? "status-badge--synced" : "");
        sumBadge.style.fontSize = "0.7rem";
        sumBadge.textContent = anyLocked
          ? `🔒 Locked (${lockedCharCount + (placeLocked ? 1 : 0)})`
          : "Unlocked (click to edit)";
        sum.appendChild(sumLeft);
        sum.appendChild(sumBadge);
        det.appendChild(sum);

        const body = document.createElement("div");
        body.style.cssText = "margin-top:10px;padding-top:10px;border-top:1px solid #1e293b;display:flex;flex-direction:column;gap:10px;";
        const sceneMsg = document.createElement("div");
        sceneMsg.style.cssText = "font-size:11px;color:#34d399;min-height:14px;";

        const sendLock = async (payload, okMsg) => {
          sceneMsg.style.color = "#fbbf24";
          sceneMsg.textContent = "Saving lock…";
          try {
            const updated = await callApi("/api/cast_lock", { project: slug, scene: s.id, ...payload });
            renderV2ContLocks(updated);
            const reopened = locksList.querySelector(`details[data-scene-id="${s.id}"]`);
            if (reopened) {
              reopened.open = true;
              const m = reopened.querySelector(".v2-cont-lock-msg");
              if (m) { m.style.color = "#34d399"; m.textContent = okMsg; }
            }
          } catch (err) {
            sceneMsg.style.color = "#f87171";
            sceneMsg.textContent = "Could not save lock: " + (err.message || err);
          }
        };

        const addCharEditor = (c) => {
          const isLocked = Boolean(c.locked && (c.locked.token || c.locked.reference));
          const card = document.createElement("div");
          card.style.cssText = "padding:8px 10px;background:#111827;border:1px solid " + (isLocked ? "rgba(16,185,129,0.45)" : "#263248") + ";border-radius:6px;display:flex;flex-direction:column;gap:6px;";

          const hdr = document.createElement("div");
          hdr.style.cssText = "display:flex;align-items:center;justify-content:space-between;gap:8px;flex-wrap:wrap;";
          const nm = document.createElement("strong");
          nm.style.color = "#f8fafc";
          nm.textContent = c.name;
          const pill = document.createElement("span");
          pill.style.cssText = isLocked
            ? "padding:1px 7px;border-radius:999px;background:rgba(16,185,129,0.16);border:1px solid rgba(16,185,129,0.4);color:#6ee7b7;font-size:10px;font-weight:600;"
            : "padding:1px 7px;border-radius:999px;background:rgba(148,163,184,0.12);color:#94a3b8;font-size:10px;";
          pill.textContent = isLocked ? "🔒 Scene Lock Active" : "Using Default Look";
          hdr.appendChild(nm);
          hdr.appendChild(pill);
          card.appendChild(hdr);

          const ta = document.createElement("textarea");
          ta.rows = 2;
          ta.maxLength = 400;
          ta.value = (c.locked && c.locked.token) || c.current || "";
          ta.placeholder = `Scene-specific costume, prop, or appearance for ${c.name} in ${s.id} (max 400 chars)…`;
          ta.style.cssText = "width:100%;padding:6px 8px;background:#070b12;color:#f8fafc;border:1px solid #334155;border-radius:5px;font:inherit;font-size:11px;";
          card.appendChild(ta);

          const ctrlRow = document.createElement("div");
          ctrlRow.style.cssText = "display:flex;align-items:center;gap:8px;flex-wrap:wrap;";

          const thumb = document.createElement("img");
          thumb.style.cssText = "width:34px;height:34px;border-radius:4px;object-fit:cover;border:1px solid #334155;display:none;";
          const sel = document.createElement("select");
          sel.style.cssText = "flex:1;min-width:180px;background:#070b12;color:#e2e8f0;border:1px solid #334155;border-radius:5px;padding:4px 6px;font-size:11px;";
          sel.appendChild(new Option("(Use default character picture)", ""));
          (c.references || []).forEach(ref => {
            sel.appendChild(new Option(ref.split("/").slice(-2).join("/"), ref));
          });
          sel.value = (c.locked && c.locked.reference) || "";
          const syncThumb = () => {
            const u = refToPreviewUrl(sel.value);
            if (u) { thumb.src = u; thumb.style.display = "block"; } else { thumb.style.display = "none"; }
          };
          syncThumb();
          sel.addEventListener("change", syncThumb);

          const btnLock = document.createElement("button");
          btnLock.type = "button";
          btnLock.className = "btn btn--primary";
          btnLock.style.cssText = "padding:4px 10px;font-size:11px;";
          btnLock.textContent = "🔒 Lock";
          btnLock.addEventListener("click", () => {
            const rawTok = ta.value.trim();
            const tok = (rawTok === (c.current || "").trim() && !(c.locked && c.locked.token) && sel.value) ? "" : rawTok;
            if (!tok && !sel.value) {
              sceneMsg.style.color = "#fbbf24";
              sceneMsg.textContent = `Edit ${c.name}'s costume description or pick a reference image to lock ${s.id}.`;
              return;
            }
            sendLock({ kind: "character", name: c.name, token: tok, reference: sel.value }, `✓ Locked ${c.name} for ${s.id}.`);
          });

          const btnUnlock = document.createElement("button");
          btnUnlock.type = "button";
          btnUnlock.className = "btn btn--ghost";
          btnUnlock.style.cssText = "padding:4px 10px;font-size:11px;color:#f87171;";
          btnUnlock.textContent = "🔓 Unlock";
          btnUnlock.disabled = !isLocked;
          btnUnlock.addEventListener("click", () => {
            sendLock({ kind: "character", name: c.name, token: "", reference: "" }, `✓ Unlocked ${c.name} in ${s.id}.`);
          });

          ctrlRow.appendChild(thumb);
          ctrlRow.appendChild(sel);
          ctrlRow.appendChild(btnLock);
          ctrlRow.appendChild(btnUnlock);
          card.appendChild(ctrlRow);
          body.appendChild(card);
        };

        if ((s.characters || []).length) {
          s.characters.forEach(addCharEditor);
        } else {
          const noneMsg = document.createElement("div");
          noneMsg.style.cssText = "color:#94a3b8;font-size:11px;";
          noneMsg.textContent = "No characters listed in this scene yet — use 'Add character lock' below to lock one.";
          body.appendChild(noneMsg);
        }

        // Allow locking another continuity-book character into this scene
        const presentSet = new Set((s.characters || []).map(c => String(c.name || "").toLowerCase()));
        const extraChars = allChars.filter(c => c.name && !presentSet.has(c.name.toLowerCase()));
        if (extraChars.length) {
          const addRow = document.createElement("div");
          addRow.style.cssText = "display:flex;align-items:center;gap:6px;flex-wrap:wrap;";
          const addSel = document.createElement("select");
          addSel.style.cssText = "background:#070b12;color:#cbd5e1;border:1px solid #334155;border-radius:5px;padding:3px 6px;font-size:11px;";
          addSel.appendChild(new Option("➕ Add character lock to this scene…", ""));
          extraChars.forEach(ec => addSel.appendChild(new Option(ec.name, ec.name)));
          addSel.addEventListener("change", () => {
            const pick = extraChars.find(ec => ec.name === addSel.value);
            if (!pick) return;
            addCharEditor({ name: pick.name, current: pick.token || "", locked: {}, references: pick.references || [] });
            addSel.value = "";
          });
          addRow.appendChild(addSel);
          body.appendChild(addRow);
        }

        // Location / Set Reference Lock row
        const locCard = document.createElement("div");
        locCard.style.cssText = "padding:8px 10px;background:#111827;border:1px solid " + (placeLocked ? "rgba(16,185,129,0.45)" : "#263248") + ";border-radius:6px;display:flex;align-items:center;gap:8px;flex-wrap:wrap;";
        const locLbl = document.createElement("strong");
        locLbl.style.color = "#f59e0b";
        locLbl.textContent = `🏛️ Set: ${placeName}`;
        const locSel = document.createElement("select");
        locSel.style.cssText = "flex:1;min-width:180px;background:#070b12;color:#e2e8f0;border:1px solid #334155;border-radius:5px;padding:4px 6px;font-size:11px;";
        locSel.appendChild(new Option("(Use default set look)", ""));
        ((s.place && s.place.references) || []).forEach(ref => {
          locSel.appendChild(new Option(ref.split("/").slice(-2).join("/"), ref));
        });
        locSel.value = (s.place && s.place.locked && s.place.locked.reference) || "";
        const btnLocLock = document.createElement("button");
        btnLocLock.type = "button";
        btnLocLock.className = "btn btn--secondary";
        btnLocLock.style.cssText = "padding:4px 10px;font-size:11px;";
        btnLocLock.textContent = locSel.value ? "🔒 Lock Set" : "🔓 Unlock Set";
        locSel.addEventListener("change", () => { btnLocLock.textContent = locSel.value ? "🔒 Lock Set" : "🔓 Unlock Set"; });
        btnLocLock.addEventListener("click", () => {
          sendLock({ kind: "location", reference: locSel.value }, locSel.value ? `✓ Locked set reference for ${s.id}.` : `✓ Unlocked set reference for ${s.id}.`);
        });
        locCard.appendChild(locLbl);
        locCard.appendChild(locSel);
        locCard.appendChild(btnLocLock);
        body.appendChild(locCard);

        sceneMsg.className = "v2-cont-lock-msg";
        body.appendChild(sceneMsg);
        det.appendChild(body);
        locksList.appendChild(det);
      });
    };

    try {
      const lk = await callApi(`/api/cast_lock?project=${encodeURIComponent(slug)}`);
      renderV2ContLocks(lk);
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
        const cfg = _v2JobConfigForStep(7);
        if (statusEl) statusEl.textContent = `Starting continuity book generation for "${slug}"…`;
        if (logEl) logEl.classList.add("hidden");
        try {
          const o = typeof window.options === "function" ? window.options() : {};
          await callApi("/api/continuity_book", {
            project: slug,
            engine: o.engine || "claude",
            claude_model: o.claude_model,
          });
          watchV2JobProgress({ ...cfg, fresh: true });
        } catch (err) {
          if (/already running/i.test(String(err.message || ""))) {
            watchV2JobProgress({ ...cfg, fresh: false });
          } else {
            if (statusEl) statusEl.textContent = "Error: " + err.message;
            btnGenCb.disabled = false;
          }
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
  let v2SelectedHardware = "computer";
  let v2GpuProfile = null;
  let v2OmniInteractions = {};

  function selectV2Hardware(hwKey) {
    const key = V2_HW_LABELS[hwKey] ? hwKey : "computer";
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
    const localGpuBadge = $("v2LocalGpuBadge");
    const localVideoBadge = $("v2LocalVideoBadge");
    const selProj = $("proj");
    const slug = (selProj && selProj.value) || activeProject || "";

    try {
      const prof = await callApi("/api/gpu_profile");
      if (prof && typeof prof === "object") {
        v2GpuProfile = prof;
        const legacyOn = Boolean(prof.legacy_cloud);
        document.querySelectorAll('.v2-hw-card[data-legacy-cloud="1"]').forEach(card => {
          card.style.display = legacyOn ? "" : "none";
        });
        if (localGpuBadge) {
          localGpuBadge.textContent = `✓ ${prof.name || "Local GPU"} (${prof.vram_gb || 0} GB · ${prof.tier || "local"})`;
          localGpuBadge.className = "status-badge status-badge--synced";
        }
        if (localVideoBadge) {
          if (prof.tier === "mac_8g_lite" || prof.supports_local_video === false) {
            localVideoBadge.textContent = `${prof.vram_gb || 8} GB Mac · Motion Animatic Active (Heavy Wan 14B Gated)`;
            localVideoBadge.className = "status-badge status-badge--working";
          } else {
            localVideoBadge.textContent = `✓ ${prof.name || "GPU"} (${prof.vram_gb || 48} GB · Wan 2.2 + ComfyUI Ready)`;
            localVideoBadge.className = "status-badge status-badge--synced";
          }
        }
      }
    } catch (e) {}

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
    let savedHw = "computer";
    try { savedHw = localStorage.getItem("studio_v2_hardware") || "computer"; } catch (e) {}
    selectV2Hardware(savedHw);

    const btnLocalVid = $("bV2RunLocalVideo");
    const btnLocalVidBatch = $("bV2RunLocalVideoBatch");
    const btnReloadVid = $("bV2ReloadVideos");
    if (btnReloadVid) btnReloadVid.addEventListener("click", () => loadV2VideoClips());
    if (btnLocalVid) {
      btnLocalVid.addEventListener("click", async () => {
        const slug = ($("proj")?.value || activeProject || "").trim();
        if (!slug) return;
        const shotId = $("v2LocalVideoShotSelect")?.value || "S001-01";
        const eng = $("v2LocalVideoEngine")?.value || "auto";
        const dur = parseInt($("v2LocalVideoDuration")?.value || "4", 10) || 4;
        const st = $("v2LocalVideoStatus");
        const stopBusy = startBusyFeedback(btnLocalVid, $("v2LocalVideoCard"), `Synthesizing ${shotId} video locally…`);
        if (st) { st.style.color = "#34d399"; st.textContent = `Synthesizing ${shotId} (${dur}s) via ${eng}…`; }
        try {
          const res = await callApi("/api/v2_video_render", { project: slug, id: shotId, engine: eng, duration: dur });
          if (st) st.textContent = `✓ Rendered ${shotId} (${res.engine}) -> ${res.video_url}`;
          await loadV2VideoClips();
        } catch (err) {
          if (st) { st.style.color = "#f87171"; st.textContent = "Local video synthesis failed: " + (err.message || err); }
        } finally {
          stopBusy();
        }
      });
    }
    if (btnLocalVidBatch) {
      btnLocalVidBatch.addEventListener("click", async () => {
        const slug = ($("proj")?.value || activeProject || "").trim();
        if (!slug) return;
        const eng = $("v2LocalVideoEngine")?.value || "auto";
        const dur = parseInt($("v2LocalVideoDuration")?.value || "4", 10) || 4;
        const st = $("v2LocalVideoStatus");
        const stopBusy = startBusyFeedback(btnLocalVidBatch, $("v2LocalVideoCard"), "Synthesizing all keyframed shots…");
        try {
          const kf = await callApi(`/api/v2_keyframes?project=${encodeURIComponent(slug)}`);
          const shots = (kf.scenes || []).flatMap(sc => sc.shots || []).filter(s => s.has_image);
          if (!shots.length) {
            if (st) { st.style.color = "#f87171"; st.textContent = "No rendered keyframes found yet. Generate keyframes in Step 17 first."; }
            return;
          }
          for (let i = 0; i < shots.length; i++) {
            const s = shots[i];
            if (st) { st.style.color = "#34d399"; st.textContent = `Synthesizing ${s.id} (${i + 1}/${shots.length})…`; }
            await callApi("/api/v2_video_render", { project: slug, id: s.id, prompt: s.prompt, engine: eng, duration: dur });
          }
          if (st) st.textContent = `✓ Rendered ${shots.length} shot video clip(s)!`;
          await loadV2VideoClips();
        } catch (err) {
          if (st) { st.style.color = "#f87171"; st.textContent = "Batch video synthesis stopped: " + (err.message || err); }
        } finally {
          stopBusy();
        }
      });
    }

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

  // ===== SHARED CHARACTER TYPES & VISUAL STYLES REGISTRY =====
  let v2CharTypesCache = null;

  async function loadV2CharacterTypes(force = false) {
    if (v2CharTypesCache && !force) return v2CharTypesCache;
    try {
      const data = await callApi("/api/character_types");
      if (data && Array.isArray(data.styles) && Array.isArray(data.archetypes)) {
        v2CharTypesCache = data;
        // Sync V2_STYLE_RECIPES map with full registry
        data.styles.forEach(s => {
          V2_STYLE_RECIPES[s.id] = {
            id: s.id,
            label: s.name || s.label || s.id,
            icon: s.icon || "🎨",
            category: s.category || "Custom",
            summary: s.summary || "",
            positives: s.positives || "",
            negatives: s.negatives || "",
            motion_cadence: s.motion_cadence || "",
            sample_url: s.sample_url || "",
            custom: Boolean(s.custom),
          };
        });
        return v2CharTypesCache;
      }
    } catch (e) {}
    return v2CharTypesCache || { styles: [], archetypes: [], style_categories: [], archetype_categories: [] };
  }
  window.loadV2CharacterTypes = loadV2CharacterTypes;

  function populateArchetypeSelect(selEl, selectedVal = "") {
    if (!selEl) return;
    const reg = v2CharTypesCache || { archetypes: [], archetype_categories: [] };
    selEl.textContent = "";
    const optAuto = document.createElement("option");
    optAuto.value = "";
    optAuto.textContent = "Auto-detect from description";
    selEl.appendChild(optAuto);

    const byCat = new Map();
    (reg.archetypes || []).forEach(a => {
      const cat = a.category || "Other";
      if (!byCat.has(cat)) byCat.set(cat, []);
      byCat.get(cat).push(a);
    });
    const cats = (reg.archetype_categories && reg.archetype_categories.length)
      ? reg.archetype_categories.filter(c => byCat.has(c)).concat([...byCat.keys()].filter(c => !reg.archetype_categories.includes(c)))
      : [...byCat.keys()];
    cats.forEach(cat => {
      const grp = document.createElement("optgroup");
      grp.label = cat;
      (byCat.get(cat) || []).forEach(a => {
        const opt = document.createElement("option");
        opt.value = a.id;
        opt.textContent = `${a.icon ? a.icon + " " : ""}${a.name || a.label || a.id}${a.custom ? " ★" : ""}`;
        grp.appendChild(opt);
      });
      selEl.appendChild(grp);
    });
    if (selectedVal) selEl.value = selectedVal;
  }

  function populateStyleSelect(selEl, selectedVal = "", emptyLabel = "Book Default (Step 09)") {
    if (!selEl) return;
    const reg = v2CharTypesCache || { styles: [], style_categories: [] };
    selEl.textContent = "";
    if (emptyLabel !== null) {
      const optDef = document.createElement("option");
      optDef.value = "";
      optDef.textContent = emptyLabel;
      selEl.appendChild(optDef);
    }
    const byCat = new Map();
    (reg.styles || []).forEach(s => {
      const cat = s.category || "Other";
      if (!byCat.has(cat)) byCat.set(cat, []);
      byCat.get(cat).push(s);
    });
    const cats = (reg.style_categories && reg.style_categories.length)
      ? reg.style_categories.filter(c => byCat.has(c)).concat([...byCat.keys()].filter(c => !reg.style_categories.includes(c)))
      : [...byCat.keys()];
    cats.forEach(cat => {
      const grp = document.createElement("optgroup");
      grp.label = cat;
      (byCat.get(cat) || []).forEach(s => {
        const opt = document.createElement("option");
        opt.value = s.id;
        opt.textContent = `${s.icon ? s.icon + " " : ""}${s.name || s.label || s.id}${s.custom ? " ★" : ""}`;
        grp.appendChild(opt);
      });
      selEl.appendChild(grp);
    });
    if (selectedVal) selEl.value = selectedVal;
  }

  // ===== STEP 08: CAST & CHARACTERS =====
  async function loadV2Cast() {
    const selProj = $("proj");
    const slug = (selProj && selProj.value) || activeProject || "";
    const grid = $("v2CastGrid");
    const summaryEl = $("v2CastSummary");
    const badgeEl = $("v2CastBadge");

    if (!grid) return;

    await loadV2CharacterTypes();
    populateArchetypeSelect($("v2CastNewArchetype"), "");
    populateStyleSelect($("v2CastNewStyle"), "", "Book Default (Step 09)");
    populateStyleSelect($("v2CastImportStyle"), "", "Book Default (Step 09)");

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

    // 5. Load per-character scene/location wardrobe states & cast reference pictures
    let wardrobeStatesMap = {};
    let castRefsList = [];
    await Promise.all([
      (async () => {
        try {
          const ws = await callApi(`/api/v2_wardrobe_states?project=${encodeURIComponent(slug)}`);
          wardrobeStatesMap = (ws && ws.states) || {};
        } catch (e) {}
      })(),
      (async () => {
        try {
          const rr = await callApi(`/api/v2_cast_references?project=${encodeURIComponent(slug)}`);
          castRefsList = (rr && Array.isArray(rr.references)) ? rr.references : [];
        } catch (e) {}
      })(),
    ]);

    const _normSlug = s => String(s || "").trim().toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "");
    const findCharRefs = (charName) => {
      const target = _normSlug(charName);
      const step08 = castRefsList.find(r => r.source === "Step 08 Reference" && (_normSlug(r.character) === target || r.slug === target));
      const step10 = castRefsList.find(r => r.source === "Step 10 Front View" && (_normSlug(r.character) === target || r.slug === target));
      return { step08, step10, primary: step08 || step10 || null };
    };
    const archById = new Map(((v2CharTypesCache && v2CharTypesCache.archetypes) || []).map(a => [a.id, a]));

    const allChars = [...merged.values()].sort((a, b) =>
      String(a.name || "").localeCompare(String(b.name || ""), undefined, { sensitivity: "base" })
    );
    if (summaryEl) {
      summaryEl.innerHTML = `<strong style="color:#f59e0b">${allChars.length} character(s)</strong> found for <strong>${slug}</strong>` +
        (allChars.length ? " — upload reference pictures, pick character types or mixed-media styles, edit dossiers, or add characters." : " — click <strong>➕ Add Character</strong> or <strong>🔄 Sync from Book</strong> to populate your cast.");
    }
    if (badgeEl) {
      badgeEl.textContent = allChars.length ? `✓ ${allChars.length} Characters` : "No Characters Yet";
      badgeEl.className = "status-badge " + (allChars.length ? "status-badge--synced" : "status-badge--drift");
    }

    // Populate Step 08 top Import Photo character dropdown (just like Step 11 Sets)
    const impCharSel = $("v2CastImportChar");
    if (impCharSel) {
      const prevChar = impCharSel.value;
      impCharSel.textContent = "";
      allChars.forEach(ch => {
        const opt = document.createElement("option");
        opt.value = ch.name;
        opt.textContent = ch.name;
        impCharSel.appendChild(opt);
      });
      if (prevChar && allChars.some(ch => ch.name === prevChar)) impCharSel.value = prevChar;
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

      // Reference Picture Upload / Preview (Original Photo -> Converted Film-Style Front View, mirroring Step 11 Sets)
      const refInfo = findCharRefs(c.name);
      const refBox = document.createElement("div");
      refBox.style.cssText = "display:flex;align-items:center;gap:10px;margin:8px 0;padding:8px;background:#0a0d14;border:1px solid #232d3f;border-radius:6px;flex-wrap:wrap;";
      const thumbsWrap = document.createElement("div");
      thumbsWrap.style.cssText = "display:flex;align-items:center;gap:6px;flex-shrink:0;";
      const makeThumb = (url, labelTxt, borderCol) => {
        const box = document.createElement("div");
        box.style.cssText = `position:relative;width:64px;height:64px;flex-shrink:0;border-radius:6px;overflow:hidden;background:#020617;border:1px solid ${borderCol};display:flex;align-items:center;justify-content:center;color:#64748b;font-size:10px;text-align:center;`;
        if (url) {
          const im = document.createElement("img");
          im.src = url + "?t=" + Date.now();
          im.alt = `${c.name} ${labelTxt}`;
          im.style.cssText = "width:100%;height:100%;object-fit:cover;cursor:zoom-in;";
          im.addEventListener("click", () => window.open(url, "_blank"));
          box.appendChild(im);
          if (labelTxt) {
            const tag = document.createElement("span");
            tag.textContent = labelTxt;
            tag.style.cssText = "position:absolute;bottom:0;left:0;right:0;background:rgba(2,6,23,.78);color:#e2e8f0;font-size:9px;text-align:center;padding:1px 2px;";
            box.appendChild(tag);
          }
        } else {
          box.textContent = labelTxt || "No Ref";
        }
        return box;
      };
      if (refInfo.step08 && refInfo.step10) {
        thumbsWrap.appendChild(makeThumb(refInfo.step08.url, "Photo", "#f59e0b"));
        const arr = document.createElement("span");
        arr.textContent = "→";
        arr.style.cssText = "color:#94a3b8;font-weight:700;font-size:12px;";
        thumbsWrap.appendChild(arr);
        thumbsWrap.appendChild(makeThumb(refInfo.step10.url, "Film Style", "#34d399"));
      } else if (refInfo.primary && refInfo.primary.url) {
        thumbsWrap.appendChild(makeThumb(refInfo.primary.url, refInfo.step08 ? "Photo" : "Front", refInfo.step08 ? "#f59e0b" : "#334155"));
      } else {
        thumbsWrap.appendChild(makeThumb("", "No Ref", "#334155"));
      }
      refBox.appendChild(thumbsWrap);

      const refMeta = document.createElement("div");
      refMeta.style.cssText = "flex:1;min-width:160px;display:flex;flex-direction:column;gap:4px;";
      const refLbl = document.createElement("div");
      refLbl.style.cssText = "font-size:11px;color:#e2e8f0;font-weight:600;";
      refLbl.textContent = refInfo.step08
        ? (refInfo.step10 ? "📷 Photo Imported & Styled (Step 08 → Step 10)" : "📷 Reference Photo Uploaded (ready to convert to film style)")
        : (refInfo.step10 ? "📷 Using Step 10 Front View (import a photo to override)" : "📷 Cast Reference Picture (optional)");
      refMeta.appendChild(refLbl);

      const refBtns = document.createElement("div");
      refBtns.style.cssText = "display:flex;gap:6px;flex-wrap:wrap;align-items:center;";
      const refFileIn = document.createElement("input");
      refFileIn.type = "file";
      refFileIn.accept = "image/*";
      refFileIn.style.display = "none";
      const btnUploadRef = document.createElement("button");
      btnUploadRef.type = "button";
      btnUploadRef.className = "btn btn--secondary";
      btnUploadRef.style.cssText = "padding:3px 9px;font-size:11px;";
      btnUploadRef.textContent = refInfo.step08 ? "📷 Replace Photo & Convert" : "📷 Import Photo & Convert";
      btnUploadRef.title = "Import a reference photo and immediately convert it into your film's visual style";
      btnUploadRef.addEventListener("click", () => refFileIn.click());
      refFileIn.addEventListener("change", () => {
        const f = refFileIn.files && refFileIn.files[0];
        if (!f) return;
        const reader = new FileReader();
        reader.onload = async () => {
          const stopBusy = startBusyFeedback(btnUploadRef, refBox, `Importing & converting ${c.name}…`);
          try {
            await callApi("/api/v2_character_ref_upload", {
              project: slug,
              character: c.name,
              image_base64: reader.result,
              convert_now: true,
              style_id: c.style_override || "",
              style_strength: 0.75,
              engine: _currentV2VisualEngine(),
            });
            if (window.loadPCastRefs) window.loadPCastRefs();
            await loadV2Cast();
          } catch (err) {
            alert("Reference import & convert failed: " + (err.message || err));
          } finally {
            stopBusy();
          }
        };
        reader.readAsDataURL(f);
      });
      refBtns.appendChild(btnUploadRef);
      refBtns.appendChild(refFileIn);

      if (refInfo.step08) {
        const btnConvertRef = document.createElement("button");
        btnConvertRef.type = "button";
        btnConvertRef.className = "btn btn--primary";
        btnConvertRef.style.cssText = "padding:3px 9px;font-size:11px;";
        btnConvertRef.textContent = refInfo.step10 ? "↺ Re-convert to Film Style" : "🎨 Convert to Film Style";
        btnConvertRef.addEventListener("click", async () => {
          const stopBusy = startBusyFeedback(btnConvertRef, refBox, `Converting ${c.name} to film style…`);
          try {
            await callApi("/api/v2_turnaround_restyle", {
              project: slug,
              character: c.name,
              style_id: c.style_override || "",
              use_cast_ref: true,
              engine: _currentV2VisualEngine(),
            });
            if (window.loadPCastRefs) window.loadPCastRefs();
            await loadV2Cast();
          } catch (err) {
            alert("Conversion failed: " + (err.message || err));
          } finally {
            stopBusy();
          }
        });
        refBtns.appendChild(btnConvertRef);

        const btnDelRef = document.createElement("button");
        btnDelRef.type = "button";
        btnDelRef.className = "btn btn--ghost";
        btnDelRef.style.cssText = "padding:3px 8px;font-size:11px;color:#f87171;";
        btnDelRef.textContent = "🗑️ Remove Ref";
        btnDelRef.addEventListener("click", async () => {
          if (!confirm(`Remove uploaded reference photo for ${c.name}?`)) return;
          btnDelRef.disabled = true;
          try {
            await callApi("/api/v2_character_ref_delete", { project: slug, character: c.name });
            if (window.loadPCastRefs) window.loadPCastRefs();
            await loadV2Cast();
          } catch (err) {
            alert("Could not remove reference: " + (err.message || err));
            btnDelRef.disabled = false;
          }
        });
        refBtns.appendChild(btnDelRef);
      }
      refMeta.appendChild(refBtns);
      refBox.appendChild(refMeta);
      card.appendChild(refBox);

      // Character Type (42+ archetypes + custom) & Visual Style Override (30+ styles for mixed-media films)
      const typeRow = document.createElement("div");
      typeRow.style.cssText = "display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-bottom:4px;";
      const archWrap = document.createElement("div");
      const archLbl = document.createElement("label");
      archLbl.className = "f";
      archLbl.textContent = "Character Type";
      const archSel = document.createElement("select");
      archSel.style.cssText = "width:100%;padding:5px 7px;background:#0a0d14;color:#f8fafc;border:1px solid #334155;border-radius:6px;font-size:11px;";
      const savedArch = (c.rawChar && c.rawChar.archetype) || "";
      populateArchetypeSelect(archSel, savedArch);
      archWrap.appendChild(archLbl);
      archWrap.appendChild(archSel);

      const styleWrap = document.createElement("div");
      const styleLbl = document.createElement("label");
      styleLbl.className = "f";
      styleLbl.textContent = "Style Override (Mixed-Media)";
      const styleSel = document.createElement("select");
      styleSel.style.cssText = "width:100%;padding:5px 7px;background:#0a0d14;color:#bae6fd;border:1px solid #334155;border-radius:6px;font-size:11px;";
      const savedStyleOv = (c.rawChar && c.rawChar.style_override) || "";
      populateStyleSelect(styleSel, savedStyleOv, "Book Default (Step 09)");
      styleWrap.appendChild(styleLbl);
      styleWrap.appendChild(styleSel);

      typeRow.appendChild(archWrap);
      typeRow.appendChild(styleWrap);
      card.appendChild(typeRow);

      const archHint = document.createElement("div");
      archHint.style.cssText = "font-size:10px;color:#94a3b8;margin-bottom:4px;min-height:13px;";
      const updateArchHint = () => {
        const a = archById.get(archSel.value);
        archHint.textContent = a && a.hint ? `💡 ${a.hint}` : "";
      };
      updateArchHint();
      archSel.addEventListener("change", updateArchHint);
      card.appendChild(archHint);

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
              archetype: archSel.value || c.rawChar.archetype || "",
              style_override: styleSel.value || "",
            };
            await callApi("/api/characters", { action: "save", character: updated });
          } else {
            await callApi("/api/characters", {
              action: "create",
              series: slug,
              name: c.name,
              description: descTa.value.trim(),
              visual_token: tokInput.value.trim(),
              archetype: archSel.value || "",
              style_override: styleSel.value || "",
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

    // Step 08 Top Import Photo & Convert to Film Style panel (mirrors Step 11 Sets Import)
    const btnCastImpToggle = $("bV2CastImportToggle");
    const castImpForm = $("v2CastImportForm");
    const btnCastImpCancel = $("bV2CastImportCancel");
    const castImpFile = $("v2CastImportFile");
    const castImpPrev = $("v2CastImportPreview");
    const castImpStr = $("v2CastImportStrength");
    const castImpStrVal = $("v2CastImportStrengthVal");
    const btnCastImpConv = $("bV2CastImportConvert");
    const btnCastImpOnly = $("bV2CastImportOnly");
    const castImpMsg = $("v2CastImportMsg");
    let pendingCastImpDataUrl = "";
    let pendingCastImpFilename = "";

    if (castImpStr && castImpStrVal) {
      castImpStr.addEventListener("input", () => { castImpStrVal.textContent = Number(castImpStr.value).toFixed(2); });
    }
    if (btnCastImpToggle && castImpForm) {
      btnCastImpToggle.addEventListener("click", () => {
        const show = castImpForm.classList.contains("hidden") || castImpForm.style.display === "none";
        castImpForm.classList.toggle("hidden", !show);
        castImpForm.style.display = show ? "flex" : "none";
      });
    }
    if (btnCastImpCancel && castImpForm) {
      btnCastImpCancel.addEventListener("click", () => {
        castImpForm.classList.add("hidden");
        castImpForm.style.display = "none";
      });
    }
    if (castImpFile) {
      castImpFile.addEventListener("change", () => {
        const f = castImpFile.files && castImpFile.files[0];
        if (!f) return;
        pendingCastImpFilename = f.name;
        const reader = new FileReader();
        reader.onload = () => {
          pendingCastImpDataUrl = String(reader.result || "");
          if (castImpPrev) {
            castImpPrev.src = pendingCastImpDataUrl;
            castImpPrev.style.display = "block";
          }
          if (castImpMsg) castImpMsg.textContent = `Ready to import "${f.name}"`;
        };
        reader.readAsDataURL(f);
      });
    }
    async function runTopCastImport(convertNow) {
      const selProj = $("proj");
      const slug = (selProj && selProj.value) || activeProject || "";
      const charName = ($("v2CastImportChar") && $("v2CastImportChar").value) ? $("v2CastImportChar").value.trim() : "";
      const styleId = ($("v2CastImportStyle") && $("v2CastImportStyle").value) ? $("v2CastImportStyle").value.trim() : "";
      const styleNotes = ($("v2CastImportNotes") && $("v2CastImportNotes").value) ? $("v2CastImportNotes").value.trim() : "";
      if (!slug) { if (castImpMsg) castImpMsg.textContent = "Pick a book in Step 01 first."; return; }
      if (!charName) { if (castImpMsg) castImpMsg.textContent = "Select a character first."; return; }
      if (!pendingCastImpDataUrl) { if (castImpMsg) castImpMsg.textContent = "Choose a reference photo file first."; return; }
      const trigBtn = convertNow ? btnCastImpConv : btnCastImpOnly;
      const stopBusy = startBusyFeedback(trigBtn, castImpForm, convertNow ? `Converting photo for ${charName}…` : `Importing photo for ${charName}…`);
      if (castImpMsg) castImpMsg.textContent = convertNow ? `Importing & converting photo for "${charName}"…` : `Importing photo for "${charName}"…`;
      try {
        const res = await callApi("/api/v2_character_ref_upload", {
          project: slug,
          character: charName,
          filename: pendingCastImpFilename || "reference.png",
          image_base64: pendingCastImpDataUrl,
          convert_now: convertNow,
          set_as_front: !convertNow,
          style_id: styleId,
          style_notes: styleNotes,
          style_strength: castImpStr ? parseFloat(castImpStr.value) : 0.75,
          engine: _currentV2VisualEngine(),
        });
        pendingCastImpDataUrl = "";
        pendingCastImpFilename = "";
        if (castImpFile) castImpFile.value = "";
        if (castImpPrev) { castImpPrev.src = ""; castImpPrev.style.display = "none"; }
        if (castImpMsg) {
          castImpMsg.textContent = convertNow
            ? `✓ Imported & converted "${charName}" into ${res.style_name || "film style"}!`
            : `✓ Imported reference photo for "${charName}"!`;
        }
        if (window.loadPCastRefs) window.loadPCastRefs();
        await loadV2Cast();
      } catch (err) {
        if (castImpMsg) castImpMsg.textContent = "Import failed: " + (err.message || err);
      } finally {
        stopBusy();
      }
    }
    if (btnCastImpConv) btnCastImpConv.addEventListener("click", () => runTopCastImport(true));
    if (btnCastImpOnly) btnCastImpOnly.addEventListener("click", () => runTopCastImport(false));

    const btnCustomToggle = $("bV2CastCustomTypeToggle");
    const customForm = $("v2CastCustomTypeForm");
    const btnCustomCancel = $("bV2CastCustomTypeCancel");
    const btnCustomSave = $("bV2CastCustomTypeSave");
    if (btnCustomToggle && customForm) {
      btnCustomToggle.addEventListener("click", () => {
        const show = customForm.classList.contains("hidden");
        customForm.classList.toggle("hidden", !show);
        customForm.style.display = show ? "flex" : "none";
        if (show && $("v2CastCustomTypeName")) $("v2CastCustomTypeName").focus();
      });
    }
    if (btnCustomCancel && customForm) {
      btnCustomCancel.addEventListener("click", () => {
        customForm.classList.add("hidden");
        customForm.style.display = "none";
      });
    }
    if (btnCustomSave) {
      btnCustomSave.addEventListener("click", async () => {
        const label = ($("v2CastCustomTypeName")?.value || "").trim();
        const category = ($("v2CastCustomTypeCat")?.value || "Custom").trim();
        const hint = ($("v2CastCustomTypeHint")?.value || "").trim();
        const cMsg = $("v2CastCustomTypeMsg");
        if (!label) { if (cMsg) cMsg.textContent = "Enter a character type name first."; return; }
        btnCustomSave.disabled = true;
        if (cMsg) cMsg.textContent = "Saving custom character type…";
        try {
          await callApi("/api/character_types_custom", { kind: "archetype", name: label, category, hint, icon: "✨" });
          await loadV2CharacterTypes(true);
          if ($("v2CastCustomTypeName")) $("v2CastCustomTypeName").value = "";
          if ($("v2CastCustomTypeHint")) $("v2CastCustomTypeHint").value = "";
          if (customForm) { customForm.classList.add("hidden"); customForm.style.display = "none"; }
          if (cMsg) cMsg.textContent = "";
          await loadV2Cast();
        } catch (err) {
          if (cMsg) cMsg.textContent = "Error: " + (err.message || err);
        } finally {
          btnCustomSave.disabled = false;
        }
      });
    }

    if (btnCreate) {
      btnCreate.addEventListener("click", async () => {
        const selProj = $("proj");
        const slug = (selProj && selProj.value) || activeProject || "";
        const name = ($("v2CastNewName") || {}).value ? $("v2CastNewName").value.trim() : "";
        const token = ($("v2CastNewToken") || {}).value ? $("v2CastNewToken").value.trim() : "";
        const desc = ($("v2CastNewDesc") || {}).value ? $("v2CastNewDesc").value.trim() : "";
        const archetype = ($("v2CastNewArchetype") || {}).value || "";
        const style_override = ($("v2CastNewStyle") || {}).value || "";
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
            archetype,
            style_override,
          });
          if ($("v2CastNewName")) $("v2CastNewName").value = "";
          if ($("v2CastNewToken")) $("v2CastNewToken").value = "";
          if ($("v2CastNewDesc")) $("v2CastNewDesc").value = "";
          if ($("v2CastNewArchetype")) $("v2CastNewArchetype").value = "";
          if ($("v2CastNewStyle")) $("v2CastNewStyle").value = "";
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
  let v2StyleActiveCat = "All";

  function renderV2StyleCatalog() {
    const catsEl = $("v2StyleCats");
    const gridEl = $("v2StyleGrid");
    if (!gridEl) return;
    const allStyles = (v2CharTypesCache && Array.isArray(v2CharTypesCache.styles) && v2CharTypesCache.styles.length)
      ? v2CharTypesCache.styles
      : Object.entries(V2_STYLE_RECIPES).map(([id, r]) => ({ id, ...r }));

    const catCounts = new Map();
    allStyles.forEach(s => {
      const c = s.category || "Custom";
      catCounts.set(c, (catCounts.get(c) || 0) + 1);
    });
    const catList = ["All", ...((v2CharTypesCache && v2CharTypesCache.style_categories) || []).filter(c => catCounts.has(c)), ...[...catCounts.keys()].filter(c => !((v2CharTypesCache && v2CharTypesCache.style_categories) || []).includes(c))];

    if (catsEl) {
      catsEl.textContent = "";
      catList.forEach(cat => {
        const b = document.createElement("button");
        b.type = "button";
        const active = v2StyleActiveCat === cat;
        b.className = "btn " + (active ? "btn--primary" : "btn--ghost");
        b.style.cssText = "padding:3px 10px;font-size:11px;border-radius:999px;";
        const cnt = cat === "All" ? allStyles.length : (catCounts.get(cat) || 0);
        b.textContent = `${cat} (${cnt})`;
        b.addEventListener("click", () => {
          v2StyleActiveCat = cat;
          renderV2StyleCatalog();
        });
        catsEl.appendChild(b);
      });
    }

    const filtered = v2StyleActiveCat === "All"
      ? allStyles
      : allStyles.filter(s => (s.category || "Custom") === v2StyleActiveCat);

    gridEl.textContent = "";
    filtered.forEach(s => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "deliverable-card v2-style-card";
      btn.dataset.look = s.id;
      btn.setAttribute("role", "radio");
      btn.setAttribute("aria-checked", String(s.id === v2SelectedLook));
      btn.style.cssText = "text-align:left;cursor:pointer;display:flex;flex-direction:column;gap:4px;";
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
      btn.addEventListener("click", () => selectV2Style(s.id));
      gridEl.appendChild(btn);
    });
    selectV2Style(v2SelectedLook, true);
    const liveSel = $("v2HybridLiveStyle");
    const cartSel = $("v2HybridCartoonStyle");
    if (liveSel) populateStyleSelect(liveSel, liveSel.value || "live_action", null);
    if (cartSel) populateStyleSelect(cartSel, cartSel.value || "vintage_1940s_2d", null);
  }

  function selectV2Style(lookKey, silent = false) {
    const key = V2_STYLE_RECIPES[lookKey] ? lookKey : "live_action";
    v2SelectedLook = key;
    const recipe = V2_STYLE_RECIPES[key];

    if (key === "hybrid_2d_live_action" && !silent && $("v2HybridEnabled")) {
      $("v2HybridEnabled").checked = true;
    }

    document.querySelectorAll(".v2-style-card").forEach(card => {
      const isSelected = card.dataset.look === key;
      card.setAttribute("aria-checked", String(isSelected));
      card.style.borderColor = isSelected ? "#f59e0b" : "#232d3f";
      card.style.background = isSelected ? "rgba(245, 158, 11, 0.12)" : "#141b27";
      card.style.boxShadow = isSelected ? "0 0 14px rgba(245, 158, 11, 0.25)" : "none";
    });

    const badge = $("v2StyleBadge");
    if (badge) badge.textContent = `✓ ${recipe.label}`;
    const prevBox = $("v2StylePreviewBox");
    const prevImg = $("v2StylePreviewImg");
    const prevTitle = $("v2StylePreviewTitle");
    const prevCat = $("v2StylePreviewCat");
    const prevDesc = $("v2StylePreviewDesc");
    if (prevBox && prevImg) {
      if (recipe.sample_url) {
        prevBox.style.display = "flex";
        prevImg.src = recipe.sample_url;
        prevImg.alt = `${recipe.label} canned preview`;
        prevImg.onclick = () => window.open(recipe.sample_url, "_blank");
        if (prevTitle) prevTitle.textContent = `${recipe.icon ? recipe.icon + " " : ""}${recipe.label}`;
        if (prevCat) prevCat.textContent = recipe.category || "Style";
        if (prevDesc) prevDesc.textContent = recipe.summary || recipe.positives || "";
      } else {
        prevBox.style.display = "none";
      }
    }
    const pos = $("v2StylePos");
    const neg = $("v2StyleNeg");
    const mot = $("v2StyleMotion");
    if (pos) pos.value = recipe.positives || "";
    if (neg) neg.value = recipe.negatives || "";
    if (mot) mot.value = recipe.motion_cadence || "";
    const msg = $("v2StyleMsg");
    if (msg && !silent) msg.textContent = `Selected "${recipe.label}" — click 💾 Apply Style to Book to save to your project.`;

    // Sync with hidden legacy look radio if present and persist in localStorage
    const legacyRadio = document.querySelector(`input[name="look"][value="${key}"]`);
    if (legacyRadio) {
      legacyRadio.checked = true;
      legacyRadio.dispatchEvent(new Event("change"));
    }
    try { localStorage.setItem("studio_v2_look", key); } catch (e) {}
    if (!silent) loadStepAutopilot();
  }

  function initV2Styles() {
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
          const hybEnabled = Boolean($("v2HybridEnabled") && $("v2HybridEnabled").checked);
          const hybrid_mode = {
            enabled: hybEnabled,
            world_style: ($("v2HybridLiveStyle") || {}).value || "live_action",
            live_style: ($("v2HybridLiveStyle") || {}).value || "live_action",
            cartoon_style: ($("v2HybridCartoonStyle") || {}).value || "vintage_1940s_2d",
            animate_on_twos: Boolean(!$("v2HybridTwos") || $("v2HybridTwos").checked),
          };
          await callApi("/api/global_params", {
            project: slug,
            look: v2SelectedLook,
            positives: ($("v2StylePos") || {}).value || "",
            negatives: ($("v2StyleNeg") || {}).value || "",
            motion_cadence: ($("v2StyleMotion") || {}).value || "",
            hybrid_mode,
          });
          const lbl = (V2_STYLE_RECIPES[v2SelectedLook] || {}).label || v2SelectedLook;
          if (msg) msg.textContent = `✓ Applied "${lbl}"${hybEnabled ? " + 🎭 Hybrid 2D-Meets-Realism Mode" : ""} to "${slug}".`;
        } catch (err) {
          if (msg) msg.textContent = "Error: " + err.message;
        } finally {
          btnApply.disabled = false;
        }
      });
    }

    const btnCustomToggle = $("bV2StyleCustomToggle");
    const customForm = $("v2StyleCustomForm");
    const btnCustomCancel = $("bV2StyleCustomCancel");
    const btnCustomSave = $("bV2StyleCustomSave");
    if (btnCustomToggle && customForm) {
      btnCustomToggle.addEventListener("click", () => {
        const show = customForm.classList.contains("hidden");
        customForm.classList.toggle("hidden", !show);
        customForm.style.display = show ? "flex" : "none";
        if (show && $("v2StyleCustomLabel")) $("v2StyleCustomLabel").focus();
      });
    }
    if (btnCustomCancel && customForm) {
      btnCustomCancel.addEventListener("click", () => {
        customForm.classList.add("hidden");
        customForm.style.display = "none";
      });
    }
    if (btnCustomSave) {
      btnCustomSave.addEventListener("click", async () => {
        const label = ($("v2StyleCustomLabel")?.value || "").trim();
        const category = ($("v2StyleCustomCat")?.value || "Custom").trim();
        const summary = ($("v2StyleCustomSummary")?.value || "").trim();
        const positives = ($("v2StyleCustomPos")?.value || "").trim();
        const negatives = ($("v2StyleCustomNeg")?.value || "").trim();
        const motion_cadence = ($("v2StyleCustomMotion")?.value || "").trim();
        const cMsg = $("v2StyleCustomMsg");
        if (!label || !positives) {
          if (cMsg) cMsg.textContent = "Enter both a Style Name and Image Prompt Keywords.";
          return;
        }
        btnCustomSave.disabled = true;
        if (cMsg) cMsg.textContent = "Saving custom style…";
        try {
          const res = await callApi("/api/character_types_custom", {
            kind: "style",
            name: label,
            category,
            summary,
            positives,
            negatives,
            motion_cadence,
            icon: "🎨",
          });
          await loadV2CharacterTypes(true);
          const savedObj = res && (res.saved || res.item);
          if (savedObj && savedObj.id) v2SelectedLook = savedObj.id;
          v2StyleActiveCat = "All";
          renderV2StyleCatalog();
          if (window.loadPStyles) window.loadPStyles();
          ["v2StyleCustomLabel", "v2StyleCustomSummary", "v2StyleCustomPos", "v2StyleCustomNeg", "v2StyleCustomMotion"].forEach(id => {
            if ($(id)) $(id).value = "";
          });
          if (customForm) { customForm.classList.add("hidden"); customForm.style.display = "none"; }
          if (cMsg) cMsg.textContent = "";
        } catch (err) {
          if (cMsg) cMsg.textContent = "Error: " + (err.message || err);
        } finally {
          btnCustomSave.disabled = false;
        }
      });
    }

    let savedLook = "live_action";
    try { savedLook = localStorage.getItem("studio_v2_look") || "live_action"; } catch (e) {}
    v2SelectedLook = savedLook;
    loadV2CharacterTypes().then(() => {
      renderV2StyleCatalog();
    });
  }

  // ===== STEP 11: LOCATIONS & SETS =====
  let v2LocCurrentList = [];

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

  function deleteCustomSet(slug, setName) {
    try {
      const key = String(setName || "").trim().toLowerCase();
      const list = getCustomSets(slug).filter(x => String(x.name || "").trim().toLowerCase() !== key);
      localStorage.setItem(`studio_v2_sets_${slug}`, JSON.stringify(list));
    } catch (e) {}
  }

  function updateV2LocInsertHint() {
    const numIn = $("v2LocNewNumber");
    const hint = $("v2LocInsertHint");
    if (!numIn || !hint) return;
    const total = v2LocCurrentList.length;
    const maxPos = total + 1;
    numIn.min = "1";
    numIn.max = String(maxPos);
    let pos = parseInt(numIn.value, 10);
    if (!Number.isFinite(pos) || pos < 1) pos = maxPos;
    if (pos > maxPos) pos = maxPos;
    if (total === 0) {
      hint.textContent = "Will be added as Set 1.";
    } else if (pos === 1) {
      hint.textContent = `Will insert as Set 1 (before "${v2LocCurrentList[0].name}") — existing sets will automatically renumber to Set 2–${maxPos}.`;
    } else if (pos > total) {
      hint.textContent = `Will append at the end as Set ${maxPos}.`;
    } else {
      const prev = v2LocCurrentList[pos - 2].name;
      const next = v2LocCurrentList[pos - 1].name;
      hint.textContent = `Will insert as Set ${pos} (between Set ${pos - 1}: "${prev}" and Set ${pos}: "${next}") — sets from Set ${pos} onward will automatically renumber.`;
    }
  }

  function openV2LocAddFormAt(position) {
    const form = $("v2LocAddForm");
    const numIn = $("v2LocNewNumber");
    if (!form) return;
    form.classList.remove("hidden");
    form.style.display = "flex";
    const maxPos = v2LocCurrentList.length + 1;
    const pos = Math.max(1, Math.min(maxPos, parseInt(position, 10) || maxPos));
    if (numIn) {
      numIn.min = "1";
      numIn.max = String(maxPos);
      numIn.value = String(pos);
    }
    updateV2LocInsertHint();
    form.scrollIntoView({ behavior: "smooth", block: "nearest" });
    if ($("v2LocNewName")) $("v2LocNewName").focus();
  }

  async function loadV2Locations() {
    const selProj = $("proj");
    const slug = (selProj && selProj.value) || activeProject || "";
    const grid = $("v2LocGrid");
    const summaryEl = $("v2LocSummary");
    const badgeEl = $("v2LocBadge");

    if (!grid) return;

    if (!slug) {
      v2LocCurrentList = [];
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

    // 0. Load deleted/hidden sets, custom set order, and disk-saved set edits
    const deletedSets = new Set();
    let savedOrder = [];
    let diskCustomSets = [];
    let diskSetImages = {};
    let diskSetViews = {};
    let filmStyleLabel = "Film Style";
    try {
      const hid = await callApi(`/api/v2_sets_hidden?project=${encodeURIComponent(slug)}`);
      ((hid && Array.isArray(hid.deleted)) ? hid.deleted : []).forEach(n => {
        const k = String(n || "").trim().toLowerCase();
        if (k) deletedSets.add(k);
      });
      if (hid && Array.isArray(hid.order)) {
        savedOrder = hid.order.map(n => String(n || "").trim().toLowerCase()).filter(Boolean);
      }
      if (hid && Array.isArray(hid.custom)) {
        diskCustomSets = hid.custom;
      }
      if (hid && hid.set_images && typeof hid.set_images === "object") {
        diskSetImages = hid.set_images;
      }
      if (hid && hid.set_views && typeof hid.set_views === "object") {
        diskSetViews = hid.set_views;
      }
      if (hid && hid.film_style_label) {
        filmStyleLabel = String(hid.film_style_label);
      }
    } catch (e) {}

    const upsert = (name, info, sourceLabel) => {
      const clean = String(name || "").trim();
      if (!clean) return;
      const key = clean.toLowerCase();
      if (deletedSets.has(key)) return;
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
      if (info.description && (!existing.description || info.inContinuity || info.prefer)) existing.description = info.description;
      if (info.lighting && (!existing.lighting || info.inContinuity || info.prefer)) existing.lighting = info.lighting;
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
        const desc = typeof loc === "object" ? (loc.description || loc.details || loc.visual_description || loc.token || "") : "";
        const light = typeof loc === "object" ? (loc.lighting || loc.atmosphere || loc.time_of_day || "") : "";
        upsert(name, { inContinuity: true, description: desc, lighting: light }, "Continuity Book");
      });
    } catch (e) {}

    // 2. Scene cast_lock places
    try {
      const lk = await callApi(`/api/cast_lock?project=${encodeURIComponent(slug)}`);
      const scenes = (lk && Array.isArray(lk.scenes)) ? lk.scenes : [];
      scenes.forEach(s => {
        const pname = s.location || (s.place && s.place.name) || "";
        if (pname) {
          upsert(pname, { description: s.summary || "" }, "Scenes");
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

    // 4. Persisted custom sets (disk + localStorage)
    getCustomSets(slug).forEach(cs => {
      upsert(cs.name, { description: cs.description || "", lighting: cs.lighting || "" }, "Custom");
    });
    diskCustomSets.forEach(cs => {
      upsert(cs.name, { description: cs.description || "", lighting: cs.lighting || "", prefer: true }, "Saved Set");
      const entry = merged.get(String(cs.name || "").trim().toLowerCase());
      if (entry) {
        entry.reserve_2d_gaps = Boolean(cs.reserve_2d_gaps);
        entry.gap_notes = String(cs.gap_notes || "");
      }
    });

    // Apply persisted set order and automatically assign contiguous Set 1..N numbering
    const rawLocs = [...merged.values()];
    let allLocs = rawLocs;
    if (savedOrder.length) {
      const rank = new Map(savedOrder.map((k, i) => [k, i]));
      const fallbackBase = savedOrder.length;
      allLocs = rawLocs
        .map((loc, origIdx) => ({ loc, origIdx, key: loc.name.toLowerCase() }))
        .sort((a, b) => {
          const ra = rank.has(a.key) ? rank.get(a.key) : (fallbackBase + a.origIdx);
          const rb = rank.has(b.key) ? rank.get(b.key) : (fallbackBase + b.origIdx);
          return ra - rb || a.origIdx - b.origIdx;
        })
        .map(x => x.loc);
    }
    v2LocCurrentList = allLocs.map(l => ({ name: l.name, key: l.name.toLowerCase() }));
    const numIn = $("v2LocNewNumber");
    if (numIn && $("v2LocAddForm") && $("v2LocAddForm").classList.contains("hidden")) {
      numIn.value = String(allLocs.length + 1);
    }
    updateV2LocInsertHint();

    if (summaryEl) {
      summaryEl.innerHTML = `<strong style="color:#f59e0b">${allLocs.length} location(s) / set(s)</strong> found for <strong>${slug}</strong>` +
        (allLocs.length ? " — drag cards to reorder, reassign set numbers, insert between sets, or delete (sets auto-renumber)." : " — click <strong>➕ Add Set</strong> or <strong>✨ Extract Sets from Script</strong> to populate your locations.");
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

    const currentOrderKeys = allLocs.map(l => l.name.toLowerCase());
    // Sync top "Import Reference Photo -> Associate with Location" selector
    const impSetSel = $("v2LocImportSet");
    if (impSetSel) {
      const prevImp = impSetSel.value;
      impSetSel.textContent = "";
      allLocs.forEach((l, i) => {
        const opt = document.createElement("option");
        opt.value = l.name;
        opt.textContent = `Set ${i + 1}: ${l.name}`;
        impSetSel.appendChild(opt);
      });
      if (prevImp && allLocs.some(l => l.name === prevImp)) impSetSel.value = prevImp;
    }
    let draggedLocKey = "";

    const clearDropHighlights = () => {
      grid.querySelectorAll(".v2-loc-drop-target").forEach(el => {
        el.classList.remove("v2-loc-drop-target");
        el.style.outline = "";
        el.style.outlineOffset = "";
      });
    };

    allLocs.forEach((loc, idx) => {
      const setNum = idx + 1;
      const locKey = loc.name.toLowerCase();
      const card = document.createElement("div");
      card.className = "direct-story-card";
      card.dataset.locKey = locKey;
      card.draggable = true;
      card.addEventListener("pointerdown", e => {
        const interactive = e.target && e.target.closest("input, textarea, select, button");
        card.draggable = !interactive;
      });
      card.addEventListener("pointerup", () => { card.draggable = true; });
      card.addEventListener("dragstart", e => {
        if (e.target && e.target.closest("input, textarea, select, button")) {
          e.preventDefault();
          return;
        }
        draggedLocKey = locKey;
        card.style.opacity = "0.45";
        if (e.dataTransfer) {
          e.dataTransfer.effectAllowed = "move";
          e.dataTransfer.setData("text/plain", locKey);
        }
      });
      card.addEventListener("dragend", () => {
        draggedLocKey = "";
        card.style.opacity = "";
        card.draggable = true;
        clearDropHighlights();
      });
      card.addEventListener("dragover", e => {
        const srcKey = draggedLocKey || (e.dataTransfer && e.dataTransfer.getData("text/plain")) || "";
        if (!srcKey || srcKey === locKey) return;
        e.preventDefault();
        if (e.dataTransfer) e.dataTransfer.dropEffect = "move";
        if (!card.classList.contains("v2-loc-drop-target")) {
          clearDropHighlights();
          card.classList.add("v2-loc-drop-target");
          card.style.outline = "2px dashed #f59e0b";
          card.style.outlineOffset = "2px";
        }
      });
      card.addEventListener("dragleave", e => {
        if (!card.contains(e.relatedTarget)) {
          card.classList.remove("v2-loc-drop-target");
          card.style.outline = "";
          card.style.outlineOffset = "";
        }
      });
      card.addEventListener("drop", async e => {
        e.preventDefault();
        const srcKey = draggedLocKey || (e.dataTransfer && e.dataTransfer.getData("text/plain")) || "";
        clearDropHighlights();
        draggedLocKey = "";
        if (!srcKey || srcKey === locKey) return;
        const targetIdx = currentOrderKeys.indexOf(locKey);
        if (targetIdx < 0) return;
        const reordered = currentOrderKeys.filter(k => k !== srcKey);
        reordered.splice(targetIdx, 0, srcKey);
        try {
          await callApi("/api/v2_set_order", { project: slug, order: reordered });
          await loadV2Locations();
        } catch (err) {
          if (summaryEl) summaryEl.textContent = "Could not reorder sets: " + (err.message || err);
        }
      });
      if (!loc.description || loc.description.trim().length < 15) {
        flagNeedsAttention(card, "Add specific set details, colors & layout so shots stay consistent in this location");
      }

      const head = document.createElement("div");
      head.style.cssText = "display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap;";
      const titleGroup = document.createElement("div");
      titleGroup.style.cssText = "display:flex;align-items:center;gap:8px;flex-wrap:wrap;";

      const dragHandle = document.createElement("span");
      dragHandle.textContent = "⋮⋮";
      dragHandle.title = `Drag to reorder Set ${setNum} ("${loc.name}") — sets auto-renumber`;
      dragHandle.style.cssText = "cursor:grab;color:#64748b;font-weight:700;font-size:14px;letter-spacing:-1px;user-select:none;padding:0 2px;";
      titleGroup.appendChild(dragHandle);

      const numSel = document.createElement("select");
      numSel.title = `Assign set number for "${loc.name}" (all other sets automatically renumber)`;
      numSel.style.cssText = "background:#0f172a;color:#f59e0b;font-weight:700;border:1px solid #334155;border-radius:6px;padding:2px 6px;font-size:12px;";
      for (let n = 1; n <= allLocs.length; n++) {
        const opt = document.createElement("option");
        opt.value = String(n);
        opt.textContent = `Set ${n}`;
        if (n === setNum) opt.selected = true;
        numSel.appendChild(opt);
      }
      numSel.addEventListener("change", async () => {
        const targetPos = Math.max(1, Math.min(allLocs.length, parseInt(numSel.value, 10) || setNum));
        if (targetPos === setNum) return;
        const reordered = currentOrderKeys.filter(k => k !== loc.name.toLowerCase());
        reordered.splice(targetPos - 1, 0, loc.name.toLowerCase());
        numSel.disabled = true;
        try {
          await callApi("/api/v2_set_order", { project: slug, order: reordered });
          await loadV2Locations();
        } catch (err) {
          numSel.disabled = false;
          numSel.value = String(setNum);
        }
      });

      const title = document.createElement("strong");
      title.style.cssText = "font-size:var(--text-base);color:#f8fafc;";
      title.textContent = loc.name;
      titleGroup.appendChild(numSel);
      titleGroup.appendChild(title);

      const srcBadge = document.createElement("span");
      srcBadge.className = "status-badge " + (loc.inContinuity ? "status-badge--synced" : "status-badge--working");
      srcBadge.style.fontSize = "0.7rem";
      srcBadge.textContent = loc.inContinuity ? "✓ Continuity Book" : `From ${[...loc.sources].join(" / ")}`;
      head.appendChild(titleGroup);
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

      // Step 11 Multi-View Reference Photo Import, Side-by-Side Film Style Conversion & Baseline Locking
      const safeSetSlug = loc.name.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "") || "set";
      const legacyImgUrl = diskSetImages[safeSetSlug] || "";
      const svData = diskSetViews[locKey] || { baseline_view_id: "", baseline_url: "", views: [] };
      const viewsList = (Array.isArray(svData.views) && svData.views.length)
        ? svData.views.slice()
        : [{
            id: "main",
            label: "Establishing View",
            notes: "",
            has_ref: false,
            ref_url: "",
            has_converted: Boolean(legacyImgUrl),
            converted_url: legacyImgUrl,
            is_baseline: false,
          }];
      // Ensure main view picks up legacy plate URL if sets_views.json hadn't recorded it yet
      viewsList.forEach(vw => {
        if (vw.id === "main" && !vw.has_converted && legacyImgUrl) {
          vw.has_converted = true;
          vw.converted_url = legacyImgUrl;
        }
      });

      const setPlateWrap = document.createElement("div");
      setPlateWrap.style.cssText = "margin-top:6px;padding:8px;background:#0a0d14;border:1px solid #232d3f;border-radius:6px;display:flex;flex-direction:column;gap:6px;";
      const gapLbl = document.createElement("label");
      gapLbl.style.cssText = "display:inline-flex;align-items:center;gap:6px;font-size:11px;color:#fde68a;font-weight:600;cursor:pointer;";
      const gapChk = document.createElement("input");
      gapChk.type = "checkbox";
      gapChk.checked = Boolean(loc.reserve_2d_gaps);
      gapLbl.appendChild(gapChk);
      gapLbl.appendChild(document.createTextNode("🎭 Plan the Gaps: Reserve empty spaces for 2D cartoon cast (no people)"));
      setPlateWrap.appendChild(gapLbl);

      const gapInput = document.createElement("input");
      gapInput.type = "text";
      gapInput.value = loc.gap_notes || "";
      gapInput.placeholder = "Where cartoons will live (e.g. empty chair on right, open tabletop foreground, open sky above)…";
      gapInput.style.cssText = "width:100%;padding:5px 8px;background:#0f172a;color:#cbd5e1;border:1px solid #334155;border-radius:4px;font-size:11px;";
      setPlateWrap.appendChild(gapInput);

      // Show active Baseline banner if pinned on this location
      if (svData.baseline_view_id) {
        const bView = viewsList.find(v => v.id === svData.baseline_view_id);
        const bBar = document.createElement("div");
        bBar.className = "v2-set-baseline-bar";
        const bTxt = document.createElement("span");
        bTxt.textContent = `📌 Active Baseline: "${(bView && bView.label) || svData.baseline_view_id}" — re-runs & other views of ${loc.name} will use this baselined image`;
        const bClr = document.createElement("button");
        bClr.type = "button";
        bClr.className = "btn btn--ghost";
        bClr.style.cssText = "padding:2px 7px;font-size:10.5px;color:#fca5a5";
        bClr.textContent = "✕ Clear Baseline";
        bClr.addEventListener("click", async () => {
          try {
            await callApi("/api/v2_set_baseline", { project: slug, name: loc.name, view_id: "" });
            await loadV2Locations();
          } catch (err) {
            msg.textContent = "Could not clear baseline: " + (err.message || err);
          }
        });
        bBar.appendChild(bTxt);
        bBar.appendChild(bClr);
        setPlateWrap.appendChild(bBar);
      }

      // Views Header + Inline "+ Add View" for multi-view locations (e.g. Living Room, Kitchen)
      const viewsHdr = document.createElement("div");
      viewsHdr.style.cssText = "display:flex;justify-content:space-between;align-items:center;gap:6px;flex-wrap:wrap;margin-top:2px;";
      const vCountLbl = document.createElement("span");
      vCountLbl.style.cssText = "font-size:11px;font-weight:700;color:#93c5fd;";
      vCountLbl.textContent = `🏛 Set Views (${viewsList.length}) · Target Style: ${filmStyleLabel}`;
      const btnAddView = document.createElement("button");
      btnAddView.type = "button";
      btnAddView.className = "btn btn--ghost";
      btnAddView.style.cssText = "padding:3px 8px;font-size:11px;color:#93c5fd;";
      btnAddView.textContent = "➕ Add View";
      viewsHdr.appendChild(vCountLbl);
      viewsHdr.appendChild(btnAddView);
      setPlateWrap.appendChild(viewsHdr);

      const addViewForm = document.createElement("div");
      addViewForm.style.cssText = "display:none;gap:6px;flex-wrap:wrap;padding:6px;background:#0f172a;border:1px solid #334155;border-radius:6px;";
      const avName = document.createElement("input");
      avName.type = "text";
      avName.placeholder = "View name (e.g. Kitchen Doorway, Window & Sofa)…";
      avName.style.cssText = "flex:1;min-width:140px;padding:4px 7px;background:#020617;color:#f8fafc;border:1px solid #334155;border-radius:4px;font-size:11px;";
      const avNotes = document.createElement("input");
      avNotes.type = "text";
      avNotes.placeholder = "Camera angle / view details (optional)…";
      avNotes.style.cssText = "flex:1;min-width:140px;padding:4px 7px;background:#020617;color:#cbd5e1;border:1px solid #334155;border-radius:4px;font-size:11px;";
      const avSave = document.createElement("button");
      avSave.type = "button";
      avSave.className = "btn btn--primary";
      avSave.style.cssText = "padding:4px 9px;font-size:11px;";
      avSave.textContent = "Save View";
      avSave.addEventListener("click", async () => {
        const lbl = avName.value.trim();
        if (!lbl) { avName.focus(); return; }
        avSave.disabled = true;
        try {
          await callApi("/api/v2_set_view_save", {
            project: slug,
            name: loc.name,
            label: lbl,
            notes: avNotes.value.trim(),
          });
          await loadV2Locations();
        } catch (err) {
          msg.textContent = "Add view failed: " + (err.message || err);
          avSave.disabled = false;
        }
      });
      addViewForm.appendChild(avName);
      addViewForm.appendChild(avNotes);
      addViewForm.appendChild(avSave);
      setPlateWrap.appendChild(addViewForm);
      btnAddView.addEventListener("click", () => {
        addViewForm.style.display = addViewForm.style.display === "none" ? "flex" : "none";
        if (addViewForm.style.display === "flex") avName.focus();
      });

      // Render each view with Side-by-Side Imported Photo <-> Converted Film-Style Plate
      const viewsContainer = document.createElement("div");
      viewsContainer.className = "v2-set-views";
      viewsList.forEach(vw => {
        const vItem = document.createElement("div");
        vItem.className = "v2-set-view-item" + (vw.is_baseline ? " is-baseline" : "");

        const vHdr = document.createElement("div");
        vHdr.className = "v2-set-view-hdr";
        const vTitle = document.createElement("span");
        vTitle.className = "v2-set-view-title";
        vTitle.textContent = `${vw.is_baseline ? "📌 " : ""}${vw.label || vw.id}`;
        const vTag = document.createElement("span");
        vTag.style.cssText = "font-size:10px;color:#94a3b8;";
        if (vw.has_ref && vw.has_converted) vTag.textContent = "📷 Ref Photo → 🎨 Converted";
        else if (vw.has_ref) vTag.textContent = "📷 Ref Photo Ready (Click Convert)";
        else if (vw.has_converted) vTag.textContent = "🎨 Generated Set Plate (No Ref Photo)";
        else vTag.textContent = "Optional Ref Photo · Ready to Generate";
        vHdr.appendChild(vTitle);
        vHdr.appendChild(vTag);
        vItem.appendChild(vHdr);

        if (vw.notes) {
          const vNoteEl = document.createElement("div");
          vNoteEl.style.cssText = "font-size:10.5px;color:#94a3b8;";
          vNoteEl.textContent = vw.notes;
          vItem.appendChild(vNoteEl);
        }

        // Side-by-side comparison grid: Imported Reference Photo | Converted Film-Style Plate
        const cmp = document.createElement("div");
        cmp.className = "v2-set-compare";

        // Left slot: Imported Reference Photo
        const refSlot = document.createElement("div");
        refSlot.className = "v2-set-img-slot";
        const refLbl = document.createElement("div");
        refLbl.className = "v2-set-img-slot__lbl";
        refLbl.textContent = "📷 Imported Reference Photo";
        const refBox = document.createElement("div");
        refBox.className = "v2-set-img-slot__box";
        if (vw.has_ref && vw.ref_url) {
          const rImg = document.createElement("img");
          rImg.src = vw.ref_url + "?t=" + Date.now();
          rImg.alt = `${loc.name} ${vw.label} imported photo`;
          rImg.title = "Click to view full imported reference photo";
          rImg.addEventListener("click", () => window.open(vw.ref_url, "_blank"));
          refBox.appendChild(rImg);
        } else {
          refBox.textContent = "No photo imported for this view (optional)";
        }
        refSlot.appendChild(refLbl);
        refSlot.appendChild(refBox);

        // Right slot: Converted Film-Style Image
        const convSlot = document.createElement("div");
        convSlot.className = "v2-set-img-slot";
        const convLbl = document.createElement("div");
        convLbl.className = "v2-set-img-slot__lbl";
        convLbl.textContent = `🎨 Converted (${filmStyleLabel})`;
        const convBox = document.createElement("div");
        convBox.className = "v2-set-img-slot__box";
        if (vw.has_converted && vw.converted_url) {
          const cImg = document.createElement("img");
          cImg.src = vw.converted_url + "?t=" + Date.now();
          cImg.alt = `${loc.name} ${vw.label} converted set plate`;
          cImg.title = "Click to view full converted set plate";
          cImg.addEventListener("click", () => window.open(vw.converted_url, "_blank"));
          convBox.appendChild(cImg);
          if (vw.is_baseline) {
            const bb = document.createElement("span");
            bb.className = "v2-set-img-slot__badge";
            bb.textContent = "📌 Baseline";
            convBox.appendChild(bb);
          }
        } else {
          convBox.textContent = vw.has_ref ? "Click Convert to Film Style →" : "Not generated yet";
        }
        convSlot.appendChild(convLbl);
        convSlot.appendChild(convBox);

        cmp.appendChild(refSlot);
        cmp.appendChild(convSlot);
        vItem.appendChild(cmp);

        // Per-view action bar: Import Ref, Convert/Re-run, Set as Baseline, Remove Ref/View
        const vAct = document.createElement("div");
        vAct.className = "v2-set-view-actions";

        const refIn = document.createElement("input");
        refIn.type = "file";
        refIn.accept = "image/*";
        refIn.style.display = "none";
        refIn.addEventListener("change", () => {
          const f = refIn.files && refIn.files[0];
          if (!f) return;
          const reader = new FileReader();
          reader.onload = async () => {
            const stopBusy = startBusyFeedback(btnImpView, vItem, `Importing ${f.name} & converting to ${filmStyleLabel}…`);
            msg.textContent = `Importing "${f.name}" for ${loc.name} (${vw.label})…`;
            try {
              await callApi("/api/v2_set_ref_upload", {
                project: slug,
                name: loc.name,
                view_id: vw.id,
                view_label: vw.label,
                view_notes: vw.notes || "",
                filename: f.name,
                image_base64: reader.result,
                description: descTa.value.trim(),
                lighting: lightInput.value.trim(),
                reserve_2d_gaps: gapChk.checked,
                gap_notes: gapInput.value.trim(),
                convert_now: true,
                engine: _currentV2VisualEngine(),
              });
              if (window.loadPCastRefs) window.loadPCastRefs();
              await loadV2Locations();
            } catch (err) {
              msg.textContent = "Import & convert failed: " + (err.message || err);
            } finally {
              stopBusy();
            }
          };
          reader.readAsDataURL(f);
        });

        const btnImpView = document.createElement("button");
        btnImpView.type = "button";
        btnImpView.className = "btn btn--ghost";
        btnImpView.textContent = vw.has_ref ? "📷 Replace Photo" : "📷 Import Photo";
        btnImpView.title = "Import a real reference photo for this view and convert it into your film's visual style";
        btnImpView.addEventListener("click", () => refIn.click());
        vAct.appendChild(btnImpView);
        vAct.appendChild(refIn);

        const btnConvView = document.createElement("button");
        btnConvView.type = "button";
        btnConvView.className = "btn " + (vw.has_converted ? "btn--secondary" : "btn--primary");
        const hasBaseForRun = Boolean(svData.baseline_view_id);
        if (vw.has_ref) {
          btnConvView.textContent = vw.has_converted
            ? (hasBaseForRun ? "↺ Re-convert (w/ Baseline)" : "↺ Re-convert Photo")
            : (hasBaseForRun ? "🎨 Convert Photo (w/ Baseline)" : "🎨 Convert to Film Style");
        } else {
          btnConvView.textContent = vw.has_converted
            ? (hasBaseForRun ? "↺ Re-run (w/ Baseline)" : "↺ Re-render Plate")
            : (hasBaseForRun ? "✨ Generate (w/ Baseline)" : "🎨 Generate Set Plate");
        }
        btnConvView.addEventListener("click", async () => {
          const stopBusy = startBusyFeedback(btnConvView, vItem, `Rendering ${loc.name} (${vw.label})…`);
          msg.textContent = `Rendering ${loc.name} — ${vw.label}…`;
          try {
            await callApi("/api/v2_set_render", {
              project: slug,
              name: loc.name,
              view_id: vw.id,
              view_label: vw.label,
              view_notes: vw.notes || "",
              description: descTa.value.trim(),
              lighting: lightInput.value.trim(),
              reserve_2d_gaps: gapChk.checked,
              gap_notes: gapInput.value.trim(),
              use_ref: vw.has_ref,
              use_baseline: true,
              engine: _currentV2VisualEngine(),
            });
            if (window.loadPCastRefs) window.loadPCastRefs();
            await loadV2Locations();
          } catch (err) {
            msg.textContent = "Render failed: " + (err.message || err);
          } finally {
            stopBusy();
          }
        });
        vAct.appendChild(btnConvView);

        if (vw.has_converted || vw.has_ref) {
          const btnBase = document.createElement("button");
          btnBase.type = "button";
          btnBase.className = "btn " + (vw.is_baseline ? "btn--primary" : "btn--ghost");
          btnBase.style.cssText = vw.is_baseline ? "background:#059669;border-color:#10b981;" : "color:#6ee7b7;";
          btnBase.textContent = vw.is_baseline ? "📌 Baseline ✓ (Update & Sync)" : "📌 Use as Baseline";
          btnBase.title = vw.is_baseline
            ? "Update the locked Baseline snapshot, analyze the set image to text, and sync Steps 07, 11, 12 & 17"
            : `Set "${vw.label}" as ${loc.name}'s Baseline, analyze its visual layout to text, and sync Steps 07, 11, 12 & 17`;
          btnBase.addEventListener("click", async () => {
            const stopBusy = startBusyFeedback(btnBase, vItem, `Pinning baseline & reading set layout → syncing Steps 07/12/17…`);
            msg.textContent = `Pinning "${vw.label}" as Baseline & translating set image to text for Steps 07, 12 & 17…`;
            try {
              const res = await callApi("/api/v2_set_baseline", { project: slug, name: loc.name, view_id: vw.id });
              const vs = (res && res.vision_sync) || {};
              await loadV2Locations();
              if (vs.ok) {
                msg.textContent = `✓ Baseline pinned & synced from image (${vs.engine}): ${(vs.updated_steps || []).join(" · ")}`;
              }
            } catch (err) {
              msg.textContent = "Baseline failed: " + (err.message || err);
            } finally {
              stopBusy();
            }
          });
          vAct.appendChild(btnBase);

          if (vw.is_baseline) {
            const btnVisionSync = document.createElement("button");
            btnVisionSync.type = "button";
            btnVisionSync.className = "btn btn--secondary";
            btnVisionSync.style.cssText = "font-size:11px;";
            btnVisionSync.textContent = "🔍 Sync Text from Baseline";
            btnVisionSync.title = "Analyze this baselined set image to text and align Step 07 Continuity, Step 12 Shot List, and Step 17 Keyframe Prompts";
            btnVisionSync.addEventListener("click", async () => {
              const stopBusy = startBusyFeedback(btnVisionSync, vItem, `Analyzing ${loc.name} baseline image → syncing Steps 07/12/17…`);
              msg.textContent = `Translating "${loc.name}" baselined image into set description & aligning Steps 07, 12 & 17…`;
              try {
                const res = await callApi("/api/v2_set_analyze_sync", { project: slug, name: loc.name });
                await loadV2Locations();
                msg.textContent = `✓ Synced from ${res.image_analyzed} (${res.engine}): ${(res.updated_steps || []).join(" · ")}`;
              } catch (err) {
                msg.textContent = "Image-to-text sync failed: " + (err.message || err);
              } finally {
                stopBusy();
              }
            });
            vAct.appendChild(btnVisionSync);
          }
        }

        if (vw.has_converted) {
          const btnDelImg = document.createElement("button");
          btnDelImg.type = "button";
          btnDelImg.className = "btn btn--ghost";
          btnDelImg.style.color = "#f87171";
          btnDelImg.textContent = "🗑️ Delete Image";
          btnDelImg.title = `Delete ONLY the generated image for "${vw.label}" (keeps the set, view, and any imported reference photo)`;
          btnDelImg.addEventListener("click", async () => {
            btnDelImg.disabled = true;
            try {
              await callApi("/api/v2_set_image_delete", { project: slug, name: loc.name, view_id: vw.id });
              if (window.loadPCastRefs) window.loadPCastRefs();
              await loadV2Locations();
            } catch (err) {
              msg.textContent = "Delete image failed: " + (err.message || err);
              btnDelImg.disabled = false;
            }
          });
          vAct.appendChild(btnDelImg);
        }

        if (vw.has_ref) {
          const btnRmRef = document.createElement("button");
          btnRmRef.type = "button";
          btnRmRef.className = "btn btn--ghost";
          btnRmRef.style.color = "#fca5a5";
          btnRmRef.textContent = "✕ Remove Photo";
          btnRmRef.addEventListener("click", async () => {
            try {
              await callApi("/api/v2_set_ref_delete", { project: slug, name: loc.name, view_id: vw.id });
              await loadV2Locations();
            } catch (err) {
              msg.textContent = "Remove photo failed: " + (err.message || err);
            }
          });
          vAct.appendChild(btnRmRef);
        }

        if (vw.id !== "main") {
          const btnRmView = document.createElement("button");
          btnRmView.type = "button";
          btnRmView.className = "btn btn--ghost";
          btnRmView.style.cssText = "color:#f87171;margin-left:auto;";
          btnRmView.textContent = "🗑️ Remove View";
          btnRmView.addEventListener("click", async () => {
            try {
              await callApi("/api/v2_set_view_save", { project: slug, name: loc.name, view_id: vw.id, delete: true });
              await loadV2Locations();
            } catch (err) {
              msg.textContent = "Remove view failed: " + (err.message || err);
            }
          });
          vAct.appendChild(btnRmView);
        }

        vItem.appendChild(vAct);
        viewsContainer.appendChild(vItem);
      });
      setPlateWrap.appendChild(viewsContainer);
      card.appendChild(setPlateWrap);

      const foot = document.createElement("div");
      foot.style.cssText = "display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-top:4px;";
      const btnSave = document.createElement("button");
      btnSave.type = "button";
      btnSave.className = "btn btn--primary";
      btnSave.style.cssText = "padding:5px 12px;font-size:var(--text-xs);";
      btnSave.textContent = "💾 Save Set";

      const btnInsertAfter = document.createElement("button");
      btnInsertAfter.type = "button";
      btnInsertAfter.className = "btn btn--ghost";
      btnInsertAfter.style.cssText = "padding:5px 10px;font-size:var(--text-xs);color:#93c5fd;";
      btnInsertAfter.textContent = `➕ Insert After Set ${setNum}`;
      btnInsertAfter.title = `Insert a new set as Set ${setNum + 1} right after "${loc.name}" (subsequent sets auto-renumber)`;
      btnInsertAfter.addEventListener("click", () => openV2LocAddFormAt(setNum + 1));

      const msg = document.createElement("span");
      msg.style.cssText = "font-size:var(--text-xs);color:#94a3b8;";

      btnSave.addEventListener("click", async () => {
        btnSave.disabled = true;
        msg.textContent = "Saving & syncing…";
        const fields = {
          description: descTa.value.trim(),
          lighting: lightInput.value.trim(),
          reserve_2d_gaps: gapChk.checked,
          gap_notes: gapInput.value.trim(),
        };
        saveCustomSet(slug, { name: loc.name, ...fields });
        try {
          const res = await callApi("/api/v2_set_save", {
            project: slug,
            name: loc.name,
            description: fields.description,
            lighting: fields.lighting,
            reserve_2d_gaps: fields.reserve_2d_gaps,
            gap_notes: fields.gap_notes,
          });
          const synced = (res && res.sync_report && res.sync_report.updated_steps) || [];
          msg.textContent = synced.length ? `✓ Saved & synced (${synced.length} step(s))` : "✓ Saved to project sets";
        } catch (err) {
          msg.textContent = "✓ Saved locally (" + err.message + ")";
        } finally {
          btnSave.disabled = false;
        }
      });

      const btnDelete = document.createElement("button");
      btnDelete.type = "button";
      btnDelete.className = "btn btn--ghost";
      btnDelete.style.cssText = "padding:5px 10px;font-size:var(--text-xs);color:#f87171;margin-left:auto;";
      btnDelete.textContent = "🗑️ Delete Set";
      btnDelete.title = `Delete Set ${setNum} ("${loc.name}") and automatically renumber remaining sets`;
      btnDelete.addEventListener("click", async () => {
        const ok = await showInstallApprovalModal(
          `Delete Set ${setNum}: "${loc.name}"?`,
          `This removes Set ${setNum} ("${loc.name}") from Step 11 (Locations & Sets)` +
            (loc.inContinuity ? " and from the Continuity Book (Step 07)" : "") +
            `, and automatically renumbers the remaining sets.\n\nClick OK to delete, or Cancel to keep it.`
        );
        if (!ok) return;
        btnDelete.disabled = true;
        msg.textContent = "Deleting…";
        deleteCustomSet(slug, loc.name);
        try {
          await callApi("/api/v2_set_delete", { project: slug, name: loc.name, order: currentOrderKeys });
          await loadV2Locations();
        } catch (err) {
          msg.textContent = "Delete failed: " + (err.message || err);
          btnDelete.disabled = false;
        }
      });

      foot.appendChild(btnSave);
      foot.appendChild(btnInsertAfter);
      foot.appendChild(msg);
      foot.appendChild(btnDelete);
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
    const numIn = $("v2LocNewNumber");

    // Top-level "Import Reference Photo & Associate with Location / View" drawer
    const btnImpToggle = $("bV2LocImportToggle");
    const impForm = $("v2LocImportForm");
    const btnImpCancel = $("bV2LocImportCancel");
    const impFile = $("v2LocImportFile");
    const impPrev = $("v2LocImportPreview");
    const impStr = $("v2LocImportStrength");
    const impStrVal = $("v2LocImportStrengthVal");
    const btnImpConv = $("bV2LocImportConvert");
    const btnImpOnly = $("bV2LocImportOnly");
    const impMsg = $("v2LocImportMsg");
    let pendingImpDataUrl = "";
    let pendingImpFilename = "";

    if (impStr && impStrVal) {
      impStr.addEventListener("input", () => { impStrVal.textContent = Number(impStr.value).toFixed(2); });
    }
    if (btnImpToggle && impForm) {
      btnImpToggle.addEventListener("click", () => {
        const show = impForm.classList.contains("hidden") || impForm.style.display === "none";
        impForm.classList.toggle("hidden", !show);
        impForm.style.display = show ? "flex" : "none";
      });
    }
    if (btnImpCancel && impForm) {
      btnImpCancel.addEventListener("click", () => {
        impForm.classList.add("hidden");
        impForm.style.display = "none";
      });
    }
    if (impFile) {
      impFile.addEventListener("change", () => {
        const f = impFile.files && impFile.files[0];
        if (!f) return;
        pendingImpFilename = f.name;
        const reader = new FileReader();
        reader.onload = () => {
          pendingImpDataUrl = String(reader.result || "");
          if (impPrev) {
            impPrev.src = pendingImpDataUrl;
            impPrev.style.display = "block";
          }
          if (impMsg) impMsg.textContent = `Ready to import "${f.name}"`;
        };
        reader.readAsDataURL(f);
      });
    }
    async function runTopLocImport(convertNow) {
      const selProj = $("proj");
      const slug = (selProj && selProj.value) || activeProject || "";
      const setName = ($("v2LocImportSet") && $("v2LocImportSet").value) ? $("v2LocImportSet").value.trim() : "";
      const viewLabel = ($("v2LocImportView") && $("v2LocImportView").value) ? $("v2LocImportView").value.trim() : "Establishing View";
      const viewNotes = ($("v2LocImportNotes") && $("v2LocImportNotes").value) ? $("v2LocImportNotes").value.trim() : "";
      const viewId = /^establishing\s+view$/i.test(viewLabel) ? "main" : viewLabel;
      if (!slug) { if (impMsg) impMsg.textContent = "Pick a book in Step 01 first."; return; }
      if (!setName) { if (impMsg) impMsg.textContent = "Select a location / set first."; return; }
      if (!pendingImpDataUrl) { if (impMsg) impMsg.textContent = "Choose a reference picture file first."; return; }
      const trigBtn = convertNow ? btnImpConv : btnImpOnly;
      const stopBusy = startBusyFeedback(trigBtn, impForm, convertNow ? `Converting photo for ${setName}…` : `Importing photo for ${setName}…`);
      if (impMsg) impMsg.textContent = convertNow ? `Importing & converting photo for "${setName}" (${viewLabel})…` : `Importing photo for "${setName}" (${viewLabel})…`;
      try {
        await callApi("/api/v2_set_ref_upload", {
          project: slug,
          name: setName,
          view_id: viewId,
          view_label: viewLabel,
          view_notes: viewNotes,
          filename: pendingImpFilename || "reference.png",
          image_base64: pendingImpDataUrl,
          convert_now: convertNow,
          style_strength: impStr ? parseFloat(impStr.value) : 0.68,
          engine: _currentV2VisualEngine(),
        });
        pendingImpDataUrl = "";
        pendingImpFilename = "";
        if (impFile) impFile.value = "";
        if (impPrev) { impPrev.src = ""; impPrev.style.display = "none"; }
        if (impMsg) impMsg.textContent = convertNow ? `✓ Imported & converted photo for "${setName}" (${viewLabel})!` : `✓ Imported photo for "${setName}" (${viewLabel})!`;
        if (window.loadPCastRefs) window.loadPCastRefs();
        await loadV2Locations();
      } catch (err) {
        if (impMsg) impMsg.textContent = "Import failed: " + (err.message || err);
      } finally {
        stopBusy();
      }
    }
    if (btnImpConv) btnImpConv.addEventListener("click", () => runTopLocImport(true));
    if (btnImpOnly) btnImpOnly.addEventListener("click", () => runTopLocImport(false));

    if (numIn) {
      numIn.addEventListener("input", updateV2LocInsertHint);
      numIn.addEventListener("change", updateV2LocInsertHint);
    }

    if (btnToggle && form) {
      btnToggle.addEventListener("click", () => {
        const show = form.classList.contains("hidden");
        if (show) {
          openV2LocAddFormAt(v2LocCurrentList.length + 1);
        } else {
          form.classList.add("hidden");
          form.style.display = "none";
        }
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
        const maxPos = v2LocCurrentList.length + 1;
        const rawPos = parseInt(($("v2LocNewNumber") || {}).value, 10);
        const position = Math.max(1, Math.min(maxPos, Number.isFinite(rawPos) ? rawPos : maxPos));
        if (!slug) { alert("Pick or save a book in Step 01 first."); return; }
        if (!name) { alert("Enter a location / set name first."); return; }
        saveCustomSet(slug, { name, lighting, description });
        try {
          await callApi("/api/v2_set_save", { project: slug, name, description, lighting });
          await callApi("/api/v2_set_order", {
            project: slug,
            order: v2LocCurrentList.map(x => x.key),
            insert_name: name,
            position,
          });
        } catch (e) {}
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
        const cfg = _v2JobConfigForStep(11);
        if (summaryEl) summaryEl.textContent = `Starting continuity book & set extraction for "${slug}"…`;
        try {
          const o = typeof window.options === "function" ? window.options() : {};
          await callApi("/api/continuity_book", { project: slug, engine: o.engine || "claude", claude_model: o.claude_model });
          watchV2JobProgress({ ...cfg, fresh: true });
        } catch (err) {
          if (/already running/i.test(String(err.message || ""))) {
            watchV2JobProgress({ ...cfg, fresh: false });
          } else {
            if (summaryEl) summaryEl.textContent = "Could not start extraction: " + err.message;
            btnBuild.disabled = false;
          }
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

    const shotTaStyle = "width:100%;min-height:86px;padding:6px 8px;background:#0a0d14;color:#e2e8f0;border:1px solid #334155;border-radius:4px;font-size:11px;line-height:1.45;resize:vertical;font-family:inherit;box-sizing:border-box;";

    shots.forEach((s, idx) => {
      const tr = document.createElement("tr");
      tr.style.borderBottom = "1px solid #1e293b";

      const tdN = document.createElement("td");
      tdN.style.cssText = "padding:8px;font-weight:700;color:#f59e0b;white-space:nowrap;vertical-align:top;";
      tdN.textContent = `Shot ${s.n || idx + 1}`;

      const tdFrame = document.createElement("td");
      tdFrame.style.cssText = "padding:8px;white-space:nowrap;vertical-align:top;";
      tdFrame.textContent = [s.type || "Shot", s.lens_mm ? `${s.lens_mm}mm` : ""].filter(Boolean).join(" · ");

      const tdCam = document.createElement("td");
      tdCam.style.cssText = "padding:8px;width:36%;min-width:260px;vertical-align:top;";
      const camText = (s.camera_notes && String(s.camera_notes).trim())
        ? String(s.camera_notes).trim()
        : ([s.height, s.movement, s.lighting].filter(Boolean).join(", ") || "Standard");
      if (v2ShotSourceKind === "shot_list") {
        const camTa = document.createElement("textarea");
        camTa.className = "v2-shot-camera-input";
        camTa.rows = 4;
        camTa.value = camText;
        camTa.placeholder = "Camera height, movement, lighting & motion notes...";
        camTa.setAttribute("aria-label", `Shot ${s.n || idx + 1} Camera and Motion`);
        camTa.style.cssText = shotTaStyle;
        camTa.addEventListener("change", () => v2ShotEdit(sc.id, s.n, { action: "edit", fields: { camera_motion: camTa.value } }));
        tdCam.appendChild(camTa);
      } else {
        tdCam.style.fontSize = "var(--text-xs)";
        tdCam.style.color = "#94a3b8";
        tdCam.textContent = camText;
      }

      const tdAct = document.createElement("td");
      tdAct.style.cssText = "padding:8px;width:36%;min-width:260px;vertical-align:top;";
      const subjActText = s.composition
        ? `Subject: ${s.composition}\nAction: ${s.action || ""}`
        : (s.action || s.prompt || "");
      if (v2ShotSourceKind === "shot_list") {
        const actTa = document.createElement("textarea");
        actTa.className = "v2-shot-action-input";
        actTa.rows = 4;
        actTa.value = subjActText;
        actTa.placeholder = "Subject: framing & visual placement\nAction: what happens in the shot...";
        actTa.setAttribute("aria-label", `Shot ${s.n || idx + 1} Subject and Action`);
        actTa.style.cssText = shotTaStyle;
        actTa.addEventListener("change", () => v2ShotEdit(sc.id, s.n, { action: "edit", fields: { subject_action: actTa.value } }));
        tdAct.appendChild(actTa);
      } else {
        tdAct.textContent = subjActText;
      }

      const tdSec = document.createElement("td");
      tdSec.style.cssText = "padding:8px;vertical-align:top;";
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
      tdBtns.style.cssText = "padding:8px;white-space:nowrap;vertical-align:top;";
      const btnWrap = document.createElement("div");
      btnWrap.style.cssText = "display:flex;gap:4px;flex-wrap:wrap;";
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
        btnWrap.appendChild(mk("↑", () => v2ShotEdit(sc.id, s.n, { action: "move", to: s.n - 1 }), s.n <= 1));
        btnWrap.appendChild(mk("↓", () => v2ShotEdit(sc.id, s.n, { action: "move", to: s.n + 1 }), s.n >= shots.length));
        btnWrap.appendChild(mk("+", () => v2ShotEdit(sc.id, s.n, { action: "add" })));
        btnWrap.appendChild(mk("×", () => { if (confirm(`Delete shot ${s.n}?`)) v2ShotEdit(sc.id, s.n, { action: "delete" }); }, shots.length <= 1));
      } else {
        btnWrap.innerHTML = `<span style="font-size:var(--text-xs);color:#64748b">CSV shot</span>`;
      }
      tdBtns.appendChild(btnWrap);

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
        const cfg = _v2JobConfigForStep(12);
        if (summaryEl) summaryEl.textContent = `Starting director's shot list generation for "${slug}"…`;
        try {
          const o = typeof window.options === "function" ? window.options() : {};
          await callApi("/api/shot_list", { project: slug, engine: o.engine || "claude", claude_model: o.claude_model });
          watchV2JobProgress({ ...cfg, fresh: true });
        } catch (err) {
          if (/already running/i.test(String(err.message || ""))) {
            watchV2JobProgress({ ...cfg, fresh: false });
          } else {
            if (summaryEl) summaryEl.textContent = "Could not start shot list: " + err.message;
            btnBuild.disabled = false;
          }
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

    initV2EarlyPromptAudit();
  }

  function initV2EarlyPromptAudit() {
    document.querySelectorAll(".v2-early-audit-btn").forEach((btn) => {
      if (btn.dataset.auditBound) return;
      btn.dataset.auditBound = "1";
      btn.addEventListener("click", async () => {
        const selProj = $("proj");
        const slug = (selProj && selProj.value) || activeProject || "";
        if (!slug) {
          alert("Pick or save a book in Step 01 first.");
          return;
        }
        const stepNum = Number(btn.getAttribute("data-audit-step") || 0);
        const outEl = $(`v2EarlyAuditOut${stepNum}`);
        const origLabel = btn.textContent;
        btn.disabled = true;
        btn.textContent = "⏳ Auditing…";
        if (outEl) {
          outEl.classList.remove("hidden");
          outEl.style.borderColor = "#f59e0b";
          outEl.textContent = `Running AI prompt continuity audit for Step ${String(stepNum).padStart(2, "0")}…`;
        }
        try {
          const payload = { project: slug, step: stepNum, use_llm: true, auto_apply: true, record_bidirectional: true };
          if (stepNum === 12 && v2ShotScenes[v2ShotActiveSceneIdx]) {
            payload.scene = v2ShotScenes[v2ShotActiveSceneIdx].id || "";
          }
          const res = await callApi("/api/v2_early_prompt_audit", payload);
          if (outEl) {
            const issues = Array.isArray(res.issues) ? res.issues : [];
            const scorecard = Array.isArray(res.scorecard) ? res.scorecard : [];
            const blindSpots = Array.isArray(res.blind_spots) ? res.blind_spots : [];
            const hasFail = scorecard.some(c => String(c.rating || "").toLowerCase() === "fail") || issues.some(it => it.ambiguous || it.severity === "critical");
            const okColor = hasFail ? "#f87171" : (issues.length ? "#f59e0b" : "#22c55e");
            outEl.style.borderColor = okColor;
            outEl.textContent = "";

            const head = document.createElement("div");
            head.style.cssText = `font-weight:700;color:${okColor};margin-bottom:${(scorecard.length || issues.length || blindSpots.length) ? "6px" : "0"}`;
            head.textContent = res.message || `Step ${stepNum} audited.`;
            outEl.appendChild(head);

            // 1. Per-criterion Scorecard (Pass / Needs Work / Fail)
            if (scorecard.length) {
              const scBar = document.createElement("div");
              scBar.style.cssText = "display:flex;flex-wrap:wrap;gap:6px;margin-bottom:6px";
              scorecard.forEach((scItem) => {
                const rating = String(scItem.rating || "Pass");
                const rLow = rating.toLowerCase();
                const bg = rLow === "fail" ? "rgba(239,68,68,0.16)" : (rLow === "needs work" ? "rgba(245,158,11,0.16)" : "rgba(34,197,94,0.14)");
                const bd = rLow === "fail" ? "#ef4444" : (rLow === "needs work" ? "#f59e0b" : "#22c55e");
                const fg = rLow === "fail" ? "#fca5a5" : (rLow === "needs work" ? "#fde68a" : "#86efac");
                const pill = document.createElement("span");
                pill.title = String(scItem.reason || "");
                pill.style.cssText = `display:inline-flex;align-items:center;gap:4px;padding:2px 8px;border-radius:999px;background:${bg};border:1px solid ${bd};color:${fg};font-size:11px;font-weight:600`;
                pill.textContent = `${scItem.criterion || "Check"}: ${rating}`;
                scBar.appendChild(pill);
              });
              outEl.appendChild(scBar);
            }

            // 2. Severity-ordered Issues & Targeted Fixes / Ambiguities
            if (issues.length) {
              const ul = document.createElement("ul");
              ul.style.cssText = "margin:0;padding-left:16px;display:flex;flex-direction:column;gap:3px;";
              issues.slice(0, 12).forEach((it) => {
                const li = document.createElement("li");
                const sev = String(it.severity || "major").toUpperCase();
                const sevColor = sev === "CRITICAL" ? "#f87171" : (sev === "MINOR" ? "#94a3b8" : "#fbbf24");
                const sevTag = document.createElement("span");
                sevTag.style.cssText = `font-weight:700;color:${sevColor};margin-right:4px`;
                sevTag.textContent = `[${sev}]`;
                li.appendChild(sevTag);
                const stateTag = it.ambiguous ? "[Needs Decision] " : (it.fixed ? "[Auto-fixed] " : "[Check] ");
                const riskTxt = it.risk ? ` — Risk: ${it.risk}` : "";
                li.appendChild(document.createTextNode(`${stateTag}${it.target ? it.target + ": " : ""}${it.issue || ""}${riskTxt}`));
                ul.appendChild(li);
              });
              if (issues.length > 12) {
                const more = document.createElement("li");
                more.textContent = `…and ${issues.length - 12} more item(s).`;
                ul.appendChild(more);
              }
              outEl.appendChild(ul);
            }

            // 3. Blind Spots & Unverified Assumptions
            if (blindSpots.length) {
              const bsBox = document.createElement("div");
              bsBox.style.cssText = "margin-top:6px;padding-top:6px;border-top:1px dashed #334155;color:#94a3b8;font-size:11px";
              const bsTitle = document.createElement("div");
              bsTitle.style.cssText = "font-weight:700;color:#cbd5e1;margin-bottom:2px";
              bsTitle.textContent = "Blind Spots & Assumptions:";
              bsBox.appendChild(bsTitle);
              const bUl = document.createElement("ul");
              bUl.style.cssText = "margin:0;padding-left:16px;display:flex;flex-direction:column;gap:2px";
              blindSpots.slice(0, 6).forEach((b) => {
                const li = document.createElement("li");
                li.textContent = String(b || "");
                bUl.appendChild(li);
              });
              bsBox.appendChild(bUl);
              outEl.appendChild(bsBox);
            }
          }
          if (stepNum === 12) await loadV2ShotList();
          else if (stepNum === 7 && typeof loadV2Continuity === "function") await loadV2Continuity();
          else if (stepNum === 6 && typeof loadV2Screenplay === "function") await loadV2Screenplay();
          else if (stepNum === 5 && typeof loadV2Beats === "function") await loadV2Beats();
          else if (stepNum === 3 && typeof loadV2Coverage === "function") await loadV2Coverage();
        } catch (err) {
          if (outEl) {
            outEl.classList.remove("hidden");
            outEl.style.borderColor = "#ef4444";
            outEl.textContent = `Audit failed: ${err.message || err}`;
          }
        } finally {
          btn.disabled = false;
          btn.textContent = origLabel;
        }
      });
    });
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
  let v2DialogueState = { project: "", lines: [], scenes: [], dialect: "american", activeScene: "ALL", engine: "gemini-tts", engines: {}, baselines: {}, profiles: {} };

  function normVoiceChar(name) {
    return String(name || "").replace(/\s*\([^)]*\)\s*/g, " ").trim().toLowerCase();
  }

  function sameVoiceCharacter(a, b) {
    const la = String(a || "").trim().toLowerCase();
    const lb = String(b || "").trim().toLowerCase();
    return Boolean(la && lb && (la === lb || normVoiceChar(la) === normVoiceChar(lb)));
  }

  function applyVoiceProfileInMemory(character, prof) {
    if (!character || !prof) return 0;
    let count = 0;
    v2DialogueState.profiles = v2DialogueState.profiles || {};
    v2DialogueState.profiles[character] = { ...(v2DialogueState.profiles[character] || {}), ...prof };
    (v2DialogueState.lines || []).forEach(l => {
      if (!sameVoiceCharacter(l.character, character)) return;
      if (prof.gemini_voice !== undefined && prof.gemini_voice !== null) l.gemini_voice = prof.gemini_voice;
      if (prof.kokoro_voice !== undefined && prof.kokoro_voice !== null) {
        l.kokoro_voice = prof.kokoro_voice;
        if (prof.kokoro_voice) l.voice = prof.kokoro_voice;
      }
      if (prof.kokoro_blend !== undefined && prof.kokoro_blend !== null) l.kokoro_blend = prof.kokoro_blend;
      if (prof.macos_voice !== undefined && prof.macos_voice !== null) l.macos_voice = prof.macos_voice;
      if (prof.persona !== undefined && prof.persona !== null) l.persona = prof.persona;
      if (prof.speed !== undefined && prof.speed !== null && Number.isFinite(Number(prof.speed))) {
        l.speed = Number(prof.speed);
      }
      count += 1;
    });
    return count;
  }

  function getCharacterBaseline(character) {
    const b = v2DialogueState.baselines || {};
    const k = Object.keys(b).find(x => sameVoiceCharacter(x, character));
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
            if (res.profile) applyVoiceProfileInMemory(ch, res.profile);
            renderV2DialogueBaselines();
            renderV2DialogueList();
            setV2DialogueStatus(`✓ Locked "${f.name}" as ${ch}'s voice baseline and synced profile across ${res.updated_lines || 0} line(s).`);
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
      empty.style.cssText = "color:#94a3b8;grid-column:1 / -1";
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
      card.style.cssText = "display:flex;flex-direction:column;gap:8px;height:100%;min-width:0;box-sizing:border-box;padding:12px";

      // Header row
      const hdr = document.createElement("div");
      hdr.style.cssText = "display:flex;flex-direction:column;gap:6px";
      const left = document.createElement("div");
      left.style.cssText = "display:flex;align-items:center;flex-wrap:wrap;gap:6px";
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
            speed: p.speed,
          });
          // Update in-memory state for all lines of this character WITHOUT touching emotion/tone or note
          applyVoiceProfileInMemory(line.character, res.profile || p);
          renderV2DialogueList();
          setV2DialogueStatus(`✓ Saved ${line.character}'s voice profile (voice, blend, persona, speed) across ${res.updated_lines || 0} lines in all scenes (scene tones untouched).`);
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
          const p = extractCardPayload(card, line);
          setV2DialogueStatus(`Locking ${line.id} as ${line.character}'s voice baseline and filling voice profile across all scenes…`);
          try {
            const res = await callApi("/api/v2_voice_baseline_set", {
              project: v2DialogueState.project,
              character: line.character,
              from_line_id: line.id,
              text: p.text || line.text || "",
              gemini_voice: p.gemini_voice,
              kokoro_voice: p.kokoro_voice,
              kokoro_blend: p.kokoro_blend,
              macos_voice: p.macos_voice,
              persona: p.persona,
              speed: p.speed,
            });
            v2DialogueState.baselines[line.character] = res.baseline;
            applyVoiceProfileInMemory(line.character, res.profile || p);
            renderV2DialogueBaselines();
            renderV2DialogueList();
            setV2DialogueStatus(`✓ Locked ${line.id} as ${line.character}'s voice baseline and filled voice profile settings across ${res.updated_lines || 0} lines in all scenes (scene tones untouched).`);
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
      ta.rows = 3;
      ta.value = line.text || "";
      ta.setAttribute("aria-label", `Spoken dialogue text for ${line.id}`);
      ta.style.cssText = "width:100%;padding:8px 10px;background:#0a0d14;color:#f8fafc;border:1px solid #334155;border-radius:6px;font-size:var(--text-sm);resize:vertical;box-sizing:border-box;";
      card.appendChild(ta);

      // Row 1: Engine-specific Voice selector (+ Kokoro Blend selector) + Character Voice Persona
      const voiceRow = document.createElement("div");
      voiceRow.style.cssText = "display:flex;gap:6px;flex-wrap:wrap;align-items:center";

      const selVoice = document.createElement("select");
      selVoice.className = "v2-dlg-voice";
      selVoice.setAttribute("aria-label", `Voice for ${line.id}`);
      selVoice.style.cssText = "flex:1 1 160px;min-width:0;max-width:100%;padding:5px 8px;background:#0f172a;color:#f8fafc;border:1px solid #334155;border-radius:4px;font-size:var(--text-xs)";
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
        selBlend.setAttribute("aria-label", `Blend voice for ${line.id}`);
        selBlend.style.cssText = "flex:1 1 150px;min-width:0;max-width:100%;padding:5px 8px;background:#0f172a;color:#cbd5e1;border:1px solid #334155;border-radius:4px;font-size:var(--text-xs)";
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
      personaIn.setAttribute("aria-label", `Voice persona for ${line.id}`);
      personaIn.placeholder = "Voice Persona (e.g. energetic 5-year-old boy, warm gentle mother)…";
      personaIn.value = line.persona || "";
      personaIn.style.cssText = "flex:1 1 180px;min-width:0;padding:5px 8px;background:#0f172a;color:#fde68a;border:1px solid #475569;border-radius:4px;font-size:var(--text-xs)";
      voiceRow.appendChild(personaIn);
      card.appendChild(voiceRow);

      // Row 2: Per-scene Tone, Speed, and Delivery Direction Note
      const ctrl = document.createElement("div");
      ctrl.style.cssText = "display:flex;gap:6px;flex-wrap:wrap;align-items:center";

      const selEmo = document.createElement("select");
      selEmo.className = "v2-dlg-emotion";
      selEmo.setAttribute("aria-label", `Scene tone for ${line.id}`);
      selEmo.style.cssText = "flex:1 1 120px;min-width:0;padding:5px 8px;background:#0f172a;color:#f8fafc;border:1px solid #334155;border-radius:4px;font-size:var(--text-xs)";
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
      selSpd.setAttribute("aria-label", `Speech speed for ${line.id}`);
      selSpd.style.cssText = "flex:0 1 105px;min-width:0;padding:5px 8px;background:#0f172a;color:#f8fafc;border:1px solid #334155;border-radius:4px;font-size:var(--text-xs)";
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
      noteIn.setAttribute("aria-label", `Delivery direction note for ${line.id}`);
      noteIn.placeholder = "Scene delivery direction (e.g. waving, soft whisper)…";
      noteIn.value = line.note || "";
      noteIn.style.cssText = "flex:1 1 150px;min-width:0;padding:5px 8px;background:#0f172a;color:#cbd5e1;border:1px solid #334155;border-radius:4px;font-size:var(--text-xs)";
      ctrl.appendChild(noteIn);
      card.appendChild(ctrl);

      // Audio player bar (pinned to bottom of each tile for aligned grid rows)
      const playerWrap = document.createElement("div");
      playerWrap.style.cssText = "margin-top:auto;display:flex;align-items:center;gap:8px;background:#0a0d14;padding:6px 8px;border-radius:6px";
      if (line.has_audio && line.audio_url) {
        const aud = document.createElement("audio");
        aud.controls = true;
        aud.preload = "none";
        aud.src = line.audio_url;
        aud.style.cssText = "width:100%;height:30px";
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
      v2DialogueState.profiles = data.profiles || {};
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

    function populateV2FoleyPresetSelect(selEl, selectedVal) {
      if (!selEl) return;
      const list = (Array.isArray(v2SoundState.presets) && v2SoundState.presets.length)
        ? v2SoundState.presets
        : [
            { id: "custom", label: "✏️ Custom (From Text)", prompt: "", group: "Core" },
            { id: "silent", label: "🔇 Silent (No SFX)", prompt: "Silent (no ambient SFX or foley).", group: "Core" },
            { id: "soft_rain_room", label: "Soft Distant Rain & Quiet Room", prompt: "Subtle muffled distant rain outside a quiet cozy room.", group: "Universal" },
            { id: "rainy_home", label: "Rain on Window & Cozy Room", prompt: "Steady rain pattering on a living room window.", group: "Universal" },
            { id: "forest_nature", label: "Quiet Night & Nature Breeze", prompt: "Gentle evening breeze with distant night crickets.", group: "Universal" },
          ];
      const byGroup = new Map();
      list.forEach(p => {
        const g = p.group || "Story";
        if (!byGroup.has(g)) byGroup.set(g, []);
        byGroup.get(g).push(p);
      });
      selEl.textContent = "";
      byGroup.forEach((items, gName) => {
        const grp = document.createElement("optgroup");
        grp.label = gName;
        items.forEach(p => {
          const o = document.createElement("option");
          o.value = p.id;
          o.textContent = p.label || p.id;
          if (p.id === selectedVal) o.selected = true;
          grp.appendChild(o);
        });
        selEl.appendChild(grp);
      });
      if (selectedVal && [...selEl.options].some(o => o.value === selectedVal)) {
        selEl.value = selectedVal;
      }
    }
    window._populateV2FoleyPresetSelect = populateV2FoleyPresetSelect;

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
      row.className = "v2-sound-scene-row" + (sc.has_sfx ? " has-audio" : "");
      row.dataset.sceneId = sc.scene;

      // Tile Header: Scene ID Pill + Heading + Status Badge
      const hdr = document.createElement("div");
      hdr.className = "v2-sc-hdr";
      const titleGroup = document.createElement("div");
      titleGroup.className = "v2-sc-title-group";
      const idPill = document.createElement("span");
      idPill.className = "v2-sc-id-pill";
      idPill.textContent = sc.scene;
      const headEl = document.createElement("span");
      headEl.className = "v2-sc-heading";
      headEl.textContent = sc.heading || "Scene";
      titleGroup.appendChild(idPill);
      titleGroup.appendChild(headEl);

      const stBadge = document.createElement("span");
      stBadge.className = "status-badge " + (sc.has_sfx ? "status-badge--synced" : "");
      stBadge.style.cssText = "font-size:10px;flex-shrink:0;";
      stBadge.textContent = sc.has_sfx ? "✓ Custom SFX" : "Default";
      hdr.appendChild(titleGroup);
      hdr.appendChild(stBadge);
      row.appendChild(hdr);

      // Full untruncated scene action description
      if (sc.hint) {
        const hint = document.createElement("div");
        hint.className = "v2-sc-desc";
        hint.textContent = sc.hint;
        row.appendChild(hint);
      }

      const normCue = s => String(s || "").trim().toLowerCase().replace(/\s+/g, " ");
      const origCue = (sc.sfx_cue || "").trim();
      const origPreset = sc.sfx_preset || "";
      const sameDescCount = scenes.filter(x => normCue(x.sfx_cue) && normCue(x.sfx_cue) === normCue(origCue)).length;

      // Controls: Full-width SFX text override + 2-column Preset & Score Mood selects
      const ctrls = document.createElement("div");
      ctrls.className = "v2-sc-controls";

      const cueWrap = document.createElement("div");
      const cueLbl = document.createElement("label");
      cueLbl.className = "v2-sc-field-lbl";
      cueLbl.textContent = "SFX Description (custom text overrides preset)";
      const cueIn = document.createElement("textarea");
      cueIn.rows = 2;
      cueIn.className = "v2-sc-sfx-cue";
      cueIn.value = sc.sfx_cue || "";
      cueIn.placeholder = "Type custom SFX (e.g. a low spaceship hum and distant voices in background)…";
      cueWrap.appendChild(cueLbl);
      cueWrap.appendChild(cueIn);

      const selRow = document.createElement("div");
      selRow.className = "v2-sc-selects";

      const preWrap = document.createElement("div");
      const preLbl = document.createElement("label");
      preLbl.className = "v2-sc-field-lbl";
      preLbl.textContent = "SFX Preset";
      const selPre = document.createElement("select");
      selPre.className = "v2-sc-sfx-preset";
      populateV2FoleyPresetSelect(selPre, sc.sfx_preset);
      selPre.addEventListener("change", () => {
        const picked = (v2SoundState.presets || []).find(p => p.id === selPre.value);
        if (picked && picked.prompt && selPre.value !== "custom") {
          cueIn.value = picked.prompt;
        }
      });
      cueIn.addEventListener("input", () => {
        if (cueIn.value.trim() && cueIn.value.trim() !== origCue) {
          selPre.value = "custom";
        }
      });
      preWrap.appendChild(preLbl);
      preWrap.appendChild(selPre);

      const moodWrap = document.createElement("div");
      const moodLbl = document.createElement("label");
      moodLbl.className = "v2-sc-field-lbl";
      moodLbl.textContent = "Score Mood";
      const selMood = document.createElement("select");
      selMood.className = "v2-sc-score-mood";
      MOODS.forEach(([k, l]) => {
        const o = document.createElement("option");
        o.value = k; o.textContent = l;
        if (k === sc.score_mood) o.selected = true;
        selMood.appendChild(o);
      });
      moodWrap.appendChild(moodLbl);
      moodWrap.appendChild(selMood);

      selRow.appendChild(preWrap);
      selRow.appendChild(moodWrap);
      ctrls.appendChild(cueWrap);
      ctrls.appendChild(selRow);
      row.appendChild(ctrls);

      // Action buttons row
      const btns = document.createElement("div");
      btns.className = "v2-sc-actions";
      const btnRen = document.createElement("button");
      btnRen.type = "button";
      btnRen.className = "btn btn--primary";
      btnRen.style.flex = "1";
      btnRen.textContent = sc.has_sfx ? "↺ Redo SFX" : "✨ Render SFX";

      const btnProp = document.createElement("button");
      btnProp.type = "button";
      btnProp.className = "btn btn--secondary";
      btnProp.textContent = sameDescCount > 1
        ? `📌 Propagate (${sameDescCount})`
        : "📌 Save & Propagate";
      btnProp.title = "Save this SFX preset, description (or blank), score mood, and audio clip, and copy it to every scene with the same SFX description";

      const upIn = document.createElement("input");
      upIn.type = "file";
      upIn.accept = "audio/*";
      upIn.style.display = "none";
      const btnUp = document.createElement("button");
      btnUp.type = "button";
      btnUp.className = "btn btn--ghost";
      btnUp.textContent = "⬆ Upload";
      btnUp.addEventListener("click", () => upIn.click());

      btns.appendChild(btnRen);
      btns.appendChild(btnProp);
      btns.appendChild(btnUp);
      btns.appendChild(upIn);
      row.appendChild(btns);

      // Audio player pinned evenly at tile bottom
      const player = document.createElement("div");
      player.className = "v2-sc-player";
      if (sc.has_sfx && sc.sfx_url) {
        const aud = document.createElement("audio");
        aud.controls = true;
        aud.preload = "none";
        aud.src = sc.sfx_url + (sc.sfx_url.includes("?") ? "&" : "?") + "t=" + Date.now();
        player.appendChild(aud);
      } else {
        player.textContent = "Using master / video-aligned SFX — click ✨ Render SFX or ⬆ Upload";
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
          const lyrTag = (res.layers && res.layers.length) ? ` (layers: ${res.layers.join(", ")})` : "";
          setV2SoundStatus(`✓ Rendered custom SFX for ${sc.scene}${lyrTag}!`);
          const newAud = document.querySelector(`#v2SoundScenesList .v2-sound-scene-row[data-scene-id="${sc.scene}"] audio`);
          if (newAud) newAud.play().catch(() => {});
        } catch (err) {
          setV2SoundStatus(`Scene ${sc.scene} SFX failed: ` + (err.message || err), true);
        } finally {
          stopBusy();
        }
      });

      btnProp.addEventListener("click", async () => {
        const curCue = cueIn.value.trim();
        const curPre = selPre.value;
        const curMood = selMood.value;
        const presetChanged = curPre !== origPreset;
        const cueChanged = curCue !== origCue;
        const stopBusy = startBusyFeedback(btnProp, row, `Propagating ${sc.scene} SFX to matching scenes…`);
        setV2SoundStatus(`Saving & propagating ${sc.scene}'s SFX to all scenes with the same description…`);
        try {
          const res = await callApi("/api/v2_sound_sfx_propagate", {
            project: v2SoundState.project,
            source_scene: sc.scene,
            match_cue: origCue,
            sfx_cue: curCue,
            sfx_preset: curPre,
            score_mood: curMood,
            duration: 8,
            render_source: presetChanged || cueChanged || !sc.has_sfx,
          });
          const updatedIds = new Set(res.updated_scenes || [sc.scene]);
          const urls = res.audio_urls || {};
          (v2SoundState.scenes || []).forEach(item => {
            if (!updatedIds.has(item.scene)) return;
            item.sfx_cue = curCue;
            item.sfx_preset = curPre;
            item.score_mood = curMood;
            if (urls[item.scene]) {
              item.has_sfx = true;
              item.sfx_url = urls[item.scene];
            }
          });
          renderV2SoundScenesList();
          setV2SoundStatus(`✓ Saved & propagated SFX to ${res.count || updatedIds.size} matching scene(s): ${(res.updated_scenes || []).join(", ")}`);
        } catch (err) {
          setV2SoundStatus(`Propagate failed for ${sc.scene}: ` + (err.message || err), true);
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
      v2SoundState.presets = Array.isArray(data.presets) ? data.presets : [];
      v2SoundState.scenes = data.scenes || [];
      renderV2SoundModeUI();
      renderV2SoundScenesList();
      const f = data.foley || {};
      const s = data.score || {};
      if (window._populateV2FoleyPresetSelect) {
        window._populateV2FoleyPresetSelect($("v2FoleyPreset"), f.preset || "custom");
      }
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
      spaceship_voices: "A low spaceship hum and distant voices in background.",
      rainy_home: "Steady rain pattering on a living room window, individual droplets on glass, and soft distant thunder.",
      soft_rain_room: "Subtle muffled distant rain outside a quiet cozy room (not hitting the window), gentle soft indoor room tone.",
      cosmic_storm: "Sweeping atmospheric wind gusts, sparkling ice-ring crystal chimes, and deep planetary resonance.",
      action_launch: "Building rocket engine roar, heavy sub-bass ignition rumble, and rising thruster turbine whine.",
      forest_nature: "Gentle evening breeze with rhythmic distant night crickets and quiet outdoor air.",
      silent: "Silent (no ambient SFX or foley).",
    };
    const selFoleyPreset = $("v2FoleyPreset");
    const taFoleyPrompt = $("v2FoleyPrompt");
    if (selFoleyPreset) {
      selFoleyPreset.addEventListener("change", () => {
        const found = (v2SoundState.presets || []).find(x => x.id === selFoleyPreset.value);
        const p = (found && found.prompt) || FOLEY_PRESET_PROMPTS[selFoleyPreset.value];
        if (p && taFoleyPrompt) taFoleyPrompt.value = p;
      });
    }
    if (taFoleyPrompt && selFoleyPreset) {
      taFoleyPrompt.addEventListener("input", () => {
        const curTxt = taFoleyPrompt.value.trim();
        const isStock = (v2SoundState.presets || []).some(x => String(x.prompt || "").trim() === curTxt) ||
          Object.values(FOLEY_PRESET_PROMPTS).some(v => v.trim() === curTxt);
        if (curTxt && !isStock) {
          selFoleyPreset.value = "custom";
        }
      });
    }
    const btnSavePreset = $("bV2SaveSfxPreset");
    if (btnSavePreset) {
      btnSavePreset.addEventListener("click", async () => {
        const slug = getSlug();
        const prompt = (taFoleyPrompt?.value || "").trim();
        if (!prompt) { setV2SoundStatus("Type an SFX description first before saving as a reusable preset.", true); return; }
        const label = window.prompt("Name for this reusable SFX preset (available in all stories):", prompt.slice(0, 36));
        if (!label || !label.trim()) return;
        btnSavePreset.disabled = true;
        try {
          const res = await callApi("/api/v2_sound_preset_save", { project: slug, label: label.trim(), prompt });
          if (Array.isArray(res.presets) && res.presets.length) {
            v2SoundState.presets = res.presets;
            if (window._populateV2FoleyPresetSelect) {
              window._populateV2FoleyPresetSelect($("v2FoleyPreset"), res.saved?.id || "custom");
            }
            renderV2SoundScenesList();
          }
          setV2SoundStatus(`✓ Saved "${label.trim()}" to Reusable SFX Library (available across all stories).`);
        } catch (err) {
          setV2SoundStatus("Could not save preset: " + (err.message || err), true);
        } finally {
          btnSavePreset.disabled = false;
        }
      });
    }

    const SCORE_MOOD_PROMPTS = {
      wonder: "Sweeping cinematic orchestral strings, warm French horns, and sparkling celesta arpeggios in major key.",
      epic: "Driving 120 BPM pulsing bass ostinato, bold heroic brass fifths, and deep booming timpani drums.",
      cozy: "Gentle 3/4 family waltz with warm Rhodes electric piano chords, soft bass, and delicate music-box twinkles.",
      mysterious: "Dark minor-key cosmic synth drone, eerie glass-harmonica shimmer, and sparse echoing metallic bells.",
      playful: "Bouncy 145 BPM pizzicato strings and cheerful staccato xylophone & glockenspiel adventure melody.",
      none: "Silent (no musical score).",
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
          const lyrTag = (res.layers && res.layers.length) ? ` (${res.layers.join(", ")})` : "";
          setV2SoundStatus(`✓ Generated ${res.duration || 12}s Foley track${lyrTag}!`);
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

  function _currentV2VisualEngine() {
    return v2SelectedHardware === "computer" ? "local" : v2SelectedHardware;
  }

  async function loadV2VideoClips() {
    const slug = ($("proj")?.value || activeProject || "").trim();
    const grid = $("v2VideoClipsGrid");
    const selShot = $("v2LocalVideoShotSelect");
    if (!grid || !slug) return;
    try {
      const kf = await callApi(`/api/v2_keyframes?project=${encodeURIComponent(slug)}`);
      const shots = (kf.scenes || []).flatMap(sc => sc.shots || []);
      if (selShot && shots.length) {
        const prev = selShot.value;
        selShot.innerHTML = shots.map(s => `<option value="${s.id}">${s.id} · ${s.type || "Shot"} (${s.seconds || 4}s)${s.has_image ? " ✓KF" : ""}</option>`).join("");
        if (shots.some(s => s.id === prev)) selShot.value = prev;
      }
      grid.innerHTML = "";
      const displayShots = shots.filter(s => s.has_image).slice(0, 12);
      if (!displayShots.length) {
        const empty = document.createElement("div");
        empty.className = "direct-story-card";
        empty.style.cssText = "grid-column:1/-1;color:#94a3b8;font-size:var(--text-sm)";
        empty.textContent = "Render keyframes in Step 17 or select a shot above and click 🎬 Synthesize Shot Video Locally.";
        grid.appendChild(empty);
        return;
      }
      displayShots.forEach(s => {
        const card = document.createElement("div");
        card.className = "deliverable-card";
        const vidUrl = `/file/${slug}/videos/${s.id}.mp4`;
        card.innerHTML = `
          <div style="background:#000;aspect-ratio:16/9;border-radius:6px;overflow:hidden;display:flex;align-items:center;justify-content:center;color:#38bdf8;position:relative">
            <video src="${vidUrl}" poster="${s.image_url || ""}" controls preload="metadata" style="width:100%;height:100%;object-fit:cover"></video>
          </div>
          <strong style="color:#f59e0b;margin-top:6px">${s.id} &middot; ${s.type || "Shot"} (${s.seconds || 4}s)</strong>
          <button type="button" class="btn btn--secondary v2-redo-clip-btn" data-shot-id="${s.id}" style="margin-top:4px;font-size:var(--text-xs)">🎬 Synthesize / Redo Clip</button>
        `;
        const btn = card.querySelector(".v2-redo-clip-btn");
        if (btn) {
          btn.addEventListener("click", async () => {
            if (selShot) selShot.value = s.id;
            $("bV2RunLocalVideo")?.click();
          });
        }
        grid.appendChild(card);
      });
    } catch (e) {}
  }

  async function renderSingleKeyframe(shot, promptText, triggerBtn, cardEl, opts = {}) {
    const stopBusy = startBusyFeedback(triggerBtn, cardEl, `Generating keyframe ${shot.id}…`);
    setV2KfStatus(`Generating 16:9 keyframe for ${shot.id} (${_currentV2VisualEngine()})…`);
    try {
      const payload = {
        project: v2KfState.project,
        id: shot.id,
        prompt: promptText,
        aspect_ratio: "16:9",
        engine: _currentV2VisualEngine(),
      };
      if (opts.initStrength !== undefined && opts.initStrength !== null && opts.initStrength !== "auto") {
        payload.init_strength = Number(opts.initStrength);
      }
      if (opts.freshSeed) {
        payload.fresh_seed = true;
      }
      const res = await callApi("/api/v2_keyframe_render", payload);
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
      const qaLbl = res.qa_engine ? ` (${res.qa_engine})` : "";
      const physTag = res.physics_repaired
        ? (res.physics_passed ? ` · ✓ QA auto-repaired${qaLbl}` : ` · ⚠️ QA flagged${qaLbl}`)
        : (res.physics_passed === false ? ` · ⚠️ QA flagged${qaLbl}` : ` · ✓ QA verified${qaLbl}`);
      const refNames = (res.char_refs_used || []).map(x => x.name).filter(Boolean);
      const setTag = res.set_ref_used && res.set_ref_used.name ? ` · Set: ${res.set_ref_used.name}` : "";
      const refTag = refNames.length
        ? `${setTag} · Turnarounds: ${refNames.join(", ")}`
        : (setTag || (res.refs_used ? ` · ${res.refs_used} ref(s)` : ""));
      const lockTag = res.init_strength_used
        ? ` · Lock ${Number(res.init_strength_used).toFixed(2)} (${res.primary_ref_id || res.continuity_mode})`
        : (res.anchor_shot_ref ? ` · Anchor ${res.anchor_shot_ref}` : "");
      setV2KfStatus(`✓ Rendered keyframe ${shot.id} (${res.model || "image"}${refTag}${lockTag})${physTag}`, res.physics_passed === false);
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
        img.addEventListener("click", () => window.open(img.src, "_blank"));
        preview.appendChild(img);
        if (shot.has_pass1 && shot.pass1_url) {
          let showingBefore = false;
          const btnReveal = document.createElement("button");
          btnReveal.type = "button";
          btnReveal.className = "btn btn--secondary";
          btnReveal.style.cssText = "position:absolute;bottom:6px;left:6px;padding:2px 8px;font-size:10px;background:rgba(15,23,42,0.88);border:1px solid #f59e0b;color:#fde68a;";
          btnReveal.textContent = "👁️ Show Pass 1 (Before 2D)";
          btnReveal.addEventListener("click", (ev) => {
            ev.stopPropagation();
            showingBefore = !showingBefore;
            img.src = showingBefore ? shot.pass1_url : shot.image_url;
            btnReveal.textContent = showingBefore ? "👁️ Show Pass 2 (With 2D Cast)" : "👁️ Show Pass 1 (Before 2D)";
          });
          preview.appendChild(btnReveal);
        }
        if (shot.is_anchor) {
          const ab = document.createElement("span");
          ab.style.cssText = "position:absolute;top:6px;left:6px;padding:2px 8px;border-radius:999px;background:rgba(56,189,248,0.92);color:#082f49;font-size:10.5px;font-weight:700;";
          ab.textContent = "📍 Scene Anchor";
          preview.appendChild(ab);
        }
        if (shot.locked) {
          const lbadge = document.createElement("span");
          lbadge.style.cssText = "position:absolute;top:6px;right:6px;padding:2px 8px;border-radius:999px;background:rgba(16,185,129,0.92);color:#022c22;font-size:11px;font-weight:700;";
          lbadge.textContent = "🔒 Locked";
          preview.appendChild(lbadge);
          card.style.borderColor = "#10b981";
        }
      } else if (shot.has_pass1 && shot.pass1_url) {
        const img = document.createElement("img");
        img.src = shot.pass1_url;
        img.alt = `Pass 1 Live Plate ${shot.id}`;
        img.style.cssText = "width:100%;height:100%;object-fit:cover;cursor:zoom-in;display:block";
        img.addEventListener("click", () => window.open(shot.pass1_url, "_blank"));
        preview.appendChild(img);
        const p1Badge = document.createElement("span");
        p1Badge.style.cssText = "position:absolute;top:6px;left:6px;padding:2px 8px;border-radius:999px;background:rgba(245,158,11,0.9);color:#0f172a;font-size:10px;font-weight:700;";
        p1Badge.textContent = "1️⃣ Pass 1 Ready · Run Pass 2 for 2D Cast";
        preview.appendChild(p1Badge);
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

      // Attached Step 10 Turnaround & Step 11 Set Reference Strip
      const charRefs = Array.isArray(shot.char_refs) ? shot.char_refs : [];
      const matchedLocs = Array.isArray(shot.matched_locations) ? shot.matched_locations : [];
      if (charRefs.length || matchedLocs.length || shot.prompt_outdated) {
        const refBar = document.createElement("div");
        refBar.className = "v2-kf-refs";
        charRefs.forEach(cr => {
          const chip = document.createElement("span");
          if (cr.has_ref && cr.ref_url) {
            chip.className = "v2-kf-ref-chip";
            chip.title = `Attached ${cr.ref_source || "turnaround"} reference for ${cr.name} (click to inspect)`;
            const thumb = document.createElement("img");
            thumb.src = cr.ref_url;
            thumb.alt = cr.name;
            chip.appendChild(thumb);
            const lbl = document.createElement("span");
            lbl.textContent = cr.name;
            chip.appendChild(lbl);
            chip.addEventListener("click", () => window.open(cr.ref_url, "_blank"));
          } else {
            chip.className = "v2-kf-ref-chip v2-kf-ref-chip--missing";
            chip.title = `No Step 10 turnaround found for ${cr.name} yet — generate in Step 10 for visual lock`;
            chip.textContent = `⚠ ${cr.name} (no turnaround)`;
          }
          refBar.appendChild(chip);
        });
        if (matchedLocs.length || shot.set_ref_url) {
          const locChip = document.createElement("span");
          locChip.className = "v2-kf-ref-chip v2-kf-ref-chip--set";
          if (shot.set_ref_url) {
            const setThumb = document.createElement("img");
            setThumb.src = shot.set_ref_url;
            setThumb.alt = matchedLocs.join(" + ") || "Set Plate";
            locChip.appendChild(setThumb);
          }
          const locLbl = document.createElement("span");
          locLbl.textContent = `🏛 ${matchedLocs.join(" + ") || "Set Plate"}`;
          locChip.appendChild(locLbl);
          locChip.title = shot.set_ref_url
            ? "Locked Step 11 Set Plate attached as primary environment reference (click to inspect)"
            : "Step 11 locked location description applied";
          if (shot.set_ref_url) {
            locChip.style.cursor = "pointer";
            locChip.addEventListener("click", () => window.open(shot.set_ref_url, "_blank"));
          }
          refBar.appendChild(locChip);
        }
        if (shot.prompt_outdated && shot.default_prompt && !shot.locked) {
          const syncChip = document.createElement("button");
          syncChip.type = "button";
          syncChip.className = "v2-kf-ref-chip v2-kf-ref-chip--sync";
          syncChip.textContent = "🔄 Sync Prompt";
          syncChip.title = "Saved prompt differs from latest Steps 08–12 cast/set/shot details — click to refresh this shot's prompt";
          syncChip.addEventListener("click", () => {
            ta.value = shot.default_prompt;
            shot.prompt = shot.default_prompt;
            shot.prompt_outdated = false;
            syncChip.remove();
            setV2KfStatus(`✓ Refreshed ${shot.id} prompt from latest Steps 08–12 (click Save Prompts or Generate to persist).`);
          });
          refBar.appendChild(syncChip);
        }
        card.appendChild(refBar);
      }

      // Editable visual prompt
      const ta = document.createElement("textarea");
      ta.className = "v2-kf-prompt";
      ta.rows = 4;
      ta.value = shot.prompt || "";
      ta.style.cssText = "width:100%;padding:6px 8px;background:#0a0d14;color:#e2e8f0;border:1px solid #334155;border-radius:4px;font-size:11px;resize:vertical;margin-top:4px";
      card.appendChild(ta);

      // Same-Angle Camera Lock, Similarity Slider & Scene Seed controls (#1)
      let selectedStrength = "auto";
      const hasSpatialBase = Boolean(shot.prev_rendered_id || (sc.anchor_shot_id && sc.anchor_shot_id !== shot.id));
      const camBox = document.createElement("div");
      camBox.className = "v2-kf-camlock";
      const camTop = document.createElement("div");
      camTop.className = "v2-kf-camlock__row";

      const modeBadge = document.createElement("span");
      const isSame = shot.camera_match_mode === "same_angle";
      const isInc = shot.camera_match_mode === "incremental";
      modeBadge.className = "v2-kf-camlock__badge" + (isSame ? " v2-kf-camlock__badge--locked" : "");
      if (isSame) {
        modeBadge.textContent = `🎯 Same Angle · Auto Lock (${shot.recommended_strength || 0.45})`;
      } else if (isInc) {
        modeBadge.textContent = `🔄 Incremental · Auto Lock (${shot.recommended_strength || 0.62})`;
      } else if (sc.anchor_shot_id && sc.anchor_shot_id !== shot.id) {
        modeBadge.textContent = `📍 Anchor: ${sc.anchor_shot_id}`;
      } else {
        modeBadge.textContent = `🎬 Scene Seed Locked`;
      }
      camTop.appendChild(modeBadge);

      const seedLbl = document.createElement("label");
      seedLbl.style.cssText = "display:inline-flex;align-items:center;gap:4px;font-size:10.5px;color:#94a3b8;cursor:pointer";
      const freshSeedChk = document.createElement("input");
      freshSeedChk.type = "checkbox";
      freshSeedChk.className = "v2-kf-fresh-seed";
      seedLbl.appendChild(freshSeedChk);
      seedLbl.appendChild(document.createTextNode("🎲 New Seed"));
      seedLbl.title = "Unchecked = share deterministic Scene Seed across this scene for maximum consistency; check to roll a random seed";
      camTop.appendChild(seedLbl);
      camBox.appendChild(camTop);

      if (hasSpatialBase && !shot.locked) {
        const sliderRow = document.createElement("div");
        sliderRow.className = "v2-kf-camlock__row";
        const sLbl = document.createElement("span");
        sLbl.style.cssText = "font-size:10.5px;color:#94a3b8;white-space:nowrap";
        sLbl.textContent = "Change:";
        const sRange = document.createElement("input");
        sRange.type = "range";
        sRange.min = "0.25";
        sRange.max = "1.00";
        sRange.step = "0.05";
        sRange.value = String(shot.recommended_strength != null ? shot.recommended_strength : 1.0);
        sRange.title = "Lower (0.30-0.45) = lock background & only shift character pose/expression; 1.00 = fresh camera angle using references only";
        const sVal = document.createElement("span");
        sVal.style.cssText = "font-size:10.5px;color:#fde68a;min-width:68px;text-align:right;font-weight:600";
        sVal.textContent = shot.recommended_strength != null ? `Auto (${Number(shot.recommended_strength).toFixed(2)})` : "Auto (Fresh)";
        sRange.addEventListener("input", () => {
          const v = parseFloat(sRange.value);
          selectedStrength = v;
          sVal.textContent = v >= 0.99 ? "Fresh (1.0)" : `Lock (${v.toFixed(2)})`;
        });
        sliderRow.appendChild(sLbl);
        sliderRow.appendChild(sRange);
        sliderRow.appendChild(sVal);
        camBox.appendChild(sliderRow);
      }
      card.appendChild(camBox);

      // Action buttons
      const row = document.createElement("div");
      row.style.cssText = "display:flex;gap:6px;flex-wrap:wrap;margin-top:6px";

      const btnGen = document.createElement("button");
      btnGen.type = "button";
      btnGen.className = "btn " + (shot.has_image ? "btn--secondary" : "btn--primary");
      btnGen.style.cssText = "padding:4px 10px;font-size:var(--text-xs);flex:1";
      btnGen.textContent = shot.locked ? "🔒 Locked" : (shot.has_image ? "↺ Re-roll" : "✨ Generate Keyframe");
      btnGen.disabled = Boolean(shot.locked);
      btnGen.addEventListener("click", () => renderSingleKeyframe(shot, ta.value.trim(), btnGen, card, {
        initStrength: selectedStrength,
        freshSeed: Boolean(freshSeedChk.checked),
      }));

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

      // #3 Clone Prev Frame & Edit button (shown when a prior rendered shot or Scene Anchor exists and shot is unlocked)
      const cloneSourceId = shot.prev_rendered_id || (sc.anchor_shot_id && sc.anchor_shot_id !== shot.id ? sc.anchor_shot_id : "");
      let clonePanel = null;
      if (cloneSourceId && !shot.locked) {
        const btnClone = document.createElement("button");
        btnClone.type = "button";
        btnClone.className = "btn btn--ghost";
        btnClone.style.cssText = "padding:4px 8px;font-size:var(--text-xs);color:#7dd3fc";
        btnClone.textContent = "📋 Clone Prev";
        btnClone.title = `Clone ${cloneSourceId} directly into ${shot.id} and apply a tight locked-camera edit (or copy frame for Canvas mask inpainting)`;
        btnClone.addEventListener("click", () => {
          if (clonePanel) clonePanel.style.display = clonePanel.style.display === "none" ? "flex" : "none";
        });
        row.appendChild(btnClone);

        clonePanel = document.createElement("div");
        clonePanel.className = "v2-kf-clone-panel";
        clonePanel.style.display = "none";
        const cHdr = document.createElement("div");
        cHdr.style.cssText = "font-size:11px;font-weight:700;color:#7dd3fc";
        cHdr.textContent = `📋 Clone ${cloneSourceId} → ${shot.id} (Locked-Camera Background)`;
        const cIn = document.createElement("input");
        cIn.type = "text";
        cIn.value = [shot.action, shot.expression].filter(Boolean).join(". ");
        cIn.placeholder = "Describe ONLY what changes (e.g. Judah flops down beside Tommy)…";
        cIn.style.cssText = "width:100%;padding:5px 8px;background:#0f172a;color:#f8fafc;border:1px solid #334155;border-radius:4px;font-size:11px";
        const cBtns = document.createElement("div");
        cBtns.style.cssText = "display:flex;gap:6px;flex-wrap:wrap";
        const btnCloneApply = document.createElement("button");
        btnCloneApply.type = "button";
        btnCloneApply.className = "btn btn--primary";
        btnCloneApply.style.cssText = "padding:4px 9px;font-size:11px";
        btnCloneApply.textContent = "✨ Clone & Apply Action";
        btnCloneApply.addEventListener("click", async () => {
          const stopBusy = startBusyFeedback(btnCloneApply, card, `Cloning ${cloneSourceId} & applying action…`);
          try {
            const res = await callApi("/api/v2_keyframe_clone_edit", {
              project: v2KfState.project,
              id: shot.id,
              source_id: cloneSourceId,
              edit_instruction: cIn.value.trim(),
              prompt: ta.value.trim(),
              apply_edit: true,
              strength: 0.38,
              engine: _currentV2VisualEngine(),
            });
            if (!shot.has_image) v2KfState.rendered_shots++;
            shot.has_image = true;
            shot.image_url = res.image_url + "?t=" + Date.now();
            renderV2KfScenesBar();
            renderV2KfGrid();
            setV2KfStatus(`✓ Cloned ${res.source_id} & applied locked-camera edit for ${shot.id} (strength ${res.strength_used}).`);
          } catch (err) {
            setV2KfStatus("Clone & edit failed: " + (err.message || err), true);
          } finally {
            stopBusy();
          }
        });
        const btnCloneOnly = document.createElement("button");
        btnCloneOnly.type = "button";
        btnCloneOnly.className = "btn btn--secondary";
        btnCloneOnly.style.cssText = "padding:4px 9px;font-size:11px";
        btnCloneOnly.textContent = "📋 Copy Frame Only (for Canvas)";
        btnCloneOnly.addEventListener("click", async () => {
          const stopBusy = startBusyFeedback(btnCloneOnly, card, `Copying ${cloneSourceId}…`);
          try {
            const res = await callApi("/api/v2_keyframe_clone_edit", {
              project: v2KfState.project,
              id: shot.id,
              source_id: cloneSourceId,
              apply_edit: false,
            });
            if (!shot.has_image) v2KfState.rendered_shots++;
            shot.has_image = true;
            shot.image_url = res.image_url + "?t=" + Date.now();
            renderV2KfScenesBar();
            renderV2KfGrid();
            setV2KfStatus(`✓ Copied ${res.source_id} into ${shot.id} — click 🎨 Mask Inpaint to edit only the changing region!`);
          } catch (err) {
            setV2KfStatus("Copy failed: " + (err.message || err), true);
          } finally {
            stopBusy();
          }
        });
        cBtns.appendChild(btnCloneApply);
        cBtns.appendChild(btnCloneOnly);
        clonePanel.appendChild(cHdr);
        clonePanel.appendChild(cIn);
        clonePanel.appendChild(cBtns);
      }

      // #4 Camera-Angle Shift button (ComfyUI Qwen-Image-Edit `apps/angles` + free local Kontext/FLUX.2 fallback)
      const angleSourceAvail = Boolean(cloneSourceId || sc.has_set_plate);
      let anglePanel = null;
      if (angleSourceAvail && !shot.locked) {
        const btnAngle = document.createElement("button");
        btnAngle.type = "button";
        btnAngle.className = "btn btn--ghost";
        btnAngle.style.cssText = "padding:4px 8px;font-size:var(--text-xs);color:#d8b4fe";
        btnAngle.textContent = "🎥 New Angle";
        btnAngle.title = "Generate a new camera angle of this scene's Anchor / Set Plate using ComfyUI Angles (Qwen-Image-Edit) or free local Kontext/FLUX.2";
        btnAngle.addEventListener("click", () => {
          if (anglePanel) anglePanel.style.display = anglePanel.style.display === "none" ? "flex" : "none";
        });
        row.appendChild(btnAngle);

        anglePanel = document.createElement("div");
        anglePanel.className = "v2-kf-angle-panel";
        anglePanel.style.display = "none";
        const aHdr = document.createElement("div");
        aHdr.style.cssText = "font-size:11px;font-weight:700;color:#d8b4fe";
        aHdr.textContent = `🎥 Shift Camera Angle from ${cloneSourceId || "Step 11 Set Plate"}`;
        const aRow = document.createElement("div");
        aRow.style.cssText = "display:flex;gap:6px;flex-wrap:wrap;align-items:center";
        const aSel = document.createElement("select");
        aSel.style.cssText = "flex:1;min-width:140px;padding:4px 7px;background:#0f172a;color:#f8fafc;border:1px solid #334155;border-radius:4px;font-size:11px";
        [
          ["rotate_left_45", "↺ Rotate 45° Left"],
          ["rotate_right_45", "↻ Rotate 45° Right"],
          ["move_forward", "🔍 Move Forward (Closer)"],
          ["move_back", "🔭 Move Back (Wider)"],
          ["move_left", "⬅ Truck Left"],
          ["move_right", "➡ Truck Right"],
          ["move_up", "⬆ Crane Up"],
          ["move_down", "⬇ Crane Down"],
          ["low_angle", "📐 Low Angle"],
          ["top_down", "🦅 Top-Down View"],
        ].forEach(([val, lbl]) => {
          const opt = document.createElement("option");
          opt.value = val;
          opt.textContent = lbl;
          aSel.appendChild(opt);
        });
        const btnRunAngle = document.createElement("button");
        btnRunAngle.type = "button";
        btnRunAngle.className = "btn btn--primary";
        btnRunAngle.style.cssText = "padding:4px 10px;font-size:11px";
        btnRunAngle.textContent = "✨ Render Angle";
        btnRunAngle.addEventListener("click", async () => {
          const stopBusy = startBusyFeedback(btnRunAngle, card, `Generating ${aSel.options[aSel.selectedIndex].textContent} for ${shot.id}…`);
          try {
            const res = await callApi("/api/v2_keyframe_angle_shift", {
              project: v2KfState.project,
              id: shot.id,
              source_id: cloneSourceId,
              move: aSel.value,
              details: ta.value.trim(),
              engine: _currentV2VisualEngine(),
            });
            if (!shot.has_image) v2KfState.rendered_shots++;
            shot.has_image = true;
            shot.image_url = res.image_url + "?t=" + Date.now();
            renderV2KfScenesBar();
            renderV2KfGrid();
            setV2KfStatus(`✓ Rendered ${res.move_label} for ${shot.id} from ${res.source} (${res.model}).`);
          } catch (err) {
            setV2KfStatus("Camera angle shift failed: " + (err.message || err), true);
          } finally {
            stopBusy();
          }
        });
        aRow.appendChild(aSel);
        aRow.appendChild(btnRunAngle);
        anglePanel.appendChild(aHdr);
        anglePanel.appendChild(aRow);
      }

      if (shot.has_image) {
        // #2 Pin as Scene Anchor button
        const btnAnchor = document.createElement("button");
        btnAnchor.type = "button";
        btnAnchor.className = "btn " + (shot.is_anchor ? "btn--secondary" : "btn--ghost");
        btnAnchor.style.cssText = "padding:4px 8px;font-size:var(--text-xs);" + (shot.is_anchor ? "border-color:#38bdf8;color:#bae6fd" : "color:#94a3b8");
        btnAnchor.textContent = shot.is_anchor ? "📍 Anchor ✓" : "📍 Set Anchor";
        btnAnchor.title = shot.is_anchor
          ? `Pinned as ${sc.id}'s Scene Master Anchor (click to unpin)`
          : `Pin ${shot.id} as ${sc.id}'s Scene Master Anchor so all other shots in ${sc.id} match this room & lighting`;
        btnAnchor.addEventListener("click", async () => {
          const nextAnchor = shot.is_anchor ? "" : shot.id;
          try {
            await callApi("/api/v2_keyframe_anchor", {
              project: v2KfState.project,
              scene: sc.id,
              shot_id: nextAnchor,
            });
            sc.anchor_shot_id = nextAnchor;
            (sc.shots || []).forEach(s => { s.is_anchor = Boolean(nextAnchor && s.id === nextAnchor); });
            renderV2KfGrid();
            setV2KfStatus(nextAnchor ? `📍 Pinned ${nextAnchor} as Scene Anchor for ${sc.id} — subsequent shots will lock to it.` : `Cleared Scene Anchor for ${sc.id}.`);
          } catch (err) {
            setV2KfStatus("Could not update Scene Anchor: " + (err.message || err), true);
          }
        });
        row.appendChild(btnAnchor);

        // #4 Direct Mask Inpaint in Canvas Studio
        const btnCanvas = document.createElement("button");
        btnCanvas.type = "button";
        btnCanvas.className = "btn btn--ghost";
        btnCanvas.style.cssText = "padding:4px 8px;font-size:var(--text-xs);color:#38bdf8";
        btnCanvas.textContent = "🎨 Mask Inpaint";
        btnCanvas.title = `Open ${shot.id} in Canvas Studio to paint a mask over ONLY the changing region (100% pixel-identical background)`;
        btnCanvas.addEventListener("click", () => {
          const wbCompareBtn = document.querySelector('#workbenchDropdown .wb-tab-btn[data-target="panel-compare"]');
          if (wbCompareBtn) wbCompareBtn.click();
          else if (typeof window.activateWorkspaceTab === "function") window.activateWorkspaceTab("canvas-compare", true);
          setTimeout(() => {
            if (typeof window.openKeyframeInCanvasStudio === "function") {
              window.openKeyframeInCanvasStudio({
                project: v2KfState.project,
                shotId: shot.id,
                imageUrl: shot.image_url,
                prompt: [shot.action, shot.expression].filter(Boolean).join(". ") || ta.value.trim(),
                engine: _currentV2VisualEngine(),
              });
            }
          }, 80);
        });
        row.appendChild(btnCanvas);

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
      if (clonePanel) card.appendChild(clonePanel);
      if (anglePanel) card.appendChild(anglePanel);

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
              engine: _currentV2VisualEngine(),
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

      // Two-Pass "2D Meets Realism" Hybrid Controls (Pass 1 Live Plate w/ Gaps -> Pass 2 Bring 2D Cast In)
      if (!shot.locked) {
        const hybDet = document.createElement("details");
        hybDet.style.cssText = "margin-top:8px;padding:6px 8px;background:#0a0d14;border:1px solid rgba(245,158,11,0.32);border-radius:6px;";
        if ((v2KfState.hybrid_mode && v2KfState.hybrid_mode.enabled) || shot.has_pass1) {
          hybDet.open = true;
        }
        const hybSum = document.createElement("summary");
        hybSum.style.cssText = "cursor:pointer;font-size:11px;font-weight:700;color:#fde68a;";
        hybSum.textContent = shot.has_pass1
          ? "🎭 Two-Pass Hybrid (✓ Pass 1 Ready → Bring 2D Cast In)"
          : "🎭 Two-Pass 2D-Meets-Realism (Pass 1 Gaps → Pass 2 2D Cast)";
        hybDet.appendChild(hybSum);

        const gapIn = document.createElement("input");
        gapIn.type = "text";
        gapIn.placeholder = "Empty space / 2D placement (e.g. Bear in empty chair on right, Otter on table foreground)";
        gapIn.style.cssText = "width:100%;margin-top:6px;padding:5px 7px;background:#0f172a;color:#e2e8f0;border:1px solid #334155;border-radius:4px;font-size:11px;";
        hybDet.appendChild(gapIn);

        const sheetChecks = [];
        if (Array.isArray(v2KfState.cast_sheets) && v2KfState.cast_sheets.length) {
          const csWrap = document.createElement("div");
          csWrap.style.cssText = "display:flex;flex-wrap:wrap;gap:6px;margin-top:6px;";
          v2KfState.cast_sheets.forEach(cs => {
            const lb = document.createElement("label");
            lb.style.cssText = "display:inline-flex;align-items:center;gap:4px;font-size:10px;color:#bae6fd;background:#0f172a;border:1px solid #334155;border-radius:4px;padding:2px 6px;cursor:pointer;";
            const ck = document.createElement("input");
            ck.type = "checkbox";
            ck.value = cs.rel_book;
            if ((shot.characters || []).some(cn => cn.toLowerCase() === cs.name.toLowerCase())) ck.checked = true;
            lb.appendChild(ck);
            lb.appendChild(document.createTextNode(`${cs.name} (${cs.kind})`));
            csWrap.appendChild(lb);
            sheetChecks.push(ck);
          });
          hybDet.appendChild(csWrap);
        }

        const hybBtns = document.createElement("div");
        hybBtns.style.cssText = "display:flex;gap:6px;flex-wrap:wrap;margin-top:6px;";
        const btnP1 = document.createElement("button");
        btnP1.type = "button";
        btnP1.className = "btn btn--secondary";
        btnP1.style.cssText = "flex:1;padding:4px 8px;font-size:11px;";
        btnP1.textContent = shot.has_pass1 ? "↺ Redo Pass 1 (Gaps)" : "1️⃣ Pass 1: Live Plate w/ Gaps";
        btnP1.addEventListener("click", async () => {
          const stopBusy = startBusyFeedback(btnP1, card, `Pass 1 live plate for ${shot.id}…`);
          setV2KfStatus(`Rendering Pass 1 Live-Action Plate (with reserved 2D gaps) for ${shot.id}…`);
          try {
            const res = await callApi("/api/v2_keyframe_hybrid_pass", {
              project: v2KfState.project,
              id: shot.id,
              pass_num: 1,
              prompt: ta.value.trim(),
              gap_notes: gapIn.value.trim(),
              engine: _currentV2VisualEngine(),
            });
            shot.has_pass1 = true;
            shot.pass1_url = res.pass1_url + "?t=" + Date.now();
            renderV2KfGrid();
            setV2KfStatus(`✓ Pass 1 Live Plate saved for ${shot.id}. Now click "2️⃣ Pass 2: Bring 2D Cast In"!`);
          } catch (err) {
            setV2KfStatus(`Pass 1 failed for ${shot.id}: ` + (err.message || err), true);
          } finally {
            stopBusy();
          }
        });

        const btnP2 = document.createElement("button");
        btnP2.type = "button";
        btnP2.className = "btn btn--primary";
        btnP2.style.cssText = "flex:1;padding:4px 8px;font-size:11px;";
        btnP2.textContent = "2️⃣ Pass 2: Bring 2D Cast In";
        btnP2.disabled = !shot.has_pass1;
        btnP2.title = shot.has_pass1 ? "Composite checked 2D character sheets into Pass 1's empty gaps" : "Run Pass 1 first to lock the live-action plate";
        btnP2.addEventListener("click", async () => {
          const pickedSheets = sheetChecks.filter(c => c.checked).map(c => c.value);
          const stopBusy = startBusyFeedback(btnP2, card, `Pass 2 bringing 2D cast into ${shot.id}…`);
          setV2KfStatus(`Pass 2: Locking Pass 1 & compositing ${pickedSheets.length} 2D character sheet(s) into ${shot.id}…`);
          try {
            const res = await callApi("/api/v2_keyframe_hybrid_pass", {
              project: v2KfState.project,
              id: shot.id,
              pass_num: 2,
              prompt: ta.value.trim(),
              placement_notes: gapIn.value.trim(),
              cartoon_refs: pickedSheets,
              engine: _currentV2VisualEngine(),
            });
            if (!shot.has_image) v2KfState.rendered_shots++;
            shot.has_image = true;
            shot.image_url = res.image_url + "?t=" + Date.now();
            renderV2KfScenesBar();
            renderV2KfGrid();
            setV2KfStatus(`✓ Pass 2 Hybrid composite rendered for ${shot.id} (${res.model || "local"}) — use 👁️ toggle for Before/After reveal!`);
          } catch (err) {
            setV2KfStatus(`Pass 2 failed for ${shot.id}: ` + (err.message || err), true);
          } finally {
            stopBusy();
          }
        });

        hybBtns.appendChild(btnP1);
        hybBtns.appendChild(btnP2);
        hybDet.appendChild(hybBtns);
        card.appendChild(hybDet);
      }

      grid.appendChild(card);
    });

    window.scrollTo({ top: savedY, behavior: "instant" });
    requestAnimationFrame(() => {
      window.scrollTo({ top: savedY, behavior: "instant" });
      grid.style.minHeight = "";
    });
  }

  const v2KfDismissedSetPopupFor = new Set();

  function updateV2KfMissingSetsWarning(slug, setPlatesCount, missingList) {
    const banner = $("v2KfMissingSetsBanner");
    const modal = $("v2KfMissingSetsModal");
    const listEl = $("v2KfMissingSetsList");
    const missing = Array.isArray(missingList) ? missingList : [];
    const totalPlates = Number(setPlatesCount || 0);

    if (banner) {
      if (totalPlates === 0 || missing.length > 0) {
        banner.style.display = "flex";
        banner.textContent = "";
        const txt = document.createElement("span");
        txt.textContent = totalPlates === 0
          ? `⚠️ No Step 11 set plates rendered yet (${missing.length} location(s) need plates) — backgrounds may drift between shots until Step 11 set plates are generated.`
          : `⚠️ ${missing.length} location(s) still lack Step 11 set plates: ${missing.slice(0, 4).join(", ")}${missing.length > 4 ? "…" : ""}`;
        const goBtn = document.createElement("button");
        goBtn.type = "button";
        goBtn.className = "btn btn--primary";
        goBtn.style.cssText = "padding:4px 10px;font-size:11px;white-space:nowrap";
        goBtn.textContent = "🏛 Go to Step 11";
        goBtn.addEventListener("click", () => activateStep(11));
        banner.appendChild(txt);
        banner.appendChild(goBtn);
      } else {
        banner.style.display = "none";
      }
    }

    // Pop up the modal dialog whenever entering Step 17 with ZERO Step 11 set plates
    if (modal && currentStep === 17 && totalPlates === 0 && !v2KfDismissedSetPopupFor.has(slug)) {
      if (listEl) {
        listEl.textContent = "";
        missing.slice(0, 10).forEach(locName => {
          const sp = document.createElement("span");
          sp.textContent = `🏛 ${locName}`;
          listEl.appendChild(sp);
        });
      }
      modal.style.display = "flex";
    }
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
      v2KfState.hybrid_mode = data.hybrid_mode || {};
      v2KfState.cast_sheets = data.cast_sheets || [];
      v2KfState.set_plates_count = Number(data.set_plates_count || 0);
      v2KfState.missing_set_plates = data.missing_set_plates || [];
      v2KfState.total_shots = data.total_shots || 0;
      v2KfState.rendered_shots = data.rendered_shots || 0;
      if (!v2KfState.activeSceneId || !v2KfState.scenes.some(s => s.id === v2KfState.activeSceneId)) {
        v2KfState.activeSceneId = (v2KfState.scenes[0] && v2KfState.scenes[0].id) || "";
      }
      renderV2KfScenesBar();
      renderV2KfGrid();
      updateV2KfMissingSetsWarning(slug, v2KfState.set_plates_count, v2KfState.missing_set_plates);
    } catch (e) {
      setV2KfStatus("Could not load keyframes: " + (e.message || e), true);
    }
  }

  let v2LocalModelsPollTimer = null;

  async function loadV2LocalConsistencyPanel() {
    const box = $("v2KfLocalModelsBox");
    if (!box || box.style.display === "none") return;
    try {
      const st = await callApi("/api/v2_local_consistency_status");
      box.textContent = "";
      const hdr = document.createElement("div");
      hdr.style.cssText = "display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap";
      const hTitle = document.createElement("strong");
      hTitle.style.cssText = "font-size:12.5px;color:#34d399";
      hTitle.textContent = "🆓 100% Free Local Consistency Engines (Your RTX GPU — Zero API Fees)";
      const btnRef = document.createElement("button");
      btnRef.type = "button";
      btnRef.className = "btn btn--ghost";
      btnRef.style.cssText = "padding:3px 8px;font-size:11px";
      btnRef.textContent = "↻ Refresh Status";
      btnRef.addEventListener("click", () => loadV2LocalConsistencyPanel());
      hdr.appendChild(hTitle);
      hdr.appendChild(btnRef);
      box.appendChild(hdr);

      const grid = document.createElement("div");
      grid.className = "v2-kf-local-grid";

      const downloads = st.downloads || {};
      let anyDownloading = false;
      (st.sd_cli_models || []).forEach(m => {
        const c = document.createElement("div");
        c.className = "v2-kf-local-card" + (m.ready ? " is-ready" : "");
        const top = document.createElement("div");
        top.style.cssText = "display:flex;justify-content:space-between;align-items:center;gap:6px";
        const nm = document.createElement("strong");
        nm.style.color = "#f8fafc";
        nm.textContent = m.label;
        const bdg = document.createElement("span");
        bdg.style.cssText = "font-size:10px;font-weight:700;padding:2px 6px;border-radius:999px;" +
          (m.ready ? "background:rgba(16,185,129,0.2);color:#6ee7b7" : "background:rgba(245,158,11,0.18);color:#fde68a");
        bdg.textContent = m.ready ? "✓ Ready" : `${m.missing_gb} GB`;
        top.appendChild(nm);
        top.appendChild(bdg);
        const sm = document.createElement("div");
        sm.style.cssText = "font-size:10.5px;color:#94a3b8;line-height:1.35";
        sm.textContent = m.summary;
        c.appendChild(top);
        c.appendChild(sm);

        const job = downloads[m.id];
        if (!m.ready) {
          if (job && job.state === "downloading") {
            anyDownloading = true;
            const prog = document.createElement("div");
            prog.style.cssText = "font-size:10.5px;color:#38bdf8;margin-top:4px";
            prog.textContent = `⬇ Downloading ${job.current_file} (${job.pct || 0}%)…`;
            c.appendChild(prog);
          } else {
            const dlBtn = document.createElement("button");
            dlBtn.type = "button";
            dlBtn.className = "btn btn--secondary";
            dlBtn.style.cssText = "margin-top:4px;padding:4px 8px;font-size:11px";
            dlBtn.textContent = `⬇ Free Download (${m.missing_gb} GB)`;
            dlBtn.addEventListener("click", async () => {
              dlBtn.disabled = true;
              dlBtn.textContent = "Starting free download…";
              try {
                await callApi("/api/v2_local_consistency_download", { model_id: m.id });
                loadV2LocalConsistencyPanel();
              } catch (err) {
                setV2KfStatus("Download failed: " + (err.message || err), true);
                dlBtn.disabled = false;
              }
            });
            c.appendChild(dlBtn);
            if (job && job.state === "error" && job.error) {
              const er = document.createElement("div");
              er.style.cssText = "font-size:10px;color:#f87171";
              er.textContent = job.error;
              c.appendChild(er);
            }
          }
        }
        grid.appendChild(c);
      });

      // Ollama Free Vision QA card
      const ol = st.ollama || {};
      const olReady = Boolean(ol.running && ol.best_model);
      const olCard = document.createElement("div");
      olCard.className = "v2-kf-local-card" + (olReady ? " is-ready" : "");
      olCard.innerHTML = `
        <div style="display:flex;justify-content:space-between;align-items:center;gap:6px">
          <strong style="color:#f8fafc">👁️ Ollama Vision QA (Free)</strong>
          <span style="font-size:10px;font-weight:700;padding:2px 6px;border-radius:999px;${olReady ? "background:rgba(16,185,129,0.2);color:#6ee7b7" : "background:rgba(148,163,184,0.2);color:#cbd5e1"}">${olReady ? "✓ " + ol.best_model : (ol.running ? "No VL model" : "Offline")}</span>
        </div>
        <div style="font-size:10.5px;color:#94a3b8;line-height:1.35">
          ${olReady ? "Automatically checks physics &amp; room continuity locally at $0 cost." : "Install Ollama &amp; run <code>ollama pull qwen2.5vl:7b</code> (or <code>gemma3:12b</code>) for free local Vision QA."}
        </div>`;
      grid.appendChild(olCard);

      // ComfyUI Qwen-Image-Edit Angles card
      const cf = st.comfyui || {};
      const cfCard = document.createElement("div");
      cfCard.className = "v2-kf-local-card" + (cf.angles_ready ? " is-ready" : "");
      cfCard.innerHTML = `
        <div style="display:flex;justify-content:space-between;align-items:center;gap:6px">
          <strong style="color:#f8fafc">🎥 ComfyUI Angles (Qwen-Edit)</strong>
          <span style="font-size:10px;font-weight:700;padding:2px 6px;border-radius:999px;${cf.angles_ready ? "background:rgba(16,185,129,0.2);color:#6ee7b7" : "background:rgba(168,85,247,0.2);color:#e9d5ff"}">${cf.angles_ready ? "✓ Ready" : (cf.angles_missing_gb ? cf.angles_missing_gb + " GB pack" : "Not installed")}</span>
        </div>
        <div style="font-size:10.5px;color:#94a3b8;line-height:1.35">
          ${cf.angles_ready ? "Active! New camera angles rotate your Set Plate / Anchor automatically." : "Install the free <code>image-qwen-edit</code> pack in Models &amp; Hardware for native 3D camera rotation (Kontext/FLUX.2 fallback active meanwhile)."}
        </div>`;
      grid.appendChild(cfCard);

      box.appendChild(grid);

      if (v2LocalModelsPollTimer) { clearTimeout(v2LocalModelsPollTimer); v2LocalModelsPollTimer = null; }
      if (anyDownloading) {
        v2LocalModelsPollTimer = setTimeout(() => loadV2LocalConsistencyPanel(), 2500);
      }
    } catch (err) {
      box.textContent = "Could not probe local consistency models: " + (err.message || err);
    }
  }

  function initV2Keyframes() {
    const btnLocalToggle = $("bV2KfLocalModelsToggle");
    const localBox = $("v2KfLocalModelsBox");
    if (btnLocalToggle && localBox) {
      btnLocalToggle.addEventListener("click", () => {
        const open = localBox.style.display === "none" || !localBox.style.display;
        localBox.style.display = open ? "flex" : "none";
        if (open) loadV2LocalConsistencyPanel();
      });
    }
    const btnContAudit = $("bV2KfContAudit");
    if (btnContAudit) {
      btnContAudit.addEventListener("click", async () => {
        const slug = v2KfState.project || ($("proj")?.value || "").trim();
        if (!slug) { setV2KfStatus("Select a book in Step 01 first.", true); return; }
        const curSc = v2KfState.activeScene || "";
        const stopBusy = startBusyFeedback(btnContAudit, $("v2KfGrid"), `Auditing shot continuity & scale (${curSc || "ALL"})…`);
        setV2KfStatus(`Auditing shot-to-shot prop persistence, grounded surfaces & character/prop scale (${curSc || "all scenes"})…`);
        try {
          const res = await callApi("/api/v2_shot_continuity_audit", { project: slug, scene: curSc, record_bidirectional: true });
          await loadV2Keyframes();
          if (typeof loadV2WorkflowSync === "function") await loadV2WorkflowSync(slug);
          setV2KfStatus(
            res.fixes_applied
              ? `✓ Continuity Audit (${res.engine}): ${res.fixes_applied} fix(es) applied & synced → ${(res.updated_steps || []).join(" · ")}`
              : `✓ Continuity Audit (${res.engine}): All ${res.scenes_audited} scene(s) passed with no prop or scale conflicts.`
          );
        } catch (err) {
          setV2KfStatus("Continuity audit failed: " + (err.message || err), true);
        } finally {
          stopBusy();
        }
      });
    }
    const btnPlateAudit = $("bV2KfPlateAudit");
    const plateAuditBox = $("v2KfPlateAuditBox");
    if (btnPlateAudit && plateAuditBox) {
      btnPlateAudit.addEventListener("click", async () => {
        const slug = v2KfState.project || ($("proj")?.value || "").trim();
        if (!slug) { setV2KfStatus("Select a book in Step 01 first.", true); return; }
        plateAuditBox.style.display = "block";
        plateAuditBox.innerHTML = `<div style="font-size:12px;color:#94a3b8">🧩 Building per-plate consistency contact sheets (Step 10 characters &amp; Step 11 sets vs Step 17 keyframes)…</div>`;
        try {
          const res = await callApi("/api/v2_plate_audit", { project: slug });
          const sheets = res.sheets || [];
          const warns = res.warnings || [];
          const ts = Date.now();
          let html = `<div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;margin-bottom:8px">
            <strong style="color:${res.passed ? "#34d399" : "#fbbf24"};font-size:13px">${res.passed ? "✓ Plate Consistency Audit Passed" : "⚠️ Plate Consistency Audit"} (${res.plate_count || 0} plates · ${res.total_rendered_stills || 0} keyframes)</strong>
            <button type="button" class="btn btn--ghost" id="bV2KfPlateAuditClose" style="padding:2px 8px;font-size:11px">✕ Close</button>
          </div>`;
          if (warns.length) {
            html += `<div style="font-size:11px;color:#fbbf24;margin-bottom:8px">${warns.map(w => `• ${esc(w)}`).join("<br>")}</div>`;
          }
          if (!sheets.length) {
            html += `<div style="font-size:12px;color:#94a3b8">No plate sheets built yet — render Step 10 character turnarounds / Step 11 set plates and Step 17 keyframes first.</div>`;
          } else {
            html += `<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:10px">` +
              sheets.map(s => `<div style="background:#0a0d14;border:1px solid #334155;border-radius:8px;padding:8px">
                <div style="font-size:12px;font-weight:700;color:#e2e8f0;margin-bottom:4px">${s.kind === "character" ? "👤" : "🏛️"} ${esc(s.label)} <span style="color:#94a3b8;font-weight:400">(${s.still_count} shot${s.still_count === 1 ? "" : "s"})</span></div>
                <a href="${esc(s.sheet_url)}?t=${ts}" target="_blank" rel="noopener"><img src="${esc(s.sheet_url)}?t=${ts}" alt="${esc(s.label)} plate sheet" style="width:100%;border-radius:6px;display:block"></a>
              </div>`).join("") + `</div>`;
          }
          plateAuditBox.innerHTML = html;
          const btnClose = $("bV2KfPlateAuditClose");
          if (btnClose) btnClose.addEventListener("click", () => { plateAuditBox.style.display = "none"; });
        } catch (err) {
          plateAuditBox.innerHTML = `<div style="font-size:12px;color:#f87171">Plate audit failed: ${esc(err.message || err)}</div>`;
        }
      });
    }
    const btnGoStep11 = $("bV2KfGoStep11");
    const btnDismissWarn = $("bV2KfDismissSetsWarn");
    const warnModal = $("v2KfMissingSetsModal");
    if (btnGoStep11) {
      btnGoStep11.addEventListener("click", () => {
        if (warnModal) warnModal.style.display = "none";
        activateStep(11);
      });
    }
    if (btnDismissWarn) {
      btnDismissWarn.addEventListener("click", () => {
        if (v2KfState.project) v2KfDismissedSetPopupFor.add(v2KfState.project);
        if (warnModal) warnModal.style.display = "none";
      });
    }
    window.__v2ActivateStep = activateStep;
    const btnReload = $("bV2KfReload");
    const btnRenderScene = $("bV2KfRenderScene");
    const btnSavePrompts = $("bV2KfSavePrompts");
    const btnRebuildPrompts = $("bV2KfRebuildPrompts");
    const btnRebuildAllPrompts = $("bV2KfRebuildAllPrompts");
    if (btnReload) btnReload.addEventListener("click", () => loadV2Keyframes());
    if (btnRebuildPrompts) {
      btnRebuildPrompts.addEventListener("click", async () => {
        const sc = (v2KfState.scenes || []).find(s => s.id === v2KfState.activeSceneId);
        if (!sc || !v2KfState.project) return;
        setV2KfStatus(`Syncing ${sc.id} prompts from latest Steps 08–12 (cast, turnarounds, sets, shotlist)…`);
        try {
          const res = await callApi("/api/v2_keyframe_sync_prompts", {
            project: v2KfState.project,
            scene: sc.id,
          });
          await loadV2Keyframes();
          const skipNote = res.skipped_locked ? ` (${res.skipped_locked} locked kept)` : "";
          setV2KfStatus(`✓ Synced ${res.updated || 0} prompt(s) in ${sc.id} with latest Steps 08–12 cast, turnarounds & sets${skipNote}.`);
        } catch (err) {
          setV2KfStatus("Sync failed: " + (err.message || err), true);
        }
      });
    }
    if (btnRebuildAllPrompts) {
      btnRebuildAllPrompts.addEventListener("click", async () => {
        if (!v2KfState.project) return;
        setV2KfStatus("Syncing ALL unlocked scenes' prompts from latest Steps 08–12…");
        try {
          const res = await callApi("/api/v2_keyframe_sync_prompts", {
            project: v2KfState.project,
          });
          await loadV2Keyframes();
          const skipNote = res.skipped_locked ? ` (${res.skipped_locked} locked kept)` : "";
          setV2KfStatus(`✓ Synced ${res.updated || 0} prompt(s) across all scenes with latest Steps 08–12 cast, turnarounds & sets${skipNote}.`);
        } catch (err) {
          setV2KfStatus("Sync all failed: " + (err.message || err), true);
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
                engine: _currentV2VisualEngine(),
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
      hdr.style.cssText = "display:flex;flex-direction:column;gap:6px;margin-bottom:10px";
      const titleRow = document.createElement("div");
      titleRow.style.cssText = "display:flex;align-items:center;flex-wrap:wrap;gap:8px";
      const title = document.createElement("strong");
      title.style.color = "#f59e0b";
      title.textContent = c.name.toUpperCase() + (outfits.length > 1 ? ` · ${outfits.length} Wardrobe Changes` : "");
      titleRow.appendChild(title);

      const ident = c.identity || {};
      const badge = document.createElement("span");
      if (ident.linked_variants && ident.linked_variants.length) {
        if (ident.has_canonical_ref && ident.ref_source_name) {
          badge.style.cssText = "padding:2px 8px;border-radius:999px;background:rgba(16,185,129,0.14);border:1px solid rgba(16,185,129,0.45);color:#a7f3d0;font-size:11px;font-weight:600";
          badge.textContent = `🔗 Same character (${ident.canonical_label}) · Ref: ${ident.ref_source_name}`;
          badge.title = `Costume & scene changes for ${c.name} automatically use ${ident.ref_source_name}'s generated picture as visual reference.`;
        } else {
          badge.style.cssText = "padding:2px 8px;border-radius:999px;background:rgba(56,189,248,0.14);border:1px solid rgba(56,189,248,0.45);color:#bae6fd;font-size:11px;font-weight:600";
          badge.textContent = `🔗 Shared identity: ${ident.canonical_label} (${ident.linked_variants.join(", ")})`;
          badge.title = `First Front View generated for ${ident.canonical_label} will automatically be used as the visual reference for all linked costumes/variants.`;
        }
      } else if (ident.is_twin) {
        badge.style.cssText = "padding:2px 8px;border-radius:999px;background:rgba(168,85,247,0.16);border:1px solid rgba(168,85,247,0.45);color:#e9d5ff;font-size:11px;font-weight:600";
        badge.textContent = `👯 Explicit Twin (${(ident.twin_with || []).join(", ")})`;
      } else {
        badge.style.cssText = "padding:2px 8px;border-radius:999px;background:rgba(148,163,184,0.12);border:1px solid rgba(148,163,184,0.32);color:#cbd5e1;font-size:11px";
        badge.textContent = "🎭 Distinct Character (non-twin)";
        badge.title = "Enforced as visually distinct from other cast members unless explicitly described as twins.";
      }
      titleRow.appendChild(badge);

      if (c.style_override) {
        const ovPill = document.createElement("span");
        ovPill.style.cssText = "padding:2px 8px;border-radius:999px;background:rgba(14,165,233,0.16);border:1px solid rgba(56,189,248,0.45);color:#bae6fd;font-size:11px;font-weight:600";
        const stObj = V2_STYLE_RECIPES[c.style_override];
        ovPill.textContent = `🎨 Style Override: ${stObj ? stObj.label : c.style_override}`;
        titleRow.appendChild(ovPill);
      }

      const idSel = document.createElement("select");
      idSel.style.cssText = "margin-left:auto;background:#0f172a;color:#cbd5e1;border:1px solid #334155;border-radius:6px;padding:2px 6px;font-size:11px;max-width:240px";
      idSel.title = "Character identity control: link costume/scene variants so they share the same face & reference image, or keep independent.";
      const optAuto = document.createElement("option");
      optAuto.value = "";
      optAuto.textContent = `Identity: Auto (${ident.canonical_label || c.name.toUpperCase()})`;
      idSel.appendChild(optAuto);
      const optSelf = document.createElement("option");
      optSelf.value = "__self__";
      optSelf.textContent = "Keep Independent (distinct character)";
      idSel.appendChild(optSelf);
      chars.forEach(other => {
        if (!other.name || other.name.toLowerCase() === c.name.toLowerCase()) return;
        const opt = document.createElement("option");
        opt.value = other.name;
        opt.textContent = `Same character as ${other.name}`;
        idSel.appendChild(opt);
      });
      idSel.value = ident.override || "";
      idSel.addEventListener("change", async () => {
        try {
          await callApi("/api/v2_character_identity_link", {
            project: v2TurnState.project,
            character: c.name,
            target_base: idSel.value,
          });
          await loadV2Turnarounds();
          setV2TurnStatus(`✓ Updated character identity control for ${c.name}.`);
        } catch (err) {
          setV2TurnStatus("Could not update character identity: " + (err.message || err), true);
        }
      });
      titleRow.appendChild(idSel);
      hdr.appendChild(titleRow);

      if (c.desc) {
        const desc = document.createElement("div");
        desc.style.cssText = "color:#cbd5e1;font-size:var(--text-xs);line-height:1.45;white-space:normal;word-break:break-word";
        desc.textContent = c.desc;
        hdr.appendChild(desc);
      }
      card.appendChild(hdr);

      outfits.forEach((of, ofIdx) => {
        const sec = document.createElement("div");
        if (ofIdx > 0) sec.style.cssText = "margin-top:12px;padding-top:12px;border-top:1px solid #232d3f;";

        const ofHdr = document.createElement("div");
        ofHdr.style.cssText = "display:flex;align-items:flex-start;flex-wrap:wrap;gap:6px;margin-bottom:8px;font-size:12px;";
        const pill = document.createElement("span");
        pill.style.cssText = "padding:2px 8px;border-radius:999px;background:rgba(245,158,11,0.14);border:1px solid rgba(245,158,11,0.45);color:#fde68a;font-weight:600;font-size:11px;";
        pill.textContent = `👗 ${of.scenes || "All Scenes"}` + (of.location ? ` · ${of.location}` : "");
        ofHdr.appendChild(pill);
        if (of.wardrobe && of.wardrobe !== c.desc) {
          const wTxt = document.createElement("span");
          wTxt.style.cssText = "color:#e2e8f0;font-size:11px;line-height:1.45;flex:1;min-width:200px;white-space:normal;word-break:break-word;";
          wTxt.textContent = of.wardrobe;
          ofHdr.appendChild(wTxt);
        } else if (!of.wardrobe && !c.desc) {
          const wTxt = document.createElement("span");
          wTxt.style.cssText = "color:#94a3b8;font-size:11px;flex:1;";
          wTxt.textContent = "No specific wardrobe set in Step 08 yet";
          ofHdr.appendChild(wTxt);
        }

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

        const hasOutfitFront = Boolean(of.views && of.views.front && of.views.front.has_image);
        const hasBaseFront = Boolean(outfits[0] && outfits[0].views && outfits[0].views.front && outfits[0].views.front.has_image);
        const hasFrontRef = hasOutfitFront || hasBaseFront;

        VIEWS.forEach(([vk, vlabel]) => {
          const vinfo = (of.views && of.views[vk]) || {};
          const needsFront = vk !== "front" && !hasFrontRef;
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
            imgBox.textContent = needsFront
              ? `${vlabel} · Generate Front View first (used as reference)`
              : `${c.name} · ${of.scenes} · ${vlabel}`;
          }
          box.appendChild(imgBox);

          const row = document.createElement("div");
          row.style.cssText = "display:flex;gap:6px";
          const btnGen = document.createElement("button");
          btnGen.type = "button";
          btnGen.className = "btn " + (vinfo.has_image ? "btn--secondary" : "btn--primary");
          btnGen.style.cssText = "flex:1;padding:4px 8px;font-size:11px";
          btnGen.textContent = vinfo.has_image
            ? `↺ Re-roll`
            : (needsFront ? `🔒 Front View First` : `✨ Generate ${vlabel}`);
          if (needsFront) {
            btnGen.disabled = true;
            btnGen.title = `Generate or upload the Front View of ${c.name} first — ${vlabel} uses the Front View as its visual reference.`;
          } else if (vk !== "front") {
            btnGen.title = `Uses ${c.name}'s Front View as the visual reference to preserve face, clothing, and proportions.`;
          }
          btnGen.addEventListener("click", async () => {
            const stopBusy = startBusyFeedback(btnGen, box, `Generating ${c.name} (${of.scenes} · ${vlabel})…`);
            const refHint = vk !== "front"
              ? " using Front View reference"
              : (ident.has_canonical_ref && ident.ref_source_name ? ` using ${ident.ref_source_name} reference` : "");
            setV2TurnStatus(`Generating ${vlabel} for ${c.name} (${of.scenes})${refHint}…`);
            try {
              const res = await callApi("/api/v2_turnaround_render", {
                project: v2TurnState.project,
                character: c.name,
                outfit_id: of.id || "default",
                view: vk,
                desc: c.desc,
                wardrobe: of.wardrobe || "",
                look: v2TurnState.look,
                engine: _currentV2VisualEngine(),
              });
              of.views[vk] = { has_image: true, image_url: res.image_url + "?t=" + Date.now() };
              if (vk === "front") {
                await loadV2Turnarounds();
              } else {
                renderV2Turnarounds();
              }
              const cc = res.character_control || {};
              let refTag = res.model ? ` (${res.model})` : "";
              if (cc.reference_reason === "same_character_costume_change" && cc.reference_source) {
                refTag = ` using ${cc.reference_source} as character reference (${res.model || "local"})`;
              } else if (cc.reference_reason === "front_view_angle_rotation") {
                refTag = ` using Front View reference (${res.model || "local"})`;
              } else if (cc.reference_reason === "explicit_twin" && cc.reference_source) {
                refTag = ` using explicit twin reference ${cc.reference_source} (${res.model || "local"})`;
              } else if (cc.distinctness && cc.distinctness.diversified_retry) {
                refTag = ` (distinct non-twin, auto-diversified via ${res.model || "local"})`;
              }
              setV2TurnStatus(`✓ Generated ${vlabel} for ${c.name} (${of.scenes})${refTag}!`);
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

          // One-Click Restyle Front View into any of the 30+ visual styles (FLUX.2-klein-4B -r ref)
          if (vk === "front" && vinfo.has_image) {
            const restyleRow = document.createElement("div");
            restyleRow.style.cssText = "display:flex;gap:4px;align-items:center;margin-top:2px;";
            const restyleSel = document.createElement("select");
            restyleSel.style.cssText = "flex:1;min-width:0;padding:3px 6px;background:#0f172a;color:#bae6fd;border:1px solid #334155;border-radius:4px;font-size:11px;";
            populateStyleSelect(restyleSel, c.style_override || v2TurnState.look || "claymation", null);
            const btnRestyle = document.createElement("button");
            btnRestyle.type = "button";
            btnRestyle.className = "btn btn--secondary";
            btnRestyle.style.cssText = "padding:3px 8px;font-size:11px;flex-shrink:0;";
            btnRestyle.textContent = "🎨 Restyle";
            btnRestyle.title = "Transform this Front View into the selected visual style while preserving character identity & pose.";
            btnRestyle.addEventListener("click", async () => {
              const targetStyle = restyleSel.value;
              if (!targetStyle) return;
              const styleLbl = (V2_STYLE_RECIPES[targetStyle] || {}).label || targetStyle;
              const stopBusy = startBusyFeedback(btnRestyle, box, `Restyling ${c.name} into ${styleLbl}…`);
              setV2TurnStatus(`Restyling ${c.name} (${of.scenes}) into ${styleLbl} using Front View reference…`);
              try {
                const res = await callApi("/api/v2_turnaround_restyle", {
                  project: v2TurnState.project,
                  character: c.name,
                  outfit_id: of.id || "default",
                  style_id: targetStyle,
                  desc: c.desc,
                  wardrobe: of.wardrobe || "",
                });
                of.views[vk] = { has_image: true, image_url: res.image_url + "?t=" + Date.now() };
                await loadV2Turnarounds();
                setV2TurnStatus(`✓ Restyled ${c.name} into ${res.style_name || styleLbl} (${res.model || "local"})!`);
              } catch (err) {
                setV2TurnStatus("Restyle failed: " + (err.message || err), true);
              } finally {
                stopBusy();
              }
            });
            restyleRow.appendChild(restyleSel);
            restyleRow.appendChild(btnRestyle);
            box.appendChild(restyleRow);
          }

          grid.appendChild(box);
        });

        sec.appendChild(grid);

        // 3-Panel Pro Character Sheet (Front Close-Up Portrait | Full Body Front | Full Body Back) from 2D_Realism_Tutorial.pdf
        const sheetBar = document.createElement("div");
        sheetBar.style.cssText = "margin-top:10px;padding:8px;background:#0a0d14;border:1px solid rgba(56,189,248,0.35);border-radius:8px;display:flex;flex-wrap:wrap;align-items:center;gap:10px;";
        const shInfo = of.sheet || {};
        if (shInfo.has_image && shInfo.image_url) {
          const shImg = document.createElement("img");
          shImg.src = shInfo.image_url + "?t=" + Date.now();
          shImg.alt = `${c.name} 3-Panel Pro Sheet`;
          shImg.style.cssText = "width:140px;aspect-ratio:4/3;object-fit:cover;border-radius:6px;border:1px solid #38bdf8;cursor:zoom-in;";
          shImg.addEventListener("click", () => window.open(shInfo.image_url, "_blank"));
          sheetBar.appendChild(shImg);
        }
        const shMeta = document.createElement("div");
        shMeta.style.cssText = "flex:1;min-width:200px;display:flex;flex-direction:column;gap:4px;";
        const shTitle = document.createElement("strong");
        shTitle.style.cssText = "font-size:11px;color:#bae6fd;";
        shTitle.textContent = "📋 3-Panel Pro Sheet (Close-Up Portrait | Full Body Front | Full Body Back — 4:3)";
        shMeta.appendChild(shTitle);
        const shCtrls = document.createElement("div");
        shCtrls.style.cssText = "display:flex;gap:6px;flex-wrap:wrap;align-items:center;";
        const shModeSel = document.createElement("select");
        shModeSel.style.cssText = "padding:3px 7px;background:#0f172a;color:#f8fafc;border:1px solid #334155;border-radius:4px;font-size:11px;";
        [
          ["auto", "Style: Auto (Character / Book Style)"],
          ["realistic", "Style: Realistic Photo Sheet (Human Actor)"],
          ["2d", "Style: Shared 2D Cartoon Sheet (1940s Cel)"],
        ].forEach(([mv, ml]) => {
          const o = document.createElement("option");
          o.value = mv;
          o.textContent = ml;
          shModeSel.appendChild(o);
        });
        const btnSheet = document.createElement("button");
        btnSheet.type = "button";
        btnSheet.className = "btn btn--primary";
        btnSheet.style.cssText = "padding:4px 10px;font-size:11px;";
        btnSheet.textContent = shInfo.has_image ? "↺ Regenerate 3-Panel Sheet" : "📋 Generate 3-Panel Pro Sheet";
        btnSheet.addEventListener("click", async () => {
          const stopBusy = startBusyFeedback(btnSheet, sheetBar, `Generating 3-Panel Pro Sheet for ${c.name}…`);
          setV2TurnStatus(`Generating 4:3 3-Panel Pro Sheet (Portrait | Front | Back) for ${c.name}…`);
          try {
            const res = await callApi("/api/v2_turnaround_sheet", {
              project: v2TurnState.project,
              character: c.name,
              outfit_id: of.id || "default",
              sheet_mode: shModeSel.value,
              desc: c.desc,
              wardrobe: of.wardrobe || "",
              look: v2TurnState.look,
              engine: _currentV2VisualEngine(),
            });
            of.sheet = { has_image: true, image_url: res.sheet_url + "?t=" + Date.now() };
            if (window.loadPCastRefs) window.loadPCastRefs();
            renderV2Turnarounds();
            setV2TurnStatus(`✓ Generated 3-Panel Pro Sheet for ${c.name} (${res.style_id}, ${res.model || "local"})!`);
          } catch (err) {
            setV2TurnStatus("3-Panel Sheet failed: " + (err.message || err), true);
          } finally {
            stopBusy();
          }
        });
        shCtrls.appendChild(shModeSel);
        shCtrls.appendChild(btnSheet);
        if (shInfo.has_image && shInfo.image_url) {
          const dlLink = document.createElement("a");
          dlLink.href = shInfo.image_url;
          dlLink.download = `${c.slug || "character"}_sheet.png`;
          dlLink.className = "btn btn--ghost";
          dlLink.style.cssText = "padding:4px 8px;font-size:11px;text-decoration:none;color:#fde68a;";
          dlLink.textContent = "⬇ Export Sheet";
          shCtrls.appendChild(dlLink);
        }
        shMeta.appendChild(shCtrls);
        sheetBar.appendChild(shMeta);
        sec.appendChild(sheetBar);

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
      await loadV2CharacterTypes();
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

    // Wire Step 18 Two-Pass Hybrid Video Prompt Exporter
    const btnHybVid = $("bV2HybridPromptsGen");
    if (btnHybVid) {
      btnHybVid.addEventListener("click", async () => {
        const slug = ($("proj")?.value || activeProject || "").trim();
        const stEl = $("v2HybridVidStatus");
        if (!slug) { if (stEl) stEl.textContent = "Select a book in Step 01 first."; return; }
        btnHybVid.disabled = true;
        if (stEl) stEl.textContent = "Building Pass 1 (Real Plate with Gaps) + Pass 2 (Bring 2D Cast In) video prompts…";
        try {
          const res = await callApi("/api/v2_hybrid_video_prompts", {
            project: slug,
            scene_id: ($("v2HybridVidScene")?.value || "").trim(),
            gap_notes: ($("v2HybridVidGaps")?.value || "").trim(),
          });
          if ($("v2HybridP1Text")) $("v2HybridP1Text").value = res.pass1_prompt || "";
          if ($("v2HybridP2Text")) $("v2HybridP2Text").value = res.pass2_prompt || "";
          if ($("v2HybridPromptsOut")) $("v2HybridPromptsOut").style.display = "grid";
          if (stEl) stEl.textContent = `✓ Generated Two-Pass prompts for ${res.scene_id} (Live: ${(res.live_cast || []).join(", ")} · 2D: ${(res.cartoon_cast || []).join(", ")})`;
        } catch (err) {
          if (stEl) stEl.textContent = "Error: " + (err.message || err);
        } finally {
          btnHybVid.disabled = false;
        }
      });
    }
    const wireCopy = (btnId, taId) => {
      const b = $(btnId);
      if (!b) return;
      b.addEventListener("click", () => {
        const txt = $(taId)?.value || "";
        if (!txt) return;
        navigator.clipboard?.writeText(txt).catch(() => {});
        const prev = b.textContent;
        b.textContent = "✓ Copied!";
        setTimeout(() => { b.textContent = prev; }, 1200);
      });
    };
    wireCopy("bV2CopyHybridP1", "v2HybridP1Text");
    wireCopy("bV2CopyHybridP2", "v2HybridP2Text");
    wireCopy("bV2BeatPromptCopy", "v2BeatPromptOut");

    const btnBeatPrompt = $("bV2BeatPromptGen");
    if (btnBeatPrompt) {
      btnBeatPrompt.addEventListener("click", async () => {
        const slug = ($("proj")?.value || activeProject || "").trim();
        const stEl = $("v2LocalVideoStatus");
        if (!slug) { if (stEl) stEl.textContent = "Select a book in Step 01 first."; return; }
        btnBeatPrompt.disabled = true;
        if (stEl) stEl.textContent = "Building timed 0.0–Xs beat-by-beat motion prompt…";
        try {
          const res = await callApi("/api/v2_beat_motion_prompt", {
            project: slug,
            shot_id: ($("v2LocalVideoShotSelect")?.value || "").trim(),
            duration: parseFloat($("v2LocalVideoDuration")?.value || "6"),
          });
          if ($("v2BeatPromptOut")) $("v2BeatPromptOut").value = res.prompt || "";
          if ($("v2BeatPromptWrap")) $("v2BeatPromptWrap").style.display = "block";
          if ($("v2OmniPrompt") && res.prompt) $("v2OmniPrompt").value = res.prompt;
          if (stEl) stEl.textContent = `✓ Built ${res.duration}s beat-by-beat prompt for ${res.shot_id} (${res.style_name}).`;
        } catch (err) {
          if (stEl) stEl.textContent = "Beat prompt error: " + (err.message || err);
        } finally {
          btnBeatPrompt.disabled = false;
        }
      });
    }
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
            normalize_lufs: Boolean($("v2MixLufsNorm")?.checked),
            lufs: -14,
          });
          const aud = _renderV2SoundPlayer("v2MixPlayerWrap", res.audio_url, "");
          const lufsTag = res.lufs_master && res.lufs_master.normalized && res.lufs_master.after_lufs != null
            ? ` · ${Number(res.lufs_master.after_lufs).toFixed(1)} LUFS`
            : "";
          if ($("v2MixBadge")) $("v2MixBadge").textContent = `✓ Mixed (${res.duration_sec || 0}s${lufsTag})`;
          if (st) st.textContent = `✓ Mixed master audio (${res.duration_sec || 0}s${lufsTag})!`;
          if (aud) aud.play().catch(() => {});
        } catch (err) {
          if (st) { st.style.color = "#f87171"; st.textContent = "Mix failed: " + (err.message || err); }
        } finally {
          stopBusy();
        }
      });
    }

    const btnLufsNorm = $("bV2MixLufsBtn");
    if (btnLufsNorm) {
      btnLufsNorm.addEventListener("click", async () => {
        const slug = getSlug();
        if (!slug) return;
        const st = $("v2MixStatus");
        btnLufsNorm.disabled = true;
        if (st) { st.style.color = "#34d399"; st.textContent = "Measuring loudness & normalizing master_mix.wav to -14 LUFS (48 kHz)…"; }
        try {
          const res = await callApi("/api/v2_lufs_normalize", { project: slug, target_lufs: -14.0 });
          _renderV2SoundPlayer("v2MixPlayerWrap", res.audio_url, "");
          const bL = res.before_lufs != null ? Number(res.before_lufs).toFixed(1) : "?";
          const aL = res.after_lufs != null ? Number(res.after_lufs).toFixed(1) : "-14.0";
          if (st) st.textContent = `✓ Normalized master audio: ${bL} LUFS ➔ ${aL} LUFS (48 kHz peak-limited).`;
        } catch (err) {
          if (st) { st.style.color = "#f87171"; st.textContent = "LUFS normalize failed: " + (err.message || err); }
        } finally {
          btnLufsNorm.disabled = false;
        }
      });
    }

    // Export helper for Steps 20 & 22
    const triggerExport = async (target, btn, statusId) => {
      const slug = getSlug();
      if (!slug) return;
      const st = $(statusId);
      const runtime = $("v2TlRuntime")?.value || "ffmpeg";
      const silenceCut = Boolean($("v2ExpSilenceCut")?.checked);
      const autoReframe = Boolean($("v2ExpAutoReframe")?.checked);
      const burnCaptions = Boolean($("v2ExpBurnCaptions")?.checked);
      const stopBusy = startBusyFeedback(btn, null, `Building ${target} (${runtime})…`);
      if (st) { st.style.color = "#34d399"; st.textContent = `Building ${target} for "${slug}" (runtime: ${runtime})…`; }
      try {
        const res = await callApi("/api/v2_export_make", {
          project: slug,
          target,
          runtime,
          silence_cut: silenceCut,
          auto_reframe: autoReframe,
          burn_captions: burnCaptions,
        });
        const capTag = res.captions_burned ? ` · 💬 ${res.captions_burned} safe-zone caption cue(s) burned in` : "";
        if (st) st.textContent = `✓ Ready: ${target}${capTag}`;
        if (res.video_url) await loadV2PostProd();
        if (res.download_url) window.open(res.download_url, "_blank");
      } catch (err) {
        if (st) { st.style.color = "#f87171"; st.textContent = "Export failed: " + (err.message || err); }
      } finally {
        stopBusy();
      }
    };

    const btnTlQa = $("bV2TlQaCheck");
    if (btnTlQa) {
      btnTlQa.addEventListener("click", async () => {
        const slug = getSlug();
        const st = $("v2TlStatus");
        if (!slug) return;
        const runtime = $("v2TlRuntime")?.value || "ffmpeg";
        if (st) { st.style.color = "#34d399"; st.textContent = `Running Pre-Render QA Check (runtime: ${runtime})…`; }
        try {
          const tlScenes = (v2PostState && v2PostState.timeline && v2PostState.timeline.scenes) || [];
          const scenesPayload = tlScenes.length
            ? tlScenes.map((s, idx) => ({
                id: s.id || `S${idx + 1}`,
                visual_source: (v2PostState?.counts?.videos || 0) > 0 ? "ai_video" : "static_image",
                motion: idx % 2 === 0 ? "pan_left" : "zoom_in",
                duration_seconds: Number(s.seconds) || 4,
              }))
            : [{ id: "S001", visual_source: "ai_video", motion: "pan_left", duration_seconds: 4 }];
          const qa = await callApi("/api/qa/check", { scenes: scenesPayload, render_runtime: runtime });
          const verdict = (qa.verdict || "pass").toUpperCase();
          const avg = qa.average !== undefined ? ` (avg score: ${qa.average}/5)` : "";
          if (st) {
            st.style.color = verdict === "FAIL" ? "#f87171" : "#34d399";
            st.textContent = `🛡️ Pre-Render QA Verdict: ${verdict}${avg} · Runtime: ${runtime}`;
          }
        } catch (err) {
          if (st) { st.style.color = "#f87171"; st.textContent = "Pre-Render QA failed: " + (err.message || err); }
        }
      });
    }

    const bindExp = (id, target, stId) => {
      const b = $(id);
      if (b) b.addEventListener("click", () => triggerExport(target, b, stId));
    };
    bindExp("bV2TlAssemble", "master_mp4", "v2TlStatus");
    bindExp("bV2TlEdl", "edl", "v2TlStatus");
    bindExp("bV2ExpMasterMp4", "master_mp4", "v2ExpStatus");
    bindExp("bV2ExpShorts", "shorts_9x16", "v2ExpStatus");
    bindExp("bV2ExpFountain", "fountain", "v2ExpStatus");
    bindExp("bV2ExpPitchPptx", "pitch_pptx", "v2ExpStatus");
    bindExp("bV2ExpProdXlsx", "prod_xlsx", "v2ExpStatus");
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

    const renderCapPreview = (cues, srtUrl, infoLine) => {
      const st = $("v2CaptionsStatus");
      const box = $("v2CaptionsPreview");
      if (st) {
        st.style.color = "#34d399";
        st.innerHTML = `${esc(infoLine)} ${srtUrl ? `· <a href="${esc(srtUrl)}" target="_blank" rel="noopener" style="color:#c4b5fd;text-decoration:underline">⬇ Download safe_captions.srt</a>` : ""}`;
      }
      if (box) {
        box.style.display = "block";
        box.textContent = (cues || []).slice(0, 40).map(c =>
          `[${Number(c.start).toFixed(2)}s–${Number(c.end).toFixed(2)}s · ${c.font_px || 56}px] ${c.text}`
        ).join("\n") || "(No caption cues generated yet)";
      }
    };

    const btnBuildCaps = $("bV2BuildCaptions");
    if (btnBuildCaps) {
      btnBuildCaps.addEventListener("click", async () => {
        const slug = getSlug();
        if (!slug) return;
        const st = $("v2CaptionsStatus");
        btnBuildCaps.disabled = true;
        if (st) { st.style.color = "#cbd5e1"; st.textContent = "Building Audio-First Clock & frame-snapped Reels safe-zone captions…"; }
        try {
          const res = await callApi("/api/v2_audio_first_clock", { project: slug, fps: 24, use_whisper: true });
          renderCapPreview(
            res.cues || [],
            res.srt_url,
            `✓ Built ${res.cue_count || 0} safe-zone caption cue(s) via ${res.engine || "clock"} (drift: ${res.sync_drift_ms ?? 0} ms · min ${res.min_caption_px || 56} px)`
          );
        } catch (err) {
          if (st) { st.style.color = "#f87171"; st.textContent = "Caption build failed: " + (err.message || err); }
        } finally {
          btnBuildCaps.disabled = false;
        }
      });
    }

    const btnCapFix = $("bV2CapFix");
    if (btnCapFix) {
      btnCapFix.addEventListener("click", async () => {
        const slug = getSlug();
        const findW = ($("v2CapFind")?.value || "").trim();
        const repW = ($("v2CapReplace")?.value || "").trim();
        const st = $("v2CaptionsStatus");
        if (!slug || !findW) {
          if (st) { st.style.color = "#fbbf24"; st.textContent = "Enter a word to find (e.g. Cloud) and its replacement (e.g. Claude)."; }
          return;
        }
        btnCapFix.disabled = true;
        try {
          const res = await callApi("/api/v2_caption_proofread", { project: slug, find: findW, replace: repW });
          renderCapPreview(
            res.cues || [],
            res.srt_url,
            `✓ Proofread applied: replaced "${findW}" ➔ "${repW}" in ${res.changed_cues || 0} cue(s) & updated safe_captions.srt`
          );
        } catch (err) {
          if (st) { st.style.color = "#f87171"; st.textContent = "Proofread failed: " + (err.message || err); }
        } finally {
          btnCapFix.disabled = false;
        }
      });
    }

    // Adder #1: Reference-Video -> Editing Style Guide Analyzer (Step 20)
    let pendingRefVidData = { base64: "", filename: "" };
    const refFileIn = $("v2RefVidFile");
    if (refFileIn) {
      refFileIn.addEventListener("change", () => {
        const f = refFileIn.files && refFileIn.files[0];
        if (!f) return;
        const st = $("v2RefVidStatus");
        if (st) { st.style.color = "#cbd5e1"; st.textContent = `Loaded reference file: ${f.name} (${(f.size / 1048576).toFixed(1)} MB) — click Analyze.`; }
        const rd = new FileReader();
        rd.onload = () => { pendingRefVidData = { base64: String(rd.result || ""), filename: f.name }; };
        rd.readAsDataURL(f);
      });
    }
    const btnRefAnalyze = $("bV2RefVidAnalyze");
    if (btnRefAnalyze) {
      btnRefAnalyze.addEventListener("click", async () => {
        const slug = getSlug();
        if (!slug) return;
        const st = $("v2RefVidStatus");
        const guideEl = $("v2RefVidGuide");
        const swEl = $("v2RefVidSwatches");
        btnRefAnalyze.disabled = true;
        if (st) { st.style.color = "#cbd5e1"; st.textContent = "Analyzing reference video cut rhythm, color palette & pacing…"; }
        try {
          const res = await callApi("/api/v2_editing_style_analyze", {
            project: slug,
            video_base64: pendingRefVidData.base64,
            filename: pendingRefVidData.filename,
            url: ($("v2RefVidUrl")?.value || "").trim(),
            use_whisper: Boolean($("v2RefVidWhisper")?.checked),
          });
          if ($("v2TlCrossfade") && res.recommended_crossfade != null) {
            $("v2TlCrossfade").value = String(res.recommended_crossfade);
          }
          if (st) {
            st.style.color = "#34d399";
            st.innerHTML = `✓ ${esc(res.pacing_label || "Style Guide Ready")} · Avg shot: ${res.avg_shot_seconds}s · Recommended crossfade: ${res.recommended_crossfade}s · <a href="${esc(res.guide_url || "#")}" target="_blank" rel="noopener" style="color:#7dd3fc;text-decoration:underline">Open Editing Style Guide.md</a>`;
          }
          if (swEl) {
            swEl.innerHTML = (res.palette || []).map(hx =>
              `<span style="display:inline-flex;align-items:center;gap:4px;padding:2px 6px;border-radius:4px;background:#0a0d14;border:1px solid #334155;font-size:10px;color:#cbd5e1"><span style="width:12px;height:12px;border-radius:2px;background:${esc(hx)};display:inline-block"></span>${esc(hx)}</span>`
            ).join("");
          }
          if (guideEl && res.guide_markdown) {
            guideEl.style.display = "block";
            guideEl.textContent = res.guide_markdown;
          }
        } catch (err) {
          if (st) { st.style.color = "#f87171"; st.textContent = "Reference analysis failed: " + (err.message || err); }
        } finally {
          btnRefAnalyze.disabled = false;
        }
      });
    }

    // Adder #2: Dialogue & Narration Humanizer (Steps 06 & 15)
    const runHumanizer = async (btn, statusEl, dialogueOnly, reloadFn) => {
      const slug = getSlug();
      if (!slug) return;
      btn.disabled = true;
      if (statusEl) { statusEl.style.color = "#cbd5e1"; statusEl.textContent = "Humanizing AI clichés & smoothing spoken cadence…"; }
      try {
        const res = await callApi("/api/v2_humanize_script", { project: slug, apply: true, dialogue_only: dialogueOnly });
        if (statusEl) {
          statusEl.style.color = "#34d399";
          statusEl.textContent = res.lines_changed
            ? `✓ Humanized ${res.lines_changed} line(s) across ${res.scenes_scanned} scene(s).`
            : `✓ Scanned ${res.lines_scanned} line(s) — already sounded natural & human!`;
        }
        if (res.lines_changed && typeof reloadFn === "function") reloadFn();
      } catch (err) {
        if (statusEl) { statusEl.style.color = "#f87171"; statusEl.textContent = "Humanizer failed: " + (err.message || err); }
      } finally {
        btn.disabled = false;
      }
    };
    const btnSpHum = $("bV2SpHumanize");
    if (btnSpHum) btnSpHum.addEventListener("click", () => runHumanizer(btnSpHum, $("v2SpHumanizeStatus"), false, () => { if (typeof loadV2Screenplay === "function") loadV2Screenplay(); }));
    const btnDlgHum = $("bV2DlgHumanize");
    if (btnDlgHum) btnDlgHum.addEventListener("click", () => runHumanizer(btnDlgHum, $("v2DialogueSummary"), true, () => { if (typeof loadV2Dialogue === "function") loadV2Dialogue(); }));

    // Adder #4: Code-Drawn Title Cards & Explainers (Step 20)
    const btnCdRender = $("bV2CdRender");
    if (btnCdRender) {
      btnCdRender.addEventListener("click", async () => {
        const slug = getSlug();
        if (!slug) return;
        const st = $("v2CdStatus");
        const prev = $("v2CdPreview");
        btnCdRender.disabled = true;
        if (st) { st.style.color = "#cbd5e1"; st.textContent = "Rendering deterministic code-drawn MP4…"; }
        try {
          const rawB = ($("v2CdBullets")?.value || "").trim();
          const bullets = rawB ? rawB.split("|").map(s => s.trim()).filter(Boolean) : [];
          const res = await callApi("/api/v2_code_drawn_render", {
            project: slug,
            template_id: $("v2CdTemplate")?.value || "cinema_title_card",
            title: ($("v2CdTitle")?.value || "").trim(),
            subtitle: ($("v2CdSubtitle")?.value || "").trim(),
            bullets,
            aspect: $("v2CdAspect")?.value || "16:9",
            duration: 4.0,
            fps: 30,
          });
          if (st) {
            st.style.color = "#34d399";
            st.innerHTML = `✓ Rendered ${esc(res.template_id)} (${res.aspect}, ${res.fps} fps) · <a href="${esc(res.download_url)}" target="_blank" rel="noopener" style="color:#fde68a;text-decoration:underline">⬇ Download MP4</a>`;
          }
          if (prev && res.video_url) {
            prev.innerHTML = `<video controls playsinline src="${esc(res.video_url)}?t=${Date.now()}" style="max-width:420px;width:100%;border-radius:8px;border:1px solid #334155"></video>`;
          }
        } catch (err) {
          if (st) { st.style.color = "#f87171"; st.textContent = "Render failed: " + (err.message || err); }
        } finally {
          btnCdRender.disabled = false;
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

  // ===== SPLASH SCREEN =====
  function hideSplashScreen() {
    const splash = $("splashScreen");
    if (splash) {
      splash.classList.add("hidden");
      // Remove from DOM after transition to free memory
      setTimeout(() => splash.remove(), 500);
    }
  }

  // ===== INITIALIZATION & BINDING =====
  window.addEventListener("DOMContentLoaded", () => {
    // Pipeline mode is the default: hide all classic panels below
    document.body.classList.remove("mode-unified");
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

    // Bind next/prev buttons in all step action docks (Approve & Next advances the bi-directional sync queue!)
    document.querySelectorAll(".btn-step-next").forEach(btn => {
      btn.addEventListener("click", (e) => {
        e.preventDefault();
        handleV2ApproveNextClick();
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

    const selProjSync = $("proj");
    if (selProjSync) {
      selProjSync.addEventListener("change", () => loadV2WorkflowSync());
    }

    setTimeout(() => {
      checkStepStorylineDrift();
      loadV2WorkflowSync();
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

      // Hide splash screen after app initialization
      hideSplashScreen();
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
