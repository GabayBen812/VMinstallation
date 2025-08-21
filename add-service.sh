#!/usr/bin/env bash
# Usage: ./add-service.sh <service_name> <relative_dir> [entry_py=main.py]
set -euo pipefail
APP_ROOT="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$APP_ROOT/.venv"
RUN_USER="$(id -un)"

NAME="${1:?service_name}"
REL_DIR="${2:?relative_dir}"
ENTRY="${3:-main.py}"

SCRIPT_DIR="$APP_ROOT/$REL_DIR"
PY_MAIN="$SCRIPT_DIR/$ENTRY"
UNIT="/etc/systemd/system/${NAME}.service"

mkdir -p "$SCRIPT_DIR/state"

sudo tee "$UNIT" >/dev/null <<EOF
[Unit]
Description=${NAME}
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
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now "$NAME"
echo "Added service '${NAME}'."
