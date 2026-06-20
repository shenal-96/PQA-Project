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
