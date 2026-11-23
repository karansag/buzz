"""Validate response parity and time both hubs under HTTP and WAL load."""
from __future__ import annotations

import argparse
import collections
import json
import os
import random
import statistics
import threading
import time
from pathlib import Path
from urllib.parse import quote

import httpx

from agent_swarm import db
from bench.db_scale import QUERIES, pick_users


def process_sample(pid):
    root = Path(f"/proc/{pid}")
    stat = (root / "stat").read_text().rsplit(")", 1)[1].split()
    cpu = (int(stat[11]) + int(stat[12])) / os.sysconf("SC_CLK_TCK")
    rss = int(stat[21]) * os.sysconf("SC_PAGE_SIZE") / 2**20
    return cpu, rss


def quantiles(values):
    values = sorted(values)
    return {
        "n": len(values),
        "p50": round(statistics.median(values), 3),
        "p95": round(values[min(len(values) - 1, int(len(values) * .95))], 3),
    }


def endpoints(plan):
    history = [f"/api/agents/{quote(u, safe='')}/messages" for u in plan["users"]]
    searches = {
        query: [f"/api/agents/{quote(u, safe='')}/messages/search?q={quote(query, safe='')}"
                for u in plan["owner_users"]]
        for query in QUERIES
    }
    return {
        "state": ["/api/state"],
        "chats": ["/api/chats"],
        "history": history,
        **{f"search {query}": urls for query, urls in searches.items()},
    }


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


def parity(targets, paths, plan, *, ignore_state_now=False):
    results = collections.defaultdict(lambda: {"cases": 0, "byte_equal": 0})
    with httpx.Client(base_url=targets[0], timeout=30) as left, \
         httpx.Client(base_url=targets[1], timeout=30) as right:
        paths = {**paths, "page cursors": [
            f"/api/agents/{quote(u, safe='')}/messages?limit=75&{cursor}={plan['old_id'][u]}"
            for u in plan["users"] for cursor in ("before", "after", "around")
        ]}
        for key, urls in paths.items():
            for url in urls:
                a, b = left.get(url), right.get(url)
                a.raise_for_status()
                b.raise_for_status()
                first, second = a.json(), b.json()
                if ignore_state_now and key == "state":
                    # Two real hubs take their snapshots at different instants.
                    first.pop("now")
                    second.pop("now")
                if canonical(first) != canonical(second):
                    keys = [k for k in first if canonical(first[k]) != canonical(second.get(k))]
                    # No private response body or handle goes in the report.
                    raise AssertionError(f"{key}: structural mismatch in {keys}")
                results[key]["cases"] += 1
                results[key]["byte_equal"] += a.content == b.content
    return dict(results)


class Measurements:
    def __init__(self):
        self.records = collections.defaultdict(lambda: collections.defaultdict(list))

    def add(self, key, response, ms):
        row = self.records[key]
        row["http"].append(ms)
        row["bytes"].append(len(response.content))
        times = {}
        for part in response.headers.get("server-timing", "").split(","):
            if ";dur=" in part:
                name, value = part.strip().split(";dur=")
                times[name] = float(value)
                row[name].append(times[name])
        if {"build", "db"} <= times.keys():
            row["build_minus_db"].append(max(0, times["build"] - times["db"]))
        if {"total", "build", "encode"} <= times.keys():
            row["framework"].append(max(0, times["total"] - times["build"] - times["encode"]))

    def report(self):
        return {k: {name: quantiles(values) for name, values in rows.items()}
                for k, rows in self.records.items()}

    def merge(self, other):
        for key, rows in other.records.items():
            for name, values in rows.items():
                self.records[key][name].extend(values)


def read(client, stats, key, url):
    start = time.perf_counter_ns()
    resp = client.get(url)
    ms = (time.perf_counter_ns() - start) / 1e6
    resp.raise_for_status()
    stats.add(key, resp, ms)


def sequential(base, pid, paths, reps):
    stats = Measurements()
    with httpx.Client(base_url=base, timeout=30) as client:
        for key, urls in paths.items():
            for url in urls:
                read(client, Measurements(), key, url)
        start_cpu, start_rss = process_sample(pid)
        start = time.monotonic()
        for i in range(reps):
            for key, urls in paths.items():
                read(client, stats, key, urls[i % len(urls)])
        end = time.monotonic()
        end_cpu, end_rss = process_sample(pid)
    return {
        "endpoints": stats.report(),
        "resources": {"seconds": end - start, "cpu_seconds": end_cpu - start_cpu,
                      "rss_start_mib": start_rss, "rss_end_mib": end_rss},
    }


