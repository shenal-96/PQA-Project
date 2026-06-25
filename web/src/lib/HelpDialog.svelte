<script lang="ts">
  import img2 from '../assets/help/csv_step2_ll_voltage.png';
  import img3 from '../assets/help/csv_step3_trend_graph.png';
  import img4 from '../assets/help/csv_step4_export_options.png';

  let { onClose }: { onClose: () => void } = $props();

  // Table-of-contents sections (id must match each <section id> below).
  const toc = [
    { id: 'csv', label: 'Generating the CSV' },
    { id: 'overview', label: 'Overview' },
    { id: 'workflow', label: 'Workflow' },
    { id: 'detection', label: 'Load-event detection' },
    { id: 'voltage', label: 'Voltage (L-N vs L-L)' },
    { id: 'loggers', label: 'Supported loggers' },
    { id: 'timing', label: 'Timing precision' },
    { id: 'deviation', label: 'Peak deviation' },
    { id: 'exit', label: 'Band-exit time' },
    { id: 'recovery', label: 'Recovery time' },
    { id: 'passfail', label: 'Pass / fail rules' },
    { id: 'steady', label: 'Steady-state (ISO 8528-5)' },
    { id: 'fault', label: 'Potential Fault flag' },
    { id: 'asymmetric', label: 'Asymmetric bands' },
    { id: 'iso', label: 'ISO 8528-5 dual bands' },
    { id: 'graphs', label: 'Time-series graphs' },
    { id: 'snapshots', label: 'Event snapshots' },
    { id: 'settings', label: 'Settings reference' },
    { id: 'tabs', label: 'Tabs' },
    { id: 'tips', label: 'Tips' },
  ];

  let active = $state('csv');
  let body: HTMLDivElement;

  function jump(id: string) {
    document.getElementById('help-' + id)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  // Highlight the TOC entry for the section currently in view.
  $effect(() => {
    if (!body) return;
    const io = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          if (e.isIntersecting) active = e.target.id.replace('help-', '');
        }
      },
      { root: body, rootMargin: '-10% 0px -80% 0px', threshold: 0 },
    );
    body.querySelectorAll('section[id]').forEach((s) => io.observe(s));
    return () => io.disconnect();
  });

  function onKey(e: KeyboardEvent) {
    if (e.key === 'Escape') onClose();
  }
</script>

<svelte:window on:keydown={onKey} />

