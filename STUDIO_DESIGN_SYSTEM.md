# Studio Design System — Biblical/Cinematic Pipeline Dashboard

## Overview
A production dashboard for the Bible Film Pipeline. 6 tabs manage the end-to-end workflow: Import → Models → Single Prompts → Characters → Movies → Results (Movies also holds the former Generate tab).

**Visual Identity**: Aged parchment, deep ochre, slate — evoking ancient manuscripts and cinematic production.

---

## 1. Color System (Semantic Palette)

### Light Theme (Default)
| Token | Value | Role |
|-------|-------|------|
| `--color-parchment` | `#fdfbf7` | Page background |
| `--color-parchment-dark` | `#f5f0e1` | Elevated surfaces, hover |
| `--color-ink` | `#1e1e1e` | Primary text |
| `--color-ink-muted` | `#6b6b6b` | Secondary text |
| `--brand` | `#8b6b2f` | **Primary** — Actions, active states, focus |
| `--brand-light` | `#d4a843` | **Secondary** — Hover, accents |
| `--brand-dark` | `#6b4f1f` | Active/pressed states |
| `--brand-bg` | `#fdf8f0` | Subtle backgrounds (badges, chips) |
| `--color-border` | `#e8e0d0` | Default borders |
| `--color-border-strong` | `#d4c8b0` | Focused/emphasized borders |

### Semantic Colors
| Token | Light | Dark | Use |
|-------|-------|------|-----|
| `--color-success` | `#059669` | `#10b981` | Complete steps, saved states |
| `--color-warning` | `#d97706` | `#f59e0b` | Pending, warnings |
| `--color-danger` | `#dc2626` | `#ef4444` | Errors, destructive |
| `--color-info` | `#0284c7` | `#38bdf8` | Info, neutral actions |

### Dark Theme (`.dark` on `<html>`)
| Token | Value |
|-------|-------|
| `--color-parchment` | `#0f1419` |
| `--color-parchment-dark` | `#141a22` |
| `--color-ink` | `#f5f0e1` |
| `--color-ink-muted` | `#a8a090` |
| `--brand` | `#d4a843` |
| `--brand-light` | `#e8c460` |
| `--brand-dark` | `#b8923a` |
| `--brand-bg` | `#1f1a10` |
| `--color-border` | `#1e293b` |
| `--color-border-strong` | `#2d3a4f` |

---

## 2. Elevation System (Layered Shadows)

| Token | Value | Use |
|-------|-------|-----|
| `--elev-1` | `0 1px 3px rgba(15,23,42,0.06), 0 1px 2px rgba(15,23,42,0.04)` | Cards, panels |
| `--elev-2` | `0 4px 12px rgba(15,23,42,0.08), 0 2px 4px rgba(15,23,42,0.04)` | Modals, dropdowns |
| `--elev-3` | `0 12px 28px rgba(15,23,42,0.1), 0 4px 8px rgba(15,23,42,0.05)` | Toasts, popovers |
| `--elev-4` | `0 20px 40px rgba(15,23,42,0.12), 0 8px 16px rgba(15,23,42,0.06)` | Full-screen overlays |

*Dark mode uses rgba(0,0,0,*) with higher opacity.*

---

## 3. Typography

| Token | Font | Scale | Use |
|-------|------|-------|-----|
| `--font-display` | `"Cinzel", "Cormorant Garamond", Georgia, serif` | `--text-2xl` to `--text-4xl` | Page titles, section headers |
| `--font-ui` | `"Inter", -apple-system, BlinkMacSystemFont, sans-serif` | `--text-xs` to `--text-xl` | UI text, labels, buttons, tables |
| `--font-mono` | `"JetBrains Mono", "Fira Code", monospace` | `--text-xs` to `--text-base` | Code, tokens, technical values |

### Type Scale
| Token | Value | Line Height |
|-------|-------|-------------|
| `--text-xs` | `0.7rem` (11.2px) | 1.4 |
| `--text-sm` | `0.8125rem` (13px) | 1.5 |
| `--text-base` | `0.9375rem` (15px) | 1.5 |
| `--text-lg` | `1.0625rem` (17px) | 1.5 |
| `--text-xl` | `1.25rem` (20px) | 1.4 |
| `--text-2xl` | `1.5rem` (24px) | 1.3 |
| `--text-3xl` | `1.875rem` (30px) | 1.25 |
| `--text-4xl` | `2.25rem` (36px) | 1.2 |

---

## 4. Spacing Scale

