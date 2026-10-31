"""Tmux delivery. Keeps stdin/text-injection details in one place."""

from __future__ import annotations

import functools
import json
import os
import re
import shlex
import socket
import subprocess
import time
from pathlib import Path
from typing import Callable, NamedTuple


# Panes are addressed by tmux's pane id (%N), which never changes or gets
# reused while the tmux server runs. The positional session:window.pane form
# is only a display label: tmux reuses and renumbers it as windows and panes
# come and go, so an agent stored that way can end up pointing at another.


def current_pane() -> str | None:
    """Return the caller's own pane id (%N), or None if not in tmux."""
    pane_target = os.environ.get("TMUX_PANE")
    command = ["tmux", "display-message", "-p"]
    if pane_target:
        command.extend(["-t", pane_target])
    command.append("#{pane_id}")
    try:
        out = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=True,
            timeout=2,
        )
    except (subprocess.SubprocessError, FileNotFoundError):
        return None
    val = out.stdout.strip()
    return val or None


DEFAULT_FLAVOR = "generic"

DEFAULT_SUBMIT_KEY = "C-m"

FLAVOR_SUBMIT_KEYS = {
    "generic": DEFAULT_SUBMIT_KEY,
    "claude": DEFAULT_SUBMIT_KEY,
    "codex": "Enter",
    "hermes": DEFAULT_SUBMIT_KEY,
    "pi": "Enter",
}

# The slash command that compacts each harness's context, sent from the
# dashboard's compact button. Each one checked by pasting it into a live pane
# of the installed harness. "generic" has none: there is no known harness.
FLAVOR_COMPACT_COMMANDS = {
    "claude": "/compact",
    "codex": "/compact",
    "pi": "/compact",
    "hermes": "/compress",
}

FLAVOR_SUBMIT_DELAYS = {
    "codex": 0.2,
}

SUBMIT_VERIFY_DELAY = float(
    os.environ.get(
        "AGENT_SWARM_SUBMIT_VERIFY_DELAY",
        os.environ.get("AGENT_MSG_SUBMIT_VERIFY_DELAY", "1.5"),
    )
)


def _has_label_token(label: str, token: str) -> bool:
    return (
        re.search(rf"(^|[^a-z0-9]){re.escape(token)}([^a-z0-9]|$)", label)
        is not None
    )


def infer_flavor(model: str | None) -> str:
    """Best-effort default delivery flavor from a telemetry model label."""
    if not model:
        return DEFAULT_FLAVOR
    label = model.lower()
    if "codex" in label:
        return "codex"
    if "claude" in label:
        return "claude"
    if "hermes" in label:
        return "hermes"
    if _has_label_token(label, "pi"):
        return "pi"
    return DEFAULT_FLAVOR


def local_node() -> str:
    """This machine's node name, as agents report it and the server stores it.

    AGENT_SWARM_NODE wins, then the name in ~/.agent-swarm/node.toml, then the
    short hostname. See agent_swarm.config.
    """
    from . import config

    return config.load().node


def submit_key_for_flavor(flavor: str | None) -> str:
    """Return the default submit key for a delivery flavor."""
    if not flavor:
        return DEFAULT_SUBMIT_KEY
    return FLAVOR_SUBMIT_KEYS.get(flavor.lower(), DEFAULT_SUBMIT_KEY)


def compact_command_for_flavor(flavor: str | None) -> str | None:
    """The slash command that compacts a harness's context, or None."""
    return FLAVOR_COMPACT_COMMANDS.get((flavor or DEFAULT_FLAVOR).lower())


def submit_delay_for_flavor(flavor: str | None) -> float:
    """Return the delay to wait after text injection before submit."""
    if not flavor:
        return 0.0
    return FLAVOR_SUBMIT_DELAYS.get(flavor.lower(), 0.0)


def status_title(user_id: str, flavor: str | None = None) -> str:
    """The pane title older builds set at registration.

    Registration no longer sets it, so the harness's own title (its summary of
    the current work) stays visible; the pane-id migration still looks for it.
    """
    if flavor:
        return f"agent-swarm: {user_id} ({flavor})"
    return f"agent-swarm: {user_id}"


