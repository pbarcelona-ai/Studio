// studio/sessions.js - work left running by an earlier session (server: /api/sessions, studio_app/resume.py). When the page opens it says,
// in plain words, what is still running: a job the Studio is following again, a job that was cut off (carry on / do the step again / forget it),
// Studio programs still busy on this computer (stop), and Kaggle notebooks those jobs pushed (with their state). Classic script: uses $ and api.
(function () {
  const box = document.getElementById("sessionBanner");
  if (!box) return;
  const el = (tag, text, cls) => { const e = document.createElement(tag); if (text) e.textContent = text; if (cls) e.className = cls; return e; };
  const btn = (text, fn, cls = "btn btn--secondary") => { const b = el("button", text, cls); b.type = "button"; b.addEventListener("click", fn); return b; };
  const what = k => k === "GPU" ? "making pictures, video or sound" : k === "AI" ? "writing with the AI" : "working";
  let kernels = [];

  async function act(body, ask) {
    if (ask && !confirm(ask)) return;
    try { await api("/api/sessions", body); } catch (e) { alert(e.message); }
    load(false);
    if (window.flowWatch) window.flowWatch();
  }

  function paint(d) {
    box.textContent = "";
    const rows = [];
    if (d.following) rows.push([el("p", `Still working from last time: ${d.following_label}. The Studio is following it again, and the rest of that job will run after it. Watch it in the log at the bottom.`)]);
    const j = d.job;
    if (j && !d.following) {
      const p = el("p", j.still_running
        ? `From last time, "${j.label}" (step ${j.step} of ${j.steps}) for ${j.project} is still running.`
        : `Last time, "${j.label}" (step ${j.step} of ${j.steps}) for ${j.project} did not finish` + (j.step_exit === 0 ? " the job: that step was done." : j.step_exit === null ? ": it was cut off." : `: it stopped with error ${j.step_exit}.`));
      const bar = el("div", "", "session-banner__buttons");
      if (j.still_running) bar.append(btn("Follow it", () => act({ action: "continue" }), "btn btn--primary"));
      else {
        bar.append(btn(j.step_exit === 0 ? `Carry on (${j.left.length} step(s) left)` : "Carry on (do that step again)", () => act({ action: "continue" }), "btn btn--primary"));
        if (j.step_exit === 0) bar.append(btn("Do that step again", () => act({ action: "redo" })));
        bar.append(btn("Forget it", () => act({ action: "discard" }, "Forget the job from last time? Nothing it made is deleted."), "btn btn--ghost"));
      }
      const det = el("details"); det.append(el("summary", "What it said last"), el("pre", (j.log || []).join("\n") || "(nothing yet)"));
      rows.push([p, bar, det]);
    }
    for (const pr of d.processes || []) {
      const p = el("p", `The Studio is still ${what(pr.kind)} on this computer (running for ${pr.running_for}): ${pr.command}`);
      rows.push([p, btn("Stop it", () => act({ action: "stop", pid: pr.pid }, "Stop this program? What it already made is kept."), "btn btn--ghost")]);
    }
    for (const k0 of d.kernels || []) {                       // the notebooks of the job now known, with the last state looked up
      const k = k0.status ? k0 : (kernels.find(x => x.ref === k0.ref) || k0);
      const p = el("p", `Kaggle notebook ${k.ref}: ${k.status ? k.status.toLowerCase().replace(/_/g, " ") : "checking..."}. `);
      const a = el("a", "Open it on Kaggle"); a.href = `https://www.kaggle.com/code/${k.ref}`; a.target = "_blank"; a.rel = "noopener noreferrer";
      p.append(a);
      if (k.status === "COMPLETE") p.append(" It is finished: press \"Fetch results\" (Make the Movie card, or Put the film together) to bring the pictures home.");
      rows.push([p]);
    }
    box.classList.toggle("hidden", !rows.length);
    if (rows.length) {
      box.append(el("strong", "Still going from last time"));
      rows.forEach(r => { const div = el("div", "", "session-banner__row"); r.forEach(x => div.append(x)); box.append(div); });
    }
  }
  async function load(withKernels) {
    let d;
    try { d = await api("/api/sessions" + (withKernels ? "?kernels=1" : "")); } catch (e) { return; }
    if (withKernels) kernels = d.kernels.filter(k => k.status);
    paint(d);
    if (window.flowRefresh) window.flowRefresh();
  }
  load(false).then(() => load(true));
  setInterval(() => { if (!document.hidden) load(false); }, 20000);
  setInterval(() => { if (!document.hidden) load(true); }, 120000);
  window.sessionsReload = load;
})();
