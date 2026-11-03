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
bench --site xlsform.localhost set-config allow_tests true
bench --site xlsform.localhost execute xlsform.tests.ui_support.complete_setup
grep -q "xlsform.localhost" /etc/hosts || echo "127.0.0.1 xlsform.localhost test.localhost" | sudo tee -a /etc/hosts >/dev/null
bench use xlsform.localhost

# Dev-only tools, kept out of the bench env so they can't disturb Frappe's pinned dependencies.
[ -d ~/pyxform-venv ] || { python3.14 -m venv ~/pyxform-venv && ~/pyxform-venv/bin/pip install -q pyxform==4.5.0; }
[ -d ~/lint-venv ] || { python3.14 -m venv ~/lint-venv && ~/lint-venv/bin/pip install -q ruff==0.14.10 pre-commit semgrep; }
./env/bin/pip install -q pytest pytest-cov
echo "Ready: http://xlsform.localhost:8010 (Administrator / admin). Start with: bench start"