# Titles a pane shows when nobody has said what it is doing: the tmux default
# (the host name), a harness's idle name, and our own old registration label.
_EMPTY_TITLES = {"claude code", "codex", "claude", ""}


def title_summary(title: str) -> str | None:
    """What a harness says it is doing, read from its pane title, or None.

    Claude Code writes a spinner or "✳" then a short topic ("✳ PR 9130
    review"); Codex writes the topic then " | <directory>". Both are stripped.
    """
    text = re.sub(r"^[^\w(\[]+", "", title or "").strip()
    topic, sep, _where = text.rpartition(" | ")
    if sep and topic:
        text = topic.strip()
    if text.lower() in _EMPTY_TITLES or text.startswith("agent-swarm:"):
        return None
    if text in {socket.gethostname(), socket.gethostname().split(".")[0]}:
        return None
    return text[:200]


def tag_pane(pane: str, handle: str) -> tuple[bool, str | None]:
    """Record the agent's handle as the pane option @agent_swarm.

    tmux formats can show it (`#{@agent_swarm}`) while the pane title keeps
    the harness's own summary of the current work.
    """
    try:
        subprocess.run(
            ["tmux", "set-option", "-p", "-t", pane, "@agent_swarm", handle],
            capture_output=True,
            text=True,
            check=True,
            timeout=2,
        )
    except subprocess.CalledProcessError as e:
        return False, e.stderr.strip() or str(e)
    except (subprocess.SubprocessError, FileNotFoundError) as e:
        return False, str(e)
    return True, None


def rename_window(pane: str, name: str) -> tuple[bool, str | None]:
    """Rename the tmux window containing `pane` so it shows the agent's id
    in the window list. Also disables automatic renaming so the launched
    command can't clobber it. Returns (ok, error_message_or_None)."""
    try:
        subprocess.run(
            ["tmux", "set-window-option", "-t", pane, "automatic-rename", "off"],
            capture_output=True,
            text=True,
            check=True,
            timeout=2,
        )
        subprocess.run(
            ["tmux", "rename-window", "-t", pane, name],
            capture_output=True,
            text=True,
            check=True,
            timeout=2,
        )
    except subprocess.CalledProcessError as e:
        return False, e.stderr.strip() or str(e)
    except (subprocess.SubprocessError, FileNotFoundError) as e:
        return False, str(e)
    return True, None


def _composer_holds_text(pane: str) -> bool:
    """True when the row under the cursor is more than a bare prompt.

    After a successful submit the composer collapses to an empty prompt line.
    When the submit key was swallowed (e.g. Codex still consuming a paste burst)
    the text — or Codex's "[Pasted Content N chars]" placeholder — is still there.
    """
    try:
        pos = subprocess.run(
            ["tmux", "display-message", "-p", "-t", pane, "#{cursor_y}"],
            capture_output=True, text=True, check=True, timeout=2,
        )
        y = int(pos.stdout.strip())
        screen = subprocess.run(
            ["tmux", "capture-pane", "-p", "-t", pane],
            capture_output=True, text=True, check=True, timeout=3,
        )
    except (ValueError, subprocess.SubprocessError, FileNotFoundError):
        return False
    rows = screen.stdout.splitlines()
    if y < 0 or y >= len(rows):
        return False
    row = rows[y].strip()
    return len(re.sub(r"^[>›❯$%#]+", "", row).strip()) > 0


SUBMIT_POLL_INTERVAL = 0.1


def _await_submit(pane: str, timeout: float) -> bool:
    """Wait up to `timeout` for the composer to clear after the submit key.

    Polls rather than sleeping the whole window: a harness usually takes the
    submit within a couple of polls, so a send returns in a few hundred ms.
    True once the composer is empty; False if text is still there at the end.
    """
    deadline = time.monotonic() + timeout
    while True:
        time.sleep(SUBMIT_POLL_INTERVAL)
        if not _composer_holds_text(pane):
            return True
        if time.monotonic() >= deadline:
            return False


