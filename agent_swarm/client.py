"""Tiny CLI client. Usage:

    agent-swarm register [--pane Y] [--name HANDLE] [--flavor NAME] [--instructions TXT]
                         [--message-prefix TXT]
    agent-swarm autoregister [--hook] [--verbose]   # from a harness startup hook
    agent-swarm send --to Y [--context CTX] --message MSG
    agent-swarm messages [--user X] [--limit N]
    agent-swarm recipients
    agent-swarm whoami       # prints detected tmux pane + registered handle
    agent-swarm status "working on X"   # what you are doing, shown on the dashboard
    agent-swarm tasks [--status open|picked_up|done]
    agent-swarm task-create TITLE [--description TEXT] [--assignee HANDLE] [--depends-on 3,5]
    agent-swarm task-update ID --status open|picked_up|done [--assignee X] [--worktree PATH]
                            [--depends-on 3,5] [--note TEXT]   # --note required to close
    agent-swarm digest [--minutes N | --after-message ID]   # what changed, as text
    agent-swarm supervisor [HANDLE [--objective TEXT] | --clear]   # the swarm supervisor role
    agent-swarm spawn [--flavor claude|codex|pi|hermes] [--model M] [--node N]
    agent-swarm stop HANDLE   # kill that agent's tmux pane
    agent-swarm snapshot      # save this machine's tmux layout and the agent in each pane
    agent-swarm restore [--from FILE] [--apply] [--stagger SECONDS]   # after a reboot
    agent-swarm restart HANDLE... | --all [--flavor F] [--force] [--apply]   # e.g. after a harness upgrade

Defaults:
    --pane            current shell's tmux pane (via `TMUX_PANE`-targeted `tmux display-message`)
    server URL        $AGENT_SWARM_URL (else http://127.0.0.1:8765)
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import sys
import time
import tomllib
from urllib.parse import quote, urlparse

import httpx

from pathlib import Path

from . import bundle, config, restart, restore, tmux
from .tmux import current_pane, local_node


def base_url() -> str:
    return config.load().hub


def _headers() -> dict[str, str]:
    """The bearer token for this machine, when it has one.

    A hub on the tailnet requires one from every non-loopback caller; a
    single-machine install has none and needs none.
    """
    token = config.load().token
    return {"Authorization": f"Bearer {token}"} if token else {}


# Each harness tells its commands which session they belong to. That is the
# caller's identity wherever the command runs: Claude Code and Codex can run a
# session's tools in a background host whose TMUX_PANE is missing or names
# another agent's pane, so the pane alone can't say who is calling.
SESSION_ENV = (
    ("claude", "CLAUDE_CODE_SESSION_ID"),
    ("codex", "CODEX_THREAD_ID"),
    ("codex", "CODEX_SESSION_ID"),
)


class AmbiguousSession(RuntimeError):
    """Both harnesses' session ids are set and the caller can't be told apart."""


def harness_of(command: str) -> str | None:
    """The harness a process command line belongs to, or None.

    Codex runs as its native binary under .../codex/..., Claude Code as
    `claude` or a versioned binary, and Pi renames its process to `pi`.
    """
    executable, _, rest = command.partition(" ")
    program = executable.rsplit("/", 1)[-1]
    if program == "node":
        # npm installs launch the harness as `node .../bin/codex`.
        script = rest.split(" ", 1)[0].rsplit("/", 1)[-1]
        program = script if script in ("codex", "pi", "claude") else program
    if program == "codex" or "/codex/" in executable:
        return "codex"
    if program == "claude" or "/claude/versions/" in executable:
        return "claude"
    if program == "pi":
        return "pi"
    return None


def nearest_harness() -> str | None:
    """The harness this command runs under: the nearest one in its ancestry."""
    for _, command in tmux.ancestors():
        harness = harness_of(command)
        if harness:
            return harness
    return None


def harness_model(harness: str | None) -> str | None:
    """The model a harness says it runs, where it tells its commands.

    Pi sets PI_MODEL for every shell command. Codex has a top-level `model`
    in its config. Claude Code exposes nothing reliable, so a Claude agent
    passes --model from its system prompt.
    """
    if harness == "pi":
        return os.environ.get("PI_MODEL") or None
    if harness == "codex":
        if os.environ.get("CODEX_MODEL"):
            return os.environ["CODEX_MODEL"]
        path = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex") / "config.toml"
        try:
            model = tomllib.loads(path.read_text()).get("model")
        except (OSError, tomllib.TOMLDecodeError):
            return None
        return model if isinstance(model, str) and model else None
    if harness == "claude":
        return os.environ.get("CLAUDE_MODEL") or os.environ.get("ANTHROPIC_MODEL") or None
    return None


def harness_session_id() -> str | None:
    """The calling harness's session id, or None outside a harness."""
    return harness_session()[1]


def harness_session() -> tuple[str | None, str | None]:
    """(harness, session id) of the calling harness, or (None, None).

    When ids from both harnesses are set (one launched the other), the nearer
    harness in this process's ancestry is the caller. If neither appears in
    the ancestry, guessing could act as the outer session, so it's an error.
    """
    found: dict[str, str] = {}
    for harness, var in SESSION_ENV:
        value = os.environ.get(var, "").strip()
        if value and harness not in found:
            found[harness] = value
    if len(found) < 2:
        return next(iter(found.items()), (None, None))
    for _, command in tmux.ancestors():
        harness = harness_of(command)
        if harness in found:
            return harness, found[harness]
    raise AmbiguousSession(
        "both CLAUDE_CODE_SESSION_ID and CODEX_THREAD_ID are set and neither harness is in this\n"
        "  process's ancestry, so it can't tell which session is calling. Pass --agent-id <id>\n"
        "  (register), or unset the outer harness's variable, e.g. env -u CLAUDE_CODE_SESSION_ID"
    )