def concurrent(base, pid, paths, database, duration, readers, writes_per_s, chats_probe=False):
    stop = threading.Event()
    errors = []
    measurements = [Measurements() for _ in range(readers)]
    write_latencies = []
    memory = []

    def reader(i):
        rng = random.Random(i)
        with httpx.Client(base_url=base, timeout=30) as client:
            while not stop.is_set():
                score = rng.random()
                if score < .50:
                    key = "state"
                elif score < .85:
                    key = "history"
                else:
                    key = f"search {rng.choice(QUERIES[:4])}"
                try:
                    read(client, measurements[i], key, rng.choice(paths[key]))
                except Exception as exc:
                    errors.append(type(exc).__name__)

    def writer():
        conn = db.connect(database)
        nxt = time.monotonic()
        try:
            while not stop.is_set():
                before = time.perf_counter_ns()
                try:
                    db.record_message(conn, "bench-a", "bench-b", "bench",
                                      "mixed load write " * 40, "delivered")
                    write_latencies.append((time.perf_counter_ns() - before) / 1e6)
                except Exception as exc:
                    errors.append(type(exc).__name__)
                nxt += 1 / writes_per_s
                stop.wait(max(0, nxt - time.monotonic()))
        finally:
            conn.close()

    def probe():
        with httpx.Client(base_url=base, timeout=30) as client:
            while not stop.is_set():
                start = time.monotonic()
                try:
                    read(client, measurements[-1], "chats", paths["chats"][0])
                except Exception as exc:
                    errors.append(type(exc).__name__)
                stop.wait(max(0, .5 - (time.monotonic() - start)))

    threads = [threading.Thread(target=reader, args=(i,)) for i in range(readers)]
    if chats_probe:
        measurements.append(Measurements())
        threads.append(threading.Thread(target=probe))
    threads.append(threading.Thread(target=writer))
    start_cpu, start_rss = process_sample(pid)
    start = time.monotonic()
    for thread in threads:
        thread.start()
    while time.monotonic() < start + duration:
        memory.append(process_sample(pid)[1])
        time.sleep(min(.25, max(0, start + duration - time.monotonic())))
    stop.set()
    for thread in threads:
        thread.join()
    end = time.monotonic()
    end_cpu, end_rss = process_sample(pid)
    total = Measurements()
    for item in measurements:
        total.merge(item)
    reads = sum(len(r["http"]) for r in total.records.values())
    return {
        "endpoints": total.report(),
        "reads_per_s": round(reads / (end - start), 1),
        "chats_probe": chats_probe,
        "writes": quantiles(write_latencies) if write_latencies else {},
        "errors": errors,
        "resources": {"seconds": end - start, "cpu_seconds": end_cpu - start_cpu,
                      "rss_start_mib": start_rss, "rss_end_mib": end_rss,
                      "rss_peak_mib": max([end_rss, *memory])},
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", type=Path, required=True)
    ap.add_argument("--base", required=True)
    ap.add_argument("--other")
    ap.add_argument("--ignore-state-now", action="store_true")
    ap.add_argument("--dashboard-variants", action="store_true",
                    help="also measure Chats filters, the between-agents list, and tasks")
    ap.add_argument("--pid", type=int, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--reps", type=int, default=40)
    ap.add_argument("--state-only", action="store_true", help="measure only state in the single-client run")
    ap.add_argument("--seconds", type=float, default=15.0)
    ap.add_argument("--readers", type=int, default=4)
    ap.add_argument("--writes-per-s", type=float, default=20.0)
    ap.add_argument("--chats-probe", action="store_true")
    args = ap.parse_args()
    plan = pick_users(args.db)
    paths = endpoints(plan)
    if args.dashboard_variants:
        paths.update({
            "chats tpu": ["/api/chats?q=tpu"],
            "chats queens": ["/api/chats?queens=true"],
            "between agents": ["/messages?limit=4000"],
            "tasks": ["/tasks"],
        })
    result = {}
    if args.other:
        result["parity"] = parity((args.base, args.other), paths, plan, ignore_state_now=args.ignore_state_now)
    single_paths = {"state": paths["state"]} if args.state_only else paths
    result["single"] = sequential(args.base, args.pid, single_paths, args.reps)
    if args.seconds:
        result["mixed"] = concurrent(args.base, args.pid, paths, args.db,
                                     args.seconds, args.readers, args.writes_per_s, args.chats_probe)
    args.out.write_text(json.dumps(result, indent=2) + "\n")
    if result.get("mixed", {}).get("errors"):
        raise SystemExit("mixed workload had errors; see output")


if __name__ == "__main__":
    main()
