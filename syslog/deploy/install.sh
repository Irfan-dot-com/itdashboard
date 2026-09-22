#!/usr/bin/env bash
#
# install.sh — install the syslog edge agent on Ubuntu (20.04 / 22.04 / 24.04).
#
# Idempotent: safe to re-run to upgrade an existing install. It never overwrites
# /etc/edge-agent/config.json once that file exists.
#
# Usage, from the syslog/ directory of a checkout on the edge box:
#     sudo bash deploy/install.sh
#
# Then:
#     sudo nano /etc/edge-agent/config.json      # set edge_id, property_id, endpoint, device_map
#     cd /opt/edge-agent/app && sudo -u edge-agent /opt/edge-agent/venv/bin/python preflight.py
#     sudo systemctl enable --now edge-agent
#     journalctl -u edge-agent -f
#
set -euo pipefail

APP_USER=edge-agent
APP_DIR=/opt/edge-agent/app
VENV_DIR=/opt/edge-agent/venv
CONF_DIR=/etc/edge-agent
STATE_DIR=/var/lib/edge-agent
LOG_DIR=/var/log/edge-agent

say() { printf '\n=== %s\n' "$*"; }

if [[ $EUID -ne 0 ]]; then
    echo "Run with sudo: sudo bash deploy/install.sh" >&2
    exit 1
fi

# Resolve the source directory (the syslog/ folder containing main.py)
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ ! -f "$SRC/main.py" ]]; then
    echo "Cannot find main.py next to deploy/ — run this from the syslog/ directory." >&2
    exit 1
fi
say "installing from $SRC"

say "1/8  installing OS packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq python3 python3-venv python3-pip logrotate >/dev/null

say "2/8  creating service account $APP_USER"
if ! id -u "$APP_USER" >/dev/null 2>&1; then
    useradd --system --no-create-home --shell /usr/sbin/nologin "$APP_USER"
    echo "     created"
else
    echo "     already exists"
fi

say "3/8  creating directories"
install -d -m 0755 -o root      -g root      /opt/edge-agent
install -d -m 0755 -o root      -g root      "$APP_DIR"
install -d -m 0750 -o root      -g "$APP_USER" "$CONF_DIR"
install -d -m 0750 -o "$APP_USER" -g "$APP_USER" "$STATE_DIR"
install -d -m 0750 -o "$APP_USER" -g "$APP_USER" "$LOG_DIR"

say "4/8  copying application files"
for f in main.py config.py aggregator.py classify.py outbound_queue.py \
         uploader.py syslog_listener.py discover.py preflight.py; do
    if [[ -f "$SRC/$f" ]]; then
        install -m 0644 -o root -g root "$SRC/$f" "$APP_DIR/$f"
        echo "     $f"
    else
        echo "     WARNING: $SRC/$f not found, skipped"
    fi
done
install -d -m 0755 "$APP_DIR/deploy"
install -m 0644 "$SRC/deploy/config.example.json" "$APP_DIR/deploy/config.example.json"
[[ -f "$SRC/deploy/DEPLOY.md" ]] && install -m 0644 "$SRC/deploy/DEPLOY.md" "$APP_DIR/deploy/DEPLOY.md"
# syslog_simulator.py is a test tool — deliberately NOT installed on an edge box.

say "5/8  creating virtualenv and installing dependencies"
if [[ ! -x "$VENV_DIR/bin/python" ]]; then
    python3 -m venv "$VENV_DIR"
fi
"$VENV_DIR/bin/pip" install --quiet --upgrade pip
if [[ -f "$SRC/requirements.txt" ]]; then
    "$VENV_DIR/bin/pip" install --quiet -r "$SRC/requirements.txt"
elif [[ -f "$SRC/deploy/requirements.txt" ]]; then
    "$VENV_DIR/bin/pip" install --quiet -r "$SRC/deploy/requirements.txt"
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
    echo "     wrote $CONF_DIR/config.json from the template"
    echo "     >>> EDIT IT before starting the service <<<"
fi

say "7/8  installing logrotate rule"
install -m 0644 "$SRC/deploy/edge-agent.logrotate" /etc/logrotate.d/edge-agent
logrotate --debug /etc/logrotate.d/edge-agent >/dev/null 2>&1 \
    && echo "     rule validates" || echo "     WARNING: logrotate reported a problem"

say "8/8  installing systemd unit"
install -m 0644 "$SRC/deploy/edge-agent.service" /etc/systemd/system/edge-agent.service
systemctl daemon-reload
echo "     installed (not started)"

cat <<EOF

========================================================================
Install complete. The service is NOT running yet — finish these steps:

  1. Configure this box
       sudo nano $CONF_DIR/config.json
     Set: edge_id, property_id, property_name, cloud_endpoint, listen_port
     Leave device_map for step 3.

  2. Check readiness (config, disk, port, cloud reachability, live POST)
       cd $APP_DIR
       sudo -u $APP_USER $VENV_DIR/bin/python preflight.py

  3. Discover the customer's devices, then fill in device_map
       sudo $VENV_DIR/bin/python $APP_DIR/discover.py --port 514 --duration 600
     Point the devices' syslog at this box first — nothing arrives otherwise.
     Merge the generated skeleton into device_map and re-run preflight.py.

  4. Start it
       sudo systemctl enable --now edge-agent
       journalctl -u edge-agent -f

Useful:
  systemctl status edge-agent
  journalctl -u edge-agent --since "10 min ago"
  sudo sqlite3 $STATE_DIR/queue.db "SELECT kind, COUNT(*) FROM outbound GROUP BY kind;"
  sudo tail -f $LOG_DIR/cloud_upload.log
========================================================================
EOF
