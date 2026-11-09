// studio/shell.js - tab navigation, stepper, command palette, settings, shortcuts, drag and drop, initialisation
// Classic script: shares globals with the other studio/*.js files; load order is set in index.html.
// ===== TAB NAVIGATION =====
function initTabs() {
    const tabBtns = document.querySelectorAll('.tab-btn');
    const tabPanels = document.querySelectorAll('.tab-panel');
    
    tabBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            const tabName = btn.dataset.tab;
            
            // Update buttons
            tabBtns.forEach(b => {
                b.classList.remove('active');
                b.setAttribute('aria-selected', 'false');
            });
            btn.classList.add('active');
            btn.setAttribute('aria-selected', 'true');
            
            // Update panels
            tabPanels.forEach(panel => {
                panel.classList.remove('active');
                panel.setAttribute('aria-hidden', 'true');
            });
            const activePanel = document.getElementById('panel-' + tabName);
            if (activePanel) {
                activePanel.classList.add('active');
                activePanel.setAttribute('aria-hidden', 'false');
            }
            
            // The book-to-film rail is about the chosen book; Single Prompts has nothing to do with it
            const offBook = tabName === 'prompts';
            document.getElementById('pipelineStepper')?.classList.toggle('hidden', offBook);
            document.getElementById('stepperHint')?.classList.toggle('hidden', offBook);

            // Save to localStorage
            try { localStorage.setItem('activeTab', tabName); } catch (e) { /* private window: the tab is just not remembered */ }
        });
    });
    
    // Restore active tab
    const savedTab = localStorage.getItem('activeTab') || 'project';
    const savedBtn = document.querySelector('.tab-btn[data-tab="' + savedTab + '"]');
    if (savedBtn) savedBtn.click();
}

// ===== no autofill anywhere =====
// The Studio never asks for personal details, but browsers and password managers offer saved names, e-mail addresses and logins (synced
// from their servers) in any box they guess at, even with autocomplete="off". Every typing box, including ones added later, is marked so
// that none of them do. Boxes that already say what they hold are left alone.
const NO_FILL = { autocomplete: "off", "data-lpignore": "true", "data-1p-ignore": "true", "data-bwignore": "true", "data-form-type": "other" };
const TYPING = 'input:not([type]), input[type=text], input[type=search], input[type=number], input[type=url], input[type=email], input[type=password], textarea';
function noAutofill(root) {                          // root: the document or one element (it and everything inside it)
    const els = [...(root.matches && root.matches(TYPING) ? [root] : []), ...root.querySelectorAll(TYPING)];
    for (const el of els)
        for (const [k, v] of Object.entries(NO_FILL)) if (!el.getAttribute(k)) el.setAttribute(k, el.type === "password" && k === "autocomplete" ? "new-password" : v);
}
noAutofill(document);
new MutationObserver(list => { for (const m of list) for (const n of m.addedNodes) if (n.nodeType === 1) noAutofill(n); }).observe(document.body, { childList: true, subtree: true });

