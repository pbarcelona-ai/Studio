// studio/oldpics.js - "Old pictures" on a storyboard card: every keyframe picture made before (earlier takes, pictures set aside when the
// storyboard was made again, other picture makers), the ones most like this shot first, and "Use this" to put one on the shot.
// Server: /api/old_pictures and /api/assign_picture (studio_app/old_pictures.py). Classic script: uses $, api and TOKEN from core.js.
(function () {
  const dlg = document.createElement("dialog");
  dlg.id = "oldPicDialog"; dlg.className = "oldpics";
  dlg.setAttribute("aria-labelledby", "oldPicTitle");
  dlg.innerHTML = `<div class="oldpics__head"><h2 id="oldPicTitle">Old pictures</h2><button type="button" class="btn btn--ghost" id="oldPicClose">Close</button></div>
    <p class="warn" id="oldPicShot"></p>
    <div class="row" style="gap:8px;align-items:flex-end;flex-wrap:wrap">
      <div><label class="f" for="oldPicKind">Show</label><select id="oldPicKind"><option value="">All old pictures</option><option value="set aside">Set aside when the storyboard was made again</option>
        <option value="earlier take">Earlier takes</option><option value="made by">Made by any picture maker now</option></select></div>
      <div><label class="f" for="oldPicFind">Find words</label><input type="search" id="oldPicFind" placeholder="garden, Eve, night" autocomplete="off"></div>
      <span class="warn" id="oldPicCount" role="status" aria-live="polite"></span>
    </div>
    <div class="oldpics__grid" id="oldPicGrid"></div>`;
  document.body.append(dlg);
  let shot = 0, all = [];
  const closeDlg = () => { if (dlg.close) dlg.close(); else dlg.removeAttribute("open"); };     // (very old browsers have no dialog methods)
  const thumb = p => "/thumb/" + ($("proj").value + "/" + p).split("/").map(encodeURIComponent).join("/") + "?t=" + TOKEN;
  const full = p => "/file/" + ($("proj").value + "/" + p).split("/").map(encodeURIComponent).join("/") + "?t=" + TOKEN;
  const el = (tag, text, cls) => { const e = document.createElement(tag); if (text) e.textContent = text; if (cls) e.className = cls; return e; };

  function paint() {
    const kind = $("oldPicKind").value, words = $("oldPicFind").value.toLowerCase().split(/\s+/).filter(Boolean);
    const list = all.filter(p => (!kind || p.source.startsWith(kind)) && words.every(w => (p.prompt || "").toLowerCase().includes(w)));
    const grid = $("oldPicGrid"); grid.textContent = "";
    $("oldPicCount").textContent = `${list.length} picture(s)`;
    for (const p of list.slice(0, 200)) {
      const fig = el("figure", "", "oldpics__item");
      const a = el("a"); a.href = full(p.path); a.target = "_blank"; a.rel = "noopener noreferrer"; a.title = "See it full size";
      const img = el("img"); img.src = thumb(p.path); img.loading = "lazy"; img.alt = `Old picture: ${p.prompt || "shot " + p.was_shot}`;
      a.append(img);
      const cap = el("figcaption");
      cap.append(el("strong", `${p.source}, was shot ${p.was_shot}${p.take ? ` (take ${p.take})` : ""}`));
      if (p.score) cap.append(el("span", ` ${Math.round(p.score * 100)}% like this shot`, "oldpics__match"));
      if (p.prompt) cap.append(el("small", p.prompt.length > 140 ? p.prompt.slice(0, 140) + "…" : p.prompt));
      const use = el("button", "Use this", "btn btn--primary"); use.type = "button";
      use.addEventListener("click", () => assign(p));
      fig.append(a, cap, use);
      grid.append(fig);
    }
    if (!list.length) grid.append(el("p", all.length ? "No old picture matches." : "There are no old pictures for this book yet.", "warn"));
  }
  async function assign(p) {
    try {
      const r = await api("/api/assign_picture", { project: $("proj").value, n: shot, path: p.path, model: p.model });
      closeDlg();
      if (window.sbRefreshCard) await window.sbRefreshCard(shot); else if (window.sbReload) await window.sbReload(); else $("sbLoad").click();   // only that card: the new picture shows at once
      $("sbStatus").textContent = `Shot ${shot} now has that picture` + (r.kept_as_take ? " (the one it had is kept as a take)" : "") + ". Say yes or no to it.";
      if (window.flowRefresh) window.flowRefresh();
    } catch (e) { $("oldPicCount").textContent = e.message; }
  }
  window.openOldPictures = async n => {
    shot = n; all = [];
    $("oldPicTitle").textContent = `Old pictures for shot ${n}`;
    $("oldPicShot").textContent = "Loading...";
    $("oldPicGrid").textContent = "";
    if (dlg.showModal) dlg.showModal(); else dlg.setAttribute("open", "");
    try {
      const r = await api(`/api/old_pictures?project=${encodeURIComponent($("proj").value)}&n=${n}`);
      all = r.pictures;
      $("oldPicShot").textContent = r.prompt ? `This shot: ${r.prompt}` : "";
      paint();
    } catch (e) { $("oldPicShot").textContent = e.message; }
  };
  $("oldPicClose").addEventListener("click", closeDlg);
  $("oldPicKind").addEventListener("change", paint);
  $("oldPicFind").addEventListener("input", paint);
})();
