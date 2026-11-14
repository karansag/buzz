"""Agent activity classification for the dashboard monitor.

Pure functions plus one registry-updating step function, so tests never
need the monitor loop or tmux. The server's monitor loop feeds captures
in as Observations and records the returned Notifications.
"""

from __future__ import annotations

import colorsys
import hashlib
import re
from typing import NamedTuple


class Observation(NamedTuple):
    user_id: str
    flavor: str | None
    pane_alive: bool
    capture: str | None  # None means the capture failed this tick
    # The same screen with its SGR color codes, when the node sent them.
    # Only the error check reads it; everything else reads `capture`.
    colored: str | None = None


class Notification(NamedTuple):
    user_id: str
    detail: str


def snapshot_hash(text: str) -> str:
    """sha1 of a capture with trailing whitespace stripped per line and overall.

    Cursor blinking and trailing spaces should not register as activity.
    """
    normalized = "\n".join(line.rstrip() for line in text.splitlines()).rstrip()
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()


def _compile(*patterns: str) -> list[re.Pattern]:
    return [re.compile(p) for p in patterns]


# What a live approval prompt looks like, per delivery flavor ("generic" is
# the fallback, also used by hermes and pi).
#
# `markers` decide that an agent is waiting: they are the answer options and
# footers only a live prompt draws, so an agent's own prose ("- Approve #9130.",
# "Do you want to land it?") never trips them. `questions` only choose the line
# shown as the reason, the prompt's question when it is on screen.
#
# Codex strings are from the 0.154 TUI; "Allow command?" is from older builds.
ATTENTION_PATTERNS: dict[str, dict[str, list[re.Pattern]]] = {
    "claude": {
        "markers": _compile(r"❯ 1\. Yes\b", r"\bEsc to cancel\b"),
        "questions": _compile(r"^\W*Do you want to .+\?\s*$"),
    },
    "codex": {
        "markers": _compile(
            r"^\W*\d\. Yes, proceed\b",
            r"tell Codex what to do differently",
            r"^\W*Allow command\?",
            # Its question form (request_user_input): "Question 1/2 (2
            # unanswered)" over options, footer "tab to add notes | ...".
            r"\btab to add notes\b",
            r"\bto navigate questions\b",
            r"^\W*Question \d+/\d+ \(\d+ unanswered\)",
        ),
        "questions": _compile(
            r"^\W*Would you like to .+\?\s*$",
            r"^\W*Do you want to proceed\?\s*$",
            r"^\W*Allow command\?",
        ),
        # The question itself is the line after this header.
        "question_headers": _compile(r"^\W*Question \d+/\d+\b"),
    },
    "generic": {
        "markers": _compile(r"\[y/N\]", r"\(y/n\)", r"(?i)\bpassword( for \S+)?:\s*$"),
        "questions": [],
    },
}


# A harness asking whether to trust its working folder, which it does
# before the agent starts. Claude draws "Accessing workspace:" over the
# folder, with "No, exit" selected; Codex asks "Trust this folder?" (older
# builds: "Do you trust the contents of this directory?"). Each title counts
# only with its answer on screen, so an agent quoting the words does not.
TRUST_PROMPTS = [
    ("Claude", re.compile(r"^\W*Accessing workspace:\s*$"), re.compile(r"Yes, I trust this folder")),
    ("Codex", re.compile(r"^\W*Trust this folder\?"), re.compile(r"Trust and continue")),
    ("Codex", re.compile(r"^\W*Do you trust the contents of this directory\?"), re.compile(r"\bYes, continue\b")),
]


def trust_prompt(capture: str) -> str | None:
    """What a workspace trust prompt on screen asks, or None.

    The prompt has to be answered by a person in the pane. A message pasted
    there would answer it: Claude's default is "No, exit", so the Enter that
    submits a message ends the agent.
    """
    lines = capture.splitlines()
    for harness, title, answer in TRUST_PROMPTS:
        at = next((i for i, line in enumerate(lines) if title.search(line)), None)
        if at is None or not any(answer.search(line) for line in lines[at:]):
            continue
        folder = next((line.strip() for line in lines[at + 1:] if line.strip()), "")
        if harness == "Claude" and folder.startswith("/"):
            return f"{harness}'s workspace trust prompt for {folder}"
        return f"{harness}'s workspace trust prompt"
    return None


