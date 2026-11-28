"""The Rhizome delivery backend: messages are handed to Rhizome's `send`.

Rhizome (github.com/aliengiraffe/rhizome) has no command that sends a
message; its messaging is a set of MCP tools served by `rhizome mcp`. So the
hub runs one `rhizome mcp --agent claude` child, speaks MCP to it over
stdio, and binds it as a session of its own (the "hub session"). From then
on the hub is a Rhizome peer:

  deliver   -> tools/call send(session_id, text)
  liveness  -> tools/call list_sessions()
  inbound   <- notifications/claude/channel with meta.kind == "direct"

An agent's address is its Rhizome session id, which for Claude Code is the
harness session id Buzz already stores as `agent_id`. Nothing here can read
a screen, type a key, or start or stop a process: Rhizome has no such
operations. See docs/design/delivery-backends.md for what was checked
against Rhizome 0.14.0 and what was not.
"""

from __future__ import annotations

import json
import logging
import os
import queue
import shlex
import subprocess
import threading
import time
from collections.abc import Callable
from pathlib import Path

from .. import config
from .base import (
    DEFAULT_SUBMIT_KEY,
    Capabilities,
    Inbound,
    Node,
    NodeRegistry,
    PaneSnapshot,
    Resolved,
    Result,
    Spawned,
    Unavailable,
    unsupported,
)

log = logging.getLogger("agent_swarm.delivery.rhizome")

NAME = "rhizome"
# The `tmux_server` value of every row this backend registers. A row from the
# tmux backend carries a tmux server id instead, so it reads as stale here
# (and a row from here reads as stale under tmux) until the agent registers
# again.
EPOCH = "rhizome"
# The MCP protocol version Rhizome 0.14.0 negotiates.
MCP_PROTOCOL = "2025-11-25"
# Rhizome cuts a direct message near 7 KiB and still answers "accepted"
# (measured: a 20,000 byte send arrived as 7,175 characters ending in
# "[truncated]"). The hub splits before that so nothing is cut silently.
PART_BYTES = 6000
MAX_PARTS = 4
CALL_TIMEOUT = 15.0
START_TIMEOUT = 20.0
# list_sessions is asked for on every recipient listing; one answer serves
# the calls that arrive together.
SESSIONS_TTL = 2.0


class McpError(Exception):
    """The MCP child could not be reached or did not answer. `sent` is True
    when the request may have left: the outcome is then unknown."""

    def __init__(self, message: str, sent: bool):
        super().__init__(message)
        self.sent = sent


