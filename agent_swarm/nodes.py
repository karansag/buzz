"""What the server asks of a machine's tmux, behind one interface.

The server never touches tmux directly. It asks the Node that owns the
recipient's pane, found by the recipient's `node` column. LocalNode is the
tmux the server runs beside; a node for another machine arrives with the
node daemon. Every method maps onto one tmux operation, so a remote
implementation is a transport, not a reinterpretation.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

from . import protocol, tmux

log = logging.getLogger("agent_swarm.nodes")

# How long the hub waits for a node to answer, by command. A paste includes
# the verify-and-retry wait, so it gets the longest.
DELIVER_TTL = 30.0
COMMAND_TTL = 15.0


@dataclass(frozen=True)
class Result:
    """Outcome of an operation with a side effect.

    `unknown` means the node cannot say whether the side effect happened: a
    message may have been pasted and its result lost. The caller must not
    retry an unknown operation on its own, or the agent gets it twice.
    """

    status: Literal["ok", "failed", "unknown"]
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.status == "ok"


@dataclass(frozen=True)
class Resolved:
    """A pane target resolved on its node: the id, its positional label, and
    the tmux server that issued the id, all from one coherent look. The
    server travels with the pane so the hub never pairs a fresh pane with
    a server id it cached earlier."""

    pane: str
    label: str
    tmux_server: str | None


@dataclass(frozen=True)
class Spawned:
    """Outcome of a spawn: a Result plus the pane it made, when it did, with
    the label and the tmux server that created it."""

    status: Literal["ok", "failed", "unknown"]
    pane: str | None = None
    error: str | None = None
    label: str | None = None
    tmux_server: str | None = None

    @property
    def ok(self) -> bool:
        return self.status == "ok"


class Unavailable(Exception):
    """The node could not observe its tmux coherently right now.

    Distinct from an empty snapshot: nothing is known, so nothing may be
    treated as confirmed absent.
    """


def new_op_id() -> str:
    """An id for a side-effecting operation that has no message row of its own."""
    return uuid.uuid4().hex


@dataclass(frozen=True)
class PaneSnapshot:
    """One look at a node's tmux: which panes exist and which hold an agent."""

    server: str | None  # tmux server id; None when tmux is not running
    server_start: float | None
    existing: frozenset[str]
    live: frozenset[str]  # existing panes running something other than a shell
    table: dict[str, dict[str, str]]  # pane id -> {label, command, title}

    def label(self, pane: str) -> str | None:
        row = self.table.get(pane)
        return row["label"] if row else None

    def title(self, pane: str) -> str | None:
        row = self.table.get(pane)
        return row["title"] if row else None


class Node(Protocol):
    """One machine's tmux.

    Every operation on a pane also names the tmux server that issued the
    pane id, and the node checks it before acting: pane ids start over when
    tmux restarts, so an id checked only at the hub could reach a different
    pane by the time the command runs. The check narrows that window; it is
    not atomic with the tmux calls that follow it.

    Every operation with a side effect (deliver, spawn, kill, tag_pane,
    rename_window) carries an op id, the message id for a delivery and a
    fresh id otherwise, and returns a Result that can be unknown. A node
    that may execute a command more than once (a remote one, after a
    reconnect) uses the id to return the earlier result instead of acting
    twice.

    snapshot() raises Unavailable when the node cannot observe its tmux
    coherently; callers treat that as nothing known, never as empty.
    """

    name: str

    def snapshot(self) -> PaneSnapshot: ...
    def server_id(self) -> str | None: ...
    def resolve(self, target: str) -> Resolved | None: ...
    def capture(
        self, pane: str, tmux_server: str | None, colors: bool = False
    ) -> tuple[str | None, str | None]: ...
    def deliver(
        self,
        op_id: str,
        pane: str,
        tmux_server: str | None,
        text: str,
        *,
        attachments: list[str] = (),
        message_prefix: str | None = None,
        submit_key: str = tmux.DEFAULT_SUBMIT_KEY,
        flavor: str | None = None,
        retry_submit: bool = True,
    ) -> Result: ...
    def spawn(self, op_id: str, command: str | None) -> Spawned: ...
    def kill(self, op_id: str, pane: str, tmux_server: str | None) -> Result: ...
    def send_key(self, op_id: str, pane: str, tmux_server: str | None, key: str) -> Result: ...
    def tag_pane(self, op_id: str, pane: str, tmux_server: str | None, handle: str) -> Result: ...
    def rename_window(self, op_id: str, pane: str, tmux_server: str | None, name: str) -> Result: ...


