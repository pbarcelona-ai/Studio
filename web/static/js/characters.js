// studio/characters.js - Characters tab: management API and editor
// Classic script: shares globals with the other studio/*.js files; load order is set in index.html.
// ---- Character Management API ----
let charCurrentSeries = "";
let charCurrentCharacter = "";

async function loadCharSeries() {
  try {
    const j = await api("/api/characters?action=list_series");
    const series = j.series || [];
    $("charSeries").innerHTML = series.map(s => `<option value="${s}">${s}</option>`).join("");
    // Also populate the New Scene series dropdown
    $("newSceneSeries").innerHTML = series.map(s => `<option value="${s}">${s}</option>`).join("");
    $("castSeries").innerHTML = `<option value="">(none)</option>` + series.map(s => `<option value="${s}">${s}</option>`).join("");
    if (series.length) {
      $("charSeries").value = series[0];
      charCurrentSeries = series[0];
      await loadCharList();
    }
    updateCharButtons();
  } catch (e) {
    showCharStatus(e.message, true);
  }
}

async function loadCharList() {
  const series = $("charSeries").value;
  if (!series) {
    $("charList").innerHTML = "";
    updateCharButtons();
    return;
  }
  charCurrentSeries = series;
  try {
    const j = await api(`/api/characters?action=list&series=${encodeURIComponent(series)}`);
    const chars = j.characters || [];
    $("charList").innerHTML = '<option value="">(select a character)</option>' + chars.map(c => `<option value="${c.name}">${c.name}</option>`).join("");
    populateCharTable(chars, series);
    updateCharButtons();
    await loadCharAllTokens();
  } catch (e) {
    showCharStatus(e.message, true);
  }
  // Populate newSceneChapter with chapters from current project
  populateNewSceneChapters();

}

// Populate character data-table
function populateCharTable(characters, series) {
    const tbody = $('charTableBody');
    if (!tbody) return;
    if ($('charPickAll')) $('charPickAll').checked = false;
    
    if (!characters || characters.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;color:var(--fg-muted);padding:24px">No characters in this series</td></tr>';
        return;
    }
    
    tbody.innerHTML = characters.map(c => {
        const refCount = (c.reference_images || []).length;
        const hasLora = c.lora && (c.lora.repo || c.lora.trigger_word);
        return `
            <tr data-name="${escapeHtml(c.name)}" data-act="select-char" style="cursor:pointer">
                <td><input type="checkbox" class="charPick" data-name="${escapeHtml(c.name)}" data-act="pick-char" aria-label="Send ${escapeHtml(c.name)} to the book"></td>
                <td><strong>${escapeHtml(c.name)}</strong></td>
                <td>${escapeHtml(c.archetype || '—')}</td>
                <td><span class="badge ${refCount > 0 ? 'badge--success' : 'badge--neutral'}">${refCount}</span></td>
                <td><span class="badge ${hasLora ? 'badge--success' : 'badge--neutral'}">${hasLora ? '✓' : '—'}</span></td>
                <td>
                    <button class="btn btn-icon btn-ghost" data-act="edit-char" data-series="${escapeHtml(series)}" data-name="${escapeHtml(c.name)}" aria-label="Edit ${escapeHtml(c.name)}">✎</button>
                    <button class="btn btn-icon btn-ghost btn-danger" data-act="delete-char" data-series="${escapeHtml(series)}" data-name="${escapeHtml(c.name)}" aria-label="Delete ${escapeHtml(c.name)}">🗑</button>
                </td>
            </tr>
        `;
    }).join('');
}

