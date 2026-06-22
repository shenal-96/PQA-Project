<script lang="ts">
  import type { EventRecord } from '../backend/types';

  let { events }: { events: EventRecord[] } = $props();

  let status = $state('');
  let statusOk = $state(true);

  /** Format a cell to fixed decimals, or '' when the value isn't numeric. */
  function fmt(v: unknown, decimals: number): string {
    const n = typeof v === 'number' ? v : Number(v);
    return v == null || v === '' || Number.isNaN(n) ? '' : n.toFixed(decimals);
  }

  /**
   * Build a 2-column TSV (deviation + recovery seconds, tab-separated, one row
   * per event) for pasting into a spreadsheet. Mirrors the Streamlit app:
   * rows where both values are blank are skipped.
   */
  function buildTsv(devCol: string, recCol: string, devDecimals: number): string {
    const lines: string[] = [];
    for (const e of events) {
      const dev = fmt(e[devCol], devDecimals);
      const rec = fmt(e[recCol], 2);
      if (dev === '' && rec === '') continue;
      lines.push(`${dev}\t${rec}`);
    }
    return lines.join('\n');
  }

  async function writeClipboard(text: string): Promise<boolean> {
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(text);
        return true;
      }
    } catch {
      // fall through to the execCommand fallback (WebView2 / file:// quirks)
    }
    try {
      const ta = document.createElement('textarea');
      ta.value = text;
      ta.style.position = 'fixed';
      ta.style.opacity = '0';
      document.body.appendChild(ta);
      ta.select();
      const ok = document.execCommand('copy');
      document.body.removeChild(ta);
      return ok;
    } catch {
      return false;
    }
  }

  async function copy(devCol: string, recCol: string, devDecimals: number, label: string) {
    const tsv = buildTsv(devCol, recCol, devDecimals);
    if (!tsv) {
      statusOk = false;
      status = `Nothing to copy for ${label}.`;
      return;
    }
    const ok = await writeClipboard(tsv);
    statusOk = ok;
    status = ok
      ? `${label} copied (${tsv.split('\n').length} rows).`
      : `Copy failed for ${label}.`;
  }
</script>

<div class="clip-row">
  <button class="clip v" onclick={() => copy('V_dev', 'V_rec_s', 1, 'Voltage')}>
    Copy Voltage Compliance to Clipboard
  </button>
  <button class="clip f" onclick={() => copy('F_dev', 'F_rec_s', 3, 'Frequency')}>
    Copy Frequency Compliance to Clipboard
  </button>
  {#if status}
    <span class="status" class:ok={statusOk} class:err={!statusOk}>{status}</span>
  {/if}
</div>

<style>
  .clip-row {
    display: flex;
    gap: 12px;
    align-items: center;
    flex-wrap: wrap;
    margin: 10px 0 4px;
  }
  .clip {
    padding: 8px 14px;
    border-radius: 8px;
    border: 1px solid transparent;
    color: #fff;
    font-weight: 600;
    font-size: 13px;
    cursor: pointer;
  }
  .clip.v { background: #2563eb; border-color: #2563eb; }
  .clip.f { background: #0891b2; border-color: #0891b2; }
  .clip:hover { filter: brightness(1.05); }
  .clip:active { filter: brightness(0.95); }
  .status { font-size: 12px; }
  .status.ok { color: #16a34a; }
  .status.err { color: #dc2626; }
</style>
