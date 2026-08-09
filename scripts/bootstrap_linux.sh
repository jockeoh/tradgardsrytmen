#!/usr/bin/env bash
set -euo pipefail

[[ $EUID -eq 0 ]] || { echo "Kör med sudo." >&2; exit 1; }
CHECKOUT=/home/clawd/.codex/tradgardsrytmen
ENV_FILE=/etc/tradgardsrytmen/tradgardsrytmen.env

id tradgardsrytmen >/dev/null 2>&1 || useradd --system --home /var/lib/tradgardsrytmen --shell /usr/sbin/nologin tradgardsrytmen
install -d -m 0755 /opt/tradgardsrytmen /etc/tradgardsrytmen
install -d -m 0750 -o tradgardsrytmen -g tradgardsrytmen /var/lib/tradgardsrytmen /var/lib/tradgardsrytmen/backups

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Skapa $ENV_FILE med appens hemligheter före bootstrap." >&2
  exit 1
fi
chmod 0600 "$ENV_FILE"
install -m 0755 "$CHECKOUT/scripts/auto_deploy_linux.sh" /usr/local/sbin/tradgardsrytmen-auto-deploy
install -m 0644 "$CHECKOUT/systemd/tradgardsrytmen-autodeploy.service" "$CHECKOUT/systemd/tradgardsrytmen-autodeploy.timer" /etc/systemd/system/
systemctl daemon-reload
/usr/local/sbin/tradgardsrytmen-auto-deploy

