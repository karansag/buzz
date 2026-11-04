"""The node daemon: a machine's tmux, driven by the hub over one websocket.

`buzz-node` reads ~/.agent-swarm/node.toml (hub, token, node name),
dials the hub, and then does two things until told otherwise: executes the
commands the hub sends, and reports what its tmux looks like every few
seconds. It keeps no state of its own beyond a small store of claims and
results for commands with side effects, so the hub can resend one after a
reconnect without the agent seeing a message twice.

What the executor promises for a command with a side effect:

- it is claimed durably, by hub and op id, before anything touches tmux;
  a duplicate that arrives while the first is in flight is answered
  unknown rather than run, and one that arrives after gets the settled
  result; a claim left in flight by a crash becomes unknown at the next
  start and is never run
- it is checked for expiry, and for still belonging to the current hub
  session, immediately before the first tmux call, after any attachment
  fetching; nothing can undo a paste, so nothing is checked after it
- commands on one pane run one at a time, waiting without holding a worker
- admission is bounded: past the limit a command is refused at once
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import shutil
import sqlite3
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import httpx

from . import attachments, config, nodes, protocol, tmux

log = logging.getLogger("agent_swarm.node")

DAY = 24 * 60 * 60
HOUR = 60 * 60
MAX_QUEUED = 64  # commands admitted per session, waiting or running
COMMAND_WORKERS = 4


def package_version() -> str:
    try:
        return version("agent-swarm")
    except PackageNotFoundError:
        return "unknown"


def harnesses_here() -> list[str]:
    """Which spawnable harness binaries this machine has on its PATH."""
    return [flavor for flavor, spec in tmux.HARNESS_SPAWN.items() if shutil.which(spec.binary)]


def fingerprint(kind: str, args: dict) -> str:
    return hashlib.sha256(json.dumps([kind, args], sort_keys=True).encode()).hexdigest()


class OpStore:
    """Claims and results of side-effecting commands, by hub and op id.

    A claim is written before the command touches tmux and settled with the
    result afterwards. The store is on disk so a daemon restart between the
    two still cannot double up: whatever was in flight becomes unknown at the
    next start. Keys carry the hub's id, since op ids (message ids) start
    over on a recreated hub.
    """

    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS ops ("
            "key TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, status TEXT NOT NULL, "
            "result TEXT, ts REAL NOT NULL)"
        )
        self._conn.commit()
        self._lock = threading.Lock()

    def claim(self, key: str, fp: str) -> tuple[str, dict | None]:
        """Try to claim `key`. Returns one of:
        ("new", None): claimed now, go ahead;
        ("in_flight", None): someone else holds it and has not settled;
        ("done", result): settled earlier;
        ("mismatch", None): the id was reused with different arguments."""
        with self._lock:
            cur = self._conn.execute(
                "INSERT OR IGNORE INTO ops(key, fingerprint, status, ts) VALUES(?,?,'in_flight',?)",
                (key, fp, time.time()),
            )
            self._conn.commit()
            if cur.rowcount == 1:
                return "new", None
            row = self._conn.execute(
                "SELECT fingerprint, status, result FROM ops WHERE key=?", (key,)
            ).fetchone()
        if row[0] != fp:
            return "mismatch", None
        if row[1] == "done":
            return "done", json.loads(row[2])
        return "in_flight", None

    def settle(self, key: str, result: dict) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE ops SET status='done', result=?, ts=? WHERE key=?",
                (json.dumps(result), time.time(), key),
            )
            self._conn.commit()

    def release(self, key: str) -> None:
        """Drop a claim whose command never touched tmux, so a later resend
        with a fresh ttl can run."""
        with self._lock:
            self._conn.execute("DELETE FROM ops WHERE key=? AND status='in_flight'", (key,))
            self._conn.commit()

    def get(self, key: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT result FROM ops WHERE key=? AND status='done'", (key,)
            ).fetchone()
        return json.loads(row[0]) if row else None

    def abandon_in_flight(self, reason: str) -> int:
        """At startup: whatever was claimed and never settled may or may not
        have happened. Unknown, and never run again."""
        with self._lock:
            rows = self._conn.execute("SELECT key FROM ops WHERE status='in_flight'").fetchall()
            for (key,) in rows:
                op_id = key.rsplit(":", 1)[-1]
                self._conn.execute(
                    "UPDATE ops SET status='done', result=?, ts=? WHERE key=?",
                    (json.dumps(protocol.result(op_id, "unknown", reason)), time.time(), key),
                )
            self._conn.commit()
        return len(rows)

    def prune(self, max_age: float = DAY) -> int:
        """Forget settled results older than `max_age`. That is the replay
        horizon: a resend older than this would run again, so the hub never
        resends anything on its own."""
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM ops WHERE status='done' AND ts < ?", (time.time() - max_age,)
            )
            self._conn.commit()
        return cur.rowcount


class AttachmentCache:
    """Files the hub sent along with messages, fetched once and kept locally.

    The hub names an attachment by the hash of its bytes, so a fetched file
    is verified against its name before it is written, and an existing file
    is trusted without another fetch.
    """

    def __init__(self, root: Path, hub: str, token: str | None):
        self.root = root
        self.hub = hub.rstrip("/")
        self.token = token

    def path_for(self, name: str, budget: float = 30.0) -> Path:
        if not attachments._NAME.match(name):
            raise ValueError(f"malformed attachment name: {name}")
        path = self.root / name
        if path.is_file():
            os.utime(path)
            return path
        headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        # The per-read timeout bounds each wait; the deadline bounds the
        # whole fetch, so a slow trickle cannot hold a worker past the
        # command's budget.
        deadline = time.monotonic() + budget
        timeout = max(1.0, min(30.0, budget))
        data = bytearray()
        with httpx.stream("GET", f"{self.hub}/attachments/{name}", headers=headers, timeout=timeout) as r:
            if not r.is_success:
                raise ValueError(f"attachment {name}: hub answered {r.status_code}")
            for chunk in r.iter_bytes():
                data += chunk
                if len(data) > attachments.MAX_BYTES:
                    raise ValueError(f"attachment {name}: larger than allowed")
                if time.monotonic() > deadline:
                    raise ValueError(f"attachment {name}: fetch exceeded its budget")
        digest, _, ext = name.partition(".")
        if hashlib.sha256(data).hexdigest() != digest or (attachments.is_image(name) and attachments.sniff(bytes(data)) != ext):
            raise ValueError(f"attachment {name}: content does not match its name")
        self.root.mkdir(parents=True, exist_ok=True)
        tmp = self.root / f".{name}.{os.getpid()}.{time.monotonic_ns()}.part"
        tmp.write_bytes(bytes(data))
        tmp.replace(path)
        return path

    def sweep(self, max_age: float = attachments.DEFAULT_RETENTION_DAYS * DAY) -> int:
        """Drop files not touched for `max_age`; an agent reading a path
        minutes after delivery is unaffected."""
        if not self.root.is_dir():
            return 0
        cutoff = time.time() - max_age
        removed = 0
        for path in self.root.iterdir():
            try:
                if path.stat().st_mtime < cutoff:
                    path.unlink()
                    removed += 1
            except FileNotFoundError:
                continue
        return removed


class Executor:
    """Runs one command against this machine's tmux and reports the outcome.

    `run` is synchronous and safe to call from several threads: a per-pane
    lock keeps commands on one pane sequential even without the daemon's
    async queueing in front of it.
    """

    def __init__(
        self,
        local: nodes.LocalNode,
        store: OpStore,
        attachment_path: Callable[[str, float], Path] | None = None,
    ):
        self.local = local
        self.store = store
        self.attachment_path = attachment_path
        self._locks: dict[str, threading.Lock] = {}
        self._locks_guard = threading.Lock()

    def _lock_for(self, pane: str | None) -> threading.Lock:
        with self._locks_guard:
            return self._locks.setdefault(pane or "", threading.Lock())

    def run(
        self,
        cmd: dict,
        received: float,
        hub_id: str = "hub",
        still_valid: Callable[[], bool] = lambda: True,
    ) -> dict:
        """Execute `cmd` (a protocol.command frame received at monotonic time
        `received`) and return its result frame.

        `still_valid` says whether the session the command came in on is
        still the current one; it is asked immediately before the first tmux
        call, so work queued behind a slow pane on a connection that has
        since been replaced never runs.
        """
        op_id, kind, args = cmd["op_id"], cmd["kind"], cmd.get("args", {})
        ttl = cmd.get("ttl")
        deadline = received + ttl if ttl is not None else None
        if kind not in protocol.KINDS:
            return protocol.result(op_id, "failed", f"unknown command kind: {kind}")
        key = f"{hub_id}:{op_id}"
        mutating = kind in protocol.MUTATING
        if mutating:
            state, earlier = self.store.claim(key, fingerprint(kind, args))
            if state == "done":
                return earlier
            if state == "in_flight":
                return protocol.result(op_id, "unknown", "already in flight on this node")
            if state == "mismatch":
                return protocol.result(op_id, "failed", "op id reused with different arguments")
        with self._lock_for(args.get("pane")):
            out = self._guarded(op_id, kind, args, deadline, still_valid)
        if mutating:
            if out.get("executed", True):
                self.store.settle(key, out)
            else:
                # Never touched tmux: a resend with a fresh ttl may still run.
                self.store.release(key)
        out.pop("executed", None)
        return out

    def _guarded(self, op_id, kind, a, deadline, still_valid) -> dict:
        prepared = None
        if kind == "deliver" and a.get("attachments"):
            if self.attachment_path is None:
                return {**protocol.result(op_id, "failed", "this node cannot fetch attachments"), "executed": False}
            prepared = []
            for name in a["attachments"]:
                budget = (deadline - time.monotonic()) if deadline else 30.0
                if budget <= 0:
                    return {**protocol.result(op_id, "failed", "expired before execution"), "executed": False}
                try:
                    prepared.append(str(self.attachment_path(name, budget)))
                except Exception as e:  # noqa: BLE001 - nothing pasted yet: a clean failure
                    return {**protocol.result(op_id, "failed", f"attachment unavailable: {e}"), "executed": False}
        # The last word before anything touches tmux. Nothing is checked
        # afterwards: a paste cannot be undone.
        if deadline is not None and time.monotonic() > deadline:
            return {**protocol.result(op_id, "failed", "expired before execution"), "executed": False}
        if not still_valid():
            return {**protocol.result(op_id, "failed", "session ended before execution"), "executed": False}
        try:
            return self._execute(op_id, kind, a, prepared)
        except Exception as e:  # noqa: BLE001 - after dispatch, anything is unknown
            log.exception("command %s (%s) raised", op_id, kind)
            return protocol.result(op_id, "unknown", f"{type(e).__name__}: {e}")

    def _execute(self, op_id: str, kind: str, a: dict, prepared: list[str] | None) -> dict:
        if kind == "deliver":
            text = self.local.render_attachments(a["text"], prepared) if prepared else a["text"]
            r = self.local.deliver(
                op_id, a["pane"], a.get("tmux_server"), text,
                message_prefix=a.get("message_prefix"),
                submit_key=a.get("submit_key") or tmux.DEFAULT_SUBMIT_KEY,
                flavor=a.get("flavor"),
                retry_submit=a.get("retry_submit", True),
            )
            return protocol.result(op_id, r.status, r.error)
        if kind == "spawn":
            s = self.local.spawn(op_id, a.get("command"))
            return protocol.result(
                op_id, s.status, s.error, pane=s.pane, label=s.label, tmux_server=s.tmux_server
            )
        if kind == "kill":
            r = self.local.kill(op_id, a["pane"], a.get("tmux_server"))
            return protocol.result(op_id, r.status, r.error)
        if kind == "send_key":
            r = self.local.send_key(op_id, a["pane"], a.get("tmux_server"), a["key"])
            return protocol.result(op_id, r.status, r.error)
        if kind == "tag_pane":
            r = self.local.tag_pane(op_id, a["pane"], a.get("tmux_server"), a["handle"])
            return protocol.result(op_id, r.status, r.error)
        if kind == "rename_window":
            r = self.local.rename_window(op_id, a["pane"], a.get("tmux_server"), a["name"])
            return protocol.result(op_id, r.status, r.error)
        if kind == "capture":
            text, err = self.local.capture(a["pane"], a.get("tmux_server"))
            return protocol.result(op_id, "ok" if err is None else "failed", err, text=text)
        if kind == "resolve":
            try:
                resolved = self.local.resolve(a["target"])
            except nodes.Unavailable as e:
                return protocol.result(op_id, "failed", str(e))
            if resolved is None:
                return protocol.result(op_id, "ok", None, pane=None, label=None, tmux_server=None)
            return protocol.result(
                op_id, "ok", None,
                pane=resolved.pane, label=resolved.label, tmux_server=resolved.tmux_server,
            )
        raise AssertionError(kind)


class _Session:
    """One connection's lifetime. `ended` is set once and never cleared."""

    def __init__(self) -> None:
        self.ended = False


