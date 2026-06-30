// Global UI theme.
//
//   'classic'  — the shipping look (light main area, navy sidebar).
//   'redesign' — the dark redesign prototype. See docs/redesign/PLAN.md.
//
// Non-default: defaults to 'classic'. Persisted to localStorage and applied as
// `data-theme` on <html>, so the CSS-variable overrides under
// `:root[data-theme="redesign"]` in app.css take effect. This is a runes module
// (`*.svelte.ts`) so `themeState` is shared reactive state across components —
// read `themeState.current`; switch with setTheme()/toggleTheme().
export type Theme = 'classic' | 'redesign';

const STORAGE_KEY = 'pqa-theme';

function readStored(): Theme {
  try {
    return localStorage.getItem(STORAGE_KEY) === 'redesign' ? 'redesign' : 'classic';
  } catch {
    return 'classic';
  }
}

function applyAttr(theme: Theme): void {
  if (typeof document !== 'undefined') {
    document.documentElement.dataset.theme = theme;
  }
}

/** Shared reactive theme state. Read `themeState.current` in components. */
export const themeState = $state<{ current: Theme }>({ current: 'classic' });

/**
 * Hydrate from storage and apply the `data-theme` attribute. Call once, as early
 * as possible (main.ts, before mount) to avoid a flash of the wrong theme.
 */
export function initTheme(): void {
  const stored = readStored();
  themeState.current = stored;
  applyAttr(stored);
}

export function setTheme(theme: Theme): void {
  themeState.current = theme;
  applyAttr(theme);
  try {
    localStorage.setItem(STORAGE_KEY, theme);
  } catch {
    /* non-persistent is acceptable */
  }
}

export function toggleTheme(): void {
  setTheme(themeState.current === 'redesign' ? 'classic' : 'redesign');
}