class Uncertain(Exception):
    """An operation's side effect may have happened; whether it did could not
    be established. Never retry an operation that ended this way on its own:
    a message may already be in the pane, a window may already exist.

    `created` is set when the operation got far enough to know which pane it
    made (a spawn whose launch command timed out): a Created, with the server
    that made it, so the pane is never rebound to whatever tmux runs later.
    """

    def __init__(self, message: str, created: "Created | None" = None):
        super().__init__(message)
        self.created = created


class Created(NamedTuple):
    """A pane as reported by the command that created it: id, positional
    label, and the tmux server that issued the id, all from one answer."""

    pane: str
    label: str
    tmux_server: str


def _error_text(e: Exception) -> str:
    if isinstance(e, subprocess.CalledProcessError):
        return (e.stderr or "").strip() or str(e)
    return str(e)


def deliver(
    pane: str,
    text: str,
    message_prefix: str | None = None,
    submit_key: str = DEFAULT_SUBMIT_KEY,
    flavor: str | None = None,
    retry_submit: bool = True,
) -> tuple[bool, str | None]:
    """Paste text into a tmux pane, then submit it.

    The text goes in as a bracketed paste (tmux only adds the paste markers when
    the pane's application has enabled them), so TUIs that detect typing bursts
    as pastes — Codex in particular — receive one atomic paste event and the
    following submit key is unambiguous.

    If the composer still holds text after the submit key, the key is sent
    once more. retry_submit=False skips that: a command that opens a menu
    (Codex's /model) leaves a menu row under the cursor, which looks like
    unsent text, and a second key would pick from the menu.

    Returns (ok, error) only when the outcome is certain: loading the buffer
    failed, or tmux refused the paste, so nothing reached the pane. Once the
    paste may have happened, any error raises Uncertain instead: a timeout
    on the paste itself, or anything wrong with the submit key afterwards.
    """
    injected = f"{message_prefix or ''}{text}"
    buf = f"agent-swarm-{os.getpid()}-{time.monotonic_ns()}"
    try:
        subprocess.run(
            ["tmux", "load-buffer", "-b", buf, "-"],
            input=injected, capture_output=True, text=True, check=True, timeout=5,
        )
    except (subprocess.SubprocessError, FileNotFoundError) as e:
        return False, _error_text(e)
    try:
        subprocess.run(
            ["tmux", "paste-buffer", "-p", "-d", "-b", buf, "-t", pane],
            capture_output=True, text=True, check=True, timeout=5,
        )
    except subprocess.CalledProcessError as e:
        # tmux answered and said no (bad target, no such buffer): no paste.
        return False, _error_text(e)
    except (subprocess.SubprocessError, FileNotFoundError) as e:
        raise Uncertain(f"paste did not report back: {_error_text(e)}") from e
    try:
        time.sleep(max(0.05, submit_delay_for_flavor(flavor)))
        subprocess.run(
            ["tmux", "send-keys", "-t", pane, submit_key],
            capture_output=True, text=True, check=True, timeout=5,
        )
        if retry_submit and not _await_submit(pane, SUBMIT_VERIFY_DELAY):
            # Retry only the submit key once; re-pasting would duplicate text.
            subprocess.run(
                ["tmux", "send-keys", "-t", pane, submit_key],
                capture_output=True, text=True, check=True, timeout=5,
            )
    except (subprocess.SubprocessError, FileNotFoundError) as e:
        raise Uncertain(f"pasted, but the submit key failed: {_error_text(e)}") from e
    return True, None


AGENTS_SESSION = "agents"