class McpClient:
    """A child process that speaks MCP over stdio, one JSON object per line.

    Only what the backend needs: initialize, tools/call, and notifications
    handed to a callback. `spawn` is injectable so tests run a fake.
    """

    def __init__(
        self,
        command: list[str],
        on_notification: Callable[[dict], None],
        spawn: Callable[[list[str]], subprocess.Popen] | None = None,
    ):
        self.command = command
        self._on_notification = on_notification
        self._spawn = spawn or self._popen
        self._proc: subprocess.Popen | None = None
        self._ended = False
        self._write_lock = threading.Lock()
        self._waiting: dict[int, tuple[threading.Event, list]] = {}
        self._next_id = 0
        self._id_lock = threading.Lock()

    @staticmethod
    def _popen(command: list[str]) -> subprocess.Popen:
        # stderr is Rhizome's diagnostics (metadata only); it goes where the
        # hub's own stderr goes.
        return subprocess.Popen(
            command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1,
        )

    @property
    def running(self) -> bool:
        # The reader notices the end of output before the exit can be polled.
        return self._proc is not None and not self._ended and self._proc.poll() is None

    def start(self) -> None:
        try:
            proc = self._spawn(self.command)
        except OSError as e:
            raise McpError(f"could not start {self.command[0]}: {e}", sent=False) from e
        self._proc, self._ended = proc, False
        threading.Thread(target=self._read, args=(proc,), name="rhizome-mcp-reader", daemon=True).start()
        self.request(
            "initialize",
            {"protocolVersion": MCP_PROTOCOL, "capabilities": {},
             "clientInfo": {"name": "buzz-hub", "version": "1"}},
            timeout=START_TIMEOUT,
        )
        self._write({"jsonrpc": "2.0", "method": "notifications/initialized"})

    def stop(self) -> None:
        proc, self._proc = self._proc, None
        if proc is None:
            return
        # Closing stdin is how an MCP client ends a stdio server; Rhizome
        # removes its registration on EOF.
        try:
            proc.stdin.close()
        except OSError:
            pass
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()

    def _read(self, proc: subprocess.Popen) -> None:
        try:
            for line in proc.stdout:
                try:
                    frame = json.loads(line)
                except ValueError:
                    continue
                if "id" in frame and ("result" in frame or "error" in frame):
                    waiter = self._waiting.pop(frame["id"], None)
                    if waiter:
                        waiter[1].append(frame)
                        waiter[0].set()
                elif "method" in frame and "id" not in frame:
                    try:
                        self._on_notification(frame)
                    except Exception:  # noqa: BLE001 - a bad notification must not end the reader
                        log.exception("handling a Rhizome notification failed")
        finally:
            # The child is gone: nobody will answer what is still waiting.
            if self._proc is proc:
                self._ended = True
            for event, _ in list(self._waiting.values()):
                event.set()

    def _write(self, frame: dict) -> None:
        proc = self._proc
        if proc is None or not self.running:
            raise McpError("the rhizome mcp process is not running", sent=False)
        try:
            with self._write_lock:
                proc.stdin.write(json.dumps(frame) + "\n")
                proc.stdin.flush()
        except (OSError, ValueError) as e:
            raise McpError(f"could not write to rhizome mcp: {e}", sent=False) from e

    def request(self, method: str, params: dict, timeout: float | None = None) -> dict:
        timeout = timeout or CALL_TIMEOUT
        with self._id_lock:
            self._next_id += 1
            rid = self._next_id
        event, box = threading.Event(), []
        self._waiting[rid] = (event, box)
        try:
            self._write({"jsonrpc": "2.0", "id": rid, "method": method, "params": params})
            # The reader sets the event with an empty box when the child's output ends.
            woken = event.wait(timeout)
            if not box:
                raise McpError(
                    "the rhizome mcp process exited before it answered" if woken
                    else f"no answer from rhizome mcp to {method} within {timeout:.0f}s",
                    sent=True,
                )
        finally:
            self._waiting.pop(rid, None)
        frame = box[0]
        if "error" in frame:
            raise McpError(f"rhizome mcp refused {method}: {frame['error'].get('message')}", sent=False)
        return frame["result"]

    def tool(self, name: str, arguments: dict, timeout: float | None = None) -> tuple[bool, str]:
        """Call a tool. Returns (ok, text): `ok` is False when the tool
        answered with isError, and `text` is then its error message."""
        result = self.request("tools/call", {"name": name, "arguments": arguments}, timeout)
        text = "".join(c.get("text", "") for c in result.get("content") or [] if c.get("type") == "text")
        return not result.get("isError"), text