def caller(pane_arg: str | None = None, agent_id_arg: str | None = None) -> dict:
    """Who this process is, as far as it can tell, for the server to resolve.

    `pane_verified` is True when the pane was given explicitly or this process
    really runs inside it, False when it doesn't (a background host, or tmux's
    active-pane guess with no TMUX_PANE), None when that can't be checked.
    """
    pane = pane_arg or current_pane()
    # in_tree is only ever the process-tree check, never an explicit --pane:
    # it is what lets the hub move a registration to a new session id.
    in_tree = tmux.process_in_pane(pane) if pane else None
    verified: bool | None = True if pane_arg else in_tree
    harness, session = (None, agent_id_arg) if agent_id_arg else harness_session()
    return {
        "pane": pane,
        "pane_verified": verified,
        "pane_in_tree": in_tree,
        "agent_id": session,
        "harness": harness,
        "explicit_pane": bool(pane_arg),
    }


def whoami_lookup(who: dict) -> dict:
    """The server's view of `who`: user_id, identified_by, detail, pane label."""
    params = {"node": local_node()}
    if who["pane"]:
        params["tmux_pane"] = who["pane"]
    if who["agent_id"]:
        params["agent_id"] = who["agent_id"]
    if who["pane_verified"] is not None:
        params["pane_verified"] = "true" if who["pane_verified"] else "false"
    if who.get("pane_in_tree"):
        params["pane_in_tree"] = "true"
    if who.get("harness"):
        params["harness"] = who["harness"]
    r = httpx.get(f"{base_url()}/whoami", params=params, headers=_headers(), timeout=5)
    if not r.is_success:
        code, text = getattr(r, "status_code", "?"), getattr(r, "text", "")
        return {"user_id": None, "detail": f"server said {code}: {text[:200]}"}
    return r.json()


def registered_user(pane: str) -> str | None:
    """The handle registered for this caller (by session id, else this pane)."""
    who = caller(pane)
    who["explicit_pane"] = False
    who["pane_verified"] = who["pane_in_tree"] = tmux.process_in_pane(pane)
    return whoami_lookup(who).get("user_id")


def _not_in_pane_message(who: dict) -> str:
    source = (
        "TMUX_PANE names it" if os.environ.get("TMUX_PANE")
        else "TMUX_PANE is unset, so this is tmux's active pane"
    )
    return (
        f"this process is not running inside tmux pane {who['pane']} ({source}). Acting\n"
        "  from here would act as whatever agent is in that pane. This happens when a harness\n"
        "  runs commands in a background host: Codex's app-server (start it with --no-daemon)\n"
        "  or a Claude Code background session. Run this from the agent's own pane, or pass\n"
        "  --pane <its pane> if you are certain which pane the agent is in."
    )


def _identify_or_explain(who: dict) -> str | None:
    """The calling agent's handle, or None after printing why it isn't known."""
    if not who["pane"] and not who["agent_id"]:
        print("error: not in a tmux pane and no harness session id; run inside the agent's pane", file=sys.stderr)
        return None
    answer = whoami_lookup(who)
    if answer.get("user_id"):
        return answer["user_id"]
    if who["pane_verified"] is False and not who["agent_id"]:
        print(f"error: {_not_in_pane_message(who)}", file=sys.stderr)
    else:
        print(f"error: {answer.get('detail') or 'this caller is not registered'}; run `agent-swarm register`", file=sys.stderr)
    return None


def cmd_register(args: argparse.Namespace) -> int:
    who = caller(args.pane, args.agent_id)
    if not who["pane"]:
        print(
            "error: could not detect tmux pane; pass --pane explicitly", file=sys.stderr
        )
        return 2
    if who["pane_verified"] is False:
        # Registering binds a handle to this pane for delivery; from a process
        # outside it, that would be someone else's pane.
        print(f"error: {_not_in_pane_message(who)}", file=sys.stderr)
        return 2
    payload: dict = {"tmux_pane": who["pane"], "node": local_node()}
    if args.name:
        payload["requested_user"] = args.name
    if who["agent_id"]:
        payload["agent_id"] = who["agent_id"]
    # Without --flavor, the harness this runs under decides how messages are
    # typed into the pane; one skill then serves every harness.
    flavor = args.flavor or nearest_harness() or who["harness"]
    model = args.model or harness_model(flavor)
    if model:
        payload["model"] = model
    if flavor:
        payload["flavor"] = flavor
    if args.instructions:
        payload["instructions"] = args.instructions
    if args.message_prefix:
        payload["message_prefix"] = args.message_prefix
    if args.submit_key:
        payload["submit_key"] = args.submit_key
    r = httpx.post(f"{base_url()}/register", json=payload, headers=_headers(), timeout=5)
    print(r.text)
    return 0 if r.is_success else 1


