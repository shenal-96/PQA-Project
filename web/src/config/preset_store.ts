// Custom acceptance presets, persisted in localStorage — mirrors how the analysis
// config (pqa.config.v2) and report fields (pqa.report.*) are already stored.
//
// Built-in presets live in defaults.ts (BUILTIN_PRESETS) and are never written
// here. A custom preset carries the SAME acceptance-criteria field subset the
// built-ins set — captured from the current sidebar config — so applying it
// overlays only those fields (display options, nominal V/f, time window stay put).
import type { AnalysisConfigInput, Preset } from './defaults';
import { BUILTIN_PRESETS } from './defaults';

const CUSTOM_PRESETS_KEY = 'pqa.presets.v1';

/**
 * The acceptance-criteria fields a preset carries = the union of keys the
 * built-in presets set. Deriving it (rather than hardcoding) keeps custom
 * presets in lock-step with the built-ins if those ever gain/lose a field.
 */
export const PRESET_FIELDS = Array.from(
  new Set(BUILTIN_PRESETS.flatMap((p) => Object.keys(p.values))),
) as (keyof AnalysisConfigInput)[];

export function loadCustomPresets(): Preset[] {
  try {
    const raw = localStorage.getItem(CUSTOM_PRESETS_KEY);
    if (raw) {
      const arr: unknown = JSON.parse(raw);
      if (Array.isArray(arr)) {
        return arr.filter(
          (p): p is Preset =>
            !!p &&
            typeof (p as Preset).name === 'string' &&
            typeof (p as Preset).values === 'object' &&
            (p as Preset).values !== null,
        );
      }
    }
  } catch {
    /* ignore — a missing/corrupt store just means no custom presets yet */
  }
  return [];
}

function persist(presets: Preset[]): void {
  try {
    localStorage.setItem(CUSTOM_PRESETS_KEY, JSON.stringify(presets));
  } catch {
    /* ignore */
  }
}

/** Capture the acceptance-criteria subset of the current config as a preset. */
export function capturePreset(name: string, config: AnalysisConfigInput): Preset {
  const values: Partial<AnalysisConfigInput> = {};
  for (const k of PRESET_FIELDS) {
    (values as Record<string, unknown>)[k] = config[k];
  }
  return { name: name.trim(), values };
}

/** Insert or replace a custom preset by name; returns the updated list. */
export function saveCustomPreset(preset: Preset, existing: Preset[] = loadCustomPresets()): Preset[] {
  const idx = existing.findIndex((p) => p.name === preset.name);
  const next = idx >= 0 ? existing.map((p, i) => (i === idx ? preset : p)) : [...existing, preset];
  persist(next);
  return next;
}

/** Remove a custom preset by name; returns the updated list. */
export function deleteCustomPreset(name: string, existing: Preset[] = loadCustomPresets()): Preset[] {
  const next = existing.filter((p) => p.name !== name);
  persist(next);
  return next;
}

/** Whether a name collides with a built-in preset (those are read-only). */
export function isBuiltinName(name: string): boolean {
  return BUILTIN_PRESETS.some((p) => p.name === name.trim());
}
