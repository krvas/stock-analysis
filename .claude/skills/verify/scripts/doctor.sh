#!/usr/bin/env bash
# Read-only health check for one verification run.
# Usage: .claude/skills/verify/scripts/doctor.sh RUN_DIR
set -u
run_dir="${1:?usage: doctor.sh RUN_DIR}"
state="$run_dir/server.json"
[ -f "$state" ] || { echo "FAIL no $state: this run never started a server"; exit 1; }
port=$(sed -E 's/.*"port": ([0-9]+).*/\1/' "$state")
pid=$(sed -E 's/.*"pid": ([0-9]+).*/\1/' "$state")
db=$(sed -E 's/.*"wizard_db": "([^"]+)".*/\1/' "$state")
ok=0
if kill -0 "$pid" 2>/dev/null; then echo "ok   server pid $pid alive"; else echo "FAIL server pid $pid not running"; ok=1; fi
owner=$(lsof -nP -iTCP:"$port" -sTCP:LISTEN -t 2>/dev/null | head -1)
if [ "$owner" = "$pid" ]; then echo "ok   port $port owned by this run"; else echo "FAIL port $port owned by '${owner:-nobody}', not $pid"; ok=1; fi
root=$(curl -s -m 5 "http://127.0.0.1:$port/")
case "$root" in *'"wizard":"/wizard/{ticker}"'*) echo "ok   / answers as the Stock Analysis app";; *) echo "FAIL / did not answer as the app: ${root:0:120}"; ok=1;; esac
case "$db" in */data/duckdb/wizard.duckdb) echo "FAIL run is pointed at the user's real wizard DB"; ok=1;; *) echo "ok   wizard DB $db";; esac
echo "rev  $(git -C "$(dirname "$0")/../../../.." rev-parse --short HEAD)$(git -C "$(dirname "$0")/../../../.." diff --quiet || echo ' +uncommitted')"
exit $ok
