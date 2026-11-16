// studio/flow.js - the film path: every step from the book to the finished film, one at a time and in order, in words a child can follow.
// Each step shows what it is for, what to do now, a button that does it (with the right options already set), the cards needed for it,
// and the rest of its settings folded under "More settings". "Next" only opens when the step is finished (the server says so: /api/path).
// When something changes in a later step (a shot edited or moved on the storyboard) the path walks back: the screenplay first, then every
// step after it in order. The cards are moved here from their tabs, not copied; "All tabs" puts them back.
// Classic script, loaded after shell.js, core.js, film.js and pizazz.js.
(function () {
  const RUN = {
    read: ["Read the book", "book", ["ingest"]], adapt: ["Plan the film", "book", ["adapt"]], screenplay: ["Write the screenplay", "book", ["screenplay"]],
    continuity: ["Make the story notes", "book", ["continuity"]], write: ["Write the shots", "book", ["write"]], rewrite: ["Write them all again", "book", ["write"], true],
    build: ["Get the shots ready", "book", ["build"]], video: ["Make the video", "movie", ["video"]], audio: ["Make the sound", "movie", ["audio"]],
    cut: ["Put the film together", "movie", ["merge", "mix"]],
  };
  // id, title, what it is for, cards shown, cards under "More settings", buttons (RUN keys, or a special one)
  const STEPS = [
    ["read", "Read the book", "Pick your book at the top of the page (or add a new one here), or add any other sources: an idea, pictures, a web page, a screenplay. Then let the Studio read it.", ["Read book", "Add your sources"], ["Tools Status", "Imported Book Tools", "Make my film"], ["read"]],
    ["chapters", "Check the chapters", "Look at the chapters. You can join, split or rename them, and drop pages that are not part of the story.", ["Chapters"], [], []],
    ["plan", "Plan the film", "Say how many minutes long your film is. The Studio picks the scenes that tell the story in that time.", ["Format, products and styles", "Read it in", "Film plan and screenplay"], ["AI Prompt Writer"], ["adapt"]],
    ["screenplay", "Write and approve the screenplay", "The screenplay is what happens and what people say in every scene. Read it, change anything, then approve it.", ["Film plan and screenplay"], [], ["screenplay", "approve"]],
    ["continuity", "Make the story notes", "The Studio writes down who is in the story, what they look like and how they sound, so they look the same in every picture.", ["Cast, places and shot list", "Look development"], ["Continuity book"], ["continuity"]],
    ["cast", "Pick the cast", "You can give each character a picture, so their face stays the same. You can skip this.", ["Cast (optional)"], [], []],
    ["look", "Choose the look and voices", "Pick how the film looks and which voice each character has. You can skip this.", ["Voice Cast"], ["Global Parameters", "Creative Direction", "Scene Enhancement"], []],
    ["write", "Write the shots", "Each scene is cut into short shots: what we see, and what is said.", [], ["Write shots"], ["write", "rewrite"]],
    ["build", "Get the shots ready", "The shots are put in the lists the picture and video makers read.", [], ["Build CSVs", "Run the ticked book steps"], ["build"]],
    ["where", "Choose the computer", "Pictures and video need a strong computer. Kaggle is free: type your Kaggle name.", ["Where to Run"], ["Which Movies"], []],
    ["keyframes", "Make the pictures", "First one picture is made for every shot. They are cheap to make, and you check them before any video is made.", ["Pictures in the master style", "Compare styles", "Picture library and start over"], ["Suggested Models", "Video and Audio"], ["stills", "getPictures"]],
    ["storyboard", "Check every picture", "Say yes or no to every picture. You can change a shot's words, move shots, or make everything again from the screenplay.", ["Storyboard (optional)"], [], ["approveRest", "getPictures"]],
    ["video", "Make the video", "Now every picture you said yes to is turned into a moving clip.", ["Video & Audio Models"], ["Video and Audio", "Make the Movie"], ["video", "getVideo"]],
    ["audio", "Make the sound", "The voices, sounds and music are made.", ["Voices, sound and music"], ["Video and Audio", "Video & Audio Models"], ["audio", "getSound"]],
    ["cut", "Put the film together", "The clips and the sound are joined into your film.", ["Timeline editor", "Final film"], ["Kaggle Runs", "Execution Log"], ["cut"]],
    ["premiere", "Share your film", "Watch it, save a copy for YouTube or a friend, and add the credits.", ["Export and credits"], ["Results Gallery", "What Exists for This Book", "Cleanup"], []],
  ];
  const ID = STEPS.map(s => s[0]);
  const MAIN_PANELS = ["project", "characters", "movies", "results"];
  const list = document.getElementById("flowList"), toggle = document.getElementById("flowToggle");
  if (!list || !toggle) return;
  let current = 0, on = true, data = null;
  try { on = localStorage.getItem("flowMode") !== "off"; current = Math.max(0, Math.min(STEPS.length - 1, parseInt(localStorage.getItem("pathStep") || "0", 10) || 0)); } catch (e) { /* private window */ }

  // ---- find every card once, before anything is moved
  const titleOf = card => { const h = card.querySelector(".card__title"); return h ? h.textContent.trim() : ""; };
  const homePanel = new Map(), byTitle = new Map(), allMain = [];
  document.querySelectorAll(".tab-panel").forEach(p => {
    const name = p.id.replace("panel-", "");
    p.querySelectorAll(":scope > .card").forEach(c => {
      homePanel.set(c, name);
      const t = titleOf(c); if (t && !byTitle.has(t)) byTitle.set(t, c);
      if (MAIN_PANELS.includes(name)) allMain.push(c);
    });
  });
  const find = prefix => { for (const [t, c] of byTitle) if (t.startsWith(prefix)) return c; return null; };
  const cardsOf = s => [...s[3], ...s[4]].map(find).filter(Boolean);
  window.flowOrphans = () => allMain.filter(c => !STEPS.some(s => cardsOf(s).includes(c))).map(titleOf);
  window.flowScreens = () => STEPS.map(s => s[1]);
  window.flowStageTitles = () => [...stage.querySelectorAll(".flow-shown > .card")].map(titleOf);
  window.flowMoreTitles = () => [...stage.querySelectorAll(".path-more > .card")].map(titleOf);

  // ---- the stage: the guide for the step, the cards it needs, then "More settings"
  const stage = document.createElement("div");
  stage.id = "flowStage"; stage.className = "flow-stage";
  stage.innerHTML = `<section class="path-guide" id="pathGuide" aria-labelledby="pathTitle">
      <p class="path-guide__count" id="pathCount"></p>
      <h2 class="path-guide__title" id="pathTitle"></h2>
      <p class="path-guide__about" id="pathAbout"></p>
      <div class="path-alerts" id="pathAlerts" role="status" aria-live="polite"></div>
      <p class="path-todo" id="pathTodo" role="status" aria-live="polite"></p>
      <div class="path-actions" id="pathActions"></div>
    </section>
    <div class="flow-shown" id="flowShown"></div>
    <details class="path-more" id="pathMore"><summary>More settings</summary></details>`;
  document.getElementById("panel-project").before(stage);
  const shown = stage.querySelector("#flowShown"), more = stage.querySelector("#pathMore");
  const away = new Map();                                    // card -> the comment that marks where it lives
  function pull(card, where) { if (!away.has(card)) { const mark = document.createComment("card home"); card.replaceWith(mark); away.set(card, mark); } where.append(card); }
  function putBack(card) { const mark = away.get(card); if (mark) { mark.replaceWith(card); away.delete(card); } }

  // ---- the state of every step, from the server
  const proj = () => $("proj").value;
  async function refresh() {
    if (!proj()) { data = null; paint(); return; }
    try { data = await api(`/api/path?project=${encodeURIComponent(proj())}`); } catch (e) { data = null; }
    paint();
  }
  function whereOk() {
    const svc = radio("svc");
    if (!svc) return [false, "Choose a computer."];
    if (svc === "kaggle" && !$("kuser").value.trim()) return [false, "Type your Kaggle name (the part after kaggle.com/)."];
    if (!$("gpu").value) return [false, "Choose a GPU."];
    return [true, ""];
  }
  const stepState = i => {                                   // {ok, done, todo} for step i
    if (!data) return i === 0 ? { ok: false, done: false, todo: proj() ? "Loading..." : "Choose your book at the top of the page, or add a new one below." } : { ok: false, done: false, todo: "" };
    const s = data.steps[i] || { ok: true, done: true, todo: "" };
    if (ID[i] === "where") { const [ok, why] = whereOk(); return { ok, done: ok, todo: why }; }
    return s;
  };
  function reachable() {                                    // the furthest step that may be opened
    let i = 0;
    while (i < STEPS.length - 1 && stepState(i).ok) i++;
    if (data && data.revisit && data.revisit.length) i = Math.min(i, ID.indexOf(data.revisit[0]));
    return i;
  }

  // ---- buttons that do the step's work
  const sayPath = (t, bad) => { const el = $("pathTodo"); el.textContent = t; el.classList.toggle("err", !!bad); };
  const say = sayPath;
  function runOnly(kind, steps, force, label, tell) {
    const out = tell || say;
    if (!proj()) { out("Pick your book first (at the top of the page).", true); return; }
    pendingOnly = { steps, force: !!force };
    activity(`Starting: ${label}...`);
    (kind === "book" ? runImport() : run())
      .then(ok => { if (ok === false) out($("msg").textContent || `${label}: it did not start.`, true); })     // why it was refused (shown at the top too)
      .catch(e => { activity(e.message || String(e), true); out(e.message || String(e), true); })
      .finally(() => { watch(); refresh(); });
    watch();
  }
  window.flowRunOnly = runOnly;
  async function makeStills(tell) {                          // only after every picture already made has a yes or a no; the no's are made again
    const say = typeof tell === "function" ? tell : sayPath;   // the film path's "To do now" line, or the card's own status line
    const nav = i => { if (on) go(i); };                        // in the classic tabs, only say what to do
    if (!proj()) { say("Pick your book first (at the top of the page).", true); return; }
    await refresh();
    const f = data && data.facts;
    if (!f) { say("Could not read the book's state. Try again.", true); return; }
    const missing = f.shots - f.keyframes;
    if (!missing && f.unreviewed_with_picture) { say(`Every shot has a picture. ${f.unreviewed_with_picture} are waiting for a yes or a no: say no to the ones to make again.`, true); nav(ID.indexOf("storyboard")); return; }
    const model = $("kfmodel").value;
    if (!model) { say("Choose the keyframe image model first (Video and Audio card).", true); return; }
    try {                                                    // old pictures of the same shots first: no GPU time for pictures you already have
      const m = await api("/api/auto_assign_pictures", { project: proj(), model });
      if (m.matched.length && !m.still_missing.length) {
        say(`${m.matched.length} old picture(s) were put back on their shots, so no new picture is needed. Say yes or no to them on the storyboard.`, true);
        await refresh(); nav(ID.indexOf("storyboard")); return;
      }
      if (m.matched.length) await refresh();
    } catch (e) { say(e.message, true); return; }
    if (f.rejected_with_picture) {
      try { const r = await api("/api/review", { project: proj(), action: "reroll_rejected", start: 1, end: f.shots, kind: "keyframe", model }); say(`Making ${r.rerolled} picture(s) again...`); }
      catch (e) { say(e.message, true); return; }
    }
    const g = (data && data.facts) || f;
    if (g.keyframes >= g.shots && !g.rejected_with_picture) { say(`Every shot already has a picture (${g.keyframes} of ${g.shots}).`); return; }
    const waiting = g.unreviewed_with_picture ? ` ${g.unreviewed_with_picture} picture(s) already made still wait for a yes or a no on the storyboard; they are not made again.` : "";
    say(`Making the pictures for the ${g.shots - g.keyframes + (g.rejected_with_picture || 0)} shot(s) that need one. Watch the log.` + waiting);
    runOnly("movie", ["keyframes"], false, "Make the pictures", say);
  }
  window.flowMakeStills = makeStills;
  const SPECIAL = {
    approve: ["Approve the screenplay", () => $("spApprove").click()],
    stills: ["Make the pictures", () => makeStills()],
    approveRest: ["Say yes to the rest", () => $("sbApproveRest").click()],
    getPictures: ["Get results: pictures", () => window.getResults && window.getResults("keyframes", "", t => say(t))],
    getVideo: ["Get results: video", () => window.getResults && window.getResults("video", "", t => say(t))],
    getSound: ["Get results: sound", () => window.getResults && window.getResults("audio", "", t => say(t))],
  };
  function actions(s) {
    const box = $("pathActions"); box.textContent = "";
    for (const k of s[5]) {
      const [label, fn] = SPECIAL[k] ? SPECIAL[k] : [RUN[k][0], () => runOnly(RUN[k][1], RUN[k][2], RUN[k][3], RUN[k][0])];
      const b = document.createElement("button"); b.type = "button"; b.className = "btn btn--primary path-btn"; b.textContent = label; b.dataset.run = k;
      b.addEventListener("click", fn);
      box.append(b);
    }
    if (ID[current] === "keyframes") {                        // the picture maker, here as well as in its card
      const lab = document.createElement("label"); lab.className = "f"; lab.htmlFor = "pathKf"; lab.textContent = "Picture maker";
      const sel = document.createElement("select"); sel.id = "pathKf"; sel.innerHTML = $("kfmodel").innerHTML; sel.value = $("kfmodel").value;
      sel.addEventListener("change", () => { $("kfmodel").value = sel.value; $("kfmodel").dispatchEvent(new Event("change")); });
      const wrap = document.createElement("span"); wrap.className = "path-pick"; wrap.append(lab, sel); box.prepend(wrap);
    }
  }

  // ---- what is running: one strip that follows the shared job log
  const bar = document.getElementById("flowActivity"), actLog = document.getElementById("flowLog"), actState = document.getElementById("flowState");
  let since = -1, watching = false;
  function activity(text, bad) { if (!bar) return; bar.classList.remove("hidden"); actState.textContent = text; actState.className = bad ? "err" : "warn"; }
  async function watch() {
    if (watching || !bar) return;
    watching = true;
    let was = false;
    try {
      for (let quiet = 0; quiet < 3;) {
        const j = await api(`/api/log?since=${since < 0 ? 1e9 : since}`);
        since = j.next;
        if (j.lines.length) { actLog.textContent = (actLog.textContent + "\n" + j.lines.join("\n")).split("\n").slice(-60).join("\n").trim(); actLog.scrollTop = actLog.scrollHeight; }
        document.querySelectorAll(".path-btn").forEach(b => { b.disabled = !!j.running; });
        document.getElementById("flowStop").disabled = !j.running;
        if (j.running) { was = true; activity("Working on it: " + (j.current || "a step") + (j.queued ? ` (${j.queued} waiting)` : "")); quiet = 0; }
        else { quiet++; if (quiet === 1 && was) { activity("Finished. Look at the log below if something went wrong."); refresh(); } }
        await new Promise(r => setTimeout(r, 2000));
      }
    } catch (e) { activity("Lost the connection to the Studio.", true); }
    watching = false;
  }
  window.flowWatch = watch;
  document.getElementById("flowStop")?.addEventListener("click", () => api("/api/stop", {}).then(() => activity("Stopping...")).catch(e => activity(e.message, true)));

  // ---- drawing
  function paint() {
    const reach = reachable(), rev = (data && data.revisit) || [];
    list.querySelectorAll("button").forEach((b, i) => {
      const st = stepState(i);
      b.classList.toggle("active", on && i === current);
      b.classList.toggle("done", !!st.done && i !== current);
      b.classList.toggle("locked", i > reach);
      b.classList.toggle("again", rev.includes(ID[i]));
      b.disabled = i > reach;
      b.title = i > reach ? "Finish the steps before this one first" : rev.includes(ID[i]) ? "Look at this step again" : "";
      if (on && i === current) b.setAttribute("aria-current", "step"); else b.removeAttribute("aria-current");
    });
    const st = stepState(current), s = STEPS[current];
    const againHere = rev[0] === ID[current];
    say(st.todo ? "To do now: " + st.todo : againHere ? "This step was changed by a later one. Check it, then press Next." : st.done ? "This step is done. Press Next." : "", !!st.todo && !st.ok);
    const box = $("pathAlerts"); box.textContent = "";
    for (const a of (data && data.alerts) || []) {
      const p = document.createElement("p"); p.className = "path-alert"; p.textContent = a.text + " ";
      const i = ID.indexOf(a.step);
      if (i >= 0 && i !== current && i <= reach) { const b = document.createElement("button"); b.type = "button"; b.className = "btn btn--ghost"; b.textContent = "Go there"; b.addEventListener("click", () => go(i)); p.append(b); }
      box.append(p);
    }
    const next = $("flowNext");
    const last = current === STEPS.length - 1;
    next.disabled = last || !st.ok;
    next.textContent = last ? "This is the last step" : `Next: ${STEPS[current + 1][1]} →`;
    next.title = st.ok ? "" : st.todo;
    $("flowBack").disabled = current === 0;
    $("flowPos").textContent = `Step ${current + 1} of ${STEPS.length}`;
  }
  function render() {
    document.body.classList.toggle("flow", on);
    document.body.dataset.step = on ? ID[current] : "";
    toggle.textContent = on ? "All tabs" : "Film path";
    list.classList.toggle("hidden", !on);
    document.getElementById("flowFoot").classList.toggle("hidden", !on);
    document.getElementById("flowAbout").classList.add("hidden");
    const s = STEPS[current];
    $("pathCount").textContent = `Step ${current + 1} of ${STEPS.length}`;
    $("pathTitle").textContent = s[1];
    $("pathAbout").textContent = s[2];
    const showCards = on ? s[3].map(find).filter(Boolean) : [], moreCards = on ? s[4].map(find).filter(Boolean) : [];
    const keep = new Set([...showCards, ...moreCards]);
    for (const c of [...away.keys()]) if (!keep.has(c)) putBack(c);
    showCards.forEach(c => pull(c, shown));
    moreCards.forEach(c => pull(c, more));
    more.classList.toggle("hidden", !moreCards.length);
    if (on) actions(s);
    try { localStorage.setItem("flowMode", on ? "on" : "off"); localStorage.setItem("pathStep", String(current)); } catch (e) { /* not remembered */ }
    paint();
    if (on) enter(ID[current]);
    document.dispatchEvent(new CustomEvent("flow-render", { detail: { screen: s[1], step: ID[current], on } }));
  }
  function enter(id) {                                       // fresh data for the cards of the step just opened
    if (id === "screenplay" && typeof spLoad === "function") spLoad();
    if (id === "storyboard" && $("sbMovie").value) $("sbLoad").click();
  }
  function go(i) {
    i = Math.max(0, Math.min(STEPS.length - 1, i));
    if (i > reachable()) { say(`Finish "${STEPS[reachable()][1]}" first.`, true); return false; }
    current = i; on = true; render(); window.scrollTo(0, 0);
    return true;
  }
  async function next() {
    const st = stepState(current);
    if (!st.ok) { say("To do now: " + st.todo, true); return; }
    const rev = (data && data.revisit) || [];
    if (rev[0] === ID[current]) {
      try { data = await api("/api/path_confirm", { project: proj(), step: ID[current] }); } catch (e) { say(e.message, true); return; }
    }
    current = Math.min(STEPS.length - 1, current + 1); render(); window.scrollTo(0, 0);
  }
  window.flowGo = idOrName => { const i = ID.includes(idOrName) ? ID.indexOf(idOrName) : STEPS.findIndex(s => s[1] === idOrName); return i >= 0 && go(i); };

  STEPS.forEach((s, i) => {
    const li = document.createElement("li"), b = document.createElement("button");
    b.type = "button"; b.className = "flow-nav__step"; b.dataset.flow = String(i + 1); b.dataset.step = s[0];
    const n = document.createElement("span"); n.className = "flow-nav__num"; n.textContent = String(i + 1);
    b.append(n, document.createTextNode(" " + s[1]));
    b.addEventListener("click", () => go(i));
    li.append(b); list.append(li);
  });
  $("flowBack").addEventListener("click", () => go(current - 1));
  $("flowNext").addEventListener("click", next);
  toggle.addEventListener("click", () => { on = !on; render(); });
  $("proj").addEventListener("change", () => { refresh().then(() => { if (current > reachable()) go(reachable()); }); });
  document.querySelectorAll("input[name=svc], #kuser, #gpu").forEach(e => e.addEventListener("change", paint));
  $("kuser").addEventListener("input", paint);
  // Changes made on the page (an approval, a verdict, a saved scene) change what the steps need: look again shortly after.
  let soon = null;
  document.addEventListener("click", e => { if (on && e.target.closest("button")) { clearTimeout(soon); soon = setTimeout(refresh, 900); } });

  // A main tab clicked from elsewhere shows the first step that has a card from that tab; an Advanced tab leaves the path.
  document.querySelectorAll(".tab-btn").forEach(b => b.addEventListener("click", () => {
    if (!on) return;
    const name = b.dataset.tab;
    if (!MAIN_PANELS.includes(name)) { on = false; render(); return; }
    if (cardsOf(STEPS[current]).some(c => homePanel.get(c) === name)) return;
    const i = STEPS.findIndex(s => cardsOf(s).some(c => homePanel.get(c) === name));
    if (i >= 0 && i <= reachable()) { current = i; render(); }
  }));
  // The rail at the top: a step goes to the path step that has its card.
  window.flowGoTo = targetId => {
    if (!on) return false;
    const card = targetId && document.getElementById(targetId);
    if (!card) return false;
    const i = STEPS.findIndex(s => cardsOf(s).includes(card));
    if (i < 0) return false;
    if (!go(i)) return true;
    card.scrollIntoView({ behavior: "smooth", block: "start" });
    return true;
  };
  // The Video and Audio card's own buttons: make the pictures (the same checks as the film path), the video or the sound, from right there.
  (function cardButtons() {
    const body = document.querySelector("#videoAudioCard .card__body");
    if (!body) return;
    const row = document.createElement("div"); row.className = "va-make";
    const st = document.createElement("span"); st.className = "warn"; st.setAttribute("role", "status"); st.setAttribute("aria-live", "polite");
    const tell = (t, bad) => { st.textContent = t; st.className = bad ? "err" : "warn"; };
    const add = (label, fn, cls) => { const b = document.createElement("button"); b.type = "button"; b.className = cls; b.textContent = label; b.addEventListener("click", fn); row.append(b); return b; };
    add("Make the keyframes", () => makeStills(tell), "btn btn--primary").id = "vaMakeStills";
    add("Make the video", () => { tell("Making the video for the movies chosen in Which Movies. Watch the log."); runOnly("movie", ["video"], false, "Make the video", tell); }, "btn btn--secondary").id = "vaMakeVideo";
    add("Make the sound", () => { tell("Making the sound. Watch the log."); runOnly("movie", ["audio"], false, "Make the sound", tell); }, "btn btn--secondary").id = "vaMakeSound";
    row.append(st);
    body.prepend(row);
  })();
  window.flowRefresh = refresh;
  setInterval(() => { if (on && !document.hidden) refresh(); }, 5000);      // the book list loads after this script, and jobs finish on their own
  window.flowStep = () => ID[current];
  render();
  refresh().then(() => { if (current > reachable()) go(reachable()); });
  watch();
})();
