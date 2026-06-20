<script lang="ts">
  import { untrack } from 'svelte';
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

  // Nominal-voltage preset vs custom (matches the Streamlit selectbox).
  const VOLT_OPTS = ['415', '690', '11000', 'Custom'];
  let voltMode = $state(
    untrack(() => (VOLTAGE_PRESETS.includes(config.nominal_voltage) ? String(config.nominal_voltage) : 'Custom')),
  );

  function applyPreset(name: string) {
    activePreset = name;
    const preset: Preset | undefined = BUILTIN_PRESETS.find((p) => p.name === name);
    if (preset) Object.assign(config, preset.values);
  }

  function setVoltMode(v: string) {
    voltMode = v;
    if (v !== 'Custom') config.nominal_voltage = Number(v);
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

  <!-- ── Acceptance Criteria ───────────────────────────────────────── -->
  <section>
    <div class="sec-title">Acceptance Criteria</div>

    <label class="grp-label" for="preset">Active Preset</label>
    <select id="preset" value={activePreset} onchange={(e) => applyPreset((e.target as HTMLSelectElement).value)}>
      <option value="None">None</option>
      {#each BUILTIN_PRESETS as p}<option value={p.name}>{p.name}</option>{/each}
    </select>

    <label class="chk"><input type="checkbox" bind:checked={config.show_limits} /> Show Limits on Graphs</label>

    <div class="grp-label">Snapshot Display Options</div>
    <label class="chk"><input type="checkbox" bind:checked={config.show_tolerance_band} /> Show Tolerance Band on Snapshots</label>
    <label class="chk"><input type="checkbox" bind:checked={config.show_deviation_limits} /> Show Deviation Limits on Snapshots</label>
    <label class="chk"><input type="checkbox" bind:checked={config.show_intersections} /> Show Intersection Points</label>
    <label class="chk"><input type="checkbox" bind:checked={config.show_max_deviation} /> Show Max Deviation</label>

    <div class="field"><span>Detection Window (s)</span><input type="number" min="1" max="30" step="1" bind:value={config.detection_window_s} /></div>
    <div class="field"><span>Snapshot Window (s)</span><input type="number" min="3" max="60" step="1" bind:value={config.snapshot_window_s} /></div>
    <div class="field"><span>Recovery Verify Window (s)</span><input type="number" min="1" max="30" step="1" bind:value={config.recovery_verify_s} /></div>
    <div class="field"><span>Fault Recovery Threshold (s)</span><input type="number" min="1" max="120" step="1" bind:value={config.fault_recovery_threshold_s} /></div>
    <div class="field"><span>Load Threshold (kW)</span><input type="number" min="0" step="10" bind:value={config.load_threshold_kw} /></div>

    <label class="chk"><input type="checkbox" bind:checked={config.apply_asymmetric_volt} /> Apply asymmetric Voltage tolerance band</label>
    <label class="chk"><input type="checkbox" bind:checked={config.apply_asymmetric_volt_dev} /> Apply asymmetric Voltage deviation limit</label>
    <label class="chk"><input type="checkbox" bind:checked={config.apply_asymmetric_freq} /> Apply asymmetric Frequency tolerance band</label>
    <label class="chk"><input type="checkbox" bind:checked={config.apply_asymmetric_freq_dev} /> Apply asymmetric Frequency deviation limit</label>
    <label class="chk"><input type="checkbox" bind:checked={config.iso_8528_5_mode} /> Apply ISO dual frequency bands</label>

    <div class="two">
      <div class="col">
        <div class="field col-f"><span>Voltage Tolerance (%)</span><input type="number" min="0" step="0.5" bind:value={config.voltage_tolerance_pct} disabled={config.apply_asymmetric_volt} /></div>
        <div class="field col-f"><span>Voltage Recovery (s)</span><input type="number" min="0" step="0.5" bind:value={config.voltage_recovery_time_s} /></div>
        <div class="field col-f"><span>Max Voltage Dev (%)</span><input type="number" min="0" step="1" bind:value={config.voltage_max_deviation_pct} disabled={config.apply_asymmetric_volt_dev} /></div>
      </div>
      <div class="col">
        <div class="field col-f"><span>Frequency Tolerance (%)</span><input type="number" min="0" step="0.1" bind:value={config.frequency_tolerance_pct} disabled={config.apply_asymmetric_freq} /></div>
        <div class="field col-f"><span>Frequency Recovery (s)</span><input type="number" min="0" step="0.5" bind:value={config.frequency_recovery_time_s} /></div>
        <div class="field col-f"><span>Max Frequency Dev (%)</span><input type="number" min="0" step="1" bind:value={config.frequency_max_deviation_pct} disabled={config.apply_asymmetric_freq_dev} /></div>
      </div>
    </div>

    {#if config.apply_asymmetric_volt}
      <div class="grp-label">Voltage Recovery Bands (V)</div>
      <div class="two">
        <div class="col">
          <div class="cap">Load Increase</div>
          <div class="field col-f"><span>Upper</span><input type="number" min="0" step="1" bind:value={config.volt_recovery_upper_increase} /></div>
          <div class="field col-f"><span>Lower</span><input type="number" min="0" step="1" bind:value={config.volt_recovery_lower_increase} /></div>
        </div>
        <div class="col">
          <div class="cap">Load Decrease</div>
          <div class="field col-f"><span>Upper</span><input type="number" min="0" step="1" bind:value={config.volt_recovery_upper_decrease} /></div>
          <div class="field col-f"><span>Lower</span><input type="number" min="0" step="1" bind:value={config.volt_recovery_lower_decrease} /></div>
        </div>
      </div>
    {/if}

    {#if config.apply_asymmetric_volt_dev}
      <div class="grp-label">Voltage Max Deviation (%)</div>
      <div class="two">
        <div class="col"><div class="cap">Load Increase</div><div class="field col-f"><span>Increase</span><input type="number" min="0" step="1" bind:value={config.volt_max_dev_pct_increase} /></div></div>
        <div class="col"><div class="cap">Load Decrease</div><div class="field col-f"><span>Decrease</span><input type="number" min="0" step="1" bind:value={config.volt_max_dev_pct_decrease} /></div></div>
      </div>
    {/if}

    {#if config.apply_asymmetric_freq}
      <div class="grp-label">Frequency Recovery Bands (Hz)</div>
      <div class="two">
        <div class="col">
          <div class="cap">Load Increase</div>
          <div class="field col-f"><span>Upper</span><input type="number" min="0" step="0.05" bind:value={config.freq_recovery_upper_increase} /></div>
          <div class="field col-f"><span>Lower</span><input type="number" min="0" step="0.05" bind:value={config.freq_recovery_lower_increase} /></div>
        </div>
        <div class="col">
          <div class="cap">Load Decrease</div>
          <div class="field col-f"><span>Upper</span><input type="number" min="0" step="0.05" bind:value={config.freq_recovery_upper_decrease} /></div>
          <div class="field col-f"><span>Lower</span><input type="number" min="0" step="0.05" bind:value={config.freq_recovery_lower_decrease} /></div>
        </div>
      </div>
    {/if}

    {#if config.apply_asymmetric_freq_dev}
      <div class="grp-label">Frequency Max Deviation (%)</div>
      <div class="two">
        <div class="col"><div class="cap">Load Increase</div><div class="field col-f"><span>Increase</span><input type="number" min="0" step="1" bind:value={config.freq_max_dev_pct_increase} /></div></div>
        <div class="col"><div class="cap">Load Decrease</div><div class="field col-f"><span>Decrease</span><input type="number" min="0" step="1" bind:value={config.freq_max_dev_pct_decrease} /></div></div>
      </div>
    {/if}

    {#if config.iso_8528_5_mode}
      <div class="grp-label">β_f Start Band (Hz)</div>
      <div class="cap">Stopwatch starts when frequency leaves this tighter band; it stops on re-entry to the Frequency Recovery (α_f) band.</div>
      <div class="two">
        <div class="col">
          <div class="cap">Load Increase</div>
          <div class="field col-f"><span>Upper</span><input type="number" min="0" step="0.05" bind:value={config.freq_start_upper_increase} /></div>
          <div class="field col-f"><span>Lower</span><input type="number" min="0" step="0.05" bind:value={config.freq_start_lower_increase} /></div>
        </div>
        <div class="col">
          <div class="cap">Load Decrease</div>
          <div class="field col-f"><span>Upper</span><input type="number" min="0" step="0.05" bind:value={config.freq_start_upper_decrease} /></div>
          <div class="field col-f"><span>Lower</span><input type="number" min="0" step="0.05" bind:value={config.freq_start_lower_decrease} /></div>
        </div>
      </div>
    {/if}

    <label class="chk"><input type="checkbox" bind:checked={config.steady_state_enabled} /> Evaluate steady-state (ISO 8528-5 δ bands)</label>
    {#if config.steady_state_enabled}
      <div class="cap">Checks every sample during the stable dwell periods between load steps against the tight δU / δf bands — separate from transient recovery. For staged load-bank tests only.</div>
      <div class="two">
        <div class="col">
          <div class="field col-f"><span>δU band (±%)</span><input type="number" min="0" step="0.5" bind:value={config.steady_voltage_band_pct} /></div>
          <div class="field col-f"><span>Dwell min (s)</span><input type="number" min="1" step="5" bind:value={config.steady_dwell_min_s} /></div>
        </div>
        <div class="col">
          <div class="field col-f"><span>δf band (±%)</span><input type="number" min="0" step="0.5" bind:value={config.steady_freq_band_pct} /></div>
          <div class="field col-f"><span>Exclude (s)</span><input type="number" min="0" step="1" bind:value={config.steady_exclusion_s} /></div>
        </div>
      </div>
    {/if}

    <div class="field"><span>Rated Load (kW)</span><input type="number" min="0" step="1" placeholder="optional" bind:value={config.rated_load_kw} /></div>
    <div class="field"><span>No. Expected Load Steps</span><input type="number" min="0" step="1" placeholder="optional" bind:value={config.expected_steps} /></div>
  </section>

  <!-- ── Display Options ───────────────────────────────────────────── -->
  <section>
    <div class="sec-title">Display Options</div>

    <div class="grp-label">Nominal Voltage</div>
    <div class="chips">
      {#each VOLT_OPTS as v}
        <button class="chip" class:on={voltMode === v} onclick={() => setVoltMode(v)}>{v === 'Custom' ? 'Custom' : `${v} V`}</button>
      {/each}
    </div>
    {#if voltMode === 'Custom'}
      <input type="number" min="1" step="1" bind:value={config.nominal_voltage} placeholder="Custom V (L-L)" />
    {/if}

    <div class="grp-label">Nominal Frequency (Hz)</div>
    <input type="number" min="1" step="0.5" bind:value={config.nominal_frequency} />

    <div class="grp-label">CSV Voltage Columns</div>
    <select bind:value={config.ln_to_ll_mode}>
      <option value="auto">Auto-detect (by column names)</option>
      <option value="force_ll">Line-to-Line — use as-is</option>
      <option value="force_ln">Line-to-Neutral — convert ×√3 to L-L</option>
    </select>
  </section>

  <button class="run" onclick={onRun} disabled={loading || !fileName}>
    {loading ? 'Analyzing…' : 'Run Analysis'}
  </button>
  {#if !fileName}<div class="hint">Load a file to enable analysis.</div>{/if}
</aside>

<style>
  .sidebar {
    width: 340px;
    flex: 0 0 340px;
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
  .head .title { font-weight: 700; color: #fff; font-size: 17px; }
  .head .sub { font-size: 11px; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.08em; }
  .head .env { margin-left: auto; background: #1e293b; color: #94a3b8; font-size: 11px; padding: 2px 8px; border-radius: 999px; }
  section { display: flex; flex-direction: column; gap: 8px; border-top: 1px solid #1e293b; padding-top: 14px; }
  .sec-title { font-size: 13px; font-weight: 700; color: #fff; letter-spacing: 0.02em; margin-bottom: 2px; }
  .grp-label { font-size: 11px; text-transform: uppercase; letter-spacing: 0.06em; color: #94a3b8; margin-top: 6px; }
  input, select { background: #0b1220; border: 1px solid #1e293b; color: #e2e8f0; border-radius: 7px; padding: 7px 9px; font-size: 13px; font-family: "JetBrains Mono", monospace; width: 100%; }
  input:focus, select:focus { outline: none; border-color: var(--blue); }
  input:disabled { opacity: 0.45; }
  .field { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
  .field span { font-size: 12px; color: #cbd5e1; }
  .field input { width: 96px; flex: 0 0 96px; text-align: right; }
  .field.col-f input { width: 84px; flex: 0 0 84px; }
  .chk { display: flex; align-items: center; gap: 8px; font-size: 12px; color: #cbd5e1; }
  .chk input { width: auto; flex: 0 0 auto; }
  .two { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
  .col { display: flex; flex-direction: column; gap: 6px; }
  .cap { font-size: 11px; color: #94a3b8; }
  .chips { display: flex; gap: 6px; flex-wrap: wrap; }
  .chip { flex: 1; min-width: 56px; background: #0b1220; border: 1px solid #1e293b; color: #cbd5e1; padding: 6px; border-radius: 7px; font-size: 12px; }
  .chip.on { background: var(--blue); border-color: var(--blue); color: #fff; font-weight: 600; }
  .file-btn { background: #1e293b; color: #fff; text-align: center; padding: 9px; border-radius: 8px; font-size: 13px; font-weight: 600; cursor: pointer; }
  .filename { font-size: 11px; color: #94a3b8; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .pill { align-self: flex-start; background: #312e81; color: #c7d2fe; font-size: 11px; padding: 2px 8px; border-radius: 999px; }
  .run { background: var(--blue); color: #fff; border: none; padding: 12px; border-radius: 9px; font-size: 15px; font-weight: 700; cursor: pointer; margin-top: 4px; }
  .run:disabled { background: #334155; color: #94a3b8; cursor: not-allowed; }
  .hint { font-size: 11px; color: #64748b; text-align: center; }
</style>
