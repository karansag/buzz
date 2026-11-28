"""Measure the Python hub and the Rust hub on copies of the same database.

    python rust/compat/bench.py --db COPY.sqlite [--seconds 10] [--out DIR]

For each hub: cold start, idle memory, then latency and throughput of
GET /api/state, GET /messages and POST /send (delivered to a pane running
`cat` on an isolated tmux server) with 1 and with 16 clients. Writes
results.json and prints a Markdown table.

The clients are Python threads with one keep-alive connection each. Both
hubs are measured by the same client on the same machine, one after the
other, so the comparison is fair, but very fast answers are limited by the
client.
"""

from __future__ import annotations

import argparse
import http.client
import json
import os
import sqlite3
import statistics
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from hubs import SCRATCH, Hub, Tmux, copy_db  # noqa: E402

AGENTS = 16


def load(hub: Hub, requests: list[tuple[str, str, bytes | None]], clients: int, seconds: float) -> dict:
    """`clients` threads, each sending its own request in a closed loop."""
    latencies: list[list[float]] = [[] for _ in range(clients)]
    errors = [0] * clients
    sizes = [0] * clients
    start = threading.Barrier(clients + 1)
    stop_at = [0.0]

    def worker(i: int) -> None:
        method, path, body = requests[i % len(requests)]
        headers = {"Content-Type": "application/json"} if body else {}
        conn = http.client.HTTPConnection("127.0.0.1", hub.port, timeout=120)
        conn.request(method, path, body, headers)  # warm the connection
        conn.getresponse().read()
        start.wait()
        while time.perf_counter() < stop_at[0]:
            began = time.perf_counter()
            conn.request(method, path, body, headers)
            response = conn.getresponse()
            data = response.read()
            latencies[i].append(time.perf_counter() - began)
            sizes[i] = len(data)
            if response.status != 200 or (method == "POST" and b'"status":"delivered"' not in data.replace(b" ", b"")):
                errors[i] += 1
        conn.close()

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(clients)]
    for t in threads:
        t.start()
    cpu_before = hub.cpu_seconds()
    stop_at[0] = time.perf_counter() + seconds + 0.2
    began = time.perf_counter()
    start.wait()
    for t in threads:
        t.join()
    elapsed = time.perf_counter() - began
    cpu = hub.cpu_seconds() - cpu_before
    done = sorted(x for per in latencies for x in per)
    cut = statistics.quantiles(done, n=100) if len(done) > 1 else done * 99
    return {
        "clients": clients, "requests": len(done), "errors": sum(errors), "seconds": round(elapsed, 2),
        "per_second": round(len(done) / elapsed, 2), "p50_ms": round(cut[49] * 1000, 2), "p95_ms": round(cut[94] * 1000, 2),
        "hub_cpu_ms_per_request": round(cpu / max(1, len(done)) * 1000, 2), "hub_cpu_cores": round(cpu / elapsed, 2),
        "response_bytes": max(sizes),
    }


def cold_start(kind: str, db: Path, tmux: Tmux, node: str, runs: int) -> list[float]:
    """Seconds from process spawn to the first good /health, on an existing database."""
    out = []
    for _ in range(runs):
        hub = Hub(kind, db, tmux, node=node)
        out.append(round(hub.ready_after, 4))
        hub.stop()
    return out


