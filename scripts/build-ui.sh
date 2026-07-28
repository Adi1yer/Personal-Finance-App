#!/usr/bin/env bash
# Build frontend/dist — uses system npm, Homebrew, Cursor's bundled node, or portable Node.
set -euo pipefail
source "$(dirname "$0")/lib.sh"
ensure_native_arch

cd "$PROJECT_ROOT/frontend"

if ! ensure_node; then
  log "ERROR: Could not find or install Node.js for UI build."
  exit 1
fi

log "Building UI with npm ($(command -v npm))…"
if is_apple_silicon; then
  arch -arm64 npm install
  arch -arm64 npm run build
else
  npm install
  npm run build
fi

if [[ ! -f dist/index.html ]]; then
  log "ERROR: build did not produce frontend/dist/index.html"
  exit 1
fi
log "UI build OK: frontend/dist"
