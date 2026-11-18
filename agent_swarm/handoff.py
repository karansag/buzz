"""Switch an agent to another harness, keeping its conversation.

The owner runs out of credits on one harness and wants the agent to carry on
in another. Buzz reads the source harness's own transcript, turns it into
plain turns (tool calls and results become short text notes), and writes a
*new* resumable session in the target harness's format. The source file is
only ever read: it is the way back. The pane is then respawned and the target
harness launched with its resume flag, so the agent keeps its handle, pane and
conversation.

What travels: the user and assistant turns, in order. What does not: thinking
blocks, tool-call structure, attachments, and any harness-specific state. A
large transcript is clipped per turn and then trimmed from the oldest end to
fit a character budget, so a resume never starts by blowing the target
model's context.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from . import restore, tmux

# Harnesses this module can move an agent to (and read transcripts from).
FLAVORS = ("claude", "codex", "pi", "agy")
# Harnesses whose own session files are not safe to hand-write yet. A switch
# into one of these writes the conversation to a markdown file in the agent's
# folder and starts a fresh session that is told to read it: the conversation
# still travels, the harness format is left alone. Codex's rollout files are
# written by its app server and `codex resume <id>` did not pick up a
# hand-written one in testing (it started empty), so it takes this route.
# The Antigravity CLI keeps conversations in its own SQLite databases.
SEED_TARGETS = frozenset({"codex", "agy"})

# Roughly 4 characters per token, so this is about 37k tokens of conversation
# plus the target's own system prompt and instructions.
DEFAULT_MAX_CHARS = 150_000
# One turn of prose: keep it long enough to hold a plan or a diff summary.
TURN_CLIP = 8_000
# One tool call or result: these are the bulk of a transcript and the least
# useful verbatim.
NOTE_CLIP = 1_200


# Handoff files live with Buzz's own data, not in the agent's folder: a file
# dropped into a repo shows up in `git status` and in other agents' `git add`.
def handoff_dir() -> Path:
    return Path(os.environ.get("AGENT_SWARM_HANDOFF_DIR")
                or (Path.home() / ".agent-swarm" / "handoffs"))


def handoff_path(handle: str, stamp: str) -> Path:
    return handoff_dir() / f"{handle}-{stamp}.md"


def _stamp(now: float) -> str:
    return datetime.fromtimestamp(now, timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _now() -> float:
    return datetime.now(timezone.utc).timestamp()


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


@dataclass(frozen=True)
class Turn:
    role: str  # "user" or "assistant"
    text: str


@dataclass
class Switch:
    """Everything a switch will do, built before anything is written."""

    handle: str
    to: str
    model: str | None
    from_flavor: str = ""
    from_agent_id: str | None = None
    source_path: Path | None = None
    cwd: str | None = None
    pane: str | None = None
    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    session_path: Path | None = None
    command: str | None = None
    turns: int = 0
    dropped: int = 0
    chars: int = 0
    route: str = "native"
    skip: str | None = None

    def describe(self) -> dict:
        return {
            "handle": self.handle,
            "to": self.to,
            "model": self.model,
            "from_flavor": self.from_flavor,
            "from_agent_id": self.from_agent_id,
            "source_path": str(self.source_path) if self.source_path else None,
            "cwd": self.cwd,
            "pane": self.pane,
            "session_id": self.session_id,
            "session_path": str(self.session_path) if self.session_path else None,
            "command": self.command,
            "turns": self.turns,
            "dropped": self.dropped,
            "chars": self.chars,
            "route": self.route,
            "skip": self.skip,
        }


# ---------- where each harness keeps sessions ----------


def claude_home() -> Path:
    return Path(os.environ.get("CLAUDE_CONFIG_DIR") or (Path.home() / ".claude"))


def codex_home() -> Path:
    return Path(os.environ.get("CODEX_HOME") or (Path.home() / ".codex"))


def pi_home() -> Path:
    return Path(os.environ.get("PI_CODING_AGENT_DIR") or (Path.home() / ".pi" / "agent"))


def agy_home() -> Path:
    """The Antigravity CLI's data folder (it tells its commands as ANTIGRAVITY_APP_DATA_DIR)."""
    return Path(os.environ.get("ANTIGRAVITY_APP_DATA_DIR")
                or (Path.home() / ".gemini" / "antigravity-cli"))


