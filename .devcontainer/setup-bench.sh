#!/usr/bin/env bash
# Creates a Frappe v16 bench with this app installed on two sites:
#   xlsform.localhost  (development, admin/admin)
#   test.localhost     (used by bench run-tests; allow_tests on)
# Idempotent: re-running skips steps that are already done.
set -euo pipefail
cd /home/frappe
BENCH=/home/frappe/bench/frappe-bench

if [ ! -d "$BENCH/apps/frappe" ]; then
  bench init --frappe-branch version-16 --skip-redis-config-generation --no-backups "$BENCH"
fi
cd "$BENCH"
bench set-config -g db_host mariadb
bench set-config -g redis_cache redis://redis-cache:6379
bench set-config -g redis_queue redis://redis-queue:6379
bench set-config -g redis_socketio redis://redis-queue:6379
bench set-config -gp developer_mode 1

if [ ! -e apps/xlsform ]; then
  ln -s /workspace/xlsform apps/xlsform
  ./env/bin/pip install -q -e apps/xlsform
  grep -qx xlsform sites/apps.txt || echo xlsform >> sites/apps.txt
fi

for SITE in xlsform.localhost test.localhost; do
  if [ ! -d "sites/$SITE" ]; then
    bench new-site "$SITE" --db-root-password 123 --admin-password admin --mariadb-user-host-login-scope='%'
    bench --site "$SITE" install-app xlsform
  fi
done
bench --site test.localhost set-config allow_tests true
bench use xlsform.localhost