# Harnesses the dashboard can spawn. Each has a launch binary, the CLI flag
# that selects a model, and the models offered in the UI. A fixed model list
# goes stale as models are released, so each list is either aliases the
# harness resolves to its newest model (claude, pi) or read from the
# harness's own catalog (codex).
# "generic" is intentionally not spawnable: launching a bare shell produces a
# registered pane with no agent in it, which is not a working target.
#
# One fixed launch per harness, with no permission choice (task #170):
# `binary [model_flag model] launch_args`, and no model flag at all when the
# harness default is wanted. startup_args remove interactive startup blockers
# that would leave a fresh pane stuck before the agent is usable (codex's
# update prompt). Every flag verified against the installed harness.
class HarnessSpec:
    def __init__(
        self,
        binary: str,
        model_flag: str,
        models: list[str] | Callable[[], list[str]],
        startup_args: str = "",
        launch_args: str = "",
        if_supported: tuple[str, ...] = (),
    ):
        self.binary = binary
        self.model_flag = model_flag
        self._models = models
        self.startup_args = startup_args
        self.launch_args = launch_args
        # Flags passed only when the installed harness accepts them, so a
        # flag added in a newer release can't stop an older one from starting.
        self.if_supported = if_supported

    @property
    def models(self) -> list[str]:
        return self._models() if callable(self._models) else self._models


def codex_models() -> list[str]:
    """The models Codex's own /model picker lists, in its order.

    Codex refreshes ~/.codex/models_cache.json from its servers, so new
    models show up here without a code change. Empty when Codex has never
    run on this machine; the menu then offers only the default model.
    """
    path = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex") / "models_cache.json"
    try:
        models = json.loads(path.read_text())["models"]
        listed = [m for m in models if m.get("visibility") == "list" and m.get("slug")]
        return [m["slug"] for m in sorted(listed, key=lambda m: m.get("priority", 0))]
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return []


HARNESS_SPAWN: dict[str, HarnessSpec] = {
    "claude": HarnessSpec(
        "claude",
        "--model",
        # Aliases: Claude Code maps each to the newest model of that family.
        ["opus", "sonnet", "haiku", "fable"],
        # Auto mode lets a classifier approve routine commands, so a spawned
        # agent can work without bypassing permission checks entirely.
        launch_args="--permission-mode auto",
    ),
    "codex": HarnessSpec(
        "codex",
        "--model",
        codex_models,
        startup_args="-c check_for_update_on_startup=false",
        # Codex's workspace-write sandbox blocks the tmux socket, the local
        # agent-swarm API and DNS, so an agent spawned inside it could not
        # register, send, or reach anything. --yolo is codex's short alias
        # for --dangerously-bypass-approvals-and-sandbox (accepted by 0.159).
        launch_args="--yolo",
        # Codex 0.156+ otherwise runs the session's commands in one shared
        # app-server daemon, whose TMUX_PANE is whichever pane started it, so
        # the agent's agent-swarm commands would claim that pane. Older
        # releases reject the flag.
        if_supported=("--no-daemon",),
    ),
    "pi": HarnessSpec(
        "pi",
        "--model",
        [
            "~anthropic/claude-opus-latest",
            "~anthropic/claude-sonnet-latest",
            "~openai/gpt-latest",
        ],
        # pi does not gate commands behind approval prompts: no extra flags.
    ),
    "hermes": HarnessSpec(
        "hermes",
        "-m",
        [],
        launch_args="--yolo --accept-hooks",
    ),
}

SPAWNABLE_FLAVORS = tuple(HARNESS_SPAWN)


def login_shell() -> str:
    """The user's login shell, the one a spawned tmux window starts."""
    shell = os.environ.get("SHELL")
    if shell:
        return shell
    try:
        import pwd

        return pwd.getpwuid(os.getuid()).pw_shell or "/bin/sh"
    except (ImportError, KeyError):
        return "/bin/sh"


@functools.lru_cache(maxsize=None)
def harness_accepts(binary: str, flag: str) -> bool:
    """Whether the installed harness parses `flag` (`binary flag --help` exits 0).

    Run through the user's login shell, so the binary is found the way the
    spawned pane will find it: a server started by launchd or systemd has a
    bare PATH without ~/.local/bin, where harnesses usually live. Cached for
    the server's lifetime; restart it after upgrading a harness.
    """
    try:
        out = subprocess.run(
            [login_shell(), "-lc", f"{shlex.quote(binary)} {shlex.quote(flag)} --help"],
            capture_output=True, text=True, timeout=20,
        )
    except (subprocess.SubprocessError, FileNotFoundError, OSError):
        return False
    return out.returncode == 0


