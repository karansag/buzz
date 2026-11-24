"""Restart running agents in place, e.g. after a harness update.

Each agent's pane is respawned (`tmux respawn-pane -k`): its processes are
killed and a fresh login shell starts in the same pane, same pane id, in the
directory the harness ran in. The harness's resume command for the agent's
session id (restore.resume_command) runs in that shell, so the agent comes
back with its conversation and re-registers under the same handle with the
newly installed harness.

What does not survive: anything the agent was running in that pane, such as
background shells, watchers, or a half-finished turn. So by default only
agents observed idle by the hub are eligible. Unknown, missing, stopped or
busy activity is skipped unless --force overrides the activity guard; pane
identity and resumability checks still apply.
"""

from __future__ import annotations

import shlex
from dataclasses import dataclass

from . import restore, tmux

# Allow-list: uncertainty or a newly introduced activity state is not idle.
RESTARTABLE_ACTIVITY = {"idle"}


@dataclass
class Restart:
    handle: str
    pane: str
    cwd: str = ""
    command: str | None = None
    skip: str | None = None  # why it will not be restarted

    @property
    def launch(self) -> str:
        return f"cd {shlex.quote(self.cwd)} && {self.command}"


def plan(
    recipients: list[dict], live: list[dict], node: str, server: str,
    handles: list[str] | None = None, flavor: str | None = None, force: bool = False,
) -> list[Restart]:
    """Which agents to restart and how; skipped ones say why.

    `recipients` are the hub's rows (with `activity`), `live` this machine's
    panes (restore.read_layout). With `handles`, exactly those agents are
    considered; otherwise every agent on this node, or every one of `flavor`.
    """
    panes = {r["pane_id"]: r for r in live}
    rows = {r["user_id"]: r for r in recipients}
    if handles:
        chosen = [rows.get(h) or {"user_id": h} for h in handles]
    else:
        chosen = [r for r in recipients if r.get("node") == node
                  and r.get("tmux_server") == server and r.get("tmux_pane") in panes
                  and (flavor is None or r.get("flavor") == flavor)]
    out = []
    for r in chosen:
        item = Restart(r["user_id"], r.get("tmux_pane") or "")
        pane = panes.get(item.pane) if r.get("node") == node and r.get("tmux_server") == server else None
        status = (r.get("activity") or {}).get("status")
        if "flavor" not in r:
            item.skip = "not registered"
        elif pane is None:
            item.skip = f"its pane is not in this machine's tmux (node {r.get('node')})"
        elif pane["command"] in tmux.SHELL_COMMANDS:
            item.skip = f"no harness is running in its pane; `buzz restore {item.handle}` resumes it there"
        elif not r.get("agent_id"):
            item.skip = "no session id, so it could not be resumed"
        elif (command := restore.resume_command(r)) is None:
            item.skip = f"no resume command for {r.get('flavor')}"
        elif status not in RESTARTABLE_ACTIVITY and not force:
            activity = status.replace("_", " ") if status else "unknown (no activity report)"
            item.skip = f"activity is {activity}; only observed-idle agents restart by default (--force overrides)"
        elif not (cwd := pane.get("cwd") or r.get("cwd")):
            item.skip = "the hub does not know which folder the harness runs in"
        else:
            item.cwd, item.command = cwd, command
        out.append(item)
    return out
