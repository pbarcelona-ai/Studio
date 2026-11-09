// Setup window: what this computer needs, and where each person pastes their own keys. Keys go to files on this computer only; the page never gets them back.
(function () {
  const css = document.createElement("style");
  css.textContent = `#setupBtn { background: transparent; border: none; padding: .5rem; border-radius: 6px; cursor: pointer; font-size: 1.05rem; color: #fff; }
  #setupBtn:hover { background: rgba(255,255,255,.16); }
  #setupDialog { max-width: min(680px, 94vw); max-height: 90vh; overflow: auto; border: 1px solid var(--border-strong); border-radius: 14px; background: var(--bg-elevated); color: var(--fg); padding: 22px 26px; }
  #setupDialog::backdrop { background: rgba(8,6,24,.6); }
  #setupDialog h2 { margin-top: 0; } #setupDialog h3 { margin: 18px 0 6px; font-size: 1rem; }
  #setupDialog ul.checks { list-style: none; padding: 0; margin: 8px 0; }
  #setupDialog ul.checks li { margin: 7px 0; display: grid; grid-template-columns: 1.6em 1fr; gap: 2px 6px; }
  #setupDialog .mark { font-weight: 700; } #setupDialog .good { color: #2e9e5b; } #setupDialog .bad { color: #d6455d; } #setupDialog .meh { color: #9a8f6a; }
  #setupDialog .detail { opacity: .75; font-size: .9em; } #setupDialog .fix { font-size: .9em; }
  #setupDialog label { display: block; margin: 8px 0 2px; font-size: .9em; }
  #setupDialog input[type=password], #setupDialog input[type=text] { width: 100%; box-sizing: border-box; }
  #setupDialog .row { display: flex; gap: 10px; flex-wrap: wrap; margin-top: 14px; }
  #setupDialog .msg { min-height: 1.4em; margin: 10px 0 0; }`;
  document.head.appendChild(css);
  const esc = s => String(s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const MARK = { true: ["✓", "good"], false_required: ["✗", "bad"], false_other: ["•", "meh"] };
  let dlg = null;

  function listHtml(S) {
    const row = i => {
      const [m, c] = i.ok ? MARK.true : (i.level === "required" ? MARK.false_required : MARK.false_other);
      return `<li><span class="mark ${c}">${m}</span><span><b>${esc(i.title)}</b> <span class="detail">${esc(i.detail)}${i.level === "optional" ? " (optional)" : ""}</span>${i.fix ? `<br><span class="fix">${esc(i.fix)}</span>` : ""}</span></li>`;
    };
    return `<ul class="checks">${S.items.map(row).join("")}</ul>`;
  }
  async function render(msg) {
    const S = await api("/api/setup");
    window.STUDIO_ROOT = S.root;
    const u = document.getElementById("kuser");
    if (u && !u.value && S.kaggle_username) { u.value = S.kaggle_username; try { localStorage.setItem("kaggle_user", S.kaggle_username); } catch (e) {} }
    if (!dlg) { dlg = document.createElement("dialog"); dlg.id = "setupDialog"; dlg.setAttribute("aria-labelledby", "setupTitle"); document.body.appendChild(dlg); }
    dlg.innerHTML = `<h2 id="setupTitle">Setup</h2>
      <p>${S.ready ? "Everything the Studio needs is here." : "The Studio needs a few more things before it can generate. The ✗ lines are required."}</p>
      ${listHtml(S)}
      <h3>Your Kaggle account (free GPUs)</h3>
      <p class="detail">Create a free account at kaggle.com and verify your phone number (needed for GPUs). Then on kaggle.com open Settings &gt; API and press <b>Create New Token</b>. Paste that token here. It is saved only on this computer.</p>
      <label for="setupKToken">Kaggle API token</label><input type="password" id="setupKToken" autocomplete="off" spellcheck="false" placeholder="paste the token (leave empty if you use the older username + key)">
      <details><summary>I have an older username + key (kaggle.json)</summary>
        <label for="setupKUser">Kaggle username</label><input type="text" id="setupKUser" autocomplete="off" spellcheck="false" placeholder="the part after kaggle.com/">
        <label for="setupKKey">Kaggle key</label><input type="password" id="setupKKey" autocomplete="off" spellcheck="false"></details>
      <h3>Hugging Face token (optional)</h3>
      <p class="detail">Only for the Hugging Face prompt writer. Inference Providers needs prepaid credit on your Hugging Face account.</p>
      <label for="setupHF">Hugging Face token</label><input type="password" id="setupHF" autocomplete="off" spellcheck="false" placeholder="hf_...">
      <div class="row"><button type="button" id="setupSave">Save</button><button type="button" id="setupTest">Test Kaggle login</button><button type="button" id="setupClose">Close</button></div>
      <p class="msg" id="setupMsg" role="status" aria-live="polite">${esc(msg || "")}</p>`;
    const say = (t, bad) => { const m = document.getElementById("setupMsg"); m.textContent = t; m.style.color = bad ? "#d6455d" : ""; };
    document.getElementById("setupClose").onclick = () => dlg.close();
    document.getElementById("setupSave").onclick = async () => {
      const g = id => document.getElementById(id).value.trim();
      const body = { kaggle_token: g("setupKToken"), kaggle_username: g("setupKUser"), kaggle_key: g("setupKKey"), hf_token: g("setupHF") };
      if (!Object.values(body).some(Boolean)) return say("Nothing to save yet: paste a token first.", true);
      try { const r = await api("/api/setup_save", body); await render("Saved: " + r.saved.join(", ").replace(/_/g, " ") + "."); if (ST) ST.hf_token_set = true; }
      catch (e) { say(e.message, true); }
    };
    document.getElementById("setupTest").onclick = async () => {
      say("Asking Kaggle…");
      try { const r = await api("/api/setup_test", {}); say(r.message, !r.ok); } catch (e) { say(e.message, true); }
    };
    return S;
  }
  async function open(msg) {
    try { await render(msg); } catch (e) { alert("Setup could not load: " + e.message); return; }
    if (typeof dlg.showModal === "function") { if (!dlg.open) dlg.showModal(); } else dlg.setAttribute("open", "");
  }
  document.getElementById("setupBtn").addEventListener("click", () => open());
  // First run: if something required is missing, open the window once per browser session; otherwise just fill in the Kaggle name.
  (async () => {
    try {
      const S = await api("/api/setup");
      window.STUDIO_ROOT = S.root;
      const u = document.getElementById("kuser");
      if (u && !u.value && S.kaggle_username) { u.value = S.kaggle_username; try { localStorage.setItem("kaggle_user", S.kaggle_username); } catch (e) {} }
      if (!S.ready && !sessionStorage.getItem("setupShown")) { sessionStorage.setItem("setupShown", "1"); open(); }
    } catch (e) { /* the page still works without it */ }
  })();
})();
