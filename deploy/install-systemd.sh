#!/usr/bin/env bash
# install-systemd.sh — install Job Scout as a daily systemd timer on a Linux box.
#
#   sudo bash deploy/install-systemd.sh
#
# It installs into /opt/job-scout, builds a virtual environment, and enables a
# timer that fires once a day. It changes nothing outside /opt/job-scout and
# /etc/systemd/system, and it never overwrites an existing .env, config.yaml or
# profile.yaml.
#
# Re-run it after a git pull to pick up new code.

set -euo pipefail

INSTALL_DIR="${INSTALL_DIR:-/opt/job-scout}"
SERVICE_USER="${SERVICE_USER:-${SUDO_USER:-$USER}}"
TIMEZONE="${TIMEZONE:-Europe/Copenhagen}"
RUN_AT="${RUN_AT:-12:00:00}"
EXTRAS="${EXTRAS:-gemini,jobspy}"

SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "=== Job Scout — systemd install ==="
echo "  source     : $SOURCE_DIR"
echo "  install to : $INSTALL_DIR"
echo "  run as     : $SERVICE_USER"
echo "  schedule   : $RUN_AT $TIMEZONE"
echo "  extras     : $EXTRAS"
echo

if [ "$(id -u)" -ne 0 ]; then
    echo "This needs root, because it writes to /etc/systemd/system." >&2
    echo "Run: sudo bash deploy/install-systemd.sh" >&2
    exit 1
fi

# Check the tools this script needs before it starts moving files around, so a
# missing one is a sentence rather than a half-finished install.
for tool in python3 rsync; do
    command -v "$tool" >/dev/null 2>&1 || {
        echo "This script needs '$tool', which is not installed." >&2
        echo "On Debian or Ubuntu: sudo apt-get install -y $tool" >&2
        [ "$tool" = "python3" ] && echo "  (you probably also want python3-venv)" >&2
        exit 1
    }
done

# python3 -m venv is a separate package on Debian and Ubuntu, and the failure it
# gives without it is famously unhelpful.
python3 -c "import venv" 2>/dev/null || {
    echo "python3 is installed but the venv module is not." >&2
    echo "On Debian or Ubuntu: sudo apt-get install -y python3-venv" >&2
    exit 1
}

# ─── 1. Copy the code into place ──────────────────────────────────────────────
echo "[1/5] Copying into $INSTALL_DIR"
mkdir -p "$INSTALL_DIR"
if [ "$SOURCE_DIR" != "$INSTALL_DIR" ]; then
    # Config, secrets and the jobs database belong to the machine, not the
    # checkout. Never copy over them.
    rsync -a --delete \
        --exclude '.git' --exclude '.venv' --exclude 'data' \
        --exclude '.env' --exclude 'config.yaml' --exclude 'profile.yaml' \
        --exclude 'outcomes.csv' \
        "$SOURCE_DIR/" "$INSTALL_DIR/"
fi
mkdir -p "$INSTALL_DIR/data"

# ─── 2. Virtual environment ───────────────────────────────────────────────────
echo "[2/5] Building the virtual environment"
if [ ! -x "$INSTALL_DIR/.venv/bin/python" ]; then
    python3 -m venv "$INSTALL_DIR/.venv"
fi
"$INSTALL_DIR/.venv/bin/pip" install --quiet --upgrade pip
"$INSTALL_DIR/.venv/bin/pip" install --quiet -e "$INSTALL_DIR[$EXTRAS]"

if [[ "$EXTRAS" == *jobindex* ]]; then
    echo "      Installing Chromium for the JobIndex source"
    "$INSTALL_DIR/.venv/bin/playwright" install chromium --with-deps 2>&1 | tail -3
fi

# ─── 3. Config and secrets ────────────────────────────────────────────────────
echo "[3/5] Config and secrets"
if [ ! -f "$INSTALL_DIR/config.yaml" ]; then
    "$INSTALL_DIR/.venv/bin/job-scout" init "$INSTALL_DIR" >/dev/null
    echo "      Wrote an example config.yaml and profile.yaml. Edit them."
fi
if [ ! -f "$INSTALL_DIR/.env" ]; then
    cp "$INSTALL_DIR/.env.example" "$INSTALL_DIR/.env" 2>/dev/null || touch "$INSTALL_DIR/.env"
    echo "      Wrote $INSTALL_DIR/.env. Put your API key in it."
fi
chmod 600 "$INSTALL_DIR/.env"
chown -R "$SERVICE_USER" "$INSTALL_DIR"

# ─── 4. systemd units ─────────────────────────────────────────────────────────
echo "[4/5] Installing systemd units"
sed "s|^User=%i$|User=$SERVICE_USER|; s|^WorkingDirectory=.*|WorkingDirectory=$INSTALL_DIR|; \
     s|^ExecStart=.*|ExecStart=$INSTALL_DIR/.venv/bin/job-scout run|; \
     s|^ReadWritePaths=.*|ReadWritePaths=$INSTALL_DIR/data|" \
    "$INSTALL_DIR/deploy/job-scout.service" > /etc/systemd/system/job-scout.service

sed "s|^OnCalendar=.*|OnCalendar=*-*-* $RUN_AT $TIMEZONE|; \
     s|^Unit=.*|Unit=job-scout.service|" \
    "$INSTALL_DIR/deploy/job-scout.timer" > /etc/systemd/system/job-scout.timer

systemctl daemon-reload
systemctl enable --now job-scout.timer

# ─── 5. Check ─────────────────────────────────────────────────────────────────
echo "[5/5] Checking the install"
sudo -u "$SERVICE_USER" "$INSTALL_DIR/.venv/bin/job-scout" check --config-dir "$INSTALL_DIR" || true

cat <<EOF

=== Done ===

Next:
  1. Put your API key in $INSTALL_DIR/.env
  2. Edit $INSTALL_DIR/profile.yaml
  3. Run it once by hand:   sudo systemctl start job-scout.service
     Watch it:              sudo journalctl -u job-scout -f
  4. When it fires next:    systemctl list-timers job-scout.timer
EOF
