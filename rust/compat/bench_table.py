"""Print one Markdown table from several bench.py result files.

    python rust/compat/bench_table.py RUN1/results.json RUN2/results.json [--variant NAME=RUN3/results.json]

Each cell is the mean over the runs that hold that hub. The last line says
how far the runs were apart, so a reader can judge the noise.
"""

from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path


def main() -> None:
    paths = [a for a in sys.argv[1:] if "=" not in a]
    variants = dict(a.removeprefix("--variant").strip().split("=", 1) for a in sys.argv[1:] if "=" in a)
    runs = [json.loads(Path(p).read_text()) for p in paths]
    columns = {"Python": [r["python"] for r in runs], "Rust": [r["rust"] for r in runs]}
    for name, path in variants.items():
        columns[name] = [json.loads(Path(path).read_text())["rust"]]
    spread = 0.0

    def cell(values: list[float], digits: int = 1) -> str:
        nonlocal spread
        if len(values) > 1 and min(values) > 0:
            spread = max(spread, max(values) / min(values) - 1)
        return f"{statistics.mean(values):,.{digits}f}"

    print("| Measure | " + " | ".join(columns) + " |\n|---|" + "---:|" * len(columns))
    simple = [("Cold start to first `/health` (ms), median of 5", lambda r: statistics.median(r["cold_start_s"]) * 1000),
              ("Memory (RSS) 3 s after start (MB)", lambda r: r["idle_rss_mb"]),
              ("Memory (RSS) after all load runs (MB)", lambda r: r["loaded_rss_mb"]),
              ("Peak memory (RSS) (MB)", lambda r: r["peak_rss_mb"])]
    for label, pick in simple:
        print(f"| {label} | " + " | ".join(cell([pick(r) for r in rs]) for rs in columns.values()) + " |")
    for case in runs[0]["python"]["cases"]:
        name, clients = case.rsplit(" c=", 1)
        who = f"{clients} client{'s' if clients != '1' else ''}"
        for label, key, digits in (("p50 / p95 (ms)", None, 1), ("requests/s", "per_second", 1), ("hub CPU per request (ms)", "hub_cpu_ms_per_request", 2)):
            cells = []
            for rs in columns.values():
                got = [r["cases"][case] for r in rs]
                if key is None:
                    cells.append(cell([g["p50_ms"] for g in got], 1) + " / " + cell([g["p95_ms"] for g in got], 1))
                else:
                    cells.append(cell([g[key] for g in got], digits))
            print(f"| `{name}`, {who}: {label} | " + " | ".join(cells) + " |")
    errors = sum(c["errors"] for rs in columns.values() for r in rs for c in r["cases"].values())
    print(f"\nFailed requests in all runs: {errors}. Largest gap between two runs of the same hub, any cell: {spread:.0%}.")


if __name__ == "__main__":
    main()
