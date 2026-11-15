// studio/storyboard_update.js - the "Update storyboard from the storyline" button on the Storyboard card.
// Rewrites the shots from the approved screenplay, rebuilds the shot list, sets the old stills and clips aside (server: /api/storyboard_reset;
// nothing is deleted) and, if ticked, makes the new stills. Classic script: uses $, api, cur, runImport, run, loadStatus from the other files.
(function () {
  const btn = document.getElementById("sbUpdate");
  if (!btn) return;
  const note = t => { $("sbUpdNote").textContent = t; };
  const kf = $("kfmodel"), mine = $("sbMakeModel");

  // The keyframe model is chosen in the Video and Audio card; this box is the same choice, so the stills can be made from here.
  function syncModel() {
    if (mine.innerHTML !== kf.innerHTML) mine.innerHTML = kf.innerHTML;
    if (mine.value !== kf.value) mine.value = kf.value;
  }
  mine.addEventListener("change", () => { kf.value = mine.value; kf.dispatchEvent(new Event("change")); });
  kf.addEventListener("change", syncModel);
  new MutationObserver(syncModel).observe(kf, { childList: true });
  document.addEventListener("flow-render", () => { syncModel(); refreshWarn(); });
  syncModel();

  // Warn when the screenplay was edited after the shots were made.
  async function refreshWarn() {
    const p = $("proj").value, pr = cur();
    if (!p || !pr || !pr.built) { $("sbStoryWarn").classList.add("hidden"); return; }      // no shot list yet: nothing to be out of date
    try { const r = await api(`/api/storyboard?project=${encodeURIComponent(p)}&start=1&end=1`); $("sbStoryWarn").classList.toggle("hidden", !r.storyline_changed); }
    catch (e) { $("sbStoryWarn").classList.add("hidden"); }                       // no shots yet: nothing to be out of date
  }
  $("sbLoad").addEventListener("click", refreshWarn);
  $("proj").addEventListener("change", refreshWarn);

  // Old pictures of the same shots go back on their shots first, so no GPU time is spent making them again.
  async function autoMatch(quiet) {
    const r = await api("/api/auto_assign_pictures", { project: $("proj").value, model: $("kfmodel").value });
    if (!quiet || r.matched.length) note(`${r.matched.length} old picture(s) put back on their shots; ${r.still_missing.length} shot(s) still need a new picture.` +
      (r.matched.length ? " Say yes or no to the old ones first." : ""));
    if (r.matched.length) $("sbLoad").click();
    if (window.flowRefresh) window.flowRefresh();
    return r;
  }
  window.sbAutoMatch = autoMatch;
  // The button checks every shot, not only the empty ones: pictures on the wrong shot (made in an old order) move to the shot they show.
  async function matchAll() {
    const r = await api("/api/match_pictures", { project: $("proj").value, model: $("kfmodel").value });
    note(`Checked every shot: ${r.kept} picture(s) were already right, ${r.moved} moved to the shot they show, ${r.from_old} came back from old pictures` +
      (r.set_aside_as_takes ? `, ${r.set_aside_as_takes} showed no shot well and were kept as takes` : "") +
      `. ${r.still_missing.length} shot(s) still need a new picture.` + (r.changed.length ? " Say yes or no to the ones that changed." : ""));
    if (window.sbReload) await window.sbReload(); else $("sbLoad").click();
    if (window.flowRefresh) window.flowRefresh();
  }
  $("sbAutoMatch").addEventListener("click", () => matchAll().catch(e => note(e.message)));

  async function update() {
    const proj = $("proj").value;
    if (!proj) { note("Pick a book first."); return; }
    btn.disabled = true;
    try {
      // 1. only an approved screenplay may be turned into shots (a book without a film plan has none, and is allowed)
      let status = null;
      try { status = (await api(`/api/screenplay?project=${encodeURIComponent(proj)}`)).status; } catch (e) { status = null; }
      if (status && !status.approved) {
        note("The screenplay is not approved (or was changed after it was approved). Approve it on the Plan screen first.");
        if (window.flowGo) window.flowGo("screenplay");
        return;
      }
      if (!confirm("Update the storyboard from the storyline?\n\n- The shots are rewritten from the approved screenplay (one AI call per chapter).\n- Your saved prompt edits and verdicts belong to the old shots, so they are set aside.\n- The old stills and clips are moved into the book's 'replaced' folder; nothing is deleted.\n\nContinue?")) { note("Cancelled: nothing was changed."); return; }
      // 2. set the old storyboard aside first, so the rebuild does not re-apply edits that belong to old shots
      note("1 of 3: setting the old stills and clips aside...");
      const r = await api("/api/storyboard_reset", { project: proj });
      note(r.moved ? `Old files moved to ${r.folder}. 2 of 3: rewriting the shots and rebuilding the shot list...` : "2 of 3: rewriting the shots and rebuilding the shot list...");
      // 3. rewrite every chapter's shots from the screenplay, then rebuild the CSVs
      pendingOnly = { steps: ["write", "build"], force: true };
      if (window.flowWatch) window.flowWatch();
      await runImport();
      if (!lastImportOk) { note("Stopped: the shots could not be rewritten. The log shows why; the old files are safe in the 'replaced' folder."); return; }
      await loadStatus(true);
      if (window.sbFillMovies) window.sbFillMovies();
      $("sbLoad").click();
      refreshWarn();
      // 4. old pictures of the same shots first (no GPU), then new stills for the rest
      const m = await autoMatch(true);
      if (m.matched.length) {
        note(`The shots are updated. ${m.matched.length} old picture(s) were put back on their shots; say yes or no to them, then press "Make the pictures" for the ${m.still_missing.length} shot(s) left.`);
      } else if ($("sbUpdMake").checked) {
        note("3 of 3: making the new stills (the log at the bottom shows progress)...");
        pendingOnly = { steps: ["keyframes"] };
        const ok = await run();
        if (window.flowWatch) window.flowWatch();
        note(ok ? "The stills are being made. When the log says it is done, press Show storyboard." : "The shots are updated, but the stills did not start (see the message above). Pick where to run in 'Where to Run', then press 'Make the keyframe stills'.");
      } else note("The shots are updated and the storyboard is empty. Press 'Make the keyframe stills' when you are ready.");
    } catch (e) { note(e.message || String(e)); }
    finally { btn.disabled = false; }
  }
  btn.addEventListener("click", update);
})();
