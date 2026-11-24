// studio/providers.js - the "Paid, external" list on the Models tab (server: /api/providers, data in studio_app/providers.json).
// Classic script: uses api() from core.js. Gated behind STUDIO_LEGACY_CLOUD=1.
(function () {
  const list = document.getElementById("paidProviders");
  if (!list) return;
  const el = (tag, text, cls) => { const e = document.createElement(tag); if (text) e.textContent = text; if (cls) e.className = cls; return e; };

  function syncLegacyCloudDom(legacyOn) {
    const grp = list.closest(".svc-group");
    if (grp) grp.classList.toggle("hidden", !legacyOn);
    list.classList.toggle("hidden", !legacyOn);
    document.querySelectorAll('input[name="svc"]').forEach(inp => {
      const isCloud = inp.value === "kaggle" || inp.value === "colab" || inp.value === "huggingface";
      if (!isCloud) return;
      const sgrp = inp.closest(".svc-group");
      if (sgrp) sgrp.classList.toggle("hidden", !legacyOn);
      const lbl = inp.closest("label");
      if (lbl) lbl.classList.toggle("hidden", !legacyOn);
    });
  }

  api("/api/providers").then(d => {
    const legacyOn = Boolean(d && d.legacy_cloud);
    syncLegacyCloudDom(legacyOn);
    list.textContent = "";
    if (!legacyOn) return;
    for (const p of d.paid || []) {
      const li = el("li", "", "paid-item");
      const head = el("span", "", "paid-item__head");
      const a = el("a", p.name); a.href = p.url; a.target = "_blank"; a.rel = "noopener noreferrer";
      head.append(a, el("span", "unproven", "badge badge--unproven"));
      li.append(head, el("small", p.kind ? p.kind + ". " + p.note : p.note));
      list.append(li);
    }
  }).catch(e => { list.textContent = ""; list.append(el("li", "Could not load the provider list: " + (e.message || e))); });
})();
