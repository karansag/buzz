"""Drive each hub with the real, unchanged `buzz` CLI from inside tmux panes.

Each pane of an isolated tmux server runs a short shell script: the CLI
commands an agent would run, then `cat`. The CLI finds its own pane and its
hub the normal way. The outputs and exit codes are compared between hubs.

    python rust/compat/cli_check.py [--out DIR]
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from hubs import REPO, SCRATCH, Hub, Tmux  # noqa: E402
from run_compat import differences, normal  # noqa: E402

# (pane, name, CLI arguments). Pane "a" registers first and then waits.
COMMANDS = [
    ("a", "register", ["register", "--name", "cli-a", "--flavor", "generic"]),
    ("b", "register", ["register", "--name", "cli-b", "--flavor", "generic", "--instructions", "ask me about the CLI"]),
    ("b", "whoami", ["whoami"]),
    ("b", "recipients", ["recipients"]),
    ("b", "send", ["send", "--to", "cli-a", "--message", "hello from the real CLI", "--context", "cli"]),
    ("b", "send to owner", ["send", "--to", "owner", "--message", "a note for the human"]),
    ("b", "send to nobody", ["send", "--to", "nobody", "--message", "x"]),
    ("b", "status", ["status", "checking the Rust hub"]),
    ("b", "messages", ["messages", "--limit", "5"]),
    ("b", "messages --id", ["messages", "--id", "1"]),
    ("b", "task-create", ["task-create", "try the CLI", "--assignee", "cli-a", "--description", "from pane b"]),
    ("b", "tasks", ["tasks"]),
    ("b", "task-update pick up", ["task-update", "1", "--status", "picked_up", "--worktree", "/tmp/cli-wt"]),
    ("b", "task-update done, no note", ["task-update", "1", "--status", "done"]),
    ("b", "task-update done", ["task-update", "1", "--status", "done", "--note", "ran cli_check"]),
]


def script(hub: Hub, work: Path, pane: str) -> Path:
    """The shell script a pane runs: its CLI commands, a marker, then cat."""
    out = work / f"cli-{hub.kind}"
    out.mkdir(exist_ok=True)
    lines = [
        "#!/bin/sh",
        # No harness session id may leak in from the shell that ran this check.
        "unset CLAUDE_CODE_SESSION_ID CODEX_THREAD_ID CLAUDECODE AGENT_SWARM_TOKEN",
        f"export HOME={shlex.quote(str(out / 'home'))} AGENT_SWARM_URL={hub.base} AGENT_SWARM_NODE=testnode",
        f"export AGENT_SWARM_CONFIG={shlex.quote(str(out / 'node.toml'))} PYTHONPATH={shlex.quote(str(REPO))}",
        "mkdir -p \"$HOME\"",
    ]
    if pane == "b":
        lines.append(f"while [ ! -e {shlex.quote(str(out / 'a.done'))} ]; do sleep 0.1; done")
    for n, (where, name, args) in enumerate(COMMANDS):
        if where == pane:
            cli = f"{shlex.quote(sys.executable)} -c 'from agent_swarm.client import main; raise SystemExit(main())'"
            target = shlex.quote(str(out / f"{n:02d}"))
            lines.append(f"{cli} {' '.join(shlex.quote(a) for a in args)} > {target}.out 2> {target}.err; echo $? > {target}.code")
    lines += [f"touch {shlex.quote(str(out / (pane + '.done')))}", "stty -echo", "exec cat"]
    path = out / f"pane-{pane}.sh"
    path.write_text("\n".join(lines) + "\n")
    path.chmod(0o755)
    return path


def run(kind: str, work: Path) -> list[tuple[str, object]]:
    tmux = Tmux(f"rustclone-c{kind[:2]}-{os.getpid()}", work)
    (work / kind).mkdir(parents=True, exist_ok=True)
    hub = Hub(kind, work / kind / "db.sqlite", tmux)
    steps: list[tuple[str, object]] = []
    try:
        panes = tmux.start(1, f"sh {script(hub, work, 'a')}")
        panes.append(tmux.window(f"sh {script(hub, work, 'b')}"))
        out = work / f"cli-{kind}"
        deadline = time.time() + 90
        while not (out / "b.done").exists():
            assert time.time() < deadline, "the CLI script did not finish"
            time.sleep(0.2)
        time.sleep(0.5)
        names = {str(work): "<work>", hub.base: "<hub>"}
        for n, (where, name, _) in enumerate(COMMANDS):
            stdout = (out / f"{n:02d}.out").read_text()
            try:
                stdout = json.loads(stdout)
            except ValueError:
                pass
            steps.append((f"buzz {name} (pane {where})", normal(
                {"exit": int((out / f"{n:02d}.code").read_text()), "stdout": stdout, "stderr": (out / f"{n:02d}.err").read_text()}, names)))
        steps.append(("pane a shows the message and the task notice", tmux.capture(panes[0])))
        assert not (out / "home" / ".agent-swarm").exists(), "the CLI wrote a config under its HOME"
    finally:
        hub.stop()
        tmux.kill()
    return steps


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=SCRATCH / "cli")
    args = parser.parse_args()
    work = args.out / f"run-{os.getpid()}"
    work.mkdir(parents=True)
    py, rs = run("python", work), run("rust", work)
    failed = 0
    print("| CLI step | Exit (Python / Rust) | Output |\n|---|---|---|")
    for (name, a), (_, b) in zip(py, rs, strict=True):
        diff = differences(a, b)
        failed += bool(diff)
        codes = f"{a['exit']} / {b['exit']}" if isinstance(a, dict) else ""
        print(f"| {name} | {codes} | {'same' if not diff else 'DIFFERENT: ' + '; '.join(diff[:3])} |")
    (work / "steps.json").write_text(json.dumps({"python": py, "rust": rs}, indent=1, ensure_ascii=False))
    print(f"\nsteps: {work / 'steps.json'}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