def _attention_detail(flavor: str | None, capture: str) -> str | None:
    """If the screen shows a live prompt awaiting the operator, return the line
    to display (its question when visible, else the first marker line)."""
    if trust := trust_prompt(capture):
        return f"waiting at {trust}: answer it in the pane"
    patterns = ATTENTION_PATTERNS.get(
        (flavor or "generic").lower(), ATTENTION_PATTERNS["generic"]
    )
    lines = capture.splitlines()
    marker = next(
        (line for line in lines if any(p.search(line) for p in patterns["markers"])),
        None,
    )
    if marker is None:
        return None
    question = next(
        (line for line in lines if any(p.search(line) for p in patterns["questions"])),
        None,
    )
    if question is None:
        for i, line in enumerate(lines):
            if any(p.search(line) for p in patterns.get("question_headers", [])):
                question = next((l for l in lines[i + 1:] if l.strip()), None)
                break
    return (question or marker).strip()


# An agent stopped by an error: a usage limit, no credits, a failed API
# call, or lost auth. Every harness prints these in red near the bottom of
# the screen, and nothing else counts: red alone is also diffs and failing
# tool output, and the words alone are also prose and pasted messages.
ERROR_WORDS = re.compile(
    r"(?i)usage limit|limit reached|hit your\b.{0,30}\b(limit|budget)|out of (extra )?usage"
    r"|usage credits|credit balance|(no|more|out of|insufficient) credits"
    r"|quota|rate.?limit|too many requests|payment required|billing"
    r"|api error|invalid api key|unauthori[sz]ed|authentication (failed|error)"
    r"|/login\b|not logged in|oauth token|overloaded|connection error"
    r"|\berror\W{1,3}[45]\d\d\b"
)

# How far up from the bottom an error may sit and still be the agent's
# current state: below it there is room only for the harness's input box,
# footer and a queued message or two.
ERROR_WINDOW = 10

# The bullet each harness starts a reply with. One below the error means
# the agent answered after it, so the error is history.
REPLY_BULLETS = {
    "claude": re.compile(r"^\s*[●⏺] "),
    "codex": re.compile(r"^\s*• "),
}

_CSI = re.compile(r"\x1b\[([0-9;:?]*)([A-Za-z])")
_OTHER_ESCAPE = re.compile(r"\x1b(\][^\x07\x1b]*(\x07|\x1b\\)|[()][A-Za-z0-9]|[=>78])")


def strip_colors(text: str) -> str:
    """The screen as plain text: what `tmux capture-pane` gives without -e."""
    return _CSI.sub("", _OTHER_ESCAPE.sub("", text))


