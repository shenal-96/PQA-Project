<script lang="ts">
  import { tick } from 'svelte';

  // A small "?" icon that reveals a description on hover / focus — the desktop
  // equivalent of Streamlit's per-widget `help=` tooltips. The bubble is
  // portaled to <body> and fixed-positioned so the scrolling, overflow-clipped
  // sidebar never crops it; it flips to the other side and clamps to the
  // viewport when there isn't room.
  let {
    text,
    size = 15,
  }: { text: string; size?: number } = $props();

  let open = $state(false);
  let positioned = $state(false); // gates the fade-in until placement is known
  let anchor = $state<HTMLButtonElement>();
  let tipEl = $state<HTMLDivElement>();
  let x = $state(0);
  let y = $state(0);
  let flip = $state(false); // placed to the left of the icon

  const GAP = 10; // space between the icon and the bubble
  const PAD = 8; // keep the bubble this far from the viewport edges

  async function place() {
    if (!anchor) return;
    await tick(); // let the bubble mount so we can measure it
    const a = anchor.getBoundingClientRect();
    const t = tipEl?.getBoundingClientRect();
    const tw = t?.width ?? 260;
    const th = t?.height ?? 40;

    // Horizontal: prefer the right of the icon, flip left if it would overflow.
    let left = a.right + GAP;
    let placeLeft = false;
    if (left + tw + PAD > window.innerWidth) {
      left = a.left - GAP - tw;
      placeLeft = true;
      if (left < PAD) left = PAD;
    }
    // Vertical: centre on the icon, clamped to the viewport.
    let top = a.top + a.height / 2 - th / 2;
    top = Math.max(PAD, Math.min(top, window.innerHeight - th - PAD));

    x = left;
    y = top;
    flip = placeLeft;
    positioned = true;
  }

  async function show() {
    if (open) return;
    open = true;
    positioned = false;
    await place();
  }
  function hide() {
    open = false;
    positioned = false;
  }
  function toggle(e: MouseEvent) {
    e.preventDefault();
    e.stopPropagation();
    open ? hide() : show();
  }

  // While open, dismiss on scroll/resize and Escape so the bubble never floats
  // detached from its icon.
  $effect(() => {
    if (!open) return;
    const dismiss = () => hide();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') hide();
    };
    window.addEventListener('scroll', dismiss, true);
    window.addEventListener('resize', dismiss);
    window.addEventListener('keydown', onKey);
    return () => {
      window.removeEventListener('scroll', dismiss, true);
      window.removeEventListener('resize', dismiss);
      window.removeEventListener('keydown', onKey);
    };
  });

  // Move the bubble to <body> so no ancestor's overflow / stacking context clips it.
  function portal(node: HTMLElement) {
    document.body.appendChild(node);
    return {
      destroy() {
        node.remove();
      },
    };
  }
</script>

<button
  bind:this={anchor}
  type="button"
  class="tip-btn"
  style="--sz:{size}px"
  aria-label={text}
  onmouseenter={show}
  onmouseleave={hide}
  onfocus={show}
  onblur={hide}
  onclick={toggle}>?</button>

{#if open}
  <div
    bind:this={tipEl}
    use:portal
    class="tip"
    class:flip
    class:show={positioned}
    style="left:{x}px; top:{y}px"
    aria-hidden="true"
  >
    {text}
  </div>
{/if}

<style>
  .tip-btn {
    width: var(--sz, 15px);
    height: var(--sz, 15px);
    min-width: var(--sz, 15px);
    flex: 0 0 auto;
    display: inline-grid;
    place-items: center;
    border-radius: 50%;
    border: 1px solid #475569;
    background: transparent;
    color: #94a3b8;
    font-size: calc(var(--sz, 15px) * 0.72);
    font-weight: 700;
    line-height: 1;
    padding: 0;
    cursor: help;
    vertical-align: middle;
    font-family: Inter, -apple-system, sans-serif;
    transition: background 0.12s, border-color 0.12s, color 0.12s;
  }
  .tip-btn:hover,
  .tip-btn:focus-visible {
    background: var(--blue, #2563eb);
    border-color: var(--blue, #2563eb);
    color: #fff;
    outline: none;
  }

  /* Portaled to <body>: scoped via Svelte's hash class, styled from scratch. */
  .tip {
    position: fixed;
    z-index: 9999;
    max-width: 280px;
    background: #ffffff;
    color: #0f172a;
    border: 1px solid #cbd5e1;
    border-radius: 8px;
    padding: 9px 11px;
    font-size: 12px;
    line-height: 1.5;
    font-family: Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    box-shadow: 0 10px 30px rgba(2, 6, 23, 0.35);
    pointer-events: none;
    white-space: normal;
    opacity: 0;
    transform: translateX(-4px);
    transition: opacity 0.1s ease, transform 0.1s ease;
  }
  .tip.flip {
    transform: translateX(4px);
  }
  .tip.show {
    opacity: 1;
    transform: translateX(0);
  }
</style>
