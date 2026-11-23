"""Isolated monitor, paste and websocket measurements with synthetic panes."""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import shlex
import shutil
import statistics
import subprocess
import threading
import time
import uuid
from collections import defaultdict
from pathlib import Path

from fastapi.testclient import TestClient

from agent_swarm import activity, db, model_switch, nodes, protocol, server, tmux

samples = defaultdict(list)


def instrument(obj, name, key=None):
    fn = getattr(obj, name)

    def wrapped(*args, **kwargs):
        start = time.perf_counter()
        try:
            return fn(*args, **kwargs)
        finally:
            samples[key or name].append((time.perf_counter() - start) * 1000)

    setattr(obj, name, wrapped)


def measure(fn, key):
    start = time.perf_counter()
    result = fn()
    samples[key].append((time.perf_counter() - start) * 1000)
    return result


def report():
    return {key: {"n": len(ms), "median_ms": statistics.median(ms),
                  "total_ms": sum(ms), "max_ms": max(ms)} for key, ms in samples.items()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", type=Path, required=True)
    ap.add_argument("--panes", type=int, default=60)
    ap.add_argument("--ticks", type=int, default=12)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    args.work.mkdir(parents=True, exist_ok=True)
    os.environ.pop("TMUX", None)
    socket = f"rust-hub-bench-{uuid.uuid4().hex[:10]}"
    binary = shutil.which("tmux")
    real = [binary, "-L", socket, "-f", "/dev/null"]
    wrapper = args.work / "tmux"
    wrapper.write_text(f'#!/bin/sh\nexec {shlex.quote(binary)} -L {socket} "$@"\n')
    wrapper.chmod(0o700)
    os.environ["PATH"] = f"{args.work.resolve()}:{os.environ['PATH']}"
    connection = db.connect(args.work / "monitor.sqlite")
    screen = ("\x1b[32mTest work output, status remains steady\x1b[0m\n" * 40).strip()
    cmd = f"printf '%s\\n' {shlex.quote(screen)}; exec cat"
    try:
        subprocess.run([*real, "new-session", "-d", "-x", "120", "-y", "45", "-s", "probe", cmd],
                       check=True)
        for i in range(1, args.panes):
            subprocess.run([*real, "new-window", "-d", "-t", f"probe:{i}", "-n", f"probe-{i}", cmd],
                           check=True)
        pane_table = tmux.pane_table()
        machine = tmux.local_node()
        for index, pane in enumerate(pane_table):
            db.register(connection, f"bench-{index}", pane, f"fake-session-{index}",
                        flavor="claude", tmux_server=tmux.server_id(), node=machine)
        assert len(pane_table) == args.panes
        app = server.create_app(args.work / "monitor.sqlite", monitor=False)
        instrument(nodes.LocalNode, "snapshot")
        instrument(nodes.LocalNode, "capture")
        instrument(activity, "step", "activity_step")
        instrument(activity, "strip_colors")
        instrument(model_switch, "screen_model")
        instrument(tmux, "title_summary")
        instrument(tmux, "deliver", "tmux_deliver")
        instrument(db, "record_message", "db_record_message")
        instrument(db, "set_message_status", "db_message_status")

        async def monitor():
            await app.state.monitor_tick()
            samples.clear()
            cpu = time.process_time()
            for _ in range(args.ticks):
                start = time.perf_counter()
                await app.state.monitor_tick()
                samples["monitor_tick"].append((time.perf_counter() - start) * 1000)
            return (time.process_time() - cpu) * 1000

        monitor_cpu = asyncio.run(monitor())
        monitor_metrics = report()
        samples.clear()

        processed = threading.Event()
        observed = nodes.RemoteNode.observed
        frames = 120
        count = 0

        def observe(node, frame):
            nonlocal count
            measure(lambda: observed(node, frame), "observed")
            count += 1
            if count == frames:
                processed.set()

        nodes.RemoteNode.observed = observe
        token = "fake-profile-token"
        db.set_node_token(connection, "bench-node", token)
        with TestClient(app, client=("127.0.0.1", 50000)) as client:
            for i in range(15):
                response = measure(lambda: client.post("/owner/send", json={
                    "recipient": "bench-0", "content": f"synthetic delivery {i}",
                }), "owner_send")
                response.raise_for_status()
                assert response.json()["status"] == "delivered"
            delivery_metrics = report()
            samples.clear()
            with client.websocket_connect("/nodes/ws", headers={"Authorization": f"Bearer {token}"}) as ws:
                ws.send_json(protocol.hello("bench-node", "bench", "fake-tmux", ["claude"]))
                assert ws.receive_json()["type"] == "welcome"
                frame = {"type": "observe", "tmux_server": "fake-tmux",
                         "screens": {f"%{i}": screen for i in range(10)}, "panes": {}}
                payload = json.dumps(frame)
                start = time.perf_counter()
                for _ in range(frames):
                    ws.send_text(payload)
                assert processed.wait(10)
                observation_ms = (time.perf_counter() - start) * 1000
            for _ in range(frames):
                measure(lambda: json.loads(payload), "observation_json_decode")
        args.out.write_text(json.dumps({
            "panes": len(pane_table), "ticks": args.ticks, "monitor_cpu_ms": monitor_cpu,
            "monitor": monitor_metrics, "delivery": delivery_metrics,
            "websocket": {"frames": frames, "frame_bytes": len(payload),
                          "total_ms": observation_ms, **report()},
        }, indent=2) + "\n")
    finally:
        connection.close()
        subprocess.run([*real, "kill-server"], capture_output=True)


if __name__ == "__main__":
    main()
