// studio/nav.js - the Advanced group of tabs (Models, Single Prompts, Library, Compare). The main flow is the four tabs before it.
// Classic script: loaded after shell.js, which switches tabs. The group opens by itself when one of its tabs is shown.
(function () {
  const toggle = document.getElementById("advToggle"), group = document.getElementById("advTabs");
  if (!toggle || !group) return;
  const set = open => { group.classList.toggle("hidden", !open); toggle.setAttribute("aria-expanded", String(open)); };
  toggle.addEventListener("click", () => set(group.classList.contains("hidden")));
  group.querySelectorAll(".tab-btn").forEach(b => b.addEventListener("click", () => set(true)));
  const active = group.querySelector(".tab-btn.active");
  if (active) set(true);
  // A step or command that opens an advanced tab by clicking its (hidden) button shows the group too.
  new MutationObserver(() => { if (group.querySelector(".tab-btn.active")) set(true); }).observe(group, { subtree: true, attributes: true, attributeFilter: ["class"] });
})();

// ---- adult-content models: hidden and refused until switched on (server: /api/adult_models)
function syncAdultToggle() { const t = document.getElementById("adultToggle"); if (t && typeof ST !== "undefined" && ST && ST.adult_models) t.checked = ST.adult_models.enabled; }
document.getElementById("adultToggle").addEventListener("change", async e => {
  const t = e.target;
  if (t.checked && !confirm("Show the adult-content models? They are for clearly adult, fictional work only, and they can make explicit pictures and video.")) { t.checked = false; return; }
  try {
    await api("/api/adult_models", { enabled: t.checked });
    await loadStatus();
    $("vmodels").innerHTML = modelGroupsHtml("vmodel", ST.video_groups, ST.video_models);
    $("imodels").innerHTML = modelGroupsHtml("imodel", ST.image_groups, ST.image_models || []);
    if (typeof updatePromptModels === "function") updatePromptModels();
    if (typeof applyConstraints === "function") applyConstraints();
  } catch (err) { t.checked = !t.checked; alert(err.message); }
});
window.addEventListener("load", () => setTimeout(syncAdultToggle, 800));