// ===== STEPPER (book-to-film rail above the tabs) =====
// Each step is done when its files exist (from /api/status), not when a checkbox is ticked. "cast" is optional and never the current step.
const STEP_NEXT = {
    ingest: 'Next: Read book (Import tab).',
    continuity: 'Next: Continuity book (Import tab).',
    write: 'Next: Write shots (Import tab).',
    build: 'Next: Build CSVs (Import tab).',
    video: 'Next: Video (Movies tab, Video and Audio card; or make keyframes first and check them in Storyboard).',
    audio: 'Next: Audio (Movies tab, Video and Audio card).',
    film: 'Next: Final film (Results tab).',
};
function stepDone(p) {
    const have = p.have || {};
    const sum = pre => Object.entries(have).filter(([k]) => k.startsWith(pre)).reduce((a, [, n]) => a + (Number(n) || 0), 0);
    const old = !!p.legacy;                                           // imported books arrive with the book steps already done
    return {
        ingest: old || (!p.not_started && !!p.chapters),
        continuity: old || !!p.continuity,
        cast: Array.isArray(p.characters) && p.characters.length > 0,
        board: sum('keyframes/') > 0,
        write: old || (p.chapters > 0 && p.scripts >= p.chapters),
        build: old || !!p.built,
        video: sum('videos/') > 0,
        audio: sum('audio/') > 0,
        film: (Number(have.films) || 0) > 0,
        counts: { video: sum('videos/'), audio: sum('audio/'), films: Number(have.films) || 0 },
    };
}
function updateStepper(project) {
    const els = document.querySelectorAll('#pipelineStepper .stepper__step');
    const hint = $('stepperHint');
    els.forEach(el => { el.classList.remove('active', 'complete'); el.removeAttribute('aria-current'); });
    if (!project) { if (hint) hint.textContent = 'Choose a book on the Import tab, or import a new one.'; return; }
    const done = stepDone(project);
    const current = [...els].find(el => !el.classList.contains('optional') && !done[el.dataset.step]);
    els.forEach(el => {
        const label = el.querySelector('.stepper__label').textContent;
        if (done[el.dataset.step]) el.classList.add('complete');
        if (el === current) { el.classList.add('active'); el.setAttribute('aria-current', 'step'); }
        el.setAttribute('aria-label', `${label}: ${done[el.dataset.step] ? 'done' : el === current ? 'next step' : 'not done yet'}`);
    });
    const c = done.counts;
    const have = `${project.slug}: ${c.video} clip(s), ${c.audio} sound file(s), ${c.films} film(s).`;
    if (hint) hint.textContent = have + ' ' + (current ? STEP_NEXT[current.dataset.step] : 'Every step is done. Watch your film on the Results tab.');
}
function goToStep(el) {
    if (el.dataset.step === 'film') { loadFilm(true); return; }       // opens the Results tab and the Make film panel with the downloaded files
    const tab = document.querySelector(`.tab-btn[data-tab="${el.dataset.go}"]`);
    if (tab) tab.click();
    const target = el.dataset.target && $(el.dataset.target);
    if (target) target.scrollIntoView({ behavior: 'smooth', block: 'start' });
}
document.querySelectorAll('#pipelineStepper .stepper__step').forEach(el => el.addEventListener('click', () => goToStep(el)));
// Every step card gets "previous step / next step" buttons taken from the rail, so the cards can be followed forwards and backwards
// in the same order and with the same names as the rail. Steps that share a card (Video, Audio) share one bar.
(function addStepNav() {
    const steps = [...document.querySelectorAll('#pipelineStepper .stepper__step')];
    const name = el => el.querySelector('.stepper__label').textContent;
    const cards = [];
    steps.forEach((el, i) => {
        const card = el.dataset.target && $(el.dataset.target);
        if (!card) return;
        const last = cards[cards.length - 1];
        if (last && last.card === card) last.to = i; else cards.push({ card, from: i, to: i });
    });
    const names = c => steps.slice(c.from, c.to + 1).map(name).join(' and ');     // a shared card is named by all its steps ("Video and Audio")
    const optional = c => steps.slice(c.from, c.to + 1).every(el => el.classList.contains('optional'));
    // Beside an optional step the bar also offers the step after it, so it can be skipped: going forward the optional step is on top and
    // the next required one below it; going back the required one is on top and the optional one below it. An optional card links plainly.
    const around = (k, dir) => {
        const out = [];
        for (let j = k + dir; j >= 0 && j < cards.length; j += dir) {
            out.push(cards[j]);
            if (optional(cards[k]) || !optional(cards[j])) break;
        }
        return dir > 0 ? out : out.reverse().sort((a, b) => optional(a) - optional(b));
    };
    cards.forEach((c, k) => {
        const body = c.card.querySelector(':scope > .card__body') || c.card;
        const nav = document.createElement('nav');
        nav.className = 'step-nav';
        nav.setAttribute('aria-label', 'Book to film steps');
        const btn = (to, text) => { const b = document.createElement('button'); b.type = 'button'; b.textContent = text; b.addEventListener('click', () => goToStep(steps[to.from])); return b; };
        const col = (list, back) => {
            const d = document.createElement('div'); d.className = 'step-nav__col' + (back ? '' : ' step-nav__col--next');
            list.forEach(t => d.appendChild(btn(t, back ? '\u2190 ' + names(t) : names(t) + ' \u2192')));
            return d;
        };
        nav.appendChild(col(around(k, -1), true));
        const mid = document.createElement('span'); mid.className = 'step-nav__here'; mid.textContent = `Step: ${names(c)}`; nav.appendChild(mid);
        nav.appendChild(col(around(k, 1), false));
        body.appendChild(nav);
    });
})();

