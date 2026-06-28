<script lang="ts">
  import { untrack } from 'svelte';
  import type { AnalysisConfigInput, Preset } from '../config/defaults';
  import { BUILTIN_PRESETS, VOLTAGE_PRESETS } from '../config/defaults';
  import { loadCustomPresets } from '../config/preset_store';
  import type { Caps } from '../backend/types';
  import TimeRangeSlider from './TimeRangeSlider.svelte';
  import PresetConfigurator from './PresetConfigurator.svelte';
  import InfoTip from './InfoTip.svelte';
  import { HELP } from '../config/help_text';
  import { dropzone, injectFiles } from './dropzone';

  let {
    config,
    caps,
    fileName,
    loggerFormat,
    loading,
    accept = '.csv,text/csv',
    fileLabel = 'Logger CSV',
    timeMin = null,
    timeMax = null,
    timeStart = $bindable(''),
    timeEnd = $bindable(''),
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
    timeMin?: string | null;
    timeMax?: string | null;
    timeStart?: string;
    timeEnd?: string;
    activePreset?: string;
    onRun: () => void;
    onFile: (ev: Event) => void;
  } = $props();

  // Drag-and-drop for the logger file: feed dropped files through the same hidden
  // <input> + onFile handler so validation/format-detection stays in one place.
  let csvInput = $state<HTMLInputElement | undefined>(undefined);
  let csvDragActive = $state(false);
  function onCsvDrop(files: File[]) {
    injectFiles(csvInput, files.slice(0, 1)); // single logger file
  }

  // ISO timestamps -> datetime-local input value (YYYY-MM-DDTHH:MM:SS).
  const toLocal = (iso: string | null | undefined): string => (iso ? iso.slice(0, 19) : '');
  const minLocal = $derived(toLocal(timeMin));
  const maxLocal = $derived(toLocal(timeMax));

  function resetWindow() {
    timeStart = '';
    timeEnd = '';
  }

  // Nominal-voltage preset vs custom (matches the Streamlit selectbox).
  const VOLT_OPTS = ['415', '690', '11000', 'Custom'];
  let voltMode = $state(
    untrack(() => (VOLTAGE_PRESETS.includes(config.nominal_voltage) ? String(config.nominal_voltage) : 'Custom')),
  );

  // ── Presets: built-in (read-only) + user custom (localStorage) ──
  let customPresets = $state<Preset[]>(loadCustomPresets());
  let presetMgrOpen = $state(false);

  function applyPreset(name: string) {
    activePreset = name;
    const preset: Preset | undefined = [...BUILTIN_PRESETS, ...customPresets].find((p) => p.name === name);
    if (preset) Object.assign(config, preset.values);
  }

  // If the active custom preset is deleted in the manager, drop the stale label.
  $effect(() => {
    const names = [...BUILTIN_PRESETS, ...customPresets].map((p) => p.name);
    if (activePreset !== 'None' && !names.includes(activePreset)) activePreset = 'None';
  });

  function setVoltMode(v: string) {
    voltMode = v;
    if (v !== 'Custom') config.nominal_voltage = Number(v);
  }

  // ── Resizable sidebar (drag handle on the right edge; width persisted) ──
  const SIDEBAR_WIDTH_KEY = 'pqa.sidebar.width.v1';
  const MIN_W = 260;
  const MAX_W = 680;
  const DEFAULT_W = 340;

  function loadWidth(): number {
    try {
      const raw = localStorage.getItem(SIDEBAR_WIDTH_KEY);
      if (raw) {
        const w = Number(raw);
        if (Number.isFinite(w)) return Math.max(MIN_W, Math.min(MAX_W, w));
      }
    } catch {
      /* ignore */
    }
    return DEFAULT_W;
  }
  function saveWidth(w: number) {
    try {
      localStorage.setItem(SIDEBAR_WIDTH_KEY, String(w));
    } catch {
      /* ignore */
    }
  }

  let sidebarWidth = $state(loadWidth());
  let dragging = $state(false);

  function startDrag(e: MouseEvent) {
    e.preventDefault();
    const startX = e.clientX;
    const startW = sidebarWidth;
    dragging = true;
    document.body.style.userSelect = 'none';
    document.body.style.cursor = 'col-resize';
    function move(ev: MouseEvent) {
      sidebarWidth = Math.max(MIN_W, Math.min(MAX_W, startW + (ev.clientX - startX)));
    }
    function up() {
      dragging = false;
      document.body.style.userSelect = '';
      document.body.style.cursor = '';
      saveWidth(sidebarWidth);
      window.removeEventListener('mousemove', move);
      window.removeEventListener('mouseup', up);
    }
    window.addEventListener('mousemove', move);
    window.addEventListener('mouseup', up);
  }
  function resetWidth() {
    sidebarWidth = DEFAULT_W;
    saveWidth(DEFAULT_W);
  }
  function onHandleKey(e: KeyboardEvent) {
    const STEP = 16;
    if (e.key === 'ArrowLeft') { sidebarWidth = Math.max(MIN_W, sidebarWidth - STEP); saveWidth(sidebarWidth); e.preventDefault(); }
    else if (e.key === 'ArrowRight') { sidebarWidth = Math.min(MAX_W, sidebarWidth + STEP); saveWidth(sidebarWidth); e.preventDefault(); }
    else if (e.key === 'Home') { resetWidth(); e.preventDefault(); }
  }
