#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/lib.sh"

stop_servers
notify_mac "Personal Finance" "Stopped."
log "Servers stopped."
