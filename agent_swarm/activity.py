"""Agent activity classification for the dashboard monitor.

Pure functions plus one registry-updating step function, so tests never
need the monitor loop or tmux. The server's monitor loop feeds captures
in as Observations and records the returned Notifications.
"""

from __future__ import annotations

import hashlib
import re
from typing import NamedTuple


class Observation(NamedTuple):
    user_id: str
    flavor: str | None
    pane_alive: bool
    capture: str | None  # None means the capture failed this tick


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
            "since": since,
            "notified": notified,
        }

    for user_id in list(registry):
        if user_id not in seen:
            del registry[user_id]

    return notifications