</script>

<aside class="sidebar" style="--sidebar-width: {sidebarWidth}px">
  <div class="sidebar-inner">
  <div class="head">
    <div class="bolt">⚡</div>
    <div>
      <div class="title">Analysis</div>
      <div class="sub">Configuration</div>
    </div>
    {#if caps}<span class="env">{caps.platform}</span>{/if}
  </div>

  <section>
    <div class="grp-label">{fileLabel} <InfoTip text={HELP.file} /></div>
    <div
      class="dropzone"
      class:drag-active={csvDragActive}
      use:dropzone={{ onDrop: onCsvDrop, onActive: (a) => (csvDragActive = a), disabled: loading }}
    >
      <label class="file-btn">
        {fileName ? 'Change file' : 'Load file'}
        <input type="file" {accept} bind:this={csvInput} onchange={onFile} hidden />
      </label>
      <div class="drop-hint">{csvDragActive ? 'Drop to load' : 'or drag & drop a file here'}</div>
    </div>
    {#if fileName}
      <div class="filename" title={fileName}>{fileName}</div>
      {#if loggerFormat}<span class="pill">{loggerFormat}</span>{/if}
    {/if}
  </section>

  <!-- ── Time Window ───────────────────────────────────────────────── -->
  {#if minLocal && maxLocal}
    <section>
      <div class="sec-title">Time Window</div>
      <div class="cap">Drag the handles to restrict analysis to a window within the file.</div>
      <TimeRangeSlider min={minLocal} max={maxLocal} bind:start={timeStart} bind:end={timeEnd} />
      <details class="exact">
        <summary>Exact times</summary>
        <label class="grp-label" for="tw-start">Start <InfoTip text={HELP.time_start} /></label>
        <input id="tw-start" type="datetime-local" step="1" min={minLocal} max={maxLocal} bind:value={timeStart} />
        <label class="grp-label" for="tw-end">End <InfoTip text={HELP.time_end} /></label>
        <input id="tw-end" type="datetime-local" step="1" min={minLocal} max={maxLocal} bind:value={timeEnd} />
      </details>
      {#if timeStart || timeEnd}
        <button class="reset-win" onclick={resetWindow}>↺ Reset to full file</button>
      {/if}
    </section>
  {/if}

  <!-- ── Acceptance Criteria ───────────────────────────────────────── -->
  <section>
    <div class="sec-title">Acceptance Criteria</div>

    <label class="grp-label" for="preset">Active Preset <InfoTip text={HELP.active_preset} /></label>
    <select id="preset" value={activePreset} onchange={(e) => applyPreset((e.target as HTMLSelectElement).value)}>
      <option value="None">None</option>
      <optgroup label="Built-in">
        {#each BUILTIN_PRESETS as p}<option value={p.name}>{p.name}</option>{/each}
      </optgroup>
      {#if customPresets.length}
        <optgroup label="Custom">
          {#each customPresets as p}<option value={p.name}>{p.name}</option>{/each}
        </optgroup>
      {/if}
    </select>
    <button class="manage-presets" onclick={() => (presetMgrOpen = true)}>⚙ Manage presets</button>

    <label class="chk"><input type="checkbox" bind:checked={config.show_limits} /> Show Limits on Graphs <InfoTip text={HELP.show_limits} /></label>

    <div class="grp-label">Snapshot Display Options <InfoTip text={HELP.snapshot_display} /></div>
    <label class="chk"><input type="checkbox" bind:checked={config.show_tolerance_band} /> Show Tolerance Band on Snapshots <InfoTip text={HELP.show_tolerance_band} /></label>
    <label class="chk"><input type="checkbox" bind:checked={config.show_deviation_limits} /> Show Deviation Limits on Snapshots <InfoTip text={HELP.show_deviation_limits} /></label>
    <label class="chk"><input type="checkbox" bind:checked={config.show_intersections} /> Show Intersection Points <InfoTip text={HELP.show_intersections} /></label>
    <label class="chk"><input type="checkbox" bind:checked={config.show_max_deviation} /> Show Max Deviation <InfoTip text={HELP.show_max_deviation} /></label>

    <div class="field"><span>Detection Window (s) <InfoTip text={HELP.detection_window_s} /></span><input type="number" min="1" max="30" step="1" bind:value={config.detection_window_s} /></div>
    <div class="field"><span>Snapshot Window (s) <InfoTip text={HELP.snapshot_window_s} /></span><input type="number" min="3" max="60" step="1" bind:value={config.snapshot_window_s} /></div>
    <div class="field"><span>Recovery Verify Window (s) <InfoTip text={HELP.recovery_verify_s} /></span><input type="number" min="1" max="30" step="1" bind:value={config.recovery_verify_s} /></div>
    <div class="field"><span>Fault Recovery Threshold (s) <InfoTip text={HELP.fault_recovery_threshold_s} /></span><input type="number" min="1" max="120" step="1" bind:value={config.fault_recovery_threshold_s} /></div>
    <div class="field"><span>Load Threshold (kW) <InfoTip text={HELP.load_threshold_kw} /></span><input type="number" min="0" step="10" bind:value={config.load_threshold_kw} /></div>

    <label class="chk"><input type="checkbox" bind:checked={config.apply_asymmetric_volt} /> Apply asymmetric Voltage tolerance band <InfoTip text={HELP.apply_asymmetric_volt} /></label>
    <label class="chk"><input type="checkbox" bind:checked={config.apply_asymmetric_volt_dev} /> Apply asymmetric Voltage deviation limit <InfoTip text={HELP.apply_asymmetric_volt_dev} /></label>
    <label class="chk"><input type="checkbox" bind:checked={config.apply_asymmetric_freq} /> Apply asymmetric Frequency tolerance band <InfoTip text={HELP.apply_asymmetric_freq} /></label>
    <label class="chk"><input type="checkbox" bind:checked={config.apply_asymmetric_freq_dev} /> Apply asymmetric Frequency deviation limit <InfoTip text={HELP.apply_asymmetric_freq_dev} /></label>
    <label class="chk"><input type="checkbox" bind:checked={config.iso_8528_5_mode} /> Apply ISO dual frequency bands <InfoTip text={HELP.iso_8528_5_mode} /></label>

    <div class="two">
      <div class="col">
        <div class="field col-f"><span>Voltage Tolerance (%) <InfoTip text={HELP.voltage_tolerance_pct} /></span><input type="number" min="0" step="0.5" bind:value={config.voltage_tolerance_pct} disabled={config.apply_asymmetric_volt} /></div>
        <div class="field col-f"><span>Voltage Recovery (s) <InfoTip text={HELP.voltage_recovery_time_s} /></span><input type="number" min="0" step="0.5" bind:value={config.voltage_recovery_time_s} /></div>
        <div class="field col-f"><span>Max Voltage Dev (%) <InfoTip text={HELP.voltage_max_deviation_pct} /></span><input type="number" min="0" step="1" bind:value={config.voltage_max_deviation_pct} disabled={config.apply_asymmetric_volt_dev} /></div>
      </div>
      <div class="col">
        <div class="field col-f"><span>Frequency Tolerance (%) <InfoTip text={HELP.frequency_tolerance_pct} /></span><input type="number" min="0" step="0.1" bind:value={config.frequency_tolerance_pct} disabled={config.apply_asymmetric_freq} /></div>
        <div class="field col-f"><span>Frequency Recovery (s) <InfoTip text={HELP.frequency_recovery_time_s} /></span><input type="number" min="0" step="0.5" bind:value={config.frequency_recovery_time_s} /></div>
        <div class="field col-f"><span>Max Frequency Dev (%) <InfoTip text={HELP.frequency_max_deviation_pct} /></span><input type="number" min="0" step="1" bind:value={config.frequency_max_deviation_pct} disabled={config.apply_asymmetric_freq_dev} /></div>
      </div>
    </div>

    {#if config.apply_asymmetric_volt}
      <div class="grp-label">Voltage Recovery Bands (V)</div>
      <div class="two">
        <div class="col">
          <div class="cap">Load Increase</div>
          <div class="field col-f"><span>Upper <InfoTip text={HELP.volt_recovery_upper_increase} /></span><input type="number" min="0" step="1" bind:value={config.volt_recovery_upper_increase} /></div>
          <div class="field col-f"><span>Lower <InfoTip text={HELP.volt_recovery_lower_increase} /></span><input type="number" min="0" step="1" bind:value={config.volt_recovery_lower_increase} /></div>
        </div>
        <div class="col">
          <div class="cap">Load Decrease</div>
          <div class="field col-f"><span>Upper <InfoTip text={HELP.volt_recovery_upper_decrease} /></span><input type="number" min="0" step="1" bind:value={config.volt_recovery_upper_decrease} /></div>
          <div class="field col-f"><span>Lower <InfoTip text={HELP.volt_recovery_lower_decrease} /></span><input type="number" min="0" step="1" bind:value={config.volt_recovery_lower_decrease} /></div>
        </div>
      </div>
    {/if}

    {#if config.apply_asymmetric_volt_dev}
      <div class="grp-label">Voltage Max Deviation (%)</div>
      <div class="two">
        <div class="col"><div class="cap">Load Increase</div><div class="field col-f"><span>Increase <InfoTip text={HELP.volt_max_dev_pct_increase} /></span><input type="number" min="0" step="1" bind:value={config.volt_max_dev_pct_increase} /></div></div>
        <div class="col"><div class="cap">Load Decrease</div><div class="field col-f"><span>Decrease <InfoTip text={HELP.volt_max_dev_pct_decrease} /></span><input type="number" min="0" step="1" bind:value={config.volt_max_dev_pct_decrease} /></div></div>
      </div>
    {/if}

    {#if config.apply_asymmetric_freq}
      <div class="grp-label">Frequency Recovery Bands (Hz)</div>
      <div class="two">
        <div class="col">
          <div class="cap">Load Increase</div>
          <div class="field col-f"><span>Upper <InfoTip text={HELP.freq_recovery_upper_increase} /></span><input type="number" min="0" step="0.05" bind:value={config.freq_recovery_upper_increase} /></div>
          <div class="field col-f"><span>Lower <InfoTip text={HELP.freq_recovery_lower_increase} /></span><input type="number" min="0" step="0.05" bind:value={config.freq_recovery_lower_increase} /></div>
        </div>
        <div class="col">
          <div class="cap">Load Decrease</div>
          <div class="field col-f"><span>Upper <InfoTip text={HELP.freq_recovery_upper_decrease} /></span><input type="number" min="0" step="0.05" bind:value={config.freq_recovery_upper_decrease} /></div>
          <div class="field col-f"><span>Lower <InfoTip text={HELP.freq_recovery_lower_decrease} /></span><input type="number" min="0" step="0.05" bind:value={config.freq_recovery_lower_decrease} /></div>
        </div>
      </div>
    {/if}

    {#if config.apply_asymmetric_freq_dev}
      <div class="grp-label">Frequency Max Deviation (%)</div>
      <div class="two">
        <div class="col"><div class="cap">Load Increase</div><div class="field col-f"><span>Increase <InfoTip text={HELP.freq_max_dev_pct_increase} /></span><input type="number" min="0" step="1" bind:value={config.freq_max_dev_pct_increase} /></div></div>
        <div class="col"><div class="cap">Load Decrease</div><div class="field col-f"><span>Decrease <InfoTip text={HELP.freq_max_dev_pct_decrease} /></span><input type="number" min="0" step="1" bind:value={config.freq_max_dev_pct_decrease} /></div></div>
      </div>
    {/if}

    {#if config.iso_8528_5_mode}
      <div class="grp-label">ISO 8528-5 Dual Frequency Bands <InfoTip text={HELP.band_mode} /></div>
      <div class="cap">β_f start band: stopwatch starts when freq leaves this band. α_f stop band: stopwatch stops on re-entry (overrides the frequency recovery band above).</div>
      <div class="chips" style="margin-bottom:4px">
        <button class="chip" class:on={config.band_mode === 'pct'} onclick={() => (config.band_mode = 'pct')}>% of Nominal</button>
        <button class="chip" class:on={config.band_mode === 'abs'} onclick={() => (config.band_mode = 'abs')}>Absolute Hz</button>
      </div>
      {#if config.band_mode === 'pct'}
        <div class="two">
          <div class="col">
            <div class="field col-f"><span>β_f band width (%) <InfoTip text={HELP.beta_f_pct} /></span><input type="number" min="0" step="0.1" bind:value={config.beta_f_pct} /></div>
          </div>
          <div class="col">
            <div class="field col-f"><span>α_f band width (%) <InfoTip text={HELP.alpha_f_pct} /></span><input type="number" min="0" step="0.1" bind:value={config.alpha_f_pct} /></div>
          </div>
        </div>
        <div class="cap iso-hint">
          β_f: ±{((config.beta_f_pct / 2) / 100 * config.nominal_frequency).toFixed(3)} Hz →
          {(config.nominal_frequency - (config.beta_f_pct / 2) / 100 * config.nominal_frequency).toFixed(3)}–{(config.nominal_frequency + (config.beta_f_pct / 2) / 100 * config.nominal_frequency).toFixed(3)} Hz<br>
          α_f: ±{((config.alpha_f_pct / 2) / 100 * config.nominal_frequency).toFixed(3)} Hz →
          {(config.nominal_frequency - (config.alpha_f_pct / 2) / 100 * config.nominal_frequency).toFixed(3)}–{(config.nominal_frequency + (config.alpha_f_pct / 2) / 100 * config.nominal_frequency).toFixed(3)} Hz
        </div>
      {:else}
        <div class="grp-label" style="font-size:11px">β_f Start Band (Hz)</div>
        <div class="two">
          <div class="col">
            <div class="cap">Load Increase</div>
            <div class="field col-f"><span>Upper <InfoTip text={HELP.freq_start_upper} /></span><input type="number" min="0" step="0.05" bind:value={config.freq_start_upper_increase} /></div>
            <div class="field col-f"><span>Lower <InfoTip text={HELP.freq_start_lower} /></span><input type="number" min="0" step="0.05" bind:value={config.freq_start_lower_increase} /></div>
          </div>
          <div class="col">
            <div class="cap">Load Decrease</div>
            <div class="field col-f"><span>Upper <InfoTip text={HELP.freq_start_upper} /></span><input type="number" min="0" step="0.05" bind:value={config.freq_start_upper_decrease} /></div>
            <div class="field col-f"><span>Lower <InfoTip text={HELP.freq_start_lower} /></span><input type="number" min="0" step="0.05" bind:value={config.freq_start_lower_decrease} /></div>
          </div>
        </div>
        <div class="grp-label" style="font-size:11px">α_f Stop Band / Recovery Band (Hz)</div>
        <div class="two">
          <div class="col">
            <div class="cap">Both Directions</div>
            <div class="field col-f"><span>Upper <InfoTip text={HELP.f_stop_upper} /></span><input type="number" min="0" step="0.05" bind:value={config.f_stop_upper} /></div>
            <div class="field col-f"><span>Lower <InfoTip text={HELP.f_stop_lower} /></span><input type="number" min="0" step="0.05" bind:value={config.f_stop_lower} /></div>
          </div>
        </div>
      {/if}
    {/if}

    <label class="chk"><input type="checkbox" bind:checked={config.steady_state_enabled} /> Evaluate steady-state (ISO 8528-5 δ bands) <InfoTip text={HELP.steady_state_enabled} /></label>
    {#if config.steady_state_enabled}
      <div class="cap">Checks the stable dwell periods between load steps. For staged load-bank tests only.</div>

      <div class="grp-label">Performance class (Table 4) <InfoTip text={HELP.steady_performance_class} /></div>
      <div class="chips" style="margin-bottom:4px">
        <button class="chip" class:on={config.steady_performance_class === null} onclick={() => (config.steady_performance_class = null)}>None</button>
        <button class="chip" class:on={config.steady_performance_class === 'G1'} onclick={() => (config.steady_performance_class = 'G1')}>G1</button>
        <button class="chip" class:on={config.steady_performance_class === 'G2'} onclick={() => (config.steady_performance_class = 'G2')}>G2</button>
        <button class="chip" class:on={config.steady_performance_class === 'G3'} onclick={() => (config.steady_performance_class = 'G3')}>G3</button>
      </div>
      {#if config.steady_performance_class === null}
        <div class="cap">Free-form mode: every sample is checked against the δU / δf bands below.</div>
      {:else}
        <div class="cap">ISO 8528-5 grading: frequency on β_f (peak-to-peak) and voltage on ΔU_st (regulation), against the {config.steady_performance_class} Table 4 limits. The δU / δf bands below drive the time-series overlay only.</div>
        <label class="chk"><input type="checkbox" bind:checked={config.steady_isochronous} /> Isochronous set (droop → 0%) <InfoTip text={HELP.steady_isochronous} /></label>
        <label class="chk"><input type="checkbox" bind:checked={config.steady_parallel_operation} /> Parallel operation (unbalance 0.5%) <InfoTip text={HELP.steady_parallel_operation} /></label>
      {/if}

      <div class="two">
        <div class="col">
          <div class="field col-f"><span>δU band (±%) <InfoTip text={HELP.steady_voltage_band_pct} /></span><input type="number" min="0" step="0.5" bind:value={config.steady_voltage_band_pct} /></div>
          <div class="field col-f"><span>Dwell min (s) <InfoTip text={HELP.steady_dwell_min_s} /></span><input type="number" min="1" step="5" bind:value={config.steady_dwell_min_s} /></div>
        </div>
        <div class="col">
          <div class="field col-f"><span>δf band (±%) <InfoTip text={HELP.steady_freq_band_pct} /></span><input type="number" min="0" step="0.5" bind:value={config.steady_freq_band_pct} /></div>
          <div class="field col-f"><span>Exclude (s) <InfoTip text={HELP.steady_exclusion_s} /></span><input type="number" min="0" step="1" bind:value={config.steady_exclusion_s} /></div>
        </div>
      </div>
    {/if}

    <div class="field"><span>Rated Load (kW) <InfoTip text={HELP.rated_load_kw} /></span><input type="number" min="0" step="1" placeholder="optional" bind:value={config.rated_load_kw} /></div>
    <div class="field"><span>No. Expected Load Steps <InfoTip text={HELP.expected_steps} /></span><input type="number" min="0" step="1" placeholder="optional" bind:value={config.expected_steps} /></div>
  </section>

  <!-- ── Display Options ───────────────────────────────────────────── -->
  <section>
    <div class="sec-title">Display Options</div>

    <div class="grp-label">Nominal Voltage <InfoTip text={HELP.nominal_voltage} /></div>
    <div class="chips">
      {#each VOLT_OPTS as v}
        <button class="chip" class:on={voltMode === v} onclick={() => setVoltMode(v)}>{v === 'Custom' ? 'Custom' : `${v} V`}</button>
      {/each}
    </div>
    {#if voltMode === 'Custom'}
      <input type="number" min="1" step="1" bind:value={config.nominal_voltage} placeholder="Custom V (L-L)" />
    {/if}

    <div class="grp-label">Nominal Frequency (Hz) <InfoTip text={HELP.nominal_frequency} /></div>
    <input type="number" min="1" step="0.5" bind:value={config.nominal_frequency} />

    <div class="grp-label">CSV Voltage Columns <InfoTip text={HELP.ln_to_ll_mode} /></div>
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
  </div>
  <button
    type="button"
    class="resize-handle"
    class:active={dragging}
    aria-label="Resize sidebar — drag, arrow keys to adjust, double-click to reset"
    title="Drag to resize · double-click to reset"
    onmousedown={startDrag}
    ondblclick={resetWidth}
    onkeydown={onHandleKey}
  ></button>
</aside>

{#if presetMgrOpen}
  <PresetConfigurator {config} bind:presets={customPresets} onApply={applyPreset} onClose={() => (presetMgrOpen = false)} />
{/if}

<style>
  .sidebar {
    width: var(--sidebar-width, 340px);
    flex: 0 0 var(--sidebar-width, 340px);
    height: 100%;
    position: relative;
    display: flex;
    background: var(--navy);
  }
  .sidebar-inner {
    flex: 1;
    min-width: 0;
    color: #cbd5e1;
    padding: 18px 16px 28px;
    display: flex;
    flex-direction: column;
    gap: 16px;
    overflow-y: auto;
  }
  .resize-handle {
    position: absolute;
    top: 0; right: 0; bottom: 0;
    width: 6px;
    cursor: col-resize;
    background: transparent;
    border: none;
    padding: 0;
    appearance: none;
    transition: background 0.15s;
    z-index: 5;
  }
  .resize-handle:hover, .resize-handle.active { background: var(--blue); }
  .resize-handle:focus-visible { outline: 2px solid var(--blue); outline-offset: -2px; }
  .manage-presets {
    background: #1e293b;
    color: #cbd5e1;
    border: 1px solid #334155;
    border-radius: 7px;
    padding: 7px;
    font-size: 12px;
    cursor: pointer;
    margin-top: 2px;
  }
  .manage-presets:hover { border-color: var(--blue); color: #fff; }
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
  .iso-hint { line-height: 1.6; font-family: "JetBrains Mono", monospace; font-size: 10.5px; background: #0b1220; border: 1px solid #1e293b; border-radius: 6px; padding: 4px 8px; margin-top: 4px; }
  .chips { display: flex; gap: 6px; flex-wrap: wrap; }
  .chip { flex: 1; min-width: 56px; background: #0b1220; border: 1px solid #1e293b; color: #cbd5e1; padding: 6px; border-radius: 7px; font-size: 12px; }
  .chip.on { background: var(--blue); border-color: var(--blue); color: #fff; font-weight: 600; }
  .file-btn { background: #1e293b; color: #fff; text-align: center; padding: 9px; border-radius: 8px; font-size: 13px; font-weight: 600; cursor: pointer; display: block; }
  .file-btn:hover { background: #334155; }
  .dropzone { display: flex; flex-direction: column; gap: 5px; border: 1.5px dashed transparent; border-radius: 10px; padding: 5px; transition: border-color 120ms, background 120ms; }
  .dropzone.drag-active { border-color: var(--blue); background: rgba(37, 99, 235, 0.14); }
  .dropzone.drag-active .file-btn { background: var(--blue); }
  .drop-hint { text-align: center; font-size: 10.5px; color: #94a3b8; letter-spacing: 0.01em; }
  .filename { font-size: 11px; color: #94a3b8; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .pill { align-self: flex-start; background: #312e81; color: #c7d2fe; font-size: 11px; padding: 2px 8px; border-radius: 999px; }
  .run { background: var(--blue); color: #fff; border: none; padding: 12px; border-radius: 9px; font-size: 15px; font-weight: 700; cursor: pointer; margin-top: 4px; }
  .run:disabled { background: #334155; color: #94a3b8; cursor: not-allowed; }
  .hint { font-size: 11px; color: #64748b; text-align: center; }
  .reset-win { background: #1e293b; color: #cbd5e1; border: 1px solid #334155; border-radius: 7px; padding: 6px; font-size: 12px; cursor: pointer; margin-top: 2px; }
  .reset-win:hover { border-color: var(--blue); color: #fff; }
  .exact { margin-top: 2px; }
  .exact summary { font-size: 11px; color: #94a3b8; cursor: pointer; user-select: none; list-style: revert; }
  .exact summary:hover { color: #cbd5e1; }
  .exact[open] { display: flex; flex-direction: column; gap: 8px; }
</style>