def _stale_server(expected: str | None) -> str | None:
    """Why a pane id from `expected` cannot be used now, or None if it can."""
    if expected is None:
        return None
    current = tmux.server_id()
    if current == expected:
        return None
    return f"tmux server changed ({expected} is gone); the pane id is from an earlier session"


class LocalNode:
    """The tmux on this machine.

    Looks tmux functions up at call time rather than binding them, so tests
    that monkeypatch the tmux module keep working through the node.
    """

    def __init__(self, name: str, attachments_root: Path | None = None):
        self.name = name
        # Where attachments live on this machine. Delivery is text-only, so
        # an attachment reaches an agent as a path it can open; the path has
        # to be one on the machine the pane is on.
        self.attachments_root = attachments_root

    def render_attachments(self, text: str, paths: list[str]) -> str:
        """The message text plus one line per attachment, as a local path."""
        lines = [f"[attached {'file' if '.file.' in Path(p).name else 'image'}: {p}]" for p in paths]
        return "\n\n".join(part for part in (text, "\n".join(lines)) if part)

    def snapshot(self) -> PaneSnapshot:
        # One read of the pane table, bracketed by the server id, so a tmux
        # restart in between cannot mix one server's panes with another's
        # identity. Existing and live panes derive from that same read. Two
        # restarts in a row is not something to guess about.
        for _ in range(2):
            before = tmux.server_id()
            table = tmux.pane_table()
            server = tmux.server_id()
            if server == before:
                break
        else:
            raise Unavailable("tmux restarted during every attempt to read its panes")
        try:
            start = float(server.split(":")[1]) if server else None
        except (IndexError, ValueError):
            start = None
        return PaneSnapshot(
            server=server,
            server_start=start,
            existing=frozenset(table),
            live=frozenset(
                p for p, row in table.items() if row["command"] not in tmux.SHELL_COMMANDS
            ),
            table=table,
        )

    def server_id(self) -> str | None:
        return tmux.server_id()

    def resolve(self, target: str) -> Resolved | None:
        # Bracketed by the server id like a snapshot: a restart in between
        # would pair the new server's pane with the old server's identity.
        before = tmux.server_id()
        found = tmux.resolve_pane(target)
        after = tmux.server_id()
        if found is None:
            return None
        if before != after:
            raise Unavailable("tmux restarted while resolving the pane")
        return Resolved(found[0], found[1], after)

    def capture(
        self, pane: str, tmux_server: str | None, colors: bool = False
    ) -> tuple[str | None, str | None]:
        if stale := _stale_server(tmux_server):
            return None, stale
        return tmux.capture_pane(pane, colors)

    def deliver(
        self,
        op_id: str,
        pane: str,
        tmux_server: str | None,
        text: str,
        *,
        attachments: list[str] = (),
        message_prefix: str | None = None,
        submit_key: str = tmux.DEFAULT_SUBMIT_KEY,
        flavor: str | None = None,
        retry_submit: bool = True,
    ) -> Result:
        if stale := _stale_server(tmux_server):
            return Result("failed", stale)
        if attachments:
            root = self.attachments_root
            text = self.render_attachments(
                text, [str(root / name) if root else name for name in attachments]
            )
        # tmux.deliver is several subprocesses. It reports failure only while
        # nothing has reached the pane; once the paste may have landed it
        # raises Uncertain, which is exactly the unknown outcome.
        try:
            ok, err = tmux.deliver(
                pane, text, message_prefix=message_prefix, submit_key=submit_key,
                flavor=flavor, retry_submit=retry_submit,
            )
        except tmux.Uncertain as e:
            return Result("unknown", str(e))
        return Result("ok" if ok else "failed", err)

    def spawn(self, op_id: str, command: str | None) -> Spawned:
        # The pane's identity comes from the command that created it, never
        # from a later look: a restart in between would pair the id with an
        # unrelated pane on the new server.
        try:
            created, err = tmux.spawn_window(command=command)
        except tmux.Uncertain as e:
            created, err, status = e.created, str(e), "unknown"
        else:
            status = "ok" if created else "failed"
        if created is None:
            return Spawned(status, None, err)
        return Spawned(status, created.pane, err, label=created.label, tmux_server=created.tmux_server)

    def kill(self, op_id: str, pane: str, tmux_server: str | None) -> Result:
        if stale := _stale_server(tmux_server):
            return Result("failed", stale)
        try:
            ok, err = tmux.kill_pane(pane)
        except tmux.Uncertain as e:
            return Result("unknown", str(e))
        return Result("ok" if ok else "failed", err)

    def send_key(self, op_id: str, pane: str, tmux_server: str | None, key: str) -> Result:
        if stale := _stale_server(tmux_server):
            return Result("failed", stale)
        try:
            ok, err = tmux.send_key(pane, key)
        except tmux.Uncertain as e:
            return Result("unknown", str(e))
        return Result("ok" if ok else "failed", err)

    def tag_pane(self, op_id: str, pane: str, tmux_server: str | None, handle: str) -> Result:
        if stale := _stale_server(tmux_server):
            return Result("failed", stale)
        ok, err = tmux.tag_pane(pane, handle)
        return Result("ok" if ok else "failed", err)

    def rename_window(self, op_id: str, pane: str, tmux_server: str | None, name: str) -> Result:
        if stale := _stale_server(tmux_server):
            return Result("failed", stale)
        ok, err = tmux.rename_window(pane, name)
        return Result("ok" if ok else "failed", err)


