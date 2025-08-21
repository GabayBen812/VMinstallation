#!/usr/bin/env bash
set -euo pipefail

# ---- config (edit names as you add scripts) ----
SERVICE_NAME="tassmonitor"
SCRIPT_REL_DIR="TassMonitor"
ENTRY_PY="main.py"

# ---- paths ----
APP_ROOT="$(cd "$(dirname "$0")" && pwd)"
SCRIPT_DIR="$APP_ROOT/$SCRIPT_REL_DIR"
PY_MAIN="$SCRIPT_DIR/$ENTRY_PY"
VENV_DIR="$APP_ROOT/.venv"
UNIT="/etc/systemd/system/${SERVICE_NAME}.service"
RUN_USER="$(id -un)"

# ---- base deps (Debian/Ubuntu) ----
if command -v apt >/dev/null; then
  sudo apt update -y
  sudo apt install -y python3 python3-venv python3-pip
fi

# ---- venv & python deps ----
python3 -m venv "$VENV_DIR"
"$VENV_DIR/bin/pip" -q install --upgrade pip
"$VENV_DIR/bin/pip" -q install -r "$SCRIPT_DIR/requirements.txt"

# ---- .env (optional) ----
# Put secrets in $APP_ROOT/.env (key=value per line)
# Example: DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
[ -f "$APP_ROOT/.env" ] || touch "$APP_ROOT/.env"

# ---- verify webhook configured ----
WEBHOOK_LINE="$(grep -E '^DISCORD_WEBHOOK_URL=' "$APP_ROOT/.env" || true)"
if [ -z "$WEBHOOK_LINE" ] || ! echo "$WEBHOOK_LINE" | grep -q 'https://discord.com/api/webhooks/'; then
  echo "ERROR: Please set DISCORD_WEBHOOK_URL in $APP_ROOT/.env before installing."
  echo "Example: DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/..."
  exit 1
fi

# ---- state dir ----
mkdir -p "$SCRIPT_DIR/state"

# ---- systemd unit ----
sudo tee "$UNIT" >/dev/null <<EOF
[Unit]
Description=${SERVICE_NAME}
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
User=${RUN_USER}
WorkingDirectory=${SCRIPT_DIR}
EnvironmentFile=${APP_ROOT}/.env
ExecStart=${VENV_DIR}/bin/python ${PY_MAIN}
Restart=always
RestartSec=5
# Give the app a clean env with venv first
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now "$SERVICE_NAME"
echo "Installed. Status: sudo systemctl status ${SERVICE_NAME}"
