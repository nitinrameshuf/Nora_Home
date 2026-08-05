#!/usr/bin/env bash
#
# Run once, via sudo, before `./nora install`:
#
#     sudo ./scripts/lib/pre-provision-pi.sh
#
# Removes the sudo password prompt for the rest of setup, every future
# `./nora upgrade`, and anything else run on this Pi from here on.
#
# This does NOT grant any new capability. The target account is already a
# full sudoer — standard for the default user on Raspberry Pi OS — and can
# already do everything this unlocks, just with a password prompt each time.
# This only removes that prompt, for one local account, on a device you
# already have physical (or already-authenticated remote) access to. It does
# not open anything to the network or to any other account.
#
set -euo pipefail

[[ $EUID -eq 0 ]] || { echo "Run this with sudo: sudo $0"; exit 1; }

TARGET_USER="${SUDO_USER:-${1:-}}"
if [[ -z "$TARGET_USER" ]]; then
    echo "Could not work out which user to grant this to."
    echo "Run it as:  sudo ./scripts/lib/pre-provision-pi.sh   (from that user's own login)"
    echo "or:         sudo ./scripts/lib/pre-provision-pi.sh <username>"
    exit 1
fi

id "$TARGET_USER" >/dev/null 2>&1 || { echo "No such user: $TARGET_USER"; exit 1; }

SUDOERS_FILE="/etc/sudoers.d/nora-home-provisioning"
TMP_FILE="$(mktemp)"
echo "$TARGET_USER ALL=(ALL) NOPASSWD: ALL" > "$TMP_FILE"

# Validate before installing — a malformed sudoers file can lock sudo out
# entirely, so this checks it in isolation first rather than trusting it.
if visudo -c -f "$TMP_FILE" >/dev/null; then
    chmod 440 "$TMP_FILE"
    mv "$TMP_FILE" "$SUDOERS_FILE"
    echo "Done. $TARGET_USER can now run sudo without a password on this machine."
    echo "Next:  ./nora install"
else
    echo "Generated sudoers file failed validation — nothing was changed." >&2
    rm -f "$TMP_FILE"
    exit 1
fi
