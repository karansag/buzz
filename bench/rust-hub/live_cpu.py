"""Measure the existing hub process, optionally adding one read-only state poller."""
import argparse
import json
import statistics
import threading
import time
import urllib.request
from pathlib import Path

from compare import process_sample


def measure(pid, seconds, interval, port=None):
    samples, requests = [], []
    stop = threading.Event()

    def poll():
        url = f"http://127.0.0.1:{port}/api/state"
        while not stop.is_set():
            now = time.monotonic()
            try:
                with urllib.request.urlopen(url, timeout=4) as response:
                    body_size = len(response.read())
                requests.append({"ms": (time.monotonic() - now) * 1000, "bytes": body_size})
            except OSError:
                requests.append({"error": True})
            stop.wait(max(0, interval - (time.monotonic() - now)))

    start = time.monotonic()
    cpu0, _ = process_sample(pid)
    thread = threading.Thread(target=poll)
    if port:
        thread.start()
    try:
        while time.monotonic() < start + seconds:
            time.sleep(min(2, max(0, start + seconds - time.monotonic())))
            samples.append(process_sample(pid)[1])
    finally:
        stop.set()
        if port:
            thread.join()
    elapsed = time.monotonic() - start
    cpu1, _ = process_sample(pid)
    return {"extra_poll": bool(port), "elapsed": elapsed, "one_core_percent": (cpu1-cpu0)/elapsed*100,
            "rss_median_mib": statistics.median(samples), "requests": requests}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pid", type=int, required=True)
    ap.add_argument("--port", type=int, required=True)
    ap.add_argument("--seconds", type=float, default=60)
    ap.add_argument("--interval", type=float, default=2)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    result = [measure(args.pid, args.seconds, args.interval, port)
              for port in (None, args.port, None)]
    args.out.write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