// ===== COMMAND PALETTE =====
const COMMANDS = [
    { id: 'new-project', label: 'New Project', desc: 'Create a new book project', keys: '⌘N', action: () => $('file').click() },
    { id: 'run-pipeline', label: 'Run Pipeline', desc: 'Execute the full pipeline', keys: '⌘R', action: () => $('bRun').click() },
    { id: 'preview-commands', label: 'Preview Commands', desc: 'Show what will be executed', keys: '⌘P', action: () => $('bPreview').click() },
    { id: 'fetch-results', label: 'Fetch Kaggle Results', desc: 'Download completed runs', keys: '⌘F', action: () => $('bFetch').click() },
    { id: 'make-film', label: 'Make Film', desc: 'Assemble clips into final film', keys: '⌘M', action: () => $('bMakeFilm').click() },
    { id: 'switch-project', label: 'Switch Project', desc: 'Change active project', keys: '⌘1', action: () => $('proj').focus() },
    { id: 'characters', label: 'Manage Characters', desc: 'Open characters tab', keys: '⌘2', action: () => document.querySelector('[data-tab="characters"]').click() },
    { id: 'models', label: 'Configure Models', desc: 'Open models tab', keys: '⌘3', action: () => document.querySelector('[data-tab="models"]').click() },
    { id: 'creative-direction', label: 'Creative Direction', desc: 'Open creative direction (Movies tab)', keys: '⌘4', action: () => { document.querySelector('[data-tab="movies"]').click(); $('dirNotes')?.scrollIntoView({block:'center'}); } },
    { id: 'toggle-theme', label: 'Toggle Theme', desc: 'Switch light/dark mode', keys: '⌘D', action: () => $('themeToggle').click() },
    { id: 'open-results', label: 'Open Results', desc: 'Open results gallery', keys: '⌘5', action: () => document.querySelector('[data-tab="results"]').click() },
    { id: 'generate-characters', label: 'Generate Character Images', desc: 'Generate reference images for selected character', keys: '', action: () => { document.querySelector('[data-tab="characters"]').click(); $('bCharGenerate')?.click(); } },
    { id: 'save-global-params', label: 'Save Global Params', desc: 'Save global prompt parameters', keys: '', action: () => $('bGlobalSave')?.click() },
    { id: 'load-global-params', label: 'Load Global Params', desc: 'Load global prompt parameters', keys: '', action: () => $('bGlobalRead')?.click() },
];

function initCommandPalette() {
    const palette = $('cmd-palette');
    const input = palette.querySelector('input');
    const list = palette.querySelector('.cmd-list');
    
    function renderCommands(filter = '') {
        const filtered = COMMANDS.filter(cmd => 
            cmd.label.toLowerCase().includes(filter.toLowerCase()) ||
            cmd.desc.toLowerCase().includes(filter.toLowerCase()) ||
            cmd.id.includes(filter.toLowerCase())
        );
        list.innerHTML = filtered.map(cmd => `
            <div class="cmd-item" data-id="${cmd.id}">
                <span class="cmd-item__icon">${getCommandIcon(cmd.id)}</span>
                <div>
                    <div class="cmd-item__label">${cmd.label}</div>
                    <div class="cmd-item__desc">${cmd.desc}</div>
                </div>
                <kbd class="cmd-item__keys">${cmd.keys}</kbd>
            </div>
        `).join('');
        
        // Add click handlers
        list.querySelectorAll('.cmd-item').forEach(item => {
            item.addEventListener('click', () => {
                const cmd = COMMANDS.find(c => c.id === item.dataset.id);
                if (cmd) {
                    cmd.action();
                    closePalette();
                }
            });
        });
    }
    
    function openPalette() {
        palette.classList.add('open');
        input.value = '';
        renderCommands();
        input.focus();
    }
    
    function closePalette() {
        palette.classList.remove('open');
        input.value = '';
    }
    
    function getCommandIcon(id) {
        const icons = {
            'new-project': '📄',
            'run-pipeline': '▶️',
            'preview-commands': '👁️',
            'fetch-results': '⬇️',
            'make-film': '🎬',
            'switch-project': '📁',
            'characters': '👥',
            'models': '🤖',
            'creative-direction': '🎨',
            'toggle-theme': '🌓',
            'open-results': '📊',
            'generate-characters': '🖼️',
            'save-global-params': '💾',
            'load-global-params': '📥',
        };
        return icons[id] || '⚡';
    }
    
    // Keyboard shortcut: Cmd/Ctrl + K
    document.addEventListener('keydown', (e) => {
        if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
            e.preventDefault();
            openPalette();
        }
        if (e.key === 'Escape') {
            closePalette();
        }
    });
    
    input.addEventListener('input', (e) => {
        renderCommands(e.target.value);
    });
    
    input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            const firstItem = list.querySelector('.cmd-item');
            if (firstItem) {
                const cmd = COMMANDS.find(c => c.id === firstItem.dataset.id);
                if (cmd) {
                    cmd.action();
                    closePalette();
                }
            }
        }
        if (e.key === 'ArrowDown') {
            e.preventDefault();
            const items = list.querySelectorAll('.cmd-item');
            const active = list.querySelector('.cmd-item:hover, .cmd-item:focus');
            let next = items[0];
            if (active) {
                const idx = Array.from(items).indexOf(active);
                next = items[(idx + 1) % items.length];
            }
            next.focus();
        }
        if (e.key === 'ArrowUp') {
            e.preventDefault();
            const items = list.querySelectorAll('.cmd-item');
            const active = list.querySelector('.cmd-item:hover, .cmd-item:focus');
            let prev = items[items.length - 1];
            if (active) {
                const idx = Array.from(items).indexOf(active);
                prev = items[(idx - 1 + items.length) % items.length];
            }
            prev.focus();
        }
    });
    
    // Click outside to close
    palette.addEventListener('click', (e) => {
        if (e.target === palette) closePalette();
    });
}

