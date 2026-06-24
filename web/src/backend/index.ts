import type { AnalysisBackend } from './AnalysisBackend';
import { PyWebviewBackend } from './PyWebviewBackend';
import { MockBackend } from './MockBackend';

/** sessionStorage flag so the self-heal reload happens at most once per window. */
const RELOAD_FLAG = 'pqa_bridge_reload_attempted';

type PyWebviewApi = NonNullable<Window['pywebview']>['api'];

const sleep = (ms: number) => new Promise<void>((r) => window.setTimeout(r, ms));

/** The bridge is only usable once its methods are actually attached. */
function readyApi(): PyWebviewApi | null {
  const api = window.pywebview?.api;
  return api && typeof api.caps === 'function' ? api : null;
}

/**
 * Probe the bridge with a real RPC round-trip. Even with methods attached, a
 * macOS cold load can leave the first call hanging, so presence is not enough —
 * we confirm a call resolves within the timeout. Never throws.
 */
function probeBridge(api: PyWebviewApi, timeoutMs: number): Promise<boolean> {
  return new Promise((resolve) => {
    let settled = false;
    const finish = (ok: boolean) => {
      if (settled) return;
      settled = true;
      window.clearTimeout(timer);
      resolve(ok);
    };
    const timer = window.setTimeout(() => finish(false), timeoutMs);
    (async () => {
      try {
        await api.caps();
        finish(true);
      } catch {
        finish(false);
      }
    })();
  });
}

interface SelectOpts {
  hostGraceMs?: number;    // how long to wait for the pywebview host to appear
  bridgeDeadlineMs?: number; // how long to keep retrying the RPC on desktop
  probeMs?: number;        // per-probe RPC timeout
  pollMs?: number;
}

/**
 * Resolve the active backend:
 *  - Mock (plain browser dev) when no pywebview host is ever detected
 *  - PyWebview (desktop) otherwise — we keep retrying the real bridge and never
 *    silently fall back to demo data inside the desktop app.
 *
 * `window.pywebview` (the object) appears in the desktop shell even before its
 * methods attach, and never appears in a plain browser — so it is the reliable
 * desktop-vs-browser discriminator. The bridge's first RPC can race on a macOS
 * cold load; we retry, and reload once to re-init the WKWebView channel if it
 * stays unresponsive.
 */
export async function selectBackend(opts: SelectOpts = {}): Promise<AnalysisBackend> {
  const { hostGraceMs = 5000, bridgeDeadlineMs = 20000, probeMs = 4000, pollMs = 100 } = opts;

  // 1) Desktop vs browser.
  const hostDeadline = performance.now() + hostGraceMs;
  while (!window.pywebview && performance.now() < hostDeadline) {
    await sleep(pollMs);
  }
  if (!window.pywebview) return new MockBackend(); // genuine browser-dev session

  // 2) Desktop: keep trying until a real RPC succeeds.
  const reloadedAlready = sessionStorage.getItem(RELOAD_FLAG) === '1';
  const bridgeDeadline = performance.now() + bridgeDeadlineMs;
  while (performance.now() < bridgeDeadline) {
    const api = readyApi();
    if (api && (await probeBridge(api, probeMs))) {
      sessionStorage.removeItem(RELOAD_FLAG);
      return new PyWebviewBackend();
    }
    await sleep(pollMs);
  }

  // 3) Bridge present but never responded — a reload reliably re-inits the
  //    WKWebView channel on macOS. Do it at most once.
  if (!reloadedAlready) {
    sessionStorage.setItem(RELOAD_FLAG, '1');
    window.location.reload();
    return new Promise<AnalysisBackend>(() => {}); // hang until reload takes over
  }

  // 4) Even after a reload the channel won't answer. Use the real backend
  //    anyway — inside the desktop app the user must work on their real data,
  //    so surface real errors rather than silently showing demo data.
  return new PyWebviewBackend();
}

export type { AnalysisBackend };
