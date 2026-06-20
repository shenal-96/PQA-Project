// Display labels + colours for the processed metrics (mirrors the design tokens
// in CLAUDE.md / visualizations.py).

export const METRIC_LABELS: Record<string, string> = {
  Avg_kW: 'Active Power (kW)',
  Avg_Voltage_LL: 'Voltage L-L (V)',
  Avg_Current: 'Current (A)',
  Avg_Frequency: 'Frequency (Hz)',
  Avg_PF: 'Power Factor',
  Avg_THD_F: 'THD (%)',
};

export const METRIC_COLORS: Record<string, string> = {
  Avg_kW: '#2563eb',
  Avg_Voltage_LL: '#9333ea',
  Avg_Current: '#0891b2',
  Avg_Frequency: '#16a34a',
  Avg_PF: '#ea580c',
  Avg_THD_F: '#dc2626',
};

export function metricLabel(key: string): string {
  return METRIC_LABELS[key] ?? key.replace(/^Avg_/, '').replace(/_/g, ' ');
}

export function cell(v: unknown): string {
  return v === null || v === undefined || v === '' ? '—' : String(v);
}

/**
 * Display a calculated value at 2 decimal places. Numbers (and numeric strings)
 * are rounded to 2 dp; non-numeric values fall through to `cell()`. Used for all
 * calculated/measured values shown to the user (compliance table, chart tooltips).
 */
export function num2(v: unknown): string {
  if (v === null || v === undefined || v === '') return '—';
  const n = typeof v === 'number' ? v : Number(v);
  return Number.isFinite(n) ? n.toFixed(2) : cell(v);
}

/** ECharts tooltip/axis value formatter — 2 dp for numbers, passthrough otherwise. */
export function fmt2(v: unknown): string {
  return typeof v === 'number' && Number.isFinite(v) ? v.toFixed(2) : String(v ?? '');
}
