#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/lib.sh"
ensure_native_arch

cd "$PROJECT_ROOT"
log "Project: $PROJECT_ROOT"
log "Machine: $(uname -m)"
ensure_dirs

PYTHON_CREATE=$(resolve_python_bin)

needs_venv_rebuild() {
  [[ ! -x "$BIN/python" ]] && return 0
  verify_venv_imports && return 1 || return 0
}

if needs_venv_rebuild; then
  if [[ -d "$VENV" ]]; then
    log "Removing broken venv…"
    rm -rf "$VENV"
  fi
  log "Creating virtual environment…"
  if [[ "$PYTHON_CREATE" == arch* ]]; then
  # shellcheck disable=SC2086
    $PYTHON_CREATE -m venv "$VENV"
  else
    "$PYTHON_CREATE" -m venv "$VENV"
  fi
fi

log "Installing Python dependencies (includes desktop UI host)…"
if is_apple_silicon; then
  arch -arm64 "$BIN/pip" install -q --upgrade pip setuptools wheel
  arch -arm64 "$BIN/pip" install -q -e ".[dev]"
else
  "$BIN/pip" install -q --upgrade pip setuptools wheel
  "$BIN/pip" install -q -e ".[dev]"
fi

if ! verify_venv_imports; then
  alert_mac "Python install failed. Try: xcode-select --install then make setup again."
  exit 1
fi

log "Initializing profile registry…"
(
  cd backend
  export PYTHONPATH=.
  if is_apple_silicon; then
    arch -arm64 "$BIN/python" -c "from app.db.registry import init_registry_database; init_registry_database()"
  else
    "$BIN/python" -c "from app.db.registry import init_registry_database; init_registry_database()"
  fi
)

if ui_dist_ready; then
  log "UI already built (frontend/dist)."
else
  log "Building desktop UI (downloads Node once if needed — no Homebrew required)…"
  if ! bash "$PROJECT_ROOT/scripts/build-ui.sh"; then
    alert_mac "UI build failed. Check internet and run: cd $PROJECT_ROOT && make setup"
    exit 1
  fi
fi

if [[ ! -f "$PROJECT_ROOT/.env" ]]; then
  cp "$PROJECT_ROOT/.env.example" "$PROJECT_ROOT/.env"
  log "Created .env"
fi

if grep -q '^PLAID_ENV=production' "$PROJECT_ROOT/.env" 2>/dev/null; then
  log "Production Plaid — ensuring trusted local HTTPS cert…"
  bash "$PROJECT_ROOT/scripts/ensure-dev-cert.sh" || log "Cert setup skipped (install mkcert: brew install mkcert && make trust-cert)"
fi

notify_mac "Personal Finance" "Setup complete."
log "Done. Open Applications → Personal Finance."