// ===== TOAST HISTORY =====
const toastHistory = [];

function showToast(message, type = 'info', duration = 4000) {
    const container = $('toast-container');
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.innerHTML = `<span>${escapeHtml(message)}</span><button class="close" aria-label="Dismiss">&times;</button>`;
    toast.querySelector('.close').onclick = () => toast.remove();
    container.appendChild(toast);
    
    // Add to history
    toastHistory.unshift({
        message,
        type,
        time: new Date().toLocaleTimeString()
    });
    if (toastHistory.length > 50) toastHistory.pop();
    updateToastHistory();
    
    if (duration > 0) setTimeout(() => toast.remove(), duration);
}

function updateToastHistory() {
    const list = document.querySelector('.toast-history__list');
    if (list) {
        list.innerHTML = toastHistory.map(t => `
            <div class="toast-history__item">
                <div class="toast-history__time">${t.time}</div>
                <div class="toast toast-${t.type}" style="margin:0;box-shadow:none;border:none;padding:0">${escapeHtml(t.message)}</div>
            </div>
        `).join('');
    }
}

function initToastHistory() {
    // Create history button and panel
    const historyBtn = document.createElement('button');
    historyBtn.className = 'toast-history__btn';
    historyBtn.innerHTML = '📋';
    historyBtn.setAttribute('aria-label', 'Notification history');
    historyBtn.title = 'Notification history (click to open)';
    
    const panel = document.createElement('div');
    panel.className = 'toast-history__panel';
    panel.innerHTML = `
        <div class="toast-history__header">
            <span>Notifications</span>
            <button class="modal__close" aria-label="Close">&times;</button>
        </div>
        <div class="toast-history__list"></div>
    `;
    
    const wrapper = document.createElement('div');
    wrapper.className = 'toast-history';
    wrapper.appendChild(historyBtn);
    wrapper.appendChild(panel);
    document.body.appendChild(wrapper);
    
    historyBtn.onclick = () => panel.classList.toggle('open');
    panel.querySelector('.modal__close').onclick = () => panel.classList.remove('open');
    
    // Close on click outside
    document.addEventListener('click', (e) => {
        if (!wrapper.contains(e.target)) panel.classList.remove('open');
    });
    
    updateToastHistory();
}

