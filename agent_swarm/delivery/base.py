"""The seam between the hub and whatever carries a message to an agent.

The hub (store, tasks, teams, dashboard API) talks to one DeliveryBackend.
The backend owns one or more Nodes, the places agents live, and says which
hub features it can serve through `capabilities`. `tmux_backend` types into
tmux panes, here and on other machines; `rhizome_backend` hands messages to
Rhizome. See docs/design/delivery-backends.md.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Literal, Protocol

# The key that submits a pasted message when a recipient names none. A tmux
# key name; a backend that types nothing ignores it.
DEFAULT_SUBMIT_KEY = "C-m"


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

    def cwd(self, pane: str) -> str | None:
        """The folder the pane's foreground program runs in; None from a node
        too old to report it."""
        row = self.table.get(pane)
        return (row.get("cwd") or None) if row else None


class Node(Protocol):
    """One place agents live: a machine's tmux, or a transport's set of sessions.

    Written for tmux, and the argument names still say so. For a backend that
    does not address agents by pane, `pane` is the agent's address on that
    transport (a Rhizome session id) and `tmux_server` is the epoch that
    address belongs to. An operation the backend cannot do returns a failed
    Result whose error says "not supported by the <name> delivery backend";
    the hub checks `DeliveryBackend.capabilities` first, so that Result is a
    second line of defence, not the normal path.

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
    spawn_dirs: list[str]  # folders a new agent may start in (AGENT_SWARM_SPAWN_DIRS)

    def snapshot(self) -> PaneSnapshot: ...
    def server_id(self) -> str | None: ...
    def resolve(self, target: str) -> Resolved | None: ...
    def capture(
        self, pane: str, tmux_server: str | None, colors: bool = False
    ) -> tuple[str | None, str | None]: ...
    def screen(self, pane: str, tmux_server: str | None) -> str | None:
        """The pane's plain screen if it can be had without waiting on a node, else None."""
        ...
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
    ) -> Result: ...
    def spawn(self, op_id: str, command: str | None, cwd: str | None = None, resume: bool = False) -> Spawned: ...
    def respawn(self, op_id: str, pane: str, tmux_server: str, cwd: str, command: str) -> Result: ...
    def kill(self, op_id: str, pane: str, tmux_server: str | None) -> Result: ...
    def send_key(self, op_id: str, pane: str, tmux_server: str | None, key: str, literal: bool = False) -> Result: ...
    def tag_pane(self, op_id: str, pane: str, tmux_server: str | None, handle: str) -> Result: ...
    def rename_window(self, op_id: str, pane: str, tmux_server: str | None, name: str) -> Result: ...


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


@dataclass(frozen=True)
class Capabilities:
    """What a backend can do. The hub refuses a feature whose flag is False
    with a 501, and /api/state carries the flags so the dashboard can hide
    the control."""

    deliver: bool = True  # hand a message to an agent and report delivered/failed/unknown
    liveness: bool = False  # say whether an agent can take a message right now
    inbound: bool = False  # carry an agent's message to the hub (besides the HTTP API)
    peek: bool = False  # read the agent's screen (/api/peek, prompt guard before a send)
    activity: bool = False  # working / idle / needs-attention, read off the screen
    keys: bool = False  # type keys or raw text at the agent (terminal, interrupt, compact, /model)
    spawn: bool = False  # start an agent, or resume a stopped one
    restart: bool = False  # restart an agent in place (also: switch harness)
    stop: bool = False  # stop a running agent
    remote_nodes: bool = False  # other machines join over the buzz-node websocket

    def as_dict(self) -> dict[str, bool]:
        return asdict(self)


class Unsupported(Exception):
    """A hub feature the active backend cannot serve."""

    def __init__(self, backend: str, capability: str, feature: str):
        self.backend, self.capability, self.feature = backend, capability, feature
        super().__init__(unsupported(backend, feature))


def unsupported(backend: str, feature: str) -> str:
    return f"{feature} is not supported by the {backend} delivery backend"


@dataclass(frozen=True)
class Inbound:
    """A message an agent sent to the hub over the transport itself."""

    address: str  # the sender's address on the transport
    text: str
    transport_id: str | None = None  # the transport's own message id, for deduplication
    reply_to: str | None = None


class DeliveryBackend(Protocol):
    """Everything the hub asks of a transport.

    `get(None)` is the node for a row or request that names none. A backend
    with `address_kind == "session"` addresses an agent by its harness
    session id: the hub then ignores pane claims and uses `agent_id` as the
    address. `on_inbound` registers the hub's handler once; a backend
    without the `inbound` capability never calls it.
    """

    name: str
    capabilities: Capabilities
    address_kind: Literal["pane", "session"]
    local: Node

    def get(self, name: str | None) -> Node | None: ...
    def names(self) -> list[str]: ...
    def add(self, node: Node) -> None: ...
    def remove(self, name: str) -> None: ...
    def offline_reason(self, address: str, snapshot: PaneSnapshot, stale: str | None) -> str | None:
        """Why the agent at `address` cannot take a message now, or None."""
        ...
    def arrival_note(self) -> str:
        """One paragraph for the protocol brief: how a message reaches the agent."""
        ...
    def on_inbound(self, handler: Callable[[Inbound], None]) -> None: ...
    def close(self) -> None: ...