# Processes that may sit between a pane's shell and its harness: shells and
# launchers. Anything else (emacs, vim, another harness) means the harness is
# embedded in a program, not the pane's own agent.
PANE_SHELLS = {"bash", "zsh", "sh", "dash", "fish", "ksh", "tcsh", "env", "login", "nix-shell", "direnv"}


def _one_shot(harness: str, command: str) -> bool:
    """Whether a harness command line is a non-interactive run (`claude -p`,
    `codex exec`): it has no pane of its own to receive messages."""
    words = command.split()[1:]
    if words and harness_of(command) and command.split(" ", 1)[0].rsplit("/", 1)[-1] == "node":
        words = words[1:]  # `node .../bin/codex exec`: skip the script path
    if harness == "codex":
        # Global options can precede the subcommand. Their values are not the
        # subcommand (`codex -m MODEL exec` must never claim the pane).
        takes_value = {
            "-c", "--config", "-m", "--model", "-p", "--profile", "-s", "--sandbox",
            "-a", "--ask-for-approval", "-C", "--cd", "-i", "--image", "--add-dir",
            "--enable", "--disable", "--remote", "--remote-auth-token-env", "--local-provider",
        }
        switches = {
            "--no-daemon", "--yolo", "--dangerously-bypass-approvals-and-sandbox",
            "--dangerously-bypass-hook-trust", "--approve-for-me", "--no-alt-screen",
            "--strict-config", "--search", "--worktree", "--oss",
        }
        index = 0
        while index < len(words):
            word = words[index]
            if word == "--":  # everything after this is a prompt, not a subcommand
                return False
            if not word.startswith("-"):
                return word in ("exec", "e", "review", "app-server", "mcp-server")
            option, separator, _ = word.partition("=")
            if option in takes_value:
                index += 1 if separator else 2
            elif word[:2] in takes_value and len(word) > 2 and not word.startswith("--"):
                index += 1  # attached short value, such as -mMODEL
            elif word in switches:
                index += 1
            else:
                # Unknown option arity: don't risk registering a one-shot run.
                return True
        return False
    return "-p" in words or "--print" in words


def own_pane_harness(pane: str) -> tuple[str | None, str]:
    """(harness, "") when the nearest harness runs straight in `pane`'s shell,
    else (None, why not).

    Above the harness's own processes (itself and its node launcher) only
    shells may stand before the pane's process. Another program there, an
    editor or another harness, means it is embedded, not the pane's agent.
    """
    chain = tmux.ancestors()
    for i, (_, command) in enumerate(chain):
        harness = harness_of(command)
        if harness:
            break
    else:
        return None, "no claude, codex or pi process above this command"
    pane_pid = tmux.pane_process(pane)
    if pane_pid is None:
        return None, f"tmux does not know pane {pane}"
    own = True
    for pid, command in chain[i:]:
        if own and harness_of(command) == harness:
            if _one_shot(harness, command):
                return None, f"not an interactive {harness} in a pane (one-shot run or daemon): {command[:80]}"
            if pid == pane_pid:
                return harness, ""
            continue
        own = False
        if pid == pane_pid:
            return harness, ""
        program = command.split(" ", 1)[0].rsplit("/", 1)[-1].lstrip("-")
        if program not in PANE_SHELLS:
            return None, f"{harness} runs inside {program}, not straight in pane {pane}"
    return None, f"{harness} is not running in pane {pane}"