def claude_project_dir(cwd: str) -> str:
    """Claude's directory name for a working directory: /home/karan → -home-karan."""
    return "-" + str(Path(cwd)).lstrip("/").replace("/", "-")


def pi_session_dir(cwd: str, agent_dir: Path | None = None) -> Path:
    """Pi's session directory for a cwd, which mirrors Pi's own encoding."""
    root = agent_dir or pi_home()
    safe = "--" + re.sub(r"[/\\:]", "-", str(Path(cwd)).lstrip("/")) + "--"
    return root / "sessions" / safe


def find_source(flavor: str, agent_id: str | None) -> Path | None:
    """The transcript a running agent's harness wrote, by its session id."""
    if not agent_id:
        return None
    if flavor == "claude":
        root = claude_home() / "projects"
        if not root.is_dir():
            return None
        for project in root.iterdir():
            candidate = project / f"{agent_id}.jsonl"
            if candidate.is_file():
                return candidate
        return None
    if flavor == "codex":
        root = codex_home() / "sessions"
        if not root.is_dir():
            return None
        for candidate in root.rglob(f"*{agent_id}*.jsonl"):
            return candidate
        return None
    if flavor == "pi":
        root = pi_home() / "sessions"
        if not root.is_dir():
            return None
        for candidate in root.rglob(f"*{agent_id}.jsonl"):
            return candidate
        return None
    if flavor == "agy":
        # agy keeps the conversation in conversations/<id>.db and writes a
        # readable copy, step by step, under brain/<id>/.
        if "/" in agent_id or agent_id.startswith("."):
            return None
        candidate = agy_home() / "brain" / agent_id / ".system_generated" / "logs" / "transcript.jsonl"
        return candidate if candidate.is_file() else None
    return None


# ---------- reading: one harness's transcript into plain turns ----------


def _clip(text: str, limit: int) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + f"…[clipped {len(text) - limit} chars]"


def _json(value) -> str:
    try:
        return json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(value)


def _tool_note(name: str, arguments) -> str:
    return _clip(f"[called {name} {_json(arguments)}]", NOTE_CLIP)


def _result_note(output) -> str:
    if isinstance(output, list):
        output = " ".join(
            part.get("text", "") for part in output
            if isinstance(part, dict) and isinstance(part.get("text"), str)
        )
    return _clip(f"[tool result] {output}", NOTE_CLIP)


def _claude_turn(record: dict) -> Turn | None:
    kind = record.get("type")
    if kind not in ("user", "assistant") or record.get("isMeta"):
        return None
    message = record.get("message") or {}
    content = message.get("content")
    parts: list[str] = []
    if isinstance(content, str):
        parts.append(content)
    elif isinstance(content, list):
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text":
                parts.append(block.get("text") or "")
            elif block.get("type") == "tool_use":
                parts.append(_tool_note(block.get("name") or "?", block.get("input")))
            elif block.get("type") == "tool_result":
                parts.append(_result_note(block.get("content")))
            # thinking, redacted_thinking and images are dropped.
    text = "\n".join(part for part in parts if part and part.strip())
    return Turn(kind, _clip(text, TURN_CLIP)) if text.strip() else None


