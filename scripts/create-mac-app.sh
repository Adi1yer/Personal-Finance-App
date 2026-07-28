#!/usr/bin/env bash
# Builds "Personal Finance.app" and installs it to ~/Applications
set -euo pipefail
source "$(dirname "$0")/lib.sh"

APP_NAME="Personal Finance"
APP_DIR="$HOME/Applications/${APP_NAME}.app"
CONTENTS="$APP_DIR/Contents"
MACOS="$CONTENTS/MacOS"
PROJECT_ROOT_ESCAPED=$(printf '%s' "$PROJECT_ROOT" | sed 's/"/\\"/g')

log "Building $APP_DIR"
log "Project root: $PROJECT_ROOT"

rm -rf "$APP_DIR"
mkdir -p "$MACOS"

cat >"$CONTENTS/Info.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleExecutable</key>
  <string>launch</string>
  <key>CFBundleIdentifier</key>
  <string>com.personalfinance.app</string>
  <key>CFBundleName</key>
  <string>${APP_NAME}</string>
  <key>CFBundleDisplayName</key>
  <string>${APP_NAME}</string>
  <key>CFBundlePackageType</key>
  <string>APPL</string>
  <key>CFBundleShortVersionString</key>
  <string>0.1.0</string>
  <key>CFBundleVersion</key>
  <string>1</string>
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

cat >"$MACOS/launch" <<EOF
#!/bin/bash
export PERSONAL_FINANCE_ROOT="$PROJECT_ROOT_ESCAPED"
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:\$PATH"
# Finder launches .app under Rosetta on some Macs; Python wheels are arm64.
if [[ "\$(sysctl -n hw.optional.arm64 2>/dev/null)" == "1" ]]; then
  exec arch -arm64 /bin/bash "\$PERSONAL_FINANCE_ROOT/scripts/launch.sh"
else
  exec "\$PERSONAL_FINANCE_ROOT/scripts/launch.sh"
fi
EOF

chmod +x "$MACOS/launch"

# Optional: run setup on first build if venv missing
if [[ ! -x "$VENV/bin/uvicorn" ]]; then
  log "First-time setup…"
  bash "$PROJECT_ROOT/scripts/setup.sh"
fi

log "Installed: $APP_DIR"
log "Open Finder → Applications → \"Personal Finance\" (or Spotlight: Personal Finance)"
open -R "$APP_DIR"

notify_mac "Personal Finance" "App icon installed in Applications."