def _hook_input() -> dict:
    """The JSON a harness hook passes on stdin, or {} when there is none."""
    if sys.stdin is None or sys.stdin.isatty():
        return {}
    try:
        data = json.loads(sys.stdin.read() or "{}")
    except (ValueError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def short_brief(brief: str) -> str:
    """The protocol brief without its peer list, for a session's context.

    A hook's output lands in every new session; the full roster would cost
    each one a screenful, and `agent-swarm recipients` gives it on demand.
    """
    lines = brief.splitlines()
    peers = [line for line in lines if line.startswith("  - ")]
    out = []
    for line in lines:
        if line.startswith("  - ") or line.startswith("Peers tagged OFFLINE"):
            continue
        out.append(line)
        if line.endswith("Currently registered peers:"):
            out.append(f"  ({len(peers)} registered; `agent-swarm recipients` lists them)")
    return "\n".join(out)


def cmd_autoregister(args: argparse.Namespace) -> int:
    """Register at session start when the harness owns its tmux pane.

    Run by each harness's startup hook. It never fails the harness: anything
    that rules registration out (no tmux, an embedded or one-shot session, the
    hub down) is a quiet exit 0, with the reason under --verbose.
    """
    def skip(why: str) -> int:
        if args.verbose:
            print(f"agent-swarm autoregister: skipped: {why}", file=sys.stderr)
        return 0

    if os.environ.get("AGENT_SWARM_AUTOREGISTER", "1") == "0":
        return skip("AGENT_SWARM_AUTOREGISTER=0")
    hook = _hook_input() if args.hook else {}
    pane = os.environ.get("TMUX_PANE")
    if not pane:
        return skip("not inside tmux")
    harness, why = own_pane_harness(pane)
    if harness is None:
        return skip(why)
    # The hook's own input names the new session. The environment may be an
    # outer session's: a nested `codex exec` inherits its parent's thread id.
    session = hook.get("session_id") if isinstance(hook.get("session_id"), str) else None
    if not session:
        try:
            env_harness, env_session = harness_session()
        except AmbiguousSession as e:
            return skip(str(e))
        # Another harness's id, inherited through the pane, is not this session.
        session = env_session if env_harness == harness else None
    payload: dict = {"tmux_pane": pane, "node": local_node(), "flavor": harness}
    if session:
        payload["agent_id"] = session
    model = hook.get("model") if isinstance(hook.get("model"), str) else None
    model = model or harness_model(harness)
    if model:
        payload["model"] = model
    try:
        r = httpx.post(f"{base_url()}/register", json=payload, headers=_headers(), timeout=5)
    except httpx.HTTPError as e:
        return skip(f"hub unreachable: {e}")
    if not r.is_success:
        return skip(f"hub refused: {r.status_code} {r.text[:200]}")
    try:
        response = r.json()
    except ValueError:
        return skip("hub returned invalid JSON")
    if not isinstance(response, dict) or not isinstance(response.get("protocol_brief"), str):
        return skip("hub returned no protocol brief")
    brief = short_brief(response["protocol_brief"])
    if args.hook:
        # Claude Code and Codex both add this to the session's context.
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": brief}}))
    else:
        print(brief)
    return 0


def _identity_payload(who: dict) -> dict:
    payload: dict = {"node": local_node()}
    if who["pane"]:
        payload["tmux_pane"] = who["pane"]
    if who["agent_id"]:
        payload["agent_id"] = who["agent_id"]
    if who["pane_verified"] is not None:
        payload["pane_verified"] = who["pane_verified"]
    if who.get("pane_in_tree"):
        payload["pane_in_tree"] = True
    if who.get("harness"):
        payload["harness"] = who["harness"]
    return payload


def cmd_send(args: argparse.Namespace) -> int:
    who = caller(getattr(args, "pane", None))
    if not _identify_or_explain(who):
        return 2
    payload = {**_identity_payload(who), "recipient": args.to, "content": args.message}
    if args.context:
        payload["context"] = args.context
    r = httpx.post(f"{base_url()}/send", json=payload, headers=_headers(), timeout=10)
    print(r.text)
    return 0 if r.is_success else 1


def cmd_status(args: argparse.Namespace) -> int:
    who = caller(getattr(args, "pane", None))
    if not _identify_or_explain(who):
        return 2
    r = httpx.post(
        f"{base_url()}/status", json={**_identity_payload(who), "text": args.text}, headers=_headers(), timeout=5
    )
    print(r.text)
    return 0 if r.is_success else 1


def cmd_messages(args: argparse.Namespace) -> int:
    params = {"limit": args.limit}
    if args.user:
        params["user"] = args.user
    r = httpx.get(f"{base_url()}/messages", params=params, headers=_headers(), timeout=5)
    print(json.dumps(r.json(), indent=2))
    return 0 if r.is_success else 1


def cmd_recipients(_: argparse.Namespace) -> int:
    r = httpx.get(f"{base_url()}/recipients", headers=_headers(), timeout=5)
    print(json.dumps(r.json(), indent=2))
    return 0 if r.is_success else 1


def cmd_snapshot(args: argparse.Namespace) -> int:
    server = tmux.server_id()
    if server is None:
        print("no tmux server is running; nothing to save", file=sys.stderr)
        return 1
    r = httpx.get(f"{base_url()}/recipients", headers=_headers(), timeout=5)
    r.raise_for_status()
    snap = restore.capture(restore.read_layout(), r.json()["recipients"], local_node(), server)
    directory = Path(args.dir).expanduser()
    path = restore.save(snap, directory)
    panes = sum(len(w["panes"]) for sess in snap["sessions"] for w in sess["windows"])
    summary = f"{len(snap['sessions'])} sessions, {panes} panes, {len(restore.agents_in(snap))} agents"
    print(f"saved {path}: {summary}" if path else f"unchanged since the last snapshot: {summary}")
    return 0


def cmd_restart(args: argparse.Namespace) -> int:
    if not args.handles and not args.all:
        print("name the agents to restart, or pass --all (optionally with --flavor)", file=sys.stderr)
        return 2
    server = tmux.server_id()
    if server is None:
        print("no tmux server is running here", file=sys.stderr)
        return 1
    r = httpx.get(f"{base_url()}/api/state", headers=_headers(), timeout=10)
    if r.status_code in (401, 403):
        # Activity, which says whether an agent is busy, is owner-only.
        print("the hub shares agent activity only with the owner; run restart on the hub's machine",
              file=sys.stderr)
        return 1
    r.raise_for_status()
    items = restart.plan(
        r.json()["recipients"], restore.read_layout(), local_node(), server,
        handles=args.handles or None, flavor=args.flavor, force=args.force,
    )
    if not items:
        print("no agents to restart")
        return 0
    own = os.environ.get("TMUX_PANE")
    # The caller's own pane goes last: restarting it ends this command.
    items.sort(key=lambda i: i.pane == own)
    failed = 0
    started = 0
    for item in items:
        if item.skip:
            print(f"  skip {item.handle}: {item.skip}")
            continue
        if not args.apply:
            print(f"  restart {item.handle} in {item.pane}\n      $ {item.launch}")
            continue
        if started and args.stagger > 0:
            time.sleep(args.stagger)
        if item.pane == own:
            print(f"  restart {item.handle} (this pane): handed to tmux; this command ends here", flush=True)
        err = restart.apply(item, own)
        started += 1
        if err:
            failed += 1
            print(f"  FAILED {item.handle}: {err}")
        elif item.pane != own:
            print(f"  restarted {item.handle}", flush=True)
    if not args.apply:
        print("dry run: nothing changed. Run again with --apply to do this.")
    return 1 if failed else 0


def cmd_restore(args: argparse.Namespace) -> int:
    directory = Path(args.dir).expanduser()
    path = Path(args.from_file).expanduser() if args.from_file else restore.pick(directory, tmux.server_id())
    if path is None:
        print(f"no snapshot from an earlier tmux server in {directory}", file=sys.stderr)
        return 1
    snap = json.loads(path.read_text())
    if snap.get("node") != local_node():
        print(f"{path} was taken on {snap.get('node')}, not {local_node()}", file=sys.stderr)
        return 1
    r = httpx.get(f"{base_url()}/recipients", headers=_headers(), timeout=5)
    r.raise_for_status()
    running = restore.running_sessions(r.json()["recipients"], restore.agents_in(snap))
    steps = restore.plan(snap, restore.read_layout(), running)
    print(f"snapshot {path} (taken {snap['taken_at']}, {len(restore.agents_in(snap))} agents)")
    if not args.apply:
        for step in steps:
            print(f"  {step.describe}" + (f"\n      $ {step.launch}" if step.launch else ""))
        print("dry run: nothing changed. Run again with --apply to do this.")
        return 0
    failed = restore.apply(steps, args.stagger, log=lambda line: print(f"  {line}", flush=True))
    print(f"done, {failed} failed" if failed else "done")
    return 1 if failed else 0


def cmd_prune(args: argparse.Namespace) -> int:
    r = httpx.post(
        f"{base_url()}/recipients/prune",
        json={"include_shells": args.include_shells},
        timeout=10,
    )
    print(json.dumps(r.json(), indent=2))
    return 0 if r.is_success else 1


def cmd_unregister(args: argparse.Namespace) -> int:
    user = args.user
    if user is None:
        who = caller()
        if who["pane"] or who["agent_id"]:
            user = whoami_lookup(who).get("user_id")
    if user is None:
        print("error: current pane is not registered; pass --user HANDLE", file=sys.stderr)
        return 2
    response = httpx.delete(f"{base_url()}/recipients/{quote(user, safe='')}", headers=_headers(), timeout=5)
    print(response.text)
    return 0 if response.is_success else 1


def cmd_tasks(args: argparse.Namespace) -> int:
    r = httpx.get(f"{base_url()}/tasks", headers=_headers(), timeout=5)
    if not r.is_success:
        print(r.text, file=sys.stderr)
        return 1
    tasks = r.json()["tasks"]
    if args.status:
        tasks = [t for t in tasks if t["status"] == args.status]
    print(json.dumps({"tasks": tasks}, indent=2))
    return 0


def _parse_deps(raw: str) -> list[int]:
    """'3,5' -> [3, 5]; '' -> [] (clears dependencies on update)."""
    return [int(part) for part in raw.split(",") if part.strip()]


def _acting_fields() -> dict:
    """Who is acting, so a task notification goes out in this agent's name.

    Keep an explicitly unverified pane in the request so the server refuses
    it. Dropping that evidence would make a loopback request look like an
    owner action.
    """
    who = caller()
    if not who["pane"] and not who["agent_id"]:
        return {}
    return _identity_payload(who)


def cmd_task_create(args: argparse.Namespace) -> int:
    payload: dict = {"title": args.title, **_acting_fields()}
    if args.description:
        payload["description"] = args.description
    if args.assignee:
        payload["assignee"] = args.assignee
    if args.depends_on is not None:
        payload["depends_on"] = _parse_deps(args.depends_on)
    r = httpx.post(f"{base_url()}/tasks", json=payload, headers=_headers(), timeout=5)
    print(r.text)
    return 0 if r.is_success else 1


def cmd_task_update(args: argparse.Namespace) -> int:
    payload: dict = {}
    fields = _acting_fields()
    if args.status:
        payload["status"] = args.status
    if args.assignee is not None:
        payload["assignee"] = args.assignee
    if args.worktree is not None:
        payload["worktree"] = args.worktree
        # A path is only meaningful on the machine it is on.
        payload["worktree_node"] = local_node()
    if args.depends_on is not None:
        payload["depends_on"] = _parse_deps(args.depends_on)
    if args.note is not None:
        payload["note"] = args.note
    if not payload:
        print(
            "error: pass --status, --assignee, --worktree, --note, "
            "and/or --depends-on",
            file=sys.stderr,
        )
        return 2
    payload.update(fields)
    r = httpx.patch(f"{base_url()}/tasks/{args.id}", json=payload, headers=_headers(), timeout=5)
    print(r.text)
    return 0 if r.is_success else 1


def cmd_digest(args: argparse.Namespace) -> int:
    params: dict = {"minutes": args.minutes}
    if args.after_message is not None:
        params["after_message"] = args.after_message
    r = httpx.get(f"{base_url()}/digest", params=params, headers=_headers(), timeout=10)
    if not r.is_success:
        print(r.text, file=sys.stderr)
        return 1
    print(r.json()["text"] if not args.json else json.dumps(r.json(), indent=2))
    return 0


def cmd_supervisor(args: argparse.Namespace) -> int:
    if args.clear:
        r = httpx.delete(f"{base_url()}/supervisor", headers=_headers(), timeout=10)
    elif args.handle:
        payload = {"user_id": args.handle}
        if args.objective:
            payload["objective"] = args.objective
        r = httpx.put(f"{base_url()}/supervisor", json=payload, headers=_headers(), timeout=15)
    else:
        r = httpx.get(f"{base_url()}/supervisor", headers=_headers(), timeout=5)
        if r.is_success and r.json()["supervisor"] is None:
            print("no supervisor is set; appoint one with: agent-swarm supervisor <handle> --objective \"...\"")
            return 0
    print(json.dumps(r.json(), indent=2) if r.headers.get("content-type", "").startswith("application/json") else r.text)
    return 0 if r.is_success else 1


def cmd_spawn(args: argparse.Namespace) -> int:
    payload: dict = {"flavor": args.flavor}
    if args.model:
        payload["model"] = args.model
    if args.node:
        payload["node"] = args.node
    r = httpx.post(f"{base_url()}/agents/spawn", json=payload, headers=_headers(), timeout=30)
    print(r.text)
    return 0 if r.is_success else 1


def cmd_stop(args: argparse.Namespace) -> int:
    r = httpx.post(f"{base_url()}/agents/{quote(args.handle, safe='')}/stop", headers=_headers(), timeout=15)
    print(r.text)
    return 0 if r.is_success else 1


def cmd_join(args: argparse.Namespace) -> int:
    """Point this machine at a hub: write the settings file, then check the
    hub answers and takes this token for this node."""
    node = args.node or config.hostname()
    path = config.write(args.hub, args.token, node)
    hub = config.load().hub
    reachable, enrolled, problem = False, False, None
    try:
        reachable = httpx.get(f"{hub}/health", timeout=5).is_success
        r = httpx.get(f"{hub}/nodes/me", headers=_headers(), timeout=5)
        if r.status_code == 401:
            problem = "the hub rejected the token"
        elif r.is_success:
            me = r.json()
            if me.get("kind") == "node" and me.get("node") != node:
                problem = f"the token belongs to node {me.get('node')!r}, not {node!r}; pass --node {me.get('node')}"
            elif me.get("kind") == "node":
                enrolled = True
            else:
                problem = "no token given: the hub sees this as the owner, which only works on the hub itself"
        else:
            problem = f"unexpected answer from the hub: {r.status_code}"
    except httpx.HTTPError as e:
        problem = f"the hub did not answer: {e}"
    print(json.dumps({"config": str(path), "hub": hub, "node": node,
                      "hub_reachable": reachable, "enrolled": enrolled}, indent=2))
    if problem:
        print(f"warning: {problem}; settings were written anyway", file=sys.stderr)
        return 1
    return 0


def cmd_node_token(args: argparse.Namespace) -> int:
    """Enrol a node with the hub (or rotate its token). Prints the token once."""
    r = httpx.post(
        f"{base_url()}/nodes/{quote(args.name, safe='')}/token", headers=_headers(), timeout=5
    )
    if not r.is_success:
        print(r.text, file=sys.stderr)
        return 1
    body = r.json()
    print(json.dumps(body, indent=2))
    # The join command runs on the other machine, so a loopback hub address
    # would point at that machine itself; guess this host's name instead.
    hub = base_url()
    host = urlparse(hub).hostname or ""
    if host in ("127.0.0.1", "localhost", "::1"):
        port = urlparse(hub).port or 8765
        hub = f"http://{config.hostname()}:{port}"
        print(f"(hub address guessed as {hub}; use this machine's tailnet name if that is wrong)", file=sys.stderr)
    print(
        f"On {body['name']}, run:\n  agent-swarm join {shlex.quote(hub)} "
        f"--token {shlex.quote(body['token'])} --node {shlex.quote(body['name'])}",
        file=sys.stderr,
    )
    return 0


def cmd_nodes(_: argparse.Namespace) -> int:
    r = httpx.get(f"{base_url()}/nodes", headers=_headers(), timeout=5)
    print(json.dumps(r.json(), indent=2))
    return 0 if r.is_success else 1


def cmd_export(args: argparse.Namespace) -> int:
    """Write this machine's agents, teams, and tasks out as a bundle.

    Reads the database without writing to it, so it is safe against a live
    server's file or an archived copy.
    """
    path = args.db or os.environ.get("AGENT_SWARM_DB", "~/.agent-swarm/db.sqlite")
    try:
        conn = bundle.open_readonly(path)
        data = bundle.read(conn, with_messages=args.with_messages)
    except bundle.Invalid as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    text = json.dumps(data, indent=1)
    counts = {k: len(data[k]) for k in ("agents", "teams", "tasks", "messages")}
    if args.out and args.out != "-":
        out = Path(args.out).expanduser()
        out.write_text(text)
        print(json.dumps({"out": str(out), "source": data["source"]["id"], **counts}, indent=2))
    else:
        print(text)
        print(json.dumps({"source": data["source"]["id"], **counts}), file=sys.stderr)
    return 0


def cmd_import(args: argparse.Namespace) -> int:
    """Hand a bundle to the hub, for agents that run on `--node`."""
    try:
        data = json.loads(Path(args.bundle).expanduser().read_text())
    except (OSError, ValueError) as e:
        print(f"error: could not read {args.bundle}: {e}", file=sys.stderr)
        return 2
    payload = {
        "node": args.node, "bundle": data, "dry_run": args.dry_run,
        "again": args.again, "merge_teams": args.merge_teams,
    }
    r = httpx.post(f"{base_url()}/import", json=payload, headers=_headers(), timeout=120)
    if not r.is_success:
        print(r.text, file=sys.stderr)
        return 1
    body = r.json()
    print(json.dumps(body["report"], indent=2))
    if body["dry_run"]:
        print("\nnothing was written; run again without --dry-run", file=sys.stderr)
    if body.get("register"):
        print(
            "\nOn " + args.node + ", only agents still running and not automatically "
            "reconnected need to run their line inside their own pane. "
            "Offline agents can wait until resumed:", file=sys.stderr,
        )
        for line in body["register"]:
            print("  " + line, file=sys.stderr)
    return 0


def cmd_whoami(_: argparse.Namespace) -> int:
    who = caller()
    answer = whoami_lookup(who) if (who["pane"] or who["agent_id"]) else {}
    if who["pane_verified"] is False and not answer.get("identified_by") == "session":
        print(f"warning: {_not_in_pane_message(who)}", file=sys.stderr)
    session = who["agent_id"]
    print(
        json.dumps(
            {
                "user": answer.get("user_id"),
                "identified_by": answer.get("identified_by"),
                "session": f"{session[:8]}…" if session else None,
                "pane": who["pane"],
                "in_pane": who["pane_verified"],
                "node": local_node(),
                "server": base_url(),
                **({"detail": answer["detail"]} if answer.get("detail") else {}),
            },
            indent=2,
        )
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="agent-swarm")
    sub = p.add_subparsers(dest="cmd", required=True)

    reg = sub.add_parser("register")
    reg.add_argument("--pane")
    reg.add_argument(
        "--name",
        help="preferred handle; granted when free, 409 when another agent holds it "
        "(default: server picks from the name pool)",
    )
    reg.add_argument(
        "--agent-id",
        help="stable session identifier (e.g. conversation UUID); used as real identity",
    )
    reg.add_argument(
        "--model",
        help="exact model id shown on the dashboard (e.g. claude-opus-4-7); "
        "default: what the harness reports (PI_MODEL, Codex config)",
    )
    reg.add_argument(
        "--flavor",
        help="delivery flavor (claude, codex, pi, hermes); default: the harness this runs under",
    )
    reg.add_argument(
        "--instructions",
        help="human guidance for peers talking to this agent",
    )
    reg.add_argument(
        "--message-prefix",
        help="literal text prefixed to each delivered message (e.g. '/queue ')",
    )
    reg.add_argument(
        "--submit-key",
        help="tmux key name used to submit each delivered message (default: C-m)",
    )
    reg.set_defaults(func=cmd_register)

    unregister = sub.add_parser("unregister", help="remove one registration without deleting messages or tasks")
    unregister.add_argument("--user", help="handle to remove (default: current pane's handle)")
    unregister.set_defaults(func=cmd_unregister)

    snap = sub.add_parser(
        "snapshot", help="save this machine's tmux layout and the agent in each pane, for restore"
    )
    snap.add_argument("--dir", default=str(restore.SNAPSHOT_DIR))
    snap.set_defaults(func=cmd_snapshot)

    rsa = sub.add_parser(
        "restart", help="restart agents in place with their harness's resume command, e.g. after an upgrade"
    )
    rsa.add_argument("handles", nargs="*", help="agents to restart")
    rsa.add_argument("--all", action="store_true", help="every agent on this machine")
    rsa.add_argument("--flavor", help="with --all: only this harness (claude, codex, pi, hermes)")
    rsa.add_argument("--force", action="store_true", help="also restart agents that are working or waiting on you")
    rsa.add_argument("--apply", action="store_true", help="do it; without this, only print the plan")
    rsa.add_argument("--stagger", type=float, default=3.0, help="seconds between restarts")
    rsa.set_defaults(func=cmd_restart)

    rst = sub.add_parser(
        "restore", help="after a reboot, recreate tmux sessions from a snapshot and resume the agents"
    )
    rst.add_argument("--dir", default=str(restore.SNAPSHOT_DIR))
    rst.add_argument(
        "--from", dest="from_file",
        help="snapshot file (default: newest one from an earlier tmux server)",
    )
    rst.add_argument("--apply", action="store_true", help="do it; without this, only print the plan")
    rst.add_argument("--stagger", type=float, default=5.0, help="seconds between agent launches")
    rst.set_defaults(func=cmd_restore)

    snd = sub.add_parser("send")
    snd.add_argument("--to", required=True)
    snd.add_argument("--message", required=True)
    snd.add_argument("--context")
    snd.add_argument("--pane", help="the agent's tmux pane, when this process isn't in it")
    snd.set_defaults(func=cmd_send)

    msg = sub.add_parser("messages")
    msg.add_argument("--user")
    msg.add_argument("--limit", type=int, default=20)
    msg.set_defaults(func=cmd_messages)

    rcp = sub.add_parser("recipients")
    rcp.set_defaults(func=cmd_recipients)

    prune = sub.add_parser(
        "prune",
        help="forget registered agents whose tmux pane no longer exists "
        "(add --include-shells to also forget panes that only run a bare shell)",
    )
    prune.add_argument("--include-shells", action="store_true")
    prune.set_defaults(func=cmd_prune)

    tsk = sub.add_parser("tasks")
    tsk.add_argument("--status", choices=["open", "picked_up", "done"])
    tsk.set_defaults(func=cmd_tasks)

    tcreate = sub.add_parser(
        "task-create", help="file a task so it appears on the shared task board"
    )
    tcreate.add_argument("title")
    tcreate.add_argument("--description")
    tcreate.add_argument("--assignee")
    tcreate.add_argument(
        "--depends-on", help="comma-separated task ids this task waits on (e.g. 3,5)"
    )
    tcreate.set_defaults(func=cmd_task_create)

    tup = sub.add_parser("task-update")
    tup.add_argument("id", type=int)
    tup.add_argument("--status", choices=["open", "picked_up", "done"])
    tup.add_argument("--assignee")
    tup.add_argument("--worktree")
    tup.add_argument(
        "--depends-on",
        help="comma-separated task ids this task waits on; empty string clears",
    )
    tup.add_argument(
        "--note",
        help="how to verify the work: how to use it, how to reproduce the "
        "problem it fixes, and where to look. Required to close a task.",
    )
    tup.set_defaults(func=cmd_task_update)

    st = sub.add_parser(
        "status", help="say in a line what you are working on; shown on the dashboard"
    )
    st.add_argument("text", help='e.g. "working on #12: pane-id migration"')
    st.add_argument("--pane", help="the agent's tmux pane, when this process isn't in it")
    st.set_defaults(func=cmd_status)

    auto = sub.add_parser(
        "autoregister",
        help="register from a harness startup hook, only when it owns its tmux pane",
    )
    auto.add_argument("--hook", action="store_true",
                      help="read the hook's JSON on stdin and answer as SessionStart hook output")
    auto.add_argument("--verbose", action="store_true", help="say why registration was skipped")
    auto.set_defaults(func=cmd_autoregister)

    who = sub.add_parser("whoami")
    who.set_defaults(func=cmd_whoami)

    dg = sub.add_parser(
        "digest", help="what changed in the swarm (agents, tasks, messages), as text for an agent to read"
    )
    dg.add_argument("--minutes", type=float, default=60, help="window when no cursor is given (default 60)")
    dg.add_argument(
        "--after-message", type=int,
        help="exact cursor: the message id the last digest ended with (its final line names it)",
    )
    dg.add_argument("--json", action="store_true", help="print the text, cursor, and counts as JSON")
    dg.set_defaults(func=cmd_digest)

    sup = sub.add_parser(
        "supervisor",
        help="show, appoint, or clear the swarm supervisor: the agent the owner asks about the whole swarm",
    )
    sup.add_argument("handle", nargs="?", help="agent to appoint; omit to show the current one")
    sup.add_argument("--objective", help="what to watch or drive; delivered with the role prompt")
    sup.add_argument("--clear", action="store_true", help="end the role")
    sup.set_defaults(func=cmd_supervisor)

    sp = sub.add_parser("spawn", help="launch a new agent in a fresh tmux window and register it")
    sp.add_argument("--flavor", default="claude", choices=["claude", "codex", "pi", "hermes"])
    sp.add_argument("--model", help="one of the harness's known models (see the dashboard's spawn menu)")
    sp.add_argument("--node", help="machine to spawn on (default: the hub)")
    sp.set_defaults(func=cmd_spawn)

    stp = sub.add_parser("stop", help="kill an agent's tmux pane")
    stp.add_argument("handle")
    stp.set_defaults(func=cmd_stop)

    join = sub.add_parser(
        "join", help="point this machine at a hub (writes ~/.agent-swarm/node.toml)"
    )
    join.add_argument("hub", help="hub URL, e.g. http://karans-linux:8765")
    join.add_argument("--token", help="this machine's token, from `agent-swarm node-token` on the hub")
    join.add_argument("--node", help="this machine's node name (default: short hostname)")
    join.set_defaults(func=cmd_join)

    ntok = sub.add_parser(
        "node-token", help="enrol a machine with this hub, or rotate its token; prints it once"
    )
    ntok.add_argument("name", help="the node name that machine will register as")
    ntok.set_defaults(func=cmd_node_token)

    nds = sub.add_parser("nodes", help="list enrolled machines")
    nds.set_defaults(func=cmd_nodes)

    exp = sub.add_parser(
        "export", help="write this machine's agents, teams, and tasks out as a bundle"
    )
    exp.add_argument("--db", help="database to read (default: $AGENT_SWARM_DB)")
    exp.add_argument("--out", help="file to write (default: standard output)")
    exp.add_argument(
        "--with-messages", action="store_true",
        help="carry message history too, as history: it is never delivered again",
    )
    exp.set_defaults(func=cmd_export)

    imp = sub.add_parser("import", help="take a bundle into this hub")
    imp.add_argument("bundle", help="the file `agent-swarm export` wrote")
    imp.add_argument("--node", required=True, help="the machine those agents run on")
    imp.add_argument("--dry-run", action="store_true", help="report what would happen, write nothing")
    imp.add_argument("--again", action="store_true", help="import a bundle that was imported before")
    imp.add_argument(
        "--merge-teams", action="store_true",
        help="add to a team of the same name here instead of importing it under a new one",
    )
    imp.set_defaults(func=cmd_import)

    args = p.parse_args(argv)
    try:
        return args.func(args)
    except AmbiguousSession as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
