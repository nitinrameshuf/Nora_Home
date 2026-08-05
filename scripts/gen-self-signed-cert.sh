#!/usr/bin/env bash
#
# Self-signed TLS cert for nginx to terminate HTTPS with. This house has no
# public domain — it's a Pi on the LAN — so there's no CA that would ever
# issue it a "real" cert. Self-signed means every browser shows a one-time
# warning to click through per device (see docs/deployment.html); the
# wall/kiosk Chromium instances bypass it with --ignore-certificate-errors
# (see scripts/lib/provision-pi.sh, run via `./nora install`).
#
# Idempotent: does nothing if a cert already exists. Delete nginx/certs/ and
# re-run (or just re-run after deleting the two files) to regenerate — e.g.
# if the Pi's LAN IP changed and you want it back in the cert's SAN list.
set -euo pipefail

CERT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/nginx/certs"
CRT="$CERT_DIR/nora-home.crt"
KEY="$CERT_DIR/nora-home.key"

if [[ -f "$CRT" && -f "$KEY" ]]; then
    echo "Cert already exists at $CRT — leaving it alone."
    exit 0
fi

mkdir -p "$CERT_DIR"


# `hostname -I` is Linux-only (this runs for real on the Pi); it doesn't
# exist on macOS, where the option itself makes `hostname` exit non-zero —
# under pipefail that would abort the whole script over a cosmetic SAN
# entry. `|| true` degrades to no LAN IP in the cert instead of failing.
LAN_IP="$(hostname -I 2>/dev/null | awk '{print $1}')" || true
SAN="DNS:localhost,DNS:nora.home,DNS:nora.local,IP:127.0.0.1"
[[ -n "${LAN_IP:-}" ]] && SAN="$SAN,IP:$LAN_IP"

echo "Generating a self-signed cert (10 years) for: $SAN"
openssl req -x509 -nodes -newkey rsa:2048 \
    -keyout "$KEY" -out "$CRT" \
    -days 3650 \
    -subj "/CN=nora.home" \
    -addext "subjectAltName=$SAN"

chmod 600 "$KEY"
echo "Wrote $CRT and $KEY"
