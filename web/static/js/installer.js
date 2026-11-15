// The install page (scripts/install_studio.py): the optional parts and Start on a first install, then the shared progress screen,
// then "Open the Studio". Every request carries the page's token (from ?t= in its address).
(function () {
  const token = new URLSearchParams(location.search).get("t") || "";
  const call = async (path, body) => {
    const r = await fetch(path, body === undefined ? { headers: { "X-Token": token } }
      : { method: "POST", headers: { "X-Token": token, "Content-Type": "application/json" }, body: JSON.stringify(body) });
    if (!r.ok) throw new Error((await r.text()) || r.statusText);
    return (r.headers.get("Content-Type") || "").includes("json") ? r.json() : r.text();
  };
  const esc = s => String(s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const choose = document.getElementById("choose"), open = document.getElementById("openStudio");
  let mounted = false;

  function showProgress() {
    if (mounted) return;
    mounted = true;
    choose.hidden = true;
    StudioProgress.mount(document.getElementById("progress"), {
      get: () => call("/api/state"), post: what => call("/api/" + what, {}), log: () => call("/api/log"),
      onState: S => { open.hidden = S.state !== "done"; },
    });
  }
  open.addEventListener("click", async () => {
    try { await call("/api/open", {}); document.getElementById("bye").hidden = false; open.disabled = true; }
    catch (e) { alert("The Studio could not start: " + e.message); }
  });
  (async () => {
    const S = await call("/api/state");
    document.getElementById("ver").textContent = "Version " + S.version;
    if (!S.first || S.state !== "ready") return showProgress();
    document.getElementById("parts").innerHTML = S.parts.map(p =>
      `<label class="part"><input type="checkbox" name="part" value="${esc(p.id)}"> ${esc(p.title)} <span class="size">(${esc(p.size)}, optional)</span></label>`).join("");
    choose.hidden = false;
    document.getElementById("start").addEventListener("click", async () => {
      const options = {};
      document.querySelectorAll("input[name=part]").forEach(b => { options[b.value] = b.checked; });
      await call("/api/start", { options });
      showProgress();
    });
  })().catch(e => { document.getElementById("progress").textContent = "The installer did not answer: " + e.message; });
})();
