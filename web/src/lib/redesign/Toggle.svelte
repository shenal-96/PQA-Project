<script lang="ts">
  import InfoTip from '../InfoTip.svelte';

  // Switch-style toggle row, ported from the design (pqa-app.jsx `Switch` +
  // `ToggleRow`). Wraps a native checkbox so `bind:checked` keeps wiring parity
  // with the classic sidebar's `<input type="checkbox">`.
  let {
    checked = $bindable(false),
    label,
    hint = undefined,
    tip = undefined,
    disabled = false,
    nested = false,
  }: {
    checked?: boolean;
    label: string;
    hint?: string;
    tip?: string;
    disabled?: boolean;
    nested?: boolean;
  } = $props();
</script>

<label class="rd-toggle" class:nested class:disabled>
  <span class="rd-toggle-text">
    <span class="rd-toggle-label">{label}{#if tip} <InfoTip text={tip} />{/if}</span>
    {#if hint}<span class="rd-toggle-hint">{hint}</span>{/if}
  </span>
  <input type="checkbox" bind:checked {disabled} />
  <span class="rd-switch" class:on={checked} aria-hidden="true"><span class="rd-knob"></span></span>
</label>

<style>
  .rd-toggle {
    display: flex; align-items: center; gap: 10px; padding: 7px 0; cursor: pointer;
  }
  .rd-toggle.nested { margin-left: 16px; }
  .rd-toggle.disabled { opacity: 0.5; cursor: not-allowed; }
  .rd-toggle-text { flex: 1; min-width: 0; display: flex; flex-direction: column; }
  .rd-toggle-label { font-size: 12.5px; color: var(--ink); }
  .rd-toggle-hint { font-size: 10.5px; color: var(--mute); margin-top: 1px; }
  /* Hide the native control but keep it accessible + the binding source. */
  .rd-toggle input { position: absolute; opacity: 0; width: 0; height: 0; pointer-events: none; }
  .rd-switch {
    width: 30px; height: 18px; border-radius: 99px; flex-shrink: 0; position: relative;
    background: #1d293f; border: 1px solid #2a3a57;
    transition: background 0.15s, border-color 0.15s;
  }
  .rd-switch.on { background: var(--blue); border-color: var(--blue); }
  .rd-knob {
    position: absolute; top: 1.5px; left: 1.5px; width: 13px; height: 13px;
    border-radius: 99px; background: #fff; box-shadow: 0 1px 2px rgba(0, 0, 0, 0.4);
    transition: left 0.15s;
  }
  .rd-switch.on .rd-knob { left: 13px; }
  .rd-toggle input:focus-visible + .rd-switch { outline: 2px solid var(--blue); outline-offset: 2px; }
</style>
