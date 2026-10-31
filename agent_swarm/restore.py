"""Save this machine's tmux layout and agents, and bring them back after a reboot.

A snapshot records every tmux session, window, and pane, with each pane's
working directory, and for each pane running a registered agent the harness
session id that resumes it (`claude --resume ID`, `codex resume ID`, ...).
The session id, not the directory, says which conversation a pane held, so
agents sharing a directory come back as themselves. A resumed harness
re-registers from its startup hook with the same session id, and the hub
gives it its old handle, so new pane ids do not matter.

Restoring creates what is missing and launches the agents. It never touches
a pane that is running something: it only types into a bare shell, such as
one tmux-resurrect put back at the same position.
"""

from __future__ import annotations

import json
import shlex
import subprocess
import time
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from . import tmux

SNAPSHOT_DIR = Path("~/.agent-swarm/snapshots").expanduser()
KEEP = 100

# Models the hub records when an agent registered without saying its model.
PLACEHOLDER_MODELS = {"claude-code", "gpt-5-codex"}

PANE_FORMAT = "\t".join([
    "#{session_name}", "#{window_index}", "#{window_name}", "#{window_layout}",
    "#{pane_index}", "#{pane_id}", "#{pane_current_path}", "#{pane_current_command}",
])


def read_layout() -> list[dict]:
    """Every pane in the running tmux server, in session/window/pane order."""
    out = tmux._tmux_out("list-panes", "-a", "-F", PANE_FORMAT)
    rows = []
    for line in (out or "").splitlines():
        parts = line.split("\t")
        if len(parts) != 8:
            continue
        session, window, wname, layout, pane, pane_id, cwd, command = parts
        rows.append({
            "session": session, "window": int(window), "window_name": wname,
            "layout": layout, "pane": int(pane), "pane_id": pane_id,
            "cwd": cwd, "command": command,
        })
    return rows


def capture(rows: list[dict], recipients: list[dict], node: str, server: str) -> dict:
    """A snapshot of `rows` (from read_layout), naming the agent in each pane.

    An agent counts only if the hub binds it to that pane in this tmux server
    and the pane runs something other than a shell: a registration left on a
    pane whose harness exited is not a running agent.
    """
    by_pane = {
        r["tmux_pane"]: r for r in recipients
        if r.get("node") == node and r.get("tmux_server") == server
    }
    sessions: dict[str, dict] = {}
    for row in rows:
        session = sessions.setdefault(row["session"], {"name": row["session"], "windows": {}})
        window = session["windows"].setdefault(row["window"], {
            "index": row["window"], "name": row["window_name"],
            "layout": row["layout"], "panes": [],
        })
        pane = {"index": row["pane"], "cwd": row["cwd"], "command": row["command"]}
        r = by_pane.get(row["pane_id"])
        if r and r.get("agent_id") and row["command"] not in tmux.SHELL_COMMANDS:
            pane["agent"] = {
                "handle": r["user_id"], "flavor": r.get("flavor"),
                "agent_id": r["agent_id"], "model": r.get("model"),
            }
        window["panes"].append(pane)
    return {
        "version": 1,
        "node": node,
        "tmux_server": server,
        "taken_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "sessions": [
            {"name": s["name"], "windows": sorted(s["windows"].values(), key=lambda w: w["index"])}
            for s in sessions.values()
        ],
    }


def agents_in(snapshot: dict) -> list[dict]:
    return [
        p["agent"] for s in snapshot["sessions"] for w in s["windows"]
        for p in w["panes"] if p.get("agent")
    ]


def save(snapshot: dict, directory: Path = SNAPSHOT_DIR) -> Path | None:
    """Write the snapshot; None when it matches the newest one already saved."""
    directory.mkdir(parents=True, exist_ok=True)
    files = sorted(directory.glob("*.json"))
    if files:
        try:
            last = json.loads(files[-1].read_text())
        except (OSError, ValueError):
            last = None
        if last and {**last, "taken_at": None} == {**snapshot, "taken_at": None}:
            return None
    stamp = datetime.now().strftime("%Y%m%dT%H%M%S%f")
    path = directory / f"{stamp}.json"
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(snapshot, indent=1) + "\n")
    temporary.replace(path)
    for old in sorted(directory.glob("*.json"))[:-KEEP]:
        old.unlink()
    return path


