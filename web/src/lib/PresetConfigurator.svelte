<script lang="ts">
  import type { AnalysisBackend } from '../backend';
  import type { AnalysisConfigInput, Preset } from '../config/defaults';
  import { BUILTIN_PRESETS, DEFAULT_CONFIG } from '../config/defaults';
  import {
    capturePreset, isBuiltinName, persistPresets, uniqueCopyName,
  } from '../config/preset_store';

  let {
    config,
    presets = $bindable([]),
    backend,
    onApply,
    onClose,
  }: {
    config: AnalysisConfigInput;
    presets?: Preset[];
    backend?: AnalysisBackend;
    onApply: (name: string) => void;
    onClose: () => void;
  } = $props();

  // ── editable field map (the meaningful pct/seconds knobs; ISO abs bands are
  //    recomputed from beta_f/alpha_f at analysis time, so they aren't edited). ──
  type NumField = { key: string; label: string; step: number };
  const NUM_GROUPS: { title: string; fields: NumField[] }[] = [
    { title: 'Voltage', fields: [
      { key: 'voltage_tolerance_pct', label: 'Tolerance (%)', step: 0.1 },
      { key: 'voltage_recovery_time_s', label: 'Recovery (s)', step: 0.1 },
      { key: 'voltage_max_deviation_pct', label: 'Max deviation (%)', step: 0.5 },
      { key: 'volt_max_dev_pct_increase', label: 'Max dev — increase (%)', step: 0.5 },
      { key: 'volt_max_dev_pct_decrease', label: 'Max dev — decrease (%)', step: 0.5 },
    ] },
    { title: 'Frequency', fields: [
      { key: 'frequency_tolerance_pct', label: 'Tolerance (%)', step: 0.1 },
      { key: 'frequency_recovery_time_s', label: 'Recovery (s)', step: 0.1 },
      { key: 'frequency_max_deviation_pct', label: 'Max deviation (%)', step: 0.5 },
      { key: 'freq_max_dev_pct_increase', label: 'Max dev — increase (%)', step: 0.5 },
      { key: 'freq_max_dev_pct_decrease', label: 'Max dev — decrease (%)', step: 0.5 },
    ] },
    { title: 'ISO 8528-5 dual band', fields: [
      { key: 'beta_f_pct', label: 'β_f start band (±%)', step: 0.05 },
      { key: 'alpha_f_pct', label: 'α_f stop band (±%)', step: 0.05 },
    ] },
  ];
  const BOOL_FIELDS: { key: string; label: string }[] = [
    { key: 'iso_8528_5_mode', label: 'ISO 8528-5 dual frequency bands' },
    { key: 'apply_asymmetric_volt_dev', label: 'Asymmetric voltage deviation limit' },
    { key: 'apply_asymmetric_freq_dev', label: 'Asymmetric frequency deviation limit' },
    { key: 'apply_asymmetric_freq', label: 'Asymmetric frequency tolerance band' },
    { key: 'apply_asymmetric_volt', label: 'Asymmetric voltage tolerance band' },
  ];
  const NUM_KEYS = NUM_GROUPS.flatMap((g) => g.fields.map((f) => f.key));
  const DEF = DEFAULT_CONFIG as unknown as Record<string, number | boolean | string>;

  let mode = $state<'list' | 'edit'>('list');
  let newName = $state('');
  let importError = $state<string | undefined>(undefined);

  // editor state
  let editName = $state('');
  let editOriginalName = $state<string | null>(null);
  let editNums = $state<Record<string, number>>({});
  let editBools = $state<Record<string, boolean>>({});
  let editExtra = $state<Record<string, number | boolean | string>>({});

  const trimmed = $derived(newName.trim());
  const nameIsBuiltin = $derived(trimmed !== '' && isBuiltinName(trimmed));
  const willOverwrite = $derived(presets.some((p) => p.name === trimmed));
  const canQuickSave = $derived(trimmed !== '' && !nameIsBuiltin);

  const editTrimmed = $derived(editName.trim());
  const editNameBuiltin = $derived(editTrimmed !== '' && isBuiltinName(editTrimmed));
  const editCollides = $derived(
    editTrimmed !== editOriginalName && presets.some((p) => p.name === editTrimmed),
  );
  const canSaveEdit = $derived(editTrimmed !== '' && !editNameBuiltin);

  function commit(next: Preset[]) {
    presets = next;
    void persistPresets(next, backend);
  }

  function summary(p: Preset): string {
    const v = p.values as Record<string, number | boolean | undefined>;
    const parts: string[] = [];
    if (v.voltage_tolerance_pct != null) parts.push(`V tol ${v.voltage_tolerance_pct}%`);
    if (v.frequency_tolerance_pct != null) parts.push(`F tol ${v.frequency_tolerance_pct}%`);
    if (v.voltage_recovery_time_s != null && v.frequency_recovery_time_s != null)
      parts.push(`rec ${v.voltage_recovery_time_s}/${v.frequency_recovery_time_s}s`);
    if (v.iso_8528_5_mode) parts.push('ISO dual-band');
    return parts.join(' · ');
  }

  // ── quick capture from the current sidebar ──
  function quickSave() {
    if (!canQuickSave) return;
    const captured = capturePreset(trimmed, config);
    commit([...presets.filter((p) => p.name !== captured.name), captured]);
    newName = '';
  }

  // ── editor ──
  function openEditor(src: Preset | null, originalName: string | null, suggestedName: string) {
    const v = (src?.values ?? {}) as Record<string, number | boolean | string>;
    const nums: Record<string, number> = {};
    for (const k of NUM_KEYS) {
      const val = v[k];
      nums[k] = typeof val === 'number' ? val : Number(DEF[k] ?? 0);
    }
    const bools: Record<string, boolean> = {};
    for (const b of BOOL_FIELDS) {
      const val = v[b.key];
      bools[b.key] = typeof val === 'boolean' ? val : Boolean(DEF[b.key]);
    }
    editExtra = { ...(src?.values ?? {}) } as Record<string, number | boolean | string>;
    editNums = nums;
    editBools = bools;
    editOriginalName = originalName;
    editName = suggestedName;
    importError = undefined;
    mode = 'edit';
  }

  function editCustom(p: Preset) {
    openEditor(p, p.name, p.name);
  }
  function duplicate(src: Preset) {
    openEditor(src, null, uniqueCopyName(src.name, presets));
  }

  function saveEditor() {
    if (!canSaveEdit) return;
    const values: Record<string, number | boolean | string> = { ...editExtra };
    for (const k of NUM_KEYS) values[k] = editNums[k];
    for (const b of BOOL_FIELDS) values[b.key] = editBools[b.key];
    if (values.band_mode == null) values.band_mode = 'pct'; // keep β_f/α_f driving the engine
    const draft: Preset = { name: editTrimmed, values: values as Preset['values'] };
    let next = editOriginalName ? presets.filter((p) => p.name !== editOriginalName) : presets.slice();
    next = next.filter((p) => p.name !== draft.name); // replace any same-named
    commit([...next, draft]);
    mode = 'list';
  }

  function remove(name: string) {
    commit(presets.filter((p) => p.name !== name));
  }
  function apply(name: string) {
    onApply(name);
    onClose();
  }

  // ── export / import ──
  function exportPresets() {
    const json = JSON.stringify(presets, null, 2);
    if (backend?.saveFile) {
      const b64 = btoa(unescape(encodeURIComponent(json)));
      void backend.saveFile('pqa_presets.json', b64);
      return;
    }
    const url = URL.createObjectURL(new Blob([json], { type: 'application/json' }));
    const a = document.createElement('a');
    a.href = url;
    a.download = 'pqa_presets.json';
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  function looksLikePreset(p: unknown): p is Preset {
    return (
      !!p &&
      typeof (p as Preset).name === 'string' &&
      !!(p as Preset).values &&
      typeof (p as Preset).values === 'object'
    );
  }

  async function onImport(ev: Event) {
    const input = ev.target as HTMLInputElement;
    const file = input.files?.[0];
    input.value = '';
    if (!file) return;
    try {
      const parsed: unknown = JSON.parse(await file.text());
      const incoming = (Array.isArray(parsed) ? parsed : []).filter(looksLikePreset);
      if (!incoming.length) {
        importError = 'No valid presets found in that file.';
        return;
      }
      const byName = new Map(presets.map((p) => [p.name, p]));
      let added = 0;
      for (const p of incoming) {
        if (isBuiltinName(p.name)) continue; // never shadow a built-in name
        byName.set(p.name.trim(), { name: p.name.trim(), values: { ...p.values } });
        added += 1;
      }
      commit([...byName.values()]);
      importError = added ? undefined : 'Those presets use built-in names — nothing imported.';
    } catch {
      importError = 'Could not read that file as preset JSON.';
    }
  }

  function onKey(e: KeyboardEvent) {
    if (e.key === 'Escape') {
      if (mode === 'edit') mode = 'list';
      else onClose();
    }
  }
</script>

<svelte:window onkeydown={onKey} />

<div class="overlay" onclick={(e) => { if (e.target === e.currentTarget) onClose(); }} role="presentation">
  <div class="dialog" role="dialog" aria-modal="true" aria-label="Manage Presets">
    <header>
      <div class="title">
        {#if mode === 'edit'}
          <button class="back" onclick={() => (mode = 'list')} aria-label="Back to preset list">←</button>
          {editOriginalName ? 'Edit preset' : 'New preset'}
        {:else}
          ⚙ Manage Presets
        {/if}
      </div>
      <button class="close" onclick={onClose} aria-label="Close">✕</button>
    </header>

    {#if mode === 'list'}
      <div class="body">
        <!-- Quick capture -->
        <section>
          <h3>Save current sidebar settings</h3>
          <p class="cap">
            Snapshots the current <b>Acceptance Criteria</b> as a reusable preset.
            Nominal voltage / frequency and display options are not included.
          </p>
          <div class="save-row">
            <input
              type="text"
              placeholder="Preset name (e.g. Site spec — 690 V)"
              bind:value={newName}
              onkeydown={(e) => { if (e.key === 'Enter') quickSave(); }} />
            <button class="primary" onclick={quickSave} disabled={!canQuickSave}>Save</button>
          </div>
          {#if nameIsBuiltin}
            <div class="cap warn">“{trimmed}” is a built-in preset name — choose a different name.</div>
          {:else if willOverwrite}
            <div class="cap warn">A custom preset “{trimmed}” already exists — saving overwrites it.</div>
          {/if}
        </section>

        <!-- Custom presets -->
        <section>
          <div class="sec-head">
            <h3>Custom presets</h3>
            <div class="io">
              <button class="ghost" onclick={exportPresets} disabled={!presets.length} title="Export all custom presets to a JSON file">⤓ Export</button>
              <label class="ghost file" title="Import presets from a JSON file">⤒ Import
                <input type="file" accept=".json,application/json" onchange={onImport} hidden />
              </label>
            </div>
          </div>
          {#if importError}<div class="cap warn">{importError}</div>{/if}
          {#if presets.length}
            <ul class="list">
              {#each presets as p (p.name)}
                <li>
                  <div class="info">
                    <span class="pname">{p.name}</span>
                    <span class="psum">{summary(p)}</span>
                  </div>
                  <button class="apply" onclick={() => apply(p.name)}>Apply</button>
                  <button class="act" onclick={() => editCustom(p)} title="Edit {p.name}">Edit</button>
                  <button class="act" onclick={() => duplicate(p)} title="Duplicate {p.name}">Duplicate</button>
                  <button class="rm" onclick={() => remove(p.name)} title="Delete {p.name}" aria-label="Delete {p.name}">✕</button>
                </li>
              {/each}
            </ul>
          {:else}
            <p class="cap empty">No custom presets yet. Save the sidebar above, or duplicate a built-in below.</p>
          {/if}
        </section>

        <!-- Built-ins -->
        <section>
          <h3>Built-in presets</h3>
          <ul class="list">
            {#each BUILTIN_PRESETS as p (p.name)}
              <li>
                <div class="info">
                  <span class="pname">{p.name}</span>
                  <span class="psum">{summary(p)}</span>
                </div>
                <span class="ro">read-only</span>
                <button class="apply" onclick={() => apply(p.name)}>Apply</button>
                <button class="act" onclick={() => duplicate(p)} title="Duplicate {p.name} to customize">Duplicate</button>
              </li>
            {/each}
          </ul>
        </section>
      </div>
    {:else}
      <!-- Editor -->
      <div class="body">
        <section>
          <label class="field name-field">Preset name
            <input type="text" bind:value={editName} placeholder="Preset name" />
          </label>
          {#if editNameBuiltin}
            <div class="cap warn">That's a built-in preset name — choose a different name.</div>
          {:else if editCollides}
            <div class="cap warn">A custom preset “{editTrimmed}” already exists — saving overwrites it.</div>
          {/if}
        </section>

        {#each NUM_GROUPS as grp}
          <section>
            <h3>{grp.title}</h3>
            <div class="grid">
              {#each grp.fields as f}
                <label class="field">{f.label}
                  <input type="number" step={f.step} bind:value={editNums[f.key]} />
                </label>
              {/each}
            </div>
          </section>
        {/each}

        <section>
          <h3>Options</h3>
          <div class="bools">
            {#each BOOL_FIELDS as b}
              <label class="chk"><input type="checkbox" bind:checked={editBools[b.key]} /> {b.label}</label>
            {/each}
          </div>
        </section>
      </div>
      <footer class="edit-actions">
        <button class="ghost" onclick={() => (mode = 'list')}>Cancel</button>
        <button class="primary" onclick={saveEditor} disabled={!canSaveEdit}>Save preset</button>
      </footer>
    {/if}
  </div>
</div>

<style>
  .overlay {
    position: fixed; inset: 0; z-index: 200;
    background: rgba(15, 23, 42, 0.55); backdrop-filter: blur(2px);
    display: grid; place-items: center; padding: clamp(8px, 4vh, 48px);
  }
  .dialog {
    width: min(620px, 100%); max-height: min(760px, 100%);
    background: var(--card, #fff); border-radius: 14px; overflow: hidden;
    display: flex; flex-direction: column;
    box-shadow: 0 24px 60px rgba(2, 6, 23, 0.45);
  }
  header {
    display: flex; align-items: center; justify-content: space-between;
    padding: 14px 18px; background: var(--navy, #0f172a); color: #fff;
  }
  .title { font-weight: 700; font-size: 16px; display: flex; align-items: center; gap: 8px; }
  .back { background: #1e293b; color: #cbd5e1; border: none; width: 28px; height: 28px; border-radius: 8px; font-size: 15px; cursor: pointer; line-height: 1; }
  .back:hover { background: #334155; color: #fff; }
  .close { background: #1e293b; color: #cbd5e1; border: none; width: 32px; height: 32px; border-radius: 8px; font-size: 14px; cursor: pointer; }
  .close:hover { background: #334155; color: #fff; }
  .body { padding: 16px 18px 20px; overflow-y: auto; display: flex; flex-direction: column; gap: 18px; }
  section { display: flex; flex-direction: column; gap: 8px; }
  .sec-head { display: flex; align-items: center; justify-content: space-between; }
  h3 { margin: 0; font-size: 13px; color: var(--text-main, #0f172a); }
  .cap { margin: 0; font-size: 12px; color: var(--text-sub, #64748b); line-height: 1.5; }
  .cap.warn { color: #b45309; }
  .cap.empty { padding: 4px 0; }
  .save-row { display: flex; gap: 8px; }
  .save-row input, .name-field input {
    flex: 1; border: 1px solid var(--border, #e2e8f0); border-radius: 7px; padding: 8px 10px;
    font-size: 13px; font-family: 'JetBrains Mono', monospace; color: var(--text-main, #0f172a); background: #fff; width: 100%;
  }
  .save-row input:focus, .field input:focus { outline: none; border-color: var(--blue, #2563eb); }
  .primary { background: var(--blue, #2563eb); color: #fff; border: none; border-radius: 7px; padding: 8px 14px; font-size: 13px; font-weight: 600; cursor: pointer; }
  .primary:disabled { background: #cbd5e1; cursor: not-allowed; }
  .ghost { background: #fff; border: 1px solid var(--border, #e2e8f0); border-radius: 7px; padding: 7px 12px; font-size: 12px; font-weight: 600; color: var(--text-main, #0f172a); cursor: pointer; }
  .ghost:hover:not(:disabled) { background: #f1f5f9; }
  .ghost:disabled { color: #94a3b8; cursor: not-allowed; }
  .io { display: flex; gap: 6px; }
  .file { display: inline-flex; align-items: center; cursor: pointer; }
  .list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 6px; }
  .list li { display: flex; align-items: center; gap: 8px; background: #f8fafc; border: 1px solid var(--border, #e2e8f0); border-radius: 8px; padding: 8px 10px; }
  .info { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 1px; }
  .pname { font-family: 'JetBrains Mono', monospace; font-size: 13px; font-weight: 600; color: var(--text-main, #0f172a); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .psum { font-size: 11px; color: var(--text-sub, #64748b); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .ro { font-size: 11px; color: var(--text-sub, #64748b); background: #e2e8f0; padding: 2px 8px; border-radius: 999px; }
  .apply { background: #eff6ff; color: var(--blue, #2563eb); border: 1px solid #bfdbfe; border-radius: 7px; padding: 6px 12px; font-size: 12px; font-weight: 600; cursor: pointer; }
  .apply:hover { background: #dbeafe; }
  .act { background: #fff; border: 1px solid var(--border, #e2e8f0); border-radius: 7px; padding: 6px 10px; font-size: 12px; font-weight: 600; color: var(--text-main, #0f172a); cursor: pointer; }
  .act:hover { background: #f1f5f9; }
  .rm { background: #fff; border: 1px solid var(--border, #e2e8f0); border-radius: 7px; width: 32px; height: 30px; cursor: pointer; color: #b91c1c; font-size: 13px; }
  .rm:hover { background: #fee2e2; }
  .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px 12px; }
  .field { display: flex; flex-direction: column; gap: 4px; font-size: 12px; color: var(--text-sub, #64748b); }
  .field input[type='number'] { border: 1px solid var(--border, #e2e8f0); border-radius: 7px; padding: 7px 9px; font-size: 13px; font-family: 'JetBrains Mono', monospace; color: var(--text-main, #0f172a); background: #fff; }
  .bools { display: flex; flex-direction: column; gap: 7px; }
  .chk { display: flex; align-items: center; gap: 7px; font-size: 13px; color: var(--text-main, #0f172a); }
  .edit-actions { display: flex; justify-content: flex-end; gap: 8px; padding: 12px 18px; border-top: 1px solid var(--border, #e2e8f0); background: #f8fafc; }
</style>
