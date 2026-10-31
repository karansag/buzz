"""Restart running agents in place, e.g. after a harness update.

Each agent's pane is respawned (`tmux respawn-pane -k`): its processes are
killed and a fresh login shell starts in the same pane, same pane id, in the
directory the harness ran in. The harness's resume command for the agent's
session id (restore.resume_command) is then typed into it, so the agent comes
back with its conversation and re-registers under the same handle with the
newly installed harness.

What does not survive: anything the agent was running in that pane, such as
background shells, watchers, or a half-finished turn. So by default only
agents that the hub sees idle are restarted.
"""

from __future__ import annotations

import shlex
import subprocess
from dataclasses import dataclass

from . import restore, tmux

# Agents in these states are mid-turn or waiting on the owner.
BUSY = {"working", "needs_attention"}


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
            item.skip = "no harness is running in its pane"
        elif not r.get("agent_id"):
            item.skip = "no session id, so it could not be resumed"
        elif (command := restore.resume_command(r)) is None:
            item.skip = f"no resume command for {r.get('flavor')}"
        elif status in BUSY and not force:
            item.skip = f"it is {status.replace('_', ' ')} (--force restarts it anyway)"
        else:
            item.cwd, item.command = pane["cwd"], command
        out.append(item)
    return out


def apply(item: Restart, own_pane: str | None) -> str | None:
    """Restart one agent; returns an error, or None.

    The caller's own pane is handed to the tmux server (run-shell -b), since
    respawning it kills this process before it could type the resume command.
    """
    respawn = ["respawn-pane", "-k", "-t", item.pane, "-c", item.cwd]
    type_it = ["send-keys", "-t", item.pane, "-l", item.launch]
    if item.pane == own_pane:
        script = "; ".join(shlex.join(["tmux", *a]) for a in (
            respawn, type_it, ["send-keys", "-t", item.pane, "C-m"]))
        argvs = [["run-shell", "-b", f"sleep 1; {script}"]]
    else:
        argvs = [respawn, type_it, ["send-keys", "-t", item.pane, "C-m"]]
    for argv in argvs:
        try:
            subprocess.run(["tmux", *argv], capture_output=True, text=True, check=True, timeout=10)
        except subprocess.CalledProcessError as e:
            return e.stderr.strip() or str(e)
        except (subprocess.SubprocessError, FileNotFoundError) as e:
            return str(e)
    return None
