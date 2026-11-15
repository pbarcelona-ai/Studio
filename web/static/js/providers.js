// studio/providers.js - the "Paid, external" list on the Models tab (server: /api/providers, data in studio_app/providers.json).
// Classic script: uses api() from core.js. The paid providers are a research list; none is connected, so none can be chosen.
(function () {
  const list = document.getElementById("paidProviders");
  if (!list) return;
  const el = (tag, text, cls) => { const e = document.createElement(tag); if (text) e.textContent = text; if (cls) e.className = cls; return e; };
  api("/api/providers").then(d => {
    list.textContent = "";
    for (const p of d.paid) {
      const li = el("li", "", "paid-item");
      const head = el("span", "", "paid-item__head");
      const a = el("a", p.name); a.href = p.url; a.target = "_blank"; a.rel = "noopener noreferrer";
      head.append(a, el("span", "unproven", "badge badge--unproven"));
      li.append(head, el("small", p.kind ? p.kind + ". " + p.note : p.note));
      list.append(li);
    }
  }).catch(e => { list.textContent = ""; list.append(el("li", "Could not load the provider list: " + (e.message || e))); });
})();