| Token | Value | Use |
|-------|-------|-----|
| `--space-0` | `0` | Reset |
| `--space-1` | `0.25rem` (4px) | Tight gaps |
| `--space-2` | `0.5rem` (8px) | Standard gaps |
| `--space-3` | `0.75rem` (12px) | Component padding |
| `--space-4` | `1rem` (16px) | Section gaps |
| `--space-5` | `1.25rem` (20px) | Card padding |
| `--space-6` | `1.5rem` (24px) | Section margins |
| `--space-8` | `2rem` (32px) | Large gaps |
| `--space-10` | `2.5rem` (40px) | Page margins |
| `--space-12` | `3rem` (48px) | Hero sections |
| `--space-16` | `4rem` (64px) | Major sections |

---

## 5. Border Radius

| Token | Value | Use |
|-------|-------|-----|
| `--radius-sm` | `6px` | Buttons, badges, inputs |
| `--radius` | `8px` | Standard cards |
| `--radius-lg` | `12px` | Modals, panels |
| `--radius-xl` | `16px` | Large containers |
| `--radius-full` | `9999px` | Pills, avatars |

---

## 6. Transitions

| Token | Value | Use |
|-------|-------|-----|
| `--transition-fast` | `120ms ease` | Hover, focus |
| `--transition` | `180ms ease` | Standard |
| `--transition-slow` | `280ms ease` | Modals, panels |

---

## 7. Component Library

### 7.1 Cards
```html
<article class="card">
  <header class="card__header">
    <h2 class="card__title">Title</h2>
    <p class="card__subtitle">Optional subtitle</p>
    <div class="card__actions">
      <button class="btn btn--icon" aria-label="Action">⋮</button>
    </div>
  </header>
  <div class="card__body">Content</div>
  <footer class="card__footer">Status / Meta</footer>
</article>
```

**Variants**: `.card--elevated` (elev-2), `.card--outlined` (border only), `.card--interactive` (hover: elev-2, focus: accent ring)

### 7.2 Data Tables
```html
<table class="data-table" role="grid">
  <thead>
    <tr><th>Column</th><th>Column</th><th></th></tr>
  </thead>
  <tbody>
    <tr><td>Data</td><td>Data</td><td><button class="btn-icon">✎</button></td></tr>
  </tbody>
</table>
```
- Sticky header on scroll
- Row hover: `--bg-hover`
- Right-aligned actions column

### 7.3 Stepper (Pipeline Progress)
```html
<nav class="stepper" aria-label="Pipeline progress">
  <ol>
    <li class="stepper__step complete" data-step="ingest">
      <span class="stepper__circle">1</span>
      <span class="stepper__label">Ingest PDF</span>
    </li>
    <!-- ... -->
  </ol>
</nav>
```
**States**: `.complete` (gold circle, check), `.active` (gold circle, pulse ring), default (slate border, muted text)
**Responsive**: Horizontal scroll on mobile, `min-width: 120px` per step

### 7.4 Buttons
| Variant | Class | Style |
|---------|-------|-------|
| Primary | `.btn` / `.btn--primary` | `--brand` bg, white text |
| Secondary | `.btn--secondary` | Outlined, `--brand` border/text |
| Ghost | `.btn--ghost` | Transparent, `--fg` text |
| Danger | `.btn--danger` | `--color-danger` bg |
| Icon | `.btn--icon` | Square, icon only |

### 7.5 Form Controls
- **Inputs**: `--bg` bg, `--border` border, `--radius-sm`, `--text-base`
- **Focus**: `--color-focus` ring (3px), `--border-strong` border
- **Labels**: `--text-sm`, `--fg-muted`, `--font-ui`
- **Selects**: Same as inputs, native dropdown
- **Textareas**: Min-height 80px, resize vertical

### 7.6 Badges
```html
<span class="badge badge--success">Complete</span>
<span class="badge badge--warning">Pending</span>
<span class="badge badge--danger">Error</span>
<span class="badge badge--info">Info</span>
<span class="badge badge--neutral">Neutral</span>
```

### 7.7 Empty States
```html
<div class="empty-state">
  <svg class="empty-state__icon" aria-hidden="true">...</svg>
  <h3 class="empty-state__title">No items yet</h3>
  <p class="empty-state__desc">Description with action hint</p>
  <button class="btn">Primary Action</button>
</div>
```

### 7.8 Toasts
```html
<div class="toast toast--success">
  <span>Message</span>
  <button class="toast__close" aria-label="Dismiss">×</button>
</div>
```
- Slide in from top-right
- Auto-dismiss after 4s (configurable)
- History drawer accessible via header

---

## 8. Per-Tab Visual Treatment