function selectCharInTable(name) {
    // Update the select dropdown to match
    const select = $('charList');
    if (select) {
        for (let i = 0; i < select.options.length; i++) {
            if (select.options[i].value === name) {
                select.selectedIndex = i;
                select.dispatchEvent(new Event('change'));
                break;
            }
        }
    }
    // Highlight the row
    document.querySelectorAll('#charTableBody tr').forEach(tr => tr.style.background = '');
    const row = document.querySelector('#charTableBody tr[data-name="' + name.replace(/"/g, '\"') + '"]');
    if (row) row.style.background = 'var(--accent-light)';
}

function deleteCharacterConfirm(series, name) {
    if (confirm('Delete character "' + name + '" from series "' + series + '"? This cannot be undone.')) {
        // Call the existing delete function logic
        api('/api/characters', { action: 'delete', series: series, name: name }).then(() => {
            showToast('Character deleted', 'success');
            loadCharList();
            loadCharAllTokens();
        }).catch(e => showToast('Failed to delete: ' + e.message, 'error'));
    }
}


function populateNewSceneChapters() {
  const p = cur();
  if (!p || !p.chapters) {
    $("newSceneChapter").innerHTML = '<option value="">(no project selected or no chapters yet)</option>';
    return;
  }
  const chapterOptions = Array.from({ length: p.chapters }, (_, i) => i + 1)
    .map(ch => `<option value="${ch}">Chapter ${ch}</option>`).join("");
  $("newSceneChapter").innerHTML = '<option value="">(select a chapter)</option>' + chapterOptions;
}

async function loadCharAllTokens() {
  const series = $("charSeries").value;
  if (!series) return;
  try {
    const j = await api(`/api/characters?action=tokens&series=${encodeURIComponent(series)}`);
    if (j.tokens) {
      $("charAllTokens").textContent = j.tokens;
    } else {
      $("charAllTokens").innerHTML = '<span class="warn">No characters in this series yet.</span>';
    }
    $("bCharCopyAll").disabled = !j.tokens;
    $("bCharRefreshAll").disabled = false;
  } catch (e) {
    $("charAllTokens").innerHTML = `<span class="err">${e.message}</span>`;
  }
}


function updateRefDir() {
  const series = $("charSeries").value;
  const name = $("charName").value;
  if (series && name) {
    // This is the path structure used by character_tokens.py
    const refDir = `projects/characters/${series}/references/${charSlug(name)}/`;
    $("charRefDir").textContent = refDir;
    $("bCharOpenRefDir").disabled = false;
  } else {
    $("charRefDir").textContent = "";
    $("bCharOpenRefDir").disabled = true;
  }
}

function getCharFormData() {
  // Collect physical traits from dropdowns/inputs
  const physical_traits = {};
  const physicalFields = ["age", "height", "build", "skin", "hair", "facial_hair", "eyes", "expression", "ethnicity", "distinguishing_features"];
  for (const field of physicalFields) {
    const el = $(`trait_${field}`);
    if (el && el.value) physical_traits[field] = el.value;
  }

  // Collect LoRA info from dropdowns/inputs
  const lora = {};
  const loraFields = ["repo", "trigger_word", "base_model", "trained"];
  for (const field of loraFields) {
    const el = $(`lora_${field}`);
    if (el) {
      if (el.type === "checkbox") {
        lora[field] = el.checked;
      } else if (el.value) {
        lora[field] = el.value;
      }
    }
  }
  // Default LoRA values if not set
  if (!lora.trigger_word && $("charName").value) {
    lora.trigger_word = $("charName").value.toLowerCase().replace(/[^a-z0-9]/g, "_") + "_token";
  }
  if (!lora.base_model) lora.base_model = "LTX-Video";
  if (lora.trained === undefined) lora.trained = false;
  if (!lora.repo) lora.repo = "";

  return {
    name: $("charName").value.trim(),
    series: $("charSeries").value,
    archetype: $("charArchetype").value || undefined,
    visual_token: $("charVisualToken").value.trim(),
    trigger_words: $("charTriggerWords").value.split(",").map(s => s.trim()).filter(s => s),
    physical_traits: physical_traits,
    clothing: $("charClothing").value.trim(),
    voice: $("charVoice").value.trim(),
    lora: lora,
    reference_images: $("charRefImages").value.split("\n").map(s => s.trim()).filter(s => s),
    consistency_notes: $("charConsistency").value.trim(),
    stages: textToStages($("charStages").value)
  };
}

function updatePromptPreview() {
  const previewEl = $("charPromptPreview");
  if (!previewEl) return;

  // Read global parameters directly from saved localStorage (the saved file)
  const globalPositives = localStorage.getItem("globalPositives") || "";
  const globalNegatives = localStorage.getItem("globalNegatives") || "";

  // Build the base prompt parts
  const parts = [];

  // Visual token
  const visualToken = $("charVisualToken").value.trim();
  if (visualToken) parts.push(visualToken);

  // Physical traits from dropdowns/inputs
  const physicalFields = ["age", "height", "build", "skin", "hair", "facial_hair", "eyes", "expression", "ethnicity", "distinguishing_features"];
  const physicalTraits = {};
  for (const field of physicalFields) {
    const el = $(`trait_${field}`);
    if (el && el.value) physicalTraits[field] = el.value;
  }
  if (Object.keys(physicalTraits).length) {
    const desc = Object.entries(physicalTraits).map(([k, v]) => `${k}: ${v}`).join(", ");
    if (desc) parts.push(desc);
  }

  // Clothing
  const clothing = $("charClothing").value.trim();
  if (clothing) parts.push(`wearing ${clothing}`);

  // Consistency notes
  const consistency = $("charConsistency").value.trim();
  if (consistency) parts.push(consistency);

  // Global positives (from saved file)
  if (globalPositives) parts.push(globalPositives);


  const basePrompt = parts.join(", ");

  // Build negative prompt with global negatives (from saved file)
  const negativePrompt = globalNegatives;

  // Get view text from text input (not dropdown) and add to prompt if provided
  const viewText = $("charGenView") ? $("charGenView").value.trim() : "";
  const fullPrompt = viewText ? basePrompt + ", " + viewText : basePrompt;

  // Show just the exact prompt that will be sent
  previewEl.textContent = fullPrompt;
}

let charSavedAt = 0;
async function saveCharacter() {
  const data = getCharFormData();
  if (!data) return;
  if (!data.name) {
    showCharStatus("Character name is required", true);
    return;
  }
  if (!data.series) {
    showCharStatus("Series is required", true);
    return;
  }
  showCharStatus("Saving character…");
  $("bCharSave").disabled = true;
  try {
    const j = await api("/api/characters", { action: "save", character: data });
    showCharStatus("Character saved: " + j.path);
    charSavedAt = Date.now();             // reloading the character fires the archetype loader; its message must not hide this one
    await loadCharList();
    await loadCharAllTokens();
    await loadCharacter(data.series, data.name);
  } catch (e) {
    showCharStatus(e.message, true);
  }
  $("bCharSave").disabled = false;
}

async function deleteCharacter() {
  const series = $("charSeries").value;
  const name = $("charName").value;
  if (!series || !name) return;
  if (!confirm(`Delete character "${name}" from series "${series}"?`)) return;
  showCharStatus("Deleting character…");
  $("bCharDelete").disabled = true;
  try {
    await api("/api/characters", { action: "delete", series, name });
    showCharStatus("Character deleted");
    $("charName").value = "";
    $("charVisualToken").value = "";
    $("charTriggerWords").value = "";
    // Clear physical traits fields
    const physicalFields = ["age", "height", "build", "skin", "hair", "facial_hair", "eyes", "expression", "ethnicity", "distinguishing_features"];
    for (const field of physicalFields) {
      const el = $(`trait_${field}`);
      if (el) el.value = "";
    }
    $("charClothing").value = "";
    $("charVoice").value = "";
    // Clear LoRA fields
    const loraFields = ["repo", "trigger_word", "base_model", "trained"];
    for (const field of loraFields) {
      const el = $(`lora_${field}`);
      if (el) {
        if (el.type === "checkbox") el.checked = false;
        else el.value = "";
      }
    }
    $("charRefImages").value = "";
    $("charConsistency").value = "";
    $("charStages").value = "";
    charCurrentCharacter = "";
    await loadCharList();
    await loadCharAllTokens();
    updateRefDir();
  } catch (e) {
    showCharStatus(e.message, true);
  }
  $("bCharDelete").disabled = false;
}

async function newSeries() {
  const name = prompt("Enter new series name (lowercase, underscores):", "mcnally");
  if (!name) return;
  // Just select it - it will be created when first character is saved
  const options = [...$("charSeries").options].map(o => o.value);
  if (!options.includes(name)) {
    const opt = document.createElement("option");
    opt.value = name;
    opt.textContent = name;
    $("charSeries").appendChild(opt);
  }
  $("charSeries").value = name;
  await loadCharList();
}

async function newCharacter() {
  const series = $("charSeries").value;
  if (!series) {
    showCharStatus("Select a series first", true);
    return;
  }
  const name = prompt("Enter new character name:", "");
  if (!name) return;
  // Clear form for new character
  $("charName").value = name;
  $("charVisualToken").value = "";
  $("charTriggerWords").value = "";
  // Clear physical traits fields
  const physicalFields = ["age", "height", "build", "skin", "hair", "facial_hair", "eyes", "expression", "ethnicity", "distinguishing_features"];
  for (const field of physicalFields) {
    const el = $(`trait_${field}`);
    if (el) el.value = "";
  }
  $("charClothing").value = "";
  $("charVoice").value = "";
  // Clear and set default LoRA fields
  const loraFields = ["repo", "trigger_word", "base_model", "trained"];
  for (const field of loraFields) {
    const el = $(`lora_${field}`);
    if (el) {
      if (el.type === "checkbox") el.checked = false;
      else el.value = "";
    }
  }
  // Set default LoRA values
  const triggerEl = $("lora_trigger_word");
  if (triggerEl) triggerEl.value = name.toLowerCase().replace(/[^a-z0-9]/g, "_") + "_token";
  const baseModelEl = $("lora_base_model");
  if (baseModelEl) baseModelEl.value = "LTX-Video";
  const trainedEl = $("lora_trained");
  if (trainedEl && trainedEl.type === "checkbox") trainedEl.checked = false;
  $("charRefImages").value = "";
  $("charConsistency").value = "";
  $("charStages").value = "";
  charCurrentCharacter = name;
  updateRefDir();
  updateCharButtons();
  showCharStatus("Fill in the details and click Save Character");
}

async function syncFromProject() {
  const project = $("proj").value;
  const series = $("charSeries").value;
  if (!project || !series) {
    showCharStatus("Select a project and series first", true);
    return;
  }
  const overwrite = $("charSyncOverwrite").checked;
  $("bCharSync").disabled = true;
  try {
    if (overwrite) {                                   // count first, then ask: overwriting cannot be undone
      showCharStatus("Checking what would change…");
      const plan = await api("/api/characters", { action: "sync", project, series, overwrite: true, dry_run: true });
      if (!plan.updated) {
        showCharStatus(plan.added ? `Nothing to overwrite; ${plan.added} new character(s) will be added.` : `Nothing to sync: the continuity book's ${plan.total} character(s) are not in "${series}" yet or have no changes.`);
        if (!plan.added) { updateCharButtons(); return; }
      } else if (!confirm(`Update ${plan.updated} existing character(s) in "${series}" from ${project}'s continuity book` + (plan.added ? ` and add ${plan.added} new one(s)` : "") + `?\n\nThe continuity book's visual token, voice, clothing, traits and notes replace yours (only where the continuity has a value). Reference images, LoRA info and trigger words you added are kept.\n\nThis cannot be undone.`)) {
        showCharStatus("Sync cancelled; nothing was changed.");
        updateCharButtons();
        return;
      }
    }
    showCharStatus("Syncing from continuity book…");
    const j = await api("/api/characters", { action: "sync", project, series, overwrite });
    const parts = [];
    if (j.added) parts.push(`added ${j.added}`);
    if (j.updated) parts.push(`updated ${j.updated}`);
    if (j.skipped) parts.push(`${j.skipped} already in the series, left unchanged`);
    showCharStatus(parts.length ? `From ${project}'s continuity book: ${parts.join(", ")}.` : `Nothing to sync: ${project}'s continuity book has no characters.`);
    await loadCharList();
    await loadCharAllTokens();
  } catch (e) {
    showCharStatus(e.message, true);
  }
  updateCharButtons();
}

async function sendToBook() {
  const project = $("proj").value, series = $("charSeries").value;
  const names = [...document.querySelectorAll("#charTableBody .charPick:checked")].map(e => e.dataset.name);
  if (!project || !series || !names.length) { showCharStatus("Pick a book and a series, and tick at least one character", true); return; }
  $("bCharSend").disabled = true;
  try {
    showCharStatus("Checking what would change…");
    const plan = await api("/api/characters", { action: "send_to_book", project, series, names, dry_run: true });
    const miss = plan.missing.length ? ` (${plan.missing.join(", ")} cannot be sent: no visual token)` : "";
    if (!plan.updated && !plan.added) { showCharStatus(`Nothing to send: ${project}'s continuity book already matches${miss}.`); updateCharButtons(); return; }
    const what = [plan.updated ? `update ${plan.updated} character(s)` : "", plan.added ? `add ${plan.added} new one(s)` : ""].filter(Boolean).join(" and ");
    if (!confirm(`In ${project}'s continuity book, ${what} using the ${series} series' visual token and voice.\n\nChapters that are already written keep the old wording; chapters written afterwards use the new one.${miss}\n\nContinue?`)) {
      showCharStatus("Cancelled; the book was not changed."); updateCharButtons(); return;
    }
    const j = await api("/api/characters", { action: "send_to_book", project, series, names });
    showCharStatus(`Sent to ${project}: ${[j.updated ? `updated ${j.updated}` : "", j.added ? `added ${j.added}` : "", j.unchanged ? `${j.unchanged} already matched` : ""].filter(Boolean).join(", ")}${miss}.`);
  } catch (e) {
    showCharStatus(e.message, true);
  }
  updateCharButtons();
}

function copyAllTokens() {
  const text = $("charAllTokens").textContent;
  if (!text) return;
  navigator.clipboard.writeText(text).then(() => {
    showCharStatus("Copied to clipboard");
  }).catch(() => {
    showCharStatus("Failed to copy", true);
  });
}

// "Generate Prompt": show the current prompt in the Prompt Preview window; if there is nothing to build it from, say so there.
function showCharacterPrompt() {
  const preview = $("charPromptPreview");
  const hasName = !!$("charName").value.trim(), hasToken = !!$("charVisualToken").value.trim(), picked = !!$("charList").value;
  if (!$("charSeries").value) {
    preview.textContent = 'No series selected. Pick a Series above (or click New Series), then select a character under "Characters in this series".';
    return;
  }
  if (!picked && !hasName && !hasToken) {
    preview.textContent = 'No character selected. Choose one under "Characters in this series", or click New Character and enter a Character Name and Visual Token, then click Generate Prompt again.';
    return;
  }
  updatePromptPreview();          // shows the exact prompt that would be sent
  copyCharacterPrompt();          // and copies it to the clipboard, as before
}

function copyCharacterPrompt() {
  // Build the prompt (same logic as updatePromptPreview)
  // Read global parameters directly from saved localStorage (the saved file)
  const globalPositives = localStorage.getItem("globalPositives") || "";
  const globalNegatives = localStorage.getItem("globalNegatives") || "";

  const parts = [];

  const visualToken = $("charVisualToken").value.trim();
  if (visualToken) parts.push(visualToken);

  const physicalFields = ["age", "height", "build", "skin", "hair", "facial_hair", "eyes", "expression", "ethnicity", "distinguishing_features"];
  const physicalTraits = {};
  for (const field of physicalFields) {
    const el = $(`trait_${field}`);
    if (el && el.value) physicalTraits[field] = el.value;
  }
  if (Object.keys(physicalTraits).length) {
    const desc = Object.entries(physicalTraits).map(([k, v]) => `${k}: ${v}`).join(", ");
    if (desc) parts.push(desc);
  }

  const clothing = $("charClothing").value.trim();
  if (clothing) parts.push(`wearing ${clothing}`);

  const consistency = $("charConsistency").value.trim();
  if (consistency) parts.push(consistency);

  // Global positives (from saved file)
  if (globalPositives) parts.push(globalPositives);


  const basePrompt = parts.join(", ");

  // Get view text from text input (not dropdown) and add to prompt if provided
  const viewText = $("charGenView") ? $("charGenView").value.trim() : "";
  const fullPrompt = viewText ? basePrompt + ", " + viewText : basePrompt;

  // Copy to clipboard
  navigator.clipboard.writeText(fullPrompt).then(() => {
    showCharStatus("Prompt copied to clipboard");
  }).catch(() => {
    showCharStatus("Failed to copy prompt", true);
  });
}

async function openRefDir() {
  try {
    await api("/api/open_reference_folder", { series: $("charSeries").value, name: $("charName").value });
    showCharStatus("Reference folder opened");
  } catch (e) { showCharStatus(e.message, true); }
}

// The pictures of this character, with the one that stands for its face marked.
async function loadCharRefs() {
  const box = $("charRefThumbs"), series = $("charSeries").value, name = $("charName").value.trim();
  const klein = checked("imodel").includes("flux2_klein_4b");
  $("charKeepFaceNote").textContent = klein ? "Uses FLUX.2 klein, even if other image models are ticked." : `Only FLUX.2 klein can take a picture and it is not ticked on the Models tab, so ${checked("imodel")[0] || "the ticked model"} will work from the words alone.`;
  if (!series || !name) { box.innerHTML = ""; return; }
  try {
    const r = await api(`/api/characters?action=references&series=${encodeURIComponent(series)}&name=${encodeURIComponent(name)}`);
    const q = t => String(t).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
    const shown = r.pictures.filter(p => p.file);
    const lost = r.pictures.filter(p => !p.exists).length;
    box.innerHTML = shown.map(p => `<figure style="margin:0;width:112px;font-size:11px"><img src="/thumb/${p.file.split("/").map(encodeURIComponent).join("/")}?t=${TOKEN}" alt="Reference picture ${q(p.name)}" loading="lazy" width="112" height="112" style="object-fit:cover;border-radius:6px;${p.used ? "outline:3px solid var(--brand)" : ""}"><figcaption style="word-break:break-all">${q(p.name)}<br>${p.used ? "<b>This is the face</b>" : `<button type="button" class="btn btn-secondary" data-useref="${q(p.path)}" style="padding:2px 6px;font-size:11px">Use this face</button>`}</figcaption></figure>`).join("")
      + (shown.length ? "" : '<span class="warn">No pictures yet: generate one, or put one in the reference folder.</span>')
      + (lost ? `<span class="warn" style="width:100%">${lost} listed file(s) no longer exist and are skipped.</span>` : "");
  } catch (e) { box.innerHTML = `<span class="err">${q0(e.message)}</span>`; }
}
const q0 = t => String(t).replace(/</g, "&lt;");
function faceBadge(c, esc) {
  const f = c.face;
  if (!f) return "";
  const text = { ok: "✓ face matches", different: "⚠ may be someone else: look at this one", no_face: "no face found", skipped: "no reference picture to compare" }[f.status] || f.status;
  const scores = Object.entries(f.scores || {}).map(([k, v]) => `${k} ${v}`).join(", ");
  return `<span class="pz-cat" style="${f.status === "different" ? "color:var(--danger)" : ""}" title="${esc(scores)}">${esc(text)}</span>`;

}

// View definitions - shared between generation and preview
const CHAR_VIEWS = {
  face: { name: "Face (close-up)", add: "extreme close-up portrait, face filling frame, detailed eyes, skin texture, photorealistic" },
  eyes: { name: "Eyes (macro)", add: "macro close-up of eyes only, detailed iris, eyelashes, catch lights, photorealistic" },
  back_head: { name: "Back of Head", add: "back of head view, hair detail, neck, ear profile, photorealistic" },
  front_body: { name: "Front Whole Body", add: "full body front view, standing pose, head to toe, accurate proportions, photorealistic" },
  rear_body: { name: "Rear Whole Body", add: "full body rear view, standing pose, back of head to heels, accurate proportions, photorealistic" }
};

let charGenBusy = false;
async function generateCharacterImage() {
  const series = $("charSeries").value;
  const name = $("charList").value;
  if (!series || !name) {
    clearCharGenLog();
    logCharGen(!series ? "Select a Series first." : 'Select a character first: choose one under "Characters in this series" (or click New Character, fill in the form and Save Character), then click Generate.', true);
    return;
  }

  // Check which generation steps are enabled
  const genImages = $("charGenImages").checked;
  const genVoice = $("charGenVoice").checked;
  const genLora = $("charGenLora").checked;
  const genMovie = $("charGenMovie").checked;

  if (!genImages && !genVoice && !genLora && !genMovie) {
    logCharGen("Select at least one generation step", true);
    return;
  }

  // Check overwrite options
  const overwriteToken = $("charOverwriteToken").checked;
  const overwriteRefs = $("charOverwriteRefs").checked;

  const warnings = [];
  if (overwriteToken) warnings.push("• The visual token will be REPLACED with the generated prompts");
  if (overwriteRefs) warnings.push("• The new picture will be ADDED at the end of the Reference Images list (nothing is replaced)");
  if (genImages) {
    const viewText = $("charGenView") ? $("charGenView").value.trim() : "";
    const viewLabel = viewText || "custom view";
    warnings.push(`• Character Images: generates ${$("charSheet").checked ? "5 pictures (character sheet)" : "1 picture"} from the words on this page (view: ${viewLabel})${$("charKeepFace").checked ? ", starting from the face marked below if this model can use it" : ", without using any reference picture"}.`);
    if (!overwriteRefs) warnings.push("• The picture is saved in the reference folder and shown below, but not added to the Reference Images list");
  }
  if (genVoice) warnings.push("• Voice: generates voice samples (placeholder)");
  if (genLora) warnings.push("• LoRA: trains LoRA for character (placeholder)");
  if (genMovie) warnings.push("• Character Movie: generates short movie with voice (placeholder)");

  if (warnings.length && !confirm(`⚠️ WARNING: This will:\n\n${warnings.join("\n")}\n\nCharacter: ${name}\nSeries: ${series}\n\nAre you sure you want to continue?`)) {
    return;
  }

  // Delete previous notebooks before generating
  await deleteNotebooks();

  // Build the base prompt from the character data
  const visualToken = $("charVisualToken").value.trim();
  // Build physicalTraits from individual dropdown/input fields
  const physicalTraits = {};
  const physicalFields = ["age", "height", "build", "skin", "hair", "facial_hair", "eyes", "expression", "ethnicity", "distinguishing_features"];
  for (const field of physicalFields) {
    const el = $(`trait_${field}`);
    if (el && el.value) physicalTraits[field] = el.value;
  }
  const clothing = $("charClothing").value.trim();
  const consistency = $("charConsistency").value.trim();

  // Read global parameters directly from saved localStorage (the saved file)
  const globalPositives = localStorage.getItem("globalPositives") || "";
  const globalNegatives = localStorage.getItem("globalNegatives") || "";

  // Build base prompt (without angle-specific additions)
  const baseParts = [];
  if (visualToken) baseParts.push(visualToken);
  if (Object.keys(physicalTraits).length) {
    const desc = Object.entries(physicalTraits).filter(([_, v]) => v).map(([k, v]) => `${k}: ${v}`).join(", ");
    if (desc) baseParts.push(desc);
  }
  if (clothing) baseParts.push(`wearing ${clothing}`);
  if (consistency) baseParts.push(consistency);
  if (globalPositives) baseParts.push(globalPositives);

  const basePrompt = baseParts.join(", ");

  // Get view text from text input and add it to the prompt if provided
  const viewText = $("charGenView") ? $("charGenView").value.trim() : "";
  const fullPrompt = viewText ? basePrompt + ", " + viewText : basePrompt;

  const negative = globalNegatives;

  // One prompt, or one per view for a character sheet
  const sheet = $("charSheet").checked;
  const allPrompts = sheet ? CHAR_SHEET_VIEWS.map(v => `${fullPrompt}, ${v}`) : [fullPrompt];
  charGenReference = $("charKeepFace").checked ? { series, name } : { };   // the server decides whether this model and service can use a picture
  if (genImages && !fullPrompt.trim()) { logCharGen("Nothing to draw yet: fill in the character fields or the view box", true); return; }

  // Get generation parameters from the "Where to run" section
  const service = document.querySelector('input[name="svc"]:checked')?.value || "kaggle";
  const gpu = $("gpu").value;

  if (!gpu && (genImages || genVoice || genLora || genMovie)) {
    logCharGen("Select a GPU first in the 'Where to run' section", true);
    return;
  }

  // Use a prompt set name based on character (lowercase, underscores only)
  const setName = `char_${name.toLowerCase().replace(/[^a-z0-9]/g, "_")}`;

  clearCharGenLog();
  logCharGen(`Starting character generation for: ${name} (${series})`);
  if (genImages) {
    const viewLabel = viewText || "custom view";
    logCharGen(`→ Character Images: ${allPrompts.length} picture(s) (view: ${viewLabel}). ${$("charKeepFace").checked && checked("imodel").includes("flux2_klein_4b") ? "Starting from the face marked below." : "From the words alone."}`);
  }
  if (genVoice) logCharGen(`→ Voice Generation`);
  if (genLora) logCharGen(`→ LoRA Training`);
  if (genMovie) logCharGen(`→ Character Movie`);
  if (overwriteToken) logCharGen("⚠ Visual token will be overwritten");
  if (overwriteRefs) logCharGen("New pictures go at the end of the Reference Images list; the marked face stays until you press Use this face.");
  charGenBusy = true; $("bCharGenerate").disabled = true;

  try {
    // Step 1: Character Images (text-to-image)
    if (genImages) {
      await generateCharacterImages(setName, allPrompts, series, name, overwriteToken, overwriteRefs, service, gpu, negative);
    }

    // Step 2: Voice Generation (placeholder)
    if (genVoice) {
      logCharGen("\n🎤 Voice Generation - Not yet implemented");
      logCharGen("   This will generate voice samples using Kokoro TTS");
    }

    // Step 3: LoRA Training (placeholder)
    if (genLora) {
      logCharGen("\n🔧 LoRA Training - Not yet implemented");
      logCharGen("   This will train a LoRA on the reference images");
    }

    // Step 4: Character Movie (placeholder)
    if (genMovie) {
      logCharGen("\n🎬 Character Movie - Not yet implemented");
      logCharGen("   This will generate a short character movie with voice");
    }

    // Reload the character list and form if either was updated
    if (overwriteToken || overwriteRefs) {
      await loadCharList();
      await loadCharacter(series, name);
    }
  } catch (e) {
    logCharGen(`✗ Error: ${e.message}`, true);
  }
  charGenBusy = false; $("bCharGenerate").disabled = false;
  loadCharRefs();
}

async function generateCharacterImages(setName, allPrompts, series, name, overwriteToken, overwriteRefs, service, gpu, negative) {
  logCharGen("\n🖼️ Generating character image (text-to-image)...");

  // Use selected image model from "Where to run" section
  const selectedImageModels = checked("imodel");
  if (selectedImageModels.length === 0) {
    logCharGen("✗ No image model selected in 'Where to run' section", true);
    return;
  }
  // Keeping a face needs a model that takes a picture, so it goes first if it is ticked at all
  const imageModel = charGenReference.name && selectedImageModels.includes("flux2_klein_4b") ? "flux2_klein_4b" : selectedImageModels[0];
  logCharGen(`  Using image model: ${imageModel}`);
  const kind = "image";

  // Image generation parameters (use defaults from MODEL_DEFAULTS if available)
  const defaults = ST?.MODEL_DEFAULTS?.[imageModel] || {};
  const width = defaults.width || 1024;
  const height = defaults.height || 1024;
  const steps = defaults.steps || 20;
  const guidance = defaults.guidance !== undefined ? defaults.guidance : 4.0;

  // Create plan with single prompt
  let planResult;
  try {
    planResult = await api("/api/plan", {
      mode: "prompts",
      kind: kind,
      set: setName,
      model: imageModel,
      service: service,
      gpu: gpu,
      kaggle_user: service === "kaggle" ? ($("kuser").value || "") : "",
      prompts: allPrompts.join("\n"), // Single prompt
      opts: {
        negative: negative,
        width: width,
        height: height,
        steps: steps,
        guidance: guidance,
        reference: charGenReference,
        overwrite: true  // Overwrite CSV with single row for character generation
      }
    });
  } catch (e) {
    // The server answers 400 with the reason (unknown model, GPU not allowed for this model, missing Kaggle user...). Show it.
    logCharGen(`✗ The server rejected the plan for ${imageModel}: ${e.message}`, true);
    return;
  }

  if (!planResult.steps || planResult.steps.length === 0) {
    logCharGen("✗ Failed to create image generation plan", true);
    return;
  }

  logCharGen(`✓ Plan created with ${planResult.steps.length} step(s)`);
  logCharGen("Starting image generation job...");

  // Run the generation
  await api("/api/run", {
    mode: "prompts",
    kind: kind,
    set: setName,
    model: imageModel,
    service: service,
    gpu: gpu,
    kaggle_user: service === "kaggle" ? ($("kuser").value || "") : "",
    prompts: allPrompts.join("\n"),
    opts: {
      negative: negative,
      width: width,
      height: height,
      steps: steps,
      guidance: guidance,
      reference: charGenReference,
        overwrite: true  // Overwrite CSV with single row for character generation
    }
  });

  logCharGen("✓ Image generation job started");

  // Poll for job completion and download image (the run_kaggle_model.sh script already fetches results)
  await waitForImagesAndSaveRefs(setName, imageModel, allPrompts, series, name, overwriteToken, overwriteRefs);
}

// Poll `kaggle kernels status` every 15 s; on COMPLETE download to my_downloads and list what arrived.
// Returns "COMPLETE", "ERROR", "CANCEL_ACKNOWLEDGED" or "TIMEOUT".
async function waitForKaggleAndDownload(ref, maxMinutes = 90, log = logCharGen) {
  const POLL_MS = 15000;
  const FAILED = ["ERROR", "CANCEL_ACKNOWLEDGED", "CANCELACKNOWLEDGED"];
  let last = "";
  let unknownCount = 0;
  log(`\n⏳ Checking Kaggle status of ${ref} every 15 s...`);
  for (let waited = 0; waited < maxMinutes * 60000; waited += POLL_MS) {
    let status = "UNKNOWN";
    try {
      const r = await api(`/api/kernel_status?ref=${encodeURIComponent(ref)}`);
      status = r.status;
    } catch (e) {
      log(`  ⚠ Status check failed: ${e.message}`, true);
    }
    if (status !== last) {
      log(`  Kaggle status: ${status}`);
      last = status;
    }
    if (status === "COMPLETE") break;
    if (FAILED.includes(status)) {
      log(`✗ Kaggle run ${status.toLowerCase()}. Open the notebook on Kaggle to see the error.`, true);
      return status;
    }
    // UNKNOWN right after a push is normal; give up only after ~2 minutes of it
    unknownCount = status === "UNKNOWN" ? unknownCount + 1 : 0;
    if (unknownCount >= 8) {
      log("✗ Kaggle keeps reporting an unknown status; the notebook may not have been pushed.", true);
      return "ERROR";
    }
    await new Promise(resolve => setTimeout(resolve, POLL_MS));
  }
  if (last !== "COMPLETE") {
    log(`✗ Gave up after ${maxMinutes} minutes (last status: ${last || "none"}).`, true);
    return "TIMEOUT";
  }
  log("✓ Kaggle run finished. Downloading results...");
  try {
    const out = await api("/api/kernel_output", { ref });
    if (out.files.length) {
      log(`✓ ${out.files.length} file(s) found in ${out.dir}:`);
      out.files.forEach(f => log(`    ${f}`));
    } else {
      log(`  ⚠ No files found in destination ${out.dir}${out.message ? " (" + out.message + ")" : ""}`, true);
    }
  } catch (e) {
    log(`  ⚠ Download failed: ${e.message}`, true);
  }
  return "COMPLETE";
}

async function waitForImagesAndSaveRefs(setName, model, allPrompts, series, name, overwriteToken, overwriteRefs) {
  logCharGen("⏳ Waiting for image generation to complete...");
  logCharGen("   (This may take several minutes - check job log for progress)");

  let notebookSlug = null;
  let imageStart = 1;
  let imageEnd = 1;

  const jobLines = await followJob(logCharGen, 5000);
  const pushedRefs = kaggleRefsFromLines(jobLines);   // what the run script really pushed (owner/slug)
  logCharGen("✓ Job completed!");

  // Job completed - now search the FULL log for the generation line
  // Pattern: ===== [1/1] image sdxl_turbo: rows 1-3 $ PROJECT=char_abel ... scripts/run_kaggle_model.sh image_sdxl_turbo 1 3
  logCharGen("🔍 Searching job log for generation info...");
  try {
    const logResult = await api("/api/log?since=0");
    const fullLog = logResult.lines.join("\n");

    // More flexible regex - match the key parts even if spacing varies
    const match = fullLog.match(/=====\s*\[\d+\/\d+\]\s*image\s+(\S+):\s*rows\s+(\d+)\s*-\s*(\d+).*?\$\s*PROJECT\s*=\s*(\S+).*?run_kaggle_model\.sh\s+image_\S+\s+(\d+)\s+(\d+)/s);
    if (match) {
      const logModel = match[1];
      const start = parseInt(match[2], 10);
      const end = parseInt(match[3], 10);
      const project = match[4];
      const start2 = parseInt(match[5], 10);
      const end2 = parseInt(match[6], 10);

      // Verify the numbers match
      if (start === start2 && end === end2) {
        imageStart = start;
        imageEnd = end;
        // Build notebook slug: <project>-image-<model>-<start>-<end>   (no prefix; the run script's own "kernel pushed" line is preferred)
        // project and model need underscores -> dashes
        const slugProject = project.replace(/_/g, "-");
        const slugModel = logModel.replace(/_/g, "-");
        notebookSlug = `${slugProject}-image-${slugModel}-${start}-${end}`;
        // Add owner prefix (kaggle username from input or default)
        const kaggleUser = $("kuser").value;
        if (kaggleUser) notebookSlug = `${kaggleUser}/${notebookSlug}`;
        logCharGen(`  ✓ Found notebook info from log: ${notebookSlug} (images ${imageStart}-${imageEnd})`);
      }
    } else {
      // Try alternative pattern - just look for the notebook push message
      const pushMatch = fullLog.match(/pushing kernel\s+([^\s]+)/i);
      if (pushMatch) {
        notebookSlug = pushMatch[1];
        logCharGen(`  ✓ Found notebook slug from push log: ${notebookSlug}`);
        // Try to extract image range from slug
        const rangeMatch = notebookSlug.match(/-(\d+)-(\d+)$/);
        if (rangeMatch) {
          imageStart = parseInt(rangeMatch[1], 10);
          imageEnd = parseInt(rangeMatch[2], 10);
        }
      }

      // Try another alternative - look for the notebook slug format directly in the log
      // Format: <project>-image-<model>-<start>-<end> (with or without an owner prefix)
      if (!notebookSlug) {
        const slugMatch = fullLog.match(/(?:[a-zA-Z0-9_-]+\/)?([a-z0-9-]+?)-image-([a-z0-9-]+)-(\d+)-(\d+)/i);
        if (slugMatch) {
          const fullSlug = slugMatch[0]; // includes owner prefix if present
          const projectFromSlug = slugMatch[1].replace(/-/g, "_");
          const modelFromSlug = slugMatch[2].replace(/-/g, "_");
          const start = parseInt(slugMatch[3], 10);
          const end = parseInt(slugMatch[4], 10);
          notebookSlug = fullSlug;
          imageStart = start;
          imageEnd = end;
          logCharGen(`  ✓ Found notebook slug from direct log match: ${notebookSlug} (images ${imageStart}-${imageEnd})`);
        }
      }
    }
  } catch (e) {
    logCharGen(`  ⚠ Could not extract notebook info from log: ${e.message}`, true);
  }

  if (pushedRefs.length) {
    if (notebookSlug && notebookSlug !== pushedRefs[0]) logCharGen(`  ℹ Using the notebook the run script pushed: ${pushedRefs[0]}`);
    notebookSlug = pushedRefs[0];
  } else {
    logCharGen("  ⚠ The run script never reported pushing a Kaggle notebook (see the log above).", true);
  }

  // If we didn't find the log line, something is wrong
  if (!notebookSlug) {
    logCharGen(`  ⚠ Could not find generation log line in job output. This indicates the job may not have started properly.`, true);
    logCharGen(`  ℹ Expected log format: "===== [1/1] image <model>: rows <start>-<end> \$ PROJECT=<project> ..."`, true);
    logCharGen(`  ℹ Without this line, the notebook was not created on Kaggle. Check the job log for errors.`, true);
    // Still try to wait and fall back
    logCharGen("\n⏳ Waiting 3 minutes before fallback check...");
    await new Promise(resolve => setTimeout(resolve, 180000));
    return await fallbackDownloadImages(setName, model, series, name, overwriteToken, overwriteRefs, allPrompts, 1, 10, notebookSlug || "");
  }

  // Poll Kaggle until the notebook finishes, then download its output
  const kaggleState = await waitForKaggleAndDownload(notebookSlug);
  if (kaggleState !== "COMPLETE") return;

  // Retry mechanism: if notebook wasn't actually pushed to Kaggle, retry generation
  const maxRetries = 2;
  let retryCount = 0;

  async function attemptFetch() {
    // Use /api/fetch to pull results from Kaggle (uses kaggle kernels output internally)
    logCharGen(`\n📥 Fetching results from Kaggle for ${notebookSlug}... (attempt ${retryCount + 1}/${maxRetries + 1})`);
    logCharGen(`   (Expecting images ${imageStart} through ${imageEnd})`);
    try {
      await api("/api/fetch", {
        slug: notebookSlug.split("/").pop(),   // the server wants the notebook name without the owner
        project: setName,  // The prompt set project where images are generated
        wait: true  // Wait for the fetch to complete
      });
      logCharGen("✓ Fetch job started, waiting for completion...");
    } catch (e) {
      const errorMsg = e.message || "";
      logCharGen(`  ⚠ Fetch API error: ${errorMsg}`, true);

      // Check if the error indicates the notebook wasn't found on Kaggle
      if (errorMsg.toLowerCase().includes("not found") ||
          errorMsg.toLowerCase().includes("404") ||
          errorMsg.toLowerCase().includes("does not exist")) {

        if (retryCount < maxRetries) {
          retryCount++;
          logCharGen(`  🔄 Notebook not found on Kaggle. Retrying generation (attempt ${retryCount}/${maxRetries})...`, true);

          // Re-run the generation job
          try {
            await api("/api/run", {
              mode: "prompts",
              kind: "image",
              set: setName,
              model: model,
              service: service,
              gpu: gpu,
              kaggle_user: service === "kaggle" ? ($("kuser").value || "") : "",
              prompts: allPrompts.join("\n"),
              opts: {
                negative: negative,
                width: width,
                height: height,
                steps: steps,
                guidance: guidance,
                reference: charGenReference,
                overwrite: true
              }
            });
            logCharGen("✓ Retry generation job started");

            await followJob(logCharGen, 5000);
            logCharGen("✓ Retry job completed!");

            // Poll Kaggle until the retried notebook finishes
            if ((await waitForKaggleAndDownload(notebookSlug)) !== "COMPLETE") return;

            // Recursively attempt fetch again
            return await attemptFetch();
          } catch (retryError) {
            logCharGen(`  ✗ Retry generation failed: ${retryError.message}`, true);
            throw e; // Throw original fetch error
          }
        }
      }

      // If we get here, either max retries exceeded or error is not "not found"
      logCharGen(`  ⚠ Falling back to direct file check...`, true);
      return await fallbackDownloadImages(setName, model, series, name, overwriteToken, overwriteRefs, allPrompts, imageStart, imageEnd, notebookSlug);
    }

    // Poll for fetch job completion (check every 10 seconds for up to 4 minutes = 24 checks)
    logCharGen("  Checking for fetched results every 10s (max 4 minutes)...");
    let fetchComplete = false;
    for (let check = 0; check < 24 && !fetchComplete; check++) {
      await new Promise(resolve => setTimeout(resolve, 10000)); // 10 seconds

      try {
        const logResult = await api("/api/log?since=0");
        const recentLog = logResult.lines.slice(-20).join("\n");
        if (recentLog.includes("✅") && recentLog.includes("file(s) copied")) {
          fetchComplete = true;
          logCharGen("✓ Fetch completed - results downloaded");
          break;
        }
        if (recentLog.includes("ERROR") || recentLog.includes("error") || recentLog.includes("not found")) {
          logCharGen(`  ⚠ Fetch may have failed: ${recentLog.slice(-200)}`);
          // Continue checking, might recover
        }
      } catch (e) {
        logCharGen(`  ⚠ Could not check fetch status: ${e.message}`, true);
      }
    }

    if (!fetchComplete) {
      logCharGen(`  ⚠ Fetch did not complete within 4 minutes. Checking for downloaded files anyway...`);
    }

    // Now look for downloaded images in the project folder using the known image range
    return await fallbackDownloadImages(setName, model, series, name, overwriteToken, overwriteRefs, allPrompts, imageStart, imageEnd, notebookSlug);
  }

  // Start the fetch attempt with retry logic
  return await attemptFetch();
}

async function fallbackDownloadImages(setName, model, series, name, overwriteToken, overwriteRefs, allPrompts, imageStart, imageEnd, notebookSlug = "") {
  logCharGen("\n📥 Checking for generated images in project folder...");

  // Build the project directory path
  const projectDir = `images/${model}/`;
  let savedRefs = [];

  // Get existing reference images to determine starting index
  let maxIndex = 0;
  try {
    const charData = await api(`/api/characters?action=get&series=${encodeURIComponent(series)}&name=${encodeURIComponent(name)}`);
    if (charData.character && charData.character.reference_images) {
      for (const ref of charData.character.reference_images) {
        const match = ref.match(/_(\d+)\.png$/);
        if (match) {
          const idx = parseInt(match[1], 10);
          if (idx > maxIndex) maxIndex = idx;
        }
      }
    }
  } catch (e) {
    logCharGen(`  ⚠ Could not load existing references: ${e.message}`, true);
  }

  // Check for images in the project folder using the known image range (imageStart to imageEnd)
  // If range not known, default to 1-10
  const start = imageStart || 1;
  const end = imageEnd || 10;
  let imageFound = false;
  const wantAll = allPrompts.length > 1;      // a character sheet keeps every view
  for (let imgNum = start; imgNum <= end && (wantAll || !imageFound); imgNum++) {
    const imagePath = `${projectDir}image-${String(imgNum).padStart(4, '0')}.png`;
    logCharGen(`  Checking for image: ${imagePath}...`);

    try {
      const imageCheck = await fetch(`/file/${setName}/${imagePath}?t=${TOKEN}`, { method: "HEAD" });
      if (!imageCheck.ok) {
        logCharGen(`    ⚠ Image not found: ${imagePath}`, true);
        continue;
      }

      // Copy the image to the reference directory (under the book project/series)
      const newIndex = maxIndex + savedRefs.length + 1;
      const paddedIndex = String(newIndex).padStart(2, '0');
      const refName = `${charSlug(name)}_${paddedIndex}.png`;
      const refPath = `projects/characters/${series}/references/${charSlug(name)}/${refName}`;

      const copyResult = await api("/api/copy_file", {
        source: `${setName}/${imagePath}`,
        dest: refPath
      });

      if (copyResult.success) {
        savedRefs.push(refPath);
        logCharGen(`    ✓ Found and saved as: ${refPath} (was ${imagePath})`);
        imageFound = true;
      } else {
        logCharGen(`    ⚠ Failed to save image: ${copyResult.error}`, true);
      }
    } catch (e) {
      logCharGen(`    ⚠ Error processing image: ${e.message}`, true);
    }
  }

  // If still not found, try alternative model name (some models have different folder names)
  if (!imageFound) {
    logCharGen(`  Trying alternative paths...`);
    const altModels = [model, model.replace(/_/g, "-")];
    for (const altModel of altModels) {
      if (altModel === model) continue;
      const altProjectDir = `images/${altModel}/`;
      for (let imgNum = start; imgNum <= end && !imageFound; imgNum++) {
        const imagePath = `${altProjectDir}image-${String(imgNum).padStart(4, '0')}.png`;
        logCharGen(`  Checking alternative path: ${imagePath}...`);
        try {
          const imageCheck = await fetch(`/file/${setName}/${imagePath}?t=${TOKEN}`, { method: "HEAD" });
          if (!imageCheck.ok) continue;
          const newIndex = maxIndex + savedRefs.length + 1;
          const paddedIndex = String(newIndex).padStart(2, '0');
          const refName = `${charSlug(name)}_${paddedIndex}.png`;
          const refPath = `projects/characters/${series}/references/${charSlug(name)}/${refName}`;
          const copyResult = await api("/api/copy_file", {
            source: `${setName}/${imagePath}`,
            dest: refPath
          });
          if (copyResult.success) {
            savedRefs.push(refPath);
            logCharGen(`    ✓ Found and saved as: ${refPath} (was ${imagePath})`);
            imageFound = true;
          }
        } catch (e) {
          // ignore
        }
      }
    }
  }

  if (!imageFound) {
    logCharGen(`  ✗ Could not find any generated image in ${projectDir}image-${String(start).padStart(4, '0')}.png through image-${String(end).padStart(4, '0')}.png`, true);
    logCharGen(`  ℹ Check the job log for errors.`, true);
    logCharGen(`  ℹ If the generation log line was missing, the notebook may not have been created.`, true);
    logCharGen(`  ℹ Manual fetch: ./scripts/fetch_kaggle_run.sh ${notebookSlug || "<notebook-slug>"} --project ${setName} --wait`, true);
  }

  // Update character with new reference images
  if (overwriteRefs && savedRefs.length > 0) {
    try {
      const charData = await api(`/api/characters?action=get&series=${encodeURIComponent(series)}&name=${encodeURIComponent(name)}`);
      if (charData.character) {
        const updatedChar = {
          ...charData.character,
          reference_images: [...(charData.character.reference_images || []), ...savedRefs]
        };
        await api("/api/characters", { action: "save", character: updatedChar });
        logCharGen(`\n✓ Added ${savedRefs.length} reference image (auto-incremented)`);
        logCharGen(`  Saved refs: ${savedRefs.join(", ")}`);
      }
    } catch (e) {
      logCharGen(`⚠ Could not update character references: ${e.message}`, true);
    }
  }

  // Update visual token with the prompt if requested
  if (overwriteToken) {
    try {
      const charData = await api(`/api/characters?action=get&series=${encodeURIComponent(series)}&name=${encodeURIComponent(name)}`);
      if (charData.character) {
        const updatedChar = {
          ...charData.character,
          visual_token: allPrompts[0],
        };
        await api("/api/characters", { action: "save", character: updatedChar });
        logCharGen("✓ Visual token updated with prompt");
      }
    } catch (e) {
      logCharGen(`⚠ Could not update visual token: ${e.message}`, true);
    }
  }

  logCharGen(`\n✅ Character image generation complete!`);
  logCharGen(`   Saved ${savedRefs.length} reference image to: projects/characters/${series}/references/${charSlug(name)}/`);
  logCharGen(`   Image is in: ${projectDir}`);
}

// Log functions for the generation log box
function clearCharGenLog() {
  $("charGenLog").innerHTML = "";
}

function logCharGen(msg, isError = false) {
  const log = $("charGenLog");
  const line = document.createElement("div");
  line.style.marginBottom = "4px";
  line.style.color = isError ? "var(--danger)" : "var(--fg)";
  line.textContent = msg;
  log.appendChild(line);
  log.scrollTop = log.scrollHeight;
}

function showCharStatus(msg, isError = false) {
  $("charStatus").textContent = msg;
  $("charStatus").className = isError ? "err" : "warn";
}

function updateCharButtons() {
  const hasSeries = !!$("charSeries").value;
  const hasChar = !!$("charName").value;
  const hasSelection = !!$("charList").value;
  const hasVisualToken = !!$("charVisualToken").value;
  // Enable Generate Prompt when there's a character name or visual token (can generate from form)
  const canGeneratePrompt = hasChar || hasVisualToken;
  $("bCharNewSeries").disabled = false;
  $("bCharNew").disabled = !hasSeries;
  $("bCharSave").disabled = !hasChar || !hasSeries;
  $("bCharDelete").disabled = !hasSelection;
  $("bCharGenPrompt").disabled = false;   // always clickable: with nothing selected it explains what is missing in the Prompt Preview window
  $("bCharSync").disabled = !hasSeries || !$("proj").value;
  const picked = document.querySelectorAll("#charTableBody .charPick:checked").length;
  $("bCharSend").disabled = !hasSeries || !$("proj").value || !picked;
  $("bCharSend").textContent = picked ? `Send ${picked} ticked to the book` : "Send ticked to the book";
  $("bCharCopyAll").disabled = !$("charAllTokens").textContent || $("charAllTokens").textContent.startsWith("No characters");
  $("bCharRefreshAll").disabled = !hasSeries;
  $("bCharOpenRefDir").disabled = !$("charRefDir").textContent;
  $("bCharGenerate").disabled = charGenBusy;   // always clickable: with nothing selected it explains what is missing in the Generation Log
}
