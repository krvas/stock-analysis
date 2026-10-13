#!/usr/bin/env bash
# Stop the server this run started and delete its DB copy. Evidence stays.
# Usage: .claude/skills/verify/scripts/stop.sh RUN_DIR
set -u
run_dir="${1:?usage: stop.sh RUN_DIR}"
pid_file="$run_dir/server.pid"
if [ -f "$pid_file" ]; then
  pid=$(cat "$pid_file")
  kill "$pid" 2>/dev/null && echo "stopped pid $pid" || echo "pid $pid already gone"
  for _ in 1 2 3 4 5; do kill -0 "$pid" 2>/dev/null || break; sleep 1; done
  rm -f "$pid_file" "$run_dir/server.json"
fi
rm -f "$run_dir/wizard.duckdb" "$run_dir/wizard.duckdb.wal"
echo "evidence kept in $run_dir/evidence"
