import type { AnalysisBackend } from './AnalysisBackend';
import { PyWebviewBackend } from './PyWebviewBackend';
import { MockBackend } from './MockBackend';

/**
 * Resolve the active backend:
 *  - PyWebview (Windows desktop) when the bridge is present
 *  - Mock (plain browser dev) otherwise
 *
 * PyWebview injects its API asynchronously and fires `pywebviewready`, so we wait
 * briefly for it before falling back to the mock.
 */
export function selectBackend(graceMs = 6000, pollMs = 50): Promise<AnalysisBackend> {
  return new Promise((resolve) => {
    let settled = false;
    const done = (backend: AnalysisBackend) => {
      if (settled) return;
      settled = true;
      resolve(backend);
    };

    // Fast path: bridge already injected (e.g. after a reload, or on Windows
    // where it attaches before our script evaluates).
    if (window.pywebview?.api) {
      done(new PyWebviewBackend());
      return;
    }

    // pywebview fires this once the JS API is attached.
    window.addEventListener('pywebviewready', () => done(new PyWebviewBackend()), { once: true });

    // macOS WebKit can attach `window.pywebview.api` on first load without a
    // reliable `pywebviewready` event, so poll for it as well. We only fall
    // back to the mock after a generous grace window — by then a genuine
    // browser-dev session (no bridge) is the only thing that hasn't resolved.
    const startedAt = performance.now();
    const poll = window.setInterval(() => {
      if (window.pywebview?.api) {
        window.clearInterval(poll);
        done(new PyWebviewBackend());
      } else if (performance.now() - startedAt >= graceMs) {
        window.clearInterval(poll);
        done(new MockBackend());
      }
    }, pollMs);
  });
}

export type { AnalysisBackend };
