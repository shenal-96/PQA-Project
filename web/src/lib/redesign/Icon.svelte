<script lang="ts">
  // Inline SVG icons for the redesign UI, ported verbatim from the design source
  // (docs/redesign/reference/pqa-app.jsx, the `Ic` map). `currentColor` driven,
  // so colour comes from the parent's `color`. Used by the top bar (Phase 2) and
  // the sidebar (Phase 3).
  type IconName =
    | 'bolt' | 'scope' | 'wrench' | 'chart' | 'book' | 'help'
    | 'chevron' | 'reset' | 'file' | 'swap' | 'clock';

  let { name, size }: { name: IconName; size?: number } = $props();

  const DEFAULT_SIZE: Record<IconName, number> = {
    bolt: 16, scope: 15, wrench: 15, chart: 15, book: 15, help: 14,
    chevron: 14, reset: 13, file: 15, swap: 13, clock: 13,
  };
  const s = $derived(size ?? DEFAULT_SIZE[name]);
</script>

{#if name === 'bolt'}
  <svg viewBox="0 0 24 24" width={s} height={s} fill="currentColor"><path d="M13 2 4 14h6l-1 8 9-12h-6l1-8z" /></svg>
{:else if name === 'scope'}
  <svg viewBox="0 0 24 24" width={s} height={s} fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12h4l2 6 4-14 2 8h6" /></svg>
{:else if name === 'wrench'}
  <svg viewBox="0 0 24 24" width={s} height={s} fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14.7 6.3a4 4 0 0 0-5 5L4 17l3 3 5.7-5.7a4 4 0 0 0 5-5l-2.5 2.5-2-2 2.5-2.5z" /></svg>
{:else if name === 'chart'}
  <svg viewBox="0 0 24 24" width={s} height={s} fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2" /><path d="M7 15l3-4 2 2 4-6" /></svg>
{:else if name === 'book'}
  <svg viewBox="0 0 24 24" width={s} height={s} fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 5a2 2 0 0 1 2-2h12v16H6a2 2 0 0 0-2 2z" /><path d="M4 5v16" /></svg>
{:else if name === 'help'}
  <svg viewBox="0 0 24 24" width={s} height={s} fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9" /><path d="M9.5 9a2.5 2.5 0 1 1 3.5 2.3c-.8.4-1 .9-1 1.7" /><circle cx="12" cy="16.5" r="0.6" fill="currentColor" /></svg>
{:else if name === 'chevron'}
  <svg viewBox="0 0 24 24" width={s} height={s} fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 9l6 6 6-6" /></svg>
{:else if name === 'reset'}
  <svg viewBox="0 0 24 24" width={s} height={s} fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12a9 9 0 1 0 3-6.7L3 8" /><path d="M3 3v5h5" /></svg>
{:else if name === 'file'}
  <svg viewBox="0 0 24 24" width={s} height={s} fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" /><path d="M14 3v5h5" /></svg>
{:else if name === 'swap'}
  <svg viewBox="0 0 24 24" width={s} height={s} fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M7 7h11l-3-3M17 17H6l3 3" /></svg>
{:else if name === 'clock'}
  <svg viewBox="0 0 24 24" width={s} height={s} fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></svg>
{/if}

<style>
  svg { display: block; flex-shrink: 0; }
</style>
