// studio/ui.js - theme toggle, toasts, character archetypes
// Classic script: shares globals with the other studio/*.js files; load order is set in index.html.
// ---- Theme Toggle ----
function initTheme() {
  const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
  const saved = localStorage.getItem("theme");
  const isDark = saved ? saved === "dark" : prefersDark;
  document.documentElement.classList.toggle("dark", isDark);
  updateThemeIcon(isDark);
}
function updateThemeIcon(isDark) {
  const btn = $("themeToggle");
  if (btn) btn.textContent = isDark ? "☀\uFE0E" : "🌙";   // \uFE0E = text form of the sun, so CSS colour applies
}
$("themeToggle").onclick = () => {
  const isDark = !document.documentElement.classList.contains("dark");
  document.documentElement.classList.toggle("dark", isDark);
  localStorage.setItem("theme", isDark ? "dark" : "light");
  updateThemeIcon(isDark);
};

// ---- Toast Notifications ----
function showToast(message, type = "info", duration = 4000) {
  const container = $("toast-container");
  const toast = document.createElement("div");
  toast.className = `toast ${type}`;
  toast.innerHTML = `<span>${escapeHtml(message)}</span><button class="close" aria-label="Dismiss">&times;</button>`;
  toast.querySelector(".close").onclick = () => toast.remove();
  container.appendChild(toast);
  if (duration > 0) setTimeout(() => toast.remove(), duration);
}

// ---- Character Archetype System ----
let charArchetypesData = null;

async function loadCharArchetypes() {
  try {
    const j = await api("/api/characters?action=archetypes");
    charArchetypesData = j.archetypes || {};
    const select = $("charArchetype");
    select.innerHTML = '<option value="">(select archetype)</option>' +
      Object.keys(charArchetypesData).map(a => `<option value="${a}">${a}</option>`).join("");
    select.onchange = () => onArchetypeChange();
  } catch (e) {
    showCharStatus("Failed to load archetypes: " + e.message, true);
  }
}

async function onArchetypeChange() {
  const archetype = $("charArchetype").value;
  if (!archetype || !charArchetypesData[archetype]) {
    clearArchetypeFields();
    return;
  }
  try {
    // Load fields schema for this archetype
    const fieldsRes = await api(`/api/characters?action=archetype_fields&archetype=${encodeURIComponent(archetype)}`);
    const fields = fieldsRes.fields || {};

    // Load valid values for dropdown fields
    const validRes = await api(`/api/characters?action=valid_values`);
    const validValues = validRes.valid_values || {};

    renderArchetypeFields(fields, validValues, archetype);
    if (Date.now() - charSavedAt > 4000) showCharStatus(`Loaded archetype: ${archetype}`);   // not right after a save: keep "Character saved"
  } catch (e) {
    showCharStatus("Failed to load archetype fields: " + e.message, true);
  }
}

function clearArchetypeFields() {
  $("physicalTraitsFields").innerHTML = "";
  $("loraFields").innerHTML = "";
}