<div class="overlay" onclick={(e) => { if (e.target === e.currentTarget) onClose(); }} role="presentation">
  <div class="dialog" role="dialog" aria-modal="true" aria-label="PQA User Guide" tabindex="-1">
    <header>
      <div class="title"><span class="bolt">⚡</span> PQA User Guide <span class="ver">v4.1</span></div>
      <button class="close" onclick={onClose} aria-label="Close">✕</button>
    </header>

    <div class="layout">
      <nav class="toc">
        {#each toc as t}
          <button class:active={active === t.id} onclick={() => jump(t.id)}>{t.label}</button>
        {/each}
      </nav>

      <div class="body" bind:this={body}>
        <section id="help-csv">
          <h2>Generating the CSV file from PQone</h2>
          <p>Follow these steps in PQone to export the CSV file that PQA expects.</p>
          <ol class="steps">
            <li><b>Step 1</b> — Open the PQA data with PQone.</li>
            <li><b>Step 2</b> — Select Line-to-Line voltage.
              <img src={img2} alt="Select line-to-line voltage" /></li>
            <li><b>Step 3</b> — Select <i>Trend Graph</i> from the CSV export options.
              <img src={img3} alt="Select Trend Graph" /></li>
            <li><b>Step 4</b> — Make the following selections and click <i>OK</i> to save the CSV.
              <img src={img4} alt="Export options" /></li>
          </ol>
          <div class="callout info">
            The CSV file name auto-populates the report title (it can be edited later). Name the
            file after the test conducted — e.g. <i>ISO 8528 Step Load</i>.
          </div>
        </section>

        <section id="help-overview">
          <h2>Overview</h2>
          <p>
            PQA reads data-logger CSV files, finds load events, and checks whether the generator's
            voltage and frequency stayed within acceptable limits after each load change. Results are
            a compliance table, time-series graphs, per-event snapshots, and an exportable Word or
            PDF report.
          </p>
        </section>

        <section id="help-workflow">
          <h2>Workflow</h2>
          <ol class="flow">
            <li><b>Load your CSV</b> — use the sidebar uploader. The file needs a timestamp column, voltage readings, frequency, and active power in kilowatts.</li>
            <li><b>Choose acceptance criteria</b> — pick a preset (ISO 8528 G1, G2, or G3) or enter custom limits. Enable <i>asymmetric</i> mode for different limits on load increases vs decreases.</li>
            <li><b>Set nominal values</b> — enter the rated voltage (415 V, 690 V, 11 000 V, or custom) and frequency. All percentage deviations are relative to these.</li>
            <li><b>Run Analysis</b> — the tool finds load events, measures deviations, and checks recovery.</li>
            <li><b>Review results</b> — the compliance table shows one row per event with a Pass/Fail verdict, peak deviation, and recovery time. Red rows and red-tinted snapshots are failures; a <i>Not Recovered</i> warning appears when the signal was still out of limits when the next step fired.</li>
            <li><b>Override recovery points</b> — if a crossing looks wrong, turn on <i>Show Intersection Points</i> and use the per-event override controls in the snapshot card.</li>
            <li><b>Export</b> — fill in the report details, then click <i>Generate Report</i>.</li>
          </ol>
        </section>

        <section id="help-detection">
          <h2>How load events are detected</h2>
          <p>The tool calculates the change in power between each consecutive sample:</p>
          <div class="formula">Power change = current kW reading − previous kW reading</div>
          <p>
            If the absolute change exceeds the <b>Load Threshold</b>, that moment is flagged. Changes
            within the <b>Detection Window</b> of each other are merged into one event and
            <b>algebraically summed</b> into a single net step.
          </p>
          <p>
            This matters for large block loads: at high sample rates a 0 → 2000 kW step is not one
            clean transition — the kW reading oscillates as the generator catches up (e.g. +1255,
            −152, +390, −45, +602). Summing them gives the true net step (≈ +2050 kW) as one event
            instead of several fragments. If the sum across the window falls below the Load Threshold,
            the group is discarded as oscillation around a stable load.
          </p>
          <div class="callout tip">
            Increase the Detection Window if a single ramp is split into separate events. Decrease it
            only if you deliberately fire an UP step and a DOWN step within a few seconds — the merge
            logic combines those into one net event otherwise.
          </div>
        </section>

        <section id="help-voltage">
          <h2>Voltage — Line-to-Neutral vs Line-to-Line</h2>
          <p>Compliance is always checked against <b>Line-to-Line (L-L) voltage</b>. The <b>CSV Voltage Columns</b> setting tells the tool how to read your file:</p>
          <table>
            <thead><tr><th>Setting</th><th>What happens</th></tr></thead>
            <tbody>
              <tr><td>Auto-detect</td><td>U1/U2/U3 columns are treated as L-N and converted; U12/U23/U31 are treated as L-L and used as-is</td></tr>
              <tr><td>Line-to-Line — use as-is</td><td>All voltage columns used directly, no conversion</td></tr>
              <tr><td>Line-to-Neutral — convert ×√3</td><td>All voltage columns multiplied by 1.732 to get L-L</td></tr>
            </tbody>
          </table>
          <div class="formula">L-L Voltage = L-N Voltage × √3 ≈ L-N Voltage × 1.732</div>
          <p>The three phases are then averaged into a single value used for all compliance checks and graphs.</p>
        </section>

        <section id="help-loggers">
          <h2>Supported data loggers</h2>
          <p>PQA auto-detects the source format from the CSV header and dispatches to the right loader:</p>
          <table>
            <thead><tr><th>Logger</th><th>Identified by</th><th>Voltage handling</th></tr></thead>
            <tbody>
              <tr><td>Hioki</td><td>Default — <code>U1/U2/U3_rms_AVG</code> (L-N) or <code>U12/U23/U31_rms_AVG</code> (L-L)</td><td>L-N scaled ×√3, L-L used as-is</td></tr>
              <tr><td>Miro</td><td>Header has <code>RMS-VA-AVG [V]</code>, <code>FREQ-VA-AVG [Hz]</code>, <code>kW-PTOTAL-AVG [kW]</code></td><td>Loaded as L-N and scaled ×√3</td></tr>
            </tbody>
          </table>
          <p>The detected logger is shown as a pill in the sidebar next to the file name. WinScope <code>.xls</code> exports are handled on their own tab using the same compliance engine.</p>
          <p>
            <b>Miro CSVs only have whole-second timestamps.</b> When the logger records faster than
            1 Hz, PQA spreads the repeated rows evenly across the second using a stable sort, so the
            data carries an honest sub-second grid without scrambling fast-changing values.
          </p>
        </section>

        <section id="help-timing">
          <h2>How timing is made more precise</h2>
          <p>
            Hioki CSVs typically record one sample per second — too coarse to measure a 2.7 s recovery
            accurately. PQA fills the gaps with a denser version of the data at one point every
            100 ms (straight-line interpolation between your samples).
          </p>
          <p>
            <b>Miro CSVs skip this step.</b> They are used at the source rate the logger recorded, and
            the recovery algorithm adapts the number of "stay-in-band" samples it requires to the
            actual interval — so accuracy matches the source without inventing readings.
          </p>
          <div class="callout info">
            The denser data is used <b>only for timing</b> (when did the signal leave / return to the
            band?). All values shown in tables, graphs, and snapshots always come from your original
            logged data.
          </div>
        </section>

        <section id="help-deviation">
          <h2>Peak deviation — how it is found</h2>
          <p>For each event the tool looks ahead through your original data for the length of the <b>Snapshot Window</b> and picks the worst-case reading:</p>
          <ul>
            <li><b>Load increase</b> (power up, voltage/frequency drops) → <b>lowest</b> recorded value</li>
            <li><b>Load decrease</b> (power down, voltage/frequency rises) → <b>highest</b> recorded value</li>
          </ul>
          <div class="formula">Deviation % = |Measured peak − Nominal| ÷ Nominal × 100</div>
          <p>For example, nominal 415 V and a measured low of 406 V → |406 − 415| ÷ 415 × 100 = <b>2.17 %</b>. The table shows both, e.g. <code>406 V (−2.17%)</code>.</p>
        </section>

        <section id="help-exit">
          <h2>Band-exit time</h2>
          <p>
            The <i>tolerance band</i> is the acceptable range around nominal — e.g. with a 1 % voltage
            tolerance at 415 V, the band is 410.85–419.15 V. To find the exact moment the signal left
            the band, the tool scans <b>backwards</b> from the event timestamp (up to 30 s), finds the
            last in-band and first out-of-band readings, and interpolates the crossing:
          </p>
          <div class="formula">Exit time = t₁ + (Band limit − V₁) ÷ (V₂ − V₁) × (t₂ − t₁)</div>
          <p>
            If the signal was still in-band at the event (the excursion happened afterwards — common
            with slow governors), it scans <b>forward</b> instead. If the signal never left the band,
            no exit time is recorded and the recovery check is skipped.
          </p>
        </section>

        <section id="help-recovery">
          <h2>Recovery time</h2>
          <p>
            From the exit time, the tool scans forward for the signal to re-enter the band and
            <b>stay there for at least 0.3 s continuously</b> (the sample count is derived from the
            actual interval — 3 samples on 100 ms, 1 on 1 s data). The re-entry crossing is then
            interpolated.
          </p>
          <p>
            It keeps watching for a further <b>Recovery Verify Window</b> (default 6 s) to ensure the
            signal does not bounce back out; if it does, the candidate is discarded and the search
            resumes — preventing false recoveries on oscillating waveforms.
          </p>
          <div class="formula">Recovery time = Time of re-entry − Time of exit</div>
        </section>

        <section id="help-passfail">
          <h2>Compliance pass / fail rules</h2>
          <p>Each event must pass <b>both</b> voltage and frequency checks.</p>
          <p><b>Deviation check</b></p>
          <ul>
            <li>Load increase (signal dropped): <b>FAIL</b> if deviation % exceeds <i>Max Dev — load increase</i></li>
            <li>Load decrease (signal rose): <b>FAIL</b> if deviation % exceeds <i>Max Dev — load decrease</i></li>
          </ul>
          <p><b>Recovery check</b> <span class="muted">(only when the signal left the band)</span></p>
          <ul>
            <li><b>FAIL</b> if the signal never returned to the band within the data</li>
            <li><b>FAIL</b> if recovery time exceeded the Voltage or Frequency Recovery limit</li>
          </ul>
          <p>The event is <b>Pass</b> only if no failure was triggered for either voltage or frequency.</p>
        </section>

        <section id="help-steady">
          <h2>Steady-state analysis (ISO 8528-5)</h2>
          <p>
            Separate from the transient checks above, steady-state analysis verifies how the
            generator behaves while load is <b>held constant</b> — the dwell periods <i>between</i>
            load steps, the way a staged load-bank test holds 25 / 50 / 75 / 100 % for several
            minutes each. It answers a different question than the transient checks: not "how fast
            did it recover from the step?" but "how steady is it once settled?"
          </p>
          <div class="callout warn">
            <b>Don't confuse the bands.</b> Steady-state uses the tight steady tolerances. Transient
            analysis uses the wider <b>α</b> (recovery target) and <b>β</b> (departure trigger) bands.
            PQA keeps them completely separate — steady-state never touches the recovery fields.
          </div>

          <h3>How the check works</h3>
          <p><b>1. It finds the stable dwell windows.</b> PQA segments the record into the spans
            between detected load steps, then trims a settling margin (<i>Exclude (s)</i>) off each
            side so the post-step governor/AVR tail is left out. Spans shorter than <i>Dwell min (s)</i>
            are discarded. With no load steps the whole record is one window. Every measured sample in
            each window is inspected on the <b>raw logged data</b> (never the interpolated grid).</p>

          <p><b>2. It grades each window — in one of two modes.</b></p>
          <ul>
            <li><b>Free-form mode</b> (Performance class = <i>None</i>): every sample is checked
              against the <b>δU / δf</b> bands you set in the sidebar (default ±2.5 % / ±2.0 %). A
              window <b>fails</b> if any sample leaves the band.</li>
            <li><b>ISO 8528-5 class mode</b> (class = <i>G1 / G2 / G3</i>): the two spec metrics drive
              the verdict, graded against the <b>Table 4</b> limits for that class:
              <ul>
                <li><b>β_f — steady-state frequency band</b> (per window): the peak-to-peak frequency
                  swing as a % of rated, <code>(f_max − f_min) / f_r × 100</code>. This is the
                  per-window frequency Pass/Fail.</li>
                <li><b>ΔU_st — steady-state voltage regulation</b> (across all windows): the spread of
                  the per-window mean voltages over the whole no-load→rated sweep,
                  <code>±(U_max − U_min) / (2·U_r) × 100</code>. Judged once, in the summary card.</li>
              </ul>
            </li>
          </ul>

          <p><b>3. It always reports two extra signals.</b> <b>Hunting</b> — sustained cyclic
            oscillation (governor/AVR), flagged even when the peaks stay in band; it's a qualitative
            red flag and does <i>not</i> fail the dwell on its own. <b>Frequency droop</b> — a sanity
            check, <code>(f_noload − f_rated) / f_r × 100</code>, expected ≈ 0 for an isochronous set.</p>

          <p>The Table 4 limits PQA grades against (after any footnote toggles):</p>
          <table>
            <thead><tr><th>Metric</th><th>G1</th><th>G2</th><th>G3</th></tr></thead>
            <tbody>
              <tr><td>β_f — frequency band (±%)</td><td>2.5</td><td>1.5</td><td>0.5</td></tr>
              <tr><td>ΔU_st — voltage regulation (±%)</td><td>5.0</td><td>2.5</td><td>1.0</td></tr>
              <tr><td>α_f — frequency tolerance / re-entry (±%)</td><td>3.5</td><td>2.0</td><td>2.0</td></tr>
              <tr><td>Voltage unbalance, no-load (%) <span class="muted">— deferred</span></td><td>1.0</td><td>1.0</td><td>1.0</td></tr>
              <tr><td>Voltage modulation Û_mod,s (%) <span class="muted">— deferred</span></td><td>AMC</td><td>0.3</td><td>0.3</td></tr>
              <tr><td>Droop δf_st (%), non-isochronous</td><td>8.0</td><td>5.0</td><td>3.0</td></tr>
            </tbody>
          </table>
          <p class="muted">
            Footnote toggles in the sidebar adjust these: <i>single/two-cylinder</i> raises β_f to
            2.5 %, <i>low-power (ISO 8528-8)</i> relaxes ΔU_st to ±10 %, <i>parallel operation</i>
            tightens unbalance to 0.5 %, and <i>isochronous</i> (on by default) sets the droop limit
            to 0 %. Voltage <b>unbalance</b> and <b>modulation</b> are not yet computed — the summary
            shows their gate status ("not computed") rather than a fabricated number.
          </p>

          <h3>Applying it to a data set</h3>
          <ol class="flow">
            <li>Tick <b>Evaluate steady-state</b> in the sidebar. It's opt-in — only meaningful for
              staged load-bank tests that hold each load level for a dwell.</li>
            <li>Pick a <b>Performance class</b> (G1 / G2 / G3) matching the genset's specification, or
              leave it <i>None</i> to grade against your own δU / δf bands. The chips tell you which
              mode you're in.</li>
            <li>Set the <b>footnote toggles</b> that apply (isochronous is on by default; tick
              single/two-cylinder, low-power, or parallel operation as relevant).</li>
            <li>Enter <b>Rated Load (kW)</b> so each dwell is auto-labelled 25 / 50 / 75 / 100 %.</li>
            <li>Tune <b>Dwell min (s)</b> below your actual hold time (so real plateaus survive but
              brief pauses don't), and <b>Exclude (s)</b> to cover the settling tail after each step —
              raise it if a slow governor/AVR is dragging transient samples into the dwell.</li>
            <li>Click <b>Run Analysis</b>. Review the dwell table + the ISO 8528-5 summary card below
              the compliance table; the δ band is overlaid on the Voltage and Frequency plots.</li>
            <li><b>Adjust if needed.</b> Relabel a dwell, edit its start/end timestamps, or remove a
              spurious window, then <b>Re-evaluate windows</b>. <b>Reset to auto-detected</b> restores
              the automatic segmentation.</li>
          </ol>

          <h3>Reading the results</h3>
          <ul>
            <li><b>Dwell table</b> — one row per window: load label, time span, duration, sample count,
              the band in use, V and F min/mean/max, the count of samples outside band, the
              <b>β_f %</b> (with its class limit), and the Pass/Fail badge. A <code>⚠ Hunting</code>
              badge appears when oscillation is detected.</li>
            <li><b>ISO 8528-5 summary card</b> — the cross-window verdicts: <b>ΔU_st</b> voltage
              regulation (value vs limit, Pass/Fail), the <b>droop</b> sanity check, the detected
              <b>sample rate</b>, and the deferred unbalance / modulation status.</li>
          </ul>
          <div class="callout tip">
            In class mode the per-window <b>frequency</b> verdict is β_f, while <b>voltage</b>
            regulation (ΔU_st) is judged once across the whole sweep in the summary card — so a single
            dwell can read "Pass" on frequency yet the run still flag a voltage-regulation problem
            overall. Read the table and the summary card together.
          </div>
        </section>

        <section id="help-fault">
          <h2>Potential Fault flag — separate from compliance fail</h2>
          <p>
            A long recovery time usually indicates an equipment problem (broken set-points, sluggish
            governor, exciter fault) rather than a marginal miss. PQA flags these separately.
          </p>
          <table>
            <thead><tr><th>Scenario</th><th>Typical recovery</th><th>Meaning</th></tr></thead>
            <tbody>
              <tr><td>Load decrease (any size)</td><td>&lt; 4 s</td><td>Unloading is normally quick</td></tr>
              <tr><td>Large block load acceptance</td><td>4–8 s</td><td>Engine + governor catch-up — still healthy</td></tr>
              <tr><td>Anything &gt; 10–15 s</td><td>Suspect</td><td>Investigate set-points or hardware</td></tr>
              <tr><td>30 s+</td><td>Almost certainly a fault</td><td></td></tr>
            </tbody>
          </table>
          <p>
            The <b>Fault Recovery Threshold</b> (default 10 s) is the cut-off. Any event exceeding it
            gets a <code>⚠ Investigate</code> badge in the Potential Fault column. This is independent
            of Pass/Fail — an event can pass compliance yet still be flagged for unusually slow
            recovery.
          </p>
        </section>

        <section id="help-asymmetric">
          <h2>Asymmetric bands</h2>
          <p>By default the same tolerance applies in both directions. The four <i>Apply asymmetric…</i> toggles let you set separate limits per direction:</p>
          <table>
            <thead><tr><th>Toggle</th><th>Unlocks</th></tr></thead>
            <tbody>
              <tr><td>Asymmetric Voltage tolerance band</td><td>Separate recovery band (V) for increase vs decrease</td></tr>
              <tr><td>Asymmetric Voltage deviation limit</td><td>Separate max-deviation % per direction</td></tr>
              <tr><td>Asymmetric Frequency tolerance band</td><td>Separate recovery band (Hz) per direction</td></tr>
              <tr><td>Asymmetric Frequency deviation limit</td><td>Separate max-deviation % per direction</td></tr>
            </tbody>
          </table>
          <p>ISO 8528 uses asymmetric frequency bands because a governor responds differently to slowing down (load increase) vs speeding up (load decrease):</p>
          <table>
            <thead><tr><th>Event</th><th>Frequency</th><th>Recovery band (G3 default)</th></tr></thead>
            <tbody>
              <tr><td>Load increase</td><td>drops</td><td>49.75 – 50.50 Hz</td></tr>
              <tr><td>Load decrease</td><td>rises</td><td>49.50 – 50.25 Hz</td></tr>
            </tbody>
          </table>
        </section>

        <section id="help-iso">
          <h2>ISO 8528-5 dual frequency bands</h2>
          <p>
            <i>Apply ISO dual frequency bands</i> enables the ISO 8528-5 §7 method for frequency: the
            recovery stopwatch <b>starts</b> when frequency leaves the tighter <b>β_f</b> start band
            and <b>stops</b> when it re-enters the wider <b>α_f</b> stop band (instead of a single band
            for both). It also adds pre-step and post-recovery steady-state checks. Off by default = the
            single-band behaviour. The ISO G1/G2/G3 presets enable it.
          </p>
        </section>

        <section id="help-graphs">
          <h2>Time-series graphs</h2>
          <p>
            Graphs are shown as tabs above the compliance table: <b>Active Power (kW)</b>,
            <b>Voltage (L-L)</b>, <b>Current (A)</b>, <b>Frequency (Hz)</b>, <b>Power Factor</b>,
            <b>THD</b>, plus the <b>ITIC curve</b>. The horizontal axis spans the full run; drag the
            zoom slider or scroll to focus on a window.
          </p>
          <p>
            When steady-state is enabled, the Voltage and Frequency plots overlay the δ band (dashed
            teal lines) and shade the detected dwell windows.
          </p>
        </section>

        <section id="help-snapshots">
          <h2>Event snapshots</h2>
          <p>
            Each event gets a four-panel zoom (Voltage, Current, Frequency, Power) centred on the load
            change, spanning the <b>Snapshot Window</b>. If the exit or recovery markers fall outside
            the window it auto-extends to include them. The title shows the load before/after, the kW
            change, and (if <i>Rated Load</i> is set) that change as a % of rated.
          </p>
          <table>
            <thead><tr><th>Toggle</th><th>What it draws</th></tr></thead>
            <tbody>
              <tr><td>Show Tolerance Band</td><td>Amber dashed recovery-band limits for this event</td></tr>
              <tr><td>Show Deviation Limits</td><td>Red dashed line — only the limit relevant to this event's direction</td></tr>
              <tr><td>Show Intersection Points</td><td>Orange star where the signal left the band; lime star where it recovered</td></tr>
              <tr><td>Show Max Deviation</td><td>Red star at the exact peak — matches the table value</td></tr>
            </tbody>
          </table>
          <p>
            A <b>Not Recovered</b> tint highlights a panel red when the signal had not returned to the
            band before the next event. Per-snapshot <b>window size</b> and <b>time shift</b> controls
            let you tune one snapshot without affecting the others — compliance values are unaffected.
          </p>
        </section>

        <section id="help-settings">
          <h2>Settings reference</h2>
          <h3>Detection &amp; timing windows</h3>
          <table>
            <thead><tr><th>Setting</th><th>Default</th><th>Range</th><th>What it does</th></tr></thead>
            <tbody>
              <tr><td>Detection Window (s)</td><td>5</td><td>1–30</td><td>Load changes within this window merge into one net event (algebraic sum)</td></tr>
              <tr><td>Snapshot Window (s)</td><td>10</td><td>3–60</td><td>Width of each snapshot; also the window used to find peak deviation</td></tr>
              <tr><td>Recovery Verify Window (s)</td><td>6</td><td>1–30</td><td>How long the signal must stay in-band before recovery is confirmed</td></tr>
              <tr><td>Fault Recovery Threshold (s)</td><td>10</td><td>1–120</td><td>Recovery longer than this triggers a Potential Fault badge</td></tr>
            </tbody>
          </table>
          <h3>Acceptance criteria — symmetric</h3>
          <table>
            <thead><tr><th>Setting</th><th>Default</th><th>What it means</th></tr></thead>
            <tbody>
              <tr><td>Load Threshold (kW)</td><td>50</td><td>Minimum power change to register an event</td></tr>
              <tr><td>Voltage Tolerance (%)</td><td>1.0</td><td>Recovery band = Nominal ± this %</td></tr>
              <tr><td>Voltage Recovery (s)</td><td>4.0</td><td>Max time to return to band — FAIL if exceeded</td></tr>
              <tr><td>Max Voltage Deviation (%)</td><td>15.0</td><td>Max peak deviation — FAIL if exceeded</td></tr>
              <tr><td>Frequency Tolerance (%)</td><td>0.5</td><td>Recovery band = Nominal ± this %</td></tr>
              <tr><td>Frequency Recovery (s)</td><td>3.0</td><td>Max time to return to band — FAIL if exceeded</td></tr>
              <tr><td>Max Frequency Deviation (%)</td><td>7.0</td><td>Max peak deviation — FAIL if exceeded</td></tr>
            </tbody>
          </table>
          <h3>Steady-state (δ bands)</h3>
          <table>
            <thead><tr><th>Setting</th><th>Default</th><th>What it does</th></tr></thead>
            <tbody>
              <tr><td>Evaluate steady-state</td><td>Off</td><td>Opt-in δ-band evaluation of the stable dwell periods</td></tr>
              <tr><td>δU band (±%)</td><td>2.5</td><td>Voltage tolerance during a dwell</td></tr>
              <tr><td>δf band (±%)</td><td>2.0</td><td>Frequency tolerance during a dwell</td></tr>
              <tr><td>Dwell min (s)</td><td>30</td><td>Ignore plateaus shorter than this</td></tr>
              <tr><td>Exclude (s)</td><td>10</td><td>Trim this off each side of a dwell to drop the settling tail</td></tr>
            </tbody>
          </table>
          <h3>Other &amp; report settings</h3>
          <table>
            <thead><tr><th>Setting</th><th>What it does</th></tr></thead>
            <tbody>
              <tr><td>Rated Load (kW)</td><td>Optional — snapshot titles show the step as a % of rated, and dwells get a 25/50/75/100 % label</td></tr>
              <tr><td>No. Expected Load Steps</td><td>Optional — warns if the detected event count differs</td></tr>
              <tr><td>Nominal Voltage / Frequency</td><td>The rated values all deviations and bands are relative to</td></tr>
              <tr><td>CSV Voltage Columns</td><td>How to interpret the voltage columns — see Voltage above</td></tr>
              <tr><td>Report details + format</td><td>Title, serial numbers, site, custom notes; export to PDF, HTML, or .docx (with a Word template)</td></tr>
            </tbody>
          </table>
        </section>

        <section id="help-tabs">
          <h2>Tabs</h2>
          <table>
            <thead><tr><th>Tab</th><th>Purpose</th></tr></thead>
            <tbody>
              <tr><td>⚡ Compliance</td><td>Main workflow — CSV upload, analysis, report</td></tr>
              <tr><td>📊 WinScope</td><td>High-resolution WinScope XLS with the same compliance engine</td></tr>
              <tr><td>🔧 Set Point</td><td>Compare ECU parameter files (XLS, XLSX, or CSV) across units</td></tr>
              <tr><td>🔌 ECU Plotting</td><td>Time-series viewer for ECU recordings, auto-grouped by channel</td></tr>
            </tbody>
          </table>
        </section>

        <section id="help-tips">
          <h2>Tips</h2>
          <ul>
            <li><b>Check the event count first</b> — after running, confirm the compliance table has the number of events you expected. If not, adjust the Load Threshold or Detection Window before chasing individual snapshots.</li>
            <li><b>Per-snapshot Time Shift</b> — when an event sits awkwardly (the dip is at the edge), nudge that one snapshot without affecting the others.</li>
            <li><b>Snapshot Window</b> — increase it if the voltage/frequency nadir occurs after the default window (slow governor). This also widens the peak-deviation search.</li>
            <li><b>Detection Window</b> — increase if a single ramp is split into multiple events; decrease only for deliberate UP-then-DOWN test patterns.</li>
            <li><b>Fault Recovery Threshold</b> — a healthy generator rarely approaches the 10 s default. Lower it to be alerted earlier; raise it for ageing equipment where 12–15 s is the baseline.</li>
            <li><b>Steady-state</b> — only enable it for staged load-bank tests where each level is held for a dwell; it is not meaningful for a single transient capture.</li>
          </ul>
        </section>
      </div>
    </div>
  </div>
</div>

<style>
  .overlay {
    position: fixed; inset: 0; z-index: 100;
    background: rgba(15, 23, 42, 0.55); backdrop-filter: blur(2px);
    display: grid; place-items: center; padding: clamp(8px, 3vh, 40px);
  }
  .dialog {
    width: min(1100px, 100%); height: min(860px, 100%);
    background: var(--card, #fff); border-radius: 14px; overflow: hidden;
    display: flex; flex-direction: column;
    box-shadow: 0 24px 60px rgba(2, 6, 23, 0.45);
  }
  header {
    display: flex; align-items: center; justify-content: space-between;
    padding: 14px 18px; background: var(--navy); color: #fff;
  }
  header .title { display: flex; align-items: center; gap: 8px; font-weight: 800; letter-spacing: -0.01em; }
  header .bolt { display: grid; place-items: center; width: 26px; height: 26px; background: var(--blue); border-radius: 7px; font-size: 14px; }
  header .ver { font-size: 11px; font-weight: 600; color: #94a3b8; background: #1e293b; padding: 2px 7px; border-radius: 999px; }
  .close { background: #1e293b; color: #cbd5e1; border: none; width: 32px; height: 32px; border-radius: 8px; font-size: 14px; cursor: pointer; }
  .close:hover { background: #334155; color: #fff; }

  .layout { flex: 1; min-height: 0; display: grid; grid-template-columns: 232px 1fr; }
  .toc {
    border-right: 1px solid var(--border); background: #f8fafc;
    overflow-y: auto; padding: 12px 8px; display: flex; flex-direction: column; gap: 2px;
  }
  .toc button {
    text-align: left; background: none; border: none; cursor: pointer;
    padding: 7px 12px; border-radius: 7px; font-size: 13px; color: var(--text-sub);
    border-left: 2px solid transparent;
  }
  .toc button:hover { background: #eef2f7; color: var(--text-main); }
  .toc button.active { background: #eff6ff; color: var(--blue); font-weight: 600; border-left-color: var(--blue); }

  .body { overflow-y: auto; padding: 8px 30px 60px; scroll-behavior: smooth; }
  section { padding-top: 22px; }
  section + section { border-top: 1px solid var(--border); }
  h2 { font-size: 1.2rem; margin: 8px 0 10px; color: var(--text-main); }
  h3 { font-size: 0.98rem; margin: 18px 0 8px; color: var(--text-main); }
  p, li { font-size: 13.5px; line-height: 1.62; color: #334155; }
  ul, ol { padding-left: 20px; display: flex; flex-direction: column; gap: 5px; margin: 8px 0; }
  ol.flow, ol.steps { gap: 10px; }
  ol.steps img { display: block; margin: 8px 0 2px; max-width: 420px; width: 100%; border: 1px solid var(--border); border-radius: 8px; }
  code { font-family: "JetBrains Mono", monospace; font-size: 12px; background: #f1f5f9; padding: 1px 5px; border-radius: 4px; color: #0f172a; }
  .muted { color: var(--text-sub); }

  .formula {
    font-family: "JetBrains Mono", monospace; font-size: 12.5px; color: #0f172a;
    background: #f1f5f9; border-left: 3px solid var(--blue); border-radius: 0 8px 8px 0;
    padding: 10px 14px; margin: 10px 0; overflow-x: auto;
  }
  .callout { padding: 11px 14px; border-radius: 9px; font-size: 13px; margin: 12px 0; line-height: 1.55; }
  .callout.info { background: #eff6ff; color: #1e40af; border: 1px solid #bfdbfe; }
  .callout.tip { background: #ecfdf5; color: #065f46; border: 1px solid #a7f3d0; }
  .callout.warn { background: #fffbeb; color: #92400e; border: 1px solid #fde68a; }

  table { border-collapse: collapse; width: 100%; margin: 10px 0; font-size: 12.5px; }
  th, td { text-align: left; padding: 8px 11px; border: 1px solid var(--border); vertical-align: top; }
  th { background: #f1f5f9; color: #475569; font-weight: 600; text-transform: uppercase; font-size: 10.5px; letter-spacing: 0.03em; }
  tbody tr:nth-child(even) { background: #fafcfe; }

  @media (max-width: 720px) {
    .layout { grid-template-columns: 1fr; }
    .toc { display: none; }
    .body { padding: 8px 18px 50px; }
  }
</style>