def pick(directory: Path, current_server: str | None) -> Path | None:
    """The newest snapshot taken under another tmux server than the running one.

    Snapshots keep being taken after a reboot, of the new near-empty server;
    the one to restore is the last one of the server that went away.
    """
    for path in sorted(directory.glob("*.json"), reverse=True):
        try:
            server = json.loads(path.read_text()).get("tmux_server")
        except (OSError, ValueError):
            continue
        if server != current_server:
            return path
    return None


def resume_command(agent: dict) -> str | None:
    """The command that resumes this agent's session, or None for an unknown harness.

    Flags match a dashboard spawn (tmux.HARNESS_SPAWN), so a restored agent
    runs with the same permissions as a newly spawned one.
    """
    flavor, sid = agent.get("flavor"), shlex.quote(agent["agent_id"])
    model = agent.get("model")
    model = None if not model or model in PLACEHOLDER_MODELS else shlex.quote(model)
    spec = tmux.HARNESS_SPAWN.get(flavor or "")
    if spec is None:
        return None
    if flavor == "claude":
        parts = ["claude", "--resume", sid]
    elif flavor == "codex":
        parts = ["codex", "resume", sid]
    elif flavor == "pi":
        parts = ["pi", "--session", sid]
    else:
        parts = ["hermes", "--resume", sid]
    if spec.startup_args:
        parts.append(spec.startup_args)
    # A Pi session file records its model, and Pi's registered model can be a
    # local file path that --model does not take.
    if model and flavor != "pi":
        parts += [spec.model_flag, model]
    if flavor == "codex":
        # Restored Codex agents must use --yolo even if dashboard defaults change.
        parts.append("--yolo")
    elif spec.launch_args:
        parts.append(spec.launch_args)
    parts += [f for f in spec.if_supported if tmux.harness_accepts(spec.binary, f)]
    return " ".join(parts)


@dataclass
class Step:
    """One thing restore does. `argv` is a tmux command; `launch` types a command into a pane."""
    describe: str
    argv: list[str] | None = None
    target: str | None = None
    launch: str | None = None
    # After new-session: the window index its first window must end up at.
    place: tuple[str, int] | None = None
    # A failed creation/split must prevent launches into an incomplete window.
    window: str | None = None


def _target(session: str, window: int, pane: int | None = None) -> str:
    # "=" makes tmux match the session name exactly, not as a prefix.
    return f"={session}:{window}" + (f".{pane}" if pane is not None else "")


def running_sessions(recipients: list[dict], candidates: Iterable[dict] = ()) -> set[str]:
    """Session ids that are running right now, so restore never starts a second copy.

    Two processes resuming one session both write its transcript. The hub
    knows which agents are alive in a pane; the process list catches a
    session resumed by id that never registered.
    """
    ids = {r["agent_id"] for r in recipients if r.get("alive") and r.get("agent_id")}
    try:
        ps = subprocess.run(["ps", "-A", "-o", "args="], capture_output=True, text=True,
                            check=True, timeout=5).stdout
    except (subprocess.SubprocessError, FileNotFoundError, OSError):
        return ids
    words = set(ps.split())
    return ids | {r["agent_id"] for r in [*recipients, *candidates] if r.get("agent_id") in words}


