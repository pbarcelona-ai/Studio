/* Universal draggable support for all Studio popups, modals, native <dialog>s, command palette, and floating panels. */
(function () {
  "use strict";

  const DRAG_THRESHOLD_PX = 4;
  const INTERACTIVE_SELECTOR = "button, a, input, select, textarea, label, [contenteditable='true'], [role='menuitem']";

  function isInteractive(el, handle) {
    if (!el || el === handle) return false;
    const hit = el.closest(INTERACTIVE_SELECTOR);
    if (!hit) return false;
    // Allow #chatToggle (which is itself a <button> acting as the Producer Chat title bar) to drag after threshold
    if (hit === handle && handle.id === "chatToggle") return false;
    return handle.contains(hit);
  }

  function clampPosition(left, top, width, height) {
    const vw = window.innerWidth || document.documentElement.clientWidth || 1024;
    const vh = window.innerHeight || document.documentElement.clientHeight || 768;
    const minVisibleX = Math.min(80, Math.max(40, width * 0.25));
    const minLeft = -width + minVisibleX;
    const maxLeft = vw - minVisibleX;
    const minTop = 0;
    const maxTop = Math.max(0, vh - Math.min(48, Math.max(32, height)));
    return {
      left: Math.round(Math.min(Math.max(left, minLeft), maxLeft)),
      top: Math.round(Math.min(Math.max(top, minTop), maxTop)),
    };
  }

  function resetPopupPosition(target) {
    if (!target || !target.classList.contains("popup-is-moved")) return;
    target.classList.remove("popup-is-moved", "popup-is-dragging");
    const saved = target._popupOrigInlineStyle;
    if (saved) {
      ["position", "left", "top", "right", "bottom", "margin", "width", "transform"].forEach((prop) => {
        target.style[prop] = saved[prop] || "";
      });
    } else {
      target.style.position = "";
      target.style.left = "";
      target.style.top = "";
      target.style.right = "";
      target.style.bottom = "";
      target.style.margin = "";
      target.style.width = "";
      target.style.transform = "";
    }
  }

  function makeDraggable(target, handle) {
    if (!target || !handle) return;
    if (target.dataset.popupDraggableBound === "1") return;
    target.dataset.popupDraggableBound = "1";
    handle.classList.add("popup-drag-handle");
    if (!handle.getAttribute("title")) {
      handle.setAttribute("title", "Drag to move · Double-click to reset position");
    }

    let pointerId = null;
    let startX = 0;
    let startY = 0;
    let origLeft = 0;
    let origTop = 0;
    let boxW = 0;
    let boxH = 0;
    let dragging = false;
    let suppressNextClick = false;

    handle.addEventListener("dblclick", (e) => {
      if (isInteractive(e.target, handle)) return;
      resetPopupPosition(target);
    });

    handle.addEventListener(
      "click",
      (e) => {
        if (suppressNextClick) {
          suppressNextClick = false;
          e.preventDefault();
          e.stopPropagation();
        }
      },
      true
    );

    handle.addEventListener("pointerdown", (e) => {
      if (e.button !== 0) return;
      if (isInteractive(e.target, handle)) return;
      const rect = target.getBoundingClientRect();
      if (rect.width === 0 && rect.height === 0) return;

      pointerId = e.pointerId;
      startX = e.clientX;
      startY = e.clientY;
      origLeft = rect.left;
      origTop = rect.top;
      boxW = rect.width;
      boxH = rect.height;
      dragging = false;

      if (!target._popupOrigInlineStyle) {
        target._popupOrigInlineStyle = {
          position: target.style.position,
          left: target.style.left,
          top: target.style.top,
          right: target.style.right,
          bottom: target.style.bottom,
          margin: target.style.margin,
          width: target.style.width,
          transform: target.style.transform,
        };
      }

      if (typeof handle.setPointerCapture === "function") {
        try {
          handle.setPointerCapture(pointerId);
        } catch (_) {
          /* ignore capture failures on synthetic events */
        }
      }
    });

    handle.addEventListener("pointermove", (e) => {
      if (pointerId === null || e.pointerId !== pointerId) return;
      const dx = e.clientX - startX;
      const dy = e.clientY - startY;

      if (!dragging) {
        if (Math.hypot(dx, dy) < DRAG_THRESHOLD_PX) return;
        dragging = true;
        target.classList.add("popup-is-moved", "popup-is-dragging");
        target.style.position = "fixed";
        target.style.right = "auto";
        target.style.bottom = "auto";
        target.style.margin = "0";
        target.style.width = `${Math.round(boxW)}px`;
        target.style.transform = "none";
      }

      const pos = clampPosition(origLeft + dx, origTop + dy, boxW, boxH);
      target.style.left = `${pos.left}px`;
      target.style.top = `${pos.top}px`;
      e.preventDefault();
    });

    const endDrag = (e) => {
      if (pointerId === null || (e && e.pointerId !== pointerId)) return;
      const pid = pointerId;
      pointerId = null;
      if (typeof handle.releasePointerCapture === "function") {
        try {
          if (handle.hasPointerCapture && handle.hasPointerCapture(pid)) {
            handle.releasePointerCapture(pid);
          }
        } catch (_) {
          /* ignore */
        }
      }
      if (dragging) {
        dragging = false;
        suppressNextClick = true;
        target.classList.remove("popup-is-dragging");
        setTimeout(() => {
          suppressNextClick = false;
        }, 0);
      }
    };

    handle.addEventListener("pointerup", endDrag);
    handle.addEventListener("pointercancel", endDrag);
  }

  function findBestHandle(box) {
    if (!box) return null;
    return (
      box.querySelector(":scope > .modal__header") ||
      box.querySelector(":scope > .v2-kf-modal__hdr") ||
      box.querySelector(":scope > header") ||
      box.querySelector(".modal__header") ||
      box.querySelector(":scope > h1, :scope > h2, :scope > h3") ||
      box
    );
  }

  function looksLikeBackdrop(el) {
    if (!(el instanceof HTMLElement)) return false;
    if (el.classList.contains("modal-overlay") || el.classList.contains("v2-kf-modal-backdrop")) {
      return true;
    }
    if (el.id === "v2InstallApprovalBackdrop" || el.id === "v2AutopilotModalBackdrop") {
      return true;
    }
    // Dynamic full-screen fixed modal backdrops wrapping a single card element
    const st = el.style;
    if (
      st &&
      st.position === "fixed" &&
      (st.inset === "0px" || st.inset === "0") &&
      el.children.length === 1 &&
      el.firstElementChild instanceof HTMLElement
    ) {
      return true;
    }
    return false;
  }

  function bindNode(node) {
    if (!(node instanceof HTMLElement)) return;

    // 1. Standard .modal-overlay and custom modal backdrops
    if (looksLikeBackdrop(node)) {
      const box =
        node.querySelector(":scope > .modal") ||
        node.querySelector(":scope > .v2-kf-modal") ||
        node.firstElementChild;
      if (box instanceof HTMLElement) {
        makeDraggable(box, findBestHandle(box));
      }
    }

    // 2. Native <dialog> elements (Setup, Local LLM, Old Pictures, etc.)
    if (node.tagName === "DIALOG") {
      makeDraggable(node, findBestHandle(node));
    }

    // 3. Command Palette
    if (node.id === "cmd-palette") {
      makeDraggable(node, node);
    }

    // 4. Floating Producer Chat panel
    if (node.id === "chatPanel") {
      const toggle = node.querySelector("#chatToggle") || node;
      makeDraggable(node, toggle);
    }

    // 5. Generic role="dialog" / role="alertdialog" popups not inside a backdrop
    const role = node.getAttribute("role");
    if ((role === "dialog" || role === "alertdialog") && !looksLikeBackdrop(node) && node.tagName !== "DIALOG") {
      makeDraggable(node, findBestHandle(node));
    }
  }

  function scanTree(root) {
    if (!root) return;
    if (root instanceof HTMLElement) bindNode(root);
    if (typeof root.querySelectorAll !== "function") return;
    root
      .querySelectorAll('.modal-overlay, .v2-kf-modal-backdrop, dialog, #cmd-palette, #chatPanel, [role="dialog"], [role="alertdialog"]')
      .forEach((el) => bindNode(el));
  }

  function clampAllMovedPopups() {
    document.querySelectorAll(".popup-is-moved").forEach((el) => {
      if (!(el instanceof HTMLElement)) return;
      const rect = el.getBoundingClientRect();
      if (rect.width === 0 && rect.height === 0) return;
      const pos = clampPosition(rect.left, rect.top, rect.width, rect.height);
      el.style.left = `${pos.left}px`;
      el.style.top = `${pos.top}px`;
    });
  }

  function initDraggablePopups() {
    scanTree(document.body);

    if (typeof MutationObserver === "function" && document.body) {
      const obs = new MutationObserver((mutations) => {
        mutations.forEach((m) => {
          m.addedNodes.forEach((n) => {
            if (n instanceof HTMLElement) {
              scanTree(n);
              // Re-check handle if a <dialog> is populated right after appendChild
              if (n.parentElement && n.parentElement.tagName === "DIALOG") {
                const dlg = n.parentElement;
                if (dlg.dataset.popupDraggableBound !== "1") {
                  makeDraggable(dlg, findBestHandle(dlg));
                }
              }
            }
          });
        });
      });
      obs.observe(document.body, { childList: true, subtree: true });
    }

    window.addEventListener("resize", clampAllMovedPopups);
    window.resetPopupPosition = resetPopupPosition;
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initDraggablePopups);
  } else {
    initDraggablePopups();
  }
})();
