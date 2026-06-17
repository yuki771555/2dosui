#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="${SERVICE_NAME:-twodosumi-web}"
APP_DIR="${APP_DIR:-/home/yuki/2dosumi}"
APP_USER="${APP_USER:-yuki}"
PYTHON_BIN="${PYTHON_BIN:-/usr/bin/python3}"
PORT="${PORT:-8080}"

sudo tee "/etc/systemd/system/${SERVICE_NAME}.service" >/dev/null <<SERVICE
[Unit]
Description=2dosumi Web UI
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${APP_USER}
WorkingDirectory=${APP_DIR}
Environment=PYTHONUNBUFFERED=1
ExecStart=${PYTHON_BIN} -m twodosumi web --config config/pi.aggregate.json --secrets config/secrets.json --host 127.0.0.1 --port ${PORT}
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
SERVICE

sudo systemctl daemon-reload
sudo systemctl enable "${SERVICE_NAME}.service"
sudo systemctl restart "${SERVICE_NAME}.service"
sudo systemctl status "${SERVICE_NAME}.service" --no-pager

cat <<EOF

Installed ${SERVICE_NAME}.service.

To expose the Web UI through Tailscale, run once:
  tailscale serve --bg ${PORT}

To check later:
  systemctl status ${SERVICE_NAME}.service --no-pager
  journalctl -u ${SERVICE_NAME}.service -f
  tailscale serve status
EOF
