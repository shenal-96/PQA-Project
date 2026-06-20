<script lang="ts">
  import type { EventRecord } from '../backend/types';
  import { cell, num2 } from '../lib/format';

  let { events }: { events: EventRecord[] } = $props();

  function isPass(e: EventRecord): boolean {
    return String(e['Compliance_Status'] ?? '').toLowerCase() === 'pass';
  }
  function isFault(e: EventRecord): boolean {
    return e['Potential_Fault'] === true;
  }
  function notes(e: EventRecord): string {
    const reasons = String(e['Failure_Reasons'] ?? '').trim();
    const fault = String(e['Fault_Reasons'] ?? '').trim();
    return [reasons, fault ? `⚠ ${fault}` : ''].filter(Boolean).join(' · ') || '—';
  }
</script>

<div class="wrap">
  <table>
    <thead>
      <tr>
        <th>Event start</th>
        <th>ΔkW</th>
        <th>Voltage extreme</th>
        <th>Freq extreme</th>
        <th>V rec (s)</th>
        <th>F rec (s)</th>
        <th>Status</th>
        <th>Notes</th>
      </tr>
    </thead>
    <tbody>
      {#each events as e}
        <tr class:fail={!isPass(e)}>
          <td class="mono">{cell(e['Start_Timestamp'])}</td>
          <td class="mono">{num2(e['dKw'])}</td>
          <td class="mono">{num2(e['V_dev'])}</td>
          <td class="mono">{num2(e['F_dev'])}</td>
          <td class="mono">{num2(e['V_rec_s'])}</td>
          <td class="mono">{num2(e['F_rec_s'])}</td>
          <td>
            <span class="pill" class:pass={isPass(e)} class:bad={!isPass(e)}>
              {cell(e['Compliance_Status'])}
            </span>
            {#if isFault(e)}<span class="pill warn">⚠ Investigate</span>{/if}
          </td>
          <td class="notes">{notes(e)}</td>
        </tr>
      {/each}
    </tbody>
  </table>
</div>

<style>
  .wrap {
    overflow-x: auto;
    border: 1px solid var(--border);
    border-radius: 10px;
    background: var(--card);
  }
  table { border-collapse: collapse; width: 100%; font-size: 13px; }
  th, td { padding: 10px 14px; text-align: left; border-bottom: 1px solid var(--border); }
  th {
    background: #f1f5f9;
    color: var(--text-sub);
    font-weight: 600;
    text-transform: uppercase;
    font-size: 11px;
    letter-spacing: 0.04em;
  }
  tr:last-child td { border-bottom: none; }
  tr.fail { background: #fef2f2; }
  .notes { color: var(--text-sub); max-width: 280px; }
  .pill {
    display: inline-block;
    padding: 2px 10px;
    border-radius: 999px;
    font-size: 12px;
    font-weight: 600;
  }
  .pill.pass { background: #dcfce7; color: #15803d; }
  .pill.bad { background: #fee2e2; color: #b91c1c; }
  .pill.warn { background: #fffbeb; color: #b45309; margin-left: 6px; }
</style>
