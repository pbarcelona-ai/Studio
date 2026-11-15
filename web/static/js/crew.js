// studio/crew.js - the "Format and project rules" card: choose the book's format recipe, edit the project rules every crew member follows,
// and see the crew. A save carries the version it was based on; if the rules changed elsewhere meanwhile, the server answers 409 and the
// card offers "Keep mine" / "Keep the saved version". Classic script: uses $, api, hdr and cur() from core.js. Server: studio_app/crew_routes.py.
(function () {
  const sel = $("crewRecipe"), rules = $("crewRules"), note = $("crewNote");
  if (!sel || !rules) return;
  let slug = "", rev = 0, recipes = [], loaded = false;

  function about() {
    const r = recipes.find(x => x.name === sel.value);
    $("crewRecipeAbout").textContent = r ? `${r.about} ${r.aspect}${r.target_minutes ? `, about ${r.target_minutes} min` : ""}${r.series ? ", in episodes" : ""}.` : "The Studio's normal film path.";
  }

  async function load(p) {
    slug = p && !p.legacy && !p.not_started ? p.slug : "";       // the server keeps rules only for a book that has been read
    if (!slug) { note.textContent = !p ? "Pick a book first." : "Read the book first, then choose its format and rules here."; return; }
    try {
      const [rc, pr] = await Promise.all([api(`/api/recipes?project=${encodeURIComponent(slug)}`), api(`/api/project_rules?project=${encodeURIComponent(slug)}`)]);
      recipes = rc.recipes;
      sel.replaceChildren(new Option("Normal film path", ""), ...recipes.map(r => new Option(r.title, r.name)));
      sel.value = rc.chosen || "";
      rules.value = pr.body; rev = pr.rev;
      $("crewConflict").classList.add("hidden");
      note.textContent = pr.rev ? `Version ${pr.rev}` : "No rules yet.";
      about();
    } catch (e) { note.textContent = e.message || String(e); }
    if (!loaded) {
      loaded = true;
      try {
        const c = await api("/api/crew");
        $("crewRoles").replaceChildren(...c.roles.map(r => { const li = document.createElement("li"); li.textContent = r.title; return li; }));
      } catch (e) { /* the crew list is only information */ }
    }
  }

  async function save(body, baseRev) {
    const r = await fetch("/api/project_rules", { method: "POST", headers: { ...hdr, "Content-Type": "application/json" }, body: JSON.stringify({ project: slug, body, rev: baseRev }) });
    const j = await r.json();
    if (r.status === 409) {
      $("crewTheirs").value = j.current.body; rev = j.current.rev;
      $("crewConflict").classList.remove("hidden");
      note.textContent = "";
      return;
    }
    if (!r.ok) throw new Error(j.error || r.statusText);
    rev = j.rev; rules.value = j.body;
    $("crewConflict").classList.add("hidden");
    note.textContent = `Saved (version ${j.rev}).`;
  }

  sel.addEventListener("change", async () => {
    about();
    try { await api("/api/recipe", { project: slug, name: sel.value }); note.textContent = "Format saved."; } catch (e) { note.textContent = e.message || String(e); }
  });
  $("crewRulesSave").addEventListener("click", () => save(rules.value, rev).catch(e => { note.textContent = e.message || String(e); }));
  $("crewKeepMine").addEventListener("click", () => save(rules.value, rev).catch(e => { note.textContent = e.message || String(e); }));
  $("crewKeepTheirs").addEventListener("click", () => { rules.value = $("crewTheirs").value; $("crewConflict").classList.add("hidden"); note.textContent = `Version ${rev}`; });

  window.loadCrewCard = load;
})();
