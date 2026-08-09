#!/usr/bin/env bash
set -euo pipefail
umask 027

CHECKOUT=/home/clawd/.codex/tradgardsrytmen
RUNTIME=/opt/tradgardsrytmen
APP="$RUNTIME/app"
VENV="$RUNTIME/venv"
ENV_FILE=/etc/tradgardsrytmen/tradgardsrytmen.env
STATE_DIR=/var/lib/tradgardsrytmen
LOCK_FILE=/run/lock/tradgardsrytmen-deploy.lock

exec 9>"$LOCK_FILE"
flock -n 9 || exit 0
cd "$CHECKOUT"
git_as_clawd() {
  runuser -u clawd -- git -C "$CHECKOUT" "$@"
}

if [[ -n "$(git_as_clawd status --porcelain)" ]]; then
  echo "Avbryter: checkouten innehåller lokala ändringar." >&2
  exit 1
fi

git_as_clawd fetch --quiet origin main
LOCAL_REV=$(git_as_clawd rev-parse HEAD)
REMOTE_REV=$(git_as_clawd rev-parse origin/main)
DEPLOYED_REV=$(cat "$STATE_DIR/deployed_commit" 2>/dev/null || true)
if [[ "$LOCAL_REV" == "$REMOTE_REV" && "$DEPLOYED_REV" == "$REMOTE_REV" ]]; then
  exit 0
fi

if [[ -f "$STATE_DIR/db.sqlite3" && -x "$VENV/bin/python" ]]; then
  runuser -u tradgardsrytmen -- env TRADGARDSRYTMEN_DB_PATH="$STATE_DIR/db.sqlite3" TRADGARDSRYTMEN_DATA_DIR="$STATE_DIR" "$VENV/bin/python" "$APP/manage.py" backup_database
fi

git_as_clawd pull --ff-only --quiet origin main
mkdir -p "$APP"
rsync -a --delete --exclude '.git' --exclude '.venv' --exclude 'db.sqlite3' --exclude 'staticfiles' "$CHECKOUT/" "$APP/"

python3.12 -m venv "$VENV"
"$VENV/bin/pip" install --quiet --disable-pip-version-check -r "$APP/requirements.txt"

set -a
source "$ENV_FILE"
set +a
runuser -u tradgardsrytmen -- "$VENV/bin/python" "$APP/manage.py" migrate --noinput
runuser -u tradgardsrytmen -- "$VENV/bin/python" "$APP/manage.py" seed_garden
"$VENV/bin/python" "$APP/manage.py" collectstatic --noinput
runuser -u tradgardsrytmen -- "$VENV/bin/python" "$APP/manage.py" check --deploy

install -m 0755 "$APP/scripts/auto_deploy_linux.sh" /usr/local/sbin/tradgardsrytmen-auto-deploy
install -m 0644 "$APP"/systemd/*.service "$APP"/systemd/*.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now tradgardsrytmen.service tradgardsrytmen-backup.timer tradgardsrytmen-tasks.timer tradgardsrytmen-reminders.timer tradgardsrytmen-autodeploy.timer tradgardsrytmen-tailscale.service
systemctl restart tradgardsrytmen.service

for _ in {1..20}; do
  if curl --fail --silent --show-error http://127.0.0.1:10443/health/ >/dev/null; then
    git_as_clawd rev-parse HEAD > "$STATE_DIR/deployed_commit"
    chown tradgardsrytmen:tradgardsrytmen "$STATE_DIR/deployed_commit"
    exit 0
  fi
  sleep 1
done
echo "Hälsokontrollen misslyckades efter driftsättning." >&2
exit 1
