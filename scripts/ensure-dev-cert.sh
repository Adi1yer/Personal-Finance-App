#!/usr/bin/env bash
# Trusted local HTTPS cert for Plaid OAuth (production requires https://127.0.0.1 redirect URIs).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CERT_DIR="$ROOT/data/certs"
CRT="$CERT_DIR/localhost.pem"
KEY="$CERT_DIR/localhost-key.pem"
MARKER="$CERT_DIR/.mkcert"

mkdir -p "$CERT_DIR"

if command -v mkcert >/dev/null 2>&1; then
  if [[ ! -f "$MARKER" ]]; then
    echo "Installing local certificate authority (one-time; macOS may ask for your password)…"
    mkcert -install
    touch "$MARKER"
  fi
  mkcert -key-file "$KEY" -cert-file "$CRT" 127.0.0.1 localhost ::1
  echo "Trusted local cert ready — browsers should not warn."
  exit 0
fi

if [[ -f "$CRT" && -f "$KEY" ]]; then
  echo "Using existing cert at $CRT"
else
  openssl req -x509 -newkey rsa:2048 \
    -keyout "$KEY" \
    -out "$CRT" \
    -days 825 \
    -nodes \
    -subj "/CN=127.0.0.1" \
    -addext "subjectAltName=DNS:localhost,DNS:127.0.0.1,IP:127.0.0.1" \
    2>/dev/null
  echo "Created local cert at $CRT"
fi

cat <<'EOF'
Browser security warning? Pick one:

1) Quick (Brave/Chrome): Advanced → Proceed to 127.0.0.1
   Safe — this is your own Mac running the app.

2) Permanent fix:
   brew install mkcert
   cd /path/to/personal_finance_repo
   make trust-cert
EOF