def _codex_turn(record: dict) -> Turn | None:
    if record.get("type") != "response_item":
        return None
    payload = record.get("payload") or {}
    kind = payload.get("type")
    if kind == "message":
        role = payload.get("role")
        if role not in ("user", "assistant"):
            return None  # developer/system instructions are not the conversation
        text = "\n".join(
            part.get("text") or "" for part in payload.get("content") or []
            if isinstance(part, dict) and isinstance(part.get("text"), str)
        )
        return Turn(role, _clip(text, TURN_CLIP)) if text.strip() else None
    if kind in ("function_call", "custom_tool_call"):
        return Turn("assistant", _tool_note(payload.get("name") or "?", payload.get("arguments")))
    if kind in ("function_call_output", "custom_tool_call_output"):
        return Turn("user", _result_note(payload.get("output")))
    return None


def _pi_turn(record: dict) -> Turn | None:
    if record.get("type") != "message":
        return None
    message = record.get("message") or {}
    role = message.get("role")
    # Pi's tool output is its own role, not a user message.
    if role == "toolResult":
        text = _pi_text(message.get("content"))
        return Turn("user", _result_note(text)) if text.strip() else None
    if role not in ("user", "assistant"):
        return None
    text = _pi_text(message.get("content"))
    return Turn(role, _clip(text, TURN_CLIP)) if text.strip() else None


def _pi_text(content) -> str:
    if isinstance(content, str):
        return content
    parts = []
    for block in content or []:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "text":
            parts.append(block.get("text") or "")
        elif block.get("type") == "toolCall":
            parts.append(_tool_note(block.get("name") or "?", block.get("arguments")))
    return "\n".join(part for part in parts if part and part.strip())


_AGY_REQUEST = re.compile(r"<USER_REQUEST>\n?(.*?)\n?</USER_REQUEST>", re.DOTALL)


def _agy_turn(record: dict) -> Turn | None:
    """One step of an Antigravity transcript.jsonl.

    USER_INPUT wraps the typed text in <USER_REQUEST> next to metadata the
    harness adds (time, settings changes); PLANNER_RESPONSE is the model's
    reply and its tool calls; GENERIC steps from the model are tool results.
    System messages are dropped.
    """
    kind, content = record.get("type"), record.get("content")
    if kind == "USER_INPUT" and record.get("source") == "USER_EXPLICIT":
        found = _AGY_REQUEST.findall(content if isinstance(content, str) else "")
        text = "\n".join(part.strip() for part in found)
        return Turn("user", _clip(text, TURN_CLIP)) if text.strip() else None
    if kind == "PLANNER_RESPONSE":
        parts = [content] if isinstance(content, str) else []
        for call in record.get("tool_calls") or []:
            if isinstance(call, dict):
                parts.append(_tool_note(call.get("name") or "?", call.get("args")))
        text = "\n".join(part for part in parts if part and part.strip())
        return Turn("assistant", _clip(text, TURN_CLIP)) if text.strip() else None
    if kind == "GENERIC" and record.get("source") == "MODEL" and isinstance(content, str) and content.strip():
        return Turn("assistant", _result_note(content))
    return None


READERS = {"claude": _claude_turn, "codex": _codex_turn, "pi": _pi_turn, "agy": _agy_turn}


def read_turns(flavor: str, path: Path) -> list[Turn]:
    """The conversation in one harness's transcript, as plain turns."""
    reader = READERS.get(flavor)
    if reader is None:
        raise ValueError(f"cannot read {flavor} transcripts")
    turns: list[Turn] = []
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except ValueError:
                continue
            if not isinstance(record, dict):
                continue
            turn = reader(record)
            if turn is not None:
                turns.append(turn)
    return turns


def fit(turns: list[Turn], max_chars: int) -> tuple[list[Turn], int]:
    """Trim the oldest turns until the conversation fits `max_chars`.

    Returns the kept turns and how many were dropped. The most recent turn is
    always kept: a handoff with no last message is not a handoff.
    """
    total = sum(len(turn.text) for turn in turns)
    dropped = 0
    while total > max_chars and len(turns) - dropped > 1:
        total -= len(turns[dropped].text)
        dropped += 1
    return turns[dropped:], dropped


