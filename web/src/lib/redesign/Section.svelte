<script lang="ts">
  import type { Snippet } from 'svelte';
  import { untrack } from 'svelte';
  import Icon from './Icon.svelte';

  // Collapsible sidebar section, ported from the design (pqa-app.jsx `Section`):
  // optional accent bar + uppercase title + optional count badge + chevron.
  let {
    title,
    count = undefined,
    accent = undefined,
    open = true,
    children,
  }: {
    title: string;
    count?: string | number;
    accent?: string;
    open?: boolean;
    children: Snippet;
  } = $props();

  // `open` is the initial-only default; after mount the section owns its state.
  let isOpen = $state(untrack(() => open));
</script>

<div class="rd-sec">
  <button class="rd-sec-head" onclick={() => (isOpen = !isOpen)} aria-expanded={isOpen}>
    {#if accent}<span class="rd-sec-accent" style="background:{accent}"></span>{/if}
    <span class="rd-sec-title">{title}</span>
    {#if count != null}<span class="rd-sec-count mono">{count}</span>{/if}
    <span class="rd-sec-chev" class:closed={!isOpen}><Icon name="chevron" /></span>
  </button>
  {#if isOpen}<div class="rd-sec-body">{@render children()}</div>{/if}
</div>

<style>
  .rd-sec { border-top: 1px solid var(--line); }
  .rd-sec-head {
    width: 100%; display: flex; align-items: center; gap: 8px; padding: 13px 0 12px;
    background: transparent; border: none; cursor: pointer;
  }
  .rd-sec-accent { width: 3px; height: 12px; border-radius: 2px; flex-shrink: 0; }
  .rd-sec-title {
    font-size: 11px; font-weight: 700; letter-spacing: 0.1em; text-transform: uppercase;
    color: var(--sub);
  }
  .rd-sec-count {
    font-size: 10px; color: var(--mute); background: var(--panel-2);
    border: 1px solid var(--line); border-radius: 99px; padding: 1px 7px;
  }
  .rd-sec-chev {
    margin-left: auto; color: var(--mute); display: grid; place-items: center;
    transition: transform 0.15s;
  }
  .rd-sec-chev.closed { transform: rotate(-90deg); }
  .rd-sec-body { padding-bottom: 14px; display: flex; flex-direction: column; gap: 8px; }
</style>
