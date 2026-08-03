#!/usr/bin/env bash
#
# One-time provisioning for the Raspberry Pi 5.
#
#     curl -fsSL https://raw.githubusercontent.com/<you>/nora-home/main/scripts/install-pi.sh | bash
#
# or, from a clone:  ./scripts/install-pi.sh
#
# Installs Docker, brings the house up, and configures both displays: the 24"
# wall screen on HDMI-0 and the 10.1" kiosk on HDMI-1, each auto-starting
# Chromium in kiosk mode pointed at the right URL. After this, updating is
# `make deploy` and nothing else.
#
set -euo pipefail

REPO_DIR="${NORA_HOME_DIR:-$HOME/nora-home}"
NORA_HOME_PORT="${NORA_HOME_PORT:-8000}"
WALL_URL="http://localhost:${NORA_HOME_PORT}/home/displays/wall/"
KIOSK_URL="http://localhost:${NORA_HOME_PORT}/home/displays/kiosk/"

info()  { printf '\n\033[1;36m==>\033[0m %s\n' "$*"; }
warn()  { printf '\033[1;33m warning:\033[0m %s\n' "$*"; }

[[ $EUID -eq 0 ]] && { echo "Run this as your normal user, not root."; exit 1; }

# ── 1. Docker ─────────────────────────────────────────────────────────────────
if ! command -v docker >/dev/null 2>&1; then
    info "Installing Docker"
    curl -fsSL https://get.docker.com | sh
    sudo usermod -aG docker "$USER"
    warn "You were added to the docker group. Log out and back in, then re-run this."
    exit 0
fi

# ── 2. System packages ────────────────────────────────────────────────────────
info "Installing supporting packages"
sudo apt-get update -qq
sudo apt-get install -y --no-install-recommends \
    git make chromium-browser unclutter xdotool wtype

# ── 3. The repo ───────────────────────────────────────────────────────────────
if [[ ! -d "$REPO_DIR" ]]; then
    info "Cloning Nora Home into $REPO_DIR"
    git clone "${NORA_HOME_REPO:?Set NORA_HOME_REPO to your git URL}" "$REPO_DIR"
fi
cd "$REPO_DIR"

if [[ ! -f .env ]]; then
    info "Creating .env with a fresh secret key"
    cp .env.example .env
    python3 -c "import secrets;print('DJANGO_SECRET_KEY='+secrets.token_urlsafe(50))" >> .env
    sed -i 's/^NORA_HOME_ENV=.*/NORA_HOME_ENV=pi/' .env
    sed -i 's#^DJANGO_SETTINGS_MODULE=.*#DJANGO_SETTINGS_MODULE=config.settings.pi#' .env
    sed -i 's/^NORA_HOME_DB_ENGINE=.*/NORA_HOME_DB_ENGINE=mysql/' .env
    sed -i 's/^DJANGO_DEBUG=.*/DJANGO_DEBUG=0/' .env
    sed -i 's/^NORA_HOME_S3_ENABLED=.*/NORA_HOME_S3_ENABLED=1/' .env
    # The .env.example default (localhost/127.0.0.1/nora.home/nora.local) 400s
    # every request from a phone or laptop hitting the Pi by its LAN IP, which is
    # how everyone actually reaches it. The LAN is already the trust boundary
    # everywhere else in this house — see CLAUDE.md §4 — so allow all of it.
    sed -i 's/^DJANGO_ALLOWED_HOSTS=.*/DJANGO_ALLOWED_HOSTS=*/' .env
    warn "Add your Slack and Anthropic keys to $REPO_DIR/.env when you have them."
fi

# ── 4. Bring the house up ─────────────────────────────────────────────────────
info "Starting the house (this builds images on first run — expect ~10 minutes)"
docker compose up -d --build

# ── 5. Start on boot ──────────────────────────────────────────────────────────
info "Installing the systemd unit so the house starts with the Pi"
sudo tee /etc/systemd/system/nora-home.service >/dev/null <<UNIT
[Unit]
Description=Nora Home
Requires=docker.service
After=docker.service network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=$REPO_DIR
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose down
User=$USER

[Install]
WantedBy=multi-user.target
UNIT
sudo systemctl daemon-reload
sudo systemctl enable nora-home.service

# ── 6. X11, not Wayland ───────────────────────────────────────────────────────
# Raspberry Pi OS defaults to labwc (Wayland) on the Pi 4/5. labwc refuses to
# let anything — not Chromium's own flags, not xdotool, not even labwc's own
# MoveToOutput action — reposition a fullscreen window once placed, so the wall
# and kiosk always land on whichever output the compositor picks, not the one
# each is meant for. Confirmed by actually running both on real dual-monitor
# hardware (see docs/progress.md, 2026-08-02). X11 (openbox) honors
# --window-position/--window-size the normal way, so switch to it here rather
# than rediscovering this from scratch on every fresh Pi.
if command -v raspi-config >/dev/null 2>&1; then
    CURRENT_SESSION="$(grep -oP '(?<=^autologin-session=).*' /etc/lightdm/lightdm.conf 2>/dev/null || true)"
    if [[ "$CURRENT_SESSION" != *-x ]]; then
        info "Switching the desktop session from Wayland to X11 (needed for correct wall/kiosk placement)"
        sudo raspi-config nonint do_wayland W1
        warn "Session switched to X11 — takes effect after the reboot at the end of this script."
    fi
