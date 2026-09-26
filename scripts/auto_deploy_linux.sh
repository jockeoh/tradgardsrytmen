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

# PostgreSQL cutover is separate; only a verified backend may be deployed.
if [[ -f "$ENV_FILE" ]]; then
  set -a
  source "$ENV_FILE"
  set +a
fi
case "${TRADGARDSRYTMEN_DB_ENGINE:-sqlite}" in
  sqlite) ;;
  postgresql)
    [[ "${TRADGARDSRYTMEN_POSTGRES_DEPLOY_READY:-0}" == 1 ]] || {
      echo "PostgreSQL cutover has not been verified; deployment stopped." >&2; exit 1;
    } ;;
  *) echo "Unsupported backend; deployment stopped." >&2; exit 1 ;;
esac

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
CARE_REPORT="$STATE_DIR/care-cleanup-$REMOTE_REV.json"
if [[ "$LOCAL_REV" == "$REMOTE_REV" && "$DEPLOYED_REV" == "$REMOTE_REV" && -f "$CARE_REPORT" ]]; then
  exit 0
fi

# Approval is tied to one verified revision, not a permanent bypass of CI.
git_as_clawd merge-base --is-ancestor "$LOCAL_REV" "$REMOTE_REV"
[[ "$(cat "$STATE_DIR/release-approved" 2>/dev/null || true)" == "$REMOTE_REV" ]] || {
  echo "Revision requires completed CI and an explicit release-approved marker." >&2
  exit 1
}
[[ -x "$VENV/bin/python" && -f "$APP/manage.py" ]] || {
  echo "Existing runtime required; first installation uses a separate bootstrap." >&2; exit 1;
}
: "${TRADGARDSRYTMEN_GARDEN_ID:?An explicit garden is required before maintenance}"
# Close the private ingress before draining bounded web requests. Timers are
# stopped, but running jobs are allowed to finish rather than killed mid-send.
systemctl stop tradgardsrytmen-autodeploy.timer tradgardsrytmen-reminders.timer tradgardsrytmen-tasks.timer tradgardsrytmen-backup.timer
for unit in tradgardsrytmen-jobs.timer tradgardsrytmen-jobs-health.timer; do
  if systemctl cat "$unit" >/dev/null 2>&1; then systemctl stop "$unit"; fi
done
systemctl stop tradgardsrytmen-tailscale.service
sleep 125
for unit in tradgardsrytmen-reminders.service tradgardsrytmen-tasks.service tradgardsrytmen-backup.service tradgardsrytmen-jobs.service; do
  for attempt in {1..180}; do
    state=$(systemctl show "$unit" -p ActiveState --value 2>/dev/null || true)
    [[ "$state" != active && "$state" != activating && "$state" != deactivating ]] && break
    sleep 1
  done
  [[ "$state" != active && "$state" != activating && "$state" != deactivating ]] || {
    echo "Writer still active: $unit; maintenance retained." >&2; exit 1;
  }
done
systemctl stop tradgardsrytmen.service
# Use the effective service backend/path. A missing source fails closed.
runuser -u tradgardsrytmen -- "$VENV/bin/python" "$APP/manage.py" backup_database

git_as_clawd merge --ff-only --quiet "$REMOTE_REV"
[[ "$(git_as_clawd rev-parse HEAD)" == "$REMOTE_REV" ]]
mkdir -p "$APP"
rsync -a --delete --exclude '.git' --exclude '.venv' --exclude 'db.sqlite3' --exclude 'staticfiles' "$CHECKOUT/" "$APP/"
chmod 0755 "$RUNTIME" "$APP"
chmod -R a+rX "$APP"

python3.12 -m venv "$VENV"
"$VENV/bin/pip" install --quiet --disable-pip-version-check -r "$APP/requirements.txt"
chmod -R a+rX "$VENV"

set -a
source "$ENV_FILE"
set +a
runuser -u tradgardsrytmen -- "$VENV/bin/python" "$APP/manage.py" migrate --noinput
: "${TRADGARDSRYTMEN_GARDEN_ID:?Set TRADGARDSRYTMEN_GARDEN_ID only after explicit legacy assignment}"
runuser -u tradgardsrytmen -- "$VENV/bin/python" "$APP/manage.py" seed_garden --garden "$TRADGARDSRYTMEN_GARDEN_ID"
# This is a deterministic local transition: it queues legacy rules for human
# review and archives only unambiguous automatic clutter. The command makes its
# own integrity-checked database backup and never invokes research or a model.
runuser -u tradgardsrytmen -- "$VENV/bin/python" "$APP/manage.py" clean_care_content --apply --report "$CARE_REPORT" --garden "$TRADGARDSRYTMEN_GARDEN_ID"
"$VENV/bin/python" "$APP/manage.py" collectstatic --noinput
chmod -R a+rX "$APP/staticfiles"
runuser -u tradgardsrytmen -- "$VENV/bin/python" "$APP/manage.py" check --deploy

install -m 0755 "$APP/scripts/auto_deploy_linux.sh" /usr/local/sbin/tradgardsrytmen-auto-deploy
install -m 0644 "$APP"/systemd/*.service "$APP"/systemd/*.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now tradgardsrytmen.service tradgardsrytmen-backup.timer tradgardsrytmen-tasks.timer tradgardsrytmen-reminders.timer tradgardsrytmen-autodeploy.timer tradgardsrytmen-tailscale.service
systemctl restart tradgardsrytmen.service
if [[ "${TRADGARDSRYTMEN_DURABLE_JOBS:-0}" == 1 ]]; then
  systemctl enable --now tradgardsrytmen-jobs.timer tradgardsrytmen-jobs-health.timer
fi

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
