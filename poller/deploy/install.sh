#!/usr/bin/env bash
#
# install.sh — install the SD-LAN poller on Ubuntu (20.04 / 22.04 / 24.04).
#
# Idempotent: safe to re-run to upgrade. Never overwrites
# /etc/sdlan-poller/config.json once it exists (it holds credentials).
#
# Usage, from the poller/ directory of a checkout on the box:
#     sudo bash deploy/install.sh
#
# Then:
#     sudo nano /etc/sdlan-poller/config.json     # url + credentials + property
#     cd /opt/sdlan-poller/app
#     sudo -u sdlan-poller /opt/sdlan-poller/venv/bin/python probe.py
#     sudo -u sdlan-poller /opt/sdlan-poller/venv/bin/python preflight.py
#     sudo systemctl enable --now sdlan-poller
#
set -euo pipefail

APP_USER=sdlan-poller
APP_DIR=/opt/sdlan-poller/app
VENV_DIR=/opt/sdlan-poller/venv
CONF_DIR=/etc/sdlan-poller
STATE_DIR=/var/lib/sdlan-poller
LOG_DIR=/var/log/sdlan-poller

say() { printf '\n=== %s\n' "$*"; }

if [[ $EUID -ne 0 ]]; then
    echo "Run with sudo: sudo bash deploy/install.sh" >&2
    exit 1
fi

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ ! -f "$SRC/main.py" ]]; then
    echo "Cannot find main.py next to deploy/ — run this from the poller/ directory." >&2
    exit 1
fi
say "installing from $SRC"

say "1/8  installing OS packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq python3 python3-venv python3-pip logrotate sqlite3 >/dev/null

say "2/8  creating service account $APP_USER"
if ! id -u "$APP_USER" >/dev/null 2>&1; then
    useradd --system --no-create-home --shell /usr/sbin/nologin "$APP_USER"
    echo "     created"
else
    echo "     already exists"
fi

say "3/8  creating directories"
install -d -m 0755 -o root        -g root        /opt/sdlan-poller
install -d -m 0755 -o root        -g root        "$APP_DIR"
install -d -m 0750 -o root        -g "$APP_USER" "$CONF_DIR"
install -d -m 0750 -o "$APP_USER" -g "$APP_USER" "$STATE_DIR"
install -d -m 0750 -o "$APP_USER" -g "$APP_USER" "$LOG_DIR"

say "4/8  copying application files"
for f in main.py config.py sdlan_client.py mapper.py state_store.py \
         outbound_queue.py uploader.py probe.py preflight.py; do
    if [[ -f "$SRC/$f" ]]; then
        install -m 0644 -o root -g root "$SRC/$f" "$APP_DIR/$f"
        echo "     $f"
    else
        echo "     WARNING: $SRC/$f not found, skipped"
    fi
done
install -d -m 0755 "$APP_DIR/deploy"
install -m 0644 "$SRC/deploy/config.example.json" "$APP_DIR/deploy/config.example.json"
[[ -f "$SRC/deploy/DEPLOY.md" ]] && \
    install -m 0644 "$SRC/deploy/DEPLOY.md" "$APP_DIR/deploy/DEPLOY.md"
# mock_sdlan.py and tests/ are test fixtures — deliberately NOT installed.

say "5/8  creating virtualenv and installing dependencies"
if [[ ! -x "$VENV_DIR/bin/python" ]]; then
    python3 -m venv "$VENV_DIR"
fi
"$VENV_DIR/bin/pip" install --quiet --upgrade pip
if [[ -f "$SRC/requirements.txt" ]]; then
    "$VENV_DIR/bin/pip" install --quiet -r "$SRC/requirements.txt"
else
    "$VENV_DIR/bin/pip" install --quiet "requests>=2.31.0"
fi
echo "     $("$VENV_DIR/bin/python" -V), requests $("$VENV_DIR/bin/python" -c 'import requests;print(requests.__version__)')"

say "6/8  installing config template"
if [[ -f "$CONF_DIR/config.json" ]]; then
    echo "     $CONF_DIR/config.json already exists — left untouched"
else
    install -m 0640 -o root -g "$APP_USER" \
        "$SRC/deploy/config.example.json" "$CONF_DIR/config.json"
    echo "     wrote $CONF_DIR/config.json (mode 0640, holds credentials)"
    echo "     >>> EDIT IT before starting the service <<<"
fi

say "7/8  installing logrotate rule"
install -m 0644 "$SRC/deploy/sdlan-poller.logrotate" /etc/logrotate.d/sdlan-poller
logrotate --debug /etc/logrotate.d/sdlan-poller >/dev/null 2>&1 \
    && echo "     rule validates" || echo "     WARNING: logrotate reported a problem"

say "8/8  installing systemd unit"
install -m 0644 "$SRC/deploy/sdlan-poller.service" \
    /etc/systemd/system/sdlan-poller.service
systemctl daemon-reload
echo "     installed (not started)"

cat <<EOF

========================================================================
Install complete. The service is NOT running yet.

  1. Configure the platform URL and credentials
       sudo nano $CONF_DIR/config.json
     Set: edge_id, property_id, property_name, cloud_endpoint,
          sdlan_base_url, sdlan_username, sdlan_password, device_id_prefix

  2. See what the platform actually returns
       cd $APP_DIR
       sudo -u $APP_USER $VENV_DIR/bin/python probe.py

     If the API rejects the request encoding:
       sudo -u $APP_USER $VENV_DIR/bin/python probe.py --try-formats

  3. Check readiness (10 checks, includes a live test POST to the cloud)
       sudo -u $APP_USER $VENV_DIR/bin/python preflight.py

  4. Try one real poll without installing the service
       sudo -u $APP_USER $VENV_DIR/bin/python main.py --once

  5. Start it
       sudo systemctl enable --now sdlan-poller
       journalctl -u sdlan-poller -f

Useful:
  systemctl status sdlan-poller
  journalctl -u sdlan-poller --since "30 min ago"
  sudo sqlite3 $STATE_DIR/state.db "SELECT device_id, status, score FROM device_state;"
  sudo sqlite3 $STATE_DIR/queue.db "SELECT state, kind, COUNT(*) FROM outbound GROUP BY state, kind;"
  sudo tail -f $LOG_DIR/cloud_upload.log
========================================================================
EOF