def measure(kind: str, source: Path, work: Path, node: str, seconds: float) -> dict:
    tmux = Tmux(f"rustclone-b{kind[:2]}-{os.getpid()}", work)
    db = work / kind / "bench.sqlite"
    copy_db(source, db)
    result: dict = {"kind": kind}
    try:
        panes = tmux.start(AGENTS + 1)
        # The first start also brings the copy up to date (schema, index).
        Hub(kind, db, tmux, node=node).stop()
        result["cold_start_s"] = cold_start(kind, db, tmux, node, 5)
        hub = Hub(kind, db, tmux, node=node)
        try:
            time.sleep(3)
            result["idle_rss_mb"] = round(hub.rss_kb() / 1024, 1)
            sender = panes[0]
            status, body, _ = hub.call("POST", "/register", {"tmux_pane": sender, "requested_user": "bench-sender"})
            assert status == 200, body
            for i, pane in enumerate(panes[1:]):
                status, body, _ = hub.call("POST", "/register", {"tmux_pane": pane, "requested_user": f"bench-{i}"})
                assert status == 200, body
            with sqlite3.connect(f"file:{db}?mode=ro", uri=True) as conn:
                busiest = conn.execute("SELECT sender FROM messages GROUP BY sender ORDER BY COUNT(*) DESC LIMIT 1").fetchone()[0]
            conn.close()
            sends = [("POST", "/send", json.dumps({"tmux_pane": sender, "recipient": f"bench-{i}", "context": "bench",
                                                   "content": f"benchmark message for pane {i}"}).encode())
                     for i in range(AGENTS)]
            cases = {
                "GET /api/state": [("GET", "/api/state", None)],
                "GET /messages": [("GET", "/messages", None)],
                "GET /messages?user=<busiest>&limit=300": [("GET", f"/messages?user={busiest}&limit=300", None)],
                "GET /tasks": [("GET", "/tasks", None)],
                "POST /send": sends,
            }
            result["cases"] = {}
            for name, requests in cases.items():
                for clients in (1, 16):
                    result["cases"][f"{name} c={clients}"] = load(hub, requests, clients, seconds)
                    print(kind, name, clients, result["cases"][f"{name} c={clients}"], file=sys.stderr, flush=True)
            result["loaded_rss_mb"] = round(hub.rss_kb() / 1024, 1)
            status_text = Path(f"/proc/{hub.pid}/status").read_text()
            result["peak_rss_mb"] = round(int(status_text.split("VmHWM:")[1].split()[0]) / 1024, 1)
            result["threads"] = int(status_text.split("Threads:")[1].split()[0])
            delivered = sum(len(tmux.capture(p).splitlines()) > 0 for p in panes[1:])
            result["panes_with_delivered_text"] = delivered
        finally:
            hub.stop()
    finally:
        tmux.kill()
        for leftover in db.parent.glob("bench.sqlite*"):
            leftover.unlink()
    return result


def table(results: dict) -> str:
    py, rs = results["python"], results["rust"]
    lines = ["| Measure | Python | Rust | Rust / Python |", "|---|---:|---:|---:|"]

    def row(label: str, a: float, b: float, unit: str = "") -> None:
        lines.append(f"| {label} | {a:g}{unit} | {b:g}{unit} | {b / a:.2f}x |" if a else f"| {label} | {a} | {b} | |")

    row("Cold start to first /health, median of 5 (s)", statistics.median(py["cold_start_s"]), statistics.median(rs["cold_start_s"]))
    row("Idle RSS, 3 s after start (MB)", py["idle_rss_mb"], rs["idle_rss_mb"])
    row("RSS after the load runs (MB)", py["loaded_rss_mb"], rs["loaded_rss_mb"])
    row("Peak RSS (MB)", py["peak_rss_mb"], rs["peak_rss_mb"])
    for case in py["cases"]:
        a, b = py["cases"][case], rs["cases"][case]
        row(f"{case}: p50 (ms)", a["p50_ms"], b["p50_ms"])
        row(f"{case}: p95 (ms)", a["p95_ms"], b["p95_ms"])
        row(f"{case}: requests/s", a["per_second"], b["per_second"])
        row(f"{case}: hub CPU per request (ms)", a["hub_cpu_ms_per_request"], b["hub_cpu_ms_per_request"])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, required=True, help="a COPY of a real database; never the live one")
    parser.add_argument("--node", default="karans-linux", help="node name the database's agents are on")
    parser.add_argument("--seconds", type=float, default=10)
    parser.add_argument("--out", type=Path, default=SCRATCH / "bench")
    parser.add_argument("--order", default="python,rust")
    args = parser.parse_args()
    assert ".agent-swarm" not in str(args.db.resolve()), "give a copy, never the live database"
    work = args.out / f"run-{os.getpid()}"
    work.mkdir(parents=True)
    results = {kind: measure(kind, args.db, work, args.node, args.seconds) for kind in args.order.split(",")}
    errors = {f"{kind} {case}": c["errors"] for kind, r in results.items() for case, c in r["cases"].items() if c["errors"]}
    (work / "results.json").write_text(json.dumps(results, indent=1))
    print(table(results))
    print(f"\nrequests that did not answer 200 (or a send not delivered): {errors or 'none'}")
    print(f"results: {work / 'results.json'}")


if __name__ == "__main__":
    main()
