// Custom acceptance presets.
//
// Persistence is host-first: on the desktop they live in a durable presets.json
// in the per-user app-data dir (via the backend bridge), so they survive
// reinstalls and can be exported/shared. In a plain browser (no bridge) they
// fall back to localStorage — same as the analysis config + report fields.
//
// A custom preset carries the SAME acceptance-criteria field subset the built-ins
// set, so applying it overlays only those fields (nominal V/f, display options and
// the time window stay put).
import type { AnalysisBackend } from '../backend';
import type { PresetRecord } from '../backend/types';
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

function isPreset(p: unknown): p is Preset {
  return (
    !!p &&
    typeof (p as Preset).name === 'string' &&
    typeof (p as Preset).values === 'object' &&
    (p as Preset).values !== null
  );
}

function normalize(arr: unknown): Preset[] {
  if (!Array.isArray(arr)) return [];
  return arr.filter(isPreset).map((p) => ({ name: p.name.trim(), values: { ...p.values } }));
}

// --- localStorage fallback (browser dev) -----------------------------------
function loadLocal(): Preset[] {
  try {
    const raw = localStorage.getItem(CUSTOM_PRESETS_KEY);
    if (raw) return normalize(JSON.parse(raw));
  } catch {
    /* ignore — a missing/corrupt store just means no custom presets yet */
  }
  return [];
}
function saveLocal(presets: Preset[]): void {
  try {
    localStorage.setItem(CUSTOM_PRESETS_KEY, JSON.stringify(presets));
  } catch {
    /* ignore */
  }
}

// --- host-first load / persist ---------------------------------------------
/** Load custom presets: durable host store on desktop, localStorage in browser. */
export async function loadPresets(backend?: AnalysisBackend): Promise<Preset[]> {
  if (backend?.listPresets) {
    try {
      return normalize(await backend.listPresets());
    } catch {
      /* fall back to localStorage */
    }
  }
  return loadLocal();
}

/** Persist the full custom-preset list; returns the (possibly normalized) list. */
export async function persistPresets(presets: Preset[], backend?: AnalysisBackend): Promise<Preset[]> {
  if (backend?.savePresets) {
    try {
      return normalize(await backend.savePresets(presets as unknown as PresetRecord[]));
    } catch {
      /* fall back to localStorage */
    }
  }
  saveLocal(presets);
  return presets;
}

/** Capture the acceptance-criteria subset of the current config as a preset. */
export function capturePreset(name: string, config: AnalysisConfigInput): Preset {
  const values: Partial<AnalysisConfigInput> = {};
  for (const k of PRESET_FIELDS) {
    (values as Record<string, unknown>)[k] = config[k];
  }
  return { name: name.trim(), values };
}

/** Whether a name collides with a built-in preset (those are read-only). */
export function isBuiltinName(name: string): boolean {
  return BUILTIN_PRESETS.some((p) => p.name === name.trim());
}

/** A non-colliding "<base> (copy)" name for duplicating a preset. */
export function uniqueCopyName(base: string, existing: Preset[]): string {
  const taken = new Set([...existing.map((p) => p.name), ...BUILTIN_PRESETS.map((p) => p.name)]);
  let name = `${base} (copy)`;
  let i = 2;
  while (taken.has(name)) name = `${base} (copy ${i++})`;
  return name;
}
