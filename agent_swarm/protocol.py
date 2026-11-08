"""What a node and the hub say to each other over one websocket.

Every frame is a JSON object with a "type". The node dials the hub, so the
hub never needs to reach a node's address, and the node never listens.

    node -> hub   hello     once, first: who I am and what I can do
                  observe   every interval: my panes, and captures of the
                            ones the hub watches; doubles as the heartbeat
                  result    the outcome of one command, by op id
    hub -> node   welcome   the interval to observe at, the panes to watch
                  watch     the watched panes changed
                  command   do something; carries an op id and a ttl

Commands with side effects (deliver, spawn, kill, send_key, tag_pane,
rename_window) are idempotent by op id on the node: a command the hub
resends after a reconnect gets the earlier result back rather than running
twice. The ttl is in seconds from when the node receives the command, not
an absolute time, so the two clocks never have to agree.
"""

from __future__ import annotations

PROTOCOL = 1

MUTATING = frozenset({"deliver", "spawn", "kill", "send_key", "tag_pane", "rename_window"})
READ_ONLY = frozenset({"capture", "resolve"})
KINDS = MUTATING | READ_ONLY

# How long a node's silence lasts before the hub considers it gone, as a
# multiple of the observation interval.
STALE_AFTER = 3


def command(op_id: str, kind: str, ttl: float, **args) -> dict:
    if kind not in KINDS:
        raise ValueError(f"unknown command kind: {kind}")
    return {"type": "command", "op_id": op_id, "kind": kind, "ttl": ttl, "args": args}


def result(op_id: str, status: str, error: str | None = None, **data) -> dict:
    return {"type": "result", "op_id": op_id, "status": status, "error": error, "data": data}


def hello(
    node: str, version: str, tmux_server: str | None, harnesses: list[str],
    spawn_dirs: list[str] = (),
) -> dict:
    return {
        "type": "hello",
        "protocol": PROTOCOL,
        "node": node,
        "version": version,
        "tmux_server": tmux_server,
        "harnesses": harnesses,
        "spawn_dirs": list(spawn_dirs),
    }


def welcome(interval: float, watch: list[dict], generation: int, hub_id: str) -> dict:
    """`hub_id` identifies this hub's database for the life of the database,
    so a node's record of executed op ids never collides with a recreated
    hub whose message ids start over."""
    return {
        "type": "welcome",
        "interval": interval,
        "watch": watch,
        "generation": generation,
        "hub_id": hub_id,
    }


def watch(panes: list[dict]) -> dict:
    return {"type": "watch", "panes": panes}


def observe(
    seq: int,
    tmux_server: str | None,
    table: dict[str, dict[str, str]] | None,
    captures: dict[str, str],
    unavailable: str | None = None,
) -> dict:
    """One tick of what the node sees. `table` is None, with `unavailable`
    saying why, when the node could not read its tmux coherently; that is
    nothing known, not an empty machine."""
    return {
        "type": "observe",
        "seq": seq,
        "tmux_server": tmux_server,
        "table": table,
        "captures": captures,
        "unavailable": unavailable,
    }
