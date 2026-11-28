"""Load the existing dashboard from each hub in headless Chrome.

Each hub serves its own copy of the database given with --db (or an empty
one). Prints, per hub, what the page drew and every request it made.

    python rust/compat/dashboard_smoke.py [--db COPY.sqlite] [--out DIR]
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from hubs import REPO, SCRATCH, Hub, Tmux, copy_db  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, help="a COPY of a real database; never the live one")
    parser.add_argument("--node", default="karans-linux")
    parser.add_argument("--out", type=Path, default=SCRATCH / "dashboard")
    args = parser.parse_args()
    work = args.out / f"run-{os.getpid()}"
    results = {}
    for kind in ("python", "rust"):
        (work / kind).mkdir(parents=True)
        tmux = Tmux(f"rustclone-d{kind[:2]}-{os.getpid()}", work)
        db = work / kind / "dash.sqlite"
        if args.db:
            assert ".agent-swarm" not in str(args.db.resolve()), "give a copy, never the live database"
            copy_db(args.db, db)
        try:
            pane = tmux.start(1)[0]
            hub = Hub(kind, db, tmux, node=args.node)
            try:
                hub.call("POST", "/register", {"tmux_pane": pane, "requested_user": "smoke-agent"})
                shot = work / f"{kind}.png"
                done = subprocess.run(["node", "rust/compat/dashboard_smoke.mjs", hub.base, str(shot)],
                                      cwd=REPO, capture_output=True, text=True, timeout=120)
                results[kind] = json.loads(done.stdout) if done.returncode == 0 else {"failed": done.stderr[-800:]}
            finally:
                hub.stop()
        finally:
            tmux.kill()
            for leftover in db.parent.glob("dash.sqlite*"):
                leftover.unlink()
    print(json.dumps(results, indent=1))
    print(f"screenshots (private: they show message text): {work}")
    ok = all("failed" not in r and not r["bad"] and not r["errors"] for r in results.values())
    drawn = {kind: r.get("drawn", {}) for kind, r in results.items()}
    for key in ("elements", "textLength", "agentTiles"):
        print(f"{key}: python {drawn['python'].get(key)}, rust {drawn['rust'].get(key)}")
    print(f"no failed requests or page errors on either hub: {ok}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
