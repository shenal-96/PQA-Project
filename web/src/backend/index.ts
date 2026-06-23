import type { AnalysisBackend } from './AnalysisBackend';
import { PyWebviewBackend } from './PyWebviewBackend';
import { MockBackend } from './MockBackend';

/** sessionStorage flag so the self-heal reload happens at most once per window. */
const RELOAD_FLAG = 'pqa_bridge_reload_attempted';

type PyWebviewApi = NonNullable<Window['pywebview']>['api'];

/** The bridge is only usable once its methods are actually attached. */
function readyApi(): PyWebviewApi | null {
  const api = window.pywebview?.api;
  return api && typeof api.caps === 'function' ? api : null;
}

/**
 * Wait for the PyWebview bridge to be fully attached (object present AND its
 * methods callable). On macOS, pywebview injects `window.pywebview.api` as an
 * empty object first and attaches methods a moment later, so we must poll for a
 * real method rather than trust the object's presence.
 *
 * Resolves with the `api` once ready, or `null` after `graceMs` (a genuine
 * browser-dev session where no bridge is ever injected).
 */
function waitForBridge(graceMs: number, pollMs: number): Promise<PyWebviewApi | null> {
  return new Promise((resolve) => {
    let settled = false;
    const finish = (api: PyWebviewApi | null) => {
      if (settled) return;
      settled = true;
      window.clearInterval(poll);
      resolve(api);
    };

    const ready = readyApi();
    if (ready) {
      finish(ready);
      return;
    }

    const startedAt = performance.now();
    const poll = window.setInterval(() => {
      const api = readyApi();
      if (api) finish(api);
      else if (performance.now() - startedAt >= graceMs) finish(null);
    }, pollMs);
  });
}

/**
 * Probe the bridge with a real RPC round-trip. Even with methods attached, a
 * macOS cold load can leave the first call hanging until the page is reloaded,
 * so presence is not enough — we confirm a call resolves. Never throws.
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
    // async wrapper so a synchronous throw (e.g. method vanished) is caught too.
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

/**
 * Resolve the active backend:
 *  - PyWebview (desktop) when the bridge is attached AND responds to a call
 *  - Mock (plain browser dev) when no bridge ever appears
 *
 * The desktop bridge can race on a macOS cold load: the api appears but its
 * first RPC hangs until the page is reloaded. We verify with a probe and, if it
 * stalls, reload once to re-init it. Every failure path falls back to the mock
 * so the UI can never hang on the "Starting…" screen.
 */
export async function selectBackend(graceMs = 6000, pollMs = 50, probeMs = 2500): Promise<AnalysisBackend> {
  try {
    const api = await waitForBridge(graceMs, pollMs);

    // No bridge after the grace window: genuine browser-dev session → mock.
    if (!api) return new MockBackend();

    // Bridge attached — confirm it actually responds before trusting it.
    if (await probeBridge(api, probeMs)) {
      sessionStorage.removeItem(RELOAD_FLAG);
      return new PyWebviewBackend();
    }

    // Bridge attached but dead. A one-time reload reliably initialises the RPC
    // channel on macOS WebKit. Guard with a flag so we never loop.
    if (!sessionStorage.getItem(RELOAD_FLAG)) {
      sessionStorage.setItem(RELOAD_FLAG, '1');
      window.location.reload();
      return new Promise<AnalysisBackend>(() => {}); // hang until reload takes over
    }

    // Already reloaded once and still unresponsive — render with the mock
    // rather than leaving the user stuck on "Starting…".
    return new MockBackend();
  } catch {
    return new MockBackend();
  }
}

export type { AnalysisBackend };
