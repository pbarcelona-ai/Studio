// studio/chapters.js - the Chapters card: list a book's chapters and rename, join, cut or drop them (server: studio_app/chapters.py).
// Classic script: uses $, api and cur() from core.js. core.js's renderProject() calls loadChapters(p).
let chapData = null;        // the last answer of /api/chapters for the chosen book
let chapOpen = 0;           // chapter number shown in the text pane (0 = none)
let chapSlug = "";          // the book chapData belongs to
let chapTimer = null;

function chapEl(tag, text, cls) { const e = document.createElement(tag); if (text !== undefined) e.textContent = text; if (cls) e.className = cls; return e; }

function loadChapters(p) {
  clearTimeout(chapTimer);
  chapTimer = setTimeout(() => chapFetch(p || cur()), 250);     // renderProject runs often; one request per burst
}

async function chapFetch(p) {
  const note = $("chapNote");
  if (!p || p.legacy || p.not_started || !p.chapters) {
    chapData = null; chapOpen = 0;
    $("chapBar").classList.add("hidden"); $("chapEditor").classList.add("hidden"); $("chapTable").textContent = "";
    note.textContent = !p ? "Pick a book first." : p.legacy ? "Imported books keep their own chapters." : "This book has not been read yet: run Read book first.";
    return;
  }
  if (p.slug !== chapSlug) { chapSlug = p.slug; chapOpen = 0; }
  try {
    chapData = await api(`/api/chapters?project=${encodeURIComponent(p.slug)}`);
  } catch (e) { note.textContent = e.message; return; }
  chapRender();
}

function chapRender() {
  const d = chapData, p = cur();
  if (!d || !p) return;
  const t = $("chapTable");
  t.textContent = "";
  const head = chapEl("tr");
  ["Pick", "#", "Title", "Words", "Starts with", "Actions"].forEach(h => head.appendChild(chapEl("th", h)));
  const thead = chapEl("thead"); thead.appendChild(head); t.appendChild(thead);
  const body = chapEl("tbody");
  d.chapters.forEach((c, i) => {
    const tr = chapEl("tr");
    const pick = chapEl("input"); pick.type = "checkbox"; pick.dataset.n = c.n; pick.setAttribute("aria-label", `Tick chapter ${c.n}`);
    pick.addEventListener("change", chapPicked);
    const tdPick = chapEl("td"); tdPick.appendChild(pick);
    const title = chapEl("input"); title.type = "text"; title.value = c.title; title.maxLength = 80; title.autocomplete = "off"; title.style.width = "100%";
    title.setAttribute("aria-label", `Title of chapter ${c.n}`);
    title.addEventListener("change", () => chapDo({ action: "rename", n: c.n, title: title.value }, false));
    const tdTitle = chapEl("td"); tdTitle.appendChild(title);
    const tdBtn = chapEl("td", "", "actions-col");
    const open = chapEl("button", "Open / split", "btn btn--ghost"); open.type = "button";
    open.addEventListener("click", () => chapShow(c.n));
    tdBtn.appendChild(open);
    if (i + 1 < d.chapters.length) {
      const join = chapEl("button", "Join with next", "btn btn--ghost"); join.type = "button";
      join.addEventListener("click", () => chapDo({ action: "merge", n: c.n }, true));
      tdBtn.appendChild(join);
    }
    [tdPick, chapEl("td", c.n), tdTitle, chapEl("td", c.words.toLocaleString()), chapEl("td", c.preview.slice(0, 90)), tdBtn].forEach(td => tr.appendChild(td));
    body.appendChild(tr);
  });
  t.appendChild(body);
  $("chapBar").classList.remove("hidden");
  const total = d.chapters.reduce((a, c) => a + c.words, 0);
  const how = d.format && d.format !== "pdf" && d.format !== "text" ? `${d.format.toUpperCase()} file` : d.format === "pdf" ? "PDF" : "text";
  $("chapSummary").textContent = `${d.chapters.length} chapters, ${total.toLocaleString()} words (from a ${how}; split by ${d.method}${d.ocr_pages ? `; ${d.ocr_pages} pages read with OCR, check the spelling` : ""})` +
    (d.front_words ? `; ${d.front_words.toLocaleString()} words of front matter kept aside` : "");
  const ds = d.downstream || {};
  $("chapNote").textContent = ds.scripts || ds.built
    ? `${ds.scripts} chapters already have shots written. Renaming is always safe; joining, cutting or dropping renumbers the chapters, so the shots would have to be written again.`
    : "Nothing has been written from these chapters yet, so you can change them freely. Short pieces (under 40 words) are usually contents pages or headings: drop or join them.";
  $("chapDrop").disabled = true;
  if (chapOpen && d.chapters.some(c => c.n === chapOpen)) chapShow(chapOpen); else { chapOpen = 0; $("chapEditor").classList.add("hidden"); }
}

function chapPicked() { $("chapDrop").disabled = !document.querySelector("#chapTable input[type=checkbox]:checked"); }

async function chapShow(n) {
  const p = cur();
  try {
    const r = await api(`/api/chapter_text?project=${encodeURIComponent(p.slug)}&n=${n}`);
    chapOpen = n;
    $("chapText").value = r.text;
    $("chapTextLabel").textContent = `Chapter ${n}: ${r.title}`;
    $("chapSplitTitle").value = "";
    $("chapEditor").classList.remove("hidden");
  } catch (e) { $("chapNote").textContent = e.message; }
}

// Sends one edit. `renumbers` edits ask first when shots are already written.
async function chapDo(body, renumbers) {
  const p = cur(), ds = (chapData && chapData.downstream) || {};
  if (!p) return;
  const b = { project: p.slug, ...body };
  if (renumbers && (ds.scripts || ds.built)) {
    if (!confirm("Shots are already written for this book. This changes the chapter numbers, so those shots will not match any more and the chapters need to be written again. Continue?")) return;
    b.force = true;
  }
  try {
    chapData = await api("/api/chapter_edit", b);
    await loadStatus();                                    // chapter count and chips
    chapRender();
  } catch (e) { $("chapNote").textContent = e.message; chapFetch(p); }
}

$("chapDrop").addEventListener("click", () => {
  const ns = [...document.querySelectorAll("#chapTable input[type=checkbox]:checked")].map(e => Number(e.dataset.n));
  if (ns.length && confirm(`Drop ${ns.length} chapter(s)? Their text is kept in dropped_text.txt in the book's folder.`)) { chapOpen = 0; chapDo({ action: "drop", ns }, true); }
});
// The text box is not readonly (a readonly box shows no cursor): it takes the cursor and selection, but every attempt to change the text is blocked.
for (const ev of ["beforeinput", "cut", "paste", "drop"]) $("chapText").addEventListener(ev, e => e.preventDefault());
$("chapSplit").addEventListener("click", () => {
  const ta = $("chapText");
  const at = [...ta.value.slice(0, ta.selectionStart)].length;          // characters (code points), as the server counts them
  chapDo({ action: "split", n: chapOpen, at, title: $("chapSplitTitle").value.trim() }, true);
});
$("chapClose").addEventListener("click", () => { chapOpen = 0; $("chapEditor").classList.add("hidden"); });