function renderArchetypeFields(fields, validValues, archetype) {
  // Render physical traits fields
  const physicalContainer = $("physicalTraitsFields");
  const physicalFields = ["age", "height", "build", "skin", "hair", "facial_hair", "eyes", "expression", "ethnicity", "distinguishing_features"];
  physicalContainer.innerHTML = physicalFields.map(field => {
    const valid = validValues[field] || [];
    const isDropdown = valid.length > 0;
    const fieldDef = fields[field] || { type: "string", required: false };
    const required = fieldDef.required ? "required" : "";
    const placeholder = fieldDef.description || field;

    if (isDropdown) {
      return `<div class="char-trait-field">
        <label class="f">${field.charAt(0).toUpperCase() + field.slice(1).replace("_", " ")} ${required ? '<span style="color:var(--danger)">*</span>' : ''}</label>
        <select id="trait_${field}" ${required}>
          <option value="">(select)</option>
          ${valid.map(v => `<option value="${escapeHtml(v)}">${escapeHtml(v)}</option>`).join("")}
        </select>
      </div>`;
    } else {
      return `<div class="char-trait-field">
        <label class="f">${field.charAt(0).toUpperCase() + field.slice(1).replace("_", " ")} ${required ? '<span style="color:var(--danger)">*</span>' : ''}</label>
        <input type="text" id="trait_${field}" placeholder="${escapeHtml(placeholder)}" ${required} autocomplete="off">
      </div>`;
    }
  }).join("");

  // Render LoRA fields
  const loraContainer = $("loraFields");
  const loraFields = ["repo", "trigger_word", "base_model", "trained"];
  loraContainer.innerHTML = loraFields.map(field => {
    const valid = validValues[field] || [];
    const isDropdown = valid.length > 0;
    const fieldDef = fields[field] || { type: "string", required: false };
    const required = fieldDef.required ? "required" : "";
    const placeholder = fieldDef.description || field;

    if (isDropdown) {
      return `<div class="char-trait-field">
        <label class="f">${field.charAt(0).toUpperCase() + field.slice(1).replace("_", " ")} ${required ? '<span style="color:var(--danger)">*</span>' : ''}</label>
        <select id="lora_${field}" ${required}>
          <option value="">(select)</option>
          ${valid.map(v => `<option value="${escapeHtml(v)}">${escapeHtml(v)}</option>`).join("")}
        </select>
      </div>`;
    } else {
      return `<div class="char-trait-field">
        <label class="f">${field.charAt(0).toUpperCase() + field.slice(1).replace("_", " ")} ${required ? '<span style="color:var(--danger)">*</span>' : ''}</label>
        <input type="text" id="lora_${field}" placeholder="${escapeHtml(placeholder)}" ${required} autocomplete="off">
      </div>`;
    }
  }).join("");

  // Set default LoRA trigger_word if empty
  setTimeout(() => {
    const triggerInput = $("lora_trigger_word");
    if (triggerInput && !triggerInput.value && $("charName").value) {
      triggerInput.value = $("charName").value.toLowerCase().replace(/[^a-z0-9]/g, "_") + "_token";
    }
  }, 0);
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

function setCharFormData(data) {
  // Set basic fields
  if (data.name) $("charName").value = data.name;
  if (data.visual_token) $("charVisualToken").value = data.visual_token;
  if (data.trigger_words) $("charTriggerWords").value = (data.trigger_words || []).join(", ");
  if (data.clothing) $("charClothing").value = data.clothing;
  if (data.voice) $("charVoice").value = data.voice;
  if (data.reference_images) $("charRefImages").value = (data.reference_images || []).join("\n");
  if (data.consistency_notes) $("charConsistency").value = data.consistency_notes;
  if (data.stages) $("charStages").value = stagesToText(data.stages);

  // Set archetype if present
  if (data.archetype && charArchetypesData && charArchetypesData[data.archetype]) {
    $("charArchetype").value = data.archetype;
    onArchetypeChange(); // This will populate fields

    // Wait for fields to render then set values
    setTimeout(() => {
      if (data.physical_traits) {
        for (const [field, value] of Object.entries(data.physical_traits)) {
          const el = $(`trait_${field}`);
          if (el) el.value = value;
        }
      }
      if (data.lora) {
        for (const [field, value] of Object.entries(data.lora)) {
          const el = $(`lora_${field}`);
          if (el) {
            if (el.type === "checkbox") el.checked = value;
            else el.value = value;
          }
        }
      }
      updateCharButtons();
    }, 100);
  } else {
    updateCharButtons();
  }
}

async function loadCharacter(series, name) {
  if (!series || !name) return;
  charCurrentSeries = series;
  charCurrentCharacter = name;
  try {
    const j = await api(`/api/characters?action=get&series=${encodeURIComponent(series)}&name=${encodeURIComponent(name)}`);
    const c = j.character;
    if (c) {
      setCharFormData(c);
      updateRefDir();
    }
    updateCharButtons();
  } catch (e) {
    showCharStatus(e.message, true);
  }
}