# ---------- writing: plain turns into the target harness's format ----------


def _token(n: int = 8) -> str:
    return uuid.uuid4().hex[:n]


def write_session(flavor: str, turns: list[Turn], *, cwd: str, model: str | None,
                  session_id: str, now: float | None = None) -> Path:
    """Write a new resumable session for `flavor`; returns its path.

    The file is created next to the harness's own sessions, so its resume
    command finds it by id. Nothing here reads or writes the source session.
    """
    now = now if now is not None else _now()
    if flavor == "claude":
        return _write_claude(turns, cwd=cwd, model=model, session_id=session_id, now=now)
    if flavor == "codex":
        return _write_codex(turns, cwd=cwd, model=model, session_id=session_id, now=now)
    if flavor == "pi":
        return _write_pi(turns, cwd=cwd, model=model, session_id=session_id, now=now)
    raise ValueError(f"cannot write {flavor} sessions")


def _write_lines(path: Path, lines: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "".join(json.dumps(line, ensure_ascii=False) + "\n" for line in lines)
    # 0o600: a transcript is as private as the harness's own.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(body)
    return path


def _write_claude(turns, *, cwd, model, session_id, now) -> Path:
    path = claude_home() / "projects" / claude_project_dir(cwd) / f"{session_id}.jsonl"
    lines: list[dict] = []
    parent = None
    for index, turn in enumerate(turns):
        uid = str(uuid.uuid4())
        if turn.role == "assistant":
            message = {
                "id": f"msg_{uuid.uuid4().hex[:24]}",
                "type": "message",
                "role": "assistant",
                "content": [{"type": "text", "text": turn.text}],
                "stop_reason": "end_turn",
                "stop_sequence": None,
                "usage": {"input_tokens": 0, "output_tokens": 0},
            }
            # Only name a model when one was asked for: Claude warns and swaps
            # when a written session names a model this version does not know.
            if model:
                message["model"] = model
        else:
            message = {"role": "user", "content": turn.text}
        lines.append({
            "parentUuid": parent,
            "isSidechain": False,
            "type": turn.role,
            "message": message,
            "uuid": uid,
            "timestamp": _iso(now + index / 1000),
            "userType": "external",
            "cwd": cwd,
            "sessionId": session_id,
            "version": "2.1.0",
        })
        parent = uid
    return _write_lines(path, lines)


def _write_codex(turns, *, cwd, model, session_id, now) -> Path:
    stamp = datetime.fromtimestamp(now, timezone.utc)
    folder = codex_home() / "sessions" / f"{stamp:%Y}" / f"{stamp:%m}" / f"{stamp:%d}"
    name = f"rollout-{stamp:%Y-%m-%dT%H-%M-%S}-{session_id}.jsonl"
    meta = {
        "session_id": session_id,
        "id": session_id,
        "timestamp": _iso(now),
        "cwd": cwd,
        "originator": "codex-tui",
        "cli_version": "unknown",
        "source": "cli",
        "thread_source": "user",
        "model_provider": "openai",
        "history_mode": "paginated",
    }
    lines: list[dict] = [{"timestamp": _iso(now), "ordinal": 0, "type": "session_meta", "payload": meta}]
    ordinal = 1
    for index, turn in enumerate(turns):
        content_type = "input_text" if turn.role == "user" else "output_text"
        lines.append({
            "timestamp": _iso(now + index / 1000),
            "ordinal": ordinal,
            "type": "response_item",
            "payload": {
                "type": "message",
                "id": f"msg_{uuid.uuid4()}",
                "role": turn.role,
                "content": [{"type": content_type, "text": turn.text}],
            },
        })
        ordinal += 1
    if model:
        lines.append({
            "timestamp": _iso(now),
            "ordinal": ordinal,
            "type": "turn_context",
            "payload": {"cwd": cwd, "model": model},
        })
    return _write_lines(folder / name, lines)


def _write_pi(turns, *, cwd, model, session_id, now) -> Path:
    stamp = datetime.fromtimestamp(now, timezone.utc)
    folder = pi_session_dir(cwd)
    name = f"{stamp:%Y-%m-%dT%H-%M-%S}-{int(now * 1000) % 1000:03d}Z_{session_id}.jsonl"
    lines: list[dict] = [{
        "type": "session",
        "version": 3,
        "id": session_id,
        "timestamp": _iso(now),
        "cwd": cwd,
    }]
    if model:
        lines.append({
            "type": "model_change",
            "id": _token(),
            "parentId": None,
            "timestamp": _iso(now),
            "provider": model.split("/")[0] if "/" in model else "",
            "modelId": model,
        })
    parent = None
    for index, turn in enumerate(turns):
        entry = _token()
        stamp = now + index / 1000
        message: dict = {
            "role": turn.role,
            "content": [{"type": "text", "text": turn.text}],
            "timestamp": int(stamp * 1000),
        }
        if turn.role == "assistant":
            # Pi's footer totals usage from every assistant turn, so a turn
            # without one crashes the resumed UI.
            message.update({
                "api": "handoff",
                "provider": "handoff",
                "model": model or "unknown",
                "usage": {
                    "input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0,
                    "reasoning": 0, "totalTokens": 0,
                    "cost": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0, "total": 0},
                },
                "stopReason": "endTurn",
                "rawStopReason": None,
                "responseId": f"handoff-{entry}",
                "durationMs": 0,
                "thinkingLevel": None,
            })
        lines.append({
            "type": "message",
            "id": entry,
            "parentId": parent,
            "timestamp": _iso(stamp),
            "message": message,
        })
        parent = entry
    return _write_lines(folder / name, lines)


