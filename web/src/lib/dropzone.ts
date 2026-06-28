// Reusable drag-and-drop file action for Svelte.
//
// Usage:
//   <div use:dropzone={{ onDrop, onActive, disabled }} class:drag-active={active}>
//
// The action only reports events — it calls `onActive(true/false)` so the host
// can highlight the zone, and `onDrop(files)` with the dropped File[]. The host
// decides how to consume them (e.g. inject into a hidden <input> and dispatch a
// `change` event so existing upload handlers run unchanged). Drag events that
// don't carry files (text selections, etc.) are ignored.

export interface DropzoneOptions {
  onDrop: (files: File[]) => void;
  /** Called with `true` while files are dragged over the zone, `false` otherwise. */
  onActive?: (active: boolean) => void;
  disabled?: boolean;
}

export function dropzone(node: HTMLElement, options: DropzoneOptions) {
  let opts = options;
  // dragenter/dragleave fire for child elements too; count depth so the active
  // state only clears when the pointer truly leaves the zone.
  let depth = 0;

  const carriesFiles = (e: DragEvent): boolean =>
    Array.from(e.dataTransfer?.types ?? []).includes('Files');

  function setActive(active: boolean) {
    opts.onActive?.(active);
  }

  function onEnter(e: DragEvent) {
    if (opts.disabled || !carriesFiles(e)) return;
    e.preventDefault();
    depth += 1;
    setActive(true);
  }
  function onOver(e: DragEvent) {
    if (opts.disabled || !carriesFiles(e)) return;
    e.preventDefault(); // required for `drop` to fire
    if (e.dataTransfer) e.dataTransfer.dropEffect = 'copy';
  }
  function onLeave(_e: DragEvent) {
    if (opts.disabled) return;
    depth = Math.max(0, depth - 1);
    if (depth === 0) setActive(false);
  }
  function onDrop(e: DragEvent) {
    depth = 0;
    setActive(false);
    if (opts.disabled) return;
    const files = Array.from(e.dataTransfer?.files ?? []);
    if (!files.length) return;
    e.preventDefault();
    opts.onDrop(files);
  }

  node.addEventListener('dragenter', onEnter);
  node.addEventListener('dragover', onOver);
  node.addEventListener('dragleave', onLeave);
  node.addEventListener('drop', onDrop);

  return {
    update(next: DropzoneOptions) {
      opts = next;
    },
    destroy() {
      node.removeEventListener('dragenter', onEnter);
      node.removeEventListener('dragover', onOver);
      node.removeEventListener('dragleave', onLeave);
      node.removeEventListener('drop', onDrop);
    },
  };
}

/**
 * Build a `change`-event injector for a hidden file `<input>`: writes the given
 * files into the input via a DataTransfer and dispatches `change`, so an
 * existing `onchange` upload handler runs exactly as if the files were picked.
 */
export function injectFiles(input: HTMLInputElement | undefined, files: File[]): void {
  if (!input || !files.length) return;
  const dt = new DataTransfer();
  for (const f of files) dt.items.add(f);
  input.files = dt.files;
  input.dispatchEvent(new Event('change', { bubbles: true }));
}