class NodeRegistry:
    """The nodes this server can reach right now, by name.

    Always holds the local node. A node that is absent is one the server
    cannot reach: its agents read offline and nothing is sent to it.
    """

    def __init__(self, local: Node):
        self.local = local
        self._nodes: dict[str, Node] = {local.name: local}

    def add(self, node: Node) -> None:
        # The local node is fixed for the server's life; a connection
        # claiming its name is misconfigured, never a replacement.
        if node.name == self.local.name:
            raise ValueError(f"{node.name} is this server's own node")
        self._nodes[node.name] = node

    def remove(self, name: str) -> None:
        if name != self.local.name:
            self._nodes.pop(name, None)

    def get(self, name: str | None) -> Node | None:
        return self._nodes.get(name or self.local.name)

    def names(self) -> list[str]:
        return list(self._nodes)


class RemoteNode:
    """A machine reached over the websocket it opened to the hub.

    One instance per connection. Commands become futures resolved by the
    result frames the socket reader hands back; observations replace the
    last one seen. `fence` ends the instance: every pending command resolves
    unknown, and later calls answer unknown without sending anything, so a
    replaced or dropped connection can never act again.

    The Node methods are synchronous because the server's endpoints are;
    they hand work to the event loop and wait, with a deadline. The ttl
    the node applies starts when it receives the command; the hub's wait
    is that ttl plus a little, so a command the network delayed is judged
    by the node from its own receipt, never refreshed by a reconnect.
    """

    def __init__(
        self,
        name: str,
        generation: int,
        loop: asyncio.AbstractEventLoop,
        send: Callable[[dict], Awaitable[None]],
        close: Callable[[], Awaitable[None]],
        interval: float,
        stale_after: int = protocol.STALE_AFTER,
    ):
        self.name = name
        self.generation = generation
        self.interval = interval
        self.stale_after = stale_after
        self._loop = loop
        self._send = send
        self._close = close
        self._send_lock = asyncio.Lock()
        self._pending: dict[str, asyncio.Future] = {}
        self._last: dict | None = None
        self._last_at: float | None = None
        self.fenced: str | None = None
        self.tmux_server: str | None = None
        self.version: str | None = None
        self.harnesses: list[str] = []

    # ---- driven by the socket reader, on the loop -------------------------

    def hello(self, frame: dict) -> None:
        self.tmux_server = frame.get("tmux_server")
        self.version = frame.get("version")
        self.harnesses = list(frame.get("harnesses") or [])

    def observed(self, frame: dict) -> None:
        self._last = frame
        self._last_at = time.monotonic()
        self.tmux_server = frame.get("tmux_server")

    def resolved(self, frame: dict) -> None:
        fut = self._pending.pop(frame.get("op_id"), None)
        if fut is not None and not fut.done():
            fut.set_result(frame)

    def fence(self, reason: str) -> None:
        """This connection is over. Pending commands are unknown, not failed:
        the node may have executed them.

        Safe from any thread: the flag is set at once, so later calls answer
        unknown without sending, and the futures and the close are handled
        on the loop that owns them.
        """
        if self.fenced:
            return
        self.fenced = reason
        try:
            on_loop = asyncio.get_running_loop() is self._loop
        except RuntimeError:
            on_loop = False
        if on_loop:
            self._fence_on_loop(reason)
        else:
            self._loop.call_soon_threadsafe(self._fence_on_loop, reason)

    def _fence_on_loop(self, reason: str) -> None:
        for op_id, fut in list(self._pending.items()):
            if not fut.done():
                fut.set_result(protocol.result(op_id, "unknown", reason))
        self._pending.clear()
        self._loop.create_task(self._closed_safely())

    async def _closed_safely(self) -> None:
        try:
            await self._close()
        except Exception:  # noqa: BLE001 - already going away
            pass

    async def _submit(self, frame: dict) -> dict:
        op_id = frame["op_id"]
        fut = self._loop.create_future()
        self._pending[op_id] = fut
        try:
            async with self._send_lock:
                # Decided again with the lock held: a fence, or the caller
                # giving up, may have happened while this waited its turn,
                # and a frame sent after that could act with nobody waiting.
                if self.fenced:
                    return protocol.result(op_id, "unknown", f"node {self.name}: {self.fenced}")
                if self._pending.get(op_id) is not fut:
                    return protocol.result(op_id, "unknown", "abandoned before it was sent")
                await self._send(frame)
            return await fut
        except Exception as e:  # noqa: BLE001 - the send failed: unknown whether it left
            return protocol.result(op_id, "unknown", f"send failed: {e}")
        finally:
            # Whatever ended this, by result, cancellation, or error, the
            # entry goes, but only if it is still ours.
            if self._pending.get(op_id) is fut:
                del self._pending[op_id]

    async def push_watch(self, panes: list[dict]) -> None:
        async with self._send_lock:
            if not self.fenced:
                await self._send(protocol.watch(panes))

    def set_watch(self, panes: list[dict]) -> None:
        """Tell the node which panes to capture; fire and forget, from any thread."""
        if not self.fenced:
            asyncio.run_coroutine_threadsafe(self.push_watch(panes), self._loop)

    # ---- the Node interface, from worker threads --------------------------

    def _call(self, kind: str, ttl: float, op_id: str | None = None, **args) -> dict:
        op_id = op_id or new_op_id()
        if self.fenced:
            return protocol.result(op_id, "unknown", f"node {self.name}: {self.fenced}")
        frame = protocol.command(op_id, kind, ttl, **args)
        future = asyncio.run_coroutine_threadsafe(self._submit(frame), self._loop)
        try:
            return future.result(timeout=ttl + 5.0)
        except FutureTimeout:
            # Cancelling ends the submit coroutine on the loop, which drops
            # its pending entry; a result arriving later finds nothing.
            future.cancel()
            return protocol.result(op_id, "unknown", f"no result from node {self.name} within {ttl:.0f}s")

    def snapshot(self) -> PaneSnapshot:
        if self._last is None or self._last_at is None:
            raise Unavailable(f"node {self.name} has not reported its panes yet")
        age = time.monotonic() - self._last_at
        if age > self.stale_after * self.interval:
            raise Unavailable(f"node {self.name} has not reported for {age:.0f}s")
        if self._last.get("table") is None:
            raise Unavailable(self._last.get("unavailable") or f"node {self.name} cannot read its tmux")
        table = self._last["table"]
        server = self._last.get("tmux_server")
        try:
            start = float(server.split(":")[1]) if server else None
        except (IndexError, ValueError):
            start = None
        return PaneSnapshot(
            server=server,
            server_start=start,
            existing=frozenset(table),
            live=frozenset(
                p for p, row in table.items() if row.get("command") not in tmux.SHELL_COMMANDS
            ),
            table=table,
        )

    def server_id(self) -> str | None:
        return self.tmux_server

    def resolve(self, target: str) -> Resolved | None:
        r = self._call("resolve", COMMAND_TTL, target=target)
        data = r.get("data") or {}
        if r.get("status") != "ok":
            raise Unavailable(r.get("error") or f"node {self.name} could not resolve {target}")
        if not data.get("pane"):
            return None
        # The server id comes from the same node-side look as the pane.
        return Resolved(data["pane"], data.get("label") or data["pane"], data.get("tmux_server"))

    def capture(
        self, pane: str, tmux_server: str | None, colors: bool = False
    ) -> tuple[str | None, str | None]:
        # The node captures watched panes with every observation; use that
        # when it is fresh rather than asking again. Those are plain text.
        last, at = self._last, self._last_at
        if not colors and last and at and time.monotonic() - at <= self.interval * 1.5:
            if tmux_server is None or last.get("tmux_server") == tmux_server:
                text = (last.get("captures") or {}).get(pane)
                if text is not None:
                    return text, None
        r = self._call("capture", COMMAND_TTL, pane=pane, tmux_server=tmux_server, colors=colors)
        if r.get("status") != "ok":
            return None, r.get("error") or "capture failed"
        return (r.get("data") or {}).get("text"), None

    def deliver(
        self,
        op_id: str,
        pane: str,
        tmux_server: str | None,
        text: str,
        *,
        attachments: list[str] = (),
        message_prefix: str | None = None,
        submit_key: str = tmux.DEFAULT_SUBMIT_KEY,
        flavor: str | None = None,
        retry_submit: bool = True,
    ) -> Result:
        r = self._call(
            "deliver", DELIVER_TTL, op_id=op_id,
            pane=pane, tmux_server=tmux_server, text=text, attachments=list(attachments),
            message_prefix=message_prefix, submit_key=submit_key, flavor=flavor,
            retry_submit=retry_submit,
        )
        return Result(r.get("status", "unknown"), r.get("error"))

    def spawn(self, op_id: str, command: str | None) -> Spawned:
        r = self._call("spawn", COMMAND_TTL, op_id=op_id, command=command)
        data = r.get("data") or {}
        return Spawned(
            r.get("status", "unknown"), data.get("pane"), r.get("error"),
            label=data.get("label"), tmux_server=data.get("tmux_server"),
        )

    def kill(self, op_id: str, pane: str, tmux_server: str | None) -> Result:
        r = self._call("kill", COMMAND_TTL, op_id=op_id, pane=pane, tmux_server=tmux_server)
        return Result(r.get("status", "unknown"), r.get("error"))

    def send_key(self, op_id: str, pane: str, tmux_server: str | None, key: str) -> Result:
        r = self._call("send_key", COMMAND_TTL, op_id=op_id, pane=pane, tmux_server=tmux_server, key=key)
        return Result(r.get("status", "unknown"), r.get("error"))

    def tag_pane(self, op_id: str, pane: str, tmux_server: str | None, handle: str) -> Result:
        r = self._call("tag_pane", COMMAND_TTL, op_id=op_id, pane=pane, tmux_server=tmux_server, handle=handle)
        return Result(r.get("status", "unknown"), r.get("error"))

    def rename_window(self, op_id: str, pane: str, tmux_server: str | None, name: str) -> Result:
        r = self._call("rename_window", COMMAND_TTL, op_id=op_id, pane=pane, tmux_server=tmux_server, name=name)
        return Result(r.get("status", "unknown"), r.get("error"))