# ---------- planning and applying ----------


def preamble(switch: Switch) -> Turn:
    from_note = f" from {switch.from_flavor}" if switch.from_flavor else ""
    dropped = (f" The oldest {switch.dropped} turns were left out to fit this "
               "session's context; ask if you need them.") if switch.dropped else ""
    return Turn("user", (
        f"[handoff] This conversation continues as the agent {switch.handle}, moved{from_note} to "
        f"{switch.to} with `buzz switch`. The turns below are its earlier conversation, in order; "
        f"tool calls and their results are summarised as bracketed notes.{dropped} "
        "Carry on from the last message as if you had been in this conversation all along."
    ))


def plan(recipient: dict, to: str, model: str | None = None, *,
         max_chars: int = DEFAULT_MAX_CHARS, force: bool = False) -> Switch:
    """What a switch would do, without writing anything.

    `recipient` is a hub row: user_id, flavor, agent_id, tmux_pane, node,
    tmux_server, cwd. A switch is refused with `skip` set, never by raising,
    so a dry run can explain every case.
    """
    item = Switch(handle=recipient.get("user_id") or "?", to=to, model=model,
                  from_flavor=recipient.get("flavor") or "",
                  from_agent_id=recipient.get("agent_id"), cwd=recipient.get("cwd"),
                  pane=recipient.get("tmux_pane"))
    if to not in FLAVORS:
        item.skip = f"{to} is not a harness this can switch to ({', '.join(FLAVORS)})"
    elif not item.from_flavor:
        item.skip = "its harness is unknown, so there is no transcript to carry over"
    elif item.from_flavor == to and not force:
        item.skip = f"it is already running {to} (--force rewrites the session anyway)"
    elif not item.from_agent_id:
        item.skip = "it has no session id, so its conversation cannot be found"
    elif not item.cwd:
        item.skip = "the hub does not know which folder it runs in"
    else:
        source = find_source(item.from_flavor, item.from_agent_id)
        if source is None:
            item.skip = f"no {item.from_flavor} transcript for session {item.from_agent_id}"
        else:
            item.source_path = source
            kept, dropped = fit(read_turns(item.from_flavor, source), max_chars)
            item.dropped, item.turns = dropped, len(kept)
            item.chars = sum(len(turn.text) for turn in kept)
            if to in SEED_TARGETS:
                item.route = "seed"
                item.session_path = handoff_path(item.handle, _stamp(_now()))
                item.command = seed_command(item, model)
            else:
                item.command = restore.resume_command({"flavor": to, "agent_id": item.session_id, "model": model})
                item.session_path = target_path(to, item.cwd, item.session_id)
    return item