class Daemon:
    """One connection to the hub at a time, forever.

    `session(ws)` drives an open socket: hello, then commands and
    observations until the socket ends. `run_forever` dials, runs a session,
    and reconnects with backoff. Tests drive `session` with a fake socket.

    Each session is its own object, ended for good when its socket closes.
    Commands remember the session they arrived under and are refused, just
    before they would touch tmux, once it has ended: a command queued
    behind a slow pane or a slow attachment fetch when the socket dropped
    must not run under the next connection. The hub's welcome generation
    is recorded for the log, never used as the fence: it is the hub's
    number and can repeat after a hub restart. Commands already inside a
    tmux call finish and settle their result in the store, where a resend
    finds it.
    """

    def __init__(
        self,
        settings: config.Settings,
        executor: Executor,
        interval: float = 5.0,
        max_queued: int = MAX_QUEUED,
        maintenance: Callable[[], None] | None = None,
    ):
        self.settings = settings
        self.executor = executor
        self.interval = interval
        self.max_queued = max_queued
        self.maintenance = maintenance
        self.watched: dict[str, str | None] = {}  # pane -> tmux_server the hub expects
        self.seq = 0
        self.generation = 0  # the hub's number for this connection, for the log
        self.hub_id = "hub"
        self.current_session: _Session | None = None
        self._pane_locks: dict[str, asyncio.Lock] = {}
        self._commands = ThreadPoolExecutor(max_workers=COMMAND_WORKERS, thread_name_prefix="cmd")
        self._observer = ThreadPoolExecutor(max_workers=1, thread_name_prefix="observe")

    @property
    def ws_url(self) -> str:
        hub = self.settings.hub
        scheme = "wss" if hub.startswith("https://") else "ws"
        return scheme + "://" + hub.split("://", 1)[1] + "/nodes/ws"

    def hello(self) -> dict:
        return protocol.hello(
            self.settings.node, package_version(), self.executor.local.server_id(), harnesses_here()
        )

    def _set_watch(self, panes: list[dict]) -> None:
        self.watched = {p["pane"]: p.get("tmux_server") for p in panes}

    def observation(self) -> dict:
        """What the hub sees of this machine this tick."""
        self.seq += 1
        try:
            snap = self.executor.local.snapshot()
        except nodes.Unavailable as e:
            return protocol.observe(self.seq, None, None, {}, str(e))
        captures = {}
        for pane, expected in self.watched.items():
            if pane not in snap.live or (expected and expected != snap.server):
                continue
            text, err = self.executor.local.capture(pane, expected)
            if err is None and text is not None:
                captures[pane] = text
        return protocol.observe(self.seq, snap.server, snap.table, captures)

    async def session(self, ws) -> None:
        await ws.send(json.dumps(self.hello()))
        welcome = json.loads(await ws.recv())
        if welcome.get("type") != "welcome":
            raise RuntimeError(f"expected welcome, got {welcome.get('type')}")
        self.interval = float(welcome.get("interval") or self.interval)
        self.generation = int(welcome.get("generation") or 0)
        hub_id = str(welcome.get("hub_id") or self.settings.hub)
        self.hub_id = hub_id
        self._set_watch(welcome.get("watch") or [])
        session = _Session()
        self.current_session = session
        loop = asyncio.get_running_loop()
        queued = 0
        tasks: set[asyncio.Task] = set()
        log.info(
            "connected to %s as %s (hub generation %d)", self.settings.hub, self.settings.node, self.generation
        )

        async def send(frame: dict) -> None:
            await ws.send(json.dumps(frame))

        def still_valid() -> bool:
            return not session.ended

        async def handle(cmd: dict, received: float) -> None:
            nonlocal queued
            try:
                pane = (cmd.get("args") or {}).get("pane") or ""
                lock = self._pane_locks.setdefault(pane, asyncio.Lock())
                async with lock:  # waits here, holding no worker
                    out = await loop.run_in_executor(
                        self._commands, self.executor.run, cmd, received, hub_id, still_valid
                    )
                if not session.ended:
                    await send(out)
            finally:
                queued -= 1

        async def read() -> None:
            nonlocal queued
            async for raw in ws:
                msg = json.loads(raw)
                kind = msg.get("type")
                if kind == "command":
                    if queued >= self.max_queued:
                        await send(protocol.result(
                            msg.get("op_id", "?"), "failed", f"node busy: {queued} commands queued"
                        ))
                        continue
                    queued += 1
                    task = asyncio.create_task(handle(msg, time.monotonic()))
                    tasks.add(task)
                    task.add_done_callback(tasks.discard)
                elif kind == "watch":
                    self._set_watch(msg.get("panes") or [])

        async def observe() -> None:
            while True:
                frame = await loop.run_in_executor(self._observer, self.observation)
                await send(frame)
                await asyncio.sleep(self.interval)

        reader = asyncio.create_task(read())
        observer = asyncio.create_task(observe())
        try:
            done, _ = await asyncio.wait({reader, observer}, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                task.result()  # surface the reason the session ended
        finally:
            for task in (reader, observer):
                task.cancel()
            # This session is over, for good: nothing queued under it may
            # run, whatever a later welcome says. Work already inside a tmux
            # call cannot be stopped; it settles in the store and the hub
            # asks again if it needs the answer.
            session.ended = True
            for task in list(tasks):
                task.cancel()

    async def _maintain(self) -> None:
        while True:
            await asyncio.sleep(HOUR)
            if self.maintenance:
                try:
                    await asyncio.to_thread(self.maintenance)
                except Exception:  # noqa: BLE001
                    log.exception("maintenance failed")

    async def run_forever(self) -> None:
        from websockets.asyncio.client import connect

        upkeep = asyncio.create_task(self._maintain())
        backoff = 1.0
        try:
            while True:
                try:
                    headers = (
                        {"Authorization": f"Bearer {self.settings.token}"} if self.settings.token else {}
                    )
                    async with connect(self.ws_url, additional_headers=headers, max_size=None) as ws:
                        backoff = 1.0
                        await self.session(ws)
                except asyncio.CancelledError:
                    raise
                except Exception as e:  # noqa: BLE001 - any failure means reconnect
                    log.warning(
                        "connection to %s ended: %s; retrying in %.0fs", self.settings.hub, e, backoff
                    )
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30.0)
        finally:
            upkeep.cancel()


def _run() -> None:
    """Console-script entry: `buzz-node` connects this machine to its hub."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    settings = config.load()
    if settings.hub.startswith("http://127.0.0.1") or settings.hub.startswith("http://localhost"):
        raise SystemExit(
            "no hub configured: run `buzz join <hub-url> --token <token>` first "
            "(the token comes from `buzz node-token <this-node>` on the hub)"
        )
    home = Path(os.environ.get("AGENT_SWARM_NODE_HOME", "~/.agent-swarm")).expanduser()
    cache = AttachmentCache(home / "attachments", settings.hub, settings.token)
    store = OpStore(home / "node-ops.sqlite")
    abandoned = store.abandon_in_flight("the node stopped before the result was recorded")
    if abandoned:
        log.warning("%d command(s) left in flight by the previous run are now unknown", abandoned)

    def maintenance() -> None:
        store.prune()
        cache.sweep()

    maintenance()
    local = nodes.LocalNode(settings.node, attachments_root=cache.root)
    daemon = Daemon(settings, Executor(local, store, cache.path_for), maintenance=maintenance)
    asyncio.run(daemon.run_forever())