def _cube(n: int) -> tuple[int, int, int]:
    """RGB of xterm 256-color index n."""
    if n < 16:
        base = [(0, 0, 0), (205, 0, 0), (0, 205, 0), (205, 205, 0), (0, 0, 238), (205, 0, 205),
                (0, 205, 205), (229, 229, 229), (127, 127, 127), (255, 0, 0), (0, 255, 0),
                (255, 255, 0), (92, 92, 255), (255, 0, 255), (0, 255, 255), (255, 255, 255)]
        return base[n]
    if n < 232:
        n -= 16
        steps = [0, 95, 135, 175, 215, 255]
        return steps[n // 36], steps[n // 6 % 6], steps[n % 6]
    v = 8 + (n - 232) * 10
    return v, v, v


def _is_red(rgb: tuple[int, int, int]) -> bool:
    """Red or pink-red, not orange, brown or grey: the error colors of
    Claude (255,107,128 and others), Codex (ANSI red) and Pi (234,127,129)."""
    h, s, v = colorsys.rgb_to_hsv(*(c / 255 for c in rgb))
    return (h >= 340 / 360 or h <= 15 / 360) and s >= 0.35 and v >= 0.4


def _red_lines(colored: str) -> list[tuple[str, bool]]:
    """Each line's plain text, and whether any visible character is red.

    tmux carries the color over line ends, so the state runs across lines.
    """
    out: list[tuple[str, bool]] = []
    red = False
    for line in colored.split("\n"):
        text, any_red, at = [], False, 0
        for m in _CSI.finditer(line):
            chunk = _OTHER_ESCAPE.sub("", line[at:m.start()])
            text.append(chunk)
            any_red = any_red or (red and bool(chunk.strip()))
            at = m.end()
            if m.group(2) != "m":
                continue
            # A color given with colons ("38:2::r:g:b", "38:5:n") is one
            # group with its own fields; with semicolons it spans several.
            params: list = []
            for group in m.group(1).split(";"):
                if ":" in group:
                    sub = [int(p) if p.isdigit() else 0 for p in group.split(":")]
                    if sub[0] in (38, 48, 58) and len(sub) >= 3:
                        rgb = sub[1] == 2 and len(sub) >= 5
                        sub = [sub[0], sub[1], *(sub[-3:] if rgb else sub[-1:])]
                    params.extend(sub)
                else:
                    params.append(int(group) if group.isdigit() else 0)
            i = 0
            while i < len(params):
                p = params[i]
                if p in (0, 39):
                    red = False
                elif 30 <= p <= 37 or 90 <= p <= 97:
                    red = p in (31, 91)
                elif p == 38 and i + 2 < len(params) and params[i + 1] == 5:
                    red = _is_red(_cube(params[i + 2] % 256))
                    i += 2
                elif p == 38 and i + 4 < len(params) and params[i + 1] == 2:
                    red = _is_red(tuple(min(c, 255) for c in params[i + 2:i + 5]))
                    i += 4
                elif p in (48, 58) and i + 1 < len(params):
                    i += 2 if params[i + 1] == 5 else 4 if params[i + 1] == 2 else 0
                i += 1
        chunk = _OTHER_ESCAPE.sub("", line[at:])
        text.append(chunk)
        any_red = any_red or (red and bool(chunk.strip()))
        out.append(("".join(text), any_red))
    return out


def error_detail(flavor: str | None, colored: str) -> str | None:
    """The error the agent stopped on, or None: the last red line near the
    bottom that names an error, with the red lines it wraps across."""
    lines = _red_lines(colored)
    shown = [i for i, (t, _) in enumerate(lines) if t.strip()]
    reply = REPLY_BULLETS.get((flavor or "").lower())
    for i in reversed(shown[-ERROR_WINDOW - 1:]):
        text, red = lines[i]
        if not (red and ERROR_WORDS.search(text)):
            continue
        if reply and any(reply.search(t) for t, _ in lines[i + 1:]):
            return None
        # A long message wraps onto the lines next to it, all red, no gap.
        first = last = i
        while first > 0 and lines[first - 1][1]:
            first -= 1
        while last + 1 < len(lines) and lines[last + 1][1]:
            last += 1
        return " ".join(t.strip() for t, _ in lines[first:last + 1])[:300]
    return None


def step(
    registry: dict[str, dict],
    observations: list[Observation],
    now: float,
    interval: float,
    grace: float,
) -> list[Notification]:
    """Advance each agent's status from a fresh round of observations.

    Mutates `registry[user_id]` in place and returns the attention
    notifications that crossed the grace threshold this tick. Registry
    rows for users not present in `observations` are dropped.
    """
    notifications: list[Notification] = []
    seen: set[str] = set()

    for obs in observations:
        seen.add(obs.user_id)
        prev = registry.get(obs.user_id)
        prev_status = prev["status"] if prev else None
        prev_hash = prev["hash"] if prev else None
        prev_changed_at = prev["changed_at"] if prev else now
        prev_since = prev["since"] if prev else now
        prev_detail = prev["detail"] if prev else None
        prev_notified = prev["notified"] if prev else False

        detail: str | None = None
        error: str | None = None
        snap = prev_hash
        changed_at = prev_changed_at

        if not obs.pane_alive:
            status = "stopped"
        elif obs.capture is None:
            status = "unknown"
        else:
            snap = snapshot_hash(obs.capture)
            if snap != prev_hash:
                status = "working"
                changed_at = now
            elif now - prev_changed_at < 2 * interval:
                # A pane is not "idle" the instant it stops changing.
                status = prev_status or "working"
                detail = prev_detail if status == "needs_attention" else None
            else:
                matched = _attention_detail(obs.flavor, obs.capture)
                if matched is not None:
                    status = "needs_attention"
                    detail = matched
                else:
                    status = "idle"
            # Only a still screen: a working agent has got past any error.
            if status != "working" and obs.colored is not None:
                error = error_detail(obs.flavor, obs.colored)

        status_changed = status != prev_status
        since = now if status_changed else prev_since

        if status == "needs_attention":
            notified = False if status_changed else prev_notified
            if not notified and now - since >= grace:
                notifications.append(Notification(obs.user_id, detail or ""))
                notified = True
        else:
            notified = False

        registry[obs.user_id] = {
            "hash": snap,
            "changed_at": changed_at,
            "status": status,
            "detail": detail,
            "error": error,
            "since": since,
            "notified": notified,
        }

    for user_id in list(registry):
        if user_id not in seen:
            del registry[user_id]

    return notifications
