/* Studio Menu Bar: File (New/Open/Save/Save As/Exit), Edit (Undo/Redo/Copy/Paste/Goto Step),
 * View (Pipeline, Creative Workbench submenu), Help (Manual, About) + standard Ctrl shortcuts.
 */
(function () {
  "use strict";

  const STEPS = [
    { num: 1, phase: "Phase 1 · Story & Script", name: "01 Ingest & Source" },
    { num: 2, phase: "Phase 1 · Story & Script", name: "02 Check & Split Chapters" },
    { num: 3, phase: "Phase 1 · Story & Script", name: "03 Coverage & Logline" },
    { num: 4, phase: "Phase 1 · Story & Script", name: "04 Format & Runtime Scope" },
    { num: 5, phase: "Phase 1 · Story & Script", name: "05 Story Structure & Beats" },
    { num: 6, phase: "Phase 1 · Story & Script", name: "06 Screenplay Editor (Trelby)" },
    { num: 7, phase: "Phase 2 · Cast & World", name: "07 Continuity, Rules & Props/Backdrops" },
    { num: 8, phase: "Phase 2 · Cast & World", name: "08 Cast & Characters" },
    { num: 9, phase: "Phase 2 · Cast & World", name: "09 Art Direction & Style" },
    { num: 10, phase: "Phase 2 · Cast & World", name: "10 Look Development & Turnarounds" },
    { num: 11, phase: "Phase 2 · Cast & World", name: "11 Static Sets" },
    { num: 12, phase: "Phase 3 · Camera & Compute", name: "12 Shot List & Cinematography" },
    { num: 13, phase: "Phase 3 · Camera & Compute", name: "13 Hardware & Where to Run" },
    { num: 14, phase: "Phase 4 · Audio & Voices", name: "14 Voice Casting & Dialects" },
    { num: 15, phase: "Phase 4 · Audio & Voices", name: "15 Spoken Dialogue Delivery" },
    { num: 16, phase: "Phase 4 · Audio & Voices", name: "16 Score & Foley Sound Design" },
    { num: 17, phase: "Phase 5 · Visuals & Motion", name: "17 Storyboard Keyframes" },
    { num: 18, phase: "Phase 5 · Visuals & Motion", name: "18 Motion & Video Synthesis" },
    { num: 19, phase: "Phase 5 · Visuals & Motion", name: "19 Lip-Sync & Polish" },
    { num: 20, phase: "Phase 6 · Post & Premiere", name: "20 Timeline Sequence Assembly" },
    { num: 21, phase: "Phase 6 · Post & Premiere", name: "21 Audio Stem Mix (-16 LUFS)" },
    { num: 22, phase: "Phase 6 · Post & Premiere", name: "22 Cinema Premiere & Export" },
  ];

  let activeProjectMeta = null;
  let allProjectsCache = [];
  let manualMarkdownCache = "";
  let statusTimer = null;

  function $(id) {
    return document.getElementById(id);
  }

  function studioToken() {
    const m = document.querySelector('meta[name="studio-token"]');
    return m ? m.getAttribute("content") || "" : "";
  }

  async function api(url, body) {
    const opts = {
      method: body !== undefined ? "POST" : "GET",
      headers: { "X-Studio-Token": studioToken() },
    };
    if (body !== undefined) {
      opts.headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(body);
    }
    const resp = await fetch(url, opts);
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) {
      throw new Error(data.error || `HTTP ${resp.status}`);
    }
    return data;
  }

  function flashStatus(msg, isError) {
    const el = $("mbStatusMsg");
    if (!el) return;
    el.style.color = isError ? "#f87171" : "#34d399";
    el.textContent = msg;
    if (statusTimer) clearTimeout(statusTimer);
    statusTimer = setTimeout(() => {
      el.textContent = "";
    }, 5500);
  }

  function currentSlug() {
    const sel = $("proj");
    if (sel && sel.value) return sel.value.trim();
    return (activeProjectMeta && activeProjectMeta.slug) || "";
  }

  function currentStepNum() {
    const activePill = document.querySelector("#pipelinePhasesBar .step-pill.active");
    if (activePill) {
      const n = parseInt(activePill.getAttribute("data-step") || "1", 10);
      if (!Number.isNaN(n)) return n;
    }
    return 1;
  }

  function updateProjectBadge(meta) {
    if (meta) activeProjectMeta = meta;
    const badge = $("mbActiveProjectBadge");
    if (!badge) return;
    const slug = currentSlug();
    if (activeProjectMeta && (!slug || activeProjectMeta.slug === slug)) {
      const bookPart = activeProjectMeta.book_source ? ` · Book: ${activeProjectMeta.book_title || activeProjectMeta.book_source}` : "";
      badge.textContent = `📁 Project: ${activeProjectMeta.name}${bookPart}`;
      badge.title = `Project: ${activeProjectMeta.name} (${activeProjectMeta.slug})${activeProjectMeta.book_source ? " · Input: " + activeProjectMeta.book_source : ""}`;
    } else if (slug) {
      badge.textContent = `📁 Project: ${slug}`;
      badge.title = `Project: ${slug}`;
    } else {
      badge.textContent = "📁 Project: (none)";
    }
  }

  function closeAllMenus() {
    document.querySelectorAll("#studioMenubar .mb-item.open, #studioMenubar .mb-subwrap.open").forEach((el) => {
      el.classList.remove("open");
      const trig = el.querySelector(":scope > button");
      if (trig) trig.setAttribute("aria-expanded", "false");
    });
  }

  function openModal(id) {
    const m = $(id);
    if (m) m.classList.add("open");
  }

  function closeModal(id) {
    const m = $(id);
    if (m) m.classList.remove("open");
  }

  function switchToPipeline(stepNum) {
    document.body.classList.remove("mode-workbench");
    const ret = $("workbenchReturnBanner");
    if (ret) ret.classList.add("hidden");
    const dd = $("workbenchDropdown");
    if (dd) dd.classList.add("hidden");
    const targetStep = stepNum || currentStepNum();
    const pill = document.querySelector(`#pipelinePhasesBar .step-pill[data-step="${targetStep}"]`);
    if (pill) pill.click();
  }

  function switchToWorkbench(panelId) {
    const wbBtn = document.querySelector(`#workbenchDropdown .wb-tab-btn[data-target="${panelId}"]`);
    if (wbBtn) {
      wbBtn.click();
      return;
    }
    document.body.classList.add("mode-workbench");
  }

  function selectProjectInStudio(projMeta, storyPreview) {
    if (!projMeta || !projMeta.slug) return;
    activeProjectMeta = projMeta;
    const sel = $("proj");
    if (sel) {
      let opt = Array.from(sel.options).find((o) => o.value === projMeta.slug);
      if (!opt) {
        opt = document.createElement("option");
        opt.value = projMeta.slug;
        opt.textContent = projMeta.name || projMeta.slug;
        sel.appendChild(opt);
      }
      sel.value = projMeta.slug;
      sel.dispatchEvent(new Event("change", { bubbles: true }));
    }
    if (projMeta.book_source && $("storyFilename")) {
      const fname = projMeta.book_source.split("/").pop() || `${projMeta.slug}.txt`;
      $("storyFilename").value = fname;
    }
    if (typeof storyPreview === "string" && storyPreview && $("storyInputText")) {
      $("storyInputText").value = storyPreview;
    }
    updateProjectBadge(projMeta);
    if (projMeta.last_step && projMeta.last_step >= 1 && projMeta.last_step <= 22) {
      switchToPipeline(projMeta.last_step);
    }
  }

  // ===== FILE ACTIONS =====
  async function openNewProjectDialog() {
    const msg = $("mbNewMsg");
    if (msg) msg.textContent = "";
    if ($("mbNewName")) $("mbNewName").value = "";
    if ($("mbNewStoryText")) $("mbNewStoryText").value = "";
    const sel = $("mbNewBook");
    if (sel) {
      sel.innerHTML = "";
      const blank = document.createElement("option");
      blank.value = "";
      blank.textContent = "— None (paste story text below or upload in Step 01) —";
      sel.appendChild(blank);
      try {
        const data = await api("/api/studio/projects");
        (data.books || []).forEach((b) => {
          const o = document.createElement("option");
          o.value = b.value;
          o.textContent = b.label;
          sel.appendChild(o);
        });
      } catch (err) {
        if (msg) msg.textContent = "Could not load book list: " + err.message;
      }
    }
    openModal("mbNewProjectModal");
    if ($("mbNewName")) $("mbNewName").focus();
  }

  async function submitNewProject() {
    const name = ($("mbNewName")?.value || "").trim();
    const bookSource = ($("mbNewBook")?.value || "").trim();
    const storyText = ($("mbNewStoryText")?.value || "").trim();
    const msg = $("mbNewMsg");
    const btn = $("bMbNewCreate");
    if (!name) {
      if (msg) msg.textContent = "Please enter a Project Name.";
      return;
    }
    if (btn) btn.disabled = true;
    if (msg) msg.textContent = "";
    try {
      const res = await api("/api/studio/project/new", {
        name,
        book_source: bookSource,
        story_text: storyText,
      });
      closeModal("mbNewProjectModal");
      const opened = await api("/api/studio/project/open", { slug: res.project.slug });
      selectProjectInStudio(opened.project, opened.story_preview || storyText);
      flashStatus(`✓ Created & opened project "${opened.project.name}"`, false);
    } catch (err) {
      if (msg) msg.textContent = err.message || String(err);
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  function renderOpenProjectList(filterText) {
    const list = $("mbOpenList");
    if (!list) return;
    list.innerHTML = "";
    const q = String(filterText || "").trim().toLowerCase();
    const filtered = allProjectsCache.filter(
      (p) =>
        !q ||
        String(p.name || "").toLowerCase().includes(q) ||
        String(p.slug || "").toLowerCase().includes(q) ||
        String(p.book_title || "").toLowerCase().includes(q) ||
        String(p.book_source || "").toLowerCase().includes(q)
    );
    if (!filtered.length) {
      const empty = document.createElement("div");
      empty.style.cssText = "padding:14px;text-align:center;color:#94a3b8;font-size:13px";
      empty.textContent = "No matching projects found. Use File → New Project (Ctrl+N) to create one.";
      list.appendChild(empty);
      return;
    }
    filtered.forEach((p) => {
      const row = document.createElement("button");
      row.type = "button";
      row.style.cssText =
        "display:flex;align-items:center;justify-content:space-between;gap:10px;width:100%;padding:9px 12px;border-radius:8px;border:1px solid var(--border,#334155);background:rgba(15,23,42,0.65);color:var(--fg,#f8fafc);cursor:pointer;text-align:left;";
      const left = document.createElement("div");
      left.style.cssText = "display:flex;flex-direction:column;gap:2px;min-width:0;";
      const title = document.createElement("strong");
      title.style.cssText = "font-size:13px;color:#f8fafc;";
      title.textContent = p.name || p.slug;
      const meta = document.createElement("small");
      meta.style.cssText = "font-size:11.5px;color:#94a3b8;";
      meta.textContent = `Book: ${p.book_source || "(unassigned)"} · Step ${p.last_step || 1}${p.history_count ? ` · ${p.history_count} snapshot(s)` : ""}`;
      left.appendChild(title);
      left.appendChild(meta);

      const tag = document.createElement("span");
      tag.style.cssText = "font-size:11px;padding:2px 8px;border-radius:999px;background:rgba(34,211,238,0.12);color:#67e8f9;white-space:nowrap;";
      tag.textContent = p.slug === currentSlug() ? "Active" : "Open";

      row.appendChild(left);
      row.appendChild(tag);
      row.addEventListener("click", async () => {
        const msg = $("mbOpenMsg");
        if (msg) msg.textContent = `Opening "${p.name || p.slug}"…`;
        try {
          const res = await api("/api/studio/project/open", { slug: p.slug });
          closeModal("mbOpenProjectModal");
          selectProjectInStudio(res.project, res.story_preview);
          flashStatus(`✓ Opened "${res.project.name}"${res.book_source ? ` (Book: ${res.book_source})` : ""}`, false);
        } catch (err) {
          if (msg) {
            msg.style.color = "#f87171";
            msg.textContent = err.message || String(err);
          }
        }
      });
      list.appendChild(row);
    });
  }

  async function openOpenProjectDialog() {
    const msg = $("mbOpenMsg");
    if (msg) {
      msg.style.color = "#94a3b8";
      msg.textContent = "Loading projects…";
    }
    if ($("mbOpenFilter")) $("mbOpenFilter").value = "";
    openModal("mbOpenProjectModal");
    try {
      const data = await api("/api/studio/projects");
      allProjectsCache = data.projects || [];
      if (msg) msg.textContent = `${allProjectsCache.length} project(s) available — click one to open & link its book.`;
      renderOpenProjectList("");
      if ($("mbOpenFilter")) $("mbOpenFilter").focus();
    } catch (err) {
      if (msg) {
        msg.style.color = "#f87171";
        msg.textContent = "Could not list projects: " + err.message;
      }
    }
  }

  async function saveActiveProject() {
    const slug = currentSlug();
    if (!slug) {
      flashStatus("Create or open a project first (Ctrl+N / Ctrl+O).", true);
      return;
    }
    // If on Step 06 screenplay editor, trigger its scene save too if present
    const spSaveBtn = $("v2SpSaveAll");
    const step6Active = $("panel-step-6") && $("panel-step-6").classList.contains("active");
    if (step6Active && spSaveBtn && !spSaveBtn.disabled) {
      spSaveBtn.click();
    }
    try {
      const stepNum = currentStepNum();
      const res = await api("/api/studio/project/save", {
        slug,
        label: `Saved at Step ${String(stepNum).padStart(2, "0")}`,
        last_step: stepNum,
      });
      updateProjectBadge(res.project);
      flashStatus(`💾 Saved "${res.project.name}" (snapshot #${res.history_count})`, false);
    } catch (err) {
      flashStatus("Save failed: " + (err.message || err), true);
    }
  }

  function openSaveAsDialog() {
    const slug = currentSlug();
    if (!slug) {
      flashStatus("Open a project first before using Save As.", true);
      return;
    }
    if ($("mbSaveAsMsg")) $("mbSaveAsMsg").textContent = "";
    if ($("mbSaveAsHint")) $("mbSaveAsHint").textContent = `Clone "${(activeProjectMeta && activeProjectMeta.name) || slug}" into a new named project folder.`;
    if ($("mbSaveAsName")) $("mbSaveAsName").value = `${(activeProjectMeta && activeProjectMeta.name) || slug} Copy`;
    openModal("mbSaveAsModal");
    if ($("mbSaveAsName")) {
      $("mbSaveAsName").focus();
      $("mbSaveAsName").select();
    }
  }

  async function submitSaveAs() {
    const slug = currentSlug();
    const newName = ($("mbSaveAsName")?.value || "").trim();
    const msg = $("mbSaveAsMsg");
    const btn = $("bMbSaveAsConfirm");
    if (!newName) {
      if (msg) msg.textContent = "Enter a new Project Name.";
      return;
    }
    if (btn) btn.disabled = true;
    if (msg) msg.textContent = "";
    try {
      const res = await api("/api/studio/project/save_as", {
        source_slug: slug,
        new_name: newName,
        last_step: currentStepNum(),
      });
      closeModal("mbSaveAsModal");
      selectProjectInStudio(res.project);
      flashStatus(`✓ Saved as new project "${res.project.name}"`, false);
    } catch (err) {
      if (msg) msg.textContent = err.message || String(err);
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  async function exitStudio() {
    const ok = window.confirm("Exit Pistachio's Studio and cleanly shut down the local server?");
    if (!ok) return;
    try {
      await api("/api/studio/shutdown", { stop_jobs: true });
    } catch (_) {
      /* server may already be closing */
    }
    document.body.innerHTML =
      '<div style="min-height:100vh;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:12px;background:#0a0d14;color:#f8fafc;font-family:system-ui,sans-serif;padding:24px;text-align:center;">' +
      '<h1 style="margin:0;color:#22d3ee;">Pistachio\'s Studio Closed</h1>' +
      '<p style="margin:0;color:#94a3b8;max-width:440px;">The local Studio server and managed background processes have shut down cleanly. You may safely close this browser tab.</p>' +
      "</div>";
    try {
      window.close();
    } catch (_) {
      /* browsers may ignore script-triggered close */
    }
  }

  // ===== EDIT ACTIONS (CONTEXT-AWARE UNDO/REDO, COPY/PASTE, GOTO STEP) =====
  function isEditableFocus() {
    const ae = document.activeElement;
    if (!ae) return false;
    const tag = (ae.tagName || "").toUpperCase();
    return tag === "INPUT" || tag === "TEXTAREA" || ae.isContentEditable === true;
  }

  async function doUndo(fromMenu) {
    if (isEditableFocus()) {
      if (fromMenu) {
        try {
          document.execCommand("undo");
        } catch (_) {
          /* ignore */
        }
      }
      return;
    }
    const slug = currentSlug();
    if (!slug) {
      flashStatus("No active project to undo.", true);
      return;
    }
    try {
      const res = await api("/api/studio/project/undo", { slug });
      if (res.ok) {
        flashStatus(`↶ ${res.message}`, false);
        const sel = $("proj");
        if (sel) sel.dispatchEvent(new Event("change", { bubbles: true }));
      } else {
        flashStatus(res.message || "Nothing to undo.", false);
      }
    } catch (err) {
      flashStatus("Undo failed: " + (err.message || err), true);
    }
  }

  async function doRedo(fromMenu) {
    if (isEditableFocus()) {
      if (fromMenu) {
        try {
          document.execCommand("redo");
        } catch (_) {
          /* ignore */
        }
      }
      return;
    }
    const slug = currentSlug();
    if (!slug) {
      flashStatus("No active project to redo.", true);
      return;
    }
    try {
      const res = await api("/api/studio/project/redo", { slug });
      if (res.ok) {
        flashStatus(`↷ ${res.message}`, false);
        const sel = $("proj");
        if (sel) sel.dispatchEvent(new Event("change", { bubbles: true }));
      } else {
        flashStatus(res.message || "Nothing to redo.", false);
      }
    } catch (err) {
      flashStatus("Redo failed: " + (err.message || err), true);
    }
  }

  async function doCopy() {
    const selText = window.getSelection ? String(window.getSelection()) : "";
    let text = selText;
    if (!text && isEditableFocus()) {
      const ae = document.activeElement;
      if (typeof ae.selectionStart === "number" && typeof ae.selectionEnd === "number") {
        text = String(ae.value || "").slice(ae.selectionStart, ae.selectionEnd);
      }
    }
    if (text && navigator.clipboard && navigator.clipboard.writeText) {
      try {
        await navigator.clipboard.writeText(text);
        flashStatus("Copied selection to clipboard.", false);
        return;
      } catch (_) {
        /* fallback */
      }
    }
    try {
      document.execCommand("copy");
      flashStatus("Copied selection.", false);
    } catch (_) {
      flashStatus("Use Ctrl+C to copy selected text.", false);
    }
  }

  async function doPaste() {
    const ae = document.activeElement;
    if (navigator.clipboard && navigator.clipboard.readText) {
      try {
        const clip = await navigator.clipboard.readText();
        if (clip && ae && (ae.tagName === "INPUT" || ae.tagName === "TEXTAREA")) {
          const start = typeof ae.selectionStart === "number" ? ae.selectionStart : ae.value.length;
          const end = typeof ae.selectionEnd === "number" ? ae.selectionEnd : ae.value.length;
          ae.value = ae.value.slice(0, start) + clip + ae.value.slice(end);
          ae.selectionStart = ae.selectionEnd = start + clip.length;
          ae.dispatchEvent(new Event("input", { bubbles: true }));
          flashStatus("Pasted from clipboard.", false);
          return;
        }
      } catch (_) {
        /* fallback */
      }
    }
    flashStatus("Focus a text field and press Ctrl+V to paste.", false);
  }

  function renderGotoStepList(filterText) {
    const list = $("mbGotoList");
    if (!list) return;
    list.innerHTML = "";
    const q = String(filterText || "").trim().toLowerCase();
    const matches = STEPS.filter(
      (s) => !q || String(s.num) === q || s.name.toLowerCase().includes(q) || s.phase.toLowerCase().includes(q)
    );
    matches.forEach((s) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.style.cssText =
        "display:flex;align-items:center;justify-content:space-between;gap:10px;width:100%;padding:8px 11px;border-radius:7px;border:1px solid var(--border,#334155);background:rgba(15,23,42,0.65);color:var(--fg,#f8fafc);cursor:pointer;text-align:left;font-size:13px;";
      const lbl = document.createElement("span");
      lbl.textContent = s.name;
      const ph = document.createElement("small");
      ph.style.cssText = "color:#94a3b8;font-size:11px;";
      ph.textContent = s.phase;
      btn.appendChild(lbl);
      btn.appendChild(ph);
      btn.addEventListener("click", () => {
        closeModal("mbGotoStepModal");
        switchToPipeline(s.num);
        flashStatus(`Jumped to ${s.name}`, false);
      });
      list.appendChild(btn);
    });
  }

  function openGotoStepDialog() {
    if ($("mbGotoFilter")) $("mbGotoFilter").value = "";
    renderGotoStepList("");
    openModal("mbGotoStepModal");
    if ($("mbGotoFilter")) $("mbGotoFilter").focus();
  }

  // ===== HELP: MANUAL & ABOUT =====
  function escHtml(str) {
    return String(str || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function formatInlineMd(text) {
    return escHtml(text)
      .replace(/`([^`]+)`/g, "<code>$1</code>")
      .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
      .replace(/\*([^*]+)\*/g, "<em>$1</em>");
  }

  function renderManual(markdown, searchQuery) {
    const toc = $("mbManualToc");
    const content = $("mbManualContent");
    if (!toc || !content) return;
    toc.innerHTML = "";
    const q = String(searchQuery || "").trim().toLowerCase();
    const lines = String(markdown || "").replace(/\r\n/g, "\n").split("\n");
    const html = [];
    const headings = [];
    let inUl = false;
    let inOl = false;
    let inTable = false;

    const closeLists = () => {
      if (inUl) { html.push("</ul>"); inUl = false; }
      if (inOl) { html.push("</ol>"); inOl = false; }
      if (inTable) { html.push("</tbody></table>"); inTable = false; }
    };

    for (let i = 0; i < lines.length; i += 1) {
      const raw = lines[i];
      const line = raw.trim();
      if (!line) {
        closeLists();
        continue;
      }
      if (/^---+$/.test(line)) {
        closeLists();
        html.push("<hr>");
        continue;
      }
      const hm = line.match(/^(#{1,3})\s+(.+)$/);
      if (hm) {
        closeLists();
        const lvl = hm[1].length;
        const txt = hm[2].trim();
        const hid = `manual-h-${headings.length}`;
        headings.push({ id: hid, level: lvl, text: txt });
        html.push(`<h${lvl} id="${hid}">${formatInlineMd(txt)}</h${lvl}>`);
        continue;
      }
      if (line.startsWith("> ")) {
        closeLists();
        html.push(`<blockquote>${formatInlineMd(line.slice(2))}</blockquote>`);
        continue;
      }
      if (line.startsWith("|") && line.endsWith("|")) {
        if (/^\|\s*[-:]+/.test(line)) continue;
        const cells = line.slice(1, -1).split("|").map((c) => c.trim());
        if (!inTable) {
          closeLists();
          inTable = true;
          html.push("<table><thead><tr>" + cells.map((c) => `<th>${formatInlineMd(c)}</th>`).join("") + "</tr></thead><tbody>");
        } else {
          html.push("<tr>" + cells.map((c) => `<td>${formatInlineMd(c)}</td>`).join("") + "</tr>");
        }
        continue;
      }
      if (line.startsWith("- ")) {
        if (inOl) { html.push("</ol>"); inOl = false; }
        if (inTable) { html.push("</tbody></table>"); inTable = false; }
        if (!inUl) { html.push("<ul>"); inUl = true; }
        html.push(`<li>${formatInlineMd(line.slice(2))}</li>`);
        continue;
      }
      const om = line.match(/^\d+\.\s+(.+)$/);
      if (om) {
        if (inUl) { html.push("</ul>"); inUl = false; }
        if (inTable) { html.push("</tbody></table>"); inTable = false; }
        if (!inOl) { html.push("<ol>"); inOl = true; }
        html.push(`<li>${formatInlineMd(om[1])}</li>`);
        continue;
      }
      closeLists();
      html.push(`<p>${formatInlineMd(line)}</p>`);
    }
    closeLists();

    let rendered = html.join("\n");
    if (q) {
      const safeQ = q.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
      const re = new RegExp(`(${safeQ})(?![^<]*>)`, "gi");
      rendered = rendered.replace(re, '<mark style="background:#f59e0b;color:#0b0e14;padding:0 2px;border-radius:2px">$1</mark>');
    }
    content.innerHTML = rendered;

    headings
      .filter((h) => h.level >= 2)
      .forEach((h) => {
        const b = document.createElement("button");
        b.type = "button";
        b.className = `mb-toc-btn${h.level === 3 ? " mb-toc-btn--h3" : ""}`;
        b.textContent = h.text;
        b.addEventListener("click", () => {
          const target = $(h.id);
          if (target) target.scrollIntoView({ behavior: "smooth", block: "start" });
        });
        toc.appendChild(b);
      });

    if (q) {
      const firstHit = content.querySelector("mark");
      if (firstHit) firstHit.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }

  async function openManualDialog() {
    openModal("mbManualModal");
    if (!manualMarkdownCache) {
      try {
        const res = await api("/api/studio/manual");
        manualMarkdownCache = res.markdown || "";
      } catch (err) {
        manualMarkdownCache = `# Manual Error\n\nCould not load manual: ${err.message}`;
      }
    }
    renderManual(manualMarkdownCache, $("mbManualSearch")?.value || "");
  }

  async function openAboutDialog() {
    openModal("mbAboutModal");
    const body = $("mbAboutBody");
    if (!body) return;
    body.textContent = "Loading…";
    try {
      const info = await api("/api/studio/about");
      body.innerHTML =
        `<div style="font-size:18px;font-weight:700;color:#22d3ee">${escHtml(info.name || "Pistachio's Studio")}</div>` +
        `<div style="color:#cbd5e1">${escHtml(info.tagline || "Local-First AI Book-to-Film Production Studio")}</div>` +
        `<div style="padding:10px 12px;border-radius:8px;background:rgba(15,23,42,0.7);border:1px solid var(--border,#334155);font-size:12.5px;display:flex;flex-direction:column;gap:4px;">` +
        `<div><strong>Version:</strong> ${escHtml(info.version || "2.0")}</div>` +
        `<div><strong>Open-Source Tools Detected:</strong> ${Number(info.tools_installed || 0)} / ${Number(info.tools_total || 0)}</div>` +
        `<div><strong>License:</strong> ${escHtml(info.license || "MIT")}</div>` +
        `<div><strong>Active Project:</strong> ${escHtml((activeProjectMeta && activeProjectMeta.name) || currentSlug() || "(none)")}</div>` +
        `</div>` +
        `<div style="font-size:12px;color:#94a3b8">Runs 100% locally on your computer with optional cloud GPU &amp; API support. Press <code>F1</code> anytime for the full User Manual.</div>`;
    } catch (err) {
      body.textContent = "Could not load About info: " + err.message;
    }
  }

  function handleMenuAction(action) {
    closeAllMenus();
    if (action === "file:new") return openNewProjectDialog();
    if (action === "file:open") return openOpenProjectDialog();
    if (action === "file:save") return saveActiveProject();
    if (action === "file:save-as") return openSaveAsDialog();
    if (action === "file:exit") return exitStudio();
    if (action === "edit:undo") return doUndo(true);
    if (action === "edit:redo") return doRedo(true);
    if (action === "edit:copy") return doCopy();
    if (action === "edit:paste") return doPaste();
    if (action === "edit:goto") return openGotoStepDialog();
    if (action === "view:pipeline") return switchToPipeline();
    if (action.startsWith("view:wb:")) return switchToWorkbench(action.slice("view:wb:".length));
    if (action === "help:manual") return openManualDialog();
    if (action === "help:about") return openAboutDialog();
  }

  function bindMenubar() {
    const bar = $("studioMenubar");
    if (!bar) return;

    // Top-level menu triggers (click to toggle, hover to switch while open)
    bar.querySelectorAll(".mb-item").forEach((item) => {
      const trig = item.querySelector(":scope > .mb-trigger");
      if (!trig) return;
      trig.addEventListener("click", (e) => {
        e.stopPropagation();
        const wasOpen = item.classList.contains("open");
        closeAllMenus();
        if (!wasOpen) {
          item.classList.add("open");
          trig.setAttribute("aria-expanded", "true");
        }
      });
      item.addEventListener("mouseenter", () => {
        const anyOpen = Boolean(bar.querySelector(".mb-item.open"));
        if (anyOpen && !item.classList.contains("open")) {
          closeAllMenus();
          item.classList.add("open");
          trig.setAttribute("aria-expanded", "true");
        }
      });
    });

    // Submenu toggle on click (also opens on hover via CSS)
    bar.querySelectorAll(".mb-subtrigger").forEach((sub) => {
      sub.addEventListener("click", (e) => {
        e.stopPropagation();
        const wrap = sub.closest(".mb-subwrap");
        if (wrap) {
          const open = wrap.classList.toggle("open");
          sub.setAttribute("aria-expanded", open ? "true" : "false");
        }
      });
    });

    // Menu action buttons
    bar.querySelectorAll("[data-mb-action]").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        handleMenuAction(btn.getAttribute("data-mb-action") || "");
      });
    });

    // Click outside closes open dropdowns
    document.addEventListener("click", (e) => {
      if (!bar.contains(e.target)) closeAllMenus();
    });

    // Wire modal buttons
    const wireClose = (btnIds, modalId) => {
      btnIds.forEach((id) => {
        const b = $(id);
        if (b) b.addEventListener("click", () => closeModal(modalId));
      });
      const m = $(modalId);
      if (m) {
        m.addEventListener("click", (e) => {
          if (e.target === m) closeModal(modalId);
        });
      }
    };
    wireClose(["bMbNewClose", "bMbNewCancel"], "mbNewProjectModal");
    wireClose(["bMbOpenClose", "bMbOpenCancel"], "mbOpenProjectModal");
    wireClose(["bMbSaveAsClose", "bMbSaveAsCancel"], "mbSaveAsModal");
    wireClose(["bMbGotoClose", "bMbGotoCancel"], "mbGotoStepModal");
    wireClose(["bMbManualClose"], "mbManualModal");
    wireClose(["bMbAboutClose", "bMbAboutOk"], "mbAboutModal");

    if ($("bMbNewCreate")) $("bMbNewCreate").addEventListener("click", submitNewProject);
    if ($("mbNewName")) {
      $("mbNewName").addEventListener("keydown", (e) => {
        if (e.key === "Enter") submitNewProject();
      });
    }
    if ($("mbOpenFilter")) {
      $("mbOpenFilter").addEventListener("input", () => renderOpenProjectList($("mbOpenFilter").value));
    }
    if ($("bMbSaveAsConfirm")) $("bMbSaveAsConfirm").addEventListener("click", submitSaveAs);
    if ($("mbSaveAsName")) {
      $("mbSaveAsName").addEventListener("keydown", (e) => {
        if (e.key === "Enter") submitSaveAs();
      });
    }
    if ($("mbGotoFilter")) {
      $("mbGotoFilter").addEventListener("input", () => renderGotoStepList($("mbGotoFilter").value));
      $("mbGotoFilter").addEventListener("keydown", (e) => {
        if (e.key === "Enter") {
          const first = $("mbGotoList")?.querySelector("button");
          if (first) first.click();
        }
      });
    }
    if ($("mbManualSearch")) {
      $("mbManualSearch").addEventListener("input", () => renderManual(manualMarkdownCache, $("mbManualSearch").value));
    }
    if ($("bMbManualNewTab")) {
      $("bMbManualNewTab").addEventListener("click", () => {
        window.open("/manual", "_blank", "noopener");
      });
    }

    // Keep active project badge synced when user changes #proj directly
    const selProj = $("proj");
    if (selProj) {
      selProj.addEventListener("change", () => {
        if (!activeProjectMeta || activeProjectMeta.slug !== selProj.value) {
          activeProjectMeta = null;
        }
        updateProjectBadge();
      });
      setTimeout(() => updateProjectBadge(), 800);
    }

    // Global standard keyboard shortcuts
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") {
        closeAllMenus();
        ["mbNewProjectModal", "mbOpenProjectModal", "mbSaveAsModal", "mbGotoStepModal", "mbManualModal", "mbAboutModal"].forEach(closeModal);
        return;
      }
      if (e.key === "F1") {
        e.preventDefault();
        openManualDialog();
        return;
      }
      const mod = e.ctrlKey || e.metaKey;
      if (!mod || e.altKey) return;
      const k = String(e.key || "").toLowerCase();

      if (k === "n" && !e.shiftKey) {
        e.preventDefault();
        openNewProjectDialog();
      } else if (k === "o" && !e.shiftKey) {
        e.preventDefault();
        openOpenProjectDialog();
      } else if (k === "s" && e.shiftKey) {
        e.preventDefault();
        openSaveAsDialog();
      } else if (k === "s" && !e.shiftKey) {
        e.preventDefault();
        saveActiveProject();
      } else if (k === "q" && !e.shiftKey) {
        e.preventDefault();
        exitStudio();
      } else if (k === "g" && !e.shiftKey) {
        e.preventDefault();
        openGotoStepDialog();
      } else if (k === "1" && !e.shiftKey) {
        e.preventDefault();
        switchToPipeline();
      } else if (k === "z" && !e.shiftKey && !isEditableFocus()) {
        e.preventDefault();
        doUndo(false);
      } else if ((k === "y" || (k === "z" && e.shiftKey)) && !isEditableFocus()) {
        e.preventDefault();
        doRedo(false);
      }
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bindMenubar);
  } else {
    bindMenubar();
  }
})();