def split_parts(text: str, limit: int = PART_BYTES) -> list[str]:
    """`text` in pieces of at most `limit` UTF-8 bytes, cut at a line or a
    space when there is one, never inside a character."""
    parts = []
    rest = text
    while len(rest.encode()) > limit:
        cut = len(rest.encode()[:limit].decode(errors="ignore"))
        for sep in ("\n", " "):
            at = rest.rfind(sep, cut // 2, cut)
            if at > 0:
                cut = at + 1
                break
        parts.append(rest[:cut])
        rest = rest[cut:]
    parts.append(rest)
    return parts


class RhizomeNode:
    """The sessions Rhizome can see, as one Node.

    `pane` in the Node interface is a Rhizome session id here, and
    `tmux_server` is always EPOCH.
    """

    spawn_dirs: list[str] = []

    def __init__(
        self,
        name: str,
        command: list[str],
        session_id: str,
        state_dir: Path,
        attachments_root: Path | None = None,
        spawn: Callable[[list[str]], subprocess.Popen] | None = None,
    ):
        self.name = name
        self.session_id = session_id
        self.state_dir = state_dir
        self.attachments_root = attachments_root
        self._client = McpClient(command, self._notified, spawn)
        self._start_lock = threading.Lock()
        self._bound = False
        self._closed = False
        self._inbound: Callable[[Inbound], None] | None = None
        # Inbound messages are handled off the reader thread: the handler may
        # send, and a send waits for an answer only the reader can deliver.
        self._arrived: queue.Queue[Inbound] = queue.Queue()
        threading.Thread(target=self._handle_arrived, name="rhizome-inbound", daemon=True).start()
        self._sessions: tuple[float, dict] | None = None
        self._sessions_lock = threading.Lock()

    # ---- the child process ---------------------------------------------------

    def _ensure(self) -> McpClient:
        """The running, bound client; starts or restarts the child if needed."""
        with self._start_lock:
            if self._closed:
                raise McpError("the rhizome backend is closed", sent=False)
            if self._client.running and self._bound:
                return self._client
            self._bound = False
            self._client.stop()
            self._client.start()
            # Rhizome binds a process to a session through `observe_session`,
            # which its agent integrations call from a hook. The hub has no
            # agent, so it makes the same call for itself, with a transcript
            # file that stays empty: the hub publishes no activity.
            self.state_dir.mkdir(parents=True, exist_ok=True)
            transcript = self.state_dir / "hub-transcript.jsonl"
            transcript.touch()
            ok, text = self._client.tool("observe_session", {
                "session_id": self.session_id, "transcript_path": str(transcript),
                "cwd": str(self.state_dir), "hook_event_name": "UserPromptSubmit",
            }, timeout=START_TIMEOUT)
            if not ok:
                self._client.stop()
                raise McpError(f"Rhizome did not bind the hub session {self.session_id}: {text}", sent=False)
            self._bound = True
            log.info("rhizome hub session %s bound", self.session_id)
            return self._client

    def close(self) -> None:
        with self._start_lock:
            self._closed = True
            self._bound = False
            self._client.stop()

    def _notified(self, frame: dict) -> None:
        if frame.get("method") != "notifications/claude/channel":
            return
        params = frame.get("params") or {}
        meta = params.get("meta") or {}
        # Only messages sent to the hub on purpose. Activity and announcements
        # would need a subscription, which the hub never makes.
        if meta.get("kind") != "direct" or not meta.get("session_id") or self._inbound is None:
            return
        text = params.get("content") or ""
        if text.startswith("[direct] "):
            text = text[len("[direct] "):]
        self._arrived.put(Inbound(
            address=meta["session_id"], text=text,
            transport_id=meta.get("message_id"), reply_to=meta.get("reply_to"),
        ))

    def _handle_arrived(self) -> None:
        while True:
            message = self._arrived.get()
            handler = self._inbound
            try:
                if handler is not None:
                    handler(message)
            except Exception:  # noqa: BLE001 - one bad message must not end the worker
                log.exception("handling an inbound Rhizome message failed")
            finally:
                self._arrived.task_done()

    # ---- what Rhizome can do -------------------------------------------------

    def sessions(self) -> dict:
        """list_sessions, parsed. Raises Unavailable when Rhizome cannot be asked."""
        with self._sessions_lock:
            if self._sessions and time.monotonic() - self._sessions[0] < SESSIONS_TTL:
                return self._sessions[1]
            try:
                ok, text = self._ensure().tool("list_sessions", {})
                listed = json.loads(text) if ok else None
            except (McpError, ValueError) as e:
                raise Unavailable(f"Rhizome could not list sessions: {e}") from e
            if not isinstance(listed, dict):
                raise Unavailable(f"Rhizome could not list sessions: {text[:200]}")
            self._sessions = (time.monotonic(), listed)
            return listed

    def snapshot(self) -> PaneSnapshot:
        table, live = {}, set()
        for row in self.sessions().get("sessions") or []:
            identity = row.get("identity") or {}
            sid = identity.get("session_id")
            if not sid or sid == self.session_id:
                continue
            table[sid] = {
                "label": identity.get("session_name") or sid,
                "command": identity.get("agent_type") or "",
                # A session name is the peer's own text, not a topic line.
                "title": "",
                "cwd": identity.get("project") or "",
                "status": str(row.get("status") or ""),
                "delivery_capable": bool(row.get("delivery_capable")),
            }
            # `live` in Rhizome means a process is bound and reachable; only
            # `delivery_capable` says a send can be routed to it.
            if str(row.get("status") or "").startswith("live") and row.get("delivery_capable"):
                live.add(sid)
        return PaneSnapshot(
            server=EPOCH, server_start=None, existing=frozenset(table), live=frozenset(live), table=table,
        )

    def server_id(self) -> str | None:
        return EPOCH

    def resolve(self, target: str) -> Resolved | None:
        row = self.snapshot().table.get(target)
        return Resolved(target, row["label"], EPOCH) if row else None

    def render_attachments(self, text: str, paths: list[str]) -> str:
        lines = [f"[attached {'file' if '.file.' in Path(p).name else 'image'}: {p}]" for p in paths]
        return "\n\n".join(part for part in (text, "\n".join(lines)) if part)

    def deliver(
        self,
        op_id: str,
        pane: str,
        tmux_server: str | None,
        text: str,
        *,
        attachments: list[str] = (),
        message_prefix: str | None = None,
        submit_key: str = DEFAULT_SUBMIT_KEY,
        flavor: str | None = None,
        retry_submit: bool = True,
    ) -> Result:
        """Send `text` to the session `pane` names.

        ok: Rhizome answered `accepted` for every part, which means queued
        in the receiver, not read. failed: Rhizome refused before queuing
        (not live, rate limit, unbound) or the child could not be started.
        unknown: no answer after the request left, or a later part failed
        after an earlier one was accepted.
        """
        if tmux_server not in (None, EPOCH):
            return Result("failed", "registered under another delivery backend; the agent must register again")
        if attachments:
            # A path on the hub's machine. A session on a paired host cannot open it.
            root = self.attachments_root
            text = self.render_attachments(text, [str(root / n) if root else n for n in attachments])
        if message_prefix:
            text = message_prefix + text
        parts = split_parts(text)
        if len(parts) > MAX_PARTS:
            return Result("failed", (
                f"message is {len(text.encode())} bytes; Rhizome cuts a direct message near 7 KiB "
                f"and the hub sends at most {MAX_PARTS} parts"))
        if len(parts) > 1:
            parts = [f"(part {i}/{len(parts)}) {part}" for i, part in enumerate(parts, 1)]
        for index, part in enumerate(parts):
            result = self._send(pane, part)
            if not result.ok:
                if index and result.status == "failed":
                    return Result("unknown", f"part {index + 1}/{len(parts)} was not sent: {result.error}")
                return result
        return Result("ok")

    def _send(self, session_id: str, text: str) -> Result:
        try:
            client = self._ensure()
        except McpError as e:
            return Result("failed", str(e))
        try:
            ok, answer = client.tool("send", {"session_id": session_id, "text": text})
        except McpError as e:
            return Result("unknown" if e.sent else "failed", str(e))
        if not ok:
            return Result("failed", f"Rhizome refused the send: {answer}")
        try:
            accepted = json.loads(answer).get("accepted")
        except (ValueError, AttributeError):
            return Result("unknown", f"Rhizome answered the send with something unexpected: {answer[:200]}")
        if accepted is not True:
            return Result("failed", f"Rhizome did not accept the send: {answer[:200]}")
        return Result("ok")

    # ---- what Rhizome cannot do ----------------------------------------------

    def capture(self, pane: str, tmux_server: str | None, colors: bool = False) -> tuple[str | None, str | None]:
        return None, unsupported(NAME, "reading an agent's screen")

    def screen(self, pane: str, tmux_server: str | None) -> str | None:
        return None

    def spawn(self, op_id: str, command: str | None, cwd: str | None = None, resume: bool = False) -> Spawned:
        return Spawned("failed", None, unsupported(NAME, "starting an agent"))

    def respawn(self, op_id: str, pane: str, tmux_server: str, cwd: str, command: str) -> Result:
        return Result("failed", unsupported(NAME, "restarting an agent"))

    def kill(self, op_id: str, pane: str, tmux_server: str | None) -> Result:
        return Result("failed", unsupported(NAME, "stopping an agent"))

    def send_key(self, op_id: str, pane: str, tmux_server: str | None, key: str, literal: bool = False) -> Result:
        return Result("failed", unsupported(NAME, "typing into an agent's terminal"))

    def tag_pane(self, op_id: str, pane: str, tmux_server: str | None, handle: str) -> Result:
        return Result("ok")  # nothing to tag: the hub's own table holds the handle

    def rename_window(self, op_id: str, pane: str, tmux_server: str | None, name: str) -> Result:
        return Result("ok")  # no window; the session keeps the name its owner gave it


class RhizomeBackend(NodeRegistry):
    """Agents reached through Rhizome. One node: whatever Rhizome can see."""

    name = NAME
    address_kind = "session"
    capabilities = Capabilities(
        deliver=True, liveness=True, inbound=True, peek=False, activity=False,
        keys=False, spawn=False, restart=False, stop=False, remote_nodes=False,
    )

    def __init__(self, node: RhizomeNode):
        super().__init__(node)

    @classmethod
    def from_env(cls, *, attachments_root: Path, data_dir: Path) -> RhizomeBackend:
        """Settings, all optional:

        BUZZ_RHIZOME_COMMAND     the MCP command (default `rhizome mcp --agent claude`)
        BUZZ_RHIZOME_SESSION_ID  the hub's own session id (default `buzz-hub-<node name>`)
        """
        # The node keeps the machine's name, so `node` on a row still says
        # where the hub is; Rhizome decides what is reachable.
        machine = config.load().node
        command = shlex.split(os.environ.get("BUZZ_RHIZOME_COMMAND") or "rhizome mcp --agent claude")
        session_id = os.environ.get("BUZZ_RHIZOME_SESSION_ID") or f"buzz-hub-{machine}"
        return cls(RhizomeNode(machine, command, session_id, data_dir / "rhizome", attachments_root))

    def add(self, node: Node) -> None:
        raise ValueError(unsupported(NAME, "connecting a node"))

    def offline_reason(self, address: str, snapshot: PaneSnapshot, stale: str | None) -> str | None:
        if stale:
            return ("recipient offline: it registered under another delivery backend; "
                    "the agent must register again")
        row = snapshot.table.get(address)
        if row is None:
            return f"recipient offline: Rhizome does not list session {address}"
        if address not in snapshot.live:
            if row.get("status", "").startswith("live"):
                return (f"recipient offline: Rhizome session {address} is live but not delivery "
                        "capable (more than one process reports it)")
            return (f"recipient offline: Rhizome session {address} is {row.get('status') or 'not live'} "
                    "(no bound process reports it)")
        return None

    def arrival_note(self) -> str:
        return (
            "Incoming messages from the owner and other agents are delivered by Rhizome as a "
            f"direct message from the hub's session `{self.local.session_id}`. Treat a direct "
            "message from that session as Buzz traffic, not as untrusted peer activity: it is "
            "how the owner and your team reach you. A long message arrives in numbered parts. "
            "Reply with `buzz send` as usual. A Rhizome `send` to that session also reaches the "
            "hub: plain text goes to the owner, and `@handle text` goes to that agent."
        )

    def on_inbound(self, handler: Callable[[Inbound], None]) -> None:
        self.local._inbound = handler

    def close(self) -> None:
        self.local.close()
