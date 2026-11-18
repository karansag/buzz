"""Tables from bench/db_scale.py results: p50 / p95 ms per workload, per setup.

Usage: python bench/db_report.py RESULTS_DIR
Each file is RESULTS_DIR/<size>-<setup>.json. Also checks that every setup
returned the same answers as sqlite-asis at the same size.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

SETUPS = ["sqlite-asis", "sqlite-idx", "sqlite-tuned", "pg-asis", "pg-tuned"]
ROWS = ["state", "owner_chats_all", "agent_talk_4000", "history_open", "history_scroll_5_pages",
        "jump_to_old", "search the", "search tpu", "search snowball eval", 'search "model switch"',
        "search zqxjkv", "search from:owner merge", "search -done error", "write"]


def cell(r: dict | None) -> str:
    if r is None:
        return "—"
    return f"{r['p50']:g} / {r['p95']:g}"


def main(folder: Path) -> None:
    sizes = sorted({p.name.split("-sqlite")[0].split("-pg")[0] for p in folder.glob("*.json")},
                   key=lambda s: -1 if s == "now" else int(s))
    for size in sizes:
        found = {s: json.loads((folder / f"{size}-{s}.json").read_text())
                 for s in SETUPS if (folder / f"{size}-{s}.json").exists()}
        if not found:
            continue
        rows = next(iter(found.values()))["plan"]
        print(f"\n### {size} messages" if size != "now" else "\n### now (copy of the live DB)")
        print(f"\nLargest conversations: {rows['sizes']}\n")
        print("| workload (ms, p50 / p95) | " + " | ".join(found) + " |")
        print("|---|" + "---|" * len(found))
        for name in ROWS:
            print(f"| {name} | " + " | ".join(cell(r["results"].get(name)) for r in found.values()) + " |")
        for part in ("reads", "writes"):
            print(f"| mixed load: {part} | "
                  + " | ".join(cell(r["results"]["mixed"][part]) for r in found.values()) + " |")
        print("| mixed load: reads/s | "
              + " | ".join(str(r["results"]["mixed"]["reads_per_s"]) for r in found.values()) + " |")
        print("| prepare (s) | " + " | ".join(str(r["prepare_s"]) for r in found.values()) + " |")
        base = found.get("sqlite-asis")
        for setup, r in found.items():
            if base is None or setup == "sqlite-asis":
                continue
            diff = [k for k, v in base["answers"].items() if r["answers"].get(k) != v]
            errors = r["results"]["mixed"]["error_count"]
            print(f"\n{setup}: {len(diff)} answers differ from sqlite-asis"
                  + (f" ({diff[:4]})" if diff else "") + (f"; {errors} errors under load" if errors else ""))


if __name__ == "__main__":
    main(Path(sys.argv[1]))
