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
export function selectBackend(timeoutMs = 800): Promise<AnalysisBackend> {
  return new Promise((resolve) => {
    if (window.pywebview?.api) {
      resolve(new PyWebviewBackend());
      return;
    }
    let settled = false;
    const onReady = () => {
      if (settled) return;
      settled = true;
      resolve(new PyWebviewBackend());
    };
    window.addEventListener('pywebviewready', onReady, { once: true });
    setTimeout(() => {
      if (settled) return;
      settled = true;
      window.removeEventListener('pywebviewready', onReady);
      resolve(new MockBackend());
    }, timeoutMs);
  });
}

export type { AnalysisBackend };
