#!/usr/bin/env bash
# Builds "Personal Finance.app" and installs it to ~/Applications
set -euo pipefail
source "$(dirname "$0")/lib.sh"

APP_NAME="Personal Finance"
APP_DIR="$HOME/Applications/${APP_NAME}.app"
CONTENTS="$APP_DIR/Contents"
MACOS="$CONTENTS/MacOS"
RESOURCES="$CONTENTS/Resources"
LAUNCHER_SRC="$PROJECT_ROOT/scripts/mac_app_launcher.c"
LAUNCHER_BIN="$MACOS/PersonalFinance"

log "Building $APP_DIR"
log "Project root: $PROJECT_ROOT"

if [[ ! -f "$LAUNCHER_SRC" ]]; then
  log "ERROR: missing $LAUNCHER_SRC"
  exit 1
fi

if ! command -v clang >/dev/null 2>&1; then
  alert_mac "clang not found. Install Xcode Command Line Tools (xcode-select --install), then re-run make mac-app."
  log "ERROR: clang required to build the Mac app launcher"
  exit 1
fi

rm -rf "$APP_DIR"
mkdir -p "$MACOS" "$RESOURCES"

# Absolute project path read by the native stub (handles spaces safely).
printf '%s\n' "$PROJECT_ROOT" >"$RESOURCES/project_root"

cat >"$CONTENTS/Info.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleExecutable</key>
  <string>PersonalFinance</string>
  <key>CFBundleIdentifier</key>
  <string>com.personalfinance.app</string>
  <key>CFBundleName</key>
  <string>${APP_NAME}</string>
  <key>CFBundleDisplayName</key>
  <string>${APP_NAME}</string>
  <key>CFBundlePackageType</key>
  <string>APPL</string>
  <key>CFBundleShortVersionString</key>
  <string>0.1.1</string>
  <key>CFBundleVersion</key>
  <string>2</string>
  <key>LSMinimumSystemVersion</key>
  <string>11.0</string>
  <key>NSHighResolutionCapable</key>
  <true/>
  <key>LSUIElement</key>
  <false/>
  <key>NSAppleScriptEnabled</key>
  <false/>
</dict>
</plist>
EOF

log "Compiling native launcher…"
clang -O2 -Wall -Wextra -o "$LAUNCHER_BIN" "$LAUNCHER_SRC"
chmod +x "$LAUNCHER_BIN"

# Drop Gatekeeper quarantine so double-click is not silently blocked for local builds.
xattr -cr "$APP_DIR" 2>/dev/null || true

# Refresh Launch Services so the Dock/Spotlight pick up the new executable name.
LSREGISTER="/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister"
if [[ -x "$LSREGISTER" ]]; then
  "$LSREGISTER" -f "$APP_DIR" 2>/dev/null || true
fi

# Optional: run setup on first build if venv missing
if [[ ! -x "$VENV/bin/uvicorn" ]]; then
  log "First-time setup…"
  bash "$PROJECT_ROOT/scripts/setup.sh"
fi

log "Installed: $APP_DIR"
log "Open with Spotlight or Finder → Applications (user) → Personal Finance"
log "If double-click still does nothing: xattr -cr \"$APP_DIR\" && open \"$APP_DIR\""
open -R "$APP_DIR"

notify_mac "Personal Finance" "App icon installed. Double-click to open (no Terminal)."
