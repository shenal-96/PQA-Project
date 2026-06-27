#!/usr/bin/env bash
# Launch the PQA desktop app with a GUARANTEED-FRESH web bundle.
#
# The desktop shell loads the COMPILED bundle web/dist/index.html, not web/src/.
# web/dist/ is gitignored, so `git pull` updates source but never the bundle —
# launching without rebuilding shows stale UI. This script rebuilds the bundle
# whenever it is missing or older than any source file, then starts the shell.
#
# Usage:
#   scripts/run-desktop.sh           # rebuild-if-stale, then launch
#   scripts/run-desktop.sh --force   # always rebuild, then launch
#   scripts/run-desktop.sh --build   # rebuild-if-stale only, do not launch
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

WEB_DIR="$REPO_ROOT/web"
BUNDLE="$WEB_DIR/dist/index.html"
VENV_PY="$REPO_ROOT/.venv/bin/python"

FORCE=0
BUILD_ONLY=0
for arg in "$@"; do
  case "$arg" in
    --force) FORCE=1 ;;
    --build) BUILD_ONLY=1 ;;
    *) echo "unknown arg: $arg" >&2; exit 2 ;;
  esac
done

# --- decide whether the bundle is stale ------------------------------------
needs_build=0
reason=""
if [[ "$FORCE" == "1" ]]; then
  needs_build=1; reason="--force"
elif [[ ! -f "$BUNDLE" ]]; then
  needs_build=1; reason="bundle missing"
else
  # Any source file newer than the bundle => stale. Watch the inputs vite reads.
  newer="$(find "$WEB_DIR/src" "$WEB_DIR/index.html" "$WEB_DIR/package.json" \
              "$WEB_DIR"/vite.config.* "$WEB_DIR"/tsconfig*.json \
              -newer "$BUNDLE" 2>/dev/null | head -1 || true)"
  if [[ -n "$newer" ]]; then
    needs_build=1; reason="source newer than bundle (e.g. ${newer#"$REPO_ROOT/"})"
  fi
fi

# --- rebuild if needed ------------------------------------------------------
if [[ "$needs_build" == "1" ]]; then
  echo "→ rebuilding web bundle ($reason)"
  if [[ ! -d "$WEB_DIR/node_modules" ]]; then
    echo "→ installing web deps (node_modules missing)"
    ( cd "$WEB_DIR" && npm install )
  fi
  ( cd "$WEB_DIR" && npm run build )
  echo "→ bundle rebuilt: $BUNDLE"
else
  echo "→ bundle is up to date — skipping build"
fi

if [[ "$BUILD_ONLY" == "1" ]]; then
  exit 0
fi

# --- launch the shell -------------------------------------------------------
if [[ ! -x "$VENV_PY" ]]; then
  echo "ERROR: venv python not found at $VENV_PY" >&2
  echo "       create it with: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt" >&2
  exit 1
fi

echo "→ launching desktop shell (python -m desktop.shell)"
exec "$VENV_PY" -m desktop.shell