def seed_command(item: Switch, model: str | None) -> str | None:
    """Launch the target harness with one prompt: read the handoff file and go."""
    launch = tmux.spawn_launch_command(item.to, model)
    if not launch or item.session_path is None:
        return None
    prompt = (f"This conversation was handed over from another harness. Read "
              f"{item.session_path} and carry on from its last message as if you had been in "
              f"it all along. Do not summarise it back to me.")
    # agy takes no bare prompt; -i runs one and stays interactive.
    flag = "-i " if item.to == "agy" else ""
    return f"{launch} {flag}{shlex.quote(prompt)}"


def target_path(flavor: str, cwd: str, session_id: str = "SESSION") -> Path | None:
    """Where a new session would live for `flavor`, for a dry run to show."""
    if flavor == "claude":
        return claude_home() / "projects" / claude_project_dir(cwd) / f"{session_id}.jsonl"
    if flavor == "codex":
        now = datetime.now(timezone.utc)
        return (codex_home() / "sessions" / f"{now:%Y}" / f"{now:%m}" / f"{now:%d}"
                / f"rollout-{now:%Y-%m-%dT%H-%M-%S}-{session_id}.jsonl")
    if flavor == "pi":
        now = datetime.now(timezone.utc)
        return pi_session_dir(cwd) / f"{now:%Y-%m-%dT%H-%M-%S}-000Z_{session_id}.jsonl"
    return None


def write(item: Switch, max_chars: int = DEFAULT_MAX_CHARS) -> Path:
    """Write the handoff session and return its path. Reads the source only."""
    if item.skip or item.source_path is None or not item.cwd:
        raise ValueError(item.skip or "nothing to write")
    turns, dropped = fit(read_turns(item.from_flavor, item.source_path), max_chars)
    item.dropped, item.turns = dropped, len(turns)
    with_preamble = [preamble(item), *turns]
    item.chars = sum(len(turn.text) for turn in with_preamble)
    if item.route == "seed":
        path = item.session_path or handoff_path(item.handle, _stamp(_now()))
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        body = "\n\n".join(f"**{turn.role}**\n\n{turn.text}" for turn in with_preamble)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(body + "\n")
        item.session_path = path
        return path
    item.session_path = write_session(
        item.to, with_preamble, cwd=item.cwd, model=item.model,
        session_id=item.session_id,
    )
    return item.session_path


def apply(item: Switch, own_pane: str | None = None) -> str | None:
    """Write the session, respawn the pane and launch the target harness.

    Returns an error string, or None when the launch was typed into the pane.
    The caller registers the new session id and flavor; this only touches the
    pane and the files.
    """
    if item.skip:
        return item.skip
    if not item.command:
        return f"no launch command for {item.to}"
    try:
        write(item)
    except (OSError, ValueError) as error:
        return f"could not write the {item.to} session: {error}"
    pane = item.pane
    if not pane:
        return "no pane to switch"
    respawn = tmux.respawn_pane(pane, item.cwd)
    if not respawn[0]:
        return f"could not respawn the pane: {respawn[1]}"
    line = f"cd {_quote(item.cwd)} && {item.command}"
    typed = tmux.type_line(pane, line)
    if not typed[0]:
        return f"could not launch {item.to}: {typed[1]}"
    return None


def _quote(text: str) -> str:
    return shlex.quote(text)