def plan(snapshot: dict, live: list[dict], running: set[str] = frozenset()) -> list[Step]:
    """What to do to bring `live` (read_layout) back to `snapshot`.

    Missing sessions and windows are created with their panes and layout.
    Existing windows are not reshaped: an agent goes back only into a pane at
    its old position that holds a bare shell. A session in `running` is
    already running somewhere and is never started again.
    """
    live_windows = {(r["session"], r["window"]) for r in live}
    live_panes = {(r["session"], r["window"], r["pane"]): r for r in live}
    live_sessions = {r["session"] for r in live}
    scheduled = set(running)
    steps: list[Step] = []
    for session in snapshot["sessions"]:
        name = session["name"]
        for window in session["windows"]:
            idx, panes = window["index"], window["panes"]
            target = _target(name, idx)
            first_step = len(steps)
            created = (name, idx) not in live_windows
            if created:
                first_cwd = panes[0]["cwd"]
                if name not in live_sessions:
                    steps.append(Step(
                        f"create session {name} with window {idx} ({window['name']})",
                        ["new-session", "-d", "-s", name, "-n", window["name"],
                         "-c", first_cwd, "-x", "220", "-y", "50"],
                        place=(name, idx),
                    ))
                    live_sessions.add(name)
                else:
                    steps.append(Step(
                        f"create window {name}:{idx} ({window['name']})",
                        ["new-window", "-d", "-t", _target(name, idx), "-n", window["name"],
                         "-c", first_cwd],
                    ))
                steps.append(Step(
                    f"set pane numbering for {name}:{idx}",
                    ["set-window-option", "-t", target, "pane-base-index", str(panes[0]["index"])],
                ))
                # Splitting the highest-numbered pane puts the new one after it,
                # so panes come back in their saved order.
                for prev, pane in zip(panes, panes[1:]):
                    steps.append(Step(
                        f"split {name}:{idx} for pane {pane['index']}",
                        ["split-window", "-d", "-t", _target(name, idx, prev["index"]),
                         "-c", pane["cwd"]],
                    ))
                    # Repeatedly halving the last pane runs out of space after
                    # a handful of splits. Spread panes out before splitting again.
                    steps.append(Step(
                        f"make room in {name}:{idx}",
                        ["select-layout", "-t", target, "tiled"],
                    ))
                if len(panes) > 1:
                    steps.append(Step(
                        f"layout {name}:{idx}",
                        ["select-layout", "-t", _target(name, idx), window["layout"]],
                    ))
            for pane in panes:
                agent = pane.get("agent")
                if not agent:
                    continue
                label = f"{name}:{idx}.{pane['index']}"
                who = f"{agent['handle']} ({agent['flavor']}) at {label}"
                command = resume_command(agent)
                if command is None:
                    steps.append(Step(f"skip {who}: no resume command for this harness"))
                    continue
                if agent["agent_id"] in scheduled:
                    steps.append(Step(f"skip {who}: its session is already running"))
                    continue
                if not created:
                    current = live_panes.get((name, idx, pane["index"]))
                    if current is None:
                        steps.append(Step(f"skip {who}: window exists without that pane"))
                        continue
                    if current["command"] not in tmux.SHELL_COMMANDS:
                        steps.append(Step(f"skip {who}: pane is running {current['command']}"))
                        continue
                steps.append(Step(
                    f"resume {who}",
                    target=_target(name, idx, pane["index"]),
                    launch=f"cd {shlex.quote(pane['cwd'])} && {command}",
                ))
                scheduled.add(agent["agent_id"])
            for step in steps[first_step:]:
                step.window = target
    return steps


def _place_first_window(session: str, index: int) -> None:
    """Move a new session's only window to `index`; it starts at base-index."""
    out = subprocess.run(
        ["tmux", "display-message", "-p", "-t", f"={session}:", "#{window_index}"],
        capture_output=True, text=True, check=True, timeout=10,
    )
    if int(out.stdout.strip()) != index:
        subprocess.run(
            ["tmux", "move-window", "-s", f"={session}:", "-t", _target(session, index)],
            capture_output=True, text=True, check=True, timeout=10,
        )


def apply(steps: list[Step], stagger: float, log=print) -> int:
    """Run the plan; returns how many steps failed. Launches are `stagger` seconds apart."""
    failed = 0
    launched = 0
    blocked = set()
    for step in steps:
        if step.window in blocked:
            log(f"skip {step.describe}: an earlier step in this window failed")
            continue
        if step.argv is None and step.launch is None:
            log(step.describe)
            continue
        if step.launch is not None and launched and stagger > 0:
            time.sleep(stagger)
        try:
            target = step.target
            if step.launch is not None:
                # Resolve to an immutable pane id immediately before typing;
                # positional targets can move during a staggered restore.
                current = subprocess.run(
                    ["tmux", "display-message", "-p", "-t", target,
                     "#{pane_id}\t#{pane_current_command}"],
                    capture_output=True, text=True, check=True, timeout=10,
                ).stdout.strip().split("\t")
                if len(current) != 2 or current[1] not in tmux.SHELL_COMMANDS:
                    raise ValueError("target is no longer a bare shell")
                target = current[0]
            argv = step.argv or ["send-keys", "-t", target, "-l", step.launch]
            subprocess.run(["tmux", *argv], capture_output=True, text=True, check=True, timeout=10)
            if step.place is not None:
                _place_first_window(*step.place)
            if step.launch is not None:
                subprocess.run(["tmux", "send-keys", "-t", target, "C-m"],
                               capture_output=True, text=True, check=True, timeout=10)
                launched += 1
        except subprocess.CalledProcessError as e:
            failed += 1
            if step.window:
                blocked.add(step.window)
            log(f"FAILED {step.describe}: {e.stderr.strip() or e}")
            continue
        except (subprocess.SubprocessError, OSError, ValueError) as e:
            failed += 1
            if step.window:
                blocked.add(step.window)
            log(f"FAILED {step.describe}: {e}")
            continue
        log(step.describe)
    return failed
