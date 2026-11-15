// The install progress screen (BOOK_TO_SCREEN_BUILD.md rule 12), shared by the installer page and the Studio's Setup window:
// one bar for the whole install (step N of M, a percentage), one for the current task named in plain words, a "Show details" log,
// Cancel, Retry and "Copy the log". StudioProgress.mount(el, { get, post, log }) draws it into el and keeps it up to date.
(function () {
  const esc = s => String(s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const CSS = `.sp-bars { display: grid; gap: 14px; margin: 12px 0; }
  .sp-bars label { display: block; font-weight: 600; margin-bottom: 4px; }
  .sp-bars progress { width: 100%; height: 18px; accent-color: #7a5cff; }
  .sp-detail { opacity: .8; font-size: .92em; min-height: 1.3em; margin-top: 3px; }
  .sp-error { color: #d6455d; font-weight: 600; margin: 10px 0; }
  .sp-done { color: #2e9e5b; font-weight: 600; margin: 10px 0; }
  .sp-row { display: flex; gap: 10px; flex-wrap: wrap; margin: 10px 0; }
  .sp-row button { min-height: 40px; padding: 0 16px; border-radius: 8px; cursor: pointer; }
  .sp-log { max-height: 260px; overflow: auto; white-space: pre-wrap; font: 12px/1.45 ui-monospace, Menlo, Consolas, monospace; background: rgba(0,0,0,.25); padding: 8px; border-radius: 6px; }
  .sp-tasks { margin: 6px 0 0; padding-left: 1.3em; } .sp-tasks li.ok::marker { content: "✓  "; color: #2e9e5b; }`;
  let styled = false;

  function mount(el, io) {
    if (!styled) { const s = document.createElement("style"); s.textContent = CSS; document.head.appendChild(s); styled = true; }
    el.innerHTML = `<div class="sp-bars">
        <div><label id="spAllL" for="spAll">Overall</label><progress id="spAll" max="100" value="0"></progress><div class="sp-detail" id="spAllD"></div></div>
        <div><label id="spTaskL" for="spTask">Waiting to start</label><progress id="spTask" max="100" value="0"></progress><div class="sp-detail" id="spTaskD" aria-live="polite"></div></div>
      </div>
      <div id="spMsg" role="status" aria-live="polite"></div>
      <div class="sp-row">
        <button type="button" id="spCancel">Cancel</button><button type="button" id="spRetry" hidden>Retry</button>
        <button type="button" id="spCopy">Copy the log</button>
      </div>
      <details id="spDetails"><summary>Show details</summary><ol class="sp-tasks" id="spTasks"></ol><pre class="sp-log" id="spLog"></pre></details>`;
    const $ = id => el.querySelector("#" + id);
    let timer = null, state = "";

    async function copyLog() {
      const text = await io.log();
      try { await navigator.clipboard.writeText(text); $("spMsg").textContent = "The log is copied: paste it into a message to ask for help."; }
      catch (e) { $("spDetails").open = true; $("spLog").textContent = text; $("spMsg").textContent = "Select the log below and copy it."; }
    }
    function draw(S) {
      state = S.state;
      $("spAll").value = S.percent || 0;
      $("spAllD").textContent = S.steps ? `${Math.round(S.percent || 0)}%` + (S.step ? `, step ${S.step} of ${S.steps}` : "") : "";
      $("spTaskL").textContent = S.task_title || (S.state === "done" ? "Finished" : "Waiting to start");
      $("spTask").value = S.task_percent || 0;
      $("spTaskD").textContent = S.detail || "";
      $("spTasks").innerHTML = (S.tasks || []).map(t => `<li class="${t.done ? "ok" : ""}">${esc(t.title)}</li>`).join("");
      const msg = $("spMsg");
      msg.className = S.state === "failed" || S.state === "cancelled" ? "sp-error" : S.state === "done" ? "sp-done" : "";
      msg.textContent = S.error || (S.state === "done" ? "Everything is installed." : "");
      $("spCancel").hidden = S.state !== "running";
      $("spRetry").hidden = !(S.state === "failed" || S.state === "cancelled");
      $("spRetry").textContent = S.state === "cancelled" ? "Start again" : "Retry";
      if (io.onState) io.onState(S);
    }
    async function poll() {
      try {
        draw(await io.get());
        if ($("spDetails").open) $("spLog").textContent = await io.log();
      } catch (e) { $("spMsg").textContent = "Lost touch with the installer: " + e.message; }
      timer = setTimeout(poll, state === "running" ? 700 : 2500);
    }
    $("spCancel").addEventListener("click", async () => draw(await io.post("cancel")));
    $("spRetry").addEventListener("click", async () => draw(await io.post("retry")));
    $("spCopy").addEventListener("click", copyLog);
    $("spDetails").addEventListener("toggle", async () => { if ($("spDetails").open) $("spLog").textContent = await io.log(); });
    poll();
    return { refresh: async () => draw(await io.get()), stop: () => clearTimeout(timer) };
  }
  window.StudioProgress = { mount };
})();
