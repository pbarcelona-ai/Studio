// studio/canvas_studio.js - Client-side HTML5 Canvas Studio (pan/zoom, lasso/box regions,
// sketch/shapes/text overlays, undo/redo, 7-category color grading, vignette/film-grain offscreen composite export).
(function () {
  "use strict";

  const GRAIN_FREQS = {
    "35mm": "0.8",
    "16mm": "0.5",
    "8mm": "0.3",
  };

  function clampNum(val, min, max, fallback) {
    const n = Number(val);
    if (!Number.isFinite(n)) return fallback;
    return Math.max(min, Math.min(max, n));
  }

  function cloneObjects(arr) {
    return (arr || []).map((item) => {
      if (item.points) {
        return { ...item, points: item.points.map((p) => ({ x: p.x, y: p.y })) };
      }
      return { ...item };
    });
  }

  function mountCanvasStudio(containerEl, options) {
    const opts = options || {};
    const d = (containerEl && containerEl.ownerDocument) || document;
    const w = d.defaultView || window;
    const host =
      containerEl ||
      d.getElementById("canvasStudioHost") ||
      d.getElementById("csHost") ||
      d.body;

    const state = {
      zoom: 1,
      panX: 0,
      panY: 0,
      tool: "draw", // "hand" | "lasso" | "box" | "draw" | "text"
      markedRegions: [],
      objects: [],
      strokes: [],
      grading: {
        exposure: { stops: 0, contrast: 0, saturation: 0 },
        colorCorrect: { temperature: 0, tint: 0, contrast: 0, saturation: 0, hue: 0 },
        lensInstructions: { vignette: 0 },
        filmGrain: { strength: 0, size: "35mm" },
      },
    };

    const undoStack = [];
    const redoStack = [];
    const MAX_UNDO = 30;

    function pushUndoSnapshot() {
      undoStack.push(cloneObjects(state.objects));
      if (undoStack.length > MAX_UNDO) undoStack.shift();
      redoStack.length = 0;
    }

    function syncStrokesAlias() {
      state.strokes = state.objects.slice();
    }

    // Build DOM using createElement (zero inline on*= attributes)
    host.textContent = "";
    const root = d.createElement("div");
    root.className = "canvas-studio-root";

    const toolbar = d.createElement("div");
    toolbar.className = "cs-toolbar row";

    function makeBtn(label, tool, title) {
      const b = d.createElement("button");
      b.type = "button";
      b.className = "btn btn--secondary cs-btn";
      b.textContent = label;
      if (tool) b.dataset.tool = tool;
      if (title) b.title = title;
      toolbar.appendChild(b);
      return b;
    }

    const btnZoomIn = makeBtn("Zoom +", "", "Zoom In");
    const btnZoomOut = makeBtn("Zoom -", "", "Zoom Out");
    const btnHand = makeBtn("Hand", "hand", "Hand Pan Tool");
    const btnResetView = makeBtn("Reset View", "", "Reset View 100%");
    const btnLasso = makeBtn("Lasso", "lasso", "Lasso Region Selection");
    const btnBox = makeBtn("Box Region", "box", "Box Region Selection");
    const btnDraw = makeBtn("Draw", "draw", "Freehand Sketch / Draw");
    const btnText = makeBtn("Text", "text", "Text Overlay Tool");

    const textInput = d.createElement("input");
    textInput.type = "text";
    textInput.className = "cs-text-input";
    textInput.placeholder = "Overlay text…";
    textInput.setAttribute("aria-label", "Overlay text");
    toolbar.appendChild(textInput);

    const btnAddText = makeBtn("Add Text", "", "Add text overlay to canvas");
    const btnUndo = makeBtn("Undo", "", "Undo");
    const btnRedo = makeBtn("Redo", "", "Redo");
    const btnResetAll = makeBtn("Reset All", "", "Reset All Grading");

    root.appendChild(toolbar);

    // Step 17 Pixel-Locked Masked Inpaint bar (shown when a keyframe is loaded from Step 17)
    let activeKfMeta = null;
    const inpaintBar = d.createElement("div");
    inpaintBar.className = "cs-inpaint-bar";
    inpaintBar.style.display = "none";

    const inpaintTitle = d.createElement("strong");
    inpaintTitle.style.color = "#7dd3fc";
    inpaintTitle.textContent = "🖌️ Mask Inpaint";

    const inpaintPrompt = d.createElement("input");
    inpaintPrompt.type = "text";
    inpaintPrompt.placeholder = "Draw a Box or Lasso over the area to change, then describe ONLY what should appear inside it…";

    const inpaintStrength = d.createElement("select");
    inpaintStrength.style.cssText = "padding:5px 7px;background:#020617;color:#f8fafc;border:1px solid #334155;border-radius:6px;font-size:11.5px";
    [
      ["0.55", "Subtle (0.55)"],
      ["0.72", "Standard (0.72)"],
      ["0.88", "Strong (0.88)"],
    ].forEach(([val, lbl]) => {
      const o = d.createElement("option");
      o.value = val;
      o.textContent = lbl;
      if (val === "0.72") o.selected = true;
      inpaintStrength.appendChild(o);
    });

    const btnClearMask = d.createElement("button");
    btnClearMask.type = "button";
    btnClearMask.className = "btn btn--ghost";
    btnClearMask.textContent = "🧹 Clear Mask";
    btnClearMask.style.cssText = "padding:5px 9px;font-size:11.5px";

    const btnRunInpaint = d.createElement("button");
    btnRunInpaint.type = "button";
    btnRunInpaint.className = "btn btn--primary";
    btnRunInpaint.textContent = "✨ Inpaint Masked Region & Save";
    btnRunInpaint.style.cssText = "padding:5px 11px;font-size:11.5px";

    const btnBackStep17 = d.createElement("button");
    btnBackStep17.type = "button";
    btnBackStep17.className = "btn btn--secondary";
    btnBackStep17.textContent = "⬅ Back to Step 17";
    btnBackStep17.style.cssText = "padding:5px 9px;font-size:11.5px";

    const inpaintMsg = d.createElement("span");
    inpaintMsg.style.cssText = "font-size:11.5px;color:#34d399;width:100%";

    inpaintBar.appendChild(inpaintTitle);
    inpaintBar.appendChild(inpaintPrompt);
    inpaintBar.appendChild(inpaintStrength);
    inpaintBar.appendChild(btnClearMask);
    inpaintBar.appendChild(btnRunInpaint);
    inpaintBar.appendChild(btnBackStep17);
    inpaintBar.appendChild(inpaintMsg);
    root.appendChild(inpaintBar);

    // 7-category Color Grading sliders panel
    const gradingPanel = d.createElement("div");
    gradingPanel.className = "cs-grading-panel row";

    const sliderDefs = [
      { key: "stops", cat: "exposure", label: "Exposure", min: "-2", max: "2", step: "0.1", val: "0" },
      { key: "contrast", cat: "colorCorrect", label: "Contrast", min: "-50", max: "50", step: "1", val: "0" },
      { key: "saturation", cat: "colorCorrect", label: "Saturation", min: "-50", max: "50", step: "1", val: "0" },
      { key: "temperature", cat: "colorCorrect", label: "Temperature", min: "-50", max: "50", step: "1", val: "0" },
      { key: "tint", cat: "colorCorrect", label: "Tint", min: "-50", max: "50", step: "1", val: "0" },
      { key: "hue", cat: "colorCorrect", label: "Hue", min: "-180", max: "180", step: "5", val: "0" },
      { key: "vignette", cat: "lensInstructions", label: "Vignette", min: "0", max: "1", step: "0.05", val: "0" },
      { key: "strength", cat: "filmGrain", label: "Film Grain", min: "0", max: "1", step: "0.05", val: "0" },
    ];

    const sliderEls = {};
    sliderDefs.forEach((def) => {
      const wrap = d.createElement("label");
      wrap.className = "cs-slider-label";
      const sp = d.createElement("span");
      sp.textContent = def.label;
      const inp = d.createElement("input");
      inp.type = "range";
      inp.min = def.min;
      inp.max = def.max;
      inp.step = def.step;
      inp.value = def.val;
      inp.dataset.cat = def.cat;
      inp.dataset.key = def.key;
      wrap.appendChild(sp);
      wrap.appendChild(inp);
      gradingPanel.appendChild(wrap);
      sliderEls[def.cat + "." + def.key] = inp;
    });

    root.appendChild(gradingPanel);

    // SVG Filter defs (feTurbulence for film grain) + region overlay SVG
    const svgNS = "http://www.w3.org/2000/svg";
    const filterSvg = d.createElementNS(svgNS, "svg");
    filterSvg.setAttribute("width", "0");
    filterSvg.setAttribute("height", "0");
    filterSvg.style.position = "absolute";
    const defs = d.createElementNS(svgNS, "defs");
    const filterEl = d.createElementNS(svgNS, "filter");
    filterEl.setAttribute("id", "csGrainFilter");
    const turbEl = d.createElementNS(svgNS, "feTurbulence");
    turbEl.setAttribute("type", "fractalNoise");
    turbEl.setAttribute("baseFrequency", GRAIN_FREQS["35mm"]);
    filterEl.appendChild(turbEl);
    defs.appendChild(filterEl);
    filterSvg.appendChild(defs);
    root.appendChild(filterSvg);

    // Viewport stage
    const viewport = d.createElement("div");
    viewport.className = "cs-viewport canvas-viewport";
    viewport.setAttribute("data-canvas-viewport", "1");
    viewport.style.position = "relative";
    viewport.style.transform = "translate(0px, 0px) scale(1)";

    const baseImg = d.createElement("img");
    baseImg.className = "cs-base-img";
    baseImg.alt = "Canvas Studio base frame";
    if (opts.imageUrl) {
      baseImg.src = String(opts.imageUrl);
    }
    viewport.appendChild(baseImg);

    const canvas = d.createElement("canvas");
    canvas.className = "cs-overlay-canvas";
    canvas.width = Math.max(1, Number(opts.width) || 320);
    canvas.height = Math.max(1, Number(opts.height) || 240);
    viewport.appendChild(canvas);

    const regionsSvg = d.createElementNS(svgNS, "svg");
    regionsSvg.setAttribute("class", "cs-regions-svg");
    regionsSvg.setAttribute("viewBox", "0 0 " + canvas.width + " " + canvas.height);
    regionsSvg.style.position = "absolute";
    regionsSvg.style.inset = "0";
    regionsSvg.style.pointerEvents = "none";
    viewport.appendChild(regionsSvg);

    root.appendChild(viewport);
    host.appendChild(root);

    function setActiveTool(t) {
      state.tool = t;
      [btnHand, btnLasso, btnBox, btnDraw, btnText].forEach((b) => {
        const active = b.dataset.tool === t;
        b.classList.toggle("active", active);
        b.setAttribute("aria-pressed", String(active));
      });
    }
    setActiveTool("draw");

    function updateTransform() {
      state.zoom = clampNum(Math.round(state.zoom * 100) / 100, 0.5, 2.0, 1);
      state.panX = clampNum(state.panX, -2000, 2000, 0);
      state.panY = clampNum(state.panY, -2000, 2000, 0);
      viewport.style.transform =
        "translate(" + state.panX + "px, " + state.panY + "px) scale(" + state.zoom + ")";
    }

    function computeFilterString() {
      const g = state.grading;
      const stops = clampNum(g.exposure && g.exposure.stops, -2, 2, 0);
      const contrast =
        clampNum(g.colorCorrect && g.colorCorrect.contrast, -90, 90, 0) +
        clampNum(g.exposure && g.exposure.contrast, -90, 90, 0);
      const sat =
        clampNum(g.colorCorrect && g.colorCorrect.saturation, -90, 90, 0) +
        clampNum(g.exposure && g.exposure.saturation, -90, 90, 0);
      const temp = clampNum(g.colorCorrect && g.colorCorrect.temperature, -100, 100, 0);
      const tint = clampNum(g.colorCorrect && g.colorCorrect.tint, -100, 100, 0);
      const hue = clampNum(g.colorCorrect && g.colorCorrect.hue, -180, 180, 0);

      const isDefault =
        stops === 0 &&
        contrast === 0 &&
        sat === 0 &&
        temp === 0 &&
        tint === 0 &&
        hue === 0 &&
        clampNum(g.lensInstructions && g.lensInstructions.vignette, 0, 1, 0) === 0 &&
        clampNum(g.filmGrain && g.filmGrain.strength, 0, 1, 0) === 0;

      if (isDefault) return "none";

      const bPct = Math.max(10, Math.round(Math.pow(2, stops) * 100));
      const cPct = Math.max(10, Math.round(100 + contrast));
      const sPct = Math.max(0, Math.round(100 + sat));
      const hDeg = Math.round(hue + temp * 0.4 - tint * 0.3);

      return (
        "brightness(" +
        bPct +
        "%) contrast(" +
        cPct +
        "%) saturate(" +
        sPct +
        "%) hue-rotate(" +
        hDeg +
        "deg)"
      );
    }

    function applyGradingToDOM() {
      const freq = GRAIN_FREQS[state.grading.filmGrain.size] || GRAIN_FREQS["35mm"];
      turbEl.setAttribute("baseFrequency", freq);
      const fStr = computeFilterString();
      baseImg.style.filter = fStr === "none" ? "" : fStr;
    }

    function setGrading(patch) {
      if (!patch || typeof patch !== "object") return state.grading;
      if (patch.exposure && typeof patch.exposure === "object") {
        if ("stops" in patch.exposure) {
          state.grading.exposure.stops = clampNum(patch.exposure.stops, -2, 2, 0);
        }
        if ("contrast" in patch.exposure) {
          state.grading.exposure.contrast = clampNum(patch.exposure.contrast, -90, 90, 0);
        }
        if ("saturation" in patch.exposure) {
          state.grading.exposure.saturation = clampNum(patch.exposure.saturation, -90, 90, 0);
        }
      }
      if (patch.colorCorrect && typeof patch.colorCorrect === "object") {
        const cc = patch.colorCorrect;
        if ("contrast" in cc) state.grading.colorCorrect.contrast = clampNum(cc.contrast, -90, 90, 0);
        if ("saturation" in cc) state.grading.colorCorrect.saturation = clampNum(cc.saturation, -90, 90, 0);
        if ("temperature" in cc) state.grading.colorCorrect.temperature = clampNum(cc.temperature, -100, 100, 0);
        if ("tint" in cc) state.grading.colorCorrect.tint = clampNum(cc.tint, -100, 100, 0);
        if ("hue" in cc) state.grading.colorCorrect.hue = clampNum(cc.hue, -180, 180, 0);
      }
      if (patch.lensInstructions && typeof patch.lensInstructions === "object") {
        if ("vignette" in patch.lensInstructions) {
          state.grading.lensInstructions.vignette = clampNum(patch.lensInstructions.vignette, 0, 1, 0);
        }
      }
      if (patch.filmGrain && typeof patch.filmGrain === "object") {
        if ("strength" in patch.filmGrain) {
          state.grading.filmGrain.strength = clampNum(patch.filmGrain.strength, 0, 1, 0);
        }
        if ("size" in patch.filmGrain && GRAIN_FREQS[patch.filmGrain.size]) {
          state.grading.filmGrain.size = patch.filmGrain.size;
        }
      }
      applyGradingToDOM();
      return state.grading;
    }

    function redrawObjects() {
      const ctx = canvas.getContext("2d");
      if (!ctx) return;
      const cw = Math.max(1, canvas.width || 320);
      const ch = Math.max(1, canvas.height || 240);
      ctx.clearRect(0, 0, cw, ch);
      state.objects.forEach((obj) => {
        if (obj.type === "stroke" && Array.isArray(obj.points) && obj.points.length > 0) {
          ctx.save();
          ctx.strokeStyle = obj.color || "#f59e0b";
          ctx.lineWidth = obj.lineWidth || 3;
          ctx.lineCap = "round";
          ctx.lineJoin = "round";
          ctx.beginPath();
          ctx.moveTo(obj.points[0].x, obj.points[0].y);
          for (let i = 1; i < obj.points.length; i++) {
            ctx.lineTo(obj.points[i].x, obj.points[i].y);
          }
          ctx.stroke();
          ctx.restore();
        } else if (obj.type === "text" && obj.text) {
          ctx.save();
          ctx.fillStyle = obj.color || "#ffffff";
          ctx.font = obj.font || "16px sans-serif";
          ctx.fillText(String(obj.text), obj.x || 24, obj.y || 36, cw - 20);
          ctx.restore();
        }
      });
    }

    function addTextOverlay(text) {
      const val = String(text == null ? "" : text).trim();
      if (!val) return;
      pushUndoSnapshot();
      state.objects.push({
        type: "text",
        text: val,
        x: 24,
        y: 36 + state.objects.filter((o) => o.type === "text").length * 22,
        color: "#ffffff",
      });
      syncStrokesAlias();
      redrawObjects();
    }

    // Toolbar button handlers
    btnZoomIn.addEventListener("click", () => {
      state.zoom = clampNum(Math.round((state.zoom + 0.1) * 100) / 100, 0.5, 2.0, 1);
      updateTransform();
    });
    btnZoomOut.addEventListener("click", () => {
      state.zoom = clampNum(Math.round((state.zoom - 0.1) * 100) / 100, 0.5, 2.0, 1);
      updateTransform();
    });
    btnResetView.addEventListener("click", () => {
      state.zoom = 1;
      state.panX = 0;
      state.panY = 0;
      updateTransform();
    });
    btnHand.addEventListener("click", () => setActiveTool("hand"));
    btnLasso.addEventListener("click", () => setActiveTool("lasso"));
    btnBox.addEventListener("click", () => setActiveTool("box"));
    btnDraw.addEventListener("click", () => setActiveTool("draw"));
    btnText.addEventListener("click", () => setActiveTool("text"));

    btnAddText.addEventListener("click", () => {
      addTextOverlay(textInput.value || "Text");
    });

    btnUndo.addEventListener("click", () => {
      if (!undoStack.length) return;
      redoStack.push(cloneObjects(state.objects));
      state.objects = undoStack.pop();
      syncStrokesAlias();
      redrawObjects();
    });

    btnRedo.addEventListener("click", () => {
      if (!redoStack.length) return;
      undoStack.push(cloneObjects(state.objects));
      state.objects = redoStack.pop();
      syncStrokesAlias();
      redrawObjects();
    });

    btnResetAll.addEventListener("click", () => {
      state.grading = {
        exposure: { stops: 0, contrast: 0, saturation: 0 },
        colorCorrect: { temperature: 0, tint: 0, contrast: 0, saturation: 0, hue: 0 },
        lensInstructions: { vignette: 0 },
        filmGrain: { strength: 0, size: "35mm" },
      };
      Object.values(sliderEls).forEach((inp) => {
        inp.value = "0";
      });
      baseImg.style.filter = "";
    });

    // Grading slider input listeners
    gradingPanel.addEventListener("input", (ev) => {
      const inp = ev.target;
      if (!inp || inp.tagName !== "INPUT") return;
      const cat = inp.dataset.cat;
      const key = inp.dataset.key;
      if (!cat || !key) return;
      setGrading({ [cat]: { [key]: Number(inp.value) } });
    });

    // Pointer interactions for pan, lasso, box, and draw
    let panSession = null;
    viewport.addEventListener("pointerdown", (ev) => {
      if (state.tool !== "hand") return;
      panSession = {
        startX: Number(ev.clientX) || 0,
        startY: Number(ev.clientY) || 0,
        origPanX: state.panX,
        origPanY: state.panY,
      };
    });
    viewport.addEventListener("pointermove", (ev) => {
      if (!panSession || state.tool !== "hand") return;
      const dx = (Number(ev.clientX) || 0) - panSession.startX;
      const dy = (Number(ev.clientY) || 0) - panSession.startY;
      state.panX = panSession.origPanX + dx;
      state.panY = panSession.origPanY + dy;
      updateTransform();
    });
    viewport.addEventListener("pointerup", () => {
      panSession = null;
    });

    let activeGesture = null;
    function getCanvasPoint(ev) {
      const rect = canvas.getBoundingClientRect();
      const rw = rect && rect.width > 0 ? rect.width : canvas.width || 320;
      const rh = rect && rect.height > 0 ? rect.height : canvas.height || 240;
      const x = clampNum(((Number(ev.clientX) || 0) - (rect ? rect.left : 0)) * ((canvas.width || 320) / rw), 0, canvas.width || 320, 0);
      const y = clampNum(((Number(ev.clientY) || 0) - (rect ? rect.top : 0)) * ((canvas.height || 240) / rh), 0, canvas.height || 240, 0);
      return { x: Math.round(x * 10) / 10, y: Math.round(y * 10) / 10 };
    }

    canvas.addEventListener("pointerdown", (ev) => {
      if (state.tool === "hand") return;
      const pt = getCanvasPoint(ev);
      activeGesture = { tool: state.tool, points: [pt] };
    });

    canvas.addEventListener("pointermove", (ev) => {
      if (!activeGesture) return;
      const pt = getCanvasPoint(ev);
      activeGesture.points.push(pt);
    });

    canvas.addEventListener("pointerup", (ev) => {
      if (!activeGesture) return;
      const pt = getCanvasPoint(ev);
      activeGesture.points.push(pt);
      const pts = activeGesture.points;
      const tool = activeGesture.tool;
      activeGesture = null;

      let minX = Infinity,
        minY = Infinity,
        maxX = -Infinity,
        maxY = -Infinity;
      pts.forEach((p) => {
        if (p.x < minX) minX = p.x;
        if (p.y < minY) minY = p.y;
        if (p.x > maxX) maxX = p.x;
        if (p.y > maxY) maxY = p.y;
      });
      const bw = maxX - minX;
      const bh = maxY - minY;

      if (tool === "lasso") {
        if (pts.length >= 3 && bw >= 5 && bh >= 5) {
          const dAttr =
            "M " +
            pts.map((p) => p.x + " " + p.y).join(" L ") +
            " Z";
          const pathEl = d.createElementNS(svgNS, "path");
          pathEl.setAttribute("d", dAttr);
          pathEl.setAttribute("fill", "rgba(245, 158, 11, 0.2)");
          pathEl.setAttribute("stroke", "#f59e0b");
          regionsSvg.appendChild(pathEl);
          state.markedRegions.push({
            id: "lasso-" + (state.markedRegions.length + 1),
            type: "lasso",
            points: pts,
            bbox: { x: minX, y: minY, width: bw, height: bh },
          });
        }
      } else if (tool === "box") {
        if (bw >= 5 && bh >= 5) {
          const dAttr =
            "M " +
            minX +
            " " +
            minY +
            " L " +
            maxX +
            " " +
            minY +
            " L " +
            maxX +
            " " +
            maxY +
            " L " +
            minX +
            " " +
            maxY +
            " Z";
          const pathEl = d.createElementNS(svgNS, "path");
          pathEl.setAttribute("d", dAttr);
          pathEl.setAttribute("fill", "rgba(56, 189, 248, 0.2)");
          pathEl.setAttribute("stroke", "#38bdf8");
          regionsSvg.appendChild(pathEl);
          state.markedRegions.push({
            id: "box-" + (state.markedRegions.length + 1),
            type: "box",
            bbox: { x: minX, y: minY, width: bw, height: bh },
          });
        }
      } else if (tool === "draw") {
        if (pts.length >= 2 && (bw >= 1 || bh >= 1)) {
          pushUndoSnapshot();
          state.objects.push({
            type: "stroke",
            points: pts,
            color: "#f59e0b",
            lineWidth: 3,
          });
          syncStrokesAlias();
          redrawObjects();
        }
      }
    });

    // Keyboard Delete / Backspace removes last object when not focused inside an input/textarea
    d.addEventListener("keydown", (ev) => {
      if (ev.key !== "Delete" && ev.key !== "Backspace") return;
      const targetTag = ev.target && ev.target.tagName ? ev.target.tagName.toUpperCase() : "";
      if (targetTag === "INPUT" || targetTag === "TEXTAREA" || targetTag === "SELECT") return;
      const active = d.activeElement;
      const activeTag = active && active.tagName ? active.tagName.toUpperCase() : "";
      if ((activeTag === "INPUT" || activeTag === "TEXTAREA" || activeTag === "SELECT") && ev.target === active) return;
      if (state.objects.length > 0) {
        pushUndoSnapshot();
        state.objects.pop();
        syncStrokesAlias();
        redrawObjects();
      }
    });

    async function exportComposite() {
      const cw = Math.max(1, Number(canvas.width) || 320);
      const ch = Math.max(1, Number(canvas.height) || 240);
      const off = d.createElement("canvas");
      off.width = cw;
      off.height = ch;
      const ctx = off.getContext("2d");

      const filterStr = computeFilterString();
      ctx.filter = filterStr;
      ctx.drawImage(baseImg, 0, 0, cw, ch);
      ctx.filter = "none";

      // Draw strokes and wrapped text overlays
      state.objects.forEach((obj) => {
        if (obj.type === "stroke" && Array.isArray(obj.points) && obj.points.length > 0) {
          ctx.save();
          ctx.strokeStyle = obj.color || "#f59e0b";
          ctx.lineWidth = obj.lineWidth || 3;
          ctx.beginPath();
          ctx.moveTo(obj.points[0].x, obj.points[0].y);
          for (let i = 1; i < obj.points.length; i++) {
            ctx.lineTo(obj.points[i].x, obj.points[i].y);
          }
          ctx.stroke();
          ctx.restore();
        } else if (obj.type === "text" && obj.text) {
          ctx.save();
          ctx.fillStyle = obj.color || "#ffffff";
          ctx.font = obj.font || "16px sans-serif";
          const words = String(obj.text).split(/\s+/);
          let line = "";
          let y = obj.y || 36;
          const maxW = Math.max(40, cw - 32);
          words.forEach((word) => {
            const test = line ? line + " " + word : word;
            if (ctx.measureText(test).width > maxW && line) {
              ctx.fillText(line, obj.x || 24, y, maxW);
              line = word;
              y += 20;
            } else {
              line = test;
            }
          });
          if (line) {
            ctx.fillText(line, obj.x || 24, y, maxW);
          }
          ctx.restore();
        }
      });

      // Apply radial gradient vignette if vignette > 0
      const vig = clampNum(
        state.grading.lensInstructions && state.grading.lensInstructions.vignette,
        0,
        1,
        0
      );
      if (vig > 0) {
        const cx = cw / 2;
        const cy = ch / 2;
        const rOuter = Math.hypot(cx, cy);
        const grad = ctx.createRadialGradient(cx, cy, rOuter * 0.25, cx, cy, rOuter);
        grad.addColorStop(0, "rgba(0,0,0,0)");
        grad.addColorStop(1, "rgba(0,0,0," + vig.toFixed(2) + ")");
        ctx.save();
        ctx.fillStyle = grad;
        ctx.fillRect(0, 0, cw, ch);
        ctx.restore();
      }

      // Apply film grain pattern if filmGrain.strength > 0
      const grainStrength = clampNum(
        state.grading.filmGrain && state.grading.filmGrain.strength,
        0,
        1,
        0
      );
      if (grainStrength > 0) {
        const tile = d.createElement("canvas");
        tile.width = 16;
        tile.height = 16;
        const tctx = tile.getContext("2d");
        tctx.fillStyle = "rgba(128,128,128," + (grainStrength * 0.35).toFixed(2) + ")";
        tctx.fillRect(0, 0, 8, 8);
        tctx.fillRect(8, 8, 8, 8);
        const pat = ctx.createPattern(tile, "repeat");
        ctx.save();
        ctx.globalCompositeOperation = "overlay";
        ctx.fillStyle = pat || "rgba(128,128,128,0.1)";
        ctx.fillRect(0, 0, cw, ch);
        ctx.restore();
      }

      return new Promise((resolve) => {
        off.toBlob((blob) => resolve(blob), "image/png");
      });
    }

    function clearRegions() {
      state.markedRegions.length = 0;
      while (regionsSvg.firstChild) regionsSvg.removeChild(regionsSvg.firstChild);
    }

    function loadKeyframe(meta) {
      if (!meta || !meta.imageUrl) return;
      activeKfMeta = {
        project: String(meta.project || ""),
        shotId: String(meta.shotId || ""),
        imageUrl: String(meta.imageUrl || ""),
        engine: String(meta.engine || "auto"),
      };
      clearRegions();
      baseImg.onload = () => {
        const nw = baseImg.naturalWidth || 1024;
        const nh = baseImg.naturalHeight || 576;
        const maxW = 960;
        const scale = nw > maxW ? maxW / nw : 1;
        const cw = Math.max(320, Math.round(nw * scale));
        const ch = Math.max(180, Math.round(nh * scale));
        canvas.width = cw;
        canvas.height = ch;
        baseImg.style.width = cw + "px";
        baseImg.style.height = ch + "px";
        regionsSvg.setAttribute("viewBox", "0 0 " + cw + " " + ch);
        redrawObjects();
      };
      baseImg.src = activeKfMeta.imageUrl + (activeKfMeta.imageUrl.includes("?") ? "&" : "?") + "t=" + Date.now();
      inpaintTitle.textContent = `🖌️ Mask Inpaint: ${activeKfMeta.shotId}`;
      inpaintPrompt.value = String(meta.prompt || "");
      inpaintMsg.style.color = "#94a3b8";
      inpaintMsg.textContent = "Step 1: Draw a Box or Lasso over ONLY the region to change. Everything outside stays 100% pixel-identical.";
      inpaintBar.style.display = "flex";
      setActiveTool("box");
    }

    btnClearMask.addEventListener("click", () => {
      clearRegions();
      inpaintMsg.style.color = "#94a3b8";
      inpaintMsg.textContent = "Mask cleared — draw a new Box or Lasso region.";
    });

    btnBackStep17.addEventListener("click", () => {
      if (typeof w.__v2ActivateStep === "function") {
        w.__v2ActivateStep(17);
      }
    });

    btnRunInpaint.addEventListener("click", async () => {
      if (!activeKfMeta || !activeKfMeta.project || !activeKfMeta.shotId) return;
      const cw = Math.max(1, Number(canvas.width) || 1);
      const ch = Math.max(1, Number(canvas.height) || 1);
      const normRegions = state.markedRegions.map((reg) => {
        if (reg.type === "box" && reg.bbox) {
          return {
            type: "box",
            bbox: {
              x: reg.bbox.x / cw,
              y: reg.bbox.y / ch,
              width: reg.bbox.width / cw,
              height: reg.bbox.height / ch,
            },
          };
        }
        if (reg.type === "lasso" && Array.isArray(reg.points)) {
          return {
            type: "lasso",
            points: reg.points.map((pt) => ({ x: pt.x / cw, y: pt.y / ch })),
          };
        }
        return null;
      }).filter(Boolean);

      if (!normRegions.length) {
        inpaintMsg.style.color = "#f87171";
        inpaintMsg.textContent = "Draw a Box or Lasso region on the image first!";
        return;
      }
      const pTxt = inpaintPrompt.value.trim();
      if (!pTxt) {
        inpaintMsg.style.color = "#f87171";
        inpaintMsg.textContent = "Enter what should change inside the masked region.";
        inpaintPrompt.focus();
        return;
      }

      btnRunInpaint.disabled = true;
      inpaintMsg.style.color = "#fbbf24";
      inpaintMsg.textContent = `⏳ Inpainting masked region of ${activeKfMeta.shotId} (keeping background pixel-identical)…`;
      try {
        const resp = await fetch("/api/v2_keyframe_mask_inpaint", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            project: activeKfMeta.project,
            id: activeKfMeta.shotId,
            prompt: pTxt,
            regions: normRegions,
            strength: parseFloat(inpaintStrength.value || "0.72"),
            engine: activeKfMeta.engine || "auto",
          }),
        });
        const data = await resp.json();
        if (!resp.ok || data.error) throw new Error(data.error || `HTTP ${resp.status}`);
        activeKfMeta.imageUrl = data.image_url;
        baseImg.src = data.image_url + "?t=" + Date.now();
        clearRegions();
        inpaintMsg.style.color = "#34d399";
        inpaintMsg.textContent = `✓ Saved pixel-locked masked inpaint for ${activeKfMeta.shotId} (${data.model})! Click ⬅ Back to Step 17 to inspect.`;
      } catch (err) {
        inpaintMsg.style.color = "#f87171";
        inpaintMsg.textContent = "✗ Masked inpaint failed: " + (err.message || err);
      } finally {
        btnRunInpaint.disabled = false;
      }
    });

    const api = {
      getState() {
        return {
          zoom: state.zoom,
          panX: state.panX,
          panY: state.panY,
          tool: state.tool,
          markedRegions: state.markedRegions.slice(),
          objects: cloneObjects(state.objects),
          strokes: cloneObjects(state.objects),
          grading: JSON.parse(JSON.stringify(state.grading)),
        };
      },
      setGrading,
      addTextOverlay,
      exportComposite,
      loadKeyframe,
      clearRegions,
    };
    w.__canvasStudioInstance = api;
    return api;
  }

  window.mountCanvasStudio = mountCanvasStudio;
  window.openKeyframeInCanvasStudio = function openKeyframeInCanvasStudio(meta) {
    const host = document.getElementById("canvasStudioHost");
    if (!window.__canvasStudioInstance && host) {
      window.__canvasStudioInstance = mountCanvasStudio(host, {});
    }
    if (window.__canvasStudioInstance && typeof window.__canvasStudioInstance.loadKeyframe === "function") {
      window.__canvasStudioInstance.loadKeyframe(meta);
    }
  };
  window.CanvasStudio = {
    mount: mountCanvasStudio,
  };
})();
