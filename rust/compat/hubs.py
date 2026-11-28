"""Start and stop test hubs (Python and Rust) and isolated tmux servers.

Safety rules this module keeps:
- every tmux call names its own server with `-L` and has TMUX unset, so the
  default tmux server is never touched;
- a hub's port is checked free first, and the listener's PID is checked to
  be the process started here before any request is sent;
- hubs are stopped by PID only;
- the Python hub gets its own AGENT_SWARM_CONFIG, so it never writes
  ~/.agent-swarm/node.toml, and its own database path.
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import socket
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRATCH = Path(os.environ.get("RUST_HUB_SCRATCH", "/mnt/storage/karan-scratchpad/rust-hub"))
RUST_BIN = Path(os.environ.get("BUZZ_HUB_BIN", SCRATCH / "target/release/buzz-hub"))
LIVE_PORT = 8765
TMUX = shutil.which("tmux") or "/usr/bin/tmux"


def free_port() -> int:
    """A port nothing listens on, never the live hub's."""
    for _ in range(50):
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        listening = subprocess.run(["ss", "-H", "-ltn", f"sport = :{port}"], capture_output=True, text=True).stdout
        if port != LIVE_PORT and not listening.strip():
            return port
    raise RuntimeError("no free port found")


def listener_pid(port: int) -> int | None:
    out = subprocess.run(["ss", "-H", "-ltnp", f"sport = :{port}"], capture_output=True, text=True).stdout
    for part in out.split("pid=")[1:]:
        return int(part.split(",")[0].split(")")[0])
    return None


# What a test pane runs: `cat`, with the terminal's own echo off. With echo
# on, the terminal's echo of a multi-line paste races cat's output and the
# screen differs from run to run. This way the screen is what cat received.
CAT = "sh -c 'stty -echo; exec cat'"


class Tmux:
    """One isolated tmux server, and a PATH entry that makes a hub use it."""

    def __init__(self, name: str, work: Path):
        assert name.startswith("rustclone-"), name
        self.name = name
        self.env = {k: v for k, v in os.environ.items() if k not in ("TMUX", "TMUX_PANE")}
        self.shim = work / f"shim-{name}"
        self.shim.mkdir(parents=True, exist_ok=True)
        script = self.shim / "tmux"
        script.write_text(f'#!/bin/sh\nunset TMUX TMUX_PANE\nexec {TMUX} -L {name} "$@"\n')
        script.chmod(0o755)

    def run(self, *args: str, check: bool = True) -> str:
        done = subprocess.run([TMUX, "-L", self.name, *args], env=self.env, capture_output=True, text=True, timeout=10)
        if check and done.returncode:
            raise RuntimeError(f"tmux {args}: {done.stderr.strip()}")
        return done.stdout

    def start(self, panes: int, command: str = CAT) -> list[str]:
        """A session with `panes` windows, each running `command`. Returns pane ids."""
        self.run("-f", "/dev/null", "new-session", "-d", "-s", "w", "-x", "200", "-y", "50", command)
        for _ in range(panes - 1):
            self.run("new-window", "-d", "-t", "w", command)
        return self.run("list-panes", "-a", "-F", "#{pane_id}").split()

    def window(self, command: str) -> str:
        return self.run("new-window", "-d", "-t", "w", "-P", "-F", "#{pane_id}", command).strip()

    def capture(self, pane: str) -> str:
        return self.run("capture-pane", "-p", "-J", "-t", pane).rstrip("\n")

    def kill(self) -> None:
        self.run("kill-server", check=False)
        # tmux can leave the dead server's socket file behind.
        socket_file = Path(os.environ.get("TMUX_TMPDIR", "/tmp")) / f"tmux-{os.getuid()}" / self.name
        if socket_file.is_socket():
            socket_file.unlink()

    def path(self) -> str:
        return f"{self.shim}:{self.env.get('PATH', '')}"


