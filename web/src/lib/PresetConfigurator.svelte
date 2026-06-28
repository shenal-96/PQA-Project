<script lang="ts">
  import type { AnalysisConfigInput, Preset } from '../config/defaults';
  import { BUILTIN_PRESETS } from '../config/defaults';
  import { capturePreset, saveCustomPreset, deleteCustomPreset, isBuiltinName } from '../config/preset_store';

  let {
    config,
    presets = $bindable([]),
    onApply,
    onClose,
  }: {
    config: AnalysisConfigInput;
    presets?: Preset[];
    onApply: (name: string) => void;
    onClose: () => void;
  } = $props();

  let newName = $state('');

  const trimmed = $derived(newName.trim());
  const nameIsBuiltin = $derived(trimmed !== '' && isBuiltinName(trimmed));
  const willOverwrite = $derived(presets.some((p) => p.name === trimmed));
  const canSave = $derived(trimmed !== '' && !nameIsBuiltin);

  function save() {
    if (!canSave) return;
    presets = saveCustomPreset(capturePreset(trimmed, config), presets);
    newName = '';
  }
  function remove(name: string) {
    presets = deleteCustomPreset(name, presets);
  }
  function apply(name: string) {
    onApply(name);
    onClose();
  }
  function onKey(e: KeyboardEvent) {
    if (e.key === 'Escape') onClose();
  }
</script>

<svelte:window onkeydown={onKey} />

<div class="overlay" onclick={(e) => { if (e.target === e.currentTarget) onClose(); }} role="presentation">
  <div class="dialog" role="dialog" aria-modal="true" aria-label="Manage Presets">
    <header>
      <div class="title">⚙ Manage Presets</div>
      <button class="close" onclick={onClose} aria-label="Close">✕</button>
    </header>

    <div class="body">
      <section>
        <h3>Save current acceptance criteria</h3>
        <p class="cap">
          Captures the current <b>Acceptance Criteria</b> settings (tolerances, recovery times,
          deviation limits, asymmetric / ISO dual-band values) as a reusable preset.
          Nominal voltage / frequency and display options are not included.
        </p>
        <div class="save-row">
          <input
            type="text"
            placeholder="Preset name (e.g. Site spec — 690 V)"
            bind:value={newName}
            onkeydown={(e) => { if (e.key === 'Enter') save(); }} />
          <button class="primary" onclick={save} disabled={!canSave}>Save preset</button>
        </div>
        {#if nameIsBuiltin}
          <div class="cap warn">“{trimmed}” is a built-in preset name — choose a different name.</div>
        {:else if willOverwrite}
          <div class="cap warn">A custom preset “{trimmed}” already exists — saving will overwrite it.</div>
        {/if}
      </section>

      <section>
        <h3>Custom presets</h3>
        {#if presets.length}
          <ul class="list">
            {#each presets as p (p.name)}
              <li>
                <span class="pname">{p.name}</span>
                <button class="apply" onclick={() => apply(p.name)}>Apply</button>
                <button class="rm" onclick={() => remove(p.name)} title="Delete {p.name}" aria-label="Delete {p.name}">✕</button>
              </li>
            {/each}
          </ul>
        {:else}
          <p class="cap empty">No custom presets yet. Configure the sidebar, then save one above.</p>
        {/if}
      </section>

      <section>
        <h3>Built-in presets</h3>
        <ul class="list">
          {#each BUILTIN_PRESETS as p (p.name)}
            <li>
              <span class="pname">{p.name}</span>
              <span class="ro">read-only</span>
              <button class="apply" onclick={() => apply(p.name)}>Apply</button>
            </li>
          {/each}
        </ul>
      </section>
    </div>
  </div>
</div>

<style>
  .overlay {
    position: fixed; inset: 0; z-index: 200;
    background: rgba(15, 23, 42, 0.55); backdrop-filter: blur(2px);
    display: grid; place-items: center; padding: clamp(8px, 4vh, 48px);
  }
  .dialog {
    width: min(560px, 100%); max-height: min(720px, 100%);
    background: var(--card, #fff); border-radius: 14px; overflow: hidden;
    display: flex; flex-direction: column;
    box-shadow: 0 24px 60px rgba(2, 6, 23, 0.45);
  }
  header {
    display: flex; align-items: center; justify-content: space-between;
    padding: 14px 18px; background: var(--navy, #0f172a); color: #fff;
  }
  .title { font-weight: 700; font-size: 16px; }
  .close { background: #1e293b; color: #cbd5e1; border: none; width: 32px; height: 32px; border-radius: 8px; font-size: 14px; cursor: pointer; }
  .close:hover { background: #334155; color: #fff; }
  .body { padding: 16px 18px 20px; overflow-y: auto; display: flex; flex-direction: column; gap: 18px; }
  section { display: flex; flex-direction: column; gap: 8px; }
  h3 { margin: 0; font-size: 13px; color: var(--text-main, #0f172a); }
  .cap { margin: 0; font-size: 12px; color: var(--text-sub, #64748b); line-height: 1.5; }
  .cap.warn { color: #b45309; }
  .cap.empty { padding: 4px 0; }
  .save-row { display: flex; gap: 8px; }
  .save-row input {
    flex: 1; border: 1px solid var(--border, #e2e8f0); border-radius: 7px; padding: 8px 10px;
    font-size: 13px; font-family: 'JetBrains Mono', monospace; color: var(--text-main, #0f172a); background: #fff;
  }
  .save-row input:focus { outline: none; border-color: var(--blue, #2563eb); }
  .primary { background: var(--blue, #2563eb); color: #fff; border: none; border-radius: 7px; padding: 8px 14px; font-size: 13px; font-weight: 600; cursor: pointer; }
  .primary:disabled { background: #cbd5e1; cursor: not-allowed; }
  .list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 6px; }
  .list li { display: flex; align-items: center; gap: 8px; background: #f8fafc; border: 1px solid var(--border, #e2e8f0); border-radius: 8px; padding: 8px 10px; }
  .pname { flex: 1; font-family: 'JetBrains Mono', monospace; font-size: 13px; font-weight: 600; color: var(--text-main, #0f172a); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .ro { font-size: 11px; color: var(--text-sub, #64748b); background: #e2e8f0; padding: 2px 8px; border-radius: 999px; }
  .apply { background: #eff6ff; color: var(--blue, #2563eb); border: 1px solid #bfdbfe; border-radius: 7px; padding: 6px 12px; font-size: 12px; font-weight: 600; cursor: pointer; }
  .apply:hover { background: #dbeafe; }
  .rm { background: #fff; border: 1px solid var(--border, #e2e8f0); border-radius: 7px; width: 32px; height: 30px; cursor: pointer; color: #b91c1c; font-size: 13px; }
  .rm:hover { background: #fee2e2; }
</style>
