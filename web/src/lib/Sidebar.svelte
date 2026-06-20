<script lang="ts">
  import type { AnalysisConfigInput, Preset } from '../config/defaults';
  import { BUILTIN_PRESETS, VOLTAGE_PRESETS } from '../config/defaults';
  import type { Caps } from '../backend/types';

  let {
    config,
    caps,
    fileName,
    loggerFormat,
    loading,
    accept = '.csv,text/csv',
    fileLabel = 'Logger CSV',
    activePreset = $bindable('None'),
    onRun,
    onFile,
  }: {
    config: AnalysisConfigInput;
    caps: Caps | undefined;
    fileName: string | undefined;
    loggerFormat: string | null | undefined;
    loading: boolean;
    accept?: string;
    fileLabel?: string;
    activePreset?: string;
    onRun: () => void;
    onFile: (ev: Event) => void;
  } = $props();

  function applyPreset(name: string) {
    activePreset = name;
    const preset: Preset | undefined = BUILTIN_PRESETS.find((p) => p.name === name);
    if (preset) Object.assign(config, preset.values);
  }
</script>

<aside class="sidebar">
  <div class="head">
    <div class="bolt">⚡</div>
    <div>
      <div class="title">PQA PROJECT</div>
      <div class="sub">Configuration</div>
    </div>
    {#if caps}<span class="env">{caps.platform}</span>{/if}
  </div>

  <section>
    <div class="grp-label">{fileLabel}</div>
    <label class="file-btn">
      {fileName ? 'Change file' : 'Load file'}
      <input type="file" {accept} onchange={onFile} hidden />
    </label>
    {#if fileName}
      <div class="filename" title={fileName}>{fileName}</div>
      {#if loggerFormat}<span class="pill">{loggerFormat}</span>{/if}
    {/if}
  </section>

  <section>
    <label class="grp-label" for="preset">Standard preset</label>
    <select id="preset" value={activePreset} onchange={(e) => applyPreset((e.target as HTMLSelectElement).value)}>
      <option value="None">None / custom</option>
      {#each BUILTIN_PRESETS as p}<option value={p.name}>{p.name}</option>{/each}
    </select>
  </section>

  <section>
    <div class="grp-label">Nominal voltage (V, L-L)</div>
    <div class="chips">
      {#each VOLTAGE_PRESETS as v}
        <button class="chip" class:on={config.nominal_voltage === v} onclick={() => (config.nominal_voltage = v)}>{v}</button>
      {/each}
    </div>
    <input type="number" bind:value={config.nominal_voltage} min="0" step="1" />

    <div class="grp-label">Nominal frequency (Hz)</div>
    <input type="number" bind:value={config.nominal_frequency} step="0.1" />

    <div class="grp-label">Voltage columns</div>
    <select bind:value={config.ln_to_ll_mode}>
      <option value="auto">Auto-detect (L-N ×√3 / L-L)</option>
      <option value="force_ll">Force L-L (no scaling)</option>
      <option value="force_ln">Force L-N (×√3)</option>
    </select>
  </section>

  <section>
    <div class="grp-label">Event detection</div>
    <div class="field"><span>Load threshold (kW)</span><input type="number" bind:value={config.load_threshold_kw} step="1" /></div>
    <div class="field"><span>Detection window (s)</span><input type="number" bind:value={config.detection_window_s} step="0.5" /></div>
    <div class="field"><span>Snapshot window (s)</span><input type="number" bind:value={config.snapshot_window_s} step="1" /></div>
  </section>

  <section>
    <div class="grp-label">Tolerances &amp; recovery</div>
    <div class="field"><span>Voltage tol (%)</span><input type="number" bind:value={config.voltage_tolerance_pct} step="0.1" /></div>
    <div class="field"><span>Voltage recovery (s)</span><input type="number" bind:value={config.voltage_recovery_time_s} step="0.5" /></div>
    <div class="field"><span>Frequency tol (%)</span><input type="number" bind:value={config.frequency_tolerance_pct} step="0.1" /></div>
    <div class="field"><span>Frequency recovery (s)</span><input type="number" bind:value={config.frequency_recovery_time_s} step="0.5" /></div>
    <div class="field"><span>Verify window (s)</span><input type="number" bind:value={config.recovery_verify_s} step="0.5" /></div>
    <div class="field"><span>Fault threshold (s)</span><input type="number" bind:value={config.fault_recovery_threshold_s} step="0.5" /></div>
  </section>

  <details>
    <summary>Advanced bands &amp; max-deviation</summary>
    <div class="grp-label">Freq recovery band — load increase (Hz)</div>
    <div class="field"><span>Upper</span><input type="number" bind:value={config.freq_recovery_upper_increase} step="0.05" /></div>
    <div class="field"><span>Lower</span><input type="number" bind:value={config.freq_recovery_lower_increase} step="0.05" /></div>
    <div class="grp-label">Freq recovery band — load decrease (Hz)</div>
    <div class="field"><span>Upper</span><input type="number" bind:value={config.freq_recovery_upper_decrease} step="0.05" /></div>
    <div class="field"><span>Lower</span><input type="number" bind:value={config.freq_recovery_lower_decrease} step="0.05" /></div>
    <div class="grp-label">Max deviation (%)</div>
    <div class="field"><span>Voltage ↑</span><input type="number" bind:value={config.volt_max_dev_pct_increase} step="1" /></div>
    <div class="field"><span>Voltage ↓</span><input type="number" bind:value={config.volt_max_dev_pct_decrease} step="1" /></div>
    <div class="field"><span>Freq ↑</span><input type="number" bind:value={config.freq_max_dev_pct_increase} step="1" /></div>
    <div class="field"><span>Freq ↓</span><input type="number" bind:value={config.freq_max_dev_pct_decrease} step="1" /></div>
  </details>

  <button class="run" onclick={onRun} disabled={loading || !fileName}>
    {loading ? 'Analyzing…' : 'Run Analysis'}
  </button>
  {#if !fileName}<div class="hint">Load a CSV to enable analysis.</div>{/if}
</aside>

<style>
  .sidebar {
    width: 320px;
    flex: 0 0 320px;
    background: var(--navy);
    color: #cbd5e1;
    padding: 18px 16px 28px;
    display: flex;
    flex-direction: column;
    gap: 16px;
    height: 100%;
    overflow-y: auto;
  }
  .head { display: flex; align-items: center; gap: 10px; }
  .head .bolt { width: 36px; height: 36px; display: grid; place-items: center; background: var(--blue); border-radius: 9px; font-size: 18px; }
  .head .title { font-weight: 700; color: #fff; font-size: 18px; }
  .head .sub { font-size: 11px; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.08em; }
  .head .env { margin-left: auto; background: #1e293b; color: #94a3b8; font-size: 11px; padding: 2px 8px; border-radius: 999px; }
  section { display: flex; flex-direction: column; gap: 8px; border-top: 1px solid #1e293b; padding-top: 14px; }
  .grp-label { font-size: 11px; text-transform: uppercase; letter-spacing: 0.06em; color: #94a3b8; margin-top: 4px; }
  input, select { background: #0b1220; border: 1px solid #1e293b; color: #e2e8f0; border-radius: 7px; padding: 7px 9px; font-size: 13px; font-family: "JetBrains Mono", monospace; width: 100%; }
  input:focus, select:focus { outline: none; border-color: var(--blue); }
  .field { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
  .field span { font-size: 12px; color: #cbd5e1; }
  .field input { width: 96px; flex: 0 0 96px; text-align: right; }
  .chips { display: flex; gap: 6px; }
  .chip { flex: 1; background: #0b1220; border: 1px solid #1e293b; color: #cbd5e1; padding: 6px; border-radius: 7px; font-size: 12px; }
  .chip.on { background: var(--blue); border-color: var(--blue); color: #fff; font-weight: 600; }
  .file-btn { background: #1e293b; color: #fff; text-align: center; padding: 9px; border-radius: 8px; font-size: 13px; font-weight: 600; cursor: pointer; }
  .filename { font-size: 11px; color: #94a3b8; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .pill { align-self: flex-start; background: #312e81; color: #c7d2fe; font-size: 11px; padding: 2px 8px; border-radius: 999px; }
  details summary { font-size: 12px; color: #94a3b8; cursor: pointer; padding: 6px 0; }
  details { border-top: 1px solid #1e293b; padding-top: 8px; display: flex; flex-direction: column; gap: 8px; }
  .run { background: var(--blue); color: #fff; border: none; padding: 12px; border-radius: 9px; font-size: 15px; font-weight: 700; cursor: pointer; margin-top: 4px; }
  .run:disabled { background: #334155; color: #94a3b8; cursor: not-allowed; }
  .hint { font-size: 11px; color: #64748b; text-align: center; }
</style>
