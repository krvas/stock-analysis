from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]


def _git(*args: str) -> bytes:
    return subprocess.run(
        ["git", "-C", str(REPO), *args], check=True, capture_output=True
    ).stdout


def tree_state() -> dict[str, str]:
    digest = hashlib.sha256(_git("diff", "HEAD", "--binary", "--", "src"))
    untracked = _git("ls-files", "-z", "--others", "--exclude-standard", "--", "src")
    for name in sorted(filter(None, untracked.split(b"\0"))):
        digest.update(b"\0" + name + b"\0")
        digest.update((REPO / name.decode()).read_bytes())
    return {
        "git_rev": _git("rev-parse", "HEAD").decode().strip(),
        "src_diff_sha256": digest.hexdigest(),
    }


def check(server_json: Path) -> int:
    launched = json.loads(server_json.read_text())
    now = tree_state()
    stale = [key for key, value in now.items() if launched.get(key) != value]
    if stale:
        for key in stale:
            print(f"FAIL {key} at launch {launched.get(key)} != now {now[key]}")
        print("FAIL server runs code older than the tree: stop.sh, then serve.py")
        return 1
    print(f"ok   server runs the current tree ({now['git_rev'][:10]})")
    return 0


if __name__ == "__main__":
    if sys.argv[1:2] != ["check"] or len(sys.argv) != 3:
        sys.exit("usage: tree_state.py check SERVER_JSON")
    sys.exit(check(Path(sys.argv[2])))