def spawn_options() -> list[dict]:
    """The harness/model menu the dashboard offers, as plain data."""
    return [
        {"flavor": flavor, "models": spec.models}
        for flavor, spec in HARNESS_SPAWN.items()
    ]


def spawn_launch_command(flavor: str, model: str | None = None) -> str | None:
    """Build the shell command that launches a harness in a fresh pane.

    Returns None for an unspawnable flavor. A model is only honored when it is
    one of the harness's known models; otherwise (including "default") no
    model flag is passed. It is shell-quoted so patterns like
    `~anthropic/claude-opus-latest` are passed literally (no tilde expansion).
    """
    spec = HARNESS_SPAWN.get(flavor)
    if spec is None:
        return None
    parts = [spec.binary]
    if spec.startup_args:
        parts.append(spec.startup_args)
    if model and model in spec.models:
        parts.append(f"{spec.model_flag} {shlex.quote(model)}")
    if spec.launch_args:
        parts.append(spec.launch_args)
    parts.extend(f for f in spec.if_supported if harness_accepts(spec.binary, f))
    return " ".join(parts)


def spawn_window(
    session: str = AGENTS_SESSION, command: str | None = None
) -> tuple[Created | None, str | None]:
    """Create a detached tmux window (and session if needed) and optionally
    launch a command in it. Returns (Created, None) or (None, error) when
    tmux answered; raises Uncertain when it did not report back.

    The window starts in the home directory. Without -c, tmux uses the
    session's directory, which for a session the node created is the
    node's own: `/` under launchd.
    """
    fmt = "#{pane_id}\t#S:#I.#P\t#{pid}:#{start_time}"
    home = str(Path.home())
    try:
        has = subprocess.run(
            ["tmux", "has-session", "-t", session],
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (subprocess.SubprocessError, FileNotFoundError) as e:
        return None, _error_text(e)
    try:
        if has.returncode != 0:
            out = subprocess.run(
                ["tmux", "new-session", "-d", "-s", session, "-c", home,
                 "-x", "220", "-y", "50", "-P", "-F", fmt],
                capture_output=True,
                text=True,
                check=True,
                timeout=5,
            )
        else:
            out = subprocess.run(
                ["tmux", "new-window", "-d", "-t", session, "-c", home, "-P", "-F", fmt],
                capture_output=True,
                text=True,
                check=True,
                timeout=5,
            )
    except subprocess.CalledProcessError as e:
        return None, _error_text(e)  # tmux answered: nothing was created
    except (subprocess.SubprocessError, FileNotFoundError) as e:
        raise Uncertain(f"window creation did not report back: {_error_text(e)}") from e
    pane, _, rest = out.stdout.strip().partition("\t")
    label, _, server = rest.partition("\t")
    if not pane.startswith("%") or not server:
        return None, "tmux did not report the new pane"
    created = Created(pane, label or pane, server)
    if command:
        try:
            subprocess.run(
                ["tmux", "send-keys", "-t", pane, command, "C-m"],
                capture_output=True,
                text=True,
                check=True,
                timeout=5,
            )
        except (subprocess.SubprocessError, FileNotFoundError) as e:
            # The window exists; whether the harness started in it is unknown.
            raise Uncertain(f"launch command did not report back: {_error_text(e)}", created) from e
    return created, None


def _tmux_out(*args: str, timeout: float = 2) -> str | None:
    try:
        out = subprocess.run(
            ["tmux", *args], capture_output=True, text=True, check=True, timeout=timeout
        )
    except (subprocess.SubprocessError, FileNotFoundError):
        return None
    return out.stdout


def ancestors(pid: int | None = None) -> list[tuple[int, str]]:
    """(pid, command) for a process and its parents, nearest first; [] without ps."""
    try:
        ps = subprocess.run(
            ["ps", "-A", "-o", "pid=,ppid=,command="], capture_output=True, text=True, check=True, timeout=5
        )
    except (subprocess.SubprocessError, FileNotFoundError, OSError):
        return []
    table: dict[int, tuple[int, str]] = {}
    for line in ps.stdout.splitlines():
        fields = line.split(None, 2)
        if len(fields) >= 2 and fields[0].isdigit() and fields[1].isdigit():
            table[int(fields[0])] = (int(fields[1]), fields[2] if len(fields) > 2 else "")
    chain, current = [], os.getpid() if pid is None else pid
    for _ in range(256):
        if current not in table:
            break
        ppid, command = table[current]
        chain.append((current, command))
        if current <= 1:
            break
        current = ppid
    return chain


def pane_process(pane: str) -> int | None:
    """The pid of the process tmux started in `pane` (usually a shell), or None."""
    out = _tmux_out("display-message", "-p", "-t", pane, "#{pane_pid}")
    try:
        return int((out or "").strip())
    except ValueError:
        return None


def process_in_pane(pane: str, pid: int | None = None) -> bool | None:
    """Whether process `pid` (default: this one) runs inside tmux pane `pane`.

    True when the pane's own process is one of its ancestors. False means the
    pane id came from somewhere else: an inherited TMUX_PANE (Codex 0.158+
    runs every session's commands in one shared daemon that kept the TMUX_PANE
    of the pane that started it), or, with no TMUX_PANE at all, tmux's guess
    of the active pane. None when it can't be told (no tmux, no ps).
    """
    pane_pid = pane_process(pane)
    if pane_pid is None:
        # A reachable server with no matching pane is negative evidence,
        # not an unverifiable caller (e.g. a daemon holding a dead pane id).
        return False if server_id() is not None else None
    try:
        ps = subprocess.run(
            ["ps", "-A", "-o", "pid=,ppid="], capture_output=True, text=True, check=True, timeout=5
        )
    except (subprocess.SubprocessError, FileNotFoundError, OSError):
        return None
    parents = {}
    for line in ps.stdout.splitlines():
        fields = line.split()
        if len(fields) == 2 and fields[0].isdigit() and fields[1].isdigit():
            parents[int(fields[0])] = int(fields[1])
    current = os.getpid() if pid is None else pid
    for _ in range(256):  # a cycle or a very deep tree ends the walk
        if current == pane_pid:
            return True
        if current not in parents or current <= 1:
            return False
        current = parents[current]
    return False


def server_id() -> str | None:
    """Identify the running tmux server ("pid:start_time"), or None without tmux.

    Pane ids restart from %0 when the tmux server restarts, so an id is only
    meaningful together with the server that issued it.
    """
    out = _tmux_out("display-message", "-p", "#{pid}:#{start_time}")
    val = (out or "").strip()
    return val or None


def server_start_time() -> float | None:
    """When the running tmux server started, or None without tmux."""
    sid = server_id()
    try:
        return float(sid.split(":")[1]) if sid else None
    except (IndexError, ValueError):
        return None


def resolve_pane(target: str) -> tuple[str, str] | None:
    """(pane id, session:window.pane label) for any tmux target, or None."""
    out = _tmux_out("display-message", "-p", "-t", target, "#{pane_id}\t#S:#I.#P")
    pane_id, _, label = (out or "").strip().partition("\t")
    return (pane_id, label) if pane_id.startswith("%") else None


def pane_table() -> dict[str, dict[str, str]]:
    """Every pane by id: its label, foreground command, and title. {} without tmux."""
    out = _tmux_out(
        "list-panes", "-a", "-F",
        "#{pane_id}\t#S:#I.#P\t#{pane_current_command}\t#{pane_title}\t#{@agent_swarm}",
    )
    table = {}
    for line in (out or "").splitlines():
        pane_id, label, command, title, handle = (line.split("\t") + ["", "", "", ""])[:5]
        if pane_id:
            table[pane_id] = {"label": label, "command": command.strip(), "title": title}
            if handle:
                table[pane_id]["agent_swarm"] = handle
    return table


def list_panes() -> set[str]:
    """Return all live pane ids (%N); empty set if tmux is unavailable."""
    return set(pane_table())


# A pane whose foreground process is one of these has no agent in it: the
# harness exited (typically a reboot) and tmux restored, or fell back to, a
# plain shell. Delivering there would type the message into the shell.
SHELL_COMMANDS = {"bash", "zsh", "sh", "dash", "fish", "ksh", "tcsh", "csh"}


def pane_commands() -> dict[str, str]:
    """Map every live pane id to its foreground command; {} if tmux is unavailable."""
    return {pane_id: row["command"] for pane_id, row in pane_table().items()}


def live_agent_panes() -> set[str]:
    """Panes that exist and are running something other than a bare shell."""
    return {pane for pane, cmd in pane_commands().items() if cmd not in SHELL_COMMANDS}


def offline_reason(
    pane: str, existing: set[str], live: set[str], stale: str | None = None
) -> str | None:
    """Why a registered pane can't take a message right now, or None if it can.

    `stale` explains why the stored pane id can't be trusted at all (it came
    from an earlier tmux server, or the agent's pane could not be verified);
    any pane that has that id now belongs to someone else.
    """
    if stale:
        return f"recipient offline: {stale}; the agent must register again"
    if pane not in existing:
        return f"recipient offline: pane {pane} no longer exists"
    if pane not in live:
        return f"recipient offline: pane {pane} is a bare shell (agent not running)"
    return None


def kill_pane(pane: str) -> tuple[bool, str | None]:
    """Kill a tmux pane. Returns (ok, error_message_or_None) when tmux
    answered; raises Uncertain when it did not, since the pane may be gone."""
    try:
        subprocess.run(
            ["tmux", "kill-pane", "-t", pane],
            capture_output=True,
            text=True,
            check=True,
            timeout=3,
        )
    except subprocess.CalledProcessError as e:
        return False, _error_text(e)
    except (subprocess.SubprocessError, FileNotFoundError) as e:
        raise Uncertain(f"kill did not report back: {_error_text(e)}") from e
    return True, None


# Keys the dashboard's terminal panel can press in an agent's pane, as tmux
# key names: enough to drive a harness's menus, such as Codex's /model picker.
TERMINAL_KEYS = ("Escape", "Up", "Down", "Enter", "Tab")


def send_key(pane: str, key: str) -> tuple[bool, str | None]:
    """Press one key in a pane. Returns (ok, error) when tmux answered;
    raises Uncertain when it did not, since the key may have landed."""
    try:
        subprocess.run(
            ["tmux", "send-keys", "-t", pane, key],
            capture_output=True, text=True, check=True, timeout=3,
        )
    except subprocess.CalledProcessError as e:
        return False, _error_text(e)
    except (subprocess.SubprocessError, FileNotFoundError) as e:
        raise Uncertain(f"key did not report back: {_error_text(e)}") from e
    return True, None


def capture_pane(pane: str) -> tuple[str | None, str | None]:
    """Return the pane's visible screen as text. Returns (text, error_or_None)."""
    try:
        out = subprocess.run(
            ["tmux", "capture-pane", "-p", "-J", "-t", pane],
            capture_output=True,
            text=True,
            check=True,
            timeout=3,
        )
    except subprocess.CalledProcessError as e:
        return None, e.stderr.strip() or str(e)
    except (subprocess.SubprocessError, FileNotFoundError) as e:
        return None, str(e)
    return out.stdout, None


def format_message(
    sender: str, context: str | None, content: str, *, owner_reply_reminder: bool = True,
) -> str:
    """Compose the inbound message body that lands in the recipient's pane."""
    head = f"[agent-msg from {sender}"
    if context:
        head += f" · {context}"
    head += "] "
    if sender == "owner" and owner_reply_reminder:
        head += (
            'Reply via `agent-swarm send --to owner --message "..."` '
            'so it appears on the dashboard.\n\n'
        )
    return head + content
