// studio/params.js - global parameters and the remaining tab logic
// Classic script: shares globals with the other studio/*.js files; load order is set in index.html.
// ---- Global Parameters ----
async function loadGlobalParams(project) {
  // If no project specified, load from localStorage (fallback for initial load)
  if (!project) {
    const pos = localStorage.getItem("globalPositives") || "";
    const neg = localStorage.getItem("globalNegatives") || "";
    if ($("globalPositives")) $("globalPositives").value = pos;
    if ($("globalNegatives")) $("globalNegatives").value = neg;
    return;
  }

  // Load from server
  try {
    const result = await api(`/api/global_params?project=${encodeURIComponent(project)}`);
    if ($("globalPositives")) $("globalPositives").value = result.positives || "";
    if ($("globalNegatives")) $("globalNegatives").value = result.negatives || "";
    // Also cache in localStorage for offline/fallback use
    localStorage.setItem("globalPositives", result.positives || "");
    localStorage.setItem("globalNegatives", result.negatives || "");
  } catch (e) {
    // Fallback to localStorage if server fails
    const pos = localStorage.getItem("globalPositives") || "";
    const neg = localStorage.getItem("globalNegatives") || "";
    if ($("globalPositives")) $("globalPositives").value = pos;
    if ($("globalNegatives")) $("globalNegatives").value = neg;
  }
}

async function saveGlobalParams() {
  if (!$("globalPositives") || !$("globalNegatives")) return;
  const positives = $("globalPositives").value.trim();
  const negatives = $("globalNegatives").value.trim();

  // Validate format: comma-separated keywords, no newlines
  function validateFormat(value, fieldName) {
    if (!value) return { valid: true, value: "" };

    // Check for newlines (should be comma-separated)
    if (value.includes("\n")) {
      return { valid: false, error: `${fieldName}: newlines are not allowed. Use comma-separated values.` };
    }

    // Normalize: split by comma, trim each part, filter empty, rejoin with ", "
    const parts = value.split(",").map(s => s.trim()).filter(s => s);
    const normalized = parts.join(", ");

    // Check for potentially problematic characters
    const hasBadChars = /[<>|{}\[\]\\]/.test(normalized);
    if (hasBadChars) {
      return { valid: false, error: `${fieldName}: contains invalid characters (< > | { } [ ] \\).` };
    }

    return { valid: true, value: normalized };
  }

  const posValidation = validateFormat(positives, "Global Positives");
  const negValidation = validateFormat(negatives, "Global Negatives");

  if (!posValidation.valid || !negValidation.valid) {
    const statusEl = $("globalStatus");
    if (statusEl) {
      statusEl.textContent = (posValidation.error || "") + " " + (negValidation.error || "");
      statusEl.className = "err";
      setTimeout(() => { statusEl.textContent = ""; }, 5000);
    }
    return;
  }

  // Use normalized values
  const normalizedPositives = posValidation.value;
  const normalizedNegatives = negValidation.value;

  // Save to localStorage immediately for fast UI feedback
  localStorage.setItem("globalPositives", normalizedPositives);
  localStorage.setItem("globalNegatives", normalizedNegatives);

  // Update the textareas with normalized values
  $("globalPositives").value = normalizedPositives;
  $("globalNegatives").value = normalizedNegatives;

  // Save to server if we have a project
  const project = $("proj").value;
  if (project) {
    try {
      await api("/api/global_params", {
        project: project,
        positives: normalizedPositives,
        negatives: normalizedNegatives
      });
      const statusEl = $("globalStatus");
      if (statusEl) {
        statusEl.textContent = "Saved to project";
        statusEl.className = "ok";
        setTimeout(() => { statusEl.textContent = ""; }, 2000);
      }
    } catch (e) {
      const statusEl = $("globalStatus");
      if (statusEl) {
        statusEl.textContent = "Saved to browser only (server failed: " + e.message + ")";
        statusEl.className = "warn";
        setTimeout(() => { statusEl.textContent = ""; }, 3000);
      }
    }
  } else {
    const statusEl = $("globalStatus");
    if (statusEl) {
      statusEl.textContent = "Saved to browser storage (no project selected)";
      statusEl.className = "warn";
      setTimeout(() => { statusEl.textContent = ""; }, 2000);
    }
  }
}

// Load global params on startup (from localStorage)
loadGlobalParams();

async function loadGlobalParamsFromServer() {
  const project = $("proj").value;
  if (!project) {
    const statusEl = $("globalStatus");
    if (statusEl) {
      statusEl.textContent = "No project selected";
      statusEl.className = "warn";
      setTimeout(() => { statusEl.textContent = ""; }, 2000);
    }
    return;
  }

  const statusEl = $("globalStatus");
  if (statusEl) {
    statusEl.textContent = "Loading...";
    statusEl.className = "warn";
  }

  try {
    const result = await api(`/api/global_params?project=${encodeURIComponent(project)}`);
    if ($("globalPositives")) $("globalPositives").value = result.positives || "";
    if ($("globalNegatives")) $("globalNegatives").value = result.negatives || "";
    // Also cache in localStorage for offline/fallback use
    localStorage.setItem("globalPositives", result.positives || "");
    localStorage.setItem("globalNegatives", result.negatives || "");

    if (statusEl) {
      statusEl.textContent = "Loaded from project";
      statusEl.className = "ok";
      setTimeout(() => { statusEl.textContent = ""; }, 2000);
    }
  } catch (e) {
    if (statusEl) {
      statusEl.textContent = "Failed to load: " + e.message;
      statusEl.className = "err";
      setTimeout(() => { statusEl.textContent = ""; }, 3000);
    }
  }
}

