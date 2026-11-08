"""Save this machine's tmux layout and agents, and bring them back after a reboot.

A snapshot records every tmux session, window, and pane, with each pane's
working directory, and for each pane running a registered agent the harness
session id that resumes it (`claude --resume ID`, `codex resume ID`, ...).
The session id, not the directory, says which conversation a pane held, so
agents sharing a directory come back as themselves. Restore registers each
resumed agent to its new pane with the same session id, and the hub gives it
its old handle, so new pane ids do not matter.

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

from . import activity, config, tmux

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
    command = config.harness_command(flavor)
    if command is not None:
        resume_flag = {"claude": "--resume", "codex": "resume", "pi": "--session",
                       "hermes": "--resume"}[flavor]
        parts = [command, resume_flag, sid]
        if model and flavor != "pi":
            parts += [spec.model_flag, model]
        return " ".join(parts)
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
    # For a launch: the agent it resumes, registered to its new pane afterwards.
    # A launch with no target goes into the pane the previous step created
    # (a creation step whose argv prints the pane id with -P).
    agent: dict | None = None


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
                    agent=agent,
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


def _wait_for_harness(pane: str, timeout: float) -> bool:
    """Whether `pane` stops running a bare shell within `timeout` seconds."""
    deadline = time.monotonic() + timeout
    while True:
        command = tmux._tmux_out("display-message", "-p", "-t", pane, "#{pane_current_command}")
        if command is None:
            return False
        if command.strip() not in tmux.SHELL_COMMANDS:
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.5)


# How long a resumed harness is watched for a startup prompt or an early exit.
SETTLE = 10.0


def startup(pane: str, launched_at: float, wait: float, settle: float = SETTLE) -> tuple[str, str | None]:
    """How a harness launched into `pane` came up: ("ok", None), ("blocked", why)
    while it waits at a workspace trust prompt, or ("failed", why).

    Watched until `settle` seconds after the launch: a trust prompt shows a
    moment after the process starts, and declining it ends the harness.
    """
    if not _wait_for_harness(pane, wait):
        return "failed", f"its harness did not start within {wait:.0f}s"
    while True:
        screen = tmux._tmux_out("capture-pane", "-p", "-J", "-t", pane)
        command = tmux._tmux_out("display-message", "-p", "-t", pane, "#{pane_current_command}")
        if screen is None or command is None:
            return "failed", "its pane is gone"
        if trust := activity.trust_prompt(screen):
            return "blocked", (f"waiting at {trust}. Answer it in that pane or the dashboard's "
                               "terminal view; the hub holds messages back until then")
        if command.strip() in tmux.SHELL_COMMANDS:
            return "failed", "its harness started and exited; see the pane"
        if time.monotonic() - launched_at >= settle:
            return "ok", None
        time.sleep(0.5)


@dataclass
class Outcome:
    failed: int = 0
    blocked: int = 0  # resumed, but waiting at a trust prompt

    def summary(self) -> str:
        parts = [f"{self.failed} failed"] if self.failed else []
        if self.blocked:
            parts.append(f"{self.blocked} waiting at a trust prompt")
        return "done" + (", " + ", ".join(parts) if parts else "")


def apply(steps: list[Step], stagger: float, register=None, wait: float = 30.0, log=print,
          settle: float = SETTLE) -> Outcome:
    """Run the plan. Launches are `stagger` seconds apart.

    After the launches, each resumed agent is registered to its new pane with
    `register(pane_id, agent)` (returns an error or None), once its harness is
    running. Hooks alone are not enough: Codex runs its hook at the session's
    first turn, and an unregistered agent never gets one, since the hub
    refuses messages to a pane from the earlier tmux server. An agent held at
    a workspace trust prompt is still registered, so the dashboard shows it
    waiting; the hub does not deliver into that prompt.
    """
    failed = 0
    blocked_agents = 0
    launched: list[tuple[str, Step, float]] = []
    blocked = set()
    created = None
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
            target = step.target or created
            if step.launch is not None:
                if target is None:
                    raise ValueError("no pane to launch into")
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
            out = subprocess.run(["tmux", *argv], capture_output=True, text=True, check=True, timeout=10)
            if step.argv and "-P" in step.argv:
                created = out.stdout.strip()
            if step.place is not None:
                _place_first_window(*step.place)
            if step.launch is not None:
                subprocess.run(["tmux", "send-keys", "-t", target, "C-m"],
                               capture_output=True, text=True, check=True, timeout=10)
                launched.append((target, step, time.monotonic()))
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
    if register is None:
        return Outcome(failed)
    for pane, step, launched_at in launched:
        handle = step.agent["handle"]
        # Registering a pane that still runs a shell would have the hub paste
        # messages into that shell as commands.
        state, why = startup(pane, launched_at, wait, settle)
        if state == "failed":
            failed += 1
            log(f"FAILED {handle} at {pane}: {why}")
            continue
        error = register(pane, step.agent)
        if error:
            failed += 1
            log(f"FAILED register {handle} at {pane}: {error}")
        elif state == "blocked":
            blocked_agents += 1
            log(f"BLOCKED {handle} at {pane}: {why}")
        else:
            log(f"registered {handle} at {pane}")
    return Outcome(failed, blocked_agents)


# ---------- one named agent: `buzz restore HANDLE` ----------


def find_agent(recipients: list[dict], name: str) -> tuple[dict | None, str | None]:
    """The hub row `name` means: its full handle, or the first part of one.

    Handles read `smew` or `smew-claude-opus-karanslinux`; `smew` names the
    latter when no other handle starts with `smew-`. Returns (row, None) or
    (None, why).
    """
    exact = [r for r in recipients if r["user_id"] == name]
    if exact:
        return exact[0], None
    matches = sorted(r["user_id"] for r in recipients if r["user_id"].startswith(name + "-"))
    if len(matches) == 1:
        return next(r for r in recipients if r["user_id"] == matches[0]), None
    if matches:
        return None, f"{name} could mean {', '.join(matches)}; give the full handle"
    return None, f"no agent named {name}"


def saved_place(directory: Path, agent_id: str) -> tuple[str, dict, dict] | None:
    """Where the newest snapshot holding this session had it: (session, window, pane)."""
    for path in sorted(directory.glob("*.json"), reverse=True):
        try:
            snap = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        for session in snap.get("sessions", []):
            for window in session["windows"]:
                for pane in window["panes"]:
                    if (pane.get("agent") or {}).get("agent_id") == agent_id:
                        return session["name"], window, pane
    return None


def plan_one(
    row: dict, live: list[dict], node: str, server: str,
    running: set[str], directory: Path = SNAPSHOT_DIR,
) -> tuple[list[Step], str | None]:
    """How to resume one stopped agent: (steps, None) or ([], why not).

    Its own pane comes first when it is still in this tmux and back at a
    bare shell (the harness exited, e.g. at a trust prompt). Otherwise it goes
    into a new window where the newest snapshot had it, in that folder. A
    pane running anything else is never touched, and a session already
    running is never started twice.
    """
    handle = row["user_id"]
    if row.get("node") != node:
        return [], f"{handle} runs on {row.get('node')}; run restore there"
    if not row.get("agent_id") or not row.get("flavor"):
        return [], f"{handle} has no saved session to resume"
    agent = {"handle": handle, "flavor": row["flavor"], "agent_id": row["agent_id"], "model": row.get("model")}
    command = resume_command(agent)
    if command is None:
        return [], f"no resume command for {row['flavor']}"
    if agent["agent_id"] in running:
        return [], f"{handle} is already running (pane {row.get('pane_label') or row.get('tmux_pane')})"
    place = saved_place(directory, agent["agent_id"])
    panes = {p["pane_id"]: p for p in live}
    own = panes.get(row.get("tmux_pane")) if row.get("tmux_server") == server else None
    if own is not None:
        if own["command"] not in tmux.SHELL_COMMANDS:
            return [], f"its pane {own['pane_id']} is running {own['command']}; restore leaves it alone"
        cwd = place[2]["cwd"] if place else own["cwd"]
        label = f"{own['session']}:{own['window']}.{own['pane']}"
        return [Step(f"resume {handle} ({row['flavor']}) in its pane {label}", target=own["pane_id"],
                     launch=f"cd {shlex.quote(cwd)} && {command}", agent=agent)], None
    if place is None:
        return [], (f"{handle}'s pane is gone and no snapshot in {directory} says where it ran; "
                    "its folder is needed to resume the session")
    session, window, pane = place
    sessions = {p["session"] for p in live}
    if session in sessions:
        create = Step(f"create a window in {session} for {handle} ({window['name']})",
                      ["new-window", "-d", "-P", "-F", "#{pane_id}", "-t", f"={session}:",
                       "-n", window["name"], "-c", pane["cwd"]])
    else:
        create = Step(f"create session {session} for {handle}",
                      ["new-session", "-d", "-P", "-F", "#{pane_id}", "-s", session,
                       "-n", window["name"], "-c", pane["cwd"], "-x", "220", "-y", "50"])
    create.window = f"{handle}-window"
    launch = Step(f"resume {handle} ({row['flavor']}) in {pane['cwd']}", launch=f"cd {shlex.quote(pane['cwd'])} && {command}",
                  agent=agent, window=create.window)
    return [create, launch], None
