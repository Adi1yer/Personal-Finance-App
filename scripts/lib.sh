# Shared helpers for launch/setup scripts.

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

# True on M1/M2/M3 Macs
is_apple_silicon() {
  [[ "$(sysctl -n hw.optional.arm64 2>/dev/null)" == "1" ]]
}

# Finder-launched .app processes often run under Rosetta (x86_64) while Terminal
# installs arm64 pip wheels — force native ARM for all Python/npm on Apple Silicon.
ensure_native_arch() {
  if ! is_apple_silicon; then
    return 0
  fi
  if [[ "$(uname -m)" == "arm64" ]]; then
    return 0
  fi
  log "Re-exec under native arm64 (was x86_64/Rosetta)"
  exec arch -arm64 /bin/bash "$0" "$@"
}

# Prefer Homebrew Python (single-arch arm64); avoid universal CLT Python + Rosetta mismatch.
resolve_python_bin() {
  if [[ -x /opt/homebrew/bin/python3 ]]; then
    echo /opt/homebrew/bin/python3
  elif is_apple_silicon; then
    echo "arch -arm64 python3"
  else
    echo python3
  fi
}

run_python() {
  if [[ ! -x "$BIN/python" ]]; then
    return 1
  fi
  if is_apple_silicon; then
    arch -arm64 "$BIN/python" "$@"
  else
    "$BIN/python" "$@"
  fi
}

verify_venv_imports() {
  run_python -c "import pydantic_core; import fastapi" 2>/dev/null
}

# Resolve project root (scripts/ is one level below repo root).
if [[ -n "${PERSONAL_FINANCE_ROOT:-}" ]]; then
  PROJECT_ROOT="$PERSONAL_FINANCE_ROOT"
else
  PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
fi

SUPPORT_DIR="$HOME/Library/Application Support/PersonalFinance"
PID_FILE="$SUPPORT_DIR/pids"
DESKTOP_PID_FILE="$SUPPORT_DIR/desktop.pid"
LAUNCH_LOCK_FILE="$SUPPORT_DIR/launch.lock"
LOG_DIR="$SUPPORT_DIR/logs"
API_PORT=8000
UI_PORT=5173
VENV="$PROJECT_ROOT/.venv"
BIN="$VENV/bin"

log() {
  echo "[$(date '+%H:%M:%S')] $*"
}

ensure_dirs() {
  mkdir -p "$SUPPORT_DIR" "$LOG_DIR" "$PROJECT_ROOT/data"
}

port_in_use() {
  lsof -iTCP:"$1" -sTCP:LISTEN -t >/dev/null 2>&1
}

read_pids() {
  API_PID=""
  UI_PID=""
  if [[ -f "$PID_FILE" ]]; then
    # shellcheck disable=SC1090
    source "$PID_FILE" 2>/dev/null || true
  fi
}

save_pids() {
  cat >"$PID_FILE" <<EOF
API_PID=${API_PID:-}
UI_PID=${UI_PID:-}
EOF
}

pid_alive() {
  [[ -n "$1" ]] && kill -0 "$1" 2>/dev/null
}

stop_servers() {
  read_pids
  if pid_alive "$API_PID"; then
    log "Stopping API (pid $API_PID)"
    kill "$API_PID" 2>/dev/null || true
  fi
  if pid_alive "$UI_PID"; then
    log "Stopping UI (pid $UI_PID)"
    kill "$UI_PID" 2>/dev/null || true
  fi
  rm -f "$PID_FILE" "$DESKTOP_PID_FILE"
  release_launch_lock
  # Free ports if something else is listening from a crashed run
  for port in "$API_PORT" "$UI_PORT"; do
    if port_in_use "$port"; then
      lsof -iTCP:"$port" -sTCP:LISTEN -t 2>/dev/null | xargs kill 2>/dev/null || true
    fi
  done
  pkill -f "electron.*personal-finance-ui" 2>/dev/null || true
  pkill -f "vite preview.*5173" 2>/dev/null || true
  pkill -f "uvicorn.*app.main:app" 2>/dev/null || true
  pkill -f "scripts/desktop.py" 2>/dev/null || true
}

wait_for_url() {
  local url=$1
  local tries=${2:-30}
  for ((i = 0; i < tries; i++)); do
    if curl -fsS "$url" >/dev/null 2>&1; then
      return 0
    fi
    sleep 0.5
  done
  return 1
}

notify_mac() {
  local title=$1
  local message=$2
  osascript -e "display notification \"$message\" with title \"$title\"" 2>/dev/null || true
}

alert_mac() {
  local message=$1
  osascript -e "display alert \"Personal Finance\" message \"$message\" as critical" 2>/dev/null || true
}

is_desktop_running() {
  if [[ ! -f "$DESKTOP_PID_FILE" ]]; then
    return 1
  fi
  local dp
  dp=$(cat "$DESKTOP_PID_FILE" 2>/dev/null) || return 1
  pid_alive "$dp"
}

activate_app() {
  osascript -e 'tell application "Personal Finance" to activate' 2>/dev/null || true
}

# One-time / repair setup without opening Terminal (logs to Support dir).
ensure_app_ready() {
  if [[ -x "$BIN/python" ]] && verify_venv_imports && ui_dist_ready && ! ui_dist_stale; then
    return 0
  fi
  notify_mac "Personal Finance" "First-time setup in progress (may take a few minutes)…"
  log "Running automatic setup…"
  if ! bash "$PROJECT_ROOT/scripts/setup.sh" >>"$LOG_DIR/setup.log" 2>&1; then
    alert_mac "Setup failed. See $LOG_DIR/setup.log"
    return 1
  fi
  [[ -x "$BIN/python" ]] && verify_venv_imports && ui_dist_ready
}

