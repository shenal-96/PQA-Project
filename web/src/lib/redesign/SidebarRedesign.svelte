<script lang="ts">
  import { onMount, untrack } from 'svelte';
  import type { AnalysisConfigInput, Preset } from '../../config/defaults';
  import { BUILTIN_PRESETS, VOLTAGE_PRESETS } from '../../config/defaults';
  import { loadPresets, persistPresets, capturePreset, PRESET_FIELDS } from '../../config/preset_store';
  import type { AnalysisBackend } from '../../backend';
  import type { Caps } from '../../backend/types';
  import TimeRangeSlider from '../TimeRangeSlider.svelte';
  import PresetConfigurator from '../PresetConfigurator.svelte';
  import InfoTip from '../InfoTip.svelte';
  import { HELP } from '../../config/help_text';
  import { dropzone, injectFiles } from '../dropzone';
  import Section from './Section.svelte';
  import Toggle from './Toggle.svelte';
  import Icon from './Icon.svelte';

  // Dark redesign of the configuration sidebar. The SCRIPT is identical to the
  // classic Sidebar.svelte — same props, same preset/voltage/resize logic — and
  // every control below binds to the exact same `config` field, so analysis is
  // byte-identical between themes (docs/redesign/PLAN.md §6, wiring parity).
  let {
    config,
    caps,
    backend,
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
    backend: AnalysisBackend | undefined;
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

  let csvInput = $state<HTMLInputElement | undefined>(undefined);
  let csvDragActive = $state(false);
  function onCsvDrop(files: File[]) {
    injectFiles(csvInput, files.slice(0, 1));
  }

  const toLocal = (iso: string | null | undefined): string => (iso ? iso.slice(0, 19) : '');
  const minLocal = $derived(toLocal(timeMin));
  const maxLocal = $derived(toLocal(timeMax));

  function resetWindow() {
    timeStart = '';
    timeEnd = '';
  }

  const VOLT_OPTS = ['415', '690', '11000', 'Custom'];
  let voltMode = $state(
    untrack(() => (VOLTAGE_PRESETS.includes(config.nominal_voltage) ? String(config.nominal_voltage) : 'Custom')),
  );

  let customPresets = $state<Preset[]>([]);
  let presetMgrOpen = $state(false);

  onMount(async () => {
    customPresets = await loadPresets(backend);
  });

  function applyPreset(name: string) {
    activePreset = name;
    const preset: Preset | undefined = [...BUILTIN_PRESETS, ...customPresets].find((p) => p.name === name);
    if (preset) Object.assign(config, preset.values);
  }

  $effect(() => {
    const names = [...BUILTIN_PRESETS, ...customPresets].map((p) => p.name);
    if (activePreset !== 'None' && !names.includes(activePreset)) activePreset = 'None';
  });

  const activePresetObj = $derived(
    activePreset === 'None'
      ? undefined
      : [...BUILTIN_PRESETS, ...customPresets].find((p) => p.name === activePreset),
  );
  const activeIsCustom = $derived(!!activePresetObj && customPresets.some((p) => p.name === activePreset));
  const presetModified = $derived.by(() => {
    const v = activePresetObj?.values as Record<string, unknown> | undefined;
    if (!v) return false;
    return PRESET_FIELDS.some((k) => k in v && config[k] !== v[k]);
  });

  async function updateActivePreset() {
    if (!activeIsCustom) return;
    const updated = capturePreset(activePreset, config);
    customPresets = customPresets.map((p) => (p.name === activePreset ? updated : p));
    await persistPresets(customPresets, backend);
  }

  function setVoltMode(v: string) {
    voltMode = v;
    if (v !== 'Custom') config.nominal_voltage = Number(v);
  }

  const statusLabel = $derived(
    [activePreset !== 'None' ? activePreset : null, loggerFormat ?? caps?.platform ?? null]
      .filter(Boolean)
      .join(' · '),
  );

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

<aside class="rd-sidebar" style="--sidebar-width: {sidebarWidth}px">
  <div class="rd-sidebar-inner">
    <!-- sticky header -->
    <div class="rd-head">
      <span class="rd-head-bar"></span>
      <span class="rd-head-title">Configuration</span>
      {#if statusLabel}<span class="rd-head-status mono">{statusLabel}</span>{/if}
    </div>

    <div class="rd-scroll">
      <!-- ── Data Source ─────────────────────────────────────────── -->
      <div class="rd-ds-wrap">
        <div class="rd-ds-label">{fileLabel} <InfoTip text={HELP.file} /></div>
        <div
          class="rd-ds-card"
          class:drag-active={csvDragActive}
          use:dropzone={{ onDrop: onCsvDrop, onActive: (a) => (csvDragActive = a), disabled: loading }}
        >
          {#if fileName}
            <div class="rd-ds-row">
              <span class="rd-ds-icon"><Icon name="file" /></span>
              <div class="rd-ds-meta">
                <div class="rd-ds-name" title={fileName}>{fileName}</div>
                {#if loggerFormat}<span class="rd-ds-pill">{loggerFormat}</span>{/if}
              </div>
            </div>
            <label class="rd-ds-change">
              <span class="rd-ds-swap"><Icon name="swap" /></span> Change file
              <input type="file" {accept} bind:this={csvInput} onchange={onFile} hidden />
            </label>
          {:else}
            <label class="rd-ds-load">
              Load file
              <input type="file" {accept} bind:this={csvInput} onchange={onFile} hidden />
            </label>
            <div class="rd-ds-hint">{csvDragActive ? 'Drop to load' : 'or drag & drop a file here'}</div>
          {/if}
        </div>
      </div>

      <!-- ── Time Window ─────────────────────────────────────────── -->
      {#if minLocal && maxLocal}
        <Section title="Time Window">
          <TimeRangeSlider min={minLocal} max={maxLocal} bind:start={timeStart} bind:end={timeEnd} />
          <details class="rd-exact">
            <summary>Exact times</summary>
            <label class="rd-glabel" for="rd-tw-start">Start <InfoTip text={HELP.time_start} /></label>
            <input id="rd-tw-start" class="rd-input" type="datetime-local" step="1" min={minLocal} max={maxLocal} bind:value={timeStart} />
            <label class="rd-glabel" for="rd-tw-end">End <InfoTip text={HELP.time_end} /></label>
            <input id="rd-tw-end" class="rd-input" type="datetime-local" step="1" min={minLocal} max={maxLocal} bind:value={timeEnd} />
          </details>
          {#if timeStart || timeEnd}
            <button class="rd-reset-win" onclick={resetWindow}><Icon name="reset" /> Reset to full file</button>
          {/if}
        </Section>
      {/if}

      <!-- ── Acceptance Preset ───────────────────────────────────── -->
      <Section title="Acceptance Preset">
        <select class="rd-input rd-select" value={activePreset} onchange={(e) => applyPreset((e.target as HTMLSelectElement).value)}>
          <option value="None">None — custom criteria</option>
          <optgroup label="Built-in">
            {#each BUILTIN_PRESETS as p}<option value={p.name}>{p.name}</option>{/each}
          </optgroup>
          {#if customPresets.length}
            <optgroup label="Custom">
              {#each customPresets as p}<option value={p.name}>{p.name}</option>{/each}
            </optgroup>
          {/if}
        </select>
        <button class="rd-ghost" onclick={() => (presetMgrOpen = true)}>⚙ Manage presets</button>
        <div class="rd-note">
          Selecting a preset fills the detection and tolerance values below.
          <span class="rd-amber">Editing any value switches to custom.</span>
        </div>
        {#if activePreset !== 'None' && presetModified}
          <div class="rd-modified">
            <span class="rd-mod-note"><span class="rd-mod-dot">●</span> Modified from “{activePreset}”</span>
            <div class="rd-mod-actions">
              {#if activeIsCustom}<button class="rd-mod-btn primary" onclick={updateActivePreset}>Update</button>{/if}
              <button class="rd-mod-btn" onclick={() => (presetMgrOpen = true)}>Save as new</button>
            </div>
          </div>
        {/if}
      </Section>

      <!-- ── Detection ───────────────────────────────────────────── -->
      <Section title="Detection" count="5">
        <div class="rd-field"><span>Detection window (s) <InfoTip text={HELP.detection_window_s} /></span><input class="rd-num" type="number" min="1" max="30" step="1" bind:value={config.detection_window_s} /></div>
        <div class="rd-field"><span>Snapshot window (s) <InfoTip text={HELP.snapshot_window_s} /></span><input class="rd-num" type="number" min="3" max="60" step="1" bind:value={config.snapshot_window_s} /></div>
        <div class="rd-field"><span>Recovery verify (s) <InfoTip text={HELP.recovery_verify_s} /></span><input class="rd-num" type="number" min="1" max="30" step="1" bind:value={config.recovery_verify_s} /></div>
        <div class="rd-field"><span>Fault recovery (s) <InfoTip text={HELP.fault_recovery_threshold_s} /></span><input class="rd-num" type="number" min="1" max="120" step="1" bind:value={config.fault_recovery_threshold_s} /></div>
        <div class="rd-field"><span>Load threshold (kW) <InfoTip text={HELP.load_threshold_kw} /></span><input class="rd-num" type="number" min="0" step="10" bind:value={config.load_threshold_kw} /></div>
      </Section>

      <!-- ── Tolerances matrix ───────────────────────────────────── -->
      <Section title="Tolerances" accent="var(--cyan)">
        <div class="rd-tol">
          <div></div>
          <div class="rd-tol-hd">Voltage</div>
          <div class="rd-tol-hd">Freq</div>

          <div class="rd-tol-row">Tolerance % <InfoTip text={HELP.voltage_tolerance_pct} /></div>
          <input class="rd-num rd-tol-cell" type="number" min="0" step="0.5" bind:value={config.voltage_tolerance_pct} disabled={config.apply_asymmetric_volt} />
          <input class="rd-num rd-tol-cell" type="number" min="0" step="0.1" bind:value={config.frequency_tolerance_pct} disabled={config.apply_asymmetric_freq} />

          <div class="rd-tol-row">Recovery s <InfoTip text={HELP.voltage_recovery_time_s} /></div>
          <input class="rd-num rd-tol-cell" type="number" min="0" step="0.5" bind:value={config.voltage_recovery_time_s} />
          <input class="rd-num rd-tol-cell" type="number" min="0" step="0.5" bind:value={config.frequency_recovery_time_s} />

          <div class="rd-tol-row">Max dev % <InfoTip text={HELP.voltage_max_deviation_pct} /></div>
          <input class="rd-num rd-tol-cell" type="number" min="0" step="1" bind:value={config.voltage_max_deviation_pct} disabled={config.apply_asymmetric_volt_dev} />
          <input class="rd-num rd-tol-cell" type="number" min="0" step="1" bind:value={config.frequency_max_deviation_pct} disabled={config.apply_asymmetric_freq_dev} />
        </div>
        <div class="rd-note">Asymmetric/per-direction bands live under <b>Advanced</b> below.</div>
      </Section>

      <!-- ── Display Options ─────────────────────────────────────── -->
      <Section title="Display Options" open={false}>
        <Toggle bind:checked={config.show_limits} label="Show limits on graphs" tip={HELP.show_limits} />
        <div class="rd-divider"></div>
        <Toggle bind:checked={config.show_data_points} label="Display data points on snapshots" tip={HELP.show_data_points} />
        {#if config.show_data_points}
          <div class="rd-subhd">On snapshots</div>
          <Toggle bind:checked={config.show_tolerance_band} label="Tolerance band" tip={HELP.show_tolerance_band} nested />
          <Toggle bind:checked={config.show_deviation_limits} label="Deviation limits" tip={HELP.show_deviation_limits} nested />
          <Toggle bind:checked={config.show_intersections} label="Intersection points" tip={HELP.show_intersections} nested />
          <Toggle bind:checked={config.show_max_deviation} label="Max deviation" tip={HELP.show_max_deviation} nested />
        {/if}
      </Section>

      <!-- ── Advanced (asymmetric + ISO dual + steady-state) ─────── -->
      <Section title="Advanced" open={false}>
        <div class="rd-subhd">Asymmetric limits <InfoTip text={HELP.enable_asymmetric_limits} /></div>
        <Toggle bind:checked={config.apply_asymmetric_volt} label="Asymmetric voltage tolerance band" tip={HELP.apply_asymmetric_volt} />
        <Toggle bind:checked={config.apply_asymmetric_volt_dev} label="Asymmetric voltage deviation limit" tip={HELP.apply_asymmetric_volt_dev} />
        <Toggle bind:checked={config.apply_asymmetric_freq} label="Asymmetric frequency tolerance band" tip={HELP.apply_asymmetric_freq} />
        <Toggle bind:checked={config.apply_asymmetric_freq_dev} label="Asymmetric frequency deviation limit" tip={HELP.apply_asymmetric_freq_dev} />
        <Toggle bind:checked={config.iso_8528_5_mode} label="ISO dual frequency bands" tip={HELP.iso_8528_5_mode} />

        {#if config.apply_asymmetric_volt}
          <div class="rd-glabel">Voltage Recovery Bands (V)</div>
          <div class="rd-two">
            <div class="rd-col">
              <div class="rd-cap">Load Increase</div>
              <div class="rd-field col-f"><span>Upper <InfoTip text={HELP.volt_recovery_upper_increase} /></span><input class="rd-num" type="number" min="0" step="1" bind:value={config.volt_recovery_upper_increase} /></div>
              <div class="rd-field col-f"><span>Lower <InfoTip text={HELP.volt_recovery_lower_increase} /></span><input class="rd-num" type="number" min="0" step="1" bind:value={config.volt_recovery_lower_increase} /></div>
            </div>
            <div class="rd-col">
              <div class="rd-cap">Load Decrease</div>
              <div class="rd-field col-f"><span>Upper <InfoTip text={HELP.volt_recovery_upper_decrease} /></span><input class="rd-num" type="number" min="0" step="1" bind:value={config.volt_recovery_upper_decrease} /></div>
              <div class="rd-field col-f"><span>Lower <InfoTip text={HELP.volt_recovery_lower_decrease} /></span><input class="rd-num" type="number" min="0" step="1" bind:value={config.volt_recovery_lower_decrease} /></div>
            </div>
          </div>
        {/if}

        {#if config.apply_asymmetric_volt_dev}
          <div class="rd-glabel">Voltage Max Deviation (%)</div>
          <div class="rd-two">
            <div class="rd-col"><div class="rd-cap">Load Increase</div><div class="rd-field col-f"><span>Increase <InfoTip text={HELP.volt_max_dev_pct_increase} /></span><input class="rd-num" type="number" min="0" step="1" bind:value={config.volt_max_dev_pct_increase} /></div></div>
            <div class="rd-col"><div class="rd-cap">Load Decrease</div><div class="rd-field col-f"><span>Decrease <InfoTip text={HELP.volt_max_dev_pct_decrease} /></span><input class="rd-num" type="number" min="0" step="1" bind:value={config.volt_max_dev_pct_decrease} /></div></div>
          </div>
        {/if}

        {#if config.apply_asymmetric_freq}
          <div class="rd-glabel">Frequency Recovery Bands (Hz)</div>
          <div class="rd-two">
            <div class="rd-col">
              <div class="rd-cap">Load Increase</div>
              <div class="rd-field col-f"><span>Upper <InfoTip text={HELP.freq_recovery_upper_increase} /></span><input class="rd-num" type="number" min="0" step="0.05" bind:value={config.freq_recovery_upper_increase} /></div>
              <div class="rd-field col-f"><span>Lower <InfoTip text={HELP.freq_recovery_lower_increase} /></span><input class="rd-num" type="number" min="0" step="0.05" bind:value={config.freq_recovery_lower_increase} /></div>
            </div>
            <div class="rd-col">
              <div class="rd-cap">Load Decrease</div>
              <div class="rd-field col-f"><span>Upper <InfoTip text={HELP.freq_recovery_upper_decrease} /></span><input class="rd-num" type="number" min="0" step="0.05" bind:value={config.freq_recovery_upper_decrease} /></div>
              <div class="rd-field col-f"><span>Lower <InfoTip text={HELP.freq_recovery_lower_decrease} /></span><input class="rd-num" type="number" min="0" step="0.05" bind:value={config.freq_recovery_lower_decrease} /></div>
            </div>
          </div>
        {/if}

        {#if config.apply_asymmetric_freq_dev}
          <div class="rd-glabel">Frequency Max Deviation (%)</div>
          <div class="rd-two">
            <div class="rd-col"><div class="rd-cap">Load Increase</div><div class="rd-field col-f"><span>Increase <InfoTip text={HELP.freq_max_dev_pct_increase} /></span><input class="rd-num" type="number" min="0" step="1" bind:value={config.freq_max_dev_pct_increase} /></div></div>
            <div class="rd-col"><div class="rd-cap">Load Decrease</div><div class="rd-field col-f"><span>Decrease <InfoTip text={HELP.freq_max_dev_pct_decrease} /></span><input class="rd-num" type="number" min="0" step="1" bind:value={config.freq_max_dev_pct_decrease} /></div></div>
          </div>
        {/if}

        {#if config.iso_8528_5_mode}
          <div class="rd-glabel">ISO 8528-5 Dual Frequency Bands <InfoTip text={HELP.band_mode} /></div>
          <div class="rd-cap">β_f start band: stopwatch starts when freq leaves this band. α_f stop band: stopwatch stops on re-entry (overrides the frequency recovery band above).</div>
          <div class="rd-chips">
            <button class="rd-chip" class:on={config.band_mode === 'pct'} onclick={() => (config.band_mode = 'pct')}>% of Nominal</button>
            <button class="rd-chip" class:on={config.band_mode === 'abs'} onclick={() => (config.band_mode = 'abs')}>Absolute Hz</button>
          </div>
          {#if config.band_mode === 'pct'}
            <div class="rd-two">
              <div class="rd-col"><div class="rd-field col-f"><span>β_f width (%) <InfoTip text={HELP.beta_f_pct} /></span><input class="rd-num" type="number" min="0" step="0.1" bind:value={config.beta_f_pct} /></div></div>
              <div class="rd-col"><div class="rd-field col-f"><span>α_f width (%) <InfoTip text={HELP.alpha_f_pct} /></span><input class="rd-num" type="number" min="0" step="0.1" bind:value={config.alpha_f_pct} /></div></div>
            </div>
            <div class="rd-cap rd-iso-hint">
              β_f: ±{((config.beta_f_pct / 2) / 100 * config.nominal_frequency).toFixed(3)} Hz →
              {(config.nominal_frequency - (config.beta_f_pct / 2) / 100 * config.nominal_frequency).toFixed(3)}–{(config.nominal_frequency + (config.beta_f_pct / 2) / 100 * config.nominal_frequency).toFixed(3)} Hz<br />
              α_f: ±{((config.alpha_f_pct / 2) / 100 * config.nominal_frequency).toFixed(3)} Hz →
              {(config.nominal_frequency - (config.alpha_f_pct / 2) / 100 * config.nominal_frequency).toFixed(3)}–{(config.nominal_frequency + (config.alpha_f_pct / 2) / 100 * config.nominal_frequency).toFixed(3)} Hz
            </div>
          {:else}
            <div class="rd-glabel sm">β_f Start Band (Hz)</div>
            <div class="rd-two">
              <div class="rd-col">
                <div class="rd-cap">Load Increase</div>
                <div class="rd-field col-f"><span>Upper <InfoTip text={HELP.freq_start_upper} /></span><input class="rd-num" type="number" min="0" step="0.05" bind:value={config.freq_start_upper_increase} /></div>
                <div class="rd-field col-f"><span>Lower <InfoTip text={HELP.freq_start_lower} /></span><input class="rd-num" type="number" min="0" step="0.05" bind:value={config.freq_start_lower_increase} /></div>
              </div>
              <div class="rd-col">
                <div class="rd-cap">Load Decrease</div>
                <div class="rd-field col-f"><span>Upper <InfoTip text={HELP.freq_start_upper} /></span><input class="rd-num" type="number" min="0" step="0.05" bind:value={config.freq_start_upper_decrease} /></div>
                <div class="rd-field col-f"><span>Lower <InfoTip text={HELP.freq_start_lower} /></span><input class="rd-num" type="number" min="0" step="0.05" bind:value={config.freq_start_lower_decrease} /></div>
              </div>
            </div>
            <div class="rd-glabel sm">α_f Stop Band / Recovery Band (Hz)</div>
            <div class="rd-two">
              <div class="rd-col">
                <div class="rd-cap">Both Directions</div>
                <div class="rd-field col-f"><span>Upper <InfoTip text={HELP.f_stop_upper} /></span><input class="rd-num" type="number" min="0" step="0.05" bind:value={config.f_stop_upper} /></div>
                <div class="rd-field col-f"><span>Lower <InfoTip text={HELP.f_stop_lower} /></span><input class="rd-num" type="number" min="0" step="0.05" bind:value={config.f_stop_lower} /></div>
              </div>
            </div>
          {/if}
        {/if}

        <Toggle bind:checked={config.steady_state_enabled} label="Evaluate steady-state (ISO 8528-5 δ bands)" tip={HELP.steady_state_enabled} />
        {#if config.steady_state_enabled}
          <div class="rd-cap">Checks the stable dwell periods between load steps. For staged load-bank tests only.</div>
          <div class="rd-glabel">Performance class (Table 4) <InfoTip text={HELP.steady_performance_class} /></div>
          <div class="rd-chips">
            <button class="rd-chip" class:on={config.steady_performance_class === null} onclick={() => (config.steady_performance_class = null)}>None</button>
            <button class="rd-chip" class:on={config.steady_performance_class === 'G1'} onclick={() => (config.steady_performance_class = 'G1')}>G1</button>
            <button class="rd-chip" class:on={config.steady_performance_class === 'G2'} onclick={() => (config.steady_performance_class = 'G2')}>G2</button>
            <button class="rd-chip" class:on={config.steady_performance_class === 'G3'} onclick={() => (config.steady_performance_class = 'G3')}>G3</button>
          </div>
          {#if config.steady_performance_class === null}
            <div class="rd-cap">Free-form mode: every sample is checked against the δU / δf bands below.</div>
          {:else}
            <div class="rd-cap">ISO 8528-5 grading: frequency on β_f (peak-to-peak) and voltage on ΔU_st (regulation), against the {config.steady_performance_class} Table 4 limits. The δU / δf bands below drive the time-series overlay only.</div>
            <Toggle bind:checked={config.steady_isochronous} label="Isochronous set (droop → 0%)" tip={HELP.steady_isochronous} />
            <Toggle bind:checked={config.steady_parallel_operation} label="Parallel operation (unbalance 0.5%)" tip={HELP.steady_parallel_operation} />
          {/if}
          <div class="rd-two">
            <div class="rd-col">
              <div class="rd-field col-f"><span>δU band (±%) <InfoTip text={HELP.steady_voltage_band_pct} /></span><input class="rd-num" type="number" min="0" step="0.5" bind:value={config.steady_voltage_band_pct} /></div>
              <div class="rd-field col-f"><span>Dwell min (s) <InfoTip text={HELP.steady_dwell_min_s} /></span><input class="rd-num" type="number" min="1" step="5" bind:value={config.steady_dwell_min_s} /></div>
            </div>
            <div class="rd-col">
              <div class="rd-field col-f"><span>δf band (±%) <InfoTip text={HELP.steady_freq_band_pct} /></span><input class="rd-num" type="number" min="0" step="0.5" bind:value={config.steady_freq_band_pct} /></div>
              <div class="rd-field col-f"><span>Exclude (s) <InfoTip text={HELP.steady_exclusion_s} /></span><input class="rd-num" type="number" min="0" step="1" bind:value={config.steady_exclusion_s} /></div>
            </div>
          </div>
        {/if}
      </Section>

      <!-- ── Signal / Nominal ────────────────────────────────────── -->
      <Section title="Signal & Nominal" open={false}>
        <div class="rd-glabel">Nominal Voltage <InfoTip text={HELP.nominal_voltage} /></div>
        <div class="rd-chips">
          {#each VOLT_OPTS as v}
            <button class="rd-chip" class:on={voltMode === v} onclick={() => setVoltMode(v)}>{v === 'Custom' ? 'Custom' : `${v} V`}</button>
          {/each}
        </div>
        {#if voltMode === 'Custom'}
          <input class="rd-input" type="number" min="1" step="1" bind:value={config.nominal_voltage} placeholder="Custom V (L-L)" />
        {/if}

        <div class="rd-glabel">Nominal Frequency (Hz) <InfoTip text={HELP.nominal_frequency} /></div>
        <input class="rd-input" type="number" min="1" step="0.5" bind:value={config.nominal_frequency} />

        <div class="rd-glabel">CSV Voltage Columns <InfoTip text={HELP.ln_to_ll_mode} /></div>
        <select class="rd-input rd-select" bind:value={config.ln_to_ll_mode}>
          <option value="auto">Auto-detect (by column names)</option>
          <option value="force_ll">Line-to-Line — use as-is</option>
          <option value="force_ln">Line-to-Neutral — convert ×√3 to L-L</option>
        </select>

        <div class="rd-field"><span>Rated Load (kW) <InfoTip text={HELP.rated_load_kw} /></span><input class="rd-num" type="number" min="0" step="1" placeholder="optional" bind:value={config.rated_load_kw} /></div>
        <div class="rd-field"><span>Expected Load Steps <InfoTip text={HELP.expected_steps} /></span><input class="rd-num" type="number" min="0" step="1" placeholder="optional" bind:value={config.expected_steps} /></div>
      </Section>

      <button class="rd-run" onclick={onRun} disabled={loading || !fileName}>
        {loading ? 'Analyzing…' : 'Run Analysis'}
      </button>
      {#if !fileName}<div class="rd-runhint">Load a file to enable analysis.</div>{/if}
    </div>
  </div>

  <button
    type="button"
    class="rd-resize"
    class:active={dragging}
    aria-label="Resize sidebar — drag, arrow keys to adjust, double-click to reset"
    title="Drag to resize · double-click to reset"
    onmousedown={startDrag}
    ondblclick={resetWidth}
    onkeydown={onHandleKey}
  ></button>
</aside>

{#if presetMgrOpen}
  <PresetConfigurator {config} bind:presets={customPresets} {backend} onApply={applyPreset} onClose={() => (presetMgrOpen = false)} />
{/if}

<style>
  .rd-sidebar {
    width: var(--sidebar-width, 340px);
    flex: 0 0 var(--sidebar-width, 340px);
    height: 100%;
    position: relative;
    display: flex;
    background: var(--bg-side);
    border-right: 1px solid var(--line);
  }
  .rd-sidebar-inner { flex: 1; min-width: 0; display: flex; flex-direction: column; overflow: hidden; }

  .rd-head {
    display: flex; align-items: center; gap: 9px; padding: 15px 18px 13px;
    border-bottom: 1px solid var(--line); flex-shrink: 0;
  }
  .rd-head-bar { width: 3px; height: 14px; border-radius: 2px; background: var(--blue); }
  .rd-head-title { font-size: 13px; font-weight: 700; letter-spacing: 0.03em; color: var(--ink); }
  .rd-head-status { margin-left: auto; font-size: 10px; color: var(--mute); }

  .rd-scroll { flex: 1; overflow-y: auto; padding: 0 18px 28px; }

  /* Data Source */
  .rd-ds-wrap { padding: 16px 0 4px; }
  .rd-ds-label {
    font-size: 11px; font-weight: 700; letter-spacing: 0.1em; text-transform: uppercase;
    color: var(--sub); margin-bottom: 10px;
  }
  .rd-ds-card {
    background: linear-gradient(160deg, var(--panel-2), var(--panel));
    border: 1px solid var(--line-2); border-radius: 11px; padding: 13px;
    transition: border-color 120ms, background 120ms;
  }
  .rd-ds-card.drag-active { border-color: var(--blue); background: rgba(59, 130, 246, 0.14); }
  .rd-ds-row { display: flex; align-items: flex-start; gap: 11px; }
  .rd-ds-icon {
    width: 36px; height: 36px; border-radius: 9px; flex-shrink: 0; display: grid; place-items: center;
    background: rgba(59, 130, 246, 0.12); border: 1px solid rgba(59, 130, 246, 0.25); color: var(--blue);
  }
  .rd-ds-meta { flex: 1; min-width: 0; }
  .rd-ds-name { font-size: 13px; font-weight: 600; color: var(--ink); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .rd-ds-pill {
    display: inline-block; margin-top: 5px; font-size: 9.5px; font-weight: 700; letter-spacing: 0.06em;
    text-transform: uppercase; color: var(--violet); background: rgba(139, 124, 246, 0.13);
    border: 1px solid rgba(139, 124, 246, 0.3); border-radius: 5px; padding: 1px 6px;
  }
  .rd-ds-change, .rd-ds-load {
    width: 100%; margin-top: 12px; height: 32px; border-radius: 8px; cursor: pointer;
    background: var(--panel-3); border: 1px solid var(--line-2); color: var(--ink);
    font-size: 12.5px; font-weight: 600; display: flex; align-items: center; justify-content: center; gap: 7px;
  }
  .rd-ds-change:hover, .rd-ds-load:hover { background: var(--line-2); }
  .rd-ds-load { margin-top: 0; }
  .rd-ds-swap { color: var(--sub); display: grid; place-items: center; }
  .rd-ds-hint { text-align: center; font-size: 10.5px; color: var(--mute); margin-top: 8px; }

  /* shared inputs */
  .rd-input, .rd-num {
    background: var(--panel); border: 1px solid var(--line-2); color: var(--ink);
    border-radius: 7px; padding: 7px 9px; font-size: 13px;
    font-family: 'JetBrains Mono', monospace; width: 100%;
  }
  .rd-input:focus, .rd-num:focus { outline: none; border-color: var(--blue); }
  .rd-num:disabled, .rd-input:disabled { opacity: 0.45; }
  .rd-select { appearance: none; cursor: pointer; font-weight: 600; }

  .rd-glabel { font-size: 11px; text-transform: uppercase; letter-spacing: 0.06em; color: var(--sub); margin-top: 6px; }
  .rd-glabel.sm { font-size: 10px; }
  .rd-subhd {
    font-size: 10px; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase;
    color: var(--faint); padding: 8px 0 2px;
  }
  .rd-divider { height: 1px; background: var(--line); margin: 4px 0; }
  .rd-note { font-size: 11px; color: var(--mute); line-height: 1.5; margin-top: 2px; }
  .rd-amber { color: var(--amber); }

  .rd-field { display: flex; align-items: center; justify-content: space-between; gap: 8px; padding: 1px 0; }
  .rd-field span { font-size: 12.5px; color: var(--sub); }
  .rd-field .rd-num { width: 88px; flex: 0 0 88px; text-align: right; font-weight: 600; }
  .rd-field.col-f .rd-num { width: 74px; flex: 0 0 74px; }

  /* Tolerances matrix */
  .rd-tol { display: grid; grid-template-columns: 1fr 70px 70px; gap: 6px 6px; align-items: center; }
  .rd-tol-hd {
    font-size: 9.5px; font-weight: 700; letter-spacing: 0.05em; text-transform: uppercase;
    color: var(--mute); text-align: center; padding-bottom: 2px;
  }
  .rd-tol-row { font-size: 12px; color: var(--sub); }
  .rd-tol-cell { text-align: center; font-weight: 600; padding: 6px; }

  .rd-two { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
  .rd-col { display: flex; flex-direction: column; gap: 6px; }
  .rd-cap { font-size: 11px; color: var(--mute); }
  .rd-iso-hint {
    line-height: 1.6; font-family: 'JetBrains Mono', monospace; font-size: 10.5px;
    background: var(--panel); border: 1px solid var(--line); border-radius: 6px; padding: 4px 8px; margin-top: 4px;
  }

  .rd-chips { display: flex; gap: 6px; flex-wrap: wrap; }
  .rd-chip {
    flex: 1; min-width: 56px; background: var(--panel); border: 1px solid var(--line-2);
    color: var(--sub); padding: 6px; border-radius: 7px; font-size: 12px;
  }
  .rd-chip.on { background: var(--blue); border-color: var(--blue); color: #fff; font-weight: 600; }

  .rd-ghost {
    background: var(--panel); color: var(--sub); border: 1px solid var(--line-2);
    border-radius: 7px; padding: 7px; font-size: 12px; cursor: pointer;
  }
  .rd-ghost:hover { border-color: var(--blue); color: var(--ink); }

  .rd-modified {
    display: flex; align-items: center; justify-content: space-between; gap: 8px; flex-wrap: wrap;
    margin-top: 6px; padding: 7px 9px; border-radius: 7px;
    background: rgba(251, 191, 36, 0.1); border: 1px solid rgba(251, 191, 36, 0.3);
  }
  .rd-mod-note { font-size: 11px; color: var(--amber); display: flex; align-items: center; gap: 5px; }
  .rd-mod-dot { font-size: 9px; }
  .rd-mod-actions { display: flex; gap: 5px; }
  .rd-mod-btn {
    background: var(--panel); color: var(--sub); border: 1px solid var(--line-2);
    border-radius: 6px; padding: 4px 9px; font-size: 11px; font-weight: 600; cursor: pointer;
  }
  .rd-mod-btn:hover { border-color: var(--blue); color: var(--ink); }
  .rd-mod-btn.primary { background: var(--blue); border-color: var(--blue); color: #fff; }

  .rd-exact summary { font-size: 11px; color: var(--mute); cursor: pointer; user-select: none; list-style: revert; }
  .rd-exact summary:hover { color: var(--sub); }
  .rd-exact[open] { display: flex; flex-direction: column; gap: 8px; }
  .rd-reset-win {
    display: flex; align-items: center; gap: 5px; justify-content: center;
    background: var(--panel); color: var(--sub); border: 1px solid var(--line-2);
    border-radius: 7px; padding: 6px; font-size: 12px; cursor: pointer;
  }
  .rd-reset-win:hover { border-color: var(--blue); color: var(--ink); }

  .rd-run {
    background: var(--blue); color: #fff; border: none; padding: 12px; border-radius: 9px;
    font-size: 15px; font-weight: 700; cursor: pointer; margin-top: 16px; width: 100%;
  }
  .rd-run:disabled { background: var(--panel-3); color: var(--mute); cursor: not-allowed; }
  .rd-runhint { font-size: 11px; color: var(--faint); text-align: center; margin-top: 6px; }

  .rd-resize {
    position: absolute; top: 0; right: 0; bottom: 0; width: 6px; cursor: col-resize;
    background: transparent; border: none; padding: 0; appearance: none; transition: background 0.15s; z-index: 5;
  }
  .rd-resize:hover, .rd-resize.active { background: var(--blue); }
  .rd-resize:focus-visible { outline: 2px solid var(--blue); outline-offset: -2px; }
</style>