// Wire up event listeners
$("charSeries").onchange = () => { loadCharList(); updateRefDir(); };
$("charList").onchange = () => { if ($("charList").value) loadCharacter($("charSeries").value, $("charList").value); updateCharButtons(); };
$("bCharNewSeries").onclick = newSeries;
$("bCharNew").onclick = newCharacter;
$("bCharSave").onclick = saveCharacter;
$("bCharDelete").onclick = deleteCharacter;
$("bCharGenPrompt").onclick = showCharacterPrompt;
$("bCharSync").onclick = syncFromProject;
$("bCharSend").onclick = sendToBook;
$("charPickAll").onchange = () => { document.querySelectorAll("#charTableBody .charPick").forEach(e => { e.checked = $("charPickAll").checked; }); updateCharButtons(); };
$("bCharCopyAll").onclick = copyAllTokens;
$("bCharRefreshAll").onclick = loadCharAllTokens;
$("bCharOpenRefDir").onclick = openRefDir;
$("charRefThumbs").addEventListener("click", async e => {
  const b = e.target.closest("[data-useref]");
  if (!b) return;
  try {
    await api("/api/characters", { action: "use_reference", series: $("charSeries").value, name: $("charName").value.trim(), path: b.dataset.useref });
    await loadCharacter($("charSeries").value, $("charName").value.trim());
    await loadCharRefs();
    showCharStatus("Face chosen");
  } catch (err) { showCharStatus(err.message, true); }
});
document.addEventListener("change", e => { if (e.target.name === "imodel") loadCharRefs(); });
$("autoClean").addEventListener("change", async e => {
  try { await api("/api/auto_cleanup", { on: e.target.checked }); }
  catch (err) { e.target.checked = !e.target.checked; clnStatus(err.message, "err"); }
});
$("bFilm").addEventListener("click", runFilm);
$("bFilmStop").addEventListener("click", () => api("/api/stop", {}).catch(() => {}));
$("proj").addEventListener("change", () => showFilmStatus($("proj").value).catch(() => {}));
$("showAdvanced").checked = localStorage.getItem("showAdvancedModels") === "1";
function applyShowAdvanced() { $("modelGrid").classList.toggle("hide-advanced", !$("showAdvanced").checked); }
$("showAdvanced").addEventListener("change", () => { localStorage.setItem("showAdvancedModels", $("showAdvanced").checked ? "1" : "0"); applyShowAdvanced(); });
applyShowAdvanced();
$("sbFaces").addEventListener("click", async () => {
  const series = $("kfseries").value;
  $("sbStatus").textContent = "Checking faces; see the log. Press Show storyboard when it ends.";
  try { await api("/api/face_check", { project: $("proj").value, series, look: radio("look") || "", ...(([s, e]) => s ? { start: s, end: e } : {})(($("sbMovie").value || "").split("-").map(Number)) }); }
  catch (err) { $("sbStatus").textContent = err.message; }
});
$("bCharGenerate").onclick = generateCharacterImage;
$("bGlobalRead").onclick = loadGlobalParamsFromServer;
$("bGlobalSave").onclick = saveGlobalParams;
$("charName").addEventListener("input", () => { updateRefDir(); updateCharButtons(); updatePromptPreview(); });
$("charVisualToken").addEventListener("input", () => { updateCharButtons(); updatePromptPreview(); });
$("charTriggerWords").addEventListener("input", updatePromptPreview);
$("charClothing").addEventListener("input", () => { updateCharButtons(); updatePromptPreview(); });
$("charVoice").addEventListener("input", updatePromptPreview);
$("charConsistency").addEventListener("input", updatePromptPreview);
$("charRefImages").addEventListener("input", updatePromptPreview);
$("charArchetype").addEventListener("change", updatePromptPreview);

// Add event listeners for dynamic physical traits and LoRA fields (delegated since they're created dynamically)
document.addEventListener("input", (e) => {
  if (e.target.id && (e.target.id.startsWith("trait_") || e.target.id.startsWith("lora_"))) {
    updatePromptPreview();
  }
});

// Add event listener for view dropdown to update preview
$("charGenView").addEventListener("change", updatePromptPreview);

// Load character series and archetypes on startup
loadCharSeries();
loadCharArchetypes();

// Initialize theme
initTheme();

// Update status badge when connected
const originalLoadStatus = loadStatus;
loadStatus = async function(applyDef) {
  await originalLoadStatus(applyDef);
  const badge = $("statusBadge");
  if (badge) {
    badge.className = "status-badge ok";
    badge.querySelector("span:last-child").textContent = "Connected";
  }
};