LAUNCH_LOCK_DIR="$SUPPORT_DIR/.launch"
LAUNCH_LOCK_PID_FILE="$LAUNCH_LOCK_DIR/launcher.pid"

release_launch_lock() {
  rm -rf "$LAUNCH_LOCK_DIR" 2>/dev/null || true
}

# True when .launch exists but no launcher/setup and no desktop window.
launch_lock_is_stale() {
  [[ -d "$LAUNCH_LOCK_DIR" ]] || return 1
  if is_desktop_running; then
    return 1
  fi
  if [[ -f "$LAUNCH_LOCK_PID_FILE" ]]; then
    local lp
    lp=$(cat "$LAUNCH_LOCK_PID_FILE" 2>/dev/null) || true
    if pid_alive "$lp"; then
      return 1
    fi
  fi
  return 0
}

acquire_launch_lock() {
  mkdir -p "$SUPPORT_DIR"
  if mkdir "$LAUNCH_LOCK_DIR" 2>/dev/null; then
    echo $$ >"$LAUNCH_LOCK_PID_FILE"
    return 0
  fi
  if launch_lock_is_stale; then
    log "Removing stale launch lock"
    release_launch_lock
    if mkdir "$LAUNCH_LOCK_DIR" 2>/dev/null; then
      echo $$ >"$LAUNCH_LOCK_PID_FILE"
      return 0
    fi
  fi
  return 1
}

find_npm() {
  command -v npm >/dev/null 2>&1
}

# Add Node/npm to PATH from common locations (no Homebrew required).
bootstrap_node_path() {
  local candidates=(
    "/opt/homebrew/bin"
    "/usr/local/bin"
    "$PROJECT_ROOT/.tools/node/bin"
    "/Applications/Cursor.app/Contents/Resources/app/resources/helpers"
  )
  for dir in "${candidates[@]}"; do
    if [[ -x "$dir/npm" ]]; then
      export PATH="$dir:$PATH"
      return 0
    fi
    if [[ -x "$dir/node" && -x "$dir/npm" ]]; then
      export PATH="$dir:$PATH"
      return 0
    fi
  done
  if command -v npm >/dev/null 2>&1; then
    return 0
  fi
  return 1
}

# Download official Node binary into .tools/node (no brew).
install_portable_node() {
  local tools="$PROJECT_ROOT/.tools"
  local node_dir="$tools/node"
  if [[ -x "$node_dir/bin/npm" ]]; then
    export PATH="$node_dir/bin:$PATH"
    return 0
  fi

  local ver="20.18.1"
  local arch_name
  case "$(uname -m)" in
    arm64) arch_name="arm64" ;;
    x86_64) arch_name="x64" ;;
    *) log "Unsupported CPU for portable Node"; return 1 ;;
  esac

  local tarball="node-v${ver}-darwin-${arch_name}.tar.gz"
  local url="https://nodejs.org/dist/v${ver}/${tarball}"
  log "Downloading Node.js ${ver} (${arch_name})…"
  mkdir -p "$tools"
  local tmp
  tmp=$(mktemp -d)
  if ! curl -fsSL "$url" -o "$tmp/$tarball"; then
    log "Download failed: $url"
    rm -rf "$tmp"
    return 1
  fi
  tar -xzf "$tmp/$tarball" -C "$tmp"
  rm -rf "$node_dir"
  mv "$tmp/node-v${ver}-darwin-${arch_name}" "$node_dir"
  rm -rf "$tmp"
  export PATH="$node_dir/bin:$PATH"
  log "Portable Node installed at $node_dir"
}

ensure_node() {
  bootstrap_node_path && return 0
  install_portable_node && bootstrap_node_path && return 0
  return 1
}

ui_dist_ready() {
  [[ -f "$PROJECT_ROOT/frontend/dist/index.html" ]]
}

ui_dist_stale() {
  if ! ui_dist_ready; then
    return 0
  fi
  local dist_mtime src_mtime
  dist_mtime=$(stat -f %m "$PROJECT_ROOT/frontend/dist/index.html" 2>/dev/null || stat -c %Y "$PROJECT_ROOT/frontend/dist/index.html" 2>/dev/null || echo 0)
  src_mtime=$(
    find "$PROJECT_ROOT/frontend/src" -type f \( -name '*.tsx' -o -name '*.ts' -o -name '*.css' \) -print0 2>/dev/null \
      | xargs -0 stat -f %m 2>/dev/null \
      | sort -rn \
      | head -1
  )
  if [[ -z "${src_mtime:-}" ]]; then
    src_mtime=$(find "$PROJECT_ROOT/frontend/src" -type f \( -name '*.tsx' -o -name '*.ts' -o -name '*.css' \) -printf '%T@\n' 2>/dev/null | sort -rn | head -1)
  fi
  [[ -n "${src_mtime:-}" && "$src_mtime" -gt "$dist_mtime" ]]
}

ensure_ui_built() {
  if ui_dist_stale; then
    log "UI source newer than dist — rebuilding…"
    if ! bash "$PROJECT_ROOT/scripts/build-ui.sh"; then
      alert_mac "UI build failed. See $LOG_DIR/setup.log"
      return 1
    fi
  fi
  ui_dist_ready
}
