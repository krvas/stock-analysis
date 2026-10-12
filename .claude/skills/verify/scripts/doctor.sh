#!/usr/bin/env bash
# Read-only health check for one verification run.
# Usage: .claude/skills/verify/scripts/doctor.sh RUN_DIR
set -u
here="$(cd "$(dirname "$0")" && pwd)"
py="$here/../../../../.venv/bin/python"
run_dir="${1:?usage: doctor.sh RUN_DIR}"
state="$run_dir/server.json"
[ -f "$state" ] || { echo "FAIL no $state: this run never started a server"; exit 1; }
IFS=$'\t' read -r port pid db < <("$py" -c '
import json, sys
s = json.load(open(sys.argv[1]))
print(s["port"], s["pid"], s["wizard_db"], sep="\t")' "$state")
ok=0
if kill -0 "$pid" 2>/dev/null; then echo "ok   server pid $pid alive"; else echo "FAIL server pid $pid not running"; ok=1; fi
owner=$(lsof -nP -iTCP:"$port" -sTCP:LISTEN -t 2>/dev/null | head -1)
if [ "$owner" = "$pid" ]; then echo "ok   port $port owned by this run"; else echo "FAIL port $port owned by '${owner:-nobody}', not $pid"; ok=1; fi
if curl -s -m 5 "http://127.0.0.1:$port/" | "$py" -c '
import json, sys
try:
    sys.exit(json.load(sys.stdin).get("wizard") != "/wizard/{ticker}")
except ValueError:
    sys.exit(1)'; then
  echo "ok   / answers as the Stock Analysis app"
else
  echo "FAIL / did not answer as the Stock Analysis app"; ok=1
fi
case "$db" in */data/duckdb/wizard.duckdb) echo "FAIL run is pointed at the user's real wizard DB"; ok=1;; *) echo "ok   wizard DB $db";; esac
"$py" "$here/tree_state.py" check "$state" || ok=1
exit $ok
