// studio/paint.js - Inpaint mask painter ported from freefield (white mask strokes on black background, 20-step undo/redo, PNG Blob export).
(function () {
  "use strict";

  const MAX_HISTORY = 20;

  function openPainter(imageUrl, options = {}) {
    return new Promise((resolve) => {
      const host = options.container || document.body;
      host.textContent = "";

      const wrap = document.createElement("div");
      wrap.className = "studio-painter";

      const toolbar = document.createElement("div");
      toolbar.className = "painter-toolbar";

      const mkBtn = (label, tool) => {
        const b = document.createElement("button");
        b.type = "button";
        b.className = "btn btn--secondary";
        b.textContent = label;
        if (tool) b.dataset.tool = tool;
        toolbar.appendChild(b);
        return b;
      };

      const brushBtn = mkBtn("Brush", "brush");
      const eraserBtn = mkBtn("Eraser", "eraser");
      const undoBtn = mkBtn("Undo");
      const redoBtn = mkBtn("Redo");
      const clearBtn = mkBtn("Clear");
      const doneBtn = mkBtn("Done");
      doneBtn.className = "btn btn--primary";

      const msgEl = document.createElement("div");
      msgEl.className = "painter-status warn";
      msgEl.setAttribute("role", "status");

      const canvas = document.createElement("canvas");
      canvas.width = 160;
      canvas.height = 120;

      wrap.appendChild(toolbar);
      wrap.appendChild(canvas);
      wrap.appendChild(msgEl);
      host.appendChild(wrap);

      const ctx = canvas.getContext("2d");
      let activeTool = "brush";
      let brushRadius = Number(options.brushSize) || 16;
      let drawing = false;
      let lastX = 0;
      let lastY = 0;

      const undoStack = [];
      const redoStack = [];

      function fillBlack() {
        ctx.save();
        ctx.globalCompositeOperation = "source-over";
        ctx.fillStyle = "#000000";
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        ctx.restore();
      }

      function snapshot() {
        const w = Math.max(1, canvas.width);
        const h = Math.max(1, canvas.height);
        return ctx.getImageData(0, 0, w, h);
      }

      function pushUndoState() {
        undoStack.push(snapshot());
        while (undoStack.length > MAX_HISTORY) {
          undoStack.shift();
        }
        redoStack.length = 0;
      }

      function restoreImageData(imgData) {
        if (!imgData) return;
        ctx.putImageData(imgData, 0, 0);
      }

      fillBlack();

      // Load reference image dimensions asynchronously if available
      if (imageUrl) {
        const img = new window.Image();
        img.onload = () => {
          const nw = Math.max(1, Number(img.naturalWidth || img.width) || 160);
          const nh = Math.max(1, Number(img.naturalHeight || img.height) || 120);
          if (undoStack.length === 0 && (canvas.width !== nw || canvas.height !== nh)) {
            canvas.width = nw;
            canvas.height = nh;
            fillBlack();
          }
        };
        img.onerror = () => {
          if (canvas.width < 1) canvas.width = 160;
          if (canvas.height < 1) canvas.height = 120;
          if (undoStack.length === 0) fillBlack();
        };
        img.src = String(imageUrl);
      }

      function toCanvasCoords(ev) {
        const rect = canvas.getBoundingClientRect();
        const rw = rect && rect.width > 0 ? rect.width : canvas.width || 160;
        const rh = rect && rect.height > 0 ? rect.height : canvas.height || 120;
        const left = rect ? rect.left : 0;
        const top = rect ? rect.top : 0;
        const x = ((ev.clientX - left) / Math.max(1, rw)) * canvas.width;
        const y = ((ev.clientY - top) / Math.max(1, rh)) * canvas.height;
        return {
          x: Number.isFinite(x) ? x : 0,
          y: Number.isFinite(y) ? y : 0,
        };
      }

      function drawSegment(x0, y0, x1, y1) {
        ctx.save();
        ctx.globalCompositeOperation = "source-over";
        ctx.strokeStyle = activeTool === "eraser" ? "#000000" : "#ffffff";
        ctx.fillStyle = activeTool === "eraser" ? "#000000" : "#ffffff";
        ctx.lineWidth = brushRadius;
        ctx.lineCap = "round";
        ctx.lineJoin = "round";
        ctx.beginPath();
        ctx.moveTo(x0, y0);
        ctx.lineTo(x1, y1);
        ctx.stroke();
        ctx.restore();
      }

      canvas.addEventListener("pointerdown", (ev) => {
        if (canvas.width < 1) canvas.width = 160;
        if (canvas.height < 1) canvas.height = 120;
        pushUndoState();
        drawing = true;
        msgEl.textContent = "";
        const pt = toCanvasCoords(ev);
        lastX = pt.x;
        lastY = pt.y;
        drawSegment(lastX, lastY, lastX, lastY);
      });

      canvas.addEventListener("pointermove", (ev) => {
        if (!drawing) return;
        const pt = toCanvasCoords(ev);
        drawSegment(lastX, lastY, pt.x, pt.y);
        lastX = pt.x;
        lastY = pt.y;
      });

      const stopDrawing = (ev) => {
        if (!drawing) return;
        const pt = toCanvasCoords(ev);
        drawSegment(lastX, lastY, pt.x, pt.y);
        drawing = false;
      };
      canvas.addEventListener("pointerup", stopDrawing);
      canvas.addEventListener("pointercancel", () => { drawing = false; });

      brushBtn.addEventListener("click", () => { activeTool = "brush"; });
      eraserBtn.addEventListener("click", () => { activeTool = "eraser"; });

      undoBtn.addEventListener("click", () => {
        if (!undoStack.length) return;
        redoStack.push(snapshot());
        const prev = undoStack.pop();
        restoreImageData(prev);
      });

      redoBtn.addEventListener("click", () => {
        if (!redoStack.length) return;
        undoStack.push(snapshot());
        while (undoStack.length > MAX_HISTORY) undoStack.shift();
        const next = redoStack.pop();
        restoreImageData(next);
      });

      clearBtn.addEventListener("click", () => {
        pushUndoState();
        fillBlack();
      });

      function hasPaintedPixels() {
        const w = Math.max(1, canvas.width);
        const h = Math.max(1, canvas.height);
        const data = ctx.getImageData(0, 0, w, h).data;
        for (let i = 0; i < data.length; i += 4) {
          if (data[i] > 10 || data[i + 1] > 10 || data[i + 2] > 10) {
            return true;
          }
        }
        return false;
      }

      doneBtn.addEventListener("click", () => {
        if (!hasPaintedPixels()) {
          msgEl.textContent = "Mask is empty — please paint or draw a mask area first.";
          return;
        }
        canvas.toBlob((blob) => {
          if (typeof options.onDone === "function") {
            options.onDone(blob);
          }
          resolve(blob);
        }, "image/png");
      });
    });
  }

  window.openPainter = openPainter;
  window.StudioPaint = { open: openPainter };
})();
