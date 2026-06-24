<script lang="ts">
  import { onMount } from 'svelte';
  import type { AnalysisBackend } from '../backend';
  import type { CrashReportResult, PendingCrash } from '../backend/types';

  const { backend }: { backend: AnalysisBackend } = $props();

  let pending = $state<PendingCrash | null>(null);
  let email = $state('');
  let sending = $state(false);
  let result = $state<CrashReportResult | null>(null);

  onMount(async () => {
    // Desktop-only feature; mock/PWA backends omit pendingCrash.
    if (!backend.pendingCrash) return;
    try {
      const status = await backend.pendingCrash();
      pending = status.pending;
      email = status.email;
    } catch {
      // best-effort: never block app start on a reporting probe
    }
  });

  async function sendReport() {
    if (!backend.emailCrashReport) return;
    sending = true;
    try {
      result = await backend.emailCrashReport();
    } catch (e) {
      result = {
        ok: false, email, report_path: null, mailto_opened: false,
        revealed: false, error: e instanceof Error ? e.message : String(e),
      };
    } finally {
      sending = false;
    }
  }

  async function dismiss() {
    try {
      await backend.dismissCrashReport?.();
    } finally {
      pending = null;
      result = null;
    }
  }
</script>

{#if pending}
  <div class="crash-overlay">
    <div class="crash-card" role="alertdialog" aria-label="Crash report">
      <div class="crash-head">
        <span class="crash-icon">⚠️</span>
        <h2>PQA closed unexpectedly last time</h2>
      </div>

      {#if !result}
        <p>
          A problem was logged on
          <strong>{new Date(pending.timestamp).toLocaleString()}</strong>
          ({pending.error_type}). You can email the crash logs to the developer to
          help get it fixed.
        </p>
        <p class="crash-dest">Report will be addressed to <strong>{email}</strong>.</p>
        <p class="crash-note">
          This opens your email app with a summary; the full log file is saved and
          highlighted so you can attach it. Nothing is sent automatically.
        </p>
        <div class="crash-actions">
          <button class="btn primary" onclick={sendReport} disabled={sending}>
            {sending ? 'Opening email…' : '✉ Email crash report'}
          </button>
          <button class="btn ghost" onclick={dismiss} disabled={sending}>Not now</button>
        </div>
      {:else}
        {#if result.ok}
          <p class="crash-ok">✓ Your email app has been opened, addressed to {email}.</p>
          {#if result.report_path}
            <p class="crash-note">
              Full report saved to:<br /><code>{result.report_path}</code><br />
              {#if result.revealed}It's highlighted in your file manager — attach it to the email.{/if}
            </p>
          {/if}
          {#if !result.mailto_opened}
            <p class="crash-warn">
              Couldn't open your mail app automatically — please email the saved
              report file to {email}.
            </p>
          {/if}
        {:else}
          <p class="crash-warn">
            Couldn't prepare the report{result.error ? `: ${result.error}` : ''}.
            You can email your logs manually to {email}.
          </p>
        {/if}
        <div class="crash-actions">
          <button class="btn primary" onclick={dismiss}>Close</button>
        </div>
      {/if}
    </div>
  </div>
{/if}

<style>
  .crash-overlay {
    position: fixed;
    inset: 0;
    background: rgba(15, 23, 42, 0.55);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
  }
  .crash-card {
    background: #ffffff;
    color: #0f172a;
    max-width: 520px;
    width: calc(100% - 2rem);
    border-radius: 12px;
    padding: 1.5rem;
    box-shadow: 0 20px 60px rgba(15, 23, 42, 0.35);
    border-top: 4px solid #ea580c;
  }
  .crash-head {
    display: flex;
    align-items: center;
    gap: 0.6rem;
    margin-bottom: 0.5rem;
  }
  .crash-head h2 {
    font-size: 1.1rem;
    margin: 0;
  }
  .crash-icon { font-size: 1.4rem; }
  .crash-card p { line-height: 1.5; margin: 0.5rem 0; }
  .crash-dest { font-size: 0.95rem; }
  .crash-note { font-size: 0.85rem; color: #64748b; }
  .crash-note code { word-break: break-all; font-size: 0.8rem; }
  .crash-ok { color: #16a34a; font-weight: 600; }
  .crash-warn { color: #b45309; font-weight: 500; }
  .crash-actions {
    display: flex;
    gap: 0.6rem;
    justify-content: flex-end;
    margin-top: 1rem;
  }
  .btn {
    padding: 0.5rem 1rem;
    border-radius: 8px;
    border: 1px solid transparent;
    font-weight: 600;
    cursor: pointer;
  }
  .btn:disabled { opacity: 0.6; cursor: default; }
  .btn.primary { background: #2563eb; color: #fff; }
  .btn.ghost { background: transparent; border-color: #cbd5e1; color: #0f172a; }
</style>
