// studio/compare.js - Side-by-side & wipe comparison for images and synchronized dual-video playback (ported from freefield).
(function () {
  "use strict";

  function openCompare(itemA, itemB, options = {}) {
    const host = options.container || document.body;
    host.textContent = "";

    const a = { ...(itemA || {}) };
    const b = { ...(itemB || {}) };
    const bothImages = a.kind === "image" && b.kind === "image";
    const bothVideos = a.kind === "video" && b.kind === "video";
    const kindMatch = a.kind === b.kind;

    const wrap = document.createElement("div");
    wrap.className = "studio-compare";

    const bar = document.createElement("div");
    bar.className = "compare-toolbar";

    const mkBtn = (text) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "btn btn--secondary";
      btn.textContent = text;
      bar.appendChild(btn);
      return btn;
    };

    const wipeBtn = mkBtn("Wipe");
    const sideBtn = mkBtn("Side-by-Side");
    const swapBtn = mkBtn("Swap");
    const closeBtn = mkBtn("Close");

    if (!kindMatch) {
      wipeBtn.disabled = true;
    }

    const stage = document.createElement("div");
    stage.className = "compare-stage wipe";
    stage.dataset.compareStage = "1";

    wrap.appendChild(bar);
    wrap.appendChild(stage);
    host.appendChild(wrap);

    let syncTimer = null;
    let wipePct = 50;
    let draggingWipe = false;
    let handleEl = null;
    let imgEls = [];
    let vidEls = [];

    function setWipePct(pct) {
      wipePct = Math.max(0, Math.min(100, Math.round(pct)));
      if (handleEl) {
        handleEl.style.left = `${wipePct}%`;
        handleEl.setAttribute("aria-valuenow", String(wipePct));
      }
      if (imgEls[1]) {
        imgEls[1].style.clipPath = `inset(0 0 0 ${wipePct}%)`;
      }
    }

    if (bothVideos) {
      const playBtn = mkBtn("Play Both");
      const muteABtn = mkBtn("Mute A");
      const muteBBtn = mkBtn("Mute B");

      const seek = document.createElement("input");
      seek.type = "range";
      seek.min = "0";
      seek.max = "100";
      seek.value = "0";
      bar.appendChild(seek);

      const vA = document.createElement("video");
      vA.src = String(a.src || "");
      if (a.duration !== undefined) vA.setAttribute("data-duration", String(a.duration));
      const vB = document.createElement("video");
      vB.src = String(b.src || "");
      if (b.duration !== undefined) vB.setAttribute("data-duration", String(b.duration));

      stage.appendChild(vA);
      stage.appendChild(vB);
      vidEls = [vA, vB];

      playBtn.addEventListener("click", () => {
        if (vA.paused || vB.paused) {
          vA.play();
          vB.play();
        } else {
          vA.pause();
          vB.pause();
        }
      });

      muteABtn.addEventListener("click", () => { vA.muted = !vA.muted; });
      muteBBtn.addEventListener("click", () => { vB.muted = !vB.muted; });

      const onSeek = () => {
        const pct = Math.max(0, Math.min(100, Number(seek.value) || 0)) / 100;
        for (const v of vidEls) {
          const d = Number(v.duration);
          if (Number.isFinite(d) && d > 0) {
            v.currentTime = Math.min(d, pct * d);
          }
        }
      };
      seek.addEventListener("input", onSeek);
      seek.addEventListener("change", onSeek);

      syncTimer = setInterval(() => {
        const tA = Number(vA.currentTime);
        const tB = Number(vB.currentTime);
        if (!Number.isFinite(tA) || !Number.isFinite(tB)) return;
        const dB = Number(vB.duration);
        const maxB = Number.isFinite(dB) && dB > 0 ? dB : Infinity;
        const targetB = Math.min(maxB, Math.max(0, tA));
        if (Math.abs(tB - targetB) > 0.35) {
          vB.currentTime = targetB;
        }
      }, 120);
    } else {
      const iA = document.createElement("img");
      iA.src = String(a.src || "");
      iA.alt = String(a.label || "A");
      const iB = document.createElement("img");
      iB.src = String(b.src || "");
      iB.alt = String(b.label || "B");
      stage.appendChild(iA);
      stage.appendChild(iB);
      imgEls = [iA, iB];

      if (bothImages) {
        handleEl = document.createElement("div");
        handleEl.className = "wipe-handle";
        handleEl.dataset.wipeHandle = "1";
        handleEl.setAttribute("role", "slider");
        handleEl.tabIndex = 0;
        stage.appendChild(handleEl);
        setWipePct(50);

        const updateFromPointer = (ev) => {
          const rect = stage.getBoundingClientRect();
          const rw = rect && rect.width > 0 ? rect.width : 320;
          const left = rect ? rect.left : 0;
          const ratio = ((ev.clientX - left) / rw) * 100;
          setWipePct(ratio);
        };

        stage.addEventListener("pointerdown", (ev) => {
          draggingWipe = true;
          updateFromPointer(ev);
        });
        stage.addEventListener("pointermove", (ev) => {
          if (!draggingWipe) return;
          updateFromPointer(ev);
        });
        stage.addEventListener("pointerup", (ev) => {
          if (draggingWipe) updateFromPointer(ev);
          draggingWipe = false;
        });

        handleEl.addEventListener("keydown", (ev) => {
          if (ev.key === "ArrowLeft") {
            ev.preventDefault();
            setWipePct(wipePct - 5);
          } else if (ev.key === "ArrowRight") {
            ev.preventDefault();
            setWipePct(wipePct + 5);
          }
        });
      }
    }

    wipeBtn.addEventListener("click", () => {
      if (wipeBtn.disabled) return;
      stage.classList.add("wipe");
      stage.classList.remove("side-by-side");
    });

    sideBtn.addEventListener("click", () => {
      stage.classList.remove("wipe");
      stage.classList.add("side-by-side");
    });

    swapBtn.addEventListener("click", () => {
      if (imgEls.length === 2) {
        const tmp = imgEls[0].src;
        imgEls[0].src = imgEls[1].src;
        imgEls[1].src = tmp;
      } else if (vidEls.length === 2) {
        const tmp = vidEls[0].src;
        vidEls[0].src = vidEls[1].src;
        vidEls[1].src = tmp;
      }
    });

    function cleanup() {
      if (syncTimer) {
        clearInterval(syncTimer);
        syncTimer = null;
      }
      for (const item of [a, b]) {
        const s = String(item.src || "");
        if (s && (item.revokeOnClose || s.startsWith("blob:"))) {
          try { window.URL.revokeObjectURL(s); } catch (_e) {}
        }
      }
    }

    closeBtn.addEventListener("click", cleanup);

    return {
      close: cleanup,
      setWipe: setWipePct,
    };
  }

  window.openCompare = openCompare;
  window.StudioCompare = { open: openCompare };
})();
