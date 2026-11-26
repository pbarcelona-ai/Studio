// studio/apps_gallery.js - Declarative ComfyUI Apps gallery (120 apps) rendered as a responsive tile grid
// with live category/pack/search filters, interactive modal runner, workflow JSON inspector, and Send to Shot.
(function (w, d) {
  "use strict";

  let allApps = [];
  let activeSection = "all";
  let activePack = "all";
  let compatibleOnly = false;
  let searchQuery = "";
  let selectedAppId = "";
  let currentHost = null;
  let escBound = false;

  const SECTION_ICONS = {
    image: "🖼️",
    video: "🎬",
    audio: "🔊",
    utility: "🛠️",
    edit: "✏️",
    vfx: "✨",
    camera: "🎥",
    character: "🧑",
    style: "🎨",
    upscale: "🔍",
  };

  async function fetchJson(url, body, host) {
    const doc = (host && host.ownerDocument) || d;
    const win = (doc && doc.defaultView) || w;
    const token = ((doc && doc.querySelector('meta[name="studio-token"]')) || {}).content || "";
    const headers = { "Content-Type": "application/json" };
    if (token && token !== "__TOKEN__") headers["X-Studio-Token"] = token;
    const fetchFn = (win && win.fetch) ? win.fetch.bind(win) : fetch;
    const r = await fetchFn(url, body ? { method: "POST", headers, body: JSON.stringify(body) } : { method: "GET", headers });
    const j = await r.json().catch(() => ({}));
    return { ok: r.ok, status: r.status, data: j };
  }

  function closeModal(detailBox) {
    const box = detailBox || (currentHost && currentHost.querySelector(".apps-detail"));
    if (!box) return;
    box.classList.remove("is-open");
    box.setAttribute("aria-hidden", "true");
    selectedAppId = "";
    if (currentHost) {
      currentHost.querySelectorAll(".app-card.is-selected").forEach(el => el.classList.remove("is-selected"));
    }
  }

  function renderGalleryDom(host) {
    if (!host) return;
    const doc = host.ownerDocument || document;
    host.textContent = "";
    activeSection = "all";
    activePack = "all";
    compatibleOnly = false;
    searchQuery = "";
    selectedAppId = "";

    const bar = doc.createElement("div");
    bar.className = "apps-toolbar";

    const row1 = doc.createElement("div");
    row1.className = "apps-toolbar-row";

    const search = doc.createElement("input");
    search.type = "search";
    search.id = "appsSearch";
    search.placeholder = "Search 120 ComfyUI apps by name, effect, or pack…";
    search.value = searchQuery;
    row1.appendChild(search);

    const packs = [...new Set(allApps.map(a => String(a.pack || "core")).filter(Boolean))].sort();
    const packSel = doc.createElement("select");
    packSel.id = "appsPackFilter";
    packSel.style.cssText = "padding:7px 10px;background:#0a0d14;color:#f8fafc;border:1px solid #334155;border-radius:8px;font-size:12px;";
    const optAllPack = doc.createElement("option");
    optAllPack.value = "all";
    optAllPack.textContent = `All Packs (${packs.length})`;
    packSel.appendChild(optAllPack);
    packs.forEach(p => {
      const o = doc.createElement("option");
      o.value = p;
      o.textContent = p;
      packSel.appendChild(o);
    });
    packSel.addEventListener("change", () => {
      activePack = packSel.value;
      renderCards();
    });
    row1.appendChild(packSel);

    const compatLbl = doc.createElement("label");
    compatLbl.style.cssText = "display:inline-flex;align-items:center;gap:6px;font-size:12px;color:#cbd5e1;cursor:pointer;user-select:none;";
    const compatChk = doc.createElement("input");
    compatChk.type = "checkbox";
    compatChk.checked = compatibleOnly;
    compatChk.addEventListener("change", () => {
      compatibleOnly = compatChk.checked;
      renderCards();
    });
    compatLbl.appendChild(compatChk);
    compatLbl.appendChild(doc.createTextNode("Compatible with my GPU only"));
    row1.appendChild(compatLbl);

    const countPill = doc.createElement("span");
    countPill.className = "apps-count-pill";
    row1.appendChild(countPill);
    bar.appendChild(row1);

    // Dynamic category pills built from real sections present in allApps
    const secCounts = new Map();
    allApps.forEach(a => {
      const s = String(a.section || "utility").toLowerCase();
      secCounts.set(s, (secCounts.get(s) || 0) + 1);
    });
    const orderedSecs = ["all", ...["image", "video", "audio", "utility"].filter(s => secCounts.has(s)), ...[...secCounts.keys()].filter(s => !["image", "video", "audio", "utility"].includes(s))];

    const secBar = doc.createElement("div");
    secBar.className = "apps-sections";
    const secButtons = new Map();
    orderedSecs.forEach(sec => {
      const b = doc.createElement("button");
      b.type = "button";
      b.dataset.section = sec;
      const cnt = sec === "all" ? allApps.length : (secCounts.get(sec) || 0);
      const icon = sec === "all" ? "🧩" : (SECTION_ICONS[sec] || "⚙️");
      b.textContent = `${icon} ${sec.toUpperCase()} (${cnt})`;
      b.addEventListener("click", () => {
        activeSection = sec;
        updateSectionButtons();
        renderCards();
      });
      secButtons.set(sec, b);
      secBar.appendChild(b);
    });
    bar.appendChild(secBar);

    function updateSectionButtons() {
      secButtons.forEach((btn, sec) => {
        btn.className = "btn " + (activeSection === sec ? "btn--primary" : "btn--ghost");
        btn.setAttribute("aria-pressed", String(activeSection === sec));
      });
    }
    updateSectionButtons();

    const grid = doc.createElement("div");
    grid.className = "apps-grid";

    const detail = doc.createElement("div");
    detail.className = "apps-detail";
    detail.setAttribute("role", "dialog");
    detail.setAttribute("aria-modal", "true");
    detail.setAttribute("aria-hidden", "true");
    detail.addEventListener("click", (ev) => {
      if (ev.target === detail) closeModal(detail);
    });

    if (!escBound && doc && doc.addEventListener) {
      escBound = true;
      doc.addEventListener("keydown", (ev) => {
        if (ev.key === "Escape") closeModal();
      });
    }

    host.appendChild(bar);
    host.appendChild(grid);
    host.appendChild(detail);

    function renderCards() {
      grid.textContent = "";
      const q = searchQuery.trim().toLowerCase();
      const filtered = allApps.filter(a => {
        if (activeSection !== "all" && String(a.section || "").toLowerCase() !== activeSection) return false;
        if (activePack !== "all" && String(a.pack || "core") !== activePack) return false;
        if (compatibleOnly && !a.compatible) return false;
        if (!q) return true;
        const hay = `${a.id || ""} ${a.name || ""} ${a.summary || ""} ${a.description || ""} ${a.pack || ""} ${a.section || ""}`.toLowerCase();
        return hay.includes(q);
      });

      countPill.textContent = `Showing ${filtered.length} of ${allApps.length} apps`;

      if (!filtered.length) {
        const empty = doc.createElement("p");
        empty.className = "warn";
        empty.style.gridColumn = "1 / -1";
        empty.textContent = "No apps match your search (0 match). Try clearing the search or switching category.";
        grid.appendChild(empty);
        return;
      }

      filtered.forEach(app => {
        const aid = String(app.id || "");
        const sec = String(app.section || "utility").toLowerCase();
        const card = doc.createElement("div");
        card.className = "deliverable-card app-card" + (selectedAppId === aid ? " is-selected" : "");
        card.dataset.appId = aid;
        card.tabIndex = 0;
        card.setAttribute("role", "button");
        card.setAttribute("aria-label", `Open ${app.name || aid}`);

        const top = doc.createElement("div");
        top.className = "app-card__top";
        const catPill = doc.createElement("span");
        catPill.className = "app-card__cat";
        catPill.dataset.sec = sec;
        catPill.textContent = `${SECTION_ICONS[sec] || "⚙️"} ${sec}`;
        const badge = doc.createElement("span");
        badge.className = "status-badge " + (app.compatible ? "status-badge--synced" : "status-badge--drift");
        badge.style.fontSize = "10px";
        badge.textContent = app.compatible ? "✓ Ready" : `${app.min_vram_gb || 0} GB VRAM`;
        top.appendChild(catPill);
        top.appendChild(badge);

        const title = doc.createElement("strong");
        title.className = "deliverable-title";
        title.textContent = String(app.name || aid);

        const desc = doc.createElement("p");
        desc.className = "deliverable-desc";
        desc.textContent = String(app.summary || app.description || "Declarative ComfyUI local workflow.");

        const meta = doc.createElement("div");
        meta.className = "app-card__meta";
        meta.title = `${aid} · pack: ${app.pack || "core"}`;
        meta.textContent = `${aid} · ${app.pack || "core"}`;

        const foot = doc.createElement("div");
        foot.className = "app-card__foot";
        const vramTag = doc.createElement("span");
        vramTag.style.cssText = "font-size:11px;color:#94a3b8;";
        vramTag.textContent = app.min_vram_gb ? `${app.min_vram_gb} GB VRAM` : "Local GPU";

        const openBtn = doc.createElement("button");
        openBtn.type = "button";
        openBtn.className = "btn btn--primary";
        openBtn.dataset.appId = aid;
        openBtn.textContent = "Open ➔";
        openBtn.addEventListener("click", (ev) => {
          ev.stopPropagation();
          openAppDetail(aid, detail);
        });
        foot.appendChild(vramTag);
        foot.appendChild(openBtn);

        card.appendChild(top);
        card.appendChild(title);
        card.appendChild(desc);
        card.appendChild(meta);
        card.appendChild(foot);

        card.addEventListener("click", () => openAppDetail(aid, detail));
        card.addEventListener("keydown", (ev) => {
          if (ev.key === "Enter" || ev.key === " ") {
            ev.preventDefault();
            openAppDetail(aid, detail);
          }
        });
        grid.appendChild(card);
      });
    }

    search.addEventListener("input", () => {
      searchQuery = search.value;
      renderCards();
    });

    renderCards();
  }

  async function loadCastRefsForModal(host) {
    const doc = (host && host.ownerDocument) || d;
    const projEl = doc && doc.getElementById("proj");
    const slug = (projEl && projEl.value) ? projEl.value.trim() : "";
    if (!slug) return [];
    try {
      const res = await fetchJson(`/api/v2_cast_references?project=${encodeURIComponent(slug)}`, undefined, host);
      return (res.ok && res.data && Array.isArray(res.data.references)) ? res.data.references : [];
    } catch (_e) {
      return [];
    }
  }

  async function openAppDetail(appId, detailBox) {
    const target = detailBox || (currentHost && currentHost.querySelector(".apps-detail")) || currentHost;
    if (!target) return null;
    const doc = target.ownerDocument || document;
    selectedAppId = String(appId || "");

    if (currentHost) {
      currentHost.querySelectorAll(".app-card").forEach(el => {
        el.classList.toggle("is-selected", el.dataset.appId === selectedAppId);
      });
    }

    // Open modal immediately with loading state so clicks ALWAYS give instant feedback
    target.textContent = "";
    target.classList.add("is-open");
    target.setAttribute("aria-hidden", "false");

    const modal = doc.createElement("div");
    modal.className = "apps-modal";
    modal.innerHTML = `<div class="apps-modal__hdr"><div><h3>Loading ${appId}…</h3></div></div>`;
    target.appendChild(modal);

    const [res, castRefs] = await Promise.all([
      fetchJson(`/api/apps/${encodeURIComponent(appId)}`, undefined, target),
      loadCastRefsForModal(target),
    ]);

    modal.textContent = "";

    const hdr = doc.createElement("div");
    hdr.className = "apps-modal__hdr";
    const hdrLeft = doc.createElement("div");
    const closeBtn = doc.createElement("button");
    closeBtn.type = "button";
    closeBtn.className = "btn btn--ghost";
    closeBtn.style.cssText = "padding:4px 10px;font-size:14px;flex-shrink:0;";
    closeBtn.textContent = "✕ Close";
    closeBtn.addEventListener("click", () => closeModal(target));

    if (!res.ok) {
      const hErr = doc.createElement("h3");
      hErr.textContent = `Could not load "${appId}"`;
      hdrLeft.appendChild(hErr);
      hdr.appendChild(hdrLeft);
      hdr.appendChild(closeBtn);
      modal.appendChild(hdr);
      const err = doc.createElement("p");
      err.className = "err";
      err.textContent = String((res.data && res.data.error) || `App ${appId} not found`);
      modal.appendChild(err);
      return null;
    }

    const app = res.data;
    const sec = String(app.section || "utility").toLowerCase();
    const h = doc.createElement("h3");
    h.textContent = `${SECTION_ICONS[sec] || "🧩"} ${app.name || appId}`;
    hdrLeft.appendChild(h);

    const sub = doc.createElement("div");
    sub.style.cssText = "font-size:12px;color:#94a3b8;margin-top:4px;";
    sub.textContent = `${appId} · ${sec.toUpperCase()} · pack: ${app.pack || "core"} · ${app.min_vram_gb || 0} GB VRAM · ${app.compatible ? "✓ Compatible with your GPU" : "⚠ Exceeds detected VRAM"}`;
    hdrLeft.appendChild(sub);

    if (app.summary || app.description) {
      const descP = doc.createElement("p");
      descP.style.cssText = "margin:6px 0 0;font-size:13px;color:#cbd5e1;line-height:1.45;";
      descP.textContent = String(app.summary || app.description);
      hdrLeft.appendChild(descP);
    }

    hdr.appendChild(hdrLeft);
    hdr.appendChild(closeBtn);
    modal.appendChild(hdr);

    // Dynamic input form generated from app.inputs
    const inputGetters = [];
    const formGrid = doc.createElement("div");
    formGrid.className = "apps-modal__form";

    (app.inputs || []).forEach(inp => {
      const iid = String(inp.id || "");
      const itype = String(inp.type || "text").toLowerCase();
      const field = doc.createElement("div");
      field.className = "apps-modal__field" + ((itype === "textarea" || itype === "image" || itype === "video" || itype === "audio") ? " full" : "");

      const lbl = doc.createElement("label");
      lbl.className = "f";
      lbl.textContent = (inp.label || iid) + (inp.required ? " *" : "");
      field.appendChild(lbl);

      if (itype === "textarea") {
        const ta = doc.createElement("textarea");
        ta.rows = 3;
        ta.value = inp.default !== undefined ? String(inp.default) : "";
        ta.placeholder = inp.help || `Enter ${inp.label || iid}…`;
        field.appendChild(ta);
        inputGetters.push(() => [iid, ta.value]);
      } else if (itype === "select") {
        const sel = doc.createElement("select");
        const isMulti = Boolean(inp.multiple);
        if (isMulti) {
          sel.multiple = true;
          sel.size = Math.min(5, (inp.options || []).length || 3);
        }
        const defArr = Array.isArray(inp.default) ? inp.default.map(String) : [String(inp.default ?? "")];
        (inp.options || []).forEach(opt => {
          const o = doc.createElement("option");
          const val = (opt && typeof opt === "object") ? String(opt.value ?? "") : String(opt);
          const text = (opt && typeof opt === "object") ? String(opt.label ?? opt.value ?? "") : String(opt);
          o.value = val;
          o.textContent = text;
          if (defArr.includes(val)) o.selected = true;
          sel.appendChild(o);
        });
        field.appendChild(sel);
        inputGetters.push(() => {
          if (isMulti) return [iid, [...sel.selectedOptions].map(o => o.value)];
          return [iid, sel.value];
        });
      } else if (itype === "slider") {
        const row = doc.createElement("div");
        row.style.cssText = "display:flex;align-items:center;gap:8px;";
        const rng = doc.createElement("input");
        rng.type = "range";
        if (inp.min !== undefined) rng.min = String(inp.min);
        if (inp.max !== undefined) rng.max = String(inp.max);
        if (inp.step !== undefined) rng.step = String(inp.step);
        rng.value = String(inp.default ?? inp.min ?? 0);
        rng.style.flex = "1";
        const numIn = doc.createElement("input");
        numIn.type = "number";
        if (inp.min !== undefined) numIn.min = String(inp.min);
        if (inp.max !== undefined) numIn.max = String(inp.max);
        if (inp.step !== undefined) numIn.step = String(inp.step);
        numIn.value = rng.value;
        numIn.style.width = "82px";
        rng.addEventListener("input", () => { numIn.value = rng.value; });
        numIn.addEventListener("input", () => { rng.value = numIn.value; });
        row.appendChild(rng);
        row.appendChild(numIn);
        field.appendChild(row);
        inputGetters.push(() => [iid, Number(numIn.value)]);
      } else if (itype === "seed") {
        const row = doc.createElement("div");
        row.style.cssText = "display:flex;gap:6px;";
        const numIn = doc.createElement("input");
        numIn.type = "number";
        numIn.value = String(inp.default ?? -1);
        numIn.style.flex = "1";
        const rndBtn = doc.createElement("button");
        rndBtn.type = "button";
        rndBtn.className = "btn btn--ghost";
        rndBtn.style.cssText = "padding:4px 8px;font-size:11px;";
        rndBtn.textContent = "🎲 Random";
        rndBtn.addEventListener("click", () => { numIn.value = "-1"; });
        row.appendChild(numIn);
        row.appendChild(rndBtn);
        field.appendChild(row);
        inputGetters.push(() => [iid, parseInt(numIn.value, 10) || -1]);
      } else if (itype === "number") {
        const numIn = doc.createElement("input");
        numIn.type = "number";
        if (inp.min !== undefined) numIn.min = String(inp.min);
        if (inp.max !== undefined) numIn.max = String(inp.max);
        if (inp.step !== undefined) numIn.step = String(inp.step);
        numIn.value = String(inp.default ?? 0);
        field.appendChild(numIn);
        inputGetters.push(() => [iid, Number(numIn.value)]);
      } else if (itype === "toggle") {
        const wrap = doc.createElement("label");
        wrap.style.cssText = "display:inline-flex;align-items:center;gap:8px;font-size:12px;color:#e2e8f0;cursor:pointer;";
        const chk = doc.createElement("input");
        chk.type = "checkbox";
        chk.checked = Boolean(inp.default);
        wrap.appendChild(chk);
        wrap.appendChild(doc.createTextNode(inp.help || "Enabled"));
        field.appendChild(wrap);
        inputGetters.push(() => [iid, chk.checked]);
      } else if (itype === "image" || itype === "video" || itype === "audio") {
        let uploadedDataUrl = "";
        const row = doc.createElement("div");
        row.style.cssText = "display:flex;flex-wrap:wrap;align-items:center;gap:8px;";

        const fileIn = doc.createElement("input");
        fileIn.type = "file";
        fileIn.accept = itype === "image" ? "image/*" : (itype === "video" ? "video/*" : "audio/*");
        fileIn.style.display = "none";

        const upBtn = doc.createElement("button");
        upBtn.type = "button";
        upBtn.className = "btn btn--secondary";
        upBtn.style.cssText = "padding:5px 10px;font-size:11px;";
        upBtn.textContent = itype === "image" ? "📷 Upload Image" : `📁 Upload ${itype}`;
        upBtn.addEventListener("click", () => fileIn.click());
        row.appendChild(upBtn);
        row.appendChild(fileIn);

        let castSel = null;
        if (itype === "image" && castRefs.length) {
          castSel = doc.createElement("select");
          castSel.style.cssText = "flex:1;min-width:180px;";
          const o0 = doc.createElement("option");
          o0.value = "";
          o0.textContent = "Or pick a Cast Member Reference…";
          castSel.appendChild(o0);
          castRefs.forEach(ref => {
            const o = doc.createElement("option");
            o.value = ref.rel_path;
            o.dataset.url = ref.url;
            o.textContent = ref.label || ref.character;
            castSel.appendChild(o);
          });
          row.appendChild(castSel);
        }

        const pathIn = doc.createElement("input");
        pathIn.type = "text";
        pathIn.placeholder = `Or enter local ${itype} path…`;
        pathIn.style.cssText = "flex:1;min-width:180px;";
        row.appendChild(pathIn);

        const preview = doc.createElement("img");
        preview.style.cssText = "display:none;width:54px;height:54px;object-fit:cover;border-radius:6px;border:1px solid #f59e0b;";
        row.appendChild(preview);

        const fileNote = doc.createElement("span");
        fileNote.style.cssText = "font-size:11px;color:#94a3b8;";
        row.appendChild(fileNote);

        fileIn.addEventListener("change", () => {
          const f = fileIn.files && fileIn.files[0];
          if (!f) return;
          const reader = new FileReader();
          reader.onload = () => {
            uploadedDataUrl = String(reader.result || "");
            if (castSel) castSel.value = "";
            pathIn.value = "";
            fileNote.textContent = `✓ ${f.name}`;
            if (itype === "image") {
              preview.src = uploadedDataUrl;
              preview.style.display = "block";
            }
          };
          reader.readAsDataURL(f);
        });
        if (castSel) {
          castSel.addEventListener("change", () => {
            if (castSel.value) {
              uploadedDataUrl = "";
              pathIn.value = castSel.value;
              const opt = castSel.selectedOptions[0];
              fileNote.textContent = `✓ ${opt ? opt.textContent : castSel.value}`;
              if (opt && opt.dataset.url) {
                preview.src = opt.dataset.url;
                preview.style.display = "block";
              }
            }
          });
        }

        field.appendChild(row);
        inputGetters.push(() => [iid, uploadedDataUrl || pathIn.value.trim()]);
      } else {
        const txt = doc.createElement("input");
        txt.type = "text";
        txt.value = inp.default !== undefined ? String(inp.default) : "";
        field.appendChild(txt);
        inputGetters.push(() => [iid, txt.value]);
      }

      if (inp.help && itype !== "toggle") {
        const hlp = doc.createElement("small");
        hlp.style.cssText = "font-size:10px;color:#64748b;";
        hlp.textContent = String(inp.help);
        field.appendChild(hlp);
      }
      formGrid.appendChild(field);
    });

    if ((app.inputs || []).length) {
      modal.appendChild(formGrid);
    }

    // Actions row
    const actions = doc.createElement("div");
    actions.style.cssText = "display:flex;flex-wrap:wrap;align-items:center;gap:8px;padding-top:8px;border-top:1px solid #232d3f;";

    const runBtn = doc.createElement("button");
    runBtn.type = "button";
    runBtn.className = "btn btn--primary";
    runBtn.textContent = "▶ Run App Locally";

    const inspectBtn = doc.createElement("button");
    inspectBtn.type = "button";
    inspectBtn.className = "btn btn--secondary";
    inspectBtn.textContent = "🔍 Inspect Workflow JSON";

    const sendShotIn = doc.createElement("input");
    sendShotIn.type = "number";
    sendShotIn.min = "1";
    sendShotIn.value = "1";
    sendShotIn.title = "Target Shot #";
    sendShotIn.style.cssText = "width:64px;padding:5px 7px;background:#0a0d14;color:#f8fafc;border:1px solid #334155;border-radius:6px;font-size:12px;";

    const sendBtn = doc.createElement("button");
    sendBtn.type = "button";
    sendBtn.className = "btn btn--secondary";
    sendBtn.textContent = "📤 Send to Shot #";

    const statusSpan = doc.createElement("span");
    statusSpan.style.cssText = "font-size:12px;color:#94a3b8;margin-left:auto;";
    statusSpan.setAttribute("aria-live", "polite");

    actions.appendChild(runBtn);
    actions.appendChild(inspectBtn);
    actions.appendChild(sendBtn);
    actions.appendChild(sendShotIn);
    actions.appendChild(statusSpan);
    modal.appendChild(actions);

    const mediaPreview = doc.createElement("div");
    mediaPreview.style.cssText = "display:none;gap:10px;flex-wrap:wrap;";
    modal.appendChild(mediaPreview);

    const outMsg = doc.createElement("pre");
    outMsg.className = "apps-modal__out";
    outMsg.style.display = "none";
    modal.appendChild(outMsg);

    let lastOutputSource = "";

    inspectBtn.addEventListener("click", async () => {
      statusSpan.textContent = "Loading workflow JSON…";
      const wf = await fetchJson(`/api/apps/${encodeURIComponent(appId)}/workflow`, undefined, target);
      outMsg.style.display = "block";
      outMsg.textContent = JSON.stringify(wf.data, null, 2);
      statusSpan.textContent = wf.ok ? `✓ Workflow loaded (${Object.keys(wf.data || {}).length} nodes)` : "✗ Could not load workflow";
    });

    runBtn.addEventListener("click", async () => {
      const inputs = {};
      inputGetters.forEach(fn => {
        const [k, v] = fn();
        if (v !== "" && v !== undefined && v !== null) inputs[k] = v;
      });
      runBtn.disabled = true;
      const started = Date.now();
      const tick = () => {
        statusSpan.textContent = `⏳ Running ${app.name || appId} on local ComfyUI… (${Math.floor((Date.now() - started) / 1000)}s)`;
      };
      tick();
      const timer = setInterval(tick, 1000);
      try {
        const r = await fetchJson(`/api/apps/${encodeURIComponent(appId)}/run`, { inputs }, target);
        clearInterval(timer);
        outMsg.style.display = "block";
        outMsg.textContent = JSON.stringify(r.data, null, 2);
        if (r.ok) {
          const elapsed = ((Date.now() - started) / 1000).toFixed(1);
          statusSpan.textContent = `✓ Completed in ${elapsed}s`;
          if (r.data && r.data.output_path) lastOutputSource = String(r.data.output_path);
          else if (r.data && Array.isArray(r.data.outputs) && r.data.outputs[0]) {
            lastOutputSource = String(r.data.outputs[0].path || r.data.outputs[0]);
          }
        } else {
          statusSpan.textContent = `✗ ${(r.data && r.data.error) || "Run failed"}`;
        }
      } catch (err) {
        clearInterval(timer);
        statusSpan.textContent = `✗ ${err.message || err}`;
      } finally {
        runBtn.disabled = false;
      }
    });

    sendBtn.addEventListener("click", async () => {
      const proj = (doc.getElementById("proj") && doc.getElementById("proj").value) || "demo";
      const shotNum = Math.max(1, parseInt(sendShotIn.value, 10) || 1);
      const source = lastOutputSource || `my_downloads/${appId}/out.png`;
      statusSpan.textContent = `Sending to ${proj} Shot #${shotNum}…`;
      const r = await fetchJson(`/api/apps/${encodeURIComponent(appId)}/send-to-shot`, {
        project: proj,
        shot: shotNum,
        kind: sec === "video" ? "video" : "keyframe",
        model: "flux3",
        source,
      }, target);
      outMsg.style.display = "block";
      outMsg.textContent = JSON.stringify(r.data, null, 2);
      statusSpan.textContent = r.ok ? `✓ Sent to ${proj} Shot #${shotNum}` : `✗ ${(r.data && r.data.error) || "Send failed"}`;
    });

    return app;
  }

  async function initAppsGallery(container) {
    currentHost = container || (d && d.getElementById("appsGalleryHost"));
    if (!currentHost) return;
    currentHost.textContent = "Loading 120 ComfyUI Apps…";
    try {
      const res = await fetchJson("/api/apps", undefined, currentHost);
      allApps = Array.isArray(res.data && res.data.apps) ? res.data.apps : [];
    } catch (_e) {
      allApps = [];
    }
    renderGalleryDom(currentHost);
  }

  w.initAppsGallery = initAppsGallery;
  w.AppsGallery = {
    render: initAppsGallery,
    open: (appId) => openAppDetail(appId),
    close: () => closeModal(),
  };

  // Auto-mount if the Apps workspace panel is already open on initial page load (e.g. #apps hash)
  if (d && d.getElementById) {
    const panel = d.getElementById("panel-apps");
    const host = d.getElementById("appsGalleryHost");
    if (panel && host && panel.classList.contains("active") && !host.children.length) {
      initAppsGallery(host);
    }
  }
})(typeof window !== "undefined" ? window : this, typeof document !== "undefined" ? document : (this && this.document));