| Tab | Accent Color | Icon | Header Treatment |
|-----|--------------|------|------------------|
| **Project** | `--brand` (ochre) | 📁 Folder | Project hero: parchment texture, book icon |
| **Models** | `#0284c7` (info blue) | 🖥️ Monitor | GPU status cards, model cards with vendor badges |
| **Pipeline** | `--brand` (ochre) | ⚙️ Gear | Stepper prominent, checklist cards |
| **Characters** | `#059669` (success green) | 👥 Users | Character grid with portrait thumbnails |
| **Creative** | `#d97706` (warning amber) | 🎨 Palette | Moodboard-style layout, image galleries |
| **Generate** | `#7c3aed` (violet) | ▶️ Play | Progress rings, queue visualization |
| **Results** | `#0284c7` (info blue) | 📦 Archive | Gallery grid, filterable, download actions |

**Shared**: All tabs use the same card, table, button, form components. Only accent color and header iconography differ.

---

## 9. Layout & Grid

### Page Structure
```
<header class="studio-header">          <!-- Fixed or static -->
  <div class="header-brand">Logo + Title</div>
  <div class="header-actions">
    <status-badge></status-badge>
    <theme-toggle></theme-toggle>
  </div>
</header>

<main>
  <nav class="tab-nav" role="tablist">  <!-- Horizontal tabs -->
    <button class="tab-btn" data-tab="...">...</button>
    ...
  </nav>

  <nav class="stepper" aria-label="Pipeline">  <!-- Visible on all tabs -->
    ...
  </nav>

  <section class="tab-panel active" id="panel-project" role="tabpanel">
    <div class="section-grid">          <!-- Responsive card grid -->
      <article class="card">...</article>
      ...
    </div>
  </section>
  ...
</main>
```

### Responsive Breakpoints
| Breakpoint | Behavior |
|------------|----------|
| `≥1024px` | Full grid, horizontal tabs, full stepper |
| `768–1023px` | 2-col grid, tabs scroll horizontally, stepper scrolls |
| `<768px` | 1-col grid, compact tabs (icons + short labels), stepper scrolls |

---

## 10. Motion & Interaction

| Interaction | Animation |
|-------------|-----------|
| Tab switch | Fade 180ms + slide Y 4px |
| Card hover | Elev-1 → Elev-2 (180ms) |
| Button press | Scale 0.98 (60ms) |
| Stepper progress | Circle fill 300ms ease-out |
| Toast enter | Slide down + fade 200ms |
| Toast exit | Slide up + fade 150ms |
| Modal enter | Fade backdrop + scale 0.95→1 (200ms) |
| Theme toggle | Cross-fade colors 200ms |

**Reduced Motion**: All animations → 0.01ms when `prefers-reduced-motion: reduce`

---

## 11. Accessibility

- **Focus Visible**: 2px `--color-focus` ring, 2px offset
- **Color Contrast**: ≥4.5:1 for text, ≥3:1 for UI elements
- **Keyboard**: All interactive elements reachable, `Tab` order logical
- **ARIA**: Proper roles on tabs (`tablist`, `tab`, `tabpanel`), stepper (`navigation`), toasts (`status`)
- **Screen Readers**: Live regions for status updates, descriptive labels

---

## 12. Implementation Checklist

### Already Done ✅
- [x] Color tokens (light/dark)
- [x] Typography (Cinzel + Inter + JetBrains Mono)
- [x] Elevation system
- [x] Tab navigation (horizontal, 6 tabs)
- [x] Stepper (visible all tabs, 7 steps)
- [x] Theme toggle (persists to localStorage)
- [x] Basic card, table, button, badge components

### To Implement
- [ ] Card variants (--elevated, --outlined, --interactive)
- [ ] Data table with sticky header, row actions
- [ ] Form control standardization (inputs, selects, textareas)
- [ ] Empty states for all list views
- [ ] Toast history drawer
- [ ] Command palette wiring (⌘K)
- [ ] Skeleton loaders for async content
- [ ] Drag-and-drop PDF upload zone
- [ ] Copy-to-clipboard on tokens/prompts
- [ ] Inline validation (char counts, required fields)
- [ ] Settings modal (GPU, batch, theme, API keys)
- [ ] Responsive refinements (mobile cards, stepper scroll)

---

## 13. File Structure (Future Modularization)

```
/studio/
  index.html              # Shell + tabs + layout
  css/
    tokens.css            # Design tokens (this spec)
    components.css        # Cards, tables, forms, stepper
    layout.css            # Grid, responsive
    themes.css            # Light/dark overrides
  js/
    app.js                # Bootstrap, routing
    api.js                # API client
    tabs/
      project.js
      models.js
      characters.js
      pipeline.js
      creative.js
      generate.js
      results.js
    utils/
      toast.js
      modal.js
      clipboard.js
      theme.js
```

---

*This document is the single source of truth for the Studio dashboard visual system. Update tokens here, then propagate to `studio.html` (or modular CSS/JS when split).*
