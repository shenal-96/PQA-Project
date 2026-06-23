<script lang="ts">
  // Dual-handle time-range slider. Operates in whole seconds from the file's
  // start; reads/writes `start`/`end` as datetime-local strings
  // (YYYY-MM-DDTHH:MM:SS), where '' means "open" (the file's min/max). Built from
  // two overlapping native range inputs so it needs no external dependency and
  // stays keyboard-accessible.

  let {
    min,
    max,
    start = $bindable(''),
    end = $bindable(''),
    step = 1,
  }: {
    min: string;            // ISO datetime, file start
    max: string;            // ISO datetime, file end
    start?: string;
    end?: string;
    step?: number;          // seconds
  } = $props();

  const minMs = $derived(new Date(min).getTime());
  const maxMs = $derived(new Date(max).getTime());
  const total = $derived(Math.max(0, Math.round((maxMs - minMs) / 1000)));
  const multiDay = $derived(new Date(minMs).toDateString() !== new Date(maxMs).toDateString());

  // Controlled positions derived from the bound strings ('' → the open edge).
  const startSec = $derived(start ? clamp(secOf(start)) : 0);
  const endSec = $derived(end ? clamp(secOf(end)) : total);

  function clamp(s: number): number {
    return Math.max(0, Math.min(total, s));
  }
  function secOf(local: string): number {
    return Math.round((new Date(local).getTime() - minMs) / 1000);
  }
  function toLocal(sec: number): string {
    // Local-time YYYY-MM-DDTHH:MM:SS (matches datetime-local + tz-naive backend).
    const d = new Date(minMs + sec * 1000);
    const p = (n: number) => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
  }
  function label(sec: number): string {
    const d = new Date(minMs + sec * 1000);
    const p = (n: number) => String(n).padStart(2, '0');
    const t = `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
    return multiDay ? `${p(d.getDate())}/${p(d.getMonth() + 1)} ${t}` : t;
  }

  const pct = (sec: number): number => (total > 0 ? (sec / total) * 100 : 0);

  function onStart(e: Event) {
    const v = clamp(Number((e.target as HTMLInputElement).value));
    const s = Math.min(v, endSec); // never cross the end thumb
    start = s <= 0 ? '' : toLocal(s);
  }
  function onEnd(e: Event) {
    const v = clamp(Number((e.target as HTMLInputElement).value));
    const s = Math.max(v, startSec); // never cross the start thumb
    end = s >= total ? '' : toLocal(s);
  }
</script>

<div class="trs">
  <div class="labels">
    <span class="lbl">{label(startSec)}</span>
    <span class="dash">→</span>
    <span class="lbl">{label(endSec)}</span>
  </div>

  <div class="rail" class:disabled={total <= 0}>
    <div class="track"></div>
    <div class="fill" style="left:{pct(startSec)}%; right:{100 - pct(endSec)}%"></div>
    <input
      class="thumb start"
      type="range" min="0" max={total} {step}
      value={startSec} oninput={onStart}
      aria-label="Window start"
      style="z-index:{startSec > total - startSec ? 4 : 3}"
    />
    <input
      class="thumb end"
      type="range" min="0" max={total} {step}
      value={endSec} oninput={onEnd}
      aria-label="Window end"
    />
  </div>
</div>

<style>
  .trs { display: flex; flex-direction: column; gap: 8px; }
  .labels { display: flex; align-items: center; justify-content: space-between; gap: 6px; font-family: "JetBrains Mono", monospace; font-size: 12px; color: #e2e8f0; }
  .labels .dash { color: #64748b; }
  .lbl { background: #0b1220; border: 1px solid #1e293b; border-radius: 6px; padding: 2px 8px; }

  .rail { position: relative; height: 28px; display: flex; align-items: center; }
  .rail.disabled { opacity: 0.4; pointer-events: none; }
  .track { position: absolute; left: 0; right: 0; height: 4px; background: #1e293b; border-radius: 999px; }
  .fill { position: absolute; height: 4px; background: var(--blue); border-radius: 999px; }

  /* Two overlapping range inputs: the input itself is transparent and
     non-interactive, only the thumbs catch the pointer so both can be grabbed. */
  .thumb {
    position: absolute;
    left: 0; right: 0; width: 100%;
    margin: 0; padding: 0;
    background: none; -webkit-appearance: none; appearance: none;
    pointer-events: none;
  }
  .thumb:focus { outline: none; }
  .thumb::-webkit-slider-thumb {
    -webkit-appearance: none; appearance: none;
    width: 16px; height: 16px; border-radius: 50%;
    background: #fff; border: 2px solid var(--blue);
    cursor: pointer; pointer-events: auto;
    box-shadow: 0 1px 3px rgba(0,0,0,0.4);
  }
  .thumb::-moz-range-thumb {
    width: 16px; height: 16px; border-radius: 50%;
    background: #fff; border: 2px solid var(--blue);
    cursor: pointer; pointer-events: auto;
  }
  .thumb:focus::-webkit-slider-thumb { border-color: #60a5fa; box-shadow: 0 0 0 3px rgba(37,99,235,0.35); }
  .thumb::-webkit-slider-runnable-track { background: none; }
  .thumb::-moz-range-track { background: none; }
</style>