// ===== SETTINGS MODAL =====
function initSettingsModal() {
    // Create modal if not exists
    if ($('settingsModal')) return;
    
    const modalHtml = `
        <div class="modal-overlay" id="settingsModal" role="dialog" aria-modal="true" aria-labelledby="settingsTitle">
            <div class="modal">
                <div class="modal__header">
                    <h2 class="modal__title" id="settingsTitle">Settings</h2>
                    <button class="modal__close" aria-label="Close">&times;</button>
                </div>
                <div class="modal__body">
                    <div style="display:grid;gap:24px">
                        <div>
                            <h3 style="margin:0 0 12px;font-size:var(--text-lg)">Appearance</h3>
                            <label class="opt" style="display:flex;align-items:center;gap:8px;margin-bottom:8px">
                                <input type="checkbox" id="settingCompact" style="width:auto">
                                <span>Compact mode (denser spacing)</span>
                            </label>
                            <label class="opt" style="display:flex;align-items:center;gap:8px">
                                <input type="checkbox" id="settingAnimations" checked style="width:auto">
                                <span>Enable animations</span>
                            </label>
                        </div>
                        <div>
                            <h3 style="margin:0 0 12px;font-size:var(--text-lg)">Defaults</h3>
                            <div class="row" style="gap:12px;align-items:flex-end">
                                <div style="min-width:200px">
                                    <label class="f">Default GPU</label>
                                    <select id="settingDefaultGpu"></select>
                                </div>
                                <div style="min-width:150px">
                                    <label class="f">Default Batch Size</label>
                                    <input type="number" id="settingDefaultBatch" min="0" value="40" autocomplete="off">
                                </div>
                            </div>
                        </div>
                        <div>
                            <h3 style="margin:0 0 12px;font-size:var(--text-lg)">Keyboard Shortcuts</h3>
                            <div class="data-table" style="font-size:var(--text-sm)">
                                <table class="data-table">
                                    <thead><tr><th>Shortcut</th><th>Action</th></tr></thead>
                                    <tbody>
                                        <tr><td><kbd>⌘K</kbd></td><td>Open Command Palette</td></tr>
                                        <tr><td><kbd>⌘R</kbd></td><td>Run Pipeline</td></tr>
                                        <tr><td><kbd>⌘P</kbd></td><td>Preview Commands</td></tr>
                                        <tr><td><kbd>⌘F</kbd></td><td>Fetch Results</td></tr>
                                        <tr><td><kbd>⌘M</kbd></td><td>Make Film</td></tr>
                                        <tr><td><kbd>⌘D</kbd></td><td>Toggle Theme</td></tr>
                                        <tr><td><kbd>1-7</kbd></td><td>Switch Tabs</td></tr>
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    </div>
                </div>
                <div class="modal__footer">
                    <button class="btn btn-secondary" id="settingsCancel">Cancel</button>
                    <button class="btn btn-primary" id="settingsSave">Save</button>
                </div>
            </div>
        </div>
    `;
    
    document.body.insertAdjacentHTML('beforeend', modalHtml);
    
    const modal = $('settingsModal');
    const closeBtn = modal.querySelector('.modal__close');
    const cancelBtn = $('settingsCancel');
    const saveBtn = $('settingsSave');
    
    function openModal() {
        modal.classList.add('open');
        // Populate GPU options
        if (ST?.gpus) {
            const svc = radio('svc');
            const gpus = ST.gpus[svc] || [];
            $('settingDefaultGpu').innerHTML = gpus.map(([v, t]) => `<option value="${v}">${t}</option>`).join('');
        }
    }
    
    function closeModal() {
        modal.classList.remove('open');
    }
    
    // Open with ⌘,
    document.addEventListener('keydown', (e) => {
        if ((e.metaKey || e.ctrlKey) && e.key === ',') {
            e.preventDefault();
            openModal();
        }
    });
    
    closeBtn.onclick = closeModal;
    cancelBtn.onclick = closeModal;
    saveBtn.onclick = () => {
        // Save settings to localStorage
        localStorage.setItem('settingCompact', $('settingCompact').checked);
        localStorage.setItem('settingAnimations', $('settingAnimations').checked);
        localStorage.setItem('settingDefaultGpu', $('settingDefaultGpu').value);
        localStorage.setItem('settingDefaultBatch', $('settingDefaultBatch').value);
        closeModal();
        showToast('Settings saved', 'success');
    };
    
    modal.onclick = (e) => { if (e.target === modal) closeModal(); };
    
    // Load saved settings
    if (localStorage.getItem('settingCompact') === 'true') {
        document.documentElement.classList.add('compact');
    }
    if (localStorage.getItem('settingAnimations') === 'false') {
        document.documentElement.classList.add('reduce-motion');
    }
}

