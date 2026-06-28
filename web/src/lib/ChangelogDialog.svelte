<script lang="ts">
  import type { AnalysisBackend } from '../backend';
  import type { FeedbackKind, FeedbackResult } from '../backend/types';
  import { APP_VERSION, CHANGELOG, DEVELOPER_EMAIL } from '../config/changelog';

  let { onClose, backend }: { onClose: () => void; backend?: AnalysisBackend } = $props();

  // 'log' = version history; 'feature'/'bug' = the feedback form.
  let mode = $state<'log' | FeedbackKind>('log');
  let message = $state('');
  let sending = $state(false);
  let result = $state<FeedbackResult | null>(null);

  const isFeedback = $derived(mode === 'feature' || mode === 'bug');
  const canSend = $derived(message.trim().length > 0 && !sending);

  function openForm(kind: FeedbackKind) {
    mode = kind;
    message = '';
    result = null;
  }

  function backToLog() {
    mode = 'log';
    result = null;
  }

  function buildMailto(kind: FeedbackKind, text: string): string {
    const label = kind === 'bug' ? 'Bug report' : 'Feature request';
    const subject = `PQA Desktop — ${label}`;
    const body = `${label} for PQA Desktop (${APP_VERSION}):\n\n${text}\n\n---\nSent from the PQA Desktop app.`;
    return `mailto:${DEVELOPER_EMAIL}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;
  }

  async function send() {
    if (!canSend || mode === 'log') return;
    const kind = mode;
    const text = message.trim();
    sending = true;
    try {
      if (backend?.sendFeedback) {
        // Desktop: Python opens the user's mail client (reliable inside WebView2).
        result = await backend.sendFeedback(kind, text);
      } else {
        // Browser / mock dev: open a plain mailto: ourselves.
        const opened = !!window.open(buildMailto(kind, text), '_blank');
        result = { ok: true, email: DEVELOPER_EMAIL, mailto_opened: opened };
      }
    } catch (e) {
      result = {
        ok: false,
        email: DEVELOPER_EMAIL,
        mailto_opened: false,
        error: e instanceof Error ? e.message : String(e),
      };
    } finally {
      sending = false;
    }
  }

  function onKey(e: KeyboardEvent) {
    if (e.key === 'Escape') onClose();
  }

  const formTitle = $derived(mode === 'bug' ? 'Report a bug' : 'Request a feature');
  const formHint = $derived(
    mode === 'bug'
      ? 'Describe what went wrong — what you did, what you expected, and what happened instead.'
      : "Describe the feature you'd like and the problem it would solve for you.",
  );
</script>

<svelte:window on:keydown={onKey} />

<div class="overlay" onclick={(e) => { if (e.target === e.currentTarget) onClose(); }} role="presentation">
  <div class="dialog" role="dialog" aria-modal="true" aria-label="Version history and feedback" tabindex="-1">
    <header>
      <div class="title">
        {#if isFeedback}
          <button class="back" onclick={backToLog} aria-label="Back to version history">←</button>
          <span class="icon">{mode === 'bug' ? '🐞' : '✨'}</span> {formTitle}
        {:else}
          <span class="icon">🗒️</span> What's new <span class="ver">{APP_VERSION}</span>
        {/if}
      </div>
      <button class="close" onclick={onClose} aria-label="Close">✕</button>
    </header>

    {#if !isFeedback}
      <!-- ---- Version history ---- -->
      <div class="body">
        <ol class="releases">
          {#each CHANGELOG as rel, i}
            <li class="release" class:latest={i === 0}>
              <div class="rel-head">
                <span class="rel-ver">{rel.version}</span>
                {#if i === 0}<span class="badge-current">Current</span>{/if}
                <span class="rel-date">{rel.date}</span>
              </div>
              {#if rel.title}<div class="rel-title">{rel.title}</div>{/if}
              <ul class="changes">
                {#each rel.changes as c}
                  <li class="change">
                    <span class="tag {c.kind}">{c.kind === 'feature' ? 'New' : 'Fix'}</span>
                    <span class="change-text">{c.text}</span>
                  </li>
                {/each}
              </ul>
            </li>
          {/each}
        </ol>
      </div>
      <footer class="actions">
        <span class="prompt">Have an idea or hit a problem?</span>
        <div class="action-btns">
          <button class="btn feature" onclick={() => openForm('feature')}>✨ Request a feature</button>
          <button class="btn bug" onclick={() => openForm('bug')}>🐞 Report a bug</button>
        </div>
      </footer>
    {:else}
      <!-- ---- Feedback form ---- -->
      <div class="body form">
        {#if result}
          {#if result.ok && result.mailto_opened}
            <div class="callout ok">
              <strong>✓ Your email app is opening.</strong>
              A draft addressed to <code>{result.email}</code> has been prepared — review it and hit send.
            </div>
          {:else if result.ok}
            <div class="callout warn">
              Couldn't open your email app automatically. Please send your message to
              <code>{result.email}</code> manually.
            </div>
          {:else}
            <div class="callout warn">
              Something went wrong{result.error ? `: ${result.error}` : ''}. You can email
              <code>{result.email}</code> directly.
            </div>
          {/if}
          <div class="form-actions">
            <button class="btn ghost" onclick={backToLog}>Back to what's new</button>
            <button class="btn primary" onclick={onClose}>Close</button>
          </div>
        {:else}
          <p class="hint">{formHint}</p>
          <textarea
            bind:value={message}
            placeholder={mode === 'bug'
              ? 'e.g. After loading a Miro CSV and clicking Run Analysis, the frequency plot is blank…'
              : "e.g. It would help to export the compliance table to Excel…"}
            rows="8"
            aria-label={formTitle}
          ></textarea>
          <p class="dest">Sends to <code>{DEVELOPER_EMAIL}</code> via your email app — nothing is sent automatically.</p>
          <div class="form-actions">
            <button class="btn ghost" onclick={backToLog} disabled={sending}>Cancel</button>
            <button class="btn primary" onclick={send} disabled={!canSend}>
              {sending ? 'Opening email…' : `Send ${mode === 'bug' ? 'bug report' : 'request'}`}
            </button>
          </div>
        {/if}
      </div>
    {/if}
  </div>
</div>

<style>
  .overlay {
    position: fixed; inset: 0; z-index: 100;
    background: rgba(15, 23, 42, 0.55); backdrop-filter: blur(2px);
    display: grid; place-items: center; padding: clamp(8px, 3vh, 40px);
  }
  .dialog {
    width: min(640px, 100%); height: min(720px, 100%);
    background: var(--card, #fff); border-radius: 14px; overflow: hidden;
    display: flex; flex-direction: column;
    box-shadow: 0 24px 60px rgba(2, 6, 23, 0.45);
  }
  header {
    display: flex; align-items: center; justify-content: space-between;
    padding: 14px 18px; background: var(--navy); color: #fff;
  }
  header .title { display: flex; align-items: center; gap: 8px; font-weight: 800; letter-spacing: -0.01em; }
  header .icon { font-size: 17px; }
  header .ver { font-size: 11px; font-weight: 600; color: #94a3b8; background: #1e293b; padding: 2px 7px; border-radius: 999px; }
  .back {
    background: #1e293b; color: #cbd5e1; border: none; width: 28px; height: 28px;
    border-radius: 8px; font-size: 15px; cursor: pointer; line-height: 1;
  }
  .back:hover { background: #334155; color: #fff; }
  .close { background: #1e293b; color: #cbd5e1; border: none; width: 32px; height: 32px; border-radius: 8px; font-size: 14px; cursor: pointer; }
  .close:hover { background: #334155; color: #fff; }

  .body { flex: 1; min-height: 0; overflow-y: auto; padding: 18px 22px; }

  /* ---- release list ---- */
  .releases { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; }
  .release { position: relative; padding: 0 0 22px 20px; border-left: 2px solid var(--border); }
  .release:last-child { padding-bottom: 4px; }
  .release::before {
    content: ''; position: absolute; left: -7px; top: 4px;
    width: 12px; height: 12px; border-radius: 50%;
    background: #cbd5e1; border: 2px solid var(--card, #fff);
  }
  .release.latest::before { background: var(--blue); }
  .rel-head { display: flex; align-items: center; gap: 10px; }
  .rel-ver { font-weight: 800; font-size: 15px; color: var(--text-main, #0f172a); letter-spacing: -0.01em; }
  .badge-current {
    font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.04em;
    color: #1e40af; background: #dbeafe; padding: 2px 7px; border-radius: 999px;
  }
  .rel-date { margin-left: auto; font-size: 12px; color: var(--text-sub, #64748b); font-family: "JetBrains Mono", monospace; }
  .rel-title { font-size: 13px; color: var(--text-sub, #64748b); margin: 3px 0 10px; font-weight: 600; }
  .changes { list-style: none; margin: 8px 0 0; padding: 0; display: flex; flex-direction: column; gap: 8px; }
  .change { display: flex; gap: 10px; align-items: flex-start; }
  .tag {
    flex: 0 0 auto; margin-top: 1px; font-size: 10px; font-weight: 700; text-transform: uppercase;
    letter-spacing: 0.03em; padding: 2px 7px; border-radius: 6px; min-width: 34px; text-align: center;
  }
  .tag.feature { color: #1e40af; background: #eff6ff; border: 1px solid #bfdbfe; }
  .tag.fix { color: #92400e; background: #fffbeb; border: 1px solid #fde68a; }
  .change-text { font-size: 13.5px; line-height: 1.5; color: #334155; }

  /* ---- footer actions ---- */
  .actions {
    flex: 0 0 auto; border-top: 1px solid var(--border);
    padding: 14px 22px; display: flex; align-items: center; justify-content: space-between;
    gap: 12px; flex-wrap: wrap; background: #f8fafc;
  }
  .actions .prompt { font-size: 13px; color: var(--text-sub, #64748b); }
  .action-btns { display: flex; gap: 8px; }

  /* ---- feedback form ---- */
  .body.form { display: flex; flex-direction: column; gap: 12px; }
  .hint { font-size: 13.5px; line-height: 1.55; color: #334155; margin: 0; }
  textarea {
    width: 100%; resize: vertical; min-height: 150px; padding: 12px 14px;
    border: 1px solid var(--border); border-radius: 10px; font: inherit; font-size: 13.5px;
    line-height: 1.55; color: var(--text-main, #0f172a); background: #fff;
  }
  textarea:focus { outline: none; border-color: var(--blue); box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.15); }
  .dest { font-size: 12px; color: var(--text-sub, #64748b); margin: 0; }
  .dest code, .callout code { font-family: "JetBrains Mono", monospace; font-size: 12px; background: #f1f5f9; padding: 1px 5px; border-radius: 4px; }
  .form-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 4px; }

  .callout { padding: 12px 14px; border-radius: 10px; font-size: 13px; line-height: 1.55; }
  .callout.ok { background: #ecfdf5; color: #065f46; border: 1px solid #a7f3d0; }
  .callout.warn { background: #fffbeb; color: #92400e; border: 1px solid #fde68a; }

  /* ---- buttons ---- */
  .btn {
    padding: 9px 14px; border-radius: 9px; border: 1px solid transparent;
    font-weight: 600; font-size: 13px; cursor: pointer; transition: background 120ms, transform 80ms, box-shadow 120ms;
  }
  .btn:active { transform: translateY(1px); }
  .btn:disabled { opacity: 0.55; cursor: default; transform: none; }
  .btn.feature { background: #eff6ff; color: #1e40af; border-color: #bfdbfe; }
  .btn.feature:hover:not(:disabled) { background: #dbeafe; }
  .btn.bug { background: #fff7ed; color: #9a3412; border-color: #fed7aa; }
  .btn.bug:hover:not(:disabled) { background: #ffedd5; }
  .btn.primary { background: var(--blue, #2563eb); color: #fff; }
  .btn.primary:hover:not(:disabled) { background: #1d4ed8; box-shadow: 0 4px 12px rgba(37, 99, 235, 0.3); }
  .btn.ghost { background: transparent; border-color: #cbd5e1; color: #0f172a; }
  .btn.ghost:hover:not(:disabled) { background: #f1f5f9; }

  @media (max-width: 560px) {
    .actions { flex-direction: column; align-items: stretch; }
    .action-btns { justify-content: stretch; }
    .action-btns .btn { flex: 1; }
  }
</style>