else
    warn "raspi-config not found — could not switch to X11. If the wall and kiosk" \
         "end up on the same screen, see docs/progress.md (2026-08-02) for why, and" \
         "run: sudo raspi-config nonint do_wayland W1 && sudo reboot"
fi

# ── 7. The two displays ───────────────────────────────────────────────────────
# The first HDMI output is the 24" wall screen (1920x1080), the second the
# touchscreen kiosk (1024x600 on the hardware this was verified against — check
# `wlr-randr` if it's ever swapped for a different panel). Each gets its own
# Chromium profile so their sessions and zoom levels stay independent.
info "Configuring both displays for kiosk mode"
mkdir -p "$HOME/.config/autostart" "$HOME/.nora"

launch_script() {
    local name="$1" url="$2" position="$3" size="$4" profile="$HOME/.nora/chromium-$1"
    cat > "$HOME/.nora/start-$name.sh" <<SCRIPT
#!/usr/bin/env bash
# Wait for the app to answer before opening a window; a kiosk showing a
# connection error is worse than a black screen for thirty more seconds.
for _ in \$(seq 1 60); do
    curl -fsS "http://localhost:${NORA_HOME_PORT}/home/health/" >/dev/null 2>&1 && break
    sleep 5
done

unclutter -idle 3 &

# --window-position alone only says where the window starts before going
# fullscreen; --kiosk then fullscreens whichever monitor that starting window
# overlaps most, and Chromium's default window size can overlap the wrong one
# on a mixed-resolution multi-monitor layout like this. --window-size pins it
# to the real target output so it fullscreens there, not the other screen.
# The apt package is called chromium-browser, but the binary it installs is
# named differently across Debian releases — "chromium-browser" on some,
# plain "chromium" on others (confirmed: Raspberry Pi OS on Trixie only ships
# /usr/bin/chromium). Resolve it at launch time instead of hardcoding either.
CHROMIUM="\$(command -v chromium-browser || command -v chromium)"
if [[ -z "\$CHROMIUM" ]]; then
    echo "No chromium/chromium-browser binary found" >&2
    exit 1
fi

"\$CHROMIUM" \\
    --kiosk "$url" \\
    --user-data-dir="$profile" \\
    --window-position=$position \\
    --window-size=$size \\
    --ozone-platform=x11 \\
    --noerrdialogs \\
    --disable-infobars \\
    --disable-session-crashed-bubble \\
    --disable-features=TranslateUI \\
    --check-for-update-interval=31536000 \\
    --autoplay-policy=no-user-gesture-required \\
    --enable-features=OverlayScrollbar &
CHROMIUM_PID=\$!

# labwc applies its own window-placement policy when the window is mapped and
# ignores the --window-position/--window-size hints above, landing every kiosk
# window on whichever output is currently primary regardless of what Chromium
# asked for. Chromium flags can't out-argue the compositor; force it onto the
# right output after the fact with xdotool instead.
WIN=""
for _ in \$(seq 1 10); do
    WIN="\$(xdotool search --pid "\$CHROMIUM_PID" --onlyvisible 2>/dev/null | head -1)"
    [[ -n "\$WIN" ]] && break
    sleep 1
done
if [[ -n "\$WIN" ]]; then
    xdotool windowmove "\$WIN" ${position/,/ }
    xdotool windowsize "\$WIN" ${size/,/ }
    # --kiosk's own fullscreen transition happens a moment after launch and can
    # retrigger labwc's placement policy a second time; reassert once it's settled.
    sleep 2
    xdotool windowmove "\$WIN" ${position/,/ }
    xdotool windowsize "\$WIN" ${size/,/ }
else
    echo "Could not find the chromium window to reposition" >&2
fi

wait "\$CHROMIUM_PID"
SCRIPT
    chmod +x "$HOME/.nora/start-$name.sh"

    cat > "$HOME/.config/autostart/nora-$name.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=Nora $name display
Exec=$HOME/.nora/start-$name.sh
X-GNOME-Autostart-enabled=true
DESKTOP
}

launch_script "wall"  "$WALL_URL"  "0,0"    "1920,1080"
launch_script "kiosk" "$KIOSK_URL" "1920,0" "1024,600"

# Never blank the wall display.
cat > "$HOME/.config/autostart/nora-no-blank.desktop" <<'DESKTOP'
[Desktop Entry]
Type=Application
Name=Nora keep displays awake
Exec=sh -c "xset s off; xset -dpms; xset s noblank"
X-GNOME-Autostart-enabled=true
DESKTOP

info "Done."
cat <<SUMMARY

  The house is at    http://$(hostname -I | awk '{print $1}'):${NORA_HOME_PORT}/home/
  Wall display       ${WALL_URL}
  Kiosk controller   ${KIOSK_URL}

  Next:
    1. cd $REPO_DIR && make member NAME=<you>     create your login
    2. Sign in on the wall and kiosk screens once — they stay signed in
    3. sudo reboot                                 both screens come up on their own

  From now on, updating is:  cd $REPO_DIR && make deploy

SUMMARY
