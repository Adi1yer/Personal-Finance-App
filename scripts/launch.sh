#!/usr/bin/env bash
# Started by Personal Finance.app — no Terminal required.
set -euo pipefail
source "$(dirname "$0")/lib.sh"
ensure_native_arch

# Support logs first — Finder launches have no Terminal for stdout.
mkdir -p "$SUPPORT_DIR" "$LOG_DIR"
exec >>"$LOG_DIR/launch.log" 2>&1

if [[ ! -d "$PROJECT_ROOT" || ! -f "$PROJECT_ROOT/scripts/launch.sh" ]]; then
  log "ERROR: invalid PROJECT_ROOT=$PROJECT_ROOT"
  alert_mac "Project folder missing or moved. From your clone run: make mac-app"
  exit 1
fi

ensure_dirs
cd "$PROJECT_ROOT"

# Optional cloud API URL (one line: https://your-server.example.com)
CLOUD_API_FILE="$HOME/Library/Application Support/PersonalFinance/cloud-api.url"
if [[ -z "${PERSONAL_FINANCE_API_URL:-}" && -f "$CLOUD_API_FILE" ]]; then
  export PERSONAL_FINANCE_API_URL="$(tr -d '[:space:]' < "$CLOUD_API_FILE")"
  log "Using cloud API: $PERSONAL_FINANCE_API_URL"
fi

log "=== Launch $(date) ==="
log "PROJECT_ROOT=$PROJECT_ROOT"

# Window already up — focus it (no launch lock needed).
if is_desktop_running; then
  log "Desktop already running"
  notify_mac "Personal Finance" "Already open."
  activate_app
  exit 0
fi

# Serialize first-time setup + cold start.
if ! acquire_launch_lock; then
  if launch_lock_is_stale; then
    log "Removing stale launch lock and retrying"
    release_launch_lock
    acquire_launch_lock || {
      notify_mac "Personal Finance" "Could not start. Try again."
      exit 1
    }
  else
    notify_mac "Personal Finance" "Already starting…"
    exit 0
  fi
fi

abort_launch() {
  release_launch_lock
}
trap abort_launch EXIT

# Another click may have started the window while we waited for the lock.
if is_desktop_running; then
  log "Desktop started while waiting for lock"
  notify_mac "Personal Finance" "Already open."
  activate_app
  exit 0
fi

# First launch or repair: install deps + build UI automatically.
if ! ensure_app_ready; then
  exit 1
fi

# Rebuild UI when frontend source changed since last dist build.
if ui_dist_stale; then
  log "Rebuilding UI (source newer than dist)…"
  if ! bash "$PROJECT_ROOT/scripts/build-ui.sh" >>"$LOG_DIR/setup.log" 2>&1; then
    alert_mac "UI build failed. See $LOG_DIR/setup.log"
    exit 1
  fi
fi

# Only clear a broken/stale server (UI not HTML). Keep a healthy running server.
if port_in_use "$API_PORT"; then
  if curl -fsS "http://127.0.0.1:$API_PORT/" 2>/dev/null | head -c 20 | grep -q "<!DOCTYPE"; then
    log "Server already serving UI"
  else
    log "Clearing stale server on port $API_PORT"
    stop_servers
  fi
else
  stop_servers
fi

log "Starting desktop window…"

cleanup() {
  log "Launch cleanup $(date)"
  release_launch_lock
  rm -f "$DESKTOP_PID_FILE"
  stop_servers
  exit 0
}
trap cleanup EXIT INT TERM

# exec replaces this shell — EXIT trap does not run, so release lock before exec.
trap - EXIT
release_launch_lock

if is_apple_silicon; then
  exec arch -arm64 "$BIN/python" "$PROJECT_ROOT/scripts/desktop.py"
else
  exec "$BIN/python" "$PROJECT_ROOT/scripts/desktop.py"
fi
