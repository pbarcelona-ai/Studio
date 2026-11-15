// ===== Pizazz: hero video, artwork banners, Library tab, Compare tab, effects switch, confetti =====
(function () {
  const fileUrl = f => "/file/" + String(f).split("/").map(encodeURIComponent).join("/") + "?t=" + TOKEN;
  const esc = s => escapeHtml(String(s == null ? "" : s));
  const fx = { on: localStorage.getItem("pzFx") !== "off" };

  // ---- effects switch (also off automatically with the OS "reduce motion" setting, through the CSS)
  function applyFx() {
    document.body.classList.toggle("fx-off", !fx.on);
    $("fxToggle").setAttribute("aria-pressed", String(fx.on));
    const v = document.querySelector(".hero-video");
    if (v && v.src) { if (fx.on) v.play().catch(() => {}); else v.pause(); }
  }
  $("fxToggle").onclick = () => { fx.on = !fx.on; localStorage.setItem("pzFx", fx.on ? "on" : "off"); applyFx(); };

  // ---- the banner logo is the app icon (the same picture as the browser tab icon)
  const fav = document.querySelector('link[rel="icon"][sizes="64x64"]');
  if (fav) $("brandLogo").src = fav.href;

  // ---- artwork from your own results: a muted loop behind the header and a picture strip on every tab
  async function loadShowcase() {
    let s;
    try { s = await api("/api/showcase"); } catch (e) { return; }                  // the page works fine without artwork
    const v = document.querySelector(".hero-video");
    if (s.hero && v) {
      v.src = fileUrl(s.hero);
      v.addEventListener("loadeddata", () => v.classList.add("on"), { once: true });
      if (fx.on) v.play().catch(() => {});
    }
    document.querySelectorAll(".tab-panel").forEach((p, i) => {
      if (p.querySelector(":scope > .tab-art")) return;
      const btn = document.querySelector('.tab-btn[data-tab="' + p.id.replace("panel-", "") + '"]');
      const d = document.createElement("div");
      d.className = "tab-art"; d.setAttribute("role", "presentation");
      if (s.art && s.art.length) d.style.backgroundImage = "url('" + fileUrl(s.art[i % s.art.length]).replace(/'/g, "%27") + "')";
      const t = document.createElement("span");
      t.textContent = btn ? btn.textContent.trim() : "";
      d.appendChild(t);
      p.insertBefore(d, p.firstChild);
    });
  }

  // ---- confetti when a run finishes
  window.pzConfetti = function () {
    if (!fx.on || matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    let c = $("pzConfetti");
    if (!c) { c = document.createElement("canvas"); c.id = "pzConfetti"; c.setAttribute("aria-hidden", "true"); document.body.appendChild(c); }
    c.width = innerWidth; c.height = innerHeight;
    const g = c.getContext("2d"), colours = ["#b9f53c", "#ff546e", "#8b5cf6", "#facc15", "#38bdf8"];
    const ps = Array.from({ length: 110 }, () => ({ x: innerWidth / 2 + (Math.random() - .5) * 200, y: innerHeight * .35, vx: (Math.random() - .5) * 14, vy: -Math.random() * 12 - 3,
      s: 4 + Math.random() * 5, r: Math.random() * 6, vr: (Math.random() - .5) * .4, col: colours[(Math.random() * colours.length) | 0] }));
    const t0 = performance.now();
    (function frame(t) {
      const age = t - t0;
      g.clearRect(0, 0, c.width, c.height);
      ps.forEach(p => { p.vy += .35; p.x += p.vx; p.y += p.vy; p.r += p.vr; g.save(); g.translate(p.x, p.y); g.rotate(p.r); g.fillStyle = p.col; g.globalAlpha = Math.max(0, 1 - age / 1800); g.fillRect(-p.s / 2, -p.s / 3, p.s, p.s * .6); g.restore(); });
      if (age < 1800) requestAnimationFrame(frame); else g.clearRect(0, 0, c.width, c.height);
    })(t0);
  };
  const baseStatus = pStatus;
  pStatus = function (text, cls) { baseStatus(text, cls); if (cls === "chip done") window.pzConfetti(); };

  // ---- lightbox
  const lb = document.createElement("div");
  lb.id = "pzLightbox"; lb.setAttribute("role", "dialog"); lb.setAttribute("aria-modal", "true"); lb.setAttribute("aria-label", "Preview");
  document.body.appendChild(lb);
  // gallery: the pictures and clips of the grid that was clicked, so Previous / Next (and the arrow keys) walk through them; once 3D view is on it stays on
  let lbSet = [], lbPos = 0, want3d = false, lbSeq = 0;
  function gallerySet(scope) {
    return Array.from(scope.querySelectorAll(".pz-media[data-file]")).map(m => ({ file: m.dataset.file, kind: m.dataset.kind, cap: m.dataset.cap || "" }));
  }
  function openLightbox(file, kind, caption, scope) {
    lbSeq++;
    if (scope) { lbSet = gallerySet(scope); want3d = false; }
    lbPos = Math.max(0, lbSet.findIndex(x => x.file === file));
    const many = lbSet.length > 1;
    lb.innerHTML = (kind === "video" ? `<video src="${fileUrl(file)}" controls autoplay loop playsinline></video>` : `<img id="pzLbImg" src="${fileUrl(file)}" alt="">`) +
      `<p id="pzLbCap">${esc(caption)}</p><div class="pz-lb-actions">` + (many ? `<button type="button" id="pzPrev" aria-label="Previous">&#8592; Previous</button><span id="pzCount" aria-live="polite">${lbPos + 1} / ${lbSet.length}</span><button type="button" id="pzNext" aria-label="Next">Next &#8594;</button>` : "") + (kind === "image" ? `<button type="button" id="pz3d">3D view</button><button type="button" id="pzReview" title="Claude (or a local model when this computer has one) looks at the picture and judges it against its prompt">Review with AI</button><button type="button" id="pzDescribe" title="An AI looks at the picture and writes a video prompt that brings it to life">Video prompt from this picture</button>` : "") + `<button type="button" id="pzLbClose">Close</button></div><p id="pzAiOut" role="status" aria-live="polite"></p>`;
    lb.classList.add("open");
    $("pzLbClose").focus();
    $("pzLbClose").onclick = closeLightbox;
    if (many) { $("pzPrev").onclick = () => lbStep(-1); $("pzNext").onclick = () => lbStep(1); }
    if (kind === "image") { $("pz3d").onclick = () => toggle3d(file, caption); $("pzReview").onclick = () => aiReview(file, caption); $("pzDescribe").onclick = () => aiDescribe(file); }
  }

  // ---- AI looks at a picture: judge it against its prompt, or write a video prompt for it.
  // Claude by default. When this computer qualifies for a local model (the local engine is ready) that is used automatically; if the local model cannot do it, Claude steps in.
  function visionEngine() {
    const e = $("engine").value, L = ST.local_llm || {};
    if (L.ready) return { engine: "local", claude_model: e === "local" ? $("cmodel").value : (L.models || [])[0] || "" };
    if (e === "hf") return { engine: "hf", claude_model: ST.hf_vision_models.includes($("cmodel").value) ? $("cmodel").value : "" };
    if (e === "local") return { engine: "claude", claude_model: "sonnet" };         // chosen, but this computer does not qualify yet
    return { engine: e, claude_model: $("cmodel").value };
  }
  const VISION_NAME = { claude: "Claude", "fcc-claude": "Claude", codex: "Codex", "fcc-codex": "Codex", hf: "Hugging Face", local: "the local model" };
  async function visionCall(path, body) {
    const v = visionEngine();
    try { return { r: await api(path, { ...body, ...v }), via: VISION_NAME[v.engine] }; }
    catch (e) {
      if (v.engine !== "local") throw e;
      const r = await api(path, { ...body, engine: "claude", claude_model: "sonnet" });
      return { r, via: "Claude (the local model could not do it: " + e.message.slice(0, 120) + ")" };
    }
  }
  async function aiReview(file, caption) {
    const out = $("pzAiOut"), btn = $("pzReview"), prompt = caption.includes(" - ") ? caption.slice(caption.indexOf(" - ") + 3) : caption;
    btn.disabled = true; out.textContent = "The AI is looking at the picture...";
    try {
      const { r, via } = await visionCall("/api/review_result", { file, prompt });
      out.textContent = `Score ${r.score}/10: ${r.summary}` + (r.problems.length ? ` Problems: ${r.problems.join("; ")}.` : "") + ` (reviewed by ${via})`;
    } catch (e) { out.textContent = e.message; }
    btn.disabled = false;
  }
  async function aiDescribe(file) {
    const out = $("pzAiOut"), btn = $("pzDescribe"), first = promptTargets().find(t => t.kind === "video");
    btn.disabled = true; out.textContent = "The AI is looking at the picture...";
    try {
      const { r, via } = await visionCall("/api/describe_image", { file, kind: "video", target: first ? first.model : "" });
      const box = $("ptext"); box.value = (box.value.trim() ? box.value.trim() + "\n" : "") + r.prompt;
      box.dispatchEvent(new Event("input", { bubbles: true }));
      out.textContent = "Added to Single Prompts (written by " + via + "): " + r.prompt;
    } catch (e) { out.textContent = e.message; }
    btn.disabled = false;
  }

  // ---- 3D view: the picture is shifted by a depth map (made on this computer by the Studio) as the mouse moves, so near things slide over far things
  const loadImage = url => new Promise((res, rej) => { const i = new Image(); i.onload = () => res(i); i.onerror = () => rej(new Error("could not load " + url.split("?")[0])); i.src = url; });
  async function loadDepth(file) {
    const r = await fetch(depthUrl(file));
    if (!r.ok) { let m = r.statusText; try { m = (await r.json()).error || m; } catch (e) {} throw new Error(m); }
    return loadImage(URL.createObjectURL(await r.blob()));
  }
  function startParallax(canvas, colour, depth) {
    const gl = canvas.getContext("webgl", { antialias: true });
    if (!gl) throw new Error("3D view needs WebGL, which this browser does not have");
    const sh = (type, src) => { const s = gl.createShader(type); gl.shaderSource(s, src); gl.compileShader(s); if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s)); return s; };
    const prog = gl.createProgram();
    gl.attachShader(prog, sh(gl.VERTEX_SHADER, "attribute vec2 p; varying vec2 v; void main(){ v = vec2(p.x * .5 + .5, .5 - p.y * .5); gl_Position = vec4(p, 0., 1.); }"));
    gl.attachShader(prog, sh(gl.FRAGMENT_SHADER, `precision mediump float; varying vec2 v; uniform sampler2D c, d; uniform vec2 m;
      void main() {
        vec2 u = (v - .5) / 1.07 + .5;                       // zoom in a little so the edges never show
        float z = texture2D(d, u).r;
        vec2 u2 = u - m * (z - .5) * .045;                   // first guess: near pixels move further than far ones
        float z2 = texture2D(d, u2).r;
        gl_FragColor = texture2D(c, clamp(u - m * (z2 - .5) * .045, 0., 1.));
      }`));
    gl.linkProgram(prog); gl.useProgram(prog);
    const buf = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, buf);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW);
    const loc = gl.getAttribLocation(prog, "p"); gl.enableVertexAttribArray(loc); gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);
    [[colour, 0, "c"], [depth, 1, "d"]].forEach(([img, unit, name]) => {
      const t = gl.createTexture(); gl.activeTexture(gl.TEXTURE0 + unit); gl.bindTexture(gl.TEXTURE_2D, t);
      gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, false);
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, img);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR); gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE); gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
      gl.uniform1i(gl.getUniformLocation(prog, name), unit);
    });
    const mLoc = gl.getUniformLocation(prog, "m");
    let tx = 0, ty = 0, cx = 0, cy = 0, last = 0;
    const move = e => { tx = (e.clientX / innerWidth - .5) * 2; ty = (e.clientY / innerHeight - .5) * 2; last = performance.now(); };
    lb.addEventListener("pointermove", move);
    (function frame(t) {
      if (!canvas.isConnected) { lb.removeEventListener("pointermove", move); return; }
      if (t - last > 2500) { tx = Math.sin(t / 1700) * .8; ty = Math.cos(t / 2300) * .45; }          // nobody is moving the mouse: sway by itself
      cx += (tx - cx) * .08; cy += (ty - cy) * .08;
      gl.viewport(0, 0, canvas.width, canvas.height);
      gl.uniform2f(mLoc, cx, cy);
      gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
      requestAnimationFrame(frame);
    })(0);
  }
  async function toggle3d(file, caption) {
    const btn = $("pz3d"), existing = lb.querySelector("canvas");
    if (existing) { want3d = false; openLightbox(file, "image", caption); return; }       // back to the flat picture
    const seq = lbSeq;
    btn.disabled = true; btn.textContent = "Making depth map...";
    try {
      const [colour, depth] = await Promise.all([loadImage(fileUrl(file)), loadDepth(file)]);
      if (seq !== lbSeq) return;                                                           // moved on to another picture while this one was loading
      const cv = document.createElement("canvas");
      const aspect = colour.naturalWidth / colour.naturalHeight, maxW = innerWidth * .92, maxH = innerHeight * .74;
      const w = Math.min(maxW, maxH * aspect), h = w / aspect, dpr = Math.min(devicePixelRatio || 1, 2);
      cv.width = Math.round(w * dpr); cv.height = Math.round(h * dpr); cv.style.width = w + "px"; cv.style.height = h + "px"; cv.style.borderRadius = "12px";
      cv.setAttribute("role", "img"); cv.setAttribute("aria-label", "3D view: move the mouse to look around");
      const flat = $("pzLbImg"); flat.replaceWith(cv);
      startParallax(cv, colour, depth);
      btn.textContent = "Flat view"; $("pzLbCap").textContent = "Move the mouse to look around. " + caption;
      want3d = true;
      const nx = lbSet.length > 1 ? lbSet[(lbPos + 1) % lbSet.length] : null;            // make the next picture's depth map ahead of time
      if (nx && nx.kind === "image") fetch(depthUrl(nx.file)).catch(() => {});
    } catch (e) {
      if (seq !== lbSeq) return;
      want3d = false;
      showToast("3D view: " + e.message, "error");
      if (lb.querySelector("canvas")) openLightbox(file, "image", caption);            // the empty canvas has replaced the picture: put the flat picture back
      else { btn.textContent = "3D view"; btn.disabled = false; }
      return;
    }
    btn.disabled = false;
  }
  function lbStep(d) {
    if (lbSet.length < 2) return;
    const it = lbSet[(lbPos + d + lbSet.length) % lbSet.length];
    openLightbox(it.file, it.kind, it.cap);
    if (want3d && it.kind === "image") toggle3d(it.file, it.cap);
  }
  function closeLightbox() { lbSeq++; lb.classList.remove("open"); lb.innerHTML = ""; }
  lb.addEventListener("click", e => { if (e.target === lb) closeLightbox(); });
  document.addEventListener("keydown", e => {
    if (!lb.classList.contains("open")) return;
    if (e.key === "Escape") closeLightbox();
    else if (e.key === "ArrowRight") { e.preventDefault(); lbStep(1); }
    else if (e.key === "ArrowLeft") { e.preventDefault(); lbStep(-1); }
  });

  // if a thumbnail cannot be made (no Pillow, unreadable file) fall back to the full file, once
  document.addEventListener("error", e => { const i = e.target; if (i && i.tagName === "IMG" && i.dataset && i.dataset.full && !i.dataset.fell) { i.dataset.fell = "1"; i.src = i.dataset.full; } }, true);

  // hover to play a clip tile: the video is created only while the pointer is over it
  function wireHover(root) {
    root.querySelectorAll(".pz-media[data-kind='video']").forEach(m => {
      const tile = m.closest(".pz-tile");
      tile.addEventListener("mouseenter", () => {
        if (!fx.on || m.querySelector("video") || !m.dataset.file) return;
        const v = document.createElement("video");
        v.src = fileUrl(m.dataset.file); v.muted = true; v.loop = true; v.playsInline = true; v.autoplay = true;
        m.insertBefore(v, m.firstChild); v.play().catch(() => {});
      });
      tile.addEventListener("mouseleave", () => { const v = m.querySelector("video"); if (v) { v.pause(); v.remove(); } });
    });
  }
  const depthUrl = f => "/depth/" + String(f).split("/").map(encodeURIComponent).join("/") + "?t=" + TOKEN;
  // v: the file's version (size and time, from the server); it changes when a picture is swapped, so the browser fetches the new one at once
  const thumbUrl = (f, v) => "/thumb/" + String(f).split("/").map(encodeURIComponent).join("/") + "?t=" + TOKEN + (v ? "&v=" + encodeURIComponent(v) : "");
  // grids show small thumbnails (a clip shows one of its frames); the full file loads only on hover (clips) or click (preview)
  const mediaHtml = (file, kind, extra, v) => `<img src="${thumbUrl(file, v)}" alt="" loading="lazy" decoding="async" data-full="${fileUrl(file)}">` +
    (kind === "video" ? '<span class="pz-play" aria-hidden="true">&#9654;</span>' : "") + (extra || "");

  // ---- Library tab
  let lib = [], libCat = "All", libKind = "all";
  function kindButtons(id, current, onPick) {
    $(id).innerHTML = [["all", "All"], ["video", "Video"], ["image", "Image"]].map(([v, l]) =>
      `<button type="button" class="pz-chip" data-kind="${v}" aria-pressed="${current === v}">${l}</button>`).join(" ");
    $(id).querySelectorAll("button").forEach(b => b.onclick = () => onPick(b.dataset.kind));
  }
  function renderLibrary() {
    const q = $("libSearch").value.trim().toLowerCase();
    const cats = ["All", ...new Set(lib.map(t => t.category))];
    $("libChips").innerHTML = cats.map(c => `<button type="button" class="pz-chip" data-cat="${esc(c)}" aria-pressed="${c === libCat}">${esc(c)}</button>`).join("");
    $("libChips").querySelectorAll("button").forEach(b => b.onclick = () => { libCat = b.dataset.cat; renderLibrary(); });
    kindButtons("libKinds", libKind, k => { libKind = k; renderLibrary(); });
    const shown = lib.filter(t => (libCat === "All" || t.category === libCat) && (libKind === "all" || t.kind === libKind) &&
      (!q || (t.title + " " + t.prompt + " " + t.category).toLowerCase().includes(q)));
    $("libEmpty").hidden = shown.length > 0;
    $("libGrid").innerHTML = shown.map(t => `<article class="pz-tile">
      <div class="pz-media" data-file="${esc(t.sample ? t.sample.file : "")}" data-kind="${esc(t.sample ? t.sample.kind : "")}" data-cap="${esc(t.title + " - " + t.prompt)}">
        ${t.sample ? mediaHtml(t.sample.file, t.sample.kind) : (t.kind === "video" ? "🎬" : "🖼")}
        <span class="pz-badge">${esc(t.kind)}</span>${t.sample ? `<span class="pz-badge right">${esc(t.sample.model)}</span>` : ""}
      </div>
      <div class="pz-body"><span class="pz-cat">${esc(t.category)}</span><span class="pz-title">${esc(t.title)}</span><span class="pz-prompt">${esc(t.prompt)}</span>
        <div class="pz-row"><button type="button" data-use="${esc(t.id)}">Use this</button><button type="button" data-copy="${esc(t.id)}">Copy</button></div></div>
    </article>`).join("");
    wireHover($("libGrid"));
  }
  $("libGrid").addEventListener("click", e => {
    const use = e.target.closest("[data-use]"), copy = e.target.closest("[data-copy]"), media = e.target.closest(".pz-media");
    const btn = use || copy, t = lib.find(x => x.id === (btn ? (btn.dataset.use || btn.dataset.copy) : ""));
    if (use && t) {
      $("ptext").value = t.prompt;
      $("ptext").dispatchEvent(new Event("input", { bubbles: true }));
      document.querySelector('[data-tab="prompts"]').click();
      showToast(`Prompt "${t.title}" is in Single Prompts. Tick a ${t.kind} model on the Models tab, then Generate.`, "info");
    } else if (copy && t) {
      (navigator.clipboard ? navigator.clipboard.writeText(t.prompt) : Promise.reject()).then(() => showToast("Prompt copied", "info"), () => showToast("Could not copy; select the text instead", "error"));
    } else if (media && media.dataset.file) {
      openLightbox(media.dataset.file, media.dataset.kind, media.dataset.cap, (media.closest(".pz-tile") || media).parentElement);
    }
  });
  $("libSearch").addEventListener("input", renderLibrary);
  async function loadLibrary() {
    try { lib = (await api("/api/library")).templates; } catch (e) { $("libGrid").innerHTML = `<p class="err">${esc(e.message)}</p>`; return; }
    renderLibrary();
  }

  // ---- Compare tab
  let cmp = [], cmpIdx = 0, cmpKind = "all";
  const stars = n => [1, 2, 3, 4, 5].map(i => `<button type="button" data-star="${i}" class="${i <= n ? "on" : ""}" aria-label="${i} star${i > 1 ? "s" : ""}">★</button>`).join("");
  function renderCompare() {
    const g = cmp[cmpIdx];
    $("cmpEmpty").hidden = !!g;
    $("cmpPromptText").value = g ? g.text : "";
    if (!g) { $("cmpGrid").innerHTML = ""; $("cmpSummary").textContent = ""; $("cmpKinds").innerHTML = ""; return; }
    kindButtons("cmpKinds", cmpKind, k => { cmpKind = k; renderCompare(); });
    const sort = $("cmpSort").value, keepOnly = $("cmpKeepOnly").checked;
    const items = g.items.filter(i => (cmpKind === "all" || i.kind === cmpKind) && (!keepOnly || i.keep))
      .sort((a, b) => sort === "stars" ? (b.stars - a.stars) || a.model.localeCompare(b.model)
        : sort === "minutes" ? ((a.minutes == null ? 1e9 : a.minutes) - (b.minutes == null ? 1e9 : b.minutes)) : a.model.localeCompare(b.model));
    const kept = g.items.filter(i => i.keep);
    $("cmpSummary").textContent = `${g.items.length} results for this prompt; ${kept.length} kept` + (kept.length ? `: ${kept.map(i => i.model).join(", ")}` : "") + ".";
    $("cmpGrid").innerHTML = items.map(i => `<article class="pz-tile ${i.keep ? "kept" : ""}" data-file="${esc(i.file)}">
      <div class="pz-media" data-file="${esc(i.file)}" data-kind="${esc(i.kind)}" data-cap="${esc(i.model + " - " + g.text)}">
        ${mediaHtml(i.file, i.kind)}<span class="pz-badge">${esc(i.kind)}</span>${i.minutes != null ? `<span class="pz-badge right">${esc(i.minutes)} min</span>` : ""}
      </div>
      <div class="pz-body"><span class="pz-title">${esc(i.model)}</span>
        <div class="pz-row"><span class="pz-stars" role="group" aria-label="Rating for ${esc(i.model)}">${stars(i.stars)}</span>
          <button type="button" class="pz-keep ${i.keep ? "on" : ""}" data-keep="1" aria-pressed="${i.keep}">${i.keep ? "Kept" : "Keep"}</button></div></div>
    </article>`).join("");
    wireHover($("cmpGrid"));
  }
  async function rate(file, starsN, keep) {
    const g = cmp[cmpIdx], it = g.items.find(x => x.file === file);
    try { await api("/api/rate", { key: file, stars: starsN, keep }); } catch (e) { showToast(e.message, "error"); return; }
    it.stars = starsN; it.keep = keep; renderCompare();
  }
  $("cmpGrid").addEventListener("click", e => {
    const tile = e.target.closest(".pz-tile"); if (!tile) return;
    const file = tile.dataset.file, g = cmp[cmpIdx], it = g.items.find(x => x.file === file); if (!it) return;
    const star = e.target.closest("[data-star]");
    if (star) { const n = Number(star.dataset.star); rate(file, n === it.stars ? 0 : n, it.keep); return; }
    if (e.target.closest("[data-keep]")) { rate(file, it.stars, !it.keep); return; }
    const media = e.target.closest(".pz-media");
    if (media) openLightbox(media.dataset.file, media.dataset.kind, media.dataset.cap, $("cmpGrid"));
  });
  $("cmpCopy").addEventListener("click", () => {
    const text = $("cmpPromptText").value;
    if (!text) { showToast("No prompt to copy", "error"); return; }
    const fallback = () => {                                   // older browsers and non-secure pages: select the box and use the copy command
      const box = $("cmpPromptText"); box.focus(); box.select();
      let ok = false; try { ok = document.execCommand("copy"); } catch (e) {}
      box.setSelectionRange(0, 0);
      showToast(ok ? "Prompt copied" : "Could not copy; select the text and press Cmd+C", ok ? "info" : "error");
    };
    if (navigator.clipboard && window.isSecureContext) navigator.clipboard.writeText(text).then(() => showToast("Prompt copied", "info"), fallback);
    else fallback();
  });
  ["cmpSort", "cmpKeepOnly"].forEach(id => $(id).addEventListener("change", renderCompare));
  $("cmpPrompt").addEventListener("change", () => { cmpIdx = Number($("cmpPrompt").value) || 0; renderCompare(); });
  async function loadCompare() {
    try { cmp = (await api("/api/compare")).prompts; } catch (e) { $("cmpGrid").innerHTML = `<p class="err">${esc(e.message)}</p>`; return; }
    cmpIdx = Math.min(cmpIdx, Math.max(cmp.length - 1, 0));
    $("cmpPrompt").innerHTML = cmp.map((g, i) => `<option value="${i}">${esc(g.items.length + " results: " + g.text.slice(0, 90))}</option>`).join("");
    $("cmpPrompt").value = String(cmpIdx);
    renderCompare();
  }


  // ---- Single Prompts: one-click camera moves and looks, added to (or removed from) every prompt line
  const CAMERA = [["Slow zoom in", "slow zoom in"], ["Zoom out", "slow zoom out"], ["Pan left", "slow pan left"], ["Pan right", "slow pan right"], ["Dolly in", "slow dolly in"],
    ["Tracking shot", "smooth tracking shot"], ["Orbit", "camera slowly orbits the subject"], ["Handheld", "handheld camera"], ["Aerial drift", "slow aerial drift"],
    ["Crane up", "crane shot rising up"], ["Low angle", "low angle shot"], ["Static", "locked-off static camera"]];
  const LOOK = [["Cinematic", "cinematic lighting"], ["Film grain", "35mm film grain"], ["Shallow focus", "shallow depth of field"], ["Golden hour", "golden hour light"],
    ["Moody", "moody low-key lighting"], ["Hyper-real", "hyper-realistic"], ["Slow motion", "slow motion"], ["Anamorphic", "anamorphic lens"]];
  const phraseRe = p => new RegExp("(?:,\\s*|^\\s*)" + p.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + "(?=\\s*(?:,|\\.|$))", "i");
  function lineHas(line, p) { return line.toLowerCase().includes(p.toLowerCase()); }
  function addPhrase(line, p) { const t = line.replace(/\s+$/, ""); return /[.!?]$/.test(t) ? t.slice(0, -1) + ", " + p + t.slice(-1) : t + ", " + p; }
  function removePhrase(line, p) { return line.replace(phraseRe(p), "").replace(/^\s*,\s*/, "").replace(/\s+$/, ""); }
  function toggleChip(p) {
    const box = $("ptext"), lines = box.value.split("\n"), real = lines.filter(l => l.trim());
    if (!real.length) { showToast("Type a prompt first", "info"); box.focus(); return; }
    const allHave = real.every(l => lineHas(l, p));
    box.value = lines.map(l => !l.trim() ? l : (allHave ? removePhrase(l, p) : (lineHas(l, p) ? l : addPhrase(l, p)))).join("\n");
    box.dispatchEvent(new Event("input", { bubbles: true }));
  }
  function renderChips() {
    const lines = $("ptext").value.split("\n").filter(l => l.trim());
    for (const [id, list] of [["chipCamera", CAMERA], ["chipLook", LOOK]]) {
      $(id).innerHTML = list.map(([label, p]) => `<button type="button" class="pz-chip" data-phrase="${esc(p)}" aria-pressed="${lines.length > 0 && lines.every(l => lineHas(l, p))}" title="Adds: ${esc(p)}">${esc(label)}</button>`).join("");
    }
  }
  $("pzChips").addEventListener("click", e => { const b = e.target.closest("[data-phrase]"); if (b) toggleChip(b.dataset.phrase); });
  $("ptext").addEventListener("input", renderChips);
  renderChips();

  document.querySelector('[data-tab="library"]').addEventListener("click", loadLibrary);
  document.querySelector('[data-tab="compare"]').addEventListener("click", loadCompare);

  // ---- Storyboard (Movies tab): one card per shot of a movie, with its keyframe, narration and the clips made from it
  let sbProj = null;
  window.sbFillMovies = function () {
    const p = cur(), sel = $("sbMovie"), keep = sel.value;
    if (sbProj !== (p ? p.slug : null)) { sbProj = p ? p.slug : null; $("sbGrid").innerHTML = ""; $("sbStatus").textContent = ""; }   // another book: old cards would mislead
    const list = (p && p.movies && p.movies.shots) || [];
    sel.innerHTML = list.length ? list.map(m => `<option value="${m.rows[0]}-${m.rows[1]}">Movie ${m.id}: rows ${m.rows[0]}-${m.rows[1]}</option>`).join("")
                                : '<option value="">no per-shot movies planned yet</option>';
    if ([...sel.options].some(o => o.value === keep)) sel.value = keep;
    $("sbLoad").disabled = !list.length;
  };
  // Takes: "Retake" keeps the current picture or clip as a take and gives the shot a new seed; run that shot again for a new version.
  // Each saved take can be previewed, and "Use" swaps it in (the version it replaces is kept as another take).
  const retakeBtn = (c, kind, model, label) => `<button type="button" class="pz-chip" data-retake="${kind}" data-model="${esc(model)}" data-n="${c.n}" title="Keep this version as a take and make a new one with a different seed">↻ ${esc(label)}</button>`;
  const kfModelOf = (c, kf) => (Object.entries(c.keyframes).find(([, f]) => f === kf) || [])[0] || $("sbKf").value || Object.keys(c.keyframes)[0] || "";
  // the pictures this shot has had (the one in use, then its takes) as small thumbnails: click one to put it on the shot straight away
  function picturesHtml(c, kf) {
    const model = kfModelOf(c, kf), takes = (c.takes || {})["keyframe:" + model] || [], proj = sbProj || $("proj").value;
    if (!takes.length) return "";
    const now = kf ? `<figure class="sb-pic sb-pic--now"><img src="${thumbUrl(proj + "/" + kf, c.ver && c.ver[kf])}" alt="The picture shot ${c.n} uses now" width="64" height="64"><figcaption>in use</figcaption></figure>` : "";
    const others = takes.map(f => {
      const k = (f.match(/-t(\d+)\.\w+$/) || [])[1];
      return `<figure class="sb-pic"><button type="button" class="sb-pic__use" data-take-use="${k}" data-kind="keyframe" data-model="${esc(model)}" data-n="${c.n}" title="Use this picture for shot ${c.n}" aria-label="Use take ${k} as the picture of shot ${c.n}">` +
        `<img src="${thumbUrl(proj + "/" + f, c.ver && c.ver[f])}" alt="" width="64" height="64" loading="lazy"></button>` +
        `<figcaption>take ${k} <button type="button" class="sb-pic__zoom" data-take-view="${esc(proj + "/" + f)}" data-kind="image" data-cap="${esc(model + " take " + k + " of shot " + c.n)}" aria-label="See take ${k} of shot ${c.n} bigger">🔍</button></figcaption></figure>`;
    }).join("");
    return `<div class="sb-pics" role="group" aria-label="Pictures of shot ${c.n}: click one to use it">${now}${others}</div>`;
  }
  // the clips' retake buttons and their saved takes
  function takesHtml(c) {
    let out = Object.keys(c.clips).map(m => retakeBtn(c, "clip", m, "Retake " + m)).join("");
    for (const [key, files] of Object.entries(c.takes || {})) {
      const [kind, model] = key.split(":");
      if (kind !== "clip") continue;
      out += files.map(f => {
        const k = (f.match(/-t(\d+)\.\w+$/) || [])[1];
        return `<span class="pz-row" style="gap:2px"><button type="button" class="pz-chip" data-take-view="${esc((sbProj || $("proj").value) + "/" + f)}" data-kind="video" data-cap="${esc(model + " take " + k + " of shot " + c.n)}">▶ ${esc(model)} take ${k}</button>` +
          `<button type="button" class="pz-chip" data-take-use="${k}" data-kind="${kind}" data-model="${esc(model)}" data-n="${c.n}">Use</button></span>`;
      }).join("");
    }
    return out ? `<div class="pz-row" style="flex-wrap:wrap;gap:6px">${out}</div>` : "";
  }
  async function takeAction(btn) {
    const proj = $("proj").value, st = $("sbStatus");
    const base = { project: proj, kind: btn.dataset.kind || btn.dataset.retake, model: btn.dataset.model, n: Number(btn.dataset.n) };
    try {
      if (btn.dataset.retake) {
        if (!confirm(`Keep this ${base.kind} as a take and clear shot ${base.n} so it can be made again with a new seed?`)) return;
        const r = await api("/api/retake", base);
        st.textContent = `Shot ${base.n}: saved as take ${r.saved_as}. Now ${r.next}.`;
      } else {
        await api("/api/pick_take", { ...base, take: Number(btn.dataset.takeUse) });
        st.textContent = `Shot ${base.n}: take ${btn.dataset.takeUse} is now the one in use.`;
      }
      const msg = st.textContent;
      await refreshCard(base.n);                      // only this card, so the new picture shows straight away
      st.textContent = msg;
    } catch (e) { st.textContent = e.message; }
  }
  let sbData = {};            // the cards on screen, by shot number
  // ---- clip lengths: per shot (a box with up/down arrows, and "Match narration"), and for the whole movie (server: /api/clip_length)
  const defaultSecs = () => Number($("clipsecs").value) || 4;
  function clipLenHtml(c) {
    const len = Number(c.seconds) || defaultSecs(), short = c.spoken > len + 0.25;
    return `<div class="pz-row clip-len" style="gap:6px;align-items:center;flex-wrap:wrap"><label class="f" for="sbLen-${c.n}" style="margin:0">Clip</label>` +
      `<input type="number" id="sbLen-${c.n}" data-len="${c.n}" min="1" step="0.5" value="${esc(c.seconds || "")}" placeholder="${defaultSecs()}" style="width:70px" aria-label="Clip length of shot ${c.n} in seconds"> s` +
      `<small class="${short ? "err" : "warn"}">${c.spoken ? `words take about ${c.spoken} s${short ? ": the clip is too short" : ""}` : "no words"}</small>` +
      `<button type="button" class="pz-chip" data-lenmatch="${c.n}" aria-label="Make shot ${c.n}'s clip as long as its narration">Match narration</button></div>`;
  }
  async function clipLen(body, msg) {
    const st = $("sbStatus");
    try {
      const r = await api("/api/clip_length", { project: $("proj").value, default_seconds: defaultSecs(), ...body });
      await loadStoryboard();
      if ($("sbCriticList").children.length) await runCritic(false);      // the critic's list shows the same lengths: refresh it too
      st.textContent = msg(r) + " Clips already made at the old length need making again.";
    } catch (e) { st.textContent = e.message; }
  }
  function movieTotal() {
    const cards = Object.values(sbData);
    const total = cards.reduce((a, c) => a + (Number(c.seconds) || defaultSecs()), 0), words = cards.reduce((a, c) => a + (c.spoken || 0), 0);
    $("sbMovieSecs").value = Math.round(total);
    $("sbMovieNote").textContent = cards.length ? `${cards.length} clips: ${Math.round(total)} s now (${(total / 60).toFixed(1)} min); the words take about ${Math.round(words)} s.` : "";
  }
  const movieRange = () => { const [start, end] = ($("sbMovie").value || "").split("-").map(Number); return start ? { start, end } : null; };
  $("sbMovieSet").addEventListener("click", () => {
    const r = movieRange(); if (!r) return;
    clipLen({ ...r, target_seconds: Number($("sbMovieSecs").value) }, x => `The movie is now about ${Math.round(x.total)} s (${(x.total / 60).toFixed(1)} min).`);
  });
  $("sbMatchAll").addEventListener("click", () => {
    const r = movieRange(); if (!r) return;
    clipLen({ ...r, match_narration: true }, x => `Every clip now fits its words: the movie is about ${Math.round(x.total)} s.`);
  });
  window.sbMovieTotal = movieTotal;
  // the clip length controls in a critic finding: a box with arrows and "Match narration", as on the cards; the critic runs again after a change
  // three grid cells (length box, words note, Match narration); a finding with no shot gets three empty cells, so every row's buttons line up
  function critLen(n, s) {
    const cell = (cls, html) => { const c = document.createElement("span"); c.className = cls; c.innerHTML = html; return c; };
    if (!s) return [cell("crit-cell", ""), cell("crit-cell", ""), cell("crit-cell", "")];
    const len = Number(s.seconds) || defaultSecs(), short = s.spoken > len + 0.25;
    return [cell("crit-cell clip-len", `<label class="f" for="crLen-${n}" style="display:inline;margin:0 4px 0 0">Clip</label>` +
                `<input type="number" id="crLen-${n}" data-crlen="${n}" min="1" step="0.5" value="${esc(s.seconds || "")}" placeholder="${defaultSecs()}" style="width:70px" aria-label="Clip length of shot ${n} in seconds"> s`),
            cell("crit-cell", `<small class="${short ? "err" : "warn"}">${s.spoken ? `words take about ${s.spoken} s` : "no words"}</small>`),
            cell("crit-cell", `<button type="button" class="pz-chip" data-crlenmatch="${n}" aria-label="Make shot ${n}'s clip as long as its narration">Match narration</button>`)];
  }
  async function critLenChange(body) {
    const st = $("sbStatus");
    try {
      const r = await api("/api/clip_length", { project: $("proj").value, default_seconds: defaultSecs(), ...body });
      await runCritic(false);                                // the finding goes away when the clip now fits
      if (Object.keys(sbData).length) await loadStoryboard();
      const s = r.shots[0];
      st.textContent = (s.seconds ? `Shot ${s.n}'s clip is now ${s.seconds} s.` : `Shot ${s.n} is back to the model's own length.`) + " " + st.textContent;
    } catch (e) { st.textContent = e.message; }
  }
  async function loadStoryboard() {
    const proj = $("proj").value, [start, end] = ($("sbMovie").value || "").split("-").map(Number);
    if (!proj || !start) return;
    $("sbStatus").textContent = "loading…";
    try {
      const r = await api(`/api/storyboard?project=${encodeURIComponent(proj)}&start=${start}&end=${end}`);
      const kfSel = $("sbKf"), keep = kfSel.value;
      kfSel.innerHTML = '<option value="">(newest)</option>' + r.keyframe_models.map(m => `<option value="${esc(m)}">${esc(m)}</option>`).join("");
      if (r.keyframe_models.includes(keep)) kfSel.value = keep;
      const pick = c => c.keyframes[kfSel.value] || Object.values(c.keyframes).pop();
      const withKf = r.cards.filter(pick).length;
      sbData = {}; r.cards.forEach(c => { sbData[c.n] = c; });
      $("sbGrid").innerHTML = r.cards.map(cardHtml).join("");
      movieTotal();
      const rv = r.review;
      $("sbStatus").textContent = `${r.cards.length} shot(s), ${withKf} with a keyframe; ${rv.approved} approved, ${rv.rejected} rejected, ${rv.pending} not reviewed` + (rv.ready ? " - all approved" : "") +
        (r.end - r.start + 1 < (end - start + 1) ? ` (first ${r.cards.length} shown)` : "");
    } catch (e) { $("sbGrid").innerHTML = ""; $("sbStatus").textContent = e.message; }
  }
  const pickKf = c => c.keyframes[$("sbKf").value] || Object.values(c.keyframes).pop();
  function cardHtml(c) {
        const proj = sbProj || $("proj").value, pick = pickKf;
        const kf = pick(c), clips = Object.entries(c.clips), cap = `Shot ${c.n} (${c.chapter}) - ${c.prompt}`;
        const still = kf ? `<div class="pz-media" tabindex="0" role="button" draggable="true" data-drag="${c.n}" data-drop="${c.n}" title="Drag onto another shot's picture to swap the two" aria-label="Open the keyframe of shot ${c.n}" data-file="${esc(proj + "/" + kf)}" data-kind="image" data-cap="${esc(cap)}">${mediaHtml(proj + "/" + kf, "image", "", c.ver && c.ver[kf])}<span class="pz-badge">${c.n}</span></div>`
                         : `<div class="pz-media" data-drop="${c.n}" aria-label="No keyframe yet for shot ${c.n}"><span class="pz-badge">${c.n}</span><span style="font-size:var(--text-sm)">no keyframe yet</span></div>`;
        const clipBtns = clips.map(([m, f]) => `<button type="button" class="pz-chip" data-clip="${esc(proj + "/" + f)}" data-cap="${esc(m + " - " + cap)}">▶ ${esc(m)}</button>`).join("");
        const st = (c.review && c.review.status) || "pending";
        const verdict = `<div class="pz-row" style="flex-wrap:wrap;gap:6px;align-items:center"><span class="pz-cat" data-verdict="${st}">${st === "approved" ? "✓ approved" : st === "rejected" ? "✗ rejected" : "not reviewed"}</span>` +
          `<button type="button" class="pz-chip" data-review="approved" data-key="${esc(c.key)}" aria-pressed="${st === "approved"}" aria-label="Approve shot ${c.n}">✓ Approve</button>` +
          `<button type="button" class="pz-chip" data-review="rejected" data-key="${esc(c.key)}" aria-pressed="${st === "rejected"}" aria-label="Reject shot ${c.n}">✗ Reject</button></div>` +
          (c.review && c.review.note ? `<small class="warn">${esc(c.review.note)}</small>` : "");
        return `<article class="pz-tile" id="sbShot-${c.n}" data-status="${st}">${still}<div class="pz-body"><span class="pz-cat">${esc(c.chapter)} · shot ${esc(c.shot)}</span>` +
          (c.characters && c.characters.length ? `<span class="pz-cat">${c.characters.map(esc).join(" · ")}</span>` : "") +
          ($("sbShowPrompts").checked ? `<span title="${esc(c.prompt)}">${esc(c.prompt.length > 160 ? c.prompt.slice(0, 160) + "…" : c.prompt)}</span>` : "") +
          (c.narration ? `<em style="color:var(--fg-muted)">“${esc(c.narration)}”</em>` : "") + faceBadge(c, esc) + verdict +
          clipLenHtml(c) +
          // one line each: move the shot; edit its words; a new picture (retake, or an old one); the pictures it has had, to swap in one click
          `<div class="sb-actions"><div class="pz-row" style="gap:6px"><button type="button" class="pz-chip" data-move="-1" data-n="${c.n}" aria-label="Move shot ${c.n} one place earlier">◀ Earlier</button><button type="button" class="pz-chip" data-move="1" data-n="${c.n}" aria-label="Move shot ${c.n} one place later">Later ▶</button></div>` +
          `<div class="pz-row" style="gap:6px"><button type="button" class="pz-chip" data-edit="${c.n}" aria-label="Edit the prompt and narration of shot ${c.n}">✎ Edit prompt</button></div><div class="sb-editor" id="sbEdit-${c.n}"></div>` +
          `<div class="pz-row" style="gap:6px;flex-wrap:wrap">${kf ? retakeBtn(c, "keyframe", kfModelOf(c, kf), "Retake keyframe") : ""}<button type="button" class="pz-chip" data-oldpics="${c.n}" aria-label="Choose an old picture for shot ${c.n}">🖼 Old pictures</button></div>` +
          picturesHtml(c, kf) + `</div>` +
          (clipBtns ? `<div class="pz-row" style="flex-wrap:wrap;gap:6px">${clipBtns}</div>` : "") + takesHtml(c) + `</div></article>`;
  }
  // one card again from the server (after a picture was swapped or retaken): the rest of the storyboard stays as it is
  async function refreshCard(n) {
    const proj = $("proj").value, el = document.getElementById("sbShot-" + n);
    if (!proj || !el) return loadStoryboard();
    const r = await api(`/api/storyboard?project=${encodeURIComponent(proj)}&start=${n}&end=${n}`);
    const c = r.cards[0]; if (!c) return;
    sbData[n] = c;
    const box = document.createElement("div"); box.innerHTML = cardHtml(c);
    const editor = el.querySelector(".sb-editor");             // an open prompt editor stays open
    el.replaceWith(box.firstElementChild);
    if (editor && editor.childElementCount) document.getElementById("sbEdit-" + n).replaceWith(editor);
    movieTotal();
  }
  window.sbRefreshCard = refreshCard;
  // drag one card's picture onto another card's picture: the two shots trade pictures (onto a shot with none, the picture moves there)
  let dragFrom = 0;
  async function swapPictures(a, b) {
    const st = $("sbStatus"), c = sbData[a];
    if (!c || !b || a === b) return;
    try {
      await api("/api/swap_pictures", { project: $("proj").value, a, b, model: kfModelOf(c, pickKf(c)) });
      await refreshCard(a); await refreshCard(b);
      st.textContent = `Shots ${a} and ${b} swapped pictures. Say yes or no to both again.`;
      if (window.flowRefresh) window.flowRefresh();
    } catch (e) { st.textContent = e.message; }
  }
  window.sbSwapPictures = swapPictures;
  const dropOf = e => e.target.closest && e.target.closest("[data-drop]");
  $("sbGrid").addEventListener("dragstart", e => {
    const m = e.target.closest && e.target.closest("[data-drag]"); if (!m) return;
    dragFrom = Number(m.dataset.drag);
    if (e.dataTransfer) { e.dataTransfer.effectAllowed = "move"; try { e.dataTransfer.setData("text/plain", String(dragFrom)); } catch (err) { /* some browsers refuse */ } }
    m.classList.add("sb-dragging");
  });
  $("sbGrid").addEventListener("dragover", e => {
    const t = dropOf(e); if (!dragFrom || !t || Number(t.dataset.drop) === dragFrom) return;
    e.preventDefault(); if (e.dataTransfer) e.dataTransfer.dropEffect = "move";
    t.classList.add("sb-drop");
  });
  $("sbGrid").addEventListener("dragleave", e => { const t = dropOf(e); if (t && !t.contains(e.relatedTarget)) t.classList.remove("sb-drop"); });
  $("sbGrid").addEventListener("drop", e => {
    const t = dropOf(e); if (!dragFrom || !t) return;
    e.preventDefault();
    const a = dragFrom, b = Number(t.dataset.drop); dragFrom = 0;
    document.querySelectorAll("#sbGrid .sb-drop, #sbGrid .sb-dragging").forEach(x => x.classList.remove("sb-drop", "sb-dragging"));
    swapPictures(a, b);
  });
  $("sbGrid").addEventListener("dragend", () => { dragFrom = 0; document.querySelectorAll("#sbGrid .sb-drop, #sbGrid .sb-dragging").forEach(x => x.classList.remove("sb-drop", "sb-dragging")); });
  $("sbLoad").addEventListener("click", loadStoryboard);
  window.sbReload = loadStoryboard;                 // other cards (old pictures) reload it and then say what they did
  $("sbAnimatic").addEventListener("click", async () => {      // stills timed to the narration: judge pacing before paying for video clips
    const proj = $("proj").value, [start, end] = ($("sbMovie").value || "").split("-").map(Number);
    if (!proj || !start) return;
    try { await api("/api/make_animatic", { project: proj, start, end, keyframes: $("sbKf").value }); $("sbStatus").textContent = `Making the animatic for rows ${start}-${end}; the log shows progress and the file lands in the films folder.`; }
    catch (e) { $("sbStatus").textContent = e.message; }
  });
  $("sbKf").addEventListener("change", loadStoryboard);
  $("sbShowPrompts").addEventListener("change", loadStoryboard);
  async function runCritic(flag) {
    const proj = $("proj").value; if (!proj) return;
    const st = $("sbStatus"), list = $("sbCriticList");
    try {
      const r = await api("/api/critic", { project: proj, flag, clip_seconds: Number($("clipsecs").value) || 4 });
      list.textContent = "";
      r.findings.slice(0, 60).forEach(f => {
        const li = document.createElement("li"); if (f.severity === "high") li.className = "err";
        const msg = document.createElement("div"); msg.className = "crit-msg";
        msg.textContent = `${f.severity.toUpperCase()} ${f.n ? "shot " + f.n : "film"} (${f.kind}): ${f.message}`;
        li.append(msg);
        if (f.n) {                                     // the controls on the next line, in a grid so they line up from one finding to the next
          const ctl = document.createElement("div"); ctl.className = "crit-ctl";
          ctl.append(...critLen(f.n, r.lengths && r.lengths[f.n]));          // the same clip length controls as the storyboard cards
          for (const [act, label, tip] of [["show", "Show shot", "Open this shot in the storyboard below"], ["edit", "Edit prompt", "Change this shot's prompt or narration"],
                                           ["reject", "Reject", "Reject this shot in the review so it is re-made"], ["dismiss", "Dismiss", "Hide this finding (it comes back the next time the critic runs)"]]) {
            const b = document.createElement("button"); b.type = "button"; b.className = "pz-chip"; b.textContent = label; b.title = tip;
            b.dataset.crit = act; b.dataset.n = f.n; b.dataset.key = f.key || ""; b.dataset.msg = f.message; ctl.append(b);
          }
          li.append(ctl);
        }
        list.appendChild(li);
      });
      if (r.findings.length > 60) { const li = document.createElement("li"); li.textContent = `... and ${r.findings.length - 60} more (critic.json in the book's folder)`; list.appendChild(li); }
      $("sbCriticFlag").disabled = !r.counts.high;
      st.textContent = `Critic: ${r.counts.high} serious, ${r.counts.warn} warnings, ${r.counts.info} notes over ${r.shots} shots` + (flag ? `; ${r.flagged_in_review} rejected in the review` : "");
      if (flag) await loadStoryboard();
    } catch (e) { st.textContent = e.message; }
  }
  $("sbCritic").addEventListener("click", () => runCritic(false));
  $("sbCriticFlag").addEventListener("click", () => runCritic(true));
  // ---- acting on what the critic found (and on any card): show the shot, edit its prompt and narration, reject it, dismiss the finding
  async function showShot(n) {
    const sel = $("sbMovie");
    const opt = [...sel.options].find(o => { const [a, b] = o.value.split("-").map(Number); return a <= n && n <= b; });
    if (!opt) { $("sbStatus").textContent = `Shot ${n} is not in a planned movie yet: plan the movies (Which Movies) first.`; return null; }
    if (sel.value !== opt.value || !sbData[n]) { sel.value = opt.value; await loadStoryboard(); }
    const card = document.getElementById("sbShot-" + n);
    if (!card) { $("sbStatus").textContent = `Shot ${n} is not on screen.`; return null; }
    card.scrollIntoView({ behavior: "smooth", block: "center" });
    card.classList.add("pz-flash"); setTimeout(() => card.classList.remove("pz-flash"), 2500);
    return card;
  }
  function openEditor(n) {
    const c = sbData[n], box = document.getElementById("sbEdit-" + n);
    if (!c || !box) return;
    if (box.firstChild) { box.textContent = ""; return; }                         // a second click closes it
    const field = (id, label, value, rows) => `<label class="f" for="${id}">${label}</label><textarea id="${id}" rows="${rows}" style="width:100%" maxlength="2000">${esc(value)}</textarea>`;
    box.innerHTML = field(`sbEp-${n}`, "Prompt (what the picture and video show)", c.prompt, 4) + (c.narration ? field(`sbEn-${n}`, "Narration (what is said)", c.narration, 2) : "") +
      `<label class="opt"><input type="checkbox" id="sbEr-${n}" checked><span>Reject this shot so it is re-made with the new prompt</span></label>` +
      `<div class="pz-row" style="gap:6px"><button type="button" class="pz-chip" data-edit-save="${n}">Save</button><button type="button" class="pz-chip" data-edit-cancel="${n}">Cancel</button></div>`;
    document.getElementById(`sbEp-${n}`).focus();
  }
  async function saveEditor(n) {
    const c = sbData[n], st = $("sbStatus"); if (!c) return;
    const fields = {}, p = document.getElementById(`sbEp-${n}`), nar = document.getElementById(`sbEn-${n}`);
    if (p && p.value.trim() !== c.prompt) fields.prompt = p.value;
    if (nar && nar.value.trim() !== c.narration) fields.narration = nar.value;
    try {
      if (Object.keys(fields).length) await api("/api/prompt_save", { project: $("proj").value, chapter: c.chapter, shot: Number(c.shot), fields });
      if (document.getElementById(`sbEr-${n}`).checked) await api("/api/review", { project: $("proj").value, action: "set", keys: [c.key], status: "rejected", note: "edited: make again" });
      await loadStoryboard();
      st.textContent = (Object.keys(fields).length ? `Shot ${n} saved` : `Shot ${n}: nothing changed`) + ". " + st.textContent;
    } catch (e) { st.textContent = e.message; }
  }
  $("sbCriticList").addEventListener("change", e => {
    const box = e.target.closest("[data-crlen]"); if (!box) return;
    const v = box.value.trim();
    critLenChange({ n: Number(box.dataset.crlen), seconds: v === "" ? null : Number(v) });
  });
  $("sbCriticList").addEventListener("click", async e => {
    const m = e.target.closest("[data-crlenmatch]");
    if (m) { critLenChange({ n: Number(m.dataset.crlenmatch), match_narration: true }); return; }
    const b = e.target.closest("[data-crit]"); if (!b) return;
    const n = Number(b.dataset.n), act = b.dataset.crit;
    if (act === "dismiss") { b.closest("li").remove(); return; }
    const card = await showShot(n); if (!card) return;
    if (act === "edit") openEditor(n);
    if (act === "reject") {
      const note = prompt("What is wrong with this shot? (optional)", b.dataset.msg) || "";
      await reviewCall({ action: "set", keys: [b.dataset.key], status: "rejected", note });
    }
  });
  async function reviewCall(body, done) {
    const st = $("sbStatus");
    try { const r = await api("/api/review", { project: $("proj").value, ...body }); await loadStoryboard(); if (done) st.textContent = done(r) + " " + st.textContent; }
    catch (e) { st.textContent = e.message; }
  }
  $("sbApproveRest").addEventListener("click", () => { const [start, end] = ($("sbMovie").value || "").split("-").map(Number); if (start) reviewCall({ action: "approve_range", start, end }); });
  $("sbReroll").addEventListener("click", () => {
    const [start, end] = ($("sbMovie").value || "").split("-").map(Number); if (!start) return;
    const model = $("sbKf").value || ([...$("sbKf").options].map(o => o.value).find(Boolean) || "");      // the chosen keyframe model, else the first one that has made keyframes
    if (!model) { $("sbStatus").textContent = "Pick the keyframe model above first."; return; }
    if (confirm("Keep each rejected shot's keyframe as a take and clear it, so the next run makes a new one?")) reviewCall({ action: "reroll_rejected", start, end, kind: "keyframe", model }, r => `Re-rolled ${r.rerolled} shot(s)${r.skipped.length ? `, skipped ${r.skipped.length}` : ""}. Run the keyframes again to make the new versions.`);
  });
  $("sbGrid").addEventListener("click", e => {
    const lm = e.target.closest("[data-lenmatch]");
    if (lm) { const n = Number(lm.dataset.lenmatch); clipLen({ n, match_narration: true }, x => `Shot ${n}'s clip is now ${x.shots[0].seconds} s, to fit its words (about ${x.shots[0].spoken} s).`); return; }
    const op = e.target.closest("[data-oldpics]");
    if (op) { if (window.openOldPictures) window.openOldPictures(Number(op.dataset.oldpics)); return; }
    const mv = e.target.closest("[data-move]");
    if (mv) {                                     // move a shot (its picture, clip, sound, verdict and words go with it); the screenplay is told
      api("/api/shot_move", { project: $("proj").value, n: Number(mv.dataset.n), direction: Number(mv.dataset.move) })
        .then(async r => { await loadStoryboard(); $("sbStatus").textContent = `Moved to place ${r.n}. The screenplay scene it came from is marked for a look.`; const c = document.getElementById("sbShot-" + r.n); if (c) c.scrollIntoView({ block: "center" }); if (window.flowRefresh) window.flowRefresh(); })
        .catch(err => { $("sbStatus").textContent = err.message; });
      return;
    }
    const ed = e.target.closest("[data-edit],[data-edit-save],[data-edit-cancel]");
    if (ed) {
      if (ed.dataset.editSave) saveEditor(Number(ed.dataset.editSave));
      else if (ed.dataset.editCancel) document.getElementById("sbEdit-" + ed.dataset.editCancel).textContent = "";
      else openEditor(Number(ed.dataset.edit));
      return;
    }
    const rv = e.target.closest("[data-review]");
    if (rv) {
      const reject = rv.dataset.review === "rejected";
      const was = rv.getAttribute("aria-pressed") === "true";
      const note = reject && !was ? (prompt("What is wrong with this shot? (optional)") || "") : "";
      reviewCall({ action: "set", keys: [rv.dataset.key], status: was ? "pending" : rv.dataset.review, note });
      return;
    }
    const act = e.target.closest("[data-retake],[data-take-use]");
    if (act) { takeAction(act); return; }
    const tv = e.target.closest("[data-take-view]");
    if (tv) {
      const one = document.createElement("div");
      one.innerHTML = `<div class="pz-media" data-file="${esc(tv.dataset.takeView)}" data-kind="${tv.dataset.kind}" data-cap="${esc(tv.dataset.cap)}"></div>`;
      openLightbox(tv.dataset.takeView, tv.dataset.kind, tv.dataset.cap, one); return;
    }
    const clip = e.target.closest("[data-clip]");
    if (clip) {                                   // a one-clip gallery, so Previous / Next do not walk another grid
      const one = document.createElement("div");
      one.innerHTML = `<div class="pz-media" data-file="${esc(clip.dataset.clip)}" data-kind="video" data-cap="${esc(clip.dataset.cap)}"></div>`;
      openLightbox(clip.dataset.clip, "video", clip.dataset.cap, one); return;
    }
    const media = e.target.closest(".pz-media[data-file]");
    if (media) openLightbox(media.dataset.file, media.dataset.kind, media.dataset.cap, $("sbGrid"));
  });
  $("sbGrid").addEventListener("change", e => {           // a clip length typed in, or changed with the arrows
    const box = e.target.closest("[data-len]");
    if (!box) return;
    const n = Number(box.dataset.len), v = box.value.trim();
    clipLen({ n, seconds: v === "" ? null : Number(v) }, x => x.shots[0].seconds ? `Shot ${n}'s clip is now ${x.shots[0].seconds} s.` : `Shot ${n} is back to the model's own length.`);
  });
  $("sbGrid").addEventListener("keydown", e => {         // the stills are focusable: Enter or Space opens them like a click
    if ((e.key === "Enter" || e.key === " ") && e.target.matches(".pz-media[data-file]")) { e.preventDefault(); e.target.click(); }
  });
  window.sbFillMovies();

  applyFx();
  loadShowcase();
})();