// ===== KEYBOARD SHORTCUTS FOR TABS =====
function initTabShortcuts() {
    document.addEventListener('keydown', (e) => {
        // Number keys 1-6 for the 6 tabs (when not in input)
        if (e.key >= '1' && e.key <= '6' && !['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement.tagName)) {
            const tabs = document.querySelectorAll('.tab-btn');
            const idx = parseInt(e.key) - 1;
            if (tabs[idx]) tabs[idx].click();
        }
    });
}

// ===== DRAG & DROP FOR FILE UPLOAD =====
function initDropZone() {
    const fileInput = $('file');
    if (!fileInput) return;
    
    // Find the parent container
    const container = fileInput.closest('div');
    if (!container) return;
    
    // Create drop zone
    const dropZone = document.createElement('div');
    dropZone.className = 'drop-zone';
    dropZone.innerHTML = `
        <div class="drop-zone__icon">📄</div>
        <div style="font-weight:500;margin-bottom:4px">Drop a PDF or text file here, or click to browse</div>
        <div style="font-size:var(--text-sm);color:var(--fg-muted)">Supports .pdf, .txt and .md files</div>
    `;
    
    // Insert before the file input
    container.insertBefore(dropZone, fileInput);
    fileInput.style.display = 'none';
    
    dropZone.onclick = () => fileInput.click();
    
    dropZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropZone.classList.add('drag-over');
    });
    
    dropZone.addEventListener('dragleave', () => {
        dropZone.classList.remove('drag-over');
    });
    
    dropZone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropZone.classList.remove('drag-over');
        if (e.dataTransfer.files.length) {
            fileInput.files = e.dataTransfer.files;
            fileInput.dispatchEvent(new Event('change'));
        }
    });
    
    fileInput.addEventListener('change', () => {
        if (fileInput.files.length) {
            dropZone.innerHTML = `
                <div class="drop-zone__icon">✅</div>
                <div style="font-weight:500;margin-bottom:4px">${escapeHtml(fileInput.files[0].name)}</div>
                <div style="font-size:var(--text-sm);color:var(--success)">Ready: press Import</div>
            `;
            dropZone.style.borderColor = 'var(--success)';
        }
    });
}

// ===== COPY TO CLIPBOARD HELPER =====
function copyToClipboard(text, label = 'Copied') {
    navigator.clipboard.writeText(text).then(() => {
        showToast(label, 'success');
    }).catch(() => {
        showToast('Failed to copy', 'error');
    });
}

// Add copy buttons to code/pre elements
function initCopyButtons() {
    document.querySelectorAll('pre, .cell code').forEach(el => {
        if (el.querySelector('.copy-btn')) return;
        const btn = document.createElement('button');
        btn.className = 'btn btn-icon copy-btn';
        btn.innerHTML = '📋';
        btn.title = 'Copy to clipboard';
        btn.style.position = 'absolute';
        btn.style.top = '8px';
        btn.style.right = '8px';
        btn.onclick = () => copyToClipboard(el.textContent);
        el.style.position = 'relative';
        el.appendChild(btn);
    });
}

// ===== INITIALIZE ALL =====
document.addEventListener('DOMContentLoaded', () => {
    initTabs();
    initCommandPalette();
    initToastHistory();
    initSettingsModal();
    initTabShortcuts();
    initDropZone();
    initCopyButtons();
    
    // Hook into loadStatus to update stepper
    const originalLoadStatus = loadStatus;
    loadStatus = async function(applyDef) {
        await originalLoadStatus(applyDef);
        updateStepper(cur());
        
        // Update status badge
        const badge = $('statusBadge');
        if (badge) {
            badge.className = 'status-badge ok';
            badge.querySelector('span:last-child').textContent = 'Connected';
        }
    };
    
    // The rail shows the chosen book, so redraw it when another book is picked
    $('proj').addEventListener('change', () => updateStepper(cur()));
});

// Override showToast to use new implementation
const originalShowToast = showToast;
showToast = function(message, type, duration) {
    originalShowToast(message, type, duration);
};

// Character table: one delegated listener instead of inline onclick handlers (the page's Content-Security-Policy forbids those).
document.addEventListener("click", ev => {
  const el = ev.target.closest("[data-act]");
  if (!el) return;
  const act = el.dataset.act;
  if (act === "pick-char") { ev.stopPropagation(); updateCharButtons(); }
  else if (act === "edit-char") { ev.stopPropagation(); loadCharacter(el.dataset.series, el.dataset.name); }
  else if (act === "delete-char") { ev.stopPropagation(); deleteCharacterConfirm(el.dataset.series, el.dataset.name); }
  else if (act === "select-char") selectCharInTable(el.dataset.name);
});
