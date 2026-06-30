# PQA Desktop — Dark UI Redesign: Implementation Plan

**Branch:** `redesign/dark-ui`
**Status:** Phase 2 complete (dark app shell + top bar); Phase 3 (sidebar) next.
**Owner:** Shenal · drives across multiple sessions; some phases handed to Codex.

---

## 1. Goal

Ship a **fully-dark restyle** of the PQA desktop app that matches the Claude
design "PQA Redesign", wired to the **real backend** (real CSV load → analysis →
charts → report), but kept **non-default** behind a runtime theme toggle so it
can be evaluated side-by-side with the current app before we commit to making it
the default.

**Definition of done (prototype):** With the redesign theme active, the
Compliance tab looks like the reference, every control is wired to the real
`config`/backend exactly as today, real analysis runs, and the current
("classic") look is still one click away. No regression to the classic app.

**Reference (visual source of truth):**
- `docs/redesign/reference/PQA-Redesign.standalone.html` — runnable, mock-data
  copy of the exact design. Open it to see the target. (Serve it:
  `python3 -m http.server -d docs/redesign/reference 8731` → http://127.0.0.1:8731/PQA-Redesign.standalone.html)
- `docs/redesign/reference/pqa-app.jsx` — the design's React source. **Read this
  for exact colors, spacing, and layout.** We do NOT port this React code; it is
  a spec, not an implementation.

---

## 2. "Why is this a big task? It's only a UI re-skin" — honest answer

You're right that it's **mostly a re-skin, not a rewrite.** The earlier "big
task" framing assumed Option 2 meant *porting the React design into the app and
re-wiring the backend*. It doesn't. Here's the real shape:

- The existing app **already implements everything the design shows** — KPI
  cards, time-series tabs (Detected Events first), ITIC curve, compliance table,
  event snapshots, report panel, and the full config sidebar. See
  `web/src/lib/ComplianceView.svelte` + `web/src/lib/Sidebar.svelte`.
- The design is **React**; our app is **Svelte 5**. But we are **not porting
  frameworks** — the React file is only a visual reference. We restyle the
  Svelte components we already have.
- All in-app charts (incl. snapshots) are **ECharts on canvas** with inline
  color options (`DetectedEventsChart`, `TimeSeriesChart`, `IticChart`,
  `SnapshotChart`). They theme to dark by changing option colors — **no white
  matplotlib images in the UI.** (matplotlib is only used for the exported
  report PDF/DOCX, which we intentionally keep print-light.)

So the work is really three buckets:

| Bucket | Effort | Why it's not trivial either |
|---|---|---|
| **Color/theme swap** (light→dark tokens) | Low | Tokens are centralized in `app.css`, but many components carry hardcoded light colors (`#0f172a`, `#e2e8f0`, `#fff`) inline that must each move to tokens. |
| **Sidebar restructure** | Medium | The design reorganizes the sidebar into a Data-Source card + collapsible Sections + a dual-handle time slider + a tolerances matrix. This is real markup/layout work, not just colors — and every control must keep its current wiring to `config`. |
| **Chart re-theming** | Low–Medium | Each ECharts option needs dark axis/grid/text colors; best done once via a shared theme object. |

Net: **moderate, well-bounded, parallelizable** — perfect for slicing into
Codex-sized tasks. The only genuine "gotcha" is keeping **wiring parity**: the
new sidebar must drive the exact same `config` fields and backend calls as the
current one, or analysis silently diverges. Each task below has an explicit
"wiring parity" acceptance check for that reason.

---

## 3. Strategy: standalone, non-default, reversible

**Mount parallel redesign components behind a runtime theme flag.** Reuse all
existing logic/children/backend; do not touch the classic components.

- `theme` store (`'classic' | 'redesign'`), persisted to `localStorage`,
  default `'classic'`. Sets `document.documentElement.dataset.theme`.
- **Colors** come from CSS variables scoped under `:root[data-theme="redesign"]`.
- **Structure** (top bar, sidebar, compliance layout) that can't be expressed in
  CSS alone is built as **new components** (`*Redesign.svelte`) that **reuse the
  existing child components and the existing backend/config**, mounted only when
  `theme === 'redesign'`.
- A small **toggle** in the top bar flips themes live for A/B comparison.

**Why parallel components, not in-place refactor (for the prototype):**
zero regression risk to the live app, trivial A/B, and trivial to delete if
rejected. When/if we approve it, **Phase 8** folds the redesign into mainline and
removes the classic shell.

**Reuse, don't reimplement:** `TimeSeriesChart`, `DetectedEventsChart`,
`IticChart`, `SnapshotChart`, `ComplianceTable`, `EventCard`, `ReportPanel`,
`ClipboardButtons`, `SteadyStatePanel`, `HelpDialog`, `ChangelogDialog`,
`CrashPrompt`, and the whole `backend/` + `config/` layer are reused as-is
(restyled, not rebuilt).

---

## 4. Design token map (classic → redesign)

From `docs/redesign/reference/PQA-Redesign.standalone.html` `:root`. Add these
under `:root[data-theme="redesign"]` and route component colors through them.

| Token | Redesign value | Used for |
|---|---|---|
| `--bg` | `#080c14` | app background |
| `--bg-side` | `#0a0f1a` | sidebar bg |
| `--bg-main` | `#0a0e16` | main panel bg |
| `--panel` | `#0f1626` | inputs, cards |
| `--panel-2` | `#131c2e` | raised card top |
| `--panel-3` | `#182238` | hover/button |
| `--line` | `#1c2740` | hairlines |
| `--line-2` | `#243149` | input borders |
| `--ink` | `#eef3fa` | primary text |
| `--sub` | `#93a2bd` | secondary text |
| `--mute` | `#5f6f8c` | tertiary text |
| `--faint` | `#41506b` | faint text |
| `--blue` | `#3b82f6` | primary accent |
| `--green` | `#34d399` | pass |
| `--red` | `#f87171` | fail |
| `--amber` | `#fbbf24` | fault/warn |
| `--violet` | `#8b7cf6` | logger pill |
| `--cyan` | `#22d3ee` | tolerances accent |

Fonts unchanged: Inter (UI) + JetBrains Mono (`.mono`, data/inputs).

---

## 5. Component inventory

| Component | Action | Notes |
|---|---|---|
| `App.svelte` | New shell `AppShellRedesign.svelte` (parallel) | Reuse tab/`go()`/mount logic; new dark top bar w/ pill nav + Help/desktop pills + version badge. |
| `Sidebar.svelte` | New `SidebarRedesign.svelte` (parallel) | Biggest visual task. Same `$props`, same `config`/backend wiring. |
| `ComplianceView.svelte` | Restyle layout (KPI strip, section heads, tabs) — can mostly be CSS-var-driven; verify | Reused by both Compliance + WinScope (`mode` prop). |
| `DetectedEventsChart` / `TimeSeriesChart` / `IticChart` / `SnapshotChart` | Dark ECharts theme | Centralize colors in one shared theme object keyed off `theme`. |
| `ComplianceTable`, `EventCard`, `ReportPanel`, `ClipboardButtons`, `SteadyStatePanel` | Restyle to tokens | Behavior untouched. |
| `HelpDialog`, `ChangelogDialog`, `CrashPrompt` | Dark restyle | Modals/overlays. |
| `SetPointView`, `EcuPlotView`, `SettingsReferenceView` | Dark consistency pass (Phase 6) | Not in the design; theme for coherence. |
| `backend/*`, `config/*` | **No change** | Source of truth for wiring. |

---

## 6. Phased task breakdown (Codex-ready briefs)

Each brief is self-contained: a fresh agent (or Codex) should be able to execute
it from the brief + the referenced files. Run on `redesign/dark-ui`. After each
task: `cd web && npm run build` must pass, and `npm run check` (svelte-check) if
present.

> **Global wiring-parity rule (applies to every phase that touches a control):**
> A redesign control must read/write the **same `config` field** and call the
> **same backend method** as its classic counterpart in `Sidebar.svelte` /
> `ComplianceView.svelte`. When in doubt, diff the bound variable names. Do not
> invent new config fields.

---

### Phase 1 — Theme scaffolding  *(Codex-friendly, ~small)*

**Files:** `web/src/theme/theme.ts` (new), `web/src/app.css`, `web/src/App.svelte`.

**Scope**
1. Create a Svelte store `theme` in `web/src/theme/theme.ts`:
   - type `Theme = 'classic' | 'redesign'`; default `'classic'`.
   - init from `localStorage['pqa-theme']`; subscribe to persist on change.
   - export a helper to set `document.documentElement.dataset.theme`.
2. In `app.css`, add the redesign tokens from §4 under
   `:root[data-theme="redesign"]`, plus dark `html,body` background/text and the
   dark scrollbar rules from the standalone reference.
3. In `App.svelte` `onMount`, apply the stored theme to
   `document.documentElement.dataset.theme`. Add a temporary toggle (a `<button>`
   in the tab bar) that flips `theme` — final placement comes in Phase 2.
4. When `theme === 'redesign'`, render a placeholder (`<div>redesign shell TBD</div>`)
   instead of the classic shell body, to prove the switch works. (Replaced in P2.)

**Acceptance**
- Toggling flips `data-theme` and persists across reload.
- Classic mode is byte-for-byte unchanged (default).
- Build passes.

**Out of scope:** any visual restyle of real content.

---

### Phase 2 — Redesign app shell + top bar  *(Codex-friendly)*

**Files:** `web/src/lib/redesign/AppShellRedesign.svelte` (new), `App.svelte`.

**Reference:** `pqa-app.jsx` `TopBar()` (lines ~102–153) and `PQAApp()`
(lines ~491–507).

**Scope**
- New shell owns the same tab state machine as `App.svelte` (`TabKey`, `TABS`,
  `visibleTabs`, `go()`, lazy `mounted` map, `helpOpen`/`changelogOpen`).
  Extract the shared tab logic so both shells use one source if practical;
  otherwise duplicate verbatim for the prototype.
- Build the dark 56px top bar: gradient bolt logo, `PQA PROJECT` wordmark,
  `v4.1` version pill (wired to `APP_VERSION`, opens `ChangelogDialog`), the 5
  tab items with active underline + icon, and right-side `Help` pill +
  `desktop`/platform status pill (green dot). Put the **theme toggle** here.
- Render the same view components as `App.svelte` (`ComplianceView`, etc.) inside
  the dark `<main>`; reuse the existing `{#if mounted...}` lazy pattern.
- `App.svelte`: when `theme === 'redesign'`, mount `AppShellRedesign`; else the
  classic shell.

**Acceptance**
- All 5 tabs switch and lazy-mount exactly as classic.
- Version pill opens changelog; Help opens help; platform pill shows `caps.platform`.
- Compliance tab renders the real `ComplianceView` (still classic-styled inside —
  that's Phases 3–4).

---

### Phase 3 — Sidebar redesign  *(largest; split into 3a/3b/3c)*

**Files:** `web/src/lib/redesign/SidebarRedesign.svelte` (new) + small section
subcomponents under `web/src/lib/redesign/sidebar/`.
**Reference:** `pqa-app.jsx` `Sidebar()` + atoms `Switch`, `ToggleRow`,
`Stepper`, `Section` (lines ~22–320).
**Wiring source of truth:** the current `web/src/lib/Sidebar.svelte` (577 lines)
— every prop, `bind:`, and backend call the redesign sidebar must reproduce.

First step for whoever picks this up: **read `Sidebar.svelte` end to end** and
write a one-page map of `{control → config field / bound prop / backend call}`.
Build against that map.

**3a — Shell + Data Source + Time Window**
- Reusable `Section` (collapsible, accent bar, count badge), `Switch`,
  `ToggleRow`, `Stepper` atoms (port visual from the jsx; make them controlled —
  value in, change out — not internally-stateful like the jsx mock).
- Sticky "Configuration" header w/ `G3 · hioki`-style status (real preset +
  logger format).
- **Data Source card:** filename, logger-format pill (hioki/miro/winscope
  colors), `.csv · N samples`, "Change file" button → existing hidden file input
  + `use:dropzone` (reuse `dropzone.ts`).
- **Time Window** Section: the two time pills (`timeStart`/`timeEnd`), the
  dual-handle slider, "Exact times" expander (the real text inputs), "Reset to
  full file". Slider may start presentational and bind to `timeStart/timeEnd`;
  making drag fully functional is an enhancement, not a blocker.

**3b — Acceptance Preset + Detection + Tolerances**
- **Acceptance Preset** select wired to the real preset list (`preset_store.ts` /
  `PresetConfigurator`), not the static options in the jsx. Selecting a preset
  fills detection/tolerance values; editing a value → "custom" (mirror current
  behavior).
- **Detection** Section: steppers for detection window, snapshot window, recovery
  verify, fault recovery, load threshold → same `config` fields as classic.
- **Tolerances** matrix (Voltage/Freq × Tolerance%/Recovery s/Max dev%): a clean
  grid of inputs bound to the real tolerance config fields. Watch asymmetric
  fields (see Advanced).

**3c — Display Options + Advanced + parity audit**
- **Display Options** Section: "Show limits on graphs" + the on-snapshot toggles
  (Tolerance band, Deviation limits, Intersection points, Max deviation) →
  `config.show_*` fields.
- **Advanced** Section: the 5 asymmetric/ISO-dual toggles → real `config` fields.
- **Parity audit:** diff the redesign sidebar's emitted `config` against the
  classic sidebar for the same inputs; they must be identical. Add a small test
  or a checklist in the PR description.

**Acceptance (3a–3c)**
- Visual match to reference sections.
- Running analysis from the redesign sidebar produces **the same `config`** and
  the same `runAnalysis` result as the classic sidebar for identical inputs.
- `onRun`, `onFile`, drag-and-drop, preset apply all functional.

---

### Phase 4 — Main content re-theme  *(Codex-friendly, mostly colors)*

**Files:** `ComplianceView.svelte` (style block), the 4 chart components, a new
`web/src/theme/echarts-dark.ts`, `ComplianceTable.svelte`, `EventCard.svelte`,
`ReportPanel.svelte`, `ClipboardButtons.svelte`, `SteadyStatePanel.svelte`.

**Scope**
- **KPI strip** → compact accent style from the jsx `Kpis()` (lines ~324–349):
  label left, big mono number right, colored left accent bar + subtle inner glow
  for pass/fail/fault. Map to existing `result.events.length`, `passCount`,
  `failCount`, `faultCount`, `result.n_rows`.
- **Section heads / time-series tabs** → dark tokens (active underline = `--blue`).
- **Charts:** create one shared dark ECharts theme (`echarts-dark.ts`) — axis
  text `--sub`, split lines `--line`, tooltip dark, series colors from tokens —
  and apply it in each chart when `theme === 'redesign'`. Replace the hardcoded
  `#64748b`/`#e2e8f0`/`#cbd5e1`/`#0f172a` in `DetectedEventsChart`/`IticChart`/
  `TimeSeriesChart`/`SnapshotChart` with theme-driven values.
- **Compliance table, EventCard, ReportPanel, ClipboardButtons, SteadyStatePanel**
  → restyle to tokens (dark surfaces, token borders, keep pass/fail semantics).
- **Banners / empty / boot states** → dark variants.

**Acceptance**
- Compliance results page matches the reference look in dark.
- Charts legible on dark (axes, grid, tooltips, markers).
- Classic theme visually unchanged.

---

### Phase 5 — Dialogs & overlays

**Files:** `HelpDialog.svelte`, `ChangelogDialog.svelte`, `CrashPrompt.svelte`,
`PresetConfigurator.svelte`, `InfoTip.svelte`.

**Scope:** dark restyle of modal surfaces, backdrops, form controls, code/preview
areas. Keep all behavior. Ensure focus rings/contrast meet AA.

**Acceptance:** every overlay is legible and on-brand in dark; classic unchanged.

---

### Phase 6 — Other tabs consistency pass

**Files:** `SetPointView.svelte`, `EcuPlotView.svelte`,
`SettingsReferenceView.svelte` (+ their charts/tables).

**Scope:** the design only specs Compliance; bring the other four tabs to the
dark theme for coherence (tables, sub-tabs, ECU plots via the shared ECharts dark
theme, settings reference typography).

**Acceptance:** no light-on-light or dark-on-dark legibility breaks on any tab.

---

### Phase 7 — QA & polish

**Scope (per `~/.claude/rules/web/testing.md`):**
- **Responsive:** 320 / 375 / 768 / 1024 / 1440 / 1920 — no overflow; sidebar
  collapse behavior at ≤820px (classic stacks; verify redesign does too).
- **Accessibility:** keyboard nav across tabs/sidebar/dialogs; visible focus;
  color-contrast AA on dark; `prefers-reduced-motion` respected for the slider/
  transitions.
- **Visual regression:** screenshot Compliance in both themes at 768/1440.
- **Cross-check:** real CSV → analysis → charts → report still correct (run the
  `report_test/` harness — reports stay print-light; confirm the dark UI did not
  leak into report images).
- **Perf:** bundle budget (app page < 300kb JS gz per the web perf rules); ensure
  shipping two shells temporarily doesn't blow the budget — if it does, lazy-load
  the inactive shell.

---

### Phase 8 — Make it the default *(separate go/no-go — do not start without sign-off)*

Only after evaluation approves the redesign:
1. Flip the `theme` default to `'redesign'` (or keep the toggle as a user pref).
2. Fold redesign components into mainline; delete the classic shell/sidebar (or
   keep classic as an opt-out for one release).
3. Remove now-dead light-only CSS; collapse duplicated tab logic.
4. Update `CLAUDE.md` "UI Design System" + "Design Tokens" sections to dark.
5. Full regression + report-harness pass; merge to `main`.

---

## 7. How to run / preview

**The redesign target (mock):**
```bash
python3 -m http.server -d docs/redesign/reference 8731
# open http://127.0.0.1:8731/PQA-Redesign.standalone.html
```

**The real app (once Phase 1+ lands), web preview with mock backend:**
```bash
cd web && npm install && npm run dev      # toggle theme in the top bar
```

**The real desktop app (real backend):**
```bash
pip install -r desktop/requirements.txt
cd web && npm run build
python -m desktop.shell
```

---

## 8. Risks & gotchas

- **Wiring parity is the #1 risk.** The new sidebar must drive identical `config`
  + backend calls. Build from a control→config map derived from `Sidebar.svelte`;
  add a parity check before calling Phase 3 done.
- **Reports stay light.** `visualizations.py` (matplotlib) renders the exported
  PDF/DOCX for print — do **not** darken it. The dark theme is UI-only. Confirm
  with the `report_test/` harness after Phase 4/7.
- **ECharts colors are inline per-component.** Centralize in `echarts-dark.ts` or
  they drift. Don't hardcode dark hexes the way the classic ones are hardcoded.
- **Dual shells temporarily double some markup/CSS.** Acceptable for a prototype;
  watch the bundle budget (Phase 7) and lazy-load if needed; Phase 8 removes the
  duplication.
- **Time slider** in the design is presentational. Functional drag is a nice-to-
  have; the functional path is the existing `timeStart/timeEnd` inputs.
- **Preset list** must come from the real `preset_store`, not the static options
  baked into the design jsx.
- **Don't restart vs hot-reload**: standard Vite HMR for web; the desktop shell
  needs a `npm run build` to pick up frontend changes.

---

## 9. Open decisions (resolve as we go)

1. **Toggle permanence:** keep the classic/redesign toggle as a shipped user
   preference, or remove it at Phase 8? (Default assumption: keep for one release
   as an opt-out, then remove.)
2. **Charts:** one shared ECharts dark theme object vs per-component overrides.
   (Recommended: shared object.)
3. **Sidebar atoms:** new redesign-only atoms vs refactoring classic atoms to be
   theme-aware. (Recommended for prototype: redesign-only, under
   `lib/redesign/`.)
4. **Phase 8 trigger:** explicit sign-off after evaluating the Phase 1–6 build.

---

## 10. Progress log

- **Phase 0 — done (this session):** extracted the design from the Claude share
  (`pqa-app.jsx` + wrapper) via the design file API; created branch
  `redesign/dark-ui`; committed reference assets
  (`docs/redesign/reference/pqa-app.jsx`,
  `docs/redesign/reference/PQA-Redesign.standalone.html`) and this plan; verified
  the standalone renders.
- **Phase 1 — done:** added `web/src/theme/theme.svelte.ts` (runes module:
  `themeState`, `initTheme`, `setTheme`, `toggleTheme`; localStorage-persisted,
  default `classic`); redesign tokens under `:root[data-theme="redesign"]` in
  `app.css` (new names + overrides of classic shared tokens + dark body/scrollbar);
  `main.ts` calls `initTheme()` before mount (no flash); `App.svelte` has a
  top-bar theme toggle and shows a dark placeholder body when redesign is active.
  Verified: toggle flips live, persists across reload, `npm run check`/`build`
  both green, classic look unchanged.
- **Phase 2 — done:** added `web/src/lib/redesign/Icon.svelte` (the design's SVG
  icon set, reused by the sidebar in P3) and
  `web/src/lib/redesign/AppShellRedesign.svelte` — dark 56px top bar (gradient
  bolt logo, wordmark, version pill → changelog, icon tabs w/ blue active
  underline, Help + Classic-toggle + platform-status pills) over the real views
  (own tab state machine + lazy mount, mirrors `App.svelte`). `App.svelte` now
  branches at the top level: redesign → `AppShellRedesign`, else the unchanged
  classic shell; the classic top bar keeps a `🌙 Redesign` toggle. Inner content
  (sidebar + results) stays classic-styled until P3/P4. Verified: top bar matches
  the design, tabs switch + lazy-mount, toggle round-trips classic↔redesign with
  no regression, `npm run check`/`build` green.
- **Phase 3 —** _not started_
- **Phase 4 —** _not started_
- **Phase 5 —** _not started_
- **Phase 6 —** _not started_
- **Phase 7 —** _not started_
- **Phase 8 —** _not started (gated on sign-off)_