class Hub:
    """A running test hub. `kind` is "python" or "rust"."""

    def __init__(self, kind: str, db: Path, tmux: Tmux | None, node: str = "testnode", monitor: bool = False):
        self.kind, self.db, self.port = kind, db, free_port()
        self.base = f"http://127.0.0.1:{self.port}"
        work = db.parent
        env = dict(tmux.env if tmux else {k: v for k, v in os.environ.items() if k not in ("TMUX", "TMUX_PANE")})
        if tmux:
            env["PATH"] = tmux.path()
        env.update({
            "AGENT_SWARM_DB": str(db), "AGENT_SWARM_PORT": str(self.port), "AGENT_SWARM_HOST": "127.0.0.1",
            "AGENT_SWARM_NODE": node, "AGENT_SWARM_CONFIG": str(work / f"node-{kind}.toml"),
            # The monitor is not cloned. Its first tick still runs at start.
            "AGENT_SWARM_MONITOR_INTERVAL": "5.0" if monitor else "86400",
            "PYTHONPATH": str(REPO), "PYTHONUNBUFFERED": "1",
        })
        for name in ("AGENT_SWARM_TOKEN", "AGENT_SWARM_URL", "AGENT_SWARM_TABS", "AGENT_SWARM_SPAWN_DIRS"):
            env.pop(name, None)
        if kind == "python":
            check = "import agent_swarm, sys; assert agent_swarm.__file__.startswith(sys.argv[1]), agent_swarm.__file__; "
            cmd = [sys.executable, "-c", check + "from agent_swarm.server import _run; _run()", str(REPO)]
        else:
            cmd = [str(RUST_BIN), "--db", str(db), "--port", str(self.port)]
        self.log = open(work / f"hub-{kind}-{self.port}.log", "w")
        self.started = time.perf_counter()
        self.proc = subprocess.Popen(cmd, env=env, cwd=REPO, stdout=self.log, stderr=subprocess.STDOUT)
        self.pid = self.proc.pid
        self.ready_after = self._wait()

    def _wait(self) -> float:
        """Seconds from spawn to the first good /health answer."""
        deadline = time.perf_counter() + 60
        while time.perf_counter() < deadline:
            if self.proc.poll() is not None:
                raise RuntimeError(f"{self.kind} hub exited: see {self.log.name}")
            try:
                with urllib.request.urlopen(f"{self.base}/health", timeout=1) as r:
                    took = time.perf_counter() - self.started
                    body = json.load(r)
                owner = listener_pid(self.port)
                if owner != self.pid or body.get("db") != str(self.db):
                    self.stop()
                    raise RuntimeError(f"port {self.port} is served by pid {owner}, not our {self.pid}")
                return took
            except (urllib.error.URLError, ConnectionError, TimeoutError):
                time.sleep(0.002)
        self.stop()
        raise RuntimeError(f"{self.kind} hub did not come up")

    def call(self, method: str, path: str, body=None, headers: dict | None = None, raw: bool = False):
        """(status, parsed JSON or text, response headers)."""
        data = json.dumps(body).encode() if body is not None and not isinstance(body, bytes) else body
        req = urllib.request.Request(self.base + path, data=data, method=method, headers=headers or {})
        if data is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                status, payload, got = r.status, r.read(), dict(r.headers)
        except urllib.error.HTTPError as e:
            status, payload, got = e.code, e.read(), dict(e.headers)
        if raw:
            return status, payload, got
        try:
            return status, json.loads(payload), got
        except ValueError:
            return status, payload.decode("utf-8", "replace"), got

    def rss_kb(self) -> int:
        for line in Path(f"/proc/{self.pid}/status").read_text().splitlines():
            if line.startswith("VmRSS:"):
                return int(line.split()[1])
        return 0

    def cpu_seconds(self) -> float:
        fields = Path(f"/proc/{self.pid}/stat").read_text().rsplit(")", 1)[1].split()
        return (int(fields[11]) + int(fields[12])) / os.sysconf("SC_CLK_TCK")

    def stop(self) -> None:
        if self.proc.poll() is None:
            os.kill(self.pid, signal.SIGTERM)
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.kill(self.pid, signal.SIGKILL)
                self.proc.wait(timeout=5)
        self.log.close()


def copy_db(src: Path, dst: Path) -> None:
    """Copy a database with SQLite's backup API; the source is opened read-only."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    for stale in (dst, Path(f"{dst}-wal"), Path(f"{dst}-shm")):
        stale.unlink(missing_ok=True)
    with sqlite3.connect(f"file:{src}?mode=ro", uri=True) as a, sqlite3.connect(dst) as b:
        a.backup(b)
    b.close()
    a.close()
