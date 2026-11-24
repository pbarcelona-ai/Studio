// studio/packs_vram.js - Hugging Face Model Pack downloader, VRAM compatibility map (48 GB vs 8 GB Mac), 2 GB disk headroom guard, and HF token input.
(function (w, d) {
  "use strict";

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

  async function initPacksVram(container) {
    const host = container || (d && d.getElementById("packsVramHost"));
    if (!host) return;
    const doc = host.ownerDocument || d;
    host.textContent = "";

    const res = await fetchJson("/api/packs", undefined, host);
    const payload = res.data || {};
    const freeGb = Number(payload.free_gb ?? 100);
    const profile = payload.gpu_profile || { tier: "full_48g", vram_gb: 48.0, ram_gb: 64.0 };
    const packs = Array.isArray(payload.packs) ? payload.packs : Object.values(payload.packs || {});

    const header = doc.createElement("div");
    header.className = "packs-header direct-story-card";
    const hwInfo = doc.createElement("div");
    hwInfo.textContent = `Hardware Profile: ${profile.tier || "unknown"} · ${profile.vram_gb ?? 0} GB VRAM · ${profile.ram_gb ?? 0} GB RAM · Free Disk: ${freeGb} GB`;
    header.appendChild(hwInfo);

    // HF Token Bar (password-masked, never echoes token)
    const tokBar = doc.createElement("div");
    tokBar.className = "packs-token-bar row";
    const tokInput = doc.createElement("input");
    tokInput.type = "password";
    tokInput.placeholder = "Paste Hugging Face token (hf_...)";
    tokInput.autocomplete = "new-password";
    const saveTokBtn = doc.createElement("button");
    saveTokBtn.type = "button";
    saveTokBtn.className = "btn btn--primary";
    saveTokBtn.textContent = "Save Token";
    const tokStatus = doc.createElement("span");
    tokStatus.className = "warn";
    tokStatus.textContent = (payload.token && (payload.token.ok || payload.token.configured))
      ? `Token configured${payload.token.user ? " (" + payload.token.user + ")" : ""}`
      : "No HF token configured (required for gated packs)";

    saveTokBtn.addEventListener("click", async () => {
      const val = tokInput.value.trim();
      tokInput.value = "";
      if (!val) return;
      const r = await fetchJson("/api/hf/token", { token: val }, host);
      tokStatus.textContent = r.ok ? `Verified HF user: ${(r.data && r.data.user) || "ok"}` : String((r.data && r.data.error) || "Invalid token");
    });

    tokBar.appendChild(tokInput);
    tokBar.appendChild(saveTokBtn);
    tokBar.appendChild(tokStatus);
    header.appendChild(tokBar);
    host.appendChild(header);

    const list = doc.createElement("div");
    list.className = "packs-grid";

    packs.forEach(p => {
      const packId = String(p.pack || p.id || "");
      const dlGb = Number(p.download_gb ?? 0);
      const missingGb = Number(p.missing_gb ?? dlGb);
      const doneGb = Number(p.done_gb ?? (p.installed ? dlGb : 0));
      const minVram = Number(p.min_vram_gb ?? 0);
      const lowDisk = (freeGb - missingGb) < 2.0 && missingGb > 0;
      const vramOk = Number(profile.vram_gb || 0) === 0 || minVram <= Number(profile.vram_gb || 0);
      const pct = dlGb > 0 ? Math.min(100, Math.round((doneGb / dlGb) * 100)) : 100;

      const card = doc.createElement("div");
      card.className = "deliverable-card pack-card";
      card.dataset.packId = packId;

      const title = doc.createElement("strong");
      title.className = "deliverable-title";
      title.textContent = `${p.title || packId} (${packId})`;

      const vramLine = doc.createElement("div");
      vramLine.className = "warn";
      vramLine.textContent = `Requires ${minVram} GB VRAM · ${dlGb} GB download · ${pct}% installed`;

      const statusLine = doc.createElement("div");
      statusLine.className = vramOk ? "ok" : "err";
      statusLine.textContent = vramOk
        ? `Fits current ${profile.vram_gb ?? 48} GB GPU`
        : `Exceeds ${profile.vram_gb ?? 8} GB memory budget (requires ${minVram} GB VRAM)`;

      card.appendChild(title);
      card.appendChild(vramLine);
      card.appendChild(statusLine);

      if (lowDisk) {
        const diskWarn = doc.createElement("div");
        diskWarn.className = "err";
        diskWarn.textContent = `Insufficient disk space: 2 GB disk headroom required (${freeGb} GB free vs ${missingGb} GB needed)`;
        card.appendChild(diskWarn);
      }

      const dlBtn = doc.createElement("button");
      dlBtn.type = "button";
      dlBtn.className = "btn btn--primary";
      dlBtn.textContent = p.installed && p.missing === 0 ? "Installed" : `Download ${packId}`;
      dlBtn.disabled = Boolean(lowDisk || (p.installed && p.missing === 0));
      dlBtn.addEventListener("click", async () => {
        if (dlBtn.disabled) return;
        await fetchJson(`/api/packs/${encodeURIComponent(packId)}/download`, {}, host);
      });

      card.appendChild(dlBtn);
      list.appendChild(card);
    });

    host.appendChild(list);
  }

  w.initPacksVram = initPacksVram;
  w.PacksVram = { render: initPacksVram };
})(typeof window !== "undefined" ? window : this, typeof document !== "undefined" ? document : (this && this.document));
