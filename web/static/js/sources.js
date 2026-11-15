// studio/sources.js - M2: the "Add your sources" card (documents, ideas, pictures, comic pages, web pages, screenplays, video / audio, each
// with a rights tick) and the products / styles part of the "Format, products and styles" card (products A-G, length, aspect, rating,
// faithfulness, quality, styles with one MASTER, and the live estimate). Classic script: uses $, api, hdr from core.js.
// Server: studio_app/sources_routes.py (+ handler.py /api/source_upload), scripts/sources.py, scripts/production.py.
(function () {
  const box = $("sourcesBody"), prod = $("prodBody");
  if (!box || !prod) return;
  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const KIND = { document: "Document", idea: "Idea", picture: "Pictures", comic: "Comic page", website: "Web page", screenplay: "Screenplay", media: "Video / audio" };
  let slug = "", saveTimer = null, P = null;

  // ------------------------------------------------------------------ sources
  function sourcesHtml(S) {
    const rows = S.sources.map(s => `<tr><td>${esc(KIND[s.kind] || s.kind)}</td><td>${esc(s.title)}${s.url ? `<br><small class="warn">${esc(s.url)}</small>` : ""}</td>
      <td>${s.words ? s.words.toLocaleString() + " words" : ""}${s.scenes ? `, ${s.scenes} scenes` : ""}${s.images.length ? `, ${s.images.length} picture(s)` : ""}</td>
      <td>${s.described ? "" : `<button type="button" class="btn btn--secondary" data-describe="${esc(s.id)}">Describe</button>`}
      <button type="button" class="btn btn--ghost" data-remove="${esc(s.id)}" aria-label="Remove ${esc(s.title)}">Remove</button></td></tr>`).join("");
    return `<label class="f" for="srcProject">Book</label>
      <input type="text" id="srcProject" value="${esc(slug)}" maxlength="40" pattern="[a-z0-9_]{2,40}" spellcheck="false" autocomplete="off" aria-describedby="srcProjectHelp">
      <small class="warn" id="srcProjectHelp">The book these sources belong to. Type a new name (lowercase letters, digits, _) to start a new one.</small>
      <table class="data-table" aria-label="Sources of this book" style="margin-top:8px"><tr><th>Kind</th><th>Source</th><th>Size</th><th></th></tr>${rows || '<tr><td colspan="4">No sources yet.</td></tr>'}</table>
      <p class="warn">${S.total_words.toLocaleString()} of ${S.max_words.toLocaleString()} words used.</p>
      <label class="opt"><input type="checkbox" id="srcRights"><span>I have the right to use these sources (my own work, public domain, or licensed to me)<small>Required for every source; saved with the date and time.</small></span></label>
      <details open><summary>Add a file</summary>
        <label class="f" for="srcFiles">Documents (.pdf .epub .docx .odt .rtf .html .txt .md), screenplays (.fountain .fdx), pictures (.jpg .png .webp), video or audio</label>
        <input type="file" id="srcFiles" multiple accept="${esc(S.accepted.join(","))}">
        <label class="opt"><input type="checkbox" id="srcComic"><span>These pictures are comic or manga pages (the panels are read in order)</span></label>
        <button type="button" class="btn btn--secondary" id="srcUpload">Add the files</button></details>
      <details><summary>Add an idea</summary>
        <label class="f" for="srcIdeaTitle">Title (optional)</label><input type="text" id="srcIdeaTitle" maxlength="120" autocomplete="off">
        <label class="f" for="srcIdea">The idea: one line or several pages</label><textarea id="srcIdea" rows="4" style="width:100%" spellcheck="true"></textarea>
        <button type="button" class="btn btn--secondary" id="srcIdeaAdd">Add the idea</button></details>
      <details><summary>Add a web page</summary>
        <label class="f" for="srcUrl">Web address (http or https)</label><input type="url" id="srcUrl" placeholder="https://" autocomplete="url" inputmode="url">
        <button type="button" class="btn btn--secondary" id="srcUrlAdd">Read the page</button>
        <small class="warn">Read on this computer. Pages whose site asks programs not to read them (robots.txt) are skipped; private addresses are refused.</small></details>
      <div class="row" style="gap:8px;margin-top:10px;flex-wrap:wrap"><button type="button" class="btn btn--primary" id="srcChapters"${S.sources.length ? "" : " disabled"}>Use these sources as the chapters</button></div>
      <p class="warn" id="srcMsg" role="status" aria-live="polite"></p>`;
  }
  const say = (t, bad) => { const m = $("srcMsg"); if (m) { m.textContent = t; m.style.color = bad ? "#d6455d" : ""; } };
  const project = () => ($("srcProject") ? $("srcProject").value.trim() : slug);
  const rights = () => { const r = $("srcRights"); if (!r || !r.checked) { say("Tick the rights box first.", true); return false; } return true; };

  async function renderSources(msg) {
    let S;
    try { S = await api(`/api/sources?project=${encodeURIComponent(slug)}`); } catch (e) { box.textContent = e.message; return; }
    box.innerHTML = sourcesHtml(S);
    if (msg) say(msg);
    $("srcProject").addEventListener("change", () => { slug = project(); renderSources(); loadProduction(); });
    box.querySelectorAll("[data-remove]").forEach(b => b.addEventListener("click", async () => {
      if (!confirm("Remove this source from the book?")) return;
      try { await api("/api/source_remove", { project: project(), id: b.dataset.remove }); renderSources("Removed."); } catch (e) { say(e.message, true); }
    }));
    box.querySelectorAll("[data-describe]").forEach(b => b.addEventListener("click", async () => {
      b.disabled = true; say("Your story analyst is looking at the pictures…");
      try { await api("/api/source_describe", { project: project(), id: b.dataset.describe, engine: ($("engine") && $("engine").value) || "claude" }); renderSources("Described."); }
      catch (e) { say(e.message, true); b.disabled = false; }
    }));
    $("srcUpload").addEventListener("click", async () => {
      const files = [...$("srcFiles").files];
      if (!files.length) return say("Choose a file first.", true);
      if (!rights()) return;
      for (const [i, f] of files.entries()) {
        say(`Adding ${f.name} (${i + 1} of ${files.length})…`);
        const q = new URLSearchParams({ project: project(), filename: f.name, rights: "1", comic: $("srcComic").checked ? "1" : "0" });
        const r = await fetch(`/api/source_upload?${q}`, { method: "POST", headers: hdr, body: f });
        const j = await r.json().catch(() => ({}));
        if (!r.ok) return say(`${f.name}: ${j.error || r.statusText}`, true);
      }
      slug = project(); renderSources(`Added ${files.length} file(s).`);
    });
    $("srcIdeaAdd").addEventListener("click", async () => {
      if (!rights()) return;
      try { await api("/api/source_add", { project: project(), kind: "idea", text: $("srcIdea").value, title: $("srcIdeaTitle").value, rights: true }); slug = project(); renderSources("Idea added."); }
      catch (e) { say(e.message, true); }
    });
    $("srcUrlAdd").addEventListener("click", async () => {
      if (!rights()) return;
      say("Reading the page…");
      try { await api("/api/source_add", { project: project(), kind: "website", url: $("srcUrl").value, rights: true }); slug = project(); renderSources("Web page added."); }
      catch (e) { say(e.message, true); }
    });
    $("srcChapters").addEventListener("click", async () => {
      try { const j = await api("/api/sources_to_chapters", { project: project() }); say(`${j.chapters} chapters made from the sources. Check them in the Chapters card.`); if (typeof refresh === "function") refresh(); }
      catch (e) { say(e.message, true); }
    });
  }

  // ------------------------------------------------------------------ format, products and styles
  function prodHtml(R) {
    const S = R.settings, C = R.catalog, E = R.estimate;
    const chosen = new Set(S.products), styles = new Set(S.styles.map(s => s.id));
    const custom = S.styles.filter(s => !C.styles.some(c => c.id === s.id));
    const opt = (list, val) => list.map(o => `<option value="${esc(o.id)}"${o.id === val ? " selected" : ""}>${esc(o.name)}</option>`).join("");
    const est = E.styles.map(s => `<tr><td>${esc(s.name)}${s.master ? " (master)" : ""}</td><td>${s.pictures}</td><td>${s.clips}</td><td>${s.calls}</td><td>${s.gpu_hours} h</td><td>$${s.dollars.toFixed(2)}</td></tr>`).join("");
    return `<fieldset><legend>What to make</legend>${C.products.map(p => `<label class="opt"><input type="checkbox" name="prodProduct" value="${p.id}"${chosen.has(p.id) ? " checked" : ""}${p.id === "screenplay" ? " disabled" : ""}><span>${p.letter}. ${esc(p.title)}${p.per_style ? " <small>(one per style)</small>" : ""}</span></label>`).join("")}</fieldset>
      <div class="row" style="gap:12px;flex-wrap:wrap">
        <div><label class="f" for="prodMinutes">Length (minutes)</label><input type="number" id="prodMinutes" min="0.5" max="600" step="0.5" value="${S.target_minutes}" style="width:7em"></div>
        <div><label class="f" for="prodAspect">Aspect ratio</label><select id="prodAspect">${opt(C.aspects.map(a => ({ id: a, name: a })), S.aspect)}</select></div>
        <div><label class="f" for="prodRating">Rating</label><select id="prodRating">${opt(C.ratings, S.rating)}</select></div>
        <div><label class="f" for="prodFaith">Faithfulness</label><select id="prodFaith">${opt(C.faithfulness, S.faithfulness)}</select></div>
        <div><label class="f" for="prodTier">Quality</label><select id="prodTier">${opt(C.tiers, S.tier)}</select></div>
      </div>
      <fieldset><legend>Styles (the same film in each look; the master is made first)</legend>
        ${C.styles.map(s => `<div class="row" style="gap:8px;align-items:center"><label class="opt" style="flex:1"><input type="checkbox" name="prodStyle" value="${s.id}"${styles.has(s.id) ? " checked" : ""}><span>${esc(s.name)}<small>${esc(s.about)}</small></span></label>
          <label><input type="radio" name="prodMaster" value="${s.id}"${S.master === s.id ? " checked" : ""}${styles.has(s.id) ? "" : " disabled"}> master</label></div>`).join("")}
        ${custom.map(s => `<div class="row" style="gap:8px;align-items:center"><label class="opt" style="flex:1"><input type="checkbox" name="prodStyle" value="${esc(s.id)}" checked data-custom="1" data-name="${esc(s.name)}" data-text="${esc(s.text)}"><span>${esc(s.name)} (custom)<small>${esc(s.text)}</small></span></label>
          <label><input type="radio" name="prodMaster" value="${esc(s.id)}"${S.master === s.id ? " checked" : ""}> master</label></div>`).join("")}
        <details><summary>Add a custom style</summary>
          <label class="f" for="prodCustomName">Name</label><input type="text" id="prodCustomName" maxlength="60" autocomplete="off">
          <label class="f" for="prodCustomText">Describe the look in words (medium, materials, light, colour)</label><textarea id="prodCustomText" rows="2" maxlength="1500" style="width:100%"></textarea>
          <button type="button" class="btn btn--secondary" id="prodCustomAdd">Add the style</button></details>
      </fieldset>
      <table class="data-table" aria-label="Estimate per style"><caption class="warn" style="text-align:left">About ${E.shots} shots (${E.seconds_per_shot} s each), ${E.text_calls} writing calls; +${Math.round(E.regen_allowance * 100)}% for regenerations</caption>
        <tr><th>Style</th><th>Pictures</th><th>Clips</th><th>GPU calls</th><th>GPU time</th><th>Cost</th></tr>${est}
        <tr><td><b>All styles</b></td><td></td><td></td><td></td><td><b>${E.gpu_hours} h</b></td><td><b>$${E.dollars.toFixed(2)}</b></td></tr></table>
      <p class="warn">${E.paid ? "" : `Free GPUs (Kaggle, Colab): $0, about ${E.free_weeks} week(s) of the free weekly Kaggle time.`}</p>
      <p class="warn" id="prodNotes" role="status" aria-live="polite">${R.notes.map(esc).join(" ")}</p>`;
  }
  function gather() {
    const styles = [...prod.querySelectorAll("input[name=prodStyle]:checked")].map(b => b.dataset.custom ? { id: b.value, name: b.dataset.name, text: b.dataset.text } : { id: b.value });
    const m = prod.querySelector("input[name=prodMaster]:checked");
    return { project: slug, products: [...prod.querySelectorAll("input[name=prodProduct]:checked")].map(b => b.value), target_minutes: Number($("prodMinutes").value),
      aspect: $("prodAspect").value, rating: $("prodRating").value, faithfulness: $("prodFaith").value, tier: $("prodTier").value, styles, master: m ? m.value : "" };
  }
  async function saveProduction(extra) {
    try { P = await api("/api/production", { ...gather(), ...(extra || {}) }); drawProduction(); }
    catch (e) { const n = $("prodNotes"); if (n) { n.textContent = e.message; n.style.color = "#d6455d"; } }
  }
  function drawProduction() {
    prod.innerHTML = prodHtml(P);
    prod.querySelectorAll("input,select").forEach(el => el.addEventListener("change", () => { clearTimeout(saveTimer); saveTimer = setTimeout(() => saveProduction(), 250); }));
    $("prodCustomAdd").addEventListener("click", () => {
      const name = $("prodCustomName").value.trim(), text = $("prodCustomText").value.trim();
      if (!name || !text) { $("prodNotes").textContent = "Give the custom style a name and describe it."; return; }
      const id = "custom_" + (name.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "").slice(0, 20) || "style");
      const g = gather(); g.styles.push({ id, name, text });
      saveProduction({ styles: g.styles });
    });
  }
  async function loadProduction() {
    if (!slug) { prod.innerHTML = ""; return; }
    try { P = await api(`/api/production?project=${encodeURIComponent(slug)}`); if (P.settings) drawProduction(); else prod.innerHTML = ""; } catch (e) { prod.innerHTML = ""; }
  }
  const recipeSel = $("crewRecipe");
  if (recipeSel) recipeSel.addEventListener("change", () => setTimeout(loadProduction, 400));      // crew.js saves the recipe first

  window.loadSourcesCard = p => {
    slug = p && p.slug && !p.legacy && /^[a-z0-9_]{2,40}$/.test(p.slug) ? p.slug : "";
    renderSources();
    loadProduction();
  };
})();
