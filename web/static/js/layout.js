// ===== layout helpers =====
(function () {
  // 1. the tab bar sticks right below the header, whatever height the header has
  const header = document.querySelector("header.studio-header");
  const setHeaderHeight = () => { if (header) document.documentElement.style.setProperty("--header-h", header.offsetHeight + "px"); };
  setHeaderHeight();
  window.addEventListener("resize", setHeaderHeight);
  window.addEventListener("load", setHeaderHeight);

  // 2. one sentence per line in help text. Splits TEXT nodes only (so <code> etc. survive) and also catches text
  //    the page writes later (model notes, hints, errors). Idempotent: a split node no longer matches, so there is no loop.
  const SELECTOR = ".warn, small, .card__subtitle, .empty-state span";
  const SENTENCE_END = /([.!?])\s+(?=[A-Z])/g;
  function splitSentences(root) {
    const targets = root.matches && root.matches(SELECTOR) ? [root] : [];
    if (root.querySelectorAll) targets.push(...root.querySelectorAll(SELECTOR));
    for (const el of targets) {
      const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
      const hits = [];
      for (let n = walker.nextNode(); n; n = walker.nextNode()) { SENTENCE_END.lastIndex = 0; if (SENTENCE_END.test(n.nodeValue)) hits.push(n); }
      for (const n of hits) {
        const parts = n.nodeValue.replace(SENTENCE_END, "$1\u0001").split("\u0001");
        const frag = document.createDocumentFragment();
        parts.forEach((t, i) => { if (i) frag.appendChild(document.createElement("br")); frag.appendChild(document.createTextNode(t)); });
        n.replaceWith(frag);
      }
    }
  }
  let queued = false;
  const run = () => { queued = false; splitSentences(document.body); };
  new MutationObserver(() => { if (!queued) { queued = true; requestAnimationFrame(run); } })
    .observe(document.body, { childList: true, subtree: true, characterData: true });
  run();
})();
