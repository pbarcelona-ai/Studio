// studio/apps_gallery.js - Declarative ComfyUI Apps gallery (120 apps), hardware compatibility badges, workflow inspector, runner, and Send to Shot.
(function (w, d) {
  "use strict";

  let allApps = [];
  let activeSection = "all";
  let searchQuery = "";
  let currentHost = null;

  async function fetchJson(url, body, host) {
    const doc = (host && host.ownerDocument) || d;
    const win = (doc && doc.defaultView) || w;
    const token = (doc && doc.querySelector('meta[name="studio-token"]') || {}).content || "";
    const headers = { "Content-Type": "application/json" };
    if (token && token !== "__TOKEN__") headers["X-Studio-Token"] = token;
    const fetchFn = (win && win.fetch) ? win.fetch.bind(win) : fetch;
    const r = await fetchFn(url, body ? { method: "POST", headers, body: JSON.stringify(body) } : { method: "GET", headers });
    const j = await r.json().catch(() => ({}));
    return { ok: r.ok, status: r.status, data: j };
  }

  function renderGalleryDom(host) {
    if (!host) return;
    const d = host.ownerDocument || document;
    host.textContent = "";
    activeSection = "all";
    searchQuery = "";

    const bar = d.createElement("div");
    bar.className = "apps-toolbar";

    const search = d.createElement("input");
    search.type = "search";
    search.id = "appsSearch";
    search.placeholder = "Search apps...";
    search.value = searchQuery;
    bar.appendChild(search);

    const sections = ["all", "image", "video", "edit", "vfx", "camera", "character", "style", "upscale", "audio", "utility"];
    const secBar = d.createElement("div");
    secBar.className = "apps-sections";
    sections.forEach(sec => {
      const b = d.createElement("button");
      b.type = "button";
      b.className = "btn " + (activeSection === sec ? "btn--primary" : "btn--ghost");
      b.textContent = sec.toUpperCase();
      b.addEventListener("click", () => {
        activeSection = sec;
        renderCards();
      });
      secBar.appendChild(b);
    });
    bar.appendChild(secBar);

    const grid = d.createElement("div");
    grid.className = "apps-grid";

    const detail = d.createElement("div");
    detail.className = "apps-detail";

    host.appendChild(bar);
    host.appendChild(grid);
    host.appendChild(detail);

    function renderCards() {
      grid.textContent = "";
      const q = searchQuery.trim().toLowerCase();
      const filtered = allApps.filter(a => {
        if (activeSection !== "all" && String(a.section || "").toLowerCase() !== activeSection) return false;
        if (!q) return true;
        const hay = `${a.id || ""} ${a.name || ""} ${a.summary || ""} ${a.description || ""} ${a.pack || ""}`.toLowerCase();
        return hay.includes(q);
      });

      if (!filtered.length) {
        const empty = d.createElement("p");
        empty.className = "warn";
        empty.textContent = "No apps match your search (0 match).";
        grid.appendChild(empty);
        return;
      }

      filtered.forEach(app => {
        const card = d.createElement("div");
        card.className = "deliverable-card app-card";
        card.dataset.appId = String(app.id || "");

        const title = d.createElement("strong");
        title.className = "deliverable-title";
        title.textContent = String(app.name || app.id || "");

        const meta = d.createElement("small");
        meta.className = "warn";
        meta.textContent = `${app.id} · ${app.section || "utility"} · pack: ${app.pack || "core"} · ${app.min_vram_gb ?? 0} GB VRAM`;

        const desc = d.createElement("p");
        desc.className = "deliverable-desc";
        desc.textContent = String(app.summary || app.description || "");

        const badge = d.createElement("span");
        badge.className = "status-badge " + (app.compatible ? "status-badge--synced" : "status-badge--drift");
        badge.textContent = app.compatible ? "Compatible" : `Requires ${app.min_vram_gb || 0} GB VRAM`;

        const openBtn = d.createElement("button");
        openBtn.type = "button";
        openBtn.className = "btn btn--secondary";
        openBtn.dataset.appId = String(app.id || "");
        openBtn.textContent = `Open ${app.id}`;
        openBtn.addEventListener("click", () => openAppDetail(String(app.id), detail));

        card.appendChild(title);
        card.appendChild(meta);
        card.appendChild(desc);
        card.appendChild(badge);
        card.appendChild(openBtn);
        card.addEventListener("click", (ev) => {
          if (ev.target !== openBtn) openAppDetail(String(app.id), detail);
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

  async function openAppDetail(appId, detailBox) {
    const target = detailBox || (currentHost && currentHost.querySelector(".apps-detail")) || currentHost;
    if (!target) return null;
    const d = target.ownerDocument || document;
    target.textContent = "";

    const res = await fetchJson(`/api/apps/${encodeURIComponent(appId)}`, undefined, target);
    if (!res.ok) {
      const err = d.createElement("p");
      err.className = "err";
      err.textContent = String((res.data && res.data.error) || `App ${appId} not found`);
      target.appendChild(err);
      return null;
    }

    const app = res.data;
    const h = d.createElement("h3");
    h.textContent = `${app.name || appId} (${appId})`;
    target.appendChild(h);

    const actions = d.createElement("div");
    actions.className = "row";

    const inspectBtn = d.createElement("button");
    inspectBtn.type = "button";
    inspectBtn.className = "btn btn--secondary";
    inspectBtn.textContent = "Inspect Workflow";

    const runBtn = d.createElement("button");
    runBtn.type = "button";
    runBtn.className = "btn btn--primary";
    runBtn.textContent = "Run App";

    const sendBtn = d.createElement("button");
    sendBtn.type = "button";
    sendBtn.className = "btn btn--secondary";
    sendBtn.textContent = "Send to Shot";

    const outMsg = d.createElement("pre");
    outMsg.className = "warn";

    inspectBtn.addEventListener("click", async () => {
      const wf = await fetchJson(`/api/apps/${encodeURIComponent(appId)}/workflow`);
      outMsg.textContent = JSON.stringify(wf.data, null, 2);
    });

    runBtn.addEventListener("click", async () => {
      const inputs = {};
      for (const inp of app.inputs || []) {
        if (inp.default !== undefined) inputs[inp.id] = inp.default;
      }
      const r = await fetchJson(`/api/apps/${encodeURIComponent(appId)}/run`, { inputs });
      outMsg.textContent = JSON.stringify(r.data, null, 2);
    });

    sendBtn.addEventListener("click", async () => {
      const proj = (d.getElementById("proj") && d.getElementById("proj").value) || "demo";
      const r = await fetchJson(`/api/apps/${encodeURIComponent(appId)}/send-to-shot`, {
        project: proj,
        shot: 1,
        kind: "keyframe",
        model: "flux3",
        source: "my_downloads/out.png",
      });
      outMsg.textContent = JSON.stringify(r.data, null, 2);
    });

    actions.appendChild(inspectBtn);
    actions.appendChild(runBtn);
    actions.appendChild(sendBtn);
    target.appendChild(actions);
    target.appendChild(outMsg);
    return app;
  }

  async function initAppsGallery(container) {
    currentHost = container || (d && d.getElementById("appsGalleryHost"));
    if (!currentHost) return;
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
  };
})(typeof window !== "undefined" ? window : this, typeof document !== "undefined" ? document : (this && this.document));
